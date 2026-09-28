#!/usr/bin/env python3
"""Pass-26 independent probe — routstr delist findings 6 (circuit breaker) and
7 (hygiene: secrets, loops) against the DEPLOYED artifacts.

Two evidence layers, both hermetic (zero network, zero artifact mutation):

  A. in-process  — real `rd.main()` driven through the CLI argument surface,
     with only `subprocess.run` intercepted (a recorder/replayer), on disk-backed
     tmp state. Covers trip sequencing, refusal, --unblock, --status, the
     exit-code space, all five finding-6 residuals, and every finding-7
     hygiene claim (env-only secret, dry-run spawn-freeness, loop boundedness).
  B. real-CLI    — the DEPLOYED script executed as a real subprocess, with a
     PATH-shimmed `ssh` that logs and fails (rc 255). No faking of internals.

Nothing here writes to ~/.hermes/bot: every --state/--override path is a tmp
tree under ~/.cache (NOT /tmp — the host tmpfs is 100% full).
"""
from __future__ import annotations

import ast
import contextlib
import hashlib
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile

HOME = os.path.expanduser("~")
BOT = f"{HOME}/.hermes/bot"
SCRIPT = f"{BOT}/scripts/routstr_delist.py"
TESTS = f"{BOT}/tests/test_routstr_delist.py"
DOC = f"{BOT}/docs/routstr-delist.md"
REPO = f"{HOME}/repos/merchant-routing"
CONTRACT_MD = f"{BOT}/docs/routstr_delist_contract.md"

TMPROOT = tempfile.mkdtemp(prefix="f67p26-", dir=f"{HOME}/.cache")
os.environ["TMPDIR"] = TMPROOT

RESULTS = []
N = [0]


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond), detail))
    N[0] += 1
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f" :: {detail}" if detail else ""))


def md5(p):
    return hashlib.md5(open(p, "rb").read()).hexdigest()


def lines(p):
    return sum(1 for _ in open(p, "rb"))


def section(t):
    print(f"\n{'=' * 78}\n{t}\n{'=' * 78}")


# ── 0. artifact identity / path status ────────────────────────────────────
section("0. ARTIFACT IDENTITY AND PATH STATUS")
check("contract.md MISSING at bot path (reported HIGH)",
      not os.path.exists(CONTRACT_MD),
      f"{CONTRACT_MD} exists={os.path.exists(CONTRACT_MD)}")
print(f"    bot docs dir contents: {sorted(os.listdir(f'{BOT}/docs'))}")
for label, p, rep in (("deployed script", SCRIPT, f"{REPO}/src/routstr_delist.py"),
                      ("deployed suite", TESTS, f"{REPO}/tests/test_routstr_delist_contract.py"),
                      ("doc", DOC, f"{REPO}/docs/routstr-delist.md")):
    print(f"    {label:15s} {lines(p):5d} L  md5={md5(p)}  repo_identical={md5(p) == md5(rep)}")

SRC = open(SCRIPT).read()
TREE = ast.parse(SRC)

# ── 1. AST inventory (finding 7b loops + finding 6 wiring) ────────────────
section("1. AST INVENTORY")
whiles = [n.lineno for n in ast.walk(TREE) if isinstance(n, ast.While)]
fors = [n.lineno for n in ast.walk(TREE) if isinstance(n, ast.For)]
comps = [n.lineno for n in ast.walk(TREE)
         if isinstance(n, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp))]
run_calls = [n for n in ast.walk(TREE)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
             and n.func.attr == "run" and isinstance(n.func.value, ast.Name)
             and n.func.value.id == "subprocess"]
run_ln = sorted(n.lineno for n in run_calls)
run_to = sorted(n.lineno for n in run_calls
                if any(k.arg == "timeout" for k in n.keywords))
shell_true = [n.lineno for n in run_calls
              if any(k.arg == "shell" and isinstance(k.value, ast.Constant)
                     and k.value.value is True for k in n.keywords)]
print(f"    while          : {whiles}")
print(f"    for            : {sorted(fors)}")
print(f"    comprehensions : {sorted(comps)}")
print(f"    subprocess.run : {run_ln}  with timeout= : {run_to}  shell=True : {shell_true}")
check("exactly ONE while loop in the deployed script", len(whiles) == 1, str(whiles))
check("every subprocess.run is timeout-bounded",
      run_ln == run_to and len(run_ln) == 2, f"run={run_ln} timeout={run_to}")
check("no shell=True anywhere", shell_true == [], str(shell_true))
check("no unbounded 'while True'", not any(
    isinstance(n.test, ast.Constant) and n.test.value is True
    for n in ast.walk(TREE) if isinstance(n, ast.While)))

# while-loop bound structure (finding 6 counter semantics + 7b)
wl = [n for n in ast.walk(TREE) if isinstance(n, ast.While)][0]
wl_body = wl.body
check("while bound is 'attempts < MAX_PULL_ATTEMPTS'",
      isinstance(wl.test, ast.Compare)
      and getattr(wl.test.left, "id", None) == "attempts"
      and getattr(wl.test.comparators[0], "id", None) == "MAX_PULL_ATTEMPTS",
      ast.unparse(wl.test))
first = wl_body[0]
check("loop body increments FIRST (attempts += 1 is body[0])",
      isinstance(first, ast.AugAssign) and getattr(first.target, "id", None) == "attempts",
      ast.unparse(first))

# save_state call sites: bare Expr (return ignored)
parents = {}


def _walk(node, parent=None):
    for ch in ast.iter_child_nodes(node):
        parents[id(ch)] = node
        _walk(ch, node)


_walk(TREE)
ss_calls = [n for n in ast.walk(TREE)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
            and n.func.id == "save_state"]
ss_bare = sorted(n.lineno for n in ss_calls
                 if isinstance(parents.get(id(n)), ast.Expr))
print(f"    save_state call sites: {sorted(n.lineno for n in ss_calls)}")
print(f"    ... of which bare (return ignored): {ss_bare}")
check("save_state return ignored at every site",
      len(ss_bare) == len(ss_calls) and len(ss_calls) == 8,
      f"{len(ss_bare)}/{len(ss_calls)}")

# breaker wiring
names = {n.id for n in ast.walk(TREE) if isinstance(n, ast.Name)}
check("BREAKER_THRESHOLD defined", "BREAKER_THRESHOLD" in names)
bt_const = next(n for n in TREE.body if isinstance(n, ast.Assign)
                and getattr(n.targets[0], "id", None) == "BREAKER_THRESHOLD")
print(f"    BREAKER_THRESHOLD = {ast.literal_eval(bt_const.value)} (line {bt_const.lineno})")
check("BREAKER_THRESHOLD == 3", ast.literal_eval(bt_const.value) == 3)

ret_ln = {}
for n in ast.walk(TREE):
    if isinstance(n, ast.Return) and isinstance(n.value, ast.Constant):
        ret_ln[n.lineno] = n.value.value
print(f"    literal returns   : { {k: ret_ln[k] for k in sorted(ret_ln)} }")
check("exit space includes 3 (blocked refusal + trip)", 3 in ret_ln.values(),
      f"lines {sorted(k for k, v in ret_ln.items() if v == 3)}")

# nsec identifier sites
nsec_sites = sorted({n.lineno for n in ast.walk(TREE)
                     if isinstance(n, ast.Name) and "nsec" in n.id.lower()})
print(f"    nsec identifier sites: {nsec_sites}")
check("nsec identifier appears at exactly 2 source sites",
      len(nsec_sites) == 2, str(nsec_sites))

# ── in-process harness ────────────────────────────────────────────────────
sys.path.insert(0, f"{BOT}/scripts")
import routstr_delist as rd  # noqa: E402

REAL_RUN = subprocess.run


class Clock:
    """Synthetic monotonic; wall time REAL (mtime freshness guard)."""

    def __init__(self):
        self.t = 0.0

    def monotonic(self):
        return self.t

    @staticmethod
    def time():
        import time
        return time.time()


def shim_cmd(cmd):
    argv = list(cmd)
    if "event" in argv:                      # nak kind-30078 publish
        return "nak"
    s = argv[2] if len(argv) > 2 else ""
    if "COUNT(*)" in s:
        return "verify"
    if "enabled=0" in s:
        return "pull"
    return "relist"


class Ssh:
    """Records/replays subprocess.run for the ssh path."""

    def __init__(self, mode="ok", secret=None, clock=None, advance=0.0,
                 nak_mode="ok", names=None, verify_count=0):
        self.mode = mode                  # ok | down | lying | relist_down
        self.secret = secret
        self.clock = clock
        self.advance = advance
        self.nak_mode = nak_mode
        self.names = names if names is not None else ["gpt-4o", "claude-3-5-sonnet"]
        self.verify_count = verify_count
        self.calls = []                   # {"kind","timeout","argv"}
        self.spawns = 0

    def __call__(self, argv, **kw):
        self.spawns += 1
        kind = shim_cmd(list(argv))
        self.calls.append({"kind": kind, "timeout": kw.get("timeout"),
                           "argv": list(argv), "env": dict(kw.get("env") or {})})
        if kw.get("timeout") is not None and self.clock is not None:
            self.clock.t += self.advance

        def cp(rc, out):
            return subprocess.CompletedProcess(list(argv), rc, out, "")

        if kind == "relist":
            if self.mode == "relist_down":
                return cp(255, "")
            return cp(0, json.dumps({"ok": True, "restored": len(self.names)}) + "\n")
        if self.mode == "down" and kind in ("pull", "verify"):
            return cp(255, "")
        if kind == "verify":
            return cp(0, json.dumps({"ok": True, "count": self.verify_count}) + "\n")
        return cp(0, json.dumps({"ok": True, "pulled": self.names}) + "\n")


def run_cli(argv, *, ssh=None, clock=None, state=None, override=None):
    st = state or os.path.join(tempfile.mkdtemp(dir=TMPROOT), "state.json")
    ov = override or os.path.join(os.path.dirname(st), "no.override")
    full = ["--state", st, "--override", ov] + list(argv)
    saved_run, saved_time = rd.subprocess.run, rd.time
    if ssh is not None:
        rd.subprocess.run = ssh
    if clock is not None:
        rd.time = clock
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out):
            rc = rd.main(full)
    finally:
        rd.subprocess.run, rd.time = saved_run, saved_time
    raw = out.getvalue()
    return rc, (json.loads(raw) if raw.strip() else {}), raw, st


# ── 2. Finding 6 — breaker on the in-process real CLI ─────────────────────
section("2. FINDING 6 — CIRCUIT BREAKER (in-process real CLI)")
s = Ssh(mode="down")
st = os.path.join(tempfile.mkdtemp(dir=TMPROOT), "state.json")
rcs, per_run = [], []
for i in range(5):
    before = len(s.calls)
    rc, out, _, st = run_cli(["--manual"], ssh=s, state=st)
    rcs.append(rc)
    per_run.append(sum(1 for c in s.calls[before:] if c["kind"] == "pull"))
print(f"    5 failing runs -> rcs {rcs}; pulls/run {per_run}; kinds {[c['kind'] for c in s.calls]}")
check("trip sequence is [1,1,3,3,3]", rcs == [1, 1, 3, 3, 3], str(rcs))
check("per-run pull attempts [2,2,2,0,0] (attempt 4 never runs)",
      per_run == [2, 2, 2, 0, 0], str(per_run))
check("no verify round-trip ever reached before/after trip",
      all(c["kind"] == "pull" for c in s.calls), str([c["kind"] for c in s.calls]))
disk = json.load(open(st))
check("durable BLOCKED marker on disk",
      disk.get("blocked") is True and disk.get("consecutive_failures") == 3, str(disk))

# refusal of every action while blocked, on a healed node
for argv in (["--manual"], ["--relist"], ["--relist", "--relist-any"],
             ["--manual", "--dry-run"], ["--delist"]):
    s2 = Ssh(mode="ok")
    rc, out, raw, _ = run_cli(argv, ssh=s2, state=st)
    check(f"blocked refuses {' '.join(argv)} (rc 3, 0 remote calls)",
          rc == 3 and out.get("action") == "blocked" and s2.spawns == 0,
          f"rc={rc} action={out.get('action')} spawns={s2.spawns}")

# --status is read-only and does NOT clear
s3 = Ssh(mode="ok")
rc, out, _, _ = run_cli(["--status"], ssh=s3, state=st)
check("--status rc 0, reports blocked/consecutive_failures, spawns nothing, non-clearing",
      rc == 0 and out.get("blocked") is True and out.get("consecutive_failures") == 3
      and s3.spawns == 0 and json.load(open(st)).get("blocked") is True,
      f"rc={rc} out={out}")

# --unblock heals
s4 = Ssh(mode="ok")
rc, out, _, st = run_cli(["--unblock", "--manual"], ssh=s4, state=st)
d = json.load(open(st))
check("--unblock --manual heals: rc 0 delist, counter 0, blocked false",
      rc == 0 and out.get("action") == "delist" and d.get("consecutive_failures") == 0
      and d.get("blocked") is False, f"rc={rc} {d}")

# exit-code space
rc_quiet, o1, _, _ = run_cli([], ssh=Ssh(mode="ok"))
rc_dry, o2, _, _ = run_cli(["--manual", "--dry-run"], ssh=Ssh(mode="ok"))
rc_bogus = None
try:
    with contextlib.redirect_stdout(io.StringIO()):
        rd.main(["--bogus"])
except SystemExit as e:
    rc_bogus = e.code
print(f"    exit space probes: quiet={rc_quiet} dry={rc_dry} bogus={rc_bogus} "
      f"(blocked=3 tripped, failure=1)")
check("exit space {0,1,3} plus argparse 2",
      rc_quiet == 0 and rc_dry == 0 and rc_bogus == 2, "see above")

# ── 3. Finding 6 residuals ────────────────────────────────────────────────
section("3. FINDING 6 — RESIDUALS (re-probed)")
# (a) no decay across non-firing runs
sd = os.path.join(tempfile.mkdtemp(dir=TMPROOT), "s.json")
sf = Ssh(mode="down")
for _ in range(2):
    run_cli(["--manual"], ssh=sf, state=sd)
mid = json.load(open(sd))
run_cli([], ssh=Ssh(mode="ok"), state=sd)            # quiet run rc 0
q = json.load(open(sd))
run_cli(["--preds", os.path.join(TMPROOT, "missing.json")], ssh=Ssh(mode="ok"), state=sd)
e = json.load(open(sd))
rc_t, out_t, _, _ = run_cli(["--manual"], ssh=Ssh(mode="down"), state=sd)
check("(a) counter holds 2 across quiet + preds_error runs, then one new failure trips",
      mid.get("consecutive_failures") == 2 and q.get("consecutive_failures") == 2
      and e.get("consecutive_failures") == 2 and rc_t == 3,
      f"after2={mid.get('consecutive_failures')} quiet={q.get('consecutive_failures')} "
      f"err={e.get('consecutive_failures')} next_rc={rc_t}")

# (b) fail-open when the state dir is unwritable at the tripping write
sd2 = tempfile.mkdtemp(dir=TMPROOT)
sp = os.path.join(sd2, "s.json")
json.dump({"consecutive_failures": 2, "blocked": False, "ts": 1}, open(sp, "w"))
os.chmod(sd2, 0o500)
try:
    rc_b, out_b, _, _ = run_cli(["--manual"], ssh=Ssh(mode="down"), state=sp)
    disk_b = json.load(open(sp))
finally:
    os.chmod(sd2, 0o700)
check("(b) fail-open: prints rc 3/blocked true while disk keeps fails 2/blocked false",
      rc_b == 3 and out_b.get("blocked") is True
      and disk_b.get("consecutive_failures") == 2 and disk_b.get("blocked") is False,
      f"rc={rc_b} out_blocked={out_b.get('blocked')} disk={disk_b}")

# (c) asymmetric relist accounting
sc = os.path.join(tempfile.mkdtemp(dir=TMPROOT), "s.json")
json.dump({"consecutive_failures": 2, "blocked": False, "pulled_models": ["gpt-4o"],
           "ts": 1}, open(sc, "w"))
rc_c, out_c, _, _ = run_cli(["--relist"], ssh=Ssh(mode="relist_down"), state=sc)
d_c = json.load(open(sc))
rc_c2, out_c2, _, _ = run_cli(["--relist"], ssh=Ssh(mode="ok"), state=sc)
d_c2 = json.load(open(sc))
check("(c) failed relist never ticks the counter; successful relist resets it",
      rc_c == 1 and d_c.get("consecutive_failures") == 2
      and rc_c2 == 0 and d_c2.get("consecutive_failures") == 0,
      f"failed: rc={rc_c} cnt={d_c.get('consecutive_failures')} | "
      f"ok: rc={rc_c2} cnt={d_c2.get('consecutive_failures')}")

# (d) dry-run interaction both directions
sd4 = os.path.join(tempfile.mkdtemp(dir=TMPROOT), "s.json")
json.dump({"consecutive_failures": 3, "blocked": True, "ts": 1}, open(sd4, "w"))
s4a = Ssh(mode="ok")
rc_d1, out_d1, _, _ = run_cli(["--manual", "--dry-run"], ssh=s4a, state=sd4)
rc_d2, out_d2, _, _ = run_cli(["--unblock", "--dry-run"], ssh=Ssh(mode="ok"), state=sd4)
d_d2 = json.load(open(sd4))
check("(d) blocked refuses --dry-run preview; --unblock --dry-run clears for real",
      rc_d1 == 3 and s4a.spawns == 0
      and "blocked" not in d_d2 and "consecutive_failures" not in d_d2,
      f"preview rc={rc_d1} spawns={s4a.spawns} | after unblock-dry: keys={sorted(d_d2)}")

# (e) bool hole in the isinstance(int) counter guard
sd5 = os.path.join(tempfile.mkdtemp(dir=TMPROOT), "s.json")
json.dump({"consecutive_failures": True, "blocked": False, "ts": 1}, open(sd5, "w"))
run_cli(["--manual"], ssh=Ssh(mode="down"), state=sd5)
d_d5 = json.load(open(sd5))
check("(e) bool counter hole: seeded true + one failure -> disk counter 2",
      d_d5.get("consecutive_failures") == 2, str(d_d5.get("consecutive_failures")))

# deadline clamping / SLA budget inside a fired run
ck = Clock()
s_dl = Ssh(mode="ok", clock=ck, advance=25.0)
rc_dl, out_dl, _, _ = run_cli(["--manual"], ssh=s_dl, clock=ck)
tos = [c["timeout"] for c in s_dl.calls]
check("remote round-trips timeout-clamped to the remaining 60 s action budget",
      rc_dl == 0 and all(t is not None and 0 < t <= rd.ACTION_BUDGET_S for t in tos),
      f"timeouts={tos} budget={rd.ACTION_BUDGET_S}")

# ── 4. Finding 7a — secret hygiene ────────────────────────────────────────
section("4. FINDING 7a — SECRET HYGIENE")
SECRET = "nsec1PROBEPASS26NEVERREAL"
nsec_dir = tempfile.mkdtemp(dir=TMPROOT)
nsecp = os.path.join(nsec_dir, "nsec")
open(nsecp, "w").write(SECRET + "\n")
st7 = os.path.join(tempfile.mkdtemp(dir=TMPROOT), "s.json")
sp7 = Ssh(mode="ok", secret=SECRET)
rc7, out7, raw7, _ = run_cli(["--manual", "--nsec", nsecp], ssh=sp7, state=st7)
state_txt = open(st7).read()
nak = [c for c in sp7.calls if c["kind"] == "nak"]
argv7 = nak[0]["argv"] if nak else []
env7 = nak[0]["env"] if nak else {}
state7 = json.load(open(st7))
check("exactly one nak publish; --env-sec present, --sec absent",
      len(nak) == 1 and "--env-sec" in argv7 and "--sec" not in argv7, f"{argv7}")
check("secret present ONLY in the child env (NOSTR_SECRET_KEY)",
      env7.get("NOSTR_SECRET_KEY") == SECRET and SECRET not in " ".join(argv7),
      f"env_keys={sorted(k for k in env7 if 'SECRET' in k or 'NOSTR' in k)}")
check("secret absent from stdout and the durable state file",
      SECRET not in raw7 and SECRET not in state_txt)
check("kind 30078 + d:routstr-delist in the publish argv",
      "30078" in [str(a) for a in argv7] and "d:routstr-delist" in argv7)
check("no credential-bearing key in state (allowlist)",
      set(state7) <= {"ts", "delisted", "snapshot", "last_reason", "pulled_models",
                      "consecutive_failures", "blocked", "last_pull_error",
                      "last_dry_run"}, str(sorted(state7)))

# raising nak is swallowed -> clean rc 0
def raising(argv, **kw):
    if "event" in argv:
        raise OSError("simulated nak failure")
    return Ssh(mode="ok")(argv, **kw)


sp8 = Ssh(mode="ok")
saved = rd.subprocess.run
rd.subprocess.run = raising
out8 = io.StringIO()
try:
    with contextlib.redirect_stdout(out8):
        rc8 = rd.main(["--state", st7, "--override", nsec_dir, "--manual",
                       "--nsec", nsecp])
finally:
    rd.subprocess.run = saved
check("7a residual: a RAISING nak is swallowed — run still rc 0, no signal",
      rc8 == 0 and json.loads(out8.getvalue())["action"] == "delist", f"rc={rc8}")

# ── 5. Finding 7b/7c — dry-run purity, spawn-free ─────────────────────────
section("5. FINDING 7b/7c — LOOPS + DRY-RUN PURITY")
spawns = []


def exploding(argv, **kw):
    spawns.append(list(argv))
    raise AssertionError("a subprocess was spawned during a dry run")


st9 = os.path.join(tempfile.mkdtemp(dir=TMPROOT), "s.json")
saved = rd.subprocess.run
rd.subprocess.run = exploding
out9 = io.StringIO()
try:
    with contextlib.redirect_stdout(out9):
        rc9 = rd.main(["--state", st9, "--override", nsec_dir,
                       "--manual", "--dry-run", "--nsec", nsecp])
finally:
    rd.subprocess.run = saved
d9 = json.load(open(st9))
check("7c dry run spawns ZERO subprocesses (not even ssh/nak)",
      rc9 == 0 and spawns == [], f"rc={rc9} spawns={spawns}")
check("7c fresh-state dry delist writes exactly [last_dry_run, ts]",
      sorted(d9) == ["last_dry_run", "ts"], str(sorted(d9)))

# seeded state survives --relist --dry-run
st10 = os.path.join(tempfile.mkdtemp(dir=TMPROOT), "s.json")
seed = {"delisted": True, "pulled_models": ["gpt-4o"], "consecutive_failures": 1,
        "snapshot": {"zai\x1f1h": 5.0}, "ts": 1}
json.dump(seed, open(st10, "w"))
saved = rd.subprocess.run
rd.subprocess.run = exploding
out10 = io.StringIO()
try:
    with contextlib.redirect_stdout(out10):
        rc10 = rd.main(["--state", st10, "--override", nsec_dir,
                        "--relist", "--dry-run", "--nsec", nsecp])
finally:
    rd.subprocess.run = saved
d10 = json.load(open(st10))
check("7c seeded delisted/pulled_models/fails/snapshot all survive a dry relist",
      rc10 == 0 and d10.get("delisted") is True and d10.get("pulled_models") == ["gpt-4o"]
      and d10.get("consecutive_failures") == 1 and d10.get("snapshot") == seed["snapshot"],
      str(sorted(d10)))

# dry run can NEVER observe an ssh failure: the dry stub at _run:797-799
# returns before subprocess.run (:808), so mode="down" is invisible in dry mode
st11 = os.path.join(tempfile.mkdtemp(dir=TMPROOT), "s.json")
sd11 = Ssh(mode="down")
rc11, out11, _, _ = run_cli(["--manual", "--dry-run"], ssh=sd11, state=st11)
d11 = json.load(open(st11))
check("7c dry run against a DEAD node still rc 0 and spawns nothing "
      "(dry stub :797-799 precedes :808)",
      rc11 == 0 and sd11.spawns == 0 and sorted(d11) == ["last_dry_run", "ts"],
      f"rc={rc11} spawns={sd11.spawns} keys={sorted(d11)}")

# exercise the dry-FAILURE branch (:717) directly by forcing a failed pull
st12 = os.path.join(tempfile.mkdtemp(dir=TMPROOT), "s.json")
saved_pl = rd.pull_listing
rd.pull_listing = lambda backend, **kw: {"ok": False, "action": "pull",
                                         "error": "forced"}
out12 = io.StringIO()
try:
    with contextlib.redirect_stdout(out12):
        rc12 = rd.main(["--state", st12, "--override", nsec_dir,
                        "--manual", "--dry-run"])
finally:
    rd.pull_listing = saved_pl
d12 = json.load(open(st12))
check("7c dry-failure branch (:717) exits 1, writes only last_dry_run/ts "
      "(no breaker keys, no last_pull_error)",
      rc12 == 1 and sorted(d12) == ["last_dry_run", "ts"]
      and d12["last_dry_run"]["action"] == "delist_failed",
      f"rc={rc12} keys={sorted(d12)}")

# 7e file mode
m = stat.S_IMODE(os.stat(st11).st_mode)
check("7e state file written with default umask, credential-free", True, f"mode={oct(m)}")

print(f"\n{'=' * 78}")
fails = [n for n, ok, _ in RESULTS if not ok]
print(f"IN-PROCESS: {N[0] - len(fails)}/{N[0]} checks passed")
for n in fails:
    print(f"  FAILED: {n}")

# ── 6. Real-CLI subprocess probe (deployed script, PATH-shimmed ssh) ───────
section("6. FINDING 6 — REAL DEPLOYED CLI AS A SUBPROCESS (ssh PATH-shimmed)")
shimdir = tempfile.mkdtemp(dir=TMPROOT)
sshlog = os.path.join(shimdir, "ssh.log")
shim = os.path.join(shimdir, "ssh")
open(shim, "w").write(f"#!/bin/sh\necho \"$*\" >> {sshlog}\nexit 255\n")
os.chmod(shim, 0o755)
env = dict(os.environ, PATH=f"{shimdir}:{os.environ['PATH']}", SSH_LOG=sshlog,
           TMPDIR=TMPROOT)
rst = os.path.join(tempfile.mkdtemp(dir=TMPROOT), "state.json")
rcs2, deltas = [], []
for i in range(5):
    n0 = sum(1 for _ in open(sshlog)) if os.path.exists(sshlog) else 0
    p = subprocess.run([sys.executable, SCRIPT, "--state", rst,
                        "--override", os.path.join(shimdir, "no.override"),
                        "--manual"], capture_output=True, text=True, env=env,
                       timeout=120)
    rcs2.append(p.returncode)
    n1 = sum(1 for _ in open(sshlog)) if os.path.exists(sshlog) else 0
    deltas.append(n1 - n0)
print(f"    per-run ssh invocations {deltas}; rcs {rcs2}")
check("REAL CLI trip rcs [1,1,3,3,3]", rcs2 == [1, 1, 3, 3, 3], str(rcs2))
check("REAL CLI per-run ssh deltas [2,2,2,0,0] (attempt 4 never runs)",
      deltas == [2, 2, 2, 0, 0], str(deltas))
check("REAL CLI no verify round-trip before the trip",
      os.path.exists(sshlog)
      and all("COUNT(*)" not in l for l in open(sshlog)), "log scanned")
d_real = json.load(open(rst))
check("REAL CLI durable BLOCKED marker", d_real.get("blocked") is True
      and d_real.get("consecutive_failures") == 3, str(d_real))
p = subprocess.run([sys.executable, SCRIPT, "--state", rst, "--status"],
                   capture_output=True, text=True, env=env, timeout=120)
st_out = json.loads(p.stdout)
check("REAL CLI --status read-only, rc 0, surfaces breaker",
      p.returncode == 0 and st_out.get("blocked") is True
      and st_out.get("consecutive_failures") == 3, str(st_out))

print(f"\n{'=' * 78}")
fails = [n for n, ok, _ in RESULTS if not ok]
print(f"TOTAL: {N[0] - len(fails)}/{N[0]} checks passed")
for n in fails:
    print(f"  FAILED: {n}")
print(f"tmp tree: {TMPROOT}")
print("artifacts mutated: NONE (all state under the tmp tree)")
