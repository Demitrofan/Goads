"""Сообщить Telegram адрес, куда присылать сообщения боту. Запустить один раз после настройки .env:
venv/bin/python manage.py set_bot_webhook"""
from django.core.management.base import BaseCommand

from ads import bot


class Command(BaseCommand):
    help = "Настроить webhook Telegram-бота (TG_BOT_TOKEN, TG_BOT_SECRET в .env)"

    def handle(self, *args, **options):
        if not bot.token():
            self.stderr.write("В .env нет TG_BOT_TOKEN")
            return
        self.stdout.write(str(bot.set_webhook()))
        me = bot.api("getMe") or {}
        self.stdout.write(f"Бот: @{(me.get('result') or {}).get('username')}")
        bot.api("setMyCommands", commands=[
            {"command": "list", "description": "Мои подписки"},
            {"command": "stop", "description": "Отписаться от всего"},
        ])
