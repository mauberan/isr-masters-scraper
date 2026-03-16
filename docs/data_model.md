# ISR Data Model

## Overview

This document describes the entity model for data collected by `isr-masters-scraper`
from the Israel Swimming Association (ISR) results platform (loglig.com).

Designing this model was the first step before writing any database code — to avoid
structural mistakes that are expensive to fix later.

---

## Source Data

The scraper collects competition results structured as follows (simplified):

```
competition → events → heats → results (one row per swimmer per heat)
```

Each result row from the raw scrape looks roughly like:

| field | example |
|-------|---------|
| competition name | "ISR Masters Championship 2024" |
| competition date | 2024-11-10 |
| event | "50m Freestyle" |
| gender | "Men" |
| birth year | 1979 |
| heat number | 3 |
| lane | 5 |
| swimmer name | "Lior Cohen" |
| club | "HaMaccabi Tel Aviv" |
| time | "25.43" |

---

## Entity Identification

From the raw data, the following real-world entities were identified:

### Competition
A swim meet — has a name, date range, and location.
- Natural key: ISR's own `competition_id` (from the URL/DOM)

### Event
A specific race within a competition — e.g. "50m Freestyle Men 45-49".
- Belongs to one competition
- Can be decomposed into: distance, stroke, gender
- Age group is not stored directly — it is derived from swimmer birth year and competition date

### Heat
A sub-group within an event — swimmers are split into heats by seed time.
- Belongs to one event
- Identified by heat number within its event

### Swimmer
A person. No stable external ID is available from the source site.
- Natural key: `(full_name, birth_year)` — name alone is not unique enough
- Club is tracked per result, not on the swimmer — swimmers change clubs over time
- Age group is computed: `competition_year - birth_year`

### Result
One swimmer's performance in one heat.
- Links a swimmer to a heat
- Contains: lane, time, DSQ/DNS flags, club at time of race

---

## Entity-Relationship Sketch

```
competitions
    │
    └──< events
              │
              └──< heats
                       │
                       └──< results >── swimmers
```

- One competition has many events
- One event has many heats
- One heat has many results
- Each result belongs to one swimmer
- Swimmers exist independently — the same swimmer appears across many competitions

---

## Key Design Decisions

**Swimmer identity: `(full_name, birth_year)`, no external ID**
The source site provides no stable swimmer ID we can rely on. `full_name` alone is
not unique enough across hundreds of swimmers. `birth_year` is the tiebreaker —
it is also needed for age group calculation, so it pulls double duty.

**Club stored on the result, not the swimmer**
Swimmers change clubs between seasons. Storing club on the swimmer row would lose
historical accuracy. Instead, `club` is a column on `results` — capturing where
the swimmer competed at the time of that race.

**Age group is derived, not stored**
`age_group = competition_year - swimmer.birth_year`. Storing it would be redundant
and could go out of sync. It is computed at query time.

**Times stored as integers (milliseconds), not strings**
`"25.43"` → `25430`. Enables arithmetic, sorting, and aggregation without parsing.

**DSQ and DNS as boolean flags, not special time values**
Avoids the temptation to store `"DSQ"` as a time string, which breaks numeric queries.

**Timezone-aware timestamps for all audit columns**
`scraped_at TIMESTAMPTZ` — avoids silent timezone bugs in multi-locale environments.