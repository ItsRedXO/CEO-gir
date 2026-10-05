"""
Pinterest Traffic Worker — pins Gumroad products to Pinterest for organic traffic.

If PINTEREST_EMAIL + PINTEREST_PASSWORD are set, Playwright opens the pin builder,
pre-fills title / description / destination URL, and waits for the human to select
a board and click Save.  Without credentials the worker still succeeds — it returns
the fully-formatted pin content so the human can post manually.

Env vars: PINTEREST_EMAIL, PINTEREST_PASSWORD, PINTEREST_BOARD (default "Digital Downloads")
"""
from __future__ import annotations
import os
import time
import logging
from .base import BaseWorker, WorkerResult

log = logging.getLogger(__name__)

PINTEREST_EMAIL    = os.environ.get("PINTEREST_EMAIL", "")
PINTEREST_PASSWORD = os.environ.get("PINTEREST_PASSWORD", "")
PINTEREST_BOARD    = os.environ.get("PINTEREST_BOARD", "Digital Downloads")

# ── Hashtag tables ─────────────────────────────────────────────────────────────

_TYPE_TAGS: dict[str, list[str]] = {
    "printable":  ["#printable", "#digitaldownload", "#instantdownload", "#printableart", "#wallart"],
    "planner":    ["#planner", "#digitalplanner", "#productivity", "#printableplanner", "#planning"],
    "logo":       ["#logo", "#logodesign", "#branding", "#graphicdesign", "#logomaker"],
    "svg":        ["#svg", "#svgfile", "#cricut", "#silhouette", "#svgdesign"],
    "svg_bundle": ["#svgbundle", "#svg", "#cricut", "#silhouette", "#craftfiles"],
    "template":   ["#template", "#socialmedia", "#canva", "#graphicdesign", "#contentcreator"],
    "social":     ["#socialmediatemplate", "#instagramtemplate", "#canva", "#contentcreator"],
    "thumbnail":  ["#youtube", "#thumbnail", "#youtuber", "#contentcreator", "#digitaldesign"],
    "3d_model":   ["#3dmodel", "#gameasset", "#3dart", "#indiegame", "#gamedev"],
    "game_asset": ["#gameasset", "#indiegame", "#gamedev", "#unity", "#unreal"],
}

_STYLE_TAGS: dict[str, list[str]] = {
    "boho":      ["#boho", "#bohemian", "#cottagecore", "#wildflower"],
    "minimal":   ["#minimalist", "#minimalism", "#clean"],
    "celestial": ["#celestial", "#moonphase", "#mystical"],
    "wildflower": ["#wildflower", "#botanical", "#floral"],
    "retro":     ["#retro", "#vintage", "#70s"],
    "corporate": ["#corporate", "#business", "#professional"],
    "pastel":    ["#pastel", "#pastelart", "#soft"],
    "low_poly":  ["#lowpoly", "#3dart", "#gamedesign"],
}

_TEMPLATES: dict[str, str] = {
    "printable":  "✨ Instant digital download! {name} — {style} printable art. Print at home in minutes. Includes {formats}. Perfect for home décor and gifts. 🖨️ → Gumroad link in bio ↓",
    "planner":    "📅 Stay organized with this {style} digital planner — {name}. Printable at home (Letter/A4). Everything you need to plan your days. ✨ → Gumroad link in bio ↓",
    "logo":       "💼 Professional {style} logo design — {name}. Includes {formats}. Commercial license included. Brand your business today. ✨ → Gumroad link in bio ↓",
    "svg":        "✂️ {style} SVG file — {name}. Works with Cricut, Silhouette + laser cutters. Includes {formats}. Commercial license! ✨ → Gumroad link in bio ↓",
    "svg_bundle": "✂️ {style} SVG Bundle — {name}! Multiple designs. Works with Cricut, Silhouette. Formats: {formats}. ✨ → Gumroad link in bio ↓",
    "template":   "📱 {style} social media template — {name}. Works with Canva & Photoshop. Includes {formats}. ✨ → Gumroad link in bio ↓",
}
_DEFAULT_TEMPLATE = "✨ {name} — {style} digital download. Includes {formats}. Instant access on Gumroad ↓"


def _build_pin(
    name: str,
    asset_type: str,
    style: str,
    formats: list[str],
    gumroad_url: str,
    preview_url: str,
    price: float,
) -> dict:
    fmt_str = ", ".join(formats[:3]) if formats else "digital files"
    template = _TEMPLATES.get(asset_type, _DEFAULT_TEMPLATE)
    body = template.format(
        name=name,
        style=style.title() if style else "Beautiful",
        formats=fmt_str,
    )
    type_tags  = _TYPE_TAGS.get(asset_type, ["#digitaldownload", "#digitalart"])[:4]
    style_tags = _STYLE_TAGS.get(style, [])[:3]
    tags = type_tags + style_tags + ["#gumroad", "#instantdownload", "#digitalproducts"]
    description = body + "\n\n" + " ".join(tags[:12])

    return {
        "title":       name[:100],
        "description": description[:500],
        "gumroad_url": gumroad_url or "https://gumroad.com",
        "preview_url": preview_url or "",
        "board":       PINTEREST_BOARD,
        "hashtags":    tags[:12],
    }


class PinterestWorker(BaseWorker):
    capabilities = ["pinterest", "traffic", "social_media", "digital_products", "pinning"]
    workstream_id = "pinterest"

    def _parse_input(self, task: dict) -> dict:
        data = task.get("input_json") or {}
        if isinstance(data, str):
            import json
            try:
                return json.loads(data)
            except Exception:
                return {}
        return data if isinstance(data, dict) else {}

    def execute(self, task: dict) -> WorkerResult:
        start = time.monotonic()
        inp = self._parse_input(task)

        name        = inp.get("title") or task.get("title", "Digital Product")
        asset_type  = inp.get("asset_type", "printable")
        style       = inp.get("style", "minimal")
        gumroad_url = inp.get("gumroad_url") or inp.get("url", "")
        preview_url = inp.get("preview_url", "")
        formats     = inp.get("formats") or ["PDF", "PNG"]
        price       = float(inp.get("price_usd", 4.99))

        pin = _build_pin(name, asset_type, style, formats, gumroad_url, preview_url, price)
        posted = False

        if PINTEREST_EMAIL and PINTEREST_PASSWORD:
            log.info("Pinterest: credentials set — launching Playwright")
            posted = self._playwright_post(pin)
        else:
            log.info("Pinterest: no credentials — pin content generated for manual posting")

        duration_ms = int((time.monotonic() - start) * 1000)
        return WorkerResult(
            success=True,
            output={
                "pin":              pin,
                "posted":           posted,
                "listing_ready":    posted,
                "platform":         "pinterest",
                "needs_manual_post": not posted,
                "post_url":         "https://www.pinterest.com/pin-builder/",
                "economic_data": {
                    "revenue":          0.0,
                    "spend":            0.0,
                    "traffic_estimate": 200 if posted else 0,
                    "platform":         "pinterest",
                },
            },
            duration_ms=duration_ms,
        )

    def _playwright_post(self, pin: dict) -> bool:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            log.warning("Playwright not available for Pinterest posting")
            return False
        try:
            with sync_playwright() as pw:
                b    = pw.chromium.launch(headless=False, slow_mo=80)
                ctx  = b.new_context(viewport={"width": 1280, "height": 900})
                page = ctx.new_page()

                page.goto("https://www.pinterest.com/login/", timeout=30_000)
                page.wait_for_load_state("networkidle", timeout=20_000)
                page.fill("#email", PINTEREST_EMAIL)
                page.fill("#password", PINTEREST_PASSWORD)
                page.click('button[type="submit"]')
                page.wait_for_load_state("networkidle", timeout=30_000)
                page.wait_for_timeout(2000)

                page.goto("https://www.pinterest.com/pin-builder/", timeout=30_000)
                page.wait_for_load_state("networkidle", timeout=20_000)
                page.wait_for_timeout(1500)

                if pin.get("preview_url"):
                    url_el = page.query_selector('input[placeholder*="url" i], input[data-test-id*="url" i]')
                    if url_el:
                        url_el.fill(pin["preview_url"])
                        page.wait_for_timeout(2000)

                title_el = page.query_selector(
                    'input[placeholder*="title" i], '
                    'textarea[data-test-id*="title" i], '
                    'input[data-test-id*="title" i]'
                )
                if title_el:
                    title_el.fill(pin["title"])
                    page.wait_for_timeout(500)

                desc_el = page.query_selector(
                    'textarea[placeholder*="desc" i], '
                    'div[contenteditable="true"][data-test-id*="desc" i], '
                    'textarea[data-test-id*="desc" i]'
                )
                if desc_el:
                    desc_el.fill(pin["description"])
                    page.wait_for_timeout(500)

                link_el = page.query_selector(
                    'input[placeholder*="destination" i], '
                    'input[placeholder*="link" i], '
                    'input[data-test-id*="link" i]'
                )
                if link_el:
                    link_el.fill(pin["gumroad_url"])
                    page.wait_for_timeout(500)

                print(f"\n{'='*55}")
                print("  CEO GIR — Pinterest Auto-Post")
                print(f"{'='*55}")
                print(f"  Title:   {pin['title']}")
                print(f"  Link:    {pin['gumroad_url']}")
                print(f"  Board:   {pin['board']}")
                print(f"\n  Select board '{pin['board']}' then click Save Pin.")
                print(f"{'='*55}\n")

                page.wait_for_timeout(600_000)
                b.close()
            return True
        except Exception as e:
            log.error("Pinterest Playwright post failed: %s", e)
            return False
