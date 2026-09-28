#!/usr/bin/env python3
"""Fresh hermetic probe harness — routstr delist findings 1-3, offload pass 16.

Written for this pass (2026-09-28); NOT derived from probe_f13_pass11..15.py.
Read-only with respect to every reviewed artifact: it only reads the script,
the two suites, the design doc and the deliverable, and executes the module's
OWN payload builders against an in-process stand-in sell node.

What it replaces: only the ssh boundary. The stand-in node holds a live
`models` (SALE listing) table, a live `upstream_providers` (provider ladder)
table and a ladder-artifact file on disk, so "the ladder is untouched" is
measured by execution rather than asserted from prose. No network, no
subprocess, no file-backed sqlite (file sqlite/fcntl can block forever on this
host), no scratch under /tmp (5.5 G tmpfs, full).

Scope: A = finding 1 (safety), B = finding 2 (confirmation), C = finding 3
(fail-safe), D = review-record audit (shape / citation resolution / mirror).

Run it twice; the printed tally must be byte-identical in both orders.
Doc target override: F13_DOC=<path>  (default: repo docs/reviews/findings_1_3.md)
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
# .../<repo>/docs/reviews/routstr_f13_probes/probe_f13_pass16.py
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

# scratch is keyed by directory, so it MUST be wiped at import or a second
# invocation re-reads the first run's durable state.
SCRATCH = Path.home() / ".cache" / "f13-pass16" / "scratch"
shutil.rmtree(SCRATCH, ignore_errors=True)
SCRATCH.mkdir(parents=True, exist_ok=True)
(SCRATCH.parent / "tmp").mkdir(parents=True, exist_ok=True)

os.fsync = lambda fd: None            # this host can stall forever in fsync

sys.path.insert(0, str(REPO / "src"))
import routstr_delist as rd  # noqa: E402

# the rigs below swap rd._SshBackend, so capture the REAL production class now
PROD_BACKEND = rd._SshBackend

# ── check plumbing ────────────────────────────────────────────────────────
CHECKS: list[tuple[str, str, bool, str]] = []


def check(cid, label, ok, detail=""):
    CHECKS.append((cid, label, bool(ok), str(detail)))


def md5(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


def nlines(p: Path) -> int:
    return p.read_bytes().count(b"\n")


# ── source / AST measurement ──────────────────────────────────────────────
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


def collect_consts(node, out):
    """Record every executable string literal and do NOT descend into it.

    Descending would double-count an implicitly-concatenated payload (once as
    the JoinedStr, once per inner Constant) — the pass-11 over-count trap.
    """
    for child in ast.iter_child_nodes(node):
        if isinstance(child, ast.Constant) and isinstance(child.value, str):
            out.append((child.lineno, child.value))
        elif isinstance(child, ast.JoinedStr):
            out.append((child.lineno, joined_text(child)))
        else:
            collect_consts(child, out)


CONSTS: list[tuple[int, str]] = []
collect_consts(TREE, CONSTS)
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

# ═══ A — finding 1: safety (SALE delist vs provider / ladder) ═════════════
print("== A: finding 1 — safety ==")

# A0 provenance / environment
check("A0a", "deployed script byte-identical to repo src",
      md5(BOT_SCRIPT) == md5(SCRIPT),
      f"src md5 {md5(SCRIPT)} ({nlines(SCRIPT)} lines) bot {md5(BOT_SCRIPT)}")
check("A0b", "bot tests copy byte-identical to repo contract suite",
      md5(BOT_TESTS) == md5(CONTRACT),
      f"{md5(CONTRACT)} ({nlines(CONTRACT)} lines)")
check("A0c", "bot doc byte-identical to repo doc",
      md5(BOT_DOC) == md5(DOC),
      f"{md5(DOC)} ({nlines(DOC)} lines)")
check("A0d", "contract markdown ABSENT at the dispatched bot path",
      not BOT_CONTRACT.exists(), f"exists={BOT_CONTRACT.exists()}")

# A1 SQL inventory on the parsed source
sql_consts = [(ln, v) for ln, v in EXEC_CONSTS
              if re.search(r"\b(UPDATE|SELECT)\b", v) and "models" in v]
check("A1a", "executable SQL-bearing string literals == 5",
      len(sql_consts) == 5, f"lines {[ln for ln, _ in sql_consts]}")
tables = set()
for _, v in sql_consts:
    tables |= set(re.findall(r"\b(?:FROM|INTO|UPDATE|JOIN)\s+([a-zA-Z_]+)", v))
check("A1b", "materialised table set is exactly ['models']",
      tables == {"models"}, f"tables {sorted(tables)}")
verbs = []
for _, v in sql_consts:
    verbs += re.findall(r"\b(UPDATE|SELECT)\b", v)
check("A1c", "mutating verbs are exactly 3 UPDATEs (rest are SELECTs)",
      verbs.count("UPDATE") == 3 and verbs.count("SELECT") == 2,
      f"{sorted(verbs)}")

# A2 upstream_providers exposure
mentions = [i + 1 for i, l in enumerate(LINES) if "upstream_providers" in l]
check("A2a", "3 upstream_providers mentions, every one inside a docstring",
      len(mentions) == 3 and all(in_docstring(m) for m in mentions),
      f"lines {mentions} docstring-span={[in_docstring(m) for m in mentions]}")
n_exec_naming = [ln for ln, v in EXEC_CONSTS if "upstream_providers" in v]
check("A2b", "0 executable literals name upstream_providers",
      not n_exec_naming,
      f"{len(EXEC_CONSTS)} executable literals inspected, hits {n_exec_naming}")

# A3 subprocess / injection surface
run_sites = [ln for ln, fn in SITES if fn == "subprocess.run"]
shell_true = [c.lineno for c in CALLS if fname(c) == "subprocess.run"
              and any(k.arg == "shell" and getattr(k.value, "value", None) is True
                      for k in c.keywords)]
eval_sites = [ln for ln, fn in SITES if fn in ("eval", "exec")]
check("A3a", "exactly 2 subprocess.run sites (nak publish, ssh docker exec)",
      run_sites == [459, 808], f"{run_sites}")
check("A3b", "shell=True count == 0", not shell_true, f"{shell_true}")
check("A3c", "eval/exec call sites == 0", not eval_sites, f"{eval_sites}")

# A4 remote-command shell quoting
payload = rd.pull_listing_payload()
cmd = rd.build_ssh_docker_cmd("debian@host", "routstr public", payload)
parts = shlex.split(cmd[2])
check("A4a", "ssh argv is 3 elements (host + ONE quoted remote command)",
      len(cmd) == 3 and cmd[0] == "ssh", f"len={len(cmd)}")
check("A4b", "remote command re-parses to the intended argv (space kept)",
      parts[:6] == ["docker", "exec", "routstr public", "python3", "-c",
                    payload],
      f"parts[:4]={parts[:4]}")

# A5 filesystem write surface
os_writes = [(ln, fn) for ln, fn in SITES
             if fn in ("os.makedirs", "os.replace", "os.unlink", "os.remove",
                       "os.rename", "os.chmod", "os.fsync")]
write_opens = [c.lineno for c in CALLS
               if fname(c) == "open" and len(c.args) > 1
               and isinstance(c.args[1], ast.Constant)
               and "w" in str(c.args[1].value)]
read_opens = [c.lineno for c in CALLS
              if fname(c) == "open"
              and (len(c.args) == 1
                   or (isinstance(c.args[1], ast.Constant)
                       and "w" not in str(c.args[1].value)))]
check("A5a", "write surface confined to the state dir (makedirs/replace/unlink/"
             "open-w/fsync)",
      sorted(ln for ln, _ in os_writes) == [229, 234, 235, 243]
      and write_opens == [231],
      f"os {sorted(os_writes)} open-w {write_opens} read-opens {read_opens}")
save_calls = [c for c in CALLS if fname(c) == "save_state"]
discarded = [c.lineno for c in save_calls
             if isinstance(PARENTS.get(id(c)), ast.Expr)]
check("A5b", "every save_state call site discards the return value",
      len(save_calls) == 8 and len(discarded) == len(save_calls),
      f"{len(discarded)}/{len(save_calls)} sites discard, lines {discarded}")
check("A5c", "no write outside save_state: open() modes are 1w:3r",
      len(write_opens) == 1 and len(read_opens) == 3,
      f"w={write_opens} r={read_opens}")

# A6/A7 execution: the stand-in sell node
ADVERTISED = ["gpt-4o", "claude-3-5-sonnet", "llama-3.1-405b"]
OPERATOR_DISABLED = ["operator-disabled-model"]
PROVIDERS = [("openrouter", 1, 20.0), ("routstr", 1, 10.0), ("zai", 1, 30.0)]


class Node:
    def __init__(self, tmpdir: Path):
        self.ladder = tmpdir / "t470_ladder.json"
        self.ladder.write_bytes(json.dumps(
            {"ladder": [{"name": n, "enabled": bool(e), "weight": w,
                         "candidate": True} for n, e, w in PROVIDERS]},
            indent=2, sort_keys=True).encode())
        self.uri = (f"file:f13p16{os.getpid()}x{id(self):x}"
                    f"?mode=memory&cache=shared")
        con = self._connect()
        con.execute("CREATE TABLE models (name TEXT PRIMARY KEY, "
                    "enabled INTEGER NOT NULL)")
        for n in ADVERTISED:
            con.execute("INSERT INTO models VALUES (?, 1)", (n,))
        for n in OPERATOR_DISABLED:
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
        return time.time()          # wall clock stays REAL (mtime guard)

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
        self.override = self.dir / "override.marker"   # absent
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
        old = time.time() - seconds
        os.utime(path, (old, old))
        return path

    def put_state(self, **kw):
        self.state.write_text(json.dumps(kw))
        return self.state


def pred(key="zai", window="1h", hours=10.0, unc=0.05):
    return {"key": key, "window": window, "exhausts_in_hours": hours,
            "uncertainty": unc}


r = Rig("A6")
ladder_before = r.node.ladder_bytes()
prov_before = r.node.providers()
rc, out, _ = r.run("--manual")
check("A6a", "manual delist confirms and returns 0",
      rc == 0 and out.get("action") == "delist" and out.get("confirmed") is True,
      f"rc={rc} action={out.get('action')}")
check("A6b", "ladder artifact byte-identical across the delist",
      r.node.ladder_bytes() == ladder_before,
      f"{len(ladder_before)} B before/after")
check("A6c", "upstream_providers row-identical across the delist",
      r.node.providers() == prov_before,
      f"{[p[0] for p in r.node.providers()]}")
check("A6d", "routstr provider still enabled and still a ladder candidate",
      any(n == "routstr" and e == 1 for n, e, _ in r.node.providers()))
mm = r.node.models_map()
check("A6e", "all advertised rows disabled, operator row stays disabled",
      all(mm[n] == 0 for n in ADVERTISED)
      and all(mm[n] == 0 for n in OPERATOR_DISABLED),
      f"models {mm}")
check("A6f", "no executed payload ever names upstream_providers",
      all("upstream_providers" not in p for _, p in r.node.calls),
      f"{r.node.kinds()}")

r2 = Rig("A7")
r2.run("--manual")
rc, out, _ = r2.run("--relist")
mm = r2.node.models_map()
check("A7a", "scoped relist restores exactly the captured names",
      rc == 0 and out.get("action") == "relist"
      and out.get("restored") == len(ADVERTISED)
      and [n for n, e in mm.items() if e == 1] == ADVERTISED,
      f"rc={rc} restored={out.get('restored')}")
check("A7b", "operator-disabled row is NOT resurrected, ladder untouched",
      all(mm[n] == 0 for n in OPERATOR_DISABLED)
      and r2.node.ladder_bytes() == ladder_before)

r3 = Rig("A8")
rc, out, raw = r3.run("--relist")
check("A8a", "blanket relist refused before any remote call",
      rc == 1 and out.get("action") == "relist_refused"
      and r3.node.calls == [] and not r3.state.exists(),
      f"rc={rc} action={out.get('action')} calls={len(r3.node.calls)}")

r4 = Rig("A9")
rc, out, _ = r4.run("--manual", "--dry-run")
st = rd.load_state(str(r4.state))
check("A9a", "firing dry-run: zero remote round-trips, no delisted flag",
      rc == 0 and r4.node.calls == [] and "delisted" not in st
      and sorted(st) == ["last_dry_run", "ts"],
      f"rc={rc} keys={sorted(st)} calls={len(r4.node.calls)}")

# A10 the newly-measured MEDIUM: dry-run purity on the QUIET path
r5 = Rig("A10")
r5.put_state(ts=1.0, delisted=False, snapshot={"zai\x1f1h": 11.0})
feed = r5.write_preds([pred(hours=10.0, unc=0.05)])   # 1.0 h move < 2.0 h
rc, out, _ = r5.run("--dry-run", preds=feed)
st_dry = rd.load_state(str(r5.state))
check("A10a", "quiet dry-run: rc 0, action none, zero remote round-trips",
      rc == 0 and out.get("action") == "none" and r5.node.calls == [],
      f"rc={rc} action={out.get('action')}")
check("A10b", "MEDIUM: quiet dry-run CONSUMES the acceleration baseline",
      st_dry.get("snapshot", {}).get("zai\x1f1h") == 10.0,
      f"snapshot {st_dry.get('snapshot')} (was 11.0)")
check("A10c", "MEDIUM: quiet dry-run leaves NO last_dry_run trace",
      "last_dry_run" not in st_dry, f"keys {sorted(st_dry)}")
r6 = Rig("A10d")
r6.put_state(ts=1.0, delisted=False, snapshot={"zai\x1f1h": 11.0})
rc2, _, _ = r6.run(preds=r6.write_preds([pred(hours=10.0, unc=0.05)]))
st_real = rd.load_state(str(r6.state))
check("A10d", "quiet dry-run state is identical to a real quiet run's",
      sorted(st_dry) == sorted(st_real)
      and st_dry.get("snapshot") == st_real.get("snapshot"),
      f"dry {sorted(st_dry)} real {sorted(st_real)}")

# ═══ B — finding 2: post-delisting confirmation via re-fetch ═════════════
print("== B: finding 2 — confirmation ==")

vp = rd.verify_pull_payload()
pp = rd.pull_listing_payload()
check("B1a", "verify payload carries no mutating verb",
      not re.search(r"\b(UPDATE|INSERT|DELETE|DROP|REPLACE)\b", vp.upper()),
      "read-only")
check("B1b", "verify payload is exactly the enabled-count re-read",
      "SELECT COUNT(*) FROM models WHERE enabled=1" in vp,
      "SELECT COUNT(*) FROM models WHERE enabled=1")
check("B2a", "success is gated on ok AND count == 0 (never the self-report)",
      'vres.get("ok") is True and vres.get("count") == 0' in SRC,
      "gate text present at line "
      f"{[i + 1 for i, l in enumerate(LINES) if 'vres.get(\"count\") == 0' in l]}")
check("B2b", "confirmed gates the durable delisted=True write",
      "confirmed" in SRC and SRC.count("confirmed = True") == 2,
      f"confirmed=True sites {SRC.count('confirmed = True')}")

rb = Rig("B3")
rc, out, _ = rb.run("--manual")
st = rd.load_state(str(rb.state))
check("B3a", "happy path: one pull + one verify, count 0, rc 0",
      rc == 0 and rb.node.kinds() == ["pull", "verify"]
      and out.get("verified_count") == 0 and out.get("confirmed") is True,
      f"kinds {rb.node.kinds()}")
check("B3b", "durable delisted=True plus captured advertised names",
      st.get("delisted") is True and st.get("pulled_models") == ADVERTISED,
      f"pulled_models {st.get('pulled_models')}")

rb2 = Rig("B4")
rb2.node.pull_lands = False
rc, out, _ = rb2.run("--manual")
st = rd.load_state(str(rb2.state))
check("B4a", "a self-reporting pull that never lands is a FAILED delist",
      rc == 1 and out.get("action") == "delist_failed"
      and out.get("ok") is False and out.get("verify", {}).get("count") == 3,
      f"rc={rc} verify={out.get('verify')}")
check("B4b", "bounded in-run retry: exactly pull/verify twice, no delist flag",
      rb2.node.kinds() == ["pull", "verify", "pull", "verify"]
      and st.get("delisted") is False and st.get("consecutive_failures") == 1,
      f"kinds {rb2.node.kinds()}")

rb3 = Rig("B5")
rb3.node.ssh_down = True
rc, out, _ = rb3.run("--manual")
st = rd.load_state(str(rb3.state))
check("B5a", "verify transport failure fails the attempt (never confirms)",
      rc == 1 and rb3.node.kinds() == ["pull", "pull"]
      and st.get("consecutive_failures") == 1,
      f"rc={rc} kinds={rb3.node.kinds()}")

rb4 = Rig("B6")
rb4.node.verify_garbage = True
rc, out, _ = rb4.run("--manual")
st = rd.load_state(str(rb4.state))
check("B6a", "garbage verify (no count key) cannot confirm: rc 1, no flag",
      rc == 1 and out.get("action") == "delist_failed"
      and st.get("delisted") is False,
      f"rc={rc} kinds={rb4.node.kinds()}")
check("B6b", "None == 0 is False: a missing count can never satisfy the gate",
      (None == 0) is False)

# B7 the MEDIUM residual: no symmetric re-fetch on the relist direction
rb5 = Rig("B7")
rb5.run("--manual")
before = len(rb5.node.calls)
rb5.node.relist_lands = False
rc, out, _ = rb5.run("--relist")
mm = rb5.node.models_map()
st = rd.load_state(str(rb5.state))
check("B7a", "relist is gated on the round-trip self-report alone (no verify)",
      rb5.node.kinds()[before:] == ["relist"],
      f"kinds after delist {rb5.node.kinds()[before:]}")
check("B7b", "MEDIUM: a lying relist is reported as rc-0 success",
      rc == 0 and out.get("action") == "relist", f"rc={rc}")
check("B7c", "MEDIUM: while the listing is measurably NOT restored",
      [n for n, e in mm.items() if e == 1] == [],
      f"enabled {[n for n, e in mm.items() if e == 1]}")
check("B7d", "MEDIUM: the scoped name set is destroyed on the false success",
      "pulled_models" not in st, f"keys {sorted(st)}")
rc, outr, _ = rb5.run("--relist")
check("B7e", "recovery by scoped relist is then refused",
      rc == 1 and outr.get("action") == "relist_refused", f"rc={rc}")
pre = [n for n, e in rb5.node.models_map().items() if e == 1]
rb5.node.relist_lands = True          # probe bug: the lie was still armed
rc, outa, _ = rb5.run("--relist", "--relist-any")
mm = rb5.node.models_map()
check("B7f", "--relist-any then re-enables EVERY row incl. the operator's",
      rc == 0 and pre == [] and all(e == 1 for e in mm.values()),
      f"pre-enabled {pre} -> {mm}")

rb6 = Rig("B8")
rc, out, _ = rb6.run("--manual", "--dry-run")
st8 = rd.load_state(str(rb6.state))
check("B8a", "firing dry-run: reports the intent as delist, zero round-trips",
      rc == 0 and out.get("action") == "delist" and out.get("fire") is True
      and out.get("dry_run") is True and rb6.node.calls == [],
      f"action={out.get('action')} keys={sorted(out)}")
check("B8b", "firing dry-run proves `confirmed` locally (src:679-681) but "
             "prints no verified_count and flips no durable flag",
      "verified_count" not in out and "confirmed" not in out
      and "delisted" not in st8
      and st8.get("last_dry_run", {}).get("action") == "delist",
      f"keys={sorted(st8)} intent={st8.get('last_dry_run', {}).get('action')}")

# ═══ C — finding 3: fail-safe on absent / garbage / stale signals ════════
print("== C: finding 3 — fail-safe ==")

rc1_ = Rig("C1")
rc, out, _ = rc1_.run()
check("C1a", "no --preds: quiet, rc 0, zero round-trips",
      rc == 0 and out.get("action") == "none" and rc1_.node.calls == [],
      f"rc={rc}")

rc2_ = Rig("C2")
rc, out, _ = rc2_.run(preds=rc2_.write_preds([pred(hours=2.0)]))
check("C2a", "first run with no baseline can never fire on acceleration",
      rc == 0 and out.get("action") == "none" and rc2_.node.calls == [],
      f"rc={rc}")

rc3_ = Rig("C3")
bad = rc3_.dir / "bad.json"
bad.write_text("{not json")
rc, out, _ = rc3_.run(preds=bad)
check("C3a", "garbage feed: preds_error, rc 1, no fire, no round-trips",
      rc == 1 and out.get("preds_error") is True
      and out.get("action") == "none" and rc3_.node.calls == [],
      f"rc={rc} preds_error={out.get('preds_error')}")

# C4 freshness matrix. `age` is `now - mtime`, so injecting `now` makes the
# boundary EXACT; the first run of this probe used the live wall clock and
# false-FAILed "exact-1800 is fresh" by ~microseconds of real elapsed time.
ref = SCRATCH / "ref.json"
ref.write_text("[]")
T = os.path.getmtime(str(ref))
matrix = {
    "age0": rd.feed_is_stale(str(ref), now=T),
    "age1800_boundary": rd.feed_is_stale(str(ref), now=T + 1800.0),
    "age1800.001": rd.feed_is_stale(str(ref), now=T + 1800.001),
    "age3600": rd.feed_is_stale(str(ref), now=T + 3600.0),
    "future_mtime": rd.feed_is_stale(str(ref), now=T - 1.0),
    "missing_file": rd.feed_is_stale(str(SCRATCH / "nope.json")),
}
check("C4a", "freshness: age 0/1800 fresh (boundary INCLUSIVE); 1800.001, "
             "3600, future mtime and missing file all STALE",
      matrix == {"age0": False, "age1800_boundary": False,
                 "age1800.001": True, "age3600": True, "future_mtime": True,
                 "missing_file": True}, f"{matrix}")
check("C4b", "fail-closed form `not (0 <= age <= max_age_s)`; STALENESS_S 1800",
      "return not (0 <= age <= max_age_s)" in SRC and rd.STALENESS_S == 1800,
      f"STALENESS_S={rd.STALENESS_S}")

rc4_ = Rig("C5")
rc4_.put_state(ts=1.0, delisted=False, snapshot={"zai\x1f1h": 100.0})
stale_feed = rc4_.age(rc4_.write_preds([pred(hours=1.0, unc=0.9)]))
rc, out, _ = rc4_.run(preds=stale_feed)
st = rd.load_state(str(rc4_.state))
check("C5a", "stale feed never fires (would have moved 99 h) and never acts",
      rc == 1 and out.get("preds_stale") is True
      and out.get("action") == "none" and rc4_.node.calls == [],
      f"rc={rc} stale={out.get('preds_stale')}")
check("C5b", "stale feed leaves the stored baseline byte-for-byte",
      st.get("snapshot") == {"zai\x1f1h": 100.0}, f"{st.get('snapshot')}")

rc5_ = Rig("C6")
rc5_.put_state(ts=1.0, delisted=False, snapshot={"zai\x1f1h": 100.0})
rc, out, _ = rc5_.run(preds=rc5_.write_preds([pred(hours=1.0, unc=0.9)]))
check("C6a", "control: the SAME numbers with a fresh mtime DO delist",
      rc == 0 and out.get("action") == "delist",
      f"rc={rc} action={out.get('action')}")

rc6_ = Rig("C7")
rc6_.put_state(ts=1.0, delisted=False, snapshot={"zai\x1f1h": 100.0})
rc, out, _ = rc6_.run("--manual",
                      preds=rc6_.age(rc6_.write_preds([pred(hours=10.0)])))
st = rd.load_state(str(rc6_.state))
check("C7a", "manual override is never gated on freshness (observed, not "
             "obeyed)",
      rc == 0 and out.get("action") == "delist"
      and out.get("preds_stale") is True
      and rc6_.node.kinds() == ["pull", "verify"],
      f"rc={rc} stale={out.get('preds_stale')}")
check("C7b", "override does not let dead data refresh the baseline",
      st.get("snapshot") == {"zai\x1f1h": 100.0}, f"{st.get('snapshot')}")

rc7_ = Rig("C8")
rc, out, _ = rc7_.run(preds=rc7_.write_preds(
    [{"key": "zai", "window": "1h", "exhausts_in_hours": "10", "uncertainty": True},
     {"key": "zai", "window": "1h", "exhausts_in_hours": None, "uncertainty": "0.9"},
     "not-a-dict", 17,
     {"key": "zai", "window": "1h", "exhausts_in_hours": 10.0,
      "uncertainty": None}]))
check("C8a", "garbage-typed rows: no crash, no fire, zero round-trips",
      rc == 0 and out.get("action") == "none" and out.get("fire") is False
      and rc7_.node.calls == [],
      f"rc={rc} action={out.get('action')}")
check("C8b", "uncertainty guard excludes bool explicitly (bool is int subclass)",
      isinstance(True, int) and "isinstance(unc, bool)" in SRC,
      "guard present at line "
      f"{[i + 1 for i, l in enumerate(LINES) if 'isinstance(unc, bool)' in l]}")
try:
    rd.evaluate_triggers([None, "x", 1], None)
    hard = True
except AttributeError:
    hard = False
except Exception:
    hard = True
check("C8c", "LOW: pure helpers are not type-hardened (direct call raises)",
      hard is False, "AttributeError from evaluate_triggers([None,'x',1], None)")

rc8_ = Rig("C9")
empty = rc8_.write_preds([])
rc, out, _ = rc8_.run(preds=empty)
check("C9a", "LOW: an EMPTY but valid feed is reported as a feed ERROR",
      rc == 1 and out.get("preds_error") is True
      and out.get("action") == "none" and rc8_.node.calls == [],
      f"rc={rc} preds_error={out.get('preds_error')}")

rc9_ = Rig("C10")
rc, out, _ = rc9_.run(preds=rc9_.write_preds([pred(key="openrouter",
                                                   unc=0.95)]))
check("C10a", "LOW: --preds-key scoping is opt-in; a foreign key fires the "
              "delist unscoped",
      out.get("action") == "delist", f"action={out.get('action')}")
rc, out, _ = rc9_.run("--preds-key", "zai",
                      preds=rc9_.write_preds(
                          [pred(key="openrouter", unc=0.95)],
                          name="foreign.json"))
check("C10b", "scoped: foreign key is quiet ... and SILENT (no error flag)",
      rc == 0 and out.get("action") == "none"
      and out.get("preds_error") is False
      and out.get("preds_stale") is False,
      f"rc={rc} preds_error={out.get('preds_error')}")
sig = [a for a in ast.parse(SRC).body if isinstance(a, ast.FunctionDef)
       and a.name == "evaluate_triggers"][0]
check("C10c", "evaluate_triggers exposes no `key` parameter to forward",
      not any(a.arg == "key" for a in sig.args.args + sig.args.kwonlyargs),
      f"args {[a.arg for a in sig.args.args]}")

rc10_ = Rig("C11")
rc, out, _ = rc10_.run("--preds-key", "zai",
                       preds=rc10_.write_preds(
                           [pred(key="zai", hours=10.0),
                            pred(key="openrouter", hours=10.0)]))
st = rd.load_state(str(rc10_.state))
check("C11a", "LOW: a scoped run narrows the durable baseline to that key",
      st.get("snapshot") == {"zai\x1f1h": 10.0}, f"{st.get('snapshot')}")

# C12 budget / timeout clamp against the REAL production backend
recorded = []


def fake_run(cmd, capture_output=False, text=False, timeout=None, **kw):
    recorded.append(timeout)

    class P:
        returncode = 0
        stdout = '{"ok": true}'
        stderr = ""
    return P()


rd.subprocess.run = fake_run
be = PROD_BACKEND("host", "container")
deadline = rd.time.monotonic() - 1.0
res = be._run("x", dry_run=False, action="pull", deadline=deadline)
check("C12a", "exhausted action budget fails closed and spawns nothing",
      res.get("ok") is False and "budget" in res.get("error", "")
      and recorded == [], f"res {res} recorded {recorded}")
r_5 = be._run("x", dry_run=False, action="pull",
              deadline=rd.time.monotonic() + 5.0)
clamp = recorded[-1]
check("C12b", "per-round-trip timeout clamped to the remaining budget",
      abs(clamp - 5.0) <= 0.05, f"timeout {clamp}")
r_full = be._run("x", dry_run=False, action="pull",
                 deadline=rd.time.monotonic() + 1000.0)
check("C12c", "timeout capped at SSH_TIMEOUT_S", recorded[-1] ==
      rd.SSH_TIMEOUT_S, f"{recorded[-1]}")
check("C12d", "SLA arithmetic: cadence + action budget == 300 s; "
              "pull+verify fits",
      rd.TRIGGER_ACTION_WINDOW_S == 300
      and rd.POLL_CADENCE_S + rd.ACTION_BUDGET_S == 300
      and 2 * rd.SSH_TIMEOUT_S <= rd.ACTION_BUDGET_S
      and rd.MAX_PULL_ATTEMPTS == 2,
      f"{rd.POLL_CADENCE_S}+{rd.ACTION_BUDGET_S}=300, "
      f"2*{rd.SSH_TIMEOUT_S}<={rd.ACTION_BUDGET_S}")

rc11_ = Rig("C13")
rc11_.node.ssh_down = True
rcs = [rc11_.run("--manual")[0] for _ in range(3)]
st = rd.load_state(str(rc11_.state))
raw = rc11_.state.read_text()
check("C13a", "3 consecutive failed runs -> rc [1,1,3] and durable BLOCKED",
      rcs == [1, 1, 3] and st.get("blocked") is True
      and st.get("consecutive_failures") == rd.BREAKER_THRESHOLD
      and '"blocked": true' in raw,
      f"rcs {rcs}")
check("C13b", "3 runs x (attempt + bounded retry) = 6 pulls; verify never "
              "reached",
      rc11_.node.kinds() == ["pull"] * 6, f"{rc11_.node.kinds()}")
rc11_.node.ssh_down = False
calls_before = len(rc11_.node.calls)
rc, out, _ = rc11_.run("--manual")
check("C13c", "an open breaker refuses ALL remote action, rc 3",
      rc == 3 and out.get("action") == "blocked"
      and len(rc11_.node.calls) == calls_before, f"rc={rc}")
rc, out, _ = rc11_.run("--unblock", "--manual")
check("C13d", "--unblock clears the breaker and the next run succeeds",
      rc == 0 and out.get("action") == "delist", f"rc={rc}")

rc12_ = Rig("C14")
rc12_.node.ssh_down = True
rcs = [rc12_.run("--manual", "--dry-run")[0] for _ in range(4)]
check("C14a", "dry-run never counts toward the breaker",
      rcs == [0, 0, 0, 0]
      and rd.load_state(str(rc12_.state)).get("blocked") is not True,
      f"rcs {rcs}")

rc13_ = Rig("C15")
rc13_.run("--manual")
rc13_.node.ssh_down = True
rcs = [rc13_.run("--relist")[0] for _ in range(4)]
st = rd.load_state(str(rc13_.state))
check("C15a", "LOW: a failed RELIST never advances the breaker (counter holds "
              "at 0, blocked stays False — keys are kept greppable, so this is "
              "a VALUE check, not an absence check)",
      rcs == [1, 1, 1, 1] and st.get("consecutive_failures") == 0
      and st.get("blocked") is False and "last_pull_error" in st,
      f"rcs {rcs} fails={st.get('consecutive_failures')} "
      f"blocked={st.get('blocked')}")

rc14_ = Rig("C16")
rc14_.put_state(ts=1.0, delisted=True, blocked=True, consecutive_failures=3,
                pulled_models=ADVERTISED)
rc, out, _ = rc14_.run("--relist")
check("C16a", "LOW: an open breaker also refuses --relist (needs --unblock "
              "first)",
      rc == 3 and out.get("action") == "blocked" and rc14_.node.calls == [],
      f"rc={rc}")

# ═══ D — review-record audit ═════════════════════════════════════════════
print("== D: review record ==")

doc_txt = DELIVERABLE.read_text(encoding="utf-8") if DELIVERABLE.exists() else ""
sections = [s for s in re.split(r"(?m)^## ", doc_txt) if s.strip()]
heads = re.findall(r"(?m)^## (.+)$", doc_txt)
check("D1a", "deliverable exists", DELIVERABLE.exists(), str(DELIVERABLE))
check("D1b", "exactly 3 `## ` sections (one per finding)",
      len(re.findall(r"(?m)^## ", doc_txt)) == 3,
      f"headings {heads}")
check("D1c", "every section carries a severity tag",
      len(re.findall(r"severity:", doc_txt)) >= 3,
      f"{len(re.findall(r'severity:', doc_txt))} severity tags")

CITE_FILES = {"routstr_delist.py": SCRIPT, "contract": CONTRACT,
              "tests": MAIN_TESTS, "docs": DOC}
unresolved = []
counts = {}
for tok, ln in re.findall(
        r"(routstr_delist\.py|contract|tests|docs):(\d+)", doc_txt):
    counts[tok] = counts.get(tok, 0) + 1
    if int(ln) > nlines(CITE_FILES[tok]):
        unresolved.append(f"{tok}:{ln}")
check("D2a", "every file:line citation resolves in the file it names",
      not unresolved,
      f"{sum(counts.values())} citations {counts}, unresolved {unresolved}")
check("D2b", "the citation-count preamble comment is internally consistent",
      (lambda s: bool(s) and int(s[0]) == sum(int(x) for x in s[1:5]))(
          (re.search(r"citation-count:\s*total=(\d+)\s+script=(\d+)\s+"
                     r"contract=(\d+)\s+tests=(\d+)\s+docs=(\d+)",
                     doc_txt).groups()
           if re.search(r"citation-count:", doc_txt) else [])),
      (re.search(r"citation-count:[^>]*", doc_txt).group(0)
       if re.search(r"citation-count:", doc_txt) else "absent"))
check("D3a", "artifact-path report names the missing contract markdown as HIGH",
      "routstr_delist_contract.md" in doc_txt and "MISSING" in doc_txt.upper()
      and "HIGH" in doc_txt, "present")
check("D4a", "duplicate-dispatch disclosure states the pass ordinal",
      bool(re.search(r"(first|second|third|fourth|fifth|sixth|seventh|eighth|"
                     r"ninth|tenth|eleventh|twelfth|thirteenth|fourteenth|"
                     r"fifteenth|sixteenth)\s+(?:[a-z]+\s+)?offload pass",
                     doc_txt, re.I)),
      (re.search(r"\w+\s+(?:[a-z]+\s+)?offload pass", doc_txt, re.I).group(0)
       if re.search(r"\w+\s+(?:[a-z]+\s+)?offload pass", doc_txt, re.I)
       else "absent"))
check("D5a", "repo deliverable and bot mirror are byte-identical",
      BOT_DELIVERABLE.exists() and md5(BOT_DELIVERABLE) == md5(DELIVERABLE),
      f"repo {md5(DELIVERABLE) if DELIVERABLE.exists() else 'n/a'} "
      f"bot {md5(BOT_DELIVERABLE) if BOT_DELIVERABLE.exists() else 'n/a'}")
check("D6a", "at least 5 file:line citations inside each finding section",
      all(len(re.findall(r"(?:routstr_delist\.py|contract|tests|docs):\d+", s))
          >= 5 for s in re.split(r"(?m)^## ", doc_txt)[1:]),
      f"{[len(re.findall(r'(?:routstr_delist[.]py|contract|tests|docs):[0-9]+', s)) for s in re.split(r'(?m)^## ', doc_txt)[1:]]}")

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
# self-digest: two invocations must print the same sha, which is the cheapest
# byte-identical order-spanning proof available without a shell redirect
# (the consent guard denies out-of-repo captures).
print(f"transcript sha256: {hashlib.sha256(chr(10).join(body).encode()).hexdigest()}")
raise SystemExit(0 if n_pass == len(CHECKS) else 1)
