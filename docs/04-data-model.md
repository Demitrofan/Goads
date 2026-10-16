# Модель данных (ER)

> Источники: `ads/models.py`, `moto/models.py`, `stuff/models.py`; связи разделов — таблица `SECTIONS`
> в `services/ads/service.py`. СУБД — SQLite ([ADR-0001](adr/0001-sqlite.md)).

## Идея модели

- **`Post`** — сырое сообщение из Telegram, общее для всех разделов. Что это за объявление, решает LLM уже после сохранения.
- **Объявления** — результат разбора, по таблице на раздел: `Listing` (жильё), `MotoListing` (байки),
  `StuffListing` (барахолка). Поля разделов слишком разные, чтобы хранить их в одной таблице.
- **Сообщение ↔ объявление — многие-ко-многим.** Одно объявление собирается из нескольких сообщений
  (дубли в разных каналах), а одно сообщение-прайс-лист («Fascino 7000, Aerox 14000») даёт несколько объявлений.
  Связь один-к-одному теряла бы либо данные, либо плодила дубли карточек.
- **Фото принадлежат объявлению**, хранится только путь к файлу. У позиций одного прайс-листа общие фото.
- **`model_info`** — справочник характеристик байков. Связи по ключу нет: при создании `MotoListing`
  объём, мощность и вес *копируются* из справочника по похожему названию модели.

## Диаграмма

Промежуточные таблицы многие-ко-многим Django создаёт сам; на диаграмме они показаны явно.

```mermaid
erDiagram
    Post ||--o{ Post_listings : ""
    Listing ||--o{ Post_listings : ""
    Post ||--o{ Post_motos : ""
    MotoListing ||--o{ Post_motos : ""
    Post ||--o{ Post_stuffs : ""
    StuffListing ||--o{ Post_stuffs : ""

    Listing ||--o{ Photo : "photos"
    MotoListing ||--o{ MotoPhoto : "photos"
    StuffListing ||--o{ StuffPhoto : "photos"
    model_info |o..o{ MotoListing : "характеристики копируются по названию"

    Post {
        bigint id PK
        varchar channel UK "имя канала; уникально вместе с msg_id"
        bigint msg_id UK "номер сообщения в канале"
        varchar grouped_id "альбом, может быть пустым"
        text text "текст сообщения"
        varchar text_hash "SHA-1 нормализованного текста, индекс"
        datetime date "дата публикации, индекс"
        varchar status "new, parsed, dup, trash, error; индекс"
        varchar trash_reason "причина, если trash"
    }
    Post_listings {
        bigint post_id FK
        bigint listing_id FK
    }
    Post_motos {
        bigint post_id FK
        bigint motolisting_id FK
    }
    Post_stuffs {
        bigint post_id FK
        bigint stufflisting_id FK
    }
    Listing {
        bigint id PK
        varchar village "посёлок, индекс"
        int price_month "рупии"
        int price_day "рупии"
        smallint agent_percent "комиссия, %"
        varchar rooms "room, 1bk, 1bhk, 2bhk, 3bhk, 4bhk+"
        bool has_ac "да / нет / не сказано"
        bool has_wifi
        bool has_fridge
        bool has_kitchen
        bool has_washing_machine
        bool has_dishes
        bool has_hot_water
        bool owners_nearby
        text text "текст первого сообщения"
        datetime first_seen "индекс"
        datetime last_seen "индекс; сортировка"
    }
    MotoListing {
        bigint id PK
        varchar model_name "индекс"
        varchar kind "scooter, motorcycle"
        smallint year
        float engine "см3, из справочника"
        float horse_power "л.с., из справочника"
        float weight "кг, из справочника"
        int price_month "рупии"
        int price_day "рупии"
        int price_sell "рупии"
        int agent_fee "комиссия, рупии"
        bool has_helmet
        bool has_delivery
        bool need_deposit
        bool need_passport
        varchar village
        text text
        datetime first_seen "индекс"
        datetime last_seen "индекс"
    }
    StuffListing {
        bigint id PK
        varchar title "что продаётся"
        varchar category "electronics, home, clothes, kids, sport, beauty, other"
        varchar condition "new, used"
        int price "рупии"
        bool is_free "отдам даром"
        varchar village
        text text
        datetime first_seen "индекс"
        datetime last_seen "индекс"
    }
    Photo {
        bigint id PK
        bigint listing_id FK
        varchar path "относительно media/; v*.jpg — обложка видео"
    }
    MotoPhoto {
        bigint id PK
        bigint listing_id FK
        varchar path
    }
    StuffPhoto {
        bigint id PK
        bigint listing_id FK
        varchar path
    }
    model_info {
        bigint id PK
        varchar moto_models_name "название модели"
        float engine
        float horse_power
        float weight
        text description
    }
```

## Таблицы

| Таблица | Приложение | Назначение | Ключевые ограничения |
|---|---|---|---|
| `Post` | `ads` | Сырые сообщения всех каналов | Уникальность (`channel`, `msg_id`) — повторный сбор не создаёт копий |
| `Listing` | `ads` | Объявления о жилье | Цены — неотрицательные целые, ₹ |
| `MotoListing` | `moto` | Объявления о байках (аренда и продажа) | `kind` — из списка |
| `StuffListing` | `stuff` | Вещи на барахолке | `category` по умолчанию `other` |
| `Photo`, `MotoPhoto`, `StuffPhoto` | по разделам | Пути к фото | Удаляются вместе с объявлением (CASCADE) |
| `model_info` | `moto` | Справочник характеристик моделей байков | Наполнен заранее, сервис только читает его |

## Соответствие раздела и таблиц

Сервис выбирает таблицы по виду объявления, который вернул LLM (`SECTIONS` в `service.py`):

| Вид (`kind`) | Объявление | Фото | Поле связи в `Post` | Папка фото |
|---|---|---|---|---|
| `rent` | `Listing` | `Photo` | `listings` | `media/photos/<id>/` |
| `bike` | `MotoListing` | `MotoPhoto` | `motos` | `media/photos/moto/<id>/` |
| `sale` | `StuffListing` | `StuffPhoto` | `stuffs` | `media/photos/stuff/<id>/` |

## Даты объявления

- `first_seen` — дата первого сообщения, из которого создано объявление.
- `last_seen` — дата самого свежего привязанного сообщения. Каждый дубль или склейка сдвигает её вперёд;
  по ней сайт фильтрует «за неделю / за месяц» и сортирует «сначала свежие».

## Архивные таблицы

`Filter_items`, `Tg_ads`, `AdsImage` (`ads`), `Filter_items_moto`, `Tg_moto` (`moto`), `Tg_stuff` (`stuff`) —
таблицы прежней версии, где каждый раздел собирался своими скриптами. Новым сервисом не используются,
оставлены как архив; на диаграмме не показаны.
