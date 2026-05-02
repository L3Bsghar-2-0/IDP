"""In-memory counters and live stats line for ReTeqFusion subscriber."""

from datetime import datetime


_DIM = "\033[2m"
_BOLD = "\033[1m"
_CYAN = "\033[36m"
_GREEN = "\033[32m"
_RED = "\033[31m"
_YELLOW = "\033[33m"
_RESET = "\033[0m"


class LiveStats:
    """Tracks per-message-type counters and renders status line + summary."""

    def __init__(self) -> None:
        self.total_messages: int = 0
        self.dht22_count: int = 0
        self.mq2_count: int = 0
        self.status_count: int = 0
        self.diagnostics_count: int = 0
        self.alert_count: int = 0
        self.error_count: int = 0
        self.start_time: datetime = datetime.now()

    def increment(self, message_type: str) -> None:
        self.total_messages += 1
        if message_type == "dht22_telemetry":
            self.dht22_count += 1
        elif message_type == "mq2_telemetry":
            self.mq2_count += 1
        elif message_type == "status":
            self.status_count += 1
        elif message_type == "diagnostics":
            self.diagnostics_count += 1
        elif message_type == "alert":
            self.alert_count += 1
        elif message_type == "unknown":
            self.error_count += 1

    def _uptime_str(self) -> str:
        delta = datetime.now() - self.start_time
        secs = int(delta.total_seconds())
        h = secs // 3600
        m = (secs % 3600) // 60
        s = secs % 60
        return f"{h:02d}:{m:02d}:{s:02d}"

    def render_line(self) -> str:
        return (
            f"{_DIM}📊 Stats{_RESET} │ "
            f"Msgs: {_BOLD}{self.total_messages}{_RESET} │ "
            f"DHT22: {_BOLD}{_CYAN}{self.dht22_count}{_RESET} │ "
            f"MQ2: {_BOLD}{_YELLOW}{self.mq2_count}{_RESET} │ "
            f"Alerts: {_BOLD}{_RED}{self.alert_count}{_RESET} │ "
            f"Errors: {_BOLD}{self.error_count}{_RESET} │ "
            f"Uptime: {_BOLD}{self._uptime_str()}{_RESET}"
        )

    def print_summary(self) -> None:
        print()
        print(f"  {_BOLD}{_CYAN}═══════════ Session Summary ═══════════{_RESET}")
        print(f"  Total messages   : {_BOLD}{self.total_messages}{_RESET}")
        print(f"  DHT22 readings   : {_CYAN}{self.dht22_count}{_RESET}")
        print(f"  MQ-2 readings    : {_YELLOW}{self.mq2_count}{_RESET}")
        print(f"  Status updates   : {_GREEN}{self.status_count}{_RESET}")
        print(f"  Diagnostics      : {_DIM}{self.diagnostics_count}{_RESET}")
        print(f"  Alerts           : {_RED}{self.alert_count}{_RESET}")
        print(f"  Errors / Unknown : {self.error_count}")
        print(f"  Total uptime     : {_BOLD}{self._uptime_str()}{_RESET}")
        print(f"  {_BOLD}{_CYAN}═══════════════════════════════════════{_RESET}")
        print()
