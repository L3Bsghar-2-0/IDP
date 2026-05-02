"""Terminal rendering / ANSI formatting for ReTeqFusion subscriber.

All print_* functions accept already-parsed dicts (from parser.py) and never
raise on missing fields — they degrade gracefully to placeholders.
"""

from datetime import datetime, timezone


# ───────────────────────────── ANSI ────────────────────────────────

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
BLINK = "\033[5m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
MAGENTA = "\033[35m"
CYAN = "\033[36m"
WHITE = "\033[37m"
BRIGHT_RED = "\033[91m"


# ───────────────────────────── helpers ─────────────────────────────


def _parse_ts(ts: str) -> str:
    if not ts:
        return "timestamp unknown"
    try:
        s = ts.replace("Z", "+00:00") if ts.endswith("Z") else ts
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc)
        return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    except Exception:
        return ts


def _fmt_uptime(seconds: int) -> str:
    if seconds < 0:
        seconds = 0
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h}h {m:02d}m {s:02d}s"


def _color_quality(q: str) -> str:
    if q == "good":
        return f"{GREEN}good{RESET}"
    if q in ("bad", "failed", "error"):
        return f"{RED}{q}{RESET}"
    return f"{YELLOW}{q}{RESET}"


def _classify_ppm(ppm: float) -> tuple[str, str]:
    """Return (label, color) for an MQ-2 ppm reading."""
    if ppm < 300:
        return "SAFE", GREEN
    if ppm < 1000:
        return "LOW", YELLOW
    if ppm < 3000:
        return "ALARM", RED
    return "HAZARD", BRIGHT_RED


def _bar(pct: int, width: int = 10) -> str:
    pct = max(0, min(100, pct))
    filled = int(round(pct / (100 / width)))
    return "█" * filled + "░" * (width - filled)


# ───────────────────────────── banners ─────────────────────────────


def print_banner() -> None:
    print()
    print(f"  {BOLD}{CYAN}╔══════════════════════════════════════════╗{RESET}")
    print(f"  {BOLD}{CYAN}║   ReTeqFusion Live Subscriber — READY    ║{RESET}")
    print(f"  {BOLD}{CYAN}║   Broker : hivemq.cloud:8883  [TLS ✓]    ║{RESET}")
    print(f"  {BOLD}{CYAN}║   Waiting for ESP32 messages...          ║{RESET}")
    print(f"  {BOLD}{CYAN}╚══════════════════════════════════════════╝{RESET}")
    print()


def print_separator() -> None:
    print(f"  {DIM}{'─' * 54}{RESET}")


def print_error(msg: str) -> None:
    print(f"\n  {BOLD}{RED}✗ {msg}{RESET}\n")


def print_warning(msg: str) -> None:
    print(f"\n  {YELLOW}⚠ {msg}{RESET}")


def print_info(msg: str) -> None:
    print(f"\n  {DIM}{msg}{RESET}")


# ───────────────────────────── messages ────────────────────────────


def print_dht22(topic: str, msg: dict) -> None:
    readings = msg.get("readings") or {}
    temp = readings.get("temperature") or {}
    hum = readings.get("humidity") or {}

    device = msg.get("device_id", "?")
    site = msg.get("site", "?")
    ts_str = _parse_ts(msg.get("ts", ""))
    seq = msg.get("seq", "?")

    print(f"  {CYAN}┌─ 🌡  DHT22 Telemetry ─────────────────────────────{RESET}")
    print(f"  {CYAN}│{RESET}  Device   : {BOLD}{device}{RESET}     Site: {site}")
    print(f"  {CYAN}│{RESET}  Time     : {ts_str}    Seq: #{seq}")

    if not readings:
        print(f"  {CYAN}│{RESET}  {DIM}No readings received{RESET}")
    else:
        if temp:
            unit = temp.get("unit", "C")
            print(
                f"  {CYAN}│{RESET}  Temp     : {BOLD}{temp.get('value', '?'):.1f} °{unit}{RESET}"
                f"    [{_color_quality(temp.get('quality', 'unknown'))}]"
                if isinstance(temp.get("value"), (int, float))
                else f"  {CYAN}│{RESET}  Temp     : {DIM}{temp.get('value', '?')}{RESET}"
            )
        if hum:
            unit = hum.get("unit", "%")
            print(
                f"  {CYAN}│{RESET}  Humidity : {BOLD}{hum.get('value', '?'):.1f} {unit}{RESET}"
                f"     [{_color_quality(hum.get('quality', 'unknown'))}]"
                if isinstance(hum.get("value"), (int, float))
                else f"  {CYAN}│{RESET}  Humidity : {DIM}{hum.get('value', '?')}{RESET}"
            )
        # Render any extra readings the device added
        for name, r in readings.items():
            if name in ("temperature", "humidity"):
                continue
            v = r.get("value", "?")
            unit = r.get("unit", "")
            q = r.get("quality", "unknown")
            print(f"  {CYAN}│{RESET}  {name:<8} : {v} {unit}    [{_color_quality(q)}]")

    print(f"  {CYAN}│{RESET}  FW       : {msg.get('fw_version', 'unknown')}")
    print(f"  {CYAN}└────────────────────────────────────────────────────{RESET}")


def print_mq2(topic: str, msg: dict) -> None:
    readings = msg.get("readings") or {}
    raw_adc = readings.get("raw_adc") or {}
    voltage = readings.get("voltage") or {}
    rs_r0 = readings.get("rs_r0_ratio") or {}
    gas_ppm = readings.get("gas_ppm") or {}
    smoke = readings.get("smoke_detected") or {}

    smoke_val = smoke.get("value", 0)
    is_alarm = bool(smoke_val == 1 or smoke_val is True)

    ppm_val = gas_ppm.get("value", 0)
    ppm_num = float(ppm_val) if isinstance(ppm_val, (int, float)) else 0.0
    hazard, hazard_color = _classify_ppm(ppm_num)

    raw_adc_val = raw_adc.get("value", 0)
    raw_adc_num = int(raw_adc_val) if isinstance(raw_adc_val, (int, float)) else 0
    pct = int((raw_adc_num / 4095) * 100) if raw_adc_num else 0
    bar = _bar(pct, 10)
    bar_color = RED if is_alarm else YELLOW

    device = msg.get("device_id", "?")
    site = msg.get("site", "?")
    ts_str = _parse_ts(msg.get("ts", ""))
    seq = msg.get("seq", "?")

    if is_alarm:
        header = f"  {BOLD}{RED}{BLINK}┌─ 🚨 MQ-2 GAS ALARM ───────────────────────────────{RESET}"
        side = f"  {BOLD}{RED}│{RESET}"
        footer = f"  {BOLD}{RED}└────────────────────────────────────────────────────{RESET}"
        gas_label = (
            f"{BOLD}{RED}{ppm_num} ppm{RESET}   ← {BOLD}{RED}⚠ ALARM{RESET}"
        )
        smoke_label = f"{BOLD}{RED}🔴 YES — ALARM TRIGGERED{RESET}"
    else:
        header = f"  {YELLOW}┌─ 💨 MQ-2 Gas Sensor ──────────────────────────────{RESET}"
        side = f"  {YELLOW}│{RESET}"
        footer = f"  {YELLOW}└────────────────────────────────────────────────────{RESET}"
        q = gas_ppm.get("quality", "unknown")
        gas_label = (
            f"{BOLD}{ppm_num} ppm{RESET}   [{_color_quality(q)}]   ← {hazard_color}{hazard}{RESET}"
        )
        smoke_label = f"{GREEN}✅ NO{RESET}"

    print(header)
    print(f"{side}  Device      : {BOLD}{device}{RESET}     Site: {site}")
    print(f"{side}  Time        : {ts_str}    Seq: #{seq}")
    print(f"{side}  Gas PPM     : {gas_label}")
    print(f"{side}  Voltage     : {voltage.get('value', '?')} V")
    print(f"{side}  Rs/R0 Ratio : {rs_r0.get('value', '?')}")
    print(
        f"{side}  Raw ADC     : {raw_adc_num} / 4095  "
        f"{bar_color}[{bar}]{RESET} {pct}%"
    )
    print(f"{side}  Smoke Alert : {smoke_label}")
    print(footer)

    if is_alarm:
        banner = f"!!!!! GAS ALARM — device {device} — {ppm_num} ppm !!!!!"
        print(f"  {BOLD}{RED}{BLINK}{banner}{RESET}")


def print_status(topic: str, msg: dict) -> None:
    status = (msg.get("status") or "unknown").lower()
    is_online = status == "online"

    color = GREEN if is_online else RED
    icon = "🟢 ONLINE" if is_online else "🔴 OFFLINE"

    ts_str = _parse_ts(msg.get("ts", ""))

    print(f"  {color}┌─ 📡 Device Status ────────────────────────────────{RESET}")
    print(
        f"  {color}│{RESET}  Device : {BOLD}{msg.get('device_id', '?')}{RESET}"
        f"   →   {color}{BOLD}{icon}{RESET}"
    )
    print(
        f"  {color}│{RESET}  IP     : {msg.get('ip', '?')}     "
        f"RSSI: {msg.get('rssi', '?')} dBm"
    )
    print(f"  {color}│{RESET}  Time   : {ts_str}")
    print(f"  {color}└────────────────────────────────────────────────────{RESET}")


def print_diagnostics(topic: str, msg: dict) -> None:
    uptime = _fmt_uptime(int(msg.get("uptime_s", 0) or 0))
    free_heap = msg.get("free_heap", 0) or 0
    free_kb = free_heap / 1024
    ts_str = _parse_ts(msg.get("ts", ""))

    print(f"  {DIM}┌─ 🔧 Diagnostics ──────────────────────────────────{RESET}")
    print(f"  {DIM}│  Device       : {msg.get('device_id', '?')}{RESET}")
    print(f"  {DIM}│  Time         : {ts_str}{RESET}")
    print(f"  {DIM}│  Uptime       : {uptime}{RESET}")
    print(f"  {DIM}│  Free Heap    : {free_kb:.1f} KB{RESET}")
    print(f"  {DIM}│  WiFi RSSI    : {msg.get('wifi_rssi', '?')} dBm{RESET}")
    print(f"  {DIM}│  Reconnects   : {msg.get('mqtt_reconnects', 0)}{RESET}")
    print(f"  {DIM}│  Buffered DLQ : {msg.get('dlq_buffered', 0)}{RESET}")
    print(f"  {DIM}└────────────────────────────────────────────────────{RESET}")


def print_alert(topic: str, raw: dict) -> None:
    print(f"  {BOLD}{RED}┌─ 🚨 ALERT ────────────────────────────────────────{RESET}")
    print(f"  {BOLD}{RED}│{RESET}  Topic   : {topic}")
    if raw:
        for k, v in raw.items():
            if k.startswith("_"):
                continue
            print(f"  {BOLD}{RED}│{RESET}  {str(k):<10}: {v}")
    else:
        print(f"  {BOLD}{RED}│{RESET}  {DIM}(empty payload){RESET}")
    print(f"  {BOLD}{RED}└────────────────────────────────────────────────────{RESET}")


def print_unknown(
    topic: str, raw_payload: bytes, error: str | None
) -> None:
    try:
        payload_str = raw_payload.decode("utf-8", errors="replace") if raw_payload else "(empty)"
    except Exception:
        payload_str = repr(raw_payload)

    if len(payload_str) > 500:
        payload_str = payload_str[:500] + "...(truncated)"

    print(f"  {MAGENTA}┌─ ⚠ UNKNOWN MESSAGE ───────────────────────────────{RESET}")
    print(f"  {MAGENTA}│{RESET}  Topic   : {topic}")
    print(f"  {MAGENTA}│{RESET}  Payload : {payload_str}")
    if error:
        # Compress multi-line tracebacks to keep the box compact
        for i, line in enumerate(str(error).splitlines()):
            label = "Error  " if i == 0 else "       "
            print(f"  {MAGENTA}│{RESET}  {label} : {line}")
    print(f"  {MAGENTA}└────────────────────────────────────────────────────{RESET}")
