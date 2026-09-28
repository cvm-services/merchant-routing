#!/usr/bin/env python3
"""probe_f13_pass22.py — fresh, independent re-derivation for the 22nd offload
pass on docs/reviews/findings_1_3.md (routstr delist findings 1-3).

READ-ONLY with respect to every artifact: it reads the script, both test
suites, the stand-in contract doc and the deliverable, and it exercises the
script's real pure functions and its main() CLI against an in-process fake
backend. It writes only under ~/.cache/mr-f13-pass22/ (never /tmp, never the
repo).

Groups:
  A  citation audit          — every path:N the deliverable cites
  B  finding 1 safety        — write-scope + argv + relist-refusal
  C  finding 2 confirmation  — re-fetch gating + relist asymmetry
  D  finding 3 fail-safe     — absent/garbage/stale feed + dry-run residual
  E  review-record integrity — parity, shape, heading/enumeration consistency

Run it twice; it prints a sha256 of its own transcript lines and the two runs
must be byte-identical.
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import shlex
import shutil
import sys
from pathlib import Path

REPO = Path("/home/c03rad0r/repos/merchant-routing")
BOT = Path(os.path.expanduser("~/.hermes/bot"))
SCRATCH = Path(os.path.expanduser("~/.cache/mr-f13-pass22"))
shutil.rmtree(SCRATCH, ignore_errors=True)
SCRATCH.mkdir(parents=True)
TMP = SCRATCH / "tmp"
TMP.mkdir()
os.environ["TMPDIR"] = str(TMP)

SCRIPT = REPO / "src" / "routstr_delist.py"
TESTS = REPO / "tests" / "test_routstr_delist.py"
CONTRACT = REPO / "tests" / "test_routstr_delist_contract.py"
DOCS = REPO / "docs" / "routstr-delist.md"
DELIV = REPO / "docs" / "reviews" / "findings_1_3.md"
MISSING_CONTRACT = BOT / "docs" / "routstr_delist_contract.md"

# fsync can stall indefinitely on this fleet host; durability is not what this
# probe measures (atomic os.replace still runs for real).
os.fsync = lambda fd: None  # type: ignore[assignment]

sys.path.insert(0, str(REPO / "src"))
import routstr_delist as rd  # noqa: E402

LINES: dict[str, list[str]] = {}


def lines_of(p: Path) -> list[str]:
    k = str(p)
    if k not in LINES:
        LINES[k] = p.read_text(encoding="utf-8").splitlines()
    return LINES[k]


RESULTS: list[tuple[str, bool, str]] = []


def check(tag: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((tag, bool(ok), detail))


def group(prefix: str) -> None:
    pass


# ── A. Citation audit ─────────────────────────────────────────────────────
P = {"script": SCRIPT, "tests": TESTS, "contract": CONTRACT, "docs": DOCS}

CITE: list[tuple[str, int, str]] = [
    # -- script: SQL literals + payload builders (finding 1) --
    ("script", 355, "UPDATE models SET enabled=0 WHERE enabled=1;"),
    ("script", 361, "UPDATE models SET enabled=1;"),
    ("script", 394, "UPDATE models SET enabled=1 WHERE name IN"),
    ("script", 371, "SELECT name FROM models WHERE enabled=1"),
    ("script", 408, "SELECT COUNT(*) FROM models WHERE enabled=1"),
    ("script", 35, "upstream_providers"),
    ("script", 352, "upstream_providers"),
    ("script", 771, "upstream_providers"),
    # -- script: remote argv safety (finding 1) --
    ("script", 414, "def build_ssh_docker_cmd"),
    ("script", 423, 'remote = " ".join(["docker", "exec", shlex.quote(container),'),
    ("script", 424, 'python3", "-c", shlex.quote(payload)'),
    ("script", 425, 'return ["ssh", ssh_target, remote]'),
    # -- script: relist refusal / scoped relist (finding 1 + 2) --
    ("script", 600, "if args.relist:"),
    ("script", 606, "relist_refused"),
    ("script", 611, "return 1"),
    ("script", 626, "if not res.get(\"ok\"):"),
    ("script", 633, "state = update_state(state, ts=time.time(), preds=preds,"),
    ("script", 635, 'state.pop("pulled_models", None)'),
    # -- script: confirmation loop (finding 2) --
    ("script", 75, "MAX_PULL_ATTEMPTS = 2"),
    ("script", 671, "while attempts < MAX_PULL_ATTEMPTS:"),
    ("script", 682, "vres = backend.verify(deadline=deadline)"),
    ("script", 683, 'if vres.get("ok") is True and vres.get("count") == 0:'),
    ("script", 687, "confirmed = True"),
    ("script", 691, "res = dict(res)"),
    ("script", 692, 'res["ok"] = False'),
    ("script", 695, "if attempts < MAX_PULL_ATTEMPTS and time.monotonic() < deadline:"),
    ("script", 719, "if not confirmed:"),
    ("script", 726, 'state["delisted"] = False'),
    ("script", 739, "return 3 if newly_blocked else 1"),
    ("script", 747, "state = update_state(state, ts=time.time(), preds=preds, delisted=True,"),
    ("script", 752, "save_state(args.state, state)"),
    ("script", 764, "return 0"),
    # -- script: fail-safe (finding 3) --
    ("script", 78, "STALENESS_S = 1800"),
    ("script", 107, "if not preds_now or not preds_prev:"),
    ("script", 143, "if not preds:"),
    ("script", 152, "isinstance(unc, (int, float))"),
    ("script", 152, "isinstance(unc, bool)"),
    ("script", 193, "def _hours(p):"),
    ("script", 196, 'return h if isinstance(h, (int, float)) else None'),
    ("script", 261, "if preds:"),
    ("script", 262, 'new["snapshot"] = snapshot_preds(preds)'),
    ("script", 479, "return [d for d in data if isinstance(d, dict)]"),
    ("script", 481, "except Exception:"),
    ("script", 482, "return []"),
    ("script", 485, "def feed_is_stale(pred_input, *, max_age_s=STALENESS_S, now=None):"),
    ("script", 494, "return not (0 <= age <= max_age_s)"),
    ("script", 495, "except OSError:"),
    ("script", 496, "return True"),
    ("script", 585, "preds_error = bool(args.preds) and not raw_preds"),
    ("script", 589, "preds_stale = bool(args.preds) and bool(raw_preds) and \\"),
    ("script", 591, "if preds_stale:"),
    ("script", 592, "raw_preds = []"),
    ("script", 594, "if args.preds_key:"),
    ("script", 597, 'preds = [p for p in raw_preds if p.get("key") == args.preds_key]'),
    ("script", 303, "var = variance_jumped(preds_now, threshold=variance_threshold)"),
    ("script", 649, 'fire = args.delist or dec["fire"]'),
    ("script", 651, "if not fire:"),
    ("script", 652, "state = update_state(state, ts=time.time(), preds=preds,"),
    ("script", 654, "save_state(args.state, state)"),
    ("script", 656, '"preds_error": preds_error,'),
    ("script", 660, "return 1 if (preds_error or preds_stale) else 0"),
    ("script", 703, "state = dict(state)"),
    ("script", 705, 'state["last_dry_run"] = {"ts": state["ts"],'),
    ("script", 710, "save_state(args.state, state)"),
    ("script", 580, "override = args.manual or manual_override(args.override)"),
    # -- script: manual override helper + method-group callsites --
    ("script", 164, "def manual_override(override_path):"),
    ("script", 172, "return os.path.isfile(override_path)"),
    ("script", 536, 'ap.add_argument("--ssh-target", default=_DEFAULT_SSH_TARGET)'),
    ("script", 537, 'ap.add_argument("--container", default=_DEFAULT_CONTAINER)'),
    ("script", 565, "save_state(args.state, state)"),
    ("script", 622, "save_state(args.state, state)"),
    ("script", 629, "save_state(args.state, state)"),
    ("script", 638, "save_state(args.state, state)"),
    ("script", 732, "save_state(args.state, state)"),
    ("script", 370, "db=sqlite3.connect('/app/data/keys.db');"),
    ("script", 385, "db=sqlite3.connect('/app/data/keys.db');"),
    ("script", 393, "db=sqlite3.connect('/app/data/keys.db');"),
    ("script", 407, "db=sqlite3.connect('/app/data/keys.db');"),
    ("script", 680, "confirmed = True"),
    ("script", 693, 'res["confirmed"] = False'),
    ("script", 694, 'res["verify"] = {k: vres.get(k) for k in'),
    ("script", 810, "data = {}"),
    ("script", 699, "if args.dry_run:"),
    ("script", 714, '"preds_stale": preds_stale,'),
    ("script", 717, "return 0 if confirmed else 1"),
    ("script", 724, "fails += 1"),
    ("script", 727, 'state["consecutive_failures"] = fails'),
    ("script", 731, 'state["blocked"] = newly_blocked'),
    ("script", 735, '"preds_stale": preds_stale,'),
    ("script", 762, '"preds_stale": preds_stale,'),
    ("script", 569, "if blocked:"),
    ("script", 578, "return 3"),
    ("script", 561, "if args.unblock and blocked:"),
    ("script", 567, "fails = 0"),
    # -- script: backend parse (finding 2) --
    ("script", 808, "proc = subprocess.run(cmd, capture_output=True, text=True,"),
    ("script", 814, "data = json.loads(out.splitlines()[-1])"),
    ("script", 822, 'res["ok"] = proc.returncode == 0 and data.get("ok") is True'),
    # -- tests (main suite) --
    ("tests", 303, "def test_pull_sql_touches_only_models_listing"),
    ("tests", 311, "def test_relist_sql_touches_only_models_listing"),
    ("tests", 336, "def test_verify_payload_scoped_to_models_listing"),
    ("tests", 345, "def test_ssh_cmd_is_single_shlex_safe_remote_command"),
    ("tests", 146, "def test_non_numeric_uncertainty_ignored_not_crash"),
    ("tests", 176, "def test_first_run_never_fires_on_acceleration"),
    ("tests", 243, "def test_update_state_empty_preds_preserves_baseline"),
    ("tests", 514, "def test_dry_run_failure_is_intent_only"),
    ("tests", 547, "def test_unreadable_preds_feed_is_error_not_quiet"),
    ("tests", 567, "def test_verify_gates_success"),
    ("tests", 603, "def test_verify_failure_is_attempt_failure"),
    ("tests", 776, "def test_preds_key_scopes_triggers"),
    ("tests", 937, "def test_stale_feed_never_triggers"),
    ("tests", 968, "def test_staleness_threshold_boundary"),
    ("tests", 980, "def test_stale_feed_exit_zero_when_override_fires"),
    ("tests", 995, "def test_stale_feed_baseline_not_consumed"),
    ("tests", 1039, "def test_relist_refuses_blanket_without_opt_in"),
    ("tests", 1056, "def test_relist_any_executes_blanket"),
    ("tests", 1073, "def test_dry_run_delist_publishes_no_event"),
    ("tests", 1107, "def test_pull_parses_last_line_json_and_gates_on_ok"),
    ("tests", 1116, "def test_pull_garbage_stdout_is_failure"),
    ("tests", 1123, "def test_pull_nonzero_rc_is_failure_even_with_ok_payload"),
    ("tests", 1146, "def test_exception_is_failure_not_crash"),
    # -- contract suite --
    ("contract", 108, "ladder_artifact"),
    ("contract", 129, "CREATE TABLE upstream_providers"),
    ("contract", 160, "SELECT name, enabled, weight FROM upstream_providers"),
    ("contract", 308, "def test_first_run_without_baseline_is_quiet"),
    ("contract", 346, "def test_unverified_pull_is_a_failed_delist"),
    ("contract", 427, "def test_manual_override_is_never_gated_on_feed_staleness"),
    ("contract", 468, "class TestSemanticGuardLadderUntouched:"),
    ("contract", 480, "assert rig.node.ladder_bytes() == ladder_before"),
    ("contract", 483, 'assert "upstream_providers" not in payload'),
    ("contract", 504, "assert rig.node.ladder_bytes() == ladder_before"),
    # -- docs (stand-in contract) --
    ("docs", 29, "**No blanket relist.**"),
    ("docs", 56, "Freshness guard (cold-review finding 3)"),
    ("docs", 60, "never gated on freshness"),
    ("docs", 69, "**Re-fetch confirmation (cold-review finding 2):**"),
    ("docs", 71, "count == 0"),
    ("docs", 87, "**Dry-run is intent-only (verification finding 7c):**"),
    ("docs", 137, "shlex.quote"),
    ("docs", 124, "kind-30078"),
]

for key, lineno, substr in CITE:
    src = lines_of(P[key])
    ok = 1 <= lineno <= len(src) and substr in src[lineno - 1]
    got = src[lineno - 1][:70] if 1 <= lineno <= len(src) else "<out of range>"
    check(f"A:{key}:{lineno}", ok, "" if ok else f"want {substr!r} got {got!r}")

# ── B. Finding 1 — safety ─────────────────────────────────────────────────
script_src = "\n".join(lines_of(SCRIPT))
upstream_lines = sorted(i + 1 for i, l in enumerate(lines_of(SCRIPT))
                        if "upstream_providers" in l)
check("B1", upstream_lines == [35, 352, 771], f"lines={upstream_lines}")

payloads = {
    "pull_sql": rd.pull_listing_sql(),
    "relist_sql": rd.relist_sql(),
    "pull_payload": rd.pull_listing_payload(),
    "relist_payload_scoped": rd.relist_payload(["a", "b"]),
    "relist_payload_blanket": rd.relist_payload([]),
    "verify_payload": rd.verify_pull_payload(),
}
for name, pl in payloads.items():
    check(f"B2:{name}:models", "models" in pl)
    check(f"B2:{name}:no-upstream", "upstream_providers" not in pl)
    check(f"B2:{name}:read-only" if name == "verify_payload" else f"B2:{name}:no-ddl",
          ("UPDATE" not in pl.upper()) if name == "verify_payload"
          else not any(k in pl.upper() for k in
                       ("INSERT", "DELETE ", "DROP", "ALTER", "REPLACE")))

check("B3:verify-is-count", "SELECT COUNT(*) FROM models WHERE enabled=1"
      in rd.verify_pull_payload())
check("B4:shell-true-absent", "shell=True" not in script_src)
check("B5:subprocess-sites",
      script_src.count("subprocess.run(") == 2,
      f"count={script_src.count('subprocess.run(')}")

hostile = "evil'; rm -rf / #"
cmd = rd.build_ssh_docker_cmd("debian@host", hostile, rd.pull_listing_payload())
check("B6:argv-len", len(cmd) == 3 and cmd[0] == "ssh", f"cmd={cmd[:1]}")
check("B7:argv-literal", cmd[1] == "debian@host")
parts = shlex.split(cmd[2])
check("B8:roundtrip-first", parts[:2] == ["docker", "exec"], f"parts={parts[:3]}")
check("B9:roundtrip-container", parts[2] == hostile, f"got={parts[2]!r}")
check("B10:roundtrip-python", parts[3:5] == ["python3", "-c"], f"got={parts[3:5]}")
check("B11:roundtrip-payload", parts[5] == rd.pull_listing_payload())
check("B12:hostile-confined", hostile not in cmd[0] and hostile not in cmd[1]
      and shlex.split(cmd[2])[2] == hostile,
      "shell metacharacters in the container name must survive as exactly one "
      "remote token, absent from argv[0]/argv[1]")

# ── C/D. Behavioural re-derivation via main() ─────────────────────────────
SNAP_SEP = "\x1f"


class FakeBackend:
    def __init__(self, *, pull_ok=True, verify_count=0, verify_ok=True,
                 relist_ok=True, pulled=None):
        self.calls: list[str] = []
        self.pull_ok = pull_ok
        self.verify_count = verify_count
        self.verify_ok = verify_ok
        self.relist_ok = relist_ok
        self.pulled = list(pulled if pulled is not None else ["gpt-4o",
                                                             "claude-3-5-sonnet"])

    def pull(self, dry_run=False, deadline=None):
        self.calls.append("pull")
        return {"ok": self.pull_ok, "action": "pull", "rc": 0,
                "pulled": list(self.pulled)}

    def verify(self, dry_run=False, deadline=None):
        self.calls.append("verify")
        return {"ok": self.verify_ok, "action": "verify", "rc": 0,
                "count": self.verify_count}

    def relist(self, names=None, dry_run=False, deadline=None):
        self.calls.append("relist")
        return {"ok": self.relist_ok, "action": "relist", "rc": 0,
                "restored": len(names or [])}


def run(fake: FakeBackend, argv: list[str], state: Path, override: Path):
    old = rd._SshBackend
    rd._SshBackend = lambda t, c: fake           # type: ignore[assignment]
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            rc = rd.main(["--state", str(state), "--override", str(override)]
                         + list(argv))
    finally:
        rd._SshBackend = old                         # type: ignore[assignment]
    raw = buf.getvalue()
    return rc, (json.loads(raw) if raw.strip() else {}), raw


def write_preds(name: str, preds) -> Path:
    p = SCRATCH / name
    p.write_text(json.dumps(preds) if not isinstance(preds, str) else preds)
    return p


def state_path(name: str) -> Path:
    return SCRATCH / f"{name}.state.json"


def mkstate(name: str, obj: dict | None = None) -> Path:
    p = state_path(name)
    if obj is not None:
        p.write_text(json.dumps(obj))
    elif p.exists():
        p.unlink()
    return p


OVERRIDE = SCRATCH / "absent.override"   # never created: no override

# C1 — happy path: pull + independent verify count==0 -> confirmed delist
st = mkstate("c1")
fb = FakeBackend(verify_count=0)
rc, out, _ = run(fb, ["--manual"], st, OVERRIDE)
check("C1:rc", rc == 0, f"rc={rc}")
check("C1:action", out.get("action") == "delist", str(out.get("action")))
check("C1:confirmed", out.get("confirmed") is True)
check("C1:verified_count", out.get("verified_count") == 0)
check("C1:kinds", fb.calls == ["pull", "verify"], str(fb.calls))
sd = rd.load_state(str(st))
check("C1:delisted", sd.get("delisted") is True)
check("C1:pulled_models", sd.get("pulled_models") == fb.pulled,
      str(sd.get("pulled_models")))

# C2 — lying pull (self-ok, verify refutes) -> failed, retried, breaker tick
st = mkstate("c2")
fb = FakeBackend(pull_ok=True, verify_count=3)
rc, out, _ = run(fb, ["--manual"], st, OVERRIDE)
check("C2:rc", rc == 1, f"rc={rc}")
check("C2:action", out.get("action") == "delist_failed", str(out.get("action")))
check("C2:ok-false", out.get("ok") is False)
check("C2:kinds", fb.calls == ["pull", "verify", "pull", "verify"], str(fb.calls))
sd = rd.load_state(str(st))
check("C2:delisted-not-set", sd.get("delisted") is False)
check("C2:failures", sd.get("consecutive_failures") == 1,
      str(sd.get("consecutive_failures")))

# C3 — relist: NO symmetric re-fetch, self-report gates, names popped (MEDIUM)
st = mkstate("c3")
fb = FakeBackend(verify_count=0)
run(fb, ["--manual"], st, OVERRIDE)              # confirmed delist
fb2 = FakeBackend()
rc, out, _ = run(fb2, ["--relist"], st, OVERRIDE)
check("C3:rc", rc == 0, f"rc={rc}")
check("C3:action", out.get("action") == "relist", str(out.get("action")))
check("C3:no-verify-round-trip", fb2.calls == ["relist"], f"kinds={fb2.calls}")
sd = rd.load_state(str(st))
check("C3:delisted-cleared", sd.get("delisted") is False)
check("C3:names-popped", "pulled_models" not in sd,
      f"pulled_models={sd.get('pulled_models')!r}")

# C4 — lying relist (self-ok) BLINDLY clears the flag and destroys the names
st = mkstate("c4")
fb = FakeBackend(verify_count=0)
run(fb, ["--manual"], st, OVERRIDE)
names_before = rd.load_state(str(st)).get("pulled_models")
fb2 = FakeBackend(relist_ok=True)
rc, out, _ = run(fb2, ["--relist"], st, OVERRIDE)
sd = rd.load_state(str(st))
check("C4:lying-relist-accepted", rc == 0 and sd.get("delisted") is False)
check("C4:names-destroyed", "pulled_models" not in sd and names_before)

# C5 — blanket relist refused with no captured names (zero remote calls)
st = mkstate("c5", {"ts": 1, "delisted": True, "snapshot": {}})
fb = FakeBackend()
rc, out, _ = run(fb, ["--relist"], st, OVERRIDE)
check("C5:rc", rc == 1, f"rc={rc}")
check("C5:action", out.get("action") == "relist_refused", str(out.get("action")))
check("C5:no-remote", fb.calls == [], str(fb.calls))

# ── D. Finding 3 — fail-safe ──────────────────────────────────────────────
# D1 — feed_is_stale boundary, injected clock (inclusive)
fp = write_preds("d1.json", [{"key": "zai", "window": "1h",
                              "exhausts_in_hours": 9.0, "uncertainty": 0.05}])
T = os.path.getmtime(fp)
check("D1:fresh", rd.feed_is_stale(str(fp), now=T) is False)
check("D1:exact1800-fresh", rd.feed_is_stale(str(fp), now=T + 1800) is False)
check("D1:1801-stale", rd.feed_is_stale(str(fp), now=T + 1801) is True)
check("D1:future-stale", rd.feed_is_stale(str(fp), now=T - 5) is True)
check("D1:missing-stale", rd.feed_is_stale(str(SCRATCH / "nope.json")) is True)

# D2 — absent feed: quiet, zero remote, no baseline invented
st = mkstate("d2")
fb = FakeBackend()
rc, out, _ = run(fb, [], st, OVERRIDE)
check("D2:rc", rc == 0, f"rc={rc}")
check("D2:action", out.get("action") == "none", str(out.get("action")))
check("D2:no-remote", fb.calls == [], str(fb.calls))
check("D2:no-baseline", rd.load_state(str(st)).get("delisted") is False)

# D3 — garbage feed: preds_error, rc 1, no remote, baseline preserved
st = mkstate("d3", {"ts": 1, "snapshot": {"zai" + SNAP_SEP + "1h": 12.0}})
before = rd.load_state(str(st)).get("snapshot")
fb = FakeBackend()
rc, out, _ = run(fb, ["--preds", str(write_preds("d3.json", "NOT JSON {{{"))],
                 st, OVERRIDE)
check("D3:rc", rc == 1, f"rc={rc}")
check("D3:preds_error", out.get("preds_error") is True)
check("D3:action", out.get("action") == "none", str(out.get("action")))
check("D3:no-remote", fb.calls == [], str(fb.calls))
check("D3:baseline-intact", rd.load_state(str(st)).get("snapshot") == before,
      f"{rd.load_state(str(st)).get('snapshot')!r} vs {before!r}")

# D4 — non-dict entries dropped, dict survives
p = write_preds("d4.json", [1, "x", None, {"key": "zai", "window": "1h",
                                           "exhausts_in_hours": 9.0,
                                           "uncertainty": 0.05}])
check("D4:preds-count", len(rd._read_preds(str(p))) == 1,
      str(rd._read_preds(str(p))))

# D5 — stale feed with elevated variance: never fires, baseline preserved
st = mkstate("d5", {"ts": 1, "snapshot": {"zai" + SNAP_SEP + "1h": 12.0}})
sp = write_preds("d5.json", [{"key": "zai", "window": "1h",
                              "exhausts_in_hours": 11.0, "uncertainty": 0.99}])
old = os.path.getmtime(sp) - 7200
os.utime(sp, (old, old))
before = rd.load_state(str(st)).get("snapshot")
fb = FakeBackend()
rc, out, _ = run(fb, ["--preds", str(sp)], st, OVERRIDE)
check("D5:rc", rc == 1, f"rc={rc}")
check("D5:stale-flag", out.get("preds_stale") is True)
check("D5:action", out.get("action") == "none", str(out.get("action")))
check("D5:no-remote", fb.calls == [], str(fb.calls))
check("D5:baseline-intact", rd.load_state(str(st)).get("snapshot") == before)

# D6 — manual override is never gated on freshness
st = mkstate("d6")
fb = FakeBackend(verify_count=0)
rc, out, _ = run(fb, ["--manual", "--preds", str(sp)], st, OVERRIDE)
check("D6:rc", rc == 0, f"rc={rc}")
check("D6:action", out.get("action") == "delist", str(out.get("action")))
check("D6:stale-observed", out.get("preds_stale") is True)

# D7 — type guards
check("D7:variance-bool-excluded",
      rd.variance_jumped([{"key": "z", "window": "1h", "uncertainty": True}]) == [])
check("D7:variance-string-ignored",
      rd.variance_jumped([{"key": "z", "window": "1h", "uncertainty": "0.9"}]) == [])
check("D7:hours-bool-accepted-cosmetic",
      rd._hours({"exhausts_in_hours": True}) is True)

# D8 — residual (MEDIUM): quiet-path dry run mutates durable state, no trace
st = mkstate("d8", {"ts": 1, "snapshot": {"zai" + SNAP_SEP + "1h": 12.0},
                    "delisted": False})
qp = write_preds("d8.json", [{"key": "zai", "window": "1h",
                             "exhausts_in_hours": 11.0, "uncertainty": 0.05}])
fb = FakeBackend()
rc, out, _ = run(fb, ["--dry-run", "--preds", str(qp)], st, OVERRIDE)
sd = rd.load_state(str(st))
check("D8:quiet-rc0", rc == 0, f"rc={rc}")
check("D8:snapshot-mutated", sd.get("snapshot") == {"zai" + SNAP_SEP + "1h": 11.0},
      f"snapshot={sd.get('snapshot')!r}")
check("D8:no-dry-run-trace", "last_dry_run" not in sd)
# contrast: the FIRING dry-run does record the intent (see D9 below)
st8b = mkstate("d8b")
_fb8b = FakeBackend(verify_count=0)
run(_fb8b, ["--dry-run", "--manual"], st8b, OVERRIDE)
check("D8:contrast-firing-dry-run-records",
      "last_dry_run" in rd.load_state(str(st8b)))

# D9 — firing dry-run: intent recorded, no durable delist flag, no publish
st = mkstate("d9")
fb = FakeBackend(verify_count=0)
rc, out, _ = run(fb, ["--dry-run", "--manual"], st, OVERRIDE)
sd = rd.load_state(str(st))
check("D9:rc0", rc == 0, f"rc={rc}")
check("D9:no-verify", fb.calls == ["pull"], str(fb.calls))
check("D9:last_dry_run", "last_dry_run" in sd)
check("D9:no-delist-flag", "delisted" not in sd)

# D10 — --preds-key scoping is opt-in; evaluate_triggers passes no key
st = mkstate("d10")
fb = FakeBackend(verify_count=0)
mixed = write_preds("d10.json", [
    {"key": "zai", "window": "1h", "exhausts_in_hours": 10.0, "uncertainty": 0.05},
    {"key": "openrouter", "window": "1h", "exhausts_in_hours": 10.0,
     "uncertainty": 0.95}])
rc, out, _ = run(fb, ["--preds", str(mixed)], st, OVERRIDE)
check("D10:unscoped-foreign-fires", out.get("action") == "delist",
      str(out.get("action")))
check("D10:key-filter-exists",
      rd.variance_jumped([{"key": "a", "window": "1h", "uncertainty": 0.9}],
                         key="b") == [])

# ── E. Review-record integrity ────────────────────────────────────────────
check("E1:contract-path-missing", not MISSING_CONTRACT.exists(), str(MISSING_CONTRACT))
tmpl = f"{MISSING_CONTRACT.name}"
check("E2:no-template-in-tree",
      not any(p.name == tmpl for p in (REPO / "docs").rglob("*")),
      "tree-wide *contract*.md absent under repo docs/")

PAIRS = [("script", SCRIPT, f"{REPO}/src/routstr_delist.py"),
         ("tests", CONTRACT, f"{BOT}/tests/test_routstr_delist.py"),
         ("docs", DOCS, f"{BOT}/docs/routstr-delist.md"),
         ("deliverable", DELIV, f"{BOT}/docs/reviews/findings_1_3.md")]
for key, a, b in PAIRS:
    from hashlib import md5
    ha = md5(a.read_bytes()).hexdigest()
    hb = md5(Path(b).read_bytes()).hexdigest() if Path(b).exists() else None
    check(f"E3:{key}-parity", ha == hb, f"repo={ha[:12]} bot={hb[:12] if hb else None}")

dl = lines_of(DELIV)
headings = [l for l in dl if l.startswith("## ")]
check("E4:exactly-three-sections", len(headings) == 3,
      f"headings={[h[:40] for h in headings]}")
for i, h in enumerate(headings, 1):
    check(f"E5:heading{i}-named", h.startswith(f"## Finding {i}"), h[:60])

# heading-declared residual counts vs enumerated items (self-referential guard)
import re as _re
secs: list[list[str]] = []
for line in dl:
    if line.startswith("## Finding "):
        secs.append([line])
    elif secs:
        secs[-1].append(line)
for i, sec in enumerate(secs, 1):
    head = sec[0]
    sev_probe = "\n".join(sec[:4])   # tag sits on the line below the heading
    low_decl = _re.search(r"\*\*LOW\*\*\s*×\s*(\d+)", sev_probe)
    med_decl = _re.search(r"\*\*MEDIUM\*\*\s*×\s*(\d+)", sev_probe)
    n_low = sum(1 for l in sec if l.startswith("- (**LOW**)"))
    n_med = sum(1 for l in sec if l.startswith("- (**MEDIUM**)"))
    check(f"E6:f{i}-severity-tag", bool(_re.search(r"severity:\s*\*\*(OK|BLOCKER|HIGH|MEDIUM|LOW)\*\*", sev_probe)), head[:70])
    lo = int(low_decl.group(1)) if low_decl else 0
    me = int(med_decl.group(1)) if med_decl else 0
    check(f"E7:f{i}-low-count", lo == n_low, f"declared={lo} enumerated={n_low}")
    check(f"E8:f{i}-med-count", me == n_med, f"declared={me} enumerated={n_med}")

check("E9:no-tmp-litter", not any(SCRATCH.glob("**/.*.tmp")), "state tmp cleanup")

# ── transcript ────────────────────────────────────────────────────────────
out_lines = []
for tag, ok, detail in RESULTS:
    out_lines.append(f"[{'PASS' if ok else 'FAIL'}] {tag}" + (f"  -- {detail}" if detail and not ok else ""))
# deterministic, file-state-dependent lines so the transcript digests the
# artifacts as well as the checks (identical run-to-run, different pre/post
# deliverable rewrite).
out_lines.append("deliverable md5: " + hashlib.md5(DELIV.read_bytes()).hexdigest())
out_lines.append("deliverable lines: " + str(len(dl)))
out_lines.append("script md5: " + hashlib.md5(SCRIPT.read_bytes()).hexdigest())
npass = sum(1 for _, ok, _ in RESULTS if ok)
out_lines.append(f"{npass}/{len(RESULTS)} PASS")
body = "\n".join(out_lines)
print(body)
print("transcript sha256:", hashlib.sha256(body.encode()).hexdigest())
raise SystemExit(0 if npass == len(RESULTS) else 1)
