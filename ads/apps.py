from django.apps import AppConfig


class AdsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'ads'
    verbose_name = "Объявления"

    def ready(self):
        from ads import lookups
        lookups.register()   # поиск по словам без учёта регистра и для кириллицы
