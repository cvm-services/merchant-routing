#!/usr/bin/env python3
"""probe_f13_pass15.py — fresh hermetic probe, FIFTEENTH offload pass.

Findings 1-3 (safety / confirmation / fail-safe) for the routstr delist script
(`~/.hermes/bot/scripts/routstr_delist.py`, byte-identical to repo
`src/routstr_delist.py`).

Written for this pass only — NOT copied from any earlier pass's harness.

Read-only w.r.t. every reviewed artifact: scratch state lives under
`~/.cache/f13-pass15/` (never /tmp, never inside the audited repo).  The
module's REAL payload builders are executed against an in-memory stand-in sell
node (named shared-cache sqlite: no file, no fcntl locks, deterministic on this
host) — no network, no subprocess, no file-backed sqlite.  `os.fsync` is
patched to a no-op for the same reason the contract `Rig` does it: fsync can
stall indefinitely on this host.

Rig convention (matters for the `kinds` assertions): a round-trip is recorded
in `node.calls` only when it actually REACHES the stand-in node.  A dead ssh
(rc 255) therefore records nothing, which is why a pull-ok / verify-dead run
yields `kinds == ["pull", "pull"]` (two attempts, each with an unreachable
verify) rather than `["pull", "verify", ...]`.

Run:  python3 probe_f13_pass15.py            (deliverable = repo path)
      FD13_DOC=/path/to/copy python3 probe_f13_pass15.py
Exits 0 when every check passes, 1 otherwise.
"""
from __future__ import annotations

import ast
import builtins
import contextlib
import hashlib
import importlib.util
import inspect
import io
import json
import os
import re
import shutil
import sqlite3
import sys
import time
import types
from pathlib import Path

SCRATCH = Path.home() / ".cache" / "f13-pass15"
shutil.rmtree(SCRATCH, ignore_errors=True)   # no cross-invocation state leak
SCRATCH.mkdir(parents=True, exist_ok=True)

REPO = Path("/home/c03rad0r/repos/merchant-routing")
BOT = Path.home() / ".hermes" / "bot"
SRC_DEPLOYED = BOT / "scripts" / "routstr_delist.py"
SRC_REPO = REPO / "src" / "routstr_delist.py"
CONTRACT_DEPLOYED = BOT / "tests" / "test_routstr_delist.py"
CONTRACT_REPO = REPO / "tests" / "test_routstr_delist_contract.py"
MAIN_SUITE = REPO / "tests" / "test_routstr_delist.py"
DOC_REPO = REPO / "docs" / "routstr-delist.md"
DOC_BOT = BOT / "docs" / "routstr-delist.md"
MISSING_CONTRACT = BOT / "docs" / "routstr_delist_contract.md"
DELIVERABLE = Path(os.environ.get("FD13_DOC", str(REPO / "docs" / "reviews"
                                                      / "findings_1_3.md")))
PROBE = Path(__file__).resolve()

# ── check accumulator ─────────────────────────────────────────────────────
CHECKS: list = []


def check(name, cond, detail=""):
    ok = bool(cond)
    CHECKS.append((name, ok, str(detail)))
    return ok


def md5(p: Path):
    return hashlib.md5(p.read_bytes()).hexdigest() if p.is_file() else ""


def nlines(p: Path):
    return len(p.read_text(encoding="utf-8").split("\n")) - 1 if p.is_file() else -1


# ── load the DEPLOYED script (the artifact under review) ──────────────────
def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


A0a_ok = SRC_DEPLOYED.is_file() and SRC_REPO.is_file() and \
    md5(SRC_DEPLOYED) == md5(SRC_REPO)
check("A0a script deployed == repo (md5)", A0a_ok,
      "deployed=%s repo=%s" % (md5(SRC_DEPLOYED)[:16], md5(SRC_REPO)[:16]))
check("A0b contract suite deployed == repo test_routstr_delist_contract.py",
      md5(CONTRACT_DEPLOYED) == md5(CONTRACT_REPO),
      "%s == %s" % (md5(CONTRACT_DEPLOYED)[:16], md5(CONTRACT_REPO)[:16]))
check("A0c docs/routstr-delist.md bot == repo (md5)",
      DOC_BOT.is_file() and md5(DOC_BOT) == md5(DOC_REPO),
      "%s == %s" % (md5(DOC_BOT)[:16], md5(DOC_REPO)[:16]))
check("A0d contract.md ABSENT at bot path (HIGH, report only)",
      not MISSING_CONTRACT.exists(), "exists=%s" % MISSING_CONTRACT.exists())
check("A0e line counts", nlines(SRC_DEPLOYED) == 829 and
      nlines(CONTRACT_DEPLOYED) == 752 and nlines(MAIN_SUITE) == 1172 and
      nlines(DOC_REPO) == 197,
      "script=%d contract=%d main=%d docs=%d" % (
          nlines(SRC_DEPLOYED), nlines(CONTRACT_DEPLOYED),
          nlines(MAIN_SUITE), nlines(DOC_REPO)))

RD = load_module(SRC_DEPLOYED, "rd_pass15")
REAL_BACKEND = RD._SshBackend        # kept: C10/C10b exercise the PRODUCTION path
os.fsync = lambda fd: None          # see module docstring: fsync can stall

SRC = SRC_DEPLOYED.read_text(encoding="utf-8")
TREE = ast.parse(SRC)


# ── AST helpers ───────────────────────────────────────────────────────────
def docstring_lines(tree):
    spans = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            if ast.get_docstring(node, clean=False) is None:
                continue
            body0 = node.body[0]
            for ln in range(body0.lineno, (body0.end_lineno or body0.lineno) + 1):
                spans.add(ln)
    return spans


def collect_strings(tree, skip_lines):
    """Every executable string literal / f-string payload exactly once.

    Records a literal and does NOT descend into it, so an implicitly
    concatenated f-string payload is not counted once as JoinedStr plus once
    per inner Constant.
    """
    out = []

    class V(ast.NodeVisitor):
        def visit_Constant(self, node):
            if isinstance(node.value, str) and node.lineno not in skip_lines:
                out.append((node.lineno, node.value))

        def visit_JoinedStr(self, node):
            if node.lineno in skip_lines:
                return
            parts = []
            for v in node.values:
                if isinstance(v, ast.Constant) and isinstance(v.value, str):
                    parts.append(v.value)
                else:
                    parts.append("{expr}")
            out.append((node.lineno, "".join(parts)))
            # deliberately no generic_visit: do not re-count inner Constants

    V().visit(tree)
    return out


def expr_call_lines(tree, fname):
    out = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call):
            f = n.value.func
            if isinstance(f, ast.Name) and f.id == fname:
                out.append(n.lineno)
    return sorted(out)


DOC_SPANS = docstring_lines(TREE)
STRINGS = collect_strings(TREE, DOC_SPANS)
ALL_STRINGS = collect_strings(TREE, set())

# ── A1: SQL inventory ─────────────────────────────────────────────────────
SQL_TABLE_RE = re.compile(
    r"\b(?:UPDATE|SELECT|INSERT|DELETE|DROP|ALTER|REPLACE)\b"
    r"[\s\S]{0,200}?\b(models|upstream_providers|providers|keys)\b")
sql_hits = [(ln, s) for ln, s in STRINGS if SQL_TABLE_RE.search(s)]
tables = sorted({SQL_TABLE_RE.search(s).group(1) for _, s in sql_hits})
updates = [ln for ln, s in sql_hits if re.search(r"\bUPDATE\b", s, re.I)]
selects = [ln for ln, s in sql_hits if re.search(r"\bSELECT\b", s, re.I)]
check("A1a SQL table refs == 5, all models",
      len(sql_hits) == 5 and tables == ["models"],
      "lines=%s tables=%s" % ([ln for ln, _ in sql_hits], tables))
check("A1c mutating verbs == 3 UPDATE, 2 SELECT",
      len(updates) == 3 and len(selects) == 2,
      "updates=%s selects=%s" % (updates, selects))

# raw-source confirmation of the five SQL texts (comment lines excluded)
raw_sql = []
for i, line in enumerate(SRC.split("\n"), 1):
    if line.strip().startswith("#"):
        continue
    if re.search(r"(UPDATE|SELECT COUNT|SELECT name)", line) and \
            "models" in line:
        raw_sql.append(i)
check("A2a raw-source SQL text lines == 355/361/371/394/408",
      raw_sql == [355, 361, 371, 394, 408], "lines=%s" % raw_sql)

# upstream_providers: docstring context only
up_all = sorted(ln for ln, _ in ALL_STRINGS if "upstream_providers" in _)
up_exec = [ln for ln, _ in STRINGS if "upstream_providers" in _]
up_text = [i for i, l in enumerate(SRC.split("\n"), 1) if "upstream_providers" in l]
check("A3a upstream_providers appears only inside docstring literals",
      len(up_all) == 3 and up_exec == [] and
      all(ln in DOC_SPANS for ln in up_all),
      "literal_starts=%s executable=%s text_lines=%s"
      % (up_all, up_exec, up_text))
check("A3b executable string literals inspected > 250",
      len(STRINGS) > 250, "executable strings=%d" % len(STRINGS))

# ── A4: subprocess / shell / eval inventory ───────────────────────────────
sub_lines = sorted(n.lineno for n in ast.walk(TREE)
                   if isinstance(n, ast.Call)
                   and isinstance(n.func, ast.Attribute)
                   and n.func.attr == "run"
                   and isinstance(n.func.value, ast.Name)
                   and n.func.value.id == "subprocess")
shell_true = [n.lineno for n in ast.walk(TREE)
              if isinstance(n, ast.keyword) and n.arg == "shell"]
dyn = sorted(n.lineno for n in ast.walk(TREE)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
             and n.func.id in ("eval", "exec"))
check("A4a subprocess.run sites == 2 (:459 nak, :808 ssh)",
      sub_lines == [459, 808], "lines=%s" % sub_lines)
check("A4b shell= kwarg count == 0 and eval/exec call sites == 0",
      shell_true == [] and dyn == [],
      "shell_kwargs=%s dynamic_calls=%s" % (shell_true, dyn))

# ── A5: write surface + ignored save_state returns ────────────────────────
makedirs = sorted(n.lineno for n in ast.walk(TREE)
                  if isinstance(n, ast.Call)
                  and isinstance(n.func, ast.Attribute)
                  and n.func.attr == "makedirs")
replaces = sorted(n.lineno for n in ast.walk(TREE)
                  if isinstance(n, ast.Call)
                  and isinstance(n.func, ast.Attribute)
                  and n.func.attr == "replace")
unlinks = sorted(n.lineno for n in ast.walk(TREE)
                 if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Attribute)
                 and n.func.attr == "unlink")
open_modes = []
for n in ast.walk(TREE):
    if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) \
            and n.func.id == "open":
        mode = "r"
        if len(n.args) > 1 and isinstance(n.args[1], ast.Constant):
            mode = n.args[1].value
        for kw in n.keywords:
            if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
                mode = kw.value.value
        open_modes.append((n.lineno, mode))
check("A5a write surface confined to save_state's atomic tmp-swap "
      "(single mode='w' open, one replace, one unlink)",
      makedirs == [229] and replaces == [235] and unlinks == [243] and
      [m for _, m in open_modes].count("w") == 1 and
      [(ln, m) for ln, m in open_modes if m == "w"] == [(231, "w")],
      "makedirs=%s replace=%s unlink=%s opens=%s" % (
          makedirs, replaces, unlinks, open_modes))
ss_expr = expr_call_lines(TREE, "save_state")
check("A5b save_state return ignored at all 8 call sites",
      ss_expr == [565, 622, 629, 638, 654, 710, 732, 752],
      "lines=%s (count=%d)" % (ss_expr, len(ss_expr)))

# ── stand-in sell node (in-memory, shared cache) ──────────────────────────
ADVERTISED = ["gpt-4o", "claude-3-5-sonnet", "llama-3.1-405b"]
OPERATOR_DISABLED = ["operator-disabled-model"]
PROVIDERS = [("openrouter", 1, 20.0), ("routstr", 1, 10.0), ("zai", 1, 30.0)]


def pred(key="zai", window="1h", hours=10.0, unc=0.05):
    return {"key": key, "window": window, "exhausts_in_hours": hours,
            "uncertainty": unc}


class StandInNode:
    def __init__(self, tag):
        self.ladder = SCRATCH / ("ladder_%s.json" % tag)
        self.ladder.write_bytes(json.dumps(
            {"ladder": [{"name": n, "enabled": bool(e), "weight": w,
                         "candidate": True} for n, e, w in PROVIDERS]},
            indent=2, sort_keys=True).encode())
        self._uri = "file:rdnode15%s%s?mode=memory&cache=shared" % (
            os.getpid(), tag)
        con = self._connect()
        con.execute("CREATE TABLE models "
                    "(name TEXT PRIMARY KEY, enabled INTEGER NOT NULL)")
        for n in ADVERTISED:
            con.execute("INSERT INTO models VALUES (?, 1)", (n,))
        for n in OPERATOR_DISABLED:
            con.execute("INSERT INTO models VALUES (?, 0)", (n,))
        con.execute("CREATE TABLE upstream_providers "
                    "(name TEXT PRIMARY KEY, enabled INTEGER NOT NULL, "
                    "weight REAL NOT NULL)")
        for row in PROVIDERS:
            con.execute("INSERT INTO upstream_providers VALUES (?, ?, ?)", row)
        con.commit()
        self._con = con          # held open: keeps the named memory db alive
        self.calls = []          # (kind, payload) for round-trips that REACHED us
        self.ssh_down = False
        self.ssh_down_kinds = set()
        self.pull_lands = True
        self.relist_lands = True
        shim = types.ModuleType("sqlite3")
        shim.connect = self._connect
        self._sqlite3 = shim

    def _connect(self, _path=None):
        return sqlite3.connect(self._uri, uri=True)

    def models_map(self):
        return dict(self._con.execute("SELECT name, enabled FROM models"))

    def providers_snapshot(self):
        return list(self._con.execute(
            "SELECT name, enabled, weight FROM upstream_providers ORDER BY name"))

    def ladder_bytes(self):
        return self.ladder.read_bytes()

    def kinds(self):
        return [k for k, _ in self.calls]

    def _import(self, name, globals=None, locals=None, fromlist=(), level=0):
        if name == "sqlite3":
            return self._sqlite3
        return builtins.__import__(name, globals, locals, fromlist, level)

    def execute(self, kind, payload):
        self.calls.append((kind, payload))
        revert = None
        if (kind == "pull" and not self.pull_lands) or \
                (kind == "relist" and not self.relist_lands):
            revert = self.models_map()
        out = io.StringIO()
        g = {"__builtins__": {"__import__": self._import, "print": print}}
        with contextlib.redirect_stdout(out):
            exec(payload, g)     # executing OUR OWN payload builders
        if revert is not None:
            con = self._connect()
            for n, e in revert.items():
                con.execute("UPDATE models SET enabled=? WHERE name=?", (e, n))
            con.commit()
            con.close()
        return json.loads(out.getvalue().strip().splitlines()[-1])


CUR = {"node": None}


class NodeBackend:
    """Stand-in for rd._SshBackend; mirrors the production result shape."""

    def __init__(self, ssh_target, container):
        self.node = CUR["node"]
        self.ssh_target = ssh_target
        self.container = container

    def pull(self, dry_run=False, deadline=None):
        return self._rt("pull", RD.pull_listing_payload(), dry_run, deadline)

    def relist(self, names=None, dry_run=False, deadline=None):
        return self._rt("relist", RD.relist_payload(names or []), dry_run,
                        deadline)

    def verify(self, dry_run=False, deadline=None):
        return self._rt("verify", RD.verify_pull_payload(), dry_run, deadline)

    def _rt(self, kind, payload, dry_run, deadline):
        if dry_run:
            return {"ok": True, "dry_run": True, "action": kind}
        if self.node.ssh_down or kind in self.node.ssh_down_kinds:
            return {"ok": False, "action": kind, "rc": 255, "error": "ssh down"}
        res = dict(self.node.execute(kind, payload))
        res["action"] = kind
        res["rc"] = 0
        res["ok"] = res.get("ok") is True
        return res


RD._SshBackend = NodeBackend
NO_OVERRIDE = str(SCRATCH / "absent.override")


def run_main(argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = RD.main(argv)
    txt = buf.getvalue().strip()
    return rc, (json.loads(txt) if txt else {})


def state_path(tag):
    return SCRATCH / ("state_%s.json" % tag)


def write_state(tag, obj):
    p = state_path(tag)
    RD.save_state(str(p), obj)
    return p


def feed(tag, rows, age_s=0.0):
    p = SCRATCH / ("feed_%s.json" % tag)
    p.write_text(json.dumps(rows))
    t = time.time() - age_s
    os.utime(p, (t, t))
    return p


# ══ FINDING 1 — SAFETY ════════════════════════════════════════════════════
node = StandInNode("a6")
CUR["node"] = node
lad0, prov0 = node.ladder_bytes(), node.providers_snapshot()
rc, out = run_main(["--manual", "--state", str(state_path("a6")),
                    "--override", NO_OVERRIDE])
check("A6  manual delist rc0 action=delist", rc == 0 and out.get("action") == "delist",
      "rc=%s action=%s" % (rc, out.get("action")))
check("A6b ladder artifact byte-identical across delist",
      node.ladder_bytes() == lad0, "bytes=%d" % len(lad0))
check("A6c upstream_providers row-identical",
      node.providers_snapshot() == prov0, "rows=%s" % node.providers_snapshot())
check("A6d routstr provider still enabled + ladder candidate",
      any(nm == "routstr" and en == 1 for nm, en, _ in node.providers_snapshot()),
      "")
mm = node.models_map()
check("A6e all advertised disabled, operator-disabled row stays 0",
      all(mm[n] == 0 for n in ADVERTISED) and
      all(mm[n] == 0 for n in OPERATOR_DISABLED),
      "models=%s" % mm)
check("A6f no executed payload ever names upstream_providers",
      all("upstream_providers" not in p for _, p in node.calls),
      "kinds=%s" % node.kinds())

rc, out = run_main(["--relist", "--state", str(state_path("a6")),
                    "--override", NO_OVERRIDE])
mm = node.models_map()
check("A7  scoped relist restores exactly the advertised set",
      rc == 0 and out.get("action") == "relist" and
      sorted(n for n, e in mm.items() if e == 1) == sorted(ADVERTISED) and
      all(mm[n] == 0 for n in OPERATOR_DISABLED),
      "restored=%s models=%s" % (out.get("restored"), mm))
check("A7b relist payload is the parameterized scoped builder",
      any("name IN (?,?,?)" in p for k, p in node.calls if k == "relist"),
      "")
check("A7c ladder still byte-identical after relist",
      node.ladder_bytes() == lad0, "")

node8 = StandInNode("a8")
CUR["node"] = node8
sp8 = state_path("a8")
rc, out = run_main(["--relist", "--state", str(sp8), "--override", NO_OVERRIDE])
check("A8  blanket relist refused: rc1, relist_refused, zero round-trips",
      rc == 1 and out.get("action") == "relist_refused" and
      node8.calls == [], "rc=%s action=%s calls=%s" % (rc, out.get("action"),
                                                       node8.kinds()))
check("A8b refusal writes no state file at all", not sp8.exists(),
      "exists=%s" % sp8.exists())

cmd = RD.build_ssh_docker_cmd("debian@host", "routstr public",
                              RD.pull_listing_payload())
parts = shlex_split = __import__("shlex").split(cmd[2]) if len(cmd) > 2 else []
check("A9  remote argv is 3 elements with the payload as ONE shell-quoted arg",
      len(cmd) == 3 and cmd[0] == "ssh" and
      parts[:4] == ["docker", "exec", "routstr public", "python3"] and
      parts[5] == RD.pull_listing_payload(),
      "len=%d parts[:4]=%s" % (len(cmd), parts[:4]))

node10 = StandInNode("a10")
CUR["node"] = node10
sp10 = state_path("a10")
rc, out = run_main(["--manual", "--dry-run", "--state", str(sp10),
                    "--override", NO_OVERRIDE])
st10 = RD.load_state(str(sp10))
check("A10 fired dry-run: zero round-trips, no durable delisted flag",
      rc == 0 and node10.calls == [] and "delisted" not in st10 and
      "last_dry_run" in st10,
      "rc=%s kinds=%s keys=%s" % (rc, node10.kinds(), sorted(st10)))

# ── A11 (NEW this pass): dry-run on the NON-firing path ───────────────────
# pre-state chosen so the run is QUIET: 11.0 -> 10.0 is a 1.0 h move, below the
# 2.0 h acceleration threshold, but the refresh to 10.0 is still observable.
base_state = {"ts": 1, "snapshot": {"zai\x1f1h": 11.0}, "delisted": False}
node11 = StandInNode("a11")
CUR["node"] = node11
f11 = feed("a11", [pred(hours=10.0)])            # fresh mtime, no trigger
p11 = write_state("a11", base_state)
rc11, out11 = run_main(["--preds", str(f11), "--dry-run", "--state", str(p11),
                        "--override", NO_OVERRIDE])
after11 = RD.load_state(str(p11))
check("A11a quiet dry-run: rc0 action=none, zero round-trips",
      rc11 == 0 and out11.get("action") == "none" and node11.calls == [],
      "rc=%s action=%s kinds=%s" % (rc11, out11.get("action"), node11.kinds()))
check("A11b quiet dry-run CONSUMES the acceleration baseline (snapshot refreshed)",
      after11.get("snapshot") == {"zai\x1f1h": 10.0},
      "snapshot=%s" % after11.get("snapshot"))
check("A11c quiet dry-run records NO last_dry_run (no intent trace at all)",
      "last_dry_run" not in after11, "keys=%s" % sorted(after11))
node11b = StandInNode("a11b")
CUR["node"] = node11b
p11b = write_state("a11b", base_state)
f11b = feed("a11b", [pred(hours=10.0)])
rc11b, out11b = run_main(["--preds", str(f11b), "--state", str(p11b),
                          "--override", NO_OVERRIDE])
after11b = RD.load_state(str(p11b))
strip = lambda d: {k: v for k, v in d.items() if k != "ts"}
check("A11d a real quiet run and a quiet --dry-run are indistinguishable "
      "(except ts)",
      strip(after11) == strip(after11b) and rc11 == rc11b,
      "dry=%s real=%s" % (sorted(after11), sorted(after11b)))

# ══ FINDING 2 — CONFIRMATION ══════════════════════════════════════════════
vp = RD.verify_pull_payload()
check("B1a verify payload contains no mutating verb",
      "UPDATE" not in vp.upper() and "INSERT" not in vp.upper() and
      "DELETE" not in vp.upper(), "payload=%r" % vp[:60])
check("B1b verify payload is exactly the read-only COUNT",
      "SELECT COUNT(*) FROM models WHERE enabled=1" in vp, "")
check("B2a :683 gates confirmation on ok is True and count == 0",
      'vres.get("ok") is True and vres.get("count") == 0' in SRC,
      "")

node3 = StandInNode("b3")
CUR["node"] = node3
p3 = write_state("b3", {"ts": 1, "snapshot": {"zai\x1f1h": 100.0}})
f3 = feed("b3", [pred(hours=10.0)])
rc3, out3 = run_main(["--preds", str(f3), "--state", str(p3),
                      "--override", NO_OVERRIDE])
st3 = RD.load_state(str(p3))
check("B3  happy path: rc0, confirmed, verified_count 0, kinds [pull, verify]",
      rc3 == 0 and out3.get("action") == "delist" and
      out3.get("confirmed") is True and out3.get("verified_count") == 0 and
      node3.kinds() == ["pull", "verify"],
      "rc=%s action=%s kinds=%s" % (rc3, out3.get("action"), node3.kinds()))
check("B3b durable delisted=true carrying the captured advertised names",
      st3.get("delisted") is True and st3.get("pulled_models") == ADVERTISED,
      "pulled=%s" % st3.get("pulled_models"))

node4 = StandInNode("b4")
node4.pull_lands = False
CUR["node"] = node4
p4 = write_state("b4", {"ts": 1, "snapshot": {"zai\x1f1h": 100.0}})
f4 = feed("b4", [pred(hours=10.0)])
rc4, out4 = run_main(["--preds", str(f4), "--state", str(p4),
                      "--override", NO_OVERRIDE])
st4 = RD.load_state(str(p4))
check("B4  lying pull refuted by execution: rc1 delist_failed, two attempts",
      rc4 == 1 and out4.get("action") == "delist_failed" and
      node4.kinds() == ["pull", "verify", "pull", "verify"],
      "rc=%s kinds=%s" % (rc4, node4.kinds()))
check("B4b refuting verify reported count=3; no flag; breaker ticked",
      out4.get("verify", {}).get("count") == 3 and
      st4.get("delisted") is False and st4.get("consecutive_failures") == 1,
      "verify=%s delisted=%s fails=%s" % (out4.get("verify"),
                                          st4.get("delisted"),
                                          st4.get("consecutive_failures")))

node5 = StandInNode("b5")
node5.ssh_down_kinds = {"verify"}
CUR["node"] = node5
p5 = write_state("b5", {"ts": 1, "snapshot": {"zai\x1f1h": 100.0}})
f5 = feed("b5", [pred(hours=10.0)])
rc5, out5 = run_main(["--preds", str(f5), "--state", str(p5),
                      "--override", NO_OVERRIDE])
st5 = RD.load_state(str(p5))
check("B5a verify transport failure is an attempt failure, never a confirmation",
      rc5 == 1 and out5.get("action") == "delist_failed" and
      node5.kinds() == ["pull", "pull"] and st5.get("delisted") is False and
      st5.get("consecutive_failures") == 1,
      "rc=%s kinds=%s fails=%s" % (rc5, node5.kinds(),
                                   st5.get("consecutive_failures")))

node7 = StandInNode("b7")
CUR["node"] = node7
p7 = write_state("b7", {"ts": 1, "snapshot": {"zai\x1f1h": 100.0}})
f7 = feed("b7", [pred(hours=10.0)])
run_main(["--preds", str(f7), "--state", str(p7), "--override", NO_OVERRIDE])
node7.calls.clear()
node7.relist_lands = False
rc7, out7 = run_main(["--relist", "--state", str(p7), "--override", NO_OVERRIDE])
st7 = RD.load_state(str(p7))
check("B7a relist runs NO verify round-trip (kinds == ['relist'])",
      node7.kinds() == ["relist"], "kinds=%s" % node7.kinds())
check("B7b lying relist reported as success: rc0 action=relist",
      rc7 == 0 and out7.get("action") == "relist", "rc=%s action=%s" % (rc7, out7.get("action")))
mm7 = node7.models_map()
check("B7c listing measurably NOT restored",
      all(mm7[n] == 0 for n in ADVERTISED), "models=%s" % mm7)
check("B7d scoped name set destroyed (pulled_models absent)",
      "pulled_models" not in st7, "keys=%s" % sorted(st7))
rc7e, out7e = run_main(["--relist", "--state", str(p7), "--override", NO_OVERRIDE])
check("B7e recovery scoped relist now refused (rc1 relist_refused)",
      rc7e == 1 and out7e.get("action") == "relist_refused",
      "rc=%s action=%s" % (rc7e, out7e.get("action")))
node7.relist_lands = True        # restore the node before the opt-in blanket relist
rc7f, out7f = run_main(["--relist", "--relist-any", "--state", str(p7),
                        "--override", NO_OVERRIDE])
mm7f = node7.models_map()
check("B7f --relist-any re-enables EVERY row incl. operator-disabled",
      rc7f == 0 and all(mm7f[n] == 1 for n in ADVERTISED) and
      all(mm7f[n] == 1 for n in OPERATOR_DISABLED),
      "models=%s" % mm7f)
check("B8a None == 0 is False: an absent/garbage count can never confirm",
      not (None == 0) and 'vres.get("count") == 0' in SRC, "")

# ══ FINDING 3 — FAIL-SAFE ═════════════════════════════════════════════════
cf = SCRATCH / "c1feed.json"
cf.write_text("[]")
base_t = 1_700_000_000.0
os.utime(cf, (base_t, base_t))
stale = RD.feed_is_stale
check("C1  staleness matrix (missing/aged/future stale; fresh + exact boundary not)",
      stale(str(cf), now=base_t) is False and
      stale(str(cf), now=base_t + 1800) is False and
      stale(str(cf), now=base_t + 1800.5) is True and
      stale(str(cf), now=base_t + 3600) is True and
      stale(str(cf), now=base_t - 100) is True and
      stale(str(SCRATCH / "nope.json")) is True,
      "")

node2 = StandInNode("c2")
CUR["node"] = node2
p2 = write_state("c2", {"ts": 1, "snapshot": {"zai\x1f1h": 100.0}})
f2 = feed("c2", [pred(hours=10.0)], age_s=3600)
rc2, out2 = run_main(["--preds", str(f2), "--state", str(p2),
                      "--override", NO_OVERRIDE])
st2 = RD.load_state(str(p2))
check("C2  stale feed: rc1 preds_stale, no fire, no calls, baseline untouched",
      rc2 == 1 and out2.get("preds_stale") is True and
      out2.get("action") == "none" and node2.calls == [] and
      st2.get("snapshot") == {"zai\x1f1h": 100.0},
      "rc=%s out=%s snapshot=%s" % (rc2, out2.get("action"),
                                    st2.get("snapshot")))
node2c = StandInNode("c2c")
CUR["node"] = node2c
p2c = write_state("c2c", {"ts": 1, "snapshot": {"zai\x1f1h": 100.0}})
f2c = feed("c2c", [pred(hours=10.0)])
rc2c, out2c = run_main(["--preds", str(f2c), "--state", str(p2c),
                        "--override", NO_OVERRIDE])
check("C2c control: identical numbers with a FRESH mtime DO fire",
      rc2c == 0 and out2c.get("action") == "delist",
      "rc=%s action=%s" % (rc2c, out2c.get("action")))

node4g = StandInNode("c4")
CUR["node"] = node4g
f4g = feed("c4", "not-json{{{")            # json.dump of a str -> written quoted; see below
f4g.write_text("{not json")
p4g = state_path("c4")
rc4g, out4g = run_main(["--preds", str(f4g), "--state", str(p4g),
                        "--override", NO_OVERRIDE])
check("C4a invalid JSON feed: rc1 preds_error, action none, zero round-trips",
      rc4g == 1 and out4g.get("preds_error") is True and
      out4g.get("action") == "none" and node4g.calls == [],
      "rc=%s out=%s" % (rc4g, out4g.get("action")))
f4c = feed("c4c", "{not json", age_s=3600)
p4c = state_path("c4c")
rc4c, out4c = run_main(["--preds", str(f4c), "--state", str(p4c),
                        "--override", NO_OVERRIDE])
check("C4c garbage AND aged: preds_error true, preds_stale false, rc1",
      rc4c == 1 and out4c.get("preds_error") is True and
      out4c.get("preds_stale") is False,
      "rc=%s error=%s stale=%s" % (rc4c, out4c.get("preds_error"),
                                   out4c.get("preds_stale")))

node5e = StandInNode("c5")
CUR["node"] = node5e
f5e = feed("c5", [])
p5e = state_path("c5")
rc5e, out5e = run_main(["--preds", str(f5e), "--state", str(p5e),
                        "--override", NO_OVERRIDE])
check("C5a empty-but-valid [] reported as a feed ERROR (rc1 preds_error)",
      rc5e == 1 and out5e.get("preds_error") is True and
      out5e.get("action") == "none", "rc=%s out=%s" % (rc5e, out5e))

node6 = StandInNode("c6")
CUR["node"] = node6
messy = [None, "x", 1, 2.5,
         {"key": "zai", "window": "1h", "exhausts_in_hours": "nope",
          "uncertainty": "high"},
         {"key": "zai", "window": "2h", "exhausts_in_hours": True,
          "uncertainty": True}]
f6 = feed("c6", messy)
p6 = write_state("c6", {"ts": 1, "snapshot": {"zai\x1f1h": 100.0}})
rc6, out6 = run_main(["--preds", str(f6), "--state", str(p6),
                      "--override", NO_OVERRIDE])
check("C6a/C6b malformed rows: no crash, no fire, rc0, empty triggers",
      rc6 == 0 and out6.get("action") == "none" and out6.get("reasons") == [],
      "rc=%s out=%s" % (rc6, out6))
check("C6c _hours accepts bool (arithmetic-safe) but rejects str",
      RD._hours({"exhausts_in_hours": True}) is True and
      RD._hours({"exhausts_in_hours": "x"}) is None, "")
try:
    RD.evaluate_triggers([None, "x", 1], None)
    raised = None
except Exception as exc:
    raised = type(exc).__name__
check("C6d NEW: pure helpers are NOT type-hardened (direct call raises)",
      raised == "AttributeError", "raised=%s" % raised)

node7m = StandInNode("c7")
CUR["node"] = node7m
p7m = write_state("c7", {"ts": 1, "snapshot": {"zai\x1f1h": 100.0}})
f7m = feed("c7", [pred(hours=10.0)], age_s=3600)
rc7m, out7m = run_main(["--manual", "--preds", str(f7m), "--state", str(p7m),
                        "--override", NO_OVERRIDE])
st7m = RD.load_state(str(p7m))
check("C7  stale feed + --manual delists; baseline NOT refreshed",
      rc7m == 0 and out7m.get("action") == "delist" and
      out7m.get("preds_stale") is True and
      node7m.kinds() == ["pull", "verify"] and
      st7m.get("snapshot") == {"zai\x1f1h": 100.0},
      "rc=%s kinds=%s snapshot=%s" % (rc7m, node7m.kinds(),
                                      st7m.get("snapshot")))
node7c = StandInNode("c7c")
CUR["node"] = node7c
f7c = feed("c7c", "{not json")
p7c = state_path("c7c")
rc7c, out7c = run_main(["--manual", "--preds", str(f7c), "--state", str(p7c),
                        "--override", NO_OVERRIDE])
check("C7c unparseable feed + --manual still delists (rc0, preds_error true)",
      rc7c == 0 and out7c.get("action") == "delist" and
      out7c.get("preds_error") is True, "rc=%s out=%s" % (rc7c, out7c))

node8k = StandInNode("c8")
CUR["node"] = node8k
f8 = feed("c8", [pred(key="openrouter", hours=10.0, unc=0.95)])
p8 = write_state("c8", {"ts": 1, "snapshot": {"zai\x1f1h": 100.0}})
rc8, out8 = run_main(["--preds", str(f8), "--state", str(p8),
                      "--override", NO_OVERRIDE])
check("C8a foreign-key variance spike fires the routstr delist (no --preds-key)",
      rc8 == 0 and out8.get("action") == "delist",
      "rc=%s action=%s" % (rc8, out8.get("action")))
node8b = StandInNode("c8b")
CUR["node"] = node8b
p8b = write_state("c8b", {"ts": 1, "snapshot": {"zai\x1f1h": 100.0}})
rc8b, out8b = run_main(["--preds", str(f8), "--preds-key", "zai",
                        "--state", str(p8b), "--override", NO_OVERRIDE])
check("C8b same feed scoped with --preds-key zai is quiet",
      rc8b == 0 and out8b.get("action") == "none",
      "rc=%s action=%s" % (rc8b, out8b.get("action")))
sig = inspect.signature(RD.evaluate_triggers)
check("C8c evaluate_triggers signature has no key parameter",
      "key" not in sig.parameters, "params=%s" % list(sig.parameters))

node9 = StandInNode("c9")
CUR["node"] = node9
two = [pred(key="zai", hours=10.0), pred(key="openrouter", hours=50.0)]
f9 = feed("c9", two)
p9 = write_state("c9", {"ts": 1, "snapshot": {"zai\x1f1h": 100.0,
                                              "openrouter\x1f1h": 60.0}})
rc9, out9 = run_main(["--preds", str(f9), "--preds-key", "zai",
                      "--state", str(p9), "--override", NO_OVERRIDE])
st9 = RD.load_state(str(p9))
check("C9a scoped run narrows the durable baseline to the scoped key",
      rc9 == 0 and st9.get("snapshot") == {"zai\x1f1h": 10.0},
      "snapshot=%s" % st9.get("snapshot"))

spawned = []
orig_run = RD.subprocess.run
RD.subprocess.run = lambda *a, **k: (spawned.append(a), None)[1]
try:
    r10 = REAL_BACKEND("t", "c")._run("print(1)", dry_run=False,
                                      action="pull",
                                      deadline=time.monotonic() - 1)
finally:
    RD.subprocess.run = orig_run
check("C10 exhausted budget: ok=false, zero subprocess spawns",
      r10.get("ok") is False and "action budget exhausted" in r10.get("error", "")
      and spawned == [], "res=%s spawned=%s" % (r10, len(spawned)))

rec = {}


def fake_run(cmd, **kw):
    rec.update(kw)
    rec["cmd"] = cmd
    return types.SimpleNamespace(returncode=0,
                                 stdout='{"ok": true, "count": 0}',
                                 stderr="")


RD.subprocess.run = fake_run
try:
    r10b = REAL_BACKEND("t", "c")._run("print(1)", dry_run=False,
                                       action="pull",
                                       deadline=time.monotonic() + 5)
finally:
    RD.subprocess.run = orig_run
check("C10b per-round-trip timeout clamped to the remaining budget",
      abs(rec.get("timeout", 0) - 5.0) < 0.05 and r10b.get("ok") is True and
      "shell" not in rec,
      "timeout=%s ok=%s kwargs=%s" % (rec.get("timeout"), r10b.get("ok"),
                                      sorted(rec)))

node11c = StandInNode("c11")
node11c.ssh_down = True
CUR["node"] = node11c
p11c = write_state("c11", {"ts": 1, "snapshot": {"zai\x1f1h": 100.0}})
f11c = feed("c11", [pred(hours=10.0)])
rcs = []
for _ in range(3):
    rc, _o = run_main(["--preds", str(f11c), "--state", str(p11c),
                       "--override", NO_OVERRIDE])
    rcs.append(rc)
st11c = RD.load_state(str(p11c))
check("C11 three consecutive failures -> rc [1,1,3] and durable blocked=true",
      rcs == [1, 1, 3] and st11c.get("blocked") is True and
      st11c.get("consecutive_failures") == 3,
      "rcs=%s blocked=%s fails=%s" % (rcs, st11c.get("blocked"),
                                      st11c.get("consecutive_failures")))
node11c.calls.clear()
rc11d, out11d = run_main(["--preds", str(f11c), "--state", str(p11c),
                          "--override", NO_OVERRIDE])
check("C11b blocked run refuses ALL remote action with zero round-trips",
      rc11d == 3 and out11d.get("action") == "blocked" and
      node11c.calls == [], "rc=%s action=%s" % (rc11d, out11d.get("action")))

node12 = StandInNode("c12")
node12.ssh_down = True
CUR["node"] = node12
p12 = write_state("c12", {"ts": 1, "consecutive_failures": 1})
rc12, out12 = run_main(["--manual", "--dry-run", "--state", str(p12),
                        "--override", NO_OVERRIDE])
st12 = RD.load_state(str(p12))
check("C12 dry-run never counts toward the breaker",
      rc12 == 0 and st12.get("consecutive_failures") == 1 and
      st12.get("blocked") in (None, False),
      "rc=%s fails=%s blocked=%s" % (rc12, st12.get("consecutive_failures"),
                                     st12.get("blocked")))

node13 = StandInNode("c13")
node13.ssh_down = True
CUR["node"] = node13
p13 = write_state("c13", {"ts": 1, "delisted": True,
                          "pulled_models": ["gpt-4o"]})
rcs13 = []
for _ in range(4):
    rc, _o = run_main(["--relist", "--state", str(p13), "--override", NO_OVERRIDE])
    rcs13.append(rc)
st13 = RD.load_state(str(p13))
check("C13a NEW: repeated dead relists never escalate to BLOCKED",
      rcs13 == [1, 1, 1, 1] and not st13.get("blocked") and
      st13.get("consecutive_failures") in (0, None),
      "rcs=%s blocked=%s fails=%s" % (rcs13, st13.get("blocked"),
                                      st13.get("consecutive_failures")))
node13b = StandInNode("c13b")
CUR["node"] = node13b
p13b = write_state("c13b", {"ts": 1, "delisted": True,
                            "pulled_models": ["gpt-4o"],
                            "consecutive_failures": 2})
rc13b, _o = run_main(["--relist", "--state", str(p13b), "--override", NO_OVERRIDE])
st13b = RD.load_state(str(p13b))
check("C13b a successful relist DOES reset accumulated failures 2 -> 0",
      rc13b == 0 and st13b.get("consecutive_failures") == 0 and
      st13b.get("blocked") is False,
      "rc=%s fails=%s" % (rc13b, st13b.get("consecutive_failures")))
node13c = StandInNode("c13c")
CUR["node"] = node13c
p13c = write_state("c13c", {"ts": 1, "delisted": True,
                            "pulled_models": ["gpt-4o"], "blocked": True,
                            "consecutive_failures": 3})
rc13c, out13c = run_main(["--relist", "--state", str(p13c), "--override", NO_OVERRIDE])
check("C13c NEW: a BLOCKED state refuses --relist (reset reachable only unblocked)",
      rc13c == 3 and out13c.get("action") == "blocked" and node13c.calls == [],
      "rc=%s action=%s" % (rc13c, out13c.get("action")))

node14 = StandInNode("c14")
CUR["node"] = node14
f14 = feed("c14", [pred(key="openrouter", hours=10.0, unc=0.95)])
p14 = write_state("c14", {"ts": 1, "snapshot": {"zai\x1f1h": 100.0}})
rc14, out14 = run_main(["--preds", str(f14), "--preds-key", "zai",
                        "--state", str(p14), "--override", NO_OVERRIDE])
check("C14 NEW: a non-matching --preds-key is a silent healthy-looking rc0",
      rc14 == 0 and out14.get("action") == "none" and
      out14.get("preds_error") is False and out14.get("preds_stale") is False
      and node14.calls == [],
      "rc=%s out=%s" % (rc14, out14))

# ══ D — citation audit + deliverable shape ════════════════════════════════
FILES = {
    "routstr_delist.py": SRC_DEPLOYED,
    "contract": CONTRACT_DEPLOYED,
    "tests": MAIN_SUITE,
    "docs": DOC_REPO,
}
LINES = {k: v.read_text(encoding="utf-8").split("\n") for k, v in FILES.items()}

CITATIONS = [
    ("routstr_delist.py", 35, "upstream_providers"),
    ("routstr_delist.py", 75, "MAX_PULL_ATTEMPTS = 2"),
    ("routstr_delist.py", 78, "STALENESS_S = 1800"),
    ("routstr_delist.py", 107, "if not preds_now or not preds_prev:"),
    ("routstr_delist.py", 132, "def variance_jumped(preds, *, threshold=VARIANCE_THRESHOLD, key=None)"),
    ("routstr_delist.py", 143, "if not preds:"),
    ("routstr_delist.py", 152, "isinstance(unc, (int, float))"),
    ("routstr_delist.py", 172, "return os.path.isfile(override_path)"),
    ("routstr_delist.py", 229, "os.makedirs(d, exist_ok=True)"),
    ("routstr_delist.py", 231, 'with open(tmp, "w", encoding="utf-8") as fh:'),
    ("routstr_delist.py", 235, "os.replace(tmp, path)"),
    ("routstr_delist.py", 243, "os.unlink(tmp)"),
    ("routstr_delist.py", 261, "if preds:"),
    ("routstr_delist.py", 272, "def evaluate_triggers(preds_now, prev_state, *,"),
    ("routstr_delist.py", 303, "var = variance_jumped(preds_now, threshold=variance_threshold)"),
    ("routstr_delist.py", 317, '"fire": bool(accel or var or override),'),
    ("routstr_delist.py", 352, "upstream_providers"),
    ("routstr_delist.py", 355, "UPDATE models SET enabled=0 WHERE enabled=1;"),
    ("routstr_delist.py", 361, "UPDATE models SET enabled=1;"),
    ("routstr_delist.py", 370, "keys.db"),
    ("routstr_delist.py", 371, "SELECT name FROM models WHERE enabled=1"),
    ("routstr_delist.py", 385, "keys.db"),
    ("routstr_delist.py", 393, "keys.db"),
    ("routstr_delist.py", 394, "UPDATE models SET enabled=1 WHERE name IN"),
    ("routstr_delist.py", 407, "keys.db"),
    ("routstr_delist.py", 408, "SELECT COUNT(*) FROM models WHERE enabled=1"),
    ("routstr_delist.py", 414, "def build_ssh_docker_cmd("),
    ("routstr_delist.py", 423, 'remote = " ".join'),
    ("routstr_delist.py", 459, "subprocess.run(argv, timeout=30,"),
    ("routstr_delist.py", 468, "def _read_preds(pred_input):"),
    ("routstr_delist.py", 479, "return [d for d in data if isinstance(d, dict)]"),
    ("routstr_delist.py", 485, "def feed_is_stale("),
    ("routstr_delist.py", 494, "return not (0 <= age <= max_age_s)"),
    ("routstr_delist.py", 526, "--relist-any"),
    ("routstr_delist.py", 529, "--unblock"),
    ("routstr_delist.py", 536, "--ssh-target"),
    ("routstr_delist.py", 537, "--container"),
    ("routstr_delist.py", 569, "if blocked:"),
    ("routstr_delist.py", 578, "return 3"),
    ("routstr_delist.py", 585, "preds_error = bool(args.preds) and not raw_preds"),
    ("routstr_delist.py", 589, "preds_stale = bool(args.preds) and bool(raw_preds) and"),
    ("routstr_delist.py", 591, "if preds_stale:"),
    ("routstr_delist.py", 597, 'preds = [p for p in raw_preds if p.get("key") == args.preds_key]'),
    ("routstr_delist.py", 602, "if not names and not args.relist_any:"),
    ("routstr_delist.py", 626, 'if not res.get("ok"):'),
    ("routstr_delist.py", 635, 'state.pop("pulled_models", None)'),
    ("routstr_delist.py", 636, 'state["consecutive_failures"] = 0'),
    ("routstr_delist.py", 649, 'fire = args.delist or dec["fire"]'),
    ("routstr_delist.py", 651, "if not fire:"),
    ("routstr_delist.py", 654, "save_state(args.state, state)"),
    ("routstr_delist.py", 660, "return 1 if (preds_error or preds_stale) else 0"),
    ("routstr_delist.py", 671, "while attempts < MAX_PULL_ATTEMPTS:"),
    ("routstr_delist.py", 675, "if not args.dry_run and attempts < MAX_PULL_ATTEMPTS and"),
    ("routstr_delist.py", 679, "if args.dry_run:"),
    ("routstr_delist.py", 680, "confirmed = True"),
    ("routstr_delist.py", 682, "vres = backend.verify(deadline=deadline)"),
    ("routstr_delist.py", 683, 'if vres.get("ok") is True and vres.get("count") == 0:'),
    ("routstr_delist.py", 687, "confirmed = True"),
    ("routstr_delist.py", 724, "fails += 1"),
    ("routstr_delist.py", 730, "newly_blocked = fails >= BREAKER_THRESHOLD"),
    ("routstr_delist.py", 739, "return 3 if newly_blocked else 1"),
    ("routstr_delist.py", 747, "delisted=True,"),
    ("routstr_delist.py", 752, "save_state(args.state, state)"),
    ("routstr_delist.py", 771, "upstream_providers"),
    ("routstr_delist.py", 790, "def verify(self, dry_run=False, deadline=None):"),
    ("routstr_delist.py", 800, "timeout = SSH_TIMEOUT_S"),
    ("routstr_delist.py", 801, "if deadline is not None:"),
    ("routstr_delist.py", 806, "timeout = min(SSH_TIMEOUT_S, remaining)"),
    ("routstr_delist.py", 822, 'res["ok"] = proc.returncode == 0 and data.get("ok") is True'),
    ("docs", 29, "**No blanket relist.**"),
    ("docs", 54, "--preds-key <key>"),
    ("docs", 55, "another provider's variance spike can never pull the routstr SALE"),
    ("docs", 56, "**Freshness guard (cold-review finding 3):**"),
    ("docs", 60, "The manual override is never gated on freshness."),
    ("docs", 69, "**Re-fetch confirmation (cold-review finding 2):**"),
    ("docs", 84, "**unreadable/corrupt `--preds` feed**"),
    ("docs", 87, "**Dry-run is intent-only"),
    ("docs", 89, "baseline consumption"),
    ("docs", 106, "*/4 * * * *"),
    ("docs", 137, "shlex.quote"),
    ("contract", 50, '"scripts"'),
    ("contract", 108, "self.ladder_artifact"),
    ("contract", 308, "def test_first_run_without_baseline_is_quiet"),
    ("contract", 334, 'assert rig.node.kinds() == ["pull", "verify"]'),
    ("contract", 346, "def test_unverified_pull_is_a_failed_delist"),
    ("contract", 427, "def test_manual_override_is_never_gated_on_feed_staleness"),
    ("contract", 468, "class TestSemanticGuardLadderUntouched"),
    ("contract", 480, "assert rig.node.ladder_bytes() == ladder_before"),
    ("contract", 483, "upstream_providers"),
    ("contract", 487, 'assert any(name == "routstr" and enabled == 1'),
    ("contract", 731, "def test_dry_run_publishes_no_event_and_flips_no_flag"),
    ("tests", 146, "def test_non_numeric_uncertainty_ignored_not_crash"),
    ("tests", 302, "class TestSaleNotProvider"),
    ("tests", 345, "def test_ssh_cmd_is_single_shlex_safe_remote_command"),
    ("tests", 354, "parts = shlex.split(cmd[2])"),
    ("tests", 566, "class TestRefetchConfirmation"),
    ("tests", 816, "class TestCircuitBreaker"),
    ("tests", 928, "class TestStalenessGuard"),
    ("tests", 937, "def test_stale_feed_never_triggers"),
    ("tests", 968, "def test_staleness_threshold_boundary"),
    ("tests", 980, "def test_stale_feed_exit_zero_when_override_fires"),
    ("tests", 995, "def test_stale_feed_baseline_not_consumed"),
    ("tests", 1072, "class TestDryRunPurity"),
    ("tests", 1166, 'self.assertIn("name IN (?,?)", remote)'),
]
bad = []
for alias, lineno, expect in CITATIONS:
    lines = LINES[alias]
    got = lines[lineno - 1] if 0 < lineno <= len(lines) else "<OUT OF RANGE>"
    if expect not in got:
        bad.append((alias, lineno, expect, got.strip()[:70]))
check("D1 every cited file:line pair carries its expected text",
      bad == [], "pairs=%d mismatches=%s" % (len(CITATIONS), bad))

# D2 — resolve every file:line citation in the deliverable.  Alias-aware:
# `tests/test_routstr_delist.py:N` must NOT be counted as a routstr_delist.py
# citation just because the basename appears inside the longer path (the trap
# a naive /routstr_delist\.py:(\d+)/ falls into).
CIT_RE = re.compile(
    r"(?:src/)?routstr_delist\.py:(\d+)"
    r"|(?:tests/)?test_routstr_delist_contract\.py:(\d+)"
    r"|(?:tests/)?test_routstr_delist\.py:(\d+)"
    r"|contract:(\d+)"
    r"|tests:(\d+)"
    r"|docs:(\d+)"
    r"|(?:docs/)?routstr-delist\.md:(\d+)")
CANON = {1: "routstr_delist.py", 2: "contract", 3: "tests",
         4: "contract", 5: "tests", 6: "docs", 7: "docs"}
if DELIVERABLE.is_file():
    doc = DELIVERABLE.read_text(encoding="utf-8")
    per, unresolved, total = {}, [], 0
    for m in CIT_RE.finditer(doc):
        gi = m.lastindex
        alias = CANON[gi]
        num = int(m.group(gi))
        total += 1
        per[alias] = per.get(alias, 0) + 1
        if num > (len(LINES[alias]) - 1):
            unresolved.append((alias, num))
    heads = [ln for ln in doc.split("\n") if ln.startswith("## Finding")]
    sev = [ln for ln in heads if "severity:" in ln]
    check("D2 every file:line citation resolves in the file it names",
          unresolved == [], "total=%d breakdown=%s unresolved=%s" % (
              total, per, unresolved))
    check("D3 deliverable shape: exactly 3 '## Finding' sections, each with a "
          "severity tag",
          len(heads) == 3 and len(sev) == 3 and
          all(t in doc for t in ("Finding 1", "Finding 2", "Finding 3")),
          "headings=%d with_severity=%d" % (len(heads), len(sev)))
    mk = re.search(r"citation-count:\s*total=(\d+)\s+script=(\d+)\s+"
                   r"contract=(\d+)\s+tests=(\d+)\s+docs=(\d+)", doc)
    if mk is None:
        check("D4 citation-count marker matches measurement "
              "(informational: this text carries no marker)",
              True, "no marker; measured total=%d %s" % (total, per))
    else:
        want = (total, per.get("routstr_delist.py", 0), per.get("contract", 0),
                per.get("tests", 0), per.get("docs", 0))
        got = tuple(int(x) for x in mk.groups())
        check("D4 citation-count marker matches measurement", got == want,
              "marker=%s measured=%s" % (got, want))
    print("[i] deliverable=%s md5=%s lines=%d citations=%d %s"
          % (DELIVERABLE, md5(DELIVERABLE)[:16], nlines(DELIVERABLE),
             total, per))
else:
    check("D2 deliverable present", False, "missing %s" % DELIVERABLE)

# ── report ────────────────────────────────────────────────────────────────
npass = sum(1 for _, ok, _ in CHECKS if ok)
nfail = len(CHECKS) - npass
print("probe=%s" % PROBE.name)
print("scratch=%s" % SCRATCH)
print("[i] D1 pairs=%d" % len(CITATIONS))
print("[i] A3b executable_string_literals=%d (docstrings excluded)"
      % len(STRINGS))
print("[i] A3a upstream_providers literal_starts=%s text_lines=%s"
      % (up_all, up_text))
print("[i] A5a open_modes=%s" % open_modes)
print("[i] A5b save_state ignored-return sites=%s" % ss_expr)
print("[i] A6b ladder_bytes=%d | A6 provider rows=%s"
      % (len(lad0), [r[0] for r in prov0]))
print("[i] A11 quiet dry-run state_keys=%s snapshot=%s | real quiet "
      "state_keys=%s snapshot=%s"
      % (sorted(after11), after11.get("snapshot"), sorted(after11b),
         after11b.get("snapshot")))
print("[i] C7 stale+manual snapshot_after=%s" % st7m.get("snapshot"))
print("[i] C10b clamped_timeout=%.5f" % rec.get("timeout", 0))
print("[i] C11 rcs=%s blocked=%s" % (rcs, st11c.get("blocked")))
print("[i] C13a dead-relist rcs=%s blocked=%s failures=%s"
      % (rcs13, st13.get("blocked"), st13.get("consecutive_failures")))
print("[i] C14 non-matching --preds-key: rc=%s %s"
      % (rc14, {k: out14.get(k) for k in ("action", "preds_error",
                                          "preds_stale")}))
for name, ok, detail in CHECKS:
    if not ok:
        print("[FAIL] %s | %s" % (name, detail))
print("checks=%d PASS=%d FAIL=%d" % (len(CHECKS), npass, nfail))
raise SystemExit(0 if nfail == 0 else 1)
