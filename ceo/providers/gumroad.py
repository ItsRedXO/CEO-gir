"""
Gumroad provider — free digital product store.

Commission: 10% per sale (no listing fee, no monthly fee).
API docs: https://app.gumroad.com/api

Requires env var: GUMROAD_ACCESS_TOKEN
Get it: Gumroad Settings → Advanced → Application → generate access token.

Supported operations:
- create_product()   — posts a new digital listing
- update_product()   — edits price, description, enabled state
- list_products()    — returns all products in account
- disable_product()  — unpublishes without deleting
- get_sales()        — revenue report
"""
from __future__ import annotations

import os
import json
from typing import Optional

try:
    import requests as _requests
    _REQUESTS_AVAILABLE = True
except ImportError:
    _REQUESTS_AVAILABLE = False

GUMROAD_BASE = "https://api.gumroad.com/v2"
_TOKEN = os.environ.get("GUMROAD_ACCESS_TOKEN", "")


def _headers() -> dict:
    return {"Authorization": f"Bearer {_TOKEN}"}


def _available() -> bool:
    return _REQUESTS_AVAILABLE and bool(_TOKEN)


# ── Products ──────────────────────────────────────────────────────────────────

def create_product(
    name: str,
    price_cents: int,
    description: str = "",
    url: str = "",
    file_url: str = "",
    published: bool = True,
    tags: list[str] = None,
    preview_url: str = "",
) -> dict:
    """
    Creates a product on Gumroad.
    Returns the API response dict with 'product' key on success.
    Returns {'error': str} on failure or when token not set.
    """
    if not _available():
        return {"error": "GUMROAD_ACCESS_TOKEN not set — product simulated", "simulated": True,
                "product": {"id": f"sim_{name[:8].lower().replace(' ','_')}", "name": name,
                            "price": price_cents, "published": published}}

    payload = {
        "name": name,
        "price": price_cents,   # in cents
        "description": description,
        "published": "true" if published else "false",
    }
    if url:
        payload["url"] = url
    if file_url:
        payload["file_url"] = file_url
    if tags:
        payload["tags[]"] = tags
    if preview_url:
        payload["preview_url"] = preview_url

    try:
        resp = _requests.post(
            f"{GUMROAD_BASE}/products",
            data=payload,
            headers=_headers(),
            timeout=20,
        )
        return resp.json()
    except Exception as e:
        return {"error": str(e)}


def update_product(
    product_id: str,
    **kwargs,
) -> dict:
    """Update fields on an existing product."""
    if not _available():
        return {"error": "GUMROAD_ACCESS_TOKEN not set", "simulated": True}

    try:
        resp = _requests.put(
            f"{GUMROAD_BASE}/products/{product_id}",
            data=kwargs,
            headers=_headers(),
            timeout=20,
        )
        return resp.json()
    except Exception as e:
        return {"error": str(e)}


def list_products() -> list[dict]:
    """Returns all products in the account."""
    if not _available():
        return []

    try:
        resp = _requests.get(
            f"{GUMROAD_BASE}/products",
            headers=_headers(),
            timeout=20,
        )
        data = resp.json()
        return data.get("products", [])
    except Exception:
        return []


def disable_product(product_id: str) -> dict:
    return update_product(product_id, published="false")


def get_sales(
    product_id: str = None,
    after: str = None,
    before: str = None,
) -> list[dict]:
    """
    Returns sales records (paged, max 10/call from Gumroad API).
    Filters: product_id, after (date str), before (date str).
    """
    if not _available():
        return []

    params = {}
    if product_id:
        params["product_id"] = product_id
    if after:
        params["after"] = after
    if before:
        params["before"] = before

    try:
        resp = _requests.get(
            f"{GUMROAD_BASE}/sales",
            params=params,
            headers=_headers(),
            timeout=20,
        )
        data = resp.json()
        return data.get("sales", [])
    except Exception:
        return []


def get_revenue_summary() -> dict:
    """Pull all sales and sum revenue."""
    sales = get_sales()
    total_cents = sum(int(s.get("price", 0)) for s in sales)
    total_gumroad_fee = sum(int(s.get("gumroad_fee", 0)) for s in sales)
    net = total_cents - total_gumroad_fee
    return {
        "total_sales": len(sales),
        "gross_cents": total_cents,
        "fee_cents": total_gumroad_fee,
        "net_cents": net,
        "gross_usd": round(total_cents / 100, 2),
        "net_usd": round(net / 100, 2),
    }
