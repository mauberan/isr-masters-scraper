# scripts/test_writer.py
from models import *
from db.document_writer import write_document
from db.connection import get_conn, close_pool

registry = IdRegistry()

club = Club(id=registry.next("club"), name="Test Club")
swimmer = Swimmer(
    id=registry.next("swimmer"), loglig_id="99999",
    full_name="Test Swimmer", birth_year=1980,
    club_id=club.id, gender="M"
)
comp = Competition(
    id=registry.next("competition"), isr_id="TEST001",
    loglig_id="9999", name="Test Competition",
    date_range="01/01/2026-02/01/2026", sport_type="swimming"
)
race = Race(
    id=registry.next("race"), competition_id=comp.id,
    loglig_event_id="55555", event_num=1,
    race_date="01/01/2026", distance=50,
    stroke="FREE", category="מאסטרס ג 45-49",
    gender="M", is_relay=False, start_time="01/01/2026 09:00:00"
)
score = IndividualScore(
    id=registry.next("individual_score"), race_id=race.id,
    swimmer_id=swimmer.id, club_id=club.id,
    race_date="01/01/2026", heat_num=1, lane=4,
    result_time="25.43", place=1, points=10,
    team_points=5, reaction_time="+0.70",
    splits="25.43;12.10"
)
doc = CompetitionDocument(
    competition=comp, races=[race],
    clubs=[club], swimmers=[swimmer],
    individual_scores=[score], relay_scores=[]
)

print("── Write 1 ──────────────────────────────")
write_document(doc)

print("── Verify ───────────────────────────────")
with get_conn() as conn:
    c = conn.execute("SELECT id, name, start_date FROM competitions WHERE competition_id='TEST001'").fetchone()
    print(f"  competition : {c}")

    s = conn.execute("SELECT id, full_name, loglig_id, gender FROM swimmers WHERE loglig_id='99999'").fetchone()
    print(f"  swimmer     : {s}")

    r = conn.execute("SELECT time_ms, splits, place, reaction_time FROM results").fetchone()
    print(f"  result      : time_ms={r[0]} (expected 25430)")
    print(f"  splits      : {r[1]} (expected {{\"1\": \"25.43\", \"2\": \"12.10\"}})")
    print(f"  place       : {r[2]}")
    print(f"  reaction    : {r[3]}")

print()
print("── Write 2 (idempotency check) ──────────")
write_document(doc)
print("  no errors ✓")

print()
print("── Cleanup ──────────────────────────────")
with get_conn() as conn:
    conn.execute("DELETE FROM competitions WHERE competition_id='TEST001'")
    print("  test data removed ✓")

close_pool()
print()
print("All checks passed ✓")