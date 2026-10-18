"""Telegram-бот уведомлений: подписка на поиск и сообщения о новых объявлениях.

Как работает:
1. На странице списка кнопка «Подписаться» сохраняет текущие фильтры (Subscription без чата)
   и ведёт на t.me/<бот>?start=<код>.
2. Человек жмёт «Старт» — Telegram присылает /start <код> на наш адрес (webhook), подписка
   привязывается к его чату.
3. Сборщик после каждого цикла вызывает notify(): новые объявления проверяются фильтрами
   каждой подписки теми же функциями, что и страницы списков.

Ключи в .env: TG_BOT_TOKEN (от @BotFather), TG_BOT_NAME (имя бота без @),
TG_BOT_SECRET (любая длинная строка: ею Telegram подписывает запросы к webhook).
"""
import json
import os
import secrets
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

from django.http import QueryDict
from django.urls import reverse

from ads.currency import CURRENCIES, convert, get_rates
from ads.models import Listing, Subscription
from ads.seo import SITE_URL

MAX_PER_CHAT = 10      # подписок у одного человека
MAX_PER_NOTIFY = 10    # объявлений в одной пачке по подписке; больше — одна ссылка на список
FRESH_HOURS = 24       # о старых сообщениях (догрузка истории) не пишем


def token() -> str:
    return os.environ.get("TG_BOT_TOKEN", "").strip()


def bot_name() -> str:
    return os.environ.get("TG_BOT_NAME", "").strip().lstrip("@")


def enabled() -> bool:
    return bool(token() and bot_name())


def api(method: str, **params):
    """Вызов Telegram Bot API. Ошибки не роняют сборщик и сайт: возвращается None."""
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token()}/{method}",
        data=json.dumps(params).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read() or b"{}")
    except Exception:
        return None


def send(chat_id: int, text: str):
    return api("sendMessage", chat_id=chat_id, text=text, parse_mode="HTML",
               link_preview_options={"prefer_large_media": True})


# ─────────────── разделы: те же фильтры, что на страницах списков ───────────────

class _FakeRequest:
    def __init__(self, query: str):
        self.GET = QueryDict(query)


def section_conf(section: str, region: str):
    """Раздел → (форма из адреса, выборка, адрес списка, адрес объявления, модель)."""
    if section == "rent":
        from ads import views
        conf = views.REGIONS[region]
        return dict(
            form=lambda q: views.get_form_data(_FakeRequest(q), conf["rooms"], conf["period"]),
            queryset=lambda form, cur: views.build_queryset(form, cur, region)[0],
            list=conf["list"], details=conf["details"], model=Listing,
            where=conf.get("brand") or "Гоа", rooms=dict(conf["rooms"]))
    if section == "bike":
        from moto import views
        from moto.models import MotoListing
        return dict(form=lambda q: views.get_form_data(_FakeRequest(q)),
                    queryset=lambda form, cur: views.build_queryset(form, cur)[0],
                    list="moto:search_properties_moto", details="moto:details_moto",
                    model=MotoListing, where="Гоа", kinds=dict(MotoListing.KINDS))
    from stuff import views
    from stuff.models import StuffListing
    return dict(form=lambda q: views.get_form_data(_FakeRequest(q)),
                queryset=lambda form, cur: views.build_queryset(form, cur),
                list="stuff:search_properties_stuff", details="stuff:details_stuff",
                model=StuffListing, where="Гоа", cats=dict(StuffListing.CATEGORIES))


def money(rupees, cur: str, rates: dict) -> str:
    value = convert(rupees, cur, rates)
    if value is None:
        return ""
    number = "{:,}".format(value).replace(",", " ")
    symbol = "Б" if cur == "BYN" else CURRENCIES[cur]
    return f"{symbol}{number}" if cur == "USD" else f"{number} {symbol}"


def describe(section: str, region: str, query: str, currency: str) -> str:
    """Человеческое описание подписки: «Жильё · Грузия · Сабуртало · 2-комнатная · до $900»."""
    c = section_conf(section, region)
    form = c["form"](query)
    parts = [dict(Subscription.SECTIONS)[section], c["where"]]
    if form.get("village"):
        parts.append(form["village"])
    if form.get("rooms"):
        parts.append(", ".join(c["rooms"].get(r, r) for r in form["rooms"]))
    if form.get("kinds"):
        parts.append(", ".join(c["kinds"].get(k, k) for k in form["kinds"]).lower())
    if form.get("model"):
        parts.append(form["model"])
    if form.get("categories"):
        parts.append(", ".join(c["cats"].get(k, k) for k in form["categories"]).lower())
    if form.get("free"):
        parts.append("даром")
    symbol = "Б" if currency == "BYN" else CURRENCIES.get(currency, "")
    fmt = (lambda n: f"${n}") if currency == "USD" else (lambda n: f"{n} {symbol}")
    lo, hi = form.get("price_from", ""), form.get("price_to", "")
    if lo.isdigit() or hi.isdigit():
        span = " ".join(([f"от {fmt(lo)}"] if lo.isdigit() else []) + ([f"до {fmt(hi)}"] if hi.isdigit() else []))
        per = {"daily": "/сутки", "monthly": "/мес"}.get(form.get("rent_period"), "")
        parts.append(span + per)
    if form.get("words"):
        parts.append(f"«{form['words']}»")
    return " · ".join(parts)


def create(section: str, region: str, query: str, currency: str) -> Subscription:
    return Subscription.objects.create(
        code=secrets.token_urlsafe(9), section=section, region=region, query=query,
        currency=currency if currency in CURRENCIES else "RUB",
        title=describe(section, region, query, currency)[:300])


# ─────────────── входящие сообщения (webhook) ───────────────

HELP = ("Я присылаю новые объявления с сайта goadoska.ru под ваши фильтры.\n\n"
        "Как подписаться: откройте на сайте жильё, байки или барахолку, выберите фильтры "
        "и нажмите «🔔 Подписаться на этот поиск».\n\n"
        "/list — мои подписки")


def handle_update(update: dict):
    msg = update.get("message") or {}
    chat = (msg.get("chat") or {}).get("id")
    text = (msg.get("text") or "").strip()
    if not chat or not text.startswith("/"):
        if chat:
            send(chat, HELP)
        return
    cmd, _, arg = text.partition(" ")
    cmd = cmd.split("@")[0]

    if cmd == "/start" and arg:
        sub = Subscription.objects.filter(code=arg.strip()).first()
        if not sub:
            send(chat, "Ссылка устарела. Нажмите «Подписаться» на сайте ещё раз.")
        elif sub.chat_id and sub.chat_id != chat:
            send(chat, "Эта ссылка уже использована. Нажмите «Подписаться» на сайте ещё раз.")
        elif Subscription.objects.filter(chat_id=chat).exclude(pk=sub.pk).count() >= MAX_PER_CHAT:
            send(chat, f"У вас уже {MAX_PER_CHAT} подписок — это максимум. Удалите лишние: /list")
        else:
            sub.chat_id = chat
            sub.save(update_fields=["chat_id"])
            send(chat, f"✅ Подписка оформлена:\n<b>{escape(sub.title)}</b>\n\n"
                       "Как только появится подходящее объявление — пришлю.\n/list — мои подписки")
    elif cmd == "/admin":
        from ads import monitor
        if chat == monitor.admin_chat():
            send(chat, "Вы владелец: сюда приходят сводка и тревоги.\n/report — сводка сейчас")
        else:
            # Номер чата владелец вписывает в серверный .env (TG_ADMIN_CHAT_ID) — бот сам права не выдаёт
            who = msg.get("chat") or {}
            with open(monitor.STATE.parent / "admin_requests.log", "a", encoding="utf-8") as f:
                f.write(f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M} {chat} "
                        f"@{who.get('username', '')} {who.get('first_name', '')}\n")
            send(chat, f"Номер вашего чата: <code>{chat}</code>\n"
                       "Если вы владелец сайта — впишите его в .env как TG_ADMIN_CHAT_ID.")
    elif cmd == "/report":
        from ads import monitor
        if chat == monitor.admin_chat():
            send(chat, monitor.report(save=False))
        else:
            send(chat, HELP)
    elif cmd == "/list":
        subs = Subscription.objects.filter(chat_id=chat).order_by("pk")
        if not subs:
            send(chat, "Подписок нет.\n\n" + HELP)
            return
        lines = [f"{i}. {escape(s.title)}\n   отписаться: /stop_{s.pk}" for i, s in enumerate(subs, 1)]
        send(chat, "Ваши подписки:\n\n" + "\n\n".join(lines) + "\n\nОтписаться от всех: /stop")
    elif cmd.startswith("/stop_"):
        n, _ = Subscription.objects.filter(chat_id=chat, pk=cmd[6:] if cmd[6:].isdigit() else 0).delete()
        send(chat, "Подписка удалена." if n else "Такой подписки нет. /list — мои подписки")
    elif cmd == "/stop":
        n, _ = Subscription.objects.filter(chat_id=chat).delete()
        send(chat, f"Удалено подписок: {n}." if n else "Подписок нет.")
    else:
        send(chat, HELP)


def escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ─────────────── рассылка (вызывает сборщик) ───────────────

def item_line(section: str, obj, cur: str, rates: dict, rooms: dict) -> str:
    if section == "rent":
        what = rooms.get(obj.rooms, obj.rooms or "Жильё")
        price = (f"{money(obj.price_month, cur, rates)}/мес" if obj.price_month
                 else f"{money(obj.price_day, cur, rates)}/сутки" if obj.price_day else "")
        bits = ["🏠 " + (obj.village or "Место не указано"), what, price]
    elif section == "bike":
        price = (f"{money(obj.price_month, cur, rates)}/мес" if obj.price_month
                 else f"{money(obj.price_day, cur, rates)}/сутки" if obj.price_day
                 else f"продажа {money(obj.price_sell, cur, rates)}" if obj.price_sell else "")
        bits = ["🛵 " + (obj.model_name or "Байк"), obj.village or "", price]
    else:
        price = "даром" if obj.is_free else money(obj.price, cur, rates)
        bits = ["🛍 " + obj.title, obj.village or "", price]
    return " · ".join(escape(b) for b in bits if b)


def notify(created: list) -> int:
    """created — [(сообщение, объявление)] из цикла сборщика. Возвращает число отправленных."""
    # «Подписаться» нажали, а «Старт» у бота — нет: через сутки такие подписки не нужны
    Subscription.objects.filter(chat_id__isnull=True,
                                created__lt=datetime.now(timezone.utc) - timedelta(days=1)).delete()
    if not enabled() or not created:
        return 0
    fresh_since = datetime.now(timezone.utc) - timedelta(hours=FRESH_HOURS)
    new = {}   # раздел → {регион → [pk]}
    for post, obj in created:
        if post.date < fresh_since:
            continue
        section = {"Listing": "rent", "MotoListing": "bike", "StuffListing": "sale"}[type(obj).__name__]
        region = getattr(obj, "region", Listing.GOA)
        new.setdefault(section, {}).setdefault(region, set()).add(obj.pk)

    rates = get_rates()
    total = 0
    for sub in Subscription.objects.filter(chat_id__isnull=False):
        ids = new.get(sub.section, {}).get(sub.region)
        if not ids:
            continue
        c = section_conf(sub.section, sub.region)
        form = c["form"](sub.query)
        matches = list(c["queryset"](form, sub.currency).filter(pk__in=ids).order_by("-last_seen"))
        if not matches:
            continue
        lines = []
        for obj in matches[:MAX_PER_NOTIFY]:
            url = SITE_URL + reverse(c["details"], args=[obj.pk])
            lines.append(f"{item_line(sub.section, obj, sub.currency, rates, c.get('rooms', {}))}\n{url}")
        more = len(matches) - MAX_PER_NOTIFY
        if more > 0:
            url = SITE_URL + reverse(c["list"]) + ("?" + sub.query if sub.query else "")
            lines.append(f"…и ещё {more}: {url}")
        head = f"🔔 Новое по подписке «{escape(sub.title)}»:"
        res = send(sub.chat_id, head + "\n\n" + "\n\n".join(lines))
        if res and not res.get("ok") and res.get("error_code") == 403:
            sub.delete()   # человек заблокировал бота — подписка больше не нужна
            continue
        sub.sent += len(matches)
        sub.save(update_fields=["sent"])
        total += len(matches)
    return total


def set_webhook() -> dict | None:
    """Сообщает Telegram, куда присылать сообщения боту (вызывается командой set_bot_webhook)."""
    return api("setWebhook", url=f"{SITE_URL}/tg/hook/", secret_token=os.environ["TG_BOT_SECRET"],
               allowed_updates=["message"], drop_pending_updates=True)
