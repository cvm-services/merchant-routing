#!/usr/bin/env python3
"""audit_doc_refs_pass21.py — verify every file:line citation in
~/.hermes/bot/docs/reviews/findings_4_5.md resolves to a real line in the
corresponding DEPLOYED artifact copy.

Checks: (a) every cited line number is within range of its artifact;
(b) a curated set of claims holds the exact quoted text. Read-only.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

BOT = Path.home() / ".hermes/bot"
REVIEW = BOT / "docs" / "reviews" / "findings_4_5.md"

FILES = {
    "src": (BOT / "scripts" / "routstr_delist.py").read_text().splitlines(),
    "contract": (BOT / "tests" / "test_routstr_delist.py").read_text().splitlines(),
    "docs": (BOT / "docs" / "routstr-delist.md").read_text().splitlines(),
}
# the repo unit suite is cited as unit:N elsewhere; not present in this doc.
text = REVIEW.read_text()

# ── (a) range check for every citation ──────────────────────────────────
# matches src:123 , contract:123-456 , docs:64-68 ... (multi-refs split on ,)
refs = re.findall(r"\b(src|contract|docs):(\d+)(?:-(\d+))?", text)
bad_range = []
count = 0
for name, a, b in refs:
    lines = FILES[name]
    lo, hi = int(a), int(b) if b else int(a)
    count += 1
    if not (1 <= lo <= len(lines) and 1 <= hi <= len(lines) and lo <= hi):
        bad_range.append((name, lo, hi, len(lines)))

print(f"citations found: {count}")
print(f"out-of-range: {len(bad_range)} {bad_range[:6]}")

# ── (b) curated claim audit (line must CONTAIN the fragment) ────────────
CLAIMS = [
    ("src", 221, "def save_state"),
    ("src", 230, "tmp = os.path.join"),
    ("src", 232, "json.dump"),
    ("src", 233, "fh.flush()"),
    ("src", 234, "os.fsync"),
    ("src", 235, "os.replace"),
    ("src", 237, "return True"),
    ("src", 238, "except Exception"),
    ("src", 240, "finally"),
    ("src", 244, "except OSError"),
    ("src", 248, "def update_state"),
    ("src", 251, "flag in the objects that publishes the"),
    ("src", 263, 'new["delisted"] = bool(delisted)'),
    ("src", 543, "state = load_state(args.state)"),
    ("src", 544, "state.get(\"consecutive_failures\""),
    ("src", 545, "isinstance(fails, int)"),
    ("src", 546, 'blocked = bool(state.get("blocked"))'),
    ("src", 548, "if args.status"),
    ("src", 552, 'pulled_models'),
    ("src", 557, "return 0"),
    ("src", 561, "if args.unblock and blocked"),
    ("src", 562, 'state.pop("blocked"'),
    ("src", 565, "save_state(args.state, state)"),
    ("src", 567, "fails = 0"),
    ("src", 569, "if blocked:"),
    ("src", 578, "return 3"),
    ("src", 585, "preds_error = bool(args.preds)"),
    ("src", 600, "if args.relist:"),
    ("src", 601, 'names = state.get("pulled_models") or []'),
    ("src", 602, "if not names and not args.relist_any"),
    ("src", 606, 'print(json.dumps({"action": "relist_refused"'),
    ("src", 611, "return 1"),
    ("src", 612, "deadline = time.monotonic() + ACTION_BUDGET_S"),
    ("src", 613, "relist(_SshBackend(args.ssh_target, args.container)"),
    ("src", 614, "deadline=deadline"),
    ("src", 626, 'if not res.get("ok"):'),
    ("src", 628, 'state["last_pull_error"]'),
    ("src", 632, "return 1"),
    ("src", 636, 'state["consecutive_failures"] = 0'),
    ("src", 637, 'state["blocked"] = False'),
    ("src", 638, "save_state(args.state, state)"),
    ("src", 667, "deadline = time.monotonic() + ACTION_BUDGET_S"),
    ("src", 671, "while attempts < MAX_PULL_ATTEMPTS"),
    ("src", 676, "time.monotonic() < deadline"),
    ("src", 683, 'vres.get("count") == 0'),
    ("src", 695, "time.monotonic() < deadline"),
    ("src", 724, "fails += 1"),
    ("src", 730, "newly_blocked = fails >= BREAKER_THRESHOLD"),
    ("src", 731, 'state["blocked"] = newly_blocked'),
    ("src", 732, "save_state(args.state, state)"),
    ("src", 739, "return 3 if newly_blocked else 1"),
    ("src", 744, 'prior = state.get("pulled_models") or []'),
    ("src", 745, 'pulled = res.get("pulled") or []'),
    ("src", 746, "merged = list(prior) + [n for n in pulled if n not in prior]"),
    ("src", 747, "state = update_state(state"),
    ("src", 749, 'extra={"pulled_models": merged})'),
    ("src", 750, 'state["consecutive_failures"] = 0'),
    ("src", 751, 'state["blocked"] = False'),
    ("src", 752, "save_state(args.state, state)"),
    ("src", 755, "if args.nsec:"),
    ("src", 756, "publish_delist_event(args.nsec, delisted=True)"),
    ("src", 451, "def publish_delist_event"),
    ("src", 459, "subprocess.run(argv, timeout=30,"),
    ("src", 464, "return argv"),
    ("src", 71, "TRIGGER_ACTION_WINDOW_S = 300"),
    ("src", 72, "POLL_CADENCE_S = 240"),
    ("src", 73, "ACTION_BUDGET_S = TRIGGER_ACTION_WINDOW_S - POLL_CADENCE_S"),
    ("src", 74, "SSH_TIMEOUT_S = 30"),
    ("src", 75, "MAX_PULL_ATTEMPTS = 2"),
    ("src", 152, "isinstance(unc, bool)"),
    ("src", 394, "c=db.execute('UPDATE models SET enabled=1 WHERE name IN"),
    ("src", 396, "restored"),
    ("src", 64, "5-minute SLA arithmetic"),
    ("src", 800, "timeout = SSH_TIMEOUT_S"),
    ("src", 801, "if deadline is not None:"),
    ("src", 803, "if remaining <= 0:"),
    ("src", 805, "action budget exhausted"),
    ("src", 806, "timeout = min(SSH_TIMEOUT_S, remaining)"),
    ("src", 822, 'res["ok"] = proc.returncode == 0 and data.get("ok") is True'),
    ("contract", 1, "TDD contract suite for routstr_delist (frozen contract"),
    ("contract", 50, "for _cand in (_HERE.parent"),
    ("contract", 54, "break"),
    ("contract", 252, "this fleet host's disk can stall indefinitely"),
    ("contract", 254, "fsync durability is behaviourally pinned"),
    ("contract", 257, 'monkeypatch.setattr(os, "fsync"'),
    ("contract", 427, "def test_manual_override_is_never_gated_on_feed_staleness"),
    ("contract", 490, "def test_scoped_relist_restores_only_the_pulled_listing"),
    ("contract", 507, 'assert "pulled_models" not in st'),
    ("contract", 524, "def test_forced_delist_on_absent_listing_is_idempotent_success"),
    ("contract", 537, "merge, no clobber"),
    ("contract", 543, "def test_poll_cadence_config_satisfies_the_window"),
    ("contract", 553, "def test_trigger_sample_to_verified_delist_under_300s"),
    ("contract", 577, "entry[\"timeout\"] <= rd.ACTION_BUDGET_S"),
    ("contract", 594, '"blocked": true'),
    ("contract", 599, 'rig.node.kinds() == ["pull"] * 6'),
    ("contract", 601, "def test_blocked_run_refuses_all_remote_action"),
    ("contract", 612, "calls_before"),
    ("contract", 628, "class TestAtomicStateWrites"),
    ("contract", 629, "@pytest.fixture(autouse=True)"),
    ("contract", 634, 'monkeypatch.setattr(os, "fsync"'),
    ("contract", 636, "def test_successful_save_swaps_whole_file_atomically"),
    ("contract", 643, "rd.save_state(str(state_path), old) is True"),
    ("contract", 657, "rd.save_state(str(state_path), new) is True"),
    ("contract", 665, "def test_crash_between_tmp_and_replace_keeps_previous_state"),
    ("contract", 682, "is False"),
    ("contract", 686, "never torn"),
    ("docs", 29, "**No blanket relist.**"),
    ("docs", 32, "--relist-any"),
    ("docs", 64, "A **failed pull/relist**"),
    ("docs", 68, "in the state file."),
    ("docs", 76, "**Circuit breaker (task body):**"),
    ("docs", 79, "Any confirmed success"),
    ("docs", 96, "POLL_CADENCE_S         = 240"),
    ("docs", 98, "SSH_TIMEOUT_S          = 30"),
    ("docs", 100, "Worst-case detection is one full poll cadence"),
    ("docs", 103, "detection (≤ 240 s) + action (≤ 60 s) ≤ 300 s"),
    ("docs", 106, "*/4 * * * *"),
    ("docs", 112, "**Deployment note (cold-review finding 6):**"),
    ("docs", 115, "outbound SSH is blocked"),
    ("docs", 122, "**Flag**"),
    ("docs", 123, "delisted=true"),
]
bad_claim = []
for name, ln, frag in CLAIMS:
    lines = FILES[name]
    if ln > len(lines) or frag not in lines[ln - 1]:
        got = lines[ln - 1].strip()[:80] if ln <= len(lines) else "<out of range>"
        bad_claim.append((name, ln, frag, got))

print(f"claim checks: {len(CLAIMS)}")
print(f"claim failures: {len(bad_claim)}")
for b in bad_claim:
    print("  BAD:", b)

ok = not bad_range and not bad_claim
print("AUDIT", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
