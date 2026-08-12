# ISR Data Model

## Overview

This document describes the database schema used by the ISR Masters Scraper to store competition results from the Israel Swimming Association platform (loglig.com).

---

## Entity-Relationship Summary

```
competitions
    └──< events
              └──< heats
                       ├──< results      ──< swimmers
                       └──< relay_results
clubs ─────────────────────────────────── (referenced by results, swimmers)
```

- One **competition** has many **events** (races)
- One **event** has many **heats** (sub-groups of swimmers)
- One **heat** has many **results** (individual) or **relay_results**
- **Swimmers** exist independently and appear across many competitions
- **Clubs** are deduplicated; club at race time is stored on the result row, not on the swimmer

---

## Tables

### `competitions`
One row per swim meet.

| Column | Type | Notes |
|--------|------|-------|
| `id` | SERIAL PK | Internal |
| `competition_id` | VARCHAR UNIQUE | ISR's own ID (from URL) |
| `loglig_id` | VARCHAR | Loglig platform ID |
| `name` | TEXT | Competition display name |
| `location` | TEXT | NULL until manually set |
| `start_date` | DATE | Parsed from date_range |
| `end_date` | DATE | NULL for single-day meets |
| `sport_type` | TEXT | e.g. "שחייה" (swimming) |
| `pool_course` | VARCHAR(2) | SC or LC, default SC |
| `scraped_at` | TIMESTAMPTZ | Audit timestamp |

### `clubs`
Deduplicated club list across all competitions.

| Column | Type | Notes |
|--------|------|-------|
| `id` | SERIAL PK | |
| `name` | TEXT UNIQUE | As it appears on loglig |

### `swimmers`
Deduplicated swimmer list across all competitions.

| Column | Type | Notes |
|--------|------|-------|
| `id` | SERIAL PK | |
| `loglig_id` | VARCHAR UNIQUE | From `/Players/Details/{id}` link |
| `full_name` | TEXT | |
| `birth_year` | INT | Used for age group calculation |
| `club_id` | INT FK → clubs | Home club at registration time |
| `gender` | VARCHAR(5) | M / F — inferred from race gender |

Upsert strategy: if `loglig_id` is a real player link ID, upsert on `loglig_id`. If the swimmer had no profile link, fall back to `(full_name, birth_year)` as the natural key.

### `events`
One row per race within a competition.

| Column | Type | Notes |
|--------|------|-------|
| `id` | SERIAL PK | |
| `competition_id` | INT FK → competitions | |
| `loglig_event_id` | VARCHAR | Discipline ID on loglig |
| `event_num` | INT | Order within the competition |
| `name` | TEXT | e.g. "50m free M" |
| `distance_m` | INT | Metres |
| `stroke` | VARCHAR(30) | FREE / BACK / BREAST / FLY / IM / MEDLEY |
| `gender` | VARCHAR(10) | M / F / MIX |
| `category` | TEXT | Raw Hebrew category string |
| `is_relay` | BOOLEAN | |
| `race_date` | DATE | From PDF header or race schedule |
| `start_time` | TEXT | Scheduled start time |
| `pool_course` | VARCHAR(2) | SC or LC, default SC |

### `heats`
Sub-groups within an event.

| Column | Type | Notes |
|--------|------|-------|
| `id` | SERIAL PK | |
| `event_id` | INT FK → events | |
| `heat_num` | INT | |

Heats are created lazily when a result row is written.

### `results`
One row per swimmer per heat.

| Column | Type | Notes |
|--------|------|-------|
| `id` | SERIAL PK | |
| `heat_id` | INT FK → heats | |
| `swimmer_id` | INT FK → swimmers | |
| `club_id` | INT FK → clubs | Club at time of race |
| `lane` | INT | |
| `time_ms` | INT | Milliseconds; NULL if DSQ or DNS |
| `dsq` | BOOLEAN | Disqualified |
| `dns` | BOOLEAN | Did not start |
| `place` | INT | Overall place in the event |
| `points` | INT | Individual points |
| `team_points` | INT | Points counting toward club score |
| `reaction_time` | VARCHAR(20) | e.g. "+0.70" — from splits PDF |
| `splits` | JSONB | `{"1": "25.43", "2": "51.22", ...}` cumulative |
| `scraped_at` | TIMESTAMPTZ | |

### `relay_results`
One row per relay team per heat.

| Column | Type | Notes |
|--------|------|-------|
| `id` | SERIAL PK | |
| `heat_id` | INT FK → heats | |
| `club_id` | INT FK → clubs | |
| `swimmer_ids` | INT[] | Ordered leg array (leg 0..3) |
| `lane` | INT | |
| `time_ms` | INT | Milliseconds |
| `dsq` / `dns` | BOOLEAN | |
| `place` | INT | |
| `points` / `team_points` | INT | |
| `splits` | JSONB | Same format as results |
| `scraped_at` | TIMESTAMPTZ | |

---

## Key Design Decisions

**Swimmer identity: `loglig_id` primary, `(full_name, birth_year)` fallback**
Loglig exposes a stable player ID via profile links. When available, it is used as the natural key. For relay legs that appear without a profile link, `(full_name, birth_year)` is the fallback.

**Club stored on the result, not the swimmer**
Swimmers change clubs between seasons. Storing club on the result row preserves the historical club affiliation at the time of the race.

**Age group is derived, not stored**
`age_group = EXTRACT(YEAR FROM race_date) - birth_year`. Storing it would be redundant and could diverge. It is computed at query time in the dbt intermediate model.

**Times stored as integers (milliseconds) in the DB**
`"25.43"` → `25430`. Enables arithmetic, sorting, and aggregation without string parsing. The raw string is stored in `result_time` in the JSON bronze layer; conversion happens at write time.

**DSQ and DNS as boolean flags**
Avoids the temptation to store `"DSQ"` as a time value, which would break numeric queries.

**Idempotent upserts**
Every write uses `INSERT ... ON CONFLICT DO UPDATE`, keyed on natural unique constraints. Re-running the pipeline on already-stored competitions is safe.

**Timezone-aware timestamps**
`scraped_at TIMESTAMPTZ` on all fact tables avoids silent timezone bugs.
