#!/usr/bin/env python3
"""probe_f13_pass25.py — fresh independent re-derivation, routstr delist findings 1-3.

Twenty-fifth offload pass. Hermetic: no network, no real ssh, no /tmp scratch
(all scratch under ~/.cache/routstr-f13-pass25). Every citation the pass-25
deliverable makes is audited line-by-line (A), then findings 1/2/3 are
re-derived by EXECUTION (B/C/D), then the review-record shape is checked (E).
Run twice; the transcript sha256 must be identical.

    python3 docs/reviews/routstr_f13_probes/probe_f13_pass25.py
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
import types
from pathlib import Path

REPO = Path("/home/c03rad0r/repos/merchant-routing")
SRC = REPO / "src" / "routstr_delist.py"
CONTRACT = REPO / "tests" / "test_routstr_delist_contract.py"
MAINT = REPO / "tests" / "test_routstr_delist.py"
DOC = REPO / "docs" / "routstr-delist.md"
DELIV = REPO / "docs" / "reviews" / "findings_1_3.md"

HOME = Path.home()
BOT = HOME / ".hermes" / "bot"
BOT_SRC = BOT / "scripts" / "routstr_delist.py"
BOT_TESTS = BOT / "tests" / "test_routstr_delist.py"
BOT_DOC = BOT / "docs" / "routstr-delist.md"
BOT_DELIV = BOT / "docs" / "reviews" / "findings_1_3.md"
CONTRACT_MISSING = BOT / "docs" / "routstr_delist_contract.md"

SCRATCH = HOME / ".cache" / "routstr-f13-pass25"
os.environ["TMPDIR"] = str(SCRATCH / "tmp")
shutil.rmtree(SCRATCH, ignore_errors=True)
(SCRATCH / "tmp").mkdir(parents=True, exist_ok=True)
os.fsync = lambda fd: None  # this host can stall inside fsync (contract Rig comment)

sys.path.insert(0, str(SRC.parent))
import routstr_delist as rd  # noqa: E402

RESULTS: list[tuple[str, bool, str]] = []


def ck(cid: str, cond: bool, detail: str = "") -> None:
    RESULTS.append((cid, bool(cond), detail))


def load(p: Path) -> list[str]:
    return p.read_text(encoding="utf-8").splitlines()


# ── A. citation audit: every file:line the deliverable cites ──────────────
PATHS = {"src": SRC, "contract": CONTRACT, "tests": MAINT, "docs": DOC}
CITE: list[tuple[str, str, int, str]] = [
    # Finding 1 — safety
    ("F1-distinction", "src", 9, "disabling the routstr provider"),
    ("F1-upstream-mention-a", "src", 35, "upstream_providers"),
    ("F1-upstream-mention-b", "src", 352, "upstream_providers"),
    ("F1-upstream-mention-c", "src", 771, "upstream_providers"),
    ("F1-pull-sql", "src", 355, "UPDATE models SET enabled=0 WHERE enabled=1;"),
    ("F1-blanket-sql", "src", 361, "UPDATE models SET enabled=1;"),
    ("F1-pull-select-names", "src", 371, "SELECT name FROM models WHERE enabled=1"),
    ("F1-relist-connect", "src", 393, "sqlite3.connect('/app/data/keys.db')"),
    ("F1-relist-scoped-update", "src", 394, "UPDATE models SET enabled=1 WHERE name IN"),
    ("F1-verify-count", "src", 408, "SELECT COUNT(*) FROM models WHERE enabled=1"),
    ("F1-build-cmd-def", "src", 414, "def build_ssh_docker_cmd"),
    ("F1-quote-container", "src", 423, "shlex.quote(container)"),
    ("F1-quote-payload", "src", 424, "shlex.quote(payload)"),
    ("F1-cmd-return", "src", 425, 'return ["ssh", ssh_target, remote]'),
    ("F1-nak-subprocess", "src", 459, "subprocess.run(argv"),
    ("F1-ssh-subprocess", "src", 808, "subprocess.run(cmd"),
    ("F1-relist-refuse-gate", "src", 600, "if args.relist:"),
    ("F1-relist-refuse-action", "src", 606, '"action": "relist_refused"'),
    ("F1-relist-refuse-rc", "src", 611, "return 1"),
    ("F1-ssh-target-arg", "src", 536, "--ssh-target"),
    ("F1-container-arg", "src", 537, "--container"),
    ("F1-keysdb-a", "src", 370, "/app/data/keys.db"),
    ("F1-keysdb-b", "src", 385, "/app/data/keys.db"),
    ("F1-keysdb-c", "src", 393, "/app/data/keys.db"),
    ("F1-keysdb-d", "src", 407, "/app/data/keys.db"),
    ("F1-save-unblock", "src", 565, "save_state(args.state, state)"),
    ("F1-save-relist-dry", "src", 622, "save_state(args.state, state)"),
    ("F1-save-relist-fail", "src", 629, "save_state(args.state, state)"),
    ("F1-save-relist-ok", "src", 638, "save_state(args.state, state)"),
    ("F1-save-quiet", "src", 654, "save_state(args.state, state)"),
    ("F1-save-delist-dry", "src", 710, "save_state(args.state, state)"),
    ("F1-save-delist-fail", "src", 732, "save_state(args.state, state)"),
    ("F1-save-delist-ok", "src", 752, "save_state(args.state, state)"),
    ("F1-ladder-artifact", "contract", 108, "self.ladder_artifact = tmpdir"),
    ("F1-provider-table", "contract", 129, "CREATE TABLE upstream_providers"),
    ("F1-provider-rows", "contract", 160, "FROM upstream_providers"),
    ("F1-semantic-class", "contract", 468, "class TestSemanticGuardLadderUntouched"),
    ("F1-ladder-byte-id", "contract", 480, "ladder_bytes() == ladder_before"),
    ("F1-no-payload-table", "contract", 483, '"upstream_providers" not in payload'),
    ("F1-relist-ladder-id", "contract", 504, "ladder_bytes() == ladder_before"),
    ("F1-pull-sql-test", "tests", 303, "def test_pull_sql_touches_only_models_listing"),
    ("F1-relist-sql-test", "tests", 311, "def test_relist_sql_touches_only_models_listing"),
    ("F1-verify-payload-test", "tests", 336, "def test_verify_payload_scoped_to_models_listing"),
    ("F1-ssh-single-arg-test", "tests", 345, "def test_ssh_cmd_is_single_shlex_safe_remote_command"),
    # Finding 2 — confirmation
    ("F2-verify-payload-def", "src", 400, "def verify_pull_payload"),
    ("F2-verify-call", "src", 682, "vres = backend.verify(deadline=deadline)"),
    ("F2-verify-gate", "src", 683, 'vres.get("ok") is True and vres.get("count") == 0'),
    ("F2-confirmed-set", "src", 687, "confirmed = True"),
    ("F2-refuted-pull", "src", 692, 'res["ok"] = False'),
    ("F2-retry", "src", 671, "while attempts < MAX_PULL_ATTEMPTS:"),
    ("F2-failure-branch", "src", 719, "if not confirmed:"),
    ("F2-failures", "src", 724, "fails += 1"),
    ("F2-relist-report-gate", "src", 626, 'if not res.get("ok"):'),
    ("F2-relist-pop", "src", 635, 'state.pop("pulled_models", None)'),
    ("F2-ssh-run-def", "src", 795, "def _run(self, payload"),
    ("F2-lastline-json", "src", 814, "json.loads(out.splitlines()[-1])"),
    ("F2-ok-gate", "src", 822, 'proc.returncode == 0 and data.get("ok") is True'),
    ("F2-verify-gates-test", "tests", 567, "def test_verify_gates_success"),
    ("F2-verify-failure-test", "tests", 603, "def test_verify_failure_is_attempt_failure"),
    ("F2-unverified-pull-test", "contract", 346, "def test_unverified_pull_is_a_failed_delist"),
    ("F2-garbage-stdout-test", "tests", 1116, "def test_pull_garbage_stdout_is_failure"),
    ("F2-nonzero-rc-test", "tests", 1123, "def test_pull_nonzero_rc_is_failure_even_with_ok_payload"),
    ("F2-exception-test", "tests", 1146, "def test_exception_is_failure_not_crash"),
    ("F2-doc-refetch", "docs", 69, "Re-fetch confirmation"),
    ("F2-doc-count-zero", "docs", 71, "count == 0"),
    ("F2-doc-dryrun-intent", "docs", 87, "Dry-run is intent-only"),
    # Finding 3 — fail-safe
    ("F3-staleness-const", "src", 78, "STALENESS_S = 1800"),
    ("F3-bool-exclusion", "src", 152, "isinstance(unc, bool)"),
    ("F3-hours-guard-a", "src", 193, "def _hours"),
    ("F3-hours-guard-b", "src", 196, "isinstance(h, (int, float))"),
    ("F3-baseline-guard-a", "src", 261, "if preds:"),
    ("F3-baseline-guard-b", "src", 262, 'new["snapshot"]'),
    ("F3-variance-no-key", "src", 303, "variance_jumped(preds_now, threshold=variance_threshold)"),
    ("F3-drop-nondict", "src", 479, "isinstance(d, dict)"),
    ("F3-read-return-empty", "src", 482, "return []"),
    ("F3-feed-is-stale", "src", 485, "def feed_is_stale"),
    ("F3-age-expr", "src", 494, "not (0 <= age <= max_age_s)"),
    ("F3-oserror-failclosed", "src", 495, "except OSError:"),
    ("F3-oserror-true", "src", 496, "return True"),
    ("F3-manual-not-gated", "src", 580, "override = args.manual or manual_override(args.override)"),
    ("F3-preds-error", "src", 585, "preds_error = bool(args.preds) and not raw_preds"),
    ("F3-stale-guard", "src", 589, "preds_stale = bool(args.preds) and bool(raw_preds)"),
    ("F3-stale-zeroes", "src", 591, "if preds_stale:"),
    ("F3-stale-zeroes2", "src", 592, "raw_preds = []"),
    ("F3-preds-key", "src", 594, "if args.preds_key:"),
    ("F3-preds-key-filter", "src", 597, "args.preds_key"),
    ("F3-fire-flag", "src", 649, 'fire = args.delist or dec["fire"]'),
    ("F3-quiet-branch", "src", 651, "if not fire:"),
    ("F3-quiet-save", "src", 654, "save_state(args.state, state)"),
    ("F3-quiet-preds-error-out", "src", 656, '"preds_error": preds_error,'),
    ("F3-quiet-preds-stale-out", "src", 657, '"preds_stale": preds_stale,'),
    ("F3-quiet-rc", "src", 660, "return 1 if (preds_error or preds_stale) else 0"),
    ("F3-dry-last-run", "src", 705, '"last_dry_run"'),
    ("F3-first-run-test", "tests", 176, "def test_first_run_never_fires_on_acceleration"),
    ("F3-nonnumeric-unc-test", "tests", 146, "def test_non_numeric_uncertainty_ignored_not_crash"),
    ("F3-baseline-preserve-test", "tests", 243, "def test_update_state_empty_preds_preserves_baseline"),
    ("F3-unreadable-feed-test", "tests", 547, "def test_unreadable_preds_feed_is_error_not_quiet"),
    ("F3-preds-key-test", "tests", 776, "def test_preds_key_scopes_triggers"),
    ("F3-stale-never-triggers", "tests", 937, "def test_stale_feed_never_triggers"),
    ("F3-boundary-test", "tests", 968, "def test_staleness_threshold_boundary"),
    ("F3-stale-override-test", "tests", 980, "def test_stale_feed_exit_zero_when_override_fires"),
    ("F3-baseline-not-consumed", "tests", 995, "def test_stale_feed_baseline_not_consumed"),
    ("F3-first-run-contract", "contract", 308, "def test_first_run_without_baseline_is_quiet"),
    ("F3-doc-freshness", "docs", 56, "Freshness guard"),
    ("F3-doc-manual-not-gated", "docs", 60, "never gated on freshness"),
    ("F3-doc-kind30078", "docs", 124, "kind-30078"),
    ("F3-doc-no-blanket", "docs", 29, "No blanket relist"),
]

for cid, key, lineno, sub in CITE:
    lines = load(PATHS[key])
    ok = 0 < lineno <= len(lines) and sub in lines[lineno - 1]
    ck(f"A:{cid}", ok, f"{key}:{lineno} <- {sub!r}")

# ── B. finding 1 — safety: SALE only, provider/ladder untouched ───────────
src_text = SRC.read_text(encoding="utf-8")
src_lines = src_text.splitlines()

up_lines = [i + 1 for i, l in enumerate(src_lines) if "upstream_providers" in l]
ck("B:upstream-mentions-exactly-3", up_lines == [35, 352, 771], str(up_lines))

sql = rd.pull_listing_sql()
rel = rd.relist_sql()
plp = rd.pull_listing_payload()
rlp_scoped = rd.relist_payload(["a", "b"])
rlp_blanket = rd.relist_payload([])
vp = rd.verify_pull_payload()
ck("B:pull-sql-models-only", "models" in sql and "upstream_providers" not in sql)
ck("B:pull-sql-disables", "enabled=0" in sql)
ck("B:blanket-sql-models-only", "models" in rel and "upstream_providers" not in rel)
ck("B:relist-parameterized", "name IN (?,?)" in rlp_scoped and repr(["a", "b"]) in rlp_scoped)
ck("B:relist-no-sql-interp", "name IN ('a'" not in rlp_scoped)
ck("B:verify-read-only", "UPDATE" not in vp.upper() and "SELECT COUNT(*)" in vp)
ck("B:no-payload-names-table",
   all("upstream_providers" not in p for p in (sql, rel, rlp_scoped, rlp_blanket, plp, vp)))
ck("B:pull-payload-one-update", plp.upper().count("UPDATE ") == 1)
ck("B:pull-payload-select-names", "SELECT name FROM models WHERE enabled=1" in plp)
ck("B:relist-scoped-one-update", rlp_scoped.upper().count("UPDATE ") == 1)
ck("B:relist-blanket-one-update", rlp_blanket.upper().count("UPDATE ") == 1)
for kw in ("INSERT ", "DELETE ", "DROP ", "ALTER ", "REPLACE "):
    ck(f"B:no-{kw.strip().lower()}", not any(kw in p.upper() for p in (plp, rlp_scoped, rlp_blanket, vp)))

tree = ast.parse(src_text)
subrun = sorted(n.lineno for n in ast.walk(tree)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and n.func.attr == "run" and isinstance(n.func.value, ast.Name)
                and n.func.value.id == "subprocess")
ck("B:subprocess-run-sites", subrun == [459, 808], str(subrun))
ck("B:no-shell-true", "shell=True" not in src_text)

cmd = rd.build_ssh_docker_cmd("debian@host", "routstr public", plp)
ck("B:ssh-argv-len3", len(cmd) == 3 and cmd[0] == "ssh" and cmd[1] == "debian@host")
parts = shlex.split(cmd[2])
ck("B:remote-roundtrip", parts[:5] == ["docker", "exec", "routstr public", "python3", "-c"]
   and parts[5] == plp)
evil = "evil'; rm -rf / #"
cmd2 = rd.build_ssh_docker_cmd("debian@host", evil, plp)
parts2 = shlex.split(cmd2[2])
ck("B:hostile-container-single-token", parts2[2] == evil and evil not in cmd2[0] and evil not in cmd2[1])

# semantic ladder guard: execute the REAL payloads against a two-table node
uri = "file:probe25node?mode=memory&cache=shared"
con = sqlite3.connect(uri, uri=True)
con.execute("CREATE TABLE models (name TEXT PRIMARY KEY, enabled INTEGER NOT NULL)")
for n in ("gpt-4o", "claude-3", "llama"):
    con.execute("INSERT INTO models VALUES (?, 1)", (n,))
con.execute("INSERT INTO models VALUES ('op-disabled', 0)")
con.execute("CREATE TABLE upstream_providers (name TEXT PRIMARY KEY, enabled INTEGER NOT NULL, weight REAL NOT NULL)")
con.execute("INSERT INTO upstream_providers VALUES ('routstr', 1, 10.0)")
con.commit()
prov_before = list(con.execute("SELECT name,enabled,weight FROM upstream_providers ORDER BY name"))
ladder = SCRATCH / "t470_ladder.json"
ladder.write_bytes(json.dumps({"ladder": [{"name": "routstr", "enabled": True}]}, sort_keys=True).encode())
ladder_before = ladder.read_bytes()

_shim = types.ModuleType("sqlite3")
_shim.connect = lambda *a, **k: sqlite3.connect(uri, uri=True)


def _imp(name, globals=None, locals=None, fromlist=(), level=0):
    if name == "sqlite3":
        return _shim
    return builtins.__import__(name, globals, locals, fromlist, level)


def exec_payload(payload: str) -> dict:
    buf = io.StringIO()
    g = {"__builtins__": {"__import__": _imp, "print": print}}
    with contextlib.redirect_stdout(buf):
        exec(payload, g)  # noqa: S102 — OUR OWN payload builders
    return json.loads(buf.getvalue().strip().splitlines()[-1])


pull_res = exec_payload(plp)
ck("B:semantic-pull-captures-names", pull_res["pulled"] == ["gpt-4o", "claude-3", "llama"], str(pull_res))
ck("B:semantic-pull-disabled-all",
   set(en for _, en in con.execute("SELECT name, enabled FROM models")) == {0})
ver_res = exec_payload(vp)
ck("B:semantic-verify-count0", ver_res == {"ok": True, "count": 0}, str(ver_res))
rel_res = exec_payload(rd.relist_payload(["gpt-4o", "claude-3", "llama"]))
ck("B:semantic-relist-restores3", rel_res.get("restored") == 3, str(rel_res))
ck("B:semantic-operator-row-stays-off",
   dict(con.execute("SELECT name, enabled FROM models"))["op-disabled"] == 0)
ck("B:semantic-providers-unchanged",
   list(con.execute("SELECT name,enabled,weight FROM upstream_providers ORDER BY name")) == prov_before)
ck("B:semantic-ladder-bytes-identical", ladder.read_bytes() == ladder_before)


# ── backend fake for main() ───────────────────────────────────────────────
class FB:
    def __init__(self, pull_res=None, verify_res=None, relist_res=None):
        self.calls = []
        self.pull_res = pull_res if pull_res is not None else {"ok": True, "pulled": ["gpt-4o"]}
        self.verify_res = verify_res if verify_res is not None else {"ok": True, "count": 0}
        self.relist_res = relist_res if relist_res is not None else {"ok": True}

    def pull(self, dry_run=False, deadline=None):
        self.calls.append("pull")
        return dict(self.pull_res)

    def verify(self, dry_run=False, deadline=None):
        self.calls.append("verify")
        return dict(self.verify_res)

    def relist(self, names=None, dry_run=False, deadline=None):
        self.calls.append("relist")
        return dict(self.relist_res)


def run_main(argv, fb=None):
    state = SCRATCH / "state.json"
    args = ["--state", str(state), "--override", str(SCRATCH / "absent.override")] + argv
    out = io.StringIO()
    orig = rd._SshBackend
    if fb is not None:
        rd._SshBackend = lambda t, c: fb
    try:
        with contextlib.redirect_stdout(out):
            rc = rd.main(args)
    finally:
        rd._SshBackend = orig
    raw = out.getvalue()
    return rc, (json.loads(raw) if raw.strip() else {}), state


def fresh_state():
    p = SCRATCH / "state.json"
    if p.exists():
        p.unlink()
    return p


def write_feed(obj, name="preds.json", age_s=0):
    p = SCRATCH / name
    p.write_text(json.dumps(obj))
    if age_s:
        import time as _t
        old = _t.time() - age_s
        os.utime(p, (old, old))
    return p


# blanket relist refusal (finding 1)
fresh_state()
fb = FB(relist_res={"ok": True})
rc, out, _ = run_main(["--relist"], fb)
ck("B:blanket-relist-refused", rc == 1 and out.get("action") == "relist_refused",
   f"rc={rc} {out.get('action')}")
ck("B:blanket-relist-no-remote", fb.calls == [], str(fb.calls))

# ── C. finding 2 — confirmation via independent read-only re-fetch ────────
ck("C:verify-select-only", "SELECT COUNT(*)" in vp and "UPDATE" not in vp.upper())

fresh_state()
fb = FB()
rc, out, _ = run_main(["--manual"], fb)
ck("C:happy-rc0", rc == 0, str(rc))
ck("C:happy-action-delist", out.get("action") == "delist", str(out.get("action")))
ck("C:happy-confirmed", out.get("confirmed") is True)
ck("C:happy-verified-count0", out.get("verified_count") == 0)
ck("C:happy-kinds", fb.calls == ["pull", "verify"], str(fb.calls))
ck("C:happy-durable-delisted", rd.load_state(str(SCRATCH / "state.json")).get("delisted") is True)

fresh_state()
fb = FB(pull_res={"ok": True, "pulled": ["x"]}, verify_res={"ok": True, "count": 3})
rc, out, _ = run_main(["--manual"], fb)
ck("C:lying-pull-rc1", rc == 1, str(rc))
ck("C:lying-pull-action", out.get("action") == "delist_failed", str(out.get("action")))
ck("C:lying-pull-kinds", fb.calls == ["pull", "verify", "pull", "verify"], str(fb.calls))
ck("C:lying-pull-no-flag", rd.load_state(str(SCRATCH / "state.json")).get("delisted") is False)

# relist asymmetry (MEDIUM)
fresh_state()
rd.save_state(str(SCRATCH / "state.json"), {"delisted": True, "pulled_models": ["gpt-4o"]})
fb = FB(relist_res={"ok": True})
rc, out, _ = run_main(["--relist"], fb)
ck("C:relist-no-verify-roundtrip", fb.calls == ["relist"], str(fb.calls))
ck("C:relist-gated-on-selfreport", rc == 0 and out.get("action") == "relist")
st = rd.load_state(str(SCRATCH / "state.json"))
ck("C:relist-clears-flag", st.get("delisted") is False)
ck("C:relist-pops-names", "pulled_models" not in st)

import unittest.mock as _mock
be = rd._SshBackend("debian@host", "routstr-public")
with _mock.patch.object(rd.subprocess, "run",
                        return_value=_mock.Mock(returncode=0, stdout='{"ok": true, "count": 0}', stderr="")):
    r = be.verify()
ck("C:run-parses-count", r.get("ok") is True and r.get("count") == 0)
with _mock.patch.object(rd.subprocess, "run",
                        return_value=_mock.Mock(returncode=0, stdout="bash: warning\n", stderr="")):
    r = be.pull()
ck("C:run-garbage-fails", r.get("ok") is False)
with _mock.patch.object(rd.subprocess, "run",
                        return_value=_mock.Mock(returncode=255, stdout='{"ok": true}', stderr="x")):
    r = be.pull()
ck("C:run-nonzero-rc-fails", r.get("ok") is False)
with _mock.patch.object(rd.subprocess, "run",
                        return_value=_mock.Mock(returncode=0, stdout='{"count": 0}', stderr="")):
    r = be.verify()
ck("C:run-missing-ok-key-fails", r.get("ok") is False)

fresh_state()
fb = FB()
rc, out, _ = run_main(["--manual", "--dry-run"], fb)
ck("C:dryrun-rc0-action", rc == 0 and out.get("action") == "delist")
ck("C:dryrun-no-confirmed-key", "confirmed" not in out, str(sorted(out)))

# ── D. finding 3 — fail-safe on absent/garbage/stale feed ─────────────────
feed = write_feed([{"key": "zai", "window": "1h", "exhausts_in_hours": 10.0, "uncertainty": 0.9}],
                  name="stale_probe.json")
T = os.path.getmtime(feed)
ck("D:stale-fresh-false", rd.feed_is_stale(str(feed), now=T) is False)
ck("D:stale-boundary-inclusive-false", rd.feed_is_stale(str(feed), now=T + 1800) is False)
ck("D:stale-1801-true", rd.feed_is_stale(str(feed), now=T + 1801) is True)
ck("D:stale-future-mtime-true", rd.feed_is_stale(str(feed), now=T - 10) is True)
ck("D:stale-missing-path-true", rd.feed_is_stale(str(SCRATCH / "nope.json")) is True)

# absence
fresh_state()
fb = FB()
rc, out, _ = run_main([], fb)
ck("D:absence-quiet-rc0", rc == 0 and out.get("action") == "none", f"rc={rc} {out.get('action')}")
ck("D:absence-no-remote", fb.calls == [])
ck("D:absence-no-preds-error", out.get("preds_error") is False)

# garbage feed -> preds_error, baseline intact
fresh_state()
rd.save_state(str(SCRATCH / "state.json"), {"snapshot": {"zai\x1f1h": 12.0}})
bad = write_feed(None, name="bad.json")
bad.write_text("{mid-write")
fb = FB()
rc, out, _ = run_main(["--preds", str(bad)], fb)
ck("D:garbage-rc1", rc == 1, str(rc))
ck("D:garbage-preds-error", out.get("preds_error") is True)
ck("D:garbage-action-none", out.get("action") == "none")
ck("D:garbage-baseline-intact",
   rd.load_state(str(SCRATCH / "state.json")).get("snapshot") == {"zai\x1f1h": 12.0})

# stale feed (variance elevated, 2h old) -> never fires, baseline intact
fresh_state()
rd.save_state(str(SCRATCH / "state.json"), {"snapshot": {"zai\x1f1h": 12.0}})
sf = write_feed([{"key": "zai", "window": "1h", "exhausts_in_hours": 1.0, "uncertainty": 0.99}],
                name="old.json", age_s=7200)
fb = FB()
rc, out, _ = run_main(["--preds", str(sf)], fb)
ck("D:stale-rc1", rc == 1, str(rc))
ck("D:stale-flag", out.get("preds_stale") is True)
ck("D:stale-action-none", out.get("action") == "none")
ck("D:stale-no-remote", fb.calls == [])
ck("D:stale-baseline-intact",
   rd.load_state(str(SCRATCH / "state.json")).get("snapshot") == {"zai\x1f1h": 12.0})

# manual override never gated on freshness
fresh_state()
fb = FB()
rc, out, _ = run_main(["--manual", "--preds", str(sf)], fb)
ck("D:manual-not-gated-rc0", rc == 0, str(rc))
ck("D:manual-not-gated-delist", out.get("action") == "delist")
ck("D:manual-stale-observed", out.get("preds_stale") is True)

# preds-key unscoped default -> foreign variance spike fires the delist (LOW)
fresh_state()
mixed = write_feed([{"key": "zai", "window": "1h", "exhausts_in_hours": 10.0, "uncertainty": 0.05},
                    {"key": "openrouter", "window": "1h", "exhausts_in_hours": 10.0, "uncertainty": 0.95}],
                   name="mixed.json")
fb = FB()
rc, out, _ = run_main(["--preds", str(mixed), "--dry-run"], fb)
ck("D:unscoped-default-fires", out.get("action") == "delist", str(out.get("action")))
rc, out, _ = run_main(["--preds", str(mixed), "--preds-key", "zai", "--dry-run"], fb)
ck("D:scoped-filter-quiets", out.get("action") == "none", str(out.get("action")))

# dry-run on the QUIET path perturbs durable state (MEDIUM)
fresh_state()
rd.save_state(str(SCRATCH / "state.json"), {"snapshot": {"zai\x1f1h": 12.0}})
quiet = write_feed([{"key": "zai", "window": "1h", "exhausts_in_hours": 11.0, "uncertainty": 0.05}],
                   name="quiet.json")
fb = FB()
rc, out, _ = run_main(["--preds", str(quiet), "--dry-run"], fb)
st = rd.load_state(str(SCRATCH / "state.json"))
ck("D:quiet-dryrun-rc0", rc == 0 and out.get("action") == "none")
ck("D:quiet-dryrun-refreshes-baseline", st.get("snapshot") == {"zai\x1f1h": 11.0}, str(st.get("snapshot")))
ck("D:quiet-dryrun-no-last-run", "last_dry_run" not in st)

save_sites = [i + 1 for i, l in enumerate(src_lines) if "save_state(args.state" in l]
ck("D:save-return-ignored-8-sites", len(save_sites) == 8, str(save_sites))
ck("D:keysdb-hardcoded-4",
   [i + 1 for i, l in enumerate(src_lines) if "/app/data/keys.db" in l] == [370, 385, 393, 407])
ck("D:ssh-target-unvalidated", "--ssh-target" in src_text and "--container" in src_text)

# ── E. review-record integrity ────────────────────────────────────────────
deliv = load(DELIV)
findings = [l for l in deliv if re.match(r"^## Finding ", l)]
ck("E:deliverable-exists", DELIV.is_file())
ck("E:exactly-3-findings", len(findings) == 3, str(findings))


def _section(header: str) -> list[str]:
    i = deliv.index(header)
    for j in range(i + 1, len(deliv)):
        if deliv[j].startswith("## "):
            return deliv[i:j]
    return deliv[i:]


def _declared(sev: str, tag: str) -> int:
    m = re.search(r"\*\*" + tag + r"\*\*\s*×\s*(\d+)", sev)
    return int(m.group(1)) if m else 0


for n, header in enumerate(findings, 1):
    sec = _section(header)
    sev = next((l for l in sec if l.startswith("severity:")), "")
    ck(f"E:finding{n}-severity-tag", bool(sev), sev)
    low = sum(1 for l in sec if re.match(r"^- \(\*\*LOW\*\*\)", l))
    med = sum(1 for l in sec if re.match(r"^- \(\*\*MEDIUM\*\*\)", l))
    ck(f"E:finding{n}-low-count-matches-declared", low == _declared(sev, "LOW"),
       f"declared {_declared(sev, 'LOW')} actual {low}")
    ck(f"E:finding{n}-medium-count-matches-declared", med == _declared(sev, "MEDIUM"),
       f"declared {_declared(sev, 'MEDIUM')} actual {med}")

for key, a, b in (("src", SRC, BOT_SRC), ("tests", CONTRACT, BOT_TESTS), ("docs", DOC, BOT_DOC)):
    ck(f"E:bot-parity-{key}", a.read_bytes() == b.read_bytes())
ck("E:bot-deliv-parity", DELIV.read_bytes() == BOT_DELIV.read_bytes())
ck("E:contract-path-missing-HIGH", not CONTRACT_MISSING.exists())

ck("E:ordinal-preamble", "twenty-fifth independent offload pass" in deliv[0], deliv[0])
ck("E:preamble-contract-HIGH", any("MISSING" in l and "HIGH" in l for l in deliv[:24]))
ck("E:no-appended-section", not any(l.startswith("## §") for l in deliv))

# ── report ────────────────────────────────────────────────────────────────
lines = [f"{cid} {'PASS' if ok else 'FAIL'}{(' ' + detail) if detail else ''}"
         for cid, ok, detail in RESULTS]
for l in lines:
    print(l)
fails = [l for l in lines if l.split(" ", 1)[1].startswith("FAIL")]
print(f"TALLY {len(lines)} checks: {len(lines) - len(fails)} PASS, {len(fails)} FAIL")
print("TRANSCRIPT_SHA256 " + hashlib.sha256("\n".join(lines).encode()).hexdigest())
raise SystemExit(1 if fails else 0)
