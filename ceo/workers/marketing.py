"""
Marketing Worker — handles affiliate content, SEO, and social distribution.
Produces structured campaign data for affiliate and content monetization.
"""
from __future__ import annotations
import time
from .base import BaseWorker, WorkerResult


class AffiliateWorker(BaseWorker):
    capabilities = ["affiliate", "content", "marketing", "monetization"]
    workstream_id = "affiliate"

    def execute(self, task: dict) -> WorkerResult:
        start = time.monotonic()
        input_data = self._parse_input(task)

        niche = input_data.get("niche", "tech")
        content_format = input_data.get("content_format", "blog_post")
        products = input_data.get("products", [])

        campaign = {
            "niche": niche,
            "content_format": content_format,
            "title": self._generate_title(niche, content_format),
            "outline": self._generate_outline(niche, content_format),
            "affiliate_placements": self._suggest_placements(content_format),
            "target_keywords": self._get_keywords(niche),
            "estimated_monthly_visitors": self._estimate_traffic(niche, content_format),
            "conversion_rate": self._estimate_conversion(niche),
            "avg_commission_usd": self._estimate_commission(niche),
            "estimated_monthly_revenue": 0.0,
            "status": "draft",
        }
        monthly_rev = (
            campaign["estimated_monthly_visitors"]
            * campaign["conversion_rate"]
            * campaign["avg_commission_usd"]
        )
        campaign["estimated_monthly_revenue"] = round(monthly_rev, 2)

        duration_ms = int((time.monotonic() - start) * 1000)
        return WorkerResult(
            success=True,
            output={"campaign": campaign, "platform": "affiliate", "next_step": "publish_content"},
            duration_ms=duration_ms,
            economic_data={
                "revenue_estimate": 0.0,
                "spend": 0.0,
            },
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

    def _generate_title(self, niche: str, content_format: str) -> str:
        templates = {
            "blog_post": f"Best {niche.title()} Products of 2025 (Tested & Reviewed)",
            "comparison": f"Top 5 {niche.title()} Tools Compared — Which One is Right for You?",
            "guide": f"Complete Beginner's Guide to {niche.title()} in 2025",
            "listicle": f"10 Must-Have {niche.title()} Products That Actually Work",
        }
        return templates.get(content_format, f"{niche.title()} Review and Recommendations")

    def _generate_outline(self, niche: str, content_format: str) -> list[str]:
        return [
            f"Introduction to {niche}",
            "What to look for",
            "Top picks (with affiliate links)",
            "Comparison table",
            "Final recommendation",
        ]

    def _suggest_placements(self, content_format: str) -> list[dict]:
        placements = [
            {"position": "intro", "type": "contextual_link", "weight": "high"},
            {"position": "comparison_table", "type": "product_box", "weight": "highest"},
            {"position": "conclusion", "type": "cta_button", "weight": "high"},
        ]
        return placements

    def _get_keywords(self, niche: str) -> list[str]:
        base = [f"best {niche}", f"{niche} review", f"{niche} comparison", f"buy {niche}"]
        return base

    def _estimate_traffic(self, niche: str, content_format: str) -> int:
        base = {"tech": 800, "fitness": 600, "finance": 1200, "home": 500}
        format_mult = {"blog_post": 1.0, "comparison": 1.3, "guide": 0.8, "listicle": 1.2}
        traffic = base.get(niche, 400) * format_mult.get(content_format, 1.0)
        return int(traffic)

    def _estimate_conversion(self, niche: str) -> float:
        rates = {"tech": 0.03, "fitness": 0.04, "finance": 0.025, "home": 0.05}
        return rates.get(niche, 0.03)

    def _estimate_commission(self, niche: str) -> float:
        commissions = {"tech": 8.0, "fitness": 12.0, "finance": 25.0, "home": 6.0}
        return commissions.get(niche, 8.0)


class SEOWorker(BaseWorker):
    capabilities = ["seo", "keyword_research", "content_optimization"]
    workstream_id = "content"

    def execute(self, task: dict) -> WorkerResult:
        start = time.monotonic()
        input_data = self._parse_input(task)

        url_or_topic = input_data.get("topic", task.get("title", ""))
        target_keyword = input_data.get("target_keyword", "")

        analysis = {
            "topic": url_or_topic,
            "target_keyword": target_keyword or url_or_topic,
            "keyword_difficulty": self._estimate_difficulty(target_keyword),
            "search_volume_monthly": self._estimate_volume(target_keyword),
            "suggested_keywords": self._suggest_keywords(url_or_topic),
            "content_gaps": ["add FAQ section", "include comparison table", "add video embed"],
            "on_page_score": 68,
            "recommendations": [
                "Increase content length to 1500+ words",
                "Add 3-5 internal links",
                "Optimize meta description",
                "Add schema markup for reviews",
            ],
            "estimated_ranking_time_days": 45,
        }

        duration_ms = int((time.monotonic() - start) * 1000)
        return WorkerResult(
            success=True,
            output={"seo_analysis": analysis, "next_step": "apply_recommendations"},
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

    def _estimate_difficulty(self, keyword: str) -> str:
        if not keyword:
            return "medium"
        length = len(keyword.split())
        if length >= 4:
            return "low"
        elif length >= 2:
            return "medium"
        return "high"

    def _estimate_volume(self, keyword: str) -> int:
        if not keyword:
            return 500
        words = len(keyword.split())
        if words >= 4:
            return 200
        elif words >= 2:
            return 800
        return 5000

    def _suggest_keywords(self, topic: str) -> list[str]:
        words = topic.lower().split()[:2]
        base = " ".join(words)
        return [
            f"best {base}",
            f"{base} guide",
            f"{base} tips",
            f"how to {base}",
            f"{base} for beginners",
        ]


class SocialMediaWorker(BaseWorker):
    capabilities = ["social_media", "distribution", "engagement", "tiktok", "youtube"]
    workstream_id = "youtube"

    def execute(self, task: dict) -> WorkerResult:
        start = time.monotonic()
        input_data = self._parse_input(task)

        platforms = input_data.get("platforms", ["youtube", "tiktok"])
        content_topic = input_data.get("topic", task.get("title", ""))
        content_type = input_data.get("content_type", "short_form")

        distribution_plan = {
            "topic": content_topic,
            "content_type": content_type,
            "platforms": [],
            "total_estimated_views": 0,
            "estimated_revenue_cpm": 0.0,
        }

        for platform in platforms:
            plan = self._create_platform_plan(platform, content_type, content_topic)
            distribution_plan["platforms"].append(plan)
            distribution_plan["total_estimated_views"] += plan["estimated_views"]
            distribution_plan["estimated_revenue_cpm"] += plan["estimated_revenue"]

        duration_ms = int((time.monotonic() - start) * 1000)
        return WorkerResult(
            success=True,
            output={"distribution_plan": distribution_plan, "next_step": "create_content"},
            duration_ms=duration_ms,
            economic_data={
                "revenue_estimate": 0.0,
                "spend": 0.0,
            },
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

    def _create_platform_plan(self, platform: str, content_type: str, topic: str) -> dict:
        configs = {
            "youtube": {
                "post_frequency": "3x/week",
                "format": "long_form" if content_type == "long_form" else "shorts",
                "estimated_views": 500,
                "cpm_usd": 3.50,
                "monetization": "ads + affiliate",
            },
            "tiktok": {
                "post_frequency": "daily",
                "format": "short_form",
                "estimated_views": 2000,
                "cpm_usd": 0.02,
                "monetization": "creator_fund + affiliate",
            },
            "instagram": {
                "post_frequency": "5x/week",
                "format": "reels",
                "estimated_views": 800,
                "cpm_usd": 0.0,
                "monetization": "affiliate + brand_deals",
            },
        }
        cfg = configs.get(platform, {"post_frequency": "3x/week", "format": "mixed", "estimated_views": 300, "cpm_usd": 0.01, "monetization": "ads"})
        revenue = round(cfg["estimated_views"] * cfg["cpm_usd"] / 1000, 2)
        return {
            "platform": platform,
            "topic": topic,
            "post_frequency": cfg["post_frequency"],
            "format": cfg["format"],
            "estimated_views": cfg["estimated_views"],
            "estimated_revenue": revenue,
            "monetization": cfg["monetization"],
        }
