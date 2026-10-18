"""Сообщения владельцу в Telegram (ads/monitor.py). Запускают таймеры systemd на сервере:
venv/bin/python manage.py monitor watchdog   # раз в 10 минут: жив ли сборщик, хватает ли денег на GPT
venv/bin/python manage.py monitor report     # утренняя сводка за сутки
venv/bin/python manage.py monitor print      # показать сводку здесь, ничего не отправляя"""
from django.core.management.base import BaseCommand

from ads import monitor


class Command(BaseCommand):
    help = "Сводка и тревоги владельцу через Telegram-бота (TG_ADMIN_CHAT_ID в .env)"

    def add_arguments(self, parser):
        parser.add_argument("action", choices=["watchdog", "report", "print"])

    def handle(self, *args, action, **options):
        if action == "print":
            self.stdout.write(monitor.report(save=False))
        elif not monitor.admin_chat():
            self.stderr.write("В .env нет TG_ADMIN_CHAT_ID — отправлять некому")
        elif action == "watchdog":
            monitor.watchdog()
        elif not monitor.send_admin(monitor.report()):
            self.stderr.write("Сводка не отправлена")
