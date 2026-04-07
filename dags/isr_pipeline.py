# dags/isr_pipeline.py
#
# ISR Masters Scraper — Airflow DAG (Step 4 — with dbt integration)
#
# Pipeline:
#   check_for_new        — ShortCircuitOperator: skip if no new competitions
#   scrape_metadata      — fetch competition list, return CompetitionMeta dicts via XCom
#   parse_competition    — dynamic: one task per competition, full pipeline inside
#   dbt_run              — rebuild gold layer (personal bests, rankings, club stats)
#   dbt_test             — run dbt schema tests against gold models
#   done                 — empty task marking clean pipeline completion

import sys
import logging
from datetime import datetime, timedelta
from dataclasses import asdict

sys.path.insert(0, '/opt/airflow/project')

from airflow.decorators import dag, task
from airflow.operators.bash import BashOperator
from airflow.operators.empty import EmptyOperator

log = logging.getLogger(__name__)

DEFAULT_ARGS = {
    'retries':                   3,
    'retry_delay':               timedelta(minutes=5),
    'retry_exponential_backoff': True,
    'execution_timeout':         timedelta(hours=1),
}

# Path to the dbt project inside the container
DBT_PROJECT_DIR = '/opt/airflow/project/isr_transforms'
DBT_CMD = f'cd {DBT_PROJECT_DIR} && dbt'


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

Scrapes competition results from ISR, writes to PostgreSQL (silver),
then runs dbt to build the gold analytics layer.

### Schedule
Daily at 06:00 UTC.

### Tasks
| Task | Type | Description |
|------|------|-------------|
| check_for_new_competitions | ShortCircuit | Skips pipeline if no new competitions |
| scrape_metadata | Python | Fetches competition list from ISR |
| parse_competition | Python (dynamic) | One task per competition |
| dbt_run | Bash | Rebuilds gold layer models |
| dbt_test | Bash | Runs schema tests on gold models |
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
        Fetches the full competition list from ISR.
        Returns serialized CompetitionMeta dicts for new competitions only.
        Full dicts travel via XCom — parse_competition never re-scrapes.
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
        execution_timeout = timedelta(minutes=45),
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

        save_competition(doc)
        log.info('  files saved')

        write_document(doc)
        log.info('  DB write complete')

        close_pool()
        return comp.isr_id

    # ── Task 4: dbt run ────────────────────────────────────────────
    # Rebuilds all gold layer models after new data is written to silver.
    # trigger_rule='all_done' means this runs even if some parse tasks
    # failed — we still want to refresh the gold layer with whatever
    # competitions did succeed.
    dbt_run = BashOperator(
        task_id      = 'dbt_run',
        bash_command = f'{DBT_CMD} run --profiles-dir {DBT_PROJECT_DIR}',
        trigger_rule = 'all_done',
    )

    # ── Task 5: dbt test ───────────────────────────────────────────
    # Runs schema tests (not_null, unique, accepted_values, relationships)
    # against the freshly built gold models.
    # If tests fail, the task turns red in the UI — the data is still
    # queryable, but you get a visible signal that something is wrong.
    dbt_test = BashOperator(
        task_id      = 'dbt_test',
        bash_command = f'{DBT_CMD} test --profiles-dir {DBT_PROJECT_DIR}',
    )

    # ── Task 6: Done marker ────────────────────────────────────────
    done = EmptyOperator(
        task_id      = 'done',
        trigger_rule = 'all_done',
    )

    # ── DAG wiring ─────────────────────────────────────────────────
    #
    # check_for_new gates everything downstream via short-circuit.
    # parse_competition runs in parallel (one instance per competition).
    # dbt_run waits for ALL parse tasks to finish before rebuilding gold.
    # dbt_test runs after dbt_run succeeds.
    # done runs regardless — clean terminal node.
    #
    has_new    = check_for_new()
    comp_dicts = scrape_metadata()
    parsed     = parse_competition.expand(comp_dict=comp_dicts)

    has_new >> comp_dicts       # short-circuit gates scrape_metadata
    parsed  >> dbt_run          # dbt rebuilds after all competitions parsed
    dbt_run >> dbt_test >> done


isr_pipeline()