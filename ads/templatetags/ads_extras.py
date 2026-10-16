from django import template

register = template.Library()


@register.filter
def rupees(value):
    """25000 → «25 000 ₹»"""
    if not value:
        return "—"
    return "{:,}".format(int(value)).replace(",", " ") + " ₹"


ROOMS_SHORT = {"room": "Комната", "1k": "1-комн.", "2k": "2-комн.", "3k": "3-комн.", "4k+": "4+ комн."}


@register.filter
def room_short(code):
    """Значок комнат на карточке: «2BHK» для Гоа, «2-комн.» для Армении."""
    if not code:
        return ""
    return ROOMS_SHORT.get(code, code.upper())


@register.filter
def sources_label(n):
    """1 → «1 канал», 3 → «3 канала», 5 → «5 каналов»"""
    n = int(n or 0)
    if n % 10 == 1 and n % 100 != 11:
        word = "канал"
    elif 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        word = "канала"
    else:
        word = "каналов"
    return f"{n} {word}"


@register.simple_tag(takes_context=True)
def money(context, rupees, currency=None):
    """Цена из рупий в валюте сайта: {% money item.price_month %} → «26 100 ₽».
    {% money item.price_month "INR" %} — в рупиях, как в объявлении."""
    from ads.currency import CURRENCIES, convert
    cur = currency or context.get("currency", "INR")
    value = convert(rupees, cur, context["rates"])
    if value is None:
        return "—"
    from django.utils.safestring import mark_safe
    number = "{:,}".format(value).replace(",", " ")
    symbol = CURRENCIES[cur]
    return mark_safe(f"{symbol}{number}" if cur == "USD" else f"{number} {symbol}")


@register.filter
def ago(value):
    """«2 часа назад» вместо «2 часа, 33 минуты назад»."""
    from django.utils.timesince import timesince
    if not value:
        return ""
    text = timesince(value, depth=1)
    return "только что" if text.startswith("0 ") else f"{text} назад"
