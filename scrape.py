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
from playwright.sync_api import sync_playwright

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

# Page officielle Nintendo "Bientôt disponibles" (filtre f=147394-14-73), paginée.
# Cette page charge son contenu en JavaScript : on utilise Playwright pour
# la rendre comme un vrai navigateur avant de l'analyser.
NINTENDO_BASE_URL = "https://www.nintendo.com/fr-fr/Rechercher/Rechercher-299117.html?f=147394-14-73"
NINTENDO_MAX_PAGES = 6  # s'arrête plus tôt si une page ne contient plus de résultats

SWITCH_ACTU_URL = "https://www.switch-actu.fr/calendrier-sorties/"

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


def scrape_nintendo_fr():
    """
    Scrape la page officielle Nintendo "Bientôt disponibles" (fr-fr).
    Cette page est une SPA : le contenu réel n'existe qu'après exécution du
    JavaScript, d'où l'usage de Playwright (navigateur headless) plutôt que
    de simples requêtes HTTP.
    """
    events = []
    seen = set()

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(user_agent=HEADERS["User-Agent"])

        for page_num in range(1, NINTENDO_MAX_PAGES + 1):
            url = NINTENDO_BASE_URL if page_num == 1 else f"{NINTENDO_BASE_URL}&p={page_num}"
            try:
                page.goto(url, wait_until="networkidle", timeout=30000)
                # laisse le temps au JS de remplir les gabarits {{pageTitle}}, etc.
                page.wait_for_timeout(2000)
            except Exception as e:
                print(f"[nintendo.com] Erreur de chargement de {url} : {e}", file=sys.stderr)
                break

            html = page.content()
            soup = BeautifulSoup(html, "html.parser")

            # Heuristique : les gabarits {{pageTitle}} / {{gameReleaseDate}} du
            # HTML brut sont remplacés, une fois rendus, par le vrai titre et
            # une date de la forme "Date de publication : JJ/MM/AAAA"
            page_events_found = 0
            for block in soup.select("li, article, div"):
                text = block.get_text(" ", strip=True)
                if "Date de publication" not in text or len(text) > 300:
                    continue
                date = parse_date_from_text(text)
                if not date:
                    continue
                title_el = block.find(["h1", "h2", "h3", "h4"])
                if not title_el:
                    continue
                title = clean_title(title_el.get_text(" ", strip=True))
                if not title or len(title) < 2 or len(title) > 120:
                    continue
                key = (title.lower(), date.date())
                if key in seen:
                    continue
                seen.add(key)
                events.append({"title": title, "date": date, "platform": "Switch / Switch 2"})
                page_events_found += 1

            print(f"[nintendo.com] page {page_num} : {page_events_found} sortie(s) détectée(s)")

            # Si une page ne remonte plus aucun résultat, on arrête la pagination
            if page_events_found == 0:
                break

        browser.close()

    print(f"[nintendo.com] {len(events)} sortie(s) au total")
    return events


def scrape_switch_actu():
    """
    Scrape la page 'Agenda des sorties' de switch-actu.fr. Contrairement à
    nintendo.com, cette page est un WordPress classique rendu côté serveur
    (pas de JavaScript à exécuter), donc un simple requests + BeautifulSoup
    suffit.

    Structure observée pour chaque jeu : un lien vers
    /calendrier-sorties/jeux/<slug>/ dont le texte contient le titre (en
    double), le(s) genre(s), la/les plateforme(s), et se termine par
    "Date de sortie : 9 juillet 2026" (ou juste une année, ou "Inconnue"
    pour les jeux sans date connue — ceux-ci sont ignorés).
    """
    events = []
    try:
        resp = requests.get(SWITCH_ACTU_URL, headers=HEADERS, timeout=20)
        resp.raise_for_status()
    except Exception as e:
        print(f"[switch-actu] Erreur de récupération : {e}", file=sys.stderr)
        return events

    soup = BeautifulSoup(resp.text, "html.parser")
    links = soup.select('a[href*="/calendrier-sorties/jeux/"]')

    seen = set()
    for link in links:
        text = link.get_text(" ", strip=True)
        if "Date de sortie" not in text:
            continue

        date_part = text.split("Date de sortie", 1)[1].lstrip(" :")
        date = parse_date_from_text(date_part)
        if not date:
            # Année seule, ou "Inconnue" : pas assez précis pour un
            # événement de calendrier, on ignore.
            continue

        leading = text.split("Genre", 1)[0].strip()
        n = len(leading)
        half = n // 2
        if n % 2 == 0 and leading[:half].strip() == leading[half:].strip():
            title = leading[:half].strip()
        else:
            title = leading.strip()
        title = clean_title(title)
        if not title or len(title) < 2 or len(title) > 120:
            continue

        # Plateforme (best-effort, à partir du texte visible)
        if "Switch 2" in text and "Switch" in text.replace("Switch 2", ""):
            platform = "Switch, Switch 2"
        elif "Switch 2" in text:
            platform = "Switch 2"
        else:
            platform = "Switch"

        key = (title.lower(), date.date())
        if key in seen:
            continue
        seen.add(key)
        events.append({"title": title, "date": date, "platform": platform})

    print(f"[switch-actu] {len(events)} sortie(s) détectée(s)")
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
    manuellement) ; ajoute uniquement les nouveautés.
    Retourne (dict fusionné, liste des nouveautés ajoutées)."""
    merged = dict(existing)
    newly_added = []
    for item in scraped:
        uid = make_uid(item["title"], item["date"])
        if uid in merged:
            continue
        merged[uid] = {
            "date": item["date"],
            "summary": f"🎮 {item['title']}",
            "description": f"Sortie de {item['title']} sur {item['platform']} (détecté automatiquement)",
        }
        newly_added.append(item)
    print(f"{len(newly_added)} nouvelle(s) sortie(s) ajoutée(s) par le scraper")
    return merged, newly_added


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


def write_new_events_file(newly_added):
    """Écrit un fichier texte listant les nouveautés, lu ensuite par le
    workflow GitHub Actions pour construire la notification ntfy.sh.
    Le fichier est vide (ou absent) s'il n'y a rien de nouveau."""
    path = Path(__file__).parent / "new_events.txt"
    if not newly_added:
        if path.exists():
            path.unlink()
        return
    lines = []
    for item in sorted(newly_added, key=lambda i: i["date"]):
        lines.append(f"{item['date'].strftime('%d/%m/%Y')} — {item['title']} ({item['platform']})")
    path.write_text("\n".join(lines), encoding="utf-8")


def main():
    existing = load_existing_events()
    print(f"{len(existing)} événement(s) déjà présents dans le fichier")

    scraped = []
    for url in SOURCES:
        scraped.extend(scrape_alertetgo(url))
    for url in CHOCOBONPLAN_PAGES:
        scraped.extend(scrape_chocobonplan(url))
    scraped.extend(scrape_nintendo_fr())
    scraped.extend(scrape_switch_actu())

    merged, newly_added = merge_events(existing, scraped)
    write_ics(merged)
    write_new_events_file(newly_added)


if __name__ == "__main__":
    main()
