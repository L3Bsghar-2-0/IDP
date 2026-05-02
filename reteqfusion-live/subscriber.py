#!/usr/bin/env python3
"""ReTeqFusion Live Subscriber.

Connects to HiveMQ Cloud over TLS, subscribes to ESP32 sensor topics,
and pretty-prints every message in the terminal.

Run with:
    python subscriber.py
"""

from __future__ import annotations

import json
import signal
import ssl
import sys
import threading
import time
import traceback

# Force UTF-8 stdout so box-drawing chars and emojis render on Windows
# without the user needing to run `chcp 65001` first. Must happen before
# any print() call.
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

import paho.mqtt.client as mqtt
from paho.mqtt.client import CallbackAPIVersion

import display
import parser as msg_parser
from stats import LiveStats


# ─────────────────────── broker configuration ────────────────────────

BROKER_HOST = "e9a3ce30ae3749ab880436548931b5d0.s1.eu.hivemq.cloud"
BROKER_PORT = 8883
USERNAME = "python-server"
PASSWORD = "Python-server5"
CLIENT_ID = "reteqfusion-debug-01"

# QoS 1 wildcard subscriptions
TOPICS = [
    ("tenants/+/sites/+/devices/+/sensors/dht22/telemetry", 1),
    ("tenants/+/sites/+/devices/+/sensors/mq2/telemetry", 1),
    ("tenants/+/sites/+/devices/+/status", 1),
    ("tenants/+/sites/+/devices/+/diagnostics", 1),
    ("tenants/+/sites/+/devices/+/alerts/#", 1),
]

# Last-will: if this subscriber dies, broker publishes "offline" for us.
LWT_TOPIC = "tenants/demo/sites/lab/debug/subscriber/status"
LWT_PAYLOAD = json.dumps({"status": "offline", "client": CLIENT_ID})

STATS_INTERVAL_SEC = 10


# ───────────────────────── shared mutable state ──────────────────────

stats = LiveStats()
shutdown_event = threading.Event()
auth_failed = threading.Event()  # set on rc=5 → do not retry


# ───────────────────────────── callbacks ─────────────────────────────


def on_connect(client, userdata, flags, reason_code, properties=None):
    rc = reason_code.value if hasattr(reason_code, "value") else int(reason_code)
    if rc == 0:
        display.print_banner()
        for topic, qos in TOPICS:
            client.subscribe(topic, qos=qos)
        display.print_info(
            f"Subscribed to {len(TOPICS)} wildcard topics @ QoS 1"
        )
        return

    # MQTT v3.1.1 rc=5 / MQTT v5 rc=134/135 = bad auth
    if rc in (4, 5, 134, 135):
        display.print_error(
            f"AUTH FAILED — check credentials (rc={rc}). "
            "Will not retry — wrong credentials won't fix themselves."
        )
        auth_failed.set()
        shutdown_event.set()
    else:
        display.print_error(f"Connection refused by broker (rc={rc})")


def on_disconnect(client, userdata, *args):
    """Signature varies by callback API version, hence *args."""
    if shutdown_event.is_set():
        return
    rc = args[-1] if args else 0
    if hasattr(rc, "value"):
        rc = rc.value
    display.print_warning(
        f"🔄 Disconnected (rc={rc}) — paho will auto-reconnect with backoff."
    )


def on_message(client, userdata, message):
    """Decode → render → count. Any exception is contained here so the
    background loop never dies on a single bad payload."""
    try:
        msg_type, parsed = msg_parser.detect_message_type(
            message.topic, message.payload
        )
        stats.increment(msg_type)

        # Carriage-return-clear in case the live stats line is mid-write.
        sys.stdout.write("\r" + " " * 120 + "\r")

        if msg_type == "dht22_telemetry" and parsed:
            display.print_dht22(message.topic, parsed)
        elif msg_type == "mq2_telemetry" and parsed:
            display.print_mq2(message.topic, parsed)
        elif msg_type == "status" and parsed:
            display.print_status(message.topic, parsed)
        elif msg_type == "diagnostics" and parsed:
            display.print_diagnostics(message.topic, parsed)
        elif msg_type == "alert":
            display.print_alert(message.topic, parsed or {})
        else:
            err = None
            if isinstance(parsed, dict):
                err = parsed.get("_error") or parsed.get("_validation_error")
            display.print_unknown(message.topic, message.payload, err)

        display.print_separator()
    except Exception:
        tb = traceback.format_exc(limit=3)
        try:
            sys.stdout.write("\r" + " " * 120 + "\r")
            display.print_unknown(message.topic, message.payload, tb)
        except Exception:
            print(f"[fatal display error]\n{tb}", file=sys.stderr)
        stats.increment("unknown")


# ─────────────────────────── live stats line ─────────────────────────


def stats_loop():
    """Re-render the in-place stats line every STATS_INTERVAL_SEC seconds."""
    while not shutdown_event.wait(STATS_INTERVAL_SEC):
        line = stats.render_line()
        sys.stdout.write("\r" + line + "  ")
        sys.stdout.flush()


# ─────────────────────────── client construction ─────────────────────


def make_client(protocol) -> mqtt.Client:
    client = mqtt.Client(
        client_id=CLIENT_ID,
        protocol=protocol,
        callback_api_version=CallbackAPIVersion.VERSION2,
    )
    client.username_pw_set(USERNAME, PASSWORD)

    ctx = ssl.create_default_context()  # full cert verification — do not weaken
    client.tls_set_context(ctx)

    client.will_set(LWT_TOPIC, payload=LWT_PAYLOAD, qos=1, retain=True)
    client.reconnect_delay_set(min_delay=2, max_delay=30)

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message
    return client


def connect_with_protocol_fallback() -> mqtt.Client | None:
    """Try MQTT v5 first, fall back to v3.1.1 on protocol-level failure."""
    for proto, name in ((mqtt.MQTTv5, "MQTTv5"), (mqtt.MQTTv311, "MQTTv3.1.1")):
        try:
            client = make_client(proto)
            client.connect(BROKER_HOST, BROKER_PORT, keepalive=60)
            display.print_info(f"Connected using {name}")
            return client
        except ssl.SSLError as e:
            display.print_error(
                f"TLS FAILED — check broker URL and port (must be 8883). Detail: {e}"
            )
            return None
        except OSError as e:
            display.print_warning(
                f"{name} connect failed ({e}); trying next protocol..."
            )
            continue
        except Exception as e:
            display.print_warning(
                f"{name} connect raised {type(e).__name__}: {e}; trying next protocol..."
            )
            continue
    return None


# ─────────────────────────────── main ────────────────────────────────


def handle_sigint(signum, frame):
    shutdown_event.set()


def main() -> int:
    signal.signal(signal.SIGINT, handle_sigint)
    try:
        # SIGTERM may not exist on all platforms (it does on Windows for Py3.8+)
        signal.signal(signal.SIGTERM, handle_sigint)
    except (AttributeError, ValueError):
        pass

    # Connect with simple bounded retry (broker may be briefly unreachable).
    client: mqtt.Client | None = None
    backoff = [2, 4, 8, 16, 30]
    attempt = 0
    while not shutdown_event.is_set():
        client = connect_with_protocol_fallback()
        if client is not None:
            break
        if auth_failed.is_set():
            return 2
        attempt += 1
        delay = backoff[min(attempt - 1, len(backoff) - 1)]
        display.print_warning(
            f"Initial connect failed (attempt #{attempt}). Retrying in {delay}s..."
        )
        if shutdown_event.wait(delay):
            return 0

    if client is None:
        return 1

    client.loop_start()

    stats_thread = threading.Thread(target=stats_loop, daemon=True)
    stats_thread.start()

    try:
        while not shutdown_event.is_set():
            time.sleep(0.5)
    finally:
        sys.stdout.write("\r" + " " * 120 + "\r")
        sys.stdout.flush()
        try:
            client.loop_stop()
        except Exception:
            pass
        try:
            client.disconnect()
        except Exception:
            pass
        stats.print_summary()

    return 0


if __name__ == "__main__":
    sys.exit(main())
