"""Сообщения владельцу через бота: утренняя сводка и тревога при сбое.

Чат владельца — TG_ADMIN_CHAT_ID в .env (номер чата бот сообщает в ответ на /admin).
- alert(): сборщик сообщает о сбое (нет денег у OpenRouter, сессия Telegram, ошибка цикла).
  Одна и та же тревога — не чаще раза в ALERT_REPEAT_HOURS; после починки приходит «✅ снова работает».
- watchdog(): раз в 10 минут (goads-watchdog.timer) — жив ли сборщик, хватает ли денег на GPT.
- report(): сводка за сутки (goads-report.timer, утром) и по команде /report.
Состояние (какие тревоги уже отправлены, счётчики прошлой сводки) — logs/monitor.json.
"""
import json
import os
import subprocess
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from django.conf import settings
from django.db.models import Count, Sum

from ads import bot

STATE = Path(settings.BASE_DIR) / "logs" / "monitor.json"
HEARTBEAT = Path(settings.BASE_DIR) / "logs" / "heartbeat"   # сборщик трогает после каждого цикла
ALERT_REPEAT_HOURS = 3
STALE_MIN = 40          # цикла не было дольше — тревога
LOW_BALANCE_USD = 1.0   # денег на GPT меньше — тревога


def admin_chat() -> int | None:
    value = os.environ.get("TG_ADMIN_CHAT_ID", "").strip()
    return int(value) if value.lstrip("-").isdigit() else None


def _load() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save(state: dict):
    STATE.parent.mkdir(exist_ok=True)
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(STATE)


def send_admin(text: str) -> bool:
    chat = admin_chat()
    if not (bot.token() and chat):
        return False
    res = bot.api("sendMessage", chat_id=chat, text=text, parse_mode="HTML",
                  link_preview_options={"is_disabled": True})
    return bool(res and res.get("ok"))


def alert(key: str, text: str):
    """Тревога владельцу. key — вид сбоя: повтор того же вида не чаще раза в ALERT_REPEAT_HOURS."""
    state = _load()
    alerts = state.setdefault("alerts", {})
    now = datetime.now(timezone.utc)
    last = alerts.get(key)
    if last and now - datetime.fromisoformat(last) < timedelta(hours=ALERT_REPEAT_HOURS):
        return
    if send_admin("🚨 " + bot.escape(text)):
        alerts[key] = now.isoformat()
        _save(state)


def resolved(*keys: str):
    """Сбой прошёл: если о нём писали — сообщаем, что всё снова работает."""
    state = _load()
    alerts = state.get("alerts", {})
    gone = [k for k in keys if k in alerts]
    if not gone:
        return
    names = ", ".join(ALERT_NAMES.get(k, k) for k in gone)
    if send_admin(f"✅ Снова работает: {names}"):
        for k in gone:
            alerts.pop(k)
        _save(state)


ALERT_NAMES = {
    "stale": "сборщик", "service": "сборщик", "cycle": "цикл сбора", "llm": "GPT (OpenRouter)",
    "tg_auth": "Telegram-сессия", "balance": "баланс OpenRouter",
}


def beat():
    """Сборщик закончил цикл без сбоя."""
    HEARTBEAT.parent.mkdir(exist_ok=True)
    HEARTBEAT.write_text(datetime.now(timezone.utc).isoformat(), encoding="utf-8")
    resolved("stale", "service", "cycle", "llm", "tg_auth")


# ─────────────── OpenRouter: расходы и остаток ───────────────

def _openrouter(path: str) -> dict:
    key = (os.environ.get("LLM_API_KEY") or os.environ.get("OPENROUTER_API_KEY", "")).strip()
    req = urllib.request.Request("https://openrouter.ai/api/v1/" + path,
                                 headers={"Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.load(resp).get("data") or {}
    except Exception:
        return {}


def gpt_money() -> dict:
    """Потрачено за сутки/месяц и сколько осталось (меньшее из баланса и месячного лимита ключа)."""
    k, c = _openrouter("key"), _openrouter("credits")
    left = []
    if c.get("total_credits") is not None:
        left.append(c["total_credits"] - c.get("total_usage", 0))
    if k.get("limit_remaining") is not None:
        left.append(k["limit_remaining"])
    return dict(day=k.get("usage_daily"), month=k.get("usage_monthly"),
                left=min(left) if left else None)


# ─────────────── сторож ───────────────

def watchdog():
    if not admin_chat():
        return
    service = subprocess.run(["systemctl", "is-active", "goads-collector"],
                             capture_output=True, text=True).stdout.strip()
    try:
        last = datetime.fromisoformat(HEARTBEAT.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        last = None
    now = datetime.now(timezone.utc)
    if service not in ("active", "activating"):
        alert("service", f"Сборщик объявлений остановлен (служба: {service or '?'}).")
    elif last is None or now - last > timedelta(minutes=STALE_MIN):
        ago = f"{int((now - last).total_seconds() // 60)} мин" if last else "давно"
        alert("stale", f"Сборщик не завершал цикл {ago} (норма — раз в 10–25 мин). "
                       f"Журнал: logs/ads_service.log")
    else:
        resolved("stale", "service")

    left = gpt_money()["left"]
    if left is not None and left < LOW_BALANCE_USD:
        alert("balance", f"На OpenRouter осталось ${left:.2f} — пора пополнить, иначе разбор встанет.")
    elif left is not None:
        resolved("balance")


# ─────────────── сводка ───────────────

def report(save: bool = True) -> str:
    from ads.models import Listing, Post, Subscription
    from moto.models import MotoListing
    from stuff.models import StuffListing

    now = datetime.now(timezone.utc)
    since = now - timedelta(days=1)

    lines = ["📊 <b>Сводка goadoska.ru за сутки</b>", "", "<b>Новые объявления</b>"]
    rent = dict(Listing.objects.filter(first_seen__gte=since).values("region")
                .annotate(n=Count("id")).values_list("region", "n"))
    for code, name in Listing.REGIONS:
        lines.append(f"🏠 Жильё, {name}: {rent.get(code, 0)}")
    lines.append(f"🛵 Байки, Гоа: {MotoListing.objects.filter(first_seen__gte=since).count()}")
    lines.append(f"🛍 Барахолка, Гоа: {StuffListing.objects.filter(first_seen__gte=since).count()}")

    closed = sum(m.objects.filter(closed__gte=since).count() for m in (Listing, MotoListing, StuffListing))
    live = sum(m.objects.filter(closed__isnull=True, last_seen__gte=now - timedelta(days=14)).count()
               for m in (Listing, MotoListing, StuffListing))
    lines += ["", f"Снято (сдано/продано/удалено): {closed}",
              f"Актуальных за 2 недели: {live}",
              f"Сообщений собрано: {Post.objects.filter(date__gte=since).count()}"]

    subs = Subscription.objects.filter(chat_id__isnull=False)
    sent_total = subs.aggregate(s=Sum("sent"))["s"] or 0
    state = _load()
    prev = state.get("report", {})
    sent_day = sent_total - prev.get("sent", sent_total) if prev else None
    lines += ["", "<b>Бот</b>",
              f"Подписчиков: {subs.values('chat_id').distinct().count()}, подписок: {subs.count()}",
              "Отправлено объявлений: " + (f"{sent_day}" if sent_day is not None and sent_day >= 0
                                           else "— (считаю со следующей сводки)")]

    money = gpt_money()
    fmt = lambda v: f"${v:.2f}" if isinstance(v, (int, float)) else "?"
    # За сутки — разница месячного расхода с прошлой сводкой (usage_daily считается с 00:00 UTC)
    day, day_name = money["day"], "сегодня с 00:00 UTC"
    was = prev.get("gpt_month")
    if isinstance(money["month"], (int, float)) and isinstance(was, (int, float)) and money["month"] >= was:
        day, day_name = money["month"] - was, "с прошлой сводки"
    lines += ["", "<b>GPT (OpenRouter)</b>",
              f"Потрачено {day_name}: {fmt(day)}, за месяц: {fmt(money['month'])}",
              f"Осталось: {fmt(money['left'])}"]

    try:
        last = datetime.fromisoformat(HEARTBEAT.read_text(encoding="utf-8"))
        lines.append(f"\nПоследний цикл сбора: {int((now - last).total_seconds() // 60)} мин назад")
    except (OSError, ValueError):
        pass
    if save:
        state = _load()   # заново: сторож мог записать тревогу, пока считали сводку
        state["report"] = {"sent": sent_total, "gpt_month": money["month"], "at": now.isoformat()}
        _save(state)
    return "\n".join(lines)
