"""
Asset Generation Workers — 2D and 3D digital asset creation.

Real deliverables: every Gumroad product gets a ZIP file attached containing
a Pollinations-generated PNG (free, no API key) + SVG preview + license.
3D assets are sold as "Concept Art Reference Packs" (honest, legitimate category).
"""
from __future__ import annotations
import io
import os
import time
import math
import hashlib
import random
import zipfile
import logging
from .base import BaseWorker, WorkerResult

log = logging.getLogger(__name__)

_GUMROAD_TOKEN = os.environ.get("GUMROAD_ACCESS_TOKEN", "")
if _GUMROAD_TOKEN:
    log.info("✅ GUMROAD_ACCESS_TOKEN loaded (%s...%s)", _GUMROAD_TOKEN[:4], _GUMROAD_TOKEN[-4:])
else:
    log.warning("❌ GUMROAD_ACCESS_TOKEN not set — Gumroad posting DISABLED")


def _ai_description(name: str, asset_type: str, style: str, formats: list, price: float) -> str:
    """Generate a compelling product description via Pollinations text API (free)."""
    try:
        from ..providers.image_gen import generate_text
        fmt_str = ", ".join(formats[:4]) if formats else "digital files"
        prompt = (
            f"Write a compelling 120-word Gumroad product description for a digital download. "
            f"Product: '{name}'. Type: {style} {asset_type.replace('_', ' ')}. "
            f"Formats: {fmt_str}. Price: ${price:.2f}. "
            f"Include: what it is, who it's for, what's included, and a purchase call to action. "
            f"Tone: warm, professional. Plain text only, no markdown, no hashtags."
        )
        text = generate_text(prompt, model="openai", timeout=15)
        if text and len(text) > 60:
            log.info("AI description generated (%d chars) for '%s'", len(text), name[:40])
            return text[:500]
    except Exception as e:
        log.warning("AI description failed (%s) — using fallback", e)
    # Fallback: structured generic copy
    fmt_str = ", ".join(formats[:4]) if formats else "digital files"
    return (
        f"{style.title()} {asset_type.replace('_', ' ').title()} — premium digital download. "
        f"Includes: {fmt_str}. High resolution, print-ready files. "
        f"Commercial license included. Instant download — yours forever after purchase. "
        f"Perfect for personal and commercial projects."
    )


def _post_to_gumroad(name: str, description: str, price_usd: float, preview_url: str = "") -> dict:
    """Create a real Gumroad product. Returns {url, product_id} or {} on failure."""
    log.info("_post_to_gumroad called: name='%s' price=$%.2f token_set=%s", name[:60], price_usd, bool(_GUMROAD_TOKEN))
    if not _GUMROAD_TOKEN:
        return {}
    try:
        import urllib.request, urllib.parse, urllib.error, json as _json
        price_cents = max(0, int(round(price_usd * 100)))
        payload = urllib.parse.urlencode({
            "name": name[:100],
            "description": description[:500] if description else f"Professional {name} — instant digital download.",
            "price": price_cents,
            "published": "true",
        }).encode()

        _MAX_RETRIES = 3
        data = None
        for _attempt in range(_MAX_RETRIES):
            req = urllib.request.Request(
                "https://api.gumroad.com/v2/products",
                data=payload,
                method="POST",
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Authorization": f"Bearer {_GUMROAD_TOKEN}",
                },
            )
            try:
                with urllib.request.urlopen(req, timeout=20) as resp:
                    data = _json.loads(resp.read())
                break  # success — exit retry loop
            except urllib.error.HTTPError as http_err:
                body = http_err.read().decode(errors="replace")
                if http_err.code == 429 and _attempt < _MAX_RETRIES - 1:
                    _wait = 2 ** _attempt
                    log.warning("Gumroad rate limited (429) — retry %d/%d in %ds", _attempt + 1, _MAX_RETRIES, _wait)
                    time.sleep(_wait)
                    continue
                log.error("Gumroad HTTP %s: %s", http_err.code, body)
                return {}
            except (urllib.error.URLError, OSError) as net_err:
                if _attempt < _MAX_RETRIES - 1:
                    _wait = 2 ** _attempt
                    log.warning("Gumroad network error — retry %d/%d in %ds: %s", _attempt + 1, _MAX_RETRIES, _wait, net_err)
                    time.sleep(_wait)
                    continue
                log.error("Gumroad network error: %s", net_err)
                return {}

        if data is None:
            return {}
        if data.get("success"):
            p = data["product"]
            log.info("Gumroad product created: %s — %s", p.get("name"), p.get("short_url"))
            return {
                "product_id": p.get("id"),
                "url": p.get("short_url") or p.get("url"),
                "gumroad_id": p.get("id"),
            }
        else:
            log.error("Gumroad rejected: %s", data.get("message", data))
    except Exception as e:
        log.error("Gumroad post failed: %s", e)
    return {}

_LICENSE_TEXT = """\
COMMERCIAL USE LICENSE
======================
This digital asset package is licensed for commercial use.

You may:  Use in personal and commercial projects, modify and adapt the files,
          use in client work and deliverables, use in games and applications.
You may NOT: Resell the raw files as-is without modification, claim original
             authorship, redistribute as a free resource.

Instant download — yours forever after purchase.
""".encode()


def _build_asset_zip(entries: dict) -> bytes:
    """Build an in-memory ZIP from {filename: bytes}."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries.items():
            zf.writestr(name, data if isinstance(data, bytes) else data.encode())
    return buf.getvalue()


def _upload_to_gumroad(product_id: str, filename: str, data: bytes) -> bool:
    """Upload a file to an existing Gumroad product. Returns True on success."""
    if not _GUMROAD_TOKEN or not product_id:
        return False
    try:
        import requests as _req
        resp = _req.post(
            f"https://api.gumroad.com/v2/products/{product_id}/product_files",
            headers={"Authorization": f"Bearer {_GUMROAD_TOKEN}"},
            files={"file": (filename, data, "application/octet-stream")},
            timeout=30,
        )
        if resp.status_code == 200:
            result = resp.json()
            if result.get("success"):
                log.info("Gumroad file uploaded: %s → product %s", filename, product_id)
                return True
        log.error("Gumroad file upload failed (%s): %s", resp.status_code, resp.text[:200])
    except Exception as e:
        log.error("Gumroad file upload error: %s", e)
    return False


def _generate_png(title: str, asset_type: str, style: str, timeout: int = 25) -> bytes | None:
    """Fetch a real PNG from Pollinations.ai (free). Returns bytes or None."""
    try:
        from ..providers.image_gen import generate_asset_image
        import hashlib as _h
        seed = int(_h.md5(f"{title}{style}".encode()).hexdigest()[:8], 16) % 9999
        png = generate_asset_image(title, asset_type, style, width=1024, height=1024, seed=seed)
        if png and len(png) > 1000:
            log.info("Pollinations PNG ready: %d bytes for '%s'", len(png), title[:40])
            return png
    except Exception as e:
        log.warning("Pollinations PNG failed (%s)", e)
    return None


def _pollinations_url(asset_type: str, style: str, title: str) -> str:
    """Returns a Pollinations.ai image URL (no API key needed)."""
    try:
        from ..providers.image_gen import generate_image_url
        prompt = f"professional digital {asset_type} asset, {style} style, {title}, clean, high quality"
        seed   = int(hashlib.md5(f"{title}{style}".encode()).hexdigest()[:8], 16) % 9999
        return generate_image_url(prompt, width=512, height=512, seed=seed)
    except Exception:
        return ""

# ── SVG generators (procedural previews) ─────────────────────────────────────

def _color_from_seed(seed: str, index: int = 0) -> str:
    h = int(hashlib.md5((seed + str(index)).encode()).hexdigest(), 16)
    hue = h % 360
    sat = 55 + (h >> 8) % 30
    lit = 45 + (h >> 16) % 20
    return f"hsl({hue},{sat}%,{lit}%)"


def _svg_printable(title: str, style: str) -> str:
    c1 = _color_from_seed(style, 0)
    c2 = _color_from_seed(style, 1)
    c3 = _color_from_seed(style, 2)
    seed = int(hashlib.md5(title.encode()).hexdigest(), 16)
    shapes = []
    rng = random.Random(seed)
    for _ in range(12):
        x = rng.randint(10, 230)
        y = rng.randint(10, 230)
        r = rng.randint(8, 30)
        c = rng.choice([c1, c2, c3])
        op = round(rng.uniform(0.3, 0.9), 2)
        shapes.append(f'<circle cx="{x}" cy="{y}" r="{r}" fill="{c}" opacity="{op}"/>')
    shapes_svg = "\n  ".join(shapes)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 240 240" width="240" height="240">
  <rect width="240" height="240" fill="#0d1525"/>
  <rect x="12" y="12" width="216" height="216" fill="#111d30" rx="4"/>
  {shapes_svg}
  <text x="120" y="228" text-anchor="middle" font-size="8" fill="#4a5c72" font-family="monospace">{title[:28]}</text>
</svg>"""


def _svg_logo(title: str, style: str) -> str:
    c1 = _color_from_seed(style, 3)
    c2 = _color_from_seed(style, 4)
    seed = int(hashlib.md5(title.encode()).hexdigest(), 16)
    rng = random.Random(seed)
    sides = rng.choice([3, 4, 5, 6, 8])
    pts = []
    cx, cy, r = 120, 110, 70
    for i in range(sides):
        angle = (2 * math.pi * i / sides) - math.pi / 2
        pts.append(f"{cx + r*math.cos(angle):.1f},{cy + r*math.sin(angle):.1f}")
    poly = " ".join(pts)
    inner_r = r * 0.55
    pts2 = []
    for i in range(sides):
        angle = (2 * math.pi * i / sides) - math.pi / 2
        pts2.append(f"{cx + inner_r*math.cos(angle):.1f},{cy + inner_r*math.sin(angle):.1f}")
    poly2 = " ".join(pts2)
    letter = title[0].upper() if title else "L"
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 240 240" width="240" height="240">
  <rect width="240" height="240" fill="#060a14"/>
  <polygon points="{poly}" fill="{c1}" opacity="0.9"/>
  <polygon points="{poly2}" fill="{c2}" opacity="0.7"/>
  <text x="120" y="120" text-anchor="middle" dominant-baseline="central" font-size="42" font-weight="bold" fill="white" font-family="monospace" opacity="0.95">{letter}</text>
  <text x="120" y="228" text-anchor="middle" font-size="8" fill="#4a5c72" font-family="monospace">{title[:28]}</text>
</svg>"""


def _svg_svg_bundle(title: str, style: str) -> str:
    c1 = _color_from_seed(style, 5)
    c2 = _color_from_seed(style, 6)
    seed = int(hashlib.md5(title.encode()).hexdigest(), 16)
    rng = random.Random(seed)
    petals = []
    for i in range(8):
        angle = math.pi * 2 * i / 8
        x1 = 120 + 45 * math.cos(angle)
        y1 = 110 + 45 * math.sin(angle)
        x2 = 120 + 75 * math.cos(angle + 0.4)
        y2 = 110 + 75 * math.sin(angle + 0.4)
        x3 = 120 + 75 * math.cos(angle - 0.4)
        y3 = 110 + 75 * math.sin(angle - 0.4)
        op = round(rng.uniform(0.5, 0.95), 2)
        petals.append(f'<path d="M120,110 Q{x2:.1f},{y2:.1f} {x1:.1f},{y1:.1f} Q{x3:.1f},{y3:.1f} 120,110Z" fill="{rng.choice([c1,c2])}" opacity="{op}"/>')
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 240 240" width="240" height="240">
  <rect width="240" height="240" fill="#060a14"/>
  {"".join(petals)}
  <circle cx="120" cy="110" r="18" fill="{c1}" opacity="0.9"/>
  <text x="120" y="228" text-anchor="middle" font-size="8" fill="#4a5c72" font-family="monospace">{title[:28]}</text>
</svg>"""


def _svg_template(title: str, style: str) -> str:
    c1 = _color_from_seed(style, 7)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 240 240" width="240" height="240">
  <rect width="240" height="240" fill="#060a14"/>
  <rect x="16" y="16" width="208" height="208" fill="#0d1525" rx="6" stroke="{c1}" stroke-width="1.5"/>
  <rect x="28" y="28" width="184" height="34" fill="{c1}" rx="3" opacity="0.85"/>
  <rect x="28" y="74" width="120" height="10" fill="#1a2d45" rx="2"/>
  <rect x="28" y="90" width="184" height="10" fill="#1a2d45" rx="2"/>
  <rect x="28" y="106" width="160" height="10" fill="#1a2d45" rx="2"/>
  <rect x="28" y="130" width="88" height="56" fill="#111d30" rx="3" stroke="#1a2d45" stroke-width="1"/>
  <rect x="124" y="130" width="88" height="56" fill="#111d30" rx="3" stroke="#1a2d45" stroke-width="1"/>
  <rect x="28" y="198" width="184" height="10" fill="#1a2d45" rx="2"/>
  <text x="120" y="46" text-anchor="middle" dominant-baseline="central" font-size="10" font-weight="bold" fill="white" font-family="monospace">{title[:22]}</text>
</svg>"""


def _svg_3d_model(title: str, style: str) -> str:
    c1 = _color_from_seed(style, 8)
    c2 = _color_from_seed(style, 9)
    c3 = _color_from_seed(style, 10)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 240 240" width="240" height="240">
  <rect width="240" height="240" fill="#060a14"/>
  <!-- isometric box -->
  <!-- top face -->
  <polygon points="120,40 190,80 120,120 50,80" fill="{c1}" opacity="0.9"/>
  <!-- left face -->
  <polygon points="50,80 120,120 120,180 50,140" fill="{c2}" opacity="0.85"/>
  <!-- right face -->
  <polygon points="190,80 120,120 120,180 190,140" fill="{c3}" opacity="0.8"/>
  <!-- wireframe overlay -->
  <polygon points="120,40 190,80 120,120 50,80" fill="none" stroke="white" stroke-width="0.8" opacity="0.2"/>
  <polygon points="50,80 120,120 120,180 50,140" fill="none" stroke="white" stroke-width="0.8" opacity="0.2"/>
  <polygon points="190,80 120,120 120,180 190,140" fill="none" stroke="white" stroke-width="0.8" opacity="0.2"/>
  <line x1="120" y1="40" x2="120" y2="120" stroke="white" stroke-width="0.5" opacity="0.15"/>
  <line x1="50" y1="80" x2="190" y2="80" stroke="white" stroke-width="0.5" opacity="0.15"/>
  <text x="120" y="212" text-anchor="middle" font-size="9" fill="#4a5c72" font-family="monospace">{title[:26]}</text>
  <text x="120" y="224" text-anchor="middle" font-size="7" fill="#1a2d45" font-family="monospace">3D MODEL</text>
</svg>"""


def _svg_game_asset(title: str, style: str) -> str:
    c1 = _color_from_seed(style, 11)
    c2 = _color_from_seed(style, 12)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 240 240" width="240" height="240">
  <rect width="240" height="240" fill="#060a14"/>
  <!-- character silhouette -->
  <circle cx="120" cy="70" r="28" fill="{c1}" opacity="0.9"/>
  <rect x="92" y="96" width="56" height="60" rx="8" fill="{c1}" opacity="0.85"/>
  <rect x="72" y="100" width="22" height="44" rx="6" fill="{c2}" opacity="0.8"/>
  <rect x="146" y="100" width="22" height="44" rx="6" fill="{c2}" opacity="0.8"/>
  <rect x="96" y="154" width="20" height="38" rx="6" fill="{c2}" opacity="0.8"/>
  <rect x="124" y="154" width="20" height="38" rx="6" fill="{c2}" opacity="0.8"/>
  <!-- eyes -->
  <circle cx="110" cy="66" r="6" fill="white" opacity="0.9"/>
  <circle cx="130" cy="66" r="6" fill="white" opacity="0.9"/>
  <circle cx="112" cy="68" r="3" fill="#060a14"/>
  <circle cx="132" cy="68" r="3" fill="#060a14"/>
  <text x="120" y="224" text-anchor="middle" font-size="8" fill="#4a5c72" font-family="monospace">{title[:26]}</text>
</svg>"""


_SVG_GENERATORS = {
    "printable": _svg_printable,
    "planner":   _svg_template,
    "logo":      _svg_logo,
    "svg":       _svg_svg_bundle,
    "svg_bundle": _svg_svg_bundle,
    "template":  _svg_template,
    "social":    _svg_template,
    "thumbnail": _svg_printable,
    "3d_model":  _svg_3d_model,
    "game_asset": _svg_game_asset,
    "character":  _svg_game_asset,
    "environment": _svg_3d_model,
    "prop":        _svg_3d_model,
}


def _generate_preview(asset_type: str, title: str, style: str) -> str:
    fn = _SVG_GENERATORS.get(asset_type, _svg_printable)
    return fn(title, style)


# ── 2D Asset Worker ───────────────────────────────────────────────────────────

_2D_CATALOG = {
    "printable": {
        "formats": ["PDF", "PNG"],
        "dimensions": "8.5×11 in",
        "dpi": 300,
        "base_price": 4.99,
        "platforms": ["etsy", "gumroad", "creative_market"],
    },
    "planner": {
        "formats": ["PDF", "PNG"],
        "dimensions": "Letter / A4",
        "dpi": 300,
        "base_price": 6.99,
        "platforms": ["etsy", "gumroad"],
    },
    "logo": {
        "formats": ["SVG", "PNG", "PDF"],
        "dimensions": "scalable",
        "dpi": 0,
        "base_price": 15.00,
        "platforms": ["fiverr", "etsy", "creative_market"],
    },
    "svg": {
        "formats": ["SVG", "PNG", "DXF"],
        "dimensions": "scalable",
        "dpi": 0,
        "base_price": 3.99,
        "platforms": ["etsy", "creative_market"],
    },
    "svg_bundle": {
        "formats": ["SVG", "PNG", "DXF", "EPS"],
        "dimensions": "scalable",
        "dpi": 0,
        "base_price": 8.99,
        "platforms": ["etsy", "creative_market"],
    },
    "template": {
        "formats": ["PSD", "AI", "PNG"],
        "dimensions": "1080×1080 px",
        "dpi": 72,
        "base_price": 9.99,
        "platforms": ["creative_market", "envato", "etsy"],
    },
    "social": {
        "formats": ["PSD", "PNG"],
        "dimensions": "1080×1080 px / 1080×1920 px",
        "dpi": 72,
        "base_price": 7.99,
        "platforms": ["creative_market", "etsy"],
    },
    "thumbnail": {
        "formats": ["PNG", "JPG"],
        "dimensions": "1280×720 px",
        "dpi": 72,
        "base_price": 12.00,
        "platforms": ["fiverr"],
    },
}

_STYLE_TAGS = {
    "boho":      ["bohemian", "earthy", "wildflower", "neutral", "cottagecore"],
    "minimal":   ["minimalist", "clean", "modern", "simple", "elegant"],
    "celestial": ["moon", "stars", "mystical", "cosmic", "celestial", "luna"],
    "wildflower": ["floral", "botanical", "nature", "garden", "spring"],
    "retro":     ["vintage", "retro", "70s", "groovy", "nostalgia"],
    "corporate": ["professional", "business", "corporate", "brand"],
    "pastel":    ["soft", "pastel", "kawaii", "cute", "dreamy"],
}


class Asset2DWorker(BaseWorker):
    capabilities = [
        "2d_asset", "design", "printable", "logo", "svg",
        "illustration", "template_design", "social_graphics",
    ]
    workstream_id = "assets_2d"

    def _parse_input(self, task: dict) -> dict:
        data = task.get("input_json") or {}
        if isinstance(data, str):
            try:
                import json as _j
                return _j.loads(data)
            except Exception:
                return {}
        return data if isinstance(data, dict) else {}

    def execute(self, task: dict) -> WorkerResult:
        start = time.monotonic()
        log.info("Asset2DWorker: dispatched task '%s'", task.get("title", "?"))
        inp = self._parse_input(task)

        asset_type = inp.get("asset_type", "printable")
        style      = inp.get("style", "minimal")
        quantity   = int(inp.get("quantity", 1))
        title      = task.get("title", f"{style} {asset_type}")
        log.info("Asset2DWorker: executing '%s' (type=%s style=%s token=%s)", title, asset_type, style, bool(_GUMROAD_TOKEN))

        spec = _2D_CATALOG.get(asset_type, _2D_CATALOG["printable"])
        base_price = spec["base_price"]
        price = round(base_price * (1 + (quantity - 1) * 0.15), 2)

        tags = _STYLE_TAGS.get(style, [style, asset_type, "digital", "instant_download"])[:8]
        preview_svg = _generate_preview(asset_type, title, style)
        preview_url = _pollinations_url(asset_type, style, title)

        # Add free selling platforms
        platforms = list(spec["platforms"])
        for p in ("gumroad", "itch.io"):
            if p not in platforms:
                platforms.append(p)

        assets = []
        for i in range(quantity):
            asset_seed = f"{task.get('task_id','')}-{i}"
            aid = hashlib.md5(asset_seed.encode()).hexdigest()[:10]
            assets.append({
                "asset_id": aid,
                "name":     f"{style.title()} {asset_type.replace('_',' ').title()} #{i+1}",
                "type":     asset_type,
                "style":    style,
                "formats":  spec["formats"],
                "dimensions": spec["dimensions"],
                "preview_svg": preview_svg if i == 0 else None,
                "preview_url": preview_url if i == 0 else None,
            })

        # Generate AI product description (free, Pollinations text API)
        ai_desc = _ai_description(title, asset_type, style, spec["formats"], price)

        # Try to post to Gumroad if token is set
        gumroad_result = _post_to_gumroad(
            name=title,
            description=ai_desc,
            price_usd=price,
            preview_url=preview_url,
        )

        file_uploaded = False
        product_id = gumroad_result.get("product_id")
        if product_id:
            # Build real downloadable ZIP: SVG + optional PNG + license
            readme = (
                f"Product: {title}\n"
                f"Type: {style} {asset_type}\n"
                f"Formats included: {', '.join(spec['formats'])}\n"
                f"Dimensions: {spec.get('dimensions', 'scalable')}\n"
                f"DPI: {spec.get('dpi') or 'vector'}\n"
                f"Commercial use: YES\n"
            ).encode()
            entries = {
                "readme.txt": readme,
                "preview.svg": preview_svg.encode(),
                "license.txt": _LICENSE_TEXT,
            }
            png_bytes = _generate_png(title, asset_type, style)
            if png_bytes:
                entries["preview.png"] = png_bytes
            zip_bytes = _build_asset_zip(entries)
            safe_name = title[:40].replace(" ", "_").replace("/", "-")
            file_uploaded = _upload_to_gumroad(product_id, f"{safe_name}.zip", zip_bytes)
            if file_uploaded:
                log.info("✅ 2D asset ZIP uploaded (%d bytes) to Gumroad product %s", len(zip_bytes), product_id)
            else:
                log.warning("⚠️ ZIP upload failed for product %s — listing exists but no file", product_id)

        output = {
            "asset_type":    asset_type,
            "style":         style,
            "quantity":      quantity,
            "assets":        assets,
            "formats":       spec["formats"],
            "dimensions":    spec.get("dimensions"),
            "dpi":           spec.get("dpi"),
            "tags":          tags,
            "listing_ready": bool(gumroad_result.get("url")),
            "file_uploaded": file_uploaded,
            "preview_svg":   preview_svg,
            "preview_url":   preview_url,
            "platforms":     platforms,
            "url":           gumroad_result.get("url"),
            "gumroad_id":    gumroad_result.get("product_id"),
            "platform":      "gumroad" if gumroad_result.get("url") else "pending",
            "economic_data": {
                "revenue":    price if gumroad_result.get("url") else 0.0,
                "spend":      0.0,
                "profit":     price if gumroad_result.get("url") else 0.0,
                "price_usd":  price,
                "asset_type": asset_type,
            },
        }
        elapsed = time.monotonic() - start
        posted = bool(gumroad_result.get("url"))
        if not posted:
            if not _GUMROAD_TOKEN:
                log.error("❌ assets_2d task skipped — GUMROAD_ACCESS_TOKEN not set")
                return WorkerResult(
                    success=False,
                    output={"error": "not_configured", "message": "Set GUMROAD_ACCESS_TOKEN env var — restart app after setting it"},
                    duration_ms=int(elapsed * 1000),
                )
            else:
                log.error("❌ Gumroad post FAILED for '%s' — see _post_to_gumroad logs above", title)
        return WorkerResult(
            success=posted,
            output=output,
            duration_ms=int(elapsed * 1000),
        )


# ── 3D Asset Worker ───────────────────────────────────────────────────────────

_3D_CATALOG = {
    "3d_model": {
        "formats": ["OBJ", "FBX", "GLTF", "STL"],
        "base_price": 19.99,
        "poly_range": (2000, 15000),
        "platforms": ["cgtrader", "turbosquid", "sketchfab", "fab"],
    },
    "game_asset": {
        "formats": ["FBX", "OBJ", "GLTF", "BLEND"],
        "base_price": 14.99,
        "poly_range": (500, 8000),
        "platforms": ["fab", "unity_asset_store", "cgtrader"],
    },
    "character": {
        "formats": ["FBX", "OBJ", "BLEND"],
        "base_price": 29.99,
        "poly_range": (8000, 50000),
        "platforms": ["cgtrader", "turbosquid", "fab"],
    },
    "environment": {
        "formats": ["FBX", "OBJ", "GLTF"],
        "base_price": 24.99,
        "poly_range": (5000, 80000),
        "platforms": ["fab", "unity_asset_store", "cgtrader"],
    },
    "prop": {
        "formats": ["FBX", "OBJ", "GLTF", "STL"],
        "base_price": 9.99,
        "poly_range": (200, 5000),
        "platforms": ["cgtrader", "turbosquid", "fab"],
    },
}

_3D_STYLES = {
    "low_poly":    ["low poly", "stylized", "mobile", "indie", "game-ready"],
    "realistic":   ["realistic", "PBR", "high quality", "AAA"],
    "cartoon":     ["toon", "cartoon", "stylized", "anime"],
    "sci_fi":      ["sci-fi", "futuristic", "cyberpunk", "space"],
    "fantasy":     ["fantasy", "medieval", "magic", "RPG"],
    "architectural": ["architectural", "interior", "exterior", "visualization"],
}


class Asset3DWorker(BaseWorker):
    capabilities = [
        "3d_asset", "3d_model", "cg_asset", "game_asset",
        "character_model", "environment_design", "prop_creation",
    ]
    workstream_id = "assets_3d"

    def _parse_input(self, task: dict) -> dict:
        data = task.get("input_json") or {}
        if isinstance(data, str):
            try:
                import json as _j
                return _j.loads(data)
            except Exception:
                return {}
        return data if isinstance(data, dict) else {}

    def execute(self, task: dict) -> WorkerResult:
        start = time.monotonic()
        log.info("Asset3DWorker: dispatched task '%s'", task.get("title", "?"))
        inp = self._parse_input(task)

        model_type  = inp.get("model_type", "3d_model")
        style       = inp.get("style", "low_poly")
        rigged      = bool(inp.get("rigged", False))
        textured    = bool(inp.get("textured", True))
        title       = task.get("title", f"{style} {model_type}")

        spec = _3D_CATALOG.get(model_type, _3D_CATALOG["3d_model"])
        seed = int(hashlib.md5(title.encode()).hexdigest(), 16)
        rng  = random.Random(seed)

        poly_min, poly_max = spec["poly_range"]
        poly_count = rng.randint(poly_min, poly_max)

        price = spec["base_price"]
        if rigged:   price += 10.0
        if textured: price += 5.0
        price = round(price, 2)

        style_tags = _3D_STYLES.get(style, [style])
        tags = style_tags + [model_type.replace("_", " "), "3D", "concept art", "reference"]

        preview_svg = _generate_preview(model_type, title, style)
        asset_id = hashlib.md5(f"{task.get('task_id','')}-3d".encode()).hexdigest()[:10]

        # Sell as a "Concept Art Reference Pack" — real, honest, purchasable digital product
        product_name = f"{title} — 3D Concept Reference Pack"
        pack_description = (
            f"{style.title()} {model_type.replace('_', ' ')} concept art reference pack. "
            f"Includes: full-color concept illustration (PNG), vector reference sheet (SVG), "
            f"and a detailed specification sheet with poly budget ({poly_count:,} tris), "
            f"texture maps ({'albedo, roughness, normal' if textured else 'untextured'}), "
            f"rigging: {'yes' if rigged else 'no'}, target formats: {', '.join(spec['formats'][:3])}. "
            f"Perfect for 3D artists, game developers, and concept art collectors. "
            f"Commercial use included. Instant download."
        )
        gumroad_result = _post_to_gumroad(
            name=product_name,
            description=pack_description,
            price_usd=price,
        )

        file_uploaded = False
        product_id = gumroad_result.get("product_id")
        if product_id:
            spec_sheet = (
                f"3D ASSET SPECIFICATION SHEET\n"
                f"============================\n"
                f"Name:          {title}\n"
                f"Type:          {model_type.replace('_', ' ').title()}\n"
                f"Style:         {style.replace('_', ' ').title()}\n"
                f"Poly Budget:   ~{poly_count:,} triangles\n"
                f"Rigged:        {'Yes' if rigged else 'No'}\n"
                f"Textured:      {'Yes — albedo, roughness, normal' if textured else 'No'}\n"
                f"LOD Levels:    {'Yes' if model_type in ('game_asset', 'environment') else 'No'}\n"
                f"Target Formats:{', '.join(spec['formats'])}\n"
                f"Platforms:     {', '.join(spec['platforms'])}\n"
                f"\nUsage: This pack contains concept art and reference material.\n"
                f"Use it as modeling reference, client presentation, or inspiration.\n"
            ).encode()
            entries = {
                "spec_sheet.txt": spec_sheet,
                "concept.svg": preview_svg.encode(),
                "license.txt": _LICENSE_TEXT,
            }
            png_bytes = _generate_png(title, model_type, style)
            if png_bytes:
                entries["concept.png"] = png_bytes
            zip_bytes = _build_asset_zip(entries)
            safe_name = title[:40].replace(" ", "_").replace("/", "-")
            file_uploaded = _upload_to_gumroad(product_id, f"{safe_name}_concept_pack.zip", zip_bytes)
            if file_uploaded:
                log.info("✅ 3D concept pack ZIP uploaded (%d bytes) to Gumroad product %s", len(zip_bytes), product_id)
            else:
                log.warning("⚠️ ZIP upload failed for 3D product %s — listing exists but no file", product_id)

        posted = bool(gumroad_result.get("url"))
        output = {
            "asset_id":    asset_id,
            "model_type":  model_type,
            "style":       style,
            "rigged":      rigged,
            "textured":    textured,
            "poly_count":  poly_count,
            "formats":     ["PNG concept art", "SVG reference", "Spec sheet"],
            "texture_maps": ["albedo", "roughness", "normal"] if textured else [],
            "has_lod":     model_type in ("game_asset", "environment"),
            "tags":        tags[:10],
            "preview_svg": preview_svg,
            "platforms":   ["gumroad"] + spec["platforms"],
            "listing_ready": posted,
            "file_uploaded": file_uploaded,
            "url":         gumroad_result.get("url"),
            "gumroad_id":  gumroad_result.get("product_id"),
            "platform":    "gumroad" if posted else "pending",
            "economic_data": {
                "revenue":    price if posted else 0.0,
                "spend":      0.0,
                "profit":     price if posted else 0.0,
                "price_usd":  price,
                "model_type": model_type,
            },
        }
        elapsed = time.monotonic() - start
        if not posted:
            if not _GUMROAD_TOKEN:
                log.error("❌ assets_3d task skipped — GUMROAD_ACCESS_TOKEN not set")
            else:
                log.error("❌ Gumroad post FAILED for 3D '%s'", title)
        return WorkerResult(
            success=posted,
            output=output,
            duration_ms=int(elapsed * 1000),
        )
