"""Tests for the RP-5 shadow-run evidence contract (src/shadow_evidence.py).

They pin the acceptance of t_5163660b:

  * the schema module is importable and self-consistent (Draft 2020-12 valid),
  * the example fixture validates against the schema,
  * stable paths resolve from defaults and from env overrides,
  * the writer round-trips all six sections, mirrors the log and the CSV,
  * invalid records are rejected (schema enforcement is real).

Pure stdlib + jsonschema; touches only tmp_path. Never the network, the
shadow DB, or the live router.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_SRC = _HERE.parent / "src"
if (_SRC / "shadow_evidence.py").is_file():
    sys.path.insert(0, str(_SRC))

import shadow_evidence as se  # noqa: E402

FIXTURE = _HERE / "fixtures" / "shadow_evidence" / "minimal_valid.json"


# ── schema module sanity ────────────────────────────────────────────────────
def test_schema_module_importable_and_version_pinned():
    assert se.SCHEMA_VERSION == "1.0.0"
    assert se.SHADOW_EVIDENCE_SCHEMA["$schema"].endswith("2020-12/schema")


def test_schema_itself_is_valid_draft_2020_12():
    from jsonschema import Draft202012Validator
    Draft202012Validator.check_schema(se.SHADOW_EVIDENCE_SCHEMA)
    Draft202012Validator.check_schema(se.LOG_LINE_SCHEMA)


def test_six_sections_match_criteria_a_to_f():
    assert se.SECTION_NAMES == {
        "a": "first_measurements",
        "b": "ollama_rate_series",
        "c": "extra_usage_events",
        "d": "glm52_extra_rate_samples",
        "e": "anomaly_alerts",
        "f": "routing_parity_snapshot",
    }
    props = se.SHADOW_EVIDENCE_SCHEMA["properties"]["sections"]["properties"]
    assert set(props) == set(se.SECTION_NAMES.values())


def test_provider_enum_is_the_canonical_six():
    assert se.EXPECTED_PROVIDERS == [
        "ours", "friend", "ollama_cloud", "ppq", "deepinfra", "openrouter",
    ]
    enum = (se.SHADOW_EVIDENCE_SCHEMA["properties"]["sections"]["properties"]
            ["first_measurements"]["properties"]["entries"]["items"]
            ["properties"]["provider"]["enum"])
    assert enum == se.EXPECTED_PROVIDERS


# ── fixture acceptance ──────────────────────────────────────────────────────
def test_example_fixture_validates():
    doc = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert se.validate_evidence(doc) == []


def test_example_fixture_covers_all_six_sections_non_empty():
    doc = json.loads(FIXTURE.read_text(encoding="utf-8"))
    sections = doc["sections"]
    assert len(sections["first_measurements"]["entries"]) == 6
    for name in ("ollama_rate_series", "extra_usage_events",
                 "glm52_extra_rate_samples", "anomaly_alerts"):
        assert len(sections[name]) >= 1, name
    assert len(sections["routing_parity_snapshot"]["rows"]) >= 1


# ── stable paths + env overrides ────────────────────────────────────────────
def test_default_stable_paths():
    paths = se.get_paths()
    assert paths["evidence"] == "/var/lib/shadow-run/evidence.json"
    assert paths["log"] == "/var/lib/shadow-run/evidence.log"
    assert paths["csv"] is None  # CSV mirror is opt-in


def test_env_overrides_paths(monkeypatch):
    monkeypatch.setenv(se.EVIDENCE_ENV, "/tmp/alt/evidence.json")
    monkeypatch.setenv(se.LOG_ENV, "/tmp/alt/evidence.log")
    monkeypatch.setenv(se.CSV_ENV, "/tmp/alt/evidence.csv")
    assert se.get_paths() == {
        "evidence": "/tmp/alt/evidence.json",
        "log": "/tmp/alt/evidence.log",
        "csv": "/tmp/alt/evidence.csv",
    }


def test_sample_window_defaults_and_env(monkeypatch):
    win = se.get_sample_window()
    assert win == {"duration_s": 48 * 3600, "refresh_interval_s": 300,
                   "stale_threshold_min": 30}
    monkeypatch.setenv(se.WINDOW_DURATION_ENV, "3600")
    monkeypatch.setenv(se.REFRESH_INTERVAL_ENV, "60")
    assert se.get_sample_window()["duration_s"] == 3600
    assert se.get_sample_window()["refresh_interval_s"] == 60


def test_sample_window_rejects_non_positive(monkeypatch):
    monkeypatch.setenv(se.WINDOW_DURATION_ENV, "0")
    with pytest.raises(ValueError):
        se.get_sample_window()


# ── writer round-trip over all six sections ─────────────────────────────────
@pytest.fixture()
def writer(tmp_path):
    return se.EvidenceWriter(
        evidence_path=str(tmp_path / "evidence.json"),
        log_path=str(tmp_path / "evidence.log"),
        run_id="rp5-test",
    )


def test_init_writes_valid_empty_evidence(writer):
    doc = writer.load()
    assert se.validate_evidence(doc) == []
    assert doc["run_id"] == "rp5-test"
    assert set(doc["sections"]) == set(se.SECTION_NAMES.values())


def test_writer_roundtrip_all_sections(writer, tmp_path):
    writer.append_first_measurement(
        "ours", "2026-09-14T19:43:10Z",
        "2026-09-14T19:42:35Z", "2026-09-14T20:12:35Z")
    writer.append_ollama_rate("2026-09-14T19:47:35Z", 0.0155)
    writer.append_extra_usage("2026-09-14T19:47:35Z", 1.0,
                              weekly_usage=0.62, regime="HIGH")
    writer.append_glm52_sample("2026-09-14T19:47:35Z", True, extra_rate=0.46)
    writer.append_anomaly("2026-09-14T19:47:35Z", "stale",
                          "routing_shadow_decisions",
                          observed=2451.0, threshold=1800)
    writer.set_section("f", {
        "kill_switch": "OFF",
        "expected_routing_fingerprint": "deadbeef",
        "rows": [{
            "requested_class": "default",
            "chosen_provider": "zai", "chosen_model": "glm-4.7",
            "expected_provider": "zai", "expected_model": "glm-4.7",
            "parity": True, "ts": "2026-09-14T19:47:35Z",
        }],
        "overall_parity": True,
    })

    doc = writer.load()
    assert se.validate_evidence(doc) == []
    a = doc["sections"]["first_measurements"]
    assert a["startup_ts"] == "2026-09-14T19:42:35Z"
    assert a["entries"][0] == {"provider": "ours",
                               "first_measured_at": "2026-09-14T19:43:10Z",
                               "within_window": True}
    assert doc["sections"]["ollama_rate_series"][0]["measured_rate"] == 0.0155
    assert doc["sections"]["extra_usage_events"][0]["triggered"] is True
    assert doc["sections"]["glm52_extra_rate_samples"][0]["extra_rate"] == 0.46
    assert doc["sections"]["anomaly_alerts"][0]["type"] == "stale"
    assert doc["sections"]["routing_parity_snapshot"]["overall_parity"] is True


def test_first_measurement_outside_window_flagged(writer):
    writer.append_first_measurement(
        "ppq", "2026-09-14T20:44:00Z",
        "2026-09-14T19:42:35Z", "2026-09-14T20:12:35Z")
    doc = writer.load()
    assert doc["sections"]["first_measurements"]["entries"][0]["within_window"] is False


def test_extra_usage_trigger_threshold(writer):
    writer.append_extra_usage("2026-09-14T19:47:35Z", 0.42)
    writer.append_extra_usage("2026-09-14T19:48:35Z", 1.3)
    doc = writer.load()
    events = doc["sections"]["extra_usage_events"]
    assert [e["triggered"] for e in events] == [False, True]


def test_log_mirror_and_csv_mirror(writer):
    writer.csv_path = writer.log_path.parent / "evidence.csv"
    writer.log("cycle complete", section="b",
               data=[{"ts": "2026-09-14T19:47:35Z", "measured_rate": 0.0155,
                      "target": 0.0155, "source": "seed"}])
    log_text = (writer.log_path).read_text(encoding="utf-8")
    line = json.loads(log_text.strip().splitlines()[-1])
    assert se.validate_log_line(line) == []
    assert line["section"] == "ollama_rate_series"
    csv_text = writer.csv_path.read_text(encoding="utf-8")
    assert "measured_rate" in csv_text.splitlines()[0]
    assert "0.0155" in csv_text


def test_invalid_record_rejected(writer):
    with pytest.raises(ValueError):
        writer.append_ollama_rate("2026-09-14T19:47:35Z", "not-a-number")
    with pytest.raises(ValueError):
        writer.append_anomaly("2026-09-14T19:47:35Z", "weird", "some_source")


def test_writer_refuses_to_persist_invalid_document(writer):
    doc = writer.load()
    doc["sections"]["ollama_rate_series"].append({"ts": "not-a-timestamp"})
    with pytest.raises(ValueError):
        writer.save(doc)
    # the on-disk file must still be valid after the refused write
    assert se.validate_evidence(writer.load()) == []


def test_bad_timestamp_rejected():
    doc = json.loads(FIXTURE.read_text(encoding="utf-8"))
    doc["sections"]["ollama_rate_series"][0]["ts"] = "2026-09-14 19:47:35"
    assert se.validate_evidence(doc) != []


# ── CLI ─────────────────────────────────────────────────writer round-trip ──
def test_cli_validate_fixture(capsys):
    assert se.main(["validate", str(FIXTURE)]) == 0
    out = capsys.readouterr().out
    assert "OK" in out


def test_cli_paths(capsys, monkeypatch):
    monkeypatch.setenv(se.EVIDENCE_ENV, "/tmp/x/evidence.json")
    assert se.main(["paths"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["paths"]["evidence"] == "/tmp/x/evidence.json"
