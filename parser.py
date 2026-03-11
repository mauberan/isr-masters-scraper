"""
parser.py — Playwright session (for splits PDF via fetch) + requests (for HTML)

Per race:
  1. requests.get HTML results page  → place, name, club, heat, lane, time, pts, loglig_id, race_date
  2. page.evaluate fetch POST        → splits PDF bytes → PDF.js text extraction
  3. Parse PDF rows → match by result_time → reaction_time + cumulative splits

Splits PDF row structure (3 logical rows per swimmer):
  Row A  (result info):  place/heat/lane/name/club/time/reaction/pts  — layout inconsistent, IGNORED
  Row B  (cumulative):   final_time | ... | 50m_cumul   (texts[0] = final time = match key)
                         len == n_splits  (n_splits from column header row)
  Row C  (lap times):    lap_n | ... | lap_2            (len == n_splits - 1)

n_splits detected from header row where tokens end with "מ'" (e.g. "'50 מ", "'100 מ" ...)
Date extracted from HTML heading: "Competition Name - DD/MM/YYYY"
"""

import re, logging, hashlib
import requests
from bs4 import BeautifulSoup
from typing import Optional
from playwright.sync_api import Page

from models import (
    IdRegistry, Club, Swimmer, Competition, Race,
    IndividualScore, RelayScore, CompetitionDocument,
)
from scraper import CompetitionMeta
from config import HEADERS

log = logging.getLogger(__name__)
LOGLIG_FALLBACK = "https://loglig.com:2053"
_SESSION = requests.Session()
_SESSION.headers.update(HEADERS)

_TIME_RE  = re.compile(r"^\d{1,2}:\d{2}\.\d{2}$")
_REACT_RE = re.compile(r"^\+\s*\d+\.\d+$")
_DATE_RE  = re.compile(r"\b(\d{2}/\d{2}/\d{4})\b")

# ─────────────────────────────────────────────────────────────────
# Playwright page factory
# ─────────────────────────────────────────────────────────────────

def _get_page(playwright):
    browser = playwright.chromium.launch(headless=True)
    ctx = browser.new_context(
        extra_http_headers=HEADERS,
        viewport={"width": 1280, "height": 900},
    )
    return ctx.new_page()


def _ensure_pdfjs(page: Page) -> None:
    """Inject PDF.js into the current page if not already present.
    Must be called after every page.goto() since navigation clears injected scripts.
    Checks window.pdfjsLib to avoid double-injection on the same page load.
    """
    page.evaluate("""() => {
        if (window.pdfjsLib) return Promise.resolve();
        return new Promise((resolve, reject) => {
            const s = document.createElement('script');
            s.src = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js';
            s.onload = () => {
                pdfjsLib.GlobalWorkerOptions.workerSrc =
                    'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';
                resolve();
            };
            s.onerror = reject;
            document.head.appendChild(s);
        });
    }""")


# ─────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────

def parse_competition(comp_meta: CompetitionMeta, registry: IdRegistry, page: Page) -> CompetitionDocument:
    competition = Competition(
        id         = registry.next("competition"),
        isr_id     = comp_meta.isr_id,
        loglig_id  = comp_meta.loglig_id or "",
        name       = comp_meta.name,
        date_range = comp_meta.date_range,
        sport_type = comp_meta.sport_type,
    )
    doc            = CompetitionDocument(competition=competition)
    clubs_seen:    dict[str, Club]    = {}
    swimmers_seen: dict[str, Swimmer] = {}
    base = comp_meta.loglig_base_url or LOGLIG_FALLBACK

    # Load disciplines page — establishes browser session for PDF fetches
    disciplines_url = f"{base}/LeagueTable/AthleticsDisciplines/{comp_meta.loglig_id}"
    log.info(f"  Loading session: {disciplines_url}")
    page.goto(disciplines_url, wait_until="domcontentloaded", timeout=30000)
    try:
        page.wait_for_selector("table.res-table", timeout=10000)
    except Exception:
        log.warning(f"  No results table for {comp_meta.name}")
        doc.clubs = []; doc.swimmers = []
        return doc

    _ensure_pdfjs(page)

    for race_meta in comp_meta.races:
        race = Race(
            id              = registry.next("race"),
            competition_id  = competition.id,
            loglig_event_id = race_meta.loglig_event_id,
            event_num       = race_meta.event_num,
            race_date       = race_meta.race_date,
            distance        = race_meta.distance,
            stroke          = race_meta.stroke,
            category        = race_meta.category,
            gender          = race_meta.gender,
            is_relay        = race_meta.is_relay,
            start_time      = race_meta.start_time,
        )
        doc.races.append(race)

        # ── Step 1: HTML results page (via requests) ──────────────
        html_url = f"{base}/LeagueTable/AthleticsDisciplineResults/{race_meta.loglig_event_id}"
        try:
            resp = _SESSION.get(html_url, timeout=15)
            resp.raise_for_status()
        except Exception as e:
            log.warning(f"    Race {race_meta.event_num}: HTML fetch error — {e}")
            continue

        soup = BeautifulSoup(resp.text, "lxml")

        # Extract race date from page heading (e.g. "Competition - 09/01/2026")
        race_date = _extract_date_from_soup(soup) or race_meta.race_date

        html_rows = _parse_html_table(soup)
        if not html_rows:
            log.warning(f"    Race {race_meta.event_num}: 0 HTML rows")
            continue

        # ── Step 2: Splits PDF via browser session ────────────────
        splits_map = _fetch_and_parse_splits(
            page, base, comp_meta.loglig_id, race_meta.loglig_event_id
        )

        log.info(
            f"    Race {race_meta.event_num}: {race_meta.distance}m {race_meta.stroke} "
            f"{race_meta.gender} {'RELAY' if race_meta.is_relay else ''} — "
            f"{len(html_rows)} results, {len(splits_map)} with splits"
        )

        # ── Step 3: Build score objects ───────────────────────────
        ind, rel = _build_scores(
            html_rows, splits_map, race, race_date,
            clubs_seen, swimmers_seen, registry,
        )
        doc.individual_scores.extend(ind)
        doc.relay_scores.extend(rel)

    doc.clubs    = list(clubs_seen.values())
    doc.swimmers = list(swimmers_seen.values())
    return doc


# ─────────────────────────────────────────────────────────────────
# Date extraction from HTML
# ─────────────────────────────────────────────────────────────────

def _extract_date_from_soup(soup: BeautifulSoup) -> Optional[str]:
    """Extract DD/MM/YYYY from page headings (e.g. 'Competition Name - 09/01/2026')."""
    for tag in soup.find_all(["h1", "h2", "h3", "h4"]):
        m = _DATE_RE.search(tag.get_text())
        if m:
            return m.group(1)
    # Fallback: any element with a date pattern
    for tag in soup.find_all(string=_DATE_RE):
        m = _DATE_RE.search(tag)
        if m:
            return m.group(1)
    return None


# ─────────────────────────────────────────────────────────────────
# Splits PDF: fetch via browser session + parse via PDF.js
# ─────────────────────────────────────────────────────────────────

def _fetch_and_parse_splits(page: Page, base: str, loglig_id: str, discipline_id: str) -> dict:
    """
    Returns {result_time: {'reaction': str|None, 'cumul_splits': [str], 'lap_splits': [str]}}
    Keyed by the swimmer's final result_time (= texts[0] of Row B in PDF).
    """
    js = f"""
    async () => {{
        // Fetch splits PDF using active session cookies
        const fd = new FormData();
        fd.append('DisciplineCompetitionId', '{discipline_id}');
        const resp = await fetch(
            '{base}/LeagueTable/ExportSwimmingDisciplineResults'
            + '?leagueId={loglig_id}&IsSplitResults=True',
            {{ method: 'POST', body: fd }}
        );
        if (!resp.ok) return {{ error: 'HTTP ' + resp.status }};
        const buf = await resp.arrayBuffer();
        if (String.fromCharCode(...new Uint8Array(buf, 0, 4)) !== '%PDF')
            return {{ error: 'not a PDF' }};

        // Parse with PDF.js, group items by Y coordinate
        const pdfDoc = await pdfjsLib.getDocument({{ data: buf }}).promise;
        const allRows = [];
        for (let p = 1; p <= pdfDoc.numPages; p++) {{
            const pg = await pdfDoc.getPage(p);
            const content = await pg.getTextContent();
            const byY = {{}};
            for (const item of content.items) {{
                const key = Math.round(item.transform[5] / 3) * 3;
                if (!byY[key]) byY[key] = [];
                byY[key].push({{ text: item.str.trim(), x: item.transform[4] }});
            }}
            for (const [y, items] of Object.entries(byY).sort((a,b) => b[0]-a[0])) {{
                const texts = items.sort((a,b) => a.x-b.x).map(i => i.text).filter(t => t);
                if (texts.length) allRows.push({{ y: parseInt(y), texts }});
            }}
        }}
        return {{ rows: allRows }};
    }}
    """
    try:
        result = page.evaluate(js)
    except Exception as e:
        log.warning(f"    PDF.js error for {discipline_id}: {e}")
        return {}

    if not result or result.get("error"):
        log.warning(f"    Splits fetch failed for {discipline_id}: {result}")
        return {}

    return _parse_splits_rows(result["rows"])


def _parse_splits_rows(rows: list) -> dict:
    """
    Parse PDF.js rows into splits map keyed by result_time (final cumulative time).

    Row B (cumulative splits): all tokens match time pattern, len == n_splits
      texts[0] = final time (highest value, used as match key)
      texts[-1] = first 50m split
    Row C (lap times): all tokens match time pattern OR are negative-lap artifacts,
      len == n_splits - 1  (one fewer than Row B)

    n_splits = number of split-distance columns in header row
    (header row contains tokens ending with "מ'" like "'50 מ", "'100 מ")
    """
    # Detect n_splits from the distance header row.
    # Header tokens match pattern: "'NNN מ" — starts with apostrophe, ends with " מ"
    _split_header_re = re.compile(r"^'\d+\s+מ$")
    n_splits = 0
    for row in rows:
        matching = [t for t in row["texts"] if _split_header_re.match(t)]
        if len(matching) >= 2 and len(matching) == len(row["texts"]):
            n_splits = len(matching)
            log.debug(f"    n_splits={n_splits} from header: {row['texts']}")
            break

    if not n_splits:
        log.debug("    n_splits not found — skipping splits parse")
        return {}

    splits_map = {}
    i = 0

    while i < len(rows):
        row = rows[i]
        texts = row["texts"]

        # Identify Row B: all tokens are valid times AND len == n_splits
        if len(texts) == n_splits and all(_TIME_RE.match(t) for t in texts):
            final_time = texts[0]   # first token = highest cumulative = final time
            cumul = list(reversed(texts))  # reverse to ascending order: 50m, 100m, ..., final

            # Row C is the next row: len == n_splits - 1, all time-like tokens
            laps = []
            row_c_found = False
            if i + 1 < len(rows):
                next_texts = rows[i + 1]["texts"]
                if len(next_texts) == n_splits - 1 and all(_TIME_RE.match(t) for t in next_texts):
                    laps = list(reversed(next_texts))
                    row_c_found = True

            # Reaction time: scan backwards from Row B for a "+ 0.xx" token
            reaction = None
            for j in range(i - 1, max(-1, i - 4), -1):
                react = next((t for t in rows[j]["texts"] if _REACT_RE.match(t)), None)
                if react:
                    reaction = re.sub(r"\s+", "", react)  # "+0.70"
                    break

            splits_map[final_time] = {
                "reaction":     reaction,
                "cumul_splits": cumul,
                "lap_splits":   laps,
            }
            i += 2 if row_c_found else 1
        else:
            i += 1

    return splits_map


# ─────────────────────────────────────────────────────────────────
# HTML table parser
# ─────────────────────────────────────────────────────────────────

def _parse_html_table(soup: BeautifulSoup) -> list[dict]:
    """
    Parse all result rows from the page.

    IMPORTANT: a page may contain multiple table.res-table elements
    (e.g. one per heat, or one per date-filter section).  We must
    derive expected_n, is_relay, and has_team_pts independently
    per table — if we merge all headers across all tables the count
    is wrong and every row gets rejected by the len-check.
    """
    rows = []

    for table in soup.select("table.res-table"):
        headers      = [th.get_text(strip=True) for th in table.select("thead th")]
        if not headers:
            continue
        is_relay     = "שנת לידה" not in headers
        has_team_pts = "ניקוד קבוצתי" in headers
        expected_n   = len(headers)

        for tr in table.select("tbody tr"):
            cells = tr.find_all("td")
            if len(cells) != expected_n:
                continue

            def cell(i): return cells[i].get_text(strip=True)
            def cint(i):
                try: return int(cells[i].get_text(strip=True))
                except: return None

            place = cint(0)
            if place is None:
                continue

            if not is_relay:
                name_tag = cells[1].find("a", href=re.compile(r"/Players/Details/"))
                rows.append({
                    "is_relay":    False,
                    "place":       place,
                    "loglig_id":   _player_id(name_tag),
                    "name":        name_tag.get_text(strip=True) if name_tag else cell(1),
                    "birth_year":  cint(2),
                    "club":        cell(3),
                    "heat":        cint(4) or 1,
                    "lane":        cint(5) or 0,
                    "result_time": cell(6),
                    "points":      cint(7),
                    "team_points": cint(8) if has_team_pts else None,
                })
            else:
                links = cells[1].find_all("a", href=re.compile(r"/Players/Details/"))
                rows.append({
                    "is_relay":    True,
                    "place":       place,
                    "names":       [a.get_text(strip=True).rstrip(",").strip() for a in links],
                    "loglig_ids":  [_player_id(a) for a in links],
                    "club":        cell(2),
                    "heat":        cint(3) or 1,
                    "lane":        cint(4) or 0,
                    "result_time": cell(5),
                    "points":      cint(6),
                    "team_points": cint(7) if has_team_pts else None,
                })

    return rows


# ─────────────────────────────────────────────────────────────────
# Score building
# ─────────────────────────────────────────────────────────────────

def _build_scores(
    html_rows: list[dict], splits_map: dict, race: Race, race_date: str,
    clubs_seen: dict, swimmers_seen: dict, registry: IdRegistry,
) -> tuple[list[IndividualScore], list[RelayScore]]:

    ind_scores: list[IndividualScore] = []
    rel_scores: list[RelayScore]      = []

    for row in html_rows:
        club = _get_club(row["club"], clubs_seen, registry)
        sp   = splits_map.get(row["result_time"], {})
        splits_str = _format_splits(sp.get("cumul_splits"))

        if not row["is_relay"]:
            sw = _get_swimmer(
                row["name"], row["loglig_id"], row["birth_year"],
                club.id, race.gender, swimmers_seen, registry,
            )
            ind_scores.append(IndividualScore(
                id            = registry.next("individual_score"),
                race_id       = race.id,
                swimmer_id    = sw.id,
                club_id       = club.id,
                race_date     = race_date,
                heat_num      = row["heat"],
                lane          = row["lane"],
                result_time   = row["result_time"],
                place         = row["place"],
                points        = row["points"],
                team_points   = row["team_points"],
                reaction_time = sp.get("reaction"),
                splits        = splits_str,
            ))
        else:
            sw_list = [
                _get_swimmer(nm, pid, None, club.id, race.gender, swimmers_seen, registry)
                for nm, pid in zip(row["names"], row["loglig_ids"])
            ]
            rel_scores.append(RelayScore(
                id          = registry.next("relay_score"),
                race_id     = race.id,
                club_id     = club.id,
                swimmer_ids = [sw.id for sw in sw_list],
                race_date   = race_date,
                heat_num    = row["heat"],
                lane        = row["lane"],
                result_time = row["result_time"],
                place       = row["place"],
                points      = row["points"],
                team_points = row["team_points"],
                splits      = splits_str,
            ))

    return ind_scores, rel_scores


def _format_splits(cumul: Optional[list]) -> Optional[str]:
    if not cumul:
        return None
    return ";".join(cumul)


# ─────────────────────────────────────────────────────────────────
# Entity helpers
# ─────────────────────────────────────────────────────────────────

def _player_id(a_tag) -> str:
    if a_tag:
        m = re.search(r"/Players/Details/(\d+)", a_tag.get("href", ""))
        if m:
            return m.group(1)
    return ""

def _get_club(name: str, clubs_seen: dict, registry: IdRegistry) -> Club:
    key = name.strip().lower()
    if key not in clubs_seen:
        clubs_seen[key] = Club(id=registry.next("club"), name=name.strip())
    return clubs_seen[key]

def _get_swimmer(
    name: str, loglig_id: str, birth_year: Optional[int],
    club_id: int, race_gender: str,
    swimmers_seen: dict, registry: IdRegistry,
) -> Swimmer:
    key = loglig_id if loglig_id else f"unk_{hashlib.md5(name.encode()).hexdigest()[:8]}"
    if key not in swimmers_seen:
        swimmers_seen[key] = Swimmer(
            id=registry.next("swimmer"), loglig_id=key,
            full_name=name, birth_year=birth_year, club_id=club_id,
        )
    sw = swimmers_seen[key]
    if race_gender in ("M", "F") and sw.gender is None:
        sw.gender = race_gender
    return sw