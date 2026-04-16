"""Phase 3g regression tests — Prometheus metrics + OTEL no-op fallback + audit repo."""

from __future__ import annotations

import os

import pytest

from gorzen.api import observability


def test_metrics_registry_counter_inc() -> None:
    reg = observability.MetricsRegistry()
    reg.http_requests_total.inc(method="GET", path="/health", status="200")
    reg.http_requests_total.inc(method="GET", path="/health", status="200")
    output = reg.http_requests_total.render()
    assert 'method="GET"' in output
    assert "/health" in output
    assert "2" in output.splitlines()[-1]


def test_metrics_registry_gauge_set() -> None:
    reg = observability.MetricsRegistry()
    reg.telemetry_link_connected.set(1)
    reg.telemetry_link_connected.set(0)
    assert reg.telemetry_link_connected.render().strip().endswith("0")


def test_metrics_registry_histogram_buckets() -> None:
    reg = observability.MetricsRegistry()
    reg.http_request_duration_seconds.observe(0.004, method="GET", path="/health")
    reg.http_request_duration_seconds.observe(0.2, method="GET", path="/health")
    output = reg.http_request_duration_seconds.render()
    # Count of two observations.
    assert "gorzen_http_request_duration_seconds_count" in output
    assert "gorzen_http_request_duration_seconds_sum" in output


def test_span_noop_without_otel() -> None:
    # When OTEL isn't installed or not configured, the context manager
    # must still work as a no-op.
    with observability.span("unit-test", answer="42"):
        assert True


def test_metrics_endpoint_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi import FastAPI

    app = FastAPI()
    monkeypatch.setenv("GORZEN_METRICS_ENABLED", "true")
    observability.mount_metrics_endpoint(app)
    paths = {getattr(r, "path", None) for r in app.routes}
    assert "/metrics" in paths


def test_metrics_endpoint_off_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi import FastAPI

    app = FastAPI()
    monkeypatch.delenv("GORZEN_METRICS_ENABLED", raising=False)
    observability.mount_metrics_endpoint(app)
    paths = {getattr(r, "path", None) for r in app.routes}
    assert "/metrics" not in paths
