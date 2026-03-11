"""
scraper.py  —  pure requests, no Playwright.

Fetches competition list and per-competition metadata:
  - loglig_id, loglig_base_url
  - race list with per-race date (from schedule start_time column)
  - all dates available in the competition (for multi-day)
"""
import re, logging
import requests
from dataclasses import dataclass, field
from typing import Optional
from bs4 import BeautifulSoup
from config import BASE_URL, COMPETITIONS_URL, HEADERS

log = logging.getLogger(__name__)

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


@dataclass
class RaceMeta:
    loglig_event_id: str
    event_num:       int
    race_date:       str   # "DD/MM/YYYY" extracted from start_time
    distance:        int
    stroke:          str
    category:        str
    gender:          str
    is_relay:        bool
    start_time:      str   # full "DD/MM/YYYY HH:MM:SS"


@dataclass
class CompetitionMeta:
    isr_id:          str
    loglig_id:       Optional[str]
    name:            str
    sport_type:      str
    loglig_base_url: Optional[str] = None
    races:           list[RaceMeta] = field(default_factory=list)
    dates:           list[str]      = field(default_factory=list)  # ["DD/MM/YYYY", ...]
    date_range:      str            = ""   # "DD/MM/YYYY" or "DD/MM/YYYY-DD/MM/YYYY"
    # day_pdf_urls: per-date PDF URL from tr.disciplines-title th a[title="תוצאות"]
    # For single-day competitions: {"": url}
    # For multi-day: {"DD/MM/YYYY": url, ...}
    day_pdf_urls:    dict[str, str] = field(default_factory=dict)


STROKE_MAP = {
    "חופשי":      "FREE",
    "גב":         "BACK",
    "חזה":        "BREAST",
    "פרפר":       "FLY",
    "מעורב אישי": "IM",
    "מעורב":      "MEDLEY",
}


def scrape_all_competitions() -> list[CompetitionMeta]:
    log.info("Fetching ISR competition list...")
    try:
        r = SESSION.get(COMPETITIONS_URL, timeout=20)
        r.raise_for_status()
    except Exception as e:
        log.error(f"Failed to load ISR competition list: {e}")
        return []

    soup  = BeautifulSoup(r.text, "lxml")
    comps = _parse_competition_list(soup)
    log.info(f"Found {len(comps)} competitions on list page")

    resolved = []
    for comp in comps:
        iframe_url = _get_loglig_iframe_url(comp.detail_url)
        if not iframe_url:
            log.info(f"  SKIP (no loglig iframe): {comp.name}")
            continue

        m = re.match(
            r"(https?://loglig\.com(?::\d+)?)/LeagueTable/AthleticsDisciplines/(\d+)",
            iframe_url,
        )
        if not m:
            continue

        base = m.group(1)
        if ":8090" in base:
            # Old competitions were published with port 8090, but the data is
            # also available on port 2053.  Rewrite silently.
            base = base.replace(":8090", ":2053")
            log.info(f"  PORT-REWRITE (8090→2053): {comp.name}")

        comp.loglig_base_url = base
        comp.loglig_id       = m.group(2)

        # Fetch race list + dates from loglig
        _enrich_competition(comp)

        resolved.append(comp)
        log.info(f"  OK  {comp.name}  loglig={comp.loglig_id}  dates={comp.dates}  races={len(comp.races)}")

    log.info(f"Resolved {len(resolved)} competitions")
    return resolved


def _enrich_competition(comp: CompetitionMeta) -> None:
    """Fetch the loglig disciplines page and extract race list + available dates + day PDF URLs."""
    url = f"{comp.loglig_base_url}/LeagueTable/AthleticsDisciplines/{comp.loglig_id}"
    try:
        r = SESSION.get(url, timeout=15)
        r.raise_for_status()
    except Exception as e:
        log.warning(f"  Failed to fetch loglig page for {comp.name}: {e}")
        return

    soup = BeautifulSoup(r.text, "lxml")

    # Extract available dates from <select id="DateSelectionFilter">
    date_sel = soup.find("select", id="DateSelectionFilter")
    if date_sel:
        comp.dates = [
            o["value"] for o in date_sel.find_all("option")
            if re.match(r"\d{2}/\d{2}/\d{4}", o.get("value", ""))
        ]

    # Build date_range
    if len(comp.dates) == 1:
        comp.date_range = comp.dates[0]
    elif len(comp.dates) > 1:
        comp.date_range = f"{comp.dates[0]}-{comp.dates[-1]}"

    # Extract day PDF URL from tr.disciplines-title th a[title="תוצאות"]
    # For multi-day competitions we need to fetch each day's filtered page separately —
    # but the base URL on the main page is the same for all days (no date param in href).
    # Store it keyed by "" for single-day; parser will handle per-day navigation.
    res_a = soup.select_one("tr.disciplines-title th a[title='תוצאות']")
    if res_a and res_a.get("href"):
        href = res_a["href"]
        if not href.startswith("http"):
            href = "https://loglig.com" + href
        comp.day_pdf_urls[""] = href

    # Parse race list
    comp.races = _parse_race_list(soup)


def _parse_race_list(soup: BeautifulSoup) -> list[RaceMeta]:
    races = []
    for row in soup.select("table.res-table tbody tr"):
        cells = [td.get_text(strip=True) for td in row.find_all("td")]
        if not cells or not cells[0].isdigit():
            continue
        # Only races that have a results link (completed races)
        link = row.find("a", href=re.compile(r"/AthleticsDisciplineResults/\d+"))
        if not link:
            continue
        # Exclude ByHeat links
        if "ByHeat" in link.get("href", ""):
            continue

        event_id   = re.search(r"/AthleticsDisciplineResults/(\d+)", link["href"]).group(1)
        raw_name   = cells[1] if len(cells) > 1 else ""
        category   = cells[2] if len(cells) > 2 else ""
        start_time = cells[4] if len(cells) > 4 else ""
        race_date  = _extract_date(start_time)
        distance, stroke, is_relay = _parse_race_name(raw_name)

        races.append(RaceMeta(
            loglig_event_id=event_id,
            event_num=int(cells[0]),
            race_date=race_date,
            distance=distance,
            stroke=stroke,
            category=category,
            gender=_parse_gender(category),
            is_relay=is_relay,
            start_time=start_time,
        ))
    return races


def _extract_date(start_time: str) -> str:
    """Extract DD/MM/YYYY from a datetime string like '09/01/2026 09:00:00'."""
    m = re.search(r"(\d{2}/\d{2}/\d{4})", start_time)
    return m.group(1) if m else ""


def _parse_race_name(raw: str) -> tuple[int, str, bool]:
    raw = raw.strip()
    is_relay = "שליחים" in raw or "מסירות" in raw
    relay_m  = re.match(r"4[Xx](\d+)", raw)
    distance = int(relay_m.group(1)) if relay_m else (
        int(m.group(1)) if (m := re.match(r"(\d+)", raw)) else 0
    )
    stroke = next((c for h, c in STROKE_MAP.items() if h in raw), "UNKNOWN")
    return distance, stroke, is_relay


def _parse_gender(cat: str) -> str:
    if "מיקס" in cat or ("מעורב" in cat and "אישי" not in cat):
        return "MIX"
    if " נ " in cat or cat.endswith(" נ") or "נשים" in cat:
        return "F"
    if " ג " in cat or cat.endswith(" ג") or "גברים" in cat:
        return "M"
    return "?"


def _parse_competition_list(soup: BeautifulSoup):
    """Returns list of partial CompetitionMeta with detail_url attached."""
    comps = []
    for row in soup.select("tr.row"):
        name_td  = row.select_one("td.c-name a")
        icon_img = row.select_one("td.c-icon img")
        if not name_td:
            continue
        href  = name_td["href"]
        match = re.search(r"compID=(\d+)", href)
        if not match:
            continue
        obj = CompetitionMeta(
            isr_id     = match.group(1),
            loglig_id  = None,
            name       = name_td.get_text(strip=True),
            sport_type = icon_img["alt"] if icon_img and icon_img.get("alt") else "",
        )
        # Stash detail_url temporarily
        obj.__dict__["detail_url"] = _abs(href)
        comps.append(obj)
    return comps


def _get_loglig_iframe_url(comp_url: str) -> Optional[str]:
    try:
        r = SESSION.get(comp_url, timeout=15)
        r.raise_for_status()
        soup   = BeautifulSoup(r.text, "lxml")
        iframe = soup.find("iframe", src=re.compile(r"loglig\.com", re.I))
        return iframe["src"] if iframe else None
    except Exception as e:
        log.warning(f"  Failed to fetch {comp_url}: {e}")
        return None


def _abs(href: str) -> str:
    return href if href.startswith("http") else f"{BASE_URL}/{href.lstrip('/')}"