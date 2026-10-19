"""Посетители сайта за сутки — по журналу nginx, для утренней сводки.

Человек = адрес, который загрузил оформление сайта (rent.css) обычным браузером: роботы и
скачивальщики оформление обычно не грузят. Адреса Google, хостингов и наших серверов отбрасываются.
Страна — по открытому реестру адресов (whois), ответы запоминаются в logs/whois_cache.json.
Журнал nginx читается, только если пользователь goads в группе adm.
"""
import gzip
import json
import os
import re
import subprocess
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from django.conf import settings

LOGS = [Path("/var/log/nginx/access.log.1"), Path("/var/log/nginx/access.log")]
CACHE = Path(settings.BASE_DIR) / "logs" / "whois_cache.json"
MARKER = "GET /static/vendor/css/rent.css"
BOT_WORDS = re.compile(r"bot|crawl|spider|slurp|preview|python|curl|wget|headless", re.I)
# Не люди: поисковики, хостинги, облака
NOT_PEOPLE = re.compile(r"google|ovh|amazon|aws|microsoft|azure|hetzner|digitalocean|linode|akamai|"
                        r"cloudflare|contabo|hosteons|oracle|alibaba|tencent|yandex|leaseweb|m247|datacamp",
                        re.I)
# Наши серверы и VPN: в .env VISITS_IGNORE_IPS="1.2.3.4 5.6.7.8"
OWN = {"127.0.0.1", *os.environ.get("VISITS_IGNORE_IPS", "").split()}
LINE = re.compile(r'^(\S+) \S+ \S+ \[([^\]]+)\] "([^"]*)" \d+ \S+ "[^"]*" "([^"]*)"')

COUNTRIES = {
    "RU": "🇷🇺 Россия", "BY": "🇧🇾 Беларусь", "UA": "🇺🇦 Украина", "IN": "🇮🇳 Индия", "AM": "🇦🇲 Армения",
    "GE": "🇬🇪 Грузия", "TH": "🇹🇭 Таиланд", "KZ": "🇰🇿 Казахстан", "TR": "🇹🇷 Турция", "DE": "🇩🇪 Германия",
    "RS": "🇷🇸 Сербия", "ID": "🇮🇩 Индонезия", "VN": "🇻🇳 Вьетнам", "AE": "🇦🇪 ОАЭ", "US": "🇺🇸 США",
}


def _lines():
    for path in LOGS:
        try:
            opener = gzip.open if path.suffix == ".gz" else open
            with opener(path, "rt", encoding="utf-8", errors="replace") as f:
                yield from f
        except OSError:
            continue


def _whois(ip: str) -> dict:
    """{"country": "BY", "org": "..."} из реестра адресов."""
    try:
        out = subprocess.run(["whois", ip], capture_output=True, text=True, timeout=15).stdout
    except (OSError, subprocess.TimeoutExpired):
        return {"country": "", "org": ""}
    country = re.search(r"^country:\s*([A-Za-z]{2})", out, re.I | re.M)
    org = re.findall(r"^(?:netname|org-name|orgname|descr|owner):\s*(.+)$", out, re.I | re.M)
    return {"country": country.group(1).upper() if country else "", "org": "; ".join(org[:4])}


def visitors(hours: int = 24) -> dict | None:
    """{"people": 5, "countries": Counter({"BY": 3, ...}), "pages": 40}; None — журнал не читается."""
    if not any(p.exists() for p in LOGS):
        return None
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    ips, pages = set(), Counter()
    readable = False
    for line in _lines():
        readable = True
        m = LINE.match(line)
        if not m:
            continue
        ip, when, request, agent = m.groups()
        try:
            if datetime.strptime(when, "%d/%b/%Y:%H:%M:%S %z") < since:
                continue
        except ValueError:
            continue
        if ip in OWN or BOT_WORDS.search(agent):
            continue
        if request.startswith(MARKER):
            ips.add(ip)
        elif request.startswith("GET /") and not request.startswith(("GET /static", "GET /media", "GET /tg/")):
            pages[ip] += 1
    if not readable:
        return None

    try:
        cache = json.loads(CACHE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cache = {}
    countries, people, seen = Counter(), 0, 0
    for ip in ips:
        if ip not in cache:
            cache[ip] = _whois(ip)
        info = cache[ip]
        if NOT_PEOPLE.search(info.get("org", "")):
            continue
        people += 1
        seen += pages[ip]
        countries[info.get("country") or "?"] += 1
    try:
        CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
    return {"people": people, "countries": countries, "pages": seen}


def report_lines() -> list[str]:
    v = visitors()
    if v is None:
        return ["", "<b>Посетители</b>", "Журнал сайта недоступен"]
    lines = ["", "<b>Посетители за сутки</b>", f"Людей: {v['people']}, страниц открыто: {v['pages']}"]
    for code, n in v["countries"].most_common():
        lines.append(f"{COUNTRIES.get(code, code if code != '?' else 'страна неизвестна')}: {n}")
    return lines
