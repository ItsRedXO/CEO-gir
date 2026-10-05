from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

from ..workers.base import BaseWorker
from ..workers.research import ResearchWorker, ContentWorker, OptimizationWorker
from ..workers.listing import EtsyListingWorker, FiverrGigWorker
from ..workers.asset import DigitalAssetWorker, ContentAssetWorker
from ..workers.marketing import AffiliateWorker, SEOWorker, SocialMediaWorker
from ..workers.analytics import PerformanceAnalyticsWorker, RevenueAnalyticsWorker
from ..workers.trend import TrendResearchWorker, NicheAnalysisWorker, ProductResearchWorker
from ..workers.delivery import ServiceDeliveryWorker, SalesTrackerWorker, PricingOptimizerWorker
from ..workers.email import ListBuildingWorker, EmailCampaignWorker
from ..workers.asset_gen import Asset2DWorker, Asset3DWorker
from ..workers.shorts import ShortsWorker


@dataclass
class WorkstreamConfig:
    workstream_id: str
    name: str
    description: str
    enabled: bool = True
    worker_class: type = None
    capabilities: list[str] = field(default_factory=list)
    priority_boost: int = 0
    revenue_target_daily: float = 0.0
    icon: str = "🔷"


WORKSTREAM_REGISTRY: dict[str, WorkstreamConfig] = {
    "research": WorkstreamConfig(
        workstream_id="research",
        name="Research",
        description="Market research and opportunity discovery",
        worker_class=ResearchWorker,
        capabilities=["research", "analysis"],
        icon="🔍",
    ),
    "content": WorkstreamConfig(
        workstream_id="content",
        name="Content",
        description="Content creation for affiliate/SEO/social",
        worker_class=ContentWorker,
        capabilities=["content", "writing", "seo"],
        revenue_target_daily=10.0,
        icon="✍️",
    ),
    "optimization": WorkstreamConfig(
        workstream_id="optimization",
        name="Optimization",
        description="ROI optimization and scaling",
        worker_class=OptimizationWorker,
        capabilities=["optimization", "scaling"],
        icon="⚡",
    ),
    "etsy": WorkstreamConfig(
        workstream_id="etsy",
        name="Etsy",
        description="Digital products on Etsy",
        enabled=True,
        worker_class=EtsyListingWorker,
        capabilities=["listing", "marketplace", "etsy", "digital_products"],
        revenue_target_daily=20.0,
        icon="🛍️",
    ),
    "fiverr": WorkstreamConfig(
        workstream_id="fiverr",
        name="Fiverr",
        description="Freelance services on Fiverr",
        enabled=True,
        worker_class=FiverrGigWorker,
        capabilities=["freelance", "service_delivery", "fiverr", "gig"],
        revenue_target_daily=15.0,
        icon="💼",
    ),
    "affiliate": WorkstreamConfig(
        workstream_id="affiliate",
        name="Affiliate",
        description="Affiliate marketing and content monetization",
        enabled=True,
        worker_class=AffiliateWorker,
        capabilities=["affiliate", "content", "marketing", "monetization"],
        revenue_target_daily=25.0,
        icon="🔗",
    ),
    "assets": WorkstreamConfig(
        workstream_id="assets",
        name="Assets",
        description="Digital asset creation and management",
        enabled=True,
        worker_class=DigitalAssetWorker,
        capabilities=["asset_creation", "digital_products", "design", "templates"],
        icon="🎨",
    ),
    "analytics": WorkstreamConfig(
        workstream_id="analytics",
        name="Analytics",
        description="Performance metrics and reporting",
        enabled=True,
        worker_class=PerformanceAnalyticsWorker,
        capabilities=["analytics", "reporting", "metrics", "performance"],
        icon="📊",
    ),
    "seo": WorkstreamConfig(
        workstream_id="seo",
        name="SEO",
        description="Search engine optimization",
        enabled=True,
        worker_class=SEOWorker,
        capabilities=["seo", "keyword_research", "content_optimization"],
        revenue_target_daily=8.0,
        icon="📈",
    ),
    "trends": WorkstreamConfig(
        workstream_id="trends",
        name="Trends",
        description="Niche and market trend research",
        enabled=True,
        worker_class=TrendResearchWorker,
        capabilities=["trend_research", "niche_discovery", "market_research"],
        icon="🔥",
    ),
    "delivery": WorkstreamConfig(
        workstream_id="delivery",
        name="Delivery",
        description="Order fulfillment and sales tracking",
        enabled=True,
        worker_class=ServiceDeliveryWorker,
        capabilities=["service_delivery", "order_fulfillment", "sales_tracking", "listing_performance"],
        icon="📦",
    ),
    "email": WorkstreamConfig(
        workstream_id="email",
        name="Email",
        description="Email marketing and list building",
        enabled=True,
        worker_class=EmailCampaignWorker,
        capabilities=["email_campaign", "email_marketing", "list_building", "lead_generation"],
        revenue_target_daily=5.0,
        icon="📧",
    ),
    "pricing": WorkstreamConfig(
        workstream_id="pricing",
        name="Pricing",
        description="Price optimization and A/B testing",
        enabled=True,
        worker_class=PricingOptimizerWorker,
        capabilities=["pricing", "ab_testing", "price_optimization"],
        icon="💲",
    ),
    "assets_2d": WorkstreamConfig(
        workstream_id="assets_2d",
        name="2D Assets",
        description="Printables, logos, SVG bundles, social templates",
        enabled=True,
        worker_class=Asset2DWorker,
        capabilities=["2d_asset", "design", "printable", "logo", "svg", "illustration", "template_design", "social_graphics"],
        revenue_target_daily=15.0,
        icon="🎨",
    ),
    "assets_3d": WorkstreamConfig(
        workstream_id="assets_3d",
        name="3D Assets",
        description="3D models for CGTrader, TurboSquid, Unity Asset Store",
        enabled=True,
        worker_class=Asset3DWorker,
        capabilities=["3d_asset", "3d_model", "cg_asset", "game_asset", "character_model", "environment_design", "prop_creation"],
        revenue_target_daily=25.0,
        icon="🧊",
    ),
    "youtube": WorkstreamConfig(
        workstream_id="youtube",
        name="YouTube Shorts",
        description="AI-narrated Shorts on trending topics — free with gTTS + Pollinations",
        enabled=True,
        worker_class=ShortsWorker,
        capabilities=["youtube_shorts", "video_content", "content", "social_media"],
        revenue_target_daily=5.0,
        icon="▶️",
    ),
    "gumroad": WorkstreamConfig(
        workstream_id="gumroad",
        name="Gumroad",
        description="Auto-post digital product listings to Gumroad (0% monthly fee)",
        enabled=True,
        worker_class=Asset2DWorker,  # reuses asset gen, posts to Gumroad
        capabilities=["2d_asset", "design", "printable"],
        revenue_target_daily=8.0,
        icon="🛒",
    ),
}


def get_workstream(workstream_id: str) -> Optional[WorkstreamConfig]:
    return WORKSTREAM_REGISTRY.get(workstream_id)


def get_enabled_workstreams() -> list[WorkstreamConfig]:
    return [ws for ws in WORKSTREAM_REGISTRY.values() if ws.enabled]


def get_all_workstreams() -> list[WorkstreamConfig]:
    return list(WORKSTREAM_REGISTRY.values())


def find_worker_for_capabilities(required_capabilities: list[str]) -> Optional[BaseWorker]:
    """Return an instantiated worker that can handle all required capabilities."""
    for ws in get_enabled_workstreams():
        if ws.worker_class is None:
            continue
        worker = ws.worker_class()
        if worker.can_handle(required_capabilities):
            return worker
    return None


def route_task(task: dict) -> Optional[BaseWorker]:
    """Route a task to the appropriate worker based on required capabilities."""
    required = task.get("required_capabilities") or []
    if isinstance(required, str):
        import json
        try:
            required = json.loads(required)
        except Exception:
            required = []

    workstream_id = task.get("workstream_id")
    if workstream_id:
        ws = get_workstream(workstream_id)
        if ws and ws.enabled and ws.worker_class:
            worker = ws.worker_class()
            if not required or worker.can_handle(required):
                return worker

    return find_worker_for_capabilities(required)


def get_workstream_summary() -> list[dict]:
    """Returns a dashboard-ready summary of all workstreams."""
    return [
        {
            "workstream_id": ws.workstream_id,
            "name": ws.name,
            "description": ws.description,
            "enabled": ws.enabled,
            "icon": ws.icon,
            "revenue_target_daily": ws.revenue_target_daily,
            "has_worker": ws.worker_class is not None,
        }
        for ws in get_all_workstreams()
    ]
