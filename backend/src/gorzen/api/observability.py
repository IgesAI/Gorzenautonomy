"""Optional observability stack: Prometheus metrics + OpenTelemetry tracing.

Both integrations are soft dependencies — if the libraries are not
installed the app still boots. Enable via environment variables:

* ``GORZEN_METRICS_ENABLED=true`` — exposes ``/metrics`` in Prometheus
  text format.
* ``GORZEN_OTEL_EXPORTER_OTLP_ENDPOINT=...`` — configures the
  OpenTelemetry OTLP exporter for HTTP-server spans.

We ship built-in counters for telemetry-message rates and param writes
so operators can Grafana them without writing PromQL from scratch.
"""

from __future__ import annotations

import logging
import os
import time
from contextlib import contextmanager
from typing import Any

from fastapi import FastAPI, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Prometheus metrics (tiny self-contained implementation so we don't add a
# hard runtime dependency on ``prometheus_client``; the format we emit is
# the Prometheus text exposition v0.0.4, which scrapers understand).
# ---------------------------------------------------------------------------


class _Counter:
    def __init__(self, name: str, help_text: str) -> None:
        self.name = name
        self.help = help_text
        self._values: dict[tuple[tuple[str, str], ...], float] = {}

    def inc(self, amount: float = 1.0, **labels: str) -> None:
        key = tuple(sorted(labels.items()))
        self._values[key] = self._values.get(key, 0.0) + amount

    def render(self) -> str:
        lines = [f"# HELP {self.name} {self.help}", f"# TYPE {self.name} counter"]
        for labels, value in self._values.items():
            if labels:
                rendered = ",".join(f'{k}="{_escape(v)}"' for k, v in labels)
                lines.append(f"{self.name}{{{rendered}}} {value}")
            else:
                lines.append(f"{self.name} {value}")
        return "\n".join(lines) + "\n"


class _Gauge:
    def __init__(self, name: str, help_text: str) -> None:
        self.name = name
        self.help = help_text
        self._values: dict[tuple[tuple[str, str], ...], float] = {}

    def set(self, value: float, **labels: str) -> None:
        key = tuple(sorted(labels.items()))
        self._values[key] = float(value)

    def render(self) -> str:
        lines = [f"# HELP {self.name} {self.help}", f"# TYPE {self.name} gauge"]
        for labels, value in self._values.items():
            if labels:
                rendered = ",".join(f'{k}="{_escape(v)}"' for k, v in labels)
                lines.append(f"{self.name}{{{rendered}}} {value}")
            else:
                lines.append(f"{self.name} {value}")
        return "\n".join(lines) + "\n"


class _Histogram:
    """Minimal Prometheus histogram (fixed bucket boundaries in seconds)."""

    _DEFAULT_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10)

    def __init__(self, name: str, help_text: str) -> None:
        self.name = name
        self.help = help_text
        self._values: dict[tuple[tuple[str, str], ...], list[float]] = {}

    def observe(self, value: float, **labels: str) -> None:
        key = tuple(sorted(labels.items()))
        self._values.setdefault(key, []).append(float(value))

    def render(self) -> str:
        lines = [f"# HELP {self.name} {self.help}", f"# TYPE {self.name} histogram"]
        for labels, observations in self._values.items():
            rendered_labels = ",".join(f'{k}="{_escape(v)}"' for k, v in labels)
            label_prefix = f"{rendered_labels}," if rendered_labels else ""
            count = len(observations)
            sum_total = sum(observations)
            cumulative = 0
            for bucket in self._DEFAULT_BUCKETS:
                cumulative = sum(1 for v in observations if v <= bucket)
                lines.append(
                    f"{self.name}_bucket{{{label_prefix}le=\"{bucket}\"}} {cumulative}"
                )
            lines.append(f"{self.name}_bucket{{{label_prefix}le=\"+Inf\"}} {count}")
            lines.append(f"{self.name}_count{{{rendered_labels}}} {count}")
            lines.append(f"{self.name}_sum{{{rendered_labels}}} {sum_total}")
        return "\n".join(lines) + "\n"


def _escape(v: str) -> str:
    return str(v).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


class MetricsRegistry:
    """Single place to register and render all counters/gauges/histograms."""

    def __init__(self) -> None:
        self.http_requests_total = _Counter(
            "gorzen_http_requests_total",
            "Total HTTP requests by method, path and status",
        )
        self.http_request_duration_seconds = _Histogram(
            "gorzen_http_request_duration_seconds",
            "HTTP request duration seconds by method and path",
        )
        self.telemetry_messages_total = _Counter(
            "gorzen_telemetry_messages_total",
            "MAVLink messages received by type",
        )
        self.telemetry_link_connected = _Gauge(
            "gorzen_telemetry_link_connected",
            "1 when the FC link is live, 0 otherwise",
        )
        self.param_writes_total = _Counter(
            "gorzen_param_writes_total",
            "FC parameter writes by outcome",
        )
        self.preflight_results_total = _Counter(
            "gorzen_preflight_results_total",
            "Pre-flight checklist results by light status",
        )

    def render(self) -> str:
        parts = [
            self.http_requests_total.render(),
            self.http_request_duration_seconds.render(),
            self.telemetry_messages_total.render(),
            self.telemetry_link_connected.render(),
            self.param_writes_total.render(),
            self.preflight_results_total.render(),
        ]
        return "\n".join(parts)


metrics = MetricsRegistry()


class MetricsMiddleware(BaseHTTPMiddleware):
    """Record request counts / latency for every HTTP call."""

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        start = time.perf_counter()
        response = await call_next(request)
        duration = time.perf_counter() - start
        # Collapse path params (e.g. /twins/{id}) into their route pattern so
        # we don't blow up cardinality.
        path_template = request.scope.get("route").path if request.scope.get("route") else request.url.path
        metrics.http_requests_total.inc(
            method=request.method, path=path_template, status=str(response.status_code)
        )
        metrics.http_request_duration_seconds.observe(
            duration, method=request.method, path=path_template
        )
        return response


# ---------------------------------------------------------------------------
# OpenTelemetry tracing (soft dependency — loads only if installed).
# ---------------------------------------------------------------------------


def setup_tracing(app: FastAPI) -> None:
    """Install OpenTelemetry tracing if the libraries are available."""
    endpoint = os.environ.get("GORZEN_OTEL_EXPORTER_OTLP_ENDPOINT")
    if not endpoint:
        return
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        logger.warning(
            "GORZEN_OTEL_EXPORTER_OTLP_ENDPOINT set but OpenTelemetry libs "
            "are not installed. pip install opentelemetry-sdk "
            "opentelemetry-exporter-otlp opentelemetry-instrumentation-fastapi"
        )
        return

    resource = Resource.create({"service.name": "gorzen-backend"})
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=endpoint)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app)
    logger.info("OpenTelemetry tracing enabled → %s", endpoint)


@contextmanager
def span(name: str, **attributes: Any):
    """Context manager that opens an OpenTelemetry span when tracing is on.

    Silently no-ops when OpenTelemetry is not installed so caller code
    can use it unconditionally.
    """
    try:
        from opentelemetry import trace
    except ImportError:
        yield
        return
    tracer = trace.get_tracer("gorzen")
    with tracer.start_as_current_span(name) as sp:
        for k, v in attributes.items():
            try:
                sp.set_attribute(k, v)
            except Exception:  # pragma: no cover - OTEL raises on bad types
                pass
        yield


def mount_metrics_endpoint(app: FastAPI) -> None:
    """Attach a ``/metrics`` GET endpoint if ``GORZEN_METRICS_ENABLED``."""
    if os.environ.get("GORZEN_METRICS_ENABLED", "").lower() not in {"1", "true", "yes"}:
        return

    @app.get("/metrics")
    async def metrics_endpoint() -> Response:
        return Response(content=metrics.render(), media_type="text/plain; version=0.0.4")

    app.add_middleware(MetricsMiddleware)


__all__ = [
    "MetricsMiddleware",
    "MetricsRegistry",
    "metrics",
    "mount_metrics_endpoint",
    "setup_tracing",
    "span",
]
