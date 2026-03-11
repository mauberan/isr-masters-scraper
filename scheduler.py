from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
import logging
from config import CRON_HOUR, CRON_MINUTE
from pipeline import run_pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("scheduler")


def main():
    scheduler = BlockingScheduler(timezone="Asia/Jerusalem")
    scheduler.add_job(
        run_pipeline,
        trigger=CronTrigger(hour=CRON_HOUR, minute=CRON_MINUTE),
        id="isr_scraper",
        name="ISR Swimming Results Scraper",
        misfire_grace_time=3600,    # if delayed, run within 1hr
        coalesce=True,                # don't stack missed runs
    )

    log.info(f"Scheduler started. Runs daily at {CRON_HOUR:02d}:{CRON_MINUTE:02d} (Jerusalem time)")
    log.info("Running immediately for initial fetch...")
    run_pipeline()                    # run once on startup

    scheduler.start()


if __name__ == "__main__":
    main()