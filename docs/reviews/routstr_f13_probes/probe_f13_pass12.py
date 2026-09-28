#!/usr/bin/env python3
"""probe_f13_pass12.py — 12th-pass independent verification of routstr delist
findings 1-3 (safety, confirmation, fail-safe).

Authored FRESH for this pass (does not reuse the pass-11 probe). Read-only with
respect to every artifact: it imports the DEPLOYED script
(~/.hermes/bot/scripts/routstr_delist.py) and the repo src copy for identity
comparison, and it never writes outside its own scratch TMPDIR.

Hermetic: the only side-effect boundary (rd._SshBackend) is replaced by a
stand-in that EXECUTES the module's real payloads against a named shared-cache
in-memory sqlite with BOTH tables (models = SALE listing, upstream_providers =
provider ladder) plus a ladder-artifact file. No subprocess, no network, no
file-backed sqlite (fleet hosts stall in fsync/lock acquisition).

Run:  TMPDIR=$HOME/.cache/rp12-pass python3 probe_f13_pass12.py
Prints one PASS/FAIL line per check and exits 0 iff every check passed.
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
import sqlite3
import sys
import tempfile
import time
import types

DEPLOYED = os.path.expanduser("~/.hermes/bot/scripts/routstr_delist.py")
REPO_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "..", "..", "..", "src", "routstr_delist.py")
DEPLOYED_TESTS = os.path.expanduser("~/.hermes/bot/tests/test_routstr_delist.py")
REPO_CONTRACT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "..", "..", "..", "tests",
                             "test_routstr_delist_contract.py")

SCRATCH = tempfile.mkdtemp(prefix="f13p12-")
RESULTS: list[tuple[str, bool, str]] = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))
    print(f"{'PASS' if ok else 'FAIL'} {name}"
          + (f" :: {detail}" if detail else ""))


def md5(p):
    with open(p, "rb") as fh:
        return hashlib.md5(fh.read()).hexdigest()


def load_module(path, name):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


rd = load_module(DEPLOYED, "rd_deployed")
ORIG_SSH = rd._SshBackend          # captured before any per-run patch
SRC = open(DEPLOYED, encoding="utf-8").read()
SRC_LINES = SRC.splitlines()
TREE = ast.parse(SRC)

# ── fixture shapes ────────────────────────────────────────────────────────
ADVERTISED = ["gpt-4o", "claude-3-5-sonnet", "llama-3.1-405b"]
OPERATOR_DISABLED = ["operator-disabled-model"]
PROVIDERS = [("openrouter", 1, 20.0), ("routstr", 1, 10.0), ("zai", 1, 30.0)]


def pred(key="zai", window="1h", hours=10.0, unc=0.05):
    return {"key": key, "window": window,
            "exhausts_in_hours": hours, "uncertainty": unc}


class Node:
    """Stand-in sell node: real SQL semantics, hermetic."""

    def __init__(self):
        self.uri = f"file:f13p12{os.getpid()}x{id(self):x}?mode=memory&cache=shared"
        self.ladder_path = os.path.join(SCRATCH, f"ladder{id(self):x}.json")
        with open(self.ladder_path, "wb") as fh:
            fh.write(json.dumps(
                {"ladder": [{"name": n, "enabled": bool(e), "weight": w,
                             "candidate": True} for n, e, w in PROVIDERS]},
                indent=2, sort_keys=True).encode())
        con = self._connect()
        con.execute("CREATE TABLE models "
                    "(name TEXT PRIMARY KEY, enabled INTEGER NOT NULL)")
        for n in ADVERTISED:
            con.execute("INSERT INTO models VALUES (?,1)", (n,))
        for n in OPERATOR_DISABLED:
            con.execute("INSERT INTO models VALUES (?,0)", (n,))
        con.execute("CREATE TABLE upstream_providers "
                    "(name TEXT PRIMARY KEY, enabled INTEGER NOT NULL, "
                    "weight REAL NOT NULL)")
        for row in PROVIDERS:
            con.execute("INSERT INTO upstream_providers VALUES (?,?,?)", row)
        con.commit()
        self._con = con
        self.calls = []
        self.ssh_down = False
        self.pull_lands = True
        self.verify_fails = False
        self.verify_count_override = None
        shim = types.ModuleType("sqlite3")
        shim.connect = self._connect
        self._sqlite3 = shim

    def _connect(self, _path=None):
        return sqlite3.connect(self.uri, uri=True)

    def _import(self, name, g=None, l=None, fromlist=(), level=0):
        if name == "sqlite3":
            return self._sqlite3
        return builtins.__import__(name, g, l, fromlist, level)

    def models_map(self):
        return dict(self._con.execute("SELECT name, enabled FROM models"))

    def providers_snapshot(self):
        return list(self._con.execute(
            "SELECT name, enabled, weight FROM upstream_providers ORDER BY name"))

    def ladder_bytes(self):
        with open(self.ladder_path, "rb") as fh:
            return fh.read()

    def kinds(self):
        return [k for k, _ in self.calls]

    def execute(self, kind, payload):
        revert = self.models_map() if (kind == "pull" and not self.pull_lands) else None
        out = io.StringIO()
        g = {"__builtins__": {"__import__": self._import, "print": print}}
        with contextlib.redirect_stdout(out):
            exec(payload, g)  # noqa: S102 — executing the module's OWN payload
        if revert is not None:
            con = self._connect()
            for name, enabled in revert.items():
                con.execute("UPDATE models SET enabled=? WHERE name=?", (enabled, name))
            con.commit()
            con.close()
        return json.loads(out.getvalue().strip().splitlines()[-1])


class Backend:
    """Stand-in for rd._SshBackend."""

    def __init__(self, node):
        self.node = node

    def pull(self, dry_run=False, deadline=None):
        return self._rt("pull", rd.pull_listing_payload(), dry_run)

    def verify(self, dry_run=False, deadline=None):
        if self.node.verify_fails:
            # a failed ssh round-trip is still a round-trip (production parity)
            self.node.calls.append(("verify", rd.verify_pull_payload()))
            return {"ok": False, "action": "verify", "rc": 255,
                    "error": "ssh down (simulated)"}
        res = self._rt("verify", rd.verify_pull_payload(), dry_run)
        if self.node.verify_count_override is not None:
            res = dict(res, count=self.node.verify_count_override,
                       ok=res.get("ok"))
        return res

    def relist(self, names=None, dry_run=False, deadline=None):
        return self._rt("relist", rd.relist_payload(names or []), dry_run)

    def _rt(self, kind, payload, dry_run):
        if dry_run:
            return {"ok": True, "dry_run": True, "action": kind}
        self.node.calls.append((kind, payload))
        if self.node.ssh_down:
            return {"ok": False, "action": kind, "rc": 255,
                    "error": "ssh: connect refused (simulated)"}
        data = self.node.execute(kind, payload)
        return {"action": kind, "rc": 0, **data, "ok": data.get("ok") is True}


def run(node, argv, state_path):
    rd._SshBackend = lambda t, c: Backend(node)
    override = os.path.join(SCRATCH, f"ovr{id(node):x}")
    if os.path.exists(override):
        os.unlink(override)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = rd.main(["--state", str(state_path), "--override", override] + argv)
    raw = buf.getvalue()
    return rc, (json.loads(raw) if raw.strip() else {})


def new_env():
    d = tempfile.mkdtemp(dir=SCRATCH)
    return Node(), os.path.join(d, "state.json"), d


def write_preds(d, preds, name="preds.json", age_s=None):
    p = os.path.join(d, name)
    with open(p, "w") as fh:
        fh.write(preds if isinstance(preds, str) else json.dumps(preds))
    if age_s:
        old = time.time() - age_s
        os.utime(p, (old, old))
    return p


# ══════════════════════════════════════════════════════════════════════════
print("== GROUP A — Finding 1: safety (SALE vs provider, ladder untouched) ==")

check("A0a deployed script == repo src (md5)",
      md5(DEPLOYED) == md5(REPO_SRC),
      f"{md5(DEPLOYED)} lines={SRC.count(chr(10)) + 1}")

check("A0b deployed tests == repo contract suite (md5)",
      md5(DEPLOYED_TESTS) == md5(REPO_CONTRACT),
      f"{md5(DEPLOYED_TESTS)} lines={open(DEPLOYED_TESTS).read().count(chr(10)) + 1}")

# A1: SQL inventory on the parsed source. Adjacent string literals are merged
# by the parser into ONE Constant (a payload built by implicit concatenation
# therefore reports the line where its FIRST fragment starts), so the table
# grep below walks EVERY string constant and requires a SQL-looking
# continuation after the table name — prose such as "into one string" or
# "from the snapshot" cannot match.
TABLE_RE = re.compile(
    r"\b(?:FROM|INTO|UPDATE|DELETE\s+FROM|JOIN)\s+([A-Za-z_][A-Za-z0-9_]*)"
    r"(?=\s*(?:SET\b|WHERE\b|\(|;|\n|$))", re.I)
sql_pairs = []
for n in ast.walk(TREE):
    if isinstance(n, ast.Constant) and isinstance(n.value, str):
        for m in TABLE_RE.finditer(n.value):
            sql_pairs.append((n.lineno, m.group(1).lower()))
tables = sorted({t for _, t in sql_pairs})
check("A1a SQL table inventory is exactly 5 models-table references",
      sorted(sql_pairs) == [(355, "models"), (361, "models"), (369, "models"),
                            (392, "models"), (406, "models")],
      f"{sorted(sql_pairs)}")
check("A1c zero SQL reference names any table other than models",
      tables == ["models"], f"tables={tables}")

# raw-source confirmation of the SQL text lines the findings cite.
raw_targets = {
    "UPDATE models SET enabled=0 WHERE enabled=1;": 355,
    "UPDATE models SET enabled=1;": 361,
    "SELECT name FROM models WHERE enabled=1": 371,
    "UPDATE models SET enabled=1 WHERE name IN": 394,
    "SELECT COUNT(*) FROM models WHERE enabled=1": 408,
}
raw_ok, raw_seen = True, {}
for text, want in raw_targets.items():
    hits = [i + 1 for i, ln in enumerate(SRC_LINES) if text in ln]
    raw_seen[want] = hits
    raw_ok = raw_ok and hits == [want]
check("A1b the 5 SQL texts sit at raw source lines 355/361/371/394/408",
      raw_ok, f"{raw_seen}")

# A2: upstream_providers must occur only inside docstrings.
docstring_spans = []
for n in ast.walk(TREE):
    body = getattr(n, "body", None)
    if isinstance(body, list) and body and isinstance(body[0], ast.Expr) \
            and isinstance(body[0].value, ast.Constant) \
            and isinstance(body[0].value.value, str):
        docstring_spans.append((body[0].value.lineno, body[0].value.end_lineno))
occ_lines = [i + 1 for i, ln in enumerate(SRC_LINES) if "upstream_providers" in ln]
occ_in_doc = [ln for ln in occ_lines
              if any(a <= ln <= b for a, b in docstring_spans)]
check("A2 upstream_providers: 3 occurrences, all inside docstrings, 0 in code",
      len(occ_lines) == 3 and len(occ_in_doc) == 3,
      f"occurrence_lines={occ_lines} docstring_lines={occ_in_doc}")

# A3: subprocess / shell / eval inventory.
sub_calls, shell_true, exec_calls = [], [], []
for node in ast.walk(TREE):
    if isinstance(node, ast.Call):
        f = node.func
        if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) \
                and f.value.id == "subprocess" and f.attr == "run":
            sub_calls.append(node.lineno)
            if any(k.arg == "shell" and getattr(k.value, "value", None) is True
                   for k in node.keywords):
                shell_true.append(node.lineno)
        if isinstance(f, ast.Name) and f.id in ("eval", "exec"):
            exec_calls.append((node.lineno, f.id))
os_calls = []
for node in ast.walk(TREE):
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
            and isinstance(node.func.value, ast.Name) and node.func.value.id == "os" \
            and node.func.attr in ("system", "remove", "unlink", "rmdir", "rename",
                                   "replace"):
        os_calls.append((node.lineno, node.func.attr))
check("A3a exactly 2 subprocess.run sites, none with shell=True",
      sorted(sub_calls) == [459, 808] and shell_true == [],
      f"subprocess={sorted(sub_calls)} shell_true={shell_true}")
check("A3b zero eval/exec call sites",
      exec_calls == [], f"eval_exec={exec_calls}")
check("A3c os.* mutation surface limited to save_state tmp swap",
      sorted(a for _, a in os_calls) == ["replace", "unlink"],
      f"os_calls={sorted(os_calls)}")

# A4: execute the REAL pull payload against both tables.
node, state, d = new_env()
ladder_before, providers_before = node.ladder_bytes(), node.providers_snapshot()
rc, out = run(node, ["--manual"], state)
check("A4a manual delist confirmed rc0",
      rc == 0 and out.get("action") == "delist" and out.get("confirmed") is True,
      f"rc={rc} action={out.get('action')} confirmed={out.get('confirmed')}")
check("A4b ladder artifact byte-identical across the delist",
      node.ladder_bytes() == ladder_before, f"{len(ladder_before)}B")
check("A4c upstream_providers rows identical across the delist",
      node.providers_snapshot() == providers_before,
      f"{node.providers_snapshot()}")
check("A4d routstr provider still an enabled ladder candidate",
      any(n == "routstr" and e == 1 for n, e, _ in node.providers_snapshot()))
check("A4e every advertised model disabled; pre-disabled row stayed disabled",
      node.models_map() == {**{n: 0 for n in ADVERTISED},
                            **{n: 0 for n in OPERATOR_DISABLED}},
      f"{node.models_map()}")
check("A4f no executed payload ever named upstream_providers",
      all("upstream_providers" not in p for _, p in node.calls),
      f"kinds={node.kinds()}")

# A5: scoped relist restores only captured names.
rc2, out2 = run(node, ["--relist"], state)
models_after = node.models_map()
check("A5a scoped relist restores exactly the captured names",
      rc2 == 0 and out2.get("restored") == len(ADVERTISED),
      f"rc={rc2} restored={out2.get('restored')}")
check("A5b operator-disabled row never re-enabled by the relist",
      all(models_after.get(n) == 0 for n in OPERATOR_DISABLED)
      and all(models_after.get(n) == 1 for n in ADVERTISED),
      f"{models_after}")
check("A5c ladder still byte-identical after the relist",
      node.ladder_bytes() == ladder_before)

# A6: blanket relist refused with no captured names.
node2, state2, _ = new_env()
rc3, out3 = run(node2, ["--relist"], state2)
check("A6a --relist without captured names refuses, rc1, zero remote calls",
      rc3 == 1 and out3.get("action") == "relist_refused" and node2.calls == [],
      f"rc={rc3} action={out3.get('action')} calls={node2.calls}")
check("A6b refusal wrote no delisted flag",
      rd.load_state(str(state2)).get("delisted") is not True)

# A7: remote command quoting round-trip.
cmd = rd.build_ssh_docker_cmd("debian@host", "routstr public", "print('x')")
round_trip = shlex.split(cmd[2]) if len(cmd) == 3 else []
check("A7a ssh argv is 3 elements with one shlex-quoted remote string",
      len(cmd) == 3 and cmd[0] == "ssh", f"len={len(cmd)}")
check("A7b remote string re-parses to the intended argv (container with space)",
      round_trip == ["docker", "exec", "routstr public", "python3", "-c",
                     "print('x')"],
      f"{round_trip}")

# A8: dry-run executes nothing and flips no flag.
node3, state3, d3 = new_env()
rc4, out4 = run(node3, ["--manual", "--dry-run"], state3)
check("A8a dry-run fires no remote round-trip",
      rc4 == 0 and node3.calls == [], f"rc={rc4} calls={node3.calls}")
check("A8b dry-run introduced no durable delisted flag",
      "delisted" not in rd.load_state(str(state3)),
      f"state_keys={sorted(rd.load_state(str(state3)))}")

# ══════════════════════════════════════════════════════════════════════════
print("== GROUP B — Finding 2: post-delisting confirmation via re-fetch ==")

ver_payload = rd.verify_pull_payload()
check("B1a verify payload contains no mutating SQL verb",
      not re.search(r"\b(UPDATE|INSERT|DELETE|DROP|ALTER)\b", ver_payload, re.I),
      ver_payload[:80])
check("B1b verify payload is exactly the COUNT re-fetch",
      "SELECT COUNT(*) FROM models WHERE enabled=1" in ver_payload)

# B2: lying pull (self-reports ok, UPDATE never lands) must be refuted.
node4, state4, d4 = new_env()
node4.pull_lands = False
rc5, out5 = run(node4, ["--manual"], state4)
st4 = rd.load_state(str(state4))
check("B2a lying pull -> rc1 delist_failed, verify count refutes it",
      rc5 == 1 and out5.get("action") == "delist_failed"
      and out5.get("ok") is False and out5.get("verify", {}).get("count") == 3,
      f"rc={rc5} action={out5.get('action')} verify={out5.get('verify')}")
check("B2b bounded in-run retry: kinds == pull,verify,pull,verify",
      node4.kinds() == ["pull", "verify", "pull", "verify"],
      f"{node4.kinds()}")
check("B2c failed delist sets no delisted flag and ticks the breaker",
      st4.get("delisted") is False and st4.get("consecutive_failures") == 1,
      f"delisted={st4.get('delisted')} fails={st4.get('consecutive_failures')}")

# B3: happy path.
node5, state5, d5 = new_env()
rc6, out6 = run(node5, ["--manual"], state5)
st5 = rd.load_state(str(state5))
check("B3a happy path rc0 confirmed=True verified_count=0",
      rc6 == 0 and out6.get("confirmed") is True
      and out6.get("verified_count") == 0,
      f"rc={rc6} confirmed={out6.get('confirmed')} "
      f"verified_count={out6.get('verified_count')}")
check("B3b exactly one pull + one verify",
      node5.kinds() == ["pull", "verify"], f"{node5.kinds()}")
check("B3c durable delisted=true with the captured advertised names",
      st5.get("delisted") is True and st5.get("pulled_models") == ADVERTISED,
      f"pulled_models={st5.get('pulled_models')}")

# B4: refuted verification (models still advertised) -> failed attempt.
node6, state6, d6 = new_env()
node6.verify_count_override = 3
rc7, out7 = run(node6, ["--manual"], state6)
st6 = rd.load_state(str(state6))
check("B4a verify count>0 refutes an ok pull -> rc1, no flag, breaker tick",
      rc7 == 1 and out7.get("action") == "delist_failed"
      and st6.get("delisted") is False and st6.get("consecutive_failures") == 1,
      f"rc={rc7} delisted={st6.get('delisted')} "
      f"fails={st6.get('consecutive_failures')}")

# B5: verify transport failure counts as an attempt failure.
node7, state7, d7 = new_env()
node7.verify_fails = True
rc8, out8 = run(node7, ["--manual"], state7)
check("B5a verify transport failure -> attempt failure, rc1, no flag",
      rc8 == 1 and out8.get("action") == "delist_failed"
      and rd.load_state(str(state7)).get("delisted") is False
      and node7.kinds() == ["pull", "verify", "pull", "verify"],
      f"rc={rc8} kinds={node7.kinds()}")

# B6: the relist direction has NO symmetric re-fetch (asymmetry residual).
node8, state8, d8 = new_env()
run(node8, ["--manual"], state8)
node8.calls = []
rc9, out9 = run(node8, ["--relist"], state8)
check("B6a relist success is gated only on the round-trip self-report",
      rc9 == 0 and out9.get("action") == "relist"
      and node8.kinds() == ["relist"],
      f"rc={rc9} kinds={node8.kinds()} (no verify follows)")

# B7: source-level gate check — confirmed only under ok AND count==0.
gate = 'vres.get("ok") is True and vres.get("count") == 0'
check("B7 confirmed is gated on the re-fetch ok+count==0 in source",
      gate in SRC)

# ══════════════════════════════════════════════════════════════════════════
print("== GROUP C — Finding 3: fail-safe on absent, garbage, stale ==")

# C1: staleness fail-safe directions, real mtimes plus pinned `now` for the
# exact boundary (wall-clock jitter between utime and the check otherwise
# pushes an "exactly 1800 s" file a microsecond over the inclusive bound).
d1 = tempfile.mkdtemp(dir=SCRATCH)
missing = os.path.join(d1, "nope.json")
fresh = write_preds(d1, [pred()], "fresh.json")
aged = write_preds(d1, [pred()], "aged.json", age_s=3600)
future = write_preds(d1, [pred()], "future.json")
os.utime(future, (time.time() + 7200, time.time() + 7200))
edge = write_preds(d1, [pred()], "edge.json")
edge_mtime = os.path.getmtime(edge)
states = {
    "missing": rd.feed_is_stale(missing),
    "aged_3600": rd.feed_is_stale(aged),
    "future_mtime": rd.feed_is_stale(future),
    "fresh": rd.feed_is_stale(fresh),
    "boundary_exact_1800": rd.feed_is_stale(edge, now=edge_mtime + 1800.0),
    "over_boundary_1800.5": rd.feed_is_stale(edge, now=edge_mtime + 1800.5),
    "zero_age": rd.feed_is_stale(edge, now=edge_mtime),
}
check("C1 staleness: missing/aged/future => stale; fresh/boundary => not",
      states == {"missing": True, "aged_3600": True, "future_mtime": True,
                 "fresh": False, "boundary_exact_1800": False,
                 "over_boundary_1800.5": True, "zero_age": False},
      f"{states}")

# C2: a stale feed can neither fire nor poison the baseline.
node9, state9, d9 = new_env()
rd.save_state(state9, {"ts": 1, "delisted": False,
                       "snapshot": {"zai\x1f1h": 10.0}})
stale_p = write_preds(d9, [pred(hours=1.0)], "stale.json", age_s=3600)
rc10, out10 = run(node9, ["--preds", stale_p], state9)
st9 = rd.load_state(str(state9))
check("C2a stale feed: no fire, preds_stale true, rc1, zero remote calls",
      rc10 == 1 and out10.get("action") == "none"
      and out10.get("preds_stale") is True and node9.calls == [],
      f"rc={rc10} action={out10.get('action')} "
      f"preds_stale={out10.get('preds_stale')} calls={node9.calls}")
check("C2b stale feed left the stored baseline untouched",
      st9.get("snapshot") == {"zai\x1f1h": 10.0},
      f"snapshot={st9.get('snapshot')}")

# C2c: control — the SAME numbers fresh DO fire (proves the guard, not absence).
node10, state10, d10 = new_env()
rd.save_state(state10, {"ts": 1, "delisted": False,
                        "snapshot": {"zai\x1f1h": 10.0}})
rc11, out11 = run(node10, ["--preds", write_preds(d10, [pred(hours=1.0)])],
                  state10)
check("C2c control: identical numbers with a fresh mtime DO delist",
      rc11 == 0 and out11.get("action") == "delist",
      f"rc={rc11} action={out11.get('action')}")

# C3: garbage feed.
node11, state11, d11 = new_env()
rd.save_state(state11, {"ts": 1, "delisted": False,
                        "snapshot": {"zai\x1f1h": 10.0}})
g = write_preds(d11, "{not json at all", "garbage.json")
rc12, out12 = run(node11, ["--preds", g], state11)
st11 = rd.load_state(str(state11))
check("C3a garbage feed: rc1, preds_error true, action none, no fire",
      rc12 == 1 and out12.get("preds_error") is True
      and out12.get("action") == "none" and node11.calls == [],
      f"rc={rc12} preds_error={out12.get('preds_error')}")
check("C3b garbage feed never wiped the stored baseline",
      st11.get("snapshot") == {"zai\x1f1h": 10.0},
      f"snapshot={st11.get('snapshot')}")

# C4: garbage AND aged — precision note on the reported flag pair.
node12, state12, d12 = new_env()
g2 = write_preds(d12, "{bad", "garbage_aged.json", age_s=7200)
rc13, out13 = run(node12, ["--preds", g2], state12)
check("C4 garbage+aged reports preds_error=true and preds_stale=false",
      rc13 == 1 and out13.get("preds_error") is True
      and out13.get("preds_stale") is False,
      f"rc={rc13} preds_error={out13.get('preds_error')} "
      f"preds_stale={out13.get('preds_stale')}")

# C5: type guards.
node13, state13, d13 = new_env()
bad = [pred(unc="0.9"), pred(unc=True), pred(unc=None), pred(hours="soon")]
rc14, out14 = run(node13, ["--preds", write_preds(d13, bad)], state13)
check("C5a malformed uncertainty/hours types never fire",
      rc14 == 0 and out14.get("action") == "none" and node13.calls == [],
      f"rc={rc14} action={out14.get('action')}")
check("C5b evaluate_triggers on the same malformed feed fires nothing",
      rd.evaluate_triggers(bad, {})["fire"] is False)
non_dicts = write_preds(d13, ["nope", 42, {"no": "shape"}], "nd.json")
rc15, out15 = run(node13, ["--preds", non_dicts], state13)
check("C5c non-dict feed entries dropped, no crash, action none",
      rc15 == 0 and out15.get("action") == "none",
      f"rc={rc15} action={out15.get('action')}")
check("C5d cosmetic: _hours accepts bool while the variance guard excludes it",
      rd._hours({"exhausts_in_hours": True}) is True
      and rd.variance_jumped([pred(unc=True)]) == [])

# C6: manual override is never gated on freshness.
node14, state14, d14 = new_env()
stale2 = write_preds(d14, [pred(unc=0.9)], "stale2.json", age_s=3600)
rc16, out16 = run(node14, ["--manual", "--preds", stale2], state14)
check("C6 manual override delists despite a stale feed (observed, not obeyed)",
      rc16 == 0 and out16.get("action") == "delist"
      and out16.get("preds_stale") is True
      and node14.kinds() == ["pull", "verify"],
      f"rc={rc16} preds_stale={out16.get('preds_stale')} kinds={node14.kinds()}")

# C7: --preds-key default is unscoped.
unscoped = [pred(key="openrouter", hours=10.0, unc=0.95)]
check("C7a evaluate_triggers applies no implicit key filter",
      rd.evaluate_triggers(unscoped, {})["fire"] is True)
node15, state15, d15 = new_env()
rc17, out17 = run(node15, ["--preds", write_preds(d15, unscoped)], state15)
check("C7b openrouter-only variance spike fires the routstr delist, unscoped",
      out17.get("action") == "delist", f"rc={rc17} action={out17.get('action')}")
node16, state16, d16 = new_env()
rc18, out18 = run(node16, ["--preds-key", "zai",
                           "--preds", write_preds(d16, unscoped)], state16)
check("C7c --preds-key zai makes the same feed quiet",
      rc18 == 0 and out18.get("action") == "none" and node16.calls == [],
      f"rc={rc18} action={out18.get('action')}")

# C8: exhausted action budget fails closed before spawning.
spawned = []
_real_sp = rd.subprocess
rd.subprocess = types.SimpleNamespace(
    run=lambda *a, **k: spawned.append(a) or None)
b = ORIG_SSH("debian@host", "c")
res_budget = b._run("print(1)", dry_run=False, action="pull",
                    deadline=time.monotonic() - 5)
rd.subprocess = _real_sp
check("C8 exhausted action budget -> ok=False, zero subprocess spawn",
      res_budget.get("ok") is False
      and "budget" in (res_budget.get("error") or "") and spawned == [],
      f"{res_budget} spawned={len(spawned)}")

# ══════════════════════════════════════════════════════════════════════════
print("== GROUP D — citation audit for every file:line asserted below ==")

T = open(DEPLOYED_TESTS, encoding="utf-8").read().splitlines()
M = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..",
                      "..", "tests", "test_routstr_delist.py"),
         encoding="utf-8").read().splitlines()
DOC = open(os.path.expanduser("~/.hermes/bot/docs/routstr-delist.md"),
           encoding="utf-8").read().splitlines()
citations = [
    # (source lines, line no, substring that must be present)
    (SRC_LINES, 78, "STALENESS_S = 1800"),
    (SRC_LINES, 107, "if not preds_now or not preds_prev:"),
    (SRC_LINES, 143, "if not preds:"),
    (SRC_LINES, 152, "isinstance(unc, (int, float)) or isinstance(unc, bool)"),
    (SRC_LINES, 172, "return os.path.isfile(override_path)"),
    (SRC_LINES, 261, "if preds:"),
    (SRC_LINES, 303, "var = variance_jumped(preds_now, threshold=variance_threshold)"),
    (SRC_LINES, 317, '"fire": bool(accel or var or override),'),
    (SRC_LINES, 355, "UPDATE models SET enabled=0 WHERE enabled=1;"),
    (SRC_LINES, 361, "UPDATE models SET enabled=1;"),
    (SRC_LINES, 371, "SELECT name FROM models WHERE enabled=1"),
    (SRC_LINES, 394, "UPDATE models SET enabled=1 WHERE name IN"),
    (SRC_LINES, 408, "SELECT COUNT(*) FROM models WHERE enabled=1"),
    (SRC_LINES, 414, "def build_ssh_docker_cmd"),
    (SRC_LINES, 423, "shlex.quote"),
    (SRC_LINES, 485, "def feed_is_stale"),
    (SRC_LINES, 494, "return not (0 <= age <= max_age_s)"),
    (SRC_LINES, 585, "preds_error = bool(args.preds) and not raw_preds"),
    (SRC_LINES, 589, "preds_stale = bool(args.preds)"),
    (SRC_LINES, 602, "if not names and not args.relist_any:"),
    (SRC_LINES, 626, 'if not res.get("ok"):'),
    (SRC_LINES, 635, 'state.pop("pulled_models", None)'),
    (SRC_LINES, 649, 'fire = args.delist or dec["fire"]'),
    (SRC_LINES, 660, "return 1 if (preds_error or preds_stale) else 0"),
    (SRC_LINES, 671, "while attempts < MAX_PULL_ATTEMPTS:"),
    (SRC_LINES, 682, "vres = backend.verify(deadline=deadline)"),
    (SRC_LINES, 683, 'vres.get("ok") is True and vres.get("count") == 0'),
    (SRC_LINES, 687, "confirmed = True"),
    (SRC_LINES, 747, "delisted=True"),
    (SRC_LINES, 790, "def verify(self"),
    (SRC_LINES, 806, "timeout = min(SSH_TIMEOUT_S, remaining)"),
    # contract suite (deployed copy == repo tests/test_routstr_delist_contract.py)
    (T, 50, "for _cand in (_HERE.parent"),
    (T, 108, "self.ladder_artifact = tmpdir"),
    (T, 308, "def test_first_run_without_baseline_is_quiet"),
    (T, 334, 'assert rig.node.kinds() == ["pull", "verify"]'),
    (T, 346, "def test_unverified_pull_is_a_failed_delist"),
    (T, 379, "def test_variance_at_threshold_is_quiet"),
    (T, 427, "def test_manual_override_is_never_gated_on_feed_staleness"),
    (T, 468, "class TestSemanticGuardLadderUntouched"),
    (T, 483, 'assert "upstream_providers" not in payload'),
    (T, 487, 'name == "routstr" and enabled == 1'),
    (T, 731, "def test_dry_run_publishes_no_event_and_flips_no_flag"),
    # main suite
    (M, 146, "def test_non_numeric_uncertainty_ignored_not_crash"),
    (M, 302, "class TestSaleNotProvider"),
    (M, 345, "def test_ssh_cmd_is_single_shlex_safe_remote_command"),
    (M, 353, "self.assertEqual(len(cmd), 3)"),
    (M, 566, "class TestRefetchConfirmation"),
    (M, 621, "class TestScopedRelist"),
    (M, 816, "class TestCircuitBreaker"),
    (M, 928, "class TestStalenessGuard"),
    (M, 937, "def test_stale_feed_never_triggers"),
    (M, 968, "def test_staleness_threshold_boundary"),
    (M, 980, "def test_stale_feed_exit_zero_when_override_fires"),
    (M, 995, "def test_stale_feed_baseline_not_consumed"),
    (M, 1072, "class TestDryRunPurity"),
    (M, 1101, "class TestRealBackendRun"),
    (M, 1166, 'self.assertIn("name IN (?,?)", remote)'),
    # ops doc (contract stand-in, bot copy)
    (DOC, 21, "TestSaleNotProvider"),
    (DOC, 29, "**No blanket relist.**"),
    (DOC, 55, "another provider's variance spike can never pull the routstr SALE"),
    (DOC, 56, "**Freshness guard (cold-review finding 3):**"),
    (DOC, 60, "The manual override is never gated on freshness."),
    (DOC, 69, "**Re-fetch confirmation (cold-review finding 2):**"),
    (DOC, 106, "--preds-key zai"),
    (DOC, 137, "shlex.quote"),
]
bad = [(ln, want) for lines, ln, want in citations
       if ln > len(lines) or want not in lines[ln - 1]]
check(f"D1 all {len(citations)} cited file:line pairs verified against source",
      bad == [], f"mismatches={bad}")

total = len(RESULTS)
failed = [n for n, ok, _ in RESULTS if not ok]
print(f"\n== probe_f13_pass12: {total - len(failed)}/{total} PASS ==")
if failed:
    print("FAILED: " + ", ".join(failed))
raise SystemExit(0 if not failed else 1)
