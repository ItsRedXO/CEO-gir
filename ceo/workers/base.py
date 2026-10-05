from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class WorkerResult:
    success: bool
    output: dict = field(default_factory=dict)
    error: Optional[str] = None
    duration_ms: Optional[int] = None
    economic_data: Optional[dict] = None

    @property
    def failure_type(self) -> Optional[str]:
        if not self.success and self.error:
            if any(k in self.error.lower() for k in ("timeout", "connection", "network")):
                return "transient"
            if any(k in self.error.lower() for k in ("permission", "auth", "forbidden")):
                return "permanent"
        return "unknown" if not self.success else None


class BaseWorker(ABC):
    capabilities: list[str] = []
    workstream_id: str = "base"

    @abstractmethod
    def execute(self, task: dict) -> WorkerResult:
        pass

    def can_handle(self, required_capabilities: list[str]) -> bool:
        return all(cap in self.capabilities for cap in required_capabilities)
