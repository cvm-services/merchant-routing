#!/usr/bin/env python3
"""shadow_evidence.py — machine-readable evidence contract for the RP-5 shadow run.

Single source of truth for the *contract*, so the capture modules for criteria
(a)-(f) can be built in parallel against it:

  * the JSON Schema of the evidence file   (``SHADOW_EVIDENCE_SCHEMA``),
  * the JSON Schema of a log line          (``LOG_LINE_SCHEMA``),
  * the stable output paths and the env vars that override them,
  * the sample-window configuration (duration, refresh interval, staleness),
  * an atomic writer (``EvidenceWriter``) plus log/CSV helpers.

Sections (a)-(f) mirror the six RP-5 gate criteria (see
``src/rp5_shadow_validator.py``):

  (a) first_measurements        per-provider first-measurement timestamps (6 providers)
  (b) ollama_rate_series        Ollama measured rate over time ($0.0155/M +/- 10%)
  (c) extra_usage_events        extra-usage triggers when session.usage >= 1.0
  (d) glm52_extra_rate_samples  glm-5.2 extra rate when active ($0.46/M +/- 30%)
  (e) anomaly_alerts            stale | nan | exception detector output
  (f) routing_parity_snapshot   kill-switch-OFF routing parity vs baseline

Importable by the capture modules; also usable as a CLI:

  python3 -m src.shadow_evidence print-schema          # evidence schema to stdout
  python3 -m src.shadow_evidence print-log-schema      # log-line schema to stdout
  python3 -m src.shadow_evidence paths                 # resolved paths + config
  python3 -m src.shadow_evidence init                  # write an empty evidence skeleton
  python3 -m src.shadow_evidence validate FILE [...]   # validate evidence file(s)

stdlib + jsonschema only: this module never touches the network, the shadow DB,
or the live router.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

try:
    from jsonschema import Draft202012Validator
except ImportError as _exc:  # pragma: no cover - environment guard
    raise ImportError(
        "shadow_evidence requires the 'jsonschema' package "
        "(jsonschema>=4.18 for JSON Schema Draft 2020-12)"
    ) from _exc

__all__ = [
    "SCHEMA_VERSION",
    "EXPECTED_PROVIDERS",
    "SECTION_NAMES",
    "RATE_UNIT",
    "TARGET_OLLAMA_RATE",
    "OLLAMA_RATE_TOL",
    "TARGET_EXTRA_RATE",
    "EXTRA_RATE_TOL",
    "STALE_THRESHOLD_MIN",
    "STARTUP_WINDOW_MIN",
    "EXTRA_USAGE_TRIGGER_SESSION_USAGE",
    "KILL_SWITCH_ENV",
    "EVIDENCE_ENV",
    "LOG_ENV",
    "CSV_ENV",
    "WINDOW_DURATION_ENV",
    "REFRESH_INTERVAL_ENV",
    "DEFAULT_EVIDENCE_PATH",
    "DEFAULT_LOG_PATH",
    "DEFAULT_CSV_PATH",
    "DEFAULT_WINDOW_DURATION_S",
    "DEFAULT_REFRESH_INTERVAL_S",
    "ISO_TS_PATTERN",
    "ISO_TS_RE",
    "SHADOW_EVIDENCE_SCHEMA",
    "LOG_LINE_SCHEMA",
    "get_paths",
    "get_sample_window",
    "utc_now_iso",
    "new_evidence",
    "init_files",
    "EvidenceWriter",
    "validate_evidence",
    "validate_log_line",
    "format_log_line",
    "csv_rows_for",
]

# ── Version and semantic constants (kept identical to rp5_shadow_validator) ──
SCHEMA_VERSION = "1.0.0"

#: Canonical provider ids (criterion (a)). MUST stay in sync with
#: ``rp5_shadow_validator.EXPECTED_PROVIDERS``.
EXPECTED_PROVIDERS = [
    "ours",
    "friend",
    "ollama_cloud",
    "ppq",
    "deepinfra",
    "openrouter",
]

#: The six evidence sections, keyed by criterion letter.
SECTION_NAMES = {
    "a": "first_measurements",
    "b": "ollama_rate_series",
    "c": "extra_usage_events",
    "d": "glm52_extra_rate_samples",
    "e": "anomaly_alerts",
    "f": "routing_parity_snapshot",
}

#: Unit applied to every rate field in this contract.
RATE_UNIT = "$/M tokens"

# RP-5 gate constants (mirror rp5_shadow_validator.py; grading stays there).
TARGET_OLLAMA_RATE = 0.0155       # $/M tokens
OLLAMA_RATE_TOL = 0.10            # +/- 10%
TARGET_EXTRA_RATE = 0.46          # $/M tokens (glm-5.2 extra-usage)
EXTRA_RATE_TOL = 0.30             # +/- 30%
STALE_THRESHOLD_MIN = 30          # minutes
STARTUP_WINDOW_MIN = 30           # minutes
EXTRA_USAGE_TRIGGER_SESSION_USAGE = 1.0  # dimensionless trigger threshold
KILL_SWITCH_ENV = "OLLAMA_THROTTLE_ENABLED"  # unset/"false" => switch OFF

# ── Stable paths (defaults; overridable via env) ────────────────────────────
EVIDENCE_ENV = "SHADOW_EVIDENCE_PATH"       # override evidence JSON path
LOG_ENV = "SHADOW_EVIDENCE_LOG"             # override human-readable log path
CSV_ENV = "SHADOW_EVIDENCE_CSV"             # set to enable the CSV mirror
WINDOW_DURATION_ENV = "SHADOW_RUN_WINDOW_S"  # sample-window duration, seconds
REFRESH_INTERVAL_ENV = "SHADOW_RUN_REFRESH_S"  # refresh interval, seconds

DEFAULT_EVIDENCE_PATH = "/var/lib/shadow-run/evidence.json"
DEFAULT_LOG_PATH = "/var/lib/shadow-run/evidence.log"
DEFAULT_CSV_PATH = "/var/lib/shadow-run/evidence.csv"

DEFAULT_WINDOW_DURATION_S = 48 * 3600   # 48 h sample window
DEFAULT_REFRESH_INTERVAL_S = 300        # one refresh cycle every 5 minutes

ISO_TS_PATTERN = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:?\d{2})$"
ISO_TS_RE = re.compile(ISO_TS_PATTERN)


# ── Schema building blocks ──────────────────────────────────────────────────
def _ts_field(description: str) -> dict[str, Any]:
    return {"type": "string", "pattern": ISO_TS_PATTERN, "description": description}


def _rate_field(description: str) -> dict[str, Any]:
    return {"type": "number", "description": f"{description} Unit: {RATE_UNIT}."}


def _provider_field() -> dict[str, Any]:
    return {"type": "string", "enum": list(EXPECTED_PROVIDERS),
            "description": "Canonical provider id (criterion (a))."}


def _build_schema() -> dict[str, Any]:
    """Assemble the evidence-file schema (Draft 2020-12)."""
    first_measurements = {
        "type": "object",
        "required": ["startup_ts", "window_deadline_ts", "entries"],
        "additionalProperties": False,
        "properties": {
            "startup_ts": {"type": ["string", "null"], "pattern": ISO_TS_PATTERN,
                           "description": "T0 of the run (ISO-8601 UTC); null until the "
                                          "first capture cycle records it."},
            "window_deadline_ts": {"type": ["string", "null"], "pattern": ISO_TS_PATTERN,
                                   "description": "startup_ts + 30 min; all first measurements "
                                                  "must land before this. null until T0 is set."},
            "entries": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["provider", "first_measured_at", "within_window"],
                    "additionalProperties": False,
                    "properties": {
                        "provider": _provider_field(),
                        "first_measured_at": _ts_field(
                            "First successful measurement for this provider (ISO-8601 UTC)."),
                        "within_window": {
                            "type": "boolean",
                            "description": "True iff first_measured_at <= window_deadline_ts.",
                        },
                    },
                },
            },
        },
    }

    ollama_rate_series = {
        "type": "array",
        "items": {
            "type": "object",
            "required": ["ts", "measured_rate"],
            "additionalProperties": False,
            "properties": {
                "ts": _ts_field("Sample timestamp (ISO-8601 UTC)."),
                "measured_rate": _rate_field("Measured Ollama rate."),
                "target": _rate_field("Reference rate ($0.0155/M)."),
                "tolerance": {
                    "type": "number", "minimum": 0, "maximum": 1,
                    "description": "Relative tolerance (0.10 = +/- 10%). Unit: dimensionless.",
                },
                "source": {
                    "type": "string",
                    "description": "Provenance, e.g. 'price_tracker' or 'seed'.",
                },
            },
        },
    }

    extra_usage_events = {
        "type": "array",
        "items": {
            "type": "object",
            "required": ["ts", "triggered", "session_usage"],
            "additionalProperties": False,
            "properties": {
                "ts": _ts_field("Observation timestamp (ISO-8601 UTC)."),
                "triggered": {
                    "type": "boolean",
                    "description": "True when session_usage >= 1.0 at this observation.",
                },
                "session_usage": {
                    "type": ["number", "null"],
                    "description": "Ollama session usage. Unit: dimensionless (fraction of quota). "
                                   "null = API unavailable.",
                },
                "weekly_usage": {
                    "type": ["number", "null"],
                    "description": "Ollama weekly usage. Unit: dimensionless. null = unavailable.",
                },
                "regime": {
                    "type": ["string", "null"],
                    "description": "Usage regime label at trigger time, if known.",
                },
            },
        },
    }

    glm52_extra_rate_samples = {
        "type": "array",
        "items": {
            "type": "object",
            "required": ["ts", "active"],
            "additionalProperties": False,
            "properties": {
                "ts": _ts_field("Sample timestamp (ISO-8601 UTC)."),
                "active": {
                    "type": "boolean",
                    "description": "Whether the glm-5.2 extra lane was active at ts.",
                },
                "extra_rate": {
                    "type": ["number", "null"],
                    "description": f"glm-5.2 extra rate. Unit: {RATE_UNIT}. "
                                   "null = not active / unavailable.",
                },
                "model": {
                    "type": ["string", "null"],
                    "description": "Model id the rate applies to (default 'glm-5.2').",
                },
            },
        },
    }

    anomaly_alerts = {
        "type": "array",
        "items": {
            "type": "object",
            "required": ["ts", "type", "source"],
            "additionalProperties": False,
            "properties": {
                "ts": _ts_field("Detection timestamp (ISO-8601 UTC)."),
                "type": {"type": "string", "enum": ["stale", "nan", "exception"]},
                "source": {
                    "type": "string",
                    "description": "Metric/provider/table the anomaly was observed on.",
                },
                "observed": {
                    "type": ["number", "string", "null"],
                    "description": "Observed value: age in seconds (stale), the non-finite "
                                   "number rendered as a string (nan), or null (exception).",
                },
                "threshold": {
                    "type": ["number", "string", "null"],
                    "description": "Threshold breached (1800 for stale); null otherwise. Unit: seconds.",
                },
                "detail": {
                    "type": ["string", "null"],
                    "description": "Exception repr or free-form context.",
                },
            },
        },
    }

    routing_parity_snapshot = {
        "type": "object",
        "required": ["kill_switch", "expected_routing_fingerprint", "rows"],
        "additionalProperties": False,
        "properties": {
            "kill_switch": {
                "type": "string",
                "enum": ["OFF", "ON"],
                "description": "Kill-switch state at snapshot time; OFF is the (f) precondition.",
            },
            "expected_routing_fingerprint": {
                "type": ["string", "null"],
                "description": "SHA-256 of the expected routing table/baseline; "
                               "null = baseline unavailable.",
            },
            "rows": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": [
                        "requested_class", "chosen_provider", "chosen_model",
                        "expected_provider", "expected_model", "parity",
                    ],
                    "additionalProperties": False,
                    "properties": {
                        "requested_class": {
                            "type": "string",
                            "description": "Route/request class exercised (e.g. 'default').",
                        },
                        "chosen_provider": {
                            "type": ["string", "null"],
                            "description": "Provider actually chosen with switch OFF.",
                        },
                        "chosen_model": {"type": ["string", "null"]},
                        "expected_provider": {
                            "type": ["string", "null"],
                            "description": "Baseline expectation.",
                        },
                        "expected_model": {"type": ["string", "null"]},
                        "parity": {
                            "type": "boolean",
                            "description": "chosen == expected for provider AND model.",
                        },
                        "ts": _ts_field("Snapshot timestamp (ISO-8601 UTC)."),
                    },
                },
            },
            "overall_parity": {
                "type": "boolean",
                "description": "All rows parity=true. Written by the capture module.",
            },
        },
    }

    sections = {
        "type": "object",
        "required": list(SECTION_NAMES.values()),
        "additionalProperties": False,
        "properties": {
            "first_measurements": first_measurements,
            "ollama_rate_series": ollama_rate_series,
            "extra_usage_events": extra_usage_events,
            "glm52_extra_rate_samples": glm52_extra_rate_samples,
            "anomaly_alerts": anomaly_alerts,
            "routing_parity_snapshot": routing_parity_snapshot,
        },
    }

    config = {
        "type": "object",
        "required": ["sample_window", "provider_set"],
        "additionalProperties": False,
        "properties": {
            "sample_window": {
                "type": "object",
                "required": ["duration_s", "refresh_interval_s", "stale_threshold_min"],
                "additionalProperties": False,
                "properties": {
                    "duration_s": {
                        "type": "integer", "exclusiveMinimum": 0,
                        "description": "Sample-window duration. Unit: seconds.",
                    },
                    "refresh_interval_s": {
                        "type": "integer", "exclusiveMinimum": 0,
                        "description": "Refresh-cycle interval. Unit: seconds.",
                    },
                    "stale_threshold_min": {
                        "type": "number",
                        "description": "Staleness threshold for criterion (e). Unit: minutes.",
                    },
                },
            },
            "provider_set": {
                "type": "array",
                "items": _provider_field(),
                "minItems": len(EXPECTED_PROVIDERS),
                "maxItems": len(EXPECTED_PROVIDERS),
                "uniqueItems": True,
                "description": "The 6 expected providers (criterion (a)).",
            },
            "kill_switch_env": {
                "type": ["string", "null"],
                "description": "Value of OLLAMA_THROTTLE_ENABLED at run start; "
                               "null = unset (switch OFF).",
            },
        },
    }

    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://felixfelix-bot.github.io/merchant-routing/schemas/shadow-evidence-1.0.0.json",
        "title": "RP-5 shadow-run evidence file",
        "type": "object",
        "required": ["schema_version", "run_id", "created_at", "updated_at", "config", "sections"],
        "additionalProperties": False,
        "properties": {
            "schema_version": {
                "type": "string", "const": SCHEMA_VERSION,
                "description": "Contract version; bump on any breaking change.",
            },
            "run_id": {
                "type": "string", "minLength": 1,
                "description": "Stable id of the shadow run (e.g. 'rp5-20260914T1942Z').",
            },
            "created_at": _ts_field("When the file was created (ISO-8601 UTC)."),
            "updated_at": _ts_field("Last append (ISO-8601 UTC)."),
            "config": config,
            "sections": sections,
        },
    }


SHADOW_EVIDENCE_SCHEMA: dict[str, Any] = _build_schema()

#: Schema of one human-readable log line (JSONL).
LOG_LINE_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://felixfelix-bot.github.io/merchant-routing/schemas/shadow-evidence-log-line-1.0.0.json",
    "title": "RP-5 shadow-run evidence log line",
    "type": "object",
    "required": ["ts", "section", "level", "message"],
    "additionalProperties": False,
    "properties": {
        "ts": _ts_field("Line timestamp (ISO-8601 UTC)."),
        "section": {"type": "string", "enum": list(SECTION_NAMES.values()) + ["meta"]},
        "level": {"type": "string", "enum": ["debug", "info", "warn", "error"]},
        "message": {"type": "string", "minLength": 1},
        "data": {"description": "Optional free-form structured payload."},
    },
}


# ── Validators ──────────────────────────────────────────────────────────────
_EVIDENCE_VALIDATOR = Draft202012Validator(SHADOW_EVIDENCE_SCHEMA)
_LOG_VALIDATOR = Draft202012Validator(LOG_LINE_SCHEMA)


def _errors(validator: Draft202012Validator, doc: Any) -> list[str]:
    return [
        f"{'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}"
        for e in sorted(validator.iter_errors(doc), key=lambda e: list(e.absolute_path))
    ]


def validate_evidence(doc: dict[str, Any]) -> list[str]:
    """Validate an evidence document. Returns error strings; empty list = valid."""
    return _errors(_EVIDENCE_VALIDATOR, doc)


def validate_log_line(line: dict[str, Any]) -> list[str]:
    """Validate one log line. Returns error strings; empty list = valid."""
    return _errors(_LOG_VALIDATOR, line)


# ── Path / config resolution ────────────────────────────────────────────────
def get_paths() -> dict[str, str | None]:
    """Resolve stable output paths, honouring env overrides.

    Returns keys ``evidence``, ``log`` and ``csv`` (``csv`` is None unless
    ``SHADOW_EVIDENCE_CSV`` is set, in which case it defaults to the packaged
    default when the value is an empty string).
    """
    csv_env = os.environ.get(CSV_ENV)
    if csv_env is None:
        csv_path: str | None = None
    else:
        csv_path = csv_env or DEFAULT_CSV_PATH
    return {
        "evidence": os.environ.get(EVIDENCE_ENV) or DEFAULT_EVIDENCE_PATH,
        "log": os.environ.get(LOG_ENV) or DEFAULT_LOG_PATH,
        "csv": csv_path,
    }


def get_sample_window() -> dict[str, Any]:
    """Resolve the sample-window config from env (seconds)."""
    duration = int(os.environ.get(WINDOW_DURATION_ENV) or DEFAULT_WINDOW_DURATION_S)
    refresh = int(os.environ.get(REFRESH_INTERVAL_ENV) or DEFAULT_REFRESH_INTERVAL_S)
    if duration <= 0 or refresh <= 0:
        raise ValueError("sample-window duration and refresh interval must be > 0")
    return {
        "duration_s": duration,
        "refresh_interval_s": refresh,
        "stale_threshold_min": STALE_THRESHOLD_MIN,
    }


def utc_now_iso() -> str:
    """Current UTC time as ISO-8601 with a trailing 'Z'."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ── Evidence construction and persistence ───────────────────────────────────
def _empty_section(name: str) -> Any:
    if name == SECTION_NAMES["a"]:
        return {"startup_ts": None, "window_deadline_ts": None, "entries": []}
    if name == SECTION_NAMES["f"]:
        return {"kill_switch": "OFF", "expected_routing_fingerprint": None, "rows": []}
    return []


def new_evidence(run_id: str, *, provider_set: list[str] | None = None,
                 kill_switch_env: str | None = None,
                 window: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build an empty, schema-valid evidence skeleton with all six sections.

    ``kill_switch_env`` defaults to the current value of the kill-switch env var
    (None when unset, which means the switch is OFF).
    """
    now = utc_now_iso()
    if kill_switch_env is None:
        kill_switch_env = os.environ.get(KILL_SWITCH_ENV)
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "created_at": now,
        "updated_at": now,
        "config": {
            "sample_window": window or get_sample_window(),
            "provider_set": list(provider_set or EXPECTED_PROVIDERS),
            "kill_switch_env": kill_switch_env,
        },
        "sections": {name: _empty_section(name) for name in SECTION_NAMES.values()},
    }


def init_files(evidence_path: str | None = None, log_path: str | None = None,
               run_id: str | None = None) -> dict[str, str]:
    """Create parent dirs and seed an empty evidence JSON + empty log.

    Idempotent: never clobbers an existing non-empty evidence file. Returns the
    resolved paths actually used.
    """
    paths = get_paths()
    ev = Path(evidence_path or paths["evidence"])
    lg = Path(log_path or paths["log"])
    for p in (ev, lg):
        p.parent.mkdir(parents=True, exist_ok=True)
    if not ev.exists() or ev.stat().st_size == 0:
        doc = new_evidence(run_id or f"rp5-{utc_now_iso()}")
        _atomic_write_text(ev, json.dumps(doc, indent=2, sort_keys=False) + "\n")
    lg.touch(exist_ok=True)
    return {"evidence": str(ev), "log": str(lg)}


def _atomic_write_text(path: Path, text: str) -> None:
    """Write text to path atomically (tmp file in the same dir + os.replace)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


class EvidenceWriter:
    """Append-only writer over the evidence file plus its human-readable log.

    The capture modules for criteria (a)-(d) use ``append_*`` for the time
    series/event sections and ``set_section`` for the singleton sections
    (``first_measurements``, ``routing_parity_snapshot``). Every write is
    atomic (read-modify-write under ``os.replace``) and re-validated before it
    lands, so a malformed section cannot corrupt the file.

    Not safe for concurrent writers; the refresh loop is expected to be
    single-threaded (one cycle at a time).
    """

    def __init__(self, evidence_path: str | None = None, log_path: str | None = None,
                 run_id: str | None = None, *, csv_path: str | None = None,
                 create: bool = True) -> None:
        paths = get_paths()
        self.evidence_path = Path(evidence_path or paths["evidence"])
        self.log_path = Path(log_path or paths["log"])
        self.csv_path = Path(csv_path) if csv_path else (Path(paths["csv"]) if paths["csv"] else None)
        if create and (not self.evidence_path.exists() or self.evidence_path.stat().st_size == 0):
            init_files(str(self.evidence_path), str(self.log_path), run_id)
        self.run_id = run_id

    # -- loading / saving ---------------------------------------------------
    def load(self) -> dict[str, Any]:
        with open(self.evidence_path, "r", encoding="utf-8") as fh:
            return json.load(fh)

    def save(self, doc: dict[str, Any], *, validate: bool = True) -> None:
        doc["updated_at"] = utc_now_iso()
        if validate:
            errs = validate_evidence(doc)
            if errs:
                raise ValueError("refusing to write invalid evidence document: "
                                 + "; ".join(errs[:5]))
        _atomic_write_text(self.evidence_path, json.dumps(doc, indent=2) + "\n")

    # -- section mutation ---------------------------------------------------
    def set_section(self, section: str, value: Any) -> dict[str, Any]:
        """Replace a whole section (criterion letter like 'a' or section name)."""
        doc = self.load()
        doc["sections"][_resolve_section(section)] = value
        self.save(doc)
        return doc

    def append(self, section: str, record: dict[str, Any]) -> dict[str, Any]:
        """Append one record to an array-shaped section."""
        name = _resolve_section(section)
        doc = self.load()
        bucket = doc["sections"][name]
        if not isinstance(bucket, list):
            raise TypeError(f"section {name!r} is not array-shaped")
        bucket.append(record)
        self.save(doc)
        return doc

    # convenience wrappers --------------------------------------------------
    def append_first_measurement(self, provider: str, first_measured_at: str,
                                 startup_ts: str, window_deadline_ts: str) -> dict[str, Any]:
        """Append one entry to the dict-shaped section (a)."""
        doc = self.load()
        sec = doc["sections"][SECTION_NAMES["a"]]
        sec["startup_ts"] = sec.get("startup_ts") or startup_ts
        sec["window_deadline_ts"] = sec.get("window_deadline_ts") or window_deadline_ts
        within = first_measured_at <= window_deadline_ts
        sec["entries"].append({
            "provider": provider,
            "first_measured_at": first_measured_at,
            "within_window": within,
        })
        self.save(doc)
        return doc

    def append_ollama_rate(self, ts: str, measured_rate: float, *,
                           target: float = TARGET_OLLAMA_RATE,
                           tolerance: float = OLLAMA_RATE_TOL,
                           source: str = "price_tracker") -> dict[str, Any]:
        return self.append("b", {"ts": ts, "measured_rate": measured_rate,
                                 "target": target, "tolerance": tolerance,
                                 "source": source})

    def append_extra_usage(self, ts: str, session_usage: float | None, *,
                           weekly_usage: float | None = None,
                           regime: str | None = None) -> dict[str, Any]:
        triggered = session_usage is not None and session_usage >= EXTRA_USAGE_TRIGGER_SESSION_USAGE
        return self.append("c", {"ts": ts, "triggered": triggered,
                                 "session_usage": session_usage,
                                 "weekly_usage": weekly_usage, "regime": regime})

    def append_glm52_sample(self, ts: str, active: bool, *,
                            extra_rate: float | None = None,
                            model: str | None = "glm-5.2") -> dict[str, Any]:
        return self.append("d", {"ts": ts, "active": active,
                                 "extra_rate": extra_rate, "model": model})

    def append_anomaly(self, ts: str, type_: str, source: str, *,
                       observed: float | str | None = None,
                       threshold: float | str | None = None,
                       detail: str | None = None) -> dict[str, Any]:
        if type_ not in ("stale", "nan", "exception"):
            raise ValueError(f"unknown anomaly type {type_!r}")
        return self.append("e", {"ts": ts, "type": type_, "source": source,
                                 "observed": observed, "threshold": threshold,
                                 "detail": detail})

    # -- human-readable log + CSV mirror ------------------------------------
    def log(self, message: str, *, section: str = "meta",
            level: str = "info", data: Any = None) -> dict[str, Any]:
        """Append one human-readable JSONL line to the log (and mirror to CSV)."""
        line = format_log_line(message, section=section, level=level, data=data)
        errs = validate_log_line(line)
        if errs:
            raise ValueError("invalid log line: " + "; ".join(errs))
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.log_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(line, sort_keys=False) + "\n")
        if self.csv_path is not None:
            self._mirror_csv(line)
        return line

    def _mirror_csv(self, line: dict[str, Any]) -> None:
        rows = csv_rows_for(line["section"], line.get("data"))
        if not rows:
            return
        new_file = not self.csv_path.exists() or self.csv_path.stat().st_size == 0
        self.csv_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.csv_path, "a", encoding="utf-8", newline="") as fh:
            for row in rows:
                writer = csv.DictWriter(fh, fieldnames=list(row.keys()))
                if new_file:
                    writer.writeheader()
                    new_file = False
                writer.writerow(row)


def _resolve_section(section: str) -> str:
    if section in SECTION_NAMES:
        return SECTION_NAMES[section]
    if section in SECTION_NAMES.values():
        return section
    raise KeyError(f"unknown section {section!r}; expected one of "
                   f"{list(SECTION_NAMES) + list(SECTION_NAMES.values())}")


# ── Log-line and CSV helpers ────────────────────────────────────────────────
def format_log_line(message: str, *, section: str = "meta", level: str = "info",
                    data: Any = None, ts: str | None = None) -> dict[str, Any]:
    """Build a schema-valid human-readable log line."""
    name = section if section == "meta" else _resolve_section(section)
    line: dict[str, Any] = {
        "ts": ts or utc_now_iso(),
        "section": name,
        "level": level,
        "message": message,
    }
    if data is not None:
        line["data"] = data
    return line


#: Flatteners for the optional CSV mirror: section -> row builder.
_CSV_ROW_BUILDERS = {
    "ollama_rate_series": lambda r: {
        "ts": r.get("ts"), "measured_rate": r.get("measured_rate"),
        "target": r.get("target"), "source": r.get("source"),
    },
    "extra_usage_events": lambda r: {
        "ts": r.get("ts"), "triggered": r.get("triggered"),
        "session_usage": r.get("session_usage"), "weekly_usage": r.get("weekly_usage"),
        "regime": r.get("regime"),
    },
    "glm52_extra_rate_samples": lambda r: {
        "ts": r.get("ts"), "active": r.get("active"),
        "extra_rate": r.get("extra_rate"), "model": r.get("model"),
    },
    "anomaly_alerts": lambda r: {
        "ts": r.get("ts"), "type": r.get("type"), "source": r.get("source"),
        "observed": r.get("observed"), "threshold": r.get("threshold"),
        "detail": r.get("detail"),
    },
    "first_measurements": lambda r: {
        "provider": r.get("provider"), "first_measured_at": r.get("first_measured_at"),
        "within_window": r.get("within_window"),
    },
    "routing_parity_snapshot": lambda r: {
        "requested_class": r.get("requested_class"),
        "chosen_provider": r.get("chosen_provider"),
        "chosen_model": r.get("chosen_model"),
        "expected_provider": r.get("expected_provider"),
        "expected_model": r.get("expected_model"),
        "parity": r.get("parity"), "ts": r.get("ts"),
    },
}


def csv_rows_for(section: str, data: Any) -> list[dict[str, Any]]:
    """Flatten a section payload into CSV rows (returns [] when unsupported)."""
    try:
        name = _resolve_section(section)
    except KeyError:
        return []
    builder = _CSV_ROW_BUILDERS.get(name)
    if builder is None or data is None:
        return []
    if isinstance(data, list):
        return [builder(r) for r in data]
    if isinstance(data, dict):
        if name == "first_measurements":
            return [builder(r) for r in data.get("entries", [])]
        if name == "routing_parity_snapshot":
            return [builder(r) for r in data.get("rows", [])]
    return []


# ── CLI ─────────────────────────────────────────────────────────────────────
def _cmd_print_schema(_args: argparse.Namespace) -> int:
    json.dump(SHADOW_EVIDENCE_SCHEMA, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


def _cmd_print_log_schema(_args: argparse.Namespace) -> int:
    json.dump(LOG_LINE_SCHEMA, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


def _cmd_paths(_args: argparse.Namespace) -> int:
    print(json.dumps({"paths": get_paths(), "sample_window": get_sample_window(),
                      "schema_version": SCHEMA_VERSION,
                      "provider_set": EXPECTED_PROVIDERS}, indent=2))
    return 0


def _cmd_init(args: argparse.Namespace) -> int:
    resolved = init_files(args.evidence, args.log, args.run_id)
    print(json.dumps(resolved, indent=2))
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    rc = 0
    for path in args.files:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                doc = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            print(f"FAIL {path}: {exc}")
            rc = 1
            continue
        errs = validate_evidence(doc)
        if errs:
            rc = 1
            print(f"FAIL {path}: {len(errs)} error(s)")
            for e in errs:
                print(f"  - {e}")
        else:
            print(f"OK   {path}")
    return rc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="shadow_evidence",
                                     description="RP-5 shadow-run evidence contract")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("print-schema", help="print the evidence JSON Schema").set_defaults(
        func=_cmd_print_schema)
    sub.add_parser("print-log-schema", help="print the log-line JSON Schema").set_defaults(
        func=_cmd_print_log_schema)
    sub.add_parser("paths", help="print resolved paths and sample-window config").set_defaults(
        func=_cmd_paths)

    p_init = sub.add_parser("init", help="write empty evidence + log files")
    p_init.add_argument("--evidence", default=None)
    p_init.add_argument("--log", default=None)
    p_init.add_argument("--run-id", default=None)
    p_init.set_defaults(func=_cmd_init)

    p_val = sub.add_parser("validate", help="validate evidence file(s)")
    p_val.add_argument("files", nargs="+")
    p_val.set_defaults(func=_cmd_validate)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
