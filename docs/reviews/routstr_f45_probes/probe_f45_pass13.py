"""13th-pass hermetic re-derivation of findings 4-5 against the DEPLOYED script.

Drives ~/.hermes/bot/scripts/routstr_delist.py in-process with a fake backend,
tempdir state, no network, no real subprocess. Read-only w.r.t. all artifacts.
"""
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import time

BOT = os.path.expanduser("~/.hermes/bot/scripts")
sys.path.insert(0, BOT)
import routstr_delist as rd  # noqa: E402

RESULTS = []


def rec(name, ok, detail):
    RESULTS.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'} {name}: {detail}")


class FakeBackend:
    def __init__(self, pull=None, verify=None, relist=None):
        self.calls = []
        self._pull = pull or {"ok": True, "pulled": ["m1", "m2"]}
        self._verify = verify or {"ok": True, "count": 0}
        self._relist = relist or {"ok": True, "restored": 2}

    def pull(self, dry_run=False, deadline=None):
        self.calls.append("pull")
        return dict(self._pull)

    def verify(self, dry_run=False, deadline=None):
        self.calls.append("verify")
        return dict(self._verify)

    def relist(self, names=None, dry_run=False, deadline=None):
        self.calls.append(("relist", list(names or [])))
        return dict(self._relist)


def run_main(argv, backend):
    old = rd._SshBackend
    rd._SshBackend = lambda t, c: backend
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out):
            rc = rd.main(argv)
    finally:
        rd._SshBackend = old
    raw = out.getvalue()
    return rc, (json.loads(raw) if raw.strip() else {})


def tmpdir():
    return tempfile.mkdtemp(prefix="f45p13_")


# ── 4a: atomic save succeeds, no tmp litter ────────────────────────────────
d = tmpdir()
sp = os.path.join(d, "s.json")
ok = rd.save_state(sp, {"delisted": True, "ts": 1}) is True
litter = [f for f in os.listdir(d) if f.endswith(".tmp")]
rec("4a_save_state_ok", ok and not litter,
    f"return={ok} litter={litter} content={json.load(open(sp))}")

# ── 4a2: failing os.replace -> save_state returns False, tmp cleaned ───────
d = tmpdir()
sp = os.path.join(d, "s.json")
rd.save_state(sp, {"delisted": False, "ts": 0})
_real_replace = os.replace


def boom(src, dst):
    if dst == sp:
        raise OSError("simulated replace failure")
    return _real_replace(src, dst)


os.replace = boom
try:
    r = rd.save_state(sp, {"delisted": True, "ts": 2})
finally:
    os.replace = _real_replace
litter = [f for f in os.listdir(d) if f.endswith(".tmp")]
rec("4a2_save_state_false_on_error", r is False and not litter,
    f"return={r} litter={litter} on_disk={json.load(open(sp))}")

# ── 4b: silent persist failure reported as success ─────────────────────────
d = tmpdir()
sp = os.path.join(d, "s.json")
rd.save_state(sp, {"delisted": False, "ts": 1})
before = json.load(open(sp))
os.replace = boom
try:
    rc, out = run_main(["--state", sp, "--delist"], FakeBackend())
finally:
    os.replace = _real_replace
after = json.load(open(sp))
rec("4b_silent_persist_failure",
    rc == 0 and out.get("confirmed") is True and after == before,
    f"rc={rc} action={out.get('action')} confirmed={out.get('confirmed')} "
    f"state_on_disk={after}")

# ── 4b2: --status then reads the stale value ───────────────────────────────
rc, out = run_main(["--state", sp, "--status"], FakeBackend())
rec("4b2_status_reads_stale", out.get("delisted") is False,
    f"rc={rc} status.delisted={out.get('delisted')}")

# ── 4c: re-delist MERGES pulled_models ─────────────────────────────────────
d = tmpdir()
sp = os.path.join(d, "s.json")
rd.save_state(sp, {"delisted": True, "ts": 1,
                   "pulled_models": ["m1", "m2"], "snapshot": {}})
rc, out = run_main(["--state", sp, "--delist"],
                   FakeBackend(pull={"ok": True, "pulled": []}))
st = json.load(open(sp))
rec("4c_redelist_merge", st.get("pulled_models") == ["m1", "m2"],
    f"rc={rc} pulled_models={st.get('pulled_models')}")

# ── 4d: no-names relist REFUSES the blanket enable ────────────────────────
d = tmpdir()
sp = os.path.join(d, "s.json")
rd.save_state(sp, {"delisted": True, "ts": 1, "snapshot": {}})
be = FakeBackend()
rc, out = run_main(["--state", sp, "--relist"], be)
rec("4d_relist_refused",
    rc == 1 and out.get("action") == "relist_refused" and be.calls == [],
    f"rc={rc} action={out.get('action')} backend_calls={be.calls}")

# ── 4e: a FAILED relist does not tick the breaker ─────────────────────────
d = tmpdir()
sp = os.path.join(d, "s.json")
rd.save_state(sp, {"delisted": True, "ts": 1, "snapshot": {},
                   "pulled_models": ["m1"], "consecutive_failures": 2})
be = FakeBackend(relist={"ok": False, "rc": 255, "error": "ssh down"})
rc, out = run_main(["--state", sp, "--relist"], be)
st = json.load(open(sp))
rec("4e_failed_relist_no_breaker_tick",
    rc == 1 and st.get("consecutive_failures") == 2,
    f"rc={rc} action={out.get('action')} "
    f"consecutive_failures={st.get('consecutive_failures')}")

# ── 4f: bool counter hole ─────────────────────────────────────────────────
d = tmpdir()
sp = os.path.join(d, "s.json")
rd.save_state(sp, {"delisted": False, "ts": 1, "snapshot": {},
                   "consecutive_failures": True})
be = FakeBackend(pull={"ok": False, "rc": 255}, verify={"ok": False})
rc, out = run_main(["--state", sp, "--manual"], be)
st = json.load(open(sp))
rec("4f_bool_counter_hole", st.get("consecutive_failures") == 2,
    f"rc={rc} consecutive_failures={st.get('consecutive_failures')}")

# ── 5a: constants arithmetic ──────────────────────────────────────────────
ok = (rd.POLL_CADENCE_S + rd.ACTION_BUDGET_S == rd.TRIGGER_ACTION_WINDOW_S
      and rd.MAX_PULL_ATTEMPTS * rd.SSH_TIMEOUT_S <= rd.ACTION_BUDGET_S)
rec("5a_constants_arithmetic", ok,
    f"window={rd.TRIGGER_ACTION_WINDOW_S} cadence={rd.POLL_CADENCE_S} "
    f"budget={rd.ACTION_BUDGET_S} ssh={rd.SSH_TIMEOUT_S} "
    f"attempts={rd.MAX_PULL_ATTEMPTS}")

# ── 5b: expired deadline -> no spawn ──────────────────────────────────────
spawns = []
_real_run = rd.subprocess.run


def spy_run(argv, **kw):
    spawns.append(kw.get("timeout"))
    return subprocess.CompletedProcess(argv, 0, stdout='{"ok":true}', stderr="")


rd.subprocess.run = spy_run
try:
    r = rd._SshBackend("h", "c")._run("payload", dry_run=False, action="pull",
                                      deadline=time.monotonic() - 1)
    r2 = rd._SshBackend("h", "c")._run("payload", dry_run=False, action="pull",
                                       deadline=None)
finally:
    rd.subprocess.run = _real_run
rec("5b_budget_exhausted_no_spawn",
    r.get("ok") is False and r.get("error") == "action budget exhausted"
    and len(spawns) == 1,
    f"expired={r} spawns={spawns}")
rec("5b2_no_deadline_timeout", spawns == [30],
    f"no-deadline timeout={spawns}")

# ── 5c: cadence arithmetic ────────────────────────────────────────────────
win = rd.TRIGGER_ACTION_WINDOW_S
b = rd.ACTION_BUDGET_S
four = rd.POLL_CADENCE_S + b      # */4
five = 300 + b                    # */5
rec("5c_cadence_arithmetic",
    four == win and five > win,
    f"*/4 -> {four}s (== {win} exact); */5 -> {five}s (> {win}, breach)")

# ── 5d: publish timeout is not budget-clamped ─────────────────────────────
d = tmpdir()
sp = os.path.join(d, "s.json")
nsec = os.path.join(d, "nsec")
open(nsec, "w").write("nsec1TESTSECRETxxxx\n")
spawns = []


def spy_run2(argv, **kw):
    spawns.append((list(argv)[:3], kw.get("timeout")))
    return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")


rd.subprocess.run = spy_run2
try:
    rc, out = run_main(["--state", sp, "--delist", "--nsec", nsec],
                       FakeBackend())
finally:
    rd.subprocess.run = _real_run
rec("5d_publish_timeout_unclamped",
    rc == 0 and out.get("confirmed") is True and len(spawns) == 1
    and spawns[0][1] == 30,
    f"rc={rc} confirmed={out.get('confirmed')} publish={spawns}")

print("\nSUMMARY: %d/%d probes PASS" % (sum(1 for _, o, _ in RESULTS if o),
                                       len(RESULTS)))
sys.exit(0 if all(o for _, o, _ in RESULTS) else 1)
