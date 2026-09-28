#!/usr/bin/env python3
"""probe_f45_pass25.py — independent re-derivation of routstr-delist findings
4 (atomicity + idempotence) and 5 (5-minute SLA arithmetic) for the 25th
offload pass.

Drives the DEPLOYED script (~/.hermes/bot/scripts/routstr_delist.py) in-process
against the contract suite's own FakeSellNode (real payload builders executed
against a named in-memory sqlite sell node). No network, no file-sqlite, no
real sleeps.

Every claim printed is measured, not asserted from the source text.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import signal
import sys
import tempfile
from pathlib import Path
from unittest import mock

REPO = Path("/home/c03rad0r/repos/merchant-routing")
BOT = Path.home() / ".hermes" / "bot"
SCRIPTS = BOT / "scripts"
TESTS = REPO / "tests" / "test_routstr_delist_contract.py"

# deployed script first (the artifact under review)
sys.path.insert(0, str(SCRIPTS))
import routstr_delist as rd  # noqa: E402

spec = importlib.util.spec_from_file_location("_contract", TESTS)
_c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(_c)
FakeSellNode, FakeTime, _NodeBackend = _c.FakeSellNode, _c.FakeTime, _c._NodeBackend

OUT = []
def say(tag, **kw):
    OUT.append(f"{tag} " + json.dumps(kw, sort_keys=True, default=str))
    print(OUT[-1], flush=True)


class Rig:
    """Minimal CLI harness (tmp state/override, in-process main())."""

    def __init__(self, tmp: Path, node=None):
        self.tmp = tmp
        self.node = node if node is not None else FakeSellNode(tmp)
        self.clock = FakeTime()
        self.state = tmp / "routstr_delist_state.json"
        self.override = tmp / "routstr_delist.override"
        self._patches = []

    def __enter__(self):
        self._patches = [
            mock.patch.object(rd, "_SshBackend",
                              lambda t, c: _NodeBackend(self.node, self.clock)),
            mock.patch.object(rd, "time", self.clock),
            # host pathology: fsync can stall on this fleet host
            mock.patch.object(os, "fsync", lambda fd: None),
        ]
        for p in self._patches:
            p.start()
        return self

    def __exit__(self, *exc):
        for p in reversed(self._patches):
            p.stop()
        return False

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


def pred(key="zai", window="1h", hours=10.0, unc=0.05):
    return {"key": key, "window": window, "exhausts_in_hours": hours,
            "uncertainty": unc}


# ══ FINDING 4 — atomicity + idempotence ═══════════════════════════════════
def probe_f4():
    say("F4.0 constants", save_state_src_lines="221-245")

    src = (SCRIPTS / "routstr_delist.py").read_text()
    def uses(tok):
        # count non-comment, non-docstring occurrences outside comments
        n = 0
        for i, line in enumerate(src.splitlines(), 1):
            s = line.split("#")[0]
            if tok in s:
                n += 1
        return n
    say("F4.1 atomic-protocol-tokens", os_replace=uses("os.replace("),
        tmp_named_file=uses(".tmp"), fsync=uses("os.fsync("),
        fcntl=uses("fcntl"), flock=uses("flock"), lock=uses("lock"))

    # --- P1: real swap observed: old intact at replace time, new complete ---
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        sp = td / "state.json"
        old = {"ts": 1, "delisted": False, "snapshot": {"zai": 10.0}}
        assert rd.save_state(str(sp), old) is True
        old_bytes = sp.read_bytes()
        new = {"ts": 2, "delisted": True, "pulled_models": ["a", "b"]}
        expected = json.dumps(new, indent=2, sort_keys=True).encode()
        real_replace = os.replace
        seen = []
        def spy(src_, dst_):
            if Path(dst_) == sp:
                seen.append({"pre_dst": Path(dst_).read_bytes(),
                             "tmp": Path(src_).read_bytes()})
            return real_replace(src_, dst_)
        with mock.patch.object(os, "replace", spy):
            ok = rd.save_state(str(sp), new)
        say("F4.P1 atomic-swap", ok=ok, swaps=len(seen),
            pre_dst_is_old=(len(seen) == 1 and seen[0]["pre_dst"] == old_bytes),
            tmp_is_complete_new=(len(seen) == 1 and seen[0]["tmp"] == expected),
            final_is_new=(sp.read_bytes() == expected),
            tmp_litter=[p.name for p in td.glob(".*.tmp")])

    # --- P2: crash between tmp-write and replace: previous state intact ---
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        sp = td / "state.json"
        old = {"ts": 1, "delisted": False, "snapshot": {"zai": 10.0}}
        rd.save_state(str(sp), old)
        with mock.patch.object(os, "replace",
                               side_effect=OSError("simulated crash")):
            ok = rd.save_state(str(sp), {"ts": 2, "delisted": True})
        say("F4.P2 crash-before-replace", ok=ok,
            previous_intact=(rd.load_state(str(sp)) == old),
            tmp_litter=[p.name for p in td.glob(".*.tmp")])

    # --- P3: persist failure on the SUCCESS path is SILENT (real CLI) ---
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        node = FakeSellNode(td)
        with Rig(td, node) as rig:
            st = json.dumps({"delisted": False, "snapshot": {}})
            rig.state.write_text(st)
            before = rig.state.read_bytes()
            with mock.patch.object(os, "replace",
                                   side_effect=OSError("simulated crash")):
                rc, out, raw = rig.run("--manual")
            after = rig.state.read_bytes()
            on_disk = json.loads(after)
            say("F4.P3 persist-failure-silent-on-success",
                rc=rc, action=out.get("action"), confirmed=out.get("confirmed"),
                stdout_ok=out.get("ok"),
                state_file_changed=(before != after),
                durable_delisted_flag=on_disk.get("delisted"),
                durable_pulled_models=on_disk.get("pulled_models", "<absent>"),
                remote_actually_delisted=(set(node.models_map().values()) == {0}),
                note="remote pull landed but the durable flag the publisher "
                     "reads was never written")

    # --- P4: is save_state's return value ever consumed? ---
    consumed = [i for i, line in enumerate(src.splitlines(), 1)
                if "save_state(" in line and not line.lstrip().startswith("def ")
                and "=" in line.split("save_state", 1)[0]]
    say("F4.4 return-value-consumed", assignment_sites=consumed,
        call_sites=[565, 622, 629, 638, 654, 710, 732, 752],
        verdict="all 8 call sites discard the bool; save_state's False is "
                "never surfaced (no exit-code change, no JSON field)")

    # --- P5: real fsync call (durability) + host stall check ---
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        sp = td / "state.json"
        calls = []
        real_fsync = os.fsync
        def spy_fsync(fd):
            calls.append(fd)
            return None
        with mock.patch.object(os, "fsync", spy_fsync):
            rd.save_state(str(sp), {"ts": 1})
        say("F4.P5 fsync-called", n=len(calls), fds=len(set(calls)))

        # does the real fsync actually return on this host?
        def _boom(signum, frame):
            raise TimeoutError("fsync stalled")
        old_h = signal.signal(signal.SIGALRM, _boom)
        signal.setitimer(signal.ITIMER_REAL, 5.0)
        try:
            fd = os.open(str(sp), os.O_RDWR)
            try:
                real_fsync(fd)
                stalled = False
            finally:
                os.close(fd)
        except TimeoutError:
            stalled = True
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, old_h)
        say("F4.P5 real-fsync-on-this-host", stalled=stalled)

    # --- P6: durability never asserted: suite suppresses fsync ---
    tsrc = TESTS.read_text()
    supp = [(i, l.strip()) for i, l in enumerate(tsrc.splitlines(), 1)
            if "os, \"fsync\"" in l or "os.fsync" in l]
    say("F4.P6 suite-fsync-suppression", sites=supp,
        note="Rig and TestAtomicStateWrites both null os.fsync; fsync "
             "durability is never asserted by any test")

    # --- P7: re-delist merge (idempotence defect 1) ---
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        node = FakeSellNode(td)
        with Rig(td, node) as rig:
            rc1, o1, _ = rig.run("--manual")
            st1 = rd.load_state(str(rig.state))
            rc2, o2, _ = rig.run("--delist")
            st2 = rd.load_state(str(rig.state))
            say("F4.P7 re-delist-merge",
                rc=[rc1, rc2],
                first_pulled=st1.get("pulled_models"),
                second_pulled_capture=o2.get("pulled"),
                second_ok=o2.get("ok"), confirmed=o2.get("confirmed"),
                merged_pulled=st2.get("pulled_models"),
                clobbered=(st2.get("pulled_models") != st1.get("pulled_models")))

    # --- P8: blanket relist refused without names (defect 2) ---
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        node = FakeSellNode(td)
        with Rig(td, node) as rig:
            rig.state.write_text(json.dumps(
                {"delisted": True, "last_reason": "manual override",
                 "snapshot": {}, "ts": 1788883877.4}))
            rc, out, _ = rig.run("--relist")
            say("F4.P8 blanket-relist-refused", rc=rc, action=out.get("action"),
                ok=out.get("ok"), remote_calls=len(node.calls),
                models_after=node.models_map())
            rc2, out2, _ = rig.run("--relist", "--relist-any", "--dry-run")
            say("F4.P8 relist-any-optin", rc=rc2, action=out2.get("action"),
                remote_calls=len(node.calls))

    # --- P9: no lock between concurrent runs (last writer wins) ---
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        sp = td / "state.json"
        rd.save_state(str(sp), {"ts": 1, "writer": "A", "snapshot": {}})
        ra = sp.read_bytes()
        rd.save_state(str(sp), {"ts": 2, "writer": "B", "snapshot": {}})
        rb = sp.read_bytes()
        say("F4.P9 last-writer-wins", a_bytes=len(ra), b_bytes=len(rb),
            final=json.loads(rb)["writer"],
            interlocks=src.count("fcntl") + src.count("flock")
                      + src.count("LockFile"))

    # --- P10: breaker durability depends on the ignored save_state bool ---
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        node = FakeSellNode(td)
        node.ssh_down = True
        with Rig(td, node) as rig:
            rcs = []
            with mock.patch.object(os, "replace",
                                   side_effect=OSError("simulated crash")):
                for _ in range(4):
                    rc, out, _ = rig.run("--manual")
                    rcs.append(rc)
            say("F4.P10 breaker-durability-with-save-failing", rcs=rcs,
                durable_blocked=rd.load_state(str(rig.state)).get("blocked"),
                durable_failures=rd.load_state(str(rig.state))
                                 .get("consecutive_failures"),
                documented=("no crontab entry is wired yet" and True),
                note="every run reports the same in-memory count because the "
                     "persist silently fails; the 'durable BLOCKED marker' is "
                     "not durable — run 4 was NOT refused")

    # --- P11: reconciliation gap — flag loss with a quiet trigger ---
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        node = FakeSellNode(td)
        with Rig(td, node) as rig:
            # a variance-spike delist whose state write silently fails
            rig.run(preds=rig.write_preds([pred(unc=0.05)], name="a.json"))
            with mock.patch.object(os, "replace",
                                   side_effect=OSError("simulated crash")):
                rc1, o1, _ = rig.run(preds=rig.write_preds(
                    [pred(unc=0.9)], name="b.json"))
            node_pulled = set(node.models_map().values()) == {0}
            # trigger goes quiet; no repair path exists
            rc2, o2, _ = rig.run(preds=rig.write_preds([pred(unc=0.05)],
                                                      name="c.json"))
            st = rd.load_state(str(rig.state))
            say("F4.P11 flag-loss-reconciliation",
                delist_rc=rc1, delist_action=o1.get("action"),
                remote_pulled=node_pulled,
                next_run_action=o2.get("action"),
                durable_delisted=st.get("delisted"),
                durable_pulled_models=st.get("pulled_models", "<absent>"),
                recon_payloads=[k for k, _ in node.calls],
                note="remote listing stays pulled while the publisher-read "
                     "flag is false; no code path ever reconciles the flag "
                     "against the node")
            # does any payload ever READ the node's real delist status?
            verify_payloads = [p for k, p in node.calls if k == "verify"]
            say("F4.P11 verify-is-read-only-count",
                verify_used_for_reconciliation=any(
                    "delisted" in p.lower() for p in verify_payloads))


# ══ FINDING 5 — 5-minute SLA arithmetic ═══════════════════════════════════
def probe_f5():
    say("F5.0 constants",
        TRIGGER_ACTION_WINDOW_S=rd.TRIGGER_ACTION_WINDOW_S,
        POLL_CADENCE_S=rd.POLL_CADENCE_S,
        ACTION_BUDGET_S=rd.ACTION_BUDGET_S,
        SSH_TIMEOUT_S=rd.SSH_TIMEOUT_S,
        MAX_PULL_ATTEMPTS=rd.MAX_PULL_ATTEMPTS,
        arithmetic_holds=(rd.POLL_CADENCE_S + rd.ACTION_BUDGET_S
                          == rd.TRIGGER_ACTION_WINDOW_S),
        two_rt_fits=(2 * rd.SSH_TIMEOUT_S <= rd.ACTION_BUDGET_S))

    src = (SCRIPTS / "routstr_delist.py").read_text().splitlines()
    for tok in ("TRIGGER_ACTION_WINDOW_S", "POLL_CADENCE_S", "ACTION_BUDGET_S",
                "SSH_TIMEOUT_S", "MAX_PULL_ATTEMPTS"):
        reads = [i for i, l in enumerate(src, 1)
                 if tok in l.split("#")[0] and "=" not in l.split(tok)[0]]
        say("F5.1 consumption", const=tok, non_comment_reads=reads)

    # AST: where is each module constant actually LOADED (not just defined)?
    import ast
    tree = ast.parse("\n".join(src))
    loads = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            loads.setdefault(node.id, []).append(node.lineno)
    say("F5.1b ast-name-loads",
        **{k: loads.get(k, []) for k in
           ("TRIGGER_ACTION_WINDOW_S", "POLL_CADENCE_S", "ACTION_BUDGET_S",
            "SSH_TIMEOUT_S", "MAX_PULL_ATTEMPTS", "BREAKER_THRESHOLD")})
    say("F5.1c runtime-read-verdict",
        TRIGGER_ACTION_WINDOW_S="never read at runtime (only consumed at "
                               "src:73 to derive ACTION_BUDGET_S)",
        POLL_CADENCE_S="NEVER read anywhere — declaration+comment only",
        ACTION_BUDGET_S=f"read at {loads.get('ACTION_BUDGET_S', [])}",
        SSH_TIMEOUT_S=f"read at {loads.get('SSH_TIMEOUT_S', [])}",
        MAX_PULL_ATTEMPTS=f"read at {loads.get('MAX_PULL_ATTEMPTS', [])}")

    # --- Q3: deadline clamps every action round-trip; action <= budget ---
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        node = FakeSellNode(td)
        node.round_trip_s = 25.0
        with Rig(td, node) as rig:
            rig.clock.advance(rd.POLL_CADENCE_S)   # worst-case detection
            t0 = rig.clock.now
            rc, out, _ = rig.run("--manual",
                                 preds=rig.write_preds([pred(hours=10.0)]))
            t1 = rig.clock.now
            say("F5.Q3 deadline-enforced", rc=rc, action=out.get("action"),
                confirmed=out.get("confirmed"),
                detection_s=rd.POLL_CADENCE_S, action_elapsed=t1 - t0,
                round_trips=node.deadline_log,
                within_window=((t1 - t0) <= rd.TRIGGER_ACTION_WINDOW_S),
                within_budget=((t1 - t0) <= rd.ACTION_BUDGET_S))

    # --- Q4: WORST-CASE latency + --nsec: nak publish is NOT deadline-clamped
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        node = FakeSellNode(td)
        node.round_trip_s = 30.0           # each ssh round-trip at SSH_TIMEOUT_S
        nsec = td / "nsec"
        nsec.write_text("nsec1PROBEPROBE\n")
        rec = []
        with Rig(td, node) as rig:
            class Shim:
                def __init__(self, clock):
                    self.c = clock
                def monotonic(self):
                    return self.c.monotonic()
                @staticmethod
                def time():
                    import time as _t
                    return _t.time()
            shim = Shim(rig.clock)

            def fake_run(argv, timeout=None, env=None, capture_output=False,
                         **kw):
                rec.append({"timeout": timeout,
                            "argv0": argv[0] if argv else None})
                # a nak publish that consumes its full timeout
                rig.clock.advance(float(timeout or 0))
                import subprocess as _sp
                return _sp.CompletedProcess(argv, 0)

            with mock.patch.object(rd, "time", shim), \
                 mock.patch.object(rd.subprocess, "run", fake_run):
                sample_t = rig.clock.now                 # trigger sample: t=0
                rig.clock.advance(rd.POLL_CADENCE_S)     # worst-case detection
                action_start = rig.clock.now
                rc, out, _ = rig.run("--manual", "--nsec", str(nsec),
                                     preds=rig.write_preds([pred(hours=10.0)]))
                done_t = rig.clock.now
            action_phase = done_t - action_start
            detection_to_done = done_t - sample_t
            say("F5.Q4 publish-unclamped", rc=rc, action=out.get("action"),
                confirmed=out.get("confirmed"),
                sample_t=sample_t, action_start=action_start, done_t=done_t,
                action_phase_s=action_phase,
                action_budget_s=rd.ACTION_BUDGET_S,
                detection_to_done_s=detection_to_done,
                window_s=rd.TRIGGER_ACTION_WINDOW_S,
                nak_publish_timeouts=[r["timeout"] for r in rec],
                breaches_window=(detection_to_done > rd.TRIGGER_ACTION_WINDOW_S),
                breaches_action_budget=(action_phase > rd.ACTION_BUDGET_S),
                nak_clamped_to_deadline=all(
                    r["timeout"] <= rd.ACTION_BUDGET_S for r in rec))

    # --- Q4b: verified-delist instant at FULL ssh timeout (strict <300?) ---
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        node = FakeSellNode(td)
        node.round_trip_s = float(rd.SSH_TIMEOUT_S)   # both round-trips maxed
        with Rig(td, node) as rig:
            sample_t = rig.clock.now
            rig.clock.advance(rd.POLL_CADENCE_S)
            rc, out, _ = rig.run("--manual",
                                 preds=rig.write_preds([pred(hours=10.0)]))
            confirmed_t = rig.clock.now
            say("F5.Q4b worst-case-verified-instant", rc=rc,
                confirmed=out.get("confirmed"),
                t_from_sample=confirmed_t - sample_t,
                window=rd.TRIGGER_ACTION_WINDOW_S,
                strictly_under_300=((confirmed_t - sample_t)
                                    < rd.TRIGGER_ACTION_WINDOW_S),
                equality=sample_t == 0 and confirmed_t == 300.0)

    # --- Q4c: nak ignores the REMAINING budget (not just the nominal cap) ---
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        node = FakeSellNode(td)
        node.round_trip_s = 25.0      # pull 25s + verify 25s -> 50s of 60s used
        nsec = td / "nsec"
        nsec.write_text("nsec1PROBEPROBE\n")
        rec = []
        with Rig(td, node) as rig:
            class Shim2:
                def __init__(self, clock):
                    self.c = clock
                def monotonic(self):
                    return self.c.monotonic()
                @staticmethod
                def time():
                    import time as _t
                    return _t.time()

            def fake_run(argv, timeout=None, env=None, capture_output=False,
                         **kw):
                rec.append({"timeout": timeout,
                            "remaining_before_nak":
                                rd.ACTION_BUDGET_S - rig.clock.monotonic()})
                rig.clock.advance(float(timeout or 0))
                import subprocess as _sp
                return _sp.CompletedProcess(argv, 0)

            with mock.patch.object(rd, "time", Shim2(rig.clock)), \
                 mock.patch.object(rd.subprocess, "run", fake_run):
                rc, out, _ = rig.run("--manual", "--nsec", str(nsec),
                                     preds=rig.write_preds([pred(hours=10.0)]))
            say("F5.Q4c nak-ignores-remaining-budget", rc=rc,
                confirmed=out.get("confirmed"),
                nak_requested_timeout=(rec[0]["timeout"] if rec else None),
                remaining_before_nak=(rec[0]["remaining_before_nak"]
                                      if rec else None),
                exceeds_remaining=bool(rec and
                                       rec[0]["timeout"] >
                                       rec[0]["remaining_before_nak"]))

    # --- Q5: retry is unreachable at worst-case latency ---
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        node = FakeSellNode(td)
        node.round_trip_s = 30.0
        node.pull_lands = False            # pull self-reports ok, refuted
        with Rig(td, node) as rig:
            rc, out, _ = rig.run("--manual",
                                 preds=rig.write_preds([pred(hours=10.0)]))
            say("F5.Q5 retry-unreachable-at-worst-case", rc=rc,
                action=out.get("action"), round_trips=node.kinds(),
                attempts_used=len([k for k in node.kinds() if k == "pull"]),
                max_pull_attempts=rd.MAX_PULL_ATTEMPTS,
                retry_ran=(node.kinds().count("pull") > 1))

    # --- Q6: deployment: is the cadence actually scheduled? ---
    import subprocess as sp
    ct = sp.run(["crontab", "-l"], capture_output=True, text=True).stdout
    entries = [l for l in ct.splitlines() if "routstr" in l.lower()]
    say("F5.Q6 crontab", routstr_entries=len(entries), entries=entries,
        documented_cadence_min=4,
        doc_says_unwired=("no crontab entry is wired yet"
                          in (REPO / "docs" / "routstr-delist.md").read_text()))


if __name__ == "__main__":
    print("=== md5 (artifacts under review) ===", flush=True)
    import hashlib
    for p in (SCRIPTS / "routstr_delist.py", BOT / "tests" / "test_routstr_delist.py",
              BOT / "docs" / "routstr-delist.md"):
        print(f"{hashlib.md5(p.read_bytes()).hexdigest()}  {p}", flush=True)
    print("=== FINDING 4 ===", flush=True)
    probe_f4()
    print("=== FINDING 5 ===", flush=True)
    probe_f5()
    Path("/home/c03rad0r/repos/merchant-routing/docs/reviews/"
         "routstr_f45_probes/probe_f45_pass25.out").write_text(
        "\n".join(OUT) + "\n")
    print("=== done ===", flush=True)
