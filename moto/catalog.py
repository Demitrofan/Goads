"""Справочник моделей байков: GPT пишет названия как попало («Aerox», «Yamaha Aerox 155», «Honda Fascino»),
здесь они сводятся к одной модели — для фильтра «Модель» и картинки модели.

Картинка модели — static/vendor/img/bikes/<код>.jpg (4:3, например 800×600). Её показывают, когда своих
фото у объявления нет или фото общие на весь прайс-лист (на них могут быть другие байки).
Модель не узнали — общий скутер/мотоцикл (generic-scooter/generic-motorcycle), тип неизвестен — bikes/none.svg. Новая модель = строка в MODELS (+ картинка).
"""
import re
from functools import lru_cache
from pathlib import Path

from django.conf import settings

# (код, название, скутер/мотоцикл, шаблон). Порядок важен: первое совпадение побеждает,
# поэтому более точные шаблоны (X-ADV, CB350) стоят раньше общих (ADV, Classic).
MODELS = [
    # ── скутеры ──
    ("aerox", "Yamaha Aerox 155", "scooter", r"aerox"),
    ("fascino", "Yamaha Fascino 125", "scooter", r"fascino"),
    ("ray-zr", "Yamaha Ray ZR 125", "scooter", r"\bray\b"),
    ("activa", "Honda Activa", "scooter", r"activa"),
    ("dio", "Honda Dio", "scooter", r"\bdio\b"),
    ("navi", "Honda Navi", "scooter", r"\bnavi\b"),
    ("grazia", "Honda Grazia", "scooter", r"grazia"),
    ("ntorq", "TVS Ntorq 125", "scooter", r"ntorq"),
    ("jupiter", "TVS Jupiter", "scooter", r"jupiter"),
    ("access", "Suzuki Access 125", "scooter", r"\baccess\b"),
    ("burgman", "Suzuki Burgman", "scooter", r"burgman"),
    ("aprilia-sr", "Aprilia SR 125/160", "scooter", r"aprilia|\bsrx?\s*1[2-6]0"),
    ("vespa", "Vespa", "scooter", r"vespa"),
    ("x-adv", "Honda X-ADV 750", "motorcycle", r"\bx-?\s?adv"),
    ("click", "Honda Click 125/160", "scooter", r"\bclick\b"),
    ("pcx", "Honda PCX 160", "scooter", r"\bpcx\b"),
    ("adv-350", "Honda ADV 350", "scooter", r"\badv\s*350"),
    ("adv-160", "Honda ADV 160", "scooter", r"\badv\b"),
    ("forza", "Honda Forza 300/350", "scooter", r"forza"),
    ("scoopy", "Honda Scoopy", "scooter", r"scoopy"),
    ("tmax", "Yamaha TMAX 560", "scooter", r"\bt-?\s?max"),
    ("xmax", "Yamaha XMAX 300", "scooter", r"\bx-?\s?max"),
    ("nmax", "Yamaha NMAX 155", "scooter", r"\bn-?\s?max"),
    ("filano", "Yamaha Grand Filano", "scooter", r"filano"),
    # ── мотоциклы ──
    ("hunter", "Royal Enfield Hunter 350", "motorcycle", r"hunter"),
    ("himalayan", "Royal Enfield Himalayan", "motorcycle", r"himalayan"),
    ("cb350", "Honda CB350", "motorcycle", r"\bcb\s*350|h'?ness"),
    ("classic", "Royal Enfield Classic 350/500", "motorcycle", r"classic"),
    ("bullet", "Royal Enfield Bullet", "motorcycle", r"bullet"),
    ("thunderbird", "Royal Enfield Thunderbird", "motorcycle", r"thunderbird"),
    ("meteor", "Royal Enfield Meteor 350", "motorcycle", r"meteor"),
    ("interceptor", "Royal Enfield Interceptor 650", "motorcycle", r"interceptor|continental"),
    ("duke", "KTM Duke", "motorcycle", r"duke|\bktm\b"),
    ("fz", "Yamaha FZ", "motorcycle", r"\bfz"),
    ("mt-15", "Yamaha MT-15", "motorcycle", r"\bmt\s*-?\s*15"),
    ("r15", "Yamaha R15", "motorcycle", r"\br\s*15"),
    ("avenger", "Bajaj Avenger 220", "motorcycle", r"[ae]venger"),
    ("pulsar", "Bajaj Pulsar", "motorcycle", r"pulsar"),
    ("dominar", "Bajaj Dominar 400", "motorcycle", r"dominar"),
    ("xpulse", "Hero XPulse", "motorcycle", r"x\s?pulse"),
    ("apache", "TVS Apache", "motorcycle", r"apache"),
]
_COMPILED = [(code, re.compile(pattern, re.I)) for code, _, _, pattern in MODELS]
NAMES = {code: name for code, name, _, _ in MODELS}
KIND = {code: kind for code, _, kind, _ in MODELS}

# Машины, которые GPT иногда принимает за байки
CARS = re.compile(r"maruti|swift|baleno|glanza|fronx|toyota|innova|hyundai|creta|\bi10\b|\bi20\b|mahindra|"
                  r"\bthar\b|ertiga|brezza|\bkia\b|seltos|sonet|\bcar\b|машин|автомобил", re.I)

IMG_DIR = Path(settings.BASE_DIR) / "static" / "vendor" / "img" / "bikes"
NO_PHOTO = "vendor/img/bikes/none.svg"


def family_of(name: str | None) -> str | None:
    """«Yamaha Aerox S» → "aerox"; незнакомая модель → None."""
    if not name:
        return None
    return next((code for code, rx in _COMPILED if rx.search(name)), None)


def is_car(name: str | None) -> bool:
    return bool(name and CARS.search(name))


def generic_picture(kind: str | None) -> str:
    """Модель не узнали и фото нет: общий скутер или мотоцикл; тип неизвестен — заглушка «без фото»."""
    code = {"scooter": "generic-scooter", "motorcycle": "generic-motorcycle"}.get(kind)
    return picture(code) or NO_PHOTO


@lru_cache(maxsize=None)
def picture(code: str | None) -> str | None:
    """Путь к картинке модели для {% static %} или None, если картинки (ещё) нет."""
    if code and (IMG_DIR / f"{code}.jpg").exists():
        return f"vendor/img/bikes/{code}.jpg"
    return None
