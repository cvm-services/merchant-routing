#!/usr/bin/env python3
"""pass-14 hermetic re-derivation probe for routstr-delist findings 1-3.

Written from scratch for this pass (NOT derived from any earlier probe):

  group A  Finding 1 -- safety: SALE-delist never disables the provider and
                        never touches the T470 flat-router ladder
  group B  Finding 2 -- post-delisting confirmation via an independent re-fetch
  group C  Finding 3 -- fail-safe behaviour on absent / garbage / stale signal
  group D  citation + shape audit of the deliverable itself

Hermetic: the ssh boundary is replaced by a stand-in sell node whose `models`
(SALE listing) and `upstream_providers` (provider ladder) tables are real
in-memory sqlite, plus a ladder-artifact file on disk.  No network, no real
subprocess, no file-backed sqlite.  Scratch lives under ~/.cache (never /tmp,
which is a 100%-full tmpfs on this host).

Read-only with respect to the artifacts under review: the only paths written
are this script's own scratch dir and (via the shell redirect) its transcript.
"""
from __future__ import annotations

import ast
import builtins
import contextlib
import io
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import types
from pathlib import Path

HOME = Path.home()
REPO = Path("/home/c03rad0r/repos/merchant-routing")
BOT = HOME / ".hermes" / "bot"

SCRIPT_REPO = REPO / "src" / "routstr_delist.py"
SCRIPT_BOT = BOT / "scripts" / "routstr_delist.py"
CONTRACT_REPO = REPO / "tests" / "test_routstr_delist_contract.py"
CONTRACT_BOT = BOT / "tests" / "test_routstr_delist.py"
MAIN = REPO / "tests" / "test_routstr_delist.py"
DOC = REPO / "docs" / "routstr-delist.md"
DOC_BOT = BOT / "docs" / "routstr-delist.md"
DELIV = REPO / "docs" / "reviews" / "findings_1_3.md"
DELIV_BOT = BOT / "docs" / "reviews" / "findings_1_3.md"
CONTRACT_MD = BOT / "docs" / "routstr_delist_contract.md"

SCRATCH = HOME / ".cache" / "f13p14" / "scratch"
shutil.rmtree(SCRATCH, ignore_errors=True)          # never leak across runs
SCRATCH.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(REPO / "src"))
import routstr_delist as rd  # noqa: E402

ADVERTISED = ["gpt-4o", "claude-3-5-sonnet", "llama-3.1-405b"]
OP_DISABLED = ["operator-disabled-model"]
PROVIDERS = [("openrouter", 1, 20.0), ("routstr", 1, 10.0), ("zai", 1, 30.0)]

RESULTS: list[tuple[str, bool, str]] = []


def ck(tag: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((tag, bool(ok), detail))
    print(f"{'PASS' if ok else 'FAIL'} {tag} :: {detail}")


def hdr(text: str) -> None:
    print(f"== {text} ==")


def md5(p: Path) -> str:
    import hashlib
    return hashlib.md5(p.read_bytes()).hexdigest()


def pred(key="zai", window="1h", hours=10.0, unc=0.05):
    return {"key": key, "window": window,
            "exhausts_in_hours": hours, "uncertainty": unc}


# ── AST helpers ───────────────────────────────────────────────────────────
def docstring_spans(tree) -> list:
    spans = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and \
                    isinstance(body[0].value, ast.Constant) and \
                    isinstance(body[0].value.value, str):
                c = body[0].value
                spans.append((c.lineno, getattr(c, "end_lineno", c.lineno)))
    return spans


def collect_strings(tree):
    """Every string literal in the module, WITHOUT descending into a JoinedStr
    (an implicitly concatenated f-string payload is therefore counted ONCE, at
    its own start line, carrying the whole concatenated text)."""
    spans = docstring_spans(tree)
    out = []

    def in_doc(lineno):
        return any(a <= lineno <= b for a, b in spans)

    class V(ast.NodeVisitor):
        def visit_JoinedStr(self, node):
            parts = []
            for v in node.values:
                if isinstance(v, ast.Constant) and isinstance(v.value, str):
                    parts.append(v.value)
            txt = "".join(parts)
            if not in_doc(node.lineno):
                out.append((node.lineno, txt, "joined"))
            # deliberately no generic_visit -> inner Constants not re-counted

        def visit_Constant(self, node):
            if isinstance(node.value, str) and not in_doc(node.lineno):
                out.append((node.lineno, node.value, "const"))

    V().visit(tree)
    return out, spans


# ── Fake sell node / backend / CLI rig ────────────────────────────────────
class FakeTime:
    def __init__(self):
        self._m = 0.0

    def monotonic(self):
        return self._m

    @staticmethod
    def time():
        return time.time()

    def advance(self, s):
        self._m += s

    @property
    def now(self):
        return self._m


class Node:
    def __init__(self, d: Path):
        self.ladder = d / "t470_ladder.json"
        self.ladder.write_bytes(json.dumps(
            {"ladder": [{"name": n, "enabled": bool(e), "weight": w,
                         "candidate": True} for n, e, w in PROVIDERS]},
            indent=2, sort_keys=True).encode())
        self.uri = (f"file:node14{os.getpid()}x{id(self):x}"
                    f"?mode=memory&cache=shared")
        con = self._connect()
        con.execute("CREATE TABLE models "
                    "(name TEXT PRIMARY KEY, enabled INTEGER NOT NULL)")
        for n in ADVERTISED:
            con.execute("INSERT INTO models VALUES (?,1)", (n,))
        for n in OP_DISABLED:
            con.execute("INSERT INTO models VALUES (?,0)", (n,))
        con.execute("CREATE TABLE upstream_providers "
                    "(name TEXT PRIMARY KEY, enabled INTEGER NOT NULL, "
                    "weight REAL NOT NULL)")
        for r in PROVIDERS:
            con.execute("INSERT INTO upstream_providers VALUES (?,?,?)", r)
        con.commit()
        self._con = con            # held open: keeps the named memory db alive
        self.calls = []
        self.deadline_log = []
        self.transport_down = False
        self.pull_lands = True
        self.relist_lands = True
        self.round_trip_s = 0.0
        shim = types.ModuleType("sqlite3")
        shim.connect = self._connect
        self._shim = shim

    def _connect(self, _path=None):
        return sqlite3.connect(self.uri, uri=True)

    def _imp(self, name, globals=None, locals=None, fromlist=(), level=0):
        if name == "sqlite3":
            return self._shim
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

    def exec_payload(self, kind, payload):
        revert = None
        if kind == "pull" and not self.pull_lands:
            revert = self.models_map()
        if kind == "relist" and not self.relist_lands:
            revert = self.models_map()
        out = io.StringIO()
        g = {"__builtins__": {"__import__": self._imp, "print": print}}
        with contextlib.redirect_stdout(out):
            exec(payload, g)  # noqa: S102 -- executing the module's OWN builders
        if revert is not None:
            con = self._connect()
            for nm, en in revert.items():
                con.execute("UPDATE models SET enabled=? WHERE name=?",
                            (en, nm))
            con.commit()
            con.close()
        return json.loads(out.getvalue().strip().splitlines()[-1])


class Backend:
    def __init__(self, node, clock):
        self.node = node
        self.clock = clock

    def pull(self, dry_run=False, deadline=None):
        return self._rt("pull", rd.pull_listing_payload(), dry_run, deadline)

    def verify(self, dry_run=False, deadline=None):
        return self._rt("verify", rd.verify_pull_payload(), dry_run, deadline)

    def relist(self, names=None, dry_run=False, deadline=None):
        return self._rt("relist", rd.relist_payload(names or []),
                        dry_run, deadline)

    def _rt(self, kind, payload, dry_run, deadline):
        n = self.node
        if deadline is not None:
            rem = deadline - self.clock.monotonic()
            n.deadline_log.append({"kind": kind, "remaining": rem,
                                   "timeout": min(rd.SSH_TIMEOUT_S,
                                                  max(rem, 0.0))})
        if dry_run:
            return {"ok": True, "dry_run": True, "action": kind}
        n.calls.append((kind, payload))
        if n.transport_down:
            return {"ok": False, "action": kind, "rc": 255,
                    "error": "ssh: connect to host 1.2.3.4 port 22: "
                             "Connection refused (simulated)"}
        data = n.exec_payload(kind, payload)
        self.clock.advance(n.round_trip_s)
        return {"action": kind, "rc": 0, **data, "ok": data.get("ok") is True}


class Rig:
    def __init__(self):
        self.tmp = Path(tempfile.mkdtemp(dir=SCRATCH))
        self.node = Node(self.tmp)
        self.clock = FakeTime()
        self.state = self.tmp / "state.json"
        self.override = self.tmp / "override"
        self._rb = rd._SshBackend
        self._rt_ = rd.time
        self._rf = os.fsync
        os.fsync = lambda fd: None          # this host's fsync can stall forever
        rd._SshBackend = lambda t, c: Backend(self.node, self.clock)
        rd.time = self.clock

    def close(self):
        rd._SshBackend = self._rb
        rd.time = self._rt_
        os.fsync = self._rf

    def write_preds(self, preds, name="preds.json"):
        p = self.tmp / name
        p.write_text(json.dumps(preds))
        return p

    def age(self, p, seconds=3600):
        old = time.time() - seconds
        os.utime(p, (old, old))
        return p

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


# ══════════════════════════════════════════════════════════════════════════
SRC = SCRIPT_REPO.read_text()
TREE = ast.parse(SRC)
SRC_LINES = SRC.splitlines()
STRINGS, DOC_SPANS = collect_strings(TREE)

hdr("GROUP A — Finding 1: safety (SALE vs provider, ladder untouched)")

ck("A0a deployed script == repo src (md5)",
   md5(SCRIPT_BOT) == md5(SCRIPT_REPO) == "2ea724ef08d857cd7b88a957300e70b4",
   f"{md5(SCRIPT_REPO)} lines={len(SRC_LINES)}")
ck("A0b deployed tests == repo contract suite (md5)",
   md5(CONTRACT_BOT) == md5(CONTRACT_REPO)
   == "031851b356f0de4089512f02f13f05cc",
   md5(CONTRACT_REPO))
ck("A0c bot docs/routstr-delist.md == repo copy (md5)",
   md5(DOC_BOT) == md5(DOC) == "e385af98b9c142eec736672d4dcca290",
   md5(DOC))
ck("A0d task-mandated contract md is ABSENT at the bot path",
   not CONTRACT_MD.exists(), f"exists={CONTRACT_MD.exists()}")

SQLRX = re.compile(r"\b(FROM|INTO|UPDATE|JOIN)\s+([A-Za-z_][A-Za-z_0-9]*)")
sql_refs = [(ln, m.group(2)) for ln, s, _k in STRINGS
            for m in [SQLRX.search(s)] if m]
verbs = sorted({m.group(1) for _ln, s, _k in STRINGS
                for m in [re.search(r"\b(UPDATE|SELECT|INSERT|DELETE)\b", s)]
                if m})
ck("A1a executable SQL inventory = exactly 5 statement sites, all models",
   len(sql_refs) == 5 and [r[0] for r in sql_refs] == [355, 361, 369, 392, 406]
   and all(t == "models" for _l, t in sql_refs),
   f"refs={sql_refs} verbs={verbs}")
ck("A1b every SQL statement site names ONLY the models table",
   {t for _l, t in sql_refs} == {"models"}, f"tables={sorted({t for _l, t in sql_refs})}")
ck("A1c mutating verbs are exactly the 3 UPDATE sites",
   len([r for r in sql_refs]) == 5
   and sorted(ln for ln, s, _k in STRINGS
              if re.search(r"\bUPDATE\b", s)) == [355, 361, 392],
   f"update_lines={sorted(ln for ln, s, _k in STRINGS if re.search(r'UPDATE', s))}")

raw_sql = [i + 1 for i, ln in enumerate(SRC_LINES)
           if re.search(r"\b(SELECT|UPDATE)\b", ln) and "models" in ln
           and not ln.lstrip().startswith("#")]
ck("A2a the 5 raw-source SQL texts sit at 355/361/371/394/408",
   raw_sql == [355, 361, 371, 394, 408], f"lines={raw_sql}")

up_raw = [i + 1 for i, ln in enumerate(SRC_LINES) if "upstream_providers" in ln]
up_code = sorted({ln for ln, s, _k in STRINGS if "upstream_providers" in s})
ck("A3a upstream_providers: 3 raw occurrences, all docstring, 0 in code",
   up_raw == [35, 352, 771] and up_code == [],
   f"raw={up_raw} code={up_code} docstring_spans={DOC_SPANS[:4]}")
ck("A3b no executable string literal names upstream_providers",
   all("upstream_providers" not in s for _l, s, _k in STRINGS),
   f"exec_strings={len(STRINGS)}")

sub_sites = []
shell_true = []
for node in ast.walk(TREE):
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
            and node.func.attr == "run" and isinstance(node.func.value, ast.Name) \
            and node.func.value.id == "subprocess":
        sub_sites.append(node.lineno)
        for kw in node.keywords:
            if kw.arg == "shell" and getattr(kw.value, "value", None) is True:
                shell_true.append(node.lineno)
ee = [n.lineno for n in ast.walk(TREE)
      if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
      and n.func.id in ("eval", "exec")]
ck("A4a exactly 2 subprocess.run sites, shell=True count 0",
   sub_sites == [459, 808] and not shell_true,
   f"subprocess={sub_sites} shell_true={shell_true}")
ck("A4b zero eval/exec call sites in the module", not ee, f"eval_exec={ee}")

os_writes = [(n.lineno, n.func.attr) for n in ast.walk(TREE)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
             and isinstance(n.func.value, ast.Name) and n.func.value.id == "os"
             and n.func.attr in ("makedirs", "replace", "unlink", "remove")]
opens = [(n.lineno, (n.args[1].value if len(n.args) > 1
                     and isinstance(n.args[1], ast.Constant) else "r"))
         for n in ast.walk(TREE)
         if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
         and n.func.id == "open"]
w_opens = sorted(ln for ln, mode in opens if mode != "r")
ck("A5a state write surface = makedirs(229) + ONE write-open(231) + replace(235) + unlink(243)",
   os_writes == [(229, "makedirs"), (235, "replace"), (243, "unlink")]
   and w_opens == [231],
   f"os_writes={os_writes} opens={opens}")

ss_nodes = [n for n in ast.walk(TREE)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
            and n.func.id == "save_state"]
ss_calls = sorted(n.lineno for n in ss_nodes)
PARENTS = {}
for n in ast.walk(TREE):
    for ch in ast.iter_child_nodes(n):
        PARENTS[id(ch)] = n
# a save_state return is CONSUMED only when the call is not a bare Expr statement
consumed = sorted(n.lineno for n in ss_nodes
                  if not isinstance(PARENTS.get(id(n)), ast.Expr))
ck("A5b all 8 save_state call sites ignore the boolean return",
   ss_calls == [565, 622, 629, 638, 654, 710, 732, 752] and consumed == [],
   f"save_state={ss_calls} return_consumed_at={consumed}")

# ── executed semantics ────────────────────────────────────────────────────
r = Rig()
rc, out, _ = r.run("--manual")
lad0 = r.node.ladder_bytes()
prov0 = r.node.providers()
ck("A6a manual delist confirms rc0", rc == 0 and out.get("action") == "delist"
   and out.get("confirmed") is True, f"rc={rc} action={out.get('action')}")
ck("A6b ladder artifact byte-identical across the delist",
   r.node.ladder_bytes() == lad0 and len(lad0) == 340, f"{len(lad0)}B")
ck("A6c upstream_providers rows identical across the delist",
   r.node.providers() == prov0, str(r.node.providers()))
ck("A6d routstr provider still an enabled ladder candidate",
   any(n == "routstr" and e == 1 for n, e, _w in r.node.providers()),
   str(r.node.providers()))
mm = r.node.models_map()
ck("A6e all advertised models disabled, pre-disabled operator row stays 0",
   all(mm[n] == 0 for n in ADVERTISED) and mm["operator-disabled-model"] == 0,
   str(mm))
ck("A6f no executed payload ever names upstream_providers",
   all("upstream_providers" not in p for _k, p in r.node.calls),
   f"kinds={r.node.kinds()}")

rc, out, _ = r.run("--relist")
ck("A7a scoped relist restores exactly the captured names",
   rc == 0 and out.get("restored") == 3,
   f"rc={rc} restored={out.get('restored')}")
mm = r.node.models_map()
ck("A7b operator-disabled row never re-enabled by the scoped relist",
   all(mm[n] == 1 for n in ADVERTISED) and mm["operator-disabled-model"] == 0,
   str(mm))
ck("A7c ladder still byte-identical after the relist",
   r.node.ladder_bytes() == lad0)
r.close()

r8 = Rig()
rc, out, _ = r8.run("--relist")
ck("A8a --relist with no captured names refuses rc1, zero remote calls",
   rc == 1 and out.get("action") == "relist_refused" and r8.node.calls == [],
   f"rc={rc} action={out.get('action')} calls={r8.node.kinds()}")
ck("A8b the refusal wrote no state file at all",
   not r8.state.exists(), f"state_exists={r8.state.exists()}")
r8.close()

cmd = rd.build_ssh_docker_cmd("debian@host", "routstr public", "print('x')")
ck("A9a ssh argv is 3 elements with ONE shlex-quoted remote string",
   isinstance(cmd, list) and len(cmd) == 3, f"len={len(cmd)}")
import shlex
ck("A9b the remote string re-parses to the intended argv (container has a space)",
   shlex.split(cmd[2]) == ["docker", "exec", "routstr public", "python3",
                           "-c", "print('x')"], str(shlex.split(cmd[2])))

r10 = Rig()
rc, out, _ = r10.run("--manual", "--dry-run")
st = json.loads(r10.state.read_text())
ck("A10a dry-run fires no remote round-trip",
   rc == 0 and r10.node.calls == [], f"rc={rc} calls={r10.node.kinds()}")
ck("A10b dry-run introduced no durable delisted flag",
   "delisted" not in st, f"keys={sorted(st)}")
r10.close()

# ══════════════════════════════════════════════════════════════════════════
hdr("GROUP B — Finding 2: post-delisting confirmation via re-fetch")
vp = rd.verify_pull_payload()
ck("B1a verify payload contains no mutating SQL verb",
   not re.search(r"\b(UPDATE|INSERT|DELETE|DROP|ALTER)\b", vp.upper()),
   vp[:90])
ck("B1b verify payload is exactly the read-only COUNT re-fetch",
   "SELECT COUNT(*) FROM models WHERE enabled=1" in vp
   and vp.rstrip().endswith("print(json.dumps({'ok':True,'count':n}))"),
   vp[-60:])
ck("B2a the confirm gate is the re-fetch ok+count==0 (line 683), flag write at 747",
   'vres.get("ok") is True and vres.get("count") == 0' in SRC_LINES[682]
   and "delisted=True" in SRC_LINES[746],
   f"L683={SRC_LINES[682].strip()[:60]!r} L747={SRC_LINES[746].strip()[:40]!r}")

rb = Rig()
rc, out, _ = rb.run("--manual")
ck("B3a happy path rc0 confirmed with verified_count 0",
   rc == 0 and out.get("confirmed") is True and out.get("verified_count") == 0,
   f"rc={rc} confirmed={out.get('confirmed')} vc={out.get('verified_count')}")
ck("B3b exactly one pull + one verify (separate round-trips)",
   rb.node.kinds() == ["pull", "verify"], str(rb.node.kinds()))
stb = json.loads(rb.state.read_text())
ck("B3c durable delisted=true carrying the captured advertised names",
   stb.get("delisted") is True and stb.get("pulled_models") == ADVERTISED,
   f"pulled_models={stb.get('pulled_models')}")
rb.close()

rb4 = Rig()
rb4.node.pull_lands = False
rc, out, _ = rb4.run("--manual")
st4 = json.loads(rb4.state.read_text())
ck("B4a lying pull -> rc1 delist_failed refuted by the re-fetch",
   rc == 1 and out.get("action") == "delist_failed"
   and out.get("verify", {}).get("count") == 3,
   f"rc={rc} action={out.get('action')} verify={out.get('verify')}")
ck("B4b bounded in-run retry: kinds == pull,verify,pull,verify",
   rb4.node.kinds() == ["pull", "verify", "pull", "verify"],
   str(rb4.node.kinds()))
ck("B4c failed delist sets no flag and ticks the breaker",
   st4.get("delisted") is False and st4.get("consecutive_failures") == 1,
   f"delisted={st4.get('delisted')} fails={st4.get('consecutive_failures')}")
ck("B4d a verify reporting count>0 refutes an ok pull (ok True, still failure)",
   out.get("verify", {}).get("ok") is True
   and out.get("verify", {}).get("count") == 3 and out.get("ok") is False,
   str(out.get("verify")))
rb4.close()

rb5 = Rig()
rb5.node.transport_down = True
rc, out, _ = rb5.run("--manual")
st5 = json.loads(rb5.state.read_text())
ck("B5a a verify transport failure is an attempt failure, not a success",
   rc == 1 and out.get("action") == "delist_failed"
   and rb5.node.kinds() == ["pull", "pull"]
   and st5.get("delisted") is False and st5.get("consecutive_failures") == 1,
   f"rc={rc} action={out.get('action')} kinds={rb5.node.kinds()}")
rb5.close()

rb7 = Rig()
rb7.run("--manual")
named_before = json.loads(rb7.state.read_text()).get("pulled_models")
rb7.node.relist_lands = False
rc, out, _ = rb7.run("--relist")
kinds7 = rb7.node.kinds()
mm7 = rb7.node.models_map()

ck("B7a no verify follows a relist (asymmetry measured)",
   kinds7 == ["pull", "verify", "relist"], str(kinds7))
ck("B7b a lying relist is reported rc0/relist -- success is faked",
   rc == 0 and out.get("action") == "relist", f"rc={rc} action={out.get('action')}")
ck("B7c the listing was NOT restored even though relist said ok",
   all(mm7[n] == 0 for n in ADVERTISED), str(mm7))
rb7_state = json.loads(rb7.state.read_text())
ck("B7d relist success destroys the scoped name set (pulled_models popped)",
   named_before == ADVERTISED and "pulled_models" not in rb7_state,
   f"before={named_before} after={rb7_state.get('pulled_models')}")
rc, out, _ = rb7.run("--relist")
ck("B7e a following scoped relist is now refused (recovery needs --relist-any)",
   rc == 1 and out.get("action") == "relist_refused", f"rc={rc}")
rb7.node.relist_lands = True            # the node heals; the operator recuperates
rc, out, _ = rb7.run("--relist", "--relist-any")
ck("B7f --relist-any executes the blanket relist that re-enables operator rows",
   rc == 0 and all(v == 1 for v in rb7.node.models_map().values()),
   str(rb7.node.models_map()))
rb7.close()

ck("B8a a verify result with no 'count' key cannot confirm (None == 0 is False)",
   'vres.get("count") == 0' in SRC_LINES[682] and (None == 0) is False,
   "gate requires ok is True AND count == 0")

# ══════════════════════════════════════════════════════════════════════════
hdr("GROUP C — Finding 3: fail-safe on absent / garbage / stale")
b_fresh = SCRATCH / "c1_fresh.json"
b_fresh.write_text("[]")
b_old = SCRATCH / "c1_old.json"
b_old.write_text("[]")
b_fut = SCRATCH / "c1_fut.json"
b_fut.write_text("[]")
b_edge = SCRATCH / "c1_edge.json"
b_edge.write_text("[]")
b_over = SCRATCH / "c1_over.json"
b_over.write_text("[]")
now = time.time()                       # capture AFTER writing the fixtures
os.utime(b_old, (now - 3600, now - 3600))
os.utime(b_fut, (now + 100, now + 100))
os.utime(b_edge, (now - 1800, now - 1800))
os.utime(b_over, (now - 1800.5, now - 1800.5))
missing = SCRATCH / "c1_missing.json"
if missing.exists():
    missing.unlink()
mat = {
    "missing": rd.feed_is_stale(str(missing), now=now),
    "aged_3600": rd.feed_is_stale(str(b_old), now=now),
    "future_mtime": rd.feed_is_stale(str(b_fut), now=now),
    "fresh": rd.feed_is_stale(str(b_fresh), now=now),
    "boundary_exact_1800": rd.feed_is_stale(str(b_edge), now=now),
    "over_boundary_1800.5": rd.feed_is_stale(str(b_over), now=now),
}
ck("C1a missing/aged/future are stale; fresh and the exact boundary are NOT",
   mat == {"missing": True, "aged_3600": True, "future_mtime": True,
           "fresh": False, "boundary_exact_1800": False,
           "over_boundary_1800.5": True}, str(mat))

rc_ = Rig()
base = rc_.write_preds([pred(hours=10.0, unc=0.05)], name="base.json")
rc_.run(preds=base)
snap0 = json.loads(rc_.state.read_text()).get("snapshot")
aged_fire = rc_.write_preds([pred(hours=4.5, unc=0.9)], name="stale.json")
rc_.age(aged_fire, 3600)
rc, out, _ = rc_.run(preds=aged_fire)
stc = json.loads(rc_.state.read_text())
ck("C2a stale feed: rc1, preds_stale, no fire, zero remote calls",
   rc == 1 and out.get("preds_stale") is True and out.get("action") == "none"
   and rc_.node.calls == [],
   f"rc={rc} preds_stale={out.get('preds_stale')} calls={rc_.node.kinds()}")
ck("C2b stale feed left the stored baseline untouched",
   stc.get("snapshot") == snap0 == {"zai\x1f1h": 10.0},
   f"snapshot={stc.get('snapshot')}")
cfresh = rc_.write_preds([pred(hours=4.5, unc=0.9)], name="fresh2.json")
rc, out, _ = rc_.run(preds=cfresh)
ck("C2c control: the identical numbers with a FRESH mtime DO delist",
   rc == 0 and out.get("action") == "delist",
   f"rc={rc} action={out.get('action')}")
rc_.close()

rg = Rig()
gb = rg.write_preds([pred(hours=10.0)], name="gbase.json")
rg.run(preds=gb)
garb = rg.tmp / "garbage.json"
garb.write_text("{not json at all")
rc, out, _ = rg.run(preds=garb)
stg = json.loads(rg.state.read_text())
ck("C4a garbage feed: rc1, preds_error true, action none, no fire",
   rc == 1 and out.get("preds_error") is True and out.get("action") == "none"
   and rg.node.calls == [], f"rc={rc} preds_error={out.get('preds_error')}")
ck("C4b garbage feed never wiped the stored baseline",
   stg.get("snapshot") == {"zai\x1f1h": 10.0}, f"snapshot={stg.get('snapshot')}")
garb2 = rg.tmp / "garbage_aged.json"
garb2.write_text("<<<>>>")
rg.age(garb2, 3600)
rc, out, _ = rg.run(preds=garb2)
ck("C4c garbage AND aged reports preds_error=true, preds_stale=false",
   rc == 1 and out.get("preds_error") is True
   and out.get("preds_stale") is False,
   f"rc={rc} preds_error={out.get('preds_error')} preds_stale={out.get('preds_stale')}")
emptyf = rg.tmp / "empty.json"
emptyf.write_text("[]")
rc, out, _ = rg.run(preds=emptyf)
ck("C5a an EMPTY (valid, readable) --preds list is reported as a FEED ERROR",
   rc == 1 and out.get("preds_error") is True and out.get("action") == "none",
   f"rc={rc} preds_error={out.get('preds_error')} action={out.get('action')}")
mal = rg.write_preds([None, "x", 1, True, {"key": "zai", "uncertainty": "hi"},
                      {"key": "zai", "uncertainty": True}], name="mal.json")
rc, out, _ = rg.run(preds=mal)
ck("C6a malformed types never fire and never crash (via the CLI)",
   rc == 0 and out.get("action") == "none", f"rc={rc} action={out.get('action')}")
CLI_NORMALISED = [{"key": "zai", "uncertainty": "hi"},
                  {"key": "zai", "uncertainty": True}]
dec = rd.evaluate_triggers(CLI_NORMALISED, None)
ck("C6b evaluate_triggers on the CLI-normalised feed fires nothing",
   dec["triggers"] == {"accel": [], "variance": [], "manual": False},
   str(dec["triggers"]))
RAW = [None, "x", 1, True] + CLI_NORMALISED
try:
    rd.evaluate_triggers(RAW, None)
    hardened = True
except AttributeError as exc:
    hardened = False
    detail6d = f"{type(exc).__name__}: {exc}"
ck("C6d OBSERVATION: the pure trigger functions are NOT type-hardened "
   "(guard lives only at the _read_preds boundary)",
   hardened is False, detail6d if not hardened else "no crash")
ck("C6c cosmetic: _hours accepts a bool while the variance guard excludes it",
   rd._hours({"exhausts_in_hours": True}) is True
   and rd.variance_jumped([pred(unc=True)]) == [],
   "bool flows into hours, never into variance")
rc, out, _ = rg.run("--manual", preds=garb)
ck("C7c manual override fires even when the feed is unparseable (garbage)",
   rc == 0 and out.get("action") == "delist"
   and out.get("preds_error") is True,
   f"rc={rc} preds_error={out.get('preds_error')} action={out.get('action')}")
rg.close()

r7 = Rig()
b7 = r7.write_preds([pred(hours=10.0, unc=0.05)], name="b7base.json")
r7.run(preds=b7)
snap7 = json.loads(r7.state.read_text()).get("snapshot")
s7 = r7.age(r7.write_preds([pred(hours=4.5, unc=0.9)], name="b7stale.json"), 3600)
rc, out, _ = r7.run("--manual", preds=s7)
st7 = json.loads(r7.state.read_text())
ck("C7a manual override delists despite a stale feed (observed, not obeyed)",
   rc == 0 and out.get("preds_stale") is True and out.get("action") == "delist"
   and r7.node.kinds()[-2:] == ["pull", "verify"],
   f"rc={rc} preds_stale={out.get('preds_stale')} kinds={r7.node.kinds()}")
ck("C7b the stale/override fire path did NOT refresh the baseline",
   snap7 == {"zai\x1f1h": 10.0} and st7.get("snapshot") == snap7,
   f"before={snap7} after={st7.get('snapshot')}")
r7.close()

ru = Rig()
rc, out, _ = ru.run(preds=ru.write_preds([pred(key="openrouter", hours=10.0,
                                               unc=0.95)]))
ck("C8a unscoped default: a foreign key's variance spike fires the routstr delist",
   rc == 0 and out.get("action") == "delist", f"rc={rc} action={out.get('action')}")
ru.close()
rs = Rig()
rc, out, _ = rs.run("--preds-key", "zai",
                    preds=rs.write_preds([pred(key="openrouter", hours=10.0,
                                               unc=0.95)]))
ck("C8b with --preds-key zai the same feed is quiet",
   rc == 0 and out.get("action") == "none", f"rc={rc} action={out.get('action')}")
rs.close()
import inspect
sig = inspect.signature(rd.evaluate_triggers)
ck("C8c evaluate_triggers applies no implicit key filter",
   "key" not in sig.parameters
   and "variance_jumped(preds_now, threshold=variance_threshold)"
   in SRC_LINES[302], str(sig))

rs9 = Rig()
rc, out, _ = rs9.run("--preds-key", "zai",
                     preds=rs9.write_preds([pred(key="zai", hours=10.0),
                                            pred(key="openrouter", hours=10.0)]))
snap9 = json.loads(rs9.state.read_text()).get("snapshot")
ck("C9a a scoped run narrows the durable baseline to the scoped key only",
   snap9 == {"zai\x1f1h": 10.0}, f"snapshot={snap9}")
rs9.close()

pb = rd._SshBackend("t", "c")
spawned = []
real_sp = rd.subprocess.run


def _spy(cmd, **kw):
    spawned.append((list(cmd), kw))
    return subprocess.CompletedProcess(cmd, 255, "", "")


rd.subprocess.run = _spy
res = pb._run(rd.pull_listing_payload(), dry_run=False, action="pull",
              deadline=time.monotonic() - 1)
ck("C10a an exhausted action budget returns ok=False and spawns NO subprocess",
   res.get("ok") is False and res.get("error") == "action budget exhausted"
   and spawned == [], f"{res} spawned={len(spawned)}")
spawned.clear()
d = time.monotonic() + 5
pb._run(rd.pull_listing_payload(), dry_run=False, action="pull", deadline=d)
to = [kw.get("timeout") for _c, kw in spawned]
ck("C10b the per-round-trip timeout is clamped to the remaining budget",
   len(to) == 1 and to[0] is not None and 4.5 < to[0] <= 5.0, f"timeouts={to}")
rd.subprocess.run = real_sp

rk = Rig()
rk.node.transport_down = True
rcs = [rk.run("--manual")[0] for _ in range(3)]
stk = json.loads(rk.state.read_text())
ck("C11a three consecutive failed runs block: rcs == [1,1,3] and blocked durable",
   rcs == [1, 1, 3] and stk.get("blocked") is True
   and stk.get("consecutive_failures") == 3,
   f"rcs={rcs} blocked={stk.get('blocked')} fails={stk.get('consecutive_failures')}")
rk.node.transport_down = False
before = len(rk.node.calls)
rc, out, _ = rk.run("--manual")
ck("C11b a blocked run refuses ALL remote action before contacting the node",
   rc == 3 and out.get("action") == "blocked" and len(rk.node.calls) == before,
   f"rc={rc} action={out.get('action')} calls_delta={len(rk.node.calls) - before}")
rk.close()

r12 = Rig()
rc, out, _ = r12.run("--manual", "--dry-run")
st12 = json.loads(r12.state.read_text())
ck("C12a dry-run never counts toward the breaker",
   "consecutive_failures" not in st12 and "blocked" not in st12,
   f"keys={sorted(st12)}")
r12.close()

hdr("GROUP C2 — breaker semantics: relist vs delist asymmetry")
rk1 = Rig()
rk1.run("--manual")                      # confirmed delist captures the names
names1 = json.loads(rk1.state.read_text()).get("pulled_models")
rk1.node.transport_down = True
rcs_r = [rk1.run("--relist")[0] for _ in range(4)]
stk1 = json.loads(rk1.state.read_text())
ck("C13a OBSERVATION: repeated FAILED relists never tick the circuit breaker",
   names1 == ADVERTISED and rcs_r == [1, 1, 1, 1]
   and stk1.get("blocked") is not True
   and stk1.get("consecutive_failures") == 0,
   f"rcs={rcs_r} blocked={stk1.get('blocked')} "
   f"fails={stk1.get('consecutive_failures')}")
rk1.close()

rk2 = Rig()
rk2.run("--manual")
rk2.node.transport_down = True
rcs_d = [rk2.run("--manual")[0] for _ in range(2)]
stk2 = json.loads(rk2.state.read_text())
rk2.node.transport_down = False
rc, out, _ = rk2.run("--relist")
stk2b = json.loads(rk2.state.read_text())
ck("C13b a successful relist clears accumulated delist failures",
   rcs_d == [1, 1] and stk2.get("consecutive_failures") == 2
   and rc == 0 and stk2b.get("consecutive_failures") == 0
   and stk2b.get("blocked") is False,
   f"fails_after_delists={stk2.get('consecutive_failures')} relist_rc={rc} "
   f"fails_after={stk2b.get('consecutive_failures')}")
rk2.close()

rk3 = Rig()
rk3.run("--manual")
rk3.node.transport_down = True
rcs_b = [rk3.run("--manual")[0] for _ in range(3)]
before3 = len(rk3.node.calls)
rk3.node.transport_down = False
rc, out, _ = rk3.run("--relist")
stk3 = json.loads(rk3.state.read_text())
ck("C13c a blocked state refuses --relist too, so :636 can only run unblocked",
   rcs_b == [1, 1, 3] and rc == 3 and out.get("action") == "blocked"
   and len(rk3.node.calls) == before3 and stk3.get("blocked") is True,
   f"rcs={rcs_b} relist_rc={rc} action={out.get('action')} "
   f"calls_delta={len(rk3.node.calls) - before3}")
rk3.close()

# ══════════════════════════════════════════════════════════════════════════
hdr("GROUP D — citation + shape audit of the deliverable")
DELIV_TXT = DELIV.read_text()
MAIN_TXT = MAIN.read_text()
CONTRACT_TXT = CONTRACT_REPO.read_text()
DOC_TXT = DOC.read_text()
SCRIPT_TXT = SRC
FILEMAP = {"routstr_delist.py": SCRIPT_TXT, "contract": CONTRACT_TXT,
           "tests": MAIN_TXT, "docs": DOC_TXT}

PAIRS = [
    ("routstr_delist.py", 355, "UPDATE models SET enabled=0 WHERE enabled=1;"),
    ("routstr_delist.py", 361, "UPDATE models SET enabled=1;"),
    ("routstr_delist.py", 369, '"import sqlite3,json;"'),
    ("routstr_delist.py", 370, "db=sqlite3.connect('/app/data/keys.db')"),
    ("routstr_delist.py", 371, "SELECT name FROM models WHERE enabled=1"),
    ("routstr_delist.py", 372, "f\"db.execute({pull_listing_sql()!r});\""),
    ("routstr_delist.py", 384, '"import sqlite3,json;"'),
    ("routstr_delist.py", 385, "db=sqlite3.connect('/app/data/keys.db')"),
    ("routstr_delist.py", 386, "f\"db.execute({relist_sql()!r});\""),
    ("routstr_delist.py", 392, '"import sqlite3,json;"'),
    ("routstr_delist.py", 393, "db=sqlite3.connect('/app/data/keys.db')"),
    ("routstr_delist.py", 394, "UPDATE models SET enabled=1 WHERE name IN"),
    ("routstr_delist.py", 406, '"import sqlite3,json;"'),
    ("routstr_delist.py", 407, "db=sqlite3.connect('/app/data/keys.db')"),
    ("routstr_delist.py", 408, "SELECT COUNT(*) FROM models WHERE enabled=1"),
    ("routstr_delist.py", 409, "fetchone()[0]"),
    ("routstr_delist.py", 35, "upstream_providers"),
    ("routstr_delist.py", 352, "upstream_providers"),
    ("routstr_delist.py", 771, "upstream_providers"),
    ("routstr_delist.py", 229, "os.makedirs"),
    ("routstr_delist.py", 231, "open(tmp"),
    ("routstr_delist.py", 235, "os.replace"),
    ("routstr_delist.py", 243, "os.unlink"),
    ("routstr_delist.py", 683, 'vres.get("ok") is True and vres.get("count") == 0'),
    ("routstr_delist.py", 747, "delisted=True"),
    ("routstr_delist.py", 626, 'if not res.get("ok"):'),
    ("routstr_delist.py", 635, 'state.pop("pulled_models", None)'),
    ("routstr_delist.py", 602, "if not names and not args.relist_any:"),
    ("routstr_delist.py", 526, "--relist-any"),
    ("routstr_delist.py", 649, 'fire = args.delist or dec["fire"]'),
    ("routstr_delist.py", 317, 'bool(accel or var or override)'),
    ("routstr_delist.py", 303, "variance_jumped(preds_now, threshold=variance_threshold)"),
    ("routstr_delist.py", 261, "if preds:"),
    ("routstr_delist.py", 107, "if not preds_now or not preds_prev:"),
    ("routstr_delist.py", 143, "if not preds:"),
    ("routstr_delist.py", 132, "def variance_jumped(preds, *, threshold=VARIANCE_THRESHOLD, key=None):"),
    ("routstr_delist.py", 152, "isinstance(unc, (int, float))"),
    ("routstr_delist.py", 272, "def evaluate_triggers(preds_now, prev_state, *, override=False,"),
    ("routstr_delist.py", 479, "return [d for d in data if isinstance(d, dict)]"),
    ("routstr_delist.py", 585, "preds_error = bool(args.preds) and not raw_preds"),
    ("routstr_delist.py", 589, "preds_stale = bool(args.preds) and bool(raw_preds)"),
    ("routstr_delist.py", 592, "raw_preds = []"),
    ("routstr_delist.py", 597, 'preds = [p for p in raw_preds if p.get("key") == args.preds_key]'),
    ("routstr_delist.py", 724, "fails += 1"),
    ("routstr_delist.py", 730, "newly_blocked = fails >= BREAKER_THRESHOLD"),
    ("routstr_delist.py", 739, "return 3 if newly_blocked else 1"),
    ("routstr_delist.py", 636, "state[\"consecutive_failures\"] = 0"),
    ("routstr_delist.py", 569, "if blocked:"),
    ("routstr_delist.py", 578, "return 3"),
    ("routstr_delist.py", 750, "state[\"consecutive_failures\"] = 0"),
    ("contract", 108, 'ladder_artifact = tmpdir / "t470_ladder.json"'),
    ("contract", 308, "def test_first_run_without_baseline_is_quiet"),
    ("contract", 731, "def test_dry_run_publishes_no_event_and_flips_no_flag"),
    ("tests", 146, "def test_non_numeric_uncertainty_ignored_not_crash"),
    ("tests", 353, "assertEqual(len(cmd), 3)"),
    ("tests", 354, "parts = shlex.split(cmd[2])"),
    ("tests", 980, "def test_stale_feed_exit_zero_when_override_fires"),
    ("routstr_delist.py", 485, "def feed_is_stale"),
    ("routstr_delist.py", 494, "return not (0 <= age <= max_age_s)"),
    ("routstr_delist.py", 78, "STALENESS_S = 1800"),
    ("routstr_delist.py", 468, "def _read_preds"),
    ("routstr_delist.py", 172, "os.path.isfile(override_path)"),
    ("routstr_delist.py", 152, "isinstance(unc, bool)"),
    ("routstr_delist.py", 400, "def verify_pull_payload"),
    ("routstr_delist.py", 682, "vres = backend.verify(deadline=deadline)"),
    ("routstr_delist.py", 790, "def verify(self, dry_run=False, deadline=None):"),
    ("routstr_delist.py", 802, "remaining = deadline - time.monotonic()"),
    ("routstr_delist.py", 806, "timeout = min(SSH_TIMEOUT_S, remaining)"),
    ("routstr_delist.py", 459, "subprocess.run(argv, timeout=30,"),
    ("routstr_delist.py", 808, "proc = subprocess.run(cmd, capture_output=True"),
    ("routstr_delist.py", 414, "def build_ssh_docker_cmd"),
    ("routstr_delist.py", 423, "remote = \" \".join([\"docker\", \"exec\""),
    ("routstr_delist.py", 699, "if args.dry_run:"),
    ("routstr_delist.py", 75, "MAX_PULL_ATTEMPTS = 2"),
    ("routstr_delist.py", 529, "--unblock"),
    ("routstr_delist.py", 77, "BREAKER_THRESHOLD = 3"),
    ("routstr_delist.py", 536, "--ssh-target"),
    ("routstr_delist.py", 537, "--container"),
    ("routstr_delist.py", 172, "os.path.isfile"),
    ("contract", 468, "class TestSemanticGuardLadderUntouched"),
    ("contract", 483, "upstream_providers"),
    ("contract", 334, '["pull", "verify"]'),
    ("contract", 346, "def test_unverified_pull_is_a_failed_delist"),
    ("contract", 427, "test_manual_override_is_never_gated_on_feed_staleness"),
    ("contract", 50, "scripts"),
    ("tests", 302, "class TestSaleNotProvider"),
    ("tests", 345, "shlex"),
    ("tests", 566, "class TestRefetchConfirmation"),
    ("tests", 816, "class TestCircuitBreaker"),
    ("tests", 928, "class TestStalenessGuard"),
    ("tests", 937, "test_stale_feed_never_triggers"),
    ("tests", 968, "test_staleness_threshold_boundary"),
    ("tests", 995, "test_stale_feed_baseline_not_consumed"),
    ("tests", 980, "test_stale_feed_exit_zero_when_override_fires"),
    ("tests", 1072, "class TestDryRunPurity"),
    ("tests", 1166, "name IN (?,?)"),
    ("docs", 29, "No blanket relist"),
    ("docs", 56, "Freshness guard (cold-review finding 3)"),
    ("docs", 57, "dead data"),
    ("docs", 60, "The manual override is never gated on freshness."),
    ("docs", 69, "Re-fetch confirmation (cold-review finding 2)"),
    ("docs", 84, "unreadable/corrupt"),
    ("docs", 86, "baseline is never wiped"),
    ("docs", 20, "never touches `upstream_providers`"),
    ("docs", 106, "--preds-key zai"),
    ("docs", 137, "shlex.quote"),
]
bad = []
for tok, ln, sub in PAIRS:
    txt = FILEMAP[tok]
    lines = txt.splitlines()
    if ln > len(lines) or sub not in lines[ln - 1]:
        got = lines[ln - 1].strip()[:70] if ln <= len(lines) else "<beyond EOF>"
        bad.append((tok, ln, sub, got))
ck(f"D1 all {len(PAIRS)} load-bearing file:line pairs resolve to the expected text",
   not bad, f"mismatches={bad}")

RX = re.compile(r"(routstr_delist\.py|contract|tests|docs):(\d+)(?:-(\d+))?"
                r"|(?<=`)(?::|/)(\d+)(?:-(\d+))?")
cur_tok = None
unresolved = []
count = 0
bytok: dict = {}
for m in RX.finditer(DELIV_TXT):
    if m.group(1):
        cur_tok = m.group(1)
        nums = [(m.group(2), m.group(3))]
    else:
        nums = [(m.group(4), m.group(5))]
    tok = cur_tok
    if tok is None:
        continue
    nlines = len(FILEMAP[tok].splitlines())
    for a, b in nums:
        count += 1
        bytok[tok] = bytok.get(tok, 0) + 1
        for val in (a, b):
            if val is not None and int(val) > nlines:
                unresolved.append((tok, val))
print(f"   citation census by token: {bytok}")
ck("D2 every file:line citation in the deliverable resolves in its file",
   not unresolved and count > 60, f"citations={count} unresolved={unresolved}")

secs = re.findall(r"^## Finding .*$", DELIV_TXT, re.M)
sev = re.findall(r"severity:\s*\*\*([A-Z]+)\*\*", DELIV_TXT)
ck("D3 the deliverable has exactly three finding sections, each with a severity",
   len(secs) == 3 and len(sev) == 3, f"sections={len(secs)} severities={sev}")
ck("D4 deliverable is mirrored byte-identically to the bot path",
   md5(DELIV) == md5(DELIV_BOT), md5(DELIV))

# D5: every `tests:N (name)` / `contract:N (name)` pin really lives at that line
pins = re.findall(
    r"(tests|contract):(\d+)(?![0-9])(?:[^0-9]){0,12}?`(Test\w+|test_\w+)`",
    DELIV_TXT)
misfiled = []
for tok, ln, name in pins:
    lines = FILEMAP[tok].splitlines()
    if int(ln) > len(lines) or name not in lines[int(ln) - 1]:
        misfiled.append((tok, ln, name))
ck(f"D5 every (tests|contract):N name pin lives at that line",
   not misfiled, f"pins={len(pins)} mis-filed={misfiled}")

# ══════════════════════════════════════════════════════════════════════════
fails = [(t, d) for t, ok, d in RESULTS if not ok]
print()
print(f"== probe_f13_pass14: {len(RESULTS) - len(fails)}/{len(RESULTS)} PASS ==")
if fails:
    for t, d in fails:
        print(f"   FAIL {t} :: {d}")
raise SystemExit(0 if not fails else 1)
