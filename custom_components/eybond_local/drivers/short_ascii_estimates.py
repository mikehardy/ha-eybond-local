"""Labelled short-ASCII estimates derived from wire measurements + ratings.

MX2: %×VA watts are an estimate, never measured active power. Keep wire load%
intact; do not publish tip-style ``load_power`` / silent source swaps here.
``best_available_ac_load_estimate`` is an explicitly labelled composite for
dashboards. Priority (first match wins): (1) net discharge BMS DC ≤ −25 W →
``bms_dc``; (2) Q1 %×VA → ``q1_percent``; else omit. Never rewrites pure keys.
"""

from __future__ import annotations

# Tip MX2-honest net-discharge floor: idle/charge pack power is not AC load.
_NET_DISCHARGE_THRESHOLD_W = -25.0


def estimated_ac_load_values(values: dict[str, object]) -> dict[str, object]:
    """Return ``estimated_ac_load_power`` from load% × rated VA, or omit."""
    percent = values.get("load_percent")
    rated_v = values.get("short_ascii_rated_voltage")
    rated_a = values.get("short_ascii_rated_current")
    if not isinstance(percent, (int, float)):
        return {}
    if not isinstance(rated_v, (int, float)) or not isinstance(rated_a, (int, float)):
        return {}
    return {
        "estimated_ac_load_power": round(float(rated_v) * float(rated_a) * float(percent) / 100.0, 1),
    }


def best_available_ac_load_estimate_values(values: dict[str, object]) -> dict[str, object]:
    """Composite dashboard estimate: bms_dc → q1_percent, or omit.

    Prefer ``estimated_ac_load_power`` when already present; otherwise compute the
    same load% × rated VA. Never rewrite pure measurement/estimate keys.
    """
    q1_w = values.get("estimated_ac_load_power")
    if not isinstance(q1_w, (int, float)):
        q1_w = estimated_ac_load_values(values).get("estimated_ac_load_power")

    battery_w = values.get("battery_power")
    if isinstance(battery_w, (int, float)) and float(battery_w) <= _NET_DISCHARGE_THRESHOLD_W:
        return {
            "best_available_ac_load_estimate": round(abs(float(battery_w)), 1),
            "best_available_ac_load_estimate_source": "bms_dc",
        }

    if isinstance(q1_w, (int, float)):
        return {
            "best_available_ac_load_estimate": float(q1_w),
            "best_available_ac_load_estimate_source": "q1_percent",
        }
    return {}
