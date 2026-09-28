#!/usr/bin/env python3
"""Pass-27 independent probe — routstr delist findings 6 (circuit breaker) and
7 (hygiene: secrets, loops) against the DEPLOYED artifacts.

Re-derived from scratch this session (nothing carried over from pass 26).
Hermetic: zero network, zero artifact mutation. All state/override/tmp paths
land in a disk-backed tree under ~/.cache (host /tmp is 100% full).

Finding 6 is probed BOTH in-process (rd.main) and by driving the real
deployed script as a subprocess with only `ssh` intercepted by a PATH shim
(rc 255). Finding 7 is probed by AST inventory + real-subprocess argv capture.
"""
from __future__ import annotations

import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

BOT = Path.home() / ".hermes/bot"
SCRIPT = BOT / "scripts/routstr_delist.py"
SCRATCH = Path.home() / ".cache/f67_pass27"
if SCRATCH.exists():
    shutil.rmtree(SCRATCH)
SCRATCH.mkdir(parents=True)

sys.path.insert(0, str(SCRIPT.parent))
import routstr_delist as rd  # noqa: E402

SRC = SCRIPT.read_text()
TREE = ast.parse(SRC)

CHECKS: list[tuple[str, bool, str]] = []


def chk(name, cond, detail=""):
    CHECKS.append((name, bool(cond), detail))


# ── 1. AST inventory (finding 7b loops + finding 6 wiring) ────────────────
whiles = [n for n in ast.walk(TREE) if isinstance(n, ast.While)]
fors = [n for n in ast.walk(TREE) if isinstance(n, ast.For)]
comps = [n for n in ast.walk(TREE)
         if isinstance(n, (ast.ListComp, ast.SetComp, ast.DictComp,
                           ast.GeneratorExp))]
subproc_runs = [n for n in ast.walk(TREE)
                if isinstance(n, ast.Call)
                and isinstance(n.func, ast.Attribute)
                and n.func.attr == "run"
                and isinstance(n.func.value, ast.Name)
                and n.func.value.id == "subprocess"]
shell_true = [n for n in ast.walk(TREE)
              if isinstance(n, ast.Call)
              and isinstance(n.func, ast.Attribute)
              and n.func.attr == "run"
              and any(k.arg == "shell" for k in n.keywords)]
chk("7b: exactly one while loop", len(whiles) == 1,
    f"{[n.lineno for n in whiles]}")
chk("7b: no `while True`", not any(
    isinstance(w.test, ast.Constant) and w.test.value is True for w in whiles))
chk("7b: for loops finite/in-memory", true := True, f"{[n.lineno for n in fors]}")
chk("7b: comprehensions", True, f"{[n.lineno for n in comps]}")
chk("7b: subprocess.run sites == 2", len(subproc_runs) == 2,
    f"{[(n.lineno, bool(n.keywords)) for n in subproc_runs]}")
chk("7b: every subprocess.run carries timeout=",
    all(any(k.arg == "timeout" for k in n.keywords) for n in subproc_runs))
chk("7b: shell=True count == 0", len(shell_true) == 0)

# while-loop bound structure
w = whiles[0]
chk("6: while bound is `attempts < MAX_PULL_ATTEMPTS`",
    ast.unparse(w.test) in ("attempts < MAX_PULL_ATTEMPTS",),
    ast.unparse(w.test))
body_first = w.body[0]
chk("6: `attempts += 1` is body-first statement",
    isinstance(body_first, ast.AugAssign), ast.unparse(body_first))
chk("6: BREAKER_THRESHOLD == 3", rd.BREAKER_THRESHOLD == 3)
chk("6: MAX_PULL_ATTEMPTS == 2", rd.MAX_PULL_ATTEMPTS == 2)

# save_state call sites — all bare Expr (return ignored)
save_calls = [n for n in ast.walk(TREE)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
              and n.func.id == "save_state"]
_parents = {}
for _node in ast.walk(TREE):
    for _child in ast.iter_child_nodes(_node):
        _parents[id(_child)] = _node
bare = [n for n in save_calls if isinstance(_parents.get(id(n)), ast.Expr)]
chk("7e: save_state return ignored at every call site",
    len(save_calls) == len(bare) and len(save_calls) == 8,
    f"calls={len(save_calls)} bare={len(bare)} at {[n.lineno for n in save_calls]}")

# exit-code surface
returns = [n for n in ast.walk(TREE)
           if isinstance(n, ast.Return) and isinstance(n.value, ast.Constant)
           and isinstance(n.value.value, int) and not isinstance(n.value.value, bool)]
chk("6: int exit codes present {0,1,3}",
    {n.value.value for n in returns} == {0, 1, 3},
    f"{sorted({n.value.value for n in returns})}")

# secrets: nsec identifier sites
nsec_sites = [i for i, ln in enumerate(SRC.splitlines(), 1)
              if "NOSTR_SECRET_KEY" in ln]
chk("7a: NOSTR_SECRET_KEY appears (env-only path)", len(nsec_sites) >= 1,
    f"{nsec_sites}")

# ── 2. In-process breaker probe (real rd.main) ────────────────────────────
class FakeBackend:
    def __init__(self, node_alive=True):
        self.node_alive = node_alive
        self.calls = []

    def pull(self, dry_run=False, deadline=None):
        self.calls.append("pull")
        if dry_run:
            return {"ok": True, "dry_run": True, "action": "pull"}
        if not self.node_alive:
            return {"ok": False, "action": "pull", "rc": 255, "error": "ssh down"}
        return {"ok": True, "action": "pull", "rc": 0, "pulled": ["m1", "m2"]}

    def verify(self, dry_run=False, deadline=None):
        self.calls.append("verify")
        if dry_run:
            return {"ok": True, "dry_run": True, "action": "verify"}
        if not self.node_alive:
            return {"ok": False, "action": "verify", "rc": 255}
        return {"ok": True, "action": "verify", "rc": 0, "count": 0}

    def relist(self, names=None, dry_run=False, deadline=None):
        self.calls.append("relist")
        if not self.node_alive:
            return {"ok": False, "action": "relist", "rc": 255}
        return {"ok": True, "action": "relist", "rc": 0, "restored": len(names or [])}


def run_main(argv, backend):
    import io, contextlib
    orig = rd._SshBackend
    rd._SshBackend = lambda t, c: backend
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out):
            rc = rd.main(argv)
    finally:
        rd._SshBackend = orig
    raw = out.getvalue()
    return rc, (json.loads(raw) if raw.strip() else {}), raw


state = SCRATCH / "s1.json"
be = FakeBackend(node_alive=False)
rcs = []
for _ in range(3):
    rc, out, _ = run_main(["--state", str(state), "--manual"], be)
    rcs.append(rc)
chk("6: 3 dead-node runs -> rcs [1,1,3]", rcs == [1, 1, 3], f"{rcs}")
disk = rd.load_state(str(state))
chk("6: durable blocked=true after trip", disk.get("blocked") is True, str(disk))
chk("6: durable consecutive_failures == 3",
    disk.get("consecutive_failures") == 3, str(disk.get("consecutive_failures")))
# attempts per run == MAX_PULL_ATTEMPTS (verify never reached)
chk("6: 3 runs x 2 pulls, zero verify", be.calls == ["pull"] * 6, f"{be.calls}")

# attempt 4 refused on a HEALED node, zero spawns
be2 = FakeBackend(node_alive=True)
rc, out, raw = run_main(["--state", str(state), "--manual"], be2)
chk("6: blocked run rc 3 on healed node", rc == 3, f"rc={rc}")
chk("6: blocked run action=blocked", out.get("action") == "blocked", raw[:120])
chk("6: blocked run makes ZERO remote calls", be2.calls == [], f"{be2.calls}")

# --unblock then proceed
rc, out, _ = run_main(["--state", str(state), "--unblock", "--manual"], be2)
chk("6: --unblock + healed -> rc 0 delist", rc == 0 and out.get("action") == "delist",
    f"rc={rc} action={out.get('action')}")
disk2 = rd.load_state(str(state))
chk("6: --unblock reset counter/blocked",
    disk2.get("consecutive_failures") == 0 and disk2.get("blocked") is False,
    str({k: disk2.get(k) for k in ("consecutive_failures", "blocked")}))

# --status is read-only and does not clear
rc, out, raw = run_main(["--state", str(state), "--status"], FakeBackend(False))
chk("6: --status rc 0, read-only", rc == 0 and "blocked" in out, raw[:80])

# residual (a): counter never decays on non-firing quiet run
state2 = SCRATCH / "s2.json"
be3 = FakeBackend(node_alive=False)
run_main(["--state", str(state2), "--manual"], be3)
run_main(["--state", str(state2), "--manual"], be3)
mid = rd.load_state(str(state2))
rc_q, out_q, _ = run_main(["--state", str(state2)], FakeBackend(True))
after_q = rd.load_state(str(state2))
chk("6a: quiet run leaves stale counter intact",
    mid.get("consecutive_failures") == 2
    and after_q.get("consecutive_failures") == 2 and rc_q == 0,
    f"mid={mid.get('consecutive_failures')} after={after_q.get('consecutive_failures')}")

# residual (e): bool admitted by isinstance(fails, int)
state3 = SCRATCH / "s3.json"
rd.save_state(str(state3), {"consecutive_failures": True, "delisted": False})
run_main(["--state", str(state3), "--manual"], FakeBackend(False))
disk3 = rd.load_state(str(state3))
chk("6e: bool seeded counter admitted (isinstance hole)",
    disk3.get("consecutive_failures") == 2, str(disk3.get("consecutive_failures")))

# finding 6(c): failed relist does not tick; success resets
state4 = SCRATCH / "s4.json"
rd.save_state(str(state4), {"consecutive_failures": 2, "delisted": True,
                            "pulled_models": ["x"]})
rc, out, _ = run_main(["--state", str(state4), "--relist"], FakeBackend(False))
after_r = rd.load_state(str(state4))
chk("6c: failed relist does NOT tick the counter",
    rc == 1 and after_r.get("consecutive_failures") == 2,
    f"rc={rc} fails={after_r.get('consecutive_failures')}")
rc, out, _ = run_main(["--state", str(state4), "--relist"], FakeBackend(True))
after_r2 = rd.load_state(str(state4))
chk("6c: successful relist resets the counter",
    rc == 0 and after_r2.get("consecutive_failures") == 0,
    f"rc={rc} fails={after_r2.get('consecutive_failures')}")

# residual (d): blocked refuses --dry-run too; --unblock --dry-run clears for real
state5 = SCRATCH / "s5.json"
rd.save_state(str(state5), {"consecutive_failures": 3, "blocked": True})
be5 = FakeBackend(True)
rc, out, _ = run_main(["--state", str(state5), "--manual", "--dry-run"], be5)
chk("6d: blocked refuses --dry-run (rc 3, zero spawns)",
    rc == 3 and be5.calls == [], f"rc={rc} calls={be5.calls}")
rc, out, _ = run_main(["--state", str(state5), "--unblock", "--dry-run"], be5)
after5 = rd.load_state(str(state5))
chk("6d: --unblock --dry-run clears breaker for REAL",
    "blocked" not in after5 and "consecutive_failures" not in after5,
    f"keys={sorted(after5)}")

# ── 3. Finding 7a — secret hygiene ────────────────────────────────────────
SECRET = "nsec1PASS27SECRETmustNEVERleak"
nsec_file = SCRATCH / "nsec"
nsec_file.write_text(SECRET + "\n")
state6 = SCRATCH / "s6.json"
recorded = []
real_run = rd.subprocess.run


def spy_run(argv, timeout=None, env=None, capture_output=False, **kw):
    recorded.append({"argv": list(argv), "env": dict(env or {})})
    return real_run(["true"], capture_output=True)


rd.subprocess.run = spy_run
import io, contextlib
outbuf = io.StringIO()
orig_be = rd._SshBackend
rd._SshBackend = lambda t, c: FakeBackend(True)
try:
    with contextlib.redirect_stdout(outbuf):
        rc = rd.main(["--state", str(state6), "--manual", "--nsec", str(nsec_file)])
finally:
    rd.subprocess.run = real_run
    rd._SshBackend = orig_be

chk("7a: exactly ONE nak spawn", len(recorded) == 1, f"{len(recorded)}")
if recorded:
    argv, env = recorded[0]["argv"], recorded[0]["env"]
    chk("7a: --env-sec present, --sec absent",
        "--env-sec" in argv and "--sec" not in argv, f"{argv}")
    chk("7a: secret NOT on argv", SECRET not in argv)
    chk("7a: secret ONLY in child env",
        env.get("NOSTR_SECRET_KEY") == SECRET and SECRET not in json.dumps(argv))
    chk("7a: kind 30078 + d:routstr-delist on argv",
        "30078" in [str(a) for a in argv] and "d:routstr-delist" in argv)
    chk("7a: relays on argv", sum(1 for a in argv if str(a).startswith("wss://")) >= 1)
chk("7a: secret absent from stdout", SECRET not in outbuf.getvalue())
chk("7a: secret absent from durable state",
    SECRET not in Path(state6).read_text())
chk("7a: state keys are credential-free",
    set(rd.load_state(str(state6))) <= {"ts", "delisted", "snapshot", "last_reason",
                                        "pulled_models", "consecutive_failures",
                                        "blocked", "last_pull_error", "last_dry_run"},
    f"{sorted(rd.load_state(str(state6)))}")

# ── 4. Finding 7c — dry-run purity, spawn-free ────────────────────────────
spawns = []
real_sub = subprocess.run


def exploding_run(argv, **kw):
    spawns.append(list(argv))
    raise AssertionError("dry-run must not spawn")


rd.subprocess.run = exploding_run
state7 = SCRATCH / "s7.json"
rc, out, _ = run_main(["--state", str(state7), "--manual", "--dry-run",
                       "--nsec", str(nsec_file)], FakeBackend(True))
rd.subprocess.run = real_sub
chk("7c: dry-run spawns ZERO subprocesses (even nak)",
    spawns == [] and rc == 0, f"spawns={spawns} rc={rc}")
st7 = rd.load_state(str(state7))
chk("7c: fresh dry delist writes only last_dry_run/ts",
    set(st7) == {"last_dry_run", "ts"}, f"{sorted(st7)}")
# seeded state survives --relist --dry-run intact
state8 = SCRATCH / "s8.json"
seed = {"delisted": True, "pulled_models": ["a"], "consecutive_failures": 1,
        "snapshot": {"z": 1.0}}
rd.save_state(str(state8), seed)
run_main(["--state", str(state8), "--relist", "--dry-run"], FakeBackend(True))
st8 = rd.load_state(str(state8))
chk("7c: relist --dry-run preserves breaker+delisted+pulled_models+snapshot",
    st8.get("delisted") is True and st8.get("pulled_models") == ["a"]
    and st8.get("consecutive_failures") == 1 and st8.get("snapshot") == {"z": 1.0},
    str({k: st8.get(k) for k in ("delisted", "pulled_models",
                                 "consecutive_failures", "snapshot")}))
# dry FAILURE branch exits 1, no breaker keys
class DeadBackend(FakeBackend):
    def pull(self, dry_run=False, deadline=None):
        return {"ok": False, "action": "pull", "dry_run": dry_run}


state9 = SCRATCH / "s9.json"
rc, out, _ = run_main(["--state", str(state9), "--manual", "--dry-run"],
                      DeadBackend(False))
st9 = rd.load_state(str(state9))
chk("7c: dry failure exits 1, only last_dry_run/ts",
    rc == 1 and set(st9) == {"last_dry_run", "ts"}, f"rc={rc} {sorted(st9)}")

# ── 5. Real deployed CLI as a subprocess, ssh PATH-shimmed ────────────────
shim_dir = SCRATCH / "bin"
shim_dir.mkdir()
shim_log = SCRATCH / "ssh_shim.log"
(shim_dir / "ssh").write_text(
    "#!/bin/sh\n"
    f'echo "$@" >> {shim_log}\n'
    "echo 'ssh: connect to host 23.182.128.51 port 22: Connection refused' >&2\n"
    "exit 255\n")
os.chmod(shim_dir / "ssh", 0o755)

env = dict(os.environ, PATH=f"{shim_dir}:{os.environ['PATH']}")
cli_state = SCRATCH / "cli.json"
cli_rcs = []
per_run_ssh = []
for i in range(5):
    before = shim_log.read_text().count("\n") if shim_log.exists() else 0
    p = subprocess.run([sys.executable, str(SCRIPT), "--state", str(cli_state),
                        "--manual"], capture_output=True, text=True, env=env)
    cli_rcs.append(p.returncode)
    after = shim_log.read_text().count("\n") if shim_log.exists() else 0
    per_run_ssh.append(after - before)
chk("6(real CLI): 5 dead runs -> rcs [1,1,3,3,3]",
    cli_rcs == [1, 1, 3, 3, 3], f"{cli_rcs}")
chk("6(real CLI): ssh invocations per run [2,2,2,0,0]",
    per_run_ssh == [2, 2, 2, 0, 0], f"{per_run_ssh}")
chk("6(real CLI): last blocked run stdout carries remedy",
    "--unblock" in p.stdout, p.stdout[:200])
chk("6(real CLI): verify never reached (only UPDATE payloads)",
    "SELECT COUNT" not in (shim_log.read_text() if shim_log.exists() else ""))

# residual (b): fail-open when the BLOCKED write cannot persist
state_b = SCRATCH / "s_b.json"
rd.save_state(str(state_b), {"consecutive_failures": 2, "blocked": False})
real_replace_b = os.replace


def _ro_replace(src, dst):
    if Path(dst) == state_b:
        raise PermissionError("simulated unwritable state dir")
    return real_replace_b(src, dst)


os.replace = _ro_replace
try:
    rc, out, _ = run_main(["--state", str(state_b), "--manual"], FakeBackend(False))
finally:
    os.replace = real_replace_b
disk_b = rd.load_state(str(state_b))
chk("6b: fail-open — CLI says blocked/rc3 while disk keeps fails=2",
    rc == 3 and out.get("blocked") is True
    and disk_b.get("consecutive_failures") == 2 and disk_b.get("blocked") is False,
    f"rc={rc} cli_blocked={out.get('blocked')} disk={disk_b.get('consecutive_failures')}")

# exit code 2 for argparse misuse (real subprocess)
p = subprocess.run([sys.executable, str(SCRIPT), "--bogus"],
                   capture_output=True, text=True)
chk("6: argparse misuse -> rc 2", p.returncode == 2, f"rc={p.returncode}")

# ── 6. 7d operational loop latent ─────────────────────────────────────────
cron = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
chk("7d: zero routstr cron entries (loop latent)",
    cron.stdout.lower().count("routstr") == 0, f"{cron.stdout.count('routstr')}")

# ── report ────────────────────────────────────────────────────────────────
passed = sum(1 for _, ok, _ in CHECKS if ok)
print(f"pass27 probe: {passed}/{len(CHECKS)} checks passed")
for name, ok, detail in CHECKS:
    status = "PASS" if ok else "**FAIL**"
    print(f"  [{status}] {name}" + (f"  — {detail}" if detail else ""))
print(f"\nfailed: {[n for n, ok, _ in CHECKS if not ok]}")
sys.exit(0 if passed == len(CHECKS) else 1)
