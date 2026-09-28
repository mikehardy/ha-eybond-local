"""Labelled short-ASCII estimates derived from wire measurements + ratings.

MX2: %×VA watts are an estimate, never measured active power. Keep wire load%
intact; do not publish tip-style ``load_power`` / silent source swaps here.
``best_available_ac_load_estimate`` is an explicitly labelled composite for
dashboards. Priority (first match wins), only after Q1 is silent (≤ 0 W):
(1) Q1 %×VA when reporting load (> 0 W) → ``q1_percent``;
(2) net BMS discharge ≤ −25 W → ``bms_dc``, or ``bms_dc_plus_pv`` when PV > 0;
(3) net BMS charge (> 0 W) with PV > 0 → ``max(0, pv − charge)`` as
    ``pv_minus_charge``;
(4) else Q1 including 0 W, or omit. Never rewrites pure keys.

BMS watts prefer live ``battery_power``; if omitted (link-loss), fall back to
``battery_power_held_estimate`` (≤180 s) and tag source with ``_held``.
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


def _q1_load_watts(values: dict[str, object]) -> float | None:
    q1_w = values.get("estimated_ac_load_power")
    if not isinstance(q1_w, (int, float)):
        q1_w = estimated_ac_load_values(values).get("estimated_ac_load_power")
    if isinstance(q1_w, (int, float)):
        return float(q1_w)
    return None


def _battery_watts(values: dict[str, object]) -> tuple[float | None, bool]:
    """Return (watts, from_held). Live measurement wins over held estimate."""
    live = values.get("battery_power")
    if isinstance(live, (int, float)):
        return float(live), False
    held = values.get("battery_power_held_estimate")
    if isinstance(held, (int, float)):
        return float(held), True
    return None, False


def best_available_ac_load_estimate_values(values: dict[str, object]) -> dict[str, object]:
    """Composite dashboard estimate for house AC demand.

    Prefer ``estimated_ac_load_power`` when already present; otherwise compute the
    same load% × rated VA. Never rewrite pure measurement/estimate keys.

    BMS / PV imputes run only when Q1 reports 0 W / is missing — Q1 is the
    house-AC signal when the inverter publishes load. Silent-Q1 cases:

    - Discharging: ``|battery|`` (+ PV if PV > 0; PV is consumed, not stored).
    - Charging + PV: ``max(0, pv − charge)`` — leftover PV after the pack takes
      what it can is house load (BMS/inverter loss may slightly inflate this).

    Battery watts use live ``battery_power`` when present; otherwise the labelled
    ``battery_power_held_estimate`` bridge across BMS link-loss gaps.
    """
    q1_w = _q1_load_watts(values)
    # Inverter reporting real load: trust Q1 for house AC demand.
    if q1_w is not None and q1_w > 0:
        return {
            "best_available_ac_load_estimate": q1_w,
            "best_available_ac_load_estimate_source": "q1_percent",
        }

    battery_w, from_held = _battery_watts(values)
    pv_w = values.get("pv_power")
    held_tag = "_held" if from_held else ""

    if battery_w is not None and battery_w <= _NET_DISCHARGE_THRESHOLD_W:
        discharge_w = abs(battery_w)
        if isinstance(pv_w, (int, float)) and float(pv_w) > 0:
            return {
                "best_available_ac_load_estimate": round(discharge_w + float(pv_w), 1),
                "best_available_ac_load_estimate_source": f"bms_dc_plus_pv{held_tag}",
            }
        return {
            "best_available_ac_load_estimate": round(discharge_w, 1),
            "best_available_ac_load_estimate_source": f"bms_dc{held_tag}",
        }

    if (
        battery_w is not None
        and battery_w > 0
        and isinstance(pv_w, (int, float))
        and float(pv_w) > 0
    ):
        return {
            "best_available_ac_load_estimate": max(0.0, round(float(pv_w) - battery_w, 1)),
            "best_available_ac_load_estimate_source": f"pv_minus_charge{held_tag}",
        }

    if q1_w is not None:
        return {
            "best_available_ac_load_estimate": q1_w,
            "best_available_ac_load_estimate_source": "q1_percent",
        }
    return {}
