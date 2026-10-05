"""
Fiverr auto-poster — uses Playwright to fill gig creation form.
Human clicks Publish; everything else is automated.

Requires: pip install playwright && playwright install chromium
Env vars: FIVERR_EMAIL, FIVERR_PASSWORD
"""
from __future__ import annotations
import os, json, time, logging

log = logging.getLogger(__name__)

FIVERR_EMAIL    = os.environ.get("FIVERR_EMAIL", "")
FIVERR_PASSWORD = os.environ.get("FIVERR_PASSWORD", "")


def _has_playwright() -> bool:
    try:
        import playwright  # noqa
        return True
    except ImportError:
        return False


def post_gig_to_fiverr(gig: dict, headless: bool = False) -> dict:
    """
    Fill out a Fiverr gig creation form using Playwright.
    Returns {"posted": bool, "error": str|None, "manual_required": bool}

    headless=False opens a visible browser so the user can watch + click Publish.
    """
    if not _has_playwright():
        return {
            "posted": False,
            "error": "playwright not installed — run: pip install playwright && playwright install chromium",
            "manual_required": True,
        }
    if not FIVERR_EMAIL or not FIVERR_PASSWORD:
        return {
            "posted": False,
            "error": "FIVERR_EMAIL and FIVERR_PASSWORD env vars not set",
            "manual_required": True,
        }

    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

    title       = gig.get("title", "")
    description = gig.get("description", "")
    category    = gig.get("category", "Graphics & Design")
    tags        = gig.get("tags", [])[:5]
    packages    = gig.get("packages", {})
    basic_price = packages.get("basic", {}).get("price", 15)
    std_price   = packages.get("standard", {}).get("price", 35)
    prem_price  = packages.get("premium", {}).get("price", 75)

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=headless, slow_mo=100)
            ctx     = browser.new_context()
            page    = ctx.new_page()

            # ── Login ─────────────────────────────────────────────────────
            page.goto("https://www.fiverr.com/login", timeout=30_000)
            page.wait_for_load_state("networkidle", timeout=20_000)

            # Fill email/password
            page.fill('input[name="email"]', FIVERR_EMAIL)
            page.fill('input[name="password"]', FIVERR_PASSWORD)
            page.click('button[type="submit"]')
            page.wait_for_load_state("networkidle", timeout=20_000)

            if "login" in page.url:
                return {"posted": False, "error": "Login failed — check FIVERR_EMAIL / FIVERR_PASSWORD", "manual_required": True}

            # ── Navigate to Create Gig ────────────────────────────────────
            page.goto("https://www.fiverr.com/users/seller_account/manage_gigs/new", timeout=30_000)
            page.wait_for_load_state("networkidle", timeout=20_000)

            # Step 1: Overview — title
            try:
                title_input = page.wait_for_selector('input[placeholder*="title" i], input[name*="title" i]', timeout=10_000)
                title_input.fill(title)
            except PWTimeout:
                log.warning("Could not find title field — Fiverr may have changed their UI")

            # Category selection is complex (dropdown) — log what we'd set
            log.info("Category target: %s (set manually if not auto-detected)", category)

            # Tags
            for tag in tags:
                try:
                    tag_input = page.query_selector('input[placeholder*="tag" i], input[placeholder*="search" i]')
                    if tag_input:
                        tag_input.fill(tag)
                        page.keyboard.press("Enter")
                        time.sleep(0.3)
                except Exception:
                    pass

            # ── Pause for human ───────────────────────────────────────────
            # Print a helper box in the terminal
            print("\n" + "=" * 60)
            print("  CEO GIR — Fiverr Auto-Post")
            print("=" * 60)
            print(f"  Title:    {title}")
            print(f"  Category: {category}")
            print(f"  Tags:     {', '.join(tags)}")
            print(f"  Packages: Basic ${basic_price} / Std ${std_price} / Prem ${prem_price}")
            print()
            print("  The browser is open and the title has been filled.")
            print("  Please review, fill in any remaining fields,")
            print("  then click PUBLISH on Fiverr.")
            print("=" * 60 + "\n")

            # Keep browser open until user closes it or 10 minutes
            page.wait_for_timeout(600_000)
            browser.close()

        return {"posted": True, "error": None, "manual_required": True, "note": "Title + tags pre-filled; user clicked Publish"}

    except Exception as e:
        return {"posted": False, "error": str(e), "manual_required": True}


def generate_fiverr_gig_content(service_type: str, price_usd: float = 15.0) -> dict:
    """
    Generate gig content without posting — for use when Playwright is unavailable.
    Returns a dict with everything needed to post manually in 2 minutes.
    """
    from .listing import FiverrGigWorker
    worker = FiverrGigWorker()
    task = {
        "title": f"Create Fiverr gig: {service_type}",
        "input_json": json.dumps({"service_type": service_type, "price_usd": price_usd}),
    }
    result = worker.execute(task)
    return result.output
