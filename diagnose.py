"""
diagnose.py — step-by-step test runner.

Usage:
    python diagnose.py                  # test first competition, no save
    python diagnose.py --all            # test ALL competitions, no save
    python diagnose.py --id 16714       # test specific competition by ISR ID
    python diagnose.py --id 16714 --save  # test + write CSV/JSON
    python diagnose.py --all --save     # full pipeline run (same as pipeline.py)
    python diagnose.py --n 3            # test first 3 competitions

Flags:
    --all       Process all competitions (not just first)
    --id ID     Process only the competition with this ISR ID
    --n N       Process first N competitions
    --save      Write CSV/JSON output (default: dry run only)
    --force     Ignore already_saved() check (re-process even if JSON exists)
"""
import argparse, logging, sys

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s %(name)s: %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("diagnose")

parser = argparse.ArgumentParser(description="ISR Scraper diagnostic runner")
parser.add_argument("--all",   action="store_true", help="Process all competitions")
parser.add_argument("--id",    type=str,  default=None, help="Force specific ISR competition ID")
parser.add_argument("--n",     type=int,  default=None, help="Process first N competitions")
parser.add_argument("--save",  action="store_true", help="Write CSV/JSON output")
parser.add_argument("--force", action="store_true", help="Re-process even if already saved")
args = parser.parse_args()

# ── Phase 1: scrape competition metadata ──────────────────────────
log.info("=== Phase 1: scrape_all_competitions ===")
from scraper import scrape_all_competitions
all_comps = scrape_all_competitions()
log.info(f"  {len(all_comps)} competitions found")
for c in all_comps:
    log.info(f"  isr={c.isr_id:>6} loglig={str(c.loglig_id):>6} dates={c.dates} races={len(c.races)}  {c.name}")

# ── Select which competitions to process ─────────────────────────
if args.id:
    comps = [c for c in all_comps if c.isr_id == args.id]
    if not comps:
        log.error(f"No competition found with ISR ID={args.id}")
        sys.exit(1)
elif args.all:
    comps = all_comps
elif args.n:
    comps = all_comps[:args.n]
else:
    comps = all_comps[:1]   # default: first only

if not args.force:
    from storage import already_saved
    skipped = [c for c in comps if already_saved(c.isr_id)]
    comps   = [c for c in comps if not already_saved(c.isr_id)]
    if skipped:
        log.info(f"  Skipping {len(skipped)} already-saved: {[c.isr_id for c in skipped]}")
        log.info(f"  (use --force to re-process them)")

if not comps:
    log.info("Nothing to process (all already saved — use --force to re-run).")
    sys.exit(0)

log.info(f"  Will process {len(comps)} competition(s): {[c.isr_id for c in comps]}")

# ── Phase 2: parse ────────────────────────────────────────────────
log.info(f"\n=== Phase 2: parse_competition ===")
from models import IdRegistry
from parser import parse_competition, _get_page
from playwright.sync_api import sync_playwright

if args.save:
    from storage import build_registry
    registry = build_registry()
else:
    registry = IdRegistry()

parsed = []

with sync_playwright() as pw:
    page = _get_page(pw)
    for i, comp in enumerate(comps, 1):
        log.info(f"\n  [{i}/{len(comps)}] {comp.name}  isr={comp.isr_id}  loglig={comp.loglig_id}")
        try:
            doc = parse_competition(comp, registry, page)
        except Exception as e:
            log.error(f"  ✗ Parse exception: {e}", exc_info=True)
            continue

        log.info(f"  ✓ races={len(doc.races)} ind={len(doc.individual_scores)} "
                 f"relay={len(doc.relay_scores)} swimmers={len(doc.swimmers)} clubs={len(doc.clubs)}")

        if doc.individual_scores:
            s = doc.individual_scores[0]
            log.info(f"    sample ind  : place={s.place} heat={s.heat_num} lane={s.lane} "
                     f"time={s.result_time} reaction={s.reaction_time} splits={s.splits}")
        if doc.relay_scores:
            r = doc.relay_scores[0]
            log.info(f"    sample relay: place={r.place} heat={r.heat_num} lane={r.lane} "
                     f"time={r.result_time} splits={r.splits}")
        if doc.swimmers:
            sw = doc.swimmers[0]
            log.info(f"    sample swimmer: {sw.full_name}  loglig={sw.loglig_id}  "
                     f"birth={sw.birth_year}  gender={sw.gender}")

        if doc.individual_scores or doc.relay_scores:
            parsed.append((comp, doc))
        else:
            log.warning(f"  ✗ 0 scores — check HTML parsing / PDF fetch")

# ── Phase 3: save ─────────────────────────────────────────────────
if args.save:
    log.info(f"\n=== Phase 3: save ({len(parsed)} competition(s)) ===")
    from storage import save_competition
    saved = 0
    for comp, doc in parsed:
        try:
            save_competition(doc)
            saved += 1
        except Exception as e:
            log.error(f"  ✗ Save failed for {comp.name}: {e}", exc_info=True)
    log.info(f"  Saved {saved}/{len(parsed)}")
else:
    log.info(f"\n=== Phase 3: SKIPPED (dry run — use --save to write output) ===")

log.info(f"\n=== DONE: {len(parsed)}/{len(comps)} parsed with scores ===")