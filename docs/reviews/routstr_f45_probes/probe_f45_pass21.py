#!/usr/bin/env python3
"""probe_f45_pass21.py — 21st-pass hermetic re-derivation of routstr delist
findings 4 (atomicity + idempotence) and 5 (5-minute SLA arithmetic).

Drives the DEPLOYED script (~/.hermes/bot/scripts/routstr_delist.py) in
process: fake backend, fake monotonic clock, tempdir state, os.replace/fsync
fault injection. No network, no real spawn, no artifact mutation. Every
finding claim below is re-derived by execution THIS session.

Usage: python3 probe_f45_pass21.py
Exit 0 iff every probe passes.
"""
from __future__ import annotations

import ast
import contextlib
import io
import json
import os
import stat
import sys
import tempfile
import time
from pathlib import Path

BOT = Path.home() / ".hermes/bot"
SCRIPT = BOT / "scripts" / "routstr_delist.py"
SUITE = BOT / "tests" / "test_routstr_delist.py"
DOC = BOT / "docs" / "routstr-delist.md"

sys.path.insert(0, str(BOT / "scripts"))
import routstr_delist as rd  # noqa: E402

RESULTS: list[tuple[str, bool, str]] = []


def check(label, ok, detail=""):
    RESULTS.append((label, bool(ok), str(detail)))
    print(f"[{'PASS' if ok else 'FAIL'}] {label} :: {detail}", flush=True)
    return bool(ok)


# ── fake clock / backend ──────────────────────────────────────────────────
class FakeClock:
    def __init__(self):
        self._m = 0.0

    def monotonic(self):
        return self._m

    @staticmethod
    def time():
        return time.time()

    def advance(self, s):
        self._m += s


class FakeBackend:
    """Mirrors production result shape: rc + parsed payload + ok gate."""

    def __init__(self, clock, *, mode="ok", round_trip_s=0.0, advertised=None):
        self.clock = clock
        self.mode = mode
        self.round_trip_s = round_trip_s
        self.models = dict(advertised or {"m1": 1, "m2": 1})
        self.calls: list[str] = []
        self.deadline_log: list[dict] = []
        self.names = None

    def _rt(self, kind, dry_run, deadline):
        if deadline is not None:
            rem = deadline - self.clock.monotonic()
            self.deadline_log.append({"kind": kind, "remaining": rem,
                                      "timeout": min(rd.SSH_TIMEOUT_S,
                                                     max(rem, 0.0))})
        if dry_run:
            return {"ok": True, "dry_run": True, "action": kind}
        self.calls.append(kind)
        if self.mode == "ssh_down":
            return {"ok": False, "action": kind, "rc": 255,
                    "error": "ssh: connect refused (simulated)"}
        self.clock.advance(self.round_trip_s)
        if kind == "pull":
            pulled = [k for k, v in self.models.items() if v == 1]
            if self.mode != "lying":
                for k in self.models:
                    self.models[k] = 0
            return {"action": "pull", "rc": 0, "ok": True, "pulled": pulled}
        if kind == "verify":
            enabled = sum(1 for v in self.models.values() if v == 1)
            return {"action": "verify", "rc": 0, "ok": True, "count": enabled}
        names = self.names if self.names is not None else list(self.models)
        restored = 0
        for k in self.models:
            if k in names:
                self.models[k] = 1
                restored += 1
        return {"action": "relist", "rc": 0, "ok": True, "restored": restored}

    def pull(self, dry_run=False, deadline=None):
        return self._rt("pull", dry_run, deadline)

    def verify(self, dry_run=False, deadline=None):
        return self._rt("verify", dry_run, deadline)

    def relist(self, names=None, dry_run=False, deadline=None):
        self.names = list(names or [])
        return self._rt("relist", dry_run, deadline)


def run(backend, clock, state, *argv, override=None):
    """Invoke the deployed main() with a fake backend + fake clock."""
    prev_backend = rd._SshBackend
    rd._SshBackend = lambda t, c: backend
    old_time = rd.time
    rd.time = clock
    ov = override or (state.parent / "no.override")
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out):
            rc = rd.main(["--state", str(state), "--override", str(ov),
                          *[str(a) for a in argv]])
    finally:
        rd.time = old_time
        rd._SshBackend = prev_backend
    raw = out.getvalue()
    return rc, (json.loads(raw) if raw.strip() else {}), raw


def tmp_state(root, name="state.json", seed=None):
    p = root / name
    if seed is not None:
        p.write_text(json.dumps(seed))
    return p


def force_replace_failure(enable):
    """Make os.replace raise for STATE paths only."""
    real = os.replace

    def maybe_fail(src, dst, *a, **kw):
        if enable["on"] and str(dst).endswith("state.json"):
            raise OSError("simulated persist failure (ENOSPC/EROFS)")
        return real(src, dst, *a, **kw)

    os.replace = maybe_fail
    return real


def main():  # noqa: C901
    # scratch OFF /tmp (policy: /tmp is tmpfs; keep probe state on disk)
    scratch = Path.home() / "worktrees" / ".f45p21-scratch"
    scratch.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="f45p21-", dir=str(scratch)))
    clock = FakeClock()

    # ── artifact integrity ──────────────────────────────────────────────
    import hashlib

    def md5(p):
        return hashlib.md5(Path(p).read_bytes()).hexdigest()

    check("artifacts present", SCRIPT.is_file() and SUITE.is_file()
          and DOC.is_file(), f"script={SCRIPT.is_file()} suite={SUITE.is_file()}"
          f" doc={DOC.is_file()}")
    check("contract doc MISSING at bot path (HIGH artifact defect)",
          not (BOT / "docs" / "routstr_delist_contract.md").exists(),
          f"{BOT}/docs/routstr_delist_contract.md ENOENT")
    n_src = len(SCRIPT.read_text().splitlines())
    check("script line count == 829", n_src == 829, f"lines={n_src} md5={md5(SCRIPT)}")
    check("suite line count == 752", len(SUITE.read_text().splitlines()) == 752,
          f"lines={len(SUITE.read_text().splitlines())} md5={md5(SUITE)}")
    check("doc line count == 197", len(DOC.read_text().splitlines()) == 197,
          f"lines={len(DOC.read_text().splitlines())} md5={md5(DOC)}")

    ast_tree = ast.parse(SCRIPT.read_text())

    # ── FINDING 4 — atomicity ───────────────────────────────────────────
    # 4a: atomic save protocol (tmp + fsync + replace + no litter).
    st = tmp_state(root, "a_state.json")
    fsyncs, replaces = [], []
    real_fsync, real_replace = os.fsync, os.replace
    os.fsync = lambda fd: fsyncs.append(fd)
    real_r = os.replace

    def spy_replace(src, dst, *a, **kw):
        replaces.append((Path(src), Path(dst), Path(dst).read_bytes() if Path(dst).exists() else None))
        return real_r(src, dst, *a, **kw)

    os.replace = spy_replace
    try:
        ret = rd.save_state(str(st), {"ts": 1, "delisted": True})
    finally:
        os.fsync, os.replace = real_fsync, real_replace
    litter = list(root.glob(".*.tmp"))
    check("4a atomic protocol: ret=True, 1 fsync, 1 replace, no litter",
          ret is True and len(fsyncs) == 1 and len(replaces) == 1 and litter == [],
          f"ret={ret} fsync_calls={len(fsyncs)} replace_calls={len(replaces)} "
          f"litter={[p.name for p in litter]}")

    # AST: every save_state(...) call site in main() is a bare expression.
    bare, assigned = [], []
    for node in ast.walk(ast_tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            f = node.value.func
            if isinstance(f, ast.Name) and f.id == "save_state":
                bare.append(node.lineno)
        if isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
            v = getattr(node, "value", None)
            if isinstance(v, ast.Call) and isinstance(v.func, ast.Name) \
                    and v.func.id == "save_state":
                assigned.append(node.lineno)
    check("4.2 AST: 8 bare save_state call sites, 0 return-value uses",
          len(bare) == 8 and assigned == [],
          f"bare={bare} assigned={assigned}")

    # 4b: silent persist failure → rc 0 / confirmed true / disk stale.
    enable = {"on": True}
    real = force_replace_failure(enable)
    try:
        st = tmp_state(root, "b_state.json",
                       {"ts": 1, "delisted": False,
                        "snapshot": {"zai\x1f1h": 10.0}, "consecutive_failures": 2})
        before = st.read_bytes()
        b = FakeBackend(clock)
        rc, out, _ = run(b, clock, st, "--manual")
        unchanged = st.read_bytes() == before
    finally:
        os.replace = real
        enable["on"] = False
    check("4b silent persist failure: rc0/ok/confirmed while disk bit-identical",
          rc == 0 and out.get("ok") is True and out.get("confirmed") is True
          and unchanged,
          f"rc={rc} action={out.get('action')} ok={out.get('ok')} "
          f"confirmed={out.get('confirmed')} disk_unchanged={unchanged}")
    check("4b2 delivered flag never flipped despite successful pull",
          json.loads(before).get("delisted") is False
          and st.read_text() == before.decode(),
          f"disk_delisted={json.loads(before).get('delisted')}")

    # 4b3: persist failure freezes the breaker yet exit 3 still fires.
    enable = {"on": True}
    real = force_replace_failure(enable)
    try:
        st = tmp_state(root, "c_state.json",
                       {"ts": 1, "delisted": False, "consecutive_failures": 2,
                        "blocked": False})
        rcs = []
        for _ in range(4):
            bb = FakeBackend(clock, mode="ssh_down")
            r, _, _ = run(bb, clock, st, "--manual")
            rcs.append(r)
        disk = json.loads(st.read_text())
    finally:
        os.replace = real
        enable["on"] = False
    check("4b3 persist failure: 4x exit3 + in-process blocked, durable marker absent",
          rcs == [3, 3, 3, 3] and disk.get("consecutive_failures") == 2
          and disk.get("blocked") is False,
          f"rcs={rcs} disk_fails={disk.get('consecutive_failures')} "
          f"disk_blocked={disk.get('blocked')}")

    # 4c: re-delist merges pulled_models (no clobber).
    st = tmp_state(root, "d_state.json",
                   {"ts": 1, "delisted": True, "pulled_models": ["m1", "m2"],
                    "consecutive_failures": 0})
    bd = FakeBackend(clock, advertised={"m1": 0, "m2": 0})
    rc, out, _ = run(bd, clock, st, "--delist")
    disk = json.loads(st.read_text())
    check("4c re-delist on absent listing MERGES (no clobber)",
          rc == 0 and out.get("pulled") == []
          and disk.get("pulled_models") == ["m1", "m2"],
          f"rc={rc} pulled={out.get('pulled')} "
          f"pulled_models={disk.get('pulled_models')}")

    # 4d: no-names relist refuses, zero backend calls.
    st = tmp_state(root, "e_state.json", {"ts": 1, "delisted": True})
    bd = FakeBackend(clock)
    rc, out, _ = run(bd, clock, st, "--relist")
    check("4d relist refusal: rc1, zero backend calls",
          rc == 1 and out.get("action") == "relist_refused" and bd.calls == [],
          f"rc={rc} action={out.get('action')} calls={bd.calls}")

    # 4e: failed relist does not tick the breaker.
    st = tmp_state(root, "f_state.json",
                   {"ts": 1, "delisted": True, "pulled_models": ["m1"],
                    "consecutive_failures": 2})
    bd = FakeBackend(clock, mode="ssh_down")
    rc, out, _ = run(bd, clock, st, "--relist")
    disk = json.loads(st.read_text())
    check("4e failed relist: rc1, counter NOT ticked",
          rc == 1 and disk.get("consecutive_failures") == 2
          and "blocked" not in disk,
          f"rc={rc} action={out.get('action')} "
          f"consecutive_failures={disk.get('consecutive_failures')} "
          f"blocked_key={'blocked' in disk}")

    # 4f: bool counter hole.
    st = tmp_state(root, "g_state.json", {"ts": 1, "consecutive_failures": True})
    bd = FakeBackend(clock, mode="ssh_down")
    rc, out, _ = run(bd, clock, st, "--manual")
    disk = json.loads(st.read_text())
    check("4f bool counter hole: True accepted as 1 -> next fail = 2",
          disk.get("consecutive_failures") == 2,
          f"rc={rc} consecutive_failures={disk.get('consecutive_failures')}")

    # 4g: interleaved read-modify-write loses an update (no lock).
    p = root / "h_state.json"
    a = rd.update_state(rd.load_state(str(p)), ts=3, preds=[],
                        delisted=True, extra={"pulled_models": ["m1"]})
    bsnap = rd.load_state(str(p))                       # B reads (pre-A)
    b = rd.update_state(bsnap, ts=2, preds=[], delisted=False)
    rd.save_state(str(p), a)                            # A commits first
    rd.save_state(str(p), b)                            # B clobbers with stale view
    final = rd.load_state(str(p))
    check("4g interleaved lost update: A's commit silently gone",
          final.get("delisted") is False and final.get("ts") == 2,
          f"final={{'delisted': {final.get('delisted')}, "
          f"'ts': {final.get('ts')}}}")
    hits = 0
    for kw in ("flock", "fcntl", "lockf", "O_EXCL", "threading", "multiprocessing"):
        hits += SCRIPT.read_text().count(kw)
    check("4g2 no inter-process lock primitive anywhere in the script",
          hits == 0, f"lock-primitive hits={hits}")

    # 4h: no directory fsync (rename atomic but not crash-durable).
    st = tmp_state(root, "i_state.json")
    opens, fsync_targets = [], []
    real_open, real_fsync = os.open, os.fsync
    os.open = lambda *a, **kw: opens.append((a, kw)) or real_open(*a, **kw)

    def rec_fsync(fd):
        try:
            fsync_targets.append(stat.S_ISDIR(os.fstat(fd).st_mode))
        except Exception:
            fsync_targets.append(None)
        return None

    os.fsync = rec_fsync
    try:
        ret = rd.save_state(str(st), {"ts": 1})
    finally:
        os.open, os.fsync = real_open, real_fsync
    check("4h no directory fsync: os.open=0, only regular-file fsync",
          ret is True and opens == [] and fsync_targets == [False],
          f"os_open_calls={len(opens)} fsync_targets_dir={fsync_targets} "
          f"O_DIRECTORY_hits={SCRIPT.read_text().count('O_DIRECTORY')}")

    # ── FINDING 5 — SLA arithmetic ──────────────────────────────────────
    check("5a constants arithmetic consistent",
          rd.TRIGGER_ACTION_WINDOW_S == 300 and rd.POLL_CADENCE_S == 240
          and rd.ACTION_BUDGET_S == 60 and rd.SSH_TIMEOUT_S == 30
          and rd.MAX_PULL_ATTEMPTS == 2
          and rd.POLL_CADENCE_S + rd.ACTION_BUDGET_S == rd.TRIGGER_ACTION_WINDOW_S
          and 2 * rd.SSH_TIMEOUT_S <= rd.ACTION_BUDGET_S,
          f"window={rd.TRIGGER_ACTION_WINDOW_S} cadence={rd.POLL_CADENCE_S} "
          f"budget={rd.ACTION_BUDGET_S} ssh={rd.SSH_TIMEOUT_S} "
          f"attempts={rd.MAX_PULL_ATTEMPTS}")

    budget_load = sorted(n.lineno for n in ast.walk(ast_tree)
                         if isinstance(n, ast.Name) and n.id == "ACTION_BUDGET_S")
    check("5a2 ACTION_BUDGET_S consumed in code (not decorative)",
          budget_load == [73, 612, 667], f"load_sites={budget_load}")

    # 5b: expired budget refuses WITHOUT spawning (real _SshBackend._run).
    b = rd._SshBackend("user@host", "cont")
    spawns = []
    real_run = rd.subprocess.run
    rd.subprocess.run = lambda *a, **kw: spawns.append(a) or None
    old_clock = rd.time
    expired = FakeClock()
    expired._m = 10_000.0
    rd.time = expired
    try:
        res = b._run("payload", dry_run=False, action="pull", deadline=10_000.0)
    finally:
        rd.subprocess.run = real_run
        rd.time = old_clock
    check("5b budget exhausted -> refusal, zero spawns",
          res.get("ok") is False and "action budget exhausted" in str(res.get("error"))
          and spawns == [],
          f"error={res.get('error')!r} spawns={len(spawns)}")

    # 5c: cadence arithmetic (zero margin at */4).
    def slack(cadence):
        return rd.TRIGGER_ACTION_WINDOW_S - (cadence + rd.ACTION_BUDGET_S)

    check("5c cadence: */4 == exactly 300s (zero margin), */5 breaches",
          slack(240) == 0 and slack(300) < 0 and slack(120) > 0,
          f"slack */4={slack(240)}s slack */5={slack(300)}s slack */2={slack(120)}s")

    # 5d: no crontab entry enforces the cadence.
    import subprocess as _sp
    try:
        crontab = _sp.run(["crontab", "-l"], capture_output=True, text=True).stdout
    except Exception as exc:
        crontab = f"<error {exc}>"
    entries = [ln for ln in crontab.splitlines() if "routstr" in ln.lower()]
    check("5d no crontab entry pins the cadence to POLL_CADENCE_S",
          entries == [], f"routstr_crontab_entries={len(entries)}")

    # 5e: un-clamped real fsync is a real synchronous call outside the deadline.
    st = tmp_state(root, "j_state.json")
    real_fsync = os.fsync
    real_calls = []
    os.fsync = lambda fd: real_calls.append(fd)
    try:
        ret = rd.save_state(str(st), {"ts": 9, "delisted": True})
    finally:
        os.fsync = real_fsync
    check("5e save_state performs an un-clamped real fsync on every path",
          ret is True and len(real_calls) == 1,
          f"ret={ret} real_fsync_calls={len(real_calls)}")

    # 5f: bounded retry is opportunistic — a lying pull can eat the whole budget.
    clock5 = FakeClock()
    bd = FakeBackend(clock5, mode="lying", round_trip_s=30.0)
    st = tmp_state(root, "k_state.json", {"ts": 1, "delisted": False})
    rc, out, _ = run(bd, clock5, st, "--manual")
    check("5f retry inert worst case: 1 attempt, budget consumed",
          rc == 1 and bd.calls == ["pull", "verify"] and clock5.monotonic() == 60.0,
          f"rc={rc} calls={bd.calls} elapsed={clock5.monotonic()}s "
          f"budget={rd.ACTION_BUDGET_S}s")

    # 5g: --nsec publish runs after the success path, outside the deadline.
    clock6 = FakeClock()
    bd = FakeBackend(clock6, round_trip_s=30.0)
    st = tmp_state(root, "l_state.json", {"ts": 1, "delisted": False})
    nsec = root / "nsec"
    nsec.write_text("nsec1PROBEsecretNEVERreal\n")
    recorded = []
    real_run = rd.subprocess.run

    def fake_run(argv, timeout=None, env=None, capture_output=True, **kw):
        recorded.append({"timeout": timeout, "env_keys": sorted((env or {}).keys())})
        clock6.advance(30.0)                       # publish charges its full timeout
        return rd.subprocess.CompletedProcess(argv, 0)

    rd.subprocess.run = fake_run
    try:
        rc, out, _ = run(bd, clock6, st, "--manual", "--nsec", str(nsec))
    finally:
        rd.subprocess.run = real_run
    total = clock6.monotonic()
    check("5g publish un-clamped: run total exceeds ACTION_BUDGET_S",
          rc == 0 and out.get("confirmed") is True
          and [r["timeout"] for r in recorded] == [30]
          and total == 90.0 and total > rd.ACTION_BUDGET_S,
          f"rc={rc} confirmed={out.get('confirmed')} "
          f"publish_timeouts={[r['timeout'] for r in recorded]} "
          f"budget={rd.ACTION_BUDGET_S}s total_elapsed={total}s")

    # ── citation audit: every file:line cited in the review holds its text ──
    LINES = {
        "src": SCRIPT.read_text().splitlines(),
        "contract": SUITE.read_text().splitlines(),
        "docs": DOC.read_text().splitlines(),
    }
    CITES = [
        ("src", 221, "def save_state"),
        ("src", 230, "tmp = os.path.join"),
        ("src", 232, "json.dump"),
        ("src", 233, "fh.flush()"),
        ("src", 234, "os.fsync"),
        ("src", 235, "os.replace"),
        ("src", 237, "return True"),
        ("src", 238, "except Exception"),
        ("src", 240, "finally"),
        ("src", 244, "except OSError"),
        ("src", 248, "def update_state"),
        ("src", 251, "flag in the objects"),
        ("src", 263, 'new["delisted"] = bool(delisted)'),
        ("src", 544, "state.get(\"consecutive_failures\""),
        ("src", 545, "isinstance(fails, int)"),
        ("src", 546, 'blocked = bool(state.get("blocked"))'),
        ("src", 548, "if args.status"),
        ("src", 557, "return 0"),
        ("src", 561, "if args.unblock and blocked"),
        ("src", 565, "save_state(args.state, state)"),
        ("src", 569, "if blocked"),
        ("src", 578, "return 3"),
        ("src", 601, 'names = state.get("pulled_models")'),
        ("src", 602, "if not names and not args.relist_any"),
        ("src", 611, "return 1"),
        ("src", 612, "deadline = time.monotonic() + ACTION_BUDGET_S"),
        ("src", 613, "relist(_SshBackend"),
        ("src", 626, "if not res.get(\"ok\")"),
        ("src", 628, 'state["last_pull_error"]'),
        ("src", 632, "return 1"),
        ("src", 636, 'state["consecutive_failures"] = 0'),
        ("src", 638, "save_state(args.state, state)"),
        ("src", 667, "deadline = time.monotonic() + ACTION_BUDGET_S"),
        ("src", 671, "while attempts < MAX_PULL_ATTEMPTS"),
        ("src", 676, "time.monotonic() < deadline"),
        ("src", 683, "vres.get(\"count\") == 0"),
        ("src", 695, "time.monotonic() < deadline"),
        ("src", 724, "fails += 1"),
        ("src", 730, "newly_blocked = fails >= BREAKER_THRESHOLD"),
        ("src", 731, 'state["blocked"] = newly_blocked'),
        ("src", 732, "save_state(args.state, state)"),
        ("src", 739, "return 3 if newly_blocked else 1"),
        ("src", 744, 'prior = state.get("pulled_models") or []'),
        ("src", 746, "merged = list(prior)"),
        ("src", 750, 'state["consecutive_failures"] = 0'),
        ("src", 752, "save_state(args.state, state)"),
        ("src", 755, "if args.nsec:"),
        ("src", 756, "publish_delist_event(args.nsec, delisted=True)"),
        ("src", 71, "TRIGGER_ACTION_WINDOW_S = 300"),
        ("src", 72, "POLL_CADENCE_S = 240"),
        ("src", 73, "ACTION_BUDGET_S"),
        ("src", 74, "SSH_TIMEOUT_S = 30"),
        ("src", 75, "MAX_PULL_ATTEMPTS = 2"),
        ("src", 152, "isinstance(unc, bool)"),
        ("src", 459, "timeout=30"),
        ("src", 803, "remaining <= 0"),
        ("src", 806, "timeout = min(SSH_TIMEOUT_S, remaining)"),
        ("src", 822, 'data.get("ok") is True'),
        ("contract", 543, "def test_poll_cadence_config_satisfies_the_window"),
        ("contract", 553, "def test_trigger_sample_to_verified_delist_under_300s"),
        ("contract", 594, '"blocked": true'),
        ("contract", 601, "def test_blocked_run_refuses_all_remote_action"),
        ("contract", 628, "class TestAtomicStateWrites"),
        ("contract", 634, 'monkeypatch.setattr(os, "fsync"'),
        ("contract", 657, "rd.save_state(str(state_path), new)"),
        ("contract", 537, "merge, no clobber"),
        ("docs", 64, "A **failed pull/relist**"),
        ("docs", 76, "**Circuit breaker (task body):**"),
        ("docs", 96, "POLL_CADENCE_S         = 240"),
        ("docs", 100, "Worst-case detection is one full poll cadence"),
        ("docs", 106, "*/4 * * * *"),
        ("docs", 112, "**Deployment note"),
        ("docs", 122, "**Flag**"),
    ]
    bad = []
    for f, ln, frag in CITES:
        try:
            text = LINES[f][ln - 1]
        except IndexError:
            bad.append((f, ln, frag, "<out of range>"))
            continue
        if frag not in text:
            bad.append((f, ln, frag, text.strip()[:70]))
    check(f"citation audit: {len(CITES)} file:line refs hold their text",
          not bad, f"bad={bad[:4]}" if bad else f"verified={len(CITES)}")

    # ── summary ─────────────────────────────────────────────────────────
    failed = [r for r in RESULTS if not r[1]]
    print(f"\n=== {len(RESULTS) - len(failed)}/{len(RESULTS)} probes PASS ===",
          flush=True)
    if failed:
        for lbl, _, det in failed:
            print(f"  FAILED: {lbl} :: {det}")
    print(f"scratch={root}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
