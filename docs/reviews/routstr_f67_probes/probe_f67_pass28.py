#!/usr/bin/env python3
"""Pass-28 independent re-derivation probe for routstr-delist findings 6 & 7.

Findings under test:
  6 — circuit breaker: 3 consecutive failed runs -> durable BLOCKED, exit 3.
  7 — hygiene: (a) secrets env-only, (b) loops bounded, (c) dry-run purity,
                (d) the operational loop, (e) permissions/housekeeping.

Fresh code, written this session; nothing reused from the prior passes' probes.
Heremetic: zero network, zero artifact mutation.  Every state/override path
lands in a disk-backed tmp tree under ~/.cache (host /tmp is 100% full).

Real-CLI legs drive the DEPLOYED script as a subprocess with ONLY `ssh`
intercepted by a PATH shim (two modes: dead / honest).  In-process legs import
the DEPLOYED module directly and swap only the backend + subprocess.run.

Prints one PASS/FAIL line per check; exits 0 iff every check passed.
"""
from __future__ import annotations

import ast
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import pathlib
import shutil
import stat
import subprocess
import sys
import tempfile
import time

HOME = pathlib.Path(os.path.expanduser("~"))
BOT = HOME / ".hermes/bot"
DEPLOYED_SCRIPT = BOT / "scripts/routstr_delist.py"
DEPLOYED_SUITE = BOT / "tests/test_routstr_delist.py"
BOT_DOC = BOT / "docs/routstr-delist.md"
TASK_CONTRACT = BOT / "docs/routstr_delist_contract.md"
REPO = pathlib.Path("/home/c03rad0r/repos/merchant-routing")
REPO_SCRIPT = REPO / "src/routstr_delist.py"
REPO_SUITE = REPO / "tests/test_routstr_delist_contract.py"
REPO_DOC = REPO / "docs/routstr-delist.md"

MD5_SCRIPT = "2ea724ef08d857cd7b88a957300e70b4"
MD5_SUITE = "031851b356f0de4089512f02f13f05cc"
MD5_DOC = "e385af98b9c142eec736672d4dcca290"

CRED_FREE_KEYS = {
    "ts", "delisted", "snapshot", "last_reason", "pulled_models",
    "consecutive_failures", "blocked", "last_pull_error", "last_dry_run",
}

CHECKS: list[tuple[str, bool, str]] = []


def check(name: str, ok, detail: str = "") -> bool:
    ok = bool(ok)
    CHECKS.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  -- {detail}" if detail else ""))
    return ok


def md5(p: pathlib.Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


def load_deployed():
    spec = importlib.util.spec_from_file_location("rd_p28", DEPLOYED_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


rd = load_deployed()
SRC_TEXT = DEPLOYED_SCRIPT.read_text()
SRC_LINES = SRC_TEXT.splitlines()


# ── Test doubles ──────────────────────────────────────────────────────────
class HealthyBackend:
    def pull(self, dry_run=False, deadline=None):
        return {"ok": True, "pulled": ["gpt-4o", "claude-3-5-sonnet"]}

    def verify(self, dry_run=False, deadline=None):
        return {"ok": True, "count": 0}

    def relist(self, names=None, dry_run=False, deadline=None):
        return {"ok": True, "restored": len(names or [])}

    def dry_run_pull(self, **kw):
        return {"ok": True, "dry_run": True}

    def dry_run_relist(self, **kw):
        return {"ok": True, "dry_run": True}


class DeadBackend:
    def pull(self, dry_run=False, deadline=None):
        return {"ok": False, "action": "pull", "rc": 255,
                "error": "ssh: connect to host 23.182.128.51 port 22: refused"}

    def verify(self, dry_run=False, deadline=None):
        return {"ok": False, "action": "verify", "rc": 255, "error": "dead"}

    def relist(self, names=None, dry_run=False, deadline=None):
        return {"ok": False, "action": "relist", "rc": 255, "error": "dead"}


class LyingBackend(HealthyBackend):
    """pull self-reports ok, re-fetch refutes it (models still advertised)."""

    def verify(self, dry_run=False, deadline=None):
        return {"ok": True, "count": 2}


@contextlib.contextmanager
def swap(mod, name, value):
    old = getattr(mod, name)
    setattr(mod, name, value)
    try:
        yield
    finally:
        setattr(mod, name, old)


def cli(argv, *, state, override):
    """Drive the DEPLOYED module's real main() in-process, capture stdout."""
    full = ["--state", str(state), "--override", str(override)] + list(argv)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = rd.main(full)
    raw = out.getvalue()
    return rc, (json.loads(raw) if raw.strip() else {}), raw


def on_disk(state):
    return json.loads(pathlib.Path(state).read_text())


# ═══ Group A — artifact identity + the required artifact-path report ═══════
print("=" * 72)
print("GROUP A — artifact identity / task-path report")
print("=" * 72)

check("A1 required contract md MISSING at bot path (HIGH)",
      not TASK_CONTRACT.exists()
      and not any(BOT.rglob("*contract*")),
      f"{TASK_CONTRACT} absent; rglob('*contract*') under {BOT} -> 0 hits")

check("A2 deployed script md5", md5(DEPLOYED_SCRIPT) == MD5_SCRIPT, md5(DEPLOYED_SCRIPT))
check("A3 deployed suite md5", md5(DEPLOYED_SUITE) == MD5_SUITE, md5(DEPLOYED_SUITE))
check("A4 bot doc md5", md5(BOT_DOC) == MD5_DOC, md5(BOT_DOC))
check("A5 script byte-identical repo<->bot", md5(REPO_SCRIPT) == md5(DEPLOYED_SCRIPT))
check("A6 suite byte-identical repo<->bot", md5(REPO_SUITE) == md5(DEPLOYED_SUITE))
check("A7 doc byte-identical repo<->bot", md5(REPO_DOC) == md5(BOT_DOC))
check("A8 line counts 829 script / 752 suite / 197 doc",
      len(SRC_TEXT.splitlines()) == 829
      and len(DEPLOYED_SUITE.read_text().splitlines()) == 752
      and len(BOT_DOC.read_text().splitlines()) == 197,
      f"{len(SRC_TEXT.splitlines())}/{len(DEPLOYED_SUITE.read_text().splitlines())}/"
      f"{len(BOT_DOC.read_text().splitlines())}")

# The deployed-layout loader must fall through to ../scripts (proves the
# deployed suite exercises the DEPLOYED script, not the repo one).
_suite_lines = DEPLOYED_SUITE.read_text().splitlines()
_loader = "\n".join(_suite_lines[48:54])
check("A9 deployed suite loader tries ../src then ../scripts",
      '_HERE.parent / "src"' in _loader and '_HERE.parent / "scripts"' in _loader,
      "lines 49-54")
check("A10 bot has no src/ copy of the script (scripts/ is the live path)",
      not (BOT / "src/routstr_delist.py").exists()
      and (BOT / "scripts/routstr_delist.py").exists(),
      "~/.hermes/bot/src/routstr_delist.py absent")

_cron = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
check("A11 crontab has zero routstr entries (operational loop latent)",
      _cron.stdout.lower().count("routstr") == 0,
      f"rc={_cron.returncode}, routstr hits=0")

_live = json.loads((BOT / "routstr_delist_state.json").read_text())
check("A12 live state keys inside credential-free allowlist",
      set(_live) <= CRED_FREE_KEYS, f"keys={sorted(_live)}")


# ═══ Group B — Finding 6: the circuit breaker ═════════════════════════════
print("=" * 72)
print("GROUP B — Finding 6: circuit breaker (real CLI subprocess + in-process)")
print("=" * 72)

TMP = pathlib.Path(tempfile.mkdtemp(prefix="f67p28_", dir=HOME / ".cache"))
shim_dir = TMP / "shim"
shim_dir.mkdir()
SHIM_LOG = TMP / "ssh_calls.log"
SHIM_MODE = TMP / "mode"
SHIM_MODE.write_text("dead")

SHIM = f"""#!/bin/sh
# PATH shim for ssh: logs the full remote command, then honours SHIM_MODE.
printf '%s\\n' "$*" >> {SHIM_LOG}
MODE="$(cat {SHIM_MODE})"
case "$MODE" in
  dead)
    exit 255 ;;
  lying)
    case "$*" in
      *"SELECT COUNT(*)"*) echo '{{"ok": true, "count": 2}}' ;;
      *"UPDATE models"*)   echo '{{"ok": true, "pulled": ["gpt-4o", "claude-3-5-sonnet"]}}' ;;
      *)                   echo '{{"ok": true}}' ;;
    esac
    exit 0 ;;
  *)
    case "$*" in
      *"SELECT COUNT(*)"*)   echo '{{"ok": true, "count": 0}}' ;;
      *"enabled=1 WHERE"*)   echo '{{"ok": true, "restored": 2}}' ;;
      *"UPDATE models"*)     echo '{{"ok": true, "pulled": ["gpt-4o", "claude-3-5-sonnet"]}}' ;;
      *)                     echo '{{"ok": true}}' ;;
    esac
    exit 0 ;;
esac
"""
shim = shim_dir / "ssh"
shim.write_text(SHIM)
shim.chmod(0o755)

ENV = dict(os.environ, PATH=f"{shim_dir}:{os.environ['PATH']}")


def real_cli(*argv, state, override):
    """Run the deployed CLI as a subprocess; return (rc, json, ssh_delta, delta_lines)."""
    before = SHIM_LOG.read_text() if SHIM_LOG.exists() else ""
    p = subprocess.run([sys.executable, str(DEPLOYED_SCRIPT),
                        "--state", str(state), "--override", str(override), *argv],
                       capture_output=True, text=True, env=ENV)
    after = SHIM_LOG.read_text() if SHIM_LOG.exists() else ""
    delta = after[len(before):].splitlines()
    try:
        payload = json.loads(p.stdout) if p.stdout.strip() else {}
    except Exception:
        payload = {"_unparsable": p.stdout[:200]}
    return p.returncode, payload, len(delta), delta


st = TMP / "b_state.json"
ov = TMP / "absent.override"

rcs, calls, run_lines = [], [], []
for _ in range(5):
    rc, env_out, n, lines = real_cli("--manual", state=st, override=ov)
    rcs.append(rc)
    calls.append(n)
    run_lines.append(lines)
check("B1 five dead-node runs -> rcs [1,1,3,3,3] (trip on run 3)",
      rcs == [1, 1, 3, 3, 3], f"rcs={rcs}")
check("B2 per-run ssh deltas [2,2,2,0,0] (attempt 4+ never runs)",
      calls == [2, 2, 2, 0, 0], f"deltas={calls}")

pre_trip = [ln for lines in run_lines[:3] for ln in lines]
pull_lines = [ln for ln in pre_trip if "UPDATE models SET enabled=0" in ln]
verify_lines = [ln for ln in pre_trip if "SELECT COUNT(*)" in ln]
check("B3 all 6 pre-trip round-trips are pull payloads; verify never reached",
      len(pull_lines) == 6 and len(verify_lines) == 0,
      f"pulls={len(pull_lines)} verifies={len(verify_lines)}")

disk = on_disk(st)
check("B4 durable BLOCKED marker + counter==3 written at trip",
      disk.get("blocked") is True and disk.get("consecutive_failures") == 3,
      f"blocked={disk.get('blocked')} fails={disk.get('consecutive_failures')}")

blocked_results = {}
for label, argv in (("--relist", ("--relist",)),
                    ("--manual", ("--manual",)),
                    ("--manual --dry-run", ("--manual", "--dry-run")),
                    ("--relist --relist-any", ("--relist", "--relist-any"))):
    rc, env_out, n, _ = real_cli(*argv, state=st, override=ov)
    blocked_results[label] = (rc, env_out.get("action"), n)
check("B5 while BLOCKED every remote action refuses rc3 with 0 round-trips",
      all(v[0] == 3 and v[1] == "blocked" and v[2] == 0
          for v in blocked_results.values()),
      "; ".join(f"{k}:rc{v[0]}/{v[1]}/{v[2]}calls" for k, v in blocked_results.items()))

rc, env_out, n, _ = real_cli("--status", state=st, override=ov)
check("B6 --status rc0 read-only, reports both breaker fields, does not clear",
      rc == 0 and env_out.get("blocked") is True
      and env_out.get("consecutive_failures") == 3 and n == 0
      and on_disk(st).get("blocked") is True,
      f"rc={rc} blocked={env_out.get('blocked')} fails={env_out.get('consecutive_failures')}")

SHIM_MODE.write_text("honest")
rc, env_out, n, _ = real_cli("--unblock", "--manual", state=st, override=ov)
disk = on_disk(st)
check("B7 --unblock heals and the same run delists (rc0, fails0, blocked false)",
      rc == 0 and env_out.get("action") == "delist" and env_out.get("confirmed") is True
      and disk.get("consecutive_failures") == 0 and disk.get("blocked") is False
      and disk.get("delisted") is True,
      f"rc={rc} action={env_out.get('action')} confirmed={env_out.get('confirmed')} "
      f"delisted={disk.get('delisted')} fails={disk.get('consecutive_failures')}")

# Exit-code space {0,1,2,3}
st2 = TMP / "b_state2.json"
rc_bogus, _, _, _ = real_cli("--bogus", state=st2, override=ov)
rc_quiet, out_quiet, n_quiet, _ = real_cli(state=st2, override=ov)
bad_preds = TMP / "garbage.json"
bad_preds.write_text("{not json")
rc_err, out_err, _, _ = real_cli("--preds", str(bad_preds), state=st2, override=ov)
rc_dry, out_dry, n_dry, _ = real_cli("--manual", "--dry-run", state=st2, override=ov)
check("B8 exit space {0,1,2,3}: bogus=2 quiet=0 preds_error=1 healthy-dry=0",
      (rc_bogus, rc_quiet, rc_err, rc_dry) == (2, 0, 1, 0)
      and out_dry.get("action") == "delist" and n_dry == 0,
      f"bogus={rc_bogus} quiet={rc_quiet} preds_error={rc_err} dry={rc_dry}")

# ── in-process breaker semantics (backend swapped only) ───────────────────
st3 = TMP / "c_state.json"
st3.write_text(json.dumps({"ts": 1, "delisted": False, "snapshot": {},
                           "pulled_models": ["gpt-4o"], "consecutive_failures": 2}))
with swap(rd, "_SshBackend", lambda t, c: DeadBackend()):
    rc, out, _ = cli(["--relist"], state=st3, override=ov)
d = on_disk(st3)
check("B9 a FAILED relist never ticks the breaker (src:626-632)",
      rc == 1 and out.get("action") == "relist_failed"
      and d.get("consecutive_failures") == 2 and d.get("blocked") is not True,
      f"rc={rc} action={out.get('action')} fails={d.get('consecutive_failures')} "
      f"blocked={d.get('blocked')!r} (no breaker key written)")

st4 = TMP / "c_state2.json"
st4.write_text(json.dumps({"ts": 1, "delisted": True, "snapshot": {},
                           "pulled_models": ["gpt-4o"], "consecutive_failures": 2}))
with swap(rd, "_SshBackend", lambda t, c: HealthyBackend()):
    rc, out, _ = cli(["--relist"], state=st4, override=ov)
d = on_disk(st4)
check("B10 a SUCCESSFUL relist resets the counter (src:636-637)",
      rc == 0 and d.get("consecutive_failures") == 0 and d.get("blocked") is False
      and "pulled_models" not in d,
      f"rc={rc} fails={d.get('consecutive_failures')} pulled_models_present="
      f"{'pulled_models' in d}")

st5 = TMP / "c_state3.json"
st5.write_text(json.dumps({"ts": 1, "delisted": False, "consecutive_failures": 2}))
with swap(rd, "_SshBackend", lambda t, c: HealthyBackend()):
    rc_q, out_q, _ = cli([], state=st5, override=ov)
    d_q = on_disk(st5)
with swap(rd, "_SshBackend", lambda t, c: DeadBackend()):
    rc_f, out_f, _ = cli(["--manual"], state=st5, override=ov)
    d_f = on_disk(st5)
check("B11 no decay: 2 stale fails survive a quiet run, then ONE new fail trips",
      rc_q == 0 and d_q.get("consecutive_failures") == 2 and rc_f == 3
      and d_f.get("consecutive_failures") == 3 and d_f.get("blocked") is True,
      f"after-quiet fails={d_q.get('consecutive_failures')} rc_fail={rc_f} "
      f"fails_after_fail={d_f.get('consecutive_failures')} blocked={d_f.get('blocked')}")

st6 = TMP / "c_state4.json"
st6.write_text(json.dumps({"ts": 1, "consecutive_failures": True}))
with swap(rd, "_SshBackend", lambda t, c: DeadBackend()):
    rc, out, _ = cli(["--manual"], state=st6, override=ov)
d = on_disk(st6)
check("B12 bool type-guard hole: seeded true + 1 fail -> disk counter 2 (src:545)",
      rc == 1 and d.get("consecutive_failures") == 2,
      f"rc={rc} fails={d.get('consecutive_failures')} (bool admitted by isinstance(int))")

st7 = TMP / "c_state5.json"
st7.write_text(json.dumps({"ts": 1, "delisted": False, "consecutive_failures": 2}))
locked = TMP / "locked"
locked.mkdir()
st7 = locked / "state.json"
st7.write_text(json.dumps({"ts": 1, "delisted": False, "consecutive_failures": 2}))
os.chmod(locked, 0o500)
try:
    with swap(rd, "_SshBackend", lambda t, c: DeadBackend()):
        rc, out, _ = cli(["--manual"], state=st7, override=ov)
finally:
    os.chmod(locked, 0o700)
d = on_disk(st7)
check("B13 fail-open: trip prints rc3/blocked true while disk keeps fails 2 (src:732)",
      rc == 3 and out.get("blocked") is True
      and d.get("consecutive_failures") == 2 and d.get("blocked") is not True,
      f"printed rc={rc} blocked={out.get('blocked')} | disk fails="
      f"{d.get('consecutive_failures')} blocked={d.get('blocked')!r}")

st8 = TMP / "c_state6.json"
st8.write_text(json.dumps({"ts": 1, "delisted": True, "snapshot": {"a\x1fb": 1.0},
                           "pulled_models": ["gpt-4o"]}))
with swap(rd, "_SshBackend", lambda t, c: DeadBackend()):
    rc, out, _ = cli(["--manual"], state=st8, override=ov)
d = on_disk(st8)
check("B14 a failed fired run force-clears the durable delisted flag (src:726)",
      rc == 1 and d.get("delisted") is False and d.get("snapshot") == {"a\x1fb": 1.0},
      f"rc={rc} delisted={d.get('delisted')} (baseline preserved)")

# ── AST structural inventory ──────────────────────────────────────────────
tree = ast.parse(SRC_TEXT)
whiles = [n for n in ast.walk(tree) if isinstance(n, ast.While)]
fors = [n for n in ast.walk(tree) if isinstance(n, ast.For)]
comps = [n for n in ast.walk(tree)
         if isinstance(n, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp))]
while_true = [n for n in whiles
              if isinstance(n.test, ast.Constant) and n.test.value is True]
run_calls = [n for n in ast.walk(tree)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
             and n.func.attr == "run"
             and isinstance(n.func.value, ast.Name) and n.func.value.id == "subprocess"]
timeout_kw = [n for n in run_calls if any(k.arg == "timeout" for k in n.keywords)]
shell_kw = [n for n in run_calls
            if any(k.arg == "shell" and getattr(k.value, "value", False) for k in n.keywords)]
danger = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
          and isinstance(n.func, ast.Attribute)
          and n.func.attr in ("system", "popen", "spawn", "spawnl")
          and isinstance(n.func.value, ast.Name) and n.func.value.id == "os"]
check("B15 AST: exactly 1 while, 0 while-True, 2 subprocess.run, both timeout=, 0 shell=True",
      len(whiles) == 1 and len(while_true) == 0 and len(run_calls) == 2
      and len(timeout_kw) == 2 and len(shell_kw) == 0 and len(danger) == 0,
      f"while={len(whiles)} whileTrue={len(while_true)} for={len(fors)} comps={len(comps)} "
      f"run={len(run_calls)} timeout={len(timeout_kw)} shell={len(shell_kw)} ospawn={len(danger)}")
check("B15b while loop is bounded by attempts < MAX_PULL_ATTEMPTS with body-first +=",
      isinstance(whiles[0].test, ast.Compare)
      and ast.unparse(whiles[0].test).startswith("attempts < MAX_PULL_ATTEMPTS"),
      ast.unparse(whiles[0].test))

# every save_state call site must be a bare Expr statement (return ignored)
parents: dict[int, ast.AST] = {}
for node in ast.walk(tree):
    for child in ast.iter_child_nodes(node):
        parents[id(child)] = node
save_calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
              and isinstance(n.func, ast.Name) and n.func.id == "save_state"]
bare = [n for n in save_calls if isinstance(parents.get(id(n)), ast.Expr)]
check("B16 all 8 save_state call sites are bare Expr (return value never checked)",
      len(save_calls) == 8 and len(bare) == 8,
      f"calls={len(save_calls)} bare={len(bare)} lines="
      f"{sorted(n.lineno for n in save_calls)}")


# ═══ Group C — Finding 7: hygiene ═════════════════════════════════════════
print("=" * 72)
print("GROUP C — Finding 7: hygiene (secrets / loops / dry-run / ops / perms)")
print("=" * 72)

# 7a — secret can only travel through the child environment
SECRET = "nsec1TESTSECRETqxNEVERuseMEinPROD"
nsec_file = TMP / "nsec"
nsec_file.write_text(SECRET + "\n")
recorded: list[dict] = []


def recording_run(argv, timeout=None, env=None, capture_output=False, **kw):
    recorded.append({"argv": list(argv), "env": dict(env or {}), "timeout": timeout})
    return subprocess.CompletedProcess(argv, 0)


st9 = TMP / "d_state.json"
with swap(rd.subprocess, "run", recording_run), \
        swap(rd, "_SshBackend", lambda t, c: HealthyBackend()):
    rc, out, raw = cli(["--manual", "--nsec", str(nsec_file)], state=st9, override=ov)
argv = recorded[0]["argv"] if recorded else []
env = recorded[0]["env"] if recorded else {}
state_txt = pathlib.Path(st9).read_text()
check("C1 exactly ONE nak spawn; --env-sec present, --sec absent, secret ONLY in child env",
      rc == 0 and len(recorded) == 1
      and "--env-sec" in argv and "--sec" not in argv
      and env.get("NOSTR_SECRET_KEY") == SECRET,
      f"spawns={len(recorded)} env_sec={'--env-sec' in argv} sec={'--sec' in argv} "
      f"env_only={env.get('NOSTR_SECRET_KEY') == SECRET}")
check("C2 secret absent from stdout, argv and the durable state file",
      SECRET not in raw and SECRET not in json.dumps(argv) and SECRET not in state_txt
      and "30078" in [str(a) for a in argv] and "d:routstr-delist" in argv,
      f"argv_tail={argv[-3:] if argv else []}")
check("C3 build_delist_event -> None when the nsec file is missing",
      rd.build_delist_event(str(TMP / "nope")) is None
      and rd.build_delist_event(None) is None)
check("C4 a failed publish is swallowed (except Exception: pass) -> rc unaffected",
      "except Exception:" in SRC_TEXT[SRC_TEXT.index("def publish_delist_event"):
                                       SRC_TEXT.index("def publish_delist_event") + 900]
      and "return argv" in SRC_TEXT[SRC_TEXT.index("def publish_delist_event"):
                                    SRC_TEXT.index("def publish_delist_event") + 900],
      "publish_delist_event src:462-464")

# 7b/7c — dry-run purity: ALL spawns intercepted with an exploding stub
spawns: list[list] = []


def exploding_run(argv, **kw):
    spawns.append(list(argv))
    raise AssertionError("SPAWN DETECTED during a dry run")


st10 = TMP / "e_state.json"
with swap(rd.subprocess, "run", exploding_run), \
        swap(rd, "_SshBackend", lambda t, c: HealthyBackend()):
    rc, out, _ = cli(["--manual", "--dry-run", "--nsec", str(nsec_file)],
                     state=st10, override=ov)
d = on_disk(st10)
check("C5 dry-run spawns ZERO subprocesses even with --nsec wired",
      rc == 0 and out.get("action") == "delist" and spawns == [],
      f"rc={rc} spawns={len(spawns)}")

st11 = TMP / "e_state2.json"
st11.write_text(json.dumps({"delisted": True,
                            "pulled_models": ["gpt-4o"],
                            "consecutive_failures": 1,
                            "snapshot": {"zai\x1f1h": 10.0}}))
with swap(rd, "_SshBackend", lambda t, c: HealthyBackend()):
    rc, out, _ = cli(["--relist", "--dry-run"], state=st11, override=ov)
d = on_disk(st11)
check("C6 seeded state survives --relist --dry-run (all four keys intact)",
      rc == 0 and d.get("delisted") is True and d.get("pulled_models") == ["gpt-4o"]
      and d.get("consecutive_failures") == 1
      and d.get("snapshot") == {"zai\x1f1h": 10.0},
      f"kept={sorted(d)}")

st12 = TMP / "e_state3.json"
with swap(rd, "_SshBackend", lambda t, c: HealthyBackend()):
    rc, out, _ = cli(["--manual", "--dry-run"], state=st12, override=ov)
d = on_disk(st12)
check("C7 a fresh dry delist writes exactly [last_dry_run, ts]",
      rc == 0 and set(d) == {"last_dry_run", "ts"},
      f"keys={sorted(d)}")

st13 = TMP / "e_state4.json"
st13.write_text(json.dumps({"delisted": False, "consecutive_failures": 2}))


class DryFailBackend(HealthyBackend):
    def dry_run_pull(self, **kw):
        return {"ok": False, "action": "pull", "error": "budget exhausted"}

    def pull(self, dry_run=False, deadline=None):
        return {"ok": False, "action": "pull", "error": "budget exhausted"}


with swap(rd, "_SshBackend", lambda t, c: DryFailBackend()):
    rc, out, _ = cli(["--manual", "--dry-run"], state=st13, override=ov)
d = on_disk(st13)
check("C8 dry-FAILURE branch exits 1 and writes only last_dry_run/ts (no breaker tick)",
      rc == 1 and set(d) == {"last_dry_run", "ts", "delisted", "consecutive_failures"}
      and d.get("consecutive_failures") == 2 and d.get("blocked") is None,
      f"rc={rc} keys={sorted(d)} fails={d.get('consecutive_failures')}")

# 7b — loops: real-CLI proof that a healthy run's round-trips are bounded
SHIM_MODE.write_text("honest")
st14 = TMP / "f_state.json"
rc, env_out, n_healthy, _ = real_cli("--manual", state=st14, override=ov)
check("C9 healthy real-CLI run = exactly 2 round-trips (1 pull + 1 verify)",
      rc == 0 and env_out.get("action") == "delist" and n_healthy == 2,
      f"rc={rc} action={env_out.get('action')} round_trips={n_healthy}")

SHIM_MODE.write_text("lying")
rc_ly, out_ly, n_ly, _ = real_cli("--manual", state=TMP / "g_state.json", override=ov)
check("C9b lying-node real-CLI run bounded to 2 attempts then fails (rc1)",
      out_ly.get("action") == "delist_failed" and n_ly == 4,
      f"rc={rc_ly} action={out_ly.get('action')} round_trips={n_ly} "
      f"(2 x [pull+verify])")

# 7e — permissions / housekeeping
mode = stat.S_IMODE((TMP / "f_state.json").stat().st_mode)
check("C10 state file mode is umask-default 0o664 (no credential material)",
      mode == 0o664 and set(on_disk(TMP / "f_state.json")) <= CRED_FREE_KEYS,
      f"mode={oct(mode)} keys={sorted(on_disk(TMP / 'f_state.json'))}")
check("C11 no os.chmod / no TODO-FIXME-XXX-HACK marker anywhere in the module",
      "os.chmod" not in SRC_TEXT
      and not any(m in SRC_TEXT for m in ("TODO", "FIXME", "XXX", "HACK")),
      "0 chmod, 0 markers")
check("C12 module text has exactly 2 subprocess.run sites and no shell=True",
      SRC_TEXT.count("subprocess.run") == 2 and "shell=True" not in SRC_TEXT
      and SRC_TEXT.count("timeout=") == 2,
      f"subprocess.run={SRC_TEXT.count('subprocess.run')} "
      f"timeout={SRC_TEXT.count('timeout=')}")


# ═══ Summary ══════════════════════════════════════════════════════════════
print("=" * 72)
passed = sum(1 for _, ok, _ in CHECKS if ok)
total = len(CHECKS)
print(f"SUMMARY: {passed}/{total} checks passed")
for name, ok, detail in CHECKS:
    if not ok:
        print(f"  FAILED: {name}  -- {detail}")
print("artifacts untouched:",
      md5(DEPLOYED_SCRIPT) == MD5_SCRIPT and md5(DEPLOYED_SUITE) == MD5_SUITE
      and md5(BOT_DOC) == MD5_DOC)
shutil.rmtree(TMP, ignore_errors=True)
raise SystemExit(0 if passed == total else 1)
