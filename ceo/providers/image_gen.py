"""
Pollinations.ai — free, no signup, no API key.

Image URL:  GET https://image.pollinations.ai/prompt/{prompt}?width=W&height=H&nologo=true
Text URL:   GET https://text.pollinations.ai/{prompt}

Usage:
    img_bytes = generate_image("anime character sword logo", width=1024, height=1024)
    Path("out.png").write_bytes(img_bytes)
"""
from __future__ import annotations

import os
import time
import urllib.parse
from typing import Optional

try:
    import requests as _requests
    _REQUESTS_AVAILABLE = True
except ImportError:
    _REQUESTS_AVAILABLE = False

POLLINATIONS_IMAGE_BASE = "https://image.pollinations.ai/prompt"
POLLINATIONS_TEXT_BASE  = "https://text.pollinations.ai"

_ENABLED = os.environ.get("POLLINATIONS_ENABLED", "true").lower() not in ("false", "0", "no")


def generate_image(
    prompt: str,
    width: int = 1024,
    height: int = 1024,
    model: str = "flux",      # flux | turbo | dreamshaper
    seed: Optional[int] = None,
    negative_prompt: str = "",
    nologo: bool = True,
    timeout: int = 60,
) -> Optional[bytes]:
    """
    Returns raw PNG bytes from Pollinations.ai, or None on failure.
    Does NOT require an API key.
    """
    if not _ENABLED or not _REQUESTS_AVAILABLE:
        return None

    encoded = urllib.parse.quote(prompt, safe="")
    params = {
        "width": width,
        "height": height,
        "model": model,
        "nologo": "true" if nologo else "false",
        "enhance": "false",
    }
    if seed is not None:
        params["seed"] = seed
    if negative_prompt:
        params["negative"] = urllib.parse.quote(negative_prompt, safe="")

    url = f"{POLLINATIONS_IMAGE_BASE}/{encoded}"
    try:
        resp = _requests.get(url, params=params, timeout=timeout)
        if resp.status_code == 200 and resp.content:
            return resp.content
        return None
    except Exception:
        return None


def generate_image_url(
    prompt: str,
    width: int = 1024,
    height: int = 1024,
    model: str = "flux",
    seed: Optional[int] = None,
    nologo: bool = True,
) -> str:
    """Returns the direct Pollinations URL (useful for embedding in HTML previews)."""
    encoded = urllib.parse.quote(prompt, safe="")
    params = f"?width={width}&height={height}&model={model}&nologo={'true' if nologo else 'false'}"
    if seed is not None:
        params += f"&seed={seed}"
    return f"{POLLINATIONS_IMAGE_BASE}/{encoded}{params}"


def generate_text(
    prompt: str,
    model: str = "openai",   # openai | mistral | llama | claude
    timeout: int = 30,
) -> Optional[str]:
    """
    Free text generation via Pollinations text API.
    Returns plain text string or None on failure.
    """
    if not _ENABLED or not _REQUESTS_AVAILABLE:
        return None

    encoded = urllib.parse.quote(prompt, safe="")
    url = f"{POLLINATIONS_TEXT_BASE}/{encoded}?model={model}"
    try:
        resp = _requests.get(url, timeout=timeout)
        if resp.status_code == 200:
            return resp.text.strip()
        return None
    except Exception:
        return None


def generate_asset_image(
    asset_name: str,
    asset_type: str,
    style: str = "",
    width: int = 1024,
    height: int = 1024,
    seed: Optional[int] = None,
) -> Optional[bytes]:
    """
    Convenience wrapper — builds a good prompt for digital asset images.
    """
    style_clause = f", {style} style" if style else ""
    prompt = (
        f"professional digital asset, {asset_name}, {asset_type}{style_clause}, "
        f"clean white background, high quality, commercial use, 4k, detailed"
    )
    negative = "watermark, text overlay, blurry, low quality, deformed"
    return generate_image(prompt, width=width, height=height, seed=seed, negative_prompt=negative, nologo=True)
