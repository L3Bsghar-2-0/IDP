"""Topic-pattern dispatcher: routes raw MQTT payloads into the processing pipeline."""
from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from pydantic import ValidationError

from app.models.diagnostics import DiagnosticsMessage
from app.models.status import StatusMessage
from app.models.telemetry import TelemetryMessage
from app.mqtt.legacy_translator import (
    translate_diagnostics,
    translate_status,
    translate_telemetry,
)
from app.mqtt.topic_parser import TopicInfo, parse_topic

if TYPE_CHECKING:
    from app.processing.pipeline import ProcessingPipeline
    from app.storage.dlq_repo import DlqRepository

logger = logging.getLogger(__name__)


class MessageDispatcher:
    """Decode JSON, validate against Pydantic model, and forward to the pipeline."""

    def __init__(self, pipeline: "ProcessingPipeline", dlq_repo: "DlqRepository") -> None:
        self._pipeline = pipeline
        self._dlq = dlq_repo

    async def dispatch(self, topic: str, raw_payload: str) -> None:
        """Route a single inbound MQTT message."""
        info = parse_topic(topic)

        # 1. JSON parse
        try:
            data = json.loads(raw_payload) if raw_payload else {}
        except json.JSONDecodeError as exc:
            await self._dlq.insert(topic, "json_decode_error", str(exc), raw_payload)
            logger.warning("dlq_json_decode", extra={"topic": topic, "err": str(exc)})
            return

        # 2. Route by topic kind
        try:
            if info.kind == "telemetry":
                await self._handle_telemetry(info, data, raw_payload)
            elif info.kind == "status":
                await self._handle_status(info, data, raw_payload)
            elif info.kind == "diagnostics":
                await self._handle_diagnostics(info, data, raw_payload)
            else:
                logger.debug("unknown_topic", extra={"topic": topic})
        except ValidationError as exc:
            await self._dlq.insert(topic, "validation_error", str(exc), raw_payload)
            logger.warning("dlq_validation", extra={"topic": topic})
        except Exception as exc:  # noqa: BLE001
            await self._dlq.insert(topic, "handler_error", str(exc), raw_payload)
            logger.exception("dlq_handler_error", extra={"topic": topic})

    # --------------------------------------------------------------- handlers

    async def _handle_telemetry(self, info: TopicInfo, data: dict, raw: str) -> None:
        msg = TelemetryMessage.model_validate(translate_telemetry(info, data))
        await self._pipeline.process_telemetry(info, msg, raw)

    async def _handle_status(self, info: TopicInfo, data: dict, raw: str) -> None:
        msg = StatusMessage.model_validate(translate_status(info, data))
        await self._pipeline.process_status(info, msg, raw)

    async def _handle_diagnostics(self, info: TopicInfo, data: dict, raw: str) -> None:
        msg = DiagnosticsMessage.model_validate(translate_diagnostics(info, data))
        await self._pipeline.process_diagnostics(info, msg, raw)
