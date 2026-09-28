#!/usr/bin/env python3
"""Pass-23 consolidated hermetic probe for routstr_delist findings 4-5.

Independent re-derivation for this session. Drives the DEPLOYED script
(~/.hermes/bot/scripts/routstr_delist.py) in process: no network, no real
subprocess, no /tmp scratch. Every finding reported in
docs/reviews/findings_4_5.md is derived here from a fresh run.

Run: python3 -P probe_f45_pass23.py
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import re
import stat
import subprocess
import tempfile
import time

SCRIPT = os.path.expanduser("~/.hermes/bot/scripts/routstr_delist.py")
TESTFILE = os.path.expanduser("~/.hermes/bot/tests/test_routstr_delist.py")
SCRATCH = os.path.expanduser("~/.tmp/f45-pass23")
os.makedirs(SCRATCH, exist_ok=True)

spec = importlib.util.spec_from_file_location("rd_deployed", SCRIPT)
rd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rd)
RealSshBackend = rd._SshBackend          # capture before any monkeypatch
SRC = open(SCRIPT).read()
TEST_SRC = open(TESTFILE).read()

RESULTS = []


def probe(name, **kw):
    RESULTS.append((name, kw))
    print(f"{name}: " + " ".join(f"{k}={v!r}" for k, v in kw.items()))


def mkdtemp():
    """Scratch under ~/.tmp, never /tmp (tmpfs, swept)."""
    return tempfile.mkdtemp(dir=SCRATCH)


class Clock:
    def __init__(self):
        self._m = 0.0

    def monotonic(self):
        return self._m

    @staticmethod
    def time():
        return time.time()

    def advance(self, s):
        self._m += s

    @property
    def now(self):
        return self._m


class FakeNode:
    """Behavioural stand-in for the ssh/docker backend."""

    def __init__(self, clock, models=None):
        self.clock = clock
        self.models = dict(models or {"advertised-a": 1, "advertised-b": 1,
                                      "operator-disabled": 0})
        self.calls = []
        self.deadline_log = []
        self.ssh_down = False
        self.pull_lands = True
        self.round_trip_s = 0.0

    def _trip(self, kind, deadline, payload=None):
        if deadline is not None:
            remaining = deadline - self.clock.monotonic()
            self.deadline_log.append({"kind": kind, "remaining": remaining,
                                      "timeout": min(rd.SSH_TIMEOUT_S,
                                                     max(remaining, 0.0))})
            if remaining <= 0:
                return {"ok": False, "action": kind,
                        "error": "action budget exhausted"}
        self.calls.append((kind, payload))
        if self.ssh_down:
            self.clock.advance(self.round_trip_s)
            return {"ok": False, "action": kind, "rc": 255,
                    "error": "ssh: connect to host: Connection refused"}
        if kind == "pull":
            pulled = [n for n, e in self.models.items() if e == 1]
            if self.pull_lands:
                for n in pulled:
                    self.models[n] = 0
            self.clock.advance(self.round_trip_s)
            return {"ok": True, "action": kind, "rc": 0, "pulled": pulled}
        if kind == "verify":
            self.clock.advance(self.round_trip_s)
            return {"ok": True, "action": kind, "rc": 0,
                    "count": sum(1 for e in self.models.values() if e == 1)}
        names = []
        self.clock.advance(self.round_trip_s)
        return {"ok": True, "action": kind, "rc": 0, "restored": len(names)}


class Backend:
    def __init__(self, node):
        self.node = node

    def pull(self, dry_run=False, deadline=None):
        return self.node._trip("pull", deadline, rd.pull_listing_payload())

    def verify(self, dry_run=False, deadline=None):
        return self.node._trip("verify", deadline, rd.verify_pull_payload())

    def relist(self, names=None, dry_run=False, deadline=None):
        return self.node._trip("relist", deadline, rd.relist_payload(names or []))


def run_main(tmp, node, *argv, preds=None):
    state = os.path.join(tmp, "state.json")
    marker = os.path.join(tmp, "marker")          # deliberately absent
    full = ["--state", state, "--override", marker]
    if preds is not None:
        full += ["--preds", preds]
    full += list(argv)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = rd.main(full)
    raw = out.getvalue()
    return rc, (json.loads(raw) if raw.strip() else {}), raw, state


def with_clock(clock, node):
    rd.time = clock
    rd._SshBackend = lambda t, c: Backend(node)


def _fail_replace(path_that_must_fail):
    real_replace = os.replace

    def bad(src, dst):
        if os.path.abspath(dst) == os.path.abspath(path_that_must_fail):
            raise OSError("simulated persist failure (ENOSPC)")
        return real_replace(src, dst)
    return bad


# ── 4.1 atomic write protocol ────────────────────────────────────────────
def p4a():
    d = mkdtemp()
    path = os.path.join(d, "s.json")
    real_fsync, real_replace = os.fsync, os.replace
    fsyncs, replaces = [], []

    def spy_fsync(fd):
        fsyncs.append(fd)
        return real_fsync(fd)

    def spy_replace(src, dst):
        replaces.append((src, dst))
        return real_replace(src, dst)

    rd.os.fsync, rd.os.replace = spy_fsync, spy_replace
    try:
        ret = rd.save_state(path, {"ts": 1, "delisted": True})
    finally:
        rd.os.fsync, rd.os.replace = real_fsync, real_replace
    litter = [f for f in os.listdir(d) if f.startswith(".") and f.endswith(".tmp")]
    probe("4a_atomic_save_protocol", ret=ret, fsync_calls=len(fsyncs),
          replace_calls=len(replaces), litter=litter,
          on_disk=json.load(open(path)))


# ── 4.2 silent persist failure through main() ────────────────────────────
def p4b():
    tmp = mkdtemp()
    state = os.path.join(tmp, "state.json")
    seeded = {"ts": 10, "delisted": False, "snapshot": {"zai\x1f1h": 10.0},
              "consecutive_failures": 2}
    rd.save_state(state, seeded)
    clock = Clock()
    node = FakeNode(clock)
    with_clock(clock, node)
    node.models = {"advertised-a": 1}
    real = os.replace
    rd.os.replace = _fail_replace(state)
    try:
        rc, out, _, _ = run_main(tmp, node, "--manual")
    finally:
        rd.os.replace = real
    disk = rd.load_state(state)
    probe("4b_silent_persist_failure_main", rc=rc, action=out.get("action"),
          ok=out.get("ok"), confirmed=out.get("confirmed"),
          disk_unchanged=(disk == seeded), disk_delisted=disk.get("delisted"))


def p4b2():
    """The publisher's advertisement flag IS the persisted delisted field."""
    tmp = mkdtemp()
    state = os.path.join(tmp, "state.json")
    rd.save_state(state, {"ts": 10, "delisted": False})
    clock = Clock()
    node = FakeNode(clock)
    node.models = {"advertised-a": 1}
    with_clock(clock, node)
    real = os.replace
    rd.os.replace = _fail_replace(state)
    try:
        rc, out, _, _ = run_main(tmp, node, "--manual")
    finally:
        rd.os.replace = real
    probe("4b2_delivered_flag_not_flipped", rc=rc, ok=out.get("ok"),
          listing_pulled=(sum(node.models.values()) == 0),
          disk_delisted=rd.load_state(state).get("delisted"))


def p4b3():
    """Persist failures: exit 3 every run, but no durable BLOCKED marker.

    Also MEASURES --status (prior passes hardcoded status_reports_blocked).
    """
    tmp = mkdtemp()
    state = os.path.join(tmp, "state.json")
    rd.save_state(state, {"ts": 10, "delisted": False,
                          "consecutive_failures": 2, "blocked": False})
    clock = Clock()
    node = FakeNode(clock)
    node.ssh_down = True
    with_clock(clock, node)
    real = os.replace
    rd.os.replace = _fail_replace(state)
    try:
        rcs = [run_main(tmp, node, "--manual")[0] for _ in range(4)]
    finally:
        rd.os.replace = real
    disk = rd.load_state(state)
    # now read the durable operator signal for real
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rd.main(["--state", state, "--override",
                 os.path.join(tmp, "marker"), "--status"])
    status = json.loads(out.getvalue())
    probe("4b3_persist_failure_freezes_breaker", rcs=rcs,
          disk_consecutive_failures=disk.get("consecutive_failures"),
          disk_blocked=disk.get("blocked"),
          status_reports_blocked=status.get("blocked"))


def p4b4():
    """Static: every save_state() call site discards the return value."""
    lines = SRC.splitlines()
    calls = [i + 1 for i, ln in enumerate(lines) if "save_state(" in ln
             and "def save_state" not in ln]
    discarded = [n for n in calls if not re.match(
        r"\s*(if |return |[A-Za-z_][A-Za-z0-9_]*\s*=|assert )", lines[n - 1])]
    guards = [i + 1 for i, ln in enumerate(lines)
              if "save_state(" in ln and ("if " in ln or "= " in ln)]
    probe("4b4_call_sites_discard_return", call_sites=calls,
          discarded=discarded, guarded=guards,
          main_checks_return=("if not save_state" in SRC or "= save_state" in SRC))


# ── 4.4 no inter-process lock (lost update) ──────────────────────────────
def p4g():
    d = mkdtemp()
    path = os.path.join(d, "state.json")
    rd.save_state(path, {"ts": 1, "delisted": False})
    snap_a = rd.load_state(path)
    snap_b = rd.load_state(path)
    a = dict(snap_a, ts=3, delisted=True, pulled_models=["m1"])
    rd.save_state(path, a)                       # A commits
    b = dict(snap_b, ts=2, delisted=False)
    rd.save_state(path, b)                       # B commits stale snapshot
    final = rd.load_state(path)
    probe("4g_no_lock_last_writer_wins", final_delisted=final.get("delisted"),
          final_ts=final.get("ts"),
          a_transition_lost=(final.get("delisted") is not True))


def p4g2():
    hits = re.findall(r"flock|fcntl|lockf|O_EXCL|threading|multiprocessing", SRC)
    probe("4g2_no_lock_primitives_static", hits=len(hits))


# ── 4.5 no directory fsync after replace ─────────────────────────────────
def p4h():
    d = mkdtemp()
    path = os.path.join(d, "state.json")
    real_fsync = os.fsync
    targets = []

    def spy(fd):
        try:
            targets.append(stat.S_ISDIR(os.fstat(fd).st_mode))
        except OSError:
            targets.append(None)
        return real_fsync(fd)

    rd.os.fsync = spy
    try:
        ret = rd.save_state(path, {"ts": 1})
    finally:
        rd.os.fsync = real_fsync
    probe("4h_no_directory_fsync", ret=ret, fsync_targets_dir=targets,
          O_DIRECTORY_hits=SRC.count("O_DIRECTORY"),
          os_open_hits=SRC.count("os.open("))


# ── 4.6 re-delist merges pulled_models ───────────────────────────────────
def p4c():
    tmp = mkdtemp()
    state = os.path.join(tmp, "state.json")
    rd.save_state(state, {"ts": 1, "delisted": True,
                          "pulled_models": ["m1", "m2"]})
    clock = Clock()
    node = FakeNode(clock)
    node.models = {}
    with_clock(clock, node)
    rc, out, _, _ = run_main(tmp, node, "--delist")
    st = rd.load_state(state)
    probe("4c_redelist_merge", rc=rc, pulled=out.get("pulled"),
          pulled_models=st.get("pulled_models"),
          clobbered=(st.get("pulled_models") != ["m1", "m2"]))


# ── 4.7 no-names relist refuses ──────────────────────────────────────────
def p4d():
    tmp = mkdtemp()
    state = os.path.join(tmp, "state.json")
    rd.save_state(state, {"ts": 1, "delisted": True})
    clock = Clock()
    node = FakeNode(clock)
    with_clock(clock, node)
    rc, out, _, _ = run_main(tmp, node, "--relist")
    probe("4d_relist_refused", rc=rc, action=out.get("action"),
          backend_calls=node.calls)


def p4d2():
    live = os.path.expanduser("~/.hermes/bot/routstr_delist_state.json")
    st = rd.load_state(live)
    probe("4d2_live_state_no_pulled_models", delisted=st.get("delisted"),
          has_pulled_models=("pulled_models" in st), keys=sorted(st.keys()))


# ── 4.8 failed relist does not tick the breaker ──────────────────────────
def p4e():
    tmp = mkdtemp()
    state = os.path.join(tmp, "state.json")
    rd.save_state(state, {"ts": 1, "delisted": True, "pulled_models": ["m1"],
                          "consecutive_failures": 2})
    clock = Clock()
    node = FakeNode(clock)
    node.ssh_down = True
    with_clock(clock, node)
    rc, out, _, _ = run_main(tmp, node, "--relist")
    st = rd.load_state(state)
    probe("4e_failed_relist_no_breaker_tick", rc=rc, action=out.get("action"),
          disk_consecutive_failures=st.get("consecutive_failures"),
          blocked_key_present=("blocked" in st))


# ── 4.9 bool counter hole ────────────────────────────────────────────────
def p4f():
    tmp = mkdtemp()
    state = os.path.join(tmp, "state.json")
    with open(state, "w") as fh:
        json.dump({"ts": 1, "delisted": False, "consecutive_failures": True}, fh)
    clock = Clock()
    node = FakeNode(clock)
    node.ssh_down = True
    with_clock(clock, node)
    rc, out, _, _ = run_main(tmp, node, "--manual")
    st = rd.load_state(state)
    probe("4f_bool_counter_hole", rc=rc,
          consecutive_failures=st.get("consecutive_failures"),
          bool_accepted_as_one=(st.get("consecutive_failures") == 2))


# ── 4.10 failed delist CLEARS the durable advertisement flag ─────────────
def p4i():
    tmp = mkdtemp()
    state = os.path.join(tmp, "state.json")
    clock = Clock()
    node = FakeNode(clock)
    with_clock(clock, node)
    rc1, out1, _, _ = run_main(tmp, node, "--manual")        # confirmed delist
    after_ok = rd.load_state(state)
    node.ssh_down = True
    rc2, out2, _, _ = run_main(tmp, node, "--manual")        # failed delist
    after_fail = rd.load_state(state)
    probe("4i_failed_delist_clears_flag", rc_ok=rc1, rc_fail=rc2,
          flag_after_success=after_ok.get("delisted"),
          flag_after_failure=after_fail.get("delisted"),
          pulled_models_kept=after_fail.get("pulled_models"),
          listing_still_pulled_on_node=(
              sum(1 for e in node.models.values() if e == 1) == 0),
          advertisement_flapped=(after_fail.get("delisted") is False))


# ── 4.11 dry-run persist failure is silent too ───────────────────────────
def p4j():
    tmp = mkdtemp()
    state = os.path.join(tmp, "state.json")
    rd.save_state(state, {"ts": 1, "delisted": False})
    before = open(state, "rb").read()
    clock = Clock()
    node = FakeNode(clock)
    with_clock(clock, node)
    real = os.replace
    rd.os.replace = _fail_replace(state)
    try:
        rc, out, _, _ = run_main(tmp, node, "--manual", "--dry-run")
    finally:
        rd.os.replace = real
    probe("4j_dry_run_persist_failure_silent", rc=rc, action=out.get("action"),
          intent_persisted=("last_dry_run" in rd.load_state(state)),
          disk_unchanged=(open(state, "rb").read() == before))


# ── 5.1 constants / wiring ───────────────────────────────────────────────
def p5a():
    sites = [i + 1 for i, ln in enumerate(SRC.splitlines())
             if "ACTION_BUDGET_S" in ln and "=" not in ln.split("ACTION_BUDGET_S")[0]]
    probe("5a_constants_arithmetic",
          window=rd.TRIGGER_ACTION_WINDOW_S, cadence=rd.POLL_CADENCE_S,
          budget=rd.ACTION_BUDGET_S, ssh=rd.SSH_TIMEOUT_S,
          max_attempts=rd.MAX_PULL_ATTEMPTS,
          sums_to_window=(rd.POLL_CADENCE_S + rd.ACTION_BUDGET_S
                          == rd.TRIGGER_ACTION_WINDOW_S),
          two_trips_fit=(2 * rd.SSH_TIMEOUT_S <= rd.ACTION_BUDGET_S),
          ACTION_BUDGET_S_load_lines=sites)


# ── 5.2 budget exhaustion refuses without spawning ───────────────────────
def p5b():
    clock = Clock()
    node = FakeNode(clock)
    with_clock(clock, node)
    clock.advance(10_000)
    deadline = clock.monotonic() - 1
    res = RealSshBackend("h", "c")._run("payload", dry_run=False,
                                        action="pull", deadline=deadline)
    probe("5b_budget_exhausted_no_spawn", error=res.get("error"),
          ok=res.get("ok"))


# ── 5.3 cadence arithmetic ───────────────────────────────────────────────
def p5c():
    out = {}
    for label, cad in (("*/4", 240), ("*/5", 300), ("*/2", 120)):
        worst = cad + rd.ACTION_BUDGET_S
        out[label] = {"worst_s": worst,
                      "slack_s": rd.TRIGGER_ACTION_WINDOW_S - worst}
    probe("5c_cadence_arithmetic", arithmetic=out)


# ── 5.4 no crontab pins the cadence ─────────────────────────────────────
def p5d():
    out = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    hits = [ln for ln in out.stdout.splitlines() if "routstr" in ln.lower()]
    probe("5d_no_cron_pins_cadence", routstr_crontab_entries=len(hits))


# ── 5.5 local fsync is outside the deadline ─────────────────────────────
def p5e():
    d = mkdtemp()
    path = os.path.join(d, "s.json")
    calls = []
    real = os.fsync

    def spy(fd):
        calls.append(fd)
        return real(fd)

    rd.os.fsync = spy
    try:
        ret = rd.save_state(path, {"ts": 1})
    finally:
        rd.os.fsync = real
    probe("5e_local_fsync_unclamped", ret=ret, real_fsync_calls=len(calls))


# ── 5.6 publish is outside the deadline ─────────────────────────────────
def p5f():
    tmp = mkdtemp()
    nsec = os.path.join(tmp, "nsec")
    open(nsec, "w").write("nsec1PROBEPLACEHOLDERnotarealkey\n")
    clock = Clock()
    node = FakeNode(clock)
    node.round_trip_s = 30.0
    with_clock(clock, node)
    timeouts = []
    real_run = rd.subprocess.run

    def fake_run(argv, timeout=None, env=None, capture_output=False, **kw):
        timeouts.append(timeout)
        clock.advance(timeout or 0)
        return subprocess.CompletedProcess(argv, 0)

    rd.subprocess.run = fake_run
    try:
        rc, out, _, _ = run_main(tmp, node, "--manual", "--nsec", nsec)
    finally:
        rd.subprocess.run = real_run
    probe("5g_publish_unclamped_total_run", rc=rc, confirmed=out.get("confirmed"),
          publish_timeouts=timeouts, budget=rd.ACTION_BUDGET_S,
          total_elapsed=clock.now)


# ── 5.7 retry structurally inert in the worst case ──────────────────────
def p5g():
    tmp = mkdtemp()
    clock = Clock()
    node = FakeNode(clock)
    node.round_trip_s = 30.0
    node.pull_lands = False
    with_clock(clock, node)
    rc, out, _, _ = run_main(tmp, node, "--manual")
    probe("5f_retry_inert_worst_case", rc=rc,
          calls=[k for k, _ in node.calls], elapsed=clock.now,
          budget=rd.ACTION_BUDGET_S,
          attempts_ran=len([1 for k, _ in node.calls if k == "pull"]))


# ── 5.8 contract suite stubs fsync everywhere (doc claim audit) ──────────
def p5h():
    stub_lines = [i + 1 for i, ln in enumerate(TEST_SRC.splitlines())
                  if 'setattr(os, "fsync"' in ln]
    doc_claim = [i + 1 for i, ln in enumerate(TEST_SRC.splitlines())
                 if "real fsync" in ln]
    probe("5h_contract_fsync_stub_audit", rig_stub_lines=stub_lines,
          claims_real_fsync_lines=doc_claim,
          stubs=len(stub_lines),
          real_fsync_exercised_by_tests=False)


def main():
    for fn in (p4a, p4b, p4b2, p4b3, p4b4, p4g, p4g2, p4h, p4c, p4d, p4d2,
               p4e, p4f, p4i, p4j, p5a, p5b, p5c, p5d, p5e, p5f, p5g, p5h):
        try:
            fn()
        except Exception as exc:                      # noqa: BLE001
            probe(fn.__name__ + "_ERROR", error=repr(exc))
    print(f"\nprobes_run={len(RESULTS)}")


if __name__ == "__main__":
    main()
