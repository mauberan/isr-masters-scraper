"""
models.py

Data model for ISR swimming competition results.

Primary data source: PDF export per race (ExportSwimmingDisciplineResults).
HTML scraping is used only for competition/race metadata.

Schema:
  competitions      — one row per competition
  races             — one row per race (event within competition)
  clubs             — deduplicated club list
  swimmers          — deduplicated swimmer list
  individual_scores — one row per swimmer per race
  relay_scores      — one row per relay team per race

Key design choices:
  - race_date on every score (from PDF header or race schedule)
  - date_range on competition (min..max of race dates)
  - splits stored as JSON string in CSV, nested object in JSON
  - dual-key: internal id (auto-int) + loglig_id (external)
"""

from dataclasses import dataclass, field, asdict
from typing import Optional
import json


class IdRegistry:
    def __init__(self):
        self._counters: dict[str, int] = {}

    def seed(self, entity: str, current_max: int) -> None:
        self._counters[entity] = max(self._counters.get(entity, 0), current_max)

    def next(self, entity: str) -> int:
        self._counters[entity] = self._counters.get(entity, 0) + 1
        return self._counters[entity]

    def peek(self, entity: str) -> int:
        return self._counters.get(entity, 0)


@dataclass
class Club:
    id:   int
    name: str


@dataclass
class Swimmer:
    id:         int
    loglig_id:  str            # from /Players/Details/{id} link
    full_name:  str
    birth_year: Optional[int]
    club_id:    int            # FK → Club.id
    gender:     Optional[str] = None   # "M" / "F" — inferred from race gender


@dataclass
class Competition:
    id:          int
    isr_id:      str
    loglig_id:   str
    name:        str
    date_range:  str           # e.g. "09/01/2026-10/01/2026" or "06/08/2021"
    sport_type:  str


@dataclass
class Race:
    id:              int
    competition_id:  int       # FK → Competition.id
    loglig_event_id: str       # discipline ID from loglig
    event_num:       int
    race_date:       str       # "DD/MM/YYYY" — from schedule or PDF header
    distance:        int       # metres
    stroke:          str       # FREE / BACK / BREAST / FLY / IM / MEDLEY
    category:        str       # raw category string e.g. "מאסטרס נ 21-99"
    gender:          str       # M / F / MIX
    is_relay:        bool
    start_time:      str       # scheduled start time


@dataclass
class IndividualScore:
    id:           int
    race_id:      int          # FK → Race.id
    swimmer_id:   int          # FK → Swimmer.id
    club_id:      int          # FK → Club.id
    race_date:    str          # denormalised for convenience
    heat_num:     int
    lane:         int
    result_time:  str
    place:        Optional[int]
    points:       Optional[int]
    team_points:  Optional[int]
    reaction_time: Optional[str] = None
    splits:       Optional[dict] = None   # {"50": {"cumulative": "...", "lap": "..."}, ...}


@dataclass
class RelayScore:
    id:           int
    race_id:      int          # FK → Race.id
    club_id:      int          # FK → Club.id
    swimmer_ids:  list[int]    # ordered swimmer FKs (leg 0..3)
    race_date:    str
    heat_num:     int
    lane:         int
    result_time:  str
    place:        Optional[int]
    points:       Optional[int]
    team_points:  Optional[int]
    splits:       Optional[dict] = None


@dataclass
class CompetitionDocument:
    competition:       Competition
    races:             list[Race]             = field(default_factory=list)
    clubs:             list[Club]             = field(default_factory=list)
    swimmers:          list[Swimmer]          = field(default_factory=list)
    individual_scores: list[IndividualScore]  = field(default_factory=list)
    relay_scores:      list[RelayScore]       = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)

    def to_flat_tables(self) -> dict[str, list[dict]]:
        def _serialise_score(s):
            d = asdict(s)
            d["splits"] = json.dumps(s.splits, ensure_ascii=False) if s.splits else None
            return d

        relay_rows = []
        for r in self.relay_scores:
            d = _serialise_score(r)
            d["swimmer_ids"] = " | ".join(str(i) for i in r.swimmer_ids)
            relay_rows.append(d)

        return {
            "competitions":      [asdict(self.competition)],
            "races":             [asdict(r) for r in self.races],
            "clubs":             [asdict(c) for c in self.clubs],
            "swimmers":          [asdict(s) for s in self.swimmers],
            "individual_scores": [_serialise_score(s) for s in self.individual_scores],
            "relay_scores":      relay_rows,
        }
