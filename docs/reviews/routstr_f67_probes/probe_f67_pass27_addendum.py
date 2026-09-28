#!/usr/bin/env python3
"""Pass-27 addendum probes: residual (f) delisted-flag flip on the failure
path, and housekeeping (TODO/FIXME markers, state perms). Read-only against
the deployed artifacts; all state in a disk-backed ~/.cache tree."""
from __future__ import annotations

import ast
import contextlib
import io
import json
import os
import shutil
import stat
from pathlib import Path

BOT = Path.home() / ".hermes/bot"
SCRIPT = BOT / "scripts/routstr_delist.py"
SCRATCH = Path.home() / ".cache/f67_pass27_add"
if SCRATCH.exists():
    shutil.rmtree(SCRATCH)
SCRATCH.mkdir(parents=True)

import sys
sys.path.insert(0, str(SCRIPT.parent))
import routstr_delist as rd  # noqa: E402

SRC = SCRIPT.read_text()
CHECKS = []


def chk(name, cond, detail=""):
    CHECKS.append((name, bool(cond), detail))


class Dead:
    def pull(self, dry_run=False, deadline=None):
        return {"ok": False, "action": "pull", "rc": 255, "error": "dead"}

    def verify(self, dry_run=False, deadline=None):
        return {"ok": False, "action": "verify", "rc": 255}

    def relist(self, names=None, dry_run=False, deadline=None):
        return {"ok": False, "action": "relist", "rc": 255}


class Alive:
    def __init__(self):
        self.calls = []

    def pull(self, dry_run=False, deadline=None):
        self.calls.append("pull")
        return {"ok": True, "action": "pull", "rc": 0, "pulled": ["a", "b"]}

    def verify(self, dry_run=False, deadline=None):
        self.calls.append("verify")
        return {"ok": True, "action": "verify", "rc": 0, "count": 0}

    def relist(self, names=None, dry_run=False, deadline=None):
        self.calls.append("relist")
        return {"ok": True, "action": "relist", "rc": 0}


def run_main(argv, backend):
    orig = rd._SshBackend
    rd._SshBackend = lambda t, c: backend
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out):
            rc = rd.main(argv)
    finally:
        rd._SshBackend = orig
    raw = out.getvalue()
    return rc, (json.loads(raw) if raw.strip() else {}), raw


# residual (f): a FAILED fired run forces delisted=False over a prior True
st = SCRATCH / "sf.json"
rd.save_state(str(st), {"delisted": False})
rc0, out0, _ = run_main(["--state", str(st), "--manual"], Alive())
before = rd.load_state(str(st))
chk("setup: confirmed delist sets delisted=True",
    rc0 == 0 and before.get("delisted") is True, str(before.get("delisted")))
rc1, out1, _ = run_main(["--state", str(st), "--manual"], Dead())
after = rd.load_state(str(st))
chk("6f: a failed fired run flips delisted True->False (src:726)",
    rc1 == 1 and before.get("delisted") is True and after.get("delisted") is False,
    f"before={before.get('delisted')} after={after.get('delisted')} rc={rc1}")

# quiet (no-fire) run PRESERVES the flag (src:651-653)
st2 = SCRATCH / "sf2.json"
rd.save_state(str(st2), {"delisted": True})
run_main(["--state", str(st2)], Dead())
after2 = rd.load_state(str(st2))
chk("contrast: quiet run preserves delisted=True",
    after2.get("delisted") is True, str(after2.get("delisted")))

# housekeeping: no TODO/FIXME/XXX/HACK markers
markers = [i for i, ln in enumerate(SRC.splitlines(), 1)
           if any(m in ln for m in ("TODO", "FIXME", "XXX", "HACK"))]
chk("7e: zero TODO/FIXME/XXX/HACK markers", markers == [], f"{markers}")

# save_state writes with default umask (no explicit mode)
tree = ast.parse(SRC)
chmod_calls = [n.lineno for n in ast.walk(tree) if isinstance(n, ast.Call)
               and isinstance(n.func, ast.Attribute) and n.func.attr == "chmod"]
chk("7e: no os.chmod in save_state (default umask)", chmod_calls == [],
    f"{chmod_calls}")
stp = SCRATCH / "perm.json"
rd.save_state(str(stp), {"delisted": False})
mode = stat.S_IMODE(os.stat(stp).st_mode)
umask = os.umask(0)
os.umask(umask)
chk("7e: state file mode is umask-derived (no 0600)",
    mode != 0o600, f"mode={oct(mode)} umask={oct(umask)}")

passed = sum(1 for _, ok, _ in CHECKS if ok)
print(f"pass27 addendum: {passed}/{len(CHECKS)} checks passed")
for name, ok, detail in CHECKS:
    print(f"  [{'PASS' if ok else '**FAIL**'}] {name}"
          + (f"  — {detail}" if detail else ""))
sys.exit(0 if passed == len(CHECKS) else 1)
