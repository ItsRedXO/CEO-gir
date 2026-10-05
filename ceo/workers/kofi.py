"""
Ko-fi Shop Worker — posts digital products to Ko-fi (0% platform fee).
Ko-fi has no seller API so this generates the listing content + uses
Playwright to fill the form. Human clicks Save.

Env vars: KOFI_EMAIL, KOFI_PASSWORD
"""
from __future__ import annotations
import os, time, logging
from .base import BaseWorker, WorkerResult
from ..providers.image_gen import generate_asset_image

log = logging.getLogger(__name__)

KOFI_EMAIL    = os.environ.get("KOFI_EMAIL", "")
KOFI_PASSWORD = os.environ.get("KOFI_PASSWORD", "")


class KofiWorker(BaseWorker):
    capabilities = ["kofi", "digital_products", "shop", "0pct_fees"]
    workstream_id = "kofi"

    def execute(self, task: dict) -> WorkerResult:
        start = time.monotonic()
        inp = self._parse_input(task)

        asset_type  = inp.get("asset_type", "printable")
        style       = inp.get("style", "minimal")
        price_usd   = float(inp.get("price_usd", 3.0))
        title       = inp.get("title") or f"{style.title()} {asset_type.replace('_',' ').title()} Pack"
        description = self._gen_description(asset_type, style, price_usd)
        preview_url = generate_asset_image(title, asset_type, style)

        listing = {
            "title":       title,
            "description": description,
            "price_usd":   price_usd,
            "preview_url": preview_url,
            "asset_type":  asset_type,
            "style":       style,
            "platform":    "kofi",
            "platform_fee": "0%",
            "listing_ready": True,
            "post_url":    "https://ko-fi.com/manage/shop",
        }

        posted = False
        if KOFI_EMAIL and KOFI_PASSWORD:
            posted = self._playwright_post(listing)

        duration_ms = int((time.monotonic() - start) * 1000)
        return WorkerResult(
            success=True,
            output={
                "listing":       listing,
                "preview_url":   preview_url,
                "listing_ready": True,
                "posted":        posted,
                "platform":      "kofi",
                "next_step":     "published" if posted else "add_KOFI_EMAIL_KOFI_PASSWORD_to_bashrc",
            },
            duration_ms=duration_ms,
            economic_data={
                "revenue_estimate": price_usd * 5,  # 5 sales/month estimate, 0% fee
                "spend": 0.0,
                "price_usd": price_usd,
            },
        )

    def _gen_description(self, asset_type: str, style: str, price_usd: float) -> str:
        return (
            f"**{style.title()} {asset_type.replace('_',' ').title()} Pack**\n\n"
            f"High-quality digital files ready for instant download.\n\n"
            f"✓ Commercial license included\n"
            f"✓ High resolution files\n"
            f"✓ Instant download after purchase\n"
            f"✓ Multiple formats included\n\n"
            f"Perfect for personal and commercial projects.\n\n"
            f"${price_usd:.2f} — one-time purchase, yours forever."
        )

    def _playwright_post(self, listing: dict) -> bool:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return False
        try:
            with sync_playwright() as pw:
                b    = pw.chromium.launch(headless=False, slow_mo=80)
                page = b.new_context().new_page()

                page.goto("https://ko-fi.com/account/login", timeout=30_000)
                page.wait_for_load_state("networkidle", timeout=20_000)
                page.fill('input[name="email"]', KOFI_EMAIL)
                page.fill('input[name="password"]', KOFI_PASSWORD)
                page.click('button[type="submit"]')
                page.wait_for_load_state("networkidle", timeout=20_000)

                page.goto("https://ko-fi.com/manage/shop/new-product", timeout=30_000)
                page.wait_for_load_state("networkidle", timeout=20_000)

                # Fill title
                t = page.query_selector('input[placeholder*="title" i], input[name*="title" i]')
                if t:
                    t.fill(listing["title"])

                # Fill price
                p = page.query_selector('input[placeholder*="price" i], input[name*="price" i]')
                if p:
                    p.fill(str(listing["price_usd"]))

                # Fill description
                d = page.query_selector('textarea[name*="desc" i], div[contenteditable="true"]')
                if d:
                    d.fill(listing["description"])

                print(f"\n{'='*55}")
                print("  CEO GIR — Ko-fi Auto-Post (0% fees)")
                print(f"{'='*55}")
                print(f"  Title:    {listing['title']}")
                print(f"  Price:    ${listing['price_usd']}")
                print(f"  Platform: Ko-fi (0% fee — you keep 100%)")
                print(f"\n  Browser open — upload your file then click Save.")
                print(f"{'='*55}\n")

                page.wait_for_timeout(600_000)
                b.close()
            return True
        except Exception as e:
            log.error("Ko-fi Playwright post failed: %s", e)
            return False

    def _parse_input(self, task: dict) -> dict:
        data = task.get("input_json") or {}
        if isinstance(data, str):
            import json
            try:
                return json.loads(data)
            except Exception:
                return {}
        return data
