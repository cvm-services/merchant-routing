#!/usr/bin/env python3
"""Hermetic re-derivation probe — routstr delist findings 4 & 5 (14th offload pass).

Drives the DEPLOYED script ~/.hermes/bot/scripts/routstr_delist.py in-process
with a fake backend and a tempdir state file. No network, no artifact touched.
Exit 0 only if every probe below passes.
"""
import importlib.util
import io
import contextlib
import json
import os
import sys
import tempfile
import time
from pathlib import Path

SCRIPT = Path.home() / ".hermes/bot/scripts/routstr_delist.py"
spec = importlib.util.spec_from_file_location("routstr_delist", SCRIPT)
rd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rd)
_REAL_SSH_BACKEND = rd._SshBackend     # keep a handle: run_main() rebinds it

RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond), detail))
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}")


class FakeNode:
    def __init__(self, pull_ok=True, pull_names=("gpt-4o",), verify_ok=True,
                 verify_count=0, relist_ok=True):
        self.pull_ok = pull_ok
        self.pull_names = list(pull_names)
        self.verify_ok = verify_ok
        self.verify_count = verify_count
        self.relist_ok = relist_ok
        self.calls = []

    def pull(self, dry_run=False, deadline=None):
        self.calls.append("pull")
        if not self.pull_ok:
            return {"ok": False, "action": "pull", "error": "ssh down"}
        return {"ok": True, "action": "pull", "pulled": list(self.pull_names)}

    def verify(self, dry_run=False, deadline=None):
        self.calls.append("verify")
        return {"ok": self.verify_ok, "action": "verify",
                "count": self.verify_count}

    def relist(self, names=None, dry_run=False, deadline=None):
        self.calls.append("relist")
        if not self.relist_ok:
            return {"ok": False, "action": "relist", "error": "ssh down"}
        return {"ok": True, "action": "relist", "restored": len(names or [])}


def run_main(node, tmp, argv):
    """Drive rd.main() against a fake backend; return (rc, parsed_out)."""
    rd._SshBackend = lambda t, c: node
    sp = tmp / "state.json"
    op = tmp / "override"
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = rd.main(["--state", str(sp), "--override", str(op)] + argv)
    raw = out.getvalue()
    return rc, (json.loads(raw) if raw.strip() else {}), sp


# ── Finding 4 ────────────────────────────────────────────────────────────────
def probe_4a(tmp):
    p = tmp / "s4a.json"
    ok = rd.save_state(str(p), {"a": 1})
    litter = list(tmp.glob(".*.tmp"))
    check("4a_save_state_ok", ok is True and not litter,
          f"ret={ok} litter={litter}")


def probe_4a2(tmp):
    p = tmp / "s4a2.json"
    real = os.replace

    def boom(src, dst):
        raise OSError("forced replace failure")

    os.replace = boom
    try:
        ok = rd.save_state(str(p), {"a": 2})
    finally:
        os.replace = real
    litter = list(tmp.glob(".*.tmp"))
    check("4a2_save_state_false_on_error", ok is False and not litter,
          f"ret={ok} litter={litter}")


def probe_4b(tmp):
    """Silent persist failure: main() reports success while disk is stale."""
    tmp = tmp / "d4b"
    tmp.mkdir()
    node = FakeNode(pull_names=["gpt-4o"], verify_count=0)
    sp = tmp / "state.json"
    sp.write_text(json.dumps({"delisted": False, "ts": 1}))
    real = os.replace

    def fail_dst(src, dst):
        if Path(dst) == sp:
            raise OSError("ENOSPC")
        return real(src, dst)

    os.replace = fail_dst
    try:
        rc, out, _ = run_main(node, tmp, ["--manual"])
    finally:
        os.replace = real
    disk = rd.load_state(str(sp))
    check("4b_silent_persist_failure",
          rc == 0 and out.get("action") == "delist"
          and out.get("confirmed") is True and disk.get("delisted") is False,
          f"rc={rc} action={out.get('action')} confirmed={out.get('confirmed')} "
          f"state_on_disk={disk}")


def probe_4b2(tmp):
    tmp = tmp / "d4b2"
    tmp.mkdir()
    node = FakeNode()
    sp = tmp / "state.json"
    sp.write_text(json.dumps({"delisted": False, "ts": 1}))
    rd._SshBackend = lambda t, c: node
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = rd.main(["--state", str(sp), "--override", str(tmp / "o"),
                      "--status"])
    data = json.loads(out.getvalue())
    check("4b2_status_reads_stale", data.get("delisted") is False,
          f"delisted={data.get('delisted')}")


def probe_4c(tmp):
    tmp = tmp / "d4c"
    tmp.mkdir()
    node = FakeNode(pull_names=[], verify_count=0)      # node advertises nothing
    sp = tmp / "state.json"
    sp.write_text(json.dumps({"delisted": True, "pulled_models": ["m1", "m2"]}))
    rd._SshBackend = lambda t, c: node
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = rd.main(["--state", str(sp), "--override", str(tmp / "o"),
                      "--delist"])
    st = rd.load_state(str(sp))
    check("4c_redelist_merge",
          rc == 0 and st.get("pulled_models") == ["m1", "m2"],
          f"rc={rc} pulled_models={st.get('pulled_models')}")


def probe_4d(tmp):
    tmp = tmp / "d4d"
    tmp.mkdir()
    node = FakeNode()
    sp = tmp / "state.json"
    sp.write_text(json.dumps({"delisted": True}))
    rd._SshBackend = lambda t, c: node
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = rd.main(["--state", str(sp), "--override", str(tmp / "o"),
                      "--relist"])
    data = json.loads(out.getvalue())
    check("4d_relist_refused",
          rc == 1 and data.get("action") == "relist_refused"
          and node.calls == [],
          f"rc={rc} action={data.get('action')} calls={node.calls}")


def probe_4e(tmp):
    tmp = tmp / "d4e"
    tmp.mkdir()
    node = FakeNode(relist_ok=False)
    sp = tmp / "state.json"
    sp.write_text(json.dumps({"delisted": True, "pulled_models": ["m1"],
                              "consecutive_failures": 2}))
    rd._SshBackend = lambda t, c: node
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = rd.main(["--state", str(sp), "--override", str(tmp / "o"),
                      "--relist"])
    st = rd.load_state(str(sp))
    check("4e_failed_relist_no_breaker_tick",
          rc == 1 and st.get("consecutive_failures") == 2,
          f"rc={rc} consecutive_failures={st.get('consecutive_failures')}")


def probe_4f(tmp):
    tmp = tmp / "d4f"
    tmp.mkdir()
    node = FakeNode(pull_ok=False)
    sp = tmp / "state.json"
    sp.write_text(json.dumps({"consecutive_failures": True}))   # bool, not int
    rd._SshBackend = lambda t, c: node
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = rd.main(["--state", str(sp), "--override", str(tmp / "o"),
                      "--manual"])
    st = rd.load_state(str(sp))
    check("4f_bool_counter_hole",
          st.get("consecutive_failures") == 2,
          f"rc={rc} consecutive_failures={st.get('consecutive_failures')}")


# ── Finding 5 ────────────────────────────────────────────────────────────────
def probe_5a():
    ok = (rd.TRIGGER_ACTION_WINDOW_S == 300 and rd.POLL_CADENCE_S == 240
          and rd.ACTION_BUDGET_S == 60
          and rd.POLL_CADENCE_S + rd.ACTION_BUDGET_S == rd.TRIGGER_ACTION_WINDOW_S
          and 2 * rd.SSH_TIMEOUT_S <= rd.ACTION_BUDGET_S)
    check("5a_constants_arithmetic", ok,
          f"{rd.POLL_CADENCE_S}+{rd.ACTION_BUDGET_S}=={rd.TRIGGER_ACTION_WINDOW_S}, "
          f"2*{rd.SSH_TIMEOUT_S}<={rd.ACTION_BUDGET_S}")


def probe_5b():
    spawns = []
    real = rd.subprocess.run

    def spy(cmd, **kw):
        spawns.append(kw)
        return real(cmd, **kw)

    rd.subprocess.run = spy
    try:
        be = _REAL_SSH_BACKEND("t", "c")
        res = be._run("payload", dry_run=False, action="pull",
                      deadline=time.monotonic() - 1)
    finally:
        rd.subprocess.run = real
    check("5b_budget_exhausted_no_spawn",
          res.get("ok") is False
          and res.get("error") == "action budget exhausted" and not spawns,
          f"res={res} spawns={len(spawns)}")


def probe_5b2():
    captured = []
    real = rd.subprocess.run

    def spy(cmd, **kw):
        captured.append(kw.get("timeout"))
        return type("P", (), {"returncode": 0, "stdout": "{}",
                              "stderr": ""})()

    rd.subprocess.run = spy
    try:
        be = _REAL_SSH_BACKEND("t", "c")
        be._run("payload", dry_run=False, action="pull", deadline=None)
    finally:
        rd.subprocess.run = real
    check("5b2_no_deadline_timeout",
          captured == [rd.SSH_TIMEOUT_S],
          f"timeouts={captured} SSH_TIMEOUT_S={rd.SSH_TIMEOUT_S}")


def probe_5c():
    worst_4 = rd.POLL_CADENCE_S + rd.ACTION_BUDGET_S      # */4
    worst_5 = 300 + rd.ACTION_BUDGET_S                    # */5
    check("5c_cadence_arithmetic",
          worst_4 == 300 and worst_5 == 360 > 300,
          f"*/4={worst_4}s */5={worst_5}s")


def probe_5d(tmp):
    """--nsec publish runs after success with an UNCLAMPED timeout=30."""
    tmp = tmp / "d5d"
    tmp.mkdir()
    sec = tmp / "nsec"
    sec.write_text("nsec1DUMMY")
    node = FakeNode(pull_names=["gpt-4o"], verify_count=0)
    sp = tmp / "state.json"
    captured = []
    real = rd.subprocess.run

    def spy(cmd, **kw):
        captured.append({"argv0": cmd[0], "timeout": kw.get("timeout")})
        return type("P", (), {"returncode": 0, "stdout": "{}",
                              "stderr": ""})()

    rd.subprocess.run = spy
    try:
        rc, out, _ = run_main(node, tmp, ["--manual", "--nsec", str(sec)])
    finally:
        rd.subprocess.run = real
    pub = [c for c in captured if c["argv0"].endswith("nak")]
    check("5d_publish_timeout_unclamped",
          out.get("confirmed") is True and pub and pub[0]["timeout"] == 30
          and pub[0]["timeout"] != rd.ACTION_BUDGET_S,
          f"confirmed={out.get('confirmed')} publish={pub}")


def main():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        probe_4a(tmp)
        probe_4a2(tmp)
        probe_4b(tmp)
        probe_4b2(tmp)
        probe_4c(tmp)
        probe_4d(tmp)
        probe_4e(tmp)
        probe_4f(tmp)
        probe_5a()
        probe_5b()
        probe_5b2()
        probe_5c()
        probe_5d(tmp)
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    print(f"\n{passed}/{len(RESULTS)} probes PASS")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
