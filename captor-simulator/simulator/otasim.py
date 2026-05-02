"""OTA (Over-The-Air) update simulation for virtual devices.

This module simulates the OTA update workflow on virtual devices:
- Tracks firmware version per device
- Simulates update checks (polling mechanism)
- Simulates OTA updates with version transitions
- Tracks boot count and simulates rollback behavior
- Injects update failures based on configuration
"""

import json
import logging
import random
import time
from dataclasses import dataclass, field
from typing import Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class OTAState:
    """Tracks OTA state for a single simulated device."""

    device_id: str
    current_version: str = "1.0.0"
    last_attempted_version: str = "1.0.0"
    boot_count: int = 0
    update_count: int = 0
    error_count: int = 0
    last_check_time: float = field(default_factory=time.time)
    state: str = "IDLE"  # IDLE, CHECKING, DOWNLOADING, VERIFYING, FLASHING, REBOOTING, ERROR
    state_enter_time: float = field(default_factory=time.time)


class OTASimulator:
    """Simulates OTA behavior for a fleet of devices."""

    def __init__(
        self,
        enabled: bool = True,
        update_interval_s: int = 3600,
        failure_rate: float = 0.05,
        available_versions: Optional[list] = None,
    ) -> None:
        """Initialize OTA simulator.

        Args:
            enabled: Enable/disable OTA simulation
            update_interval_s: How often to check for updates (seconds)
            failure_rate: Probability (0-1) that an update will fail
            available_versions: List of firmware versions that can be deployed
                               (default: ["1.0.0", "1.0.1", "1.1.0", "2.0.0"])
        """
        self.enabled = enabled
        self.update_interval_s = update_interval_s
        self.failure_rate = max(0.0, min(1.0, failure_rate))
        self.available_versions = available_versions or ["1.0.0", "1.0.1", "1.1.0", "2.0.0"]
        self.device_states: Dict[str, OTAState] = {}
        self.active_deployments: Dict[str, str] = {}  # device_id -> target_version

    def initialize_device(self, device_id: str, initial_version: str = "1.0.0") -> None:
        """Initialize OTA state for a device.

        Args:
            device_id: Unique device identifier
            initial_version: Starting firmware version
        """
        if device_id not in self.device_states:
            self.device_states[device_id] = OTAState(
                device_id=device_id,
                current_version=initial_version,
                last_attempted_version=initial_version,
            )
            logger.info(f"[OTA] initialized device {device_id} with version {initial_version}")

    def trigger_update(self, device_id: str, target_version: str) -> bool:
        """Trigger an update to a specific device.

        Args:
            device_id: Device to update
            target_version: Target firmware version

        Returns:
            True if update was triggered, False if device not found
        """
        if device_id not in self.device_states:
            logger.warning(f"[OTA] device {device_id} not found")
            return False

        if target_version not in self.available_versions:
            logger.warning(f"[OTA] version {target_version} not available")
            return False

        state = self.device_states[device_id]
        if self._is_version_newer(target_version, state.current_version):
            self.active_deployments[device_id] = target_version
            state.last_attempted_version = target_version
            logger.info(f"[OTA] triggered update: {device_id} {state.current_version} → {target_version}")
            return True
        else:
            logger.warning(
                f"[OTA] target version {target_version} not newer than "
                f"current {state.current_version}"
            )
            return False

    def tick(self, device_id: str) -> Optional[Dict[str, any]]:
        """Simulate one tick of OTA state machine for a device.

        Returns:
            Dictionary with OTA event (update_available, update_complete, update_failed, etc.)
            or None if no event occurred.
        """
        if not self.enabled or device_id not in self.device_states:
            return None

        state = self.device_states[device_id]
        now = time.time()

        # Check if a deployment is active for this device
        if device_id in self.active_deployments:
            target_version = self.active_deployments[device_id]
            return self._simulate_active_deployment(state, target_version, now)

        # Periodic check for updates (polling mechanism)
        if now - state.last_check_time >= self.update_interval_s:
            state.last_check_time = now
            return self._simulate_polling_check(state, now)

        return None

    def _simulate_active_deployment(
        self, state: OTAState, target_version: str, now: float
    ) -> Optional[Dict[str, any]]:
        """Simulate an active deployment to a device."""

        # Transition through OTA state machine
        if state.state == "IDLE":
            state.state = "DOWNLOADING"
            state.state_enter_time = now
            state.update_count += 1
            return {
                "event": "update_started",
                "device_id": state.device_id,
                "target_version": target_version,
                "state": "DOWNLOADING",
            }

        elif state.state == "DOWNLOADING":
            # Simulate download taking 2-5 seconds
            if now - state.state_enter_time >= random.uniform(2, 5):
                state.state = "VERIFYING"
                state.state_enter_time = now
                return {
                    "event": "download_complete",
                    "device_id": state.device_id,
                    "target_version": target_version,
                    "state": "VERIFYING",
                }

        elif state.state == "VERIFYING":
            # Simulate signature verification (instant or very fast)
            if now - state.state_enter_time >= 0.1:
                # Check if this update should fail
                if random.random() < self.failure_rate:
                    state.error_count += 1
                    state.state = "ERROR"
                    state.state_enter_time = now
                    del self.active_deployments[state.device_id]
                    return {
                        "event": "update_failed",
                        "device_id": state.device_id,
                        "target_version": target_version,
                        "reason": "signature_verification_failed",
                        "error_count": state.error_count,
                    }

                state.state = "FLASHING"
                state.state_enter_time = now
                return {
                    "event": "signature_verified",
                    "device_id": state.device_id,
                    "target_version": target_version,
                    "state": "FLASHING",
                }

        elif state.state == "FLASHING":
            # Simulate flashing taking 3-8 seconds
            if now - state.state_enter_time >= random.uniform(3, 8):
                state.state = "REBOOTING"
                state.state_enter_time = now
                return {
                    "event": "flash_complete",
                    "device_id": state.device_id,
                    "target_version": target_version,
                    "state": "REBOOTING",
                }

        elif state.state == "REBOOTING":
            # Simulate reboot taking 1-2 seconds
            if now - state.state_enter_time >= random.uniform(1, 2):
                # Successfully update to target version
                state.current_version = target_version
                state.boot_count = 0
                state.state = "IDLE"
                del self.active_deployments[state.device_id]
                return {
                    "event": "update_complete",
                    "device_id": state.device_id,
                    "current_version": target_version,
                    "boot_count": 0,
                }

        elif state.state == "ERROR":
            # Return to idle after error delay
            if now - state.state_enter_time >= 5:
                state.state = "IDLE"

        return None

    def _simulate_polling_check(self, state: OTAState, now: float) -> Optional[Dict[str, any]]:
        """Simulate a polling check for updates."""

        # Find a newer available version (randomly select one)
        newer_versions = [v for v in self.available_versions if self._is_version_newer(v, state.current_version)]

        if newer_versions:
            # Randomly select a newer version to offer
            target = random.choice(newer_versions)
            return {
                "event": "update_available",
                "device_id": state.device_id,
                "current_version": state.current_version,
                "available_version": target,
            }

        return {
            "event": "check_complete",
            "device_id": state.device_id,
            "current_version": state.current_version,
            "status": "up_to_date",
        }

    def get_state(self, device_id: str) -> Optional[Dict[str, any]]:
        """Get current OTA state for a device."""
        if device_id not in self.device_states:
            return None

        state = self.device_states[device_id]
        return {
            "device_id": state.device_id,
            "current_version": state.current_version,
            "last_attempted_version": state.last_attempted_version,
            "boot_count": state.boot_count,
            "update_count": state.update_count,
            "error_count": state.error_count,
            "state": state.state,
        }

    def _is_version_newer(self, incoming: str, current: str) -> bool:
        """Check if incoming version is newer than current version (semantic versioning)."""
        try:
            incoming_parts = tuple(map(int, incoming.split(".")))
            current_parts = tuple(map(int, current.split(".")))

            # Pad with zeros if lengths differ
            max_len = max(len(incoming_parts), len(current_parts))
            incoming_parts = incoming_parts + (0,) * (max_len - len(incoming_parts))
            current_parts = current_parts + (0,) * (max_len - len(current_parts))

            return incoming_parts > current_parts
        except (ValueError, AttributeError):
            return False
