#!/usr/bin/env python3
"""Claim-4 probes for the routstrd funding guard (reviewer kimi, 2026-09-27).

Read-only: every probe builds its own fixture wallet under a private temp dir.
"""
import hashlib
import importlib.util
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

GUARD = "/tmp/rv41-eng-wt/scripts/routstrd_funding_guard.py"
spec = importlib.util.spec_from_file_location("guard_probe", GUARD)
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)

MINIBITS = "https://mint.minibits.cash/Bitcoin"
ORANGE = "https://mint.orangesync.tech"

DDL = """
CREATE TABLE coco_cashu_proofs (
  mintUrl TEXT NOT NULL, id TEXT NOT NULL, amount INTEGER NOT NULL,
  secret TEXT NOT NULL, C TEXT NOT NULL, dleqJson TEXT, witnessJson TEXT,
  state TEXT NOT NULL CHECK (state IN ('inflight','ready','spent')),
  createdAt INTEGER NOT NULL, usedByOperationId TEXT, createdByOperationId TEXT,
  PRIMARY KEY (mintUrl, secret))
"""


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def mkwallet(path, proofs, *, wal=False):
    con = sqlite3.connect(str(path))
    if wal:
        con.execute("PRAGMA journal_mode=WAL")
    con.execute(DDL)
    for i, (mint, amt, st) in enumerate(proofs):
        con.execute("INSERT INTO coco_cashu_proofs (mintUrl,id,amount,secret,C,state,"
                    "createdAt) VALUES (?,?,?,?,?,?,?)",
                    (mint, f"i{i}", amt, f"s{i}", f"C{i}", st, 1758900000 + i))
    con.commit()
    return con


print("=== P1: WAL replay differential (rows resident only in -wal) ===")
d = Path(tempfile.mkdtemp(prefix="rev41-wal-"))
w = d / "coco.db"
con = mkwallet(w, [(MINIBITS, 35008, "ready"), (ORANGE, 500, "ready")], wal=True)
wal_sz = os.path.getsize(str(w) + "-wal") if os.path.exists(str(w) + "-wal") else -1
# guard technique: copy db + -wal + -shm, open copy read-write, checkpoint
try:
    guard_bal = g._read_balance_db(w)
    guard_ok = f"{guard_bal} total={sum(guard_bal.values())}"
except Exception as e:
    guard_ok = f"RAISED {type(e).__name__}: {e}"
# naive read-only / immutable reader on the LIVE file (no -wal copy)
try:
    uri = f"file:{w}?immutable=1"
    c2 = sqlite3.connect(uri, uri=True)
    tot = c2.execute("SELECT COALESCE(SUM(amount),0) FROM coco_cashu_proofs "
                     "WHERE state='ready'").fetchone()[0]
    imm = tot
    c2.close()
except Exception as e:
    imm = f"RAISED {type(e).__name__}: {e}"
try:
    c3 = sqlite3.connect(f"file:{w}?mode=ro", uri=True)
    tot2 = c3.execute("SELECT COALESCE(SUM(amount),0) FROM coco_cashu_proofs "
                      "WHERE state='ready'").fetchone()[0]
    ro = tot2
    c3.close()
except Exception as e:
    ro = f"RAISED {type(e).__name__}: {e}"
print(f"  -wal size={wal_sz}B   guard(copy+checkpoint)={guard_ok}")
print(f"  immutable=1 reader total={imm}   mode=ro reader total={ro}")
# source wallet untouched by the read?
h_before = sha(w)
g._read_balance_db(w)
print(f"  source wallet sha unchanged after read: {h_before == sha(w)}")
# cleanup temp copy con
con.close()

print()
print("=== P2: network_sats excludes the orangesync testnut ===")
print("  net(35008 minibits + 500 testnut) =",
      g.network_sats_from({MINIBITS: 35008, ORANGE: 500}),
      "| per-mint kept:", {MINIBITS: 35008, ORANGE: 500})

print()
print("=== P3: main() exit codes by wallet state (argv[0]='--balance-json') ===")


def call_main(wallet_db, home_dir):
    old = {}
    for k, v in (("HOME", str(home_dir)), ("ROUTSTRD_WALLET_DB", str(wallet_db)),
                 ("ROUTSTRD_CLI", "")):
        old[k] = os.environ.get(k)
        os.environ[k] = v
    import io
    from contextlib import redirect_stdout
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            rc = g.main(["--balance-json"])
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    return rc, buf.getvalue().strip()[:160]


# WALLET_DIR is module-level (HOME at import); emulate with a fake HOME tree
d2 = Path(tempfile.mkdtemp(prefix="rev41-home-"))
(d2 / ".routstrd" / "wallet").mkdir(parents=True)
rc, out = call_main(d2 / "nope" / "coco.db", d2)     # dir present, db missing
print(f"  B  waller dir present, db missing  -> rc={rc} out={out!r}")
d3 = Path(tempfile.mkdtemp(prefix="rev41-home2-"))   # no ~/.routstrd at all
rc, out = call_main(d3 / "nope" / "coco.db", d3)
print(f"  A  no ~/.routstrd on the host      -> rc={rc} out={out!r}")
empty = d2 / "empty.db"
empty.write_bytes(b"")
rc, out = call_main(empty, d2)
print(f"  C  0-byte legacy wallet db         -> rc={rc} out={out!r}")
zerotab = d2 / "zt.db"
sqlite3.connect(str(zerotab)).close()
rc, out = call_main(zerotab, d2)
print(f"  D  db with zero tables             -> rc={rc} out={out!r}")
noproofs = d2 / "np.db"
c = sqlite3.connect(str(noproofs))
c.execute(DDL)
c.commit()
c.close()
rc, out = call_main(noproofs, d2)
print(f"  E  schema present, zero proofs     -> rc={rc} out={out!r}")
good = d2 / "good.db"
con = mkwallet(good, [(MINIBITS, 35508, "ready"), (ORANGE, 5000, "ready")], wal=True)
rc, out = call_main(good, d2)
print(f"  F  healthy wallet (35508 net)      -> rc={rc} out={out!r}")
con.close()
print("READ_FAILED_EXIT constant =", g.READ_FAILED_EXIT)
