"""
pdf_agent.py

Downloads the per-event PDF from loglig.com.

Discovery (live):
  The PDF button is a form submit:
    POST https://loglig.com:2053/LeagueTable/ExportSwimmingDisciplineResults?leagueId={loglig_id}
    body: DisciplineCompetitionId={discipline_id}

  The form requires session cookies (AWSALB) set by loglig during page load,
  so we use Playwright to click the button and capture the download.

Two entry points:
  download_event_pdf(loglig_id, discipline_id, dest) → Path | None
      Download the PDF for one specific event/discipline.

  download_competition_pdf(loglig_id, dest) → Path | None
      Download the full competition PDF (the "Res" link from the disciplines page).
"""

from playwright.sync_api import sync_playwright, Page
from pathlib import Path
from typing import Optional
import logging

from config import PDF_DIR, HEADERS

log = logging.getLogger(__name__)

LOGLIG_PORT  = "https://loglig.com:2053"
LOGLIG_BASE  = "https://loglig.com"


# ─────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────

def download_event_pdf(loglig_id: str, discipline_id: str) -> Optional[Path]:
    """
    Download the PDF for one discipline (event) within a competition.
    Clicks the #excelBtnExp submit button after loading the results page.

    POST .../ExportSwimmingDisciplineResults?leagueId={loglig_id}
    body: DisciplineCompetitionId={discipline_id}
    """
    dest = PDF_DIR / f"{loglig_id}_D{discipline_id}.pdf"
    if dest.exists():
        log.debug(f"PDF cached: {dest.name}")
        return dest

    results_url = f"{LOGLIG_PORT}/LeagueTable/AthleticsDisciplineResults/{discipline_id}"
    return _click_and_download(results_url, "#excelBtnExp", dest)


def download_competition_pdf(loglig_id: str) -> Optional[Path]:
    """
    Download the full competition results PDF.
    Clicks the 'Res' link (second <a> in last thead) on the disciplines page.

    GET .../ExportSwimmingCompetitionResults?competitionId={loglig_id}&...
    """
    dest = PDF_DIR / f"{loglig_id}_full.pdf"
    if dest.exists():
        log.debug(f"PDF cached: {dest.name}")
        return dest

    disciplines_url = f"{LOGLIG_PORT}/LeagueTable/AthleticsDisciplines/{loglig_id}"
    return _click_second_thead_link(disciplines_url, dest)


# ─────────────────────────────────────────────────────────────────
# Playwright helpers
# ─────────────────────────────────────────────────────────────────

def _click_and_download(page_url: str, button_selector: str, dest: Path) -> Optional[Path]:
    """Navigate to page_url, wait for button, click it, capture download."""
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(
            accept_downloads=True,
            extra_http_headers=HEADERS,
            viewport={"width": 1280, "height": 900},
        )
        page = ctx.new_page()
        try:
            page.goto(page_url, wait_until="domcontentloaded", timeout=25000)
            page.wait_for_selector(button_selector, timeout=8000)

            with page.expect_download(timeout=30000) as dl_info:
                page.click(button_selector)

            dl = dl_info.value
            dl.save_as(dest)
            log.info(f"Downloaded: {dest.name}")
            return dest

        except Exception as e:
            log.error(f"Download failed for {page_url}: {e}")
            return None
        finally:
            browser.close()


def _click_second_thead_link(page_url: str, dest: Path) -> Optional[Path]:
    """
    Navigate to the disciplines page, find the 2nd link in the last thead
    (the 'Res' link), click it and capture the download.
    """
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(
            accept_downloads=True,
            extra_http_headers=HEADERS,
            viewport={"width": 1280, "height": 900},
        )
        page = ctx.new_page()
        try:
            page.goto(page_url, wait_until="domcontentloaded", timeout=25000)
            page.wait_for_selector("tr.disciplines-title", timeout=10000)

            # Get the href of the second link in last thead
            pdf_href = page.evaluate("""() => {
                const dt = document.querySelector('tr.disciplines-title');
                const table = dt.closest('table');
                const theads = Array.from(table.querySelectorAll('thead'));
                const lastThead = theads[theads.length - 1];
                const links = lastThead.querySelectorAll('a[href]');
                return links[1] ? links[1].getAttribute('href') : null;
            }""")

            if not pdf_href:
                log.warning(f"No Res link found on {page_url}")
                return None

            full_url = pdf_href if pdf_href.startswith("http") else f"{LOGLIG_BASE}{pdf_href}"

            with page.expect_download(timeout=30000) as dl_info:
                page.goto(full_url)

            dl = dl_info.value
            dl.save_as(dest)
            log.info(f"Downloaded full competition PDF: {dest.name}")
            return dest

        except Exception as e:
            log.error(f"Full PDF download failed for {page_url}: {e}")
            return None
        finally:
            browser.close()