#!/usr/bin/env python3
"""Pass-75 independent re-derivation probe for routstr delist findings 1-3.

Re-measures, from raw source, every load-bearing citation and semantic claim
in docs/reviews/findings_1_3.md, and re-executes the module's real payloads
and CLI paths against hermetic fakes. Prints PASS/FAIL per check plus a
transcript sha256 (run twice -> identical digest).

Scratch lives on /dev/shm (RAM-backed, OFF /tmp): this host's home filesystem
(/dev/sda2, ~93% full) is slow to commit sqlite writes, which would otherwise
wedge the payload re-execution this probe performs.

NOTE on ordering: check E:ordinal-preamble asserts line 1 of the review doc
ends with "seventy-fifth independent offload pass".  It therefore FAILs on the
PRE-write leg (the doc still carries the seventy-fourth title) and PASSes POST.
That is expected and disclosed, not a defect -- run PRE for the measurement
baseline and POST after the rewrite; the POST tally is the acceptance run.
"""
from __future__ import annotations

import ast
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
import tokenize
from pathlib import Path

REPO = Path("/home/c03rad0r/repos/merchant-routing")
SRC = REPO / "src" / "routstr_delist.py"
CONTRACT = REPO / "tests" / "test_routstr_delist_contract.py"
MAIN = REPO / "tests" / "test_routstr_delist.py"
DOCS = REPO / "docs" / "routstr-delist.md"
BOTDOCS_CONTRACT = Path.home() / ".hermes/bot/docs/routstr_delist_contract.md"
BOTDOC = Path.home() / ".hermes/bot/docs/reviews/findings_1_3.md"
BOT_SRC = Path.home() / ".hermes/bot/scripts/routstr_delist.py"
BOT_TEST = Path.home() / ".hermes/bot/tests/test_routstr_delist.py"
BOT_DOCS = Path.home() / ".hermes/bot/docs/routstr-delist.md"
REVIEW = REPO / "docs" / "reviews" / "findings_1_3.md"

SCRATCH = Path("/dev/shm") / "f13-pass75"
if SCRATCH.exists():
    shutil.rmtree(SCRATCH, ignore_errors=True)
SCRATCH.mkdir(parents=True)

sys.path.insert(0, str(REPO / "src"))
import routstr_delist as rd  # noqa: E402

# A durable state write must not stall this host; atomicity (tmp+os.replace)
# still runs. Durability is not what this probe measures.
os.fsync = lambda fd: None  # type: ignore[assignment]

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, bool(ok), detail))


def slice_line(path: Path, n: int) -> str:
    return path.read_text(encoding="utf-8").splitlines()[n - 1]


# ── Section A: citation audit ─────────────────────────────────────────────
CITATIONS = [
    (SRC, 355, "UPDATE models SET enabled=0 WHERE enabled=1"),
    (SRC, 361, "UPDATE models SET enabled=1;"),
    (SRC, 394, "UPDATE models SET enabled=1 WHERE name IN"),
    (SRC, 371, "SELECT name FROM models WHERE enabled=1"),
    (SRC, 408, "SELECT COUNT(*) FROM models WHERE enabled=1"),
    (SRC, 414, "def build_ssh_docker_cmd"),
    (SRC, 423, "shlex.quote(container)"),
    (SRC, 424, "shlex.quote(payload)"),
    (SRC, 425, '["ssh", ssh_target, remote]'),
    (SRC, 459, "subprocess.run(argv"),
    (SRC, 808, "subprocess.run(cmd"),
    (SRC, 536, "--ssh-target"),
    (SRC, 537, "--container"),
    (SRC, 370, "/app/data/keys.db"),
    (SRC, 385, "/app/data/keys.db"),
    (SRC, 393, "/app/data/keys.db"),
    (SRC, 407, "/app/data/keys.db"),
    (SRC, 526, "--relist-any"),
    (SRC, 528, "enables every model row"),
    (SRC, 565, "save_state(args.state, state)"),
    (SRC, 622, "save_state(args.state, state)"),
    (SRC, 629, "save_state(args.state, state)"),
    (SRC, 638, "save_state(args.state, state)"),
    (SRC, 654, "save_state(args.state, state)"),
    (SRC, 710, "save_state(args.state, state)"),
    (SRC, 732, "save_state(args.state, state)"),
    (SRC, 752, "save_state(args.state, state)"),
    (SRC, 35, "upstream_providers"),
    (SRC, 352, "upstream_providers"),
    (SRC, 771, "upstream_providers"),
    (SRC, 600, "args.relist"),
    (SRC, 602, "if not names and not args.relist_any:"),
    (SRC, 606, "relist_refused"),
    (SRC, 611, "return 1"),
    (SRC, 626, "if not res.get(\"ok\"):"),
    (SRC, 634, 'delisted=False, last_reason="relist"'),
    (SRC, 635, 'state.pop("pulled_models", None)'),
    (SRC, 400, "def verify_pull_payload():"),
    (SRC, 682, "vres = backend.verify(deadline=deadline)"),
    (SRC, 683, 'vres.get("ok") is True and vres.get("count") == 0'),
    (SRC, 687, "confirmed = True"),
    (SRC, 671, "while attempts < MAX_PULL_ATTEMPTS:"),
    (SRC, 691, "res = dict(res)"),
    (SRC, 719, "if not confirmed:"),
    (SRC, 726, 'state["delisted"] = False'),
    (SRC, 739, "return 3 if newly_blocked else 1"),
    (SRC, 747, "state = update_state(state, ts=time.time(), preds=preds, delisted=True,"),
    (SRC, 75, "MAX_PULL_ATTEMPTS = 2"),
    (SRC, 78, "STALENESS_S = 1800"),
    (SRC, 649, 'fire = args.delist or dec["fire"]'),
    (SRC, 107, "preds"),
    (SRC, 143, "if not preds:"),
    (SRC, 479, "isinstance(d, dict)"),
    (SRC, 481, "except Exception:"),
    (SRC, 482, "return []"),
    (SRC, 585, "preds_error = bool(args.preds) and not raw_preds"),
    (SRC, 261, "if preds:"),
    (SRC, 262, 'new["snapshot"] = snapshot_preds(preds)'),
    (SRC, 152, "isinstance(unc, (int, float)) or isinstance(unc, bool)"),
    (SRC, 193, "def _hours(p):"),
    (SRC, 196, "isinstance(h, (int, float))"),
    (SRC, 164, "def manual_override(override_path):"),
    (SRC, 172, "return os.path.isfile(override_path)"),
    (SRC, 485, "def feed_is_stale(pred_input"),
    (SRC, 494, "return not (0 <= age <= max_age_s)"),
    (SRC, 495, "except OSError:"),
    (SRC, 496, "return True"),
    (SRC, 589, "preds_stale = bool(args.preds) and bool(raw_preds)"),
    (SRC, 591, "if preds_stale:"),
    (SRC, 592, "raw_preds = []"),
    (SRC, 594, "if args.preds_key:"),
    (SRC, 597, 'preds = [p for p in raw_preds if p.get("key") == args.preds_key]'),
    (SRC, 303, "var = variance_jumped(preds_now, threshold=variance_threshold)"),
    (SRC, 656, '"preds_error": preds_error'),
    (SRC, 660, "return 1 if (preds_error or preds_stale) else 0"),
    (SRC, 580, "override = args.manual or manual_override(args.override)"),
    (SRC, 699, "if args.dry_run:"),
    (SRC, 705, 'state["last_dry_run"]'),
    (SRC, 651, "if not fire:"),
    (SRC, 652, "update_state(state, ts=time.time(), preds=preds"),
    (SRC, 654, "save_state(args.state, state)"),
    (SRC, 724, "fails += 1"),
    (SRC, 727, 'state["consecutive_failures"] = fails'),
    (SRC, 731, 'state["blocked"] = newly_blocked'),
    (SRC, 569, "if blocked:"),
    (SRC, 578, "return 3"),
    (SRC, 561, "if args.unblock and blocked:"),
    (SRC, 567, "fails = 0"),
    (SRC, 790, "def verify(self, dry_run=False, deadline=None):"),
    (SRC, 814, "data = json.loads(out.splitlines()[-1])"),
    (SRC, 822, 'res["ok"] = proc.returncode == 0 and data.get("ok") is True'),
    (DOCS, 29, "No blanket relist"),
    (DOCS, 54, "scopes evaluation to predictions with that `key`"),
    (DOCS, 55, "another provider's variance spike can never pull the routstr SALE"),
    (DOCS, 56, "Freshness guard"),
    (DOCS, 60, "manual override is never gated on freshness"),
    (DOCS, 65, "re-fetch that fails to confirm"),
    (DOCS, 69, "Re-fetch confirmation"),
    (DOCS, 71, "Success is gated on the re-fetch reporting `count == 0`"),
    (DOCS, 87, "Dry-run is intent-only"),
    (MAIN, 345, "def test_ssh_cmd_is_single_shlex_safe_remote_command"),
    (MAIN, 567, "def test_verify_gates_success"),
    (MAIN, 603, "def test_verify_failure_is_attempt_failure"),
    (MAIN, 776, "def test_preds_key_scopes_triggers"),
    (MAIN, 937, "def test_stale_feed_never_triggers"),
    (MAIN, 968, "def test_staleness_threshold_boundary"),
    (MAIN, 980, "def test_stale_feed_exit_zero_when_override_fires"),
    (MAIN, 995, "def test_stale_feed_baseline_not_consumed"),
    (MAIN, 1039, "def test_relist_refuses_blanket_without_opt_in"),
    (MAIN, 1056, "def test_relist_any_executes_blanket"),
    (MAIN, 1107, "def test_pull_parses_last_line_json_and_gates_on_ok"),
    (MAIN, 1116, "def test_pull_garbage_stdout_is_failure"),
    (MAIN, 1123, "def test_pull_nonzero_rc_is_failure_even_with_ok_payload"),
    (MAIN, 1146, "def test_exception_is_failure_not_crash"),
    (MAIN, 146, "def test_non_numeric_uncertainty_ignored_not_crash"),
    (MAIN, 176, "def test_first_run_never_fires_on_acceleration"),
    (MAIN, 243, "def test_update_state_empty_preds_preserves_baseline"),
    (MAIN, 303, "def test_pull_sql_touches_only_models_listing"),
    (MAIN, 311, "def test_relist_sql_touches_only_models_listing"),
    (MAIN, 336, "def test_verify_payload_scoped_to_models_listing"),
    (MAIN, 547, "def test_unreadable_preds_feed_is_error_not_quiet"),
    (CONTRACT, 108, "ladder_artifact"),
    (CONTRACT, 129, "CREATE TABLE upstream_providers"),
    (CONTRACT, 160, "FROM upstream_providers"),
    (CONTRACT, 308, "def test_first_run_without_baseline_is_quiet"),
    (CONTRACT, 346, "def test_unverified_pull_is_a_failed_delist"),
    (CONTRACT, 468, "class TestSemanticGuardLadderUntouched"),
    (CONTRACT, 480, "assert rig.node.ladder_bytes() == ladder_before"),
    (CONTRACT, 483, 'assert "upstream_providers" not in payload'),
    (CONTRACT, 504, "assert rig.node.ladder_bytes() == ladder_before"),
]
for path, n, needle in CITATIONS:
    line = slice_line(path, n)
    check(f"A:{path.name}:{n}", needle in line, f"{needle!r} in {line.strip()[:70]!r}")

# source-wide structural facts
src_text = SRC.read_text(encoding="utf-8")
src_lines = src_text.splitlines()
up_lines = [i + 1 for i, l in enumerate(src_lines) if "upstream_providers" in l]
check("A:upstream-mentions-exactly-3", up_lines == [35, 352, 771], str(up_lines))
check("A:src-829-lines", len(src_lines) == 829, str(len(src_lines)))
check("A:contract-752-lines",
      len(CONTRACT.read_text(encoding="utf-8").splitlines()) == 752, "")
check("A:docs-197-lines",
      len(DOCS.read_text(encoding="utf-8").splitlines()) == 197, "")
# Statement counts are taken over EXECUTABLE STRING LITERALS ONLY. Two rounds
# of false-FAIL on the first runs of this probe (both PROBE bugs; the source
# is unchanged: md5 2ea724ef…, 829 lines, A:src-829-lines and every citation
# below pass):
#   round 1 — raw `src_text.count("UPDATE ")` / `count("SELECT ")` counts the
#     non-executable context mentions too (one COMMENT at 604, one DOCSTRING
#     at 404) and read 4 / 3 against the correct 3 / 2;
#   round 2 — tokenizing every STRING token still saw the docstring, whose
#     single token STARTS at line 401 while it mentions SELECT on line 404,
#     so the literal-line set read [371, 401, 408] against the correct
#     [371, 408].
# Fix: docstring spans come from `ast` and are excluded; comments are not
# STRING tokens at all. F-string SQL fragments (line 394) tokenize as
# FSTRING_MIDDLE in 3.12+, hence that type is included.
_doc_span: set[int] = set()
for _n in ast.walk(ast.parse(src_text)):
    if isinstance(_n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                       ast.ClassDef)):
        _b = getattr(_n, "body", [])
        if _b and isinstance(_b[0], ast.Expr) \
                and isinstance(_b[0].value, ast.Constant) \
                and isinstance(_b[0].value.value, str):
            _d = _b[0].value
            _doc_span.update(range(_d.lineno, (_d.end_lineno or _d.lineno) + 1))
_STR_TYPES = {tokenize.STRING}
if hasattr(tokenize, "FSTRING_MIDDLE"):
    _STR_TYPES.add(tokenize.FSTRING_MIDDLE)
_literals = [(tok.start[0], tok.string)
             for tok in tokenize.generate_tokens(io.StringIO(src_text).readline)
             if tok.type in _STR_TYPES and tok.start[0] not in _doc_span]
check("A:update-statement-lines-3",
      [ln for ln, s in _literals if "UPDATE " in s] == [355, 361, 394],
      str([ln for ln, s in _literals if "UPDATE " in s]))
check("A:select-statement-lines-2",
      [ln for ln, s in _literals if "SELECT " in s] == [371, 408],
      str([ln for ln, s in _literals if "SELECT " in s]))
check("A:update-mention-4-is-comment",
      [i + 1 for i, l in enumerate(src_lines) if "UPDATE " in l]
      == [355, 361, 394, 604] and src_lines[603].lstrip().startswith("#"),
      src_lines[603].strip()[:70])
check("A:select-mention-3-is-docstring",
      [i + 1 for i, l in enumerate(src_lines) if "SELECT " in l]
      == [371, 404, 408] and "Read-only: SELECT only" in src_lines[403],
      src_lines[403].strip()[:70])

# deployed copies are byte-identical to the repo ones (re-measured, not assumed)
check("A:bot-src-identical",
      hashlib.md5(BOT_SRC.read_bytes()).hexdigest()
      == hashlib.md5(SRC.read_bytes()).hexdigest(), "")
check("A:bot-test-identical",
      hashlib.md5(BOT_TEST.read_bytes()).hexdigest()
      == hashlib.md5(CONTRACT.read_bytes()).hexdigest(), "")
check("A:bot-docs-identical",
      hashlib.md5(BOT_DOCS.read_bytes()).hexdigest()
      == hashlib.md5(DOCS.read_bytes()).hexdigest(), "")

# ── Section B: finding 1 — safety ─────────────────────────────────────────
pulls = rd.pull_listing_payload()
relist_blanket = rd.relist_payload([])
relist_scoped = rd.relist_payload(["a", "b", "c"])
verify = rd.verify_pull_payload()
_MUT = ("INSERT", "DELETE", "DROP", "ALTER", "REPLACE")

for label, payload in (("pull", pulls), ("relist-blanket", relist_blanket),
                       ("relist-scoped", relist_scoped), ("verify", verify)):
    check(f"B:{label}-names-models", "models" in payload, payload[:60])
    check(f"B:{label}-no-providers", "upstream_providers" not in payload, "")
    has_mut = any(kw in payload for kw in _MUT)
    check(f"B:{label}-no-other-dml", not has_mut, "")
check("B:verify-read-only", "UPDATE" not in verify, "")
check("B:pull-one-update", pulls.count("UPDATE") == 1, str(pulls.count("UPDATE")))
check("B:relist-scoped-one-update", relist_scoped.count("UPDATE") == 1, "")
check("B:relist-blanket-one-update", relist_blanket.count("UPDATE") == 1, "")

# ssh argv shaping (hermetic, no network)
argv = rd.build_ssh_docker_cmd("debian@host", "routstr-public", pulls)
check("B:ssh-argv-len3", isinstance(argv, list) and len(argv) == 3, str(len(argv)))
check("B:ssh-argv0-1", argv[0] == "ssh" and argv[1] == "debian@host", str(argv[:2]))
remote_tokens = shlex.split(argv[2])
check("B:ssh-remote-decompose",
      remote_tokens[:3] == ["docker", "exec", "routstr-public"]
      and remote_tokens[3:5] == ["python3", "-c"], str(remote_tokens[:5]))
hostile = rd.build_ssh_docker_cmd("debian@host", "evil'; rm -rf / #", "print(1)")
htok = shlex.split(hostile[2])
check("B:hostile-round-trips",
      "evil'; rm -rf / #" in htok and htok[3] == "python3",
      str(htok))
hostile_host = rd.build_ssh_docker_cmd("-oProxyCommand=sh -c id", "c", "print(1)")
check("B:hostile-target-is-one-argv-element",
      hostile_host[1] == "-oProxyCommand=sh -c id" and len(hostile_host) == 3,
      str(hostile_host[:2]))
check("B:no-shell-true", "shell=True" not in src_text, "")
check("B:subprocess-run-2-sites", src_text.count("subprocess.run(") == 2, "")
check("B:no-target-validation",
      not re.search(r"ssh_target\s*(?:not\s+in|in\s*\(|\.startswith)", src_text), "")

# semantic: execute the REAL payloads against a live two-table node
db = SCRATCH / "keys.db"
con = sqlite3.connect(str(db))
con.execute("CREATE TABLE models (name TEXT, enabled INTEGER, weight INTEGER)")
con.execute("CREATE TABLE upstream_providers (name TEXT, enabled INTEGER, weight INTEGER)")
con.executemany("INSERT INTO models VALUES (?,?,?)",
                [("routstr-a", 1, 10), ("routstr-b", 1, 20), ("operator-off", 0, 5)])
con.executemany("INSERT INTO upstream_providers VALUES (?,?,?)",
                [("routstr", 1, 100), ("other", 1, 50)])
con.commit()
con.close()
ladder = SCRATCH / "t470_ladder.json"
ladder.write_text(json.dumps({"routstr": {"enabled": True}, "ladder": [1, 2]}))
ladder_before = ladder.read_bytes()
prov_before = list(sqlite3.connect(str(db)).execute(
    "SELECT name, enabled, weight FROM upstream_providers"))


def exec_payload(payload: str) -> dict:
    code = payload.replace("/app/data/keys.db", str(db))
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        exec(compile(code, "<payload>", "exec"), {})
    return json.loads(buf.getvalue().strip().splitlines()[-1])


r_pull = exec_payload(pulls)
check("B:semantic-pull-captures-names",
      set(r_pull.get("pulled", [])) == {"routstr-a", "routstr-b"}, str(r_pull))
enabled_now = sqlite3.connect(str(db)).execute(
    "SELECT COUNT(*) FROM models WHERE enabled=1").fetchone()[0]
check("B:semantic-pull-disabled-all", enabled_now == 0, str(enabled_now))
r_ver = exec_payload(verify)
check("B:semantic-verify-count0", r_ver.get("count") == 0, str(r_ver))
r_rel = exec_payload(rd.relist_payload(r_pull["pulled"]))
check("B:semantic-relist-restores-2", r_rel.get("restored") == 2, str(r_rel))
prov_after = list(sqlite3.connect(str(db)).execute(
    "SELECT name, enabled, weight FROM upstream_providers"))
check("B:semantic-providers-unchanged", prov_after == prov_before, "")
check("B:semantic-ladder-identical", ladder.read_bytes() == ladder_before, "")
routstr_candidate = sqlite3.connect(str(db)).execute(
    "SELECT enabled FROM upstream_providers WHERE name='routstr'").fetchone()[0]
check("B:semantic-routstr-still-candidate", routstr_candidate == 1, "")
off = sqlite3.connect(str(db)).execute(
    "SELECT enabled FROM models WHERE name='operator-off'").fetchone()[0]
check("B:semantic-operator-row-stays-off", off == 0, str(off))

# ── Section C: finding 2 — confirmation ───────────────────────────────────
CALLS: list[str] = []


class FakeBackend:
    pull_res = {"ok": True, "pulled": ["a", "b", "c"]}
    verify_res = {"ok": True, "count": 0}
    relist_res = {"ok": True}

    def __init__(self, *a, **k):
        pass

    def pull(self, dry_run=False, deadline=None):
        CALLS.append("pull")
        return dict(FakeBackend.pull_res)

    def verify(self, dry_run=False, deadline=None):
        CALLS.append("verify")
        return dict(FakeBackend.verify_res)

    def relist(self, names=None, dry_run=False, deadline=None):
        CALLS.append("relist")
        return dict(FakeBackend.relist_res)


rd._SshBackend = FakeBackend  # type: ignore[assignment]

NO_OVERRIDE = SCRATCH / "no-override"


def run_main(args: list[str]) -> tuple[int, dict]:
    CALLS.clear()
    buf = io.StringIO()
    full = list(args)
    if "--override" not in full:
        full += ["--override", str(NO_OVERRIDE)]
    with contextlib.redirect_stdout(buf):
        rc = rd.main(full)
    return rc, json.loads(buf.getvalue())


st = SCRATCH / "state.json"
st.write_text(json.dumps({}))
FakeBackend.pull_res = {"ok": True, "pulled": ["a", "b", "c"]}
FakeBackend.verify_res = {"ok": True, "count": 0}
rc, out = run_main(["--delist", "--state", str(st)])
check("C:happy-rc0", rc == 0, str(rc))
check("C:happy-action-delist", out.get("action") == "delist", out.get("action"))
check("C:happy-confirmed", out.get("confirmed") is True, str(out.get("confirmed")))
check("C:happy-verified-count0", out.get("verified_count") == 0, "")
check("C:happy-kinds", CALLS == ["pull", "verify"], str(CALLS))
durable = json.loads(st.read_text())
check("C:happy-durable-delisted", durable.get("delisted") is True, "")
check("C:happy-records-names", durable.get("pulled_models") == ["a", "b", "c"],
      str(durable.get("pulled_models")))

# lying pull: self-reports ok, re-fetch still sees advertised models
st.write_text(json.dumps({}))
FakeBackend.pull_res = {"ok": True, "pulled": []}
FakeBackend.verify_res = {"ok": True, "count": 3}
rc, out = run_main(["--delist", "--state", str(st)])
check("C:lying-rc1", rc == 1, str(rc))
check("C:lying-action", out.get("action") == "delist_failed", out.get("action"))
check("C:lying-kinds", CALLS == ["pull", "verify", "pull", "verify"], str(CALLS))
check("C:lying-no-flag", json.loads(st.read_text()).get("delisted") is False, "")
check("C:lying-breaker-tick",
      json.loads(st.read_text()).get("consecutive_failures") == 1, "")

# a verify round-trip that ITSELF fails is also a failed attempt
st.write_text(json.dumps({}))
FakeBackend.pull_res = {"ok": True, "pulled": ["a"]}
FakeBackend.verify_res = {"ok": False, "count": None}
rc, out = run_main(["--delist", "--state", str(st)])
check("C:verify-fail-rc1", rc == 1, str(rc))
check("C:verify-fail-action", out.get("action") == "delist_failed", out.get("action"))
check("C:verify-fail-no-flag", json.loads(st.read_text()).get("delisted") is False, "")

# relist: NO symmetric re-fetch (the residual MEDIUM)
st.write_text(json.dumps({"pulled_models": ["a", "b", "c"]}))
FakeBackend.relist_res = {"ok": True}
rc, out = run_main(["--relist", "--state", str(st)])
check("C:relist-rc0", rc == 0, str(rc))
check("C:relist-no-verify-roundtrip", CALLS == ["relist"], str(CALLS))
check("C:relist-gated-on-selfreport", out.get("action") == "relist", out.get("action"))
stt = json.loads(st.read_text())
check("C:relist-clears-flag", stt.get("delisted") is False, "")
check("C:relist-pops-names", "pulled_models" not in stt, str(stt.get("pulled_models")))

# no captured names -> relist REFUSED before any remote call
st.write_text(json.dumps({"delisted": True}))
FakeBackend.relist_res = {"ok": True}
rc, out = run_main(["--relist", "--state", str(st)])
check("C:relist-refused-rc1", rc == 1, str(rc))
check("C:relist-refused-action",
      out.get("action") == "relist_refused", out.get("action"))
check("C:relist-refused-no-remote", CALLS == [], str(CALLS))

# --relist-any executes the blanket relist (operator opt-in)
st.write_text(json.dumps({"delisted": True}))
rc, out = run_main(["--relist", "--relist-any", "--state", str(st)])
check("C:relist-any-rc0", rc == 0, str(rc))
check("C:relist-any-remote", CALLS == ["relist"], str(CALLS))

# ── Section D: finding 3 — fail-safe ──────────────────────────────────────
f = SCRATCH / "preds.json"
f.write_text(json.dumps([{"key": "zai", "window": "1h", "exhausts_in_hours": 11.0}]))
T = os.path.getmtime(f)
check("D:stale-fresh-false", rd.feed_is_stale(f, now=T) is False, "")
check("D:stale-boundary-inclusive-false",
      rd.feed_is_stale(f, now=T + 1800) is False, "exact 1800 must be fresh")
check("D:stale-1801-true", rd.feed_is_stale(f, now=T + 1801) is True, "")
check("D:stale-future-mtime-true", rd.feed_is_stale(f, now=T - 60) is True, "")
check("D:stale-missing-path-true",
      rd.feed_is_stale(SCRATCH / "nope.json") is True, "")

g = SCRATCH / "garbage.json"
g.write_text("{ not json at all ][")
check("D:garbage-read-preds-empty", rd._read_preds(str(g)) == [], "")
check("D:garbage-none-empty", rd._read_preds(None) == [], "")
d = SCRATCH / "dict.json"
d.write_text(json.dumps({"key": "zai"}))
check("D:non-list-json-empty", rd._read_preds(str(d)) == [], "")
mixed = SCRATCH / "mixed.json"
mixed.write_text(json.dumps([{"key": "zai"}, "junk", 42]))
check("D:garbage-drops-nondict", rd._read_preds(str(mixed)) == [{"key": "zai"}], "")

# empty preds never clobber the stored baseline / stored names (pure helper)
check("D:update-state-empty-keeps-snapshot",
      rd.update_state({"snapshot": {"zai\x1f1h": 12.0}}, ts=1, preds=[],
                      delisted=False).get("snapshot") == {"zai\x1f1h": 12.0}, "")
check("D:update-state-nonempty-replaces",
      rd.update_state({"snapshot": {"zai\x1f1h": 12.0}}, ts=1,
                      preds=[{"key": "zai", "window": "1h",
                              "exhausts_in_hours": 11.0}],
                      delisted=False).get("snapshot") == {"zai\x1f1h": 11.0}, "")

# garbage feed -> rc1, preds_error, action none, no remote, baseline intact
st.write_text(json.dumps({"snapshot": {"zai\x1f1h": 12.0}}))
rc, out = run_main(["--state", str(st), "--preds", str(g)])
check("D:garbage-rc1", rc == 1, str(rc))
check("D:garbage-preds-error", out.get("preds_error") is True, "")
check("D:garbage-action-none", out.get("action") == "none", out.get("action"))
check("D:garbage-no-remote", CALLS == [], str(CALLS))
check("D:garbage-baseline-intact",
      json.loads(st.read_text()).get("snapshot") == {"zai\x1f1h": 12.0}, "")

# absent feed: no --preds at all -> quiet, no error, baseline untouched
st.write_text(json.dumps({"snapshot": {"zai\x1f1h": 12.0}}))
rc, out = run_main(["--state", str(st)])
check("D:absent-rc0", rc == 0, str(rc))
check("D:absent-no-error", out.get("preds_error") is False, "")
check("D:absent-action-none", out.get("action") == "none", out.get("action"))
check("D:absent-no-remote", CALLS == [], str(CALLS))

# stale feed with elevated variance -> quiet, no remote, baseline intact
old = SCRATCH / "old.json"
old.write_text(json.dumps([{"key": "zai", "window": "1h",
                            "exhausts_in_hours": 1.0, "uncertainty": 0.99}]))
os.utime(old, (T - 7200, T - 7200))
st.write_text(json.dumps({"snapshot": {"zai\x1f1h": 12.0}}))
rc, out = run_main(["--state", str(st), "--preds", str(old)])
check("D:stale-rc1", rc == 1, str(rc))
check("D:stale-flag", out.get("preds_stale") is True, "")
check("D:stale-action-none", out.get("action") == "none", out.get("action"))
check("D:stale-no-remote", CALLS == [], str(CALLS))
check("D:stale-baseline-intact",
      json.loads(st.read_text()).get("snapshot") == {"zai\x1f1h": 12.0}, "")

# manual override is never gated on freshness
ovr = SCRATCH / "override"
ovr.write_text("x")
FakeBackend.pull_res = {"ok": True, "pulled": ["a"]}
FakeBackend.verify_res = {"ok": True, "count": 0}
rc, out = run_main(["--state", str(st), "--preds", str(old), "--override", str(ovr)])
check("D:manual-not-gated-rc0", rc == 0, str(rc))
check("D:manual-stale-observed", out.get("preds_stale") is True, "")

# MEDIUM: quiet-path dry-run refreshes the baseline and records no last_dry_run
fresh = SCRATCH / "fresh.json"
fresh.write_text(json.dumps([{"key": "zai", "window": "1h", "exhausts_in_hours": 11.0}]))
st.write_text(json.dumps({"snapshot": {"zai\x1f1h": 12.0}}))
rc, out = run_main(["--state", str(st), "--preds", str(fresh), "--dry-run"])
dstate = json.loads(st.read_text())
check("D:quiet-dryrun-rc0", rc == 0, str(rc))
check("D:quiet-dryrun-refreshes-baseline",
      dstate.get("snapshot") == {"zai\x1f1h": 11.0}, str(dstate.get("snapshot")))
check("D:quiet-dryrun-no-last-run", "last_dry_run" not in dstate, "")

# firing dry-run IS pure: records intent, pulls only, no durable flag
st.write_text(json.dumps({}))
rc, out = run_main(["--delist", "--dry-run", "--state", str(st)])
dstate = json.loads(st.read_text())
check("D:firing-dryrun-pull-only", CALLS == ["pull"], str(CALLS))
check("D:firing-dryrun-no-flag", dstate.get("delisted") in (None, False), "")
check("D:firing-dryrun-records-intent", "last_dry_run" in dstate, "")

# unfiltered default fires on a foreign key's spike (LOW a)
spike = SCRATCH / "spike.json"
spike.write_text(json.dumps([{"key": "openrouter", "window": "1h",
                              "exhausts_in_hours": 1.0, "uncertainty": 0.99}]))
st.write_text(json.dumps({}))
rc, out = run_main(["--state", str(st), "--preds", str(spike)])
check("D:unscoped-default-fires", out.get("action") == "delist", out.get("action"))
st.write_text(json.dumps({}))
rc, out = run_main(["--state", str(st), "--preds", str(spike),
                    "--preds-key", "zai"])
check("D:scoped-filter-quiets", out.get("action") == "none", out.get("action"))

# ── Section E: review-record integrity ────────────────────────────────────
doc_text = REVIEW.read_text(encoding="utf-8")
check("E:contract-path-missing", not BOTDOCS_CONTRACT.exists(), str(BOTDOCS_CONTRACT))
check("E:mirror-exists", BOTDOC.is_file(), "")
check("E:exactly-three-findings", doc_text.count("\n## Finding ") == 3,
      str(doc_text.count("\n## Finding ")))
check("E:ordinal-preamble",
      doc_text.splitlines()[0].endswith("seventy-fifth independent offload pass"),
      doc_text.splitlines()[0])
sev = re.findall(r"^severity: \*\*(OK|BLOCKER|HIGH|MEDIUM|LOW)", doc_text, re.M)
check("E:three-severity-tags", len(sev) == 3, str(sev))

# ── report ────────────────────────────────────────────────────────────────
fails = [(n, d) for n, ok, d in RESULTS if not ok]
for n, ok, d in RESULTS:
    if not ok:
        print(f"[FAIL] {n} :: {d}")
print(f"checks: {len(RESULTS)}  PASS: {len(RESULTS) - len(fails)}  FAIL: {len(fails)}")
from collections import Counter
_sec = Counter(n.split(":")[0] for n, _, _ in RESULTS)
print("sections:", " ".join(f"{k}={v}" for k, v in sorted(_sec.items())))
transcript = "\n".join(f"{n}={int(ok)}" for n, ok, _ in RESULTS)
print("transcript sha256:", hashlib.sha256(transcript.encode()).hexdigest())
raise SystemExit(0 if not fails else 1)
