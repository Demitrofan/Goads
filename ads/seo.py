"""Всё для поисковиков: robots.txt, карта сайта, заголовки и описания страниц."""
import os
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.decorators import login_not_required
from django.contrib.sitemaps import Sitemap
from django.contrib.sitemaps.views import sitemap
from django.http import HttpResponse
from django.templatetags.static import static
from django.urls import reverse
from django.utils import timezone

from ads.models import Listing
from moto.models import MotoListing
from stuff.models import StuffListing

# Адрес сайта для ссылок в тегах (canonical, превью); в .env SITE_URL
SITE_URL = os.environ.get("SITE_URL", "https://goadoska.ru").rstrip("/")
SITE_NAME = "GOA доска"
# Объявление, которое не появлялось в каналах дольше этого срока, скрываем от поиска
FRESH_DAYS = 30


def is_stale(item):
    return item.last_seen < timezone.now() - timedelta(days=FRESH_DAYS)


def price(value):
    return "{:,}".format(int(value)).replace(",", " ") + " ₹" if value else ""


def absolute(path):
    return path if path.startswith("http") else SITE_URL + path


def photo_url(item, fallback):
    photo = item.photos.all()[:1]
    return absolute(settings.MEDIA_URL + photo[0].path) if photo else absolute(static(fallback))


def short(text, limit=160):
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[:limit - 1].rsplit(" ", 1)[0] + "…"


def page(title, description, path, image="vendor/img/housing.jpg", noindex=False):
    return {
        "title": title,
        "description": short(description),
        "canonical": SITE_URL + path,
        "image": absolute(static(image)) if not image.startswith("http") else image,
        "noindex": noindex,
    }


def list_page(request, title, description, image):
    """Страница списка. С фильтрами — не индексируется (иначе тысячи почти одинаковых
    страниц), но поисковик проходит по ссылкам на объявления."""
    filtered = any(k != "page" for k in request.GET)
    seo = page(title, description, request.path, image, noindex=filtered)
    if request.GET.get("page", "1") != "1":
        seo["canonical"] += "?page=" + request.GET["page"]
        seo["title"] += f" — страница {request.GET['page']}"
    return seo


# ─────────────── страницы ───────────────

def index_seo():
    return page("Аренда жилья и байков в Гоа, барахолка — GOA доска",
                "Объявления из русскоязычных Telegram-каналов Гоа в одном месте: аренда жилья, "
                "аренда и продажа байков, барахолка. Фильтры по цене и посёлку.", "/")


def rent_list_seo(request):
    return list_page(request, "Аренда жилья в Гоа — дома и квартиры посуточно и помесячно",
                     "Объявления об аренде жилья в Гоа из русскоязычных Telegram-каналов: "
                     "Арамбол, Морджим, Ашвем, Мандрем, Сиолим и другие. Цены, фото, удобства, "
                     "дубли из разных каналов склеены.", "vendor/img/housing.jpg")


def moto_list_seo(request):
    return list_page(request, "Аренда байков в Гоа — скутеры и мотоциклы",
                     "Аренда и продажа байков в Гоа: скутеры и мотоциклы от владельцев и прокатов "
                     "из русскоязычных Telegram-каналов. Цены за сутки и месяц, характеристики моделей.",
                     "vendor/img/moto.jpg")


def stuff_list_seo(request):
    return list_page(request, "Барахолка Гоа — купить и продать вещи",
                     "Барахолка русскоязычного Гоа: электроника, мебель, одежда, детские вещи, "
                     "спорт. Объявления из Telegram-каналов, можно отдать даром.",
                     "vendor/img/stuff.jpg")


def rent_seo(item, room_label):
    where = f", {item.village}" if item.village else ""
    what = room_label or "Жильё"
    cost = (f"{price(item.price_month)}/мес" if item.price_month
            else f"{price(item.price_day)}/сутки" if item.price_day else "")
    title = f"{what}{where}" + (f" — {cost}" if cost else "") + " | Аренда жилья в Гоа"
    description = f"Аренда: {what}{where}, Гоа. " + (f"Цена {cost}. " if cost else "") + item.text
    seo = page(title, description, reverse("ads:details", args=[item.pk]), noindex=is_stale(item))
    seo["image"] = photo_url(item, "vendor/img/housing.jpg")
    return seo


def moto_seo(item):
    name = item.model_name or item.get_kind_display() or "Байк"
    if item.price_sell and not (item.price_month or item.price_day):
        deal, cost = "Продажа", price(item.price_sell)
    else:
        deal = "Аренда"
        cost = (f"{price(item.price_month)}/мес" if item.price_month
                else f"{price(item.price_day)}/сутки" if item.price_day else "")
    where = f", {item.village}" if item.village else ""
    title = f"{name} — {deal.lower()}{where}" + (f", {cost}" if cost else "") + " | Байки в Гоа"
    description = f"{deal} {name} в Гоа{where}. " + (f"Цена {cost}. " if cost else "") + item.text
    seo = page(title, description, reverse("moto:details_moto", args=[item.pk]),
               noindex=is_stale(item))
    seo["image"] = photo_url(item, "vendor/img/moto.jpg")
    return seo


def stuff_seo(item):
    cost = "даром" if item.is_free else price(item.price)
    where = f", {item.village}" if item.village else ""
    title = f"{item.title}" + (f" — {cost}" if cost else "") + " | Барахолка Гоа"
    description = f"{item.title}{where}, Гоа. " + (f"Цена: {cost}. " if cost else "") + item.text
    seo = page(title, description, reverse("stuff:details_stuff", args=[item.pk]),
               noindex=is_stale(item))
    seo["image"] = photo_url(item, "vendor/img/stuff.jpg")
    return seo


# ─────────────── robots.txt и карта сайта ───────────────

@login_not_required
def robots_txt(request):
    lines = [
        "User-agent: *",
        "Disallow: /admin/",
        "Disallow: /accounts/",
        "",
        f"Sitemap: {SITE_URL}/sitemap.xml",
    ]
    return HttpResponse("\n".join(lines) + "\n", content_type="text/plain")


class StaticSitemap(Sitemap):
    protocol = SITE_URL.split(":")[0]
    changefreq = "hourly"

    def items(self):
        return ["index", "ads:search_properties", "moto:search_properties_moto",
                "stuff:search_properties_stuff"]

    def location(self, name):
        return reverse(name)

    def priority(self, name):
        return 1.0 if name == "index" else 0.9


class ListingSitemap(Sitemap):
    protocol = SITE_URL.split(":")[0]
    changefreq = "daily"
    priority = 0.6

    def __init__(self, model, url_name):
        self.model, self.url_name = model, url_name

    def items(self):
        since = timezone.now() - timedelta(days=FRESH_DAYS)
        return self.model.objects.filter(last_seen__gte=since).order_by("-last_seen")

    def location(self, item):
        return reverse(self.url_name, args=[item.pk])

    def lastmod(self, item):
        return item.last_seen


SITEMAPS = {
    "pages": StaticSitemap(),
    "rent": ListingSitemap(Listing, "ads:details"),
    "moto": ListingSitemap(MotoListing, "moto:details_moto"),
    "stuff": ListingSitemap(StuffListing, "stuff:details_stuff"),
}


@login_not_required
def sitemap_xml(request):
    return sitemap(request, sitemaps=SITEMAPS)
