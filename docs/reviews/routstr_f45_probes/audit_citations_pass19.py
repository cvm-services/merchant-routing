#!/usr/bin/env python3
"""Pass-19 citation audit: every file:line cited in findings_4_5.md.

Prints the actual source line for each cited reference so the claim can be
eyeballed against the artifact. Read-only.
"""
import os

BOT = os.path.expanduser("~/.hermes/bot")
REPO = os.path.expanduser("~/repos/merchant-routing")
FILES = {
    "routstr_delist.py": f"{BOT}/scripts/routstr_delist.py",
    "contract": f"{BOT}/tests/test_routstr_delist.py",
    "docs": f"{BOT}/docs/routstr-delist.md",
    "unit": f"{REPO}/tests/test_routstr_delist.py",
}

# ref -> (file-key, [lines], what we expect to see)
CHECKS = [
    # finding 4
    ("save_state def/body", "routstr_delist.py", [221, 230, 232, 233, 234, 235, 237, 238, 239, 240, 245]),
    ("silent-persist call sites", "routstr_delist.py", [565, 622, 629, 638, 654, 710, 732, 752]),
    ("main returns", "routstr_delist.py", [557, 578, 611, 625, 632, 644, 660, 717, 739, 764]),
    ("delisted flag in update_state", "routstr_delist.py", [248, 253, 263]),
    ("--status block", "routstr_delist.py", [548, 557]),
    ("blocked branch", "routstr_delist.py", [569, 578]),
    ("unblock clear", "routstr_delist.py", [561, 567]),
    ("counter read + bool hole", "routstr_delist.py", [544, 545, 546]),
    ("bool exclusion in variance", "routstr_delist.py", [152]),
    ("delist merge", "routstr_delist.py", [744, 745, 746, 747, 749]),
    ("failed delist tick", "routstr_delist.py", [724, 730, 731]),
    ("failed relist no tick", "routstr_delist.py", [626, 628, 632]),
    ("relist success reset", "routstr_delist.py", [636, 637]),
    ("relist refuse", "routstr_delist.py", [600, 601, 602, 611, 613]),
    ("relist parametrized payload", "routstr_delist.py", [390, 397]),
    ("publish after success", "routstr_delist.py", [754, 756]),
    ("nak publish fn", "routstr_delist.py", [451, 459, 464]),
    # finding 5
    ("SLA constants", "routstr_delist.py", [71, 72, 73, 74, 75]),
    ("deadline arm sites", "routstr_delist.py", [612, 667]),
    ("_run clamp", "routstr_delist.py", [800, 803, 804, 805, 806]),
    ("retry guards", "routstr_delist.py", [675, 676, 677, 695, 696]),
    # tests
    ("contract atomic class", "contract", [628, 636, 643, 657, 663, 665, 682, 686]),
    ("contract fsync stub note", "contract", [252, 253, 254, 256, 257, 629, 634]),
    ("contract idempotence", "contract", [524, 537, 538]),
    ("contract scoped relist", "contract", [490, 507]),
    ("contract breaker", "contract", [582, 594, 599, 601, 612]),
    ("contract sla", "contract", [543, 551, 553, 574, 577]),
    ("contract loader fallback", "contract", [1, 47, 54, 92, 190]),
    ("unit pins", "unit", [273, 282, 284, 289, 296, 298, 1017, 1035, 1039, 1053, 1056]),
    # docs
    ("docs delist flag", "docs", [122, 123]),
    ("docs failure semantics", "docs", [64, 68, 76, 79]),
    ("docs relist rules", "docs", [29, 32]),
    ("docs sla", "docs", [96, 100, 103, 106]),
    ("docs deployment", "docs", [112, 115]),
    ("original review refs", None, [158, 194, 196, 234]),
]

src_cache = {}
for key, path in FILES.items():
    with open(path, encoding="utf-8") as fh:
        src_cache[key] = fh.readlines()

if None not in [c[1] for c in CHECKS]:
    pass

for label, key, lines in CHECKS:
    if key is None:
        continue
    rows = src_cache[key]
    print(f"\n--- {label} [{key}] ---")
    for n in lines:
        txt = rows[n - 1].rstrip() if 0 < n <= len(rows) else "<OUT OF RANGE>"
        print(f"{key}:{n}| {txt[:150]}")

# original review doc refs
print("\n--- original review doc ---")
with open(f"{REPO}/docs/reviews/routstr_delist_review.md", encoding="utf-8") as fh:
    orig = fh.readlines()
for n in (158, 194, 196, 234):
    print(f"review:{n}| {orig[n-1].rstrip()[:150]}")
