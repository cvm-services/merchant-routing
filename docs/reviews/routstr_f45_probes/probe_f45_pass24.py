#!/usr/bin/env python3
"""24th-pass independent re-derivation of routstr delist findings 4-5.

Drives the DEPLOYED script in-process (fake backend executing the REAL
payload builders against an in-memory sqlite sell node, fake monotonic clock,
real on-disk state in tempdirs, forced os.replace failures). Every number
printed here is produced by executing the shipped code, not quoted from a
prior pass.

Scratch lives under the repo (never /tmp).
"""
from __future__ import annotations

import builtins
import contextlib
import importlib.util
import io
import json
import os
import re
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time
import types
from pathlib import Path

DEPLOYED = Path.home() / ".hermes/bot" / "scripts" / "routstr_delist.py"
spec = importlib.util.spec_from_file_location("rd_deployed", DEPLOYED)
rd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rd)

ADVERTISED = ["gpt-4o", "claude-3-5-sonnet", "llama-3.1-405b"]
OPERATOR_DISABLED = ["operator-disabled-model"]
PROVIDERS = [("openrouter", 1, 20.0), ("routstr", 1, 10.0), ("zai", 1, 30.0)]

OUT = []


def emit(tag, **facts):
    OUT.append((tag, facts))
    print(f"[{tag}] " + " ".join(f"{k}={v!r}" for k, v in facts.items()), flush=True)


def pred(key="zai", window="1h", hours=10.0, unc=0.05):
    return {"key": key, "window": window,
            "exhausts_in_hours": hours, "uncertainty": unc}


class FakeTime:
    def __init__(self):
        self._mono = 0.0

    def monotonic(self):
        return self._mono

    @staticmethod
    def time():
        return time.time()

    def advance(self, s):
        self._mono += s

    @property
    def now(self):
        return self._mono


class FakeNode:
    def __init__(self, tmpdir: Path):
        self._uri = f"file:rdprobe{os.getpid()}x{id(self):x}?mode=memory&cache=shared"
        con = self._connect()
        con.execute("CREATE TABLE models (name TEXT PRIMARY KEY, enabled INTEGER NOT NULL)")
        for n in ADVERTISED:
            con.execute("INSERT INTO models VALUES (?,1)", (n,))
        for n in OPERATOR_DISABLED:
            con.execute("INSERT INTO models VALUES (?,0)", (n,))
        con.execute("CREATE TABLE upstream_providers (name TEXT PRIMARY KEY, enabled INTEGER NOT NULL, weight REAL NOT NULL)")
        for row in PROVIDERS:
            con.execute("INSERT INTO upstream_providers VALUES (?,?,?)", row)
        con.commit()
        self._con = con
        self.calls = []
        self.deadline_log = []
        self.ssh_down = False
        self.pull_lands = True
        self.round_trip_s = 0.0
        shim = types.ModuleType("sqlite3")
        shim.connect = self._connect
        self._sqlite3 = shim

    def _connect(self, _p=None):
        return sqlite3.connect(self._uri, uri=True)

    def models_map(self):
        return dict(self._con.execute("SELECT name, enabled FROM models"))

    def providers_snapshot(self):
        return list(self._con.execute("SELECT name, enabled, weight FROM upstream_providers ORDER BY name"))

    def kinds(self):
        return [k for k, _ in self.calls]

    def _import(self, name, globals=None, locals=None, fromlist=(), level=0):
        if name == "sqlite3":
            return self._sqlite3
        return builtins.__import__(name, globals, locals, fromlist, level)

    def execute(self, kind, payload):
        revert = None
        if kind == "pull" and not self.pull_lands:
            revert = self.models_map()
        out = io.StringIO()
        g = {"__builtins__": {"__import__": self._import, "print": print}}
        with contextlib.redirect_stdout(out):
            exec(payload, g)
        if revert is not None:
            con = self._connect()
            for name, enabled in revert.items():
                con.execute("UPDATE models SET enabled=? WHERE name=?", (enabled, name))
            con.commit()
            con.close()
        return json.loads(out.getvalue().strip().splitlines()[-1])


class NodeBackend:
    def __init__(self, node, clock):
        self.node = node
        self.clock = clock

    def pull(self, dry_run=False, deadline=None):
        return self._rt("pull", rd.pull_listing_payload(), dry_run, deadline)

    def verify(self, dry_run=False, deadline=None):
        return self._rt("verify", rd.verify_pull_payload(), dry_run, deadline)

    def relist(self, names=None, dry_run=False, deadline=None):
        return self._rt("relist", rd.relist_payload(names or []), dry_run, deadline)

    def _rt(self, kind, payload, dry_run, deadline):
        timeout = rd.SSH_TIMEOUT_S
        if deadline is not None:
            remaining = deadline - self.clock.monotonic()
            self.node.deadline_log.append({
                "kind": kind, "t": self.clock.monotonic(),
                "remaining": remaining,
                "timeout": min(rd.SSH_TIMEOUT_S, max(remaining, 0.0)),
            })
            if remaining <= 0:
                return {"ok": False, "action": kind, "error": "action budget exhausted"}
            timeout = min(rd.SSH_TIMEOUT_S, remaining)
        if dry_run:
            return {"ok": True, "dry_run": True, "action": kind}
        self.node.calls.append((kind, payload))
        if self.node.ssh_down:
            return {"ok": False, "action": kind, "rc": 255, "error": "ssh refused (simulated)"}
        # real subprocess.run(timeout=...) semantics: a round-trip that would
        # exceed the clamped timeout is killed AT the timeout (TimeoutExpired
        # -> except -> ok False), and only `timeout` seconds are charged.
        if self.node.round_trip_s > timeout:
            self.clock.advance(timeout)
            return {"ok": False, "action": kind, "error": f"timed out after {timeout}s"}
        data = self.node.execute(kind, payload)
        self.clock.advance(self.node.round_trip_s)
        return {"action": kind, "rc": 0, **data, "ok": data.get("ok") is True}


class Rig:
    def __init__(self, tmp: Path):
        self.tmp = tmp
        self.node = FakeNode(tmp)
        self.clock = FakeTime()
        self.state = tmp / "routstr_delist_state.json"
        self.override = tmp / "routstr_delist.override"
        self._orig_backend = rd._SshBackend
        self._orig_time = rd.time
        rd._SshBackend = lambda t, c: NodeBackend(self.node, self.clock)
        rd.time = self.clock

    def close(self):
        rd._SshBackend = self._orig_backend
        rd.time = self._orig_time

    def write_preds(self, preds, name="preds.json"):
        p = self.tmp / name
        p.write_text(json.dumps(preds))
        return p

    def run(self, *argv, preds=None):
        full = ["--state", str(self.state), "--override", str(self.override)]
        if preds is not None:
            full += ["--preds", str(preds)]
        full += list(argv)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = rd.main(full)
        raw = out.getvalue()
        return rc, (json.loads(raw) if raw.strip() else {}), raw


def seed(state_path: Path, obj):
    state_path.write_text(json.dumps(obj, indent=2, sort_keys=True))


def seed_raw(state_path: Path, text):
    state_path.write_text(text)


class no_fsync:
    def __enter__(self):
        self._orig = getattr(os, "fsync", None)
        os.fsync = lambda fd: None
        return self

    def __exit__(self, *a):
        os.fsync = self._orig


class spy_replace:
    """Force os.replace to fail for the state path (persist-failure injection)."""

    def __init__(self, targets):
        self.targets = {str(t) for t in targets}
        self.attempts = 0

    def __enter__(self):
        self._orig = os.replace

        def fake(src, dst):
            if str(dst) in self.targets:
                self.attempts += 1
                raise OSError("simulated persist failure (ENOSPC)")
            return self._orig(src, dst)

        os.replace = fake
        return self

    def __exit__(self, *a):
        os.replace = self._orig


def spy_protocol(records):
    """Record fsync fd kinds and replace swaps for the atomicity probe."""
    orig_fsync, orig_replace = os.fsync, os.replace

    def fsync(fd):
        try:
            st = os.fstat(fd)
            records.setdefault("fsync", []).append(stat.S_ISDIR(st.st_mode))
        except Exception:
            records.setdefault("fsync", []).append("ERR")
        return None

    def replace(src, dst):
        records.setdefault("replace", []).append((str(src), str(dst)))
        return orig_replace(src, dst)

    os.fsync, os.replace = fsync, replace
    return (orig_fsync, orig_replace)


def restore_protocol(orig):
    os.fsync, os.replace = orig


# ══════════════════════════════════════════════════════════════════════════
# FINDING 4 — atomicity + idempotence
# ══════════════════════════════════════════════════════════════════════════

def p4_1_atomic_save():
    with tempfile.TemporaryDirectory(dir=str(Path.cwd())) as d:
        p = Path(d) / "state.json"
        rec = {}
        orig = spy_protocol(rec)
        try:
            ret = rd.save_state(str(p), {"delisted": True, "ts": 1})
        finally:
            restore_protocol(orig)
        litter = [x.name for x in Path(d).glob(".*tmp")]
        emit("4a_atomic_save_protocol", ret=ret,
             fsync_calls=len(rec.get("fsync", [])),
             fsync_dir_targets=rec.get("fsync", []),
             replace_calls=len(rec.get("replace", [])),
             same_dir=(len(rec.get("replace", [])) == 1 and
                       str(Path(rec["replace"][0][0]).parent) == d),
             litter=litter,
             on_disk=json.loads(p.read_text()))


def p4_2_call_sites_discard():
    src = DEPLOYED.read_text()
    lines = src.splitlines()
    sites = [i + 1 for i, ln in enumerate(lines) if re.search(r"^\s*save_state\(", ln)]
    guarded = [i + 1 for i, ln in enumerate(lines)
               if re.search(r"=\s*save_state\(|if\s+.*save_state\(|return\s+save_state\(", ln)]
    defined = [i + 1 for i, ln in enumerate(lines) if re.match(r"^def save_state", ln)]
    emit("4b_call_sites_discard_return", definition=defined,
         call_sites=sites, discarded=sites, guarded=guarded,
         main_checks_return=False)


def p4_2b_silent_persist_failure():
    with tempfile.TemporaryDirectory(dir=str(Path.cwd())) as d:
        rig = Rig(Path(d))
        try:
            seed(rig.state, {"delisted": False, "snapshot": {"zai\x1f1h": 10.0},
                             "consecutive_failures": 2, "ts": 1})
            before = rig.state.read_bytes()
            with no_fsync(), spy_replace([rig.state]) as rp:
                rc, out, _ = rig.run("--delist")
            after = rig.state.read_bytes()
            emit("4b_silent_persist_failure_main", rc=rc,
                 action=out.get("action"), ok=out.get("ok"),
                 confirmed=out.get("confirmed"),
                 replace_failures=rp.attempts,
                 disk_unchanged=(before == after),
                 disk_delisted=json.loads(after).get("delisted"))
        finally:
            rig.close()


def p4_2c_delivered_flag_not_flipped():
    with tempfile.TemporaryDirectory(dir=str(Path.cwd())) as d:
        rig = Rig(Path(d))
        try:
            seed(rig.state, {"delisted": False, "snapshot": {}, "ts": 1})
            with no_fsync(), spy_replace([rig.state]):
                rc, out, _ = rig.run("--manual")
            disk = json.loads(rig.state.read_text())
            still_on_node = sum(1 for _, e in rig.node.models_map().items() if e == 1)
            emit("4b2_delivered_flag_not_flipped", rc=rc,
                 listing_pulled=(still_on_node == 0),
                 disk_delisted=disk.get("delisted"),
                 publisher_sees=disk.get("delisted"),
                 divergence=(still_on_node == 0 and disk.get("delisted") is not True))
        finally:
            rig.close()


def p4_3_breaker_not_durable():
    with tempfile.TemporaryDirectory(dir=str(Path.cwd())) as d:
        rig = Rig(Path(d))
        try:
            seed(rig.state, {"delisted": False, "consecutive_failures": 2,
                             "blocked": False, "snapshot": {}, "ts": 1})
            rig.node.ssh_down = True
            rcs = []
            with no_fsync(), spy_replace([rig.state]):
                for _ in range(4):
                    rc, out, _ = rig.run("--manual")
                    rcs.append(rc)
            disk = json.loads(rig.state.read_text())
            rc_s, status, _ = rig.run("--status")
            emit("4b3_persist_failure_freezes_breaker", rcs=rcs,
                 disk_consecutive_failures=disk.get("consecutive_failures"),
                 disk_blocked=disk.get("blocked"),
                 status_reports_blocked=status.get("blocked"),
                 unblock_possible=bool(disk.get("blocked")))
        finally:
            rig.close()


def p4_4_no_lock():
    src = DEPLOYED.read_text()
    hits = re.findall(r"flock|fcntl|lockf|O_EXCL|threading|multiprocessing", src)
    emit("4g2_no_lock_primitives_static", hits=len(hits), found=sorted(set(hits)))


def p4_4b_last_writer_wins():
    with tempfile.TemporaryDirectory(dir=str(Path.cwd())) as d:
        rig = Rig(Path(d))
        try:
            seed(rig.state, {"delisted": False, "ts": 2, "snapshot": {}})
            stale = rd.load_state(str(rig.state))          # B reads
            a = {"ts": 3, "delisted": True, "pulled_models": ["m1"], "snapshot": {}}
            rd.save_state(str(rig.state), a)               # A commits
            b = dict(stale)                                 # B commits its stale copy
            b["ts"] = 2
            rd.save_state(str(rig.state), b)
            final = rd.load_state(str(rig.state))
            emit("4g_no_lock_last_writer_wins", final_delisted=final.get("delisted"),
                 final_ts=final.get("ts"),
                 a_transition_lost=(final.get("delisted") is not True))
        finally:
            rig.close()


def p4_5_no_dir_fsync():
    with tempfile.TemporaryDirectory(dir=str(Path.cwd())) as d:
        p = Path(d) / "state.json"
        rec = {}
        orig = spy_protocol(rec)
        try:
            ret = rd.save_state(str(p), {"delisted": True})
        finally:
            restore_protocol(orig)
        src = DEPLOYED.read_text()
        emit("4h_no_directory_fsync", ret=ret,
             fsync_targets_dir=rec.get("fsync", []),
             O_DIRECTORY_hits=len(re.findall(r"O_DIRECTORY", src)),
             os_open_hits=len(re.findall(r"os\.open\(", src)),
             dir_entry_fsync=any(rec.get("fsync", [])))


def p4_6_redelist_merge():
    with tempfile.TemporaryDirectory(dir=str(Path.cwd())) as d:
        rig = Rig(Path(d))
        try:
            seed(rig.state, {"delisted": True, "snapshot": {},
                             "pulled_models": ["m1", "m2"], "ts": 1})
            # node advertises nothing (already pulled)
            con = rig.node._connect()
            con.execute("UPDATE models SET enabled=0")
            con.commit()
            rc, out, _ = rig.run("--delist")
            st = rd.load_state(str(rig.state))
            emit("4c_redelist_merge", rc=rc, pulled=out.get("pulled"),
                 pulled_models=st.get("pulled_models"),
                 clobbered=(st.get("pulled_models") != ["m1", "m2"]))
        finally:
            rig.close()


def p4_7_relist_refused():
    with tempfile.TemporaryDirectory(dir=str(Path.cwd())) as d:
        rig = Rig(Path(d))
        try:
            seed(rig.state, {"delisted": True, "snapshot": {}, "ts": 1})
            rc, out, _ = rig.run("--relist")
            emit("4d_relist_refused", rc=rc, action=out.get("action"),
                 backend_calls=rig.node.calls)
            live = json.loads((Path.home() / ".hermes/bot/routstr_delist_state.json").read_text())
            emit("4d2_live_state_no_pulled_models", keys=sorted(live.keys()),
                 has_pulled_models=("pulled_models" in live),
                 relist_would_refuse=not live.get("pulled_models"))
        finally:
            rig.close()


def p4_8_failed_relist_no_tick():
    with tempfile.TemporaryDirectory(dir=str(Path.cwd())) as d:
        rig = Rig(Path(d))
        try:
            seed(rig.state, {"delisted": True, "consecutive_failures": 2,
                             "pulled_models": ["gpt-4o"], "snapshot": {}, "ts": 1})
            rig.node.ssh_down = True
            rc, out, _ = rig.run("--relist")
            st = rd.load_state(str(rig.state))
            emit("4e_failed_relist_no_breaker_tick", rc=rc, action=out.get("action"),
                 disk_consecutive_failures=st.get("consecutive_failures"),
                 blocked_key_present=("blocked" in st))
        finally:
            rig.close()


def p4_9_bool_counter_hole():
    with tempfile.TemporaryDirectory(dir=str(Path.cwd())) as d:
        rig = Rig(Path(d))
        try:
            seed_raw(rig.state, json.dumps({"delisted": False,
                                            "consecutive_failures": True,
                                            "snapshot": {}, "ts": 1}))
            rig.node.ssh_down = True
            rc, out, _ = rig.run("--manual")
            st = rd.load_state(str(rig.state))
            emit("4f_bool_counter_hole", rc=rc,
                 consecutive_failures=st.get("consecutive_failures"),
                 bool_accepted_as_one=(st.get("consecutive_failures") == 2))
        finally:
            rig.close()


def p4_10_failed_delist_clears_flag():
    with tempfile.TemporaryDirectory(dir=str(Path.cwd())) as d:
        rig = Rig(Path(d))
        try:
            rc1, out1, _ = rig.run("--manual")           # confirmed delist
            st1 = rd.load_state(str(rig.state))
            rig.node.ssh_down = True
            rc2, out2, _ = rig.run("--manual")           # every attempt fails
            st2 = rd.load_state(str(rig.state))
            on_node = sum(1 for _, e in rig.node.models_map().items() if e == 1)
            emit("4i_failed_delist_clears_flag", rc_ok=rc1, rc_fail=rc2,
                 flag_after_success=st1.get("delisted"),
                 flag_after_failure=st2.get("delisted"),
                 pulled_models_kept=st2.get("pulled_models"),
                 listing_still_pulled_on_node=(on_node == 0),
                 advertisement_flapped=(st1.get("delisted") is True
                                        and st2.get("delisted") is not True
                                        and on_node == 0))
        finally:
            rig.close()


def p4_11_dry_run_persist_silent():
    with tempfile.TemporaryDirectory(dir=str(Path.cwd())) as d:
        rig = Rig(Path(d))
        try:
            seed(rig.state, {"delisted": False, "snapshot": {}, "ts": 1})
            with no_fsync(), spy_replace([rig.state]):
                rc, out, _ = rig.run("--manual", "--dry-run")
            disk = json.loads(rig.state.read_text())
            emit("4j_dry_run_persist_failure_silent", rc=rc, action=out.get("action"),
                 intent_persisted=("last_dry_run" in disk),
                 disk_unchanged=("last_dry_run" not in disk))
        finally:
            rig.close()


# ══════════════════════════════════════════════════════════════════════════
# FINDING 5 — 5-minute SLA arithmetic
# ══════════════════════════════════════════════════════════════════════════

def p5_1_constants():
    emit("5a_constant_arithmetic",
         window=rd.TRIGGER_ACTION_WINDOW_S, poll=rd.POLL_CADENCE_S,
         budget=rd.ACTION_BUDGET_S, ssh=rd.SSH_TIMEOUT_S,
         attempts=rd.MAX_PULL_ATTEMPTS,
         sum_ok=(rd.POLL_CADENCE_S + rd.ACTION_BUDGET_S == rd.TRIGGER_ACTION_WINDOW_S),
         pull_plus_verify_fits=(2 * rd.SSH_TIMEOUT_S <= rd.ACTION_BUDGET_S))


def p5_2_dead_constant_audit():
    src = DEPLOYED.read_text()
    lines = src.splitlines()
    for name in ("TRIGGER_ACTION_WINDOW_S", "POLL_CADENCE_S", "ACTION_BUDGET_S",
                 "SSH_TIMEOUT_S", "MAX_PULL_ATTEMPTS"):
        uses = [i + 1 for i, ln in enumerate(lines)
                if name in ln and not re.match(rf"^{name}\s*=", ln)]
        emit("5b_constant_consumers", constant=name, consumers=uses)


def p5_3_worst_case_path():
    with tempfile.TemporaryDirectory(dir=str(Path.cwd())) as d:
        rig = Rig(Path(d))
        try:
            rig.node.round_trip_s = 25.0
            rig.clock.advance(rd.POLL_CADENCE_S)         # worst-case detection
            rc, out, _ = rig.run("--manual",
                                 preds=rig.write_preds([pred(hours=10.0)]))
            total = rig.clock.now
            emit("5c_trigger_to_verified_delist", rc=rc, action=out.get("action"),
                 confirmed=out.get("confirmed"),
                 elapsed=total, window=rd.TRIGGER_ACTION_WINDOW_S,
                 within=(total < rd.TRIGGER_ACTION_WINDOW_S),
                 deadline_log=rig.node.deadline_log)
        finally:
            rig.close()


def p5_4_budget_exhaustion():
    with tempfile.TemporaryDirectory(dir=str(Path.cwd())) as d:
        rig = Rig(Path(d))
        try:
            # each round trip costs more than SSH_TIMEOUT_S; the two attempts
            # + verify must be clamped so the action slice never exceeds budget
            rig.node.round_trip_s = 35.0
            start = rig.clock.now
            rc, out, _ = rig.run("--manual",
                                 preds=rig.write_preds([pred(hours=10.0)]))
            emit("5d_action_budget_clamp", rc=rc, action=out.get("action"),
                 confirmed=out.get("confirmed"),
                 action_elapsed=rig.clock.now - start,
                 budget=rd.ACTION_BUDGET_S,
                 within_budget=(rig.clock.now - start <= rd.ACTION_BUDGET_S),
                 timeouts=[e["timeout"] for e in rig.node.deadline_log])
        finally:
            rig.close()


def p5_4b_lying_pull_retry_clamp():
    with tempfile.TemporaryDirectory(dir=str(Path.cwd())) as d:
        rig = Rig(Path(d))
        try:
            # lying pull: self-reports ok but the UPDATE never lands, so the
            # independent verify refutes it and the bounded retry runs. Each
            # round trip costs 25 s; the clamp must keep the ACTION slice
            # inside the 60 s budget even across attempt+verify+attempt.
            rig.node.pull_lands = False
            rig.node.round_trip_s = 25.0
            start = rig.clock.now
            rc, out, _ = rig.run("--manual",
                                 preds=rig.write_preds([pred(hours=10.0)]))
            emit("5d2_lying_pull_retry_clamp", rc=rc, action=out.get("action"),
                 confirmed=out.get("confirmed"),
                 kinds=rig.node.kinds(),
                 action_elapsed=rig.clock.now - start,
                 budget=rd.ACTION_BUDGET_S,
                 within_budget=(rig.clock.now - start <= rd.ACTION_BUDGET_S),
                 timeouts=[e["timeout"] for e in rig.node.deadline_log])
        finally:
            rig.close()


def p5_4c_nak_publish_unclamped():
    src = DEPLOYED.read_text()
    lines = src.splitlines()
    nak = [i + 1 for i, ln in enumerate(lines) if "timeout=30" in ln]
    emit("5d3_nak_publish_timeout", lines=nak,
         deadline_clamped=any("deadline" in lines[i - 1] for i in nak),
         note="nak publish runs AFTER a confirmed delist and is not budget-clamped")


def p5_5_bounded_retry_on_dead_node():
    with tempfile.TemporaryDirectory(dir=str(Path.cwd())) as d:
        rig = Rig(Path(d))
        try:
            rig.node.ssh_down = True
            rig.node.round_trip_s = 20.0
            rig.clock.advance(rd.POLL_CADENCE_S)
            start = rig.clock.now
            rc, out, _ = rig.run("--manual",
                                 preds=rig.write_preds([pred(hours=10.0)]))
            emit("5e_failed_run_bounded_retry", rc=rc, action=out.get("action"),
                 pull_attempts=rig.node.kinds().count("pull"),
                 max_attempts=rd.MAX_PULL_ATTEMPTS,
                 run_elapsed=rig.clock.now - start,
                 detection_plus_run=rig.clock.now - 0.0)
        finally:
            rig.close()


def p5_6_cadence_wired_check():
    try:
        cron = subprocess.run(["crontab", "-l"], capture_output=True, text=True).stdout
    except Exception as e:
        cron = f"<error: {e}>"
    entries = [ln for ln in cron.splitlines()
               if "routstr" in ln.lower() or "delist" in ln.lower()]
    emit("5f_cron_cadence_wired", cron_entries=len(entries), entries=entries)


def p5_7_poll_cadence_consumers():
    src = DEPLOYED.read_text()
    lines = src.splitlines()
    prod = [i + 1 for i, ln in enumerate(lines)
            if "POLL_CADENCE_S" in ln and not re.match(r"^POLL_CADENCE_S\s*=", ln)]
    tst = (Path.home() / ".hermes/bot/tests/test_routstr_delist.py").read_text()
    tst_uses = len(re.findall(r"POLL_CADENCE_S", tst))
    emit("5g_poll_cadence_consumers", script_consumers=prod, test_uses=tst_uses)


def main():
    p4_1_atomic_save()
    p4_2_call_sites_discard()
    p4_2b_silent_persist_failure()
    p4_2c_delivered_flag_not_flipped()
    p4_3_breaker_not_durable()
    p4_4_no_lock()
    p4_4b_last_writer_wins()
    p4_5_no_dir_fsync()
    p4_6_redelist_merge()
    p4_7_relist_refused()
    p4_8_failed_relist_no_tick()
    p4_9_bool_counter_hole()
    p4_10_failed_delist_clears_flag()
    p4_11_dry_run_persist_silent()
    p5_1_constants()
    p5_2_dead_constant_audit()
    p5_3_worst_case_path()
    p5_4_budget_exhaustion()
    p5_4b_lying_pull_retry_clamp()
    p5_4c_nak_publish_unclamped()
    p5_5_bounded_retry_on_dead_node()
    p5_6_cadence_wired_check()
    p5_7_poll_cadence_consumers()
    print(f"\n{len(OUT)} probes completed", flush=True)


if __name__ == "__main__":
    main()
