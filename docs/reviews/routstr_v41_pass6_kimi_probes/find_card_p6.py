#!/usr/bin/env python3
"""Bounded card-resolution sweep: find the kanban card this review belongs to.

Surfaces (per the fleet's 5-surface rule):
 1. task title LIKE '%cross-family%' or '%REVIEW (%'
 2. title/body/result for the brief's key phrases
 3. comments tables for the same phrases
 4. the author's dispatch id (deleg_17f47ac6)
 5. any non-terminal task with 'routstr' in the title
"""
import sqlite3
import glob
import os

ROOTS = [
    os.path.expanduser("~/.hermes/kanban/boards"),
    os.path.expanduser("~/hermes-kanban/boards"),
]

PHRASES = [
    "deleg_17f47ac6",
    "v4.1 lane wiring",
    "lane wiring",
    "routstrd service",
    "guard iac",
    "routstr",
    "cross-family",
]

TASK_CANDIDATES = set()
COMMENT_HITS = []

for root in ROOTS:
    for db in sorted(glob.glob(os.path.join(root, "*", "kanban.db"))):
        board = os.path.basename(os.path.dirname(db))
        try:
            con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
            con.row_factory = sqlite3.Row
        except sqlite3.Error:
            continue
        try:
            tabs = [r[0] for r in con.execute(
                "select name from sqlite_master where type='table'")]
            cols = {}
            for t in tabs:
                cols[t] = [r[1] for r in con.execute(f"pragma table_info({t})")]
            if "tasks" in cols:
                tsel = [c for c in ("id", "title", "status", "assignee") if c in cols["tasks"]]
                for row in con.execute(f"select {','.join(tsel)} from tasks"):
                    d = dict(zip(tsel, row))
                    blob = " ".join(str(x) for x in row)
                    for p in PHRASES:
                        if p and p.lower() in blob.lower():
                            TASK_CANDIDATES.add((board, d.get("id"), d.get("status"),
                                                 (d.get("title") or "")[:80], p))
                            break
            for t in tabs:
                if "comment" not in t.lower():
                    continue
                ccols = cols[t]
                textcol = next((c for c in ("body", "content", "text", "message")
                                if c in ccols), None)
                if not textcol:
                    continue
                idcol = next((c for c in ("task_id", "card_id") if c in ccols), None)
                for row in con.execute(f"select * from {t}"):
                    r = dict(zip(ccols, row))
                    blob = str(r.get(textcol) or "")
                    for p in ("deleg_17f47ac6", "v4.1 lane wiring", "FULL_REVIEW"):
                        if p.lower() in blob.lower():
                            COMMENT_HITS.append((board, t, r.get(idcol), p,
                                                 blob[:120].replace("\n", " ")))
                            break
        except sqlite3.Error as e:
            print(f"ERR {board}: {e}")
        finally:
            con.close()

print("=== TASK HITS ===")
for h in sorted(TASK_CANDIDATES):
    print(h)
print(f"total task hits: {len(TASK_CANDIDATES)}")
print("=== COMMENT HITS ===")
for h in COMMENT_HITS[:40]:
    print(h)
print(f"total comment hits: {len(COMMENT_HITS)}")
