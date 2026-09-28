import re
from pathlib import Path

p = Path(__file__).resolve().parents[3] / "docs" / "reviews" / "findings_1_3.md"
txt = p.read_text(encoding="utf-8")
rx = re.compile(r"(routstr_delist\.py|contract|tests|docs):(\d+)")
per_line = {}
for i, line in enumerate(txt.splitlines(), 1):
    for m in rx.finditer(line):
        per_line.setdefault(i, []).append(m.group(0))
tot = {k: 0 for k in ("routstr_delist.py", "contract", "tests", "docs")}
for i, lst in sorted(per_line.items()):
    for tok in lst:
        tot[re.match(r"[a-z_.]+", tok).group(0)] += 1
print("per-line:", {i: v for i, v in sorted(per_line.items())})
print("totals:", tot, "sum:", sum(tot.values()))
print("lines containing the token at :0 ->", [i for i, v in per_line.items()
      if any(x.endswith(":0") for x in v)])
