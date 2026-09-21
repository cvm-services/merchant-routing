"""Gate 1/2 tests for routstr_delist (T-D, ADR-007 Gate 4).

Spec-derived (task body + ADR-007 + Gate 2.5 cold review), stdlib unittest so
the suite runs under both `python3 -m unittest discover -s tests` and
`python3 -m pytest tests/ -v`. All tests are hermetic: the SSH backend is
faked or monkeypatched, all state lives in tmpdirs, no network is touched.
"""
import contextlib
import io
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

_HERE = Path(__file__).resolve().parent
# repo layout (../src) first; deployed bot layout (../scripts) second so the
# ~/.hermes/bot/tests copy runs against the deployed script copy.
for _cand in (_HERE.parent / "src", _HERE.parent / "scripts"):
    if (_cand / "routstr_delist.py").is_file():
        sys.path.insert(0, str(_cand))
        break

import routstr_delist as rd  # noqa: E402


def pred(key="zai", window="1h", hours: float | str | None = 10.0,
         unc: float | str | bool | None = 0.05):
    """burn_predictor.predict_exhaustion-shaped prediction dict (tolerates
    deliberately-corrupt values for negative tests)."""
    return {"key": key, "window": window,
            "exhausts_in_hours": hours, "uncertainty": unc}


class FakeBackend:
    """Scriptable stand-in for _SshBackend (never touches the network).

    pull_seq: optional list of result dicts consumed one per pull() call
    (for in-run retry / sequence tests); when absent pull_res is returned
    every call. sleep_s simulates a slow backend for deadline tests.
    """

    def __init__(self, pull_res=None, relist_res=None, pull_seq=None,
                 verify_res=None, sleep_s=0.0):
        self.calls = []
        self.pull_res = pull_res or {"ok": True, "pulled": ["gpt-4o", "claude-3"]}
        self.relist_res = relist_res or {"ok": True}
        self.verify_res = verify_res or {"ok": True, "count": 0}
        self.pull_seq = list(pull_seq) if pull_seq is not None else None
        self.sleep_s = sleep_s

    def pull(self, dry_run=False, deadline=None):
        self.calls.append(("pull", dry_run))
        if self.sleep_s:
            time.sleep(self.sleep_s)
        if self.pull_seq is not None:
            res = self.pull_seq.pop(0) if self.pull_seq else \
                {"ok": False, "error": "seq exhausted"}
            return dict(res)
        return dict(self.pull_res)

    def verify(self, dry_run=False, deadline=None):
        self.calls.append(("verify", dry_run))
        return dict(self.verify_res)

    def relist(self, names=None, dry_run=False, deadline=None):
        self.calls.append(("relist", list(names or []), dry_run))
        return dict(self.relist_res)


# ── Trigger 1: burn-rate accelerates (predicted exhaustion moves forward) ──
class TestBurnAcceleration(unittest.TestCase):
    def test_hours_decrease_past_threshold_fires(self):
        now = [pred(hours=6.0)]
        prev = [pred(hours=10.0)]
        fired = rd.exhaustion_accelerated(now, prev, move_hours=2.0)
        self.assertEqual(len(fired), 1)
        self.assertEqual(fired[0]["prev_hours"], 10.0)
        self.assertEqual(fired[0]["now_hours"], 6.0)

    def test_exhaustion_pushed_back_never_fires(self):
        """Burn slowing down (hours INCREASING) is not a delist trigger."""
        fired = rd.exhaustion_accelerated([pred(hours=12.0)], [pred(hours=10.0)])
        self.assertEqual(fired, [])

    def test_movement_below_threshold_does_not_fire(self):
        fired = rd.exhaustion_accelerated([pred(hours=8.9)], [pred(hours=10.0)],
                                          move_hours=2.0)
        self.assertEqual(fired, [])

    def test_threshold_is_inclusive(self):
        fired = rd.exhaustion_accelerated([pred(hours=8.0)], [pred(hours=10.0)],
                                          move_hours=2.0)
        self.assertEqual(len(fired), 1)

    def test_no_baseline_never_fires(self):
        self.assertEqual(rd.exhaustion_accelerated([pred(hours=1.0)], []), [])
        self.assertEqual(rd.exhaustion_accelerated([pred(hours=1.0)], None), [])

    def test_windows_tracked_separately(self):
        """Only the accelerating window is reported, keyed by key|window."""
        now = [pred(key="zai", window="1h", hours=5.0),
               pred(key="zai", window="24h", hours=40.0),
               pred(key="openrouter", window="1h", hours=9.5)]
        prev = [pred(key="zai", window="1h", hours=10.0),
                pred(key="zai", window="24h", hours=40.0),
                pred(key="openrouter", window="1h", hours=10.0)]
        fired = rd.exhaustion_accelerated(now, prev, move_hours=2.0)
        self.assertEqual([f["key"] for f in fired], ["zai"])
        self.assertEqual([f["window"] for f in fired], ["1h"])

    def test_non_numeric_hours_ignored(self):
        bad = [pred(hours=None), pred(hours="soon")]
        self.assertEqual(rd.exhaustion_accelerated(bad, [pred(hours=10.0)]), [])


# ── Trigger 2: Kalman variance elevated ────────────────────────────────────
class TestVarianceJump(unittest.TestCase):
    def test_uncertainty_above_threshold_fires(self):
        fired = rd.variance_jumped([pred(unc=0.55)], threshold=0.30)
        self.assertEqual(len(fired), 1)
        self.assertEqual(fired[0]["uncertainty"], 0.55)

    def test_uncertainty_below_threshold_quiet(self):
        self.assertEqual(rd.variance_jumped([pred(unc=0.29)], threshold=0.30), [])

    def test_threshold_is_strict(self):
        self.assertEqual(rd.variance_jumped([pred(unc=0.30)], threshold=0.30), [])

    def test_key_filter(self):
        preds = [pred(key="zai", unc=0.9), pred(key="openrouter", unc=0.9)]
        fired = rd.variance_jumped(preds, threshold=0.30, key="openrouter")
        self.assertEqual([f["key"] for f in fired], ["openrouter"])

    def test_missing_uncertainty_ignored(self):
        p = pred()
        del p["uncertainty"]
        self.assertEqual(rd.variance_jumped([p], threshold=0.0), [])

    def test_non_numeric_uncertainty_ignored_not_crash(self):
        """Type-guard like exhausts_in_hours (review should-fix): a string
        or bool uncertainty must be skipped, never raise TypeError."""
        fired = rd.variance_jumped([pred(unc="0.9"), pred(unc=True)],
                                  threshold=0.30)
        self.assertEqual(fired, [])


# ── Trigger 3: manual override ─────────────────────────────────────────────
class TestManualOverride(unittest.TestCase):
    def test_marker_file_present_fires(self):
        with tempfile.TemporaryDirectory() as d:
            m = Path(d) / "override"
            m.write_text("")
            self.assertTrue(rd.manual_override(str(m)))

    def test_missing_marker_quiet(self):
        self.assertFalse(rd.manual_override("/nonexistent/override"))

    def test_none_path_quiet(self):
        self.assertFalse(rd.manual_override(None))

    def test_directory_at_marker_path_is_not_an_override(self):
        """Marker semantics pinned: only a FILE counts (isfile, not exists)."""
        with tempfile.TemporaryDirectory() as d:
            self.assertFalse(rd.manual_override(d))


# ── Decision assembly ──────────────────────────────────────────────────────
class TestEvaluateTriggers(unittest.TestCase):
    def test_first_run_never_fires_on_acceleration(self):
        """No baseline -> acceleration cannot fire (would be a false positive)."""
        dec = rd.evaluate_triggers([pred(hours=0.5)], None)
        self.assertFalse(dec["fire"])
        self.assertEqual(dec["reasons"], [])

    def test_baseline_state_drives_acceleration(self):
        prev_state = {"snapshot": {"zai|1h": 10.0}}   # legacy '|' keys
        dec = rd.evaluate_triggers([pred(hours=6.0)], prev_state)
        self.assertTrue(dec["fire"])
        self.assertTrue(any("exhaustion accelerated" in r for r in dec["reasons"]))

    def test_unitsep_snapshot_keys_supported(self):
        key = f"zai{rd._SNAP_SEP}1h"
        dec = rd.evaluate_triggers([pred(hours=5.0)], {"snapshot": {key: 10.0}})
        self.assertTrue(dec["fire"])

    def test_variance_only_fires(self):
        dec = rd.evaluate_triggers([pred(hours=10.0, unc=0.8)], None)
        self.assertTrue(dec["fire"])
        self.assertTrue(any("kalman variance" in r for r in dec["reasons"]))

    def test_override_only_fires(self):
        dec = rd.evaluate_triggers([], None, override=True)
        self.assertTrue(dec["fire"])
        self.assertIn("manual override", dec["reasons"])

    def test_all_triggers_reported(self):
        prev_state = {"snapshot": {f"zai{rd._SNAP_SEP}1h": 10.0}}
        dec = rd.evaluate_triggers([pred(hours=5.0, unc=0.9)], prev_state,
                                   override=True)
        self.assertTrue(dec["fire"])
        self.assertEqual(len(dec["reasons"]), 3)
        self.assertEqual(dec["triggers"]["manual"], True)

    def test_quiet_predictions_no_fire(self):
        prev_state = {"snapshot": {"zai|1h": 10.0}}
        dec = rd.evaluate_triggers([pred(hours=10.5, unc=0.01)], prev_state)
        self.assertFalse(dec["fire"])


# ── Snapshot key round-trip (cold-review nit 7) ────────────────────────────
class TestSnapshotKeys(unittest.TestCase):
    def test_key_containing_pipe_roundtrips(self):
        preds = [pred(key="vendor|eu", window="1h", hours=10.0)]
        snap = rd.snapshot_preds(preds)
        # parse the single snap key
        k = next(iter(snap))
        key, window = rd._parse_snap_key(k)
        self.assertEqual(key, "vendor|eu")
        self.assertEqual(window, "1h")
        # and acceleration detection works through a full state cycle
        st = rd.update_state({}, ts=1.0, preds=preds, delisted=False)
        dec = rd.evaluate_triggers([pred(key="vendor|eu", hours=6.0)], st)
        self.assertTrue(dec["fire"])


# ── Durable state ──────────────────────────────────────────────────────────
class TestState(unittest.TestCase):
    def test_update_state_snapshot_and_flag(self):
        st = rd.update_state({}, ts=1.0, preds=[pred(hours=3.5)],
                             delisted=True, last_reason="x")
        self.assertEqual(st["snapshot"], {f"zai{rd._SNAP_SEP}1h": 3.5})
        self.assertTrue(st["delisted"])
        self.assertEqual(st["last_reason"], "x")
        self.assertEqual(st["ts"], 1.0)

    def test_update_state_empty_preds_preserves_baseline(self):
        """A missing/corrupt feed must NOT wipe the stored baseline
        (cold-review finding 3)."""
        st0 = rd.update_state({}, ts=1.0, preds=[pred(hours=10.0)],
                              delisted=False)
        st1 = rd.update_state(st0, ts=2.0, preds=[], delisted=False)
        self.assertEqual(st1["snapshot"], st0["snapshot"])

    def test_save_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            p = str(Path(d) / "nested" / "state.json")
            st = rd.update_state({}, ts=2.0, preds=[pred(hours=7.0)],
                                 delisted=True, last_reason="r")
            self.assertTrue(rd.save_state(p, st))
            self.assertEqual(rd.load_state(p), st)

    def test_load_state_never_raises(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "bad.json"
            p.write_text("{not json")
            self.assertEqual(rd.load_state(str(p)), {})
            self.assertEqual(rd.load_state(str(Path(d) / "missing")), {})

    def test_load_state_rejects_non_dict_json(self):
        """A well-formed but non-dict state file loads as {} (guard pin)."""
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "list.json"
            p.write_text('["delisted", true]')
            self.assertEqual(rd.load_state(str(p)), {})

    def test_save_state_atomic_no_tmp_left_behind(self):
        """Atomicity (cold-review finding 4): every save replaces the file in
        one os.replace; no temp files ever remain in the directory."""
        with tempfile.TemporaryDirectory() as d:
            p = str(Path(d) / "state.json")
            rd.save_state(p, {"a": 1})
            rd.save_state(p, {"a": 2})
            rd.save_state(p, {"a": 3})
            self.assertEqual(sorted(os.listdir(d)), ["state.json"])
            self.assertEqual(rd.load_state(p), {"a": 3})

    def test_torn_write_never_replaces_good_state(self):
        """A crash mid-dump must leave the previous state fully intact (the
        old plain open("w") truncated the file first)."""
        with tempfile.TemporaryDirectory() as d:
            p = str(Path(d) / "state.json")
            self.assertTrue(rd.save_state(p, {"delisted": True, "ts": 1.0}))

            def boom(*a, **kw):
                a[1].write('{"delisted": tru')   # partial write, then crash
                raise RuntimeError("disk full")

            with mock.patch.object(rd.json, "dump", side_effect=boom):
                self.assertFalse(rd.save_state(p, {"delisted": False}))
            self.assertEqual(rd.load_state(p), {"delisted": True, "ts": 1.0})
            self.assertEqual(sorted(os.listdir(d)), ["state.json"])


# ── SALE vs PROVIDER distinction (the load-bearing requirement) ────────────
class TestSaleNotProvider(unittest.TestCase):
    def test_pull_sql_touches_only_models_listing(self):
        sql = rd.pull_listing_sql()
        self.assertIn("models", sql)
        self.assertIn("enabled=0", sql)
        low = sql.lower()
        self.assertNotIn("upstream_providers", low)
        self.assertNotIn("provider", low)

    def test_relist_sql_touches_only_models_listing(self):
        sql = rd.relist_sql()
        self.assertIn("models", sql)
        low = sql.lower()
        self.assertNotIn("upstream_providers", low)
        self.assertNotIn("provider", low)

    def test_pull_payload_scoped_to_models_table(self):
        p = rd.pull_listing_payload()
        self.assertIn("UPDATE models SET enabled=0 WHERE enabled=1", p)
        self.assertNotIn("upstream_providers", p)
        self.assertIn("/app/data/keys.db", p)
        # captures advertised names for a scoped relist
        self.assertIn("SELECT name FROM models WHERE enabled=1", p)

    def test_relist_payload_parameterized_for_known_names(self):
        names = ["a b", "c';drop"]
        p = rd.relist_payload(names)
        self.assertIn("name IN (?,?)", p)
        self.assertIn(repr(names), p)          # embedded as a python literal
        self.assertNotIn("name IN ('a b'", p)  # never string-interpolated SQL

    def test_relist_payload_fallback_when_no_names(self):
        self.assertIn(rd.relist_sql(), rd.relist_payload([]))

    def test_verify_payload_scoped_to_models_listing(self):
        """The re-fetch confirmation payload is read-only and listing-scoped."""
        p = rd.verify_pull_payload()
        self.assertIn("SELECT COUNT(*) FROM models WHERE enabled=1", p)
        self.assertIn("/app/data/keys.db", p)
        low = p.lower()
        self.assertNotIn("upstream_providers", low)
        self.assertNotIn("update", low)   # the re-fetch never mutates

    def test_ssh_cmd_is_single_shlex_safe_remote_command(self):
        """Cold-review BLOCKER 1 regression: ssh joins args after the host
        into ONE remote-shell string — the remote command must be a single
        properly-quoted argv element that re-parses to the intended argv."""
        payload = rd.pull_listing_payload()
        cmd = rd.build_ssh_docker_cmd("debian@host", "routstr public", payload)
        self.assertEqual(cmd[0], "ssh")
        self.assertEqual(cmd[1], "debian@host")
        self.assertEqual(len(cmd), 3)  # host + exactly one remote command
        parts = shlex.split(cmd[2])    # what the remote shell will parse
        self.assertEqual(parts[:4], ["docker", "exec", "routstr public",
                                     "python3"])
        self.assertEqual(parts[4], "-c")
        self.assertEqual(parts[5], payload)  # payload survives round-trip intact

    def test_backend_pull_delegates(self):
        fb = FakeBackend()
        res = rd.pull_listing(fb, dry_run=False)
        self.assertEqual(res["ok"], True)
        self.assertEqual(fb.calls, [("pull", False)])

    def test_backend_relist_receives_scoped_names(self):
        fb = FakeBackend()
        rd.relist(fb, names=["gpt-4o"], dry_run=False)
        self.assertEqual(fb.calls, [("relist", ["gpt-4o"], False)])

    def test_backend_dry_run_preferred(self):
        class Fake:
            def pull(self, dry_run=False):
                raise AssertionError("must not hit ssh in dry-run")

            def dry_run_pull(self, dry_run=True):
                return {"ok": True, "dry_run": True}

        res = rd.pull_listing(Fake(), dry_run=True)
        self.assertTrue(res["dry_run"])


# ── Event-based delist signal ──────────────────────────────────────────────
class TestDelistEvent(unittest.TestCase):
    def test_missing_nsec_returns_none(self):
        self.assertIsNone(rd.build_delist_event("/nonexistent/nsec"))

    def test_event_argv_shape(self):
        with tempfile.TemporaryDirectory() as d:
            sec = Path(d) / "nsec"
            sec.write_text("nsec1dummy\n")
            argv = rd.build_delist_event(str(sec), relays=["wss://relay.example"])
        self.assertIsNotNone(argv)
        argv = argv or []
        self.assertIn("--kind", argv)
        # NIP-78 application data, not a squatted registered 303xx kind
        self.assertEqual(argv[argv.index("--kind") + 1], "30078")
        self.assertIn("d:routstr-delist", argv)
        self.assertIn("--env-sec", argv)      # never --sec: leaks key via ps
        self.assertNotIn("--sec", argv)
        self.assertIn("wss://relay.example", argv)
        content = json.loads(argv[argv.index("--content") + 1])
        self.assertTrue(content["delisted"])

    def test_event_content_reflects_relist(self):
        """RELIST event content must carry delisted:false — with a REAL sec
        file (the old version tested the missing-sec path, which returns
        None before the content is ever built)."""
        with tempfile.TemporaryDirectory() as d:
            sec = Path(d) / "nsec"
            sec.write_text("nsec1dummy\n")
            argv = rd.build_delist_event(str(sec), delisted=False)
        self.assertIsNotNone(argv)
        argv = argv or []
        content = json.loads(argv[argv.index("--content") + 1])
        self.assertFalse(content["delisted"])


# ── 5-minute SLA wiring (cold-review finding 5) ────────────────────────────
class TestSlaWiring(unittest.TestCase):
    def test_detection_plus_action_bounded_by_window(self):
        """The SLA invariant the doc promises: worst-case detection (one full
        poll cadence) + worst-case in-run action budget must fit the window.
        ACTION_BUDGET_S is consumed by main() as a real monotonic deadline."""
        self.assertLessEqual(rd.POLL_CADENCE_S + rd.ACTION_BUDGET_S,
                             rd.TRIGGER_ACTION_WINDOW_S)
        self.assertEqual(rd.ACTION_BUDGET_S,
                         rd.TRIGGER_ACTION_WINDOW_S - rd.POLL_CADENCE_S)
        # one attempt = pull + verify round-trips; both must fit the budget
        self.assertLessEqual(2 * rd.SSH_TIMEOUT_S, rd.ACTION_BUDGET_S)

    def test_transient_failure_retried_in_run(self):
        """A failed pull attempt is retried once in-run (bounded: counts as a
        single breaker failure) and a transient failure recovers in-run."""
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        state = str(Path(d) / "state.json")
        fb = FakeBackend(pull_seq=[{"ok": False, "error": "ssh down"},
                                    {"ok": True, "pulled": ["gpt-4o"]}])
        with mock.patch.object(rd, "_SshBackend", lambda t, c: fb):
            with contextlib.redirect_stdout(io.StringIO()) as buf:
                rc = rd.main(["--state", state, "--manual"])
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(buf.getvalue())["action"], "delist")
        # attempt 1 (pull fails, no verify) + in-run retry (pull + verify)
        self.assertEqual(fb.calls,
                         [("pull", False), ("pull", False), ("verify", False)])
        self.assertEqual(rd.load_state(state)["consecutive_failures"], 0)

    def test_no_retry_past_deadline(self):
        """The action deadline caps in-run retries: once the budget is spent,
        no further attempt is made (hard SLA bound)."""
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        state = str(Path(d) / "state.json")
        fb = FakeBackend(pull_res={"ok": False, "error": "ssh down"},
                         sleep_s=0.02)
        with mock.patch.object(rd, "ACTION_BUDGET_S", 0.001), \
                mock.patch.object(rd, "_SshBackend", lambda t, c: fb):
            with contextlib.redirect_stdout(io.StringIO()):
                rc = rd.main(["--state", state, "--manual"])
        self.assertEqual(rc, 1)
        self.assertEqual(len(fb.calls), 1)          # deadline spent: no retry


class TestFiveMinuteWindow(unittest.TestCase):
    def test_triggered_run_pulls_within_window(self):
        """A fired trigger must pull the listing IN-RUN (well under 5 min).
        Dry-run is intent-only: no durable delisted flip (purity)."""
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        state = str(Path(d) / "state.json")
        t0 = time.monotonic()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = rd.main(["--manual", "--dry-run", "--state", state])
        elapsed = time.monotonic() - t0
        self.assertEqual(rc, 0)
        self.assertLess(elapsed, rd.TRIGGER_ACTION_WINDOW_S)
        self.assertEqual(json.loads(buf.getvalue())["action"], "delist")
        st = rd.load_state(state)
        self.assertFalse(st.get("delisted", False))   # dry-run flips nothing
        self.assertIn("last_dry_run", st)


# ── Failure semantics (cold-review findings 2 + 3) ────────────────────────
class TestFailureSemantics(unittest.TestCase):
    def test_failed_pull_keeps_baseline_and_exits_nonzero(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        state = str(Path(d) / "state.json")
        preds_a = Path(d) / "a.json"   # baseline 10h
        preds_b = Path(d) / "b.json"   # accelerated to 5h
        preds_a.write_text(json.dumps([pred(hours=10.0)]))
        preds_b.write_text(json.dumps([pred(hours=5.0)]))
        failing = FakeBackend(pull_res={"ok": False, "error": "ssh down"})
        with mock.patch.object(rd, "_SshBackend", lambda t, c: failing):
            with contextlib.redirect_stdout(io.StringIO()):
                rd.main(["--state", state, "--preds", str(preds_a)])
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = rd.main(["--state", state, "--preds", str(preds_b)])
        out = json.loads(buf.getvalue())
        self.assertEqual(rc, 1)                       # cron must see failure
        self.assertEqual(out["action"], "delist_failed")
        st = rd.load_state(state)
        self.assertFalse(st["delisted"])              # flag not set on failure
        self.assertIn("last_pull_error", st)
        self.assertEqual(st["consecutive_failures"], 1)
        # baseline NOT consumed: same acceleration still fires on retry
        dec = rd.evaluate_triggers(json.loads(preds_b.read_text()), st)
        self.assertTrue(dec["fire"])

    def test_dry_run_failure_is_intent_only(self):
        """Dry-run purity (verification finding 7c): a dry-run failure records
        intent but never durable failure state — no breaker counting, no
        last_pull_error, no delist flag."""
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        state = str(Path(d) / "state.json")
        failing = FakeBackend(pull_res={"ok": False, "error": "ssh down"})
        with mock.patch.object(rd, "_SshBackend", lambda t, c: failing):
            with contextlib.redirect_stdout(io.StringIO()) as buf:
                rc = rd.main(["--state", state, "--manual", "--dry-run"])
        self.assertEqual(rc, 1)
        self.assertEqual(json.loads(buf.getvalue())["action"], "delist_failed")
        st = rd.load_state(state)
        self.assertNotIn("last_pull_error", st)
        self.assertEqual(st.get("consecutive_failures", 0), 0)
        self.assertIn("last_dry_run", st)

    def test_failed_relist_exits_nonzero(self):
        failing = FakeBackend(relist_res={"ok": False, "error": "ssh down"})
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        state = str(Path(d) / "state.json")
        rd.save_state(state, {"delisted": True,
                              "pulled_models": ["gpt-4o"]})
        buf = io.StringIO()
        with mock.patch.object(rd, "_SshBackend", lambda t, c: failing), \
                contextlib.redirect_stdout(buf):
            rc = rd.main(["--state", state, "--relist"])
        self.assertEqual(rc, 1)
        self.assertEqual(json.loads(buf.getvalue())["action"], "relist_failed")
        self.assertTrue(rd.load_state(state)["delisted"])

    def test_unreadable_preds_feed_is_error_not_quiet(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        state = str(Path(d) / "state.json")
        rd.save_state(state, {"snapshot": {f"zai{rd._SNAP_SEP}1h": 10.0}})
        bad = Path(d) / "bad.json"
        bad.write_text("{mid-write")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = rd.main(["--state", state, "--preds", str(bad), "--dry-run"])
        out = json.loads(buf.getvalue())
        self.assertEqual(rc, 1)
        self.assertTrue(out["preds_error"])
        # baseline survives the bad read (acceleration stays detectable)
        st = rd.load_state(state)
        self.assertEqual(st["snapshot"], {f"zai{rd._SNAP_SEP}1h": 10.0})


# ── Re-fetch confirmation (cold-review finding 2) ──────────────────────────
class TestRefetchConfirmation(unittest.TestCase):
    def test_verify_gates_success(self):
        """Success requires the independent post-pull re-fetch: the pull
        round-trip's self-report is not enough."""
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        state = str(Path(d) / "state.json")
        fb = FakeBackend(pull_res={"ok": True, "pulled": ["gpt-4o"]},
                         verify_res={"ok": True, "count": 1})
        with mock.patch.object(rd, "_SshBackend", lambda t, c: fb):
            with contextlib.redirect_stdout(io.StringIO()) as buf:
                rc = rd.main(["--state", state, "--manual"])
        out = json.loads(buf.getvalue())
        self.assertEqual(rc, 1)                  # listing still advertised
        self.assertEqual(out["action"], "delist_failed")
        self.assertFalse(rd.load_state(state)["delisted"])
        self.assertEqual(fb.calls.count(("verify", False)), 2)
        # one verify per attempt; both attempts saw count=1
        self.assertEqual(len(fb.calls), 4)        # 2 pulls + 2 verifies

    def test_confirmed_delist_resets_breaker_and_records(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        state = str(Path(d) / "state.json")
        rd.save_state(state, {"consecutive_failures": 2, "delisted": False})
        fb = FakeBackend(pull_res={"ok": True, "pulled": ["gpt-4o"]},
                         verify_res={"ok": True, "count": 0})
        with mock.patch.object(rd, "_SshBackend", lambda t, c: fb):
            with contextlib.redirect_stdout(io.StringIO()) as buf:
                rc = rd.main(["--state", state, "--manual"])
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(buf.getvalue())["action"], "delist")
        st = rd.load_state(state)
        self.assertTrue(st["delisted"])
        self.assertEqual(st["consecutive_failures"], 0)   # success resets
        self.assertEqual(st["pulled_models"], ["gpt-4o"])

    def test_verify_failure_is_attempt_failure(self):
        """A verify round-trip that fails outright counts as a failed attempt
        (retry re-pulls; remote pull is idempotent)."""
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        state = str(Path(d) / "state.json")
        fb = FakeBackend(pull_res={"ok": True, "pulled": ["m"]},
                         verify_res={"ok": False, "error": "ssh timeout"})
        with mock.patch.object(rd, "_SshBackend", lambda t, c: fb):
            with contextlib.redirect_stdout(io.StringIO()):
                rc = rd.main(["--state", state, "--manual"])
        self.assertEqual(rc, 1)
        st = rd.load_state(state)
        self.assertFalse(st["delisted"])
        self.assertEqual(st["consecutive_failures"], 1)


# ── Scoped relist round-trip (cold-review finding 4) ──────────────────────
class TestScopedRelist(unittest.TestCase):
    def test_pull_captures_names_and_relist_restores_them(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        state = str(Path(d) / "state.json")
        fb = FakeBackend(pull_res={"ok": True, "pulled": ["gpt-4o", "llama-3"]})
        with mock.patch.object(rd, "_SshBackend", lambda t, c: fb):
            with contextlib.redirect_stdout(io.StringIO()):
                rd.main(["--state", state, "--manual"])
        st = rd.load_state(state)
        self.assertEqual(st["pulled_models"], ["gpt-4o", "llama-3"])
        fb2 = FakeBackend()
        with mock.patch.object(rd, "_SshBackend", lambda t, c: fb2):
            with contextlib.redirect_stdout(io.StringIO()):
                rc = rd.main(["--state", state, "--relist"])
        self.assertEqual(rc, 0)
        self.assertEqual(fb2.calls, [("relist", ["gpt-4o", "llama-3"], False)])
        self.assertNotIn("pulled_models", rd.load_state(state))

    def test_relist_publishes_countering_event(self):
        """A successful --relist must publish the delisted:false event
        (cold-review finding 9 / round-2 NIT 3)."""
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        state = str(Path(d) / "state.json")
        rd.save_state(state, {"delisted": True, "pulled_models": ["gpt-4o"]})
        with mock.patch.object(rd, "_SshBackend", lambda t, c: FakeBackend()), \
                mock.patch.object(rd, "publish_delist_event") as pub, \
                contextlib.redirect_stdout(io.StringIO()):
            rc = rd.main(["--state", state, "--relist", "--nsec", "/tmp/nsec"])
        self.assertEqual(rc, 0)
        pub.assert_called_once_with("/tmp/nsec", delisted=False)

    def test_delist_publishes_event_on_success(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        state = str(Path(d) / "state.json")
        with mock.patch.object(rd, "_SshBackend",
                               lambda t, c: FakeBackend()), \
                mock.patch.object(rd, "publish_delist_event") as pub, \
                contextlib.redirect_stdout(io.StringIO()):
            rd.main(["--state", state, "--manual", "--nsec", "/tmp/nsec"])
        pub.assert_called_once_with("/tmp/nsec", delisted=True)


# ── CLI ────────────────────────────────────────────────────────────────────
class TestCLI(unittest.TestCase):
    def run_main(self, argv):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        state = str(Path(d) / "state.json")
        argv = ["--state", state] + argv
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = rd.main(argv)
        return rc, json.loads(buf.getvalue()), state

    def test_status_prints_state(self):
        rc, out, state = self.run_main(["--status"])
        self.assertEqual(rc, 0)
        self.assertIn("delisted", out)

    def test_quiet_run_without_preds_keeps_absent_baseline(self):
        rc, out, state = self.run_main(["--dry-run"])
        self.assertEqual(rc, 0)
        self.assertEqual(out["action"], "none")
        self.assertFalse(out["preds_error"])
        st = rd.load_state(state)
        self.assertFalse(st["delisted"])

    def test_baseline_then_acceleration_fires(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        state = str(Path(d) / "state.json")
        preds_a = Path(d) / "a.json"
        preds_b = Path(d) / "b.json"
        preds_a.write_text(json.dumps([pred(hours=10.0)]))
        preds_b.write_text(json.dumps([pred(hours=5.0)]))
        buf = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()):
            rd.main(["--state", state, "--preds", str(preds_a), "--dry-run"])
            with contextlib.redirect_stdout(buf):
                rc = rd.main(["--state", state, "--preds", str(preds_b),
                              "--dry-run"])
        self.assertEqual(rc, 0)
        out = json.loads(buf.getvalue())
        self.assertEqual(out["action"], "delist")
        self.assertTrue(any("exhaustion accelerated" in r for r in out["reasons"]))
        # dry-run purity: intent only — the durable delisted flag is NOT set
        self.assertFalse(rd.load_state(state)["delisted"])

    def test_manual_marker_file_fires(self):
        with tempfile.TemporaryDirectory() as d:
            marker = Path(d) / "override"
            marker.write_text("")
            rc, out, _ = self.run_main(["--override", str(marker), "--dry-run"])
        self.assertEqual(rc, 0)
        self.assertEqual(out["action"], "delist")
        self.assertIn("manual override", out["reasons"])

    def test_delist_flag_forces_fire(self):
        rc, out, _ = self.run_main(["--delist", "--dry-run"])
        self.assertEqual(rc, 0)
        self.assertEqual(out["action"], "delist")

    def test_relist_restores(self):
        """No captured names -> blanket relist REFUSED (cold-review finding 4:
        enabling operator-disabled rows). The live state file has exactly this
        no-pulled_models shape."""
        rc, out, state = self.run_main(["--relist", "--dry-run"])
        self.assertEqual(rc, 1)
        self.assertEqual(out["action"], "relist_refused")

    def test_relist_any_is_explicit_blanket_opt_in(self):
        rc, out, _ = self.run_main(["--relist", "--relist-any", "--dry-run"])
        self.assertEqual(rc, 0)
        self.assertEqual(out["action"], "relist")

    def test_status_reports_all_state_keys(self):
        """--status key drop regression (review mutation M7): every state
        summary key must be present, including the breaker fields."""
        rc, out, _ = self.run_main(["--status"])
        self.assertEqual(rc, 0)
        for k in ("delisted", "ts", "last_reason", "pulled_models",
                  "snapshot_windows", "consecutive_failures", "blocked"):
            self.assertIn(k, out)

    def test_cli_variance_threshold_is_wired(self):
        """Review mutation M8: --variance must actually feed the trigger."""
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        feed = Path(d) / "p.json"
        feed.write_text(json.dumps([pred(unc=0.05)]))
        rc, out, _ = self.run_main(["--preds", str(feed),
                                    "--variance", "0.01", "--dry-run"])
        self.assertEqual(out["action"], "delist")
        rc, out, _ = self.run_main(["--preds", str(feed),
                                    "--variance", "0.9", "--dry-run"])
        self.assertEqual(out["action"], "none")

    def test_cli_move_hours_threshold_is_wired(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        state = str(Path(d) / "state.json")
        a, b = Path(d) / "a.json", Path(d) / "b.json"
        a.write_text(json.dumps([pred(hours=10.0)]))
        b.write_text(json.dumps([pred(hours=5.0)]))
        with contextlib.redirect_stdout(io.StringIO()):
            rd.main(["--state", state, "--preds", str(a), "--dry-run"])
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rd.main(["--state", state, "--preds", str(b),
                     "--move-hours", "100", "--dry-run"])
        self.assertEqual(json.loads(buf.getvalue())["action"], "none")

    def test_preds_key_scopes_triggers(self):
        """Review finding 3 (MEDIUM): an openrouter variance spike must not
        pull the routstr SALE when --preds-key scopes the feed."""
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        feed = Path(d) / "p.json"
        feed.write_text(json.dumps([pred(key="openrouter", unc=0.9),
                                    pred(key="routstr", unc=0.05)]))
        rc, out, _ = self.run_main(["--preds", str(feed),
                                    "--preds-key", "routstr", "--dry-run"])
        self.assertEqual(out["action"], "none")
        rc, out, _ = self.run_main(["--preds", str(feed),
                                    "--preds-key", "openrouter", "--dry-run"])
        self.assertEqual(out["action"], "delist")

    def test_missing_preds_file_when_not_given_is_not_error(self):
        """No --preds at all (override-only deployments) stays rc 0."""
        rc, out, _ = self.run_main(["--dry-run"])
        self.assertEqual(rc, 0)
        self.assertFalse(out["preds_error"])

    def test_non_dict_preds_entries_are_dropped_not_fatal(self):
        """A valid-JSON feed with garbage entries must not crash the run
        (cold-review round-2 NIT 1)."""
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        state = str(Path(d) / "state.json")
        feed = Path(d) / "p.json"
        feed.write_text(json.dumps(["garbage", 42, pred(hours=10.0)]))
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = rd.main(["--state", state, "--preds", str(feed), "--dry-run"])
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(buf.getvalue())["action"], "none")
        # the one well-formed prediction formed the baseline
        st = rd.load_state(state)
        self.assertEqual(st["snapshot"], {f"zai{rd._SNAP_SEP}1h": 10.0})


# ── Circuit breaker (task body: 3x fail -> BLOCKED; finding 6) ──────────────
class TestCircuitBreaker(unittest.TestCase):
    def _fail(self, state, n):
        failing = FakeBackend(pull_res={"ok": False, "error": "ssh down"})
        rcs = []
        with mock.patch.object(rd, "_SshBackend", lambda t, c: failing):
            for _ in range(n):
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    rcs.append((rd.main(["--state", state, "--manual"]),
                                json.loads(buf.getvalue())))
        return rcs

    def test_third_failure_blocks_and_exits_3(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        state = str(Path(d) / "state.json")
        rcs = self._fail(state, 3)
        # failures 1 and 2: normal delist_failed, rc 1
        self.assertEqual([rc for rc, _ in rcs[:2]], [1, 1])
        self.assertEqual([out["action"] for _, out in rcs[:2]],
                         ["delist_failed", "delist_failed"])
        # failure 3: BLOCKED, rc 3, surfaced in output + state
        self.assertEqual(rcs[2][0], 3)
        self.assertTrue(rcs[2][1]["blocked"])
        self.assertEqual(rcs[2][1]["action"], "delist_failed")
        st = rd.load_state(state)
        self.assertEqual(st["consecutive_failures"], 3)
        self.assertTrue(st["blocked"])

    def test_blocked_halts_attempts_attempt_4_never_runs(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        state = str(Path(d) / "state.json")
        self._fail(state, 3)
        fb = FakeBackend(pull_res={"ok": True, "pulled": ["x"]})
        with mock.patch.object(rd, "_SshBackend", lambda t, c: fb):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = rd.main(["--state", state, "--manual"])
        out = json.loads(buf.getvalue())
        # blocked: no attempt made, no recovery while blocked
        self.assertEqual(fb.calls, [])
        self.assertEqual(rc, 3)
        self.assertEqual(out["action"], "blocked")
        self.assertTrue(out["blocked"])

    def test_success_resets_the_counter(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        state = str(Path(d) / "state.json")
        self._fail(state, 2)
        fb = FakeBackend(pull_res={"ok": True, "pulled": ["x"]},
                         verify_res={"ok": True, "count": 0})
        with mock.patch.object(rd, "_SshBackend", lambda t, c: fb):
            with contextlib.redirect_stdout(io.StringIO()):
                rc = rd.main(["--state", state, "--manual"])
        self.assertEqual(rc, 0)
        st = rd.load_state(state)
        self.assertEqual(st["consecutive_failures"], 0)
        self.assertFalse(st["blocked"])

    def test_relist_refused_while_blocked(self):
        """The breaker also guards the relist path: a blocked state must not
        allow remote actions until the operator clears it (--unblock)."""
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        state = str(Path(d) / "state.json")
        self._fail(state, 3)
        fb = FakeBackend(relist_res={"ok": True})
        with mock.patch.object(rd, "_SshBackend", lambda t, c: fb):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = rd.main(["--state", state, "--relist",
                              "--relist-any", "--dry-run"])
        self.assertEqual(rc, 3)
        self.assertEqual(json.loads(buf.getvalue())["action"], "blocked")
        self.assertEqual(fb.calls, [])

    def test_unblock_clears_and_allows_action(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        state = str(Path(d) / "state.json")
        self._fail(state, 3)
        fb = FakeBackend(pull_res={"ok": True, "pulled": ["x"]},
                         verify_res={"ok": True, "count": 0})
        with mock.patch.object(rd, "_SshBackend", lambda t, c: fb):
            with contextlib.redirect_stdout(io.StringIO()):
                rc = rd.main(["--state", state, "--manual", "--unblock"])
        self.assertEqual(rc, 0)
        st = rd.load_state(state)
        self.assertFalse(st["blocked"])
        self.assertEqual(st.get("consecutive_failures", 0), 0)

    def test_relist_success_clears_breaker(self):
        """An operator --relist is an explicit action: success clears both the
        delisted flag and the breaker state."""
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        state = str(Path(d) / "state.json")
        self._fail(state, 3)
        fb = FakeBackend(relist_res={"ok": True})
        with mock.patch.object(rd, "_SshBackend", lambda t, c: fb):
            with contextlib.redirect_stdout(io.StringIO()) as buf:
                rc = rd.main(["--state", state, "--relist", "--relist-any",
                              "--unblock"])
        self.assertEqual(rc, 0)
        st = rd.load_state(state)
        self.assertFalse(st["blocked"])
        self.assertFalse(st["delisted"])


# ── Feed freshness guard (cold-review finding 3, HIGH) ─────────────────────
class TestStalenessGuard(unittest.TestCase):
    def _mkfeed(self, d, age, rows=None):
        feed = Path(d) / "preds.json"
        feed.write_text(json.dumps(rows if rows is not None
                                   else [pred(hours=10.0, unc=0.9)]))
        old = time.time() - age
        os.utime(feed, (old, old))
        return feed

    def test_stale_feed_never_triggers(self):
        """A variance-elevated but STALE feed must not fire (level-based
        variance on dead data delists forever otherwise)."""
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        state = str(Path(d) / "state.json")
        feed = self._mkfeed(d, 6 * 3600)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = rd.main(["--state", state, "--preds", str(feed),
                          "--dry-run"])
        out = json.loads(buf.getvalue())
        self.assertEqual(rc, 1)
        self.assertEqual(out["action"], "none")
        self.assertTrue(out["preds_stale"])
        self.assertFalse(rd.load_state(state)["delisted"])

    def test_fresh_feed_still_fires(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        state = str(Path(d) / "state.json")
        feed = self._mkfeed(d, 30)          # fresh: 30 s old
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = rd.main(["--state", state, "--preds", str(feed),
                          "--dry-run"])
        out = json.loads(buf.getvalue())
        self.assertEqual(rc, 0)
        self.assertEqual(out["action"], "delist")
        self.assertFalse(out["preds_stale"])

    def test_staleness_threshold_boundary(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        state = str(Path(d) / "state.json")
        feed = self._mkfeed(d, rd.STALENESS_S + 60)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = rd.main(["--state", state, "--preds", str(feed),
                          "--dry-run"])
        self.assertEqual(rc, 1)
        self.assertTrue(json.loads(buf.getvalue())["preds_stale"])

    def test_stale_feed_exit_zero_when_override_fires(self):
        """Stale feed is an error but never blocks the manual override."""
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        state = str(Path(d) / "state.json")
        feed = self._mkfeed(d, 6 * 3600)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = rd.main(["--state", state, "--preds", str(feed),
                          "--manual", "--dry-run"])
        out = json.loads(buf.getvalue())
        self.assertEqual(rc, 0)
        self.assertEqual(out["action"], "delist")
        self.assertIn("manual override", out["reasons"])

    def test_stale_feed_baseline_not_consumed(self):
        """A stale feed must not update the acceleration baseline either."""
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        state = str(Path(d) / "state.json")
        rd.save_state(state, {"snapshot": {f"zai{rd._SNAP_SEP}1h": 10.0}})
        feed = self._mkfeed(d, 6 * 3600, rows=[pred(hours=1.0)])
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rd.main(["--state", state, "--preds", str(feed), "--dry-run"])
        st = rd.load_state(state)
        self.assertEqual(st["snapshot"], {f"zai{rd._SNAP_SEP}1h": 10.0})


# ── Idempotence: double delist / pulled_models preservation (finding 4) ────
class TestIdempotence(unittest.TestCase):
    def _delist(self, state, fb):
        with mock.patch.object(rd, "_SshBackend", lambda t, c: fb):
            with contextlib.redirect_stdout(io.StringIO()) as buf:
                rc = rd.main(["--state", state, "--manual"])
        return rc, json.loads(buf.getvalue())

    def test_double_delist_merges_pulled_models(self):
        """Re-delist while delisted: the empty second capture must NOT
        clobber the stored names (they feed the scoped relist)."""
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        state = str(Path(d) / "state.json")
        fb = FakeBackend(pull_res={"ok": True, "pulled": ["gpt-4o", "llama-3"]})
        self._delist(state, fb)
        # second delist: remote SELECT now returns nothing (all disabled)
        fb2 = FakeBackend(pull_res={"ok": True, "pulled": []})
        rc, out = self._delist(state, fb2)
        self.assertEqual(rc, 0)
        st = rd.load_state(state)
        self.assertEqual(st["pulled_models"], ["gpt-4o", "llama-3"])
        # and the relist is still scoped to the merged names
        fb3 = FakeBackend(relist_res={"ok": True})
        with mock.patch.object(rd, "_SshBackend", lambda t, c: fb3):
            with contextlib.redirect_stdout(io.StringIO()):
                rd.main(["--state", state, "--relist"])
        self.assertEqual(fb3.calls,
                         [("relist", ["gpt-4o", "llama-3"], False)])

    def test_relist_refuses_blanket_without_opt_in(self):
        """No captured names (legacy/no-pulled_models state) -> relist must
        REFUSE the blanket enable (would enable operator-disabled rows)."""
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        state = str(Path(d) / "state.json")
        rd.save_state(state, {"delisted": True, "ts": 1.0})  # live shape
        fb = FakeBackend(relist_res={"ok": True})
        with mock.patch.object(rd, "_SshBackend", lambda t, c: fb):
            with contextlib.redirect_stdout(io.StringIO()) as buf:
                rc = rd.main(["--state", state, "--relist"])
        out = json.loads(buf.getvalue())
        self.assertEqual(rc, 1)
        self.assertEqual(out["action"], "relist_refused")
        self.assertEqual(fb.calls, [])          # nothing executed remotely
        self.assertTrue(rd.load_state(state)["delisted"])  # state untouched

    def test_relist_any_executes_blanket(self):
        """--relist-any is the explicit operator opt-in to the blanket path."""
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        state = str(Path(d) / "state.json")
        rd.save_state(state, {"delisted": True, "ts": 1.0})
        fb = FakeBackend(relist_res={"ok": True})
        with mock.patch.object(rd, "_SshBackend", lambda t, c: fb):
            with contextlib.redirect_stdout(io.StringIO()) as buf:
                rc = rd.main(["--state", state, "--relist", "--relist-any"])
        self.assertEqual(rc, 0)
        self.assertEqual(fb.calls, [("relist", [], False)])
        self.assertFalse(rd.load_state(state)["delisted"])


# ── Dry-run purity (verification-pass finding 7c, MEDIUM) ──────────────────
class TestDryRunPurity(unittest.TestCase):
    def test_dry_run_delist_publishes_no_event(self):
        """--dry-run --nsec must not fire the real nak publish."""
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        state = str(Path(d) / "state.json")
        with mock.patch.object(rd, "_SshBackend",
                               lambda t, c: FakeBackend()), \
                mock.patch.object(rd, "publish_delist_event") as pub, \
                contextlib.redirect_stdout(io.StringIO()):
            rd.main(["--state", state, "--manual", "--nsec", "/tmp/nsec",
                     "--dry-run"])
        pub.assert_not_called()

    def test_dry_run_relist_publishes_no_event(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        state = str(Path(d) / "state.json")
        rd.save_state(state, {"delisted": True, "pulled_models": ["x"]})
        with mock.patch.object(rd, "_SshBackend",
                               lambda t, c: FakeBackend()), \
                mock.patch.object(rd, "publish_delist_event") as pub, \
                contextlib.redirect_stdout(io.StringIO()):
            rd.main(["--state", state, "--relist", "--nsec", "/tmp/nsec",
                     "--dry-run"])
        pub.assert_not_called()


# ── Real _SshBackend._run parsing (review finding 8 mock-only gap) ─────────
class TestRealBackendRun(unittest.TestCase):
    """Hermetic: patches subprocess.run; never touches the network."""

    def _backend(self):
        return rd._SshBackend("debian@host", "routstr-public")

    def test_pull_parses_last_line_json_and_gates_on_ok(self):
        out = '{"ok": true, "pulled": ["gpt-4o"]}\n'
        proc = subprocess.CompletedProcess([], 0, stdout=out, stderr="")
        with mock.patch.object(rd.subprocess, "run", return_value=proc) as sr:
            res = self._backend().pull()
        sr.assert_called_once()
        self.assertTrue(res["ok"])
        self.assertEqual(res["pulled"], ["gpt-4o"])

    def test_pull_garbage_stdout_is_failure(self):
        proc = subprocess.CompletedProcess([], 0, stdout="bash: warning\n",
                                           stderr="")
        with mock.patch.object(rd.subprocess, "run", return_value=proc):
            res = self._backend().pull()
        self.assertFalse(res["ok"])

    def test_pull_nonzero_rc_is_failure_even_with_ok_payload(self):
        out = '{"ok": true, "pulled": []}\n'
        proc = subprocess.CompletedProcess([], 255, stdout=out, stderr="x")
        with mock.patch.object(rd.subprocess, "run", return_value=proc):
            res = self._backend().pull()
        self.assertFalse(res["ok"])

    def test_payload_dies_after_commit_is_failure(self):
        """Remote python dies between commit and print -> no ok in stdout ->
        attempt failure (delisted remotely, but state stays honest)."""
        proc = subprocess.CompletedProcess([], 1, stdout="", stderr="boom")
        with mock.patch.object(rd.subprocess, "run", return_value=proc):
            res = self._backend().pull()
        self.assertFalse(res["ok"])

    def test_verify_parses_count(self):
        out = '{"ok": true, "count": 0}\n'
        proc = subprocess.CompletedProcess([], 0, stdout=out, stderr="")
        with mock.patch.object(rd.subprocess, "run", return_value=proc):
            res = self._backend().verify()
        self.assertTrue(res["ok"])
        self.assertEqual(res["count"], 0)

    def test_exception_is_failure_not_crash(self):
        def boom(*a, **kw):
            raise subprocess.TimeoutExpired(cmd="ssh", timeout=60)
        with mock.patch.object(rd.subprocess, "run", side_effect=boom):
            res = self._backend().pull()
        self.assertFalse(res["ok"])
        self.assertIn("error", res)

    def test_dry_run_returns_without_subprocess(self):
        with mock.patch.object(rd.subprocess, "run") as sr:
            res = self._backend().pull(dry_run=True)
        sr.assert_not_called()
        self.assertTrue(res["dry_run"])

    def test_relist_passes_names_payload(self):
        out = '{"ok": true, "restored": 2}\n'
        proc = subprocess.CompletedProcess([], 0, stdout=out, stderr="")
        with mock.patch.object(rd.subprocess, "run", return_value=proc) as sr:
            res = self._backend().relist(names=["a", "b"])
        remote = sr.call_args[0][0][2]
        self.assertIn("name IN (?,?)", remote)
        self.assertTrue(res["ok"])
        self.assertEqual(res["restored"], 2)


if __name__ == "__main__":
    unittest.main()
