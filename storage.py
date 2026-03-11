import csv, logging
from pathlib import Path
from models import CompetitionDocument, IdRegistry
from config import CSV_DIR, JSON_DIR

log = logging.getLogger(__name__)

CSV_SCHEMA: dict[str, str] = {
    "competitions":      "id",
    "races":             "id",
    "clubs":             "id",
    "swimmers":          "id",
    "individual_scores": "id",
    "relay_scores":      "id",
}


def build_registry() -> IdRegistry:
    registry = IdRegistry()
    entity_map = {
        "competitions":      "competition",
        "races":             "race",
        "clubs":             "club",
        "swimmers":          "swimmer",
        "individual_scores": "individual_score",
        "relay_scores":      "relay_score",
    }
    for table, entity in entity_map.items():
        path = CSV_DIR / f"{table}.csv"
        if path.exists():
            max_id = 0
            with open(path, encoding="utf-8-sig") as f:
                for row in csv.DictReader(f):
                    try:
                        max_id = max(max_id, int(row["id"]))
                    except (ValueError, KeyError):
                        pass
            registry.seed(entity, max_id)
    return registry


def save_competition(doc: CompetitionDocument) -> None:
    _write_json(doc)
    _write_csvs(doc)
    log.info(f"  Saved: {doc.competition.name}  "
             f"({len(doc.races)} races, {len(doc.individual_scores)} ind, "
             f"{len(doc.relay_scores)} relay, {len(doc.swimmers)} swimmers)")


def already_saved(isr_id: str) -> bool:
    return (JSON_DIR / f"{isr_id}.json").exists()


def _write_json(doc: CompetitionDocument) -> None:
    path = JSON_DIR / f"{doc.competition.isr_id}.json"
    path.write_text(doc.to_json(), encoding="utf-8-sig")


def _write_csvs(doc: CompetitionDocument) -> None:
    for table_name, pk_col in CSV_SCHEMA.items():
        rows = doc.to_flat_tables().get(table_name, [])
        if rows:
            _upsert_csv(CSV_DIR / f"{table_name}.csv", rows, pk_col)


def _upsert_csv(path: Path, new_rows: list[dict], pk: str) -> None:
    if not new_rows:
        return
    existing_pks: set[str] = set()
    if path.exists():
        with open(path, encoding="utf-8-sig") as f:
            existing_pks = {row[pk] for row in csv.DictReader(f) if pk in row}

    to_write = [r for r in new_rows if str(r.get(pk, "")) not in existing_pks]
    if not to_write:
        return

    write_header = not path.exists()
    with open(path, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(to_write[0].keys()), extrasaction="ignore")
        if write_header:
            writer.writeheader()
        writer.writerows(to_write)

    log.debug(f"    CSV {path.name} +{len(to_write)} rows")
