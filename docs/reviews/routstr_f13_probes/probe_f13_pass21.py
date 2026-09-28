#!/usr/bin/env python3
"""probe_f13_pass21.py — fresh independent re-verification for the
findings_1_3.md deliverable (routstr dynamic delist), TWENTY-FIRST offload pass.

Hermetic: no network, no ssh spawn, no fsync (patched to a no-op — fsync can
stall indefinitely on this host). Scratch lives under ~/.cache/f13-pass21/tmp,
never /tmp (RAM tmpfs, ENOSPC-prone on this host).

Sections:
  A  citation audit — every file:line the deliverable cites must contain the
     substring it claims lives there (script, main suite, contract suite, docs).
  B  safety — payload scoping: no payload names upstream_providers; the three
     UPDATEs are models-only; scoped relist is parameterized; the remote command
     is a single shlex-quoted argv element; no shell=True.
  C  confirmation — a lying pull is refuted (rc 1, 2 attempts); a confirmed
     delist gates on the re-fetch count==0 (rc 0, delisted true); the relist runs
     NO verify round-trip and pops the scoped names (MEDIUM residual).
  D  fail-safe — feed_is_stale fail-closed incl. inclusive boundary; uncertainty
     type guards; garbage feed never wipes the baseline; stale never triggers;
     manual override never gated on staleness; dry-run on the QUIET path
     refreshes the baseline and records no last_dry_run (MEDIUM residual).
  E  review-record integrity — three `## Finding` sections, each with a
     severity tag; every `path:N` citation in the deliverable is covered by the
     section-A audit; the bot mirror is byte-identical to the repo copy; the
     named-but-absent contract doc is disclosed.

Run: python3 docs/reviews/routstr_f13_probes/probe_f13_pass21.py
Prints a per-check PASS/FAIL tally and a transcript sha256 (run twice; the
digest must be identical and the tally must read N/N PASS).
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
import re
import shlex
import shutil
import sys
import tempfile

REPO = "/home/c03rad0r/repos/merchant-routing"
SRC = os.path.join(REPO, "src", "routstr_delist.py")
MAIN = os.path.join(REPO, "tests", "test_routstr_delist.py")
CONTRACT = os.path.join(REPO, "tests", "test_routstr_delist_contract.py")
DOCS = os.path.join(REPO, "docs", "routstr-delist.md")
DELIV = os.path.join(REPO, "docs", "reviews", "findings_1_3.md")
BOT = os.path.expanduser("~/.hermes/bot")
CACHE = os.path.expanduser("~/.cache/f13-pass21")
SCRATCH = os.path.join(CACHE, "tmp")
shutil.rmtree(CACHE, ignore_errors=True)
os.makedirs(SCRATCH, exist_ok=True)
os.environ["TMPDIR"] = SCRATCH

# ── load the module under review ──────────────────────────────────────────
spec = importlib.util.spec_from_file_location("rd21", SRC)
rd = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(rd)
# durability is not what these probes measure; atomicity (tmp+os.replace) is
rd.os.fsync = lambda fd: None  # type: ignore[assignment]

RESULTS: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    RESULTS.append(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}".rstrip())


def lines_of(path: str) -> list[str]:
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read().split("\n")


def md5_of(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.md5(fh.read()).hexdigest()


SRC_L = lines_of(SRC)
MAIN_L = lines_of(MAIN)
CON_L = lines_of(CONTRACT)
DOC_L = lines_of(DOCS)

AUDITED: list[tuple[str, int]] = []


def cite(name: str, tag: str, path_lines: list[str], lineno: int,
         needle: str) -> None:
    line = path_lines[lineno - 1] if 0 < lineno <= len(path_lines) else "<OOB>"
    AUDITED.append((tag, lineno))
    check(name, needle in line, f"{tag}:{lineno}<-{needle!r}")


# ── Section A: citation audit ─────────────────────────────────────────────
# script — SQL / payload shaping
cite("A1 pull SQL disables advertised models only", "routstr_delist.py", SRC_L, 355,
     "UPDATE models SET enabled=0 WHERE enabled=1")
cite("A2 blanket relist SQL (legacy fallback)", "routstr_delist.py", SRC_L, 361,
     "UPDATE models SET enabled=1;")
cite("A3 scoped relist SQL parameterized", "routstr_delist.py", SRC_L, 394,
     "UPDATE models SET enabled=1 WHERE name IN")
cite("A4 verify SQL is read-only COUNT", "routstr_delist.py", SRC_L, 408,
     "SELECT COUNT(*) FROM models WHERE enabled=1")
cite("A5 pull payload captures advertised names", "routstr_delist.py", SRC_L, 371,
     "SELECT name FROM models WHERE enabled=1")
cite("A6 db path in pull payload", "routstr_delist.py", SRC_L, 370,
     "/app/data/keys.db")
cite("A7 db path in blanket relist payload", "routstr_delist.py", SRC_L, 385,
     "/app/data/keys.db")
cite("A8 db path in scoped relist payload", "routstr_delist.py", SRC_L, 393,
     "/app/data/keys.db")
cite("A9 db path in verify payload", "routstr_delist.py", SRC_L, 407,
     "/app/data/keys.db")
# script — the three upstream_providers mentions are docstring-only
cite("A10 upstream_providers mention 1 (module docstring)",
     "routstr_delist.py", SRC_L, 35, "upstream_providers")
cite("A11 upstream_providers mention 2 (pull_listing_sql docstring)",
     "routstr_delist.py", SRC_L, 352, "upstream_providers")
cite("A12 upstream_providers mention 3 (_SshBackend docstring)",
     "routstr_delist.py", SRC_L, 771, "upstream_providers")
# script — ssh command shaping
cite("A13 build_ssh_docker_cmd signature", "routstr_delist.py", SRC_L, 414,
     "def build_ssh_docker_cmd")
cite("A14 container shlex-quoted", "routstr_delist.py", SRC_L, 423,
     "shlex.quote(container)")
cite("A15 payload shlex-quoted", "routstr_delist.py", SRC_L, 424,
     "shlex.quote(payload)")
cite("A16 argv is 3 elements", "routstr_delist.py", SRC_L, 425,
     '["ssh", ssh_target, remote]')
cite("A17 nak subprocess.run", "routstr_delist.py", SRC_L, 459, "subprocess.run(argv")
cite("A18 ssh subprocess.run", "routstr_delist.py", SRC_L, 808, "subprocess.run(cmd")
# script — relist refusal
cite("A19 blanket relist refusal block", "routstr_delist.py", SRC_L, 600,
     "if args.relist:")
cite("A20 refusal action tag", "routstr_delist.py", SRC_L, 606,
     '"action": "relist_refused"')
cite("A21 relist-any opt-in flag", "routstr_delist.py", SRC_L, 526,
     "--relist-any")
cite("A22 ssh-target / container args", "routstr_delist.py", SRC_L, 536,
     "--ssh-target")
cite("A23 container arg", "routstr_delist.py", SRC_L, 537, "--container")
# script — confirmation
cite("A24 verify payload builder", "routstr_delist.py", SRC_L, 400,
     "def verify_pull_payload")
cite("A25 backend.verify method", "routstr_delist.py", SRC_L, 790,
     "def verify(self")
cite("A26 verify invoked in attempt loop", "routstr_delist.py", SRC_L, 682,
     "vres = backend.verify")
cite("A27 success gated on count==0", "routstr_delist.py", SRC_L, 683,
     'vres.get("ok") is True and vres.get("count") == 0')
cite("A28 confirmed flag set", "routstr_delist.py", SRC_L, 687,
     "confirmed = True")
cite("A29 refuted self-report forced ok=False", "routstr_delist.py", SRC_L, 692,
     'res["ok"] = False')
cite("A30 MAX_PULL_ATTEMPTS constant", "routstr_delist.py", SRC_L, 75,
     "MAX_PULL_ATTEMPTS = 2")
cite("A31 failure branch keeps delisted false", "routstr_delist.py", SRC_L, 726,
     'state["delisted"] = False')
cite("A32 failure branch is rc 1/3", "routstr_delist.py", SRC_L, 739,
     "return 3 if newly_blocked else 1")
cite("A33 success writes delisted=true", "routstr_delist.py", SRC_L, 747,
     "delisted=True")
cite("A34 success rc 0", "routstr_delist.py", SRC_L, 764, "return 0")
cite("A35 relist success gated on self-report only", "routstr_delist.py", SRC_L, 626,
     'if not res.get("ok"):')
cite("A36 relist pops scoped names", "routstr_delist.py", SRC_L, 635,
     'state.pop("pulled_models", None)')
cite("A37 dry-run sets confirmed without remote verify",
     "routstr_delist.py", SRC_L, 680, "confirmed = True")
cite("A38 _run returncode+ok gate", "routstr_delist.py", SRC_L, 822,
     'res["ok"] = proc.returncode == 0 and data.get("ok") is True')
cite("A39 _run last-line JSON parse", "routstr_delist.py", SRC_L, 814,
     "json.loads(out.splitlines()[-1])")
# script — fail-safe
cite("A40 STALENESS_S = 1800", "routstr_delist.py", SRC_L, 78, "STALENESS_S = 1800")
cite("A41 feed_is_stale signature (injectable now)", "routstr_delist.py", SRC_L, 485,
     "def feed_is_stale")
cite("A42 feed_is_stale inclusive boundary", "routstr_delist.py", SRC_L, 494,
     "return not (0 <= age <= max_age_s)")
cite("A43 feed_is_stale fails closed on OSError", "routstr_delist.py", SRC_L, 495,
     "except OSError:")
cite("A44 accel needs both sides non-empty", "routstr_delist.py", SRC_L, 107,
     "if not preds_now or not preds_prev:")
cite("A45 variance needs non-empty preds", "routstr_delist.py", SRC_L, 143,
     "if not preds:")
cite("A46 uncertainty isinstance+bool guard", "routstr_delist.py", SRC_L, 152,
     "not isinstance(unc, (int, float)) or isinstance(unc, bool)")
cite("A47 _hours type guard", "routstr_delist.py", SRC_L, 193, "def _hours")
cite("A48 _hours isinstance check", "routstr_delist.py", SRC_L, 196,
     "return h if isinstance(h, (int, float)) else None")
cite("A49 _read_preds never raises", "routstr_delist.py", SRC_L, 481,
     "except Exception:")
cite("A50 _read_preds drops non-dicts", "routstr_delist.py", SRC_L, 479,
     "return [d for d in data if isinstance(d, dict)]")
cite("A51 update_state refreshes baseline only when preds",
     "routstr_delist.py", SRC_L, 261, "if preds:")
cite("A52 preds_error computed", "routstr_delist.py", SRC_L, 585,
     "preds_error = bool(args.preds) and not raw_preds")
cite("A53 preds_stale wiring", "routstr_delist.py", SRC_L, 589,
     "preds_stale = bool(args.preds)")
cite("A54 stale zeroes preds before evaluation", "routstr_delist.py", SRC_L, 591,
     "if preds_stale:")
cite("A55 preds-key scoping of the evaluated list", "routstr_delist.py", SRC_L, 597,
     'p.get("key") == args.preds_key')
cite("A56 evaluate_triggers calls variance without key",
     "routstr_delist.py", SRC_L, 303,
     "var = variance_jumped(preds_now, threshold=variance_threshold)")
cite("A57 variance_jumped has a key param it never gets",
     "routstr_delist.py", SRC_L, 132, "def variance_jumped")
cite("A58 variance_jumped key filter branch", "routstr_delist.py", SRC_L, 147,
     'if key is not None and p.get("key") != key:')
cite("A59 override computed before freshness", "routstr_delist.py", SRC_L, 580,
     "override = args.manual or manual_override(args.override)")
cite("A60 manual_override is presence-based", "routstr_delist.py", SRC_L, 172,
     "return os.path.isfile(override_path)")
cite("A61 fire = args.delist or decision", "routstr_delist.py", SRC_L, 649,
     'fire = args.delist or dec["fire"]')
cite("A62 decision fire = accel|var|override", "routstr_delist.py", SRC_L, 317,
     'bool(accel or var or override)')
cite("A63 quiet branch has NO dry-run guard", "routstr_delist.py", SRC_L, 651,
     "if not fire:")
cite("A64 quiet branch refreshes baseline + saves", "routstr_delist.py", SRC_L, 652,
     "state = update_state(state, ts=time.time(), preds=preds")
cite("A65 quiet branch rc 1 when err/stale", "routstr_delist.py", SRC_L, 660,
     "return 1 if (preds_error or preds_stale) else 0")
cite("A66 preds_stale surfaced on the quiet branch",
     "routstr_delist.py", SRC_L, 657, '"preds_stale": preds_stale')
cite("A67 preds_stale surfaced on the dry-run branch",
     "routstr_delist.py", SRC_L, 714, '"preds_stale": preds_stale')
cite("A68 preds_stale surfaced on the failure branch",
     "routstr_delist.py", SRC_L, 735, '"preds_stale": preds_stale')
cite("A69 preds_stale surfaced on the success branch",
     "routstr_delist.py", SRC_L, 762, '"preds_stale": preds_stale')
cite("A70 breaker refuse-all block", "routstr_delist.py", SRC_L, 569, "if blocked:")
cite("A71 breaker exit 3", "routstr_delist.py", SRC_L, 578, "return 3")
cite("A72 breaker increments + sets blocked", "routstr_delist.py", SRC_L, 730,
     "newly_blocked = fails >= BREAKER_THRESHOLD")
cite("A73 --unblock clears breaker", "routstr_delist.py", SRC_L, 561,
     "if args.unblock and blocked:")
cite("A74 dry-run branch is intent-only", "routstr_delist.py", SRC_L, 699,
     "if args.dry_run:")
# script — save_state call sites (return value ignored at all 8)
for i, ln in enumerate((565, 622, 629, 638, 654, 710, 732, 752), start=1):
    cite(f"A75.{i} save_state call site ignored", "routstr_delist.py", SRC_L, ln,
         "save_state(args.state, state)")
# main suite pins
cite("A76 main: pull SQL models-only", "tests", MAIN_L, 303,
     "def test_pull_sql_touches_only_models_listing")
cite("A77 main: relist SQL models-only", "tests", MAIN_L, 311,
     "def test_relist_sql_touches_only_models_listing")
cite("A78 main: verify payload read-only", "tests", MAIN_L, 336,
     "def test_verify_payload_scoped_to_models_listing")
cite("A79 main: ssh cmd single shlex-safe", "tests", MAIN_L, 345,
     "def test_ssh_cmd_is_single_shlex_safe_remote_command")
cite("A80 main: verify gates success", "tests", MAIN_L, 567,
     "def test_verify_gates_success")
cite("A81 main: verify failure = attempt failure", "tests", MAIN_L, 603,
     "def test_verify_failure_is_attempt_failure")
cite("A82 main: non-numeric uncertainty ignored", "tests", MAIN_L, 146,
     "def test_non_numeric_uncertainty_ignored_not_crash")
cite("A83 main: first run never fires on acceleration", "tests", MAIN_L, 176,
     "def test_first_run_never_fires_on_acceleration")
cite("A84 main: empty preds preserves baseline", "tests", MAIN_L, 243,
     "def test_update_state_empty_preds_preserves_baseline")
cite("A85 main: unreadable feed is error not quiet", "tests", MAIN_L, 547,
     "def test_unreadable_preds_feed_is_error_not_quiet")
cite("A86 main: stale feed never triggers", "tests", MAIN_L, 937,
     "def test_stale_feed_never_triggers")
cite("A87 main: stale + override exits 0", "tests", MAIN_L, 980,
     "def test_stale_feed_exit_zero_when_override_fires")
cite("A88 main: stale baseline not consumed", "tests", MAIN_L, 995,
     "def test_stale_feed_baseline_not_consumed")
cite("A89 main: relist refuses blanket", "tests", MAIN_L, 1039,
     "def test_relist_refuses_blanket_without_opt_in")
cite("A90 main: relist-any executes blanket", "tests", MAIN_L, 1056,
     "def test_relist_any_executes_blanket")
cite("A91 main: dry-run failure intent-only", "tests", MAIN_L, 514,
     "def test_dry_run_failure_is_intent_only")
cite("A92 main: last-line JSON + ok gate", "tests", MAIN_L, 1107,
     "def test_pull_parses_last_line_json_and_gates_on_ok")
# contract suite pins
cite("A93 contract: ladder artifact built", "contract", CON_L, 108, "ladder_artifact")
cite("A94 contract: fake node models+providers tables", "contract", CON_L, 129,
     "CREATE TABLE upstream_providers")
cite("A95 contract: provider rows read", "contract", CON_L, 160,
     "SELECT name, enabled, weight FROM upstream_providers")
cite("A96 contract: Case 6 semantic guard header", "contract", CON_L, 467,
     "Case 6: SEMANTIC GUARD")
cite("A97 contract: ladder guard class", "contract", CON_L, 468,
     "class TestSemanticGuardLadderUntouched")
cite("A98 contract: ladder byte-identical assert", "contract", CON_L, 480,
     "assert rig.node.ladder_bytes() == ladder_before")
cite("A99 contract: no executed payload names the table", "contract", CON_L, 483,
     'assert "upstream_providers" not in payload')
cite("A100 contract: routstr still enabled candidate", "contract", CON_L, 487,
     'assert any(name == "routstr" and enabled == 1')
cite("A101 contract: scoped relist ladder byte-identical", "contract", CON_L, 504,
     "assert rig.node.ladder_bytes() == ladder_before")
cite("A102 contract: first run quiet", "contract", CON_L, 308,
     "def test_first_run_without_baseline_is_quiet")
cite("A103 contract: unverified pull is a failed delist", "contract", CON_L, 346,
     "def test_unverified_pull_is_a_failed_delist")
cite("A104 contract: manual override never gated on staleness", "contract", CON_L, 427,
     "def test_manual_override_is_never_gated_on_feed_staleness")
# docs pins
cite("A105 docs: no-blanket-relist rule", "docs", DOC_L, 29, "No blanket relist")
cite("A106 docs: re-delist merges", "docs", DOC_L, 33, "Re-delist merges")
cite("A107 docs: preds-key scopes evaluation", "docs", DOC_L, 54, "--preds-key")
cite("A108 docs: freshness guard", "docs", DOC_L, 56, "Freshness guard")
cite("A109 docs: override never gated on freshness", "docs", DOC_L, 60,
     "never gated on freshness")
cite("A110 docs: re-fetch confirmation", "docs", DOC_L, 69,
     "Re-fetch confirmation")
cite("A111 docs: dry-run intent-only", "docs", DOC_L, 87,
     "Dry-run is intent-only")
cite("A112 contract: routstr candidate comment", "contract", CON_L, 486,
     "the routstr provider is still a routable ladder candidate")
# script — start lines of ranges the deliverable cites
cite("A113 manual_override def", "routstr_delist.py", SRC_L, 164,
     "def manual_override(override_path)")
cite("A114 preds-key filter block", "routstr_delist.py", SRC_L, 594,
     "if args.preds_key:")
cite("A115 relist success state update", "routstr_delist.py", SRC_L, 633,
     "state = update_state(state, ts=time.time(), preds=preds,")
cite("A116 attempt loop start", "routstr_delist.py", SRC_L, 671,
     "while attempts < MAX_PULL_ATTEMPTS:")
cite("A117 dry-run confirmed branch inside loop", "routstr_delist.py", SRC_L, 679,
     "if args.dry_run:")
cite("A118 refusal branch copies res", "routstr_delist.py", SRC_L, 691,
     "res = dict(res)")
cite("A119 failure branch start", "routstr_delist.py", SRC_L, 719,
     "if not confirmed:")
cite("A120 failure counter increment", "routstr_delist.py", SRC_L, 724,
     "fails += 1")
cite("A121 _run def", "routstr_delist.py", SRC_L, 795, "def _run(self, payload")
cite("A122 _run stdout parse init", "routstr_delist.py", SRC_L, 810, "data = {}")

# ── Section B: safety ─────────────────────────────────────────────────────
PAYLOADS = {
    "pull": rd.pull_listing_payload(),
    "verify": rd.verify_pull_payload(),
    "relist_scoped": rd.relist_payload(["gpt-4o", "llama-3"]),
    "relist_blanket": rd.relist_payload([]),
}
for nm, pl in PAYLOADS.items():
    check(f"B1 payload[{nm}] does NOT name upstream_providers",
          "upstream_providers" not in pl, pl[:48])
    check(f"B2 payload[{nm}] targets the models table", "models" in pl)
    check(f"B3 payload[{nm}] has no destructive DDL/DML",
          not any(v in pl.upper() for v in
                  ("INSERT ", "DELETE ", "DROP ", "ALTER ", "REPLACE INTO")))
check("B4 pull SQL is exactly models-only enabled=0",
      rd.pull_listing_sql().strip() == "UPDATE models SET enabled=0 WHERE enabled=1;")
check("B5 blanket relist SQL is exactly models-only enabled=1",
      rd.relist_sql().strip() == "UPDATE models SET enabled=1;")
check("B6 scoped relist SQL uses placeholders (no interpolation)",
      "WHERE name IN (" in rd.relist_payload(["a", "b"])
      and "?,?" in rd.relist_payload(["a", "b"]))
check("B7 verify payload contains no UPDATE",
      "UPDATE" not in rd.verify_pull_payload())
cmd = rd.build_ssh_docker_cmd("debian@host", "ctr name; rm -rf /", "p=1")
check("B8 remote argv is 3 elements (one remote cmd)", len(cmd) == 3, str(len(cmd)))
check("B9 remote cmd round-trips via shlex.split",
      shlex.split(cmd[2]) == ["docker", "exec", "ctr name; rm -rf /", "python3",
                              "-c", "p=1"])
check("B10 no shell=True anywhere",
      "shell=True" not in "\n".join(SRC_L))
check("B11 exactly 2 subprocess.run sites",
      sum(1 for x in SRC_L if "subprocess.run(" in x) == 2)
check("B12 six models-SQL lines in source (5 statements + 1 comment)",
      sum(1 for x in SRC_L if "models" in x and ("UPDATE" in x or "SELECT" in x)) == 6)
check("B13 upstream_providers occurs exactly 3x in source, all in docstrings",
      "\n".join(SRC_L).count("upstream_providers") == 3)


# ── stubs driving main() (no ssh spawn) ───────────────────────────────────
class FakeBackend:
    def __init__(self, ssh_target, container):
        self.kinds: list[str] = []
        self.verify_count = 99
        self.pull_lands = True
        self.relist_lands = True

    def _res(self, action):
        self.kinds.append(action)
        if action == "verify":
            return {"ok": True, "count": self.verify_count, "action": action}
        if action == "pull":
            return {"ok": self.pull_lands, "pulled": ["gpt-4o"], "action": action}
        if action == "relist":
            return {"ok": self.relist_lands, "action": action, "restored": 1}
        return {"ok": True, "action": action}

    def pull(self, dry_run=False, deadline=None):
        return self._res("pull")

    def verify(self, dry_run=False, deadline=None):
        return self._res("verify")

    def relist(self, names=None, dry_run=False, deadline=None):
        return self._res("relist")


def run_main(backend, args):
    rd._SshBackend = lambda t, c: backend  # type: ignore[assignment]
    buf = io.StringIO()
    real = sys.stdout
    sys.stdout = buf
    try:
        rc = rd.main(args)
    finally:
        sys.stdout = real
    try:
        out = json.loads(buf.getvalue())
    except Exception:
        out = {"_raw": buf.getvalue()}
    out["_rc"] = rc
    return out


def write_state(path, obj):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh)


def write_preds(path, preds, age_s=0.0):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(preds, fh)
    if age_s:
        t = os.path.getmtime(path) - age_s
        os.utime(path, (t, t))


def read_state(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def new_paths(tag):
    d = tempfile.mkdtemp(dir=SCRATCH, prefix=tag + "-")
    return os.path.join(d, "state.json"), os.path.join(d, "preds.json")


# ── Section C: confirmation ───────────────────────────────────────────────
st, pf = new_paths("C1")
write_preds(pf, [{"key": "zai", "window": "1h", "exhausts_in_hours": 10.0}])
write_state(st, {"snapshot": {"zai\x1f1h": 20.0}, "delisted": False})
b = FakeBackend("h", "c")
b.verify_count = 1
out = run_main(b, ["--state", st, "--preds", pf, "--manual"])
check("C1 lying pull refuted -> rc1", out["_rc"] == 1, str(out.get("_rc")))
check("C1 kinds == pull,verify,pull,verify",
      b.kinds == ["pull", "verify", "pull", "verify"], str(b.kinds))
check("C1 delisted stays false", read_state(st)["delisted"] is False)
check("C1 consecutive_failures == 1", read_state(st)["consecutive_failures"] == 1)

st, pf = new_paths("C2")
write_preds(pf, [{"key": "zai", "window": "1h", "exhausts_in_hours": 10.0}])
write_state(st, {"snapshot": {"zai\x1f1h": 20.0}, "delisted": False})
b = FakeBackend("h", "c")
b.verify_count = 0
out = run_main(b, ["--state", st, "--preds", pf, "--manual"])
check("C2 confirmed -> rc0", out["_rc"] == 0, str(out.get("_rc")))
check("C2 kinds == pull,verify", b.kinds == ["pull", "verify"], str(b.kinds))
s = read_state(st)
check("C2 delisted true", s["delisted"] is True)
check("C2 pulled_models captured", s.get("pulled_models") == ["gpt-4o"])
check("C2 verified_count surfaced 0", out.get("verified_count") == 0)

st, pf = new_paths("C3")
write_state(st, {"delisted": True, "pulled_models": ["gpt-4o"],
                 "snapshot": {"zai\x1f1h": 20.0}})
b = FakeBackend("h", "c")
out = run_main(b, ["--state", st, "--preds", pf, "--relist"])
check("C3 relist kinds == [relist] only", b.kinds == ["relist"], str(b.kinds))
check("C3 relist rc0 on self-report", out["_rc"] == 0, str(out.get("_rc")))
s = read_state(st)
check("C3 relist flips delisted false on self-report alone", s["delisted"] is False)
check("C3 relist destroys the scoped name set", "pulled_models" not in s)

st, pf = new_paths("C4")
write_state(st, {"delisted": True, "pulled_models": ["gpt-4o"]})
b = FakeBackend("h", "c")
b.relist_lands = True
out = run_main(b, ["--state", st, "--preds", pf, "--relist"])
check("C4 no verify kind executed on the relist path", "verify" not in b.kinds,
      str(b.kinds))

# ── Section D: fail-safe ──────────────────────────────────────────────────
f = os.path.join(SCRATCH, "feed.json")
write_preds(f, [{"key": "zai", "window": "1h", "exhausts_in_hours": 5.0}])
tm = os.path.getmtime(f)
check("D1 fresh feed is not stale", rd.feed_is_stale(f, now=tm + 10) is False)
check("D2 exact boundary 1800s is FRESH (inclusive)",
      rd.feed_is_stale(f, now=tm + 1800) is False)
check("D3 aged 1801s is stale", rd.feed_is_stale(f, now=tm + 1801) is True)
check("D4 future mtime is stale", rd.feed_is_stale(f, now=tm - 1) is True)
check("D5 missing path is stale",
      rd.feed_is_stale(os.path.join(SCRATCH, "nope.json")) is True)
check("D6 uncertainty string ignored",
      rd.variance_jumped([{"key": "z", "uncertainty": "0.9"}]) == [])
check("D7 uncertainty bool ignored",
      rd.variance_jumped([{"key": "z", "uncertainty": True}]) == [])
check("D8 uncertainty numeric fires",
      len(rd.variance_jumped([{"key": "z", "uncertainty": 0.9}])) == 1)
check("D9 _hours accepts bool (cosmetic LOW)",
      rd._hours({"exhausts_in_hours": True}) is True)
check("D10 no baseline -> acceleration never fires",
      rd.exhaustion_accelerated([{"key": "z", "window": "1h",
                                  "exhausts_in_hours": 1.0}], []) == [])
check("D12 key filter works when supplied",
      rd.variance_jumped([{"key": "openrouter", "uncertainty": 0.95}],
                         key="zai") == [])


def _w(p, s):
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(s)
    return p


check("D13 unparseable feed returns []",
      rd._read_preds(_w(os.path.join(SCRATCH, "bad.json"), "{ nope")) == [])
check("D14 non-dict entries dropped",
      rd._read_preds(_w(os.path.join(SCRATCH, "mix.json"),
                        '[1, {"key": "z"}]')) == [{"key": "z"}])

st, pf = new_paths("D15")
_w(pf, "{ this is not json")
write_state(st, {"snapshot": {"zai\x1f1h": 10.0}, "delisted": False})
b = FakeBackend("h", "c")
out = run_main(b, ["--state", st, "--preds", pf])
check("D15 garbage feed rc1", out["_rc"] == 1, str(out.get("_rc")))
check("D15 preds_error true", out.get("preds_error") is True)
check("D15 baseline preserved", read_state(st)["snapshot"] == {"zai\x1f1h": 10.0})
check("D15 no remote action", b.kinds == [], str(b.kinds))

st, pf = new_paths("D16")
write_preds(pf, [{"key": "zai", "window": "1h", "exhausts_in_hours": 5.0,
                  "uncertainty": 0.99}], age_s=7200)
write_state(st, {"snapshot": {}, "delisted": False})
b = FakeBackend("h", "c")
out = run_main(b, ["--state", st, "--preds", pf])
check("D16 stale -> rc1", out["_rc"] == 1, str(out.get("_rc")))
check("D16 action none", out.get("action") == "none")
check("D16 preds_stale true", out.get("preds_stale") is True)
check("D16 no remote action", b.kinds == [], str(b.kinds))
check("D16 baseline not refreshed by a stale feed",
      read_state(st).get("snapshot") == {})

st, pf = new_paths("D17")
write_preds(pf, [{"key": "zai", "window": "1h", "exhausts_in_hours": 5.0}], age_s=7200)
write_state(st, {"snapshot": {}, "delisted": False})
b = FakeBackend("h", "c")
b.verify_count = 0
out = run_main(b, ["--state", st, "--preds", pf, "--manual"])
check("D17 stale + --manual delists rc0", out["_rc"] == 0, str(out.get("_rc")))
check("D17 action delist", out.get("action") == "delist")

st, pf = new_paths("D18")
write_preds(pf, [{"key": "zai", "window": "1h", "exhausts_in_hours": 11.0}])
write_state(st, {"snapshot": {"zai\x1f1h": 12.0}, "delisted": False})
b = FakeBackend("h", "c")
out = run_main(b, ["--state", st, "--preds", pf, "--dry-run"])
s = read_state(st)
check("D18 dry-run quiet path rc0", out["_rc"] == 0, str(out.get("_rc")))
check("D18 dry-run quiet path REFRESHES baseline (12.0 -> 11.0)",
      s["snapshot"].get("zai\x1f1h") == 11.0, str(s.get("snapshot")))
check("D18 dry-run quiet path records NO last_dry_run",
      "last_dry_run" not in s)

st, pf = new_paths("D19")
write_preds(pf, [{"key": "zai", "window": "1h", "exhausts_in_hours": 10.0}])
write_state(st, {"snapshot": {"zai\x1f1h": 20.0}, "delisted": False})
b = FakeBackend("h", "c")
out = run_main(b, ["--state", st, "--preds", pf, "--manual", "--dry-run"])
s = read_state(st)
check("D19 firing dry-run rc0", out["_rc"] == 0, str(out.get("_rc")))
check("D19 firing dry-run records last_dry_run", "last_dry_run" in s)
check("D19 firing dry-run flips NO durable delist flag",
      s.get("delisted") is False)
check("D19 firing dry-run delegates to backend.pull (dry-run flag forwarded)",
      b.kinds == ["pull"], str(b.kinds))
check("D19 firing dry-run runs NO verify round-trip", "verify" not in b.kinds)

# ── Section E: review-record integrity ────────────────────────────────────
DELIV_TXT = "\n".join(lines_of(DELIV))
check("E1 deliverable has exactly 3 '## Finding' sections",
      len(re.findall(r"^## Finding ", DELIV_TXT, re.M)) == 3,
      str(len(re.findall(r"^## Finding ", DELIV_TXT, re.M))))
check("E2 deliverable has exactly 3 '## ' sections (no strays)",
      len(re.findall(r"^## ", DELIV_TXT, re.M)) == 3,
      str(len(re.findall(r"^## ", DELIV_TXT, re.M))))
findings = re.split(r"^## Finding ", DELIV_TXT, flags=re.M)[1:]
for i, sec in enumerate(findings, start=1):
    check(f"E3.{i} Finding {i} carries a severity tag",
          "severity:" in sec, sec.split("\n")[0][:60])
check("E4 names the twenty-first pass", "twenty-first" in DELIV_TXT.lower())
check("E5 discloses the missing contract doc as HIGH",
      "routstr_delist_contract.md" in DELIV_TXT
      and "MISSING" in DELIV_TXT and "HIGH" in DELIV_TXT)
check("E6 discloses the duplicate dispatch", "Duplicate-dispatch" in DELIV_TXT
      or "re-dispatched" in DELIV_TXT)
check("E7 bot mirror of the deliverable is byte-identical",
      md5_of(DELIV) == md5_of(os.path.join(BOT, "docs", "reviews", "findings_1_3.md")))
check("E8 script bot copy == repo copy",
      md5_of(SRC) == md5_of(os.path.join(BOT, "scripts", "routstr_delist.py")))
check("E9 contract suite bot copy == repo copy",
      md5_of(CONTRACT) == md5_of(os.path.join(BOT, "tests", "test_routstr_delist.py")))
check("E10 docs bot copy == repo copy",
      md5_of(DOCS) == md5_of(os.path.join(BOT, "docs", "routstr-delist.md")))
check("E11 the named contract doc truly does not exist",
      not os.path.exists(os.path.join(BOT, "docs", "routstr_delist_contract.md")))
DELIV_CITES = {(tag, int(ln)) for tag, ln in
               re.findall(r"(routstr_delist\.py|tests|contract|docs):(\d+)",
                          DELIV_TXT)}
check("E12 every path:N citation in the deliverable is covered by section A",
      DELIV_CITES <= set(AUDITED),
      str(sorted(DELIV_CITES - set(AUDITED))))
check("E13 deliverable's severity summary carries the stable vector",
      "OK" in DELIV_TXT and "MEDIUM" in DELIV_TXT and "LOW" in DELIV_TXT)

# ── transcript digest + tally ─────────────────────────────────────────────
transcript = "\n".join(RESULTS) + "\n"
digest = hashlib.sha256(transcript.encode("utf-8")).hexdigest()
for line in RESULTS:
    print(line)
fails = sum(1 for r in RESULTS if r.startswith("[FAIL]"))
print(f"\nTALLY {len(RESULTS) - fails}/{len(RESULTS)} PASS")
print(f"transcript sha256 {digest}")
sys.exit(1 if fails else 0)
