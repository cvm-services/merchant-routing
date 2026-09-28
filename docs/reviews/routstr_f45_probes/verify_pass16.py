#!/usr/bin/env python3
"""Verify the findings_4_5.md acceptance criteria + copy to the bot path."""
import re
import shutil
from pathlib import Path

REPO = Path("/home/c03rad0r/repos/merchant-routing/docs/reviews/findings_4_5.md")
BOT = Path("/home/c03rad0r/.hermes/bot/docs/reviews/findings_4_5.md")

txt = REPO.read_text()
lines = txt.splitlines()

sections = [l for l in lines if l.startswith("## Finding")]
sev = re.findall(r"## Finding (\d) —[^\n]*\*\*(BLOCKER|HIGH|MEDIUM|LOW|OK)\*\*",
                 txt)
refline = re.findall(r"(?:routstr_delist\.py|contract|docs|unit|src):\d+", txt)
item_heads = [l for l in lines if re.match(r"\*\*\d+\.\d+ —", l)]
# severity tag inside each item block (items 5.3/5.6/5.7 headlines wrap, so
# scan the block text, not just the header line)
blocks = []
cur = None
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
print(f"sections={len(sections)} -> {[s[:40] for s in sections]}")
print(f"section_severities={sev}")
print(f"numbered_items={len(item_heads)} item_severities={item_sev}")
print(f"file_line_refs={len(refline)} e.g. {sorted(set(refline))[:8]}")
print(f"HIGH_missing_report={'MISSING — HIGH' in txt}")
print(f"artifact_paths_named={all(p in txt for p in ('~/.hermes/bot/docs/routstr_delist_contract.md','~/.hermes/bot/scripts/routstr_delist.py','~/.hermes/bot/tests/test_routstr_delist.py'))}")

ok = (REPO.is_file() and len(sections) == 2 and len(sev) == 2
      and item_sev and refline and "MISSING — HIGH" in txt)
if ok:
    BOT.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(REPO, BOT)
    print(f"copied -> {BOT} ({BOT.stat().st_size} bytes)")
print("ACCEPTANCE", "PASS" if ok else "FAIL")
