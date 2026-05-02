"""TLS-secured paho-mqtt client running in a background thread.

Bridges incoming messages onto an asyncio.Queue consumed by the FastAPI loop.
"""
from __future__ import annotations

import asyncio
import json
import logging
import ssl
import threading
import time
from typing import Optional

import paho.mqtt.client as mqtt
from paho.mqtt.client import CallbackAPIVersion

from app.config import Settings

logger = logging.getLogger(__name__)


SUBSCRIPTIONS: tuple[tuple[str, int], ...] = (
    ("tenants/+/sites/+/devices/+/sensors/dht22/telemetry", 1),
    ("tenants/+/sites/+/devices/+/sensors/mq2/telemetry", 1),
    ("tenants/+/sites/+/devices/+/status", 1),
    ("tenants/+/sites/+/devices/+/diagnostics", 1),
)


class MqttClient:
    """Paho MQTT client wrapper with TLS, auth, reconnect, and asyncio bridge."""

    def __init__(
        self,
        settings: Settings,
        queue: asyncio.Queue,
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        self._settings = settings
        self._queue = queue
        self._loop = loop
        self._client: mqtt.Client = mqtt.Client(
            callback_api_version=CallbackAPIVersion.VERSION2,
            client_id=settings.mqtt_client_id,
            clean_session=False,
            protocol=mqtt.MQTTv311,
        )
        self._client.username_pw_set(settings.mqtt_username, settings.mqtt_password)

        if settings.mqtt_tls:
            ctx = ssl.create_default_context()
            ctx.check_hostname = True
            ctx.verify_mode = ssl.CERT_REQUIRED
            self._client.tls_set_context(ctx)

        # Last-will published if we drop unexpectedly
        self._will_topic = (
            f"servers/{settings.mqtt_client_id}/status"
        )
        self._client.will_set(
            self._will_topic,
            payload=json.dumps({"status": "offline", "client_id": settings.mqtt_client_id}),
            qos=1,
            retain=True,
        )

        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message

        self._stop_evt = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._connected = False

    # ------------------------------------------------------------------ public

    def start(self) -> None:
        """Spawn the background networking thread."""
        self._thread = threading.Thread(target=self._run, name="mqtt-client", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Disconnect and stop the background thread."""
        self._stop_evt.set()
        try:
            self._client.disconnect()
        except Exception:  # noqa: BLE001
            pass
        try:
            self._client.loop_stop()
        except Exception:  # noqa: BLE001
            pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)

    def is_connected(self) -> bool:
        """Return True if the client currently has an active broker connection."""
        return self._connected

    def publish(self, topic: str, payload: dict | str, qos: int = 1, retain: bool = False) -> None:
        """Thread-safe publish; serializes dicts to JSON automatically."""
        body = payload if isinstance(payload, str) else json.dumps(payload, default=str)
        try:
            info = self._client.publish(topic, body, qos=qos, retain=retain)
            if info.rc != mqtt.MQTT_ERR_SUCCESS:
                logger.warning("mqtt_publish_failed", extra={"topic": topic, "rc": info.rc})
        except Exception as exc:  # noqa: BLE001
            logger.exception("mqtt_publish_exception", extra={"topic": topic, "err": str(exc)})

    # ----------------------------------------------------------------- private

    def _run(self) -> None:
        """Connect-with-backoff loop."""
        delay = 1.0
        while not self._stop_evt.is_set():
            try:
                logger.info(
                    "mqtt_connecting",
                    extra={
                        "host": self._settings.mqtt_host,
                        "port": self._settings.mqtt_port,
                        "tls": self._settings.mqtt_tls,
                    },
                )
                self._client.connect(
                    self._settings.mqtt_host,
                    self._settings.mqtt_port,
                    keepalive=self._settings.mqtt_keepalive,
                )
                # Blocking network loop; returns on disconnect / stop
                self._client.loop_forever(retry_first_connection=False)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "mqtt_connect_error",
                    extra={"err": str(exc), "retry_in_s": delay},
                )
            finally:
                self._connected = False

            if self._stop_evt.is_set():
                break

            # Exponential backoff up to 30 s
            time.sleep(delay)
            delay = min(delay * 2.0, 30.0)

    # paho-mqtt v2 callbacks (CallbackAPIVersion.VERSION2)

    def _on_connect(self, client, _userdata, _flags, reason_code, _props=None) -> None:  # type: ignore[no-untyped-def]
        if reason_code == 0 or (hasattr(reason_code, "is_failure") and not reason_code.is_failure):
            self._connected = True
            logger.info("mqtt_connected", extra={"client_id": self._settings.mqtt_client_id})
            for topic, qos in SUBSCRIPTIONS:
                client.subscribe(topic, qos=qos)
                logger.info("mqtt_subscribed", extra={"topic": topic, "qos": qos})
            # Announce online
            self.publish(
                self._will_topic,
                {"status": "online", "client_id": self._settings.mqtt_client_id},
                qos=1,
                retain=True,
            )
        else:
            logger.error("mqtt_connect_refused", extra={"reason_code": str(reason_code)})

    def _on_disconnect(self, _client, _userdata, _flags, reason_code, _props=None) -> None:  # type: ignore[no-untyped-def]
        self._connected = False
        logger.warning("mqtt_disconnected", extra={"reason_code": str(reason_code)})

    def _on_message(self, _client, _userdata, msg) -> None:  # type: ignore[no-untyped-def]
        """Forward incoming message onto the asyncio queue (thread → loop)."""
        try:
            payload = msg.payload.decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            payload = ""
        try:
            asyncio.run_coroutine_threadsafe(
                self._queue.put((msg.topic, payload)),
                self._loop,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("mqtt_enqueue_failed", extra={"topic": msg.topic, "err": str(exc)})
