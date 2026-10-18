from django.db import models


class Tg_stuff(models.Model):
    single_msg_id = models.CharField(max_length=256, null=True, blank=True)
    grouped_id = models.CharField(max_length=256, null=True, blank=True)
    channel_id = models.CharField(max_length=256)
    msg_url = models.CharField(max_length=1000)
    text = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(null=True, blank=True)
    is_trash = models.BooleanField(null=True, blank=True)
    buy_ads = models.BooleanField(null=True, blank=True)


# ════════════════════════════════════════════════
#  Новая схема (2026-10): сервис services/ads/service.py
#  Сообщения хранятся в ads.Post, сюда попадают разобранные объявления барахолки.
# ════════════════════════════════════════════════

class StuffListing(models.Model):
    CATEGORIES = [
        ("electronics", "Электроника"),
        ("home", "Мебель и дом"),
        ("clothes", "Одежда и обувь"),
        ("kids", "Детское"),
        ("sport", "Спорт и отдых"),
        ("beauty", "Красота и здоровье"),
        ("other", "Другое"),
    ]
    CONDITIONS = [("new", "Новое"), ("used", "Б/у")]

    title = models.CharField("Что продаётся", max_length=120)
    category = models.CharField("Категория", max_length=12, choices=CATEGORIES, default="other", db_index=True)
    condition = models.CharField("Состояние", max_length=4, choices=CONDITIONS, null=True, blank=True)
    price = models.PositiveIntegerField("Цена, ₹", null=True, blank=True)
    is_free = models.BooleanField("Отдам даром", default=False)

    village = models.CharField("Посёлок", max_length=100, null=True, blank=True)
    text = models.TextField("Текст")
    first_seen = models.DateTimeField("Впервые замечено", db_index=True)
    last_seen = models.DateTimeField("Последний раз замечено", db_index=True)
    # Снято: автор удалил сообщение или дописал «сдано/продано». Из списков пропадает.
    closed = models.DateTimeField("Снято", null=True, blank=True, db_index=True)

    class Meta:
        verbose_name = "Вещь"
        verbose_name_plural = "Барахолка"
        ordering = ["-last_seen"]

    def __str__(self):
        return f"{self.title} · {'даром' if self.is_free else (self.price or '—')}"

    @property
    def main_url(self):
        post = self.posts.order_by("-date").first()
        return post.url if post else ""


class StuffPhoto(models.Model):
    listing = models.ForeignKey(StuffListing, on_delete=models.CASCADE, related_name="photos")
    path = models.CharField(max_length=300)  # относительно MEDIA_ROOT

    class Meta:
        verbose_name = "Фото вещи"
        verbose_name_plural = "Фото вещей"

    @property
    def is_video(self):
        return self.path.rsplit("/", 1)[-1].startswith("v")
