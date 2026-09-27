#!/usr/bin/env python3
"""Locate the kanban card that owns this fleet-offload review brief.

Scans every kanban.db under ~/.hermes/kanban/boards/ and ~/hermes-kanban/boards/
for task rows whose title/body/result mention the brief, and for comment rows
mentioning the brief or FULL_REVIEW / cross-family. Read-only.
"""
from __future__ import annotations

import glob
import sqlite3

NEEDLES = ("cross-family", "routstr v4.1", "lane wiring", "routstrd service",
           "guard iac", "deleg_17f47ac6", "routstrd-lane", "routstr-v41")
DB_GLOBS = ("/home/c03rad0r/.hermes/kanban/boards/*/kanban.db",
            "/home/c03rad0r/hermes-kanban/boards/*/kanban.db",
            "/home/c03rad0r/kanban-boards/*/kanban.db")

dbs = sorted({p for g in DB_GLOBS for p in glob.glob(g)})
print(f"{len(dbs)} board DBs")
for db in dbs:
    board = db.split("/boards/")[-1].rsplit("/", 1)[0]
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
    except Exception as e:  # noqa: BLE001
        print(f"  !! {board}: {e}")
        continue
    tables = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    task_tbl = "tasks" if "tasks" in tables else None
    if task_tbl:
        cols = [r[1] for r in con.execute(f"PRAGMA table_info({task_tbl})")]
        for r in con.execute(f"SELECT * FROM {task_tbl}"):
            blob = " ".join(str(r[c] or "") for c in cols).lower()
            if any(n.lower() in blob for n in NEEDLES):
                print(f"[{board}] TASK {r['id']} status={r['status']} title={r['title']!r}")
    for t in sorted(tables):
        if "comment" in t:
            ccols = [r[1] for r in con.execute(f"PRAGMA table_info({t})")]
            for r in con.execute(f"SELECT * FROM {t}"):
                blob = " ".join(str(r[c] or "") for c in ccols).lower()
                if any(n.lower() in blob for n in NEEDLES):
                    tid = r["task_id"] if "task_id" in ccols else "?"
                    print(f"[{board}] COMMENT on {tid} in {t}: {str(r[ccols[-1]])[:160]!r}")
    con.close()
print("done")
