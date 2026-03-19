"""
pipeline.py

Phase 1  scrape_all_competitions()   pure HTTP → list[CompetitionMeta]
Phase 2  parse_competition()         Playwright (session for splits PDF) + requests (HTML)
Phase 3  save_competition()          pure file I/O  (bronze layer — raw files)
Phase 4  write_document()            PostgreSQL     (silver layer — structured DB)

Flags:
  --force        re-scrape and re-write all competitions, even already-saved ones
  --db-only      skip scraping/parsing, write existing JSON files to DB only
  --limit N      process at most N competitions (useful for testing)
"""
import argparse
import json
import logging
from pathlib import Path
from playwright.sync_api import sync_playwright
from scraper import scrape_all_competitions
from parser import parse_competition, _get_page
from storage import save_competition, already_saved, build_registry
from db.document_writer import write_document
from db.connection import close_pool
from models import (
    CompetitionDocument, Competition, Race, Club,
    Swimmer, IndividualScore, RelayScore
)
from config import JSON_DIR

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("pipeline")


# =============================================================================
# JSON → CompetitionDocument deserializer
# models.py uses dataclasses + asdict() for serialization, so the JSON
# contains nested plain dicts. We reconstruct dataclasses explicitly.
# =============================================================================

def _doc_from_dict(raw: dict) -> CompetitionDocument:
    comp = Competition(**raw["competition"])

    races    = [Race(**r)    for r in raw.get("races", [])]
    clubs    = [Club(**c)    for c in raw.get("clubs", [])]
    swimmers = [Swimmer(**s) for s in raw.get("swimmers", [])]

    individual_scores = [
        IndividualScore(**s) for s in raw.get("individual_scores", [])
    ]
    relay_scores = [
        RelayScore(**{**s, "swimmer_ids": s.get("swimmer_ids", [])})
        for s in raw.get("relay_scores", [])
    ]

    return CompetitionDocument(
        competition=comp,
        races=races,
        clubs=clubs,
        swimmers=swimmers,
        individual_scores=individual_scores,
        relay_scores=relay_scores,
    )


# =============================================================================
# Pipeline
# =============================================================================

def run_pipeline(force: bool = False, db_only: bool = False, limit: int = None) -> None:
    log.info("=" * 60)
    log.info("ISR Scraper Pipeline Starting")
    if force:   log.info("  mode: --force (re-scrape everything)")
    if db_only: log.info("  mode: --db-only (write existing JSON to DB)")
    if limit:   log.info(f"  mode: --limit {limit}")
    log.info("=" * 60)

    if db_only:
        _run_db_only(limit)
        return

    registry = build_registry()

    # ── Phase 1 ───────────────────────────────────────────────────
    log.info("─── Phase 1: Scrape competition metadata ───")
    all_comps = scrape_all_competitions()

    if force:
        to_process = all_comps
        log.info(f"  {len(all_comps)} found, {len(to_process)} to process (--force)")
    else:
        to_process = [c for c in all_comps if not already_saved(c.isr_id)]
        log.info(f"  {len(all_comps)} found, {len(to_process)} to process")

    if limit:
        to_process = to_process[:limit]
        log.info(f"  limited to {len(to_process)} competitions")

    if not to_process:
        log.info("Nothing to do.")
        close_pool()
        return

    # ── Phase 2 ───────────────────────────────────────────────────
    log.info("─── Phase 2: Parse all competitions ───")
    parsed = []

    with sync_playwright() as pw:
        page = _get_page(pw)

        for i, comp in enumerate(to_process, 1):
            log.info(f"[{i}/{len(to_process)}] {comp.name}  isr={comp.isr_id}  loglig={comp.loglig_id}")
            try:
                doc = parse_competition(comp, registry, page)
            except Exception as e:
                log.error(f"  ✗ Parse failed: {e}", exc_info=True)
                continue

            log.info(
                f"  ✓ races={len(doc.races)} ind={len(doc.individual_scores)} "
                f"relay={len(doc.relay_scores)} swimmers={len(doc.swimmers)}"
            )
            if doc.individual_scores or doc.relay_scores:
                parsed.append((comp, doc))
            else:
                log.warning(f"  ✗ 0 scores — skipping")

    log.info(f"Phase 2 done: {len(parsed)}/{len(to_process)} competitions with scores")

    # ── Phase 3 ───────────────────────────────────────────────────
    log.info("─── Phase 3: Save raw files (bronze) ───")
    saved_files = 0
    for comp, doc in parsed:
        try:
            save_competition(doc)
            saved_files += 1
        except Exception as e:
            log.error(f"  ✗ File save failed for {comp.name}: {e}", exc_info=True)

    # ── Phase 4 ───────────────────────────────────────────────────
    log.info("─── Phase 4: Write to PostgreSQL (silver) ───")
    saved_db = 0
    for comp, doc in parsed:
        log.info(f"  Writing {comp.name} ...")
        try:
            write_document(doc)
            saved_db += 1
        except Exception as e:
            log.error(f"  ✗ DB write failed for {comp.name}: {e}", exc_info=True)

    close_pool()

    log.info("=" * 60)
    log.info(f"Done: {saved_files} files saved | {saved_db} written to DB | "
             f"{len(to_process) - len(parsed)} failed/empty")
    log.info("=" * 60)


def _run_db_only(limit: int = None) -> None:
    """
    Load existing JSON files and write them to the DB without re-scraping.
    Useful when the DB is fresh but JSON files already exist.
    """
    json_files = sorted(JSON_DIR.glob("*.json"))
    if limit:
        json_files = json_files[:limit]

    log.info(f"─── db-only: loading {len(json_files)} JSON file(s) ───")
    saved_db = 0

    for path in json_files:
        log.info(f"  Loading {path.name} ...")
        try:
            raw = json.loads(path.read_text(encoding="utf-8-sig"))
            doc = _doc_from_dict(raw)
            log.info(
                f"    races={len(doc.races)} ind={len(doc.individual_scores)} "
                f"relay={len(doc.relay_scores)} swimmers={len(doc.swimmers)}"
            )
            write_document(doc)
            saved_db += 1
        except Exception as e:
            log.error(f"  ✗ Failed {path.name}: {e}", exc_info=True)

    close_pool()
    log.info("=" * 60)
    log.info(f"Done: {saved_db}/{len(json_files)} written to DB")
    log.info("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ISR Masters scraper pipeline")
    parser.add_argument("--force",   action="store_true", help="re-scrape all competitions")
    parser.add_argument("--db-only", action="store_true", dest="db_only", help="write existing JSON files to DB only")
    parser.add_argument("--limit",   type=int, default=None, help="process at most N competitions")
    args = parser.parse_args()

    run_pipeline(force=args.force, db_only=args.db_only, limit=args.limit)