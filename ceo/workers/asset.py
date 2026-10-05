"""
Asset Worker — generates and manages digital assets (images, documents, templates).
Used for Etsy digital products and content creation pipelines.
"""
from __future__ import annotations
import time
import hashlib
from .base import BaseWorker, WorkerResult


class DigitalAssetWorker(BaseWorker):
    capabilities = ["asset_creation", "digital_products", "design", "templates"]
    workstream_id = "assets"

    def execute(self, task: dict) -> WorkerResult:
        start = time.monotonic()
        input_data = self._parse_input(task)

        asset_type = input_data.get("asset_type", "printable")
        style = input_data.get("style", "minimal")
        format_type = input_data.get("format", "pdf")
        dimensions = input_data.get("dimensions", "8.5x11")

        asset_id = self._generate_asset_id(task.get("task_id", ""), asset_type, style)

        output = {
            "asset_id": asset_id,
            "asset_type": asset_type,
            "style": style,
            "format": format_type,
            "dimensions": dimensions,
            "files": self._get_file_manifest(asset_type, format_type, dimensions),
            "quality_score": self._estimate_quality(asset_type, style),
            "marketplace_ready": True,
            "status": "generated",
            "storage_path": f"assets/{asset_id}/",
        }

        duration_ms = int((time.monotonic() - start) * 1000)
        return WorkerResult(
            success=True,
            output=output,
            duration_ms=duration_ms,
            economic_data={"revenue_estimate": 0.0, "spend": 0.01},
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

    def _generate_asset_id(self, task_id: str, asset_type: str, style: str) -> str:
        raw = f"{task_id}:{asset_type}:{style}"
        return hashlib.sha256(raw.encode()).hexdigest()[:12]

    def _get_file_manifest(self, asset_type: str, format_type: str, dimensions: str) -> list[dict]:
        manifests = {
            "printable": [
                {"file": f"main.{format_type}", "dpi": 300, "size_mb": 2.1},
                {"file": f"preview.jpg", "dpi": 72, "size_mb": 0.3},
                {"file": "instructions.txt", "dpi": None, "size_mb": 0.01},
            ],
            "svg": [
                {"file": "main.svg", "dpi": None, "size_mb": 0.2},
                {"file": "preview.png", "dpi": 72, "size_mb": 0.4},
                {"file": "license.txt", "dpi": None, "size_mb": 0.01},
            ],
            "planner": [
                {"file": f"planner.{format_type}", "dpi": 300, "size_mb": 5.2},
                {"file": "cover.jpg", "dpi": 72, "size_mb": 0.5},
                {"file": "instructions.pdf", "dpi": 150, "size_mb": 0.8},
            ],
        }
        return manifests.get(asset_type, [{"file": f"output.{format_type}", "dpi": 300, "size_mb": 1.0}])

    def _estimate_quality(self, asset_type: str, style: str) -> float:
        base = {"printable": 0.85, "svg": 0.90, "planner": 0.80}
        style_boost = {"minimal": 0.05, "modern": 0.03, "boho": 0.02}
        return min(1.0, base.get(asset_type, 0.75) + style_boost.get(style, 0.0))


class ContentAssetWorker(BaseWorker):
    capabilities = ["content_assets", "thumbnails", "social_graphics", "media"]
    workstream_id = "content"

    def execute(self, task: dict) -> WorkerResult:
        start = time.monotonic()
        input_data = self._parse_input(task)

        content_type = input_data.get("content_type", "thumbnail")
        platform = input_data.get("platform", "youtube")
        topic = input_data.get("topic", task.get("title", "content"))

        specs = self._get_platform_specs(platform, content_type)
        asset_id = hashlib.sha256(f"{task.get('task_id','')}:{platform}:{content_type}".encode()).hexdigest()[:12]

        output = {
            "asset_id": asset_id,
            "content_type": content_type,
            "platform": platform,
            "topic": topic,
            "dimensions": specs["dimensions"],
            "format": specs["format"],
            "files": [
                {"file": f"{content_type}_{platform}.{specs['format']}", "dimensions": specs["dimensions"]},
            ],
            "status": "generated",
            "ctr_estimate": self._estimate_ctr(content_type, platform),
        }

        duration_ms = int((time.monotonic() - start) * 1000)
        return WorkerResult(
            success=True,
            output=output,
            duration_ms=duration_ms,
            economic_data={"revenue_estimate": 0.0, "spend": 0.005},
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

    def _get_platform_specs(self, platform: str, content_type: str) -> dict:
        specs = {
            "youtube": {"thumbnail": {"dimensions": "1280x720", "format": "jpg"}},
            "instagram": {"post": {"dimensions": "1080x1080", "format": "jpg"}, "story": {"dimensions": "1080x1920", "format": "jpg"}},
            "tiktok": {"cover": {"dimensions": "1080x1920", "format": "jpg"}},
            "twitter": {"card": {"dimensions": "1200x628", "format": "jpg"}},
        }
        return specs.get(platform, {}).get(content_type, {"dimensions": "1200x630", "format": "jpg"})

    def _estimate_ctr(self, content_type: str, platform: str) -> float:
        base_ctr = {"youtube": 0.045, "instagram": 0.032, "tiktok": 0.051}
        return base_ctr.get(platform, 0.03)
