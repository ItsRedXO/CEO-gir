"""
Listing Worker — creates and manages marketplace listings for Etsy and Fiverr.
Produces structured listing data that can be submitted via platform APIs.
"""
from __future__ import annotations
import time
from .base import BaseWorker, WorkerResult


class EtsyListingWorker(BaseWorker):
    capabilities = ["listing", "marketplace", "etsy", "digital_products"]
    workstream_id = "etsy"

    def execute(self, task: dict) -> WorkerResult:
        start = time.monotonic()
        input_data = self._parse_input(task)

        product_type = input_data.get("product_type", "digital_art")
        niche = input_data.get("niche", "general")
        price_usd = float(input_data.get("price_usd", 4.99))
        quantity = int(input_data.get("quantity", 1))

        # Generate listing structure — real impl calls Etsy API
        listing = {
            "title": self._generate_title(product_type, niche),
            "description": self._generate_description(product_type, niche),
            "price_usd": price_usd,
            "quantity": quantity,
            "tags": self._generate_tags(product_type, niche),
            "category": "Digital Downloads",
            "processing_time": "instant",
            "digital": True,
            "status": "draft",
            "estimated_monthly_revenue": self._estimate_revenue(price_usd, niche),
        }

        duration_ms = int((time.monotonic() - start) * 1000)
        return WorkerResult(
            success=True,
            output={"listing": listing, "platform": "etsy", "next_step": "review_and_publish"},
            duration_ms=duration_ms,
            economic_data={
                "revenue_estimate": listing["estimated_monthly_revenue"],
                "spend": 0.20,  # Etsy listing fee
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

    def _generate_title(self, product_type: str, niche: str) -> str:
        templates = {
            "digital_art": f"Instant Download Digital Art Print — {niche.title()} Wall Art",
            "printable": f"Printable {niche.title()} Template — Instant Download PDF",
            "planner": f"Digital Planner {niche.title()} — PDF Instant Download",
            "svg": f"{niche.title()} SVG Cut File — Cricut Silhouette Instant Download",
        }
        return templates.get(product_type, f"{product_type.title()} — {niche.title()} Instant Download")

    def _generate_description(self, product_type: str, niche: str) -> str:
        return (
            f"High-quality {product_type} for {niche} enthusiasts.\n\n"
            f"✓ Instant digital download\n"
            f"✓ High resolution files included\n"
            f"✓ Commercial use license\n"
            f"✓ Optimized for home and professional printing\n\n"
            f"Perfect for home decor, gifts, and personal projects."
        )

    def _generate_tags(self, product_type: str, niche: str) -> list[str]:
        base = ["instant download", "digital download", "printable", product_type.replace("_", " ")]
        niche_tags = [niche, f"{niche} gift", f"{niche} decor", f"{niche} print"]
        return (base + niche_tags)[:13]

    def _estimate_revenue(self, price_usd: float, niche: str) -> float:
        # Conservative estimate: 3-8 sales/month for a new listing
        niche_multipliers = {"minimal": 6, "boho": 8, "floral": 7, "abstract": 5}
        sales = niche_multipliers.get(niche, 4)
        return round(price_usd * sales * 0.75, 2)  # ~25% Etsy fees


class FiverrGigWorker(BaseWorker):
    capabilities = ["freelance", "service_delivery", "fiverr", "gig"]
    workstream_id = "fiverr"

    def execute(self, task: dict) -> WorkerResult:
        start = time.monotonic()
        input_data = self._parse_input(task)

        service_type = input_data.get("service_type", "logo_design")
        tier = input_data.get("tier", "basic")
        price_usd = float(input_data.get("price_usd", 15.0))

        gig = {
            "title": self._generate_gig_title(service_type),
            "description": self._generate_gig_description(service_type),
            "packages": self._generate_packages(service_type, price_usd),
            "tags": self._generate_tags(service_type),
            "category": self._get_category(service_type),
            "delivery_time_days": self._get_delivery_days(service_type, tier),
            "status": "draft",
            "estimated_monthly_revenue": self._estimate_revenue(price_usd, service_type),
        }

        duration_ms = int((time.monotonic() - start) * 1000)
        return WorkerResult(
            success=True,
            output={"gig": gig, "platform": "fiverr", "next_step": "review_and_publish"},
            duration_ms=duration_ms,
            economic_data={
                "revenue_estimate": gig["estimated_monthly_revenue"],
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

    def _generate_gig_title(self, service_type: str) -> str:
        titles = {
            "logo_design": "I will design a modern minimalist logo for your brand",
            "social_media": "I will create stunning social media graphics for your business",
            "video_editing": "I will edit your YouTube or TikTok video professionally",
            "content_writing": "I will write SEO-optimized blog posts and articles",
            "data_entry": "I will do accurate and fast data entry and web research",
        }
        return titles.get(service_type, f"I will provide professional {service_type.replace('_', ' ')}")

    def _generate_gig_description(self, service_type: str) -> str:
        return (
            f"Professional {service_type.replace('_', ' ')} service.\n\n"
            f"Why choose me:\n"
            f"✓ Fast delivery\n"
            f"✓ Unlimited revisions until satisfied\n"
            f"✓ Professional quality\n"
            f"✓ 100% satisfaction guarantee\n\n"
            f"Message me before ordering to discuss your specific needs."
        )

    def _generate_packages(self, service_type: str, base_price: float) -> dict:
        return {
            "basic": {"price": base_price, "delivery_days": 3, "revisions": 2},
            "standard": {"price": base_price * 2.5, "delivery_days": 2, "revisions": 5},
            "premium": {"price": base_price * 5, "delivery_days": 1, "revisions": "unlimited"},
        }

    def _generate_tags(self, service_type: str) -> list[str]:
        tag_map = {
            "logo_design": ["logo", "brand", "design", "minimalist", "modern logo"],
            "social_media": ["social media", "graphics", "instagram", "facebook", "posts"],
            "video_editing": ["video editing", "youtube", "tiktok", "reels", "shorts"],
            "content_writing": ["content writing", "blog", "seo", "copywriting", "articles"],
        }
        return tag_map.get(service_type, [service_type.replace("_", " ")])

    def _get_category(self, service_type: str) -> str:
        cats = {
            "logo_design": "Graphics & Design",
            "social_media": "Graphics & Design",
            "video_editing": "Video & Animation",
            "content_writing": "Writing & Translation",
        }
        return cats.get(service_type, "Other")

    def _get_delivery_days(self, service_type: str, tier: str) -> int:
        base = {"logo_design": 3, "social_media": 2, "video_editing": 5, "content_writing": 2}
        return base.get(service_type, 3)

    def _estimate_revenue(self, price_usd: float, service_type: str) -> float:
        monthly_orders = {"logo_design": 4, "social_media": 8, "video_editing": 3, "content_writing": 10}
        orders = monthly_orders.get(service_type, 4)
        return round(price_usd * orders * 0.80, 2)  # 20% Fiverr fee
