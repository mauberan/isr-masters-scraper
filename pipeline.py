"""
pipeline.py

Phase 1  scrape_all_competitions()   pure HTTP → list[CompetitionMeta]
Phase 2  parse_competition()         Playwright (session for splits PDF) + requests (HTML)
Phase 3  save_competition()          pure file I/O
"""
import logging
from playwright.sync_api import sync_playwright
from scraper import scrape_all_competitions
from parser import parse_competition, _get_page
from storage import save_competition, already_saved, build_registry

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("pipeline")


def run_pipeline() -> None:
    log.info("=" * 60)
    log.info("ISR Scraper Pipeline Starting")
    log.info("=" * 60)

    registry = build_registry()

    # ── Phase 1 ───────────────────────────────────────────────────
    log.info("─── Phase 1: Scrape competition metadata ───")
    all_comps  = scrape_all_competitions()
    to_process = [c for c in all_comps if not already_saved(c.isr_id)]
    log.info(f"  {len(all_comps)} found, {len(to_process)} to process")

    if not to_process:
        log.info("Nothing to do.")
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
    log.info("─── Phase 3: Save all ───")
    saved = 0
    for comp, doc in parsed:
        try:
            save_competition(doc)
            saved += 1
        except Exception as e:
            log.error(f"  ✗ Save failed for {comp.name}: {e}", exc_info=True)

    log.info("=" * 60)
    log.info(f"Done: {saved} saved | {len(to_process)-len(parsed)} failed/empty")
    log.info("=" * 60)


if __name__ == "__main__":
    run_pipeline()