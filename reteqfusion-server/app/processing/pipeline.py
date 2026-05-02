"""Orchestrates: validate → enrich → detect → store → publish alerts."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.config import Settings
from app.models.diagnostics import DiagnosticsMessage
from app.models.status import StatusMessage
from app.models.telemetry import Reading, TelemetryMessage
from app.mqtt.topic_parser import TopicInfo
from app.processing.anomaly import AnomalyDetector, AnomalyResult
from app.processing.enricher import enrich_dht22, enrich_mq2
from app.processing.validator import validate_telemetry

if TYPE_CHECKING:
    from app.mqtt.client import MqttClient
    from app.storage.device_repo import DeviceRepository
    from app.storage.dlq_repo import DlqRepository
    from app.storage.telemetry_repo import TelemetryRepository

logger = logging.getLogger(__name__)


class ProcessingPipeline:
    """Glue layer between MQTT decoder and persistence/alerting."""

    def __init__(
        self,
        *,
        telemetry_repo: "TelemetryRepository",
        dlq_repo: "DlqRepository",
        device_repo: "DeviceRepository",
        mqtt_client: "MqttClient",
        settings: Settings,
    ) -> None:
        self._telemetry = telemetry_repo
        self._dlq = dlq_repo
        self._devices = device_repo
        self._mqtt = mqtt_client
        self._settings = settings
        self._detector = AnomalyDetector(
            smoke_threshold_ppm=settings.mq2_smoke_alarm_ppm,
            hazard_threshold_ppm=settings.mq2_hazard_ppm,
        )

    # ----------------------------------------------------------- telemetry

    async def process_telemetry(
        self, info: TopicInfo, msg: TelemetryMessage, raw: str
    ) -> None:
        """Validate, enrich, persist every reading_key, run anomaly detection, alert."""
        result = validate_telemetry(msg)
        if result.flags:
            logger.info(
                "telemetry_flags",
                extra={
                    "device_id": msg.device_id,
                    "sensor_type": msg.sensor_type,
                    "flags": result.flags,
                },
            )

        cleaned = result.cleaned_readings

        # Enrichments
        dht_enrich = None
        mq2_enrich = None
        if msg.sensor_type == "dht22":
            dht_enrich = enrich_dht22(cleaned)
        else:
            mq2_enrich = enrich_mq2(
                cleaned,
                self._settings.mq2_smoke_alarm_ppm,
                self._settings.mq2_hazard_ppm,
            )

        # Persist last-seen
        await self._devices.touch_last_seen(msg.device_id, msg.ts, msg.fw_version)

        # Persist a row per reading_key
        raw_envelope = msg.model_dump(mode="json")
        for key, reading in cleaned.items():
            await self._telemetry.insert_reading(
                ts=msg.ts,
                tenant=msg.tenant,
                site=msg.site,
                device_id=msg.device_id,
                sensor_id=msg.sensor_id,
                sensor_type=msg.sensor_type,
                reading_key=key,
                value=float(reading.value),
                unit=reading.unit,
                quality=reading.quality,
                seq=msg.seq,
                fw_version=msg.fw_version,
                heat_index=getattr(dht_enrich, "heat_index", None) if msg.sensor_type == "dht22" else None,
                absolute_humidity=getattr(dht_enrich, "absolute_humidity", None) if msg.sensor_type == "dht22" else None,
                dew_point=getattr(dht_enrich, "dew_point", None) if msg.sensor_type == "dht22" else None,
                comfort_index=getattr(dht_enrich, "comfort_index", None) if msg.sensor_type == "dht22" else None,
                hazard_level=getattr(mq2_enrich, "hazard_level", None) if msg.sensor_type == "mq2" else None,
                raw_json=raw_envelope,
            )

        # Anomaly detection
        anomalies = self._detector.detect(msg, cleaned)
        for anom in anomalies:
            await self._telemetry.insert_anomaly(
                ts=anom.ts,
                device_id=anom.device_id,
                sensor_id=anom.sensor_id,
                sensor_type=anom.sensor_type,
                anomaly_type=anom.type,
                confidence=anom.confidence,
                description=anom.description,
                reading_value=anom.reading_value,
            )
            await self._handle_anomaly_publish(anom, cleaned)

    # ----------------------------------------------------------- status

    async def process_status(self, info: TopicInfo, msg: StatusMessage, raw: str) -> None:
        await self._devices.upsert_status(
            device_id=msg.device_id,
            status=msg.status,
            ts=msg.ts,
            ip=msg.ip,
            rssi=msg.rssi,
            fw_version=msg.fw_version,
        )
        logger.info(
            "device_status",
            extra={"device_id": msg.device_id, "status": msg.status, "rssi": msg.rssi},
        )

    # ------------------------------------------------------ diagnostics

    async def process_diagnostics(
        self, info: TopicInfo, msg: DiagnosticsMessage, raw: str
    ) -> None:
        await self._telemetry.insert_diagnostic(
            ts=msg.ts,
            device_id=msg.device_id,
            uptime_s=msg.uptime_s,
            free_heap=msg.free_heap,
            wifi_rssi=msg.wifi_rssi,
            mqtt_reconnects=msg.mqtt_reconnects,
            dlq_buffered=msg.dlq_buffered,
        )
        await self._devices.touch_last_seen(msg.device_id, msg.ts)

    # ----------------------------------------------------------- helpers

    async def _handle_anomaly_publish(
        self, anom: AnomalyResult, readings: dict[str, Reading]
    ) -> None:
        """Persist gas alert + publish MQTT for SMOKE_ALARM / HAZARD_ALARM."""
        if anom.type not in {"SMOKE_ALARM", "HAZARD_ALARM"}:
            return

        level = "SMOKE" if anom.type == "SMOKE_ALARM" else "HAZARD"
        gas_ppm = anom.reading_value
        await self._telemetry.insert_gas_alert(
            ts=anom.ts,
            device_id=anom.device_id,
            sensor_id=anom.sensor_id,
            level=level,
            gas_ppm=gas_ppm,
        )

        topic = (
            f"tenants/{self._settings.alert_tenant}/sites/{self._settings.alert_site}"
            f"/alerts/{anom.device_id}/gas_alarm"
        )
        payload = {
            "type": "GAS_ALARM",
            "level": level,
            "ppm": gas_ppm,
            "ts": anom.ts.isoformat(),
            "device_id": anom.device_id,
            "sensor_id": anom.sensor_id,
        }
        self._mqtt.publish(topic, payload, qos=1, retain=False)
        logger.warning("gas_alarm_published", extra={"topic": topic, **payload})
