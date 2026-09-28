#!/usr/bin/env python3
"""probe_f13_pass18.py — fresh independent re-verification for the
findings_1_3.md deliverable (routstr dynamic delist), nineteenth offload pass.

Hermetic: no network, no ssh spawn, no fsync (patched to a no-op — fsync can
stall indefinitely on this host). Scratch lives under
~/.cache/f13-pass18/tmp, never /tmp (RAM tmpfs, ENOSPC on this host).

Sections:
  A  citation audit — every file:line the deliverable cites must contain the
     substring it claims lives there (script, main test suite, contract suite).
  B  safety — payload scoping: no payload names upstream_providers; pull SQL is
     models-only; scoped relist parameterized; single shlex-quoted remote argv.
  C  confirmation — lying pull is refuted (rc 1), confirmed delist gates on
     count==0 (rc 0, delisted true); relist runs NO verify round-trip (MEDIUM).
  D  fail-safe — feed_is_stale fail-closed incl. inclusive boundary; uncertainty
     type guards; garbage feed never wipes the baseline; manual override never
     gated on staleness; dry-run on the QUIET path refreshes the baseline and
     records no last_dry_run (MEDIUM).

Run: python3 docs/reviews/routstr_f13_probes/probe_f13_pass18.py
Prints a per-check PASS/FAIL tally and a transcript sha256 (run twice; the
digest must be identical and the tally must read N/N PASS).
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
import shutil
import sys
import tempfile
import traceback

REPO = "/home/c03rad0r/repos/merchant-routing"
SRC = os.path.join(REPO, "src", "routstr_delist.py")
MAIN = os.path.join(REPO, "tests", "test_routstr_delist.py")
CONTRACT = os.path.join(REPO, "tests", "test_routstr_delist_contract.py")
CACHE = os.path.expanduser("~/.cache/f13-pass18")
SCRATCH = os.path.join(CACHE, "tmp")
shutil.rmtree(CACHE, ignore_errors=True)
os.makedirs(SCRATCH, exist_ok=True)
os.environ["TMPDIR"] = SCRATCH

# ── load the module under review ──────────────────────────────────────────
spec = importlib.util.spec_from_file_location("rd18", SRC)
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


SRC_L = lines_of(SRC)
MAIN_L = lines_of(MAIN)
CON_L = lines_of(CONTRACT)


def cite(name: str, path_lines: list[str], lineno: int, needle: str) -> None:
    line = path_lines[lineno - 1] if 0 < lineno <= len(path_lines) else "<OOB>"
    check(name, needle in line, f"L{lineno}<-{needle!r}")


# ── Section A: citation audit ─────────────────────────────────────────────
cite("A1 pull_listing_sql UPDATE models enabled=0", SRC_L, 355,
     "UPDATE models SET enabled=0 WHERE enabled=1")
cite("A2 relist_sql blanket UPDATE models enabled=1", SRC_L, 361,
     "UPDATE models SET enabled=1;")
cite("A3 scoped relist parameterized UPDATE", SRC_L, 394,
     "UPDATE models SET enabled=1 WHERE name IN")
cite("A4 verify payload SELECT COUNT read-only", SRC_L, 408,
     "SELECT COUNT(*) FROM models WHERE enabled=1")
cite("A5 upstream_providers docstring L35", SRC_L, 35, "upstream_providers")
cite("A6 upstream_providers docstring L352", SRC_L, 352, "upstream_providers")
cite("A7 upstream_providers docstring L771", SRC_L, 771, "upstream_providers")
cite("A8 shlex.quote(container)", SRC_L, 423, "shlex.quote(container)")
cite("A9 shlex.quote(payload)", SRC_L, 424, "shlex.quote(payload)")
cite("A10 ssh argv element", SRC_L, 425, '["ssh", ssh_target, remote]')
cite("A11 STALENESS_S=1800", SRC_L, 78, "STALENESS_S = 1800")
cite("A12 feed_is_stale fail-closed OSError", SRC_L, 495, "except OSError:")
cite("A13 feed_is_stale inclusive bound", SRC_L, 494,
     "return not (0 <= age <= max_age_s)")
cite("A14 preds_error computed", SRC_L, 585, "preds_error = bool(args.preds)")
cite("A15 preds_stale wiring", SRC_L, 589, "preds_stale = bool(args.preds)")
cite("A16 stale zeroes preds", SRC_L, 591, "if preds_stale:")
cite("A17 preds-key filter", SRC_L, 597, 'p.get("key") == args.preds_key')
cite("A18 evaluate_triggers no key to variance", SRC_L, 303,
     "var = variance_jumped(preds_now, threshold=variance_threshold)")
cite("A19 override before freshness", SRC_L, 580, "override = args.manual")
cite("A20 quiet branch exit 1 if err/stale", SRC_L, 660,
     "return 1 if (preds_error or preds_stale) else 0")
cite("A21 verify call inside loop", SRC_L, 682, "vres = backend.verify")
cite("A22 confirm gate count==0", SRC_L, 683,
     'vres.get("ok") is True and vres.get("count") == 0')
cite("A23 refute lying pull", SRC_L, 692, 'res["ok"] = False')
cite("A24 failure branch no delisted", SRC_L, 726, 'state["delisted"] = False')
cite("A25 relist self-report gate (no verify)", SRC_L, 626, 'if not res.get("ok"):')
cite("A26 relist pops pulled_models", SRC_L, 635, 'state.pop("pulled_models", None)')
cite("A27 MAX_PULL_ATTEMPTS=2", SRC_L, 75, "MAX_PULL_ATTEMPTS = 2")
cite("A28 blanket relist refused", SRC_L, 606, '"action": "relist_refused"')
cite("A29 uncertainty type guard", SRC_L, 152,
     "not isinstance(unc, (int, float)) or isinstance(unc, bool)")
cite("A30 update_state baseline only if preds", SRC_L, 261, "if preds:")
cite("A31 quiet path has no dry-run guard", SRC_L, 651, "if not fire:")
cite("A32 quiet path refreshes snapshot", SRC_L, 652,
     "state = update_state(state, ts=time.time(), preds=preds")
cite("A33 main suite: verify gates success", MAIN_L, 567,
     "def test_verify_gates_success")
cite("A34 main suite: verify failure=attempt failure", MAIN_L, 603,
     "def test_verify_failure_is_attempt_failure")
cite("A35 main suite: relist refuses blanket", MAIN_L, 1039,
     "def test_relist_refuses_blanket_without_opt_in")
cite("A36 main suite: manual override vs staleness", MAIN_L, 980,
     "def test_stale_feed_exit_zero_when_override_fires")
cite("A37 main suite: stale baseline not consumed", MAIN_L, 995,
     "def test_stale_feed_baseline_not_consumed")
cite("A38 main suite: ssh shlex-safe single cmd", MAIN_L, 345,
     "def test_ssh_cmd_is_single_shlex_safe_remote_command")
cite("A39 main suite: non-numeric uncertainty", MAIN_L, 146,
     "def test_non_numeric_uncertainty_ignored_not_crash")
cite("A40 main suite: update_state preserves baseline", MAIN_L, 243,
     "def test_update_state_empty_preds_preserves_baseline")
cite("A41 contract: ladder guard class", CON_L, 468,
     "class TestSemanticGuardLadderUntouched")
cite("A42 contract: ladder byte-identical assert", CON_L, 480,
     "assert rig.node.ladder_bytes() == ladder_before")
cite("A43 contract: no payload names upstream_providers", CON_L, 483,
     'assert "upstream_providers" not in payload')
cite("A44 contract: lying pull refuted case", CON_L, 346,
     "def test_unverified_pull_is_a_failed_delist")
cite("A45 contract: manual override not gated on staleness", CON_L, 427,
     "def test_manual_override_is_never_gated_on_feed_staleness")
cite("A46 contract: ladder artifact built", CON_L, 108, "ladder_artifact")
cite("A47 contract: fake node DECLARES models vs providers", CON_L, 129,
     "CREATE TABLE upstream_providers")

# ── Section B: safety ─────────────────────────────────────────────────────
PAYLOADS = {
    "pull": rd.pull_listing_payload(),
    "verify": rd.verify_pull_payload(),
    "relist_scoped": rd.relist_payload(["gpt-4o", "llama-3"]),
    "relist_blanket": rd.relist_payload([]),
}
for nm, pl in PAYLOADS.items():
    check(f"B1 payload[{nm}] does not name upstream_providers",
          "upstream_providers" not in pl, pl[:40])
    check(f"B2 payload[{nm}] targets models table", "models" in pl)
check("B3 no INSERT/DELETE/DROP in any payload",
      not any(v in "".join(PAYLOADS.values()).upper()
              for v in ("INSERT ", "DELETE ", "DROP ", "ALTER ", "REPLACE INTO")))
check("B4 pull SQL models-only enabled=0",
      rd.pull_listing_sql().strip() == "UPDATE models SET enabled=0 WHERE enabled=1;")
check("B5 blanket relist SQL is models-only",
      rd.relist_sql().strip() == "UPDATE models SET enabled=1;")
cmd = rd.build_ssh_docker_cmd("debian@host", "ctr name", "p=1")
check("B6 remote argv is 3 elements (single remote cmd)", len(cmd) == 3, str(len(cmd)))
import shlex as _sh
check("B7 remote cmd round-trips via shlex.split",
      _sh.split(cmd[2]) == ["docker", "exec", "ctr name", "python3", "-c", "p=1"])
check("B8 no shell=True anywhere (source grep)",
      "shell=True" not in "\n".join(SRC_L))
check("B9 exactly 2 subprocess.run sites",
      sum(1 for x in SRC_L if "subprocess.run(" in x) == 2)

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


def run_main(backend: FakeBackend, args: list[str]) -> dict:
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


def write_state(path: str, obj: dict) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh)


def write_preds(path: str, preds: list, age_s: float = 0.0) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(preds, fh)
    if age_s:
        t = os.path.getmtime(path) - age_s
        os.utime(path, (t, t))


def read_state(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


# ── Section C: confirmation ───────────────────────────────────────────────
def new_paths(tag: str):
    d = tempfile.mkdtemp(dir=SCRATCH, prefix=tag + "-")
    return os.path.join(d, "state.json"), os.path.join(d, "preds.json")


# C1 lying pull refuted (verify count=1) -> rc 1, delisted false, 2 attempts
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

# C2 confirmed delist (verify count=0) -> rc 0, delisted true, 1 attempt
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
check("C2 verify payload read-only",
      "UPDATE" not in rd.verify_pull_payload())

# C3 relist runs NO verify round-trip (MEDIUM residual)
st, pf = new_paths("C3")
write_state(st, {"delisted": True, "pulled_models": ["gpt-4o"],
                 "snapshot": {"zai\x1f1h": 20.0}})
b = FakeBackend("h", "c")
out = run_main(b, ["--state", st, "--preds", pf, "--relist"])
check("C3 relist kinds == [relist] only", b.kinds == ["relist"], str(b.kinds))
check("C3 relist rc0", out["_rc"] == 0, str(out.get("_rc")))
s = read_state(st)
check("C3 relist flips delisted false on self-report", s["delisted"] is False)
check("C3 relist destroys scoped names (asymmetry)", "pulled_models" not in s)

# ── Section D: fail-safe ──────────────────────────────────────────────────
f = os.path.join(SCRATCH, "feed.json")
write_preds(f, [{"key": "zai", "window": "1h", "exhausts_in_hours": 5.0}])
tm = os.path.getmtime(f)
check("D1 fresh feed not stale", rd.feed_is_stale(f, now=tm + 10) is False)
check("D2 exact boundary inclusive (fresh)", rd.feed_is_stale(f, now=tm + 1800) is False)
check("D3 aged feed stale", rd.feed_is_stale(f, now=tm + 1801) is True)
check("D4 future mtime stale", rd.feed_is_stale(f, now=tm - 1) is True)
check("D5 missing path stale", rd.feed_is_stale(os.path.join(SCRATCH, "nope.json")) is True)
check("D6 uncertainty string guard",
      rd.variance_jumped([{"key": "z", "uncertainty": "0.9"}]) == [])
check("D7 uncertainty bool guard",
      rd.variance_jumped([{"key": "z", "uncertainty": True}]) == [])
check("D8 uncertainty numeric fires",
      len(rd.variance_jumped([{"key": "z", "uncertainty": 0.9}])) == 1)
check("D9 _hours accepts bool (cosmetic LOW)",
      rd._hours({"exhausts_in_hours": True}) is True)
check("D10 no baseline -> acceleration never fires",
      rd.exhaustion_accelerated([{"key": "z", "window": "1h",
                                  "exhausts_in_hours": 1.0}], []) == [])
check("D11 preds-key scoping filters foreign key",
      rd.variance_jumped([{"key": "openrouter", "uncertainty": 0.95}],
                         key="zai") == [])

# D12 garbage feed: rc 1, preds_error true, baseline preserved
st, pf = new_paths("D12")
with open(pf, "w", encoding="utf-8") as fh:
    fh.write("{ this is not json")
write_state(st, {"snapshot": {"zai\x1f1h": 10.0}, "delisted": False})
b = FakeBackend("h", "c")
out = run_main(b, ["--state", st, "--preds", pf])
check("D12 garbage feed rc1", out["_rc"] == 1, str(out.get("_rc")))
check("D12 preds_error true", out.get("preds_error") is True)
check("D12 baseline preserved",
      read_state(st)["snapshot"] == {"zai\x1f1h": 10.0})
check("D12 no remote action", b.kinds == [], str(b.kinds))

# D13 stale feed + variance: never fires, rc1, preds_stale true
st, pf = new_paths("D13")
write_preds(pf, [{"key": "zai", "window": "1h", "exhausts_in_hours": 5.0,
                  "uncertainty": 0.99}], age_s=7200)
write_state(st, {"snapshot": {}, "delisted": False})
b = FakeBackend("h", "c")
out = run_main(b, ["--state", st, "--preds", pf])
check("D13 stale -> rc1", out["_rc"] == 1, str(out.get("_rc")))
check("D13 action none", out.get("action") == "none")
check("D13 preds_stale true", out.get("preds_stale") is True)
check("D13 no remote action", b.kinds == [], str(b.kinds))

# D14 manual override never gated on staleness
st, pf = new_paths("D14")
write_preds(pf, [{"key": "zai", "window": "1h", "exhausts_in_hours": 5.0}],
            age_s=7200)
write_state(st, {"snapshot": {}, "delisted": False})
b = FakeBackend("h", "c")
b.verify_count = 0
out = run_main(b, ["--state", st, "--preds", pf, "--manual"])
check("D14 stale + --manual delists rc0", out["_rc"] == 0, str(out.get("_rc")))
check("D14 action delist", out.get("action") == "delist")

# D15 MEDIUM: dry-run on the QUIET path refreshes the baseline and records no
# last_dry_run (docs promise intent-only; the quiet branch has no dry-run guard)
st, pf = new_paths("D15")
write_preds(pf, [{"key": "zai", "window": "1h", "exhausts_in_hours": 11.0}])
write_state(st, {"snapshot": {"zai\x1f1h": 12.0}, "delisted": False})
b = FakeBackend("h", "c")
out = run_main(b, ["--state", st, "--preds", pf, "--dry-run"])
s = read_state(st)
check("D15 dry-run quiet path rc0", out["_rc"] == 0, str(out.get("_rc")))
check("D15 dry-run quiet path refreshes baseline (11.0)",
      s["snapshot"].get("zai\x1f1h") == 11.0, str(s.get("snapshot")))
check("D15 dry-run quiet path records NO last_dry_run",
      "last_dry_run" not in s)

# ── transcript digest + tally ─────────────────────────────────────────────
transcript = "\n".join(RESULTS) + "\n"
digest = hashlib.sha256(transcript.encode("utf-8")).hexdigest()
for line in RESULTS:
    print(line)
fails = sum(1 for r in RESULTS if r.startswith("[FAIL]"))
print(f"\nTALLY {len(RESULTS) - fails}/{len(RESULTS)} PASS")
print(f"transcript sha256 {digest}")
sys.exit(1 if fails else 0)
