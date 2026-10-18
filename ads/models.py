from django.db import models
from django.utils import timezone
import pytz


class Filter_items(models.Model):
    ulid = models.CharField(max_length=256, null=True, blank=True)
    body = models.TextField(null=True, blank=True)
    price_month = models.IntegerField(null=True, blank=True)
    price_day = models.IntegerField(null=True, blank=True)
    agent_percent = models.IntegerField(null=True, blank=True)
    room_count = models.CharField(null=True, max_length=256)
    has_ac = models.BooleanField(null=True, blank=True)
    has_wifi = models.BooleanField(null=True, blank=True)
    has_freezer = models.BooleanField(null=True, blank=True)
    has_kitchen = models.BooleanField(null=True, blank=True)
    has_washing_machine = models.BooleanField(null=True, blank=True)
    has_dishes = models.BooleanField(null=True, blank=True)
    has_hot_water = models.BooleanField(null=True, blank=True)
    has_owners = models.BooleanField(null=True, blank=True)
    created_at = models.DateTimeField(null=True, blank=True)
    village_name = models.CharField(max_length=256, null=True, blank=True)
    id = models.PositiveIntegerField(default=0, primary_key=True)
    msg_url = models.CharField(max_length=1000)
    channel_id = models.CharField(max_length=256)
    grouped_id = models.CharField(null=True, max_length=256)
    image = models.ImageField(
        upload_to='product_images', null=True, blank=True)

    @staticmethod
    def format_price(price):
        if price is None or price == 0:
            return "—"
        try:
            return "{:,}".format(int(price)).replace(",", " ")
        except (ValueError, TypeError):
            return str(price) or "—"

    @property
    def price_month_formatted(self):
        return self.format_price(self.price_month)

    @property
    def price_day_formatted(self):
        return self.format_price(self.price_day)

    @property
    def agent_percent_formatted(self):
        return self.format_price(self.agent_percent)

    def save(self, *args, **kwargs):
        if not self.created_at:
            self.created_at = timezone.now().astimezone(pytz.timezone('Asia/Kolkata'))
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "Распознанные объявления"
        verbose_name_plural = "Распознанные объявления"

        def __str__(self):
            return self.name


class Tg_ads(models.Model):
    id = models.PositiveIntegerField(default=0, primary_key=True)
    channel_id = models.CharField(max_length=256)
    msg_url = models.CharField(max_length=1000)
    grouped_id = models.CharField(null=True, max_length=256)
    text = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(null=True, blank=True)
    is_trash = models.TextField(null=True, blank=True)

    class Meta:
        verbose_name = "Нераспознанные объявления"
        verbose_name_plural = "Нераспознанные объявления"

        def __str__(self):
            return self.name


class AdsImage(models.Model):
    ad = models.ForeignKey(
        Filter_items,
        on_delete=models.CASCADE,
        related_name="images"
    )
    image_url = models.URLField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'ads_cloud_image'          # ← вот это ключевая строка

    def __str__(self):
        return f"Image for Ads {self.ad.id}"


# ════════════════════════════════════════════════
#  Новая схема (2026-10): сервис services/ads/service.py
# ════════════════════════════════════════════════

class Listing(models.Model):
    """Разобранное объявление. Дубли из разных каналов склеиваются в одно."""

    GOA, ARMENIA, GEORGIA = "goa", "am", "ge"
    REGIONS = [(GOA, "Гоа"), (ARMENIA, "Армения"), (GEORGIA, "Грузия")]

    region = models.CharField("Регион", max_length=8, choices=REGIONS, default=GOA, db_index=True)
    village = models.CharField("Посёлок", max_length=100, null=True, blank=True, db_index=True)
    price_month = models.PositiveIntegerField("Цена за месяц, ₹", null=True, blank=True)
    price_day = models.PositiveIntegerField("Цена за сутки, ₹", null=True, blank=True)
    agent_percent = models.PositiveSmallIntegerField("Комиссия, %", null=True, blank=True)
    rooms = models.CharField("Комнаты", max_length=10, null=True, blank=True)

    has_ac = models.BooleanField("Кондиционер", null=True)
    has_wifi = models.BooleanField("Wi-Fi", null=True)
    has_fridge = models.BooleanField("Холодильник", null=True)
    has_kitchen = models.BooleanField("Кухня", null=True)
    has_washing_machine = models.BooleanField("Стиральная машина", null=True)
    has_dishes = models.BooleanField("Посуда", null=True)
    has_hot_water = models.BooleanField("Горячая вода", null=True)
    owners_nearby = models.BooleanField("Хозяева рядом", null=True)

    text = models.TextField("Текст")
    first_seen = models.DateTimeField("Впервые замечено", db_index=True)
    last_seen = models.DateTimeField("Последний раз замечено", db_index=True)

    class Meta:
        verbose_name = "Объявление"
        verbose_name_plural = "Объявления"
        ordering = ["-last_seen"]

    def __str__(self):
        return f"{self.village or '?'} · {self.rooms or '?'} · {self.price_month or '—'} ₹"

    @property
    def main_url(self):
        post = self.posts.order_by("-date").first()
        return post.url if post else ""


class Post(models.Model):
    """Сырое сообщение из Telegram-канала."""

    NEW, PARSED, DUPLICATE, TRASH, ERROR = "new", "parsed", "dup", "trash", "error"
    STATUSES = [(NEW, "новое"), (PARSED, "разобрано"), (DUPLICATE, "дубль"),
                (TRASH, "мусор"), (ERROR, "ошибка")]

    channel = models.CharField("Канал", max_length=100)
    msg_id = models.PositiveBigIntegerField("Номер сообщения")
    grouped_id = models.CharField(max_length=40, null=True, blank=True)
    text = models.TextField()
    text_hash = models.CharField(max_length=40, db_index=True)
    date = models.DateTimeField(db_index=True)
    status = models.CharField(max_length=8, choices=STATUSES, default=NEW, db_index=True)
    trash_reason = models.CharField(max_length=40, blank=True)
    # Обычно сообщение → одно объявление; прайс-лист («Fascino 7000, Aerox 14000») → несколько
    listings = models.ManyToManyField(Listing, blank=True, related_name="posts")
    motos = models.ManyToManyField("moto.MotoListing", blank=True, related_name="posts")
    stuffs = models.ManyToManyField("stuff.StuffListing", blank=True, related_name="posts")

    class Meta:
        verbose_name = "Сообщение"
        verbose_name_plural = "Сообщения"
        constraints = [models.UniqueConstraint(fields=["channel", "msg_id"],
                                               name="uniq_channel_msg")]

    def __str__(self):
        return f"@{self.channel}/{self.msg_id}"

    @property
    def url(self):
        return f"https://t.me/{self.channel}/{self.msg_id}"


class Photo(models.Model):
    listing = models.ForeignKey(Listing, on_delete=models.CASCADE, related_name="photos")
    path = models.CharField(max_length=300)  # относительно MEDIA_ROOT

    @property
    def is_video(self):
        """Превью видео сохраняются как v1.jpg, v2.jpg..."""
        return self.path.rsplit("/", 1)[-1].startswith("v")

    class Meta:
        verbose_name = "Фото"
        verbose_name_plural = "Фото"
