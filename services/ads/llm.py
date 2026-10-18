"""Разбор текста объявления через любой API, совместимый с OpenAI (OpenRouter, AITUNNEL и др.).

В .env: LLM_API_KEY (или OPENROUTER_API_KEY), LLM_BASE_URL, LLM_MODEL.
"""

import json
import os
import time
import urllib.error
import urllib.request

from loguru import logger

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"

PROMPT = """Ты разбираешь объявления из Telegram-чатов Гоа (Индия). Ответь ТОЛЬКО JSON-объектом с полями:

kind: что это за сообщение:
  "rent" — сдаётся жильё (дом, квартира, комната, вилла);
  "seek" — человек ищет жильё;
  "bike", "car" — аренда/продажа транспорта;
  "sale" — продажа или раздача вещей (техника, мебель, одежда, детское и т.п.);
  "property_sale" — продажа недвижимости или земли;
  "work", "service", "exchange", "visa" — работа, услуги, обмен валют, визы;
  "other" — всё остальное (болтовня, реклама, спам).
village: населённый пункт по-русски, с большой буквы, в правильном написании
  (Арамболь, Морджим, Ашвем, Мандрем, Нижний Мандрем, Верхний Мандрем, Сиолим, Керим, Палием,
  Каргао, Анджуна, Вагатор, Чапора, Ассагао, Калангут, Кандолим, Бага, Палолем, Агонда, Патнем)
  или null, если не указан.
price_month: цена за месяц в рупиях, целое число, или null. "30k", "30 к", "30 тыс" = 30000.
  Комиссию агента к цене НЕ прибавлять. Цену за неделю игнорировать.
  Если указаны разные цены по сезонам — бери цену высокого сезона (октябрь–март),
  а не цену «сезона дождей» / «муссона».
price_day: цена за сутки в рупиях, целое число, или null.
agent_percent: комиссия агента в процентах, целое число, или null.
  Если комиссия указана суммой в рупиях — переведи в процент от месячной цены и округли.
  Если написано "без комиссии" — 0.
rooms: "room" (комната), "1bk" (студия), "1bhk", "2bhk", "3bhk", "4bhk+" или null.
  "2 спальни" = "2bhk".
many_objects: true, только если в сообщении описаны несколько разных объектов со своими ценами
  (например, список из 3 квартир с ценами). Если подробно описан один объект с одной ценой
  (или вилкой цен) — это false, даже если в конце реклама агентства: "есть и другие варианты,
  пишите в ЛС", "есть разные объекты", "этот и ещё 700+ вариантов", ссылки на ботов,
  хэштеги вроде #31__40k.
has_ac, has_wifi, has_fridge, has_kitchen, has_washing_machine, has_dishes, has_hot_water,
owners_nearby: true (явно есть), false (явно нет) или null (не сказано).
  "Овнеры" = хозяева.

Если kind = "bike" (скутер или мотоцикл сдаётся или продаётся), добавь поля:
bike_model: марка и модель латиницей, как принято писать, например "Yamaha Aerox 155",
  "Honda Activa 6G", "Royal Enfield Classic 350", или null.
bike_kind: "scooter" или "motorcycle".
bike_year: год выпуска или null.
price_sell: цена продажи в рупиях или null (для аренды — null).
agent_fee: комиссия агента в рупиях или null; "без комиссии" — 0.
has_helmet, has_delivery, need_deposit, need_passport: true / false / null.
  "Без залогов и депозитов" — need_deposit false. "Фото паспорта", "копия паспорта" — need_passport true.
Для байков поля price_month, price_day, village, many_objects заполняются так же, как для жилья.
Список из нескольких разных моделей с разными ценами — many_objects true.

Если kind = "sale" (барахолка), добавь поля:
item_title: что продаётся, коротко, 2–6 слов, с большой буквы, например "Детская коляска Chicco",
  "Сёрф-доска 7'2", "Кондиционер LG 1.5 т".
item_category: "electronics" (техника, телефоны, ноутбуки), "home" (мебель, посуда, всё для дома),
  "clothes" (одежда, обувь, сумки), "kids" (детские вещи, игрушки), "sport" (сёрф, йога, велосипеды),
  "beauty" (косметика, здоровье) или "other".
item_condition: "new", "used" или null.
price_sell: цена в рупиях. Если цена в рублях — переведи в рупии, умножив на 1.15.
is_free: true, если отдают даром.
Если продаётся несколько разных вещей со своими ценами — many_objects true.

Если many_objects = true, добавь поле items — список объектов (не больше 15). В каждом — только то,
чем объекты отличаются друг от друга:
  жильё: village, rooms, price_month, price_day;
  байки: bike_model, bike_kind, price_month, price_day, price_sell;
  барахолка: item_title, item_category, item_condition, price_sell, is_free.
Общее для всех (посёлок, комиссия, удобства, шлем, доставка, залог) пиши на верхнем уровне.
Объекты без цены в items не включай.
Пример: "Fascino — 7000/500, Aerox — 14000/1000, Арамболь" →
  "village": "Арамболь", "many_objects": true, "items": [
    {"bike_model": "Yamaha Fascino 125", "bike_kind": "scooter", "price_month": 7000, "price_day": 500},
    {"bike_model": "Yamaha Aerox 155", "bike_kind": "scooter", "price_month": 14000, "price_day": 1000}]
"""

# Армения (Ереван): только жильё. Цены — в валюте объявления, в рупии переводит сервис.
PROMPT_ARMENIA = """Ты разбираешь объявления об аренде жилья из Telegram-каналов Армении (в основном Ереван).
Ответь ТОЛЬКО JSON-объектом с полями:

kind: "rent" — сдаётся жильё (квартира, дом, комната); "seek" — человек ищет жильё;
  "property_sale" — продажа недвижимости; "other" — всё остальное (реклама, услуги, болтовня).
city: город по-русски: Ереван, Гюмри, Дилижан, Цахкадзор, Абовян, Ванадзор, Севан…
  Если город не назван, но указан район или улица Еревана — "Ереван". Пригород или село рядом
  с Ереваном (Джрвеж, Дзорахбюр, Масис, Птгни) — это отдельный city, не Ереван. null, если место не указано.
village: только для Еревана — район по-русски, с большой буквы (Кентрон, Арабкир, Ачапняк, Аван,
  Давташен, Эребуни, Канакер-Зейтун, Малатия-Себастия, Нор-Норк, Норк-Мараш, Нубарашен, Шенгавит).
  Улица без района — определи район по улице, если уверен, иначе null. Для других городов — null.
price_month: цена за месяц, целое число, в валюте объявления, или null. "350к", "350 000" = 350000.
price_day: цена за сутки, целое число, в валюте объявления, или null.
currency: валюта цены: "AMD" (драм, ֏, dram), "USD" ($), "RUB" (₽, руб), "EUR" (€).
  Если валюта не указана: число меньше 10000 — "USD", иначе "AMD".
agent_percent: комиссия агента в процентах, целое число, или null. "без комиссии" — 0.
  Комиссия «50% от месячной цены» = 50.
rooms: "room" (комната), "1k" (однокомнатная), "2k", "3k", "4k+" или null.
  В Армении считают все комнаты: "2-комнатная" = "2k", "3 комнаты" = "3k".
many_objects: true, только если в сообщении несколько разных квартир со своими ценами.
has_ac, has_wifi, has_fridge, has_kitchen, has_washing_machine, has_dishes, has_hot_water,
owners_nearby: true (явно есть), false (явно нет) или null (не сказано).

Если many_objects = true, добавь поле items — список квартир (не больше 15), в каждой:
city, village, rooms, price_month, price_day, currency. Квартиры без цены не включай.
"""

# Грузия (Тбилиси, Батуми): только жильё. Цены — в валюте объявления, в рупии переводит сервис.
PROMPT_GEORGIA = """Ты разбираешь объявления об аренде жилья из Telegram-каналов Грузии (в основном Тбилиси и Батуми).
Объявления бывают на русском и английском. Ответь ТОЛЬКО JSON-объектом с полями:

kind: "rent" — сдаётся жильё (квартира, дом, комната); "seek" — человек ищет жильё;
  "property_sale" — продажа недвижимости; "other" — всё остальное (реклама, услуги, болтовня).
city: город по-русски: Тбилиси, Батуми, Кутаиси, Гудаури, Бакуриани, Мцхета, Кобулети…
  Если город не назван, но указан район или улица Тбилиси — "Тбилиси". Цхнети, Лиси, Цодорети,
  Окрокана, Табахмела — это Тбилиси. Сёла дальше от города (Сагурамо, Мухрани) — отдельный city.
  null, если место не указано.
village: район внутри города по-русски, с большой буквы, или null.
  Тбилиси: Мтацминда, Ваке, Сабуртало, Крцаниси, Исани, Самгори, Чугурети, Дидубе, Надзаладеви, Глдани.
  Микрорайон или улицу переведи в район: Сололаки, Вера → Мтацминда; Ортачала → Крцаниси;
  Авлабари → Исани; Варкетили → Самгори; Дигоми, Диди Дигоми → Сабуртало; Багеби, Лиси, Цхнети → Ваке.
  Батуми: Старый Батуми (старый город), Новый бульвар, Махинджаури, Гонио.
  Не уверен в районе — null. Для других городов — null.
price_month: цена за месяц, целое число, в валюте объявления, или null. "1.2k", "1 200" = 1200.
price_day: цена за сутки, целое число, в валюте объявления, или null.
currency: валюта цены: "USD" ($, долларов), "GEL" (₾, лари, GEL), "EUR" (€), "RUB" (₽, руб).
  Если валюта не указана — "USD".
agent_percent: комиссия агента в процентах, целое число, или null. "без комиссии" — 0.
  Комиссия «50% от месячной цены» = 50.
rooms: "room" (комната), "1k" (однокомнатная, студия), "2k", "3k", "4k+" или null.
  Считай все комнаты: "2-комнатная" = "2k", "Комнаты: 3" = "3k". Если указаны только спальни
  ("2 спальни", "2 bedrooms", "2bed"), комнат на одну больше: "1bed" = "2k", "2bed" = "3k".
many_objects: true, только если в сообщении несколько разных квартир со своими ценами.
has_ac, has_wifi, has_fridge, has_kitchen, has_washing_machine, has_dishes, has_hot_water,
owners_nearby: true (явно есть), false (явно нет) или null (не сказано).

Если many_objects = true, добавь поле items — список квартир (не больше 15), в каждой:
city, village, rooms, price_month, price_day, currency. Квартиры без цены не включай.
"""

FIELDS_BOOL = ["has_ac", "has_wifi", "has_fridge", "has_kitchen", "has_washing_machine",
               "has_dishes", "has_hot_water", "owners_nearby"]
ROOMS = {"room", "1bk", "1bhk", "2bhk", "3bhk", "4bhk+",
         "1k", "2k", "3k", "4k+"}   # последние — Армения и Грузия: считают все комнаты
CURRENCIES = {"AMD", "GEL", "USD", "RUB", "EUR", "INR"}
FIELDS_BIKE_BOOL = ["has_helmet", "has_delivery", "need_deposit", "need_passport"]
ITEM_CATEGORIES = {"electronics", "home", "clothes", "kids", "sport", "beauty", "other"}


def _int_or_none(v):
    try:
        v = int(float(v))
        return v if v >= 0 else None
    except (TypeError, ValueError):
        return None


MAX_ITEMS = 15


def _clean(data: dict) -> dict:
    """Приводит ответ модели к ожидаемым типам. items — позиции списка, каждая уже с общими полями."""
    out = _clean_one(data)
    items = data.get("items") if out["many_objects"] else None
    out["items"] = [_clean_one({**data, **it, "many_objects": False})
                    for it in (items if isinstance(items, list) else [])[:MAX_ITEMS]
                    if isinstance(it, dict)]
    return out


def _clean_one(data: dict) -> dict:
    """Приводит ответ модели к ожидаемым типам: модели иногда путают форматы."""
    out = {
        "kind": str(data.get("kind") or "other").lower(),
        "village": (str(data["village"]).strip() or None) if data.get("village") else None,
        "city": (str(data["city"]).strip() or None) if data.get("city") else None,
        "price_month": _int_or_none(data.get("price_month")),
        "price_day": _int_or_none(data.get("price_day")),
        "agent_percent": _int_or_none(data.get("agent_percent")),
        "rooms": str(data.get("rooms") or "").lower() or None,
        "many_objects": bool(data.get("many_objects")),
    }
    rooms = (out["rooms"] or "").replace(" ", "")
    if rooms[:1].isdigit() and int(rooms[0]) >= 4 and "bhk" in rooms:
        rooms = "4bhk+"   # 4bhk, 5bhk, 4bhk+ → одна категория
    elif rooms[:1].isdigit() and int(rooms[0]) >= 4 and rooms.rstrip("+").endswith("k"):
        rooms = "4k+"
    out["rooms"] = rooms if rooms in ROOMS else None
    if out["agent_percent"] is not None and out["agent_percent"] > 100:
        out["agent_percent"] = None
    for f in FIELDS_BOOL + FIELDS_BIKE_BOOL:
        v = data.get(f)
        out[f] = v if isinstance(v, bool) else None
    out["bike_model"] = (str(data["bike_model"]).strip() or None) if data.get("bike_model") else None
    out["bike_kind"] = data.get("bike_kind") if data.get("bike_kind") in ("scooter", "motorcycle") else None
    out["bike_year"] = _int_or_none(data.get("bike_year"))
    if out["bike_year"] and not 1950 <= out["bike_year"] <= 2030:
        out["bike_year"] = None
    out["price_sell"] = _int_or_none(data.get("price_sell"))
    out["item_title"] = (str(data["item_title"]).strip()[:120] or None) if data.get("item_title") else None
    out["item_category"] = data.get("item_category") if data.get("item_category") in ITEM_CATEGORIES else "other"
    out["item_condition"] = data.get("item_condition") if data.get("item_condition") in ("new", "used") else None
    out["is_free"] = data.get("is_free") is True
    out["agent_fee"] = _int_or_none(data.get("agent_fee"))
    cur = str(data.get("currency") or "").upper()
    out["currency"] = cur if cur in CURRENCIES else "INR"
    return out


def parse_ad(text: str, model: str, retries: int = 3, prompt: str = PROMPT) -> dict | None:
    """Возвращает словарь с полями объявления или None, если модель не ответила."""
    key = (os.environ.get("LLM_API_KEY") or os.environ["OPENROUTER_API_KEY"]).strip()
    url = os.environ.get("LLM_BASE_URL", DEFAULT_BASE_URL).rstrip("/") + "/chat/completions"
    payload = {
        "model": model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": text[:4000]},
        ],
    }

    for attempt in range(1, retries + 1):
        body = json.dumps(payload).encode()
        req = urllib.request.Request(url, data=body, headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "X-Title": "Goads",
        })
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                answer = json.load(resp)
            content = answer["choices"][0]["message"]["content"]
            # Некоторые модели оборачивают JSON в ```json ... ```
            content = content.strip().removeprefix("```json").removeprefix("```").removesuffix("```")
            return _clean(json.loads(content))
        except urllib.error.HTTPError as e:
            msg = e.read()[:300].decode(errors="replace")
            logger.warning(f"LLM HTTP {e.code} (попытка {attempt}): {msg}")
            if e.code in (401, 402, 403):  # неверный ключ или нет денег: повторять бесполезно
                raise RuntimeError(f"LLM API отказал ({e.code}): {msg}") from e
            if e.code == 400 and "response_format" in payload and (
                    "structured" in msg or "response_format" in msg or "json" in msg.lower()):
                payload.pop("response_format")  # модель не умеет JSON-режим: просим JSON в промпте
                continue
        except Exception as e:
            logger.warning(f"LLM ошибка (попытка {attempt}): {type(e).__name__}: {e}")
        time.sleep(5 * attempt)
    return None
