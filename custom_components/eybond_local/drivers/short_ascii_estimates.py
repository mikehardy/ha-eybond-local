"""Labelled short-ASCII estimates derived from wire measurements + ratings.

MX2: %×VA watts are an estimate, never measured active power. Keep wire load%
intact; do not publish tip-style ``load_power`` / silent source swaps here.
``best_available_ac_load_estimate`` is an explicitly labelled composite for
dashboards. Priority (first match wins): (1) Q1 %×VA when the inverter is
actually reporting load (> 0 W) → ``q1_percent``; (2) otherwise, if net BMS
discharge ≤ −25 W → ``bms_dc``, or ``bms_dc_plus_pv`` when PV > 0 (shoulder
impute: house ≈ discharge + consumed PV); (3) else Q1 including 0 W, or omit.
Never rewrites pure keys.
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


def best_available_ac_load_estimate_values(values: dict[str, object]) -> dict[str, object]:
    """Composite dashboard estimate: q1 when reporting → else bms_dc(+pv), or omit.

    Prefer ``estimated_ac_load_power`` when already present; otherwise compute the
    same load% × rated VA. Never rewrite pure measurement/estimate keys.

    BMS (+ optional PV) impute is only for the floor where Q1 reports 0 W / is
    missing — not a rewrite of Q1 when the inverter is already publishing load.
    When imputing and PV > 0 while the pack still discharges, add PV (consumed,
    not stored). That is not the old ``pv_minus_charge`` charge-morning residual.
    """
    q1_w = _q1_load_watts(values)
    # Inverter reporting real load: trust Q1 for house AC demand.
    if q1_w is not None and q1_w > 0:
        return {
            "best_available_ac_load_estimate": q1_w,
            "best_available_ac_load_estimate_source": "q1_percent",
        }

    battery_w = values.get("battery_power")
    if isinstance(battery_w, (int, float)) and float(battery_w) <= _NET_DISCHARGE_THRESHOLD_W:
        discharge_w = abs(float(battery_w))
        pv_w = values.get("pv_power")
        if isinstance(pv_w, (int, float)) and float(pv_w) > 0:
            return {
                "best_available_ac_load_estimate": round(discharge_w + float(pv_w), 1),
                "best_available_ac_load_estimate_source": "bms_dc_plus_pv",
            }
        return {
            "best_available_ac_load_estimate": round(discharge_w, 1),
            "best_available_ac_load_estimate_source": "bms_dc",
        }

    if q1_w is not None:
        return {
            "best_available_ac_load_estimate": q1_w,
            "best_available_ac_load_estimate_source": "q1_percent",
        }
    return {}
