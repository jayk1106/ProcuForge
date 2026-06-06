"""Cloud Trace span exporter that offloads oversized payloads to Cloud Logging.

Cloud Trace rejects span attributes larger than ~256 bytes. Agent traces often
carry large prompt/response payloads, so this exporter stores any oversized
attribute in Cloud Logging and replaces the span attribute with a pointer to
the log entry, keeping the trace itself within limits.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Sequence

from google.cloud import logging as google_cloud_logging
from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExportResult

# Cloud Trace attribute value limit (bytes). Stay safely below 256.
_MAX_ATTRIBUTE_BYTES = 256

_LOG = logging.getLogger(__name__)


class CloudTraceLoggingSpanExporter(CloudTraceSpanExporter):
    """Cloud Trace exporter that diverts large attributes to Cloud Logging."""

    def __init__(
        self,
        project_id: str | None = None,
        service_name: str = "agent-service",
        logging_client: google_cloud_logging.Client | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(project_id=project_id, **kwargs)
        self.project_id = project_id
        self.service_name = service_name
        self.logging_client = logging_client or google_cloud_logging.Client(
            project=project_id
        )
        self.logger = self.logging_client.logger(__name__)

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        """Export spans, offloading oversized attributes to Cloud Logging."""
        try:
            for span in spans:
                self._process_span(span)
        except Exception as exc:  # pragma: no cover - best-effort tracing
            _LOG.warning("Failed to pre-process spans for export: %s", exc)
        return super().export(spans)

    def _process_span(self, span: ReadableSpan) -> None:
        attributes = getattr(span, "_attributes", None)
        if not attributes:
            return

        for key, value in list(attributes.items()):
            if not isinstance(value, str):
                continue
            if len(value.encode("utf-8")) <= _MAX_ATTRIBUTE_BYTES:
                continue

            span_context = span.get_span_context()
            log_pointer = self._store_in_logging(
                key=key,
                value=value,
                trace_id=format(span_context.trace_id, "032x"),
                span_id=format(span_context.span_id, "016x"),
            )
            attributes[key] = log_pointer

    def _store_in_logging(
        self, key: str, value: str, trace_id: str, span_id: str
    ) -> str:
        """Write an oversized attribute to Cloud Logging and return a pointer."""
        payload = {
            "service_name": self.service_name,
            "attribute_key": key,
            "trace_id": trace_id,
            "span_id": span_id,
            "value": value,
        }
        try:
            self.logger.log_struct(payload, severity="INFO")
        except Exception as exc:  # pragma: no cover - best-effort tracing
            _LOG.warning("Failed to store oversized span attribute: %s", exc)

        return json.dumps(
            {
                "type": "cloud_logging_pointer",
                "trace_id": trace_id,
                "span_id": span_id,
                "attribute_key": key,
            }
        )
