"""
Trend Research Workers — find profitable niches, trending topics, and market opportunities.
These feed the front of every workstream pipeline.
"""
from __future__ import annotations
import time
import random
from .base import BaseWorker, WorkerResult


# Niche database — real impl would call Etsy/Google Trends/TikTok APIs
ETSY_HOT_NICHES = [
    {"niche": "boho", "demand": "high", "competition": "medium", "avg_price": 5.99, "monthly_searches": 14000},
    {"niche": "minimal", "demand": "high", "competition": "high", "avg_price": 4.99, "monthly_searches": 22000},
    {"niche": "wildflower", "demand": "rising", "competition": "low", "avg_price": 6.99, "monthly_searches": 8500},
    {"niche": "gothic", "demand": "steady", "competition": "low", "avg_price": 7.99, "monthly_searches": 6200},
    {"niche": "celestial", "demand": "rising", "competition": "medium", "avg_price": 5.49, "monthly_searches": 11000},
    {"niche": "cottagecore", "demand": "high", "competition": "medium", "avg_price": 5.99, "monthly_searches": 9800},
    {"niche": "vintage", "demand": "high", "competition": "high", "avg_price": 6.99, "monthly_searches": 18000},
    {"niche": "farmhouse", "demand": "steady", "competition": "high", "avg_price": 4.99, "monthly_searches": 15000},
    {"niche": "abstract", "demand": "steady", "competition": "medium", "avg_price": 5.49, "monthly_searches": 7500},
    {"niche": "floral", "demand": "high", "competition": "high", "avg_price": 4.99, "monthly_searches": 25000},
]

FIVERR_HOT_SERVICES = [
    {"service": "logo_design", "demand": "high", "avg_price": 25, "orders_per_month": 8, "skill_required": "medium"},
    {"service": "video_editing", "demand": "very_high", "avg_price": 45, "orders_per_month": 6, "skill_required": "medium"},
    {"service": "social_media", "demand": "high", "avg_price": 20, "orders_per_month": 12, "skill_required": "low"},
    {"service": "content_writing", "demand": "high", "avg_price": 15, "orders_per_month": 15, "skill_required": "medium"},
    {"service": "data_entry", "demand": "steady", "avg_price": 10, "orders_per_month": 20, "skill_required": "low"},
    {"service": "voiceover", "demand": "rising", "avg_price": 35, "orders_per_month": 5, "skill_required": "low"},
    {"service": "thumbnail_design", "demand": "very_high", "avg_price": 15, "orders_per_month": 18, "skill_required": "low"},
    {"service": "ai_image_editing", "demand": "rising", "avg_price": 20, "orders_per_month": 14, "skill_required": "low"},
]

AFFILIATE_HOT_NICHES = [
    {"niche": "tech", "avg_commission": 8.0, "competition": "high", "traffic_potential": "high"},
    {"niche": "fitness", "avg_commission": 12.0, "competition": "medium", "traffic_potential": "high"},
    {"niche": "finance", "avg_commission": 30.0, "competition": "high", "traffic_potential": "medium"},
    {"niche": "home_garden", "avg_commission": 6.0, "competition": "medium", "traffic_potential": "high"},
    {"niche": "pet", "avg_commission": 10.0, "competition": "low", "traffic_potential": "medium"},
    {"niche": "beauty", "avg_commission": 8.0, "competition": "medium", "traffic_potential": "high"},
    {"niche": "software_saas", "avg_commission": 25.0, "competition": "medium", "traffic_potential": "medium"},
]

YOUTUBE_HOT_TOPICS = [
    {"topic": "ai tools", "trend": "explosive", "cpm": 8.0, "monthly_searches": 450000},
    {"topic": "passive income", "trend": "steady_high", "cpm": 12.0, "monthly_searches": 200000},
    {"topic": "side hustle", "trend": "steady_high", "cpm": 10.0, "monthly_searches": 180000},
    {"topic": "budget cooking", "trend": "rising", "cpm": 4.0, "monthly_searches": 120000},
    {"topic": "home workouts", "trend": "steady", "cpm": 5.0, "monthly_searches": 90000},
    {"topic": "personal finance", "trend": "steady_high", "cpm": 15.0, "monthly_searches": 250000},
    {"topic": "productivity hacks", "trend": "rising", "cpm": 9.0, "monthly_searches": 80000},
]


class TrendResearchWorker(BaseWorker):
    capabilities = ["trend_research", "market_research", "niche_discovery", "research"]
    workstream_id = "research"

    def execute(self, task: dict) -> WorkerResult:
        start = time.monotonic()
        input_data = self._parse_input(task)
        platform = input_data.get("platform", "etsy")
        top_n = int(input_data.get("top_n", 3))

        if platform == "etsy":
            opportunities = self._rank_etsy_niches(top_n)
        elif platform == "fiverr":
            opportunities = self._rank_fiverr_services(top_n)
        elif platform == "affiliate":
            opportunities = self._rank_affiliate_niches(top_n)
        elif platform == "youtube":
            opportunities = self._rank_youtube_topics(top_n)
        else:
            opportunities = self._rank_etsy_niches(top_n)

        output = {
            "platform": platform,
            "top_opportunities": opportunities,
            "analysis_date": time.strftime("%Y-%m-%d"),
            "recommendation": opportunities[0] if opportunities else None,
            "confidence": 0.75,
            "next_step": f"create_{platform}_listing" if platform in ("etsy", "fiverr") else f"create_{platform}_content",
        }

        duration_ms = int((time.monotonic() - start) * 1000)
        return WorkerResult(
            success=True,
            output=output,
            duration_ms=duration_ms,
        )

    def _parse_input(self, task: dict) -> dict:
        data = task.get("input_json") or {}
        if isinstance(data, str):
            import json
            try:
                return json.loads(data)
            except Exception:
                return {}
        return data

    def _score_etsy_niche(self, n: dict) -> float:
        demand_score = {"high": 3, "rising": 2.5, "steady": 1.5, "low": 0.5}.get(n["demand"], 1)
        comp_score = {"low": 3, "medium": 2, "high": 1}.get(n["competition"], 1.5)
        return demand_score * comp_score * n["avg_price"] * (n["monthly_searches"] / 10000)

    def _rank_etsy_niches(self, top_n: int) -> list[dict]:
        scored = sorted(ETSY_HOT_NICHES, key=self._score_etsy_niche, reverse=True)
        return [
            {**n, "score": round(self._score_etsy_niche(n), 2),
             "estimated_monthly_revenue": round(n["avg_price"] * random.randint(4, 12) * 0.75, 2)}
            for n in scored[:top_n]
        ]

    def _rank_fiverr_services(self, top_n: int) -> list[dict]:
        scored = sorted(
            FIVERR_HOT_SERVICES,
            key=lambda s: s["orders_per_month"] * s["avg_price"] * (1.5 if s["skill_required"] == "low" else 1.0),
            reverse=True,
        )
        return [
            {**s, "estimated_monthly_revenue": round(s["orders_per_month"] * s["avg_price"] * 0.80, 2)}
            for s in scored[:top_n]
        ]

    def _rank_affiliate_niches(self, top_n: int) -> list[dict]:
        scored = sorted(
            AFFILIATE_HOT_NICHES,
            key=lambda n: n["avg_commission"] * (1.5 if n["competition"] != "high" else 1.0),
            reverse=True,
        )
        return [{**n, "estimated_monthly_revenue": round(n["avg_commission"] * random.randint(20, 80), 2)} for n in scored[:top_n]]

    def _rank_youtube_topics(self, top_n: int) -> list[dict]:
        scored = sorted(YOUTUBE_HOT_TOPICS, key=lambda t: t["cpm"] * t["monthly_searches"], reverse=True)
        return [
            {**t, "estimated_monthly_revenue": round(t["cpm"] * random.randint(5000, 50000) / 1000, 2)}
            for t in scored[:top_n]
        ]


class NicheAnalysisWorker(BaseWorker):
    capabilities = ["niche_analysis", "competitor_analysis", "market_validation"]
    workstream_id = "research"

    def execute(self, task: dict) -> WorkerResult:
        start = time.monotonic()
        input_data = self._parse_input(task)
        niche = input_data.get("niche", "general")
        platform = input_data.get("platform", "etsy")

        analysis = {
            "niche": niche,
            "platform": platform,
            "market_size": "medium",
            "top_competitors": self._mock_competitors(niche, platform),
            "pricing_analysis": {
                "low": 2.99,
                "median": 5.99,
                "high": 14.99,
                "recommended_entry": 4.99,
            },
            "keyword_gaps": [f"{niche} minimal", f"{niche} printable bundle", f"instant {niche} download"],
            "differentiation_angles": [
                f"Bundle {niche} prints (3-pack, 5-pack)",
                "Commercial license included",
                "Extra large format (24x36)",
            ],
            "verdict": "proceed",
            "confidence": 0.72,
            "estimated_monthly_revenue": random.randint(40, 180),
        }

        duration_ms = int((time.monotonic() - start) * 1000)
        return WorkerResult(success=True, output={"niche_analysis": analysis}, duration_ms=duration_ms)

    def _parse_input(self, task: dict) -> dict:
        data = task.get("input_json") or {}
        if isinstance(data, str):
            import json
            try:
                return json.loads(data)
            except Exception:
                return {}
        return data

    def _mock_competitors(self, niche: str, platform: str) -> list[dict]:
        return [
            {"name": f"{niche.title()} Studio", "sales": random.randint(500, 5000), "price": round(random.uniform(3, 12), 2)},
            {"name": f"The {niche.title()} Shop", "sales": random.randint(100, 1500), "price": round(random.uniform(2, 8), 2)},
            {"name": f"{niche.title()} Prints Co", "sales": random.randint(200, 2000), "price": round(random.uniform(4, 10), 2)},
        ]


class ProductResearchWorker(BaseWorker):
    capabilities = ["product_research", "digital_product_research", "research"]
    workstream_id = "research"

    def execute(self, task: dict) -> WorkerResult:
        start = time.monotonic()
        input_data = self._parse_input(task)
        product_type = input_data.get("product_type", "printable")
        niche = input_data.get("niche", "minimal")

        products = self._generate_product_ideas(product_type, niche)

        output = {
            "product_type": product_type,
            "niche": niche,
            "product_ideas": products,
            "best_opportunity": products[0] if products else None,
            "total_estimated_revenue": sum(p["estimated_monthly_revenue"] for p in products),
        }

        duration_ms = int((time.monotonic() - start) * 1000)
        return WorkerResult(success=True, output=output, duration_ms=duration_ms)

    def _parse_input(self, task: dict) -> dict:
        data = task.get("input_json") or {}
        if isinstance(data, str):
            import json
            try:
                return json.loads(data)
            except Exception:
                return {}
        return data

    def _generate_product_ideas(self, product_type: str, niche: str) -> list[dict]:
        ideas = {
            "printable": [
                {"name": f"{niche.title()} Wall Art 3-Pack", "price": 7.99, "estimated_monthly_revenue": 48},
                {"name": f"{niche.title()} Quote Prints", "price": 4.99, "estimated_monthly_revenue": 35},
                {"name": f"{niche.title()} Bundle (10-Pack)", "price": 14.99, "estimated_monthly_revenue": 75},
            ],
            "planner": [
                {"name": f"{niche.title()} Daily Planner", "price": 6.99, "estimated_monthly_revenue": 55},
                {"name": f"{niche.title()} Weekly Tracker", "price": 5.49, "estimated_monthly_revenue": 42},
            ],
            "svg": [
                {"name": f"{niche.title()} SVG Bundle", "price": 9.99, "estimated_monthly_revenue": 80},
                {"name": f"{niche.title()} Cut File Set", "price": 4.99, "estimated_monthly_revenue": 45},
            ],
        }
        return ideas.get(product_type, ideas["printable"])
