"""ReTeqFusion live subscriber — connects to HiveMQ Cloud over TLS and pretty-prints
every ESP32 telemetry / status / diagnostics / alert message.

Run with:
    python subscriber.py

Dependencies:
    pip install paho-mqtt==2.1.0 pydantic==2.7.0
"""
from __future__ import annotations

import json
import os
import signal
import ssl
import sys
import threading
import time
from datetime import datetime, timezone
from typing import Any

import paho.mqtt.client as mqtt
from paho.mqtt.client import CallbackAPIVersion
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

# -----------------------------------------------------------------------------
# Broker (use exactly as given)
# -----------------------------------------------------------------------------

MQTT_HOST = "e9a3ce30ae3749ab880436548931b5d0.s1.eu.hivemq.cloud"
MQTT_PORT = 8883
MQTT_USERNAME = "python-server"
MQTT_PASSWORD = "Python-server5"
MQTT_CLIENT_ID = "reteqfusion-debug-01"
MQTT_KEEPALIVE = 60

SUBSCRIPTIONS: tuple[tuple[str, int], ...] = (
    ("tenants/+/sites/+/devices/+/sensors/dht22/telemetry", 1),
    ("tenants/+/sites/+/devices/+/sensors/mq2/telemetry", 1),
    ("tenants/+/sites/+/devices/+/status", 1),
    ("tenants/+/sites/+/devices/+/diagnostics", 1),
    ("tenants/+/sites/+/devices/+/alerts/#", 1),
)

# -----------------------------------------------------------------------------
# ANSI styling
# -----------------------------------------------------------------------------

if os.name == "nt":
    # Enable ANSI escape sequence handling on Windows 10+ consoles.
    os.system("")


class C:
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"
    BLINK   = "\033[5m"
    REV     = "\033[7m"

    BLACK   = "\033[30m"
    RED     = "\033[31m"
    GREEN   = "\033[32m"
    YELLOW  = "\033[33m"
    BLUE    = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN    = "\033[36m"
    WHITE   = "\033[37m"
    GRAY    = "\033[90m"

    BG_RED  = "\033[41m"

    CLEAR_LINE = "\033[2K"
    CURSOR_UP  = "\033[1A"


def colored(text: str, *codes: str) -> str:
    return "".join(codes) + text + C.RESET


# -----------------------------------------------------------------------------
# Pydantic models — lenient: extra="allow", coerce values defensively.
# -----------------------------------------------------------------------------


def _parse_iso(value: object) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    raise ValueError(f"unsupported ts type: {type(value).__name__}")


class Reading(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")
    value: float = 0.0
    unit: str = ""
    quality: str = "good"

    @field_validator("value", mode="before")
    @classmethod
    def _coerce(cls, v: object) -> float:
        if isinstance(v, bool):
            return float(int(v))
        if v is None:
            return 0.0
        try:
            return float(v)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return 0.0


class TelemetryMessage(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")
    schema_version: str = "1.0"
    ts: datetime
    device_id: str
    tenant: str = ""
    site: str = ""
    sensor_id: str = ""
    sensor_type: str = ""
    seq: int = 0
    readings: dict[str, Reading] = Field(default_factory=dict)
    fw_version: str = ""

    @field_validator("ts", mode="before")
    @classmethod
    def _ts(cls, v: object) -> datetime:
        return _parse_iso(v)


class StatusMessage(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")
    device_id: str
    status: str
    ts: datetime
    ip: str | None = None
    rssi: int | None = None
    fw_version: str | None = None

    @field_validator("ts", mode="before")
    @classmethod
    def _ts(cls, v: object) -> datetime:
        return _parse_iso(v)


class DiagnosticsMessage(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")
    device_id: str
    ts: datetime
    uptime_s: int = 0
    free_heap: int = 0
    wifi_rssi: int = 0
    mqtt_reconnects: int = 0
    dlq_buffered: int = 0

    @field_validator("ts", mode="before")
    @classmethod
    def _ts(cls, v: object) -> datetime:
        return _parse_iso(v)


# -----------------------------------------------------------------------------
# Counters + thread-safe stats line
# -----------------------------------------------------------------------------


class Stats:
    """Aggregate counts shown on the live stats line."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.start = time.time()
        self.total = 0
        self.dht22 = 0
        self.mq2 = 0
        self.status = 0
        self.diagnostics = 0
        self.alerts = 0
        self.smoke_alarms = 0
        self.hazard_alarms = 0
        self.unknown = 0

    def render(self) -> str:
        elapsed = max(1, int(time.time() - self.start))
        rate = self.total / elapsed
        return (
            f"{C.DIM}— live —"
            f"  total {C.RESET}{C.BOLD}{self.total:>5}{C.RESET}"
            f"{C.DIM}  ({rate:.2f} msg/s)  {C.RESET}"
            f"{C.CYAN}DHT22 {self.dht22}{C.RESET} "
            f"{C.YELLOW}MQ2 {self.mq2}{C.RESET} "
            f"{C.GREEN}STATUS {self.status}{C.RESET} "
            f"{C.GRAY}DIAG {self.diagnostics}{C.RESET} "
            f"{C.MAGENTA}ALERT {self.alerts}{C.RESET} "
            f"{C.RED}SMOKE {self.smoke_alarms} HAZARD {self.hazard_alarms}{C.RESET} "
            f"{C.MAGENTA}UNK {self.unknown}{C.RESET}"
        )


STATS = Stats()
PRINT_LOCK = threading.Lock()


def _emit_block(lines: list[str]) -> None:
    """Print a multi-line block and re-render the live stats line."""
    with PRINT_LOCK:
        # Wipe the stats line we previously left at the bottom
        sys.stdout.write("\r" + C.CLEAR_LINE)
        for line in lines:
            sys.stdout.write(line + "\n")
        sys.stdout.write(STATS.render())
        sys.stdout.flush()


def _refresh_stats_line() -> None:
    with PRINT_LOCK:
        sys.stdout.write("\r" + C.CLEAR_LINE + STATS.render())
        sys.stdout.flush()


# -----------------------------------------------------------------------------
# Formatters
# -----------------------------------------------------------------------------


def _fmt_ts(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _fmt_uptime(seconds: int) -> str:
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}h {m:02d}m {s:02d}s"


def _quality_tag(q: str) -> str:
    if q == "good":
        return colored("[good]", C.GREEN)
    if q == "uncertain":
        return colored("[uncertain]", C.YELLOW)
    return colored("[bad]", C.RED, C.BOLD)


def _hazard_tag(ppm: float) -> str:
    if ppm >= 3000:
        return colored("← ⚠ HAZARD", C.RED, C.BOLD)
    if ppm >= 1000:
        return colored("← ⚠ ALARM", C.RED, C.BOLD)
    if ppm >= 300:
        return colored("← LOW", C.YELLOW)
    return colored("← SAFE", C.GREEN)


def format_dht22(msg: TelemetryMessage) -> list[str]:
    head = colored("┌─ 🌡  DHT22 Telemetry ─────────────────────────────", C.CYAN, C.BOLD)
    foot = colored("└────────────────────────────────────────────────────", C.CYAN)

    temp_r = msg.readings.get("temperature")
    hum_r  = msg.readings.get("humidity")

    def _line(label: str, body: str) -> str:
        return colored("│  ", C.CYAN) + f"{label:<9}: {body}"

    body: list[str] = [head]
    body.append(_line("Device", f"{C.BOLD}{msg.device_id}{C.RESET}     Site: {msg.site or '-'}"))
    body.append(_line("Time", f"{_fmt_ts(msg.ts)}    Seq: #{msg.seq}"))
    if temp_r is not None:
        body.append(
            _line("Temp", f"{C.BOLD}{temp_r.value:.1f}{C.RESET} °C    {_quality_tag(temp_r.quality)}")
        )
    if hum_r is not None:
        body.append(
            _line("Humidity", f"{C.BOLD}{hum_r.value:.1f}{C.RESET} %     {_quality_tag(hum_r.quality)}")
        )
    body.append(_line("FW", msg.fw_version or "-"))
    body.append(foot)
    return body


def format_mq2(msg: TelemetryMessage) -> list[str]:
    gas      = msg.readings.get("gas_ppm")
    voltage  = msg.readings.get("voltage")
    rs_r0    = msg.readings.get("rs_r0_ratio")
    raw_adc  = msg.readings.get("raw_adc")
    smoke    = msg.readings.get("smoke_detected")

    smoke_on = bool(smoke and int(smoke.value) == 1)
    gas_ppm  = float(gas.value) if gas else 0.0

    if smoke_on:
        STATS.lock.acquire()
        try:
            STATS.smoke_alarms += 1
            if gas_ppm >= 3000:
                STATS.hazard_alarms += 1
        finally:
            STATS.lock.release()

        head_color = (C.RED, C.BOLD)
        head = colored("┌─ 🚨 MQ-2 GAS ALARM ───────────────────────────────", *head_color)
        title_alarm = True
    else:
        head_color = (C.YELLOW, C.BOLD)
        head = colored("┌─ 💨 MQ-2 Gas Sensor ──────────────────────────────", *head_color)
        title_alarm = False

    bar_color = C.RED if smoke_on else C.YELLOW
    foot = colored("└────────────────────────────────────────────────────", bar_color)

    def _line(label: str, body: str) -> str:
        return colored("│  ", bar_color) + f"{label:<12}: {body}"

    out: list[str] = [head]
    out.append(_line("Device", f"{C.BOLD}{msg.device_id}{C.RESET}     Site: {msg.site or '-'}"))
    out.append(_line("Time", f"{_fmt_ts(msg.ts)}    Seq: #{msg.seq}"))

    if gas is not None:
        ppm_str = f"{C.BOLD}{gas_ppm:.1f}{C.RESET} ppm   {_quality_tag(gas.quality)}   {_hazard_tag(gas_ppm)}"
        out.append(_line("Gas PPM", ppm_str))
    if voltage is not None:
        out.append(_line("Voltage", f"{voltage.value:.2f} V"))
    if rs_r0 is not None:
        out.append(_line("Rs/R0 Ratio", f"{rs_r0.value:.2f}"))
    if raw_adc is not None:
        out.append(_line("Raw ADC", f"{int(raw_adc.value)} / 4095"))

    if smoke_on:
        out.append(_line("Smoke Alert", colored("🔴 YES — ALARM TRIGGERED", C.RED, C.BOLD)))
    else:
        out.append(_line("Smoke Alert", colored("✅ NO", C.GREEN)))

    out.append(foot)

    if title_alarm:
        banner = (
            f" !!!!! GAS ALARM — device {msg.device_id} — {gas_ppm:.0f} ppm !!!!! "
        )
        out.append(colored(banner, C.BG_RED, C.WHITE, C.BOLD, C.BLINK))

    return out


def format_status(msg: StatusMessage) -> list[str]:
    head = colored("┌─ 📡 Device Status ────────────────────────────────", C.GREEN, C.BOLD)
    foot = colored("└────────────────────────────────────────────────────", C.GREEN)

    def _line(label: str, body: str) -> str:
        return colored("│  ", C.GREEN) + f"{label:<7}: {body}"

    if msg.status == "online":
        badge = colored("🟢 ONLINE", C.GREEN, C.BOLD)
    elif msg.status == "offline":
        badge = colored("🔴 OFFLINE", C.RED, C.BOLD)
    else:
        badge = colored(f"❓ {msg.status.upper()}", C.YELLOW, C.BOLD)

    out: list[str] = [head]
    out.append(_line("Device", f"{C.BOLD}{msg.device_id}{C.RESET}   →   {badge}"))
    if msg.ip or msg.rssi is not None:
        ip = msg.ip or "?"
        rssi = f"{msg.rssi} dBm" if msg.rssi is not None else "?"
        out.append(_line("IP", f"{ip}     RSSI: {rssi}"))
    out.append(_line("Time", _fmt_ts(msg.ts)))
    out.append(foot)
    return out


def format_diagnostics(msg: DiagnosticsMessage) -> list[str]:
    head = colored("┌─ 🔧 Diagnostics ──────────────────────────────────", C.GRAY, C.BOLD)
    foot = colored("└────────────────────────────────────────────────────", C.GRAY)

    def _line(label: str, body: str) -> str:
        return colored("│  ", C.GRAY) + colored(f"{label:<13}: {body}", C.DIM)

    out: list[str] = [head]
    out.append(_line("Device", msg.device_id))
    out.append(_line("Uptime", _fmt_uptime(int(msg.uptime_s))))
    out.append(_line("Free Heap", f"{msg.free_heap / 1024:.1f} KB"))
    out.append(_line("WiFi RSSI", f"{msg.wifi_rssi} dBm"))
    out.append(_line("Reconnects", str(msg.mqtt_reconnects)))
    out.append(_line("Buffered DLQ", str(msg.dlq_buffered)))
    out.append(foot)
    return out


def format_alert(topic: str, payload: dict[str, Any]) -> list[str]:
    head = colored("┌─ 🛎  Alert ───────────────────────────────────────", C.MAGENTA, C.BOLD)
    foot = colored("└────────────────────────────────────────────────────", C.MAGENTA)

    def _line(label: str, body: str) -> str:
        return colored("│  ", C.MAGENTA) + f"{label:<10}: {body}"

    out: list[str] = [head]
    out.append(_line("Topic", topic))
    for key in ("type", "level", "device_id", "sensor_id"):
        if key in payload:
            out.append(_line(key, str(payload[key])))
    if "ppm" in payload:
        out.append(_line("ppm", colored(str(payload["ppm"]), C.RED, C.BOLD)))
    if "value" in payload:
        out.append(_line("value", str(payload["value"])))
    if "ts" in payload:
        out.append(_line("ts", str(payload["ts"])))
    extra = {k: v for k, v in payload.items() if k not in {"type", "level", "device_id", "sensor_id", "ppm", "value", "ts"}}
    if extra:
        out.append(_line("extra", json.dumps(extra, default=str)))
    out.append(foot)
    return out


def format_unknown(topic: str, raw: str, error: str | None = None) -> list[str]:
    head = colored("┌─ ⚠ UNKNOWN MESSAGE ───────────────────────────────", C.MAGENTA, C.BOLD)
    foot = colored("└────────────────────────────────────────────────────", C.MAGENTA)

    def _line(label: str, body: str) -> str:
        return colored("│  ", C.MAGENTA) + f"{label:<8}: {body}"

    truncated = raw if len(raw) <= 500 else raw[:500] + "…"
    out: list[str] = [head]
    out.append(_line("Topic", topic))
    out.append(_line("Payload", truncated))
    if error:
        out.append(_line("Error", colored(error, C.RED)))
    out.append(foot)
    return out


# -----------------------------------------------------------------------------
# Topic dispatcher
# -----------------------------------------------------------------------------


def topic_kind(topic: str) -> str:
    parts = topic.strip("/").split("/")
    if len(parts) >= 7 and parts[0] == "tenants" and parts[2] == "sites" and parts[4] == "devices":
        if len(parts) == 7:
            if parts[6] == "status":
                return "status"
            if parts[6] == "diagnostics":
                return "diagnostics"
        if len(parts) >= 9 and parts[6] == "sensors" and parts[8] == "telemetry":
            if parts[7] == "dht22":
                return "dht22"
            if parts[7] == "mq2":
                return "mq2"
        if len(parts) >= 8 and parts[6] == "alerts":
            return "alert"
    return "unknown"


def handle_message(topic: str, raw: str) -> None:
    kind = topic_kind(topic)
    try:
        data = json.loads(raw) if raw else {}
    except json.JSONDecodeError as exc:
        STATS.lock.acquire()
        try:
            STATS.total += 1
            STATS.unknown += 1
        finally:
            STATS.lock.release()
        _emit_block(format_unknown(topic, raw, f"json: {exc}"))
        return

    try:
        if kind == "dht22":
            msg = TelemetryMessage.model_validate(data)
            STATS.lock.acquire()
            try:
                STATS.total += 1
                STATS.dht22 += 1
            finally:
                STATS.lock.release()
            _emit_block(format_dht22(msg))
        elif kind == "mq2":
            msg = TelemetryMessage.model_validate(data)
            STATS.lock.acquire()
            try:
                STATS.total += 1
                STATS.mq2 += 1
            finally:
                STATS.lock.release()
            _emit_block(format_mq2(msg))
        elif kind == "status":
            msg = StatusMessage.model_validate(data)
            STATS.lock.acquire()
            try:
                STATS.total += 1
                STATS.status += 1
            finally:
                STATS.lock.release()
            _emit_block(format_status(msg))
        elif kind == "diagnostics":
            msg = DiagnosticsMessage.model_validate(data)
            STATS.lock.acquire()
            try:
                STATS.total += 1
                STATS.diagnostics += 1
            finally:
                STATS.lock.release()
            _emit_block(format_diagnostics(msg))
        elif kind == "alert":
            STATS.lock.acquire()
            try:
                STATS.total += 1
                STATS.alerts += 1
            finally:
                STATS.lock.release()
            _emit_block(format_alert(topic, data if isinstance(data, dict) else {"raw": data}))
        else:
            STATS.lock.acquire()
            try:
                STATS.total += 1
                STATS.unknown += 1
            finally:
                STATS.lock.release()
            _emit_block(format_unknown(topic, raw))
    except ValidationError as exc:
        STATS.lock.acquire()
        try:
            STATS.total += 1
            STATS.unknown += 1
        finally:
            STATS.lock.release()
        _emit_block(format_unknown(topic, raw, f"validation: {exc.errors()[:1]}"))
    except Exception as exc:  # noqa: BLE001
        STATS.lock.acquire()
        try:
            STATS.total += 1
            STATS.unknown += 1
        finally:
            STATS.lock.release()
        _emit_block(format_unknown(topic, raw, f"error: {exc}"))


# -----------------------------------------------------------------------------
# MQTT callbacks
# -----------------------------------------------------------------------------


def on_connect(client, _userdata, _flags, reason_code, _props=None) -> None:  # type: ignore[no-untyped-def]
    if hasattr(reason_code, "is_failure") and reason_code.is_failure:
        with PRINT_LOCK:
            sys.stdout.write("\r" + C.CLEAR_LINE)
            print(colored(f"  ✗ Connect refused: {reason_code}", C.RED, C.BOLD))
        return
    if isinstance(reason_code, int) and reason_code != 0:
        with PRINT_LOCK:
            sys.stdout.write("\r" + C.CLEAR_LINE)
            print(colored(f"  ✗ Connect refused (rc={reason_code})", C.RED, C.BOLD))
        return

    with PRINT_LOCK:
        sys.stdout.write("\r" + C.CLEAR_LINE)
        banner = [
            "",
            colored("  ╔══════════════════════════════════════════╗", C.CYAN, C.BOLD),
            colored("  ║   ReTeqFusion Live Subscriber — READY    ║", C.CYAN, C.BOLD),
            colored(f"  ║   Broker : {MQTT_HOST.split('.')[1] + '.cloud'}:{MQTT_PORT}  [TLS ✓]   ║", C.CYAN),
            colored("  ║   Waiting for ESP32 messages...          ║", C.CYAN),
            colored("  ╚══════════════════════════════════════════╝", C.CYAN, C.BOLD),
            "",
        ]
        for line in banner:
            print(line)

    for topic, qos in SUBSCRIPTIONS:
        client.subscribe(topic, qos=qos)
        with PRINT_LOCK:
            print(colored(f"  ✓ subscribed  {topic}  (QoS {qos})", C.GREEN))

    _refresh_stats_line()


def on_disconnect(_client, _userdata, _flags, reason_code, _props=None) -> None:  # type: ignore[no-untyped-def]
    with PRINT_LOCK:
        sys.stdout.write("\r" + C.CLEAR_LINE)
        print(colored(f"  ⚠ disconnected (reason={reason_code}) — reconnecting…", C.YELLOW, C.BOLD))


def on_message(_client, _userdata, msg) -> None:  # type: ignore[no-untyped-def]
    try:
        raw = msg.payload.decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        raw = ""
    handle_message(msg.topic, raw)


# -----------------------------------------------------------------------------
# Live stats refresher thread (so the bottom line ticks even when idle)
# -----------------------------------------------------------------------------


def _stats_loop(stop: threading.Event) -> None:
    while not stop.wait(1.0):
        _refresh_stats_line()


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------


def _build_client() -> mqtt.Client:
    """Try MQTT v5 first; fall back to v3.1.1 if the broker rejects it."""
    try:
        client = mqtt.Client(
            callback_api_version=CallbackAPIVersion.VERSION2,
            client_id=MQTT_CLIENT_ID,
            protocol=mqtt.MQTTv5,
        )
    except Exception:  # noqa: BLE001
        client = mqtt.Client(
            callback_api_version=CallbackAPIVersion.VERSION2,
            client_id=MQTT_CLIENT_ID,
            protocol=mqtt.MQTTv311,
        )
    return client


def main() -> int:
    print(colored("  · ReTeqFusion subscriber starting…", C.DIM))

    client = _build_client()
    client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)

    ctx = ssl.create_default_context()
    ctx.check_hostname = True
    ctx.verify_mode = ssl.CERT_REQUIRED
    client.tls_set_context(ctx)

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message

    client.reconnect_delay_set(min_delay=1, max_delay=30)

    stop = threading.Event()
    refresher = threading.Thread(target=_stats_loop, args=(stop,), daemon=True, name="stats-refresher")
    refresher.start()

    def _graceful_exit(*_a) -> None:
        stop.set()
        try:
            client.disconnect()
        except Exception:  # noqa: BLE001
            pass
        with PRINT_LOCK:
            sys.stdout.write("\n" + colored("  · stopped — goodbye 👋\n", C.DIM))
            sys.stdout.flush()
        sys.exit(0)

    signal.signal(signal.SIGINT, _graceful_exit)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _graceful_exit)

    try:
        client.connect(MQTT_HOST, MQTT_PORT, keepalive=MQTT_KEEPALIVE)
    except Exception as exc:  # noqa: BLE001
        print(colored(f"  ✗ initial connect failed: {exc}", C.RED, C.BOLD))
        return 1

    try:
        client.loop_forever(retry_first_connection=True)
    except KeyboardInterrupt:
        _graceful_exit()
    finally:
        stop.set()

    return 0


if __name__ == "__main__":
    sys.exit(main())
