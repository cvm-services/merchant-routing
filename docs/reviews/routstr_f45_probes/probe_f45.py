#!/usr/bin/env python3
"""Read-only hermetic probe for findings 4/5 (atomicity/idempotence, SLA).

Touches only tempfile.mkdtemp() paths; modifies no artifact. Exercises the
real main() with an injected fake backend.
"""
import contextlib
import io
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.expanduser("~/.hermes/bot/scripts"))
import routstr_delist as rd  # noqa: E402


class FakeBackend:
    def __init__(self, mode):
        self.mode = mode

    def pull(self, dry_run=False, deadline=None):
        if self.mode in ("ok", "flake"):
            return {"ok": True, "action": "pull", "pulled": ["A", "B"], "rc": 0}
        return {"ok": False, "action": "pull", "rc": 255, "error": "ssh down"}

    def verify(self, dry_run=False, deadline=None):
        if self.mode == "ok":
            return {"ok": True, "action": "verify", "count": 0, "rc": 0}
        return {"ok": False, "action": "verify", "rc": 255, "error": "ssh down"}


def run(argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = rd.main(argv)
    raw = buf.getvalue()
    return rc, (json.loads(raw) if raw.strip() else {})


tmp = tempfile.mkdtemp(prefix="f45probe_")
ov = os.path.join(tmp, "ov")

# --- Probe 5.3: SLA boundary arithmetic -----------------------------------
print("PROBE 5.3 POLL=%s BUDGET=%s SSH=%s WINDOW=%s" % (
    rd.POLL_CADENCE_S, rd.ACTION_BUDGET_S, rd.SSH_TIMEOUT_S,
    rd.TRIGGER_ACTION_WINDOW_S))
print("  POLL+BUDGET=%s  (< WINDOW? %s)" % (
    rd.POLL_CADENCE_S + rd.ACTION_BUDGET_S,
    rd.POLL_CADENCE_S + rd.ACTION_BUDGET_S < rd.TRIGGER_ACTION_WINDOW_S))
print("  240+30+30=%s  (<300? %s)" % (
    rd.POLL_CADENCE_S + rd.SSH_TIMEOUT_S + rd.SSH_TIMEOUT_S,
    rd.POLL_CADENCE_S + rd.SSH_TIMEOUT_S + rd.SSH_TIMEOUT_S < 300))

# --- Probe 4.2: unmakeable state path -> save_state False discarded -------
blocker = os.path.join(tmp, "blocker")
with open(blocker, "w") as fh:
    fh.write("x")
state_unmakeable = os.path.join(blocker, "state.json")  # parent is a file
rd._SshBackend = lambda t, c: FakeBackend("ok")
rc, out = run(["--state", state_unmakeable, "--override", ov, "--manual"])
print("PROBE 4.2 rc=%s action=%s state_exists=%s" % (
    rc, out.get("action"), os.path.exists(state_unmakeable)))

# --- Probe 4.3: failure path falsifies a durable delisted=true flag -------
state2 = os.path.join(tmp, "s2.json")
ov2 = os.path.join(tmp, "ov2")
rd._SshBackend = lambda t, c: FakeBackend("ok")
rc1, out1 = run(["--state", state2, "--override", ov2, "--manual"])
print("PROBE 4.3 run1 rc=%s delisted=%s pulled=%s" % (
    rc1, rd.load_state(state2).get("delisted"),
    rd.load_state(state2).get("pulled_models")))
rd._SshBackend = lambda t, c: FakeBackend("flake")   # pull ok, verify flakes
rc2, out2 = run(["--state", state2, "--override", ov2, "--manual"])
st2 = rd.load_state(state2)
print("  run2 rc=%s action=%s delisted=%s fails=%s" % (
    rc2, out2.get("action"), st2.get("delisted"),
    st2.get("consecutive_failures")))
rc3, out3 = run(["--state", state2, "--override", ov2, "--delist"])
print("  run3 rc=%s action=%s blocked=%s" % (
    rc3, out3.get("action"), out3.get("blocked")))

# --- Probe 4.8: string-typed pulled_models -> wrong scoped relist ---------
rd._SshBackend = lambda t, c: FakeBackend("ok")
state3 = os.path.join(tmp, "s3.json")
with open(state3, "w") as fh:
    json.dump({"delisted": True, "pulled_models": "AB"}, fh)
captured = {}


class Recorder(FakeBackend):
    def relist(self, names=None, dry_run=False, deadline=None):
        captured["names"] = names
        return {"ok": True, "action": "relist", "rc": 0, "restored": 2}


rd._SshBackend = lambda t, c: Recorder("ok")
rc4, out4 = run(["--state", state3, "--override", ov2, "--relist"])
print("PROBE 4.8 rc=%s names=%s" % (rc4, captured.get("names")))
