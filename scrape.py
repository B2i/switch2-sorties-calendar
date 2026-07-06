#!/usr/bin/env python3
"""
Scrape les sorties de jeux Nintendo Switch / Switch 2 depuis plusieurs sources
et génère un fichier .ics à jour.

Sources :
- alertetgo.com (précommandes Switch 2 et Switch)
- chocobonplan.com (précommandes Switch 2, plusieurs pages)

NOTE : ce scraper repose sur des heuristiques (regex sur le texte visible des
pages) plutôt que sur des sélecteurs CSS figés, car la structure HTML exacte
de ces sites n'a pas pu être testée en amont. Il peut avoir besoin d'un
ajustement si un site change son gabarit. Chaque source est protégée par un
try/except : si une source échoue, les autres continuent de fonctionner et
l'événement existant du fichier ICS est conservé (le script fusionne avec
l'existant, il ne repart jamais de zéro).
"""

import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ICS_PATH = Path(__file__).parent / "sorties_switch2.ics"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
}

SOURCES = [
    "https://alertetgo.com/category/precommandes-et-bons-plans/nintendo-switch-2/",
    "https://alertetgo.com/category/precommandes-et-bons-plans/nintendo-switch/",
]

# chocobonplan est paginé ; on couvre les 4 premières pages (largement suffisant
# pour un horizon de quelques mois, à ajuster si besoin)
CHOCOBONPLAN_PAGES = [
    "https://chocobonplan.com/bons-plans/c/precommandes-jeux-switch-2/?orderby=datefin",
    "https://chocobonplan.com/bons-plans/c/precommandes-jeux-switch-2/page/2/?orderby=datefin",
    "https://chocobonplan.com/bons-plans/c/precommandes-jeux-switch-2/page/3/?orderby=datefin",
    "https://chocobonplan.com/bons-plans/c/precommandes-jeux-switch-2/page/4/?orderby=datefin",
]

MONTHS_FR = {
    "janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5,
    "juin": 6, "juillet": 7, "août": 8, "aout": 8, "septembre": 9,
    "octobre": 10, "novembre": 11, "décembre": 12, "decembre": 12,
}

DATE_PATTERNS = [
    # 16/07/2026 ou 16/07/26
    re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b"),
    # 16 juillet 2026
    re.compile(
        r"\b(\d{1,2})\s+(" + "|".join(MONTHS_FR.keys()) + r")\s+(\d{4})\b",
        re.IGNORECASE,
    ),
]


def strip_accents(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn"
    )


def parse_date_from_text(text: str):
    """Essaie d'extraire une date JJ/MM/AAAA depuis un texte libre."""
    for pattern in DATE_PATTERNS:
        m = pattern.search(text)
        if not m:
            continue
        groups = m.groups()
        if groups[1].isdigit():
            day, month, year = int(groups[0]), int(groups[1]), int(groups[2])
        else:
            day = int(groups[0])
            month = MONTHS_FR[strip_accents(groups[1].lower())]
            year = int(groups[2])
        if year < 100:
            year += 2000
        try:
            return datetime(year, month, day)
        except ValueError:
            continue
    return None


def clean_title(title: str) -> str:
    title = re.sub(r"\s+", " ", title).strip()
    # enlève les mentions de prix/promo qui traînent parfois dans les titres
    title = re.sub(r"\s*[-–]\s*\d+[,.]\d+\s*€.*$", "", title)
    return title.strip(" -–:")


def scrape_alertetgo(url):
    """
    Structure attendue (best-effort) : des blocs 'article' ou 'div.card'
    contenant un titre de jeu et une date de sortie (souvent au format
    JJ/MM/AAAA à proximité du titre).
    """
    events = []
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
    except Exception as e:
        print(f"[alertetgo] Erreur de récupération de {url} : {e}", file=sys.stderr)
        return events

    soup = BeautifulSoup(resp.text, "html.parser")

    # Heuristique : chercher les conteneurs d'articles/cartes les plus probables
    candidates = soup.select("article, .card, .post, li")
    seen_blocks = set()
    for block in candidates:
        text = block.get_text(" ", strip=True)
        if not text or len(text) > 400:
            continue
        date = parse_date_from_text(text)
        if not date:
            continue
        # Le titre est généralement dans un lien ou un heading du bloc
        title_el = block.find(["h1", "h2", "h3", "h4", "a"])
        title = clean_title(title_el.get_text(" ", strip=True)) if title_el else None
        if not title or len(title) < 2 or len(title) > 120:
            continue
        key = (title.lower(), date.date())
        if key in seen_blocks:
            continue
        seen_blocks.add(key)
        platform = "Switch 2" if "switch-2" in url else "Switch"
        events.append({"title": title, "date": date, "platform": platform})

    print(f"[alertetgo] {len(events)} sorties détectées sur {url}")
    return events


def scrape_chocobonplan(url):
    events = []
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
    except Exception as e:
        print(f"[chocobonplan] Erreur de récupération de {url} : {e}", file=sys.stderr)
        return events

    soup = BeautifulSoup(resp.text, "html.parser")
    candidates = soup.select("article, .card, .post, li")
    seen_blocks = set()
    for block in candidates:
        text = block.get_text(" ", strip=True)
        if not text or len(text) > 400:
            continue
        date = parse_date_from_text(text)
        if not date:
            continue
        title_el = block.find(["h1", "h2", "h3", "h4", "a"])
        title = clean_title(title_el.get_text(" ", strip=True)) if title_el else None
        if not title or len(title) < 2 or len(title) > 120:
            continue
        key = (title.lower(), date.date())
        if key in seen_blocks:
            continue
        seen_blocks.add(key)
        events.append({"title": title, "date": date, "platform": "Switch 2"})

    print(f"[chocobonplan] {len(events)} sorties détectées sur {url}")
    return events


def load_existing_events():
    """Relit le fichier ICS existant (s'il existe) pour ne jamais perdre de données."""
    events = {}
    if not ICS_PATH.exists():
        return events

    text = ICS_PATH.read_text(encoding="utf-8")
    blocks = text.split("BEGIN:VEVENT")[1:]
    for block in blocks:
        uid_m = re.search(r"UID:(.+)", block)
        date_m = re.search(r"DTSTART;VALUE=DATE:(\d{8})", block)
        summary_m = re.search(r"SUMMARY:(.+)", block)
        desc_m = re.search(r"DESCRIPTION:(.+)", block)
        if not (uid_m and date_m and summary_m):
            continue
        uid = uid_m.group(1).strip()
        date = datetime.strptime(date_m.group(1), "%Y%m%d")
        summary = summary_m.group(1).strip()
        description = desc_m.group(1).strip() if desc_m else ""
        events[uid] = {"date": date, "summary": summary, "description": description}
    return events


def make_uid(title: str, date: datetime) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]", "", title)
    return f"{slug}@{date.strftime('%Y-%m-%d')}"


def merge_events(existing, scraped):
    """Fusionne les nouvelles sorties scrapées avec celles déjà connues.
    N'écrase jamais un événement existant (qui peut avoir été enrichi/corrigé
    manuellement) ; ajoute uniquement les nouveautés."""
    merged = dict(existing)
    added = 0
    for item in scraped:
        uid = make_uid(item["title"], item["date"])
        if uid in merged:
            continue
        merged[uid] = {
            "date": item["date"],
            "summary": f"🎮 {item['title']}",
            "description": f"Sortie de {item['title']} sur {item['platform']} (détecté automatiquement)",
        }
        added += 1
    print(f"{added} nouvelle(s) sortie(s) ajoutée(s) par le scraper")
    return merged


def write_ics(events: dict):
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Mehdi Falou//Sorties Jeux Switch 2//FR",
        "",
    ]
    for uid, ev in sorted(events.items(), key=lambda kv: kv[1]["date"]):
        date_str = ev["date"].strftime("%Y%m%d")
        lines.append("BEGIN:VEVENT")
        lines.append(f"UID:{uid}")
        lines.append(f"DTSTART;VALUE=DATE:{date_str}")
        lines.append(f"DTEND;VALUE=DATE:{date_str}")
        lines.append(f"SUMMARY:{ev['summary']}")
        lines.append(f"DESCRIPTION:{ev['description']}")
        lines.append("END:VEVENT")
        lines.append("")
    lines.append("END:VCALENDAR")

    content = "\r\n".join(lines) + "\r\n"
    ICS_PATH.write_text(content, encoding="utf-8", newline="")
    print(f"Fichier écrit : {ICS_PATH} ({len(events)} événements)")


def main():
    existing = load_existing_events()
    print(f"{len(existing)} événement(s) déjà présents dans le fichier")

    scraped = []
    for url in SOURCES:
        scraped.extend(scrape_alertetgo(url))
    for url in CHOCOBONPLAN_PAGES:
        scraped.extend(scrape_chocobonplan(url))

    merged = merge_events(existing, scraped)
    write_ics(merged)


if __name__ == "__main__":
    main()
