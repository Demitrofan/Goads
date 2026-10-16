# Проверка Telegram-сессий: только чтение, без входа и без отправки сообщений.
# Запуск из корня проекта: venv/Scripts/python check_telegram.py

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "services" / "ads" / "parser"))
from tg_urls import tg_urls as ads_urls  # noqa: E402

# Та же сессия и приложение, что у сервиса сбора (services/ads/service.py)
APP = (int(os.environ["TG_API_ID_2"]), os.environ["TG_API_HASH_2"])

SESSIONS = [
    ("media_session", APP),
]


async def check(name, app):
    print(f"\n=== {name}.session ===")
    client = TelegramClient(str(ROOT / name), *app)
    await client.connect()
    try:
        if not await client.is_user_authorized():
            print("  НЕ АВТОРИЗОВАНА (нужен повторный вход по коду)")
            return False
        me = await client.get_me()
        print(f"  OK: {me.first_name or ''} (@{me.username or '-'})")
        return True
    finally:
        await client.disconnect()


async def check_channels(name, app):
    print(f"\n=== Каналы аренды через {name} ===")
    async with TelegramClient(str(ROOT / name), *app) as client:
        for url in ads_urls:
            try:
                msgs = await client.get_messages(url, limit=1)
                last = msgs[0].date.strftime("%Y-%m-%d %H:%M") if msgs else "пусто"
                print(f"  {url:45} последнее: {last}")
            except Exception as e:
                print(f"  {url:45} ОШИБКА: {type(e).__name__}: {e}")


async def main():
    alive = None
    for name, app in SESSIONS:
        try:
            if await check(name, app) and alive is None:
                alive = (name, app)
        except Exception as e:
            print(f"  ОШИБКА: {type(e).__name__}: {e}")
    if alive:
        await check_channels(*alive)


asyncio.run(main())
