import json
import logging
import os
from datetime import timedelta

from django.contrib.auth.decorators import login_not_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from ads.currency import cookie_name, current_currency, get_rates, region_of_path, to_rupees
from ads.models import Listing, Subscription
from ads import seo
from ads.places import main_city

logger = logging.getLogger(__name__)

ROOMS = [
    ("room", "Комната"),
    ("1bk", "Студия (1BK)"),
    ("1bhk", "1 BHK"),
    ("2bhk", "2 BHK"),
    ("3bhk", "3 BHK"),
    ("4bhk+", "4+ BHK"),
]

# В Армении и Грузии считают все комнаты: «2-комнатная» — гостиная и спальня
ROOMS_ARMENIA = [
    ("room", "Комната"),
    ("1k", "1-комнатная"),
    ("2k", "2-комнатная"),
    ("3k", "3-комнатная"),
    ("4k+", "4+ комнат"),
]

# На Пхукете считают спальни; коды те же, что в Гоа (1bhk = 1 спальня)
ROOMS_THAI = [
    ("room", "Комната"),
    ("1bk", "Студия"),
    ("1bhk", "1 спальня"),
    ("2bhk", "2 спальни"),
    ("3bhk", "3 спальни"),
    ("4bhk+", "4+ спальни"),
]

# Регион → что отличается на страницах жилья: адреса, комнаты, подписи.
# brand — название в шапке списка, where — «где» в подписях, of — «каналов чего» на главной.
REGIONS = {
    Listing.GOA: dict(rooms=ROOMS, home="index", list="ads:search_properties",
                      details="ads:details", place="Населённый пункт", period="7",
                      where="в Гоа", of="Гоа"),
    Listing.ARMENIA: dict(rooms=ROOMS_ARMENIA, home="index_am", list="rent_am",
                          details="details_am", place="Район", period="14", cities=True,
                          brand="Ереван", where="в Ереване", of="Армении"),
    Listing.GEORGIA: dict(rooms=ROOMS_ARMENIA, home="index_ge", list="rent_ge",
                          details="details_ge", place="Район", period="14", cities=True,
                          brand="Грузия", where="в Грузии", of="Грузии"),
    Listing.PHUKET: dict(rooms=ROOMS_THAI, home="index_th", list="rent_th",
                         details="details_th", place="Район", period="14", moto="moto_th",
                         brand="Пхукет", where="на Пхукете", of="Пхукета"),
}

# Главная регионов кроме Гоа: картинки карточек
HOME_CARDS = {
    Listing.ARMENIA: dict(housing="vendor/img/housing_am.jpg", moto="vendor/img/moto_am.jpg",
                          stuff="vendor/img/stuff_am.jpg", v=3),   # v — сменить при замене картинок
    Listing.GEORGIA: dict(housing="vendor/img/housing_ge.jpg", moto="vendor/img/moto_ge.jpg",
                          stuff="vendor/img/stuff_ge.jpg", v=2),
    # moto_list — у байков есть страница (на Пхукете), иначе карточка «Скоро»
    Listing.PHUKET: dict(housing="vendor/img/housing_th.jpg", moto="vendor/img/moto_th.jpg",
                         stuff="vendor/img/stuff_th.jpg", moto_list="moto_th", v=2),
}

AMENITIES = [
    ("has_ac", "Кондиционер"),
    ("has_wifi", "Wi-Fi"),
    ("has_kitchen", "Кухня"),
    ("has_fridge", "Холодильник"),
    ("has_dishes", "Посуда"),
    ("has_hot_water", "Горячая вода"),
    ("has_washing_machine", "Стиральная машина"),
    ("owners_nearby", "Хозяева рядом"),
]

PERIODS = [
    ("1", "за сутки"),
    ("3", "за 3 дня"),
    ("7", "за неделю"),
    ("14", "за 2 недели"),
    ("30", "за месяц"),
]


def village_list(region=Listing.GOA):
    """[(район, город)] — город нужен меню районов, чтобы показывать районы выбранного города."""
    # order_by сбрасывает сортировку модели по дате, иначе distinct не схлопывает повторы
    return list(
        Listing.objects.filter(region=region)
        .exclude(village__isnull=True).exclude(village="")
        .order_by("village", "city").values_list("village", "city").distinct()
    )


def city_list(region):
    """Города региона: главный первым, остальные — по числу объявлений."""
    rows = (Listing.objects.filter(region=region).exclude(city__isnull=True).exclude(city="")
            .order_by().values("city").annotate(n=Count("id")).values_list("city", "n"))
    main = main_city(region)
    return [c for c, _ in sorted(rows, key=lambda r: (r[0] != main, -r[1], r[0]))]


def get_form_data(request, rooms=ROOMS, default_period="7"):
    g = request.GET
    period = g.get("period", default_period)
    return {
        "rent_period": g.get("rent_period", "monthly"),
        "price_from": g.get("price_from", "").strip(),
        "price_to": g.get("price_to", "").strip(),
        "words": g.get("words", "").strip(),
        "city": g.get("city", "").strip(),
        "village": g.get("village", "").strip(),
        "period": period if period in dict(PERIODS) else default_period,
        "rooms": [r for r, _ in rooms if g.get(f"rooms_{r}") == "on"],
        "amenities": [a for a, _ in AMENITIES if g.get(a) == "on"],
    }


def build_queryset(form, currency="INR", region=Listing.GOA):
    price_field = "price_day" if form["rent_period"] == "daily" else "price_month"
    since = timezone.now() - timedelta(days=int(form["period"]))
    rates = get_rates()

    # Цена в фильтре — в валюте сайта, в базе — рупии
    q = Q(region=region) & Q(last_seen__gte=since, closed__isnull=True) & Q(**{f"{price_field}__gt": 0})
    if form["price_from"].isdigit():
        q &= Q(**{f"{price_field}__gte": to_rupees(int(form["price_from"]), currency, rates)})
    if form["price_to"].isdigit():
        q &= Q(**{f"{price_field}__lte": to_rupees(int(form["price_to"]), currency, rates)})
    if form["rooms"]:
        q &= Q(rooms__in=form["rooms"])
    if form["city"]:
        q &= Q(city=form["city"])
    if form["village"]:
        q &= Q(village=form["village"])
    if form["words"]:
        for word in form["words"].replace(",", " ").split():
            q &= Q(text__ucontains=word)
    for field in form["amenities"]:
        q &= Q(**{field: True})

    qs = (Listing.objects.filter(q)
          .annotate(sources=Count("posts__channel", distinct=True))
          .prefetch_related("photos"))
    return qs, price_field


def index(request):
    return render(request, "index.html", {"seo": seo.index_seo()})


def index_region(request, region):
    return render(request, "index.html", {"seo": seo.index_region_seo(region), "conf": REGIONS[region],
                                          "cards": HOME_CARDS[region]})


def search_properties(request, region=Listing.GOA):
    conf = REGIONS[region]
    form = get_form_data(request, conf["rooms"], conf["period"])
    currency = current_currency(request, region)
    queryset, price_field = build_queryset(form, currency, region)

    sort = request.GET.get("sort", "fresh")
    if sort == "cheap":
        queryset = queryset.order_by(price_field, "-last_seen")
    elif sort == "expensive":
        queryset = queryset.order_by(f"-{price_field}", "-last_seen")
    else:
        sort = "fresh"
        queryset = queryset.order_by("-last_seen")

    page_obj = Paginator(queryset, 48).get_page(request.GET.get("page"))

    # Параметры без page: чтобы пагинация не сбрасывала фильтры
    params = request.GET.copy()
    params.pop("page", None)
    params.pop("cur", None)

    response = render(request, "ads.html", {
        "page_obj": page_obj,
        "villages": village_list(region),
        "cities": city_list(region) if conf.get("cities") else [],
        "form": form,
        "rooms": conf["rooms"],
        "conf": conf,
        "amenities": AMENITIES,
        "periods": PERIODS,
        "num_properties": page_obj.paginator.count,
        "price_field": price_field,
        "sort": sort,
        "query": params.urlencode(),
        "seo": seo.rent_list_seo(request) if region == Listing.GOA else seo.rent_list_region_seo(request, region),
    })
    return remember_currency(request, response)


def remember_currency(request, response):
    """Выбранная валюта запоминается на год — для каждого региона своя."""
    if "cur" in request.GET:
        region = region_of_path(request.path)
        response.set_cookie(cookie_name(region), current_currency(request, region), max_age=365 * 24 * 3600)
    return response


def details(request, item_id, region=Listing.GOA):
    item = get_object_or_404(Listing.objects.prefetch_related("photos"), pk=item_id)
    if item.region != region:   # объявление другого региона — на его адрес
        return redirect(reverse(REGIONS[item.region]["details"], args=[item.pk]), permanent=True)
    conf = REGIONS[region]
    amenities = [(label, getattr(item, field)) for field, label in AMENITIES]
    room_label = dict(conf["rooms"]).get(item.rooms, item.rooms)
    return render(request, "details.html", {
        "item": item,
        "conf": conf,
        "seo": seo.rent_seo(item, room_label),
        "posts": item.posts.order_by("-date"),
        "amenities": amenities,
        "room_label": room_label,
    })


# ─────────────── Telegram-бот: подписка на поиск ───────────────

@require_POST
def subscribe(request):
    """Кнопка «Подписаться»: запоминаем фильтры и отправляем человека к боту."""
    from ads import bot
    section = request.POST.get("section")
    region = request.POST.get("region", Listing.GOA)
    from moto.views import REGIONS as MOTO_REGIONS
    allowed = {"rent": REGIONS, "bike": MOTO_REGIONS, "sale": [Listing.GOA]}
    if not bot.enabled() or region not in allowed.get(section, []):
        return redirect("index")
    sub = bot.create(section, region, request.POST.get("query", ""), current_currency(request, region))
    return redirect(f"https://t.me/{bot.bot_name()}?start={sub.code}")


@csrf_exempt
@login_not_required
@require_POST
def telegram_hook(request):
    """Сюда Telegram присылает сообщения боту. Подлинность — по секрету в заголовке."""
    from ads import bot
    secret = os.environ.get("TG_BOT_SECRET", "")
    if not secret or request.headers.get("X-Telegram-Bot-Api-Secret-Token") != secret:
        return HttpResponseForbidden()
    try:
        bot.handle_update(json.loads(request.body))
    except Exception:
        logger.exception("Бот: ошибка обработки сообщения")
    return HttpResponse("ok")   # всегда 200, иначе Telegram будет слать то же сообщение снова
