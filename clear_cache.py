"""clear_cache.py — wipe all saved data for a clean run."""
import shutil, logging
from config import CSV_DIR, JSON_DIR, PDF_DIR

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("clear_cache")

for d in [CSV_DIR, JSON_DIR, PDF_DIR]:
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    log.info(f"Cleared: {d}")

log.info("Done — run pipeline.py for a fresh start")
