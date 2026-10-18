from django.db import models
from django.utils import timezone
import pytz


class Filter_items_moto(models.Model):
    # moto или скутер
    ulid = models.CharField(max_length=256, null=True, blank=True)
    body = models.TextField(null=True, blank=True)
    moto_models_name = models.CharField(max_length=256, null=True, blank=True)
    is_it_motorcycle = models.BooleanField(null=True, blank=True)
    price_month = models.IntegerField(null=True, blank=True)
    price_day = models.IntegerField(null=True, blank=True)
    agent_percent = models.IntegerField(null=True, blank=True)
    price_sell = models.IntegerField(null=True, blank=True)
    engine = models.FloatField(null=True, blank=True)
    horse_power = models.FloatField(null=True, blank=True)
    weight = models.FloatField(null=True, blank=True)
    has_helmet = models.BooleanField(null=True, blank=True)
    need_deposit = models.BooleanField(null=True, blank=True)
    need_passport = models.BooleanField(null=True, blank=True)
    has_delivery = models.BooleanField(null=True, blank=True)
    # is_it_car = models.BooleanField(null=True, blank=True)
    village_name = models.CharField(max_length=256, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(null=True, blank=True)
    id = models.PositiveIntegerField(default=0, primary_key=True)
    channel_id = models.CharField(max_length=256)
    msg_url = models.CharField(max_length=1000)
    grouped_id = models.CharField(null=True, max_length=256)
    year = models.IntegerField(null=True, blank=True)
    provider = models.CharField(max_length=256, null=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.created_at:
            self.created_at = timezone.now().astimezone(pytz.timezone('Asia/Kolkata'))
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "Распознанные объявления"
        verbose_name_plural = "Распознанные объявления"

        def __str__(self):
            return self.name


class Tg_moto(models.Model):
    id = models.PositiveIntegerField(default=0, primary_key=True)
    single_msg_id = models.CharField(max_length=256, null=True, blank=True)
    grouped_id = models.CharField(null=True, max_length=256)
    channel_id = models.CharField(max_length=256)
    msg_url = models.CharField(max_length=1000)
    text = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(null=True, blank=True)
    is_trash = models.BooleanField(null=True, blank=True)
    is_many_models = models.BooleanField(null=True, blank=True)

    class Meta:
        verbose_name = "Нераспознанные объявления"
        verbose_name_plural = "Нераспознанные объявления"

        def __str__(self):
            return self.name


class model_info(models.Model):
    moto_models_name = models.CharField(max_length=256, null=True, blank=True)
    engine = models.FloatField(max_length=256, null=True, blank=True)
    horse_power = models.FloatField(null=True, blank=True)
    weight = models.FloatField(null=True, blank=True)
    description = models.TextField(null=True, blank=True)


# ════════════════════════════════════════════════
#  Новая схема (2026-10): сервис services/ads/service.py
#  Сообщения хранятся в ads.Post, сюда попадают разобранные объявления о байках.
# ════════════════════════════════════════════════

class MotoListing(models.Model):
    SCOOTER, MOTORCYCLE = "scooter", "motorcycle"
    KINDS = [(SCOOTER, "Скутер"), (MOTORCYCLE, "Мотоцикл")]

    # Гоа или Пхукет (коды как у Listing.REGIONS)
    region = models.CharField("Регион", max_length=8, default="goa", db_index=True)
    model_name = models.CharField("Модель", max_length=100, null=True, blank=True, db_index=True)
    kind = models.CharField("Тип", max_length=12, choices=KINDS, null=True, blank=True)
    year = models.PositiveSmallIntegerField("Год", null=True, blank=True)
    engine = models.FloatField("Объём, см³", null=True, blank=True)
    horse_power = models.FloatField("Мощность, л.с.", null=True, blank=True)
    weight = models.FloatField("Вес, кг", null=True, blank=True)

    price_month = models.PositiveIntegerField("Цена за месяц, ₹", null=True, blank=True)
    price_day = models.PositiveIntegerField("Цена за сутки, ₹", null=True, blank=True)
    price_sell = models.PositiveIntegerField("Цена продажи, ₹", null=True, blank=True)
    agent_fee = models.PositiveIntegerField("Комиссия, ₹", null=True, blank=True)

    has_helmet = models.BooleanField("Шлем", null=True)
    has_delivery = models.BooleanField("Доставка", null=True)
    need_deposit = models.BooleanField("Залог", null=True)
    need_passport = models.BooleanField("Паспорт", null=True)

    village = models.CharField("Посёлок", max_length=100, null=True, blank=True)
    text = models.TextField("Текст")
    first_seen = models.DateTimeField("Впервые замечено", db_index=True)
    last_seen = models.DateTimeField("Последний раз замечено", db_index=True)
    # Снято: автор удалил сообщение или дописал «сдано/продано». Из списков пропадает.
    closed = models.DateTimeField("Снято", null=True, blank=True, db_index=True)

    class Meta:
        verbose_name = "Байк"
        verbose_name_plural = "Байки"
        ordering = ["-last_seen"]

    def __str__(self):
        return f"{self.model_name or '?'} · {self.price_month or '—'} ₹/мес"

    @property
    def main_url(self):
        post = self.posts.order_by("-date").first()
        return post.url if post else ""


class MotoPhoto(models.Model):
    listing = models.ForeignKey(MotoListing, on_delete=models.CASCADE, related_name="photos")
    path = models.CharField(max_length=300)  # относительно MEDIA_ROOT

    class Meta:
        verbose_name = "Фото байка"
        verbose_name_plural = "Фото байков"

    @property
    def is_video(self):
        return self.path.rsplit("/", 1)[-1].startswith("v")
