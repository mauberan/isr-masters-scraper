# db/queries.py
#
# Python interface to the analytics queries in db/queries/.
#
# Why a Python wrapper instead of running .sql files directly?
#   - Parameter binding is handled safely by psycopg (no injection risk)
#   - Results come back as Python dicts, ready for JSON serialization
#     or passing to a dashboard/API
#   - Easier to call from the scraper, tests, or a future API layer

from db.connection import get_conn


def get_personal_bests(full_name: str | None = None) -> list[dict]:
    """
    Returns personal best times per swimmer per event.
    Optionally filter by swimmer name.
    """
    where = "AND s.full_name = %(full_name)s" if full_name else ""

    with get_conn() as conn:
        rows = conn.execute(
            f"""
            WITH valid_results AS (
                SELECT
                    r.swimmer_id,
                    r.time_ms,
                    e.stroke,
                    e.distance_m,
                    e.gender,
                    EXTRACT(YEAR FROM c.start_date) - s.birth_year AS age
                FROM results r
                JOIN heats h        ON h.id = r.heat_id
                JOIN events e       ON e.id = h.event_id
                JOIN competitions c ON c.id = e.competition_id
                JOIN swimmers s     ON s.id = r.swimmer_id
                WHERE r.dsq = FALSE AND r.dns = FALSE AND r.time_ms IS NOT NULL
                {where}
            )
            SELECT
                s.full_name,
                s.birth_year,
                vr.gender,
                vr.distance_m,
                vr.stroke,
                MIN(vr.time_ms)          AS pb_ms,
                ROUND(MIN(vr.time_ms) / 1000.0, 2) AS pb_seconds
            FROM valid_results vr
            JOIN swimmers s ON s.id = vr.swimmer_id
            GROUP BY s.full_name, s.birth_year, vr.gender, vr.distance_m, vr.stroke
            ORDER BY s.full_name, vr.distance_m, vr.stroke
            """,
            {"full_name": full_name}
        ).fetchall()

        cols = ["full_name", "birth_year", "gender", "distance_m", "stroke", "pb_ms", "pb_seconds"]
        return [dict(zip(cols, row)) for row in rows]


def get_swimmer_progression(full_name: str, stroke: str, distance_m: int) -> list[dict]:
    """
    Returns a swimmer's times for a specific event, ordered chronologically.
    Includes delta from previous race.
    """
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT
                c.start_date,
                c.name                                          AS competition,
                r.club,
                r.time_ms,
                ROUND(r.time_ms / 1000.0, 2)                   AS time_seconds,
                r.time_ms - LAG(r.time_ms)
                    OVER (ORDER BY c.start_date)                AS delta_ms
            FROM results r
            JOIN heats h        ON h.id = r.heat_id
            JOIN events e       ON e.id = h.event_id
            JOIN competitions c ON c.id = e.competition_id
            JOIN swimmers s     ON s.id = r.swimmer_id
            WHERE s.full_name = %s
              AND e.stroke     = %s
              AND e.distance_m = %s
              AND r.dsq = FALSE AND r.dns = FALSE
            ORDER BY c.start_date
            """,
            (full_name, stroke, distance_m)
        ).fetchall()

        cols = ["date", "competition", "club", "time_ms", "time_seconds", "delta_ms"]
        return [dict(zip(cols, row)) for row in rows]


def get_event_rankings(stroke: str, distance_m: int, gender: str) -> list[dict]:
    """
    Returns ranked results for a given event across all competitions.
    One entry per swimmer (their personal best only), ranked within age groups.
    """
    with get_conn() as conn:
        rows = conn.execute(
            """
            WITH valid_results AS (
                SELECT
                    r.swimmer_id, r.club, r.time_ms,
                    c.name AS competition, c.start_date,
                    EXTRACT(YEAR FROM c.start_date) - s.birth_year AS age
                FROM results r
                JOIN heats h        ON h.id = r.heat_id
                JOIN events e       ON e.id = h.event_id
                JOIN competitions c ON c.id = e.competition_id
                JOIN swimmers s     ON s.id = r.swimmer_id
                WHERE e.stroke = %s AND e.distance_m = %s AND e.gender = %s
                  AND r.dsq = FALSE AND r.dns = FALSE AND r.time_ms IS NOT NULL
            ),
            best_per_swimmer AS (
                SELECT DISTINCT ON (swimmer_id)
                    swimmer_id, club, time_ms, competition, start_date, age,
                    CONCAT((FLOOR(age/5)*5)::INT, '-', (FLOOR(age/5)*5+4)::INT) AS age_group
                FROM valid_results
                ORDER BY swimmer_id, time_ms ASC
            )
            SELECT
                b.age_group,
                RANK() OVER (PARTITION BY b.age_group ORDER BY b.time_ms) AS rank,
                s.full_name,
                s.birth_year,
                b.club,
                ROUND(b.time_ms / 1000.0, 2) AS time_seconds,
                b.competition,
                b.start_date
            FROM best_per_swimmer b
            JOIN swimmers s ON s.id = b.swimmer_id
            ORDER BY b.age_group, rank
            """,
            (stroke, distance_m, gender)
        ).fetchall()

        cols = ["age_group", "rank", "full_name", "birth_year", "club",
                "time_seconds", "competition", "start_date"]
        return [dict(zip(cols, row)) for row in rows]


# =============================================================================
# Quick test — run directly to verify queries work:
#   python -m db.queries
# =============================================================================
if __name__ == "__main__":
    print("Personal bests (all swimmers):")
    pbs = get_personal_bests()
    print(f"  {len(pbs)} rows returned")
    if pbs:
        print(f"  Sample: {pbs[0]}")
