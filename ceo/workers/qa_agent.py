"""
Quality Assurance Agent — evaluates generated asset images before Gumroad listing.

Uses Claude claude-haiku-4-5-20251001 Vision via direct HTTP to score assets on:
  • Clarity / no distortion
  • Commercial viability (would a buyer pay for this?)
  • Match to intended type/style
  • No obvious AI artifacts (garbled text, melted faces, morphed limbs)

score_asset_image() returns a QAResult with .passed, .score (0-10), .reason.
"""
from __future__ import annotations

import os
import base64
import logging
import json
from dataclasses import dataclass
from typing import Optional

log = logging.getLogger(__name__)

_ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
_QA_THRESHOLD  = 6      # 0-10 scale; pass if score >= threshold
_HAIKU_MODEL   = "claude-haiku-4-5-20251001"

_SYSTEM = (
    "You are a professional digital asset quality reviewer for an online marketplace. "
    "You evaluate AI-generated images for commercial suitability. "
    "Be strict — buyers pay real money, so reject anything distorted, garbled, or amateurish."
)

_PROMPT_TEMPLATE = (
    "Evaluate this AI-generated digital asset image.\n\n"
    "Asset type: {asset_type}\n"
    "Style: {style}\n"
    "Product title: {title}\n\n"
    "Score the image on these criteria (each 0-10):\n"
    "1. Clarity — is it sharp, clean, no blurring or obvious distortion?\n"
    "2. Commercial viability — would someone pay $5-$20 for this as a digital product?\n"
    "3. Style match — does it look like a '{style} {asset_type}' as described?\n"
    "4. AI artifact absence — no garbled text, melted shapes, or morphed content?\n\n"
    "Respond with ONLY valid JSON in this exact format:\n"
    '{{"score": <0-10 average>, "passed": <true|false>, '
    '"reason": "<one sentence max>", '
    '"criteria": {{"clarity": <0-10>, "commercial": <0-10>, "style_match": <0-10>, "clean": <0-10>}}}}\n\n'
    "Pass threshold is score >= 6. Be strict — reject morphed AI slop."
)


@dataclass
class QAResult:
    score:    float
    passed:   bool
    reason:   str
    criteria: dict

    def __str__(self) -> str:
        verdict = "✅ PASS" if self.passed else "❌ FAIL"
        return f"QA {verdict} score={self.score:.1f}/10 — {self.reason}"


def score_asset_image(
    png_bytes: bytes,
    title: str,
    asset_type: str,
    style: str,
) -> Optional[QAResult]:
    """
    Send png_bytes to Claude Vision for quality scoring.
    Returns QAResult or None if the call fails (caller should treat None as pass-through).
    """
    if not _ANTHROPIC_KEY:
        log.warning("QA Agent: ANTHROPIC_API_KEY not set — skipping QA check")
        return None
    if not png_bytes:
        log.warning("QA Agent: no image bytes — skipping QA check")
        return None

    try:
        import requests

        b64 = base64.standard_b64encode(png_bytes).decode()
        prompt = _PROMPT_TEMPLATE.format(
            asset_type=asset_type,
            style=style,
            title=title[:80],
        )

        payload = {
            "model": _HAIKU_MODEL,
            "max_tokens": 256,
            "system": _SYSTEM,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": b64,
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        }

        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": _ANTHROPIC_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        raw = resp.json()
        text = raw["content"][0]["text"].strip()

        # Strip markdown fences if present
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]

        data = json.loads(text)
        score    = float(data.get("score", 0))
        passed   = bool(data.get("passed", score >= _QA_THRESHOLD))
        reason   = str(data.get("reason", ""))[:200]
        criteria = data.get("criteria", {})

        result = QAResult(score=score, passed=passed, reason=reason, criteria=criteria)
        log.info("QA Agent: %s", result)
        return result

    except Exception as exc:
        log.warning("QA Agent call failed (%s) — treating as pass-through", exc)
        return None


def improved_prompt_hint(asset_type: str, style: str, reason: str) -> str:
    """
    Return a suffix to append to the image prompt on retry after QA failure.
    Steers generation away from the noted defect.
    """
    hints = [
        "ultra sharp, professional quality, clean lines",
        "high detail, no distortion, commercial grade",
        "crisp edges, balanced composition, sellable product",
    ]
    base = hints[hash(reason) % len(hints)]
    return f", {base}, {style} style, perfect {asset_type.replace('_', ' ')}, no artifacts"
