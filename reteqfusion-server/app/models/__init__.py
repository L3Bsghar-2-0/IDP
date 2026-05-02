"""Pydantic data models for incoming MQTT messages."""

from app.models.diagnostics import DiagnosticsMessage
from app.models.status import StatusMessage
from app.models.telemetry import Reading, TelemetryMessage

__all__ = [
    "DiagnosticsMessage",
    "Reading",
    "StatusMessage",
    "TelemetryMessage",
]
