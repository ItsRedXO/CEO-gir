from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

from ..workers.base import BaseWorker
from ..workers.research import ResearchWorker, ContentWorker, OptimizationWorker


@dataclass
class WorkstreamConfig:
    workstream_id: str
    name: str
    description: str
    enabled: bool = True
    worker_class: type = None
    capabilities: list[str] = field(default_factory=list)
    priority_boost: int = 0


WORKSTREAM_REGISTRY: dict[str, WorkstreamConfig] = {
    "research": WorkstreamConfig(
        workstream_id="research",
        name="Research",
        description="Market research and opportunity discovery",
        worker_class=ResearchWorker,
        capabilities=["research", "analysis"],
    ),
    "content": WorkstreamConfig(
        workstream_id="content",
        name="Content",
        description="Content creation for affiliate/SEO/social",
        worker_class=ContentWorker,
        capabilities=["content", "writing", "seo"],
    ),
    "optimization": WorkstreamConfig(
        workstream_id="optimization",
        name="Optimization",
        description="ROI optimization and scaling",
        worker_class=OptimizationWorker,
        capabilities=["optimization", "scaling"],
    ),
    "etsy": WorkstreamConfig(
        workstream_id="etsy",
        name="Etsy",
        description="Etsy store management and listings",
        enabled=False,
        capabilities=["listing", "marketplace"],
    ),
    "fiverr": WorkstreamConfig(
        workstream_id="fiverr",
        name="Fiverr",
        description="Fiverr gig management and delivery",
        enabled=False,
        capabilities=["freelance", "service_delivery"],
    ),
    "affiliate": WorkstreamConfig(
        workstream_id="affiliate",
        name="Affiliate",
        description="Affiliate marketing and content monetization",
        enabled=False,
        capabilities=["affiliate", "content", "marketing"],
    ),
    "youtube": WorkstreamConfig(
        workstream_id="youtube",
        name="YouTube",
        description="YouTube channel management and monetization",
        enabled=False,
        capabilities=["video", "content", "youtube"],
    ),
}


def get_workstream(workstream_id: str) -> Optional[WorkstreamConfig]:
    return WORKSTREAM_REGISTRY.get(workstream_id)


def get_enabled_workstreams() -> list[WorkstreamConfig]:
    return [ws for ws in WORKSTREAM_REGISTRY.values() if ws.enabled]


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
