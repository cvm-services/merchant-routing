#!/usr/bin/env python3
"""Fresh hermetic probe harness — routstr delist findings 1-3, offload pass 17.

Written for this pass (2026-09-28) against the primary artifacts; NOT derived
from probe_f13_pass11..16.py, though it uses the same (correct) shape: swap
only the ssh boundary and execute the module's OWN payload builders against an
in-process stand-in sell node that holds a live `models` (SALE) table, a live
`upstream_providers` (provider ladder) table and a ladder-artifact file.

Read-only with respect to every reviewed artifact. No network, no subprocess,
no file-backed sqlite, no scratch under /tmp (5.5 G tmpfs on this host).

Scope: A = finding 1 (safety), B = finding 2 (confirmation),
       C = finding 3 (fail-safe), D = review-record audit.

Run it twice; the printed tally AND the transcript sha256 must be identical.
Doc target override: F13_DOC=<path> (default repo docs/reviews/findings_1_3.md)
"""
from __future__ import annotations

import ast
import builtins
import contextlib
import hashlib
import io
import json
import os
import re
import shlex
import shutil
import sqlite3
import sys
import time
import types
from pathlib import Path

HERE = Path(__file__).resolve()
# .../<repo>/docs/reviews/routstr_f13_probes/probe_f13_pass17.py
REPO = HERE.parents[3]
BOT = Path.home() / ".hermes" / "bot"

SCRIPT = REPO / "src" / "routstr_delist.py"
BOT_SCRIPT = BOT / "scripts" / "routstr_delist.py"
CONTRACT = REPO / "tests" / "test_routstr_delist_contract.py"
MAIN_TESTS = REPO / "tests" / "test_routstr_delist.py"
BOT_TESTS = BOT / "tests" / "test_routstr_delist.py"
DOC = REPO / "docs" / "routstr-delist.md"
BOT_DOC = BOT / "docs" / "routstr-delist.md"
BOT_CONTRACT = BOT / "docs" / "routstr_delist_contract.md"
DELIVERABLE = (Path(os.environ["F13_DOC"]) if os.environ.get("F13_DOC")
               else REPO / "docs" / "reviews" / "findings_1_3.md")
BOT_DELIVERABLE = BOT / "docs" / "reviews" / "findings_1_3.md"

# Scratch is keyed by DIRECTORY, so wipe at import or a 2nd run re-reads the
# 1st run's durable state (the pass-11 leak).
SCRATCH = Path.home() / ".cache" / "f13-pass17" / "scratch"
shutil.rmtree(SCRATCH, ignore_errors=True)
SCRATCH.mkdir(parents=True, exist_ok=True)

os.fsync = lambda fd: None            # this host can stall forever in fsync

sys.path.insert(0, str(REPO / "src"))
import routstr_delist as rd  # noqa: E402

PROD_BACKEND = rd._SshBackend         # capture before any rig swaps it
REAL_TIME = time

# ── check plumbing ────────────────────────────────────────────────────────
CHECKS: list[tuple[str, str, bool, str]] = []


def check(cid, label, ok, detail=""):
    CHECKS.append((cid, label, bool(ok), str(detail)))


def md5(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


def nlines(p: Path) -> int:
    return p.read_bytes().count(b"\n")


# ── AST measurement of the module under review ────────────────────────────
SRC = SCRIPT.read_text(encoding="utf-8")
LINES = SRC.splitlines()
TREE = ast.parse(SRC)


def docstring_spans(tree):
    spans = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            body = getattr(node, "body", None)
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                spans.append((body[0].lineno, body[0].end_lineno))
    return spans


DOC_SPANS = docstring_spans(TREE)


def in_docstring(lineno):
    return any(lo <= lineno <= hi for lo, hi in DOC_SPANS)


def joined_text(node):
    parts = []
    for v in node.values:
        if isinstance(v, ast.Constant) and isinstance(v.value, str):
            parts.append(v.value)
        else:
            parts.append("{?}")
    return "".join(parts)


def collect_strings(node, out):
    """Record each executable string literal ONCE and do not descend into it
    (descending double-counts an implicitly-concatenated payload)."""
    for child in ast.iter_child_nodes(node):
        if isinstance(child, ast.Constant) and isinstance(child.value, str):
            out.append((child.lineno, child.value))
        elif isinstance(child, ast.JoinedStr):
            out.append((child.lineno, joined_text(child)))
        else:
            collect_strings(child, out)


CONSTS: list[tuple[int, str]] = []
collect_strings(TREE, CONSTS)
EXEC_CONSTS = [(ln, v) for ln, v in CONSTS if not in_docstring(ln)]

CALLS = [n for n in ast.walk(TREE) if isinstance(n, ast.Call)]


def fname(call):
    f = call.func
    if isinstance(f, ast.Attribute):
        base = f.value.id if isinstance(f.value, ast.Name) else ""
        return f"{base}.{f.attr}" if base else f.attr
    if isinstance(f, ast.Name):
        return f.id
    return ""


PARENTS = {}
for _n in ast.walk(TREE):
    for _c in ast.iter_child_nodes(_n):
        PARENTS[id(_c)] = _n

SITES = [(c.lineno, fname(c)) for c in CALLS]

# ═══ A — finding 1: SALE delist must not disable the provider / ladder ════
print("== A: finding 1 — safety ==")

check("A1a", "deployed script byte-identical to repo src",
      md5(BOT_SCRIPT) == md5(SCRIPT),
      f"src {md5(SCRIPT)} ({nlines(SCRIPT)} lines) bot {md5(BOT_SCRIPT)}")
check("A1b", "bot tests copy byte-identical to repo contract suite",
      md5(BOT_TESTS) == md5(CONTRACT), f"{md5(CONTRACT)} ({nlines(CONTRACT)} lines)")
check("A1c", "bot doc byte-identical to repo doc",
      md5(BOT_DOC) == md5(DOC), f"{md5(DOC)} ({nlines(DOC)} lines)")
check("A1d", "contract markdown ABSENT at the dispatched bot path (see record)",
      not BOT_CONTRACT.exists(), f"exists={BOT_CONTRACT.exists()}")

sql_consts = [(ln, v) for ln, v in EXEC_CONSTS
              if re.search(r"\b(UPDATE|SELECT)\b", v) and "models" in v]
check("A2a", "executable SQL-bearing literals == 5",
      len(sql_consts) == 5, f"lines {[ln for ln, _ in sql_consts]}")
tables = set()
verbs = []
for _, v in sql_consts:
    tables |= set(re.findall(r"\b(?:FROM|INTO|UPDATE|JOIN)\s+([a-zA-Z_]+)", v))
    verbs += re.findall(r"\b(UPDATE|SELECT)\b", v)
check("A2b", "materialised table set is exactly {models}",
      tables == {"models"}, f"{sorted(tables)}")
check("A2c", "verb inventory is 3 UPDATE + 2 SELECT",
      verbs.count("UPDATE") == 3 and verbs.count("SELECT") == 2, f"{sorted(verbs)}")

mentions = [i + 1 for i, l in enumerate(LINES) if "upstream_providers" in l]
check("A3a", "3 upstream_providers mentions, every one inside a docstring",
      mentions == [35, 352, 771] and all(in_docstring(m) for m in mentions),
      f"lines {mentions} in-docstring={[in_docstring(m) for m in mentions]}")
check("A3b", "0 executable literals name upstream_providers",
      [ln for ln, v in EXEC_CONSTS if "upstream_providers" in v] == [],
      f"{len(EXEC_CONSTS)} executable literals inspected")

run_sites = [ln for ln, fn in SITES if fn == "subprocess.run"]
shell_true = [c.lineno for c in CALLS if fname(c) == "subprocess.run"
              and any(k.arg == "shell" and getattr(k.value, "value", None) is True
                      for k in c.keywords)]
eval_sites = [ln for ln, fn in SITES if fn in ("eval", "exec")]
check("A4a", "exactly 2 subprocess.run sites (nak publish, ssh docker exec)",
      run_sites == [459, 808], f"{run_sites}")
check("A4b", "shell=True count == 0", shell_true == [], f"{shell_true}")
check("A4c", "eval/exec call sites == 0", eval_sites == [], f"{eval_sites}")

payload = rd.pull_listing_payload()
cmd = rd.build_ssh_docker_cmd("debian@host", "routstr public", payload)
parts = shlex.split(cmd[2])
check("A5a", "ssh argv is 3 elements: host + ONE quoted remote command",
      len(cmd) == 3 and cmd[0] == "ssh", f"len={len(cmd)}")
check("A5b", "remote command re-parses to the intended argv (space preserved)",
      parts[:6] == ["docker", "exec", "routstr public", "python3", "-c", payload],
      f"parts[:4]={parts[:4]}")

os_mut = sorted(ln for ln, fn in SITES if fn in (
    "os.makedirs", "os.replace", "os.unlink", "os.remove", "os.rename",
    "os.chmod", "os.fsync"))
OPEN_CALLS = [c for c in CALLS if fname(c) == "open"]
w_opens = [c.lineno for c in OPEN_CALLS if len(c.args) > 1
           and isinstance(c.args[1], ast.Constant)
           and "w" in str(c.args[1].value)]
# a read-mode open may carry an explicit mode or none at all (`open(sec_file)`)
r_opens = [c.lineno for c in OPEN_CALLS if c.lineno not in w_opens]
check("A6a", "filesystem mutation surface == the state dir only",
      os_mut == [229, 234, 235, 243] and w_opens == [231],
      f"os-mut {os_mut} write-open {w_opens}")
check("A6b", "read-mode opens are exactly 3 (:214 :457 :476) and no write "
             "escapes save_state",
      r_opens == [214, 457, 476] and len(w_opens) == 1,
      f"w={w_opens} r={r_opens}")
save_calls = [c for c in CALLS if fname(c) == "save_state"]
discarded = [c.lineno for c in save_calls
             if isinstance(PARENTS.get(id(c)), ast.Expr)]
check("A6c", "all 8 save_state call sites discard the return value",
      len(save_calls) == 8 and len(discarded) == 8,
      f"{len(discarded)}/{len(save_calls)} discard, lines {sorted(discarded)}"
      .replace("565, 622, 629, 638, 654, 710, 732, 752",
               "565/622/629/638/654/710/732/752"))

# ── the stand-in sell node ────────────────────────────────────────────────
ADVERTISED = ["gpt-4o", "claude-3-5-sonnet", "llama-3.1-405b"]
OP_DISABLED = ["operator-disabled-model"]
PROVIDERS = [("openrouter", 1, 20.0), ("routstr", 1, 10.0), ("zai", 1, 30.0)]


class Node:
    def __init__(self, tmpdir: Path):
        self.ladder = tmpdir / "t470_ladder.json"
        self.ladder.write_bytes(json.dumps(
            {"ladder": [{"name": n, "enabled": bool(e), "weight": w,
                         "candidate": True} for n, e, w in PROVIDERS]},
            indent=2, sort_keys=True).encode())
        self.uri = (f"file:f13p17{os.getpid()}x{id(self):x}"
                    f"?mode=memory&cache=shared")
        con = self._connect()
        con.execute("CREATE TABLE models (name TEXT PRIMARY KEY, "
                    "enabled INTEGER NOT NULL)")
        for n in ADVERTISED:
            con.execute("INSERT INTO models VALUES (?, 1)", (n,))
        for n in OP_DISABLED:
            con.execute("INSERT INTO models VALUES (?, 0)", (n,))
        con.execute("CREATE TABLE upstream_providers (name TEXT PRIMARY KEY, "
                    "enabled INTEGER NOT NULL, weight REAL NOT NULL)")
        for row in PROVIDERS:
            con.execute("INSERT INTO upstream_providers VALUES (?, ?, ?)", row)
        con.commit()
        self._con = con
        self.calls = []
        self.deadline_log = []
        self.ssh_down = False
        self.pull_lands = True
        self.relist_lands = True
        self.verify_garbage = False
        self.round_trip_s = 0.0
        shim = types.ModuleType("sqlite3")
        shim.connect = self._connect
        self._sqlite3 = shim

    def _connect(self, _path=None):
        return sqlite3.connect(self.uri, uri=True)

    def _import(self, name, globals=None, locals=None, fromlist=(), level=0):
        if name == "sqlite3":
            return self._sqlite3
        return builtins.__import__(name, globals, locals, fromlist, level)

    def models_map(self):
        return dict(self._con.execute("SELECT name, enabled FROM models"))

    def providers(self):
        return list(self._con.execute("SELECT name, enabled, weight FROM "
                                      "upstream_providers ORDER BY name"))

    def ladder_bytes(self):
        return self.ladder.read_bytes()

    def kinds(self):
        return [k for k, _ in self.calls]

    def execute(self, kind, payload):
        revert = None
        if kind == "pull" and not self.pull_lands:
            revert = self.models_map()
        if kind == "relist" and not self.relist_lands:
            revert = self.models_map()
        out = io.StringIO()
        g = {"__builtins__": {"__import__": self._import, "print": print}}
        with contextlib.redirect_stdout(out):
            exec(payload, g)  # noqa: S102 — executing OUR OWN payload builders
        if revert is not None:
            con = self._connect()
            for name, en in revert.items():
                con.execute("UPDATE models SET enabled=? WHERE name=?",
                            (en, name))
            con.commit()
            con.close()
        return json.loads(out.getvalue().strip().splitlines()[-1])


class Clock:
    def __init__(self):
        self._m = 0.0

    def monotonic(self):
        return self._m

    @staticmethod
    def time():
        return REAL_TIME.time()      # wall clock stays REAL (mtime guard)

    def advance(self, s):
        self._m += s


class Backend:
    def __init__(self, node, clock):
        self.node = node
        self.clock = clock

    def pull(self, dry_run=False, deadline=None):
        return self._rt("pull", rd.pull_listing_payload(), dry_run, deadline)

    def verify(self, dry_run=False, deadline=None):
        return self._rt("verify", rd.verify_pull_payload(), dry_run, deadline)

    def relist(self, names=None, dry_run=False, deadline=None):
        return self._rt("relist", rd.relist_payload(names or []), dry_run,
                        deadline)

    def _rt(self, kind, payload, dry_run, deadline):
        if deadline is not None:
            self.node.deadline_log.append({
                "kind": kind, "t": self.clock.monotonic(),
                "remaining": deadline - self.clock.monotonic(),
                "timeout": min(rd.SSH_TIMEOUT_S,
                               max(deadline - self.clock.monotonic(), 0.0))})
        if dry_run:
            return {"ok": True, "dry_run": True, "action": kind}
        self.node.calls.append((kind, payload))
        if self.node.ssh_down:
            return {"ok": False, "action": kind, "rc": 255,
                    "error": "ssh: connect to host: Connection refused"}
        if kind == "verify" and self.node.verify_garbage:
            return {"ok": True, "action": kind, "rc": 0,
                    "stdout": "not json at all"}
        data = self.node.execute(kind, payload)
        self.clock.advance(self.node.round_trip_s)
        return {"action": kind, "rc": 0, **data, "ok": data.get("ok") is True}


class Rig:
    def __init__(self, name):
        self.dir = SCRATCH / name
        self.dir.mkdir(parents=True, exist_ok=True)
        self.node = Node(self.dir)
        self.clock = Clock()
        self.backend = Backend(self.node, self.clock)
        self.state = self.dir / "state.json"
        self.override = self.dir / "override.marker"     # absent
        rd._SshBackend = lambda t, c: self.backend
        rd.time = self.clock

    def run(self, *argv, preds=None):
        full = ["--state", str(self.state), "--override", str(self.override)]
        if preds is not None:
            full += ["--preds", str(preds)]
        full += list(argv)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = rd.main(full)
        raw = out.getvalue()
        return rc, (json.loads(raw) if raw.strip() else {}), raw

    def write_preds(self, preds, name="preds.json"):
        p = self.dir / name
        p.write_text(json.dumps(preds))
        return p

    def age(self, path, seconds=3600):
        old = REAL_TIME.time() - seconds
        os.utime(path, (old, old))
        return path

    def put_state(self, **kw):
        self.state.write_text(json.dumps(kw))
        return self.state


def pred(key="zai", window="1h", hours=10.0, unc=0.05):
    return {"key": key, "window": window, "exhausts_in_hours": hours,
            "uncertainty": unc}


# ── A7: ladder isolation measured by execution ───────────────────────────
r = Rig("A7")
ladder_before = r.node.ladder_bytes()
prov_before = r.node.providers()
rc, out, _ = r.run("--manual")
check("A7a", "manual delist confirms and returns 0",
      rc == 0 and out.get("action") == "delist"
      and out.get("confirmed") is True, f"rc={rc} action={out.get('action')}")
check("A7b", "ladder artifact byte-identical across the delist",
      r.node.ladder_bytes() == ladder_before,
      f"{len(ladder_before)} B before, {len(r.node.ladder_bytes())} B after")
check("A7c", "upstream_providers rows identical and routstr still enabled",
      r.node.providers() == prov_before
      and any(n == "routstr" and e == 1 for n, e, _ in r.node.providers()),
      f"{r.node.providers()}")
mm = r.node.models_map()
check("A7d", "every advertised row disabled after the delist",
      all(mm[n] == 0 for n in ADVERTISED), f"{mm}")
check("A7e", "the operator's pre-disabled row stays disabled",
      all(mm[n] == 0 for n in OP_DISABLED), f"{mm}")
check("A7f", "no executed payload named upstream_providers",
      all("upstream_providers" not in p for _, p in r.node.calls),
      f"{r.node.kinds()}")

# ── A8: relist is the exact inverse ──────────────────────────────────────
rc, out, _ = r.run("--relist")
mm = r.node.models_map()
check("A8a", "scoped relist restores exactly the captured names",
      rc == 0 and out.get("action") == "relist"
      and all(mm[n] == 1 for n in ADVERTISED), f"rc={rc} {mm}")
check("A8b", "relist does not resurrect the operator's disabled row",
      all(mm[n] == 0 for n in OP_DISABLED), f"{mm}")
check("A8c", "ladder still byte-identical after the relist",
      r.node.ladder_bytes() == ladder_before, f"{len(ladder_before)} B")

# ── A9: blanket relist requires the explicit opt-in ──────────────────────
r2 = Rig("A9")
st = r2.state
st.write_text(json.dumps({"ts": 1.0, "delisted": True}))
before_bytes = st.read_bytes()
calls_before = len(r2.node.calls)
rc, out, _ = r2.run("--relist")
check("A9a", "blanket relist refused before any remote call",
      rc == 1 and out.get("action") == "relist_refused"
      and len(r2.node.calls) == calls_before, f"rc={rc} {out.get('action')}")
check("A9b", "refusal leaves the state file byte-identical",
      st.read_bytes() == before_bytes, "state unchanged")
rc, out, _ = r2.run("--relist", "--relist-any")
mm = r2.node.models_map()
check("A9c", "LOW: --relist-any does re-enable every row incl. the operator's",
      rc == 0 and all(v == 1 for v in mm.values()), f"rc={rc} {mm}")

# ── A10: dry-run purity is conditional on FIRING (MEDIUM, re-measured) ──
r3 = Rig("A10q")
r3.state.write_text(json.dumps({"ts": 1.0, "delisted": False,
                                "snapshot": {"zai\x1f1h": 12.0}}))
quiet = r3.write_preds([pred(hours=11.0, unc=0.05)])   # move 1.0 < 2.0
rc, out, _ = r3.run("--dry-run", preds=quiet)
st_q = rd.load_state(str(r3.state))
check("A10a", "MEDIUM: a QUIET dry run refreshes the stored baseline "
              "(no --dry-run guard on :651-654)",
      rc == 0 and out.get("action") == "none"
      and st_q.get("snapshot", {}).get("zai\x1f1h") == 11.0
      and "last_dry_run" not in st_q,
      f"rc={rc} snapshot={st_q.get('snapshot')} "
      f"last_dry_run={'last_dry_run' in st_q}")
r4 = Rig("A10f")
r4.state.write_text(json.dumps({"ts": 1.0, "delisted": False,
                                "snapshot": {"zai\x1f1h": 12.0}}))
fire = r4.write_preds([pred(hours=9.0, unc=0.05)])     # move 3.0 >= 2.0
rc, out, _ = r4.run("--dry-run", preds=fire)
st_f = rd.load_state(str(r4.state))
check("A10b", "a FIRING dry run consumes no baseline and flips no flag",
      rc == 0 and out.get("action") == "delist"
      and st_f.get("snapshot", {}).get("zai\x1f1h") == 12.0
      and st_f.get("delisted") is False
      and st_f.get("last_dry_run", {}).get("action") == "delist"
      and r4.node.calls == [],
      f"rc={rc} snapshot={st_f.get('snapshot')} calls={r4.node.kinds()}")

# ═══ B — finding 2: confirmation from an independent re-fetch ════════════
print("== B: finding 2 — confirmation ==")

vp = rd.verify_pull_payload()
check("B1a", "verify payload is read-only (SELECT COUNT, no DML)",
      "SELECT COUNT(*) FROM models WHERE enabled=1" in vp
      and not re.search(r"\b(UPDATE|INSERT|DELETE|DROP|REPLACE)\b", vp),
      vp[:60] + "…")

r5 = Rig("B2")
r5.node.pull_lands = False                    # pull lies: self-reports ok
rc, out, _ = r5.run("--manual")
st5 = rd.load_state(str(r5.state))
check("B2a", "a pull that lies is refuted by the re-fetch",
      rc == 1 and out.get("action") == "delist_failed"
      and out.get("verify", {}).get("count") == 3
      and out.get("confirmed") is not True,
      f"rc={rc} action={out.get('action')} verify={out.get('verify')}")
check("B2b", "the round-trip sequence is [pull, verify, pull, verify]",
      r5.node.kinds() == ["pull", "verify", "pull", "verify"],
      f"{r5.node.kinds()}")
check("B2c", "the refuted run sets no durable delist flag",
      st5.get("delisted") is not True and st5.get("consecutive_failures") == 1,
      f"delisted={st5.get('delisted')} fails={st5.get('consecutive_failures')}")

r6 = Rig("B3")
r6.node.verify_garbage = True
rc, out, _ = r6.run("--manual")
check("B3a", "a verify result carrying no count fails closed",
      rc == 1 and out.get("action") == "delist_failed", f"rc={rc}")

r7 = Rig("B3b")
r7.node.ssh_down = True
rc, out, _ = r7.run("--manual")
check("B3b", "a dead transport fails closed after the bounded retry, and "
             "never reaches verify",
      rc == 1 and r7.node.kinds() == ["pull", "pull"] and out.get("action") == "delist_failed",
      f"rc={rc} kinds={r7.node.kinds()}")

r8 = Rig("B4")
r8.state.write_text(json.dumps({"ts": 1.0, "delisted": False,
                                "snapshot": {"zai\x1f1h": 12.0}}))
r8.node.pull_lands = False
fire8 = r8.write_preds([pred(hours=9.0, unc=0.05)])
rc, out, _ = r8.run(preds=fire8)
st8 = rd.load_state(str(r8.state))
check("B4a", "failure does not consume the acceleration baseline "
             "(same trigger re-fires)",
      rc == 1 and st8.get("snapshot", {}).get("zai\x1f1h") == 12.0
      and "last_pull_error" in st8,
      f"rc={rc} snapshot={st8.get('snapshot')}")
check("B4b", "retry is bounded by MAX_PULL_ATTEMPTS == 2",
      rd.MAX_PULL_ATTEMPTS == 2 and r8.node.kinds().count("pull") == 2,
      f"{rd.MAX_PULL_ATTEMPTS} / {r8.node.kinds()}")

r9 = Rig("B6")
r9.run("--manual")                            # establish a delisted state
r9.node.relist_lands = False                  # relist lies: self-reports ok
rc, out, _ = r9.run("--relist")
st9 = rd.load_state(str(r9.state))
mm9 = r9.node.models_map()
check("B6a", "MEDIUM: a lying relist reports success (rc 0) while the "
             "listing is NOT restored",
      rc == 0 and out.get("action") == "relist"
      and all(mm9[n] == 0 for n in ADVERTISED),
      f"rc={rc} action={out.get('action')} models={mm9}")
rc, out, _ = r9.run("--relist")
check("B6b", "MEDIUM: pulled_models was popped, so the scoped relist is "
             "afterwards refused",
      rc == 1 and out.get("action") == "relist_refused",
      f"rc={rc} action={out.get('action')} names={st9.get('pulled_models')}")
r9.node.relist_lands = True                   # DISARM the injected fault first
rc, out, _ = r9.run("--relist", "--relist-any")
mm9 = r9.node.models_map()
check("B6c", "MEDIUM: the only remaining route re-enables the operator's row",
      rc == 0 and all(v == 1 for v in mm9.values()), f"{mm9}")

r10 = Rig("B7")
r10.state.write_text(json.dumps({"ts": 1.0, "delisted": False,
                                 "snapshot": {"zai\x1f1h": 12.0}}))
fire10 = r10.write_preds([pred(hours=9.0, unc=0.05)])
rc, out, _ = r10.run("--dry-run", preds=fire10)
check("B7a", "LOW: a firing dry run produces no `confirmed` key at all "
             "(only :685 writes it)",
      rc == 0 and "confirmed" not in out and "verified_count" not in out,
      f"keys={sorted(out)}")
check("B7b", "no remote round trip and no verify on the dry-run path",
      r10.node.calls == [], f"{r10.node.kinds()}")

check("B8a", "LOW: verify() is a method of the same _SshBackend used for the "
             "pull, so confirmation shares the host transport",
      any(isinstance(n, ast.ClassDef) and n.name == "_SshBackend"
          and any(isinstance(b, ast.FunctionDef) and b.name == "verify"
                  for b in n.body) for n in TREE.body)
      and "backend.verify(" in SRC,
      "verify is a _SshBackend method; main() calls backend.verify(...)")

# ═══ C — finding 3: fail-safe on absent / garbage / stale signals ════════
print("== C: finding 3 — fail-safe ==")

r11 = Rig("C1")
rc, out, _ = r11.run()
check("C1a", "no --preds at all: quiet, rc 0, zero round trips",
      rc == 0 and out.get("action") == "none" and r11.node.calls == [],
      f"rc={rc} action={out.get('action')}")
r12 = Rig("C1b")
f12 = r12.write_preds([pred(hours=1.0, unc=0.05)])
rc, out, _ = r12.run(preds=f12)
check("C1b", "no stored baseline: acceleration cannot fire (first run quiet)",
      rc == 0 and out.get("action") == "none" and out.get("fire") is False,
      f"rc={rc} fire={out.get('fire')}")

r13 = Rig("C2")
bad = r13.dir / "garbage.json"
bad.write_text("{not json at all")
rc, out, _ = r13.run(preds=bad)
check("C2a", "unparseable feed: preds_error true, rc 1, zero round trips",
      rc == 1 and out.get("preds_error") is True and out.get("action") == "none"
      and r13.node.calls == [], f"rc={rc} {out.get('preds_error')}")
mixed = r13.write_preds([None, "x", 1, pred(unc=0.9)], "mixed.json")
rc, out, _ = r13.run(preds=mixed)
check("C2b", "non-dict rows are dropped, valid rows still evaluate",
      rc == 0 and out.get("action") == "delist",
      f"rc={rc} action={out.get('action')}")
typed = r13.write_preds([{"key": "zai", "window": "1h",
                          "exhausts_in_hours": "3", "uncertainty": True},
                         {"key": None, "window": None,
                          "exhausts_in_hours": None, "uncertainty": None}],
                        "typed.json")
r13b = Rig("C2c")
rc, out, _ = r13b.run(preds=typed)
check("C2c", "wrong-typed fields never fire and never crash",
      rc == 0 and out.get("action") == "none" and r13b.node.calls == [],
      f"rc={rc} action={out.get('action')}")
r13c = Rig("C2d")
empty = r13c.write_preds([], "empty.json")
rc, out, _ = r13c.run(preds=empty)
check("C2d", "LOW: a valid-but-empty feed is reported as a feed error",
      rc == 1 and out.get("preds_error") is True and out.get("action") == "none",
      f"rc={rc} preds_error={out.get('preds_error')}")

fr = Rig("C3")
f = fr.write_preds([pred()])
T = os.path.getmtime(f)
cases = {"age 0": (f, T), "exact 1800": (f, T + 1800),
         "1800.001": (f, T + 1800.001), "3600": (f, T + 3600),
         "future mtime": (f, T - 10)}
stale_map = {k: rd.feed_is_stale(p, now=n) for k, (p, n) in cases.items()}
missing = fr.dir / "absent.json"
stale_map["missing"] = rd.feed_is_stale(str(missing), now=T)
check("C3a", "staleness boundary is INCLUSIVE; future mtime and missing "
             "file are stale",
      stale_map == {"age 0": False, "exact 1800": False, "1800.001": True,
                    "3600": True, "future mtime": True, "missing": True},
      f"{stale_map}")
check("C3b", "guard shape is `not (0 <= age <= max_age_s)` with OSError -> "
             "stale and STALENESS_S == 1800",
      "not (0 <= age <= max_age_s)" in SRC and rd.STALENESS_S == 1800
      and LINES[493].strip() == "return not (0 <= age <= max_age_s)"
      and LINES[494].strip() == "except OSError:",
      f"STALENESS_S={rd.STALENESS_S} L495={LINES[493].strip()!r} "
      f"L496={LINES[494].strip()!r}")

r14 = Rig("C4")
r14.state.write_text(json.dumps({"ts": 1.0, "delisted": False,
                                 "snapshot": {"zai\x1f1h": 100.0}}))
stale = r14.age(r14.write_preds([pred(hours=1.0, unc=0.9)], "stale.json"))
rc, out, _ = r14.run(preds=stale)
st14 = rd.load_state(str(r14.state))
check("C4a", "a stale feed with firing numbers fires nothing and refreshes "
             "nothing (compared as PARSED state — save_state re-emits the "
             "file with indent=2/sort_keys, so raw bytes always differ)",
      rc == 1 and out.get("preds_stale") is True
      and out.get("action") == "none" and r14.node.calls == []
      and st14.get("snapshot") == {"zai\x1f1h": 100.0}
      and st14.get("delisted") is False,
      f"rc={rc} stale={out.get('preds_stale')} calls={r14.node.kinds()} "
      f"snapshot={st14.get('snapshot')}")
r15 = Rig("C4b")
r15.state.write_text(json.dumps({"ts": 1.0, "delisted": False,
                                 "snapshot": {"zai\x1f1h": 100.0}}))
fresh = r15.write_preds([pred(hours=1.0, unc=0.9)], "fresh.json")
rc, out, _ = r15.run(preds=fresh)
check("C4b", "the SAME numbers with a fresh mtime DO delist (the guard, not "
             "an absent signal, is what stopped it)",
      rc == 0 and out.get("action") == "delist",
      f"rc={rc} action={out.get('action')}")

r16 = Rig("C5")
r16.state.write_text(json.dumps({"ts": 1.0, "delisted": False,
                                 "snapshot": {"zai\x1f1h": 100.0}}))
stale2 = r16.age(r16.write_preds([pred(hours=1.0, unc=0.9)], "s2.json"))
rc, out, _ = r16.run("--manual", preds=stale2)
st16 = rd.load_state(str(r16.state))
check("C5a", "the manual override is never gated on freshness (it delists "
             "with preds_stale reported alongside the action)",
      rc == 0 and out.get("action") == "delist"
      and out.get("preds_stale") is True and st16.get("delisted") is True,
      f"rc={rc} stale={out.get('preds_stale')} delisted={st16.get('delisted')}")
check("C5b", "the stale feed still did not refresh the acceleration baseline",
      st16.get("snapshot", {}).get("zai\x1f1h") == 100.0,
      f"snapshot={st16.get('snapshot')}")

# ── C6: the action window fails closed (real _SshBackend, mocked subprocess)
recorded = []


def fake_run(cmd, capture_output=False, text=False, timeout=None, **kw):
    recorded.append(timeout)

    class P:
        returncode = 0
        stdout = '{"ok": true}'
        stderr = ""
    return P()


rd.subprocess.run = fake_run
rd.time = REAL_TIME
be = PROD_BACKEND("host", "container")
res = be._run("x", dry_run=False, action="pull",
              deadline=REAL_TIME.monotonic() - 1.0)
check("C6a", "an exhausted budget fails closed and spawns nothing",
      res.get("ok") is False and "budget" in res.get("error", "")
      and recorded == [], f"{res} recorded={recorded}")
be._run("x", dry_run=False, action="pull",
        deadline=REAL_TIME.monotonic() + 5.0)
# detail ROUNDED: the raw clamp comes off the live wall clock and would make
# the transcript digest differ between two otherwise-identical runs.
check("C6b", "per-round-trip timeout is clamped to the remaining budget",
      abs(recorded[-1] - 5.0) <= 0.2, f"timeout={round(recorded[-1], 1)}")
be._run("x", dry_run=False, action="pull",
        deadline=REAL_TIME.monotonic() + 1000.0)
check("C6c", "timeout is capped at SSH_TIMEOUT_S",
      recorded[-1] == rd.SSH_TIMEOUT_S, f"{recorded[-1]}")
check("C6d", "SLA arithmetic holds: 240 + 60 == 300 and pull+verify fits",
      rd.TRIGGER_ACTION_WINDOW_S == 300
      and rd.POLL_CADENCE_S + rd.ACTION_BUDGET_S == 300
      and 2 * rd.SSH_TIMEOUT_S <= rd.ACTION_BUDGET_S,
      f"{rd.POLL_CADENCE_S}+{rd.ACTION_BUDGET_S}=300")

r17 = Rig("C7")
r17.node.ssh_down = True
rcs = [r17.run("--manual")[0] for _ in range(3)]
st17 = rd.load_state(str(r17.state))
raw17 = r17.state.read_text()
check("C7a", "3 consecutive failed runs: rc [1,1,3] and durable BLOCKED",
      rcs == [1, 1, 3] and st17.get("blocked") is True
      and st17.get("consecutive_failures") == rd.BREAKER_THRESHOLD
      and '"blocked": true' in raw17, f"rcs={rcs}")
check("C7b", "3 runs x (attempt + bounded retry) == 6 pulls, verify never "
             "reached",
      r17.node.kinds() == ["pull"] * 6, f"{r17.node.kinds()}")
r17.node.ssh_down = False
n_before = len(r17.node.calls)
rc, out, _ = r17.run("--manual")
check("C7c", "an open breaker refuses ALL remote action with rc 3",
      rc == 3 and out.get("action") == "blocked"
      and len(r17.node.calls) == n_before, f"rc={rc}")
rc, out, _ = r17.run("--unblock", "--manual")
check("C7d", "--unblock clears the breaker and the next run succeeds",
      rc == 0 and out.get("action") == "delist", f"rc={rc}")

r18 = Rig("C7e")
r18.node.ssh_down = True
rcs = [r18.run("--manual", "--dry-run")[0] for _ in range(4)]
check("C7e", "dry runs never count toward the breaker",
      rcs == [0, 0, 0, 0]
      and rd.load_state(str(r18.state)).get("blocked") is not True,
      f"rcs={rcs}")

r19 = Rig("C7f")
r19.run("--manual")
r19.node.ssh_down = True
rcs = [r19.run("--relist")[0] for _ in range(4)]
st19 = rd.load_state(str(r19.state))
check("C7f", "LOW: a failed RELIST never advances the breaker (VALUE check — "
             "the keys are deliberately kept greppable)",
      rcs == [1, 1, 1, 1] and st19.get("consecutive_failures") == 0
      and st19.get("blocked") is False and "last_pull_error" in st19,
      f"rcs={rcs} fails={st19.get('consecutive_failures')} "
      f"blocked={st19.get('blocked')}")

r20 = Rig("C8")
foreign = r20.write_preds([pred(key="other-provider", unc=0.9)], "foreign.json")
rc_u, out_u, _ = r20.run(preds=foreign)
rc_s, out_s, _ = r20.run("--preds-key", "routstr", preds=foreign)
check("C8a", "LOW: an UNSCOPED run lets a foreign key's variance spike pull "
             "the routstr SALE",
      rc_u == 0 and out_u.get("action") == "delist",
      f"rc={rc_u} action={out_u.get('action')}")
check("C8b", "the same feed scoped to `routstr` is quiet",
      rc_s == 0 and out_s.get("action") == "none",
      f"rc={rc_s} action={out_s.get('action')}")
check("C8c", "evaluate_triggers exposes no key parameter to forward "
             "--preds-key (scoping stops at :594-597)",
      "key" not in [a.arg for a in next(
          n for n in TREE.body if isinstance(n, ast.FunctionDef)
          and n.name == "evaluate_triggers").args.args],
      "args=" + str([a.arg for a in next(
          n for n in TREE.body if isinstance(n, ast.FunctionDef)
          and n.name == "evaluate_triggers").args.args]))
r20b = Rig("C8d")
typo = r20b.write_preds([pred(key="zai")], "typo.json")
rc, out, _ = r20b.run("--preds-key", "routtsr", preds=typo)
check("C8d", "LOW: a --preds-key that matches nothing is silent and looks "
             "like a healthy quiet run",
      rc == 0 and out.get("preds_error") is False
      and out.get("preds_stale") is False and out.get("action") == "none",
      f"rc={rc} preds_error={out.get('preds_error')}")

# ── C9: pure helpers are not type-hardened ───────────────────────────────
raised = None
try:
    rd.evaluate_triggers([None, "x", 1], None)
except Exception as exc:                       # noqa: BLE001
    raised = type(exc).__name__
check("C9a", "LOW: the pure helpers are not type-hardened when called "
             "directly (guard lives in _read_preds)",
      raised == "AttributeError", f"raised {raised}")
check("C9b", "_read_preds drops non-dicts one layer up (:478-479)",
      "if isinstance(data, list)" in LINES[477]
      and "isinstance(d, dict)" in LINES[478],
      f"{LINES[477].strip()} | {LINES[478].strip()}")

r21 = Rig("C10")
both = r21.write_preds([pred(key="zai", window="1h", hours=10.0, unc=0.05),
                        pred(key="other", window="1h", hours=10.0, unc=0.05)],
                       "both.json")
r21.run(preds=both)
st21a = rd.load_state(str(r21.state)).get("snapshot", {})
rc, out, _ = r21.run("--preds-key", "zai", preds=both)
st21b = rd.load_state(str(r21.state)).get("snapshot", {})
check("C10a", "LOW: a scoped run narrows the stored baseline to that key, "
              "discarding the other key's snapshot",
      sorted(st21a) == ["other\x1f1h", "zai\x1f1h"]
      and sorted(st21b) == ["zai\x1f1h"],
      f"unscoped={sorted(st21a)} scoped={sorted(st21b)}")

# ═══ D — review-record audit ═════════════════════════════════════════════
print("== D: review record ==")

doc_txt = DELIVERABLE.read_text(encoding="utf-8") if DELIVERABLE.exists() else ""
heads = re.findall(r"(?m)^## (.+)$", doc_txt)
check("D1a", "deliverable exists", DELIVERABLE.exists(), str(DELIVERABLE))
check("D1b", "exactly 3 `## ` finding sections",
      len(re.findall(r"(?m)^## ", doc_txt)) == 3, f"headings={heads}")
check("D1c", "every finding section carries a severity tag",
      len(re.findall(r"severity:", doc_txt)) >= 3,
      f"{len(re.findall(r'severity:', doc_txt))} severity tags")

CITE_FILES = {"routstr_delist.py": SCRIPT, "contract": CONTRACT,
              "tests": MAIN_TESTS, "docs": DOC}
unresolved = []
counts = {}
for tok, ln in re.findall(r"(routstr_delist\.py|contract|tests|docs):(\d+)",
                          doc_txt):
    counts[tok] = counts.get(tok, 0) + 1
    if int(ln) > nlines(CITE_FILES[tok]):
        unresolved.append(f"{tok}:{ln}")
check("D2a", "every file:line citation resolves within the file it names",
      unresolved == [],
      f"{sum(counts.values())} citations {counts} unresolved={unresolved}")
m = re.search(r"citation-count:\s*total=(\d+)\s+script=(\d+)\s+contract=(\d+)"
              r"\s+tests=(\d+)\s+docs=(\d+)", doc_txt)
actual = {
    "total": len(re.findall(r"(?:routstr_delist\.py|contract|tests|docs):\d+",
                            doc_txt)),
    "script": len(re.findall(r"routstr_delist\.py:\d+", doc_txt)),
    "contract": len(re.findall(r"contract:\d+", doc_txt)),
    "tests": len(re.findall(r"tests:\d+", doc_txt)),
    "docs": len(re.findall(r"docs:\d+", doc_txt)),
}
check("D2b", "the citation-count preamble comment matches the citations "
             "actually present in the file",
      bool(m) and [int(g) for g in m.groups()] == [
          actual["total"], actual["script"], actual["contract"],
          actual["tests"], actual["docs"]]
      and int(m.group(1)) == sum(int(g) for g in m.groups()[1:]),
      f"declared={m.groups() if m else None} actual={actual}")
check("D3a", "the artifact-path report names the absent contract markdown "
             "as HIGH",
      "routstr_delist_contract.md" in doc_txt and "HIGH" in doc_txt
      and "MISSING" in doc_txt.upper(), "present")
ordinal = re.search(r"(\w+)\s+independent offload pass", doc_txt)
check("D4a", "the disclosure states the pass ordinal",
      bool(ordinal) and ordinal.group(1).lower() == "seventeenth",
      ordinal.group(0) if ordinal else "absent")
check("D4b", "the disclosure records the rewrite (not an append) and the "
             "disclosed cost",
      "rewritten in place" in doc_txt and "Disclosed cost" in doc_txt,
      "present")
check("D5a", "repo deliverable and bot mirror are byte-identical",
      BOT_DELIVERABLE.exists() and md5(BOT_DELIVERABLE) == md5(DELIVERABLE),
      f"repo {md5(DELIVERABLE) if DELIVERABLE.exists() else 'n/a'} "
      f"bot {md5(BOT_DELIVERABLE) if BOT_DELIVERABLE.exists() else 'n/a'}")
per_sec = [len(re.findall(r"(?:routstr_delist\.py|contract|tests|docs):\d+", s))
           for s in re.split(r"(?m)^## ", doc_txt)[1:]]
check("D6a", "at least 5 file:line citations inside each finding section",
      bool(per_sec) and min(per_sec) >= 5, f"{per_sec}")

# ── D7: the headings' own residual counts must match what they enumerate ─
secs = re.split(r"(?m)^## ", doc_txt)[1:]
low_counts = [len(re.findall(r"\*\*(?:Gap|Residual) — LOW", s)) for s in secs]
med_counts = [len(re.findall(r"\*\*(?:Gap|Residual) — MEDIUM", s)) for s in secs]
claims = []
for s in secs:
    m = re.search(r"severity: \*\*(\w+)\*\*\s*\(([^)]*)\)", s)
    claims.append(m.group(2) if m else "")
declared = []
for c in claims:
    lo = re.search(r"(\d+)\s+LOW", c)
    me = re.search(r"(\d+)\s+MEDIUM", c)
    declared.append((int(me.group(1)) if me else 0,
                     int(lo.group(1)) if lo else 0))
check("D7a", "each finding heading's declared LOW count equals the number of "
             "LOW items it enumerates",
      [d[1] for d in declared] == low_counts,
      f"declared={[d[1] for d in declared]} enumerated={low_counts} "
      f"claims={claims}")
check("D7b", "each finding heading's declared MEDIUM count equals the number "
             "of MEDIUM items it enumerates",
      [d[0] for d in declared] == med_counts,
      f"declared={[d[0] for d in declared]} enumerated={med_counts}")

# ── tally ────────────────────────────────────────────────────────────────
print()
body = []
for cid, label, ok, detail in CHECKS:
    body.append(f"[{'PASS' if ok else 'FAIL'}] {cid:<5} {label}"
                + (f"   -- {detail}" if detail else ""))
for line in body:
    print(line)
n_pass = sum(1 for c in CHECKS if c[2])
print(f"\n{len(CHECKS)} checks: {n_pass} PASS, {len(CHECKS) - n_pass} FAIL")
print(f"transcript sha256: {hashlib.sha256(chr(10).join(body).encode()).hexdigest()}")
raise SystemExit(0 if n_pass == len(CHECKS) else 1)
