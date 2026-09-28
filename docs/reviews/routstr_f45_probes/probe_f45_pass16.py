#!/usr/bin/env python3
"""Hermetic re-derivation probes for routstr-delist findings 4 (atomicity /
idempotence) and 5 (5-minute SLA), offload pass 16.

Drives the DEPLOYED script (~/.hermes/bot/scripts/routstr_delist.py) in-process
via rd.main() plus the real rd._SshBackend._run. No network, no real ssh, no
test-file execution, tempdir state only. Read-only w.r.t. every artifact.

Prints one line per probe: "<name> <observations>  PASS|FAIL" then a summary.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

DEPLOYED = Path(os.path.expanduser("~/.hermes/bot/scripts"))
sys.path.insert(0, str(DEPLOYED))
import routstr_delist as rd  # noqa: E402

RESULTS = []


def check(name, ok, detail):
    RESULTS.append((name, ok))
    print(f"{name} {detail}  {'PASS' if ok else 'FAIL'}")


class Clock:
    """Synthetic monotonic clock; wall time stays real."""

    def __init__(self):
        self._mono = 0.0

    def monotonic(self):
        return self._mono

    @staticmethod
    def time():
        return time.time()

    def advance(self, s):
        self._mono += s

    @property
    def now(self):
        return self._mono


class FakeNode:
    """In-memory sell node: pull/verify/relist results are canned."""

    def __init__(self, clock=None, round_trip_s=0.0):
        self.clock = clock
        self.round_trip_s = round_trip_s
        self.calls = []
        self.deadlines = []
        self.pull_ok = True
        self.pull_lands = True          # LYING pull: ok-printed, verify refutes
        self.verify_ok = True
        self.verify_count = 0
        self.relist_ok = True
        self.pulled = ["m1"]

    def _tick(self):
        if self.clock is not None:
            self.clock.advance(self.round_trip_s)

    def pull(self, dry_run=False, deadline=None):
        self.calls.append("pull")
        self.deadlines.append(("pull", deadline))
        self._tick()
        if not self.pull_ok:
            return {"ok": False, "action": "pull", "rc": 255,
                    "error": "ssh: connect refused (simulated)"}
        return {"ok": True, "action": "pull", "rc": 0,
                "pulled": list(self.pulled) if self.pull_lands else []}

    def verify(self, dry_run=False, deadline=None):
        self.calls.append("verify")
        self.deadlines.append(("verify", deadline))
        self._tick()
        if not self.verify_ok:
            return {"ok": False, "action": "verify", "rc": 255}
        return {"ok": True, "action": "verify", "rc": 0,
                "count": self.verify_count}

    def relist(self, names=None, dry_run=False, deadline=None):
        self.calls.append("relist")
        self.deadlines.append(("relist", deadline))
        self._tick()
        if not self.relist_ok:
            return {"ok": False, "action": "relist", "rc": 255,
                    "error": "ssh: connect refused (simulated)"}
        return {"ok": True, "action": "relist", "rc": 0,
                "restored": len(names or [])}


class Harness:
    def __init__(self, clock=None, node_kw=None, real_fsync=False,
                 fail_replace=False):
        self.tmp = Path(tempfile.mkdtemp(prefix="f45p16-"))
        self.state = self.tmp / "state.json"
        self.override = self.tmp / "absent.override"
        self.clock = clock
        self.node = FakeNode(clock, **(node_kw or {}))
        self._saved = {}
        self.real_fsync = real_fsync
        self.fsync_calls = 0
        self.opened_flags = []
        self.fail_replace = fail_replace
        self._patch()

    def _patch(self):
        self._saved["_SshBackend"] = rd._SshBackend
        rd._SshBackend = lambda t, c: self.node
        if self.clock is not None:
            self._saved["time"] = rd.time
            rd.time = self.clock
        real_fsync = os.fsync
        real_open = os.open
        real_replace = os.replace
        self._saved["os.fsync"] = real_fsync
        self._saved["os.open"] = real_open
        self._saved["os.replace"] = real_replace
        h = self

        def counting_fsync(fd):
            h.fsync_calls += 1
            if h.real_fsync:
                return real_fsync(fd)
            return None

        def counting_open(path, flags, *a, **kw):
            h.opened_flags.append(flags)
            return real_open(path, flags, *a, **kw)

        def maybe_failing_replace(src, dst):
            if h.fail_replace and Path(dst) == h.state:
                raise OSError("simulated persist failure (ENOSPC)")
            return real_replace(src, dst)

        os.fsync = counting_fsync
        os.open = counting_open
        os.replace = maybe_failing_replace

    def restore(self):
        rd._SshBackend = self._saved["_SshBackend"]
        if "time" in self._saved:
            rd.time = self._saved["time"]
        os.fsync = self._saved["os.fsync"]
        os.open = self._saved["os.open"]
        os.replace = self._saved["os.replace"]

    def seed(self, obj):
        rd.save_state(str(self.state), obj)

    def run(self, *argv):
        argv = ["--state", str(self.state), "--override",
                str(self.override)] + list(argv)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = rd.main(argv)
        raw = out.getvalue()
        return rc, (json.loads(raw) if raw.strip() else {}), raw

    def disk(self):
        return rd.load_state(str(self.state))


def probe_4a_atomic():
    h = Harness()
    try:
        ok = rd.save_state(str(h.state), {"ts": 1, "delisted": True})
        litter = [p.name for p in h.tmp.glob(".*.tmp")]
        check("4a_save_state_ok", ok is True and litter == [],
              f"ret={ok} litter={litter} fsync_calls={h.fsync_calls}")
        h.fail_replace = True
        ok2 = rd.save_state(str(h.state), {"ts": 2})
        litter2 = [p.name for p in h.tmp.glob(".*.tmp")]
        check("4a2_save_state_false_on_error", ok2 is False and litter2 == [],
              f"ret={ok2} litter={litter2}")
    finally:
        h.restore()


def probe_4b_silent_persist():
    h = Harness()
    try:
        h.seed({"ts": 1, "delisted": False, "snapshot": {"zai": 10.0},
                "consecutive_failures": 2})
        before = h.state.read_bytes()
        h.fail_replace = True
        rc, out, _ = h.run("--delist")
        after = h.state.read_bytes()
        check("4b_silent_persist_failure",
              rc == 0 and out.get("action") == "delist"
              and out.get("confirmed") is True and after == before,
              f"rc={rc} action={out.get('action')} "
              f"confirmed={out.get('confirmed')} state_on_disk={h.disk()}")
        h.fail_replace = False
        rc2, out2, _ = h.run("--status")
        check("4b2_status_reads_stale", out2.get("delisted") is False,
              f"rc={rc2} delisted={out2.get('delisted')}")
    finally:
        h.restore()


def probe_4b3_breaker_freeze():
    h = Harness()
    try:
        h.seed({"ts": 1, "delisted": False, "consecutive_failures": 2,
                "blocked": False})
        h.fail_replace = True
        h.node.pull_ok = False
        rcs = []
        for _ in range(4):
            rc, out, _ = h.run("--manual")
            rcs.append(rc)
        disk = h.disk()
        check("4b3_persist_failure_freezes_breaker",
              rcs == [3, 3, 3, 3] and disk.get("consecutive_failures") == 2
              and disk.get("blocked") is False,
              f"rcs={rcs} disk_consecutive_failures="
              f"{disk.get('consecutive_failures')} "
              f"disk_blocked={disk.get('blocked')}")
        h.fail_replace = False
        rc_s, out_s, _ = h.run("--status")
        check("4b3b_status_says_closed",
              out_s.get("blocked") is False
              and out_s.get("consecutive_failures") == 2,
              f"status_blocked={out_s.get('blocked')} "
              f"status_fails={out_s.get('consecutive_failures')}")
    finally:
        h.restore()


def probe_4c_redelist_merge():
    h = Harness()
    try:
        h.seed({"ts": 1, "delisted": True, "pulled_models": ["m1", "m2"]})
        h.node.pulled = []          # nothing advertised any more
        rc, out, _ = h.run("--delist")
        disk = h.disk()
        check("4c_redelist_merge",
              rc == 0 and disk.get("pulled_models") == ["m1", "m2"],
              f"rc={rc} pulled={out.get('pulled')} "
              f"pulled_models={disk.get('pulled_models')}")
    finally:
        h.restore()


def probe_4d_relist_refused():
    h = Harness()
    try:
        h.seed({"ts": 1, "delisted": True})      # no pulled_models captured
        rc, out, _ = h.run("--relist")
        check("4d_relist_refused",
              rc == 1 and out.get("action") == "relist_refused"
              and h.node.calls == [],
              f"rc={rc} action={out.get('action')} calls={h.node.calls}")
    finally:
        h.restore()


def probe_4e_failed_relist_no_breaker_tick():
    h = Harness()
    try:
        h.seed({"ts": 1, "delisted": True, "pulled_models": ["m1"],
                "consecutive_failures": 2})
        h.node.relist_ok = False
        rc, out, _ = h.run("--relist")
        disk = h.disk()
        check("4e_failed_relist_no_breaker_tick",
              rc == 1 and disk.get("consecutive_failures") == 2
              and disk.get("blocked") is None,
              f"rc={rc} action={out.get('action')} "
              f"consecutive_failures={disk.get('consecutive_failures')} "
              f"blocked={disk.get('blocked')}")
    finally:
        h.restore()


def probe_4f_bool_counter_hole():
    h = Harness()
    try:
        h.state.write_text(json.dumps({"ts": 1, "delisted": False,
                                       "consecutive_failures": True}))
        h.node.pull_ok = False
        rc, out, _ = h.run("--manual")
        disk = h.disk()
        check("4f_bool_counter_hole",
              disk.get("consecutive_failures") == 2,
              f"rc={rc} consecutive_failures={disk.get('consecutive_failures')}")
    finally:
        h.restore()


def probe_4g_lost_update():
    h = Harness()
    try:
        rd.save_state(str(h.state), {"ts": 1, "delisted": False})
        a = rd.load_state(str(h.state))       # run A reads
        b = rd.load_state(str(h.state))       # run B reads concurrently
        a.update({"delisted": True, "pulled_models": ["m1"], "ts": 2})
        rd.save_state(str(h.state), a)        # A writes (delist)
        b.update({"delisted": False, "ts": 2})
        rd.save_state(str(h.state), b)        # B writes (relist) -> A lost
        final = h.disk()
        check("4g_interleaved_lost_update",
              "pulled_models" not in final and final.get("delisted") is False,
              f"final={final} (run A's delist+pulled_models clobbered)")
    finally:
        h.restore()


def probe_4h_no_directory_fsync():
    h = Harness()
    try:
        rd.save_state(str(h.state), {"ts": 1})
        dir_flags = [f for f in h.opened_flags
                     if hasattr(os, "O_DIRECTORY") and f & os.O_DIRECTORY]
        check("4h_no_directory_fsync",
              h.fsync_calls == 1 and dir_flags == [],
              f"fsync_calls={h.fsync_calls} dir_opens={len(dir_flags)} "
              f"os_open_flags={h.opened_flags}")
    finally:
        h.restore()


def probe_4i_blocked_refuses_publish():
    h = Harness()
    try:
        h.seed({"ts": 1, "delisted": True, "blocked": True,
                "consecutive_failures": 3})
        nsec = h.tmp / "nsec"
        nsec.write_text("nsec1TEST\n")
        spawned = []
        real_run = rd.subprocess.run
        rd.subprocess.run = lambda argv, **kw: (
            spawned.append(list(argv)),
            real_run(["true"], **kw))[1]
        try:
            rc, out, _ = h.run("--manual", "--nsec", str(nsec))
        finally:
            rd.subprocess.run = real_run
        nak = [a for a in spawned if a and "nak" in str(a[0])]
        check("4i_blocked_refuses_publish_too",
              rc == 3 and h.node.calls == [] and nak == [],
              f"rc={rc} action={out.get('action')} api_calls={h.node.calls} "
              f"nak_publishes={len(nak)}")
    finally:
        h.restore()


def probe_4i2_blocked_test_blind_to_publish():
    body = (DEPLOYED.parent / "tests" / "test_routstr_delist.py")
    txt = body.read_text()
    start = txt.find("def test_blocked_run_refuses_all_remote_action")
    seg = txt[start:start + 900]
    check("4i2_blocked_test_blind_to_publish",
          "nsec" not in seg and "subprocess" not in seg,
          f"mentions_nsec={'nsec' in seg} "
          f"mentions_subprocess={'subprocess' in seg} "
          f"(asserts only FakeSellNode.calls)")
    return seg


def probe_5a_constants():
    ok = (rd.TRIGGER_ACTION_WINDOW_S == 300 and rd.POLL_CADENCE_S == 240
          and rd.ACTION_BUDGET_S == 60 and rd.SSH_TIMEOUT_S == 30
          and rd.MAX_PULL_ATTEMPTS == 2
          and rd.POLL_CADENCE_S + rd.ACTION_BUDGET_S
          == rd.TRIGGER_ACTION_WINDOW_S
          and 2 * rd.SSH_TIMEOUT_S <= rd.ACTION_BUDGET_S)
    check("5a_constants_arithmetic", ok,
          f"window={rd.TRIGGER_ACTION_WINDOW_S} cadence={rd.POLL_CADENCE_S} "
          f"budget={rd.ACTION_BUDGET_S} ssh={rd.SSH_TIMEOUT_S} "
          f"max_attempts={rd.MAX_PULL_ATTEMPTS}")


def probe_5b_budget_exhausted_no_spawn():
    spawned = []
    real_run = rd.subprocess.run
    rd.subprocess.run = lambda argv, **kw: (
        spawned.append((list(argv), kw.get("timeout"))), None)[1]
    try:
        be = rd._SshBackend("host", "cont")
        expired = be._run("payload", dry_run=False, action="pull",
                          deadline=time.monotonic() - 1)
        spawns_after_expired = len(spawned)
        live = be._run("payload", dry_run=False, action="pull",
                       deadline=time.monotonic() + 0.999)
    finally:
        rd.subprocess.run = real_run
    timeouts = [t for _, t in spawned]
    check("5b_budget_exhausted_no_spawn",
          expired.get("error") == "action budget exhausted"
          and spawns_after_expired == 0 and timeouts
          and all(t <= 1.0 for t in timeouts),
          f"res={expired} spawns_after_expired={spawns_after_expired} "
          f"live_budget_timeout={timeouts}")


def probe_5b2_no_deadline():
    seen = []
    real_run = rd.subprocess.run
    rd.subprocess.run = lambda argv, **kw: (
        seen.append(kw.get("timeout")), None)[1]
    try:
        be = rd._SshBackend("host", "cont")
        be._run("payload", dry_run=False, action="pull", deadline=None)
    finally:
        rd.subprocess.run = real_run
    check("5b2_no_deadline_timeout", seen == [rd.SSH_TIMEOUT_S],
          f"timeouts={seen}")


def probe_5c_cadence_arithmetic():
    obs = {}
    for tick, secs in (("*/4", 240), ("*/5", 300), ("*/2", 120)):
        worst = secs + rd.ACTION_BUDGET_S
        obs[tick] = rd.TRIGGER_ACTION_WINDOW_S - worst
    check("5c_cadence_arithmetic",
          obs["*/4"] == 0 and obs["*/5"] < 0 and obs["*/2"] > 0,
          f"slack */4={obs['*/4']}s */5={obs['*/5']}s */2={obs['*/2']}s "
          f"(worst=240+60=300 == window exactly)")


def probe_5d_publish_unclamped():
    h = Harness()
    try:
        nsec = h.tmp / "nsec"
        nsec.write_text("nsec1TEST\n")
        seen = []
        real_run = rd.subprocess.run
        rd.subprocess.run = lambda argv, **kw: (
            seen.append(kw.get("timeout")), None)[1]
        try:
            rc, out, _ = h.run("--delist", "--nsec", str(nsec))
        finally:
            rd.subprocess.run = real_run
        check("5d_publish_timeout_unclamped",
              out.get("confirmed") is True and seen == [30],
              f"rc={rc} confirmed={out.get('confirmed')} "
              f"publish_timeouts={seen} budget={rd.ACTION_BUDGET_S}")
    finally:
        h.restore()


def probe_5e_retry_one_deadline():
    clk = Clock()
    h = Harness(clock=clk, node_kw={"round_trip_s": 0.0})
    try:
        h.node.pull_ok = False
        before = clk.now
        rc, out, _ = h.run("--manual")
        deadlines = {d for _, d in h.node.deadlines}
        check("5e_inrun_retry_bounded",
              h.node.calls == ["pull", "pull"] and len(deadlines) == 1
              and rc == 1,
              f"calls={h.node.calls} one_deadline_for_all_attempts="
              f"{len(deadlines) == 1} attempts={len(h.node.calls)} "
              f"deadline_offset_from_start="
              f"{round(out.get('consecutive_failures', 0) and 0 or 0, 2)}"
              f"mono={round(clk.now - before, 2)}")
    finally:
        h.restore()


def probe_5f_local_fsync_unclamped():
    h = Harness(real_fsync=False)
    try:
        rc, out, _ = h.run("--delist")
        check("5f_local_fsync_unclamped",
              rc == 0 and h.fsync_calls >= 1,
              f"rc={rc} action={out.get('action')} "
              f"local_fsync_calls={h.fsync_calls} "
              f"(deadline at :667 gates only _SshBackend._run :800-806)")
    finally:
        h.restore()


def probe_5g_worst_case_eats_retry():
    clk = Clock()
    h = Harness(clock=clk, node_kw={"round_trip_s": 30.0})
    try:
        h.node.verify_count = 3          # pull self-reports ok, verify refutes
        rc, out, _ = h.run("--manual")
        check("5g_worst_case_eats_retry",
              h.node.calls == ["pull", "verify"] and rc == 1
              and abs(clk.now - 60.0) < 1e-6,
              f"rc={rc} calls={h.node.calls} elapsed={clk.now}s "
              f"budget={rd.ACTION_BUDGET_S}s -> retry refused")
    finally:
        h.restore()


def probe_5g2_half_budget_retries():
    clk = Clock()
    h = Harness(clock=clk, node_kw={"round_trip_s": 30.0})
    try:
        h.node.pull_ok = False
        rc, out, _ = h.run("--manual")
        check("5g2_half_budget_attempt_retries",
              h.node.calls == ["pull", "pull"] and rc == 1,
              f"rc={rc} calls={h.node.calls} elapsed={clk.now}s")
    finally:
        h.restore()


def main():
    for fn in (probe_4a_atomic, probe_4b_silent_persist,
               probe_4b3_breaker_freeze, probe_4c_redelist_merge,
               probe_4d_relist_refused, probe_4e_failed_relist_no_breaker_tick,
               probe_4f_bool_counter_hole, probe_4g_lost_update,
               probe_4h_no_directory_fsync, probe_4i_blocked_refuses_publish,
               probe_4i2_blocked_test_blind_to_publish, probe_5a_constants,
               probe_5b_budget_exhausted_no_spawn, probe_5b2_no_deadline,
               probe_5c_cadence_arithmetic, probe_5d_publish_unclamped,
               probe_5e_retry_one_deadline, probe_5f_local_fsync_unclamped,
               probe_5g_worst_case_eats_retry, probe_5g2_half_budget_retries):
        fn()
    passed = sum(1 for _, ok in RESULTS if ok)
    print(f"\nSUMMARY {passed}/{len(RESULTS)} probes PASS")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
