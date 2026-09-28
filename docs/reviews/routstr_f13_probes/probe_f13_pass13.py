#!/usr/bin/env python3
"""probe_f13_pass13.py — FRESH hermetic verification harness for the routstr
delist review, findings 1-3 (thirteenth offload pass, 2026-09-28).

Written for this pass from a cold read of the artifacts; no code is reused
from probe_f13_pass11/12. Read-only with respect to every artifact: the only
paths it writes are under ~/.cache/f13p13/scratch (NEVER /tmp — this host's
/tmp is a full 5.5G tmpfs and both suites die ENOSPC there).

What it does NOT do: no network, no real subprocess, no file-backed sqlite.
It EXECUTES the module's own payload builders against a stand-in node holding
a live `models` (SALE listing) table, a live `upstream_providers` (T470
provider ladder) table and a ladder-artifact file on disk.

Run:  python3 probe_f13_pass13.py        (twice; output must be byte-identical)
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
import shutil
import sqlite3
import sys
import time
import types
from pathlib import Path

# ── paths ─────────────────────────────────────────────────────────────────
HOME = Path.home()
BOT = HOME / ".hermes" / "bot"
REPO = Path("/home/c03rad0r/repos/merchant-routing")

SCRIPT_BOT = BOT / "scripts" / "routstr_delist.py"
SCRIPT_REPO = REPO / "src" / "routstr_delist.py"
TESTS_BOT = BOT / "tests" / "test_routstr_delist.py"
CONTRACT = REPO / "tests" / "test_routstr_delist_contract.py"
MAIN_TESTS = REPO / "tests" / "test_routstr_delist.py"
DOC = REPO / "docs" / "routstr-delist.md"
DOC_BOT = BOT / "docs" / "routstr-delist.md"
CONTRACT_MD = BOT / "docs" / "routstr_delist_contract.md"
DELIVERABLE = REPO / "docs" / "reviews" / "findings_1_3.md"
DELIVERABLE_BOT = BOT / "docs" / "reviews" / "findings_1_3.md"

SCRATCH = HOME / ".cache" / "f13p13" / "scratch"
shutil.rmtree(SCRATCH, ignore_errors=True)          # no cross-invocation leaks
SCRATCH.mkdir(parents=True, exist_ok=True)

PROBE_OUT = Path(__file__).resolve().with_name("pass13_output.txt")
PROBE_OUT_BYTES = PROBE_OUT.stat().st_size if PROBE_OUT.is_file() else 0


class _Tee(io.TextIOBase):
    """Mirror stdout so the archived transcript is byte-identical to the run."""

    def __init__(self, real):
        self.real, self.buf = real, io.StringIO()

    def write(self, s):
        self.buf.write(s)
        return self.real.write(s)

    def flush(self):
        self.real.flush()


_TEE = _Tee(sys.stdout)
sys.stdout = _TEE

sys.path.insert(0, str(SCRIPT_BOT.parent))
import routstr_delist as rd  # noqa: E402

SRC = SCRIPT_BOT.read_text(encoding="utf-8")
LINES = SRC.splitlines()

RESULTS: list[tuple[str, bool, str]] = []


def ck(tag: str, ok: bool, detail: str = "") -> bool:
    RESULTS.append((tag, bool(ok), detail))
    return bool(ok)


def md5(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


def hdr(text: str) -> None:
    print(text)


# ── AST helpers (docstring-aware, no descent into literals) ───────────────
TREE = ast.parse(SRC)


def _docstring_spans(tree) -> list[tuple[int, int]]:
    spans = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and \
                    isinstance(body[0].value, ast.Constant) and \
                    isinstance(body[0].value.value, str):
                spans.append((body[0].lineno, body[0].end_lineno or body[0].lineno))
    return spans


DOC_SPANS = _docstring_spans(TREE)


def _in_doc(lineno: int) -> bool:
    return any(a <= lineno <= b for a, b in DOC_SPANS)


def walk_no_literal_descent(node):
    """Walk the tree but STOP at every string literal, so an implicitly
    concatenated payload (plain strings + f-string) is reported exactly ONCE
    with the lineno of its first element, instead of once per merged Constant."""
    yield node
    if isinstance(node, (ast.Constant, ast.JoinedStr)):
        return
    for child in ast.iter_child_nodes(node):
        yield from walk_no_literal_descent(child)


def collect_strings(tree, *, in_docstring: bool):
    out = []
    for node in walk_no_literal_descent(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if _in_doc(node.lineno) is in_docstring:
                out.append((node, node.lineno, node.value))
        elif isinstance(node, ast.JoinedStr):
            if _in_doc(node.lineno) is in_docstring:
                parts = [v.value for v in node.values
                         if isinstance(v, ast.Constant) and isinstance(v.value, str)]
                out.append((node, node.lineno, "".join(parts)))
    return out


SQL_TABLE_RE = re.compile(
    r"\b(?:FROM|INTO|UPDATE|JOIN|TABLE)\s+([A-Za-z_][A-Za-z0-9_]*)", re.I)
SQL_VERB_RE = re.compile(r"\b(SELECT|INSERT|UPDATE|DELETE|REPLACE|DROP|ALTER)\b", re.I)
MUTATING_RE = re.compile(r"\b(INSERT|UPDATE|DELETE|REPLACE|DROP|ALTER)\b", re.I)

EXEC_STRINGS = collect_strings(TREE, in_docstring=False)
ALL_STRINGS = collect_strings(TREE, in_docstring=True)


# ── stand-in sell node (hermetic: named shared-cache in-memory sqlite) ────
ADVERTISED = ["gpt-4o", "claude-3-5-sonnet", "llama-3.1-405b"]
OPERATOR_DISABLED = ["operator-disabled-model"]
PROVIDERS = [("openrouter", 1, 20.0), ("routstr", 1, 10.0), ("zai", 1, 30.0)]


class Clock:
    def __init__(self):
        self._m = 0.0

    def monotonic(self):
        return self._m

    @staticmethod
    def time():
        return time.time()

    def advance(self, s):
        self._m += s


class Node:
    def __init__(self, tmp: Path):
        self.ladder = tmp / "t470_ladder.json"
        self.ladder.write_bytes(json.dumps(
            {"ladder": [{"name": n, "enabled": bool(e), "weight": w,
                         "candidate": True} for n, e, w in PROVIDERS]},
            indent=2, sort_keys=True).encode())
        self._uri = f"file:rdnode{os.getpid()}x{id(self):x}?mode=memory&cache=shared"
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
        self.round_trip_s = 0.0
        shim = types.ModuleType("sqlite3")
        shim.connect = self._connect
        self._shim = shim

    def _connect(self, _path=None):
        return sqlite3.connect(self._uri, uri=True)

    def models_map(self):
        return dict(self._con.execute("SELECT name, enabled FROM models"))

    def providers(self):
        return list(self._con.execute(
            "SELECT name, enabled, weight FROM upstream_providers ORDER BY name"))

    def ladder_bytes(self):
        return self.ladder.read_bytes()

    def kinds(self):
        return [k for k, _ in self.calls]

    def _import(self, name, globals=None, locals=None, fromlist=(), level=0):
        if name == "sqlite3":
            return self._shim
        return builtins.__import__(name, globals, locals, fromlist, level)

    def execute(self, kind, payload):
        revert = None
        if kind == "pull" and not self.pull_lands:
            revert = self.models_map()
        if kind == "relist" and not self.relist_lands:
            revert = self.models_map()
        out = io.StringIO()
        g = {"__builtins__": {"__import__": self._import, "print": print}}
        with contextlib.redirect_stdout(out):
            exec(payload, g)  # noqa: S102 — executing the module's OWN builders
        if revert is not None:                     # the UPDATE "never landed"
            con = self._connect()
            for name, enabled in revert.items():
                con.execute("UPDATE models SET enabled=? WHERE name=?", (enabled, name))
            con.commit()
            con.close()
        return json.loads(out.getvalue().strip().splitlines()[-1])


class Backend:
    """Mirror of rd._SshBackend's observable result shape."""

    def __init__(self, node: Node, clock: Clock):
        self.node, self.clock = node, clock

    def pull(self, dry_run=False, deadline=None):
        return self._rt("pull", rd.pull_listing_payload(), dry_run, deadline)

    def verify(self, dry_run=False, deadline=None):
        return self._rt("verify", rd.verify_pull_payload(), dry_run, deadline)

    def relist(self, names=None, dry_run=False, deadline=None):
        return self._rt("relist", rd.relist_payload(names or []), dry_run, deadline)

    def _rt(self, kind, payload, dry_run, deadline):
        if deadline is not None:
            remaining = deadline - self.clock.monotonic()
            self.node.deadline_log.append({
                "kind": kind, "remaining": remaining,
                "timeout": min(rd.SSH_TIMEOUT_S, max(remaining, 0.0))})
        if dry_run:
            return {"ok": True, "dry_run": True, "action": kind}
        self.node.calls.append((kind, payload))
        if self.node.ssh_down:
            return {"ok": False, "action": kind, "rc": 255, "error": "ssh refused"}
        data = self.node.execute(kind, payload)
        self.clock.advance(self.node.round_trip_s)
        return {"action": kind, "rc": 0, **data, "ok": data.get("ok") is True}


class Rig:
    def __init__(self, name: str):
        self.dir = SCRATCH / name
        self.dir.mkdir(parents=True, exist_ok=True)
        self.node = Node(self.dir)
        self.clock = Clock()
        self.state = self.dir / "state.json"
        self.override = self.dir / "override.marker"

    @contextlib.contextmanager
    def _patched(self):
        real_backend, real_time, real_fsync = rd._SshBackend, rd.time, os.fsync
        rd._SshBackend = lambda t, c: Backend(self.node, self.clock)
        rd.time = self.clock
        os.fsync = lambda fd: None     # this host's fsync can stall forever
        try:
            yield
        finally:
            rd._SshBackend, rd.time, os.fsync = real_backend, real_time, real_fsync

    def write_preds(self, preds, name="preds.json"):
        p = self.dir / name
        p.write_text(json.dumps(preds))
        return p

    def age(self, path, seconds=3600):
        old = time.time() - seconds
        os.utime(path, (old, old))
        return path

    def run(self, *argv, preds=None):
        full = ["--state", str(self.state), "--override", str(self.override)]
        if preds is not None:
            full += ["--preds", str(preds)]
        full += list(argv)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            with self._patched():
                rc = rd.main(full)
        raw = out.getvalue()
        return rc, (json.loads(raw) if raw.strip() else {}), raw

    def state_json(self):
        return rd.load_state(str(self.state))


def pred(key="zai", window="1h", hours=10.0, unc=0.05):
    return {"key": key, "window": window, "exhausts_in_hours": hours,
            "uncertainty": unc}


# ══ GROUP A — Finding 1: safety (SALE vs provider, ladder untouched) ══════
hdr("== GROUP A — Finding 1: safety (SALE vs provider, ladder untouched) ==")

ck("A0a deployed script == repo src (md5)",
   md5(SCRIPT_BOT) == md5(SCRIPT_REPO),
   f"{md5(SCRIPT_BOT)} lines={len(LINES)}")
ck("A0b deployed tests == repo contract suite (md5)",
   md5(TESTS_BOT) == md5(CONTRACT), f"{md5(TESTS_BOT)}")
ck("A0c bot docs/routstr-delist.md == repo docs/routstr-delist.md (md5)",
   md5(DOC_BOT) == md5(DOC), f"{md5(DOC)}")
ck("A0d contract md absent at the task-mandated bot path",
   not CONTRACT_MD.exists(), f"exists={CONTRACT_MD.exists()}")

# A1: SQL executable inventory
sql_entries = []
for node, ln, text in EXEC_STRINGS:
    if SQL_VERB_RE.search(text):
        for tbl in SQL_TABLE_RE.findall(text):
            sql_entries.append((ln, tbl.lower(),
                                SQL_VERB_RE.search(text).group(1).upper()))
tables = sorted({t for _, t, _ in sql_entries})
ck("A1a executable SQL inventory is exactly 5 models-table references",
   len(sql_entries) == 5 and tables == ["models"],
   f"refs={[(l, t) for l, t, _ in sql_entries]} verbs={sorted({v for _,_,v in sql_entries})}")
ck("A1c zero SQL reference names any table other than models", tables == ["models"],
   f"tables={tables}")

# A2: raw-source lines of the five SQL texts
sql_texts = ["UPDATE models SET enabled=0", "UPDATE models SET enabled=1;",
             "SELECT name FROM models WHERE enabled=1",
             "UPDATE models SET enabled=1 WHERE name IN",
             "SELECT COUNT(*) FROM models WHERE enabled=1"]
hit_lines = [i + 1 for i, l in enumerate(LINES)
             if any(t in l for t in sql_texts)]
ck("A2a the 5 SQL texts sit at raw source lines 355/361/371/394/408",
   hit_lines == [355, 361, 371, 394, 408], f"lines={hit_lines}")

# A3: upstream_providers occurrences, docstring-only
occ = [i + 1 for i, l in enumerate(LINES) if "upstream_providers" in l]
prog_occ = [i for i, l in enumerate(LINES) if "upstream_providers" in l
            and not _in_doc(i + 1)]
ck("A3a upstream_providers: 3 raw occurrences, all inside docstrings, 0 in code",
   occ == [35, 352, 771] and prog_occ == [],
   f"occurrence_lines={occ} code_lines={prog_occ} docstring_spans={DOC_SPANS[:4]}…")
ck("A3b no executable string literal ever names upstream_providers",
   not any("upstream_providers" in t for _, ln, t in ALL_STRINGS if not _in_doc(ln)),
   f"exec_strings={len(EXEC_STRINGS)}")

# A4: subprocess / eval-exec surface
sub_calls = [n.lineno for n in ast.walk(TREE)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
             and n.func.attr == "run"
             and isinstance(n.func.value, ast.Name) and n.func.value.id == "subprocess"]
shell_true = [n.lineno for n in ast.walk(TREE)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
              and n.func.attr == "run"
              and any(k.arg == "shell" and getattr(k.value, "value", False)
                      for k in n.keywords)]
ee = [n.lineno for n in ast.walk(TREE)
      if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
      and n.func.id in ("eval", "exec")]
ck("A4a exactly 2 subprocess.run sites, none with shell=True",
   sub_calls == [459, 808] and shell_true == [],
   f"subprocess={sub_calls} shell_true={shell_true}")
ck("A4b zero eval/exec call sites in the module", ee == [], f"eval_exec={ee}")

# A5: filesystem write surface
os_writes = sorted({(n.lineno, n.func.attr) for n in ast.walk(TREE)
                    if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                    and isinstance(n.func.value, ast.Name) and n.func.value.id == "os"
                    and n.func.attr in ("replace", "unlink", "remove", "makedirs",
                                        "mkdir", "rename", "chmod", "write")})
ck("A5a os write surface is the state path only (makedirs dir + tmp replace + unlink)",
   os_writes == [(229, "makedirs"), (235, "replace"), (243, "unlink")],
   f"os_writes={os_writes}")
ss_calls = [n.lineno for n in ast.walk(TREE)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
            and n.func.id == "save_state"]
ss_used = [n.lineno for n in ast.walk(TREE)
           if isinstance(n, ast.Assign)
           and any(isinstance(x, ast.Call) and isinstance(x.func, ast.Name)
                   and x.func.id == "save_state" for x in ast.walk(n))]
ck("A5b all 8 save_state call sites ignore the boolean return",
   sorted(ss_calls) == [565, 622, 629, 638, 654, 710, 732, 752] and ss_used == [],
   f"save_state={sorted(ss_calls)} return_consumed_at={ss_used}")

# A6: execution proof
r = Rig("a6")
ladder0, prov0 = r.node.ladder_bytes(), r.node.providers()
rc, out, _ = r.run("--manual")
ck("A6a manual delist confirmed rc0", rc == 0 and out.get("confirmed") is True,
   f"rc={rc} action={out.get('action')} confirmed={out.get('confirmed')}")
ck("A6b ladder artifact byte-identical across the delist",
   r.node.ladder_bytes() == ladder0, f"{len(ladder0)}B")
ck("A6c upstream_providers rows identical across the delist",
   r.node.providers() == prov0, f"{prov0}")
ck("A6d routstr provider still an enabled ladder candidate",
   any(n == "routstr" and e == 1 for n, e, _ in r.node.providers()),
   f"providers={r.node.providers()}")
ck("A6e all advertised models disabled, pre-disabled operator row stays 0",
   r.node.models_map() == {**{n: 0 for n in ADVERTISED},
                           **{n: 0 for n in OPERATOR_DISABLED}},
   f"models={r.node.models_map()}")
ck("A6f no executed payload ever named upstream_providers",
   all("upstream_providers" not in p for _, p in r.node.calls),
   f"kinds={r.node.kinds()}")

# A7: scoped relist
rc, out, _ = r.run("--relist")
ck("A7a scoped relist restores exactly the captured names",
   rc == 0 and out.get("restored") == len(ADVERTISED),
   f"rc={rc} restored={out.get('restored')}")
ck("A7b operator-disabled row never re-enabled by the scoped relist",
   all(r.node.models_map()[n] == 0 for n in OPERATOR_DISABLED),
   f"models={r.node.models_map()}")
ck("A7c ladder still byte-identical after the relist",
   r.node.ladder_bytes() == ladder0, "")

# A8: blanket relist refusal
r2 = Rig("a8")
rc, out, _ = r2.run("--relist")
ck("A8a --relist with no captured names refuses rc1 with zero remote calls",
   rc == 1 and out.get("action") == "relist_refused" and r2.node.calls == [],
   f"rc={rc} action={out.get('action')} calls={r2.node.calls}")
ck("A8b refusal wrote no delisted flag", "delisted" not in r2.state_json(),
   f"state={sorted(r2.state_json())}")

# A9: ssh argv shape
argv = rd.build_ssh_docker_cmd("debian@host", "routstr public", "print('x')")
rt = None
try:
    import shlex as _shlex
    rt = _shlex.split(argv[2])
except Exception as exc:                                   # pragma: no cover
    rt = str(exc)
ck("A9a ssh argv is 3 elements with ONE shlex-quoted remote string",
   len(argv) == 3, f"len={len(argv)}")
ck("A9b remote string re-parses to the intended argv (container with a space)",
   rt == ["docker", "exec", "routstr public", "python3", "-c", "print('x')"],
   f"{rt}")

# A10: dry-run purity
r3 = Rig("a10")
rc, out, _ = r3.run("--manual", "--dry-run")
ck("A10a dry-run fires no remote round-trip", rc == 0 and r3.node.calls == [],
   f"rc={rc} calls={r3.node.calls}")
ck("A10b dry-run introduced no durable delisted flag",
   "delisted" not in r3.state_json() and "last_dry_run" in r3.state_json(),
   f"keys={sorted(r3.state_json())}")

# ══ GROUP B — Finding 2: post-delisting confirmation via re-fetch ═════════
hdr("== GROUP B — Finding 2: post-delisting confirmation via re-fetch ==")

vp = rd.verify_pull_payload()
ck("B1a verify payload contains no mutating SQL verb",
   not MUTATING_RE.search(vp), f"{vp[:70]}…")
ck("B1b verify payload is exactly the read-only COUNT re-fetch",
   "SELECT COUNT(*) FROM models WHERE enabled=1" in vp, f"{vp[-40:]}")
gate_src = [i + 1 for i, l in enumerate(LINES)
            if 'vres.get("ok") is True and vres.get("count") == 0' in l]
confirm_src = [i + 1 for i, l in enumerate(LINES)
               if "state = update_state(state, ts=time.time(), preds=preds, delisted=True"
               in l]
ck("B2a the confirm gate is the re-fetch ok+count==0 in source",
   gate_src == [683] and confirm_src == [747],
   f"gate={gate_src} delisted_write={confirm_src}")

r = Rig("b3")
rc, out, _ = r.run("--manual")
st = r.state_json()
ck("B3a happy path rc0 confirmed with verified_count 0",
   rc == 0 and out.get("confirmed") is True and out.get("verified_count") == 0,
   f"rc={rc} confirmed={out.get('confirmed')} verified_count={out.get('verified_count')}")
ck("B3b exactly one pull + one verify",
   r.node.kinds() == ["pull", "verify"], f"{r.node.kinds()}")
ck("B3c durable delisted=true carrying the captured advertised names",
   st.get("delisted") is True and st.get("pulled_models") == ADVERTISED,
   f"pulled_models={st.get('pulled_models')}")

r = Rig("b4")
r.node.pull_lands = False
rc, out, _ = r.run("--manual")
st = r.state_json()
ck("B4a lying pull -> rc1 delist_failed refuted by the re-fetch",
   rc == 1 and out.get("action") == "delist_failed"
   and out.get("verify", {}).get("count") == 3,
   f"rc={rc} action={out.get('action')} verify={out.get('verify')}")
ck("B4b bounded in-run retry: kinds == pull,verify,pull,verify",
   r.node.kinds() == ["pull", "verify", "pull", "verify"], f"{r.node.kinds()}")
ck("B4c failed delist sets no flag and ticks the breaker",
   st.get("delisted") is False and st.get("consecutive_failures") == 1,
   f"delisted={st.get('delisted')} fails={st.get('consecutive_failures')}")

r = Rig("b5")
r.node.ssh_down = True
rc, out, _ = r.run("--manual")
ck("B5a pull transport failure -> rc1, no flag, breaker tick",
   rc == 1 and r.state_json().get("delisted") is False
   and r.state_json().get("consecutive_failures") == 1,
   f"rc={rc} action={out.get('action')}")

r = Rig("b6")
fake = {"ok": True, "count": 3}
_real_exec = r.node.execute


def _exec(kind, payload):
    if kind == "verify":
        r.node.calls.append((kind, payload))
        return dict(fake)
    return _real_exec(kind, payload)


r.node.execute = _exec
rc, out, _ = r.run("--manual")
ck("B6a a verify reporting count>0 refutes an ok pull (rc1, no flag, tick)",
   rc == 1 and r.state_json().get("delisted") is False
   and r.state_json().get("consecutive_failures") == 1,
   f"rc={rc} action={out.get('action')} count={out.get('verify', {}).get('count')}")

# B7 — the MEDIUM: relist success gated on the round-trip self-report only
r = Rig("b7")
rc0, out0, _ = r.run("--manual")
models_after_delist = r.node.models_map()
before_scope = r.state_json().get("pulled_models")
r.node.relist_lands = False                       # a LYING relist
rc1, out1, _ = r.run("--relist")
st1 = r.state_json()
ck("B7a no verify follows a relist (asymmetry measured)",
   r.node.kinds() == ["pull", "verify", "relist"],
   f"kinds={r.node.kinds()}")
ck("B7b a lying relist is reported rc0 'relist' — success faked",
   rc1 == 0 and out1.get("action") == "relist", f"rc={rc1} action={out1.get('action')}")
ck("B7c the listing was NOT restored even though relist said ok",
   r.node.models_map() == models_after_delist,
   f"models={r.node.models_map()}")
ck("B7d relist success destroys the scoped name set (pulled_models popped)",
   "pulled_models" not in st1 and bool(before_scope),
   f"before={before_scope} after={st1.get('pulled_models')}")
rc2, out2, _ = r.run("--relist")
ck("B7e a following scoped relist is now refused (recovery needs --relist-any)",
   rc2 == 1 and out2.get("action") == "relist_refused",
   f"rc={rc2} action={out2.get('action')}")
r.node.relist_lands = True
rc3, out3, _ = r.run("--relist", "--relist-any")
ck("B7f --relist-any executes the blanket relist that re-enables operator rows",
   rc3 == 0 and all(v == 1 for v in r.node.models_map().values()),
   f"models={r.node.models_map()}")

r = Rig("b8")
ck("B8a a verify result with no 'count' key cannot confirm (None == 0 is False)",
   (None == 0) is False and rd.pull_listing_payload().count("pulled") == 1,
   "gate is vres.get('count') == 0 with ok is True")

# ══ GROUP C — Finding 3: fail-safe on absent, garbage, stale ══════════════
hdr("== GROUP C — Finding 3: fail-safe on absent, garbage, stale ==")

now = time.time()
p = r.dir / "stale_probe.json"
p.write_text("[]")
stim = {}
stim["missing"] = rd.feed_is_stale(str(r.dir / "nope.json"), now=now)
p.write_text("[]")
os.utime(p, (now - 3600, now - 3600))
stim["aged_3600"] = rd.feed_is_stale(str(p), now=now)
os.utime(p, (now + 600, now + 600))
stim["future_mtime"] = rd.feed_is_stale(str(p), now=now)
os.utime(p, (now, now))
stim["fresh"] = rd.feed_is_stale(str(p), now=now)
os.utime(p, (now - 1800, now - 1800))
stim["boundary_exact_1800"] = rd.feed_is_stale(str(p), now=now)
os.utime(p, (now - 1800.5, now - 1800.5))
stim["over_boundary_1800.5"] = rd.feed_is_stale(str(p), now=now)
ck("C1a staleness: missing/aged/future are stale; fresh and the exact "
   "boundary are NOT",
   stim == {"missing": True, "aged_3600": True, "future_mtime": True,
            "fresh": False, "boundary_exact_1800": False,
            "over_boundary_1800.5": True}, f"{stim}")

r = Rig("c2")
base = r.write_preds([pred(hours=10.0)])
r.run(preds=base)                                     # store a baseline
snap0 = r.state_json().get("snapshot")
stale = r.age(r.write_preds([pred(hours=4.0, unc=0.9)], name="stale.json"))
rc, out, _ = r.run(preds=stale)
ck("C2a stale feed: rc1, preds_stale, no fire, zero remote calls",
   rc == 1 and out.get("action") == "none" and out.get("preds_stale") is True
   and r.node.calls == [],
   f"rc={rc} action={out.get('action')} preds_stale={out.get('preds_stale')} calls={r.node.calls}")
ck("C2b stale feed left the stored baseline untouched",
   r.state_json().get("snapshot") == snap0,
   f"snapshot={r.state_json().get('snapshot')}")
fresh_same = r.write_preds([pred(hours=4.0, unc=0.9)], name="fresh.json")
rc, out, _ = r.run(preds=fresh_same)
ck("C2c control: the identical numbers with a FRESH mtime DO delist",
   rc == 0 and out.get("action") == "delist", f"rc={rc} action={out.get('action')}")

r = Rig("c4")
r.run(preds=r.write_preds([pred(hours=10.0)]))
snap0 = r.state_json().get("snapshot")
bad = r.dir / "bad.json"
bad.write_text("{not json at all")
rc, out, _ = r.run(preds=bad)
ck("C4a garbage feed: rc1, preds_error true, action none, no fire",
   rc == 1 and out.get("preds_error") is True and out.get("action") == "none",
   f"rc={rc} preds_error={out.get('preds_error')}")
ck("C4b garbage feed never wiped the stored baseline",
   r.state_json().get("snapshot") == snap0,
   f"snapshot={r.state_json().get('snapshot')}")
r.age(bad, 3600)
rc, out, _ = r.run(preds=bad)
ck("C4c garbage AND aged reports preds_error=true, preds_stale=false",
   rc == 1 and out.get("preds_error") is True and out.get("preds_stale") is False,
   f"rc={rc} preds_error={out.get('preds_error')} preds_stale={out.get('preds_stale')}")

empty = r.dir / "empty.json"
empty.write_text("[]")
rc, out, _ = r.run(preds=empty)
ck("C5a an EMPTY (but valid, readable) --preds list is reported as a FEED ERROR",
   rc == 1 and out.get("preds_error") is True and out.get("action") == "none"
   and r.node.calls == [],
   f"rc={rc} preds_error={out.get('preds_error')} action={out.get('action')}")

r = Rig("c6")
mal = r.write_preds([{"key": "zai", "window": "1h", "exhausts_in_hours": "10",
                      "uncertainty": "0.9"},
                     {"key": "zai", "window": "2h", "exhausts_in_hours": True,
                      "uncertainty": True},
                     {"key": "zai", "window": "3h", "exhausts_in_hours": None,
                      "uncertainty": None},
                     "not-a-dict", 42])
rc, out, _ = r.run(preds=mal)
ck("C6a malformed types never fire and never crash",
   rc == 0 and out.get("action") == "none" and r.node.calls == [],
   f"rc={rc} action={out.get('action')}")
dec = rd.evaluate_triggers([{"key": "zai", "window": "1h",
                             "exhausts_in_hours": "10", "uncertainty": "0.9"},
                            {"key": "zai", "window": "2h",
                             "exhausts_in_hours": True, "uncertainty": True}],
                           {})
ck("C6b evaluate_triggers on the same malformed feed fires nothing",
   dec["fire"] is False, f"{dec['triggers']}")
ck("C6c cosmetic: _hours accepts a bool while the variance guard excludes it",
   rd._hours({"exhausts_in_hours": True}) is True
   and rd.variance_jumped([{"key": "z", "window": "1h", "uncertainty": True}]) == [],
   "bool flows into hours, never into variance")

r = Rig("c7")
stale_o = r.age(r.write_preds([pred(hours=10.0, unc=0.9)]))
rc, out, _ = r.run("--manual", preds=stale_o)
ck("C7a manual override delists despite a stale feed (observed, not obeyed)",
   rc == 0 and out.get("action") == "delist" and out.get("preds_stale") is True
   and r.node.kinds() == ["pull", "verify"],
   f"rc={rc} preds_stale={out.get('preds_stale')} kinds={r.node.kinds()}")
ck("C7b the stale fire path did NOT consume/refresh the baseline",
   r.state_json().get("snapshot") in (None, {}),
   f"snapshot={r.state_json().get('snapshot')}")

r = Rig("c8")
unscoped = r.write_preds([pred(key="openrouter", hours=10.0, unc=0.95)])
rc, out, _ = r.run(preds=unscoped)
ck("C8a unscoped default: a foreign key's variance spike fires the routstr delist",
   rc == 0 and out.get("action") == "delist", f"rc={rc} action={out.get('action')}")
r2 = Rig("c8b")
rc, out, _ = r2.run("--preds-key", "zai", preds=r2.write_preds(
    [pred(key="openrouter", hours=10.0, unc=0.95)]))
ck("C8b with --preds-key zai the same feed is quiet",
   rc == 0 and out.get("action") == "none" and r2.node.calls == [],
   f"rc={rc} action={out.get('action')}")
ck("C8c evaluate_triggers applies no implicit key filter",
   rd.evaluate_triggers([pred(key="openrouter", unc=0.95)], {})["fire"] is True,
   "no key argument exists in the signature")

r = Rig("c9")
r.run("--preds-key", "zai", preds=r.write_preds(
    [pred(key="zai", hours=10.0), pred(key="openrouter", hours=10.0)], name="p1.json"))
snap = r.state_json().get("snapshot", {})
ck("C9a a scoped run narrows the durable baseline to the scoped key only",
   set(snap) == {"zai\x1f1h"}, f"snapshot={snap}")

r = Rig("c10")
spawned = []
real_sub = rd.subprocess.run
_real_backend_cls = rd._SshBackend


class _P:
    returncode = 0
    stdout = '{"ok": true}'
    stderr = ""


def fake_run(cmd, **kw):
    spawned.append(kw)
    return _P()


try:
    rd.subprocess.run = fake_run
    be = _real_backend_cls("debian@23.182.128.51", "routstr-public")
    spawned.clear()
    res_past = be._run(rd.pull_listing_payload(), dry_run=False, action="pull",
                       deadline=time.monotonic() - 1)
    past_spawns = list(spawned)
finally:
    rd.subprocess.run = real_sub
ck("C10a an exhausted action budget returns ok=False and spawns NO subprocess",
   res_past.get("ok") is False
   and res_past.get("error") == "action budget exhausted" and past_spawns == [],
   f"{res_past} spawned={len(past_spawns)}")

spawned_ok = []
try:
    rd.subprocess.run = fake_run
    spawned.clear()
    be = _real_backend_cls("debian@23.182.128.51", "routstr-public")
    res_clamped = be._run(rd.pull_listing_payload(), dry_run=False,
                          action="pull", deadline=time.monotonic() + 5)
    spawned_ok = list(spawned)
finally:
    rd.subprocess.run = real_sub
ck("C10b the per-round-trip timeout is clamped to the remaining budget",
   len(spawned_ok) == 1 and 0 < spawned_ok[0].get("timeout", 0) <= 5.0,
   f"timeouts={[round(s.get('timeout', -1), 3) for s in spawned_ok]}")

r = Rig("c11")
r.node.ssh_down = True
rcs = [r.run("--manual")[0] for _ in range(3)]
st = r.state_json()
ck("C11a three consecutive failed runs block: rcs == [1, 1, 3] and blocked durable",
   rcs == [1, 1, 3] and st.get("blocked") is True
   and st.get("consecutive_failures") == rd.BREAKER_THRESHOLD,
   f"rcs={rcs} blocked={st.get('blocked')} fails={st.get('consecutive_failures')}")
r.node.ssh_down = False
before_calls = len(r.node.calls)
rc, out, _ = r.run("--manual")
ck("C11b a blocked run refuses ALL remote action before contacting the node",
   rc == 3 and out.get("action") == "blocked"
   and len(r.node.calls) == before_calls,
   f"rc={rc} action={out.get('action')} calls_delta={len(r.node.calls)-before_calls}")

r = Rig("c12")
r.run("--manual", "--dry-run")
ck("C12a dry-run never counts toward the breaker",
   r.state_json().get("consecutive_failures") is None
   and r.state_json().get("blocked") is None,
   f"state={sorted(r.state_json())}")

# ══ GROUP D — citation audit for every file:line asserted in the report ═══
hdr("== GROUP D — citation audit for every file:line asserted in the report ==")

CITE_FILES = {"routstr_delist.py": SCRIPT_BOT, "contract": CONTRACT,
              "tests": MAIN_TESTS, "docs": DOC, "routstr-delist.md": DOC}
EXPECT = {
    ("routstr_delist.py", 355): "UPDATE models SET enabled=0",
    ("routstr_delist.py", 361): "UPDATE models SET enabled=1",
    ("routstr_delist.py", 371): "SELECT name FROM models",
    ("routstr_delist.py", 394): "WHERE name IN",
    ("routstr_delist.py", 408): "SELECT COUNT(*) FROM models",
    ("routstr_delist.py", 683): 'vres.get("count") == 0',
    ("routstr_delist.py", 682): "backend.verify",
    ("routstr_delist.py", 747): "delisted=True",
    ("routstr_delist.py", 626): 'if not res.get("ok")',
    ("routstr_delist.py", 635): 'state.pop("pulled_models"',
    ("routstr_delist.py", 602): "if not names and not args.relist_any",
    ("routstr_delist.py", 494): "return not (0 <= age <= max_age_s)",
    ("routstr_delist.py", 485): "def feed_is_stale",
    ("routstr_delist.py", 589): "preds_stale = bool(args.preds)",
    ("routstr_delist.py", 649): 'fire = args.delist or dec["fire"]',
    ("routstr_delist.py", 317): "bool(accel or var or override)",
    ("routstr_delist.py", 303): "variance_jumped(preds_now, threshold=",
    ("routstr_delist.py", 261): "if preds:",
    ("routstr_delist.py", 152): "isinstance(unc, bool)",
    ("routstr_delist.py", 172): "os.path.isfile(override_path)",
    ("routstr_delist.py", 75): "MAX_PULL_ATTEMPTS",
    ("routstr_delist.py", 78): "STALENESS_S",
    ("routstr_delist.py", 526): "--relist-any",
    ("routstr_delist.py", 536): "--ssh-target",
    ("routstr_delist.py", 537): "--container",
    ("routstr_delist.py", 808): "proc = subprocess.run",
    ("routstr_delist.py", 459): "subprocess.run(argv",
    ("contract", 50): '"scripts"',
    ("contract", 108): "t470_ladder.json",
    ("contract", 334): '["pull", "verify"]',
    ("contract", 346): "test_unverified_pull_is_a_failed_delist",
    ("contract", 468): "class TestSemanticGuardLadderUntouched",
    ("contract", 483): "upstream_providers",
    ("contract", 487): "routstr",
    ("contract", 308): "test_first_run_without_baseline_is_quiet",
    ("contract", 731): "test_dry_run_publishes_no_event_and_flips_no_flag",
    ("contract", 257): "os, \"fsync\"",
    ("tests", 302): "class TestSaleNotProvider",
    ("tests", 345): "def test_ssh_cmd_is_single_shlex_safe_remote_command",
    ("tests", 353): "assertEqual(len(cmd), 3)",
    ("tests", 427): None,          # NOT a main-suite line — see D5
    ("tests", 566): "class TestRefetchConfirmation",
    ("tests", 816): "class TestCircuitBreaker",
    ("tests", 928): "class TestStalenessGuard",
    ("tests", 937): "def test_stale_feed_never_triggers",
    ("tests", 968): "def test_staleness_threshold_boundary",
    ("tests", 980): "def test_stale_feed_exit_zero_when_override_fires",
    ("tests", 995): "def test_stale_feed_baseline_not_consumed",
    ("tests", 1072): "class TestDryRunPurity",
    ("tests", 1166): "name IN (?,?)",
    ("tests", 146): "def test_non_numeric_uncertainty_ignored_not_crash",
    ("docs", 29): "No blanket relist",
    ("docs", 54): "--preds-key",
    ("docs", 57): "STALENESS_S",
    ("docs", 60): "never gated on freshness",
    ("docs", 69): "Re-fetch confirmation",
    ("docs", 86): "baseline is never wiped",
    ("docs", 137): "shlex",
    ("docs", 32): "relist-any",
}
bad = []
for (fname, ln), needle in EXPECT.items():
    if needle is None:
        continue
    f = CITE_FILES[fname]
    lines = f.read_text(encoding="utf-8").splitlines()
    if not (1 <= ln <= len(lines)):
        bad.append(f"{fname}:{ln} out of range")
        continue
    if needle not in lines[ln - 1]:
        bad.append(f"{fname}:{ln} missing {needle!r} (got {lines[ln-1].strip()[:70]!r})")
ck(f"D1 all {sum(1 for v in EXPECT.values() if v)} load-bearing file:line pairs "
   "resolve to the expected text", not bad, f"mismatches={bad}")

# D5 — the file:line for a NAMED test must name the file that really holds it
main_txt = MAIN_TESTS.read_text(encoding="utf-8")
cit_txt = DELIVERABLE.read_text(encoding="utf-8") if DELIVERABLE.is_file() else ""
main_lines = main_txt.splitlines()
mis = []
for m in re.finditer(r"`tests:(\d+)`\s*\(`([A-Za-z_][A-Za-z0-9_]*)`\)", cit_txt):
    ln_, name = int(m.group(1)), m.group(2)
    window = main_lines[max(0, ln_ - 3):ln_ + 2]
    if not any(name in w for w in window):
        mis.append(f"tests:{ln_} names {name!r}, absent from the main suite")
ck("D5 every `tests:N (name)` pin names a test that really lives at that main-suite line",
   not mis, f"mis-filed={mis} "
   f"(contract:427 {main_lines[426].strip()[:40]!r} is not it)")

# deliverable citation audit (runs whether or not the report is already written)
cite_count = 0
if DELIVERABLE.is_file():
    text = DELIVERABLE.read_text(encoding="utf-8")
    pat = re.compile(r"\b(?:routstr_delist\.py|contract|tests|docs):(\d+)(?:-(\d+))?")
    unresolved = []
    for m in pat.finditer(text):
        fname = m.group(0).split(":")[0]
        a, b = int(m.group(1)), int(m.group(2) or m.group(1))
        f = CITE_FILES.get(fname)
        n = len(f.read_text(encoding="utf-8").splitlines()) if f else 0
        cite_count += 1
        if not f or a < 1 or b > n or a > b:
            unresolved.append(m.group(0))
    sect = re.findall(r"^## Finding ", text, re.M)
    sev = re.findall(r"severity: \*\*(BLOCKER|HIGH|MEDIUM|LOW|OK)", text)
    ck("D2 every file:line citation in the deliverable resolves in its file",
       not unresolved,
       f"citations={cite_count} unresolved={unresolved}")
    ck("D3 the deliverable has exactly three finding sections, each with a severity",
       len(sect) == 3 and len(sev) >= 3,
       f"sections={len(sect)} severities={sev}")
    ck("D4 deliverable is mirrored byte-identically to the bot path",
       DELIVERABLE_BOT.is_file()
       and md5(DELIVERABLE) == md5(DELIVERABLE_BOT),
       f"{md5(DELIVERABLE)}")
else:
    ck("D2 deliverable present for citation audit", False, "missing")

# ══ summary ═══════════════════════════════════════════════════════════════
fails = [(t, d) for t, ok, d in RESULTS if not ok]
for tag, ok, detail in RESULTS:
    print(f"{'PASS' if ok else 'FAIL'} {tag}" + (f" :: {detail}" if detail else ""))
print()
print(f"== probe_f13_pass13: {len(RESULTS) - len(fails)}/{len(RESULTS)} PASS ==")
sys.stdout = _TEE.real
transcript = _TEE.buf.getvalue()
PROBE_OUT.write_text(transcript, encoding="utf-8")
print(f"(transcript archived: {PROBE_OUT} — {len(transcript)} B; "
      f"prior size {PROBE_OUT_BYTES} B)")
raise SystemExit(0 if not fails else 1)
