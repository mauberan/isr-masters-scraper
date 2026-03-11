"""
splits.py  —  parse splits PDF into a dict keyed by (heat, lane).

The splits PDF (IsSplitResults=True) has the same layout as the results PDF
but adds cumulative and lap time rows per swimmer block.

Returns:
    dict[(heat, lane)] = {
        "reaction_time": "00:00.65",   # may be None
        "splits": {
            "50":  {"cumulative": "00:36.94", "lap": "00:36.94"},
            "100": {"cumulative": "01:17.42", "lap": "00:40.48"},
            ...
        }
    }
"""

from pathlib import Path
from typing import Optional
import pdfplumber, re, logging

log = logging.getLogger(__name__)
TIME_RE    = re.compile(r"^\d{1,2}:\d{2}\.\d{2}$")
DIST_RE    = re.compile(r"'?(\d{2,4})\s*מ")


def parse_splits_pdf(pdf_path: Path) -> dict[tuple[int, int], dict]:
    result: dict[tuple[int, int], dict] = {}
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                _parse_page(page, result)
    except Exception as e:
        log.error(f"Failed to parse splits PDF {pdf_path.name}: {e}")
    return result


def _parse_page(page, result: dict) -> None:
    words = page.extract_words(x_tolerance=3, y_tolerance=3)
    if not words:
        return

    rows: dict[int, list] = {}
    for w in words:
        y = round(w["top"])
        rows.setdefault(y, []).append(w)
    for y in rows:
        rows[y].sort(key=lambda w: -w["x0"])   # RTL

    sorted_ys = sorted(rows.keys())

    # Identify checkpoint header rows (contain distance labels like '50 מ)
    checkpoints: list[int] = []
    for y in sorted_ys:
        dists = [int(m.group(1)) for t in [w["text"] for w in rows[y]]
                 if (m := DIST_RE.search(t))]
        if dists:
            checkpoints.extend(dists)
    checkpoints = sorted(set(checkpoints))
    if not checkpoints:
        return

    current_heat = 1
    i = 0
    while i < len(sorted_ys):
        y   = sorted_ys[i]
        texts = [w["text"] for w in rows[y]]

        # Heat separator
        joined = " ".join(texts)
        heat_m = re.search(r"מקצה\s*:?\s*(\d+)", joined)
        if heat_m and len(texts) <= 4:
            current_heat = int(heat_m.group(1))
            i += 1
            continue

        # Swimmer block: starts with a place number
        if not re.fullmatch(r"\d{1,3}", texts[0]):
            i += 1
            continue

        place = int(texts[0])
        remaining = texts[1:]

        # Find heat and lane from this row
        time_idx = next((j for j, t in enumerate(remaining) if TIME_RE.match(t)), None)
        if time_idx is None:
            i += 1
            continue

        result_time = remaining[time_idx]
        reaction_time = None
        after_time_idx = time_idx + 1
        if after_time_idx < len(remaining) and TIME_RE.match(remaining[after_time_idx]):
            reaction_time = remaining[after_time_idx]
            after_time_idx += 1

        before_time = remaining[:time_idx]
        lane = heat = None
        for j in range(len(before_time) - 1, -1, -1):
            if re.fullmatch(r"\d{1,2}", before_time[j]):
                if lane is None:
                    lane = int(before_time[j])
                elif heat is None:
                    heat = int(before_time[j])
                    break
        heat = heat or current_heat
        lane = lane or 0

        # Collect subsequent rows that contain time values (split rows)
        cum_times: list[str] = []
        lap_times: list[str] = []
        j = i + 1
        while j < len(sorted_ys) and (sorted_ys[j] - sorted_ys[j-1]) < 30:
            row_texts = [w["text"] for w in rows[sorted_ys[j]]]
            times_in_row = [t for t in row_texts if TIME_RE.match(t)]
            if not times_in_row:
                break
            if _is_cumulative(times_in_row):
                cum_times.extend(times_in_row)
            else:
                lap_times.extend(times_in_row)
            j += 1

        splits = {}
        for idx, dist in enumerate(checkpoints):
            cum = cum_times[idx] if idx < len(cum_times) else None
            lap = lap_times[idx] if idx < len(lap_times) else None
            if cum or lap:
                splits[str(dist)] = {"cumulative": cum, "lap": lap}

        result[(heat, lane)] = {
            "reaction_time": reaction_time,
            "splits":        splits or None,
        }
        i = j


def _is_cumulative(times: list[str]) -> bool:
    for t in times:
        m = re.match(r"(\d+):", t)
        if m and int(m.group(1)) >= 1:
            return True
    return False
