from django.contrib import admin
import os
from django.utils.translation import gettext_lazy as _
from stuff.models import Tg_stuff


from django.conf import settings
BASE_DIR = settings.BASE_DIR


@admin.register(Tg_stuff)
class Tg_adsAdmin(admin.ModelAdmin):

    # Поля, которые будут отображаться в списке объектов
    list_display = ('id',   'grouped_id',
                    'text', 'created_at')

    # Поля, которые можно будет редактировать непосредственно из списка объектов
    list_editable = ('grouped_id',
                     'text', 'created_at')


# ── Новая схема ──────────────────────────────────
from stuff.models import StuffListing, StuffPhoto  # noqa: E402


class StuffPhotoInline(admin.TabularInline):
    model = StuffPhoto
    extra = 0


@admin.register(StuffListing)
class StuffListingAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "category", "condition", "price", "is_free", "last_seen")
    list_filter = ("category", "condition", "is_free")
    search_fields = ("title", "text")
    date_hierarchy = "last_seen"
    inlines = [StuffPhotoInline]
