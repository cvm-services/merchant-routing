#!/usr/bin/env python3
"""19th-pass independent hermetic probes for routstr-delist findings 4-5.

Re-derives every behavioural claim in docs/reviews/findings_4_5.md from the
CURRENT deployed artifact set, in-process, with a fake backend, tempdir state,
forced persist failures and no network / no real ssh spawn. Read-only w.r.t.
every artifact under review.

Scratch lives under ~/worktrees (never /tmp).

Usage: python3 probe_f45_pass19.py
"""
import ast
import contextlib
import io
import json
import os
import signal
import stat as statmod
import sys
import tempfile
import time

BOT = os.path.expanduser("~/.hermes/bot/scripts")
SCRATCH = os.path.expanduser("~/worktrees/f45-review-19-scratch")
os.makedirs(SCRATCH, exist_ok=True)
sys.path.insert(0, BOT)
import routstr_delist as rd  # noqa: E402

RESULTS = []


def record(tag, ok, detail):
    RESULTS.append((tag, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'} {tag} :: {detail}")


class FakeNode:
    def __init__(self, advertised=None, ssh_down=False, pull_lands=True,
                 relist_fail=False):
        self.advertised = advertised if advertised is not None else ["m1", "m2"]
        self.ssh_down = ssh_down
        self.pull_lands = pull_lands
        self.relist_fail = relist_fail
        self.calls = []


class FakeBackend:
    def __init__(self, node):
        self.node = node

    def pull(self, dry_run=False, deadline=None):
        self.node.calls.append("pull")
        if self.node.ssh_down:
            return {"ok": False, "action": "pull", "rc": 255, "error": "ssh down"}
        return {"ok": True, "action": "pull", "pulled": list(self.node.advertised)}

    def verify(self, dry_run=False, deadline=None):
        self.node.calls.append("verify")
        if self.node.ssh_down:
            return {"ok": False, "action": "verify", "rc": 255}
        if not self.node.pull_lands:
            return {"ok": True, "action": "verify",
                    "count": len(self.node.advertised)}
        return {"ok": True, "action": "verify", "count": 0}

    def relist(self, names=None, dry_run=False, deadline=None):
        self.node.calls.append("relist")
        if self.node.relist_fail:
            return {"ok": False, "action": "relist", "rc": 1, "error": "boom"}
        return {"ok": True, "action": "relist", "restored": len(names or [])}


def run_main(argv, node, state_path, *, replace_fails=False, spawn_log=None):
    """Run rd.main() against the fake backend; capture rc + parsed JSON."""
    orig_backend = rd._SshBackend
    orig_replace = os.replace
    orig_subprocess_run = rd.subprocess.run
    rd._SshBackend = lambda t, c: FakeBackend(node)
    if replace_fails:
        def bad_replace(src, dst):
            if os.path.normpath(str(dst)) == os.path.normpath(state_path):
                raise OSError("simulated ENOSPC/EROFS on state persist")
            return orig_replace(src, dst)
        os.replace = bad_replace
    if spawn_log is not None:
        class _CP:
            def __init__(self, argv, rc):
                self.args = argv
                self.returncode = rc
                self.stdout = ""
                self.stderr = ""
        def fake_run(argv, timeout=None, env=None, capture_output=False, **kw):
            spawn_log.append({"argv": list(argv), "timeout": timeout})
            return _CP(argv, 0)
        rd.subprocess.run = fake_run
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out):
            rc = rd.main(list(argv))
    finally:
        rd._SshBackend = orig_backend
        os.replace = orig_replace
        rd.subprocess.run = orig_subprocess_run
    raw = out.getvalue()
    return rc, (json.loads(raw) if raw.strip() else {}), raw


def state_seed(path, obj):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh)
    return path


def argv_for(state_path, *rest):
    return ["--state", str(state_path),
            "--override", os.path.join(SCRATCH, "no.override"), *rest]


# ── 4a: atomic save protocol (tmp + flush + fsync + os.replace) ───────────
def probe_4a():
    path = os.path.join(SCRATCH, "4a.json")
    fsyncs, replaces = [], []
    orig_fsync, orig_replace = os.fsync, os.replace
    os.fsync = lambda fd: fsyncs.append(fd)
    def spy_replace(src, dst):
        replaces.append((src, dst))
        return orig_replace(src, dst)
    os.replace = spy_replace
    try:
        ret = rd.save_state(path, {"ts": 1, "delisted": True})
    finally:
        os.fsync, os.replace = orig_fsync, orig_replace
    litter = [f for f in os.listdir(SCRATCH) if f.endswith(".tmp")]
    detail = (f"ret={ret} fsync_calls={len(fsyncs)} replace_calls={len(replaces)} "
              f"litter={litter}")
    record("4a_atomic_save_protocol",
           ret is True and len(fsyncs) == 1 and len(replaces) == 1 and not litter,
           detail)


# ── 4b: a failed persist is reported to the caller as success ─────────────
def probe_4b():
    path = os.path.join(SCRATCH, "4b.json")
    seed = {"ts": 1, "delisted": False, "snapshot": {"zai\x1f1h": 10.0},
            "consecutive_failures": 2}
    state_seed(path, seed)
    node = FakeNode(advertised=["m1"])
    rc, out, _ = run_main(argv_for(path, "--manual"), node, path,
                          replace_fails=True)
    disk = json.load(open(path))
    detail = (f"rc={rc} action={out.get('action')} confirmed={out.get('confirmed')} "
              f"disk_unchanged={disk == seed} disk={disk}")
    record("4b_silent_persist_failure",
           rc == 0 and out.get("action") == "delist"
           and out.get("confirmed") is True and disk == seed, detail)


# ── 4b3: persist failure freezes the durable BLOCKED marker, rc 3 still fires
def probe_4b3():
    path = os.path.join(SCRATCH, "4b3.json")
    seed = {"ts": 1, "delisted": False, "consecutive_failures": 2,
            "blocked": False}
    state_seed(path, seed)
    node = FakeNode(ssh_down=True)
    rcs = []
    for _ in range(4):
        rc, out, _ = run_main(argv_for(path, "--manual"), node, path,
                              replace_fails=True)
        rcs.append(rc)
    disk = json.load(open(path))
    detail = (f"rcs={rcs} disk_consecutive_failures="
              f"{disk.get('consecutive_failures')} disk_blocked="
              f"{disk.get('blocked')}")
    record("4b3_persist_failure_freezes_breaker",
           rcs == [3, 3, 3, 3] and disk.get("consecutive_failures") == 2
           and disk.get("blocked") is False, detail)


# ── 4c: re-delist MERGES pulled_models (never clobbers) ───────────────────
def probe_4c():
    path = os.path.join(SCRATCH, "4c.json")
    state_seed(path, {"ts": 1, "delisted": True, "pulled_models": ["m1", "m2"],
                      "consecutive_failures": 0})
    node = FakeNode(advertised=[])          # nothing advertised now
    rc, out, _ = run_main(argv_for(path, "--delist"), node, path)
    disk = json.load(open(path))
    detail = (f"rc={rc} pulled={out.get('pulled')} "
              f"pulled_models={disk.get('pulled_models')}")
    record("4c_redelist_merge",
           rc == 0 and out.get("pulled") == []
           and disk.get("pulled_models") == ["m1", "m2"], detail)


# ── 4d: no-names relist REFUSES before any remote round-trip ──────────────
def probe_4d():
    path = os.path.join(SCRATCH, "4d.json")
    state_seed(path, {"ts": 1, "delisted": True})   # no pulled_models
    node = FakeNode()
    rc, out, _ = run_main(argv_for(path, "--relist"), node, path)
    detail = f"rc={rc} action={out.get('action')} calls={node.calls}"
    record("4d_relist_refused",
           rc == 1 and out.get("action") == "relist_refused"
           and node.calls == [], detail)


# ── 4e: a failed relist does NOT tick the breaker ─────────────────────────
def probe_4e():
    path = os.path.join(SCRATCH, "4e.json")
    state_seed(path, {"ts": 1, "delisted": True, "pulled_models": ["m1"],
                      "consecutive_failures": 2, "blocked": False})
    node = FakeNode(relist_fail=True)
    rc, out, _ = run_main(argv_for(path, "--relist"), node, path)
    disk = json.load(open(path))
    detail = (f"rc={rc} action={out.get('action')} "
              f"consecutive_failures={disk.get('consecutive_failures')} "
              f"blocked={disk.get('blocked')}")
    record("4e_failed_relist_no_breaker_tick",
           rc == 1 and out.get("action") == "relist_failed"
           and disk.get("consecutive_failures") == 2
           and disk.get("blocked") is False, detail)


# ── 4f: bool counter hole at the breaker read ─────────────────────────────
def probe_4f():
    path = os.path.join(SCRATCH, "4f.json")
    state_seed(path, {"ts": 1, "delisted": False, "consecutive_failures": True,
                      "blocked": False})
    node = FakeNode(ssh_down=True)
    rc, out, _ = run_main(argv_for(path, "--manual"), node, path)
    disk = json.load(open(path))
    detail = (f"rc={rc} seeded_bool=True -> "
              f"consecutive_failures={disk.get('consecutive_failures')}")
    record("4f_bool_counter_hole", disk.get("consecutive_failures") == 2, detail)


# ── 4g: interleaved read-modify-write loses an update (no lock) ───────────
def probe_4g():
    path = os.path.join(SCRATCH, "4g.json")
    # run A reads
    a = rd.load_state(path)
    # run B reads the same (pre-A) state, mutates, writes
    b = rd.load_state(path)
    b.update({"ts": 2, "delisted": False})
    rd.save_state(path, b)
    # run A commits its own update on its stale snapshot
    a.update({"ts": 3, "delisted": True, "pulled_models": ["m1"]})
    rd.save_state(path, a)
    final = rd.load_state(path)
    detail = f"final={final}"
    record("4g_interleaved_lost_update",
           final.get("delisted") is True and "pulled_models" in final, detail)


# ── 4h: no directory fsync (rename atomic but not crash-durable) ──────────
def probe_4h():
    src = open(os.path.join(BOT, "routstr_delist.py"), encoding="utf-8").read()
    tree = ast.parse(src)
    os_open = sum(1 for n in ast.walk(tree)
                  if isinstance(n, ast.Attribute) and n.attr == "open")
    dir_const = src.count("O_DIRECTORY")
    path = os.path.join(SCRATCH, "4h.json")
    seen = []
    orig_fsync = os.fsync
    os.fsync = lambda fd: seen.append(statmod.S_ISDIR(os.fstat(fd).st_mode))
    try:
        ret = rd.save_state(path, {"ts": 1})
    finally:
        os.fsync = orig_fsync
    detail = (f"os_open_attr={os_open} O_DIRECTORY={dir_const} "
              f"fsync_calls={len(seen)} dir_fsyncs={sum(seen)} ret={ret}")
    record("4h_no_directory_fsync",
           dir_const == 0 and len(seen) == 1 and sum(seen) == 0, detail)


# ── 4i: an open breaker refuses the nak publish too ──────────────────────
def probe_4i():
    path = os.path.join(SCRATCH, "4i.json")
    state_seed(path, {"ts": 1, "delisted": False, "consecutive_failures": 3,
                      "blocked": True})
    nsec = os.path.join(SCRATCH, "nsec")
    with open(nsec, "w") as fh:
        fh.write("nsec1FAKE\n")
    node = FakeNode()
    spawns = []
    rc, out, _ = run_main(argv_for(path, "--manual", "--nsec", nsec), node,
                          path, spawn_log=spawns)
    detail = (f"rc={rc} action={out.get('action')} api_calls={node.calls} "
              f"spawns={len(spawns)}")
    record("4i_blocked_refuses_publish_too",
           rc == 3 and out.get("action") == "blocked" and node.calls == []
           and spawns == [], detail)


# ── 5a: constants are internally consistent (non-decorative) ──────────────
def probe_5a():
    detail = (f"window={rd.TRIGGER_ACTION_WINDOW_S} cadence={rd.POLL_CADENCE_S} "
              f"budget={rd.ACTION_BUDGET_S} ssh={rd.SSH_TIMEOUT_S} "
              f"max_attempts={rd.MAX_PULL_ATTEMPTS}")
    record("5a_constants_arithmetic",
           rd.POLL_CADENCE_S + rd.ACTION_BUDGET_S == rd.TRIGGER_ACTION_WINDOW_S
           and 2 * rd.SSH_TIMEOUT_S <= rd.ACTION_BUDGET_S, detail)


# ── 5b: an exhausted budget refuses WITHOUT spawning; live call clamped ───
def probe_5b():
    src = open(os.path.join(BOT, "routstr_delist.py"), encoding="utf-8").read()
    # deadline armed from the two call sites (relist + delist)
    armed = [i + 1 for i, line in enumerate(src.splitlines())
             if "ACTION_BUDGET_S" in line and "monotonic" in line]
    spawns = []
    orig_run = rd.subprocess.run
    rd.subprocess.run = lambda argv, **kw: (spawns.append(kw.get("timeout")),
                                            _cp(argv))[1]
    backend = rd._SshBackend("deadtarget", "deadcontainer")
    try:
        expired = backend._run("print(1)", dry_run=False, action="pull",
                               deadline=time.monotonic() - 5)
        live = backend._run("print(1)", dry_run=False, action="pull",
                            deadline=time.monotonic() + 5)
    finally:
        rd.subprocess.run = orig_run
    detail = (f"deadline_sites={armed} expired={expired.get('error')} "
              f"spawns={spawns}")
    record("5b_budget_exhausted_no_spawn",
           expired.get("error") == "action budget exhausted"
           and len(spawns) == 1 and spawns[0] <= 5.01 and len(armed) == 2, detail)


class _cp:
    def __init__(self, argv):
        self.args = argv
        self.returncode = 0
        self.stdout = '{"ok": true}'
        self.stderr = ""


# ── 5c: worst-case detection + action vs the 300 s contract ───────────────
def probe_5c():
    w, b = rd.TRIGGER_ACTION_WINDOW_S, rd.ACTION_BUDGET_S
    # slack = window - (worst-case detection + action budget)
    s4, s5, s2 = w - (240 + b), w - (300 + b), w - (120 + b)
    detail = (f"slack */4={s4}s slack */5={s5}s slack */2={s2}s")
    record("5c_cadence_arithmetic", s4 == 0 and s5 == -60 and s2 == 120, detail)


# ── 5d: the --nsec publish carries the full 30 s constant, unclamped ──────
def probe_5d():
    path = os.path.join(SCRATCH, "5d.json")
    nsec = os.path.join(SCRATCH, "nsec")
    with open(nsec, "w") as fh:
        fh.write("nsec1FAKE\n")
    node = FakeNode(advertised=["m1"])
    spawns = []
    rc, out, _ = run_main(argv_for(path, "--manual", "--nsec", nsec), node,
                          path, spawn_log=spawns)
    detail = (f"rc={rc} confirmed={out.get('confirmed')} "
              f"publish_timeouts={[s['timeout'] for s in spawns]} "
              f"budget={rd.ACTION_BUDGET_S}")
    record("5d_publish_timeout_unclamped",
           rc == 0 and out.get("confirmed") is True
           and [s["timeout"] for s in spawns] == [30], detail)


# ── 5f: the local fsync is real and outside the action deadline ───────────
def probe_5f():
    path = os.path.join(SCRATCH, "5f.json")
    calls = []
    orig_fsync = os.fsync
    os.fsync = lambda fd: (calls.append(fd), orig_fsync(fd))[1]
    err, ret = None, None
    def _alarm(*_a):
        raise TimeoutError("fsync stalled > 8 s")
    old = signal.signal(signal.SIGALRM, _alarm)
    signal.alarm(8)
    try:
        ret = rd.save_state(path, {"ts": 1})
    except Exception as exc:
        err = type(exc).__name__
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)
        os.fsync = orig_fsync
    detail = (f"ret={ret} real_fsync_calls={len(calls)} err={err}")
    record("5f_local_fsync_unclamped", ret is True and len(calls) == 1, detail)


def main():
    for fn in (probe_4a, probe_4b, probe_4b3, probe_4c, probe_4d, probe_4e,
               probe_4f, probe_4g, probe_4h, probe_4i, probe_5a, probe_5b,
               probe_5c, probe_5d, probe_5f):
        try:
            fn()
        except Exception as exc:
            record(fn.__name__, False, f"EXC {type(exc).__name__}: {exc}")
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    print(f"\n{passed}/{len(RESULTS)} probes PASS")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
