#!/usr/bin/env python3
"""Verify the findings_4_5.md acceptance criteria (pass 17) and sync to the
mandated bot path. Read-only w.r.t. the three reviewed artifacts."""
import hashlib
import re
import shutil
from pathlib import Path

REPO = Path("/home/c03rad0r/repos/merchant-routing/docs/reviews/findings_4_5.md")
BOT = Path("/home/c03rad0r/.hermes/bot/docs/reviews/findings_4_5.md")
ARTIFACTS = [
    Path("/home/c03rad0r/.hermes/bot/scripts/routstr_delist.py"),
    Path("/home/c03rad0r/repos/merchant-routing/src/routstr_delist.py"),
    Path("/home/c03rad0r/.hermes/bot/tests/test_routstr_delist.py"),
    Path("/home/c03rad0r/repos/merchant-routing/tests/test_routstr_delist_contract.py"),
]
EXPECT = {
    "/home/c03rad0r/.hermes/bot/scripts/routstr_delist.py":
        "2ea724ef08d857cd7b88a957300e70b4",
    "/home/c03rad0r/repos/merchant-routing/src/routstr_delist.py":
        "2ea724ef08d857cd7b88a957300e70b4",
    "/home/c03rad0r/.hermes/bot/tests/test_routstr_delist.py":
        "031851b356f0de4089512f02f13f05cc",
    "/home/c03rad0r/repos/merchant-routing/tests/test_routstr_delist_contract.py":
        "031851b356f0de4089512f02f13f05cc",
}

txt = REPO.read_text()
lines = txt.splitlines()
sections = [l for l in lines if l.startswith("## Finding")]
sev = re.findall(
    r"## Finding (\d) —[^\n]*\*\*(BLOCKER|HIGH|MEDIUM|LOW|OK)\*\*", txt)
refs = sorted(set(re.findall(
    r"(?:routstr_delist\.py|contract|docs|unit|src):\d+", txt)))
item_heads = [l for l in lines if re.match(r"\*\*\d+\.\d+ —", l)]

# severity tag per item block (headers wrap on 5.3/5.6/5.7 -> scan the block)
blocks, cur = [], None
for l in lines:
    if re.match(r"\*\*\d+\.\d+ —", l):
        if cur:
            blocks.append("\n".join(cur))
        cur = [l]
    elif cur is not None:
        cur.append(l)
if cur:
    blocks.append("\n".join(cur))
item_sev = []
for b in blocks:
    m = re.search(r"(BLOCKER|HIGH|MEDIUM|LOW|OK)[^*]*\*\*", b)
    item_sev.append(m.group(1) if m else "??")

print(f"file_exists={REPO.is_file()} lines={len(lines)} chars={len(txt)}")
print(f"sections={len(sections)} -> {[s[:34] for s in sections]}")
print(f"section_severities={sev}")
print(f"numbered_items={len(item_heads)} item_severities={item_sev}")
print(f"file_line_refs={len(refs)} sample={refs[:6]}")
print(f"HIGH_missing_report={'MISSING — HIGH' in txt}")
print("artifact_paths_named_in_report=" + str(all(
    p in txt for p in ("~/.hermes/bot/docs/routstr_delist_contract.md",
                       "~/.hermes/bot/scripts/routstr_delist.py",
                       "~/.hermes/bot/tests/test_routstr_delist.py"))))
print(f"probe_lines_quoted={txt.count('PASS')}  probe_ref="
      f"{'probe_f45_pass17.py' in txt}")

hashes = {}
for a in ARTIFACTS:
    h = hashlib.md5(a.read_bytes()).hexdigest()
    hashes[str(a)] = h
print("artifact_hashes_unchanged=" + str(
    all(hashes[str(a)] == EXPECT[str(a)] for a in ARTIFACTS)))

ok = (REPO.is_file() and len(sections) == 2 and len(sev) == 2
      and "MISSING — HIGH" in txt and refs and item_heads
      and all(h == EXPECT[str(a)] for a, h in hashes.items()))
if ok:
    BOT.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(REPO, BOT)
    rb, bb = REPO.read_bytes(), BOT.read_bytes()
    print(f"copied -> {BOT} bytes={len(bb)} "
          f"byte_identical={rb == bb} sha256={hashlib.sha256(bb).hexdigest()}")
print("ACCEPTANCE", "PASS" if ok else "FAIL")
