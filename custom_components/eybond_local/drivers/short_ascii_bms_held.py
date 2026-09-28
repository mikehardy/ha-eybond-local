"""Labelled BMS held estimates — mirror live, hold across link-loss gaps.

MX2/ADR 0003: measurement keys stay omit-on-loss (never look fresh). These
``*_held_estimate`` keys are explicitly labelled estimates for dashboards and
for best-available load imputation.

TTL 180 s ≈ site p90–p95 BMS-unavailable gap coverage without holding forever.
"""

from __future__ import annotations

from dataclasses import dataclass, field

STATE_KEY = "short_ascii_bms_held"
HELD_TTL_S = 180.0

# Keys withdrawn when RB reports link-loss (V=0∧SoC=0) / omit path.
BMS_HOLD_KEYS: tuple[str, ...] = (
    "bms_total_voltage",
    "battery_soc",
    "bms_charging_current",
    "bms_discharging_current",
    "battery_power",
    "bms_cell_temperature",
    "bms_cycle_count",
    "bms_internal_temperature",
    "bms_mos_temperature",
    "bms_max_cell_voltage",
    "bms_min_cell_voltage",
    "bms_low_protection_voltage",
    "bms_charge_cutoff_voltage",
    "short_ascii_bms_charge_path_enabled",
    "short_ascii_bms_discharge_path_enabled",
)

BINARY_HOLD_KEYS = frozenset({
    "short_ascii_bms_charge_path_enabled",
    "short_ascii_bms_discharge_path_enabled",
})


def held_estimate_key(source_key: str) -> str:
    return f"{source_key}_held_estimate"


def _live_bms_snapshot(values: dict[str, object]) -> dict[str, object] | None:
    """Return holdable live keys, or None when BMS measurements are absent."""
    if values.get("short_ascii_bms_data_available") is not True:
        return None
    voltage = values.get("bms_total_voltage")
    if not isinstance(voltage, (int, float)):
        return None
    snap = {key: values[key] for key in BMS_HOLD_KEYS if key in values}
    return snap or None


@dataclass
class BmsHeldEstimates:
    """Runtime cache of last-good BMS fields (not persisted)."""

    values: dict[str, object] = field(default_factory=dict)
    sampled_at: float | None = None

    def clear(self) -> None:
        self.values.clear()
        self.sampled_at = None

    def apply(self, live_values: dict[str, object], now: float) -> dict[str, object]:
        """Publish ``*_held_estimate`` mirrors (live) or holds (gap ≤ TTL)."""
        live = _live_bms_snapshot(live_values)
        if live is not None:
            self.values = dict(live)
            self.sampled_at = now
            mode = "live"
            age = 0.0
        elif (
            self.sampled_at is not None
            and self.values
            and 0.0 <= now - self.sampled_at < HELD_TTL_S
        ):
            mode = "held"
            age = now - self.sampled_at
        else:
            self.clear()
            return {}

        out: dict[str, object] = {
            held_estimate_key(key): value for key, value in self.values.items()
        }
        out["bms_held_estimate_age_seconds"] = round(age, 1)
        out["bms_held_estimate_mode"] = mode
        return out


def bms_held_for(runtime_state: dict) -> BmsHeldEstimates:
    held = runtime_state.get(STATE_KEY)
    if type(held) is not BmsHeldEstimates:
        held = BmsHeldEstimates()
        runtime_state[STATE_KEY] = held
    return held
