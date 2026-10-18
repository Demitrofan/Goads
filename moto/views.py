from datetime import timedelta

from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from ads.currency import current_currency, get_rates, to_rupees
from ads import seo
from ads.views import PERIODS, remember_currency
from moto.models import MotoListing

KINDS = MotoListing.KINDS

# (поле, значение, подпись): фильтр срабатывает, если поле равно значению
OPTIONS = [
    ("has_helmet", True, "Шлем в комплекте"),
    ("has_delivery", True, "Доставка"),
    ("need_deposit", False, "Без залога"),
    ("need_passport", False, "Без паспорта"),
]

DEFAULT_PERIOD = "30"   # байки публикуют реже, чем жильё

# Регион → адреса и подписи раздела байков (байки есть в Гоа и на Пхукете)
REGIONS = {
    "goa": dict(list="moto:search_properties_moto", details="moto:details_moto", home="index",
                rent="ads:search_properties", where="в Гоа"),
    "th": dict(list="moto_th", details="details_moto_th", home="index_th", rent="rent_th",
               brand="Пхукет", where="на Пхукете"),
}


def model_list(region="goa"):
    return list(
        MotoListing.objects.filter(region=region)
        .exclude(model_name__isnull=True).exclude(model_name="")
        .order_by("model_name").values_list("model_name", flat=True).distinct()
    )


def get_form_data(request):
    g = request.GET
    period = g.get("period", DEFAULT_PERIOD)
    return {
        "rent_period": g.get("rent_period", "monthly"),
        "price_from": g.get("price_from", "").strip(),
        "price_to": g.get("price_to", "").strip(),
        "words": g.get("words", "").strip(),
        "model": g.get("model", "").strip(),
        "period": period if period in dict(PERIODS) else DEFAULT_PERIOD,
        "kinds": [k for k, _ in KINDS if g.get(f"kind_{k}") == "on"],
        "options": [f for f, _, _ in OPTIONS if g.get(f) == "on"],
    }


def build_queryset(form, currency, region="goa"):
    price_field = {"daily": "price_day", "sell": "price_sell"}.get(form["rent_period"], "price_month")
    since = timezone.now() - timedelta(days=int(form["period"]))
    rates = get_rates()

    q = Q(region=region, last_seen__gte=since, closed__isnull=True) & Q(**{f"{price_field}__gt": 0})
    if form["price_from"].isdigit():
        q &= Q(**{f"{price_field}__gte": to_rupees(int(form["price_from"]), currency, rates)})
    if form["price_to"].isdigit():
        q &= Q(**{f"{price_field}__lte": to_rupees(int(form["price_to"]), currency, rates)})
    if form["kinds"]:
        q &= Q(kind__in=form["kinds"])
    if form["model"]:
        q &= Q(model_name=form["model"])
    if form["words"]:
        for word in form["words"].replace(",", " ").split():
            q &= Q(text__ucontains=word)
    for field, value, _ in OPTIONS:
        if field in form["options"]:
            q &= Q(**{field: value})

    qs = (MotoListing.objects.filter(q)
          .annotate(sources=Count("posts", distinct=True))
          .prefetch_related("photos"))
    return qs, price_field


def search_properties_moto(request, region="goa"):
    form = get_form_data(request)
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
    params = request.GET.copy()
    params.pop("page", None)
    params.pop("cur", None)

    response = render(request, "moto.html", {
        "page_obj": page_obj,
        "models": model_list(region),
        "conf": REGIONS[region],
        "form": form,
        "kinds": KINDS,
        "options": [(f, label) for f, _, label in OPTIONS],
        "periods": PERIODS,
        "num_properties": page_obj.paginator.count,
        "price_field": price_field,
        "sort": sort,
        "query": params.urlencode(),
        "seo": seo.moto_list_seo(request, region),
    })
    return remember_currency(request, response)


def details_moto(request, item_id, region="goa"):
    item = get_object_or_404(MotoListing.objects.prefetch_related("photos"), pk=item_id)
    if item.region != region:
        return redirect(reverse(REGIONS[item.region]["details"], args=[item.pk]), permanent=True)
    options = [
        ("Шлем в комплекте", item.has_helmet),
        ("Доставка", item.has_delivery),
        ("Нужен залог", item.need_deposit),
        ("Нужен паспорт", item.need_passport),
    ]
    return render(request, "details_moto.html", {
        "item": item,
        "conf": REGIONS[region],
        "seo": seo.moto_seo(item),
        "posts": item.posts.order_by("-date"),
        "options": options,
        "kind_label": dict(KINDS).get(item.kind, ""),
    })
