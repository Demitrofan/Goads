"""Курсы валют для показа цен. В базе цены в рупиях, на сайте — в выбранной валюте."""

import json
import urllib.request

from django.core.cache import cache
from django.utils.safestring import mark_safe

CBR_URL = "https://www.cbr-xml-daily.ru/daily_json.js"
CACHE_KEY = "inr_rates"
CACHE_SECONDS = 6 * 60 * 60

# Запасные курсы на случай, если ЦБ недоступен (октябрь 2026)
FALLBACK = {"INR": 1.0, "RUB": 0.87, "USD": 0.0104, "UAH": 0.469, "BYN": 0.0313}

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
        for code in CURRENCIES:
            if code not in rates:
                rates[code] = inr_rub / rub(code)
        cache.set(CACHE_KEY, rates, CACHE_SECONDS)
    except Exception:
        rates = FALLBACK
        cache.set(CACHE_KEY, rates, 10 * 60)   # повторим попытку через 10 минут
    return rates


def current_currency(request) -> str:
    cur = request.GET.get("cur") or request.COOKIES.get(COOKIE) or DEFAULT
    return cur if cur in CURRENCIES else DEFAULT


def convert(rupees, currency: str, rates: dict):
    """Рупии → валюта, с округлением (см. ROUND_TO)."""
    if not rupees:
        return None
    return int(round(rupees * rates[currency], ROUND_TO.get(currency, 0)))


def to_rupees(amount: int, currency: str, rates: dict) -> int:
    """Для фильтра цены: сумма в выбранной валюте → рупии."""
    return int(amount / rates[currency])


def context(request):
    """Контекст-процессор: валюта и курсы доступны во всех шаблонах."""
    cur = current_currency(request)
    return {
        "currency": cur,
        "currency_symbol": CURRENCIES[cur],
        "currencies": CURRENCIES,
        "rates": get_rates(),
        "rates_json": json.dumps(get_rates()),
    }
