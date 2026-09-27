#!/usr/bin/env python3
"""Subprocess-level probes: guard + balance-cron exit codes under a fake HOME.

HOME must be set before the guard is imported/executed, because WALLET_DIR is a
module-level constant computed from Path.home() at import time.
"""
import os
import sqlite3
import subprocess
import tempfile
from pathlib import Path

GUARD = "/tmp/rv41-eng-wt/scripts/routstrd_funding_guard.py"
CRON = "/tmp/rv41-eng-wt/scripts/routstrd_balance_cron.sh"
REPO = "/tmp/rv41-eng-wt"
MINIBITS = "https://mint.minibits.cash/Bitcoin"
ORANGE = "https://mint.orangesync.tech"
DDL = ("CREATE TABLE coco_cashu_proofs (mintUrl TEXT NOT NULL, id TEXT NOT NULL,"
       " amount INTEGER NOT NULL, secret TEXT NOT NULL, C TEXT NOT NULL,"
       " dleqJson TEXT, witnessJson TEXT, state TEXT NOT NULL,"
       " createdAt INTEGER NOT NULL, usedByOperationId TEXT,"
       " createdByOperationId TEXT, PRIMARY KEY (mintUrl, secret))")


def mkhome(with_routstrd):
    h = Path(tempfile.mkdtemp(prefix="rev41-home-"))
    if with_routstrd:
        (h / ".routstrd" / "wallet").mkdir(parents=True)
    return h


def run(cmd, home, wallet_db, burn_db):
    env = dict(os.environ)
    env.update({"HOME": str(home), "ROUTSTRD_WALLET_DB": str(wallet_db),
                "ROUTSTRD_CLI": "", "ROUTSTRD_REPO": REPO,
                "API_BURN_DB": str(burn_db)})
    p = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=120)
    return p.returncode, (p.stdout + p.stderr).strip().replace("\n", " | ")[:220]


def burn(path):
    c = sqlite3.connect(str(path))
    c.execute("CREATE TABLE provider_balances (id INTEGER PRIMARY KEY, provider TEXT,"
              " collected_at REAL, usage REAL, limit_credits REAL, limit_remaining"
              " REAL, usage_fraction REAL, is_unlimited INTEGER, is_free_tier INTEGER,"
              " raw_json TEXT)")
    c.commit()
    c.close()
    return path


def rows(path):
    c = sqlite3.connect(str(path))
    try:
        n = c.execute("SELECT COUNT(*) FROM provider_balances").fetchone()[0]
    finally:
        c.close()
    return n


print("=== guard --balance-json under a fake HOME ===")
for label, with_dir, make_db in (
        ("G1 ~/.routstrd EXISTS, db missing  ", True, None),
        ("G2 ~/.routstrd ABSENT,  db missing  ", False, None),
        ("G3 ~/.routstrd EXISTS, db 0-byte    ", True, "empty"),
        ("G4 ~/.routstrd EXISTS, db healthy   ", True, "good")):
    h = mkhome(with_dir)
    db = h / ".routstrd" / "wallet" / "coco.db"
    if make_db == "empty":
        db.write_bytes(b"")
    elif make_db == "good":
        c = sqlite3.connect(str(db))
        c.execute(DDL)
        for i, (m, a, s) in enumerate([(MINIBITS, 35508, "ready"), (ORANGE, 5000, "ready"),
                                       (MINIBITS, 526, "spent")]):
            c.execute("INSERT INTO coco_cashu_proofs (mintUrl,id,amount,secret,C,state,"
                      "createdAt) VALUES (?,?,?,?,?,?,?)", (m, f"i{i}", a, f"s{i}", f"C{i}", s, 1))
        c.commit()
        c.close()
    rc, out = run(["/usr/bin/python3", GUARD, "--balance-json"], h, db, h / "b.db")
    print(f"  {label} -> rc={rc} out={out!r}")

print()
print("=== balance cron (routstrd_balance_cron.sh) — same states, row count ===")
for label, with_dir, make_db in (
        ("C1 ~/.routstrd EXISTS, db missing  ", True, None),
        ("C2 ~/.routstrd ABSENT,  db missing  ", False, None),
        ("C3 ~/.routstrd EXISTS, db 0-byte    ", True, "empty"),
        ("C4 ~/.routstrd EXISTS, db healthy   ", True, "good")):
    h = mkhome(with_dir)
    db = h / ".routstrd" / "wallet" / "coco.db"
    if make_db == "empty":
        db.write_bytes(b"")
    elif make_db == "good":
        c = sqlite3.connect(str(db))
        c.execute(DDL)
        for i, (m, a, s) in enumerate([(MINIBITS, 35508, "ready"), (ORANGE, 5000, "ready")]):
            c.execute("INSERT INTO coco_cashu_proofs (mintUrl,id,amount,secret,C,state,"
                      "createdAt) VALUES (?,?,?,?,?,?,?)", (m, f"i{i}", a, f"s{i}", f"C{i}", s, 1))
        c.commit()
        c.close()
    b = burn(h / "burn.db")
    rc, out = run(["bash", CRON], h, db, b)
    print(f"  {label} -> rc={rc} rows={rows(b)} out={out!r}")
