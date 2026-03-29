# dags/isr_pipeline.py
#
# ISR Masters Scraper — Airflow DAG (production, Step 3 capstone)
#
# Pipeline:
#   check_for_new        — ShortCircuitOperator: skip if no new competitions
#   scrape_metadata      — fetch competition list, return CompetitionMeta dicts via XCom
#   parse_competition    — dynamic: one task per competition, full pipeline inside
#   done                 — empty task marking clean pipeline completion
#
# Design decisions:
#   - scrape_all_competitions() called ONCE in scrape_metadata (not re-scraped in parse)
#   - Full CompetitionMeta serialized to dict and passed via XCom
#   - check_for_new makes its own lightweight HTTP call — acceptable duplication,
#     keeps short-circuit logic self-contained
#   - Each parse_competition task is fully idempotent (all DB writes are upserts)
#   - Playwright session opened and closed within each task (not shared across tasks)
#   - DB connection pool closed at end of each task (LocalExecutor subprocess isolation)

import sys
import logging
from datetime import datetime, timedelta
from dataclasses import asdict

sys.path.insert(0, '/opt/airflow/project')

from airflow.decorators import dag, task
from airflow.operators.empty import EmptyOperator

log = logging.getLogger(__name__)

DEFAULT_ARGS = {
    'retries':                   3,
    'retry_delay':               timedelta(minutes=5),
    'retry_exponential_backoff': True,
    'execution_timeout':         timedelta(hours=1),
}


@dag(
    dag_id          = 'isr_pipeline',
    schedule        = '0 6 * * *',
    start_date      = datetime(2025, 1, 1),
    catchup         = False,
    max_active_runs = 1,
    default_args    = DEFAULT_ARGS,
    tags            = ['isr', 'scraper'],
    doc_md          = """
## ISR Masters Scraper Pipeline

Scrapes competition results from the Israel Swimming Association (ISR) site,
parses them via Playwright, saves raw files (bronze), and writes to PostgreSQL (silver).

### Schedule
Daily at 06:00 UTC.

### Tasks
| Task | Type | Description |
|------|------|-------------|
| check_for_new_competitions | ShortCircuit | Skips pipeline if no new competitions |
| scrape_metadata | Python | Fetches competition list from ISR |
| parse_competition | Python (dynamic) | One task per competition |
| done | Empty | Marks clean pipeline completion |
    """,
)
def isr_pipeline():

    # ── Task 1: Short-circuit ──────────────────────────────────────
    @task.short_circuit(task_id='check_for_new_competitions')
    def check_for_new() -> bool:
        """
        Lightweight HTTP check — no Playwright, no parsing.
        Returns False to skip the entire pipeline if no new competitions exist.
        """
        from scraper import scrape_all_competitions
        from storage import already_saved

        all_comps = scrape_all_competitions()
        new_comps = [c for c in all_comps if not already_saved(c.isr_id)]
        log.info(f'check_for_new: {len(all_comps)} total, {len(new_comps)} new')
        return len(new_comps) > 0

    # ── Task 2: Scrape metadata ────────────────────────────────────
    @task(task_id='scrape_metadata')
    def scrape_metadata() -> list[dict]:
        """
        Fetches the full competition list from ISR — the only task that makes
        HTTP requests to the ISR site. Returns serialized CompetitionMeta dicts
        for new (unsaved) competitions only.
        """
        from scraper import scrape_all_competitions
        from storage import already_saved

        all_comps = scrape_all_competitions()
        new_comps = [c for c in all_comps if not already_saved(c.isr_id)]
        log.info(f'scrape_metadata: {len(new_comps)} competitions to process')
        return [asdict(c) for c in new_comps]

    # ── Task 3: Parse + store (one per competition) ────────────────
    @task(
        task_id           = 'parse_competition',
        retries           = 3,
        retry_delay       = timedelta(minutes=5),
        execution_timeout = timedelta(minutes=45),  # per-competition timeout
    )
    def parse_competition(comp_dict: dict) -> str:
        """
        Full pipeline for a single competition:
          1. Reconstruct CompetitionMeta from XCom dict
          2. Parse via Playwright + requests -> CompetitionDocument
          3. Save raw files (bronze)
          4. Write to PostgreSQL (silver)

        Idempotent — safe to retry. Returns isr_id on success.
        """
        from scraper import CompetitionMeta, RaceMeta
        from playwright.sync_api import sync_playwright
        from parser import parse_competition as _parse, _get_page
        from storage import save_competition, build_registry
        from db.document_writer import write_document
        from db.connection import close_pool

        # Reconstruct CompetitionMeta from XCom dict
        comp_dict['races'] = [RaceMeta(**r) for r in comp_dict.get('races', [])]
        comp = CompetitionMeta(**comp_dict)

        log.info(f'parse_competition: starting {comp.name} (isr={comp.isr_id})')

        # Parse
        registry = build_registry()
        with sync_playwright() as pw:
            page = _get_page(pw)
            doc  = _parse(comp, registry, page)

        log.info(
            f'  parsed: races={len(doc.races)} '
            f'ind={len(doc.individual_scores)} '
            f'relay={len(doc.relay_scores)} '
            f'swimmers={len(doc.swimmers)}'
        )

        if not doc.individual_scores and not doc.relay_scores:
            raise ValueError(f'{comp.isr_id}: 0 scores scraped — will retry')

        # Save files (bronze)
        save_competition(doc)
        log.info('  files saved')

        # Write to DB (silver)
        write_document(doc)
        log.info('  DB write complete')

        # Clean up DB pool (subprocess isolation)
        close_pool()

        return comp.isr_id

    # ── Task 4: Done marker ────────────────────────────────────────
    done = EmptyOperator(task_id='done', trigger_rule='all_done')
    # trigger_rule='all_done' means done runs even if some parse tasks
    # failed or were skipped — it marks the end of the pipeline run
    # regardless of individual competition outcomes

    # ── DAG wiring ─────────────────────────────────────────────────
    has_new    = check_for_new()
    comp_dicts = scrape_metadata()
    parsed     = parse_competition.expand(comp_dict=comp_dicts)

    has_new >> comp_dicts   # short-circuit gates scrape_metadata
    parsed >> done          # done runs after all parse tasks complete

isr_pipeline()