#!/usr/bin/env python3
"""Read-only probe of the LIVE routstrd wallet + the funding guard's read paths.

Writes nothing outside a private temp dir. Never mutates the live wallet.
"""
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

WALLET = Path.home() / ".routstrd" / "wallet" / "coco.db"
LEGACY = Path.home() / ".cocod" / "coco.db"
GUARD = Path("/tmp/rv41_guard.py")   # copy of scripts/routstrd_funding_guard.py @8b91148
print("### host=%s date=%s" % (os.uname().nodename, subprocess.run(
    ["date", "-Is"], capture_output=True, text=True).stdout.strip()))
print("### wallet:", WALLET, "exists=", WALLET.exists(),
      "size=", WALLET.stat().st_size if WALLET.exists() else None)
for suf in ("-wal", "-shm"):
    p = Path(str(WALLET) + suf)
    print("###   %s exists=%s size=%s" % (suf, p.exists(), p.stat().st_size if p.exists() else None))
print("### legacy:", LEGACY, "exists=", LEGACY.exists(),
      "size=", LEGACY.stat().st_size if LEGACY.exists() else None)

# 1. immutable=1 / mode=ro reader straight off the LIVE file (the naive technique)
try:
    con = sqlite3.connect("file:%s?immutable=1" % WALLET, uri=True)
    rows = con.execute("SELECT mintUrl, SUM(amount) FROM coco_cashu_proofs "
                       "WHERE state='ready' GROUP BY mintUrl").fetchall()
    n = con.execute("SELECT COUNT(*) FROM coco_cashu_proofs").fetchone()[0]
    con.close()
    print("### IMMUTABLE reader: proofs=%d per-mint=%s" % (n, dict(rows)))
except Exception as e:
    print("### IMMUTABLE reader FAILED:", type(e).__name__, e)

# 2. read-only (not immutable) URI against the LIVE file
try:
    con = sqlite3.connect("file:%s?mode=ro" % WALLET, uri=True)
    rows = con.execute("SELECT mintUrl, SUM(amount) FROM coco_cashu_proofs "
                       "WHERE state='ready' GROUP BY mintUrl").fetchall()
    con.close()
    print("### MODE=RO reader: per-mint=%s" % dict(rows))
except Exception as e:
    print("### MODE=RO reader FAILED:", type(e).__name__, e)

# 3. the GUARD's own technique (copy db+wal+shm, open copy rw, checkpoint)
tmp = tempfile.mkdtemp(prefix="rv41-probe-")
dst = Path(tmp) / "coco.db"
for suf in ("", "-wal", "-shm"):
    s = Path(str(WALLET) + suf)
    if s.exists():
        shutil.copy2(s, str(dst) + suf)
try:
    con = sqlite3.connect(str(dst))
    con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    rows = con.execute("SELECT mintUrl, SUM(amount) FROM coco_cashu_proofs "
                       "WHERE state='ready' GROUP BY mintUrl").fetchall()
    n = con.execute("SELECT COUNT(*) FROM coco_cashu_proofs").fetchone()[0]
    con.close()
    print("### COPY+CHECKPOINT reader: proofs=%d per-mint=%s" % (n, dict(rows)))
finally:
    shutil.rmtree(tmp, ignore_errors=True)

# 4. run the guard in --balance-json mode against the LIVE wallet (read-only mode)
r = subprocess.run([sys.executable, str(GUARD), "--balance-json"],
                   capture_output=True, text=True, timeout=120,
                   env={**os.environ, "ROUTSTRD_CLI": ""})
print("### guard --balance-json rc=%d stdout=%s stderr=%s" % (r.returncode, r.stdout.strip(), r.stderr.strip()))

# 5. guard with a MISSING wallet db (its "not installed here" vs fail-loud gate)
r = subprocess.run([sys.executable, str(GUARD), "--balance-json"],
                   capture_output=True, text=True, timeout=120,
                   env={**os.environ, "ROUTSTRD_CLI": "",
                        "ROUTSTRD_WALLET_DB": "/tmp/rv41-absent/nope/coco.db"})
print("### guard missing-wallet-db rc=%d stdout=%s" % (r.returncode, r.stdout.strip()))

# 6. guard with an EMPTY (0-byte) wallet db
empty = Path("/tmp/rv41-empty-coco.db")
empty.write_bytes(b"")
r = subprocess.run([sys.executable, str(GUARD), "--balance-json"],
                   capture_output=True, text=True, timeout=120,
                   env={**os.environ, "ROUTSTRD_CLI": "",
                        "ROUTSTRD_WALLET_DB": str(empty)})
print("### guard empty-wallet-db rc=%d stdout=%s" % (r.returncode, r.stdout.strip()[:300]))
empty.unlink(missing_ok=True)
