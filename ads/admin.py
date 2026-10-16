from django.contrib import admin
import os
from django.utils.translation import gettext_lazy as _
from ads.models import Filter_items, Listing, Photo, Post, Tg_ads


from django.conf import settings
BASE_DIR = settings.BASE_DIR


@admin.register(Filter_items)
class FilterItemsAdmin(admin.ModelAdmin):

    # Добавлены поле id и body в список отображаемых полей
    list_display = ('id', 'body', 'created_at')

    def get_fields(self, request, obj=None):
        fields = super().get_fields(request, obj)
        return fields


@admin.register(Tg_ads)
class Tg_adsAdmin(admin.ModelAdmin):

    # Поля, которые будут отображаться в списке объектов
    list_display = ('id',   'grouped_id',
                    'text', 'created_at')

    # Поля, которые можно будет редактировать непосредственно из списка объектов
    list_editable = ('grouped_id',
                     'text', 'created_at')


# ── Новая схема ──────────────────────────────────

class PostInline(admin.TabularInline):
    model = Post.listings.through
    verbose_name = "Сообщение"
    verbose_name_plural = "Сообщения"
    raw_id_fields = ("post",)
    extra = 0


class PhotoInline(admin.TabularInline):
    model = Photo
    extra = 0


@admin.register(Listing)
class ListingAdmin(admin.ModelAdmin):
    list_display = ("id", "village", "rooms", "price_month", "price_day", "agent_percent", "last_seen")
    list_filter = ("village", "rooms")
    search_fields = ("text",)
    date_hierarchy = "last_seen"
    inlines = [PostInline, PhotoInline]


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ("id", "channel", "msg_id", "date", "status", "trash_reason")
    list_filter = ("status", "trash_reason", "channel")
    search_fields = ("text",)
    raw_id_fields = ("listings", "motos", "stuffs")
