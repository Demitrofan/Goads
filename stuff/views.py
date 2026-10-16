from datetime import timedelta

from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from ads.currency import current_currency, get_rates, to_rupees
from ads.views import PERIODS, remember_currency
from stuff.models import StuffListing

CATEGORIES = StuffListing.CATEGORIES
CONDITIONS = StuffListing.CONDITIONS
DEFAULT_PERIOD = "30"


def get_form_data(request):
    g = request.GET
    period = g.get("period", DEFAULT_PERIOD)
    return {
        "price_from": g.get("price_from", "").strip(),
        "price_to": g.get("price_to", "").strip(),
        "words": g.get("words", "").strip(),
        "period": period if period in dict(PERIODS) else DEFAULT_PERIOD,
        "categories": [c for c, _ in CATEGORIES if g.get(f"cat_{c}") == "on"],
        "conditions": [c for c, _ in CONDITIONS if g.get(f"cond_{c}") == "on"],
        "free": g.get("free") == "on",
    }


def build_queryset(form, currency):
    since = timezone.now() - timedelta(days=int(form["period"]))
    rates = get_rates()

    q = Q(last_seen__gte=since)
    if form["free"]:
        q &= Q(is_free=True)
    if form["price_from"].isdigit():
        q &= Q(price__gte=to_rupees(int(form["price_from"]), currency, rates))
    if form["price_to"].isdigit():
        # «до N» включает и бесплатное
        q &= Q(price__lte=to_rupees(int(form["price_to"]), currency, rates)) | Q(is_free=True)
    if form["categories"]:
        q &= Q(category__in=form["categories"])
    if form["conditions"]:
        q &= Q(condition__in=form["conditions"])
    if form["words"]:
        for word in form["words"].replace(",", " ").split():
            q &= Q(text__icontains=word) | Q(title__icontains=word)

    return (StuffListing.objects.filter(q)
            .annotate(sources=Count("posts", distinct=True))
            .prefetch_related("photos"))


def search_properties_stuff(request):
    form = get_form_data(request)
    currency = current_currency(request)
    queryset = build_queryset(form, currency)

    sort = request.GET.get("sort", "fresh")
    if sort == "cheap":
        queryset = queryset.order_by("price", "-last_seen")
    elif sort == "expensive":
        queryset = queryset.order_by("-price", "-last_seen")
    else:
        sort = "fresh"
        queryset = queryset.order_by("-last_seen")

    page_obj = Paginator(queryset, 48).get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)
    params.pop("cur", None)

    response = render(request, "stuff.html", {
        "page_obj": page_obj,
        "form": form,
        "categories": CATEGORIES,
        "conditions": CONDITIONS,
        "periods": PERIODS,
        "num_properties": page_obj.paginator.count,
        "sort": sort,
        "query": params.urlencode(),
    })
    return remember_currency(request, response)


def details_stuff(request, item_id):
    item = get_object_or_404(StuffListing.objects.prefetch_related("photos"), pk=item_id)
    return render(request, "details_stuff.html", {
        "item": item,
        "posts": item.posts.order_by("-date"),
        "category_label": dict(CATEGORIES).get(item.category, ""),
        "condition_label": dict(CONDITIONS).get(item.condition, ""),
    })
