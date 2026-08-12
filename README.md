# ISR Masters Scraper

An end-to-end data pipeline that scrapes Israeli swimming competition results from the ISR platform, stores them in PostgreSQL, and builds an analytics layer with dbt — all orchestrated by Apache Airflow.

---

## What it does

The Israel Swimming Association (ISR) publishes Masters competition results on a third-party platform (loglig.com) that offers no public API. This project automates the extraction, structuring, and analysis of that data:

- **Scrapes** competition metadata, race results, and split times from HTML pages and PDF exports
- **Parses** PDFs in-browser using PDF.js injected into a headless Playwright session
- **Stores** raw data as JSON (bronze layer) and structured records in PostgreSQL (silver layer)
- **Transforms** the silver layer into analytics-ready mart tables via dbt (gold layer)
- **Runs daily** on a cron schedule via an Airflow DAG, with per-competition parallel tasks and automatic retries

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Airflow DAG                              │
│                                                                 │
│  check_for_new ─► scrape_metadata ─► parse_competition (×N)    │
│                                              │                  │
│                                         dbt_run ─► dbt_test    │
└─────────────────────────────────────────────────────────────────┘
         │                    │                    │
         ▼                    ▼                    ▼
   ISR / loglig.com     JSON files           PostgreSQL
   (HTTP + Playwright)  (bronze)        (silver → gold via dbt)
```

### Pipeline phases

| Phase | Description | Layer |
|-------|-------------|-------|
| 1 — Scrape metadata | Fetch competition list; resolve loglig IDs and race schedules | — |
| 2 — Parse competition | Playwright session + requests: HTML results + PDF split times | — |
| 3 — Save files | Write `CompetitionDocument` as JSON | Bronze |
| 4 — Write to DB | Upsert competitions, clubs, swimmers, events, results | Silver |
| 5 — dbt run/test | Rebuild personal bests, event rankings, club statistics | Gold |

---

## Tech stack

| Layer | Tool |
|-------|------|
| Scraping | Python · [Playwright](https://playwright.dev/python/) · [requests](https://requests.readthedocs.io/) · [BeautifulSoup](https://www.crummy.com/software/BeautifulSoup/) |
| PDF parsing | [PDF.js](https://mozilla.github.io/pdf.js/) (injected into Playwright browser context) |
| Database | PostgreSQL 16 |
| DB driver | [psycopg3](https://www.psycopg.org/psycopg3/) + connection pool |
| Transforms | [dbt](https://www.getdbt.com/) (staging → intermediate → mart models) |
| Orchestration | [Apache Airflow](https://airflow.apache.org/) (dynamic task mapping, ShortCircuit, BashOperator) |
| Infrastructure | Docker Compose (two Postgres instances: ISR data + Airflow metadata) |

---

## Project structure

```
isrscraper/
├── scraper.py              # Phase 1 — pure HTTP, fetches competition list + race schedule
├── parser.py               # Phase 2 — Playwright + PDF.js + HTML parsing
├── storage.py              # Phase 3 — saves CompetitionDocument to JSON
├── pipeline.py             # CLI entrypoint — runs all 4 phases
├── models.py               # Dataclasses: Competition, Race, Swimmer, IndividualScore, RelayScore
├── config.py               # URLs, paths, headers
│
├── db/
│   ├── schema.sql          # Full PostgreSQL schema (for a fresh database)
│   ├── document_writer.py  # Phase 4 — upserts CompetitionDocument to Postgres
│   ├── connection.py       # psycopg3 connection pool
│   └── queries/            # Ad-hoc analytical SQL queries
│
├── dags/
│   └── isr_pipeline.py     # Airflow DAG — daily cron, dynamic task mapping
│
├── isr_transforms/         # dbt project
│   └── models/
│       ├── staging/        # stg_* — clean, typed views over raw tables
│       ├── intermediate/   # int_* — enriched results with age group info
│       └── marts/          # fct_personal_bests, fct_event_rankings, fct_club_statistics
│
├── migrations/             # Incremental SQL migrations for existing databases
├── docs/
│   └── data_model.md       # Entity model and key design decisions
│
├── Dockerfile              # Airflow image (Python + Playwright + dbt)
├── docker-compose.yml      # Development stack
├── docker-compose.prod.yml # Production stack (Railway)
└── requirements.txt
```

---

## Data model

Six tables, one transaction per competition:

```
competitions
    └──< events (races)
              └──< heats
                       ├──< results      (individual)
                       └──< relay_results
clubs ──────────────────────────────────┘ (referenced by results)
swimmers ───────────────────────────────┘ (referenced by results)
```

Key design decisions are documented in [`docs/data_model.md`](docs/data_model.md).

---

## dbt gold layer

Three mart models built from the silver layer:

| Model | Description |
|-------|-------------|
| `fct_personal_bests` | Each swimmer's best result per event/gender/pool-type |
| `fct_event_rankings` | Cross-competition rankings by stroke, distance, age group |
| `fct_club_statistics` | Aggregate club performance: total points, race counts, podiums |

---

## Local setup

### Prerequisites

- Docker & Docker Compose
- (Optional) Python 3.12 + `playwright install chromium` for running the pipeline directly

### 1. Configure environment

```bash
cp .env.example .env
# Fill in POSTGRES_*, AIRFLOW_*, and AIRFLOW__CORE__FERNET_KEY
```

Generate the Fernet key:
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### 2. Configure dbt

```bash
cp isr_transforms/profiles.yml.example isr_transforms/profiles.yml
# Edit host/user/password to match your .env values
```

### 3. Start the stack

```bash
docker compose up --build
```

This starts:
- `db` — ISR data (PostgreSQL 16, schema auto-applied on first start)
- `airflow-db` — Airflow metadata database
- `airflow-init` — runs migrations and creates admin user, then exits
- `airflow-webserver` — Airflow UI at http://localhost:8080
- `airflow-scheduler` — runs the DAG on schedule

### 4. Run the pipeline manually

**Via Airflow UI** (recommended): open http://localhost:8080, unpause `isr_pipeline`, trigger a run.

**Via CLI** (without Airflow):
```bash
# Full pipeline
python pipeline.py

# Re-scrape everything
python pipeline.py --force

# Write existing JSON files to DB only (useful after schema changes)
python pipeline.py --db-only

# Test with a small batch
python pipeline.py --limit 3
```

---

## Notable implementation details

**PDF splits via browser session** — loglig.com requires an active session cookie to download split-time PDFs. Rather than handling cookie jars in plain requests, the pipeline keeps a persistent Playwright page open, uses `page.evaluate()` to POST the PDF endpoint within that session, and parses the returned bytes with PDF.js — all without writing the PDF to disk.

**Dynamic task mapping** — the Airflow DAG uses `.expand()` so each competition gets its own task instance, enabling parallelism and per-competition retry logic without fan-out boilerplate.

**Idempotent upserts** — every DB write uses `INSERT ... ON CONFLICT DO UPDATE`, so re-running the pipeline on already-processed competitions is safe.

**Hebrew source data** — race names, club names, and category strings are in Hebrew. The scraper includes stroke-name mapping (`STROKE_MAP`) and gender/relay detection logic that handles RTL text patterns.

---

## Running dbt independently

```bash
cd isr_transforms
dbt run   --profiles-dir .
dbt test  --profiles-dir .
dbt docs generate --profiles-dir . && dbt docs serve
```
