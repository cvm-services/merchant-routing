#!/usr/bin/env python3
"""Pass-20 follow-up audit: every `file:line` token in the DELIVERED
findings_4_5.md must (a) parse, (b) resolve to an existing line in the named
file with the cited end >= start, and (c) for an anchor set, hold the claimed
text. Read-only. Usage: python3 audit_doc_refs_pass20.py"""
import os
import re
import sys

ROOT = os.path.expanduser("~/repos/merchant-routing")
BOT = os.path.expanduser("~/.hermes/bot")
DOC = os.path.join(BOT, "docs/reviews/findings_4_5.md")
FILES = {
    "src": os.path.join(BOT, "scripts/routstr_delist.py"),
    "contract": os.path.join(BOT, "tests/test_routstr_delist.py"),
    "docs": os.path.join(BOT, "docs/routstr-delist.md"),
    "unit": os.path.join(ROOT, "tests/test_routstr_delist.py"),
    "orig": os.path.join(ROOT, "docs/reviews/routstr_delist_review.md"),
}

# anchors added in this pass's write, not covered by audit_citations_pass20.py
ANCHORS = [
    ("contract", 1, "frozen contract"),
    ("contract", 50, '_HERE.parent / "src"'),
    ("contract", 54, "break"),
    ("contract", 490, "def test_scoped_relist_restores_only_the_pulled_listing"),
    ("contract", 636, "test_successful_save_swaps_whole_file_atomically"),
    ("contract", 663, "no tmp litter"),
    ("contract", 665, "test_crash_between_tmp_and_replace_keeps_previous_state"),
    ("unit", 273, "def test_save_state_atomic_no_tmp_left_behind"),
    ("unit", 282, ""),
    ("unit", 284, "def test_torn_write_never_replaces_good_state"),
    ("unit", 298, ""),
    ("unit", 1017, "def test_double_delist_merges_pulled_models"),
    ("unit", 1035, ""),
    ("unit", 1039, "def test_relist_refuses_blanket_without_opt_in"),
    ("unit", 1053, ""),
    ("unit", 1056, "def test_relist_any_executes_blanket"),
    ("unit", 289, "save_state"),
    ("unit", 278, "save_state"),
    ("src", 64, "5-minute SLA arithmetic"),
    ("src", 70, "run can never spend more than ACTION_BUDGET_S acting"),
    ("src", 543, "load_state(args.state)"),
    ("src", 562, 'state.pop("blocked", None)'),
    ("src", 567, "fails = 0"),
    ("docs", 106, "*/4 * * * *"),
    ("docs", 115, "outbound SSH is blocked by policy there"),
    ("docs", 32, "--relist-any"),
    ("orig", 194, "rather than blanket-enable."),
]

text = open(DOC, encoding="utf-8").read()
lines = open(DOC, encoding="utf-8").read().splitlines()
cache = {}
for k, v in FILES.items():
    cache[k] = open(v, encoding="utf-8").read().splitlines()

bad = 0
# (a)+(b): every token in the doc resolves
tokens = re.findall(r"\b(src|contract|docs|unit|orig):(\d+)(?:-(\d+))?", text)
seen = set()
for key, a, b in tokens:
    a, b = int(a), int(b) if b else int(a)
    if (key, a, b) in seen:
        continue
    seen.add((key, a, b))
    n = len(cache[key])
    if not (1 <= a <= b <= n):
        bad += 1
        print(f"BAD RANGE {key}:{a}-{b} (file has {n} lines)")
print(f"{len(seen)} distinct ref ranges resolve in-bounds")

# (c): anchors
for key, ln, sub in ANCHORS:
    got = cache[key][ln - 1] if 0 < ln <= len(cache[key]) else "<OUT OF RANGE>"
    if sub not in got:
        bad += 1
        print(f"ANCHOR MISMATCH {key}:{ln} expected {sub!r} got {got!r}")
print(f"{len(ANCHORS) - sum(1 for k,l,s in ANCHORS if s and s not in (cache[k][l-1] if 0 < l <= len(cache[k]) else ''))}/{len(ANCHORS)} anchors verified")

h4 = [i for i, ln in enumerate(lines) if ln.startswith("## Finding 4")]
h5 = [i for i, ln in enumerate(lines) if ln.startswith("## Finding 5")]
ok_sections = len(h4) == 1 and len(h5) == 1 and h4[0] < h5[0]
print(f"sections: finding4={len(h4)} finding5={len(h5)} ordered={h4[0] < h5[0]}")
sev = (re.search(r"— (BLOCKER|HIGH|MEDIUM|LOW|OK)\s*$", lines[h4[0]]),
       re.search(r"— (BLOCKER|HIGH|MEDIUM|LOW|OK)\s*$", lines[h5[0]]))
ok_sev = all(sev)
print(f"severity tags: {sev[0].group(1) if sev[0] else None} / "
      f"{sev[1].group(1) if sev[1] else None}")
sys.exit(1 if (bad or not ok_sections or not ok_sev) else 0)
