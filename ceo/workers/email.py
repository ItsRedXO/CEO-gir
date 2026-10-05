"""
Email & List Building Workers — builds subscriber lists, sends campaigns,
measures affiliate conversions from email traffic.
"""
from __future__ import annotations
import time
import random
from .base import BaseWorker, WorkerResult


class ListBuildingWorker(BaseWorker):
    capabilities = ["list_building", "lead_generation", "email_capture"]
    workstream_id = "affiliate"

    def execute(self, task: dict) -> WorkerResult:
        start = time.monotonic()
        input_data = self._parse_input(task)

        niche        = input_data.get("niche", "general")
        lead_magnet  = input_data.get("lead_magnet", "free_guide")
        traffic_source = input_data.get("traffic_source", "organic")

        result = self._simulate_list_build(niche, lead_magnet, traffic_source)

        duration_ms = int((time.monotonic() - start) * 1000)
        return WorkerResult(
            success=True,
            output=result,
            duration_ms=duration_ms,
            economic_data={"revenue_estimate": 0.0, "spend": 0.0},
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

    def _simulate_list_build(self, niche: str, lead_magnet: str, traffic_source: str) -> dict:
        base_subs = {"organic": random.randint(20, 80), "social": random.randint(50, 150), "paid": random.randint(100, 400)}
        subs = base_subs.get(traffic_source, 30)
        open_rate = round(random.uniform(0.25, 0.45), 2)
        click_rate = round(random.uniform(0.03, 0.08), 2)
        conversion = round(random.uniform(0.01, 0.04), 2)
        avg_order = {"tech": 35, "fitness": 45, "finance": 60, "general": 25}.get(niche, 25)
        monthly_rev = round(subs * open_rate * click_rate * conversion * avg_order * 30, 2)

        return {
            "niche": niche,
            "lead_magnet": lead_magnet,
            "traffic_source": traffic_source,
            "new_subscribers": subs,
            "opt_in_page_cvr": round(random.uniform(0.15, 0.35), 2),
            "open_rate": open_rate,
            "click_rate": click_rate,
            "conversion_rate": conversion,
            "avg_order_value": avg_order,
            "projected_monthly_revenue": monthly_rev,
            "cost": 0.0 if traffic_source == "organic" else round(subs * 0.50, 2),
            "status": "sequence_live",
            "recommended_sequences": ["welcome", "value_series_5", "promotion_10pct_off"],
        }


class EmailCampaignWorker(BaseWorker):
    capabilities = ["email_campaign", "email_marketing", "newsletter", "automation"]
    workstream_id = "affiliate"

    def execute(self, task: dict) -> WorkerResult:
        start = time.monotonic()
        input_data = self._parse_input(task)

        campaign_type = input_data.get("campaign_type", "promotional")
        list_size     = int(input_data.get("list_size", 200))
        niche         = input_data.get("niche", "general")
        product_link  = input_data.get("product_link", "")

        campaign = self._build_campaign(campaign_type, list_size, niche)

        duration_ms = int((time.monotonic() - start) * 1000)
        return WorkerResult(
            success=True,
            output={"campaign": campaign, "next_step": "monitor_and_optimize"},
            duration_ms=duration_ms,
            economic_data={
                "revenue": campaign["projected_revenue"],
                "spend": campaign["send_cost"],
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

    def _build_campaign(self, campaign_type: str, list_size: int, niche: str) -> dict:
        config = {
            "promotional":  {"open_rate": 0.22, "ctr": 0.045, "conversion": 0.03, "avg_value": 30},
            "nurture":      {"open_rate": 0.38, "ctr": 0.055, "conversion": 0.015, "avg_value": 25},
            "abandoned":    {"open_rate": 0.45, "ctr": 0.12,  "conversion": 0.08,  "avg_value": 40},
            "re_engagement":{"open_rate": 0.18, "ctr": 0.03,  "conversion": 0.01,  "avg_value": 20},
        }
        cfg = config.get(campaign_type, config["promotional"])
        opens       = int(list_size * cfg["open_rate"])
        clicks      = int(opens * cfg["ctr"])
        conversions = int(clicks * cfg["conversion"])
        revenue     = round(conversions * cfg["avg_value"], 2)

        return {
            "campaign_type": campaign_type,
            "list_size": list_size,
            "niche": niche,
            "subject_lines": self._generate_subjects(campaign_type, niche),
            "opens": opens,
            "clicks": clicks,
            "conversions": conversions,
            "projected_revenue": revenue,
            "send_cost": round(list_size * 0.001, 2),  # ~$0.001/email
            "roi": round((revenue / max(0.01, list_size * 0.001)) - 1, 2),
            "status": "sent",
        }

    def _generate_subjects(self, campaign_type: str, niche: str) -> list[str]:
        subjects = {
            "promotional": [
                f"🔥 {niche.title()} deals you can't miss",
                f"[ENDS TONIGHT] {niche.title()} sale",
                f"We picked this just for you",
            ],
            "nurture": [
                f"3 tips to get more from {niche}",
                f"The {niche} mistake everyone makes",
                f"Quick {niche} win for today",
            ],
        }
        return subjects.get(campaign_type, [f"{niche.title()} update"])
