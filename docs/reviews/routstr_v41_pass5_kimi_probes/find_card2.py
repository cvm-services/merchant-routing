#!/usr/bin/env python3
"""Surface 5b: every task/comment anywhere mentioning routstr (title or body)."""
from __future__ import annotations

import glob
import sqlite3

dbs = sorted(glob.glob("/home/c03rad0r/.hermes/kanban/boards/*/kanban.db") +
             glob.glob("/home/c03rad0r/hermes-kanban/boards/*/kanban.db"))
for db in dbs:
    board = db.split("/boards/")[-1].rsplit("/", 1)[0]
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
    except Exception:  # noqa: BLE001
        continue
    try:
        for r in con.execute("SELECT id,title,status,assignee FROM tasks"):
            t = (r["title"] or "").lower()
            if "routstr" in t:
                print(f"[{board}] {r['id']} {r['status']} ({r['assignee']}): {r['title'][:110]}")
    except Exception:  # noqa: BLE001
        pass
    con.close()
print("done")
