import pytest
from ceo.workers.base import BaseWorker, WorkerResult
from ceo.workers.research import ResearchWorker, ContentWorker, OptimizationWorker
from ceo.workstreams.registry import (
    get_workstream, get_enabled_workstreams, find_worker_for_capabilities, route_task,
    WORKSTREAM_REGISTRY,
)


class TestWorkerResult:
    def test_success_result(self):
        r = WorkerResult(success=True, output={"x": 1})
        assert r.success is True
        assert r.failure_type is None

    def test_failure_result_with_transient_error(self):
        r = WorkerResult(success=False, error="connection timeout")
        assert r.failure_type == "transient"

    def test_failure_result_with_permanent_error(self):
        r = WorkerResult(success=False, error="permission denied")
        assert r.failure_type == "permanent"

    def test_failure_result_unknown(self):
        r = WorkerResult(success=False, error="something weird happened")
        assert r.failure_type == "unknown"

    def test_duration_ms(self):
        r = WorkerResult(success=True, duration_ms=150)
        assert r.duration_ms == 150


class TestResearchWorker:
    def test_capabilities(self):
        w = ResearchWorker()
        assert "research" in w.capabilities
        assert "analysis" in w.capabilities

    def test_execute_returns_result(self):
        w = ResearchWorker()
        task = {"title": "Market research", "input_json": {"topic": "Etsy opportunities"}}
        result = w.execute(task)
        assert result.success is True
        assert "findings" in result.output

    def test_execute_with_empty_input(self):
        w = ResearchWorker()
        result = w.execute({"title": "Research", "input_json": {}})
        assert result.success is True

    def test_can_handle_research(self):
        w = ResearchWorker()
        assert w.can_handle(["research"])
        assert w.can_handle(["research", "analysis"])
        assert not w.can_handle(["listing"])


class TestContentWorker:
    def test_capabilities(self):
        w = ContentWorker()
        assert "content" in w.capabilities
        assert "writing" in w.capabilities

    def test_execute_returns_result(self):
        w = ContentWorker()
        task = {"title": "Blog post", "input_json": {"content_type": "article", "topic": "side hustles"}}
        result = w.execute(task)
        assert result.success is True
        assert result.output["content_type"] == "article"

    def test_economic_data_in_result(self):
        w = ContentWorker()
        result = w.execute({"title": "Content", "input_json": {}})
        assert result.economic_data is not None


class TestOptimizationWorker:
    def test_capabilities(self):
        w = OptimizationWorker()
        assert "optimization" in w.capabilities
        assert "scaling" in w.capabilities

    def test_execute(self):
        w = OptimizationWorker()
        result = w.execute({"title": "Optimize", "input_json": {}})
        assert result.success is True


class TestWorkstreamRegistry:
    def test_get_known_workstream(self):
        ws = get_workstream("research")
        assert ws is not None
        assert ws.workstream_id == "research"

    def test_get_unknown_workstream(self):
        assert get_workstream("nonexistent") is None

    def test_get_enabled_workstreams(self):
        enabled = get_enabled_workstreams()
        assert len(enabled) > 0
        assert all(ws.enabled for ws in enabled)

    def test_research_is_enabled(self):
        ws = get_workstream("research")
        assert ws.enabled is True

    def test_etsy_is_in_registry(self):
        ws = get_workstream("etsy")
        assert ws is not None
        assert ws.workstream_id == "etsy"

    def test_fiverr_is_in_registry(self):
        ws = get_workstream("fiverr")
        assert ws is not None
        assert ws.workstream_id == "fiverr"

    def test_find_worker_for_research(self):
        worker = find_worker_for_capabilities(["research"])
        assert worker is not None
        assert isinstance(worker, ResearchWorker)

    def test_find_worker_for_content(self):
        worker = find_worker_for_capabilities(["content"])
        assert worker is not None

    def test_find_worker_for_unknown_cap(self):
        worker = find_worker_for_capabilities(["nonexistent_cap"])
        assert worker is None

    def test_route_task_by_workstream_id(self):
        task = {"workstream_id": "research", "required_capabilities": []}
        worker = route_task(task)
        assert isinstance(worker, ResearchWorker)

    def test_route_task_by_capability(self):
        task = {"workstream_id": None, "required_capabilities": ["research", "analysis"]}
        worker = route_task(task)
        assert worker is not None

    def test_route_task_unknown_returns_none(self):
        task = {"workstream_id": None, "required_capabilities": ["nonexistent_xyz_cap_12345"]}
        worker = route_task(task)
        assert worker is None

    def test_route_task_etsy_returns_worker(self):
        from ceo.workers.listing import EtsyListingWorker
        task = {"workstream_id": "etsy", "required_capabilities": ["listing"]}
        worker = route_task(task)
        assert isinstance(worker, EtsyListingWorker)

    def test_all_workstreams_in_registry(self):
        expected = {"research", "content", "optimization", "etsy", "fiverr", "affiliate", "youtube"}
        assert expected.issubset(set(WORKSTREAM_REGISTRY.keys()))
