#!/usr/bin/env python3
"""18th-pass independent hermetic probes for routstr-delist findings 4-5.

Drives the DEPLOYED script (~/.hermes/bot/scripts/routstr_delist.py) in-process
with a fake backend, tempdir state, forced persist failures, and no network /
no ssh spawn. Read-only w.r.t. every artifact under review.

Usage: python3 probe_f45_pass18.py
"""
import io
import contextlib
import json
import os
import signal
import stat as statmod
import sys
import time

BOT = os.path.expanduser("~/.hermes/bot/scripts")
SCRATCH = os.path.expanduser("~/worktrees/f45-review-18/scratch")
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


def run_main(argv, node, state_path, *, replace_fails=False):
    """Run rd.main() against the fake backend; capture rc + parsed JSON."""
    orig = rd._SshBackend
    orig_replace = os.replace
    rd._SshBackend = lambda t, c: FakeBackend(node)
    if replace_fails:
        def bad_replace(src, dst):
            if os.path.normpath(str(dst)) == os.path.normpath(state_path):
                raise OSError("simulated ENOSPC/EROFS on state persist")
            return orig_replace(src, dst)
        os.replace = bad_replace
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out):
            rc = rd.main(list(argv))
    finally:
        rd._SshBackend = orig
        os.replace = orig_replace
    raw = out.getvalue()
    return rc, (json.loads(raw) if raw.strip() else {}), raw


def seed(state_path, obj):
    with open(state_path, "w") as fh:
        json.dump(obj, fh)
    return state_path


def p4a():
    """4.1 atomic write protocol: tmp+fsync+replace, no litter."""
    p = os.path.join(SCRATCH, "s4a.json")
    fsync_n, replace_n, opens = [], [], []
    orig_fsync, orig_replace, orig_open = os.fsync, os.replace, open

    class SpyFH:
        def __init__(self, fh):
            self._fh = fh
        def __getattr__(self, n):
            return getattr(self._fh, n)
        def fileno(self):
            return self._fh.fileno()

    def spy_open(path, *a, **k):
        fh = orig_open(path, *a, **k)
        opens.append(str(path))
        return fh

    os.fsync = lambda fd: fsync_n.append(fd)
    def spy_replace(src, dst):
        replace_n.append((str(src), str(dst)))
        return orig_replace(src, dst)
    os.replace = spy_replace
    builtins_open = __builtins__["open"] if isinstance(__builtins__, dict) else __builtins__.open
    import builtins as _b
    _b.open = spy_open
    try:
        ret = rd.save_state(p, {"ts": 1, "delisted": False,
                                "snapshot": {"zai": 10.0}})
    finally:
        os.fsync, os.replace, _b.open = orig_fsync, orig_replace, orig_open
    litter = [f for f in os.listdir(SCRATCH) if f.startswith(".") and f.endswith(".tmp")]
    record("4a_atomic_save_protocol", ret is True and len(fsync_n) == 1 and
           len(replace_n) == 1 and litter == [],
           f"ret={ret} fsync_calls={len(fsync_n)} replace_calls={len(replace_n)} litter={litter}")


def p4b():
    """4.2 silent persist failure: rc 0 + confirmed true while disk stale."""
    p = os.path.join(SCRATCH, "s4b.json")
    seed(p, {"ts": 1, "delisted": False, "snapshot": {"zai\x1f1h": 10.0},
             "consecutive_failures": 2})
    before = open(p, "rb").read()
    node = FakeNode(advertised=["a", "b"])
    rc, out, _ = run_main(["--state", p, "--override", os.path.join(SCRATCH, "nope"),
                           "--manual"], node, p, replace_fails=True)
    after = open(p, "rb").read()
    record("4b_silent_persist_failure",
           rc == 0 and out.get("confirmed") is True and out.get("action") == "delist"
           and after == before,
           f"rc={rc} action={out.get('action')} confirmed={out.get('confirmed')} "
           f"disk_unchanged={after == before} disk={json.loads(after)}")


def p4c():
    """4.3 persist failure freezes the breaker but exit 3 still fires."""
    p = os.path.join(SCRATCH, "s4c.json")
    seed(p, {"ts": 1, "delisted": False, "consecutive_failures": 2,
             "blocked": False})
    node = FakeNode(ssh_down=True)
    rcs = []
    for _ in range(4):
        rc, out, _ = run_main(["--state", p, "--override",
                               os.path.join(SCRATCH, "nope"), "--manual"],
                              node, p, replace_fails=True)
        rcs.append(rc)
    disk = json.load(open(p))
    record("4b3_persist_failure_freezes_breaker",
           rcs == [3, 3, 3, 3] and disk.get("blocked") is False
           and disk.get("consecutive_failures") == 2,
           f"rcs={rcs} disk_consecutive_failures={disk.get('consecutive_failures')} "
           f"disk_blocked={disk.get('blocked')}")


def p4d():
    """4.4 no lock: interleaved read-modify-write loses an update."""
    p = os.path.join(SCRATCH, "s4d.json")
    seed(p, {"ts": 0, "delisted": False})
    a = rd.load_state(p)
    b = rd.load_state(p)          # two runs read the same snapshot
    a = dict(a); a.update({"delisted": True, "pulled_models": ["m1", "m2"], "ts": 1})
    b = dict(b); b.update({"delisted": False, "ts": 2})
    rd.save_state(p, a)           # run A commits the delist
    rd.save_state(p, b)           # run B, armed with the stale read, clobbers it
    final = json.load(open(p))
    record("4g_interleaved_lost_update",
           final.get("delisted") is False and "pulled_models" not in final,
           f"final={final}")


def p4e():
    """4.5 no directory fsync: os.open/O_DIRECTORY absent, file-only fsync."""
    src = open(os.path.join(BOT, "routstr_delist.py")).read()
    hits = {pat: src.count(pat) for pat in ("os.open", "O_DIRECTORY", "O_DIRECTORY")}
    p = os.path.join(SCRATCH, "s4e.json")
    fds = []
    orig_fsync = os.fsync
    os.fsync = lambda fd: fds.append(fd)
    try:
        rd.save_state(p, {"ts": 1})
        real = orig_fsync  # count only; do not actually fsync this host
        stats = []
        for fd in fds:
            try:
                stats.append(os.fstat(fd))
            except OSError:
                stats.append(None)
        dirs = sum(1 for s in stats if s is not None and statmod.S_ISDIR(s.st_mode))
    finally:
        os.fsync = orig_fsync
    record("4h_no_directory_fsync",
           hits["os.open"] == 0 and hits["O_DIRECTORY"] == 0 and len(fds) == 1 and dirs == 0,
           f"os.open={hits['os.open']} O_DIRECTORY={hits['O_DIRECTORY']} "
           f"fsync_calls={len(fds)} dir_fsyncs={dirs}")


def p4f():
    """4.6 re-delist MERGES pulled_models, never clobbers."""
    p = os.path.join(SCRATCH, "s4f.json")
    seed(p, {"ts": 1, "delisted": True, "pulled_models": ["m1", "m2"],
             "snapshot": {}})
    node = FakeNode(advertised=[])          # nothing advertised now
    rc, out, _ = run_main(["--state", p, "--override",
                           os.path.join(SCRATCH, "nope"), "--delist"], node, p)
    st = json.load(open(p))
    record("4c_redelist_merge",
           rc == 0 and out.get("pulled") == [] and st.get("pulled_models") == ["m1", "m2"],
           f"rc={rc} pulled={out.get('pulled')} pulled_models={st.get('pulled_models')}")


def p4g():
    """4.7 no-names relist refuses before any remote round-trip."""
    p = os.path.join(SCRATCH, "s4g.json")
    seed(p, {"ts": 1, "delisted": True})     # legacy state, no pulled_models
    node = FakeNode()
    rc, out, _ = run_main(["--state", p, "--override",
                           os.path.join(SCRATCH, "nope"), "--relist"], node, p)
    record("4d_relist_refused",
           rc == 1 and out.get("action") == "relist_refused" and node.calls == [],
           f"rc={rc} action={out.get('action')} calls={node.calls}")


def p4h():
    """4.8 a FAILED relist does not tick the breaker."""
    p = os.path.join(SCRATCH, "s4h.json")
    seed(p, {"ts": 1, "delisted": True, "pulled_models": ["m1"],
             "consecutive_failures": 2, "blocked": False})
    node = FakeNode(relist_fail=True)
    rc, out, _ = run_main(["--state", p, "--override",
                           os.path.join(SCRATCH, "nope"), "--relist"], node, p)
    st = json.load(open(p))
    record("4e_failed_relist_no_breaker_tick",
           rc == 1 and out.get("action") == "relist_failed"
           and st.get("consecutive_failures") == 2,
           f"rc={rc} action={out.get('action')} "
           f"consecutive_failures={st.get('consecutive_failures')} "
           f"blocked={st.get('blocked')}")


def p4i():
    """4.9 bool is an int: a `true` counter is accepted and increments."""
    p = os.path.join(SCRATCH, "s4i.json")
    seed(p, {"ts": 1, "delisted": False, "consecutive_failures": True})
    node = FakeNode(ssh_down=True)
    rc, out, _ = run_main(["--state", p, "--override",
                           os.path.join(SCRATCH, "nope"), "--manual"], node, p)
    st = json.load(open(p))
    record("4f_bool_counter_hole",
           st.get("consecutive_failures") == 2,
           f"rc={rc} consecutive_failures={st.get('consecutive_failures')}")


def p4j():
    """4.10 blocked run refuses the nak publish too (behaviour correct)."""
    p = os.path.join(SCRATCH, "s4j.json")
    seed(p, {"ts": 1, "delisted": False, "consecutive_failures": 3,
             "blocked": True})
    nsec = os.path.join(SCRATCH, "nsec.txt")
    open(nsec, "w").write("nsec1FAKE\n")
    node = FakeNode()
    spawned = []
    orig_run = rd.subprocess.run
    rd.subprocess.run = lambda *a, **k: spawned.append(a) or None
    try:
        rc, out, _ = run_main(["--state", p, "--override",
                               os.path.join(SCRATCH, "nope"), "--manual",
                               "--nsec", nsec], node, p)
    finally:
        rd.subprocess.run = orig_run
    record("4i_blocked_refuses_publish_too",
           rc == 3 and out.get("action") == "blocked" and node.calls == []
           and spawned == [],
           f"rc={rc} action={out.get('action')} api_calls={node.calls} "
           f"spawns={len(spawned)}")


def p5a():
    """5.1 constants wired and internally consistent."""
    w, c, b, s, m = (rd.TRIGGER_ACTION_WINDOW_S, rd.POLL_CADENCE_S,
                     rd.ACTION_BUDGET_S, rd.SSH_TIMEOUT_S, rd.MAX_PULL_ATTEMPTS)
    record("5a_constants_arithmetic",
           w == 300 and c == 240 and b == 60 and s == 30 and m == 2
           and c + b == w and 2 * s <= b,
           f"window={w} cadence={c} budget={b} ssh={s} max_attempts={m}")


def p5b():
    """5.2 expired deadline refuses WITHOUT spawning; live call is clamped."""
    spawns = []
    orig_run = rd.subprocess.run
    rd.subprocess.run = lambda argv, **k: spawns.append(k.get("timeout")) or type(
        "P", (), {"returncode": 0, "stdout": '{"ok":true,"pulled":[]}',
                  "stderr": ""})()
    try:
        be = rd._SshBackend("h", "c")
        expired = be._run("payload", dry_run=False, action="pull",
                          deadline=time.monotonic() - 1)
        t0 = time.monotonic()
        dl = t0 + 5.0
        live = be._run("payload", dry_run=False, action="pull", deadline=dl)
    finally:
        rd.subprocess.run = orig_run
    record("5b_budget_exhausted_no_spawn",
           expired.get("ok") is False and "budget exhausted" in expired.get("error", "")
           and len(spawns) == 1 and spawns[0] <= rd.SSH_TIMEOUT_S and spawns[0] < 5.0,
           f"expired={expired.get('error')} spawns={spawns} (expired spawned nothing, "
           f"live clamped to {spawns[0] if spawns else None})")


def p5c():
    """5.3 cadence arithmetic: */4 is exactly at the window boundary."""
    w, b = rd.TRIGGER_ACTION_WINDOW_S, rd.ACTION_BUDGET_S
    out = {}
    for label, cad in (("*/4", 240), ("*/5", 300), ("*/2", 120)):
        out[label] = f"worst={cad + b}s slack={w - (cad + b)}s"
    ok = (240 + b == w) and (300 + b > w) and (120 + b < w)
    record("5c_cadence_arithmetic", ok, json.dumps(out))


def p5d():
    """5.6 the nak publish carries the full timeout, outside the deadline."""
    p = os.path.join(SCRATCH, "s5d.json")
    seed(p, {"ts": 1, "delisted": False})
    nsec = os.path.join(SCRATCH, "nsec2.txt")
    open(nsec, "w").write("nsec1FAKE\n")
    node = FakeNode(advertised=["m1"])
    timeouts = []
    orig_run = rd.subprocess.run
    def spy(argv, **k):
        timeouts.append(k.get("timeout"))
        return type("P", (), {"returncode": 0, "stdout": "", "stderr": ""})()
    rd.subprocess.run = spy
    try:
        rc, out, _ = run_main(["--state", p, "--override",
                               os.path.join(SCRATCH, "nope"), "--manual",
                               "--nsec", nsec], node, p)
    finally:
        rd.subprocess.run = orig_run
    record("5d_publish_timeout_unclamped",
           rc == 0 and out.get("confirmed") is True
           and timeouts == [30],
           f"rc={rc} confirmed={out.get('confirmed')} publish_timeouts={timeouts} "
           f"budget={rd.ACTION_BUDGET_S}")


def p5e():
    """5.5 save_state's fsync is real and un-clamped (bounded by alarm)."""
    p = os.path.join(SCRATCH, "s5e.json")
    hits = []
    orig_fsync = os.fsync
    def counted(fd):
        hits.append(fd)
        return orig_fsync(fd)
    os.fsync = counted

    def bail(signum, frame):
        raise TimeoutError("fsync stalled")
    signal.signal(signal.SIGALRM, bail)
    signal.alarm(8)
    try:
        ret = rd.save_state(p, {"ts": 1, "delisted": True})
        note = "completed"
        err = None
    except Exception as exc:
        ret, note, err = None, "TIMED_OUT/raised", str(exc)
    finally:
        signal.alarm(0)
        os.fsync = orig_fsync
    record("5f_local_fsync_unclamped",
           ret is True and len(hits) == 1,
           f"ret={ret} real_fsync_calls={len(hits)} note={note} err={err}")


def main():
    for fn in (p4a, p4b, p4c, p4d, p4e, p4f, p4g, p4h, p4i, p4j,
               p5a, p5b, p5c, p5d, p5e):
        try:
            fn()
        except Exception as exc:
            record(fn.__name__, False, f"EXC {type(exc).__name__}: {exc}")
    npass = sum(1 for _, ok, _ in RESULTS if ok)
    print(f"\nTOTAL {npass}/{len(RESULTS)} probes PASS")
    return 0 if npass == len(RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
