from django.contrib import admin
import os
from django.utils.translation import gettext_lazy as _
from moto.models import Filter_items_moto, Tg_moto


from django.conf import settings
BASE_DIR = settings.BASE_DIR


@admin.register(Filter_items_moto)
class FilterItemsAdmin(admin.ModelAdmin):

    # Добавлены поле id и body в список отображаемых полей
    list_display = ('id', 'body', 'created_at')

    def get_fields(self, request, obj=None):
        fields = super().get_fields(request, obj)
        return fields


@admin.register(Tg_moto)
class Tg_adsAdmin(admin.ModelAdmin):

    # Поля, которые будут отображаться в списке объектов
    list_display = ('id',   'grouped_id',
                    'text', 'created_at')

    # Поля, которые можно будет редактировать непосредственно из списка объектов
    list_editable = ('grouped_id',
                     'text', 'created_at')


# ── Новая схема ──────────────────────────────────
from moto.models import MotoListing, MotoPhoto  # noqa: E402


class MotoPhotoInline(admin.TabularInline):
    model = MotoPhoto
    extra = 0


@admin.register(MotoListing)
class MotoListingAdmin(admin.ModelAdmin):
    list_display = ("id", "model_name", "kind", "price_month", "price_day", "price_sell", "last_seen")
    list_filter = ("kind", "model_name")
    search_fields = ("text", "model_name")
    date_hierarchy = "last_seen"
    inlines = [MotoPhotoInline]
