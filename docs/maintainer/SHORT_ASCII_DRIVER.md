# EyeBond short-ASCII driver

Family behavior for `eybond_short_ascii`. The shared auxiliary-read rule stays
in [ADDING_DRIVERS.md](ADDING_DRIVERS.md). The EyeBond/AABB wire contract,
claim overlap, reject table, and MPPT poller health machine stay in
[SHORT_ASCII_MIXED_SOCKET.md](SHORT_ASCII_MIXED_SOCKET.md). This page is the
driver: probes, optional FC4, admission, labelled estimates, and RB gates.

`payload/short_ascii_mppt.py` decodes one explicitly framed AABB/0200 sample
into an immutable value object. It does not choose the grammar, send the
query, or publish telemetry. Settings `0202` are rejected. MPPT
voltage, temperature, and DC load current stay distinct from BMS voltage,
reference voltage, inverter temperature, and AC load power. Unknown enums
stay raw codes. The sample has no timestamp. Offline inspection is
[tools/README.md](../../tools/README.md#inspect-a-short-ascii-mppt-frame-offline).
Quiet diagnostics `mppt_error_code` / `mppt_error` and Q1 `q1_error_code` /
`q1_error` / `ups_fault` are default-on diagnostic sensors (entity state
only). Do not force-enable live PV/MPPT measurements from catalog overlays.

## Probes

The driver is read-only FC4 plus an admitted auxiliary 0200. It uses the
catalog probe DAG and requires all three replies: MP (38 bytes), Q1 (51 bytes,
unsigned additive checksum), and MD (24 bytes including fixed padding). Every
query has a fixed timeout. There is no UART-mode change and no raw-serial
fallback.

The field layout follows vendor 19B4 segment 1 and saved exchanges from two
devices. Fixed widths, status bits, checksum, and envelope are validated
before a complete Q1 snapshot is published. A failed mandatory read raises
rather than returning an empty success. Only static protocol and firmware
facts enter identity details. The MD firmware text and collector PN are not
inverter serials or retail model identifiers. The schema separates battery
reference voltage, does not mirror output frequency as grid frequency, and
leaves the unresolved Q1 output word in raw support evidence.

The catalog surface is partial and read-only, with no controls profile. A
confirmed metadata snapshot may persist only with a current matching catalog,
candidate revisions, resolution, and evidence fingerprint. Reload must restore
that schema without borrowing default driver controls. Unqualified schema-only
hints remain invalid.

## Optional FC4 and admitted MPPT

Optional F (22-byte fixed text), RH (30 bytes, unsigned 8-bit body sum), and
RB (40 bytes, unsigned 8-bit body sum, not Q1's 16-bit checksum) are runtime
reads, not detection probes. The documented 25-byte RB layout and captured 12
zero padding bytes are required. Vendor 19B4 segments 6 and 7 qualify the
non-current RB fields. Segment 7 documents charge/discharge `multiply=0.1`.
Those currents and measured `battery_power` (V × (Icharge − Idischarge))
publish only while optional RH reports BMS current display accuracy `1` and F
ratings are available for the I/P bounds. RH `0`, unread, expired, or failed
RH omits the keys. RH=1 is the discriminator. That path is
SmartValue-correlated on one live family member.

`short_ascii_optional` owns per-runtime samples, scoped to the transport and
inverter binding. The hub discards sample state on recovery. Samples are not
identity. Each successful Q1 cycle performs at most one optional request
(4-second bound): RB every 30 seconds with a 60-second TTL, F and RH every
900 seconds with a 900-second TTL, and MPPT (`0200`) every 30 seconds with a
60-second TTL **only when admitted**.

Admission is the config-entry option `admit_short_ascii_mppt` (default
absent/false), mirrored into runtime state by the hub. `enabled_default:
false` only hides entities and must not poll. When admitted, the driver calls
`async_auxiliary_read` with the documented runtime query. It does not send
`0202`.

When both an FC4 sample and MPPT are due, FC4 wins while MPPT is fresh. When
MPPT is stale, channel health is `healthy`, and RB is also due, that cycle
takes MPPT instead. A poisoned channel does not solicit 0200 until the
monotonic deadline in the socket document. A flaky timeout may retry once in
the same cycle. A framing kill does not. Soft MPPT failure does not call
`record_command_failure`, does not abort the Q1 merge, and holds the last good
MPPT sample until the 60-second TTL. It does not store the failed reply. TTL
expiry still clears it.

Only optional FC4 failures alongside a successful Q1 count toward the shared
four-strike command cache. The re-check action re-enables those requests.
MPPT must not enter that cache. A failed or cancelled mandatory cycle, a lost
connection, a changed binding, or a clock rollback clears optional samples.
MPPT channel health lives on runtime state, not on those samples, so a rebuild
does not forget an active poison. Support Archive capture may include
correlated `0200_request` / `0200` hex when the aux facade is available.

## Labelled estimates

Live BMS measurement keys are omitted on link-loss (V=0 and SoC=0). They are
not refreshed so they look current. Separately, `short_ascii_bms_held.py`
publishes `*_held_estimate` mirrors with a 180-second TTL for dashboards and
for load imputation. Those keys are estimates. They are not the live BMS
sensors.

`estimated_ac_load_power` is load% × rated VA. `best_available_ac_load_estimate`
is a labelled composite and must not rewrite that value, `battery_power`, or
`pv_power`:

1. Q1 load watts when the inverter reports load greater than 0 W.
2. Otherwise `max(0, PV − battery watts)`, with battery sign +charge /
   −discharge. Live `battery_power` wins. If it is omitted, the labelled
   `battery_power_held_estimate` may fill the gap and the source tag gains
   `_held`.
3. Otherwise PV alone when BMS watts are missing.
4. Otherwise Q1, including 0 W, or omit.

## RB hard-reject

After a valid RB envelope, field gates run before publish.

- **Pack voltage (F-gated):** when `short_ascii_rated_battery_voltage` from F
  is unknown, do not hard-reject on pack voltage alone. When known, the
  inclusive window is **0.75×–4/3×** that rating (24 V → 18–32 so 25.6 V
  passes; 48 V → 36–64 so 16 V and 1230 V die). Not a universal 30–70 V band.
- **Current / power:** SoC outside [0, 100] rejects. SoC 0 stays allowed when
  pack voltage is present. Reject when abs(I) > **3×** F VA / F Vbat, or
  abs(P) > **3×** F VA.
- **Link-loss:** on V=0 and SoC=0, publish
  `short_ascii_bms_data_available=False` and omit BMS measurement keys from
  the FULL snapshot. Do not refresh hub freshness with stale V/SoC/I.
  Checksum or length failure drops the reply. A hard-reject of an impossible
  sample keeps the previous RB sample for the ~60 s optional TTL. The 180 s
  series is only the labelled `*_held_estimate` keys above.

An RB reply with zero voltage and zero SoC withdraws all BMS measurements and
path flags, including nonzero trailing fields. Positive voltage with zero SoC
remains valid. Data availability is not a physical connection detector.
Reference voltage, BMS voltage, and ratings have separate owners. Pack voltage
is never inferred from reference voltage.

Live PV stays behind `admit_short_ascii_mppt`. Inverter controls are separate
work. Do not report full device support from these fields or a saved-wire
replay alone.
