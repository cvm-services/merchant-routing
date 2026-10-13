# RP-5 Shadow-Run Evidence Contract

**Status:** contract fixed by t_5163660b — capture modules for criteria (a)-(f)
build against this document. Schema version **1.0.0**.

- Machine-readable contract: `src/shadow_evidence.py` (import as
  `shadow_evidence`; JSON Schemas also printable via CLI, see below)
- Example fixture: `tests/fixtures/shadow_evidence/minimal_valid.json`
- Tests: `tests/test_shadow_evidence_schema.py`
- Grading (PASS/FAIL per criterion) stays in `src/rp5_shadow_validator.py`

## 1. Stable output paths

| Purpose | Default | Env override |
|---|---|---|
| Evidence JSON | `/var/lib/shadow-run/evidence.json` | `SHADOW_EVIDENCE_PATH` |
| Human-readable log (JSONL) | `/var/lib/shadow-run/evidence.log` | `SHADOW_EVIDENCE_LOG` |
| CSV mirror (optional) | `/var/lib/shadow-run/evidence.csv` | `SHADOW_EVIDENCE_CSV` (set to enable) |

The CSV mirror is **opt-in**: it is written only when `SHADOW_EVIDENCE_CSV` is
set. All writers create parent directories as needed; evidence writes are
atomic (temp file + `os.replace` in the same directory), and every write is
schema-validated before it lands.

## 2. Sample-window configuration

| Key | Default | Env override | Unit |
|---|---|---|---|
| duration | 172800 (48 h) | `SHADOW_RUN_WINDOW_S` | seconds |
| refresh interval | 300 (5 min) | `SHADOW_RUN_REFRESH_S` | seconds |
| stale threshold | 30 (fixed) | — | minutes |

Resolved at runtime by `shadow_evidence.get_sample_window()`; recorded inside
the evidence file under `config.sample_window` so a file is self-describing.

## 3. Evidence file top level

```json
{
  "schema_version": "1.0.0",
  "run_id": "rp5-20260914T1942Z",
  "created_at": "2026-09-14T19:42:35Z",
  "updated_at": "2026-09-14T19:47:35Z",
  "config": { "sample_window": {...}, "provider_set": [...], "kill_switch_env": null },
  "sections": { "first_measurements": {...}, "ollama_rate_series": [...], ... }
}
```

- `run_id`: string, non-empty — stable id of the shadow run.
- `created_at` / `updated_at`: ISO-8601 UTC (`YYYY-MM-DDTHH:MM:SSZ`).
- `config.kill_switch_env`: value of `OLLAMA_THROTTLE_ENABLED` at run start;
  `null` = unset = kill switch **OFF** (the criterion (f) precondition).
- `config.provider_set`: exactly the 6 canonical providers (see §4.1).
- No additional top-level keys are allowed (`additionalProperties: false`).

Timestamps everywhere are **ISO-8601 UTC strings**; rates are **$/M tokens**;
durations are **seconds** unless suffixed `_min` (minutes).

## 4. The six sections (criteria a-f)

### 4.1 (a) `first_measurements` — per-provider first-measurement timestamps

Object with `startup_ts`, `window_deadline_ts` (both nullable until the first
capture cycle records T0), and `entries[]`:

| Field | Type | Unit | Nullable | Notes |
|---|---|---|---|---|
| `provider` | string enum | — | no | one of `ours, friend, ollama_cloud, ppq, deepinfra, openrouter` |
| `first_measured_at` | string | ISO-8601 | no | first successful measurement |
| `within_window` | boolean | — | no | `first_measured_at <= window_deadline_ts` |

Criterion (a) passes when all 6 providers have an entry with
`within_window: true`.

### 4.2 (b) `ollama_rate_series` — Ollama measured rate over time

Array of samples (one per refresh cycle):

| Field | Type | Unit | Nullable | Notes |
|---|---|---|---|---|
| `ts` | string | ISO-8601 | no | sample time |
| `measured_rate` | number | $/M tokens | no | measured rate |
| `target` | number | $/M tokens | yes | reference, 0.0155 |
| `tolerance` | number | dimensionless | yes | relative, 0.10 = ±10% |
| `source` | string | — | yes | provenance, e.g. `price_tracker`, `seed` |

### 4.3 (c) `extra_usage_events` — extra-usage trigger events

Array of observations:

| Field | Type | Unit | Nullable | Notes |
|---|---|---|---|---|
| `ts` | string | ISO-8601 | no | observation time |
| `triggered` | boolean | — | no | `session_usage >= 1.0` |
| `session_usage` | number | dimensionless | yes | fraction of quota; null = API unavailable |
| `weekly_usage` | number | dimensionless | yes | |
| `regime` | string | — | yes | usage regime label |

### 4.4 (d) `glm52_extra_rate_samples` — glm-5.2 extra rate

Array of samples:

| Field | Type | Unit | Nullable | Notes |
|---|---|---|---|---|
| `ts` | string | ISO-8601 | no | |
| `active` | boolean | — | no | lane active at `ts` |
| `extra_rate` | number | $/M tokens | yes | null = not active/unavailable |
| `model` | string | — | yes | default `glm-5.2` |

### 4.5 (e) `anomaly_alerts` — NaN / crash / staleness detector

Array of alerts:

| Field | Type | Unit | Nullable | Notes |
|---|---|---|---|---|
| `ts` | string | ISO-8601 | no | detection time |
| `type` | enum `stale \| nan \| exception` | — | no | |
| `source` | string | — | no | metric/provider/table observed on |
| `observed` | number or string | seconds (stale) | yes | age for stale; non-finite rendered as string for nan; null for exception |
| `threshold` | number or string | seconds | yes | 1800 for stale |
| `detail` | string | — | yes | exception repr / context |

### 4.6 (f) `routing_parity_snapshot` — kill-switch-OFF routing parity

Object:

| Field | Type | Nullable | Notes |
|---|---|---|---|
| `kill_switch` | enum `OFF \| ON` | no | `OFF` is the (f) precondition |
| `expected_routing_fingerprint` | string | yes | SHA-256 of expected routing table/baseline |
| `rows[].requested_class` | string | no | route/request class exercised |
| `rows[].chosen_provider` / `chosen_model` | string | yes | actual choice with switch OFF |
| `rows[].expected_provider` / `expected_model` | string | yes | baseline expectation |
| `rows[].parity` | boolean | no | chosen == expected (provider AND model) |
| `rows[].ts` | string | yes | snapshot time (ISO-8601) |
| `overall_parity` | boolean | yes | all rows parity=true |

## 5. Human-readable log

One JSON object per line at the log path; validated by `LOG_LINE_SCHEMA`:

| Field | Type | Notes |
|---|---|---|
| `ts` | string (ISO-8601) | |
| `section` | enum | one of the six section names, or `meta` |
| `level` | enum `debug \| info \| warn \| error` | |
| `message` | string | human-readable summary |
| `data` | any | optional structured payload; mirrored to CSV when supported |

The CSV mirror flattens `data` per section (see `shadow_evidence.csv_rows_for`);
unsupported payloads are skipped, never malformed.

## 6. Usage

```python
from shadow_evidence import EvidenceWriter, SECTION_NAMES

w = EvidenceWriter(run_id="rp5-20260914T1942Z")   # honours env overrides
w.append_ollama_rate(ts, 0.0155)                   # section (b)
w.log("rate sample recorded", section="b", data=[...])
```

```console
$ python3 -m src.shadow_evidence paths                # resolved paths + window
$ python3 -m src.shadow_evidence init                 # seed empty evidence + log
$ python3 -m src.shadow_evidence print-schema         # JSON Schema to stdout
$ python3 -m src.shadow_evidence validate FILE [...]  # exit 1 on invalid
```

The capture modules for (a)-(d), the anomaly detector (e), and the parity
snapshot (f) append via `EvidenceWriter`; the summarizer
(`rp5_shadow_validator.py`) reads the evidence file and grades each criterion
PASS/FAIL. This module itself never touches the network, the shadow DB, or the
live router.
