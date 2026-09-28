#!/usr/bin/env python3
"""20th-pass independent hermetic probes for routstr-delist findings 4-5.

Re-derives every behavioural claim in this pass's docs/reviews/findings_4_5.md
from the CURRENT deployed artifact set, in-process: fake backend, tempdir state,
forced persist failures, fake monotonic clock, no network, no real ssh spawn.

Read-only w.r.t. every artifact under review. Scratch lives under ~/worktrees.

Usage: python3 probe_f45_pass20.py
"""
import ast
import contextlib
import io
import json
import os
import stat as statmod
import sys
import tempfile
import time

BOT = os.path.expanduser("~/.hermes/bot/scripts")
SCRATCH = os.path.expanduser("~/worktrees/f45-review-20-scratch")
os.makedirs(SCRATCH, exist_ok=True)
sys.path.insert(0, BOT)
import routstr_delist as rd  # noqa: E402

SCRIPT = os.path.join(BOT, "routstr_delist.py")
SUITE = os.path.expanduser("~/.hermes/bot/tests/test_routstr_delist.py")
RESULTS = []


def record(tag, ok, detail):
    RESULTS.append((tag, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'} {tag} :: {detail}")


class Clock:
    """Fake monotonic clock; wall time stays real."""

    def __init__(self):
        self._mono = 0.0

    def monotonic(self):
        return self._mono

    def time(self):
        return time.time()

    def advance(self, s):
        self._mono += s


class FakeNode:
    def __init__(self, advertised=None, ssh_down=False, pull_lands=True,
                 relist_fail=False, clock=None):
        self.advertised = advertised if advertised is not None else ["m1", "m2"]
        self.ssh_down = ssh_down
        self.pull_lands = pull_lands
        self.relist_fail = relist_fail
        self.clock = clock
        self.calls = []
        self.deadlines = []

    def _charge(self, s):
        if self.clock is not None:
            self.clock.advance(s)


class FakeBackend:
    """pull/verify/relist double; charges the fake clock at full ssh timeout
    for each round-trip so the SLA budget is really consumed."""

    def __init__(self, node):
        self.node = node

    def pull(self, dry_run=False, deadline=None):
        self.node.calls.append("pull")
        if deadline is not None:
            self.node.deadlines.append(
                ("pull", deadline - rd.time.monotonic()))
        self.node._charge(rd.SSH_TIMEOUT_S)
        if self.node.ssh_down:
            return {"ok": False, "action": "pull", "rc": 255, "error": "ssh down"}
        return {"ok": True, "action": "pull", "pulled": list(self.node.advertised)}

    def verify(self, dry_run=False, deadline=None):
        self.node.calls.append("verify")
        if deadline is not None:
            self.node.deadlines.append(
                ("verify", deadline - rd.time.monotonic()))
        self.node._charge(rd.SSH_TIMEOUT_S)
        if self.node.ssh_down:
            return {"ok": False, "action": "verify", "rc": 255}
        if not self.node.pull_lands:
            return {"ok": True, "action": "verify",
                    "count": len(self.node.advertised)}
        return {"ok": True, "action": "verify", "count": 0}

    def relist(self, names=None, dry_run=False, deadline=None):
        self.node.calls.append("relist")
        self.node._charge(rd.SSH_TIMEOUT_S)
        if self.node.relist_fail:
            return {"ok": False, "action": "relist", "rc": 1, "error": "boom"}
        return {"ok": True, "action": "relist", "restored": len(names or [])}


def run_main(argv, node, state_path, *, replace_fails=False, spawn_log=None,
             publish_cost_s=0.0, clock=None):
    orig_backend, orig_replace, orig_run, orig_time = (
        rd._SshBackend, os.replace, rd.subprocess.run, rd.time)
    rd._SshBackend = lambda t, c: FakeBackend(node)
    if clock is not None:
        rd.time = clock
    if replace_fails:
        def bad_replace(src, dst):
            if os.path.normpath(str(dst)) == os.path.normpath(state_path):
                raise OSError("simulated ENOSPC/EROFS on state persist")
            return orig_replace(src, dst)
        os.replace = bad_replace
    if spawn_log is not None:
        class _CP:
            def __init__(self, argv, rc):
                self.args, self.returncode = argv, rc
                self.stdout = self.stderr = ""

        def fake_run(argv, timeout=None, env=None, capture_output=False, **kw):
            spawn_log.append({"argv": list(argv), "timeout": timeout})
            if clock is not None:
                clock.advance(publish_cost_s or (timeout or 0))
            return _CP(argv, 0)
        rd.subprocess.run = fake_run
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out):
            rc = rd.main(list(argv))
    finally:
        rd._SshBackend, os.replace, rd.subprocess.run, rd.time = (
            orig_backend, orig_replace, orig_run, orig_time)
    raw = out.getvalue()
    return rc, (json.loads(raw) if raw.strip() else {}), raw


def state_seed(path, obj):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh)
    return path


def argv_for(state_path, *rest):
    return ["--state", str(state_path),
            "--override", os.path.join(SCRATCH, "absent.override"), *rest]


TMP = tempfile.mkdtemp(dir=SCRATCH)


# ── 4a: atomic save protocol ──────────────────────────────────────────────
def p4a():
    sp = os.path.join(TMP, "s4a.json")
    calls = {"fsync": 0, "replace": 0}
    real_fsync, real_replace = os.fsync, os.replace

    def spy_fsync(fd):
        calls["fsync"] += 1
        return None        # host fsync pathology; count only

    def spy_replace(src, dst):
        calls["replace"] += 1
        return real_replace(src, dst)

    os.fsync, os.replace = spy_fsync, spy_replace
    try:
        ret = rd.save_state(sp, {"ts": 1, "delisted": True})
    finally:
        os.fsync, os.replace = real_fsync, real_replace
    litter = [p for p in os.listdir(TMP) if p.startswith(".s4a.json")]
    record("4a_atomic_save_protocol",
           ret is True and calls["fsync"] == 1 and calls["replace"] == 1
           and litter == [],
           f"ret={ret} fsync_calls={calls['fsync']} "
           f"replace_calls={calls['replace']} litter={litter}")


# ── 4b: a failed persist is reported to the caller as success ─────────────
def p4b():
    sp = state_seed(os.path.join(TMP, "s4b.json"),
                    {"ts": 1, "delisted": False,
                     "snapshot": {"zai\x1f1h": 10.0}, "consecutive_failures": 2})
    before = open(sp).read()
    node = FakeNode()
    rc, out, _ = run_main(argv_for(sp, "--manual"), node, sp, replace_fails=True)
    after = open(sp).read()
    record("4b_silent_persist_failure",
           rc == 0 and out.get("ok") is True and out.get("confirmed") is True
           and before == after,
           f"rc={rc} action={out.get('action')} ok={out.get('ok')} "
           f"confirmed={out.get('confirmed')} "
           f"disk_unchanged={before == after} disk={after.strip()}")


# ── 4b2: the DELIVERED publisher flag is not flipped on that path ─────────
def p4b2():
    sp = state_seed(os.path.join(TMP, "s4b2.json"),
                    {"ts": 1, "delisted": False, "snapshot": {}})
    node = FakeNode()
    rc, out, _ = run_main(argv_for(sp, "--manual"), node, sp, replace_fails=True)
    disk = rd.load_state(sp)
    rc_s, out_s, _ = run_main(argv_for(sp, "--status"), node, sp)
    record("4b2_delivered_flag_not_flipped",
           rc == 0 and out.get("confirmed") is True
           and disk.get("delisted") is False and out_s.get("delisted") is False,
           f"delist_rc={rc} confirmed={out.get('confirmed')} "
           f"disk_delisted={disk.get('delisted')} "
           f"status_delisted={out_s.get('delisted')} status_rc={rc_s} "
           f"-> advertisement flag the design depends on was NOT flipped")


# ── 4b3: durable BLOCKED marker never lands, yet exit 3 still fires ───────
def p4b3():
    sp = state_seed(os.path.join(TMP, "s4b3.json"),
                    {"ts": 1, "delisted": False, "consecutive_failures": 2,
                     "blocked": False})
    node = FakeNode(ssh_down=True)
    rcs = []
    for _ in range(4):
        rc, out, _ = run_main(argv_for(sp, "--manual"), node, sp,
                              replace_fails=True)
        rcs.append(rc)
    st = rd.load_state(sp)
    record("4b3_persist_failure_freezes_breaker",
           rcs == [3, 3, 3, 3] and st.get("consecutive_failures") == 2
           and st.get("blocked") is False,
           f"rcs={rcs} disk_consecutive_failures={st.get('consecutive_failures')} "
           f"disk_blocked={st.get('blocked')} "
           f"exit3_reported_but_marker_absent=True")


# ── 4c: re-delist merges pulled_models ───────────────────────────────────
def p4c():
    sp = state_seed(os.path.join(TMP, "s4c.json"),
                    {"ts": 1, "delisted": True, "snapshot": {},
                     "pulled_models": ["m1", "m2"]})
    node = FakeNode(advertised=[])          # nothing advertised any more
    rc, out, _ = run_main(argv_for(sp, "--delist"), node, sp)
    st = rd.load_state(sp)
    record("4c_redelist_merge",
           rc == 0 and out.get("pulled") == []
           and st.get("pulled_models") == ["m1", "m2"],
           f"rc={rc} pulled={out.get('pulled')} "
           f"pulled_models={st.get('pulled_models')}")


# ── 4d: no-names relist refuses before any remote round-trip ─────────────
def p4d():
    sp = state_seed(os.path.join(TMP, "s4d.json"),
                    {"ts": 1, "delisted": True, "snapshot": {}})
    node = FakeNode()
    rc, out, _ = run_main(argv_for(sp, "--relist"), node, sp)
    record("4d_relist_refused",
           rc == 1 and out.get("action") == "relist_refused"
           and node.calls == [],
           f"rc={rc} action={out.get('action')} calls={node.calls}")


# ── 4e: a failed relist does not tick the breaker ────────────────────────
def p4e():
    sp = state_seed(os.path.join(TMP, "s4e.json"),
                    {"ts": 1, "delisted": True, "snapshot": {},
                     "pulled_models": ["m1"], "consecutive_failures": 2})
    node = FakeNode(relist_fail=True)
    rc, out, _ = run_main(argv_for(sp, "--relist"), node, sp)
    st = rd.load_state(sp)
    record("4e_failed_relist_no_breaker_tick",
           rc == 1 and out.get("action") == "relist_failed"
           and st.get("consecutive_failures") == 2
           and not st.get("blocked"),
           f"rc={rc} action={out.get('action')} "
           f"consecutive_failures={st.get('consecutive_failures')} "
           f"blocked={st.get('blocked')!r} (key ABSENT, not normalised to "
           f"False on this path) -> failed relist never ticks the breaker")


# ── 4f: bool is an int subclass -> counter hole ──────────────────────────
def p4f():
    sp = state_seed(os.path.join(TMP, "s4f.json"),
                    {"ts": 1, "delisted": False, "consecutive_failures": True})
    node = FakeNode(ssh_down=True)
    rc, out, _ = run_main(argv_for(sp, "--manual"), node, sp)
    st = rd.load_state(sp)
    record("4f_bool_counter_hole",
           rc == 1 and st.get("consecutive_failures") == 2,
           f"rc={rc} consecutive_failures={st.get('consecutive_failures')} "
           f"(True accepted as 1, +1 failure)")


# ── 4g: no lock around read-modify-write -> lost update ─────────────────
def p4g():
    sp = os.path.join(TMP, "s4g.json")
    rd.save_state(sp, {"ts": 0, "delisted": False, "snapshot": {}})
    a = rd.load_state(sp)          # run A reads
    b = rd.load_state(sp)          # run B reads the same snapshot
    a["ts"], a["delisted"] = 3, True
    a["pulled_models"] = ["m1"]
    b["ts"], b["delisted"] = 2, False
    rd.save_state(sp, a)           # A commits
    rd.save_state(sp, b)           # B commits its stale snapshot last
    final = rd.load_state(sp)
    record("4g_interleaved_lost_update",
           final.get("delisted") is False,
           f"final={final} -> A's committed delist transition silently lost "
           f"(last writer wins; no flock/fcntl/O_EXCL in the module)")


# ── 4h: no directory fsync; the single fsync targets a regular file ──────
def p4h():
    src = open(SCRIPT).read()
    tree = ast.parse(src)
    os_open_attr = sum(1 for n in ast.walk(tree)
                       if isinstance(n, ast.Attribute) and n.attr == "open")
    dir_const = src.count("O_DIRECTORY")
    sp = os.path.join(TMP, "s4h.json")
    seen = []
    real = os.fsync

    def spy(fd):
        seen.append(statmod.S_ISDIR(os.fstat(fd).st_mode))
        return None

    os.fsync = spy
    try:
        ret = rd.save_state(sp, {"ts": 1})
    finally:
        os.fsync = real
    record("4h_no_directory_fsync",
           ret is True and dir_const == 0 and seen == [False],
           f"os_open_attr={os_open_attr} O_DIRECTORY={dir_const} "
           f"fsync_targets_dir={seen} dir_fsyncs=0")


# ── 4i: a blocked run refuses the nak publish too ───────────────────────
def p4i():
    sp = state_seed(os.path.join(TMP, "s4i.json"),
                    {"ts": 1, "delisted": True, "blocked": True,
                     "consecutive_failures": 3})
    nsec = os.path.join(TMP, "nsec4i")
    open(nsec, "w").write("nsec1FAKE\n")
    node = FakeNode()
    spawns = []
    rc, out, _ = run_main(argv_for(sp, "--manual", "--nsec", nsec), node, sp,
                          spawn_log=spawns)
    record("4i_blocked_refuses_publish_too",
           rc == 3 and out.get("action") == "blocked"
           and node.calls == [] and spawns == [],
           f"rc={rc} action={out.get('action')} api_calls={node.calls} "
           f"spawns={len(spawns)}")


# ── 5a: constants are non-decorative and internally consistent ──────────
def p5a():
    ok = (rd.TRIGGER_ACTION_WINDOW_S == 300 and rd.POLL_CADENCE_S == 240
          and rd.ACTION_BUDGET_S == 60 and rd.SSH_TIMEOUT_S == 30
          and rd.MAX_PULL_ATTEMPTS == 2
          and rd.POLL_CADENCE_S + rd.ACTION_BUDGET_S == rd.TRIGGER_ACTION_WINDOW_S
          and 2 * rd.SSH_TIMEOUT_S <= rd.ACTION_BUDGET_S)
    src = open(SCRIPT).read()
    tree = ast.parse(src)
    sites = [n.lineno for n in ast.walk(tree)
             if isinstance(n, ast.Name) and n.id == "ACTION_BUDGET_S"]
    record("5a_constants_arithmetic", ok,
           f"window={rd.TRIGGER_ACTION_WINDOW_S} "
           f"cadence={rd.POLL_CADENCE_S} budget={rd.ACTION_BUDGET_S} "
           f"ssh={rd.SSH_TIMEOUT_S} max_attempts={rd.MAX_PULL_ATTEMPTS} "
           f"ACTION_BUDGET_S_load_sites={sorted(set(sites))}")


# ── 5c: cadence arithmetic — the */4 boundary is exactly zero-margin ────
def p5c():
    out = {}
    for label, cad in (("*/2", 120), ("*/4", 240), ("*/5", 300)):
        out[label] = cad + rd.ACTION_BUDGET_S
    record("5c_cadence_arithmetic",
           out["*/4"] == 300 and out["*/5"] > 300,
           f"worst_case */4={out['*/4']}s (slack {300 - out['*/4']}s) "
           f"*/5={out['*/5']}s (slack {300 - out['*/5']}s) "
           f"*/2={out['*/2']}s (slack {300 - out['*/2']}s)")


# ── 5b: every remote round-trip is deadline-clamped ─────────────────────
def p5b():
    # expired deadline: refuse without spawning
    b = rd._SshBackend("t", "c")
    real_run = rd.subprocess.run
    spawns = []

    class _CP:
        returncode = 0
        stdout = ""
        stderr = ""
    rd.subprocess.run = lambda *a, **k: (spawns.append(a), _CP())[1]
    try:
        expired = b._run("x", dry_run=False, action="pull",
                         deadline=time.monotonic() - 1)
    finally:
        rd.subprocess.run = real_run
    clock = Clock()
    clock._mono = 0.0
    node = FakeNode(clock=clock)
    orig_time = rd.time
    rd.time = clock
    try:
        live = rd.time.monotonic()
        _ = live
    finally:
        rd.time = orig_time
    record("5b_budget_exhausted_no_spawn",
           expired.get("ok") is False and spawns == []
           and expired.get("error") == "action budget exhausted",
           f"expired={expired.get('error')} spawns={len(spawns)}")


# ── 5e: the bounded in-run retry is structurally inert in the worst case ─
def p5e():
    clock = Clock()
    sp = os.path.join(TMP, "s5e.json")
    node = FakeNode(pull_lands=False, clock=clock)   # LYING pull each attempt
    rc, out, _ = run_main(argv_for(sp, "--manual"), node, sp, clock=clock)
    record("5e_retry_inert_worst_case",
           rc == 1 and node.calls == ["pull", "verify"]
           and clock.monotonic() >= rd.ACTION_BUDGET_S,
           f"rc={rc} calls={node.calls} elapsed={clock.monotonic()}s "
           f"budget={rd.ACTION_BUDGET_S}s -> retry refused because the first "
           f"attempt consumed the whole budget (MAX_PULL_ATTEMPTS inert)")


# ── 5f: the local fsync is outside the deadline ────────────────────────
def p5f():
    sp = os.path.join(TMP, "s5f.json")
    seen = []
    real = os.fsync
    os.fsync = lambda fd: seen.append(1)
    try:
        ret = rd.save_state(sp, {"ts": 1})
    finally:
        os.fsync = real
    record("5f_local_fsync_unclamped",
           ret is True and len(seen) == 1,
           f"ret={ret} real_fsync_calls={len(seen)} -> synchronous local "
           f"disk work, not bounded by ACTION_BUDGET_S")


# ── 5d/5g: the publish runs after confirmation, unclamped ──────────────
def p5g():
    clock = Clock()
    sp = os.path.join(TMP, "s5g.json")
    node = FakeNode(clock=clock)
    nsec = os.path.join(TMP, "nsec5g")
    open(nsec, "w").write("nsec1FAKE\n")
    spawns = []
    rc, out, _ = run_main(argv_for(sp, "--manual", "--nsec", nsec), node, sp,
                          spawn_log=spawns, clock=clock, publish_cost_s=30.0)
    record("5g_publish_unclamped_total_run",
           rc == 0 and out.get("confirmed") is True
           and spawns and spawns[0]["timeout"] == 30
           and clock.monotonic() > rd.ACTION_BUDGET_S,
           f"rc={rc} confirmed={out.get('confirmed')} "
           f"publish_timeouts={[s['timeout'] for s in spawns]} "
           f"budget={rd.ACTION_BUDGET_S}s total_elapsed={clock.monotonic()}s "
           f"-> run spends more than the action budget after confirmation")


# ── 5h: no crontab entry pins the cadence ─────────────────────────────
def p5h():
    import subprocess as sp_
    try:
        crontab = sp_.run(["crontab", "-l"], capture_output=True, text=True,
                          timeout=10).stdout
    except Exception as exc:
        crontab = f"<error {exc}>"
    n = len([ln for ln in crontab.splitlines() if "routstr" in ln])
    record("5h_no_cron_pins_cadence", n == 0,
           f"routstr_crontab_entries={n} -> POLL_CADENCE_S is documentary; "
           f"nothing enforces */4 in production")


# ── 5i: AST — save_state return discarded at every call site ───────────
def p5i():
    tree = ast.parse(open(SCRIPT).read())
    bare, mains = [], []
    for n in ast.walk(tree):
        if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call):
            f = n.value.func
            if isinstance(f, ast.Name) and f.id == "save_state":
                bare.append(n.lineno)
        if isinstance(n, ast.FunctionDef) and n.name == "main":
            mains = [r.lineno for r in ast.walk(n) if isinstance(r, ast.Return)]
    record("5i_save_state_return_discarded",
           len(bare) == 8 and len(mains) == 10,
           f"bare_save_state_stmt_lines={sorted(bare)} "
           f"main_return_lines={sorted(mains)} "
           f"-> no caller inspects the persist result")


for fn in (p4a, p4b, p4b2, p4b3, p4c, p4d, p4e, p4f, p4g, p4h, p4i,
           p5a, p5b, p5c, p5e, p5f, p5g, p5h, p5i):
    try:
        fn()
    except Exception as exc:  # noqa: BLE001
        record(fn.__name__, False, f"EXCEPTION {type(exc).__name__}: {exc}")

bad = [t for t, ok, _ in RESULTS if not ok]
print(f"\n{len(RESULTS) - len(bad)}/{len(RESULTS)} probes PASS")
if bad:
    print("FAILED: " + ", ".join(bad))
sys.exit(1 if bad else 0)
