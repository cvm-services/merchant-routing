#!/usr/bin/env python3
"""Pass-11 FRESH verification probes for routstr-delist findings 1, 2, 3.

Written from scratch for this pass (does not reuse the contract suite's harness).
Read-only with respect to every artifact: imports the DEPLOYED script and
executes its REAL payload builders against an in-memory shared-cache sqlite
stand-in for /app/data/keys.db. No network, no ssh, no real subprocess spawn.

Scratch lives under ~/.cache/rp11-pass — NEVER /tmp: /tmp is a 5.5 G tmpfs at
100% (4.0K free) on this host and every write there raises ENOSPC.

Findings under test:
  F1 safety      — SALE delist must never disable the routstr provider / touch
                   the T470 flat-router ladder.
  F2 confirmation— post-delisting confirmation by independent re-fetch.
  F3 fail-safe   — absent / garbage / stale monitor signals.

Exit 0 iff every check passes.
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

HOME = Path.home()
DEPLOYED = HOME / ".hermes/bot/scripts/routstr_delist.py"
TESTS_DEPLOYED = HOME / ".hermes/bot/tests/test_routstr_delist.py"
REPO = Path("/home/c03rad0r/repos/merchant-routing")
SCRATCH = HOME / ".cache/rp11-pass"
# A re-run must start from a clean scratch: the rigs key durable state by
# finding dir, so a leftover state.json from a previous invocation silently
# carried consecutive_failures over and made B2d read fails=2 (the same
# "a counter that increments every time it is measured" trap the lane skill
# documents). Nuke and recreate.
shutil.rmtree(SCRATCH, ignore_errors=True)
SCRATCH.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(DEPLOYED.parent))
import routstr_delist as rd  # noqa: E402

# This fleet host's disk can stall indefinitely inside fsync (the same
# pathology the contract suite documents at its Rig fixture). Durability is
# not what these probes measure — atomicity (the tmp + os.replace protocol)
# still runs for real. Same rationale, independently applied here.
_REAL_FSYNC = os.fsync
os.fsync = lambda fd: None

RESULTS: list[tuple[str, bool, str]] = []


def check(cid: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((cid, bool(ok), detail))
    print(("PASS " if ok else "FAIL ") + cid + ((" :: " + detail) if detail else ""),
          flush=True)


def md5(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


# ── Caller-class-shaped fixtures ──────────────────────────────────────────
ADVERTISED = ["gpt-4o", "claude-3-5-sonnet", "llama-3.1-405b"]
OPERATOR_DISABLED = ["operator-disabled-model"]
PROVIDERS = [("openrouter", 1, 20.0), ("routstr", 1, 10.0), ("zai", 1, 30.0)]


def pred(key="zai", window="1h", hours=10.0, unc=0.05):
    return {"key": key, "window": window, "exhausts_in_hours": hours,
            "uncertainty": unc}


class Clock:
    """Fake monotonic (SLA narratives); REAL wall time (mtime freshness)."""

    def __init__(self):
        self._mono = 0.0

    def monotonic(self):
        return self._mono

    @staticmethod
    def time():
        return time.time()

    def advance(self, s):
        self._mono += s

    @property
    def now(self):
        return self._mono


class SellNode:
    """In-memory stand-in for the sell node: models (the SALE) + providers
    (the T470 ladder). Executes the script's REAL payloads."""

    def __init__(self, d: Path):
        self.ladder_artifact = d / "t470_ladder.json"
        self.ladder_artifact.write_bytes(json.dumps(
            {"ladder": [{"name": n, "enabled": bool(e), "weight": w,
                         "candidate": True} for n, e, w in PROVIDERS]},
            indent=2, sort_keys=True).encode())
        self._uri = (f"file:rp11sell{os.getpid()}x{id(self):x}"
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
        self.round_trip_s = 0.0
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
        return self.ladder_artifact.read_bytes()

    def kinds(self):
        return [k for k, _ in self.calls]

    def _import(self, name, globals=None, locals=None, fromlist=(), level=0):
        if name == "sqlite3":
            return self._sqlite3
        return builtins.__import__(name, globals, locals, fromlist, level)

    def execute(self, kind, payload):
        revert = self.models_map() if (kind == "pull" and not self.pull_lands) else None
        out = io.StringIO()
        g = {"__builtins__": {"__import__": self._import, "print": print}}
        with contextlib.redirect_stdout(out):
            exec(payload, g)  # noqa: S102 — our own payload builders
        if revert is not None:
            con = self._connect()
            for name, enabled in revert.items():
                con.execute("UPDATE models SET enabled=? WHERE name=?",
                            (enabled, name))
            con.commit()
            con.close()
        return json.loads(out.getvalue().strip().splitlines()[-1])


class NodeBackend:
    """Mirrors rd._SshBackend's result shape at the FakeSellNode."""

    def __init__(self, node, clock):
        self.node = node
        self.clock = clock

    def pull(self, dry_run=False, deadline=None):
        return self._rt("pull", rd.pull_listing_payload(), dry_run, deadline)

    def verify(self, dry_run=False, deadline=None):
        return self._rt("verify", rd.verify_pull_payload(), dry_run, deadline)

    def relist(self, names=None, dry_run=False, deadline=None):
        return self._rt("relist", rd.relist_payload(names or []), dry_run, deadline)

    def _rt(self, kind, payload, dry_run, deadline):
        if deadline is not None:
            rem = deadline - self.clock.monotonic()
            self.node.deadline_log.append(
                {"kind": kind, "remaining": rem,
                 "timeout": min(rd.SSH_TIMEOUT_S, max(rem, 0.0))})
        if dry_run:
            return {"ok": True, "dry_run": True, "action": kind}
        self.node.calls.append((kind, payload))
        if self.node.ssh_down:
            return {"ok": False, "action": kind, "rc": 255,
                    "error": "ssh: connect refused (simulated)"}
        data = self.node.execute(kind, payload)
        self.clock.advance(self.node.round_trip_s)
        return {"action": kind, "rc": 0, **data, "ok": data.get("ok") is True}


class Rig:
    """Fresh CLI harness (own implementation, not the contract suite's)."""

    def __init__(self, name):
        self.dir = SCRATCH / name
        self.dir.mkdir(parents=True, exist_ok=True)
        self.node = SellNode(self.dir)
        self.clock = Clock()
        self.state = self.dir / "state.json"
        self.override = self.dir / "override"      # absent by default
        self._orig_backend = rd._SshBackend
        rd._SshBackend = lambda t, c: NodeBackend(self.node, self.clock)
        self._orig_time = rd.time
        rd.time = self.clock

    def close(self):
        rd._SshBackend = self._orig_backend
        rd.time = self._orig_time

    def write_preds(self, preds, name="preds.json"):
        p = self.dir / name
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
# A0 — artifact identity: the things I verified ARE the deployed artifacts
# ══════════════════════════════════════════════════════════════════════════
check("A0a deployed script == repo src",
      md5(DEPLOYED) == md5(REPO / "src/routstr_delist.py"),
      f"md5 {md5(DEPLOYED)}")
check("A0b deployed suite == repo contract suite",
      md5(TESTS_DEPLOYED) == md5(REPO / "tests/test_routstr_delist_contract.py"),
      f"md5 {md5(TESTS_DEPLOYED)}")

SRC = DEPLOYED.read_text()
tree = ast.parse(SRC)


def render(node):
    """Best-effort source text of a string literal / f-string node."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(p.value if isinstance(p, ast.Constant) and
                       isinstance(p.value, str) else "\x00"
                       for p in node.values)
    return ""


# ══════════════════════════════════════════════════════════════════════════
# FINDING 1 — safety: SALE delist vs provider / T470 ladder
# ══════════════════════════════════════════════════════════════════════════
# A1: AST inventory of every SQL literal in the module. Fresh measure: not a
#     hand-typed list. Every DML statement must target `models` ONLY.
#     Docstrings are collected first so that prose (e.g. verify_pull_payload's
#     "Read-only: SELECT only" + "...models." in one docstring) cannot be
#     mistaken for an executable statement, and each literal is collected
#     exactly once (a naive ast.walk descends into an f-string's parts and
#     reports the same payload two or three times).
doc_spans = []
for n in ast.walk(tree):
    if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef,
                      ast.AsyncFunctionDef)):
        b = getattr(n, "body", [])
        if b and isinstance(b[0], ast.Expr) \
                and isinstance(b[0].value, ast.Constant) \
                and isinstance(b[0].value.value, str):
            doc_spans.append((b[0].value.lineno, b[0].value.end_lineno))


def in_doc(ln):
    return any(a <= ln <= b for a, b in doc_spans)


def collect_strings(node, out):
    """Every string literal exactly once; never descends into a literal."""
    for child in ast.iter_child_nodes(node):
        if isinstance(child, ast.JoinedStr):
            out.append((child.lineno, getattr(child, "end_lineno", child.lineno),
                        render(child)))
            continue
        if isinstance(child, ast.Constant) and isinstance(child.value, str):
            out.append((child.lineno, getattr(child, "end_lineno", child.lineno),
                        child.value))
            continue
        collect_strings(child, out)


_all_strings = []
collect_strings(tree, _all_strings)
sql_lits = [(ln, s) for ln, end, s in _all_strings
            if not any(ln >= a and end <= b for a, b in doc_spans)
            and re.search(r"\b(UPDATE|INSERT|DELETE|SELECT|DROP|ALTER)\b", s, re.I)
            and "models" in s]
check("A1a AST finds exactly 5 executable models-SQL literals",
      len(sql_lits) == 5, f"lines {sorted(ln for ln, _ in sql_lits)}")
check("A1b every SQL literal targets the models table only",
      all("models" in s for _, s in sql_lits) and
      not any("upstream" in s for _, s in sql_lits),
      f"{len(sql_lits)} literals, 0 naming upstream_providers")

# A2: `upstream_providers` may appear ONLY in comments/docstrings — never in a
#     literal that could be executed. Classify every occurrence by line.
raw_lines = SRC.splitlines()
prov_refs = [i + 1 for i, ln in enumerate(raw_lines) if "upstream_providers" in ln]
prov_ctx = {ln: ("comment" if raw_lines[ln - 1].strip().startswith("#")
                 else "docstring" if in_doc(ln) else "CODE") for ln in prov_refs}
check("A2a upstream_providers appears only in comments/docstrings",
      len(prov_refs) == 3 and all(v != "CODE" for v in prov_ctx.values()),
      f"lines {prov_refs} -> {prov_ctx}")

# A3: no eval/exec/os.system anywhere; exactly 2 subprocess sites; no shell=.
shell_kw = [n for n in ast.walk(tree)
            if isinstance(n, ast.Call)
            for kw in n.keywords if kw.arg == "shell"]
subproc = [n.lineno for n in ast.walk(tree)
           if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
           and n.func.attr == "run" and isinstance(n.func.value, ast.Name)
           and n.func.value.id == "subprocess"]
check("A3a exactly 2 subprocess.run sites, zero shell=True",
      len(subproc) == 2 and not shell_kw, f"sites {subproc}")
danger = [n.lineno for n in ast.walk(tree)
          if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
          and n.func.id in ("eval", "exec")]
check("A3b zero eval/exec call sites", not danger, f"{danger}")

# A4: SEMANTIC guard — execute the REAL pull payload against a node that has
#     BOTH tables; the ladder artifact and the provider rows must be
#     byte/row-identical afterwards.
rig = Rig("A4")
try:
    lb, pb = rig.node.ladder_bytes(), rig.node.providers_snapshot()
    rc, out, _ = rig.run("--manual")
    check("A4a manual delist succeeds", rc == 0 and out["action"] == "delist",
          f"rc={rc} action={out.get('action')}")
    check("A4b ladder artifact byte-identical across the delist",
          rig.node.ladder_bytes() == lb, f"{len(lb)} B unchanged")
    check("A4c upstream_providers rows identical across the delist",
          rig.node.providers_snapshot() == pb, f"{pb}")
    check("A4d routstr provider still an enabled ladder candidate",
          any(n == "routstr" and e == 1 for n, e, _ in rig.node.providers_snapshot()))
    check("A4e the SALE was actually pulled (all advertised rows disabled)",
          all(rig.node.models_map()[n] == 0 for n in ADVERTISED)
          and rig.node.models_map() == {**{n: 0 for n in ADVERTISED},
                                        **{n: 0 for n in OPERATOR_DISABLED}})
    check("A4f no executed payload even names upstream_providers",
          all("upstream_providers" not in p for _, p in rig.node.calls))
finally:
    rig.close()

# A5: blanket relist refused (would enable operator-disabled rows).
rig = Rig("A5")
try:
    rc, out, _ = rig.run("--relist")
    st = json.loads(rig.state.read_text()) if rig.state.exists() else {}
    check("A5a --relist with no captured names REFUSES (rc 1, no remote call)",
          rc == 1 and out.get("action") == "relist_refused" and rig.node.calls == [],
          f"rc={rc} calls={rig.node.calls}")
    check("A5b refusal leaves the operator-disabled row untouched",
          rig.node.models_map()[OPERATOR_DISABLED[0]] == 0)
    check("A5c refusal writes no delisted flag",
          "delisted" not in st or st.get("delisted") is False)
finally:
    rig.close()

# A6: scoped relist restores EXACTLY the pulled set, ladder untouched.
rig = Rig("A6")
try:
    lb = rig.node.ladder_bytes()
    rig.run("--manual")
    rc, out, _ = rig.run("--relist")
    m = rig.node.models_map()
    check("A6a scoped relist restores exactly the advertised set",
          rc == 0 and [n for n, e in m.items() if e == 1] == ADVERTISED,
          f"restored={out.get('restored')}")
    check("A6b pre-delist operator-disabled row stays disabled",
          m[OPERATOR_DISABLED[0]] == 0)
    check("A6c ladder byte-identical across the relist too",
          rig.node.ladder_bytes() == lb)
finally:
    rig.close()

# ══════════════════════════════════════════════════════════════════════════
# FINDING 2 — post-delisting confirmation via independent re-fetch
# ══════════════════════════════════════════════════════════════════════════
vp = rd.verify_pull_payload()
check("B1a verify payload is READ-ONLY (no DML keyword)",
      not re.search(r"\b(UPDATE|INSERT|DELETE|DROP|ALTER)\b", vp, re.I), vp[:60])
check("B1b verify payload counts still-advertised models",
      "SELECT COUNT(*) FROM models WHERE enabled=1" in vp)

# B2: a LYING pull (self-reports ok, UPDATE never lands) must be refuted.
rig = Rig("B2")
try:
    rig.node.pull_lands = False
    rc, out, _ = rig.run("--manual")
    check("B2a lying pull is a FAILED delist (rc 1)", rc == 1,
          f"rc={rc} action={out.get('action')}")
    check("B2b refuted attempt records ok=False + verify.count",
          out.get("ok") is False and out.get("verify", {}).get("count") == len(ADVERTISED),
          f"verify={out.get('verify')}")
    check("B2c bounded in-run retry: exactly pull,verify,pull,verify",
          rig.node.kinds() == ["pull", "verify", "pull", "verify"],
          f"{rig.node.kinds()}")
    st = rd.load_state(str(rig.state))
    check("B2d no delisted=true on a refuted delist",
          st.get("delisted") is False and st.get("consecutive_failures") == 1,
          f"delisted={st.get('delisted')} fails={st.get('consecutive_failures')}")
finally:
    rig.close()

# B3: happy path — confirmation gates success and reports verified_count.
rig = Rig("B3")
try:
    rc, out, _ = rig.run("--manual")
    check("B3a confirmed delist: rc 0, delisted, verified_count 0",
          rc == 0 and out.get("confirmed") is True
          and out.get("verified_count") == 0 and out.get("action") == "delist",
          f"rc={rc} confirmed={out.get('confirmed')} n={out.get('verified_count')}")
    check("B3b exactly one pull + one verify (no redundant round-trips)",
          rig.node.kinds() == ["pull", "verify"], f"{rig.node.kinds()}")
    st = rd.load_state(str(rig.state))
    check("B3c durable delisted=true + pulled_models == the advertised set",
          st.get("delisted") is True and st.get("pulled_models") == ADVERTISED,
          f"pulled={st.get('pulled_models')}")
finally:
    rig.close()

# B4: MEASURE the relist asymmetry — the relist path performs NO re-fetch.
rig = Rig("B4")
try:
    rig.run("--manual")
    rig.node.calls.clear()
    rc, out, _ = rig.run("--relist")
    check("B4a relist executes WITHOUT any verification round-trip (asymmetry)",
          rc == 0 and out.get("action") == "relist"
          and rig.node.kinds() == ["relist"],
          f"kinds={rig.node.kinds()} (no 'verify' -> self-report only)")
    check("B4b relist success is therefore gated on the pull's own ok flag",
          "ok" in out and "confirmed" not in out, f"keys={sorted(out)}")
finally:
    rig.close()

# B5: dry-run confirmation is intent-only (no remote verify, no flag flip).
rig = Rig("B5")
try:
    rc, out, _ = rig.run("--manual", "--dry-run")
    st = rd.load_state(str(rig.state))
    check("B5a dry-run reports delist with ZERO remote round-trips",
          rc == 0 and out.get("action") == "delist" and rig.node.calls == [],
          f"calls={rig.node.calls}")
    check("B5b dry-run flips no durable delisted flag, records intent only",
          "delisted" not in st and "last_dry_run" in st, f"state keys={sorted(st)}")
finally:
    rig.close()

# ══════════════════════════════════════════════════════════════════════════
# FINDING 3 — fail-safe on absent / garbage / stale monitor signals
# ══════════════════════════════════════════════════════════════════════════
d = SCRATCH / "C1"
d.mkdir(parents=True, exist_ok=True)
now = time.time()
missing = d / "nope.json"
fresh = d / "fresh.json"
fresh.write_text("[]")
aged = d / "aged.json"
aged.write_text("[]")
os.utime(aged, (now - 3600, now - 3600))
future = d / "future.json"
future.write_text("[]")
os.utime(future, (now + 3600, now + 3600))
boundary = d / "boundary.json"
boundary.write_text("[]")
os.utime(boundary, (now - rd.STALENESS_S, now - rd.STALENESS_S))
check("C1a absent feed -> stale (fail-safe)", rd.feed_is_stale(str(missing)) is True)
check("C1b aged feed -> stale",
      rd.feed_is_stale(str(aged), max_age_s=rd.STALENESS_S) is True, "age 3600 > 1800")
check("C1c future mtime -> stale (negative age is not freshness)",
      rd.feed_is_stale(str(future)) is True)
check("C1d fresh feed -> not stale", rd.feed_is_stale(str(fresh)) is False)
check("C1e boundary age == STALENESS_S is INCLUSIVE (not stale)",
      rd.feed_is_stale(str(boundary), max_age_s=rd.STALENESS_S, now=now) is False)

# C2: garbage feed -> feed error, rc 1, baseline NOT wiped.
rig = Rig("C2")
try:
    rig.run(preds=rig.write_preds([pred(hours=10.0)], name="a.json"))
    before = rd.load_state(str(rig.state)).get("snapshot")
    bad = rig.dir / "garbage.json"
    bad.write_text("{not json at all")
    rc, out, _ = rig.run(preds=bad)
    after = rd.load_state(str(rig.state)).get("snapshot")
    check("C2a garbage feed -> preds_error true, rc 1, no fire",
          rc == 1 and out.get("preds_error") is True and out.get("action") == "none",
          f"rc={rc} preds_error={out.get('preds_error')}")
    check("C2b garbage feed never wipes the stored baseline",
          before is not None and after == before, f"snapshot preserved: {after == before}")
finally:
    rig.close()

# C3: stale feed -> no fire AND baseline not refreshed by dead data.
rig = Rig("C3")
try:
    rig.run(preds=rig.write_preds([pred(hours=10.0)], name="a.json"))
    before = rd.load_state(str(rig.state)).get("snapshot")
    stale = rig.age(rig.write_preds([pred(hours=1.0)], name="b.json"))
    rc, out, _ = rig.run(preds=stale)
    after = rd.load_state(str(rig.state)).get("snapshot")
    check("C3a stale feed -> preds_stale true, no fire, rc 1",
          rc == 1 and out.get("preds_stale") is True
          and out.get("fire") is False and rig.node.calls == [],
          f"rc={rc} stale={out.get('preds_stale')} calls={rig.node.calls}")
    check("C3b stale feed does NOT refresh the acceleration baseline",
          after == before,
          f"snapshot unchanged despite feed saying 1.0h (was {list((before or {}).values())})")
finally:
    rig.close()

# C4: type guards — non-dict entries dropped; non-numeric uncertainty ignored.
d4 = SCRATCH / "C4"
d4.mkdir(parents=True, exist_ok=True)
f4 = d4 / "mixed.json"
f4.write_text(json.dumps([pred(), 1, "x", None, ["y"]]))
check("C4a non-dict feed entries dropped, dicts kept",
      rd._read_preds(str(f4)) == [pred()], f"{rd._read_preds(str(f4))}")
check("C4b string/bool/None uncertainty never fires variance",
      rd.variance_jumped([{"key": "zai", "window": "1h", "uncertainty": "0.9"},
                          {"key": "zai", "window": "1h", "uncertainty": True},
                          {"key": "zai", "window": "1h", "uncertainty": None}]) == [])
check("C4c non-numeric exhausts_in_hours yields no acceleration",
      rd.exhaustion_accelerated(
          [{"key": "zai", "window": "1h", "exhausts_in_hours": "abc"}],
          [{"key": "zai", "window": "1h", "exhausts_in_hours": 10.0}]) == [])

# C5: manual override is never gated on freshness.
rig = Rig("C5")
try:
    p = rig.age(rig.write_preds([pred(hours=10.0, unc=0.9)]))
    rc, out, _ = rig.run("--manual", preds=p)
    check("C5a manual override delists despite a stale feed (observed, not obeyed)",
          rc == 0 and out.get("action") == "delist"
          and out.get("preds_stale") is True,
          f"rc={rc} stale={out.get('preds_stale')} action={out.get('action')}")
finally:
    rig.close()

# C6: --preds-key scoping. Default (unset) is UNSCOPED -> another provider's
#     variance spike can pull the SALE; scoping prevents it.
rig = Rig("C6")
try:
    other = rig.write_preds([pred(key="openrouter", hours=10.0, unc=0.95)])
    rc_u, out_u, _ = rig.run(preds=other)
    check("C6a UNSCOPED default: another key's variance fires the delist (LOW)",
          rc_u == 0 and out_u.get("action") == "delist",
          f"action={out_u.get('action')} (key=openrouter only, no --preds-key)")
    check("C6b evaluate_triggers applies no implicit key filter (LOW)",
          rd.evaluate_triggers([pred(key="openrouter", hours=10.0, unc=0.95)],
                               {})["fire"] is True,
          "a foreign key's spike fires when no --preds-key is given")
finally:
    rig.close()

rig = Rig("C6b")
try:
    other = rig.write_preds([pred(key="openrouter", hours=10.0, unc=0.95)])
    rc_s, out_s, _ = rig.run("--preds-key", "zai", preds=other)
    check("C6c scoped --preds-key zai: same feed is quiet",
          rc_s == 0 and out_s.get("action") == "none" and rig.node.calls == [],
          f"action={out_s.get('action')}")
finally:
    rig.close()

# C7: exhausted action budget -> refuse before spawning anything.
class _Counter:
    n = 0


def _fake_run(*a, **kw):
    _Counter.n += 1
    raise AssertionError("spawn attempted on an exhausted budget")


_orig_sub = rd.subprocess.run
rd.subprocess.run = _fake_run
try:
    be = rd._SshBackend("deploy@host", "routstr-public")
    r = be.pull(deadline=time.monotonic() - 1.0)
    check("C7 exhausted deadline -> ok False, zero spawns",
          r.get("ok") is False and _Counter.n == 0
          and "budget" in str(r.get("error", "")), f"{r}")
finally:
    rd.subprocess.run = _orig_sub

# ══════════════════════════════════════════════════════════════════════════
# GROUP TALLY + exit status
# ══════════════════════════════════════════════════════════════════════════
groups = {}
for cid, ok, _ in RESULTS:
    g = cid[0]
    groups.setdefault(g, 0)
    groups[g] += 1
fails = [c for c in RESULTS if not c[1]]
print("\nGROUP TALLY: " + " ".join(f"{k}={v}" for k, v in sorted(groups.items()))
      + f" total={len(RESULTS)}")
print(f"PASS {len(RESULTS) - len(fails)} / FAIL {len(fails)}")
for cid, _, detail in fails:
    print(f"  FAILED {cid} :: {detail}")
raise SystemExit(0 if not fails else 1)
