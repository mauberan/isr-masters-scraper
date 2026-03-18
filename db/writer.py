# db/writer.py
#
# Writes scraped ISR data to PostgreSQL using upserts.
#
# Design principles:
#   1. Every function accepts an open connection — the caller controls
#      the transaction boundary. Never open a new connection inside a writer.
#   2. All writes are upserts (INSERT ... ON CONFLICT) — safe to re-run.
#   3. Functions return the database id of the upserted row — needed to
#      write child rows (events need competition_id, heats need event_id, etc.)
#
# Typical usage (one transaction for an entire competition):
#
#   with get_conn() as conn:
#       comp_id    = upsert_competition(conn, comp_data)
#       event_id   = upsert_event(conn, comp_id, event_data)
#       heat_id    = upsert_heat(conn, event_id, heat_num)
#       swimmer_id = upsert_swimmer(conn, swimmer_data)
#       upsert_result(conn, heat_id, swimmer_id, result_data)

import psycopg
from utils.time_utils import time_str_to_ms, is_non_time


def upsert_competition(conn: psycopg.Connection, data: dict) -> int:
    """
    Insert or update a competition row.

    data keys: competition_id, name, location, start_date, end_date (optional)

    ON CONFLICT target: competition_id (the ISR site's own ID)
    Returns: internal database id
    """
    row = conn.execute(
        """
        INSERT INTO competitions (competition_id, name, location, start_date, end_date)
        VALUES (%(competition_id)s, %(name)s, %(location)s, %(start_date)s, %(end_date)s)
        ON CONFLICT (competition_id) DO UPDATE SET
            name       = EXCLUDED.name,
            location   = EXCLUDED.location,
            start_date = EXCLUDED.start_date,
            end_date   = EXCLUDED.end_date
        RETURNING id
        """,
        {**data, "end_date": data.get("end_date")}
    ).fetchone()
    return row[0]


def upsert_swimmer(conn: psycopg.Connection, full_name: str, birth_year: int) -> int:
    """
    Insert or update a swimmer row.

    ON CONFLICT target: (full_name, birth_year) — our natural key.
    Club is NOT stored on the swimmer — it belongs on the result row.
    Returns: internal database id
    """
    row = conn.execute(
        """
        INSERT INTO swimmers (full_name, birth_year)
        VALUES (%s, %s)
        ON CONFLICT (full_name, birth_year) DO UPDATE SET
            full_name = EXCLUDED.full_name  -- no-op, just to trigger RETURNING
        RETURNING id
        """,
        (full_name, birth_year)
    ).fetchone()
    return row[0]


def upsert_event(conn: psycopg.Connection, competition_id: int, data: dict) -> int:
    """
    Insert or update an event row.

    data keys: name, distance_m, stroke, gender
    ON CONFLICT target: (competition_id, name) — event names are unique per competition.
    Returns: internal database id
    """
    row = conn.execute(
        """
        INSERT INTO events (competition_id, name, distance_m, stroke, gender)
        VALUES (%(competition_id)s, %(name)s, %(distance_m)s, %(stroke)s, %(gender)s)
        ON CONFLICT (competition_id, name) DO UPDATE SET
            distance_m = EXCLUDED.distance_m,
            stroke     = EXCLUDED.stroke,
            gender     = EXCLUDED.gender
        RETURNING id
        """,
        {**data, "competition_id": competition_id}
    ).fetchone()
    return row[0]


def upsert_heat(conn: psycopg.Connection, event_id: int, heat_num: int) -> int:
    """
    Insert or update a heat row.

    ON CONFLICT target: (event_id, heat_num)
    Returns: internal database id
    """
    row = conn.execute(
        """
        INSERT INTO heats (event_id, heat_num)
        VALUES (%s, %s)
        ON CONFLICT (event_id, heat_num) DO UPDATE SET
            heat_num = EXCLUDED.heat_num  -- no-op
        RETURNING id
        """,
        (event_id, heat_num)
    ).fetchone()
    return row[0]


def upsert_result(
    conn: psycopg.Connection,
    heat_id: int,
    swimmer_id: int,
    lane: int,
    time_str: str | None,
    club: str | None = None,
) -> None:
    """
    Insert or update a result row.

    time_str is the raw string from the scraper (e.g. "25.43", "DSQ", "DNS").
    Conversion to milliseconds and flag detection happens here.

    ON CONFLICT target: (heat_id, swimmer_id) — a swimmer swims a heat once.
    """
    time_ms = time_str_to_ms(time_str)
    is_dsq, is_dns = is_non_time(time_str)

    conn.execute(
        """
        INSERT INTO results (heat_id, swimmer_id, club, lane, time_ms, dsq, dns)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (heat_id, swimmer_id) DO UPDATE SET
            club    = EXCLUDED.club,
            lane    = EXCLUDED.lane,
            time_ms = EXCLUDED.time_ms,
            dsq     = EXCLUDED.dsq,
            dns     = EXCLUDED.dns
        """,
        (heat_id, swimmer_id, club, lane, time_ms, is_dsq, is_dns)
    )