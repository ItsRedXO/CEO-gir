"""
Mock Providers — simulates external API responses for development and testing.
Lets the system run fully without real Etsy/Fiverr/OpenAI credentials.
"""
from __future__ import annotations

import time
import random
import hashlib
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class MockResponse:
    success: bool
    data: dict
    latency_ms: int
    provider: str


class MockEtsyProvider:
    """Simulates Etsy API responses."""

    def create_listing(self, listing: dict) -> MockResponse:
        latency = random.randint(200, 800)
        time.sleep(latency / 1000)
        listing_id = int(hashlib.sha256(listing.get("title", "").encode()).hexdigest()[:8], 16)
        return MockResponse(
            success=True,
            data={
                "listing_id": listing_id,
                "state": "draft",
                "url": f"https://www.etsy.com/listing/{listing_id}",
                "title": listing.get("title"),
                "price": listing.get("price_usd"),
                "created_timestamp": int(time.time()),
            },
            latency_ms=latency,
            provider="mock_etsy",
        )

    def get_listing_stats(self, listing_id: int) -> MockResponse:
        latency = random.randint(100, 400)
        time.sleep(latency / 1000)
        views = random.randint(0, 150)
        favorites = int(views * random.uniform(0.05, 0.15))
        sales = int(favorites * random.uniform(0.1, 0.3))
        return MockResponse(
            success=True,
            data={
                "listing_id": listing_id,
                "views": views,
                "favorites": favorites,
                "sales": sales,
                "revenue_usd": round(sales * random.uniform(3.99, 9.99), 2),
            },
            latency_ms=latency,
            provider="mock_etsy",
        )


class MockFiverrProvider:
    """Simulates Fiverr API responses."""

    def create_gig(self, gig: dict) -> MockResponse:
        latency = random.randint(300, 900)
        time.sleep(latency / 1000)
        gig_id = hashlib.sha256(gig.get("title", "").encode()).hexdigest()[:12]
        return MockResponse(
            success=True,
            data={
                "gig_id": gig_id,
                "status": "active",
                "url": f"https://www.fiverr.com/s/{gig_id}",
                "title": gig.get("title"),
                "packages": gig.get("packages"),
                "created_at": int(time.time()),
            },
            latency_ms=latency,
            provider="mock_fiverr",
        )

    def get_gig_stats(self, gig_id: str) -> MockResponse:
        latency = random.randint(100, 400)
        time.sleep(latency / 1000)
        impressions = random.randint(0, 500)
        clicks = int(impressions * random.uniform(0.02, 0.08))
        orders = int(clicks * random.uniform(0.05, 0.15))
        return MockResponse(
            success=True,
            data={
                "gig_id": gig_id,
                "impressions": impressions,
                "clicks": clicks,
                "orders": orders,
                "revenue_usd": round(orders * random.uniform(15, 50), 2),
                "rating": round(random.uniform(4.5, 5.0), 1),
            },
            latency_ms=latency,
            provider="mock_fiverr",
        )


class MockLLMProvider:
    """Simulates LLM API responses for research/content tasks."""

    def complete(self, prompt: str, max_tokens: int = 500) -> MockResponse:
        latency = random.randint(500, 2000)
        time.sleep(latency / 1000)
        words = min(max_tokens // 4, 120)
        mock_text = " ".join(["word"] * words)
        return MockResponse(
            success=True,
            data={
                "text": mock_text,
                "tokens_used": words * 4,
                "model": "mock-gpt-4",
                "finish_reason": "stop",
            },
            latency_ms=latency,
            provider="mock_llm",
        )

    def embed(self, text: str) -> MockResponse:
        latency = random.randint(50, 200)
        time.sleep(latency / 1000)
        embedding = [random.uniform(-1, 1) for _ in range(1536)]
        return MockResponse(
            success=True,
            data={"embedding": embedding, "dimensions": 1536},
            latency_ms=latency,
            provider="mock_llm",
        )


class MockAnalyticsProvider:
    """Simulates analytics/tracking API responses."""

    def get_traffic(self, url: str, period_days: int = 30) -> MockResponse:
        latency = random.randint(100, 500)
        time.sleep(latency / 1000)
        daily_avg = random.randint(10, 500)
        return MockResponse(
            success=True,
            data={
                "url": url,
                "period_days": period_days,
                "total_visits": daily_avg * period_days,
                "unique_visitors": int(daily_avg * period_days * 0.7),
                "bounce_rate": round(random.uniform(0.4, 0.8), 2),
                "avg_session_duration_s": random.randint(60, 300),
                "top_sources": [
                    {"source": "organic", "pct": 0.45},
                    {"source": "direct", "pct": 0.30},
                    {"source": "social", "pct": 0.25},
                ],
            },
            latency_ms=latency,
            provider="mock_analytics",
        )


# Registry — easy access to all mock providers
class MockProviderRegistry:
    def __init__(self):
        self.etsy = MockEtsyProvider()
        self.fiverr = MockFiverrProvider()
        self.llm = MockLLMProvider()
        self.analytics = MockAnalyticsProvider()

    def get(self, provider_name: str):
        providers = {
            "etsy": self.etsy,
            "fiverr": self.fiverr,
            "llm": self.llm,
            "analytics": self.analytics,
        }
        return providers.get(provider_name)


_mock_registry: Optional[MockProviderRegistry] = None


def get_mock_providers() -> MockProviderRegistry:
    global _mock_registry
    if _mock_registry is None:
        _mock_registry = MockProviderRegistry()
    return _mock_registry
