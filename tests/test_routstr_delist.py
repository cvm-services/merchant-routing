"""Gate 1/2 tests for routstr_delist (T-D, ADR-007 Gate 4).

Spec-derived (task body + ADR-007 + Gate 2.5 cold review), stdlib unittest so
the suite runs under both `python3 -m unittest discover -s tests` and
`python3 -m pytest tests/ -v`. All tests are hermetic: the SSH backend is
faked or monkeypatched, all state lives in tmpdirs, no network is touched.
"""
import contextlib
import io
import json
import shlex
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import routstr_delist as rd  # noqa: E402


def pred(key="zai", window="1h", hours: float | str | None = 10.0, unc=0.05):
    """burn_predictor.predict_exhaustion-shaped prediction dict (tolerates
    deliberately-corrupt values for negative tests)."""
    return {"key": key, "window": window,
            "exhausts_in_hours": hours, "uncertainty": unc}


class FakeBackend:
    """Scriptable stand-in for _SshBackend (never touches the network)."""

    def __init__(self, pull_res=None, relist_res=None):
        self.calls = []
        self.pull_res = pull_res or {"ok": True, "pulled": ["gpt-4o", "claude-3"]}
        self.relist_res = relist_res or {"ok": True}

    def pull(self, dry_run=False):
        self.calls.append(("pull", dry_run))
        return dict(self.pull_res)

    def relist(self, names=None, dry_run=False):
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
        argv = rd.build_delist_event("/nonexistent", delisted=False)
        self.assertIsNone(argv)  # still None without a sec file


# ── 5-minute action window ─────────────────────────────────────────────────
class TestFiveMinuteWindow(unittest.TestCase):
    def test_window_constant_is_300s(self):
        self.assertEqual(rd.TRIGGER_ACTION_WINDOW_S, 300)

    def test_triggered_run_pulls_within_window(self):
        """A fired trigger must pull the listing IN-RUN (well under 5 min)."""
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
        self.assertTrue(st["delisted"])


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
                rd.main(["--state", state, "--preds", str(preds_a), "--dry-run"])
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = rd.main(["--state", state, "--preds", str(preds_b),
                              "--dry-run"])
        out = json.loads(buf.getvalue())
        self.assertEqual(rc, 1)                       # cron must see failure
        self.assertEqual(out["action"], "delist_failed")
        st = rd.load_state(state)
        self.assertFalse(st["delisted"])              # flag not set on failure
        self.assertIn("last_pull_error", st)
        # baseline NOT consumed: same acceleration still fires on retry
        dec = rd.evaluate_triggers(json.loads(preds_b.read_text()), st)
        self.assertTrue(dec["fire"])

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
            rc = rd.main(["--state", state, "--relist", "--dry-run"])
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
        self.assertTrue(rd.load_state(state)["delisted"])

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
        rc, out, state = self.run_main(["--relist", "--dry-run"])
        self.assertEqual(rc, 0)
        self.assertEqual(out["action"], "relist")
        self.assertFalse(rd.load_state(state)["delisted"])

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


if __name__ == "__main__":
    unittest.main()
