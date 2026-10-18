"""Курсы валют для показа цен. В базе цены в рупиях, на сайте — в выбранной валюте."""

import json
import os
import urllib.request

from django.core.cache import cache
from django.utils.safestring import mark_safe

CBR_URL = "https://www.cbr-xml-daily.ru/daily_json.js"
CACHE_KEY = "inr_rates_v3"
CACHE_SECONDS = 6 * 60 * 60

# Запасные курсы на случай, если ЦБ недоступен (октябрь 2026)
FALLBACK = {"INR": 1.0, "RUB": 0.87, "USD": 0.0104, "UAH": 0.469, "BYN": 0.0313,
            "AMD": 4.0, "EUR": 0.0095, "GEL": 0.028}

# Не показываются, но нужны сборщику: цены в драмах, лари и евро → рупии
EXTRA = ["AMD", "GEL", "EUR"]

CURRENCIES = {
    "RUB": "₽",
    "BYN": mark_safe('<span class="byn-sign">Б</span>'),  # знака нет в Unicode: Б с чертой через CSS
    "UAH": "₴",
    "USD": "$",
    "INR": "₹",
}

# Округление при показе: рубли до сотни, гривны до десятка, остальное до единицы
ROUND_TO = {"RUB": -2, "UAH": -1}
DEFAULT = "RUB"
COOKIE = "currency"


def get_rates() -> dict:
    """Сколько единиц валюты стоит 1 рупия: {"INR": 1, "RUB": 0.87, "USD": 0.0104, ...}."""
    rates = cache.get(CACHE_KEY)
    if rates:
        return rates
    try:
        with urllib.request.urlopen(CBR_URL, timeout=5) as resp:
            valute = json.load(resp)["Valute"]
        def rub(code):   # сколько рублей стоит 1 единица валюты
            return valute[code]["Value"] / valute[code]["Nominal"]

        inr_rub = rub("INR")
        rates = {"INR": 1.0, "RUB": inr_rub}
        for code in [*CURRENCIES, *EXTRA]:
            if code not in rates:
                rates[code] = inr_rub / rub(code)
        cache.set(CACHE_KEY, rates, CACHE_SECONDS)
    except Exception:
        rates = FALLBACK
        cache.set(CACHE_KEY, rates, 10 * 60)   # повторим попытку через 10 минут
    return rates


def region_currencies(region: str = "goa") -> dict:
    """Валюты в переключателе: вне Гоа (Армения, Грузия) рупии не нужны."""
    if region == "goa":
        return CURRENCIES
    return {code: sym for code, sym in CURRENCIES.items() if code != "INR"}


def current_currency(request, region: str = "goa") -> str:
    cur = request.GET.get("cur") or request.COOKIES.get(COOKIE) or DEFAULT
    return cur if cur in region_currencies(region) else DEFAULT


def convert(rupees, currency: str, rates: dict):
    """Рупии → валюта, с округлением (см. ROUND_TO)."""
    if not rupees:
        return None
    return int(round(rupees * rates[currency], ROUND_TO.get(currency, 0)))


def to_rupees(amount: int, currency: str, rates: dict) -> int:
    """Для фильтра цены: сумма в выбранной валюте → рупии."""
    return int(amount / rates[currency])


def price_to_rupees(amount, currency: str):
    """Для сборщика: цена из объявления (драмы, доллары...) → рупии, как хранится в базе."""
    if not amount or currency == "INR":
        return amount
    rates = get_rates()
    if currency not in rates:
        rates = FALLBACK
    return round(amount / rates[currency])


# Начало адреса → регион; всё остальное — Гоа
REGION_PREFIXES = {"/am/": "am", "/ge/": "ge"}


def region_of_path(path: str) -> str:
    return next((r for prefix, r in REGION_PREFIXES.items() if path.startswith(prefix)), "goa")


def context(request):
    """Контекст-процессор: валюта и курсы доступны во всех шаблонах."""
    region = region_of_path(request.path)
    cur = current_currency(request, region)
    return {
        "region": region,
        "currency": cur,
        "currency_symbol": CURRENCIES[cur],
        "currencies": region_currencies(region),
        "rates": get_rates(),
        "rates_json": json.dumps(get_rates()),
        # номер счётчика Яндекс Метрики (в .env YANDEX_METRIKA_ID); пусто — счётчика нет
        "metrika_id": os.environ.get("YANDEX_METRIKA_ID", "").strip(),
        # кнопка «Подписаться» — только если бот настроен (TG_BOT_TOKEN и TG_BOT_NAME в .env)
        "bot_enabled": bool(os.environ.get("TG_BOT_TOKEN", "").strip() and os.environ.get("TG_BOT_NAME", "").strip()),
    }
