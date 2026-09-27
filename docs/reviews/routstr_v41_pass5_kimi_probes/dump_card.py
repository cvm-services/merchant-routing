#!/usr/bin/env python3
"""Dump one kanban card (task row + its comments) read-only."""
from __future__ import annotations

import sqlite3
import sys

DB = "/home/c03rad0r/.hermes/kanban/boards/merchant-routing/kanban.db"
TID = sys.argv[1] if len(sys.argv) > 1 else "t_774ac9ec"

con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
con.row_factory = sqlite3.Row
cols = [r[1] for r in con.execute("PRAGMA table_info(tasks)")]
for r in con.execute("SELECT * FROM tasks WHERE id=?", (TID,)):
    for c in cols:
        v = r[c]
        if v in (None, ""):
            continue
        s = str(v)
        print(f"{c} = {s if len(s) < 1500 else s[:1500] + '…'}")
print("\n=== comments ===")
tables = {x[0] for x in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
for t in sorted(tables):
    if "comment" not in t:
        continue
    ccols = [r[1] for r in con.execute(f"PRAGMA table_info({t})")]
    if "task_id" not in ccols:
        continue
    for r in con.execute(f"SELECT * FROM {t} WHERE task_id=?", (TID,)):
        body = r["body"] if "body" in ccols else r[ccols[-1]]
        who = r["author"] if "author" in ccols else "?"
        print(f"--- {t} by {who} ---\n{str(body)[:2500]}\n")
con.close()
