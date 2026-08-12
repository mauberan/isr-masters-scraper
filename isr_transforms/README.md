# isr_transforms — dbt project

dbt transformation layer for the ISR Masters Scraper. Transforms structured PostgreSQL data (silver) into analytics-ready mart tables (gold).

## Model layers

### Staging (`models/staging/`)

Clean, typed views over the raw silver tables. One model per source table:

| Model | Source table |
|-------|-------------|
| `stg_competitions` | `competitions` |
| `stg_events` | `events` |
| `stg_clubs` | `clubs` |
| `stg_swimmers` | `swimmers` |
| `stg_results` | `results` |

Staging models cast types, rename columns to consistent naming conventions, and filter out DSQ/DNS records where appropriate.

### Intermediate (`models/intermediate/`)

| Model | Description |
|-------|-------------|
| `int_results_enriched` | Joins results with swimmer, club, event, and competition data; computes age group from `birth_year` and `race_date` |

### Marts (`models/marts/`)

| Model | Description |
|-------|-------------|
| `fct_personal_bests` | Best result per swimmer per event type (stroke + distance + gender + pool course) |
| `fct_event_rankings` | Cross-competition rankings by stroke, distance, and age group |
| `fct_club_statistics` | Aggregate club performance: total points, podium count, race participation |

## Schema tests

Tests are defined in `models/staging/schema.yml` and cover:
- `not_null` on primary keys and required fields
- `unique` on primary keys
- `accepted_values` on `pool_course` (SC/LC) and `gender` (M/F/MIX)

## Setup

Copy and fill in the profiles file:
```bash
cp profiles.yml.example profiles.yml
```

Run models and tests:
```bash
dbt run   --profiles-dir .
dbt test  --profiles-dir .
```

Generate and view documentation:
```bash
dbt docs generate --profiles-dir .
dbt docs serve
```
