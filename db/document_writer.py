# db/document_writer.py
#
# Writes a CompetitionDocument to PostgreSQL in a single transaction.
#
# Audited against the real parser.py / models.py — key differences from
# the course draft:
#   - splits is a semicolon string ("25.43;51.22") not a dict — converted to JSONB on write
#   - loglig_id on swimmers can be "unk_{hash}" for swimmers without a real ID —
#     upsert falls back to (full_name, birth_year) for those
#   - Competition has no location field (scraper doesn't collect it)
#   - relay_results conflict target is (heat_id, club_id, lane) not (heat_id, club_id)
#
# Entity write order (dependency chain):
#   competitions → clubs → swimmers → events → heats (lazy) → results / relay_results

import json
import logging
from models import CompetitionDocument, Competition, Club, Swimmer, Race, IndividualScore, RelayScore
from db.connection import get_conn
from utils.time_utils import time_str_to_ms, is_non_time

log = logging.getLogger(__name__)


# =============================================================================
# Public interface
# =============================================================================

def write_document(doc: CompetitionDocument) -> None:
    """
    Writes a full CompetitionDocument to PostgreSQL in one transaction.
    Safe to call multiple times on the same document (idempotent).
    """
    with get_conn() as conn:
        club_id_map:    dict[int, int] = {}
        swimmer_id_map: dict[int, int] = {}
        event_id_map:   dict[int, int] = {}

        comp_db_id = _upsert_competition(conn, doc.competition)
        log.debug(f"  db competition id={comp_db_id}")

        for club in doc.clubs:
            club_id_map[club.id] = _upsert_club(conn, club)

        for swimmer in doc.swimmers:
            home_club_db_id = club_id_map.get(swimmer.club_id)
            swimmer_id_map[swimmer.id] = _upsert_swimmer(conn, swimmer, home_club_db_id)

        for race in doc.races:
            event_id_map[race.id] = _upsert_event(conn, comp_db_id, race)

        for score in doc.individual_scores:
            event_db_id   = event_id_map[score.race_id]
            swimmer_db_id = swimmer_id_map[score.swimmer_id]
            club_db_id    = club_id_map.get(score.club_id)
            _upsert_individual_score(conn, event_db_id, swimmer_db_id, club_db_id, score)

        for score in doc.relay_scores:
            event_db_id    = event_id_map[score.race_id]
            club_db_id     = club_id_map[score.club_id]
            swimmer_db_ids = [swimmer_id_map[sid] for sid in score.swimmer_ids]
            _upsert_relay_score(conn, event_db_id, club_db_id, swimmer_db_ids, score)

        log.info(
            f"  wrote: {len(doc.clubs)} clubs  {len(doc.swimmers)} swimmers  "
            f"{len(doc.races)} events  {len(doc.individual_scores)} results  "
            f"{len(doc.relay_scores)} relay results"
        )


# =============================================================================
# Private helpers
# =============================================================================

def _parse_dd_mm_yyyy(s: str | None) -> str | None:
    """Convert DD/MM/YYYY → YYYY-MM-DD for Postgres DATE columns."""
    if not s:
        return None
    try:
        d, m, y = s.strip().split("/")
        return f"{y}-{m}-{d}"
    except Exception:
        return None


def _splits_to_jsonb(splits_str: str | None) -> str | None:
    """
    Convert parser.py's semicolon split string to a JSONB-compatible dict.

    Input:  "25.43;51.22;1:08.11"
    Output: '{"1": "25.43", "2": "51.22", "3": "1:08.11"}'
    """
    if not splits_str:
        return None
    parts = [s.strip() for s in splits_str.split(";") if s.strip()]
    return json.dumps({str(i + 1): t for i, t in enumerate(parts)}, ensure_ascii=False)


def _upsert_competition(conn, c: Competition) -> int:
    dr = (c.date_range or "").strip()
    if "-" in dr[9:]:
        idx        = dr.index("-", 9)
        start_date = _parse_dd_mm_yyyy(dr[:idx])
        end_date   = _parse_dd_mm_yyyy(dr[idx + 1:])
    else:
        start_date = _parse_dd_mm_yyyy(dr) if dr else None
        end_date   = None

    row = conn.execute(
        """
        INSERT INTO competitions
            (competition_id, loglig_id, name, start_date, end_date, sport_type)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (competition_id) DO UPDATE SET
            loglig_id  = EXCLUDED.loglig_id,
            name       = EXCLUDED.name,
            start_date = COALESCE(EXCLUDED.start_date, competitions.start_date),
            end_date   = COALESCE(EXCLUDED.end_date,   competitions.end_date),
            sport_type = EXCLUDED.sport_type
        RETURNING id
        """,
        (c.isr_id, c.loglig_id or None, c.name, start_date, end_date, c.sport_type or None)
    ).fetchone()
    return row[0]


def _upsert_club(conn, club: Club) -> int:
    row = conn.execute(
        """
        INSERT INTO clubs (name)
        VALUES (%s)
        ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name
        RETURNING id
        """,
        (club.name,)
    ).fetchone()
    return row[0]


def _upsert_swimmer(conn, swimmer: Swimmer, home_club_db_id: int | None) -> int:
    """
    Two upsert strategies:
      - Real loglig_id: upsert on loglig_id
      - "unk_" prefix:  upsert on (full_name, birth_year)
    """
    is_real_id = swimmer.loglig_id and not swimmer.loglig_id.startswith("unk_")

    if is_real_id:
        row = conn.execute(
            """
            INSERT INTO swimmers (loglig_id, full_name, birth_year, club_id, gender)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (loglig_id) DO UPDATE SET
                full_name  = EXCLUDED.full_name,
                birth_year = COALESCE(EXCLUDED.birth_year, swimmers.birth_year),
                club_id    = COALESCE(EXCLUDED.club_id,    swimmers.club_id),
                gender     = COALESCE(EXCLUDED.gender,     swimmers.gender)
            RETURNING id
            """,
            (swimmer.loglig_id, swimmer.full_name, swimmer.birth_year,
             home_club_db_id, swimmer.gender)
        ).fetchone()
    else:
        row = conn.execute(
            """
            INSERT INTO swimmers (full_name, birth_year, club_id, gender)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (full_name, birth_year) DO UPDATE SET
                club_id = COALESCE(EXCLUDED.club_id, swimmers.club_id),
                gender  = COALESCE(EXCLUDED.gender,  swimmers.gender)
            RETURNING id
            """,
            (swimmer.full_name, swimmer.birth_year, home_club_db_id, swimmer.gender)
        ).fetchone()
    return row[0]


def _upsert_event(conn, competition_db_id: int, race: Race) -> int:
    race_date = _parse_dd_mm_yyyy(race.race_date)

    row = conn.execute(
        """
        INSERT INTO events
            (competition_id, loglig_event_id, event_num, name,
             distance_m, stroke, gender, category,
             is_relay, race_date, start_time)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (competition_id, loglig_event_id) DO UPDATE SET
            event_num  = EXCLUDED.event_num,
            name       = EXCLUDED.name,
            distance_m = EXCLUDED.distance_m,
            stroke     = EXCLUDED.stroke,
            gender     = EXCLUDED.gender,
            category   = EXCLUDED.category,
            is_relay   = EXCLUDED.is_relay,
            race_date  = EXCLUDED.race_date,
            start_time = EXCLUDED.start_time
        RETURNING id
        """,
        (
            competition_db_id, race.loglig_event_id, race.event_num,
            f"{race.distance}m {race.stroke} {race.gender}",
            race.distance, race.stroke.lower(), race.gender,
            race.category, race.is_relay, race_date, race.start_time,
        )
    ).fetchone()
    return row[0]


def _get_or_create_heat(conn, event_db_id: int, heat_num: int) -> int:
    row = conn.execute(
        """
        INSERT INTO heats (event_id, heat_num)
        VALUES (%s, %s)
        ON CONFLICT (event_id, heat_num) DO UPDATE SET heat_num = EXCLUDED.heat_num
        RETURNING id
        """,
        (event_db_id, heat_num)
    ).fetchone()
    return row[0]


def _upsert_individual_score(
    conn, event_db_id: int, swimmer_db_id: int,
    club_db_id: int | None, score: IndividualScore,
) -> None:
    heat_db_id     = _get_or_create_heat(conn, event_db_id, score.heat_num)
    time_ms        = time_str_to_ms(score.result_time)
    is_dsq, is_dns = is_non_time(score.result_time)
    splits_json    = _splits_to_jsonb(score.splits)

    conn.execute(
        """
        INSERT INTO results
            (heat_id, swimmer_id, club_id, lane, time_ms, dsq, dns,
             place, points, team_points, reaction_time, splits)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (heat_id, swimmer_id) DO UPDATE SET
            club_id       = EXCLUDED.club_id,
            lane          = EXCLUDED.lane,
            time_ms       = EXCLUDED.time_ms,
            dsq           = EXCLUDED.dsq,
            dns           = EXCLUDED.dns,
            place         = EXCLUDED.place,
            points        = EXCLUDED.points,
            team_points   = EXCLUDED.team_points,
            reaction_time = EXCLUDED.reaction_time,
            splits        = EXCLUDED.splits
        """,
        (heat_db_id, swimmer_db_id, club_db_id, score.lane,
         time_ms, is_dsq, is_dns,
         score.place, score.points, score.team_points,
         score.reaction_time, splits_json)
    )


def _upsert_relay_score(
    conn, event_db_id: int, club_db_id: int,
    swimmer_db_ids: list[int], score: RelayScore,
) -> None:
    heat_db_id     = _get_or_create_heat(conn, event_db_id, score.heat_num)
    time_ms        = time_str_to_ms(score.result_time)
    is_dsq, is_dns = is_non_time(score.result_time)
    splits_json    = _splits_to_jsonb(score.splits)

    conn.execute(
        """
        INSERT INTO relay_results
            (heat_id, club_id, swimmer_ids, lane, time_ms, dsq, dns,
             place, points, team_points, splits)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (heat_id, club_id, lane) DO UPDATE SET
            swimmer_ids = EXCLUDED.swimmer_ids,
            time_ms     = EXCLUDED.time_ms,
            dsq         = EXCLUDED.dsq,
            dns         = EXCLUDED.dns,
            place       = EXCLUDED.place,
            points      = EXCLUDED.points,
            team_points = EXCLUDED.team_points,
            splits      = EXCLUDED.splits
        """,
        (heat_db_id, club_db_id, swimmer_db_ids, score.lane,
         time_ms, is_dsq, is_dns,
         score.place, score.points, score.team_points,
         splits_json)
    )