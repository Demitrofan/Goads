# Архитектура: модель C4, уровни 1–2

> Источники: `services/ads/service.py`, `services/ads/llm.py`, `ads/currency.py`, `goads/settings.py`,
> `goads/urls.py`, `ads/templates/metrika.html`.
> Диаграммы нарисованы блок-схемами Mermaid в нотации C4 (тип элемента — в квадратных скобках):
> встроенный в Mermaid тип `C4Context` на GitHub пока отображается нестабильно.

## Уровень 1. Контекст системы

Кто пользуется системой и с какими внешними системами она связана.

```mermaid
flowchart TB
    user(["<b>Пользователь</b><br/>[Person]<br/>Ищет жильё, байк или вещь в Гоа,<br/>чаще с телефона"])
    admin(["<b>Владелец</b><br/>[Person]<br/>Администрирует сайт,<br/>следит за качеством разбора"])

    goads["<b>Goads</b><br/>[Software System]<br/>Собирает объявления из Telegram,<br/>разбирает их LLM и показывает<br/>на сайте с поиском и фильтрами"]

    tg["<b>Telegram</b><br/>[External System]<br/>34 публичных канала<br/>с объявлениями"]
    llm["<b>OpenRouter</b><br/>[External System]<br/>API языковых моделей,<br/>совместимый с OpenAI"]
    cbr["<b>Курсы ЦБ РФ</b><br/>[External System]<br/>JSON-зеркало cbr-xml-daily.ru"]
    metrika["<b>Яндекс Метрика</b><br/>[External System]<br/>Статистика посещений"]

    user -->|"Ищет и смотрит объявления<br/>[HTTPS]"| goads
    user -->|"Переходит к исходному<br/>сообщению автора"| tg
    admin -->|"Просматривает и правит данные<br/>[HTTPS, админка Django]"| goads
    goads -->|"Читает новые сообщения и фото<br/>[MTProto, Telethon]"| tg
    goads -->|"Отправляет текст, получает JSON<br/>[HTTPS, REST]"| llm
    goads -->|"Получает курсы валют<br/>[HTTPS, JSON]"| cbr
    user -.->|"Счётчик в браузере"| metrika

    classDef person fill:#08427b,stroke:#052e56,color:#fff
    classDef system fill:#1168bd,stroke:#0b4884,color:#fff
    classDef external fill:#999,stroke:#6b6b6b,color:#fff
    class user,admin person
    class goads system
    class tg,llm,cbr,metrika external
```

## Уровень 2. Контейнеры

Из чего состоит Goads на сервере и как части обмениваются данными.

```mermaid
flowchart LR
    user(["<b>Пользователь</b><br/>[Person]"])
    admin(["<b>Владелец</b><br/>[Person]"])

    subgraph vps["Отдельный VPS (Linux)"]
        direction LR
        nginx["<b>nginx</b><br/>[Container: веб-сервер]<br/>HTTPS (Let's Encrypt),<br/>отдаёт /static/ и /media/,<br/>остальное — в Gunicorn"]
        web["<b>Веб-приложение</b><br/>[Container: Django 6 + Gunicorn,<br/>systemd-служба]<br/>/rent/, /moto/, /stuff/,<br/>фильтры, карточки,<br/>валюты, админка"]
        db[("<b>База данных</b><br/>[Container: SQLite]<br/>Post, Listing, MotoListing,<br/>StuffListing, фото,<br/>справочник")]
        media[/"<b>Хранилище фото</b><br/>[Container: файлы]<br/>media/photos/"/]
        collector["<b>Служба сбора</b><br/>[Container: Python 3.12,<br/>systemd-служба]<br/>services/ads/service.py,<br/>цикл раз в 10 минут,<br/>своя Telegram-сессия"]
    end

    cbr["<b>Курсы ЦБ РФ</b><br/>[External System]"]
    tg["<b>Telegram</b><br/>[External System]"]
    llm["<b>OpenRouter</b><br/>[External System]"]

    user -->|"HTTPS"| nginx
    admin -->|"HTTPS"| nginx
    nginx -->|"HTTP,<br/>только локально"| web
    nginx -->|"Читает файлы"| media
    web -->|"Читает<br/>[Django ORM]"| db
    web -->|"Курсы, кэш 6 ч<br/>[HTTPS]"| cbr

    collector -->|"Пишет сообщения<br/>и объявления<br/>[Django ORM]"| db
    collector -->|"JPEG ≤ 1280 px"| media
    collector -->|"Новые сообщения, фото<br/>[MTProto]"| tg
    collector -->|"Текст → JSON,<br/>8 потоков [HTTPS]"| llm

    classDef person fill:#08427b,stroke:#052e56,color:#fff
    classDef container fill:#438dd5,stroke:#2e6295,color:#fff
    classDef external fill:#999,stroke:#6b6b6b,color:#fff
    class user,admin person
    class nginx,web,collector,db,media container
    class tg,llm,cbr external
```

## Пояснения к контейнерам

| Контейнер | Технология | Ответственность | Ключевые настройки |
|---|---|---|---|
| nginx | nginx | Завершает HTTPS, отдаёт статику и фото, проксирует остальное в Gunicorn | Сертификат Let's Encrypt, автопродление |
| Веб-приложение | Django 6, Gunicorn | Списки с фильтрами и сортировкой, карточки, перевод цен в валюты, вход (по настройке), админка | `SITE_HTTPS`, `SITE_LOGIN_REQUIRED`, `ALLOWED_HOSTS` |
| Служба сбора | Python 3.12, Telethon, Pillow | Сбор → дубли → разбор LLM → отсев мусора → склейка → фото ([подробно](03-collection-sequence.md)) | `INTERVAL_MIN = 10`, `LLM_WORKERS = 8`, `MAX_AGE_DAYS = 7`, `LLM_MODEL` |
| База данных | SQLite (один файл) | Сообщения, объявления трёх разделов, пути к фото, справочник байков ([модель](04-data-model.md)) | [ADR-0001](adr/0001-sqlite.md) |
| Хранилище фото | Папки на диске | До 6 JPEG на объявление; обложки видео — `v1.jpg`, `v2.jpg`… | Папка `photos`, а не `ads` — иначе режут блокировщики рекламы |

## Взаимодействие контейнеров

- Служба сбора и сайт **не вызывают друг друга**: общаются только через базу и папку фото.
  Сайт можно перезапускать, не останавливая сбор, и наоборот.
- В базу пишет **один процесс** — служба сбора; сайт только читает (кроме входа и админки).
  Это снимает главное ограничение SQLite — одну запись в момент времени.
- Второй экземпляр службы сбора не стартует (блокировка файла): одна Telegram-сессия в двух процессах
  ломает соединение.
- Курсы валют кэшируются на 6 часов; если ЦБ недоступен — запасные курсы, повторная попытка через 10 минут.
- Почему сайт на отдельном сервере — [ADR-0003](adr/0003-separate-vps.md).
