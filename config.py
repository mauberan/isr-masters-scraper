from pathlib import Path

BASE_URL = "https://isr.org.il"

# cYear=-1 = all years, cType=5 = swimming/masters
COMPETITIONS_URL = (
    "https://isr.org.il/competitions.asp"
    "?cYear=-1&cMonth=0&cType=5&cMode=0&isFinish="
)

DATA_DIR = Path("data")
PDF_DIR  = DATA_DIR / "pdfs"
CSV_DIR  = DATA_DIR / "csv"
JSON_DIR = DATA_DIR / "json"
LOG_DIR  = Path("logs")

for d in [PDF_DIR, CSV_DIR, JSON_DIR, LOG_DIR]:
    d.mkdir(parents=True, exist_ok=True)

CRON_HOUR, CRON_MINUTE = 6, 0

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "he-IL,he;q=0.9,en;q=0.8",
}