#!/usr/bin/env python3
"""Citation verifier for docs/reviews/findings_6_7.md (pass 28).

Extracts every `src:N`, `src:N-M`, `contract:N`, `contract:N-M`, `docs:N`,
`docs:N-M` reference — including the abbreviated `:N` / `:N-M` forms that
continue the most recent file prefix — and asserts each cited line/range
exists in the corresponding artifact, is non-blank, and is not beyond EOF.

Read-only. Exits 0 iff every citation resolves.
"""
from __future__ import annotations

import hashlib
import pathlib
import re
import sys

REPO = pathlib.Path("/home/c03rad0r/repos/merchant-routing")
BOT = pathlib.Path.home() / ".hermes/bot"

DOC = REPO / "docs/reviews/findings_6_7.md"

TARGETS = {
    "src": BOT / "scripts/routstr_delist.py",
    "contract": BOT / "tests/test_routstr_delist.py",
    "docs": BOT / "docs/routstr-delist.md",
}

EXPECT_MD5 = {
    "src": "2ea724ef08d857cd7b88a957300e70b4",
    "contract": "031851b356f0de4089512f02f13f05cc",
    "docs": "e385af98b9c142eec736672d4dcca290",
}

TEXT = DOC.read_text()
LINES = {k: p.read_text().splitlines() for k, p in TARGETS.items()}

# Citation forms: prefixed `src:N[-M]` / `contract:N[-M]` / `docs:N[-M]`,
# or the abbreviation `:N[-M]` (colon REQUIRED) continuing the last prefix.
TOKEN = re.compile(
    r"(?:(src|contract|docs):(\d+)(?:-(\d+))?)|(?::(\d+)(?:-(\d+))?)")
PREFIX = re.compile(r"\b(src|contract|docs)$")

failures: list[str] = []
resolved = 0
prefix = None
total_refs = 0
per_target: dict[str, int] = {}

# Scan each full line. To avoid counting prose numbers ("3 consecutive",
# "829 lines", "0.71 s"), a citation must carry a colon: either a prefixed
# form `src:N` / `contract:N` / `docs:N` (optionally a `N-M` range) or the
# abbreviated continuation form `:N` seen inside citation lists.
for lineno, raw_line in enumerate(TEXT.splitlines(), 1):
    for tm in TOKEN.finditer(raw_line):
        if tm.group(1):
            name, start, end = tm.group(1), int(tm.group(2)), tm.group(3)
            prefix = name
        else:
            start, end = int(tm.group(4)), tm.group(5)
            # the abbreviation is only a citation if the colon immediately
            # follows a file prefix token (e.g. "`src:565`, `:622`") or sits
            # inside a citation list — never bare prose like "ts: 1"
            before = raw_line[:tm.start()]
            if not (PREFIX.search(before)
                    or re.search(r"[,;(]\s*$", before)
                    or prefix is None):
                continue
        target = prefix
        total_refs += 1
        lines = LINES[target]
        hi = int(end) if end else start
        if not (1 <= start <= len(lines)) or not (1 <= hi <= len(lines)):
            failures.append(
                f"L{lineno}: {target}:{start}{'-' + str(hi) if end else ''} "
                f"out of range (file has {len(lines)} lines)")
            continue
        if start == hi and not lines[start - 1].strip():
            failures.append(f"L{lineno}: {target}:{start} is a BLANK line")
            continue
        resolved += 1
        per_target[target] = per_target.get(target, 0) + 1

# md5 identity of every cited artifact
for key, path in TARGETS.items():
    got = hashlib.md5(path.read_bytes()).hexdigest()
    if got != EXPECT_MD5[key]:
        failures.append(f"{key}: md5 {got} != pinned {EXPECT_MD5[key]}")

# structural requirements: exactly two finding sections, each with a severity
heads = [ln for ln in TEXT.splitlines() if ln.startswith("## Finding")]
sev6 = [ln for ln in heads if ln.startswith("## Finding 6")]
sev7 = [ln for ln in heads if ln.startswith("## Finding 7")]
if len(heads) != 2:
    failures.append(f"expected exactly 2 `## Finding` sections, found {len(heads)}")
for ln in heads:
    if not re.search(r"\*\*(OK|BLOCKER|HIGH|MEDIUM|LOW)\*\*", ln):
        failures.append(f"section lacks a severity tag: {ln[:70]}")
if not sev6 or not sev7:
    failures.append("Finding 6 and/or Finding 7 section missing")

print(f"citation tokens seen : {total_refs}")
print(f"resolved             : {resolved}")
for k in sorted(per_target):
    print(f"  {k}: {per_target[k]}")
print(f"finding sections     : {len(heads)}")
for ln in heads:
    print(f"  {ln}")
print(f"failures             : {len(failures)}")
for f in failures:
    print(f"  FAIL {f}")
print("RESULT:", "PASS" if not failures else "FAIL")
raise SystemExit(0 if not failures else 1)
