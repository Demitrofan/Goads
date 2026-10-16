from datetime import timedelta

from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from ads.currency import COOKIE, current_currency, get_rates, to_rupees
from ads.models import Listing
from ads import seo

ROOMS = [
    ("room", "Комната"),
    ("1bk", "Студия (1BK)"),
    ("1bhk", "1 BHK"),
    ("2bhk", "2 BHK"),
    ("3bhk", "3 BHK"),
    ("4bhk+", "4+ BHK"),
]

# В Армении считают все комнаты: «2-комнатная» — гостиная и спальня
ROOMS_ARMENIA = [
    ("room", "Комната"),
    ("1k", "1-комнатная"),
    ("2k", "2-комнатная"),
    ("3k", "3-комнатная"),
    ("4k+", "4+ комнат"),
]

# Регион → что отличается на страницах жилья: адреса, комнаты, подписи
REGIONS = {
    Listing.GOA: dict(rooms=ROOMS, home="index", list="ads:search_properties",
                      details="ads:details", place="Населённый пункт"),
    Listing.ARMENIA: dict(rooms=ROOMS_ARMENIA, home="index_am", list="rent_am",
                          details="details_am", place="Район"),
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
    ("30", "за месяц"),
]
DEFAULT_PERIOD = "7"


def village_list(region=Listing.GOA):
    # order_by сбрасывает сортировку модели по дате, иначе distinct не схлопывает повторы
    return list(
        Listing.objects.filter(region=region)
        .exclude(village__isnull=True).exclude(village="")
        .order_by("village").values_list("village", flat=True).distinct()
    )


def get_form_data(request, rooms=ROOMS):
    g = request.GET
    period = g.get("period", DEFAULT_PERIOD)
    return {
        "rent_period": g.get("rent_period", "monthly"),
        "price_from": g.get("price_from", "").strip(),
        "price_to": g.get("price_to", "").strip(),
        "words": g.get("words", "").strip(),
        "village": g.get("village", "").strip(),
        "period": period if period in dict(PERIODS) else DEFAULT_PERIOD,
        "rooms": [r for r, _ in rooms if g.get(f"rooms_{r}") == "on"],
        "amenities": [a for a, _ in AMENITIES if g.get(a) == "on"],
    }


def build_queryset(form, currency="INR", region=Listing.GOA):
    price_field = "price_day" if form["rent_period"] == "daily" else "price_month"
    since = timezone.now() - timedelta(days=int(form["period"]))
    rates = get_rates()

    # Цена в фильтре — в валюте сайта, в базе — рупии
    q = Q(region=region) & Q(last_seen__gte=since) & Q(**{f"{price_field}__gt": 0})
    if form["price_from"].isdigit():
        q &= Q(**{f"{price_field}__gte": to_rupees(int(form["price_from"]), currency, rates)})
    if form["price_to"].isdigit():
        q &= Q(**{f"{price_field}__lte": to_rupees(int(form["price_to"]), currency, rates)})
    if form["rooms"]:
        q &= Q(rooms__in=form["rooms"])
    if form["village"]:
        q &= Q(village=form["village"])
    if form["words"]:
        for word in form["words"].replace(",", " ").split():
            q &= Q(text__icontains=word)
    for field in form["amenities"]:
        q &= Q(**{field: True})

    qs = (Listing.objects.filter(q)
          .annotate(sources=Count("posts", distinct=True))
          .prefetch_related("photos"))
    return qs, price_field


def index(request):
    return render(request, "index.html", {"seo": seo.index_seo()})


def index_armenia(request):
    return render(request, "index.html", {"seo": seo.index_armenia_seo()})


def search_properties(request, region=Listing.GOA):
    conf = REGIONS[region]
    form = get_form_data(request, conf["rooms"])
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
        "form": form,
        "rooms": conf["rooms"],
        "conf": conf,
        "amenities": AMENITIES,
        "periods": PERIODS,
        "num_properties": page_obj.paginator.count,
        "price_field": price_field,
        "sort": sort,
        "query": params.urlencode(),
        "seo": seo.rent_list_seo(request) if region == Listing.GOA else seo.rent_list_armenia_seo(request),
    })
    return remember_currency(request, response)


def remember_currency(request, response):
    """Выбранная валюта запоминается на год."""
    if "cur" in request.GET:
        response.set_cookie(COOKIE, current_currency(request), max_age=365 * 24 * 3600)
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
