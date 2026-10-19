# Архитектура: модель C4, уровни 1–2

> Источники: `services/ads/service.py`, `services/ads/llm.py`, `ads/currency.py`, `ads/bot.py`, `ads/monitor.py`,
> `ads/visits.py`, `ads/seo.py`, `goads/settings.py`, `goads/urls.py`, `ads/templates/metrika.html`, `deploy/`.
> Диаграммы нарисованы блок-схемами Mermaid в нотации C4 (тип элемента — в квадратных скобках):
> встроенный в Mermaid тип `C4Context` на GitHub пока отображается нестабильно.

## Уровень 1. Контекст системы

Кто пользуется системой и с какими внешними системами она связана.

```mermaid
flowchart TB
    user(["<b>Пользователь</b><br/>[Person]<br/>Ищет жильё, байк или вещь<br/>в Гоа, Армении, Грузии, на Пхукете,<br/>чаще с телефона"])
    admin(["<b>Владелец</b><br/>[Person]<br/>Администрирует сайт,<br/>получает сводку и тревоги"])

    goads["<b>Goads</b><br/>[Software System]<br/>Собирает объявления из Telegram,<br/>разбирает их LLM и показывает<br/>на сайте с поиском и фильтрами;<br/>присылает новые по подписке"]

    tg["<b>Telegram</b><br/>[External System]<br/>55 открытых каналов и групп<br/>с объявлениями"]
    bot["<b>Telegram Bot API</b><br/>[External System]<br/>Бот @Goadoskabot:<br/>подписки и сообщения владельцу"]
    llm["<b>OpenRouter</b><br/>[External System]<br/>API языковых моделей,<br/>совместимый с OpenAI"]
    cbr["<b>Курсы ЦБ РФ</b><br/>[External System]<br/>JSON-зеркало cbr-xml-daily.ru"]
    search["<b>Яндекс, Google</b><br/>[External System]<br/>Поиск, Вебмастер,<br/>Search Console, Метрика"]

    user -->|"Ищет и смотрит объявления<br/>[HTTPS]"| goads
    user -->|"Переходит к исходному<br/>сообщению автора"| tg
    user -->|"Подписывается на поиск,<br/>получает новые объявления"| bot
    admin -->|"Просматривает и правит данные<br/>[HTTPS, админка Django]"| goads
    bot -->|"Сводка, тревоги"| admin
    goads -->|"Читает новые сообщения и фото<br/>[MTProto, Telethon]"| tg
    goads <-->|"Webhook входящих,<br/>отправка сообщений [HTTPS]"| bot
    goads -->|"Отправляет текст, получает JSON;<br/>проверяет остаток [HTTPS, REST]"| llm
    goads -->|"Получает курсы валют<br/>[HTTPS, JSON]"| cbr
    search -->|"Индексирует страницы Гоа<br/>(robots.txt, sitemap.xml)"| goads
    user -.->|"Счётчик Метрики в браузере"| search

    classDef person fill:#08427b,stroke:#052e56,color:#fff
    classDef system fill:#1168bd,stroke:#0b4884,color:#fff
    classDef external fill:#999,stroke:#6b6b6b,color:#fff
    class user,admin person
    class goads system
    class tg,bot,llm,cbr,search external
```

## Уровень 2. Контейнеры

Из чего состоит Goads на сервере и как части обмениваются данными.

```mermaid
flowchart LR
    user(["<b>Пользователь</b><br/>[Person]"])
    admin(["<b>Владелец</b><br/>[Person]"])

    subgraph vps["Отдельный VPS (Ubuntu 24.04, 2 ГБ RAM)"]
        direction LR
        nginx["<b>nginx</b><br/>[Container: веб-сервер]<br/>HTTPS (Let's Encrypt),<br/>www → goadoska.ru,<br/>отдаёт /static/ и /media/,<br/>остальное — в Gunicorn"]
        web["<b>Веб-приложение</b><br/>[Container: Django 6 + Gunicorn,<br/>3 воркера, служба goads-web]<br/>4 региона, фильтры, карточки,<br/>валюты, SEO, webhook бота,<br/>админка"]
        db[("<b>База данных</b><br/>[Container: SQLite, 28 МБ]<br/>Post, Listing, MotoListing,<br/>StuffListing, фото, подписки,<br/>справочник")]
        media[/"<b>Хранилище фото</b><br/>[Container: файлы, 1,8 ГБ]<br/>media/photos/"/]
        collector["<b>Служба сбора</b><br/>[Container: Python 3.12,<br/>служба goads-collector,<br/>лимит памяти 700 МБ]<br/>цикл раз в 10 минут,<br/>своя Telegram-сессия"]
        timers["<b>Таймеры обслуживания</b><br/>[Container: systemd timers]<br/>watchdog — каждые 10 мин,<br/>report — 9:00 по Гоа,<br/>backup — каждую ночь"]
        backups[/"<b>Резервные копии</b><br/>[Container: файлы]<br/>backups/*.db.gz, 7 шт."/]
    end

    home["<b>Домашний компьютер</b><br/>[Задача Windows]<br/>раз в неделю забирает<br/>последнюю копию"]
    cbr["<b>Курсы ЦБ РФ</b><br/>[External System]"]
    tg["<b>Telegram</b><br/>[External System]"]
    bot["<b>Telegram Bot API</b><br/>[External System]"]
    llm["<b>OpenRouter</b><br/>[External System]"]

    user -->|"HTTPS"| nginx
    admin -->|"HTTPS"| nginx
    nginx -->|"HTTP,<br/>только локально"| web
    nginx -->|"Читает файлы"| media
    web -->|"Читает; пишет подписки<br/>[Django ORM]"| db
    web -->|"Курсы, кэш 6 ч<br/>[HTTPS]"| cbr
    bot -->|"Webhook /tg/hook/<br/>[HTTPS, секрет]"| nginx
    web -->|"Ответы на команды"| bot

    collector -->|"Пишет сообщения<br/>и объявления<br/>[Django ORM]"| db
    collector -->|"JPEG ≤ 1280 px"| media
    collector -->|"Новые сообщения, история,<br/>проверка «снято» [MTProto]"| tg
    collector -->|"Текст → JSON,<br/>8 потоков [HTTPS]"| llm
    collector -->|"Новые объявления<br/>подписчикам, тревоги"| bot

    timers -->|"Читает статистику"| db
    timers -->|"Остаток денег"| llm
    timers -->|"Сводка, тревоги"| bot
    timers -->|"sqlite3 .backup"| backups
    home -->|"scp, раз в неделю"| backups

    classDef person fill:#08427b,stroke:#052e56,color:#fff
    classDef container fill:#438dd5,stroke:#2e6295,color:#fff
    classDef external fill:#999,stroke:#6b6b6b,color:#fff
    class user,admin person
    class nginx,web,collector,db,media,timers,backups container
    class tg,bot,llm,cbr,home external
```

## Пояснения к контейнерам

| Контейнер | Технология | Ответственность | Ключевые настройки |
|---|---|---|---|
| nginx | nginx | Завершает HTTPS, перенаправляет www, отдаёт статику и фото, проксирует остальное в Gunicorn; его журнал — источник подсчёта посетителей | Сертификат Let's Encrypt, автопродление `certbot.timer`; ufw: только ssh, 80, 443 |
| Веб-приложение | Django 6, Gunicorn | Списки с фильтрами и сортировкой по 4 регионам, карточки, перевод цен в валюты, SEO (robots, sitemap, превью), приём сообщений бота, вход (по настройке), админка | `SITE_HTTPS`, `SITE_LOGIN_REQUIRED`, `ALLOWED_HOSTS`, `YANDEX_METRIKA_ID`, `TG_BOT_*` |
| Служба сбора | Python 3.12, Telethon, Pillow | Сбор → догрузка истории → дубли → разбор LLM → отсев мусора → склейка → фото → рассылка бота → раз в ~3 ч проверка «снято» ([подробно](03-collection-sequence.md)) | `INTERVAL_MIN = 10`, `LLM_WORKERS = 8`, `MAX_AGE_DAYS = 7 / 14`, `LLM_MODEL`, `MemoryMax=700M` |
| Таймеры обслуживания | systemd timers + `manage.py monitor`, `deploy/backup_db.sh` | Сторож, утренняя сводка, ночная резервная копия ([ADR-0007](adr/0007-telegram-monitoring.md)) | `TG_ADMIN_CHAT_ID`, `STALE_MIN = 40`, `LOW_BALANCE_USD = 1` |
| База данных | SQLite (один файл) | Сообщения, объявления трёх разделов, пути к фото, подписки, справочник байков ([модель](04-data-model.md)) | [ADR-0001](adr/0001-sqlite.md) |
| Хранилище фото | Папки на диске | До 6 JPEG на объявление; обложки видео — `v1.jpg`, `v2.jpg`… | Папка `photos`, а не `ads` — иначе режут блокировщики рекламы |
| Резервные копии | gzip-файлы | Ночные копии базы с проверкой `integrity_check`, 7 последних + `latest.db.gz` | Восстановление: `gunzip` при остановленных службах |

## Взаимодействие контейнеров

- Служба сбора и сайт **не вызывают друг друга**: общаются только через базу и папку фото.
  Сайт можно перезапускать, не останавливая сбор, и наоборот.
- Объявления пишет **один процесс** — служба сбора; сайт пишет только подписки, вход и правки админки.
  Это снимает главное ограничение SQLite — одну запись в момент времени.
- Все четыре региона обслуживает **одна** служба сбора с одной Telegram-сессией ([ADR-0005](adr/0005-regions-as-config.md)).
  Второй экземпляр не стартует (блокировка файла): одна сессия в двух процессах ломает соединение.
- Рассылка подписчикам идёт из службы сбора сразу после цикла — по тем же функциям фильтрации (`build_queryset`),
  что и страницы сайта, поэтому бот и сайт показывают одно и то же.
- Курсы валют кэшируются на 6 часов; если ЦБ недоступен — запасные курсы, повторная попытка через 10 минут.
- Сборщик отмечает каждый завершённый цикл в `logs/heartbeat`; по нему сторож понимает, что сбор не завис.
- Почему сайт на отдельном сервере — [ADR-0003](adr/0003-separate-vps.md).
