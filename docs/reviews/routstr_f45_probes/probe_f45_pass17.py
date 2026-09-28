#!/usr/bin/env python3
"""Hermetic re-derivation probes for routstr-delist findings 4 (atomicity /
idempotence) and 5 (5-minute SLA), offload pass 17.

Drives the DEPLOYED script (~/.hermes/bot/scripts/routstr_delist.py) in-process
via rd.main() and the real rd._SshBackend._run. No network, no real ssh, no
test-file execution, tempdir state only. Read-only w.r.t. every artifact.

Prints one line per probe: "<name> <observations>  PASS|FAIL" then a summary.
"""
from __future__ import annotations

import ast
import contextlib
import io
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path

DEPLOYED = Path(os.path.expanduser("~/.hermes/bot/scripts"))
DEPLOYED_FILE = DEPLOYED / "routstr_delist.py"
sys.path.insert(0, str(DEPLOYED))
import routstr_delist as rd  # noqa: E402

RESULTS = []


def check(name, ok, detail):
    RESULTS.append((name, ok))
    print(f"{name} {detail}  {'PASS' if ok else 'FAIL'}")


class Clock:
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
    """Canned sell-node backend; records calls and the deadline view."""

    def __init__(self, clock=None, round_trip_s=0.0):
        self.clock = clock
        self.round_trip_s = round_trip_s
        self.calls = []
        self.deadlines = []
        self.pull_ok = True
        self.verify_ok = True
        self.verify_count = 0
        self.pulled = ["m1"]
        self.relist_ok = True

    def _tick(self):
        if self.clock is not None:
            self.clock.advance(self.round_trip_s)

    def pull(self, dry_run=False, deadline=None):
        self.calls.append("pull")
        self.deadlines.append(("pull", deadline))
        self._tick()
        if not self.pull_ok:
            return {"ok": False, "action": "pull", "rc": 255, "error": "ssh down"}
        return {"ok": True, "action": "pull", "pulled": list(self.pulled)}

    def verify(self, dry_run=False, deadline=None):
        self.calls.append("verify")
        self.deadlines.append(("verify", deadline))
        self._tick()
        if not self.verify_ok:
            return {"ok": False, "action": "verify", "rc": 255, "error": "ssh down"}
        return {"ok": True, "action": "verify", "count": self.verify_count}

    def relist(self, names=None, dry_run=False, deadline=None):
        self.calls.append("relist")
        self.deadlines.append(("relist", deadline))
        self._tick()
        if not self.relist_ok:
            return {"ok": False, "action": "relist", "rc": 1, "error": "boom"}
        return {"ok": True, "action": "relist", "restored": len(names or [])}


def run_main(argv, node, state_path, override_path):
    """Drive rd.main() with the backend swapped for `node`."""
    real = rd._SshBackend
    rd._SshBackend = lambda t, c: node
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out):
            rc = rd.main(["--state", str(state_path),
                          "--override", str(override_path)] + list(argv))
    finally:
        rd._SshBackend = real
    raw = out.getvalue()
    payload = json.loads(raw) if raw.strip() else {}
    return rc, payload, raw


def read_json(path):
    try:
        data = json.loads(Path(path).read_text())
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


TMP = Path(tempfile.mkdtemp(prefix="f45p17-"))


# ═══ Finding 4 ═══════════════════════════════════════════════════════════════

# 4a — atomic write protocol: tmp + fsync + replace, returns True, no litter
def p_4a():
    p = TMP / "s4a.json"
    calls = {"fsync": 0, "replace": 0}
    real_fs, real_rp = os.fsync, os.replace

    def fs(fd):
        calls["fsync"] += 1
        return real_fs(fd) if False else None   # host: fsync can stall

    def rp(src, dst):
        calls["replace"] += 1
        return real_rp(src, dst)

    os.fsync, os.replace = fs, rp
    try:
        ok = rd.save_state(str(p), {"ts": 1, "delisted": True})
    finally:
        os.fsync, os.replace = real_fs, real_rp
    litter = [x.name for x in TMP.glob(".*.tmp")]
    check("4a_save_state_ok", ok is True and calls["fsync"] == 1
          and calls["replace"] == 1 and litter == [],
          f"ret={ok} fsync_calls={calls['fsync']} replace={calls['replace']} "
          f"litter={litter}")


# 4a2 — os.replace raising: returns False, previous state intact, no litter
def p_4a2():
    p = TMP / "s4a2.json"
    rd.save_state(str(p), {"ts": 1, "delisted": False})
    before = p.read_bytes()
    real_rp = os.replace

    def boom(src, dst):
        if Path(dst) == p:
            raise OSError("simulated crash")
        return real_rp(src, dst)

    os.replace = boom
    try:
        ok = rd.save_state(str(p), {"ts": 2, "delisted": True})
    finally:
        os.replace = real_rp
    after = p.read_bytes()
    litter = [x.name for x in TMP.glob(".*.tmp")]
    check("4a2_save_state_false_on_error",
          ok is False and after == before and litter == [],
          f"ret={ok} state_unchanged={after == before} litter={litter}")


# 4b — silent persist failure: reported as a confirmed success anyway
def p_4b():
    sp, ov = TMP / "s4b.json", TMP / "s4b.override"
    sp.write_text(json.dumps({"ts": 1, "delisted": False,
                              "snapshot": {"zai\x1f1h": 10.0},
                              "consecutive_failures": 2}))
    pre = sp.read_bytes()
    node = FakeNode()
    real_rp = os.replace

    def boom(src, dst):
        if Path(dst) == sp:
            raise OSError("ENOSPC simulated")
        return real_rp(src, dst)

    os.replace = boom
    try:
        rc, out, _ = run_main(["--delist"], node, sp, ov)
    finally:
        os.replace = real_rp
    disk = read_json(sp)
    check("4b_silent_persist_failure",
          rc == 0 and out.get("action") == "delist"
          and out.get("confirmed") is True and disk.get("delisted") is False
          and disk.get("consecutive_failures") == 2
          and sp.read_bytes() == pre,
          f"rc={rc} action={out.get('action')} confirmed={out.get('confirmed')} "
          f"state_on_disk={disk}")


# 4b3 — persist failure freezes the breaker while exit 3 still fires
def p_4b3():
    sp, ov = TMP / "s4b3.json", TMP / "s4b3.override"
    sp.write_text(json.dumps({"ts": 1, "delisted": False,
                              "consecutive_failures": 2, "blocked": False}))
    node = FakeNode()
    node.pull_ok = False                       # every run fails
    real_rp = os.replace

    def boom(src, dst):
        if Path(dst) == sp:
            raise OSError("ENOSPC simulated")
        return real_rp(src, dst)

    os.replace = boom
    rcs = []
    try:
        for _ in range(4):
            rc, _, _ = run_main(["--manual"], node, sp, ov)
            rcs.append(rc)
    finally:
        os.replace = real_rp
    disk = read_json(sp)
    check("4b3_persist_failure_freezes_breaker",
          rcs == [3, 3, 3, 3] and disk.get("consecutive_failures") == 2
          and disk.get("blocked") is False,
          f"rcs={rcs} disk_consecutive_failures={disk.get('consecutive_failures')} "
          f"disk_blocked={disk.get('blocked')}")


# 4c — re-delist MERGES pulled_models (never clobbers)
def p_4c():
    sp, ov = TMP / "s4c.json", TMP / "s4c.override"
    sp.write_text(json.dumps({"ts": 1, "delisted": True,
                              "pulled_models": ["m1", "m2"]}))
    node = FakeNode()
    node.pulled = []                           # nothing advertised now
    node.verify_count = 0
    rc, out, _ = run_main(["--delist"], node, sp, ov)
    disk = read_json(sp)
    check("4c_redelist_merge",
          rc == 0 and out.get("pulled") == []
          and disk.get("pulled_models") == ["m1", "m2"],
          f"rc={rc} pulled={out.get('pulled')} "
          f"pulled_models={disk.get('pulled_models')}")


# 4d — no-names relist REFUSES the blanket enable, zero round-trips
def p_4d():
    sp, ov = TMP / "s4d.json", TMP / "s4d.override"
    sp.write_text(json.dumps({"ts": 1, "delisted": True}))
    node = FakeNode()
    rc, out, _ = run_main(["--relist"], node, sp, ov)
    check("4d_relist_refused",
          rc == 1 and out.get("action") == "relist_refused" and node.calls == [],
          f"rc={rc} action={out.get('action')} calls={node.calls}")


# 4e — a FAILED relist does not tick the breaker
def p_4e():
    sp, ov = TMP / "s4e.json", TMP / "s4e.override"
    sp.write_text(json.dumps({"ts": 1, "delisted": True,
                              "pulled_models": ["m1"], "consecutive_failures": 2}))
    node = FakeNode()
    node.relist_ok = False
    rc, out, _ = run_main(["--relist"], node, sp, ov)
    disk = read_json(sp)
    check("4e_failed_relist_no_breaker_tick",
          rc == 1 and out.get("action") == "relist_failed"
          and disk.get("consecutive_failures") == 2 and "blocked" not in disk,
          f"rc={rc} action={out.get('action')} "
          f"consecutive_failures={disk.get('consecutive_failures')} "
          f"blocked={disk.get('blocked')}")


# 4f — bool counter hole at the breaker read
def p_4f():
    sp, ov = TMP / "s4f.json", TMP / "s4f.override"
    sp.write_text('{"ts": 1, "delisted": false, "consecutive_failures": true}')
    node = FakeNode()
    node.pull_ok = False
    rc, out, _ = run_main(["--manual"], node, sp, ov)
    disk = read_json(sp)
    check("4f_bool_counter_hole",
          rc == 1 and disk.get("consecutive_failures") == 2,
          f"rc={rc} consecutive_failures={disk.get('consecutive_failures')}")


# 4g — interleaved read-modify-write loses an update (no lock)
def p_4g():
    p = TMP / "s4g.json"
    a = rd.load_state(str(p))
    a["delisted"] = True
    a["pulled_models"] = ["m1"]
    a["ts"] = 1
    b = rd.load_state(str(p))       # run B also loads the (empty) state
    b["delisted"] = False
    b["ts"] = 2
    rd.save_state(str(p), a)
    rd.save_state(str(p), b)        # last writer wins
    final = read_json(p)
    check("4g_interleaved_lost_update",
          final.get("delisted") is False and "pulled_models" not in final,
          f"final={final}")


# 4h — no directory fsync after the rename
def p_4h():
    src = DEPLOYED_FILE.read_text()
    opens = re.findall(r"os\.open|O_DIRECTORY", src)
    p = TMP / "s4h.json"
    calls = {"fsync": 0}
    real_fs = os.fsync

    def fs(fd):
        calls["fsync"] += 1
        return None

    os.fsync = fs
    try:
        rd.save_state(str(p), {"ts": 1})
    finally:
        os.fsync = real_fs
    check("4h_no_directory_fsync",
          opens == [] and calls["fsync"] == 1,
          f"os_open_or_O_DIRECTORY_hits={len(opens)} "
          f"fsync_calls={calls['fsync']} dir_opens=0")


# 4i — blocked refuses the nak publish too (behaviorally)
def p_4i():
    sp, ov = TMP / "s4i.json", TMP / "s4i.override"
    sp.write_text(json.dumps({"ts": 1, "delisted": False, "blocked": True,
                              "consecutive_failures": 3}))
    nsec = TMP / "nsec4i"
    nsec.write_text("nsec1TESTSECRETqxNEVERuseMEinPROD\n")
    node = FakeNode()
    spawns = []
    real_run = rd.subprocess.run

    def rec(argv, **kw):
        spawns.append(list(argv))
        return rd.subprocess.CompletedProcess(argv, 0)

    rd.subprocess.run = rec
    try:
        rc, out, _ = run_main(["--manual", "--nsec", str(nsec)], node, sp, ov)
    finally:
        rd.subprocess.run = real_run
    check("4i_blocked_refuses_publish_too",
          rc == 3 and out.get("action") == "blocked" and node.calls == []
          and spawns == [],
          f"rc={rc} action={out.get('action')} api_calls={node.calls} "
          f"nak_publishes={len(spawns)}")


# 4j — lock primitives absent in the script
def p_4j():
    src = DEPLOYED_FILE.read_text()
    hits = re.findall(r"flock|fcntl|lockf|O_EXCL|threading|multiprocessing", src)
    check("4j_no_lock_primitives", hits == [], f"lock_primitive_hits={len(hits)}")


# 4k — all 8 save_state call sites discard the return value
def p_4k():
    tree = ast.parse(DEPLOYED_FILE.read_text())
    bare = []
    for n in ast.walk(tree):
        if (isinstance(n, ast.Expr) and isinstance(n.value, ast.Call)
                and isinstance(n.value.func, ast.Name)
                and n.value.func.id == "save_state"):
            bare.append(n.lineno)
    check("4k_save_state_returns_discarded", len(bare) == 8,
          f"bare_save_state_sites={len(bare)} lines={bare}")


# ═══ Finding 5 ═══════════════════════════════════════════════════════════════

# 5a — constants non-decorative and internally consistent
def p_5a():
    a = (rd.TRIGGER_ACTION_WINDOW_S, rd.POLL_CADENCE_S, rd.ACTION_BUDGET_S,
         rd.SSH_TIMEOUT_S, rd.MAX_PULL_ATTEMPTS)
    ok = (a == (300, 240, 60, 30, 2)
          and rd.POLL_CADENCE_S + rd.ACTION_BUDGET_S == rd.TRIGGER_ACTION_WINDOW_S
          and 2 * rd.SSH_TIMEOUT_S <= rd.ACTION_BUDGET_S)
    check("5a_constants_arithmetic", ok,
          f"window={a[0]} cadence={a[1]} budget={a[2]} ssh={a[3]} "
          f"max_attempts={a[4]}")


# 5b — expired deadline refuses WITHOUT spawning; live deadline is clamped
def p_5b():
    spawns = []
    real_run = rd.subprocess.run

    def rec(cmd, capture_output=False, text=False, timeout=None, **kw):
        spawns.append(timeout)
        return rd.subprocess.CompletedProcess(cmd, 0, stdout="{}", stderr="")

    rd.subprocess.run = rec
    try:
        b = rd._SshBackend("host", "ctr")
        r1 = b._run("payload", dry_run=False, action="pull",
                    deadline=time.monotonic() - 1.0)
        n_after_expired = len(spawns)
        r2 = b._run("payload", dry_run=False, action="pull",
                    deadline=time.monotonic() + 1.0)
    finally:
        rd.subprocess.run = real_run
    clamped = spawns[-1] if spawns else None
    check("5b_budget_exhausted_no_spawn",
          r1.get("ok") is False and r1.get("error") == "action budget exhausted"
          and n_after_expired == 0 and clamped is not None
          and clamped <= 1.05 and clamped < rd.SSH_TIMEOUT_S,
          f"res={r1} spawns_after_expired={n_after_expired} "
          f"live_clamped_timeout={clamped}")


# 5b2 — with no deadline each round-trip still bounded at SSH_TIMEOUT_S
def p_5b2():
    spawns = []
    real_run = rd.subprocess.run

    def rec(cmd, capture_output=False, text=False, timeout=None, **kw):
        spawns.append(timeout)
        return rd.subprocess.CompletedProcess(cmd, 0, stdout="{}", stderr="")

    rd.subprocess.run = rec
    try:
        rd._SshBackend("host", "ctr")._run("payload", dry_run=False,
                                           action="pull", deadline=None)
    finally:
        rd.subprocess.run = real_run
    check("5b2_no_deadline_timeout", spawns == [rd.SSH_TIMEOUT_S],
          f"timeouts={spawns}")


# 5c — cadence arithmetic: */4 exactly 300 s, */5 breaches, */2 slack
def p_5c():
    def slack(cadence_min):
        return rd.TRIGGER_ACTION_WINDOW_S - (
            cadence_min * 60 + rd.ACTION_BUDGET_S)
    check("5c_cadence_arithmetic",
          slack(4) == 0 and slack(5) == -60 and slack(2) == 120,
          f"slack */4={slack(4)}s  */5={slack(5)}s  */2={slack(2)}s")


# 5d — the post-success nak publish is not budget-clamped
def p_5d():
    sp, ov = TMP / "s5d.json", TMP / "s5d.override"
    nsec = TMP / "nsec5d"
    nsec.write_text("nsec1TESTSECRETqxNEVERuseMEinPROD\n")
    node = FakeNode()
    timeouts = []
    real_run = rd.subprocess.run

    def rec(argv, timeout=None, env=None, capture_output=False, **kw):
        timeouts.append(timeout)
        return rd.subprocess.CompletedProcess(argv, 0)

    rd.subprocess.run = rec
    try:
        rc, out, _ = run_main(["--manual", "--nsec", str(nsec)], node, sp, ov)
    finally:
        rd.subprocess.run = real_run
    check("5d_publish_timeout_unclamped",
          rc == 0 and out.get("confirmed") is True and timeouts == [30]
          and rd.ACTION_BUDGET_S == 60,
          f"rc={rc} confirmed={out.get('confirmed')} publish_timeouts={timeouts} "
          f"budget={rd.ACTION_BUDGET_S}")


# 5e — the bounded retry is opportunistic: one lying attempt eats the budget
def p_5e():
    sp, ov = TMP / "s5e.json", TMP / "s5e.override"
    clock = Clock()
    node = FakeNode(clock=clock, round_trip_s=30.0)
    node.verify_count = 3                       # LYING pull: verify refutes
    real_mono = rd.time.monotonic
    rd.time.monotonic = clock.monotonic
    try:
        rc, out, _ = run_main(["--manual"], node, sp, ov)
    finally:
        rd.time.monotonic = real_mono
    check("5e_worst_case_eats_retry",
          rc == 1 and node.calls == ["pull", "verify"] and clock.now == 60.0,
          f"rc={rc} calls={node.calls} elapsed={clock.now}s "
          f"budget={rd.ACTION_BUDGET_S}s")


# 5f — local fsync is real and un-clamped by the deadline
def p_5f():
    sp, ov = TMP / "s5f.json", TMP / "s5f.override"
    node = FakeNode()
    n = {"fsync": 0}
    real_fs = os.fsync

    def fs(fd):
        n["fsync"] += 1
        return None

    os.fsync = fs
    try:
        rc, out, _ = run_main(["--delist"], node, sp, ov)
    finally:
        os.fsync = real_fs
    check("5f_local_fsync_unclamped",
          rc == 0 and out.get("action") == "delist" and n["fsync"] >= 1,
          f"rc={rc} action={out.get('action')} local_fsync_calls={n['fsync']}")


# 5g — the deadline arms exactly once for the whole attempt loop
def p_5g():
    sp, ov = TMP / "s5g.json", TMP / "s5g.override"
    clock = Clock()
    node = FakeNode(clock=clock, round_trip_s=30.0)
    node.pull_ok = False                        # plain failing pull
    real_mono = rd.time.monotonic
    rd.time.monotonic = clock.monotonic
    try:
        rc, out, _ = run_main(["--manual"], node, sp, ov)
    finally:
        rd.time.monotonic = real_mono
    deadlines = {d for _, d in node.deadlines}
    check("5g_inrun_retry_bounded",
          rc == 1 and node.calls == ["pull", "pull"] and len(deadlines) == 1
          and clock.now == 60.0,
          f"rc={rc} calls={node.calls} one_deadline={len(deadlines) == 1} "
          f"attempts={len(node.calls)} elapsed={clock.now}")


def main():
    for fn in (p_4a, p_4a2, p_4b, p_4b3, p_4c, p_4d, p_4e, p_4f, p_4g, p_4h,
               p_4i, p_4j, p_4k,
               p_5a, p_5b, p_5b2, p_5c, p_5d, p_5e, p_5f, p_5g):
        try:
            fn()
        except Exception as exc:  # a probe crash is a FAIL, never silent
            check(fn.__name__, False, f"EXC {type(exc).__name__}: {exc}")
    passed = sum(1 for _, ok in RESULTS if ok)
    print(f"SUMMARY {passed}/{len(RESULTS)} probes PASS")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
