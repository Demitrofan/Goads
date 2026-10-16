"""
Сервис объявлений (жильё, байки, барахолка): один процесс вместо четырёх скриптов.

Каждый цикл (по умолчанию раз в 10 минут):
  1. Сбор:    новые сообщения из каналов tg_urls → таблица Post.
              Продолжает с последнего сохранённого сообщения, ничего не теряет.
  2. Дубли:   одинаковый текст (без ссылок, @ников и телефонов) → в уже известное объявление,
              без вызова GPT.
  3. Разбор:  остальное → GPT (OpenRouter) → Listing. Мусор помечается и не показывается.
              Похожее объявление (тот же посёлок, цена, комнаты, близкий текст) склеивается.
  4. Фото:    до 6 фото на объявление → media/photos/<id>/, уменьшенные до 1280 px.

Запуск из корня проекта:
  venv/Scripts/python services/ads/service.py           # работать постоянно
  venv/Scripts/python services/ads/service.py --once    # один цикл и выход
"""

import argparse
import hashlib
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent / "parser"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "goads.settings")

import django  # noqa: E402

django.setup()

from django.conf import settings  # noqa: E402
from django.db.models import Max  # noqa: E402
from loguru import logger  # noqa: E402
from PIL import Image  # noqa: E402
from telethon import functions  # noqa: E402
from telethon.errors import FloodWaitError  # noqa: E402
from telethon.sync import TelegramClient  # noqa: E402
from telethon.tl.types import InputPeerChannel, MessageMediaDocument, MessageMediaPhoto  # noqa: E402

from ads.models import Listing, Photo, Post  # noqa: E402
from llm import parse_ad  # noqa: E402
from moto.models import MotoListing, MotoPhoto, model_info  # noqa: E402
from stuff.models import StuffListing, StuffPhoto  # noqa: E402
from tg_urls import tg_urls as rent_urls  # noqa: E402


def _load_urls(path: Path) -> list:
    scope = {}
    exec(path.read_text(encoding="utf-8"), scope)
    return scope["tg_urls"]


# Каналы жилья, байков и барахолки собираются вместе: GPT сам решает, что это за объявление
moto_urls = _load_urls(ROOT / "services" / "moto" / "parser" / "tg_urls.py")
stuff_urls = _load_urls(ROOT / "services" / "stuff" / "parser" / "tg_urls.py")
tg_urls = list(dict.fromkeys(u.rstrip("/") for u in rent_urls + moto_urls + stuff_urls))

# Вид объявления → (таблица, таблица фото, поле в Post, папка фото внутри media/photos)
SECTIONS = {
    "rent": (Listing, Photo, "listings", ""),
    "bike": (MotoListing, MotoPhoto, "motos", "moto"),
    "sale": (StuffListing, StuffPhoto, "stuffs", "stuff"),
}


def section_of(obj):
    return next(sec for sec in SECTIONS.values() if isinstance(obj, sec[0]))


def linked_listings(post) -> list:
    """Объявления, к которым привязано сообщение (любого раздела; у прайс-листа их несколько)."""
    return [obj for _, _, field, _ in SECTIONS.values() for obj in getattr(post, field).all()]

# ───────────────────────────────
# Настройки
# ───────────────────────────────

INTERVAL_MIN = 10            # пауза между циклами
FIRST_RUN_DAYS = 2           # сколько дней истории забрать при первом запуске канала
MIN_TEXT_LEN = 60            # короче — точно не объявление
DUP_WINDOW_DAYS = 30         # окно поиска дублей
MAX_AGE_DAYS = 7             # сообщения старше — не разбираем (неактуальны), помечаем мусором "old"
LLM_WORKERS = 8              # сколько сообщений отправлять в GPT одновременно
MAX_PHOTOS = 6
PHOTO_MAX_SIDE = 1280

SESSION = str(ROOT / "media_session")
API_ID = int(os.environ["TG_API_ID_2"])
API_HASH = os.environ["TG_API_HASH_2"]

(ROOT / "logs").mkdir(exist_ok=True)
logger.add(ROOT / "logs" / "ads_service.log", rotation="5 MB", retention=5,
           encoding="utf-8", format="{time:YYYY-MM-DD HH:mm:ss} | {level: <7} | {message}")


# ───────────────────────────────
# Текст
# ───────────────────────────────

_URL = re.compile(r"https?://\S+|t\.me/\S+|www\.\S+", re.I)
_MENTION = re.compile(r"@\w+")
_PHONE = re.compile(r"\+?\d[\d\s\-()]{8,}\d")
_NON_WORD = re.compile(r"[^\w]+")


def normalize(text: str) -> str:
    """Текст без ссылок, ников, телефонов, эмодзи и знаков: для сравнения дублей."""
    t = text.lower()
    t = _URL.sub(" ", t)
    t = _MENTION.sub(" ", t)
    t = _PHONE.sub(" ", t)
    t = _NON_WORD.sub(" ", t)
    return " ".join(t.split())


def text_hash(text: str) -> str:
    return hashlib.sha1(normalize(text).encode()).hexdigest()


def channel_name(url: str) -> str:
    return url.rstrip("/").rsplit("/", 1)[-1]


def is_video(m) -> bool:
    doc = m.media.document if isinstance(m.media, MessageMediaDocument) else None
    return bool(doc and (doc.mime_type or "").startswith("video/") and doc.thumbs)


def has_picture(m) -> bool:
    """Фото или видео с обложкой: из видео берём превью-картинку."""
    return isinstance(m.media, MessageMediaPhoto) or is_video(m)


# ───────────────────────────────
# 1. Сбор
# ───────────────────────────────

def resolve_channels(client) -> dict:
    """username → InputPeerChannel. Запрашиваем напрямую: кэш сессии бывает устаревшим."""
    peers = {}
    for url in tg_urls:
        name = channel_name(url)
        try:
            r = client(functions.contacts.ResolveUsernameRequest(username=name))
            ch = r.chats[0]
            peers[name] = InputPeerChannel(ch.id, ch.access_hash)
        except FloodWaitError as e:
            logger.warning(f"FloodWait {e.seconds} с при поиске @{name}, жду")
            time.sleep(e.seconds + 1)
        except Exception as e:
            logger.error(f"Канал @{name} недоступен: {type(e).__name__}: {e}")
        time.sleep(1)
    logger.info(f"Каналов доступно: {len(peers)} из {len(tg_urls)}")
    return peers


def collect(client, peers: dict) -> dict:
    """Сохраняет новые сообщения. Возвращает {post.pk: [сообщения с фото]} для скачивания."""
    media = {}
    since = datetime.now(timezone.utc) - timedelta(days=FIRST_RUN_DAYS)
    total = 0

    for name, peer in peers.items():
        last_id = Post.objects.filter(channel=name).aggregate(m=Max("msg_id"))["m"] or 0
        albums = {}   # grouped_id → список сообщений альбома
        singles = []
        try:
            for m in client.iter_messages(peer, min_id=last_id, limit=3000):
                if not last_id and m.date < since:
                    break
                if m.grouped_id:
                    albums.setdefault(m.grouped_id, []).append(m)
                else:
                    singles.append([m])
        except FloodWaitError as e:
            logger.warning(f"FloodWait {e.seconds} с на @{name}, жду")
            time.sleep(e.seconds + 1)
            continue
        except Exception as e:
            logger.error(f"Ошибка чтения @{name}: {type(e).__name__}: {e}")
            continue

        for group in list(albums.values()) + singles:
            group.sort(key=lambda x: x.id)
            text = next((x.message for x in group if x.message), "") or ""
            text = text.strip()
            if len(text) < MIN_TEXT_LEN:
                continue
            first = group[0]
            post, created = Post.objects.get_or_create(
                channel=name, msg_id=first.id,
                defaults=dict(
                    grouped_id=str(first.grouped_id) if first.grouped_id else None,
                    text=text, text_hash=text_hash(text), date=first.date,
                ))
            if created:
                total += 1
                photos = [x for x in group if has_picture(x)]
                if photos:
                    media[post.pk] = photos
        time.sleep(1)

    logger.info(f"Сбор: новых сообщений {total}")
    return media


# ───────────────────────────────
# 2–3. Дубли и разбор
# ───────────────────────────────

def attach(post: Post, obj, status=Post.DUPLICATE):
    """Привязывает сообщение к объявлению любого раздела (жильё, байк, барахолка)."""
    getattr(post, section_of(obj)[2]).add(obj)
    post.status = status
    post.save(update_fields=["status"])
    if post.date > obj.last_seen:
        obj.last_seen = post.date
        obj.save(update_fields=["last_seen"])


def find_exact_duplicate(post: Post):
    """Тот же нормализованный текст за последние DUP_WINDOW_DAYS дней."""
    since = post.date - timedelta(days=DUP_WINDOW_DAYS)
    return (Post.objects.filter(text_hash=post.text_hash, date__gte=since)
            .exclude(pk=post.pk).exclude(status=Post.NEW)
            .order_by("-date").first())


def _similar_text(candidates, text):
    norm = normalize(text)
    for c in candidates[:50]:
        if SequenceMatcher(None, norm, normalize(c.text)).ratio() >= 0.75:
            return c
    return None


def find_similar_listing(data: dict, text: str, date):
    """Похожее жильё: тот же посёлок, цена и комнаты, текст совпадает на 75%+."""
    if not (data["village"] and (data["price_month"] or data["price_day"])):
        return None
    return _similar_text(Listing.objects.filter(
        village=data["village"], rooms=data["rooms"],
        price_month=data["price_month"], price_day=data["price_day"],
        last_seen__gte=date - timedelta(days=DUP_WINDOW_DAYS)), text)


def find_similar_moto(data: dict, text: str, date):
    """Похожий байк: та же модель и цены, текст совпадает на 75%+."""
    if not data["bike_model"]:
        return None
    return _similar_text(MotoListing.objects.filter(
        model_name=data["bike_model"], price_month=data["price_month"],
        price_day=data["price_day"], price_sell=data["price_sell"],
        last_seen__gte=date - timedelta(days=DUP_WINDOW_DAYS)), text)


def find_similar_stuff(data: dict, text: str, date):
    """Похожая вещь: то же название и цена, текст совпадает на 75%+."""
    if not data["item_title"]:
        return None
    return _similar_text(StuffListing.objects.filter(
        title=data["item_title"], price=data["price_sell"],
        last_seen__gte=date - timedelta(days=DUP_WINDOW_DAYS)), text)


FIND_SIMILAR = {"rent": find_similar_listing, "bike": find_similar_moto, "sale": find_similar_stuff}


def trash_reason(data: dict) -> str:
    kind = data["kind"]
    if kind not in SECTIONS:
        return kind
    if data["many_objects"] and not any(not trash_reason(it) for it in data["items"]):
        # список, из которого не вышло ни одной годной позиции
        return {"rent": "many_objects", "bike": "bike_many", "sale": "sale_many"}[kind]
    if data["many_objects"]:
        return ""
    if kind == "sale":
        if not data["item_title"]:
            return "sale_no_title"
        if not (data["price_sell"] or data["is_free"]):
            return "sale_no_price"
        return ""
    has_price = data["price_month"] or data["price_day"] or (kind == "bike" and data["price_sell"])
    if not has_price:
        return "no_price" if kind == "rent" else "bike_no_price"
    return ""


_SPECS = None


def bike_specs(name: str):
    """Объём, мощность и вес из справочника моделей: точное совпадение или очень похожее имя."""
    global _SPECS
    if _SPECS is None:
        _SPECS = {normalize(m.moto_models_name or ""): m for m in model_info.objects.all()}
    if not name:
        return None
    key = normalize(name)
    if key in _SPECS:
        return _SPECS[key]
    # Числа в названии (125, 160, 350) должны совпадать: SR 125 и SR 160 — разные модели
    # (в справочнике без числа — например «Yamaha Fascino» — подходит любая версия)
    digits = re.findall(r"\d+", key)
    candidates = [k for k in _SPECS if re.findall(r"\d+", k) in (digits, [])]
    best = max(candidates, key=lambda k: SequenceMatcher(None, key, k).ratio(), default=None)
    if best and SequenceMatcher(None, key, best).ratio() >= 0.85:
        return _SPECS[best]
    return None


def create_listing(post: Post, data: dict):
    if data["kind"] == "sale":
        return StuffListing.objects.create(
            title=data["item_title"], category=data["item_category"],
            condition=data["item_condition"], price=data["price_sell"], is_free=data["is_free"],
            village=data["village"], text=post.text, first_seen=post.date, last_seen=post.date)
    if data["kind"] == "bike":
        spec = bike_specs(data["bike_model"])
        return MotoListing.objects.create(
            model_name=data["bike_model"], kind=data["bike_kind"], year=data["bike_year"],
            engine=spec.engine if spec else None,
            horse_power=spec.horse_power if spec else None,
            weight=spec.weight if spec else None,
            price_month=data["price_month"], price_day=data["price_day"],
            price_sell=data["price_sell"], agent_fee=data["agent_fee"],
            has_helmet=data["has_helmet"], has_delivery=data["has_delivery"],
            need_deposit=data["need_deposit"], need_passport=data["need_passport"],
            village=data["village"], text=post.text, first_seen=post.date, last_seen=post.date)
    return Listing.objects.create(
        village=data["village"], price_month=data["price_month"],
        price_day=data["price_day"], agent_percent=data["agent_percent"],
        rooms=data["rooms"], text=post.text,
        first_seen=post.date, last_seen=post.date,
        **{f: data[f] for f in ("has_ac", "has_wifi", "has_fridge", "has_kitchen",
                                "has_washing_machine", "has_dishes", "has_hot_water",
                                "owners_nearby")},
    )


def prefetch_answers(batch: list, model: str) -> dict:
    """Параллельно спрашивает GPT по сообщениям пачки, которым он понадобится.
    Точные дубли (уже известные или повтор внутри пачки) пропускаем — для них GPT не нужен."""
    need, seen = [], set()
    for post in batch:
        if post.text_hash in seen or find_exact_duplicate(post):
            continue
        seen.add(post.text_hash)
        need.append(post)
    with ThreadPoolExecutor(LLM_WORKERS) as pool:
        results = pool.map(lambda p: parse_ad(p.text, model), need)
        return {p.pk: data for p, data in zip(need, results)}


def process_new(model: str, limit: int | None = None) -> list:
    """Разбирает новые сообщения. Возвращает [(post, объявление)] новых объявлений для фото."""
    created = []
    stats = dict(dup=0, trash=0, rent=0, bike=0, sale=0, merged=0, error=0)

    pending = Post.objects.filter(status__in=[Post.NEW, Post.ERROR])
    old = pending.filter(date__lt=datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS))
    stats["trash"] += old.update(status=Post.TRASH, trash_reason="old")

    # ERROR тоже берём: повторная попытка после сбоя OpenRouter
    posts = list(pending.order_by("date")[:limit])
    answers = {}   # post.pk → ответ GPT, запрошенный заранее пачкой
    for i, post in enumerate(posts):
        if i % (LLM_WORKERS * 4) == 0:
            answers = prefetch_answers(posts[i:i + LLM_WORKERS * 4], model)

        prev = find_exact_duplicate(post)
        if prev:
            if linked_listings(prev):
                for obj in linked_listings(prev):
                    attach(post, obj)
                stats["dup"] += 1
            else:
                post.status, post.trash_reason = Post.TRASH, prev.trash_reason or "dup_trash"
                post.save(update_fields=["status", "trash_reason"])
                stats["trash"] += 1
            continue

        data = answers[post.pk] if post.pk in answers else parse_ad(post.text, model)
        logger.debug(f"{post}: {data}")
        if data is None:
            post.status = Post.ERROR
            post.save(update_fields=["status"])
            stats["error"] += 1
            continue

        reason = trash_reason(data)
        if reason:
            post.status, post.trash_reason = Post.TRASH, reason
            post.save(update_fields=["status", "trash_reason"])
            stats["trash"] += 1
            continue

        # Прайс-лист → своя карточка на каждую годную позицию, обычное объявление → одна
        items = [it for it in data["items"] if not trash_reason(it)] if data["many_objects"] else [data]
        is_new = False
        for item in items:
            similar = FIND_SIMILAR[item["kind"]](item, post.text, post.date)
            if similar:
                attach(post, similar)
                stats["merged"] += 1
                continue
            obj = create_listing(post, item)
            attach(post, obj)
            created.append((post, obj))
            stats[item["kind"]] += 1
            is_new = True
        if is_new:
            post.status = Post.PARSED
            post.save(update_fields=["status"])

    logger.info("Разбор: жильё {rent}, байки {bike}, барахолка {sale}, склеено похожих {merged}, "
                "точных дублей {dup}, мусор {trash}, ошибок {error}".format(**stats))
    return created


# ───────────────────────────────
# 4. Фото
# ───────────────────────────────

def save_photos(client, peers: dict, created: list, media: dict):
    saved = {}   # post.pk → пути уже скачанных фото: позиции одного прайс-листа делят общие фото
    for post, obj in created:
        _, photo_model, _, subfolder = section_of(obj)
        if post.pk in saved:
            photo_model.objects.bulk_create([photo_model(listing=obj, path=p) for p in saved[post.pk]])
            continue
        saved[post.pk] = []

        msgs = media.get(post.pk)
        if msgs is None and post.channel in peers:
            # Сообщение собрано в прошлом запуске: забираем альбом заново
            ids = list(range(post.msg_id, post.msg_id + 10))
            got = [m for m in client.get_messages(peers[post.channel], ids=ids) if m]
            msgs = [m for m in got if has_picture(m)
                    and (m.id == post.msg_id or (post.grouped_id and str(m.grouped_id) == post.grouped_id))]
        if not msgs:
            continue

        # не "ads": блокировщики рекламы режут такие адреса
        folder = Path(settings.MEDIA_ROOT) / "photos" / subfolder / str(obj.pk)
        folder.mkdir(parents=True, exist_ok=True)
        for i, m in enumerate(msgs[:MAX_PHOTOS], start=1):
            video = is_video(m)
            target = folder / (f"v{i}.jpg" if video else f"{i}.jpg")   # v — превью видео
            try:
                raw = m.download_media(file=bytes, thumb=-1) if video else m.download_media(file=bytes)
                img = Image.open(BytesIO(raw)).convert("RGB")
                img.thumbnail((PHOTO_MAX_SIDE, PHOTO_MAX_SIDE))
                img.save(target, "JPEG", quality=80, optimize=True)
                path = target.relative_to(settings.MEDIA_ROOT).as_posix()
                photo_model.objects.create(listing=obj, path=path)
                saved[post.pk].append(path)
            except Exception as e:
                logger.warning(f"Фото {post}: {type(e).__name__}: {e}")
    logger.info(f"Фото: обработано объявлений {len(created)}")


# ───────────────────────────────
# Главный цикл
# ───────────────────────────────

def run_cycle(client, peers, model, limit=None):
    media = collect(client, peers)
    created = process_new(model, limit)
    save_photos(client, peers, created, media)


def single_instance():
    """Блокировка файла: второй экземпляр сервиса получит None. Снимается сама при выходе."""
    f = open(ROOT / "logs" / "service.lock", "w")
    try:
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        return None
    return f


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="один цикл и выход")
    ap.add_argument("--limit", type=int, help="разобрать не больше N сообщений за цикл")
    args = ap.parse_args()

    lock = single_instance()
    if lock is None:
        logger.warning("Сервис уже запущен (одна Telegram-сессия на двоих ломает связь) — выхожу")
        return

    model = settings.LLM_MODEL
    logger.info(f"Старт сервиса, модель {model}")

    client = TelegramClient(SESSION, API_ID, API_HASH)
    client.connect()
    if not client.is_user_authorized():
        logger.error("Telegram-сессия не авторизована. Нужен повторный вход.")
        return

    try:
        peers = resolve_channels(client)
        while True:
            try:
                run_cycle(client, peers, model, args.limit)
            except RuntimeError as e:   # нет денег / неверный ключ OpenRouter
                logger.error(str(e))
                if args.once:
                    break
            except Exception:
                logger.exception("Ошибка цикла")
            if args.once:
                break
            logger.info(f"Пауза {INTERVAL_MIN} мин")
            time.sleep(INTERVAL_MIN * 60)
    finally:
        client.disconnect()


if __name__ == "__main__":
    main()
