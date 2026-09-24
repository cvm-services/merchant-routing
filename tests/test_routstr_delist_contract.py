"""TDD contract suite for routstr_delist (frozen contract: docs/routstr-delist.md).

Authored test-first against the task-0 contract; the cases below map 1:1 to
the 11 REQUIRED CASES in the offload task body. pytest-native (fixtures,
tmp_path, monkeypatch, capsys); deterministic — zero real sleeps, all timing
via a fake monotonic clock.

Deviations from the task body's METHOD, justified by the frozen contract:

* "mock HTTP with respx or httpx.MockTransport" — the contract's routstr API
  is NOT HTTP: it is `ssh <sell-node> docker exec <container> python3 -c
  <payload>` against the sell node's `/app/data/keys.db` (respx is not
  installed and the module has no HTTP client). The mock therefore sits at
  the contract's actual API boundary: a FakeSellNode that EXECUTES the
  script's real payload builders against a local sqlite DB (models = the
  SALE listing table, upstream_providers = the provider ladder). Hermetic:
  no subprocess, no network, no live routstr API.
* "--force-delist" — the frozen contract names the manual overrides
  `--manual` (flag/marker file) and `--delist` (force-pull now); those are
  what Case 4 exercises.
* "the poll/subscription interval in config" — the contract has no config
  file; the poll interval is the documented cron cadence constant
  POLL_CADENCE_S (*/4), wired with TRIGGER_ACTION_WINDOW_S/ACTION_BUDGET_S.
  Case 8 asserts both the constant arithmetic and the observable fake-clock
  path (worst-case detection charged a full cadence).

The fake clock patches only rd.time.monotonic (synthetic, for SLA/debounce
narratives); rd.time.time stays REAL so the mtime freshness guard sees the
just-written fixture feeds as fresh.
"""
from __future__ import annotations

import builtins
import contextlib
import io
import json
import os
import sqlite3
import subprocess
import sys
import time
import types
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
# repo layout (../src) first; deployed bot layout (../scripts) second so the
# ~/.hermes/bot/tests copy runs against the deployed script copy.
for _cand in (_HERE.parent / "src", _HERE.parent / "scripts"):
    if (_cand / "routstr_delist.py").is_file():
        if str(_cand) not in sys.path:
            sys.path.insert(0, str(_cand))
        break

import routstr_delist as rd  # noqa: E402


# ── Fixture builders ──────────────────────────────────────────────────────
def pred(key="zai", window="1h", hours=10.0, unc=0.05):
    """burn_predictor.predict_exhaustion-shaped prediction dict."""
    return {"key": key, "window": window,
            "exhausts_in_hours": hours, "uncertainty": unc}


ADVERTISED = ["gpt-4o", "claude-3-5-sonnet", "llama-3.1-405b"]   # the SALE
OPERATOR_DISABLED = ["operator-disabled-model"]                  # pre-off
PROVIDERS = [("openrouter", 1, 20.0), ("routstr", 1, 10.0), ("zai", 1, 30.0)]


class FakeTime:
    """Synthetic monotonic clock; wall time stays real (freshness guard)."""

    def __init__(self):
        self._mono = 0.0

    def monotonic(self):
        return self._mono

    @staticmethod
    def time():
        return time.time()

    def advance(self, seconds):
        self._mono += seconds

    @property
    def now(self):
        return self._mono


class FakeSellNode:
    """The mocked routstr sell-node API (hermetic: named in-memory sqlite).

    Executes the script's REAL remote payloads (pull/verify/relist) against
    a local sqlite stand-in for /app/data/keys.db, so tests observe actual
    SQL effects on the `models` (listing) table — and can prove the
    `upstream_providers` ladder is never touched. `ladder_artifact` mirrors
    the T470 flat-router ladder file for the byte-identity semantic guard.

    ssh_down: every round-trip fails like a dead ssh (rc 255, no SQL).
    pull_lands: False simulates a LYING pull — rc 0, ok-printed, but the
    UPDATE never lands (enabled flags restored), so only the independent
    re-fetch can refute it.
    """

    def __init__(self, tmpdir: Path):
        self.ladder_artifact = tmpdir / "t470_ladder.json"
        self.ladder_artifact.write_bytes(json.dumps(
            {"ladder": [{"name": n, "enabled": bool(e), "weight": w,
                         "candidate": True} for n, e, w in PROVIDERS]},
            indent=2, sort_keys=True).encode())

        # Named SHARED-CACHE in-memory sqlite: every connection below (the
        # node's own AND the ones the payloads open via the sqlite3 shim)
        # attaches to the same living database with NO file and NO fcntl
        # locks — real SQL semantics, hermetic and deterministic on any
        # host (file-backed sqlite can block indefinitely on lock
        # acquisition inside sandboxed kernels).
        self._uri = f"file:rdsellnode{os.getpid()}x{id(self):x}" \
                    f"?mode=memory&cache=shared"
        con = self._connect()
        con.execute("CREATE TABLE models "
                    "(name TEXT PRIMARY KEY, enabled INTEGER NOT NULL)")
        for n in ADVERTISED:
            con.execute("INSERT INTO models VALUES (?, 1)", (n,))
        for n in OPERATOR_DISABLED:
            con.execute("INSERT INTO models VALUES (?, 0)", (n,))
        con.execute("CREATE TABLE upstream_providers "
                    "(name TEXT PRIMARY KEY, enabled INTEGER NOT NULL, "
                    "weight REAL NOT NULL)")
        for row in PROVIDERS:
            con.execute("INSERT INTO upstream_providers VALUES (?, ?, ?)", row)
        con.commit()
        self._con = con   # held open: keeps the named memory db alive

        self.calls = []          # (kind, payload) per executed round-trip
        self.deadline_log = []   # SLA observations from the backend adapter
        self.ssh_down = False
        self.pull_lands = True
        self.round_trip_s = 0.0  # simulated ssh latency (fake clock)

        # redirect the payload's hardcoded /app/data/keys.db at our memory db
        shim = types.ModuleType("sqlite3")
        shim.connect = self._connect
        self._sqlite3 = shim

    def _connect(self, _path=None):
        """sqlite3.connect stand-in; the payload's hardcoded
        /app/data/keys.db path is accepted and ignored."""
        return sqlite3.connect(self._uri, uri=True)

    # -- state observers ---------------------------------------------------
    def models_map(self):
        rows = dict(self._con.execute("SELECT name, enabled FROM models"))
        return rows

    def providers_snapshot(self):
        return list(self._con.execute(
            "SELECT name, enabled, weight FROM upstream_providers "
            "ORDER BY name"))

    def ladder_bytes(self):
        return self.ladder_artifact.read_bytes()

    def kinds(self):
        return [k for k, _ in self.calls]

    # -- payload execution (the mocked API) --------------------------------
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
            exec(payload, g)  # noqa: S102 — executing OUR OWN payload builders
        if revert is not None:  # the UPDATE "never landed"
            con = self._connect()
            for name, enabled in revert.items():
                con.execute("UPDATE models SET enabled=? WHERE name=?",
                            (enabled, name))
            con.commit()
            con.close()
        return json.loads(out.getvalue().strip().splitlines()[-1])


class _NodeBackend:
    """Stand-in for rd._SshBackend routing at the FakeSellNode.

    Mirrors the production result shape: parsed last-line JSON merged with
    rc, `ok` gated on the payload's own ok flag, ssh failures as
    {"ok": False, rc: 255, error: ...}. Records the SLA deadline view
    (remaining budget + clamped timeout) observed at each round-trip.
    """

    def __init__(self, node, clock):
        self.node = node
        self.clock = clock

    def pull(self, dry_run=False, deadline=None):
        return self._round_trip("pull", rd.pull_listing_payload(),
                                dry_run, deadline)

    def verify(self, dry_run=False, deadline=None):
        return self._round_trip("verify", rd.verify_pull_payload(),
                                dry_run, deadline)

    def relist(self, names=None, dry_run=False, deadline=None):
        return self._round_trip("relist", rd.relist_payload(names or []),
                                dry_run, deadline)

    def _round_trip(self, kind, payload, dry_run, deadline):
        if deadline is not None:
            remaining = deadline - self.clock.monotonic()
            self.node.deadline_log.append({
                "kind": kind,
                "t": self.clock.monotonic(),
                "remaining": remaining,
                "timeout": min(rd.SSH_TIMEOUT_S, max(remaining, 0.0)),
            })
        if dry_run:
            return {"ok": True, "dry_run": True, "action": kind}
        # every real API attempt is recorded — ssh failures included
        self.node.calls.append((kind, payload))
        if self.node.ssh_down:
            return {"ok": False, "action": kind, "rc": 255,
                    "error": "ssh: connect to host 23.182.128.51 port 22: "
                             "Connection refused (simulated)"}
        data = self.node.execute(kind, payload)
        self.clock.advance(self.node.round_trip_s)
        return {"action": kind, "rc": 0, **data, "ok": data.get("ok") is True}


class Rig:
    """CLI harness: tmp state/override, preds writer, in-process main()."""

    def __init__(self, tmp_path, monkeypatch):
        self.tmp = tmp_path
        self.node = FakeSellNode(tmp_path)
        self.clock = FakeTime()
        self.state = tmp_path / "routstr_delist_state.json"
        self.override = tmp_path / "routstr_delist.override"  # absent
        monkeypatch.setattr(rd, "_SshBackend",
                            lambda t, c: _NodeBackend(self.node, self.clock))
        monkeypatch.setattr(rd, "time", self.clock)
        # Host workaround: this fleet host's disk can stall indefinitely
        # inside fsync (same pathology as file-sqlite lock acquisition).
        # fsync durability is behaviourally pinned by Case 10's
        # TestAtomicStateWrites (real fsync, no rig); for every other case
        # the atomic os.replace — the observable atomicity — still runs.
        monkeypatch.setattr(os, "fsync", lambda fd: None)

    def write_preds(self, preds, name="preds.json"):
        p = self.tmp / name
        p.write_text(json.dumps(preds))
        return p

    def age_preds(self, path, seconds=3600):
        old = time.time() - seconds
        os.utime(path, (old, old))
        return path

    def place_marker(self):
        self.override.write_text("manual delist requested\n")
        return self.override

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


@pytest.fixture
def rig(tmp_path, monkeypatch):
    return Rig(tmp_path, monkeypatch)


# ── Case 1: no trigger -> exit 0, zero delist calls ───────────────────────
class TestQuietNoTrigger:
    def test_steady_burn_and_variance_never_delists(self, rig):
        """Two consecutive identical samples (steady burn-rate, steady
        Kalman variance): exit 0, action none, ZERO routstr API calls."""
        preds = rig.write_preds([pred(hours=10.0, unc=0.05)])
        rc1, out1, _ = rig.run(preds=preds)
        rc2, out2, _ = rig.run(preds=preds)
        assert (rc1, rc2) == (0, 0)
        assert out1["action"] == out2["action"] == "none"
        assert out2["fire"] is False
        assert rig.node.calls == []                    # zero delist calls
        st = rd.load_state(str(rig.state))
        assert st.get("delisted") is False
        assert "pulled_models" not in st
        assert rig.node.models_map() == {**{n: 1 for n in ADVERTISED},
                                         **{n: 0 for n in OPERATOR_DISABLED}}

    def test_first_run_without_baseline_is_quiet(self, rig):
        """No stored baseline -> acceleration can never fire (false-positive
        guard): a single quiet sample exits 0 with zero API calls."""
        rc, out, _ = rig.run(preds=rig.write_preds([pred(hours=2.0)]))
        assert rc == 0
        assert out["action"] == "none"
        assert rig.node.calls == []


# ── Case 2: acceleration -> exactly one delist, 2nd-listings-fetch verified
class TestBurnAccelerationDelist:
    def test_acceleration_fires_exactly_one_delist_verified_by_refetch(self, rig):
        """Predicted exhaustion moves forward past the threshold -> exactly
        ONE delist, and success is gated on the independent second listings
        fetch (read-only SELECT COUNT), not the pull's self-report."""
        rig.run(preds=rig.write_preds([pred(hours=10.0)], name="a.json"))
        rc, out, _ = rig.run(
            preds=rig.write_preds([pred(hours=4.5)], name="b.json"))

        assert rc == 0
        assert out["action"] == "delist"
        assert out["confirmed"] is True
        assert out["verified_count"] == 0
        assert "exhaustion accelerated" in out["reasons"][0]

        # exactly one delist: one pull + one verification re-fetch
        assert rig.node.kinds() == ["pull", "verify"]
        pull_payload, verify_payload = rig.node.calls[0][1], rig.node.calls[1][1]
        assert pull_payload == rd.pull_listing_payload()
        assert verify_payload == rd.verify_pull_payload()
        assert "SELECT COUNT(*) FROM models WHERE enabled=1" in verify_payload
        assert "UPDATE" not in verify_payload.upper()   # re-fetch is read-only

        st = rd.load_state(str(rig.state))
        assert st["delisted"] is True
        assert st["pulled_models"] == ADVERTISED        # not operator-disabled
        assert set(rig.node.models_map().values()) == {0}  # listing pulled

    def test_unverified_pull_is_a_failed_delist(self, rig):
        """A pull that self-reports ok but is refuted by the re-fetch
        (models still advertised) is NOT a success: bounded in-run retry,
        then failure semantics (exit 1, no delisted flag, breaker tick)."""
        rig.node.pull_lands = False
        rc, out, _ = rig.run("--manual")
        assert rc == 1
        assert out["action"] == "delist_failed"
        assert out["ok"] is False
        assert out["verify"]["count"] == len(ADVERTISED)
        # attempt 1 (pull+verify refuted) + in-run retry (pull+verify refuted)
        assert rig.node.kinds() == ["pull", "verify", "pull", "verify"]
        st = rd.load_state(str(rig.state))
        assert st.get("delisted") is False
        assert st["consecutive_failures"] == 1


# ── Case 3: Kalman variance jump -> exactly one delist ────────────────────
class TestKalmanVarianceDelist:
    def test_variance_jump_fires_exactly_one_delist(self, rig):
        """uncertainty above the threshold (burn-rate unchanged) -> exactly
        one delist, confirmed by the second listings fetch."""
        rig.run(preds=rig.write_preds([pred(hours=10.0, unc=0.05)],
                                      name="a.json"))
        rc, out, _ = rig.run(preds=rig.write_preds([pred(hours=10.0, unc=0.9)],
                                                   name="b.json"))
        assert rc == 0
        assert out["action"] == "delist"
        assert out["confirmed"] is True
        assert rig.node.kinds() == ["pull", "verify"]
        assert out["reasons"][0].startswith("kalman variance jumped")
        assert rd.load_state(str(rig.state))["delisted"] is True

    def test_variance_at_threshold_is_quiet(self, rig):
        """The trigger is strictly greater-than: 0.30 exactly does not fire."""
        rig.run(preds=rig.write_preds([pred(hours=10.0, unc=0.05)],
                                      name="a.json"))
        rc, out, _ = rig.run(preds=rig.write_preds([pred(hours=10.0, unc=0.30)],
                                                   name="b.json"))
        assert rc == 0
        assert out["action"] == "none"
        assert rig.node.calls == []

    def test_other_providers_variance_cannot_pull_routstr_sale(self, rig):
        """--preds-key scoping: an openrouter variance spike must never
        delist the routstr SALE."""
        rc, out, _ = rig.run(
            "--preds-key", "zai",
            preds=rig.write_preds([pred(key="zai", hours=10.0, unc=0.05),
                                   pred(key="openrouter", hours=10.0,
                                        unc=0.95)]))
        assert rc == 0
        assert out["action"] == "none"
        assert rig.node.calls == []


# ── Case 4: manual override delists despite quiet signals ─────────────────
class TestManualOverride:
    def test_manual_flag_delists_with_quiet_signals(self, rig):
        preds = rig.write_preds([pred(hours=10.0, unc=0.05)])
        rc, out, _ = rig.run("--manual", preds=preds)
        assert rc == 0
        assert out["action"] == "delist"
        assert "manual override" in out["reasons"]
        assert rig.node.kinds() == ["pull", "verify"]

    def test_force_delist_flag_ignores_triggers(self, rig):
        """Contract `--delist` (the task body's `--force-delist`): forces the
        pull with no preds and no trigger at all."""
        rc, out, _ = rig.run("--delist")
        assert rc == 0
        assert out["action"] == "delist"
        assert rig.node.kinds() == ["pull", "verify"]

    def test_marker_file_fires_without_cli_flag(self, rig):
        rig.place_marker()
        rc, out, _ = rig.run(preds=rig.write_preds([pred(hours=10.0)]))
        assert rc == 0
        assert out["action"] == "delist"
        assert rig.node.kinds() == ["pull", "verify"]

    def test_manual_override_is_never_gated_on_feed_staleness(self, rig):
        p = rig.age_preds(rig.write_preds([pred(hours=10.0, unc=0.9)]))
        rc, out, _ = rig.run("--manual", preds=p)
        assert rc == 0
        assert out["action"] == "delist"
        assert out["preds_stale"] is True      # observed …
        assert rig.node.kinds() == ["pull", "verify"]   # … but not obeyed


# ── Case 5: debounce — consecutive samples, one delist ────────────────────
class TestDebounceCooldown:
    def test_consecutive_acceleration_samples_delist_once(self, rig):
        """Baseline run, then an accelerated sample (delist #1, baseline
        consumed), then the SAME accelerated condition again inside the
        trigger-action window: no re-fire, total delists == 1."""
        rig.clock.advance(100)                      # t=100: baseline
        rig.run(preds=rig.write_preds([pred(hours=10.0)], name="a.json"))
        assert rig.node.kinds() == []

        rig.clock.advance(100)                      # t=200: acceleration
        rc2, out2, _ = rig.run(
            preds=rig.write_preds([pred(hours=5.0)], name="b.json"))
        assert rc2 == 0 and out2["action"] == "delist"

        rig.clock.advance(60)                       # t=260: same sample again,
        # still within TRIGGER_ACTION_WINDOW_S of the first delist
        assert 260 - 200 < rd.TRIGGER_ACTION_WINDOW_S
        rc3, out3, _ = rig.run(preds=rig.write_preds([pred(hours=5.0)],
                                                     name="b.json"))
        assert rc3 == 0
        assert out3["action"] == "none"
        assert out3["fire"] is False

        # exactly one delist across the whole window: 1 pull + 1 verify, ever
        assert rig.node.kinds() == ["pull", "verify"]
        st = rd.load_state(str(rig.state))
        assert st["delisted"] is True              # durable flag preserved
        assert st["pulled_models"] == ADVERTISED


# ── Case 6: SEMANTIC GUARD — ladder byte-identical across a delist ────────
class TestSemanticGuardLadderUntouched:
    def test_provider_ladder_byte_identical_across_delist(self, rig):
        """Delisting the SALE must never touch the routstr provider entry:
        the ladder artifact is byte-identical before/after, the
        upstream_providers table is row-identical, and no executed payload
        even names that table."""
        ladder_before = rig.node.ladder_bytes()
        providers_before = rig.node.providers_snapshot()

        rc, out, _ = rig.run("--manual")
        assert rc == 0 and out["action"] == "delist"

        assert rig.node.ladder_bytes() == ladder_before
        assert rig.node.providers_snapshot() == providers_before
        for kind, payload in rig.node.calls:
            assert "upstream_providers" not in payload
            assert "UPDATE models SET enabled=0" in payload or \
                "SELECT COUNT(*) FROM models" in payload
        # the routstr provider is still a routable ladder candidate
        assert any(name == "routstr" and enabled == 1
                   for name, enabled, _ in rig.node.providers_snapshot())

    def test_scoped_relist_restores_only_the_pulled_listing(self, rig):
        """Inverse direction of the same guard: relist re-enables exactly
        the captured names — never rows the operator disabled before the
        delist — and the ladder stays byte-identical throughout."""
        ladder_before = rig.node.ladder_bytes()
        rig.run("--manual")
        rc, out, _ = rig.run("--relist")
        assert rc == 0
        assert out["action"] == "relist"
        assert out["restored"] == len(ADVERTISED)

        models = rig.node.models_map()
        assert [n for n, e in models.items() if e == 1] == ADVERTISED
        assert all(models[n] == 0 for n in OPERATOR_DISABLED)
        assert rig.node.ladder_bytes() == ladder_before
        st = rd.load_state(str(rig.state))
        assert st.get("delisted") is False
        assert "pulled_models" not in st


# ── Case 7: idempotency — SALE already absent ─────────────────────────────
class TestIdempotencyAlreadyAbsent:
    def test_already_delisted_quiet_run_is_a_noop(self, rig):
        """State records a confirmed delist, the node advertises nothing,
        signals quiet: exit 0, action none, ZERO delist calls."""
        rig.run("--manual")                       # confirmed delist
        assert rig.node.kinds() == ["pull", "verify"]
        rc, out, _ = rig.run(preds=rig.write_preds([pred(hours=10.0,
                                                         unc=0.05)]))
        assert rc == 0
        assert out["action"] == "none"
        assert rig.node.kinds() == ["pull", "verify"]   # nothing new
        assert rd.load_state(str(rig.state))["delisted"] is True

    def test_forced_delist_on_absent_listing_is_idempotent_success(self, rig):
        """Even a FORCED re-delist with nothing advertised succeeds (pull
        captures [], re-fetch confirms 0) without clobbering the stored
        pulled_models or arming the breaker."""
        rig.run("--manual")
        st_before = rd.load_state(str(rig.state))
        rc, out, _ = rig.run("--delist")
        assert rc == 0
        assert out["action"] == "delist"
        assert out["confirmed"] is True
        assert out["pulled"] == []
        assert rig.node.kinds() == ["pull", "verify"] * 2
        st = rd.load_state(str(rig.state))
        assert st["pulled_models"] == st_before["pulled_models"]  # merge, no clobber
        assert st["consecutive_failures"] == 0


# ── Case 8: SLA — trigger → verified delist < 300 s (fake clock) ──────────
class TestSlaWindow:
    def test_poll_cadence_config_satisfies_the_window(self):
        """Config arithmetic: worst-case detection (one full poll cadence)
        plus the action budget fits the 300 s contract, and the budget can
        absorb a pull + verification round-trip at full ssh timeout."""
        assert rd.TRIGGER_ACTION_WINDOW_S == 300
        assert rd.POLL_CADENCE_S < rd.TRIGGER_ACTION_WINDOW_S
        assert rd.POLL_CADENCE_S + rd.ACTION_BUDGET_S == \
            rd.TRIGGER_ACTION_WINDOW_S
        assert 2 * rd.SSH_TIMEOUT_S <= rd.ACTION_BUDGET_S

    def test_trigger_sample_to_verified_delist_under_300s(self, rig):
        """Observable path with a fake clock: trigger sample lands at t=0,
        worst-case detection charges a full poll cadence (t=240), each ssh
        round-trip costs 25 s — the VERIFIED delist (pull + re-fetch) still
        completes inside the 300 s window, every round-trip timeout-clamped
        to the remaining action budget."""
        rig.node.round_trip_s = 25.0
        sample_t = rig.clock.now                      # trigger sample: t=0
        rig.clock.advance(rd.POLL_CADENCE_S)          # worst-case poll fires

        rc, out, _ = rig.run("--manual",
                             preds=rig.write_preds([pred(hours=10.0)]))
        assert rc == 0 and out["action"] == "delist" and out["confirmed"]

        confirmed_t = rig.clock.now
        assert confirmed_t - sample_t < rd.TRIGGER_ACTION_WINDOW_S   # < 300 s
        assert confirmed_t - sample_t <= \
            rd.POLL_CADENCE_S + rd.ACTION_BUDGET_S

        # the run's own deadline bookkeeping: pull + verify, never past budget
        assert [e["kind"] for e in rig.node.deadline_log] == ["pull", "verify"]
        for entry in rig.node.deadline_log:
            assert entry["remaining"] > 0
            assert entry["timeout"] <= rd.SSH_TIMEOUT_S
            assert entry["timeout"] <= rd.ACTION_BUDGET_S


# ── Case 9: circuit breaker — 3 consecutive API failures → BLOCKED ───────
class TestCircuitBreaker:
    def test_three_consecutive_failures_block_with_exit_3(self, rig):
        """The routstr API errors on every attempt: three consecutive failed
        RUNS trip the breaker — the third exits 3 and writes the durable
        BLOCKED marker into the state file."""
        rig.node.ssh_down = True
        rcs = []
        for _ in range(3):
            rc, out, _ = rig.run("--manual")
            rcs.append(rc)
        assert rcs == [1, 1, 3]

        raw = rig.state.read_text()
        assert '"blocked": true' in raw               # BLOCKED marker written
        st = rd.load_state(str(rig.state))
        assert st["blocked"] is True
        assert st["consecutive_failures"] == rd.BREAKER_THRESHOLD
        # 3 runs x (attempt + bounded retry) = 6 pulls; verify never reached
        assert rig.node.kinds() == ["pull"] * 6

    def test_blocked_run_refuses_all_remote_action(self, rig):
        """With the breaker open, a subsequent run refuses BEFORE any API
        call and still exits 3."""
        rig.node.ssh_down = True
        for _ in range(3):
            rig.run("--manual")
        rig.node.ssh_down = False                     # node healed …
        calls_before = len(rig.node.calls)
        rc, out, _ = rig.run("--manual")
        assert rc == 3
        assert out["action"] == "blocked"
        assert len(rig.node.calls) == calls_before    # … but never contacted

    def test_unblock_clears_breaker_and_next_run_succeeds(self, rig):
        rig.node.ssh_down = True
        for _ in range(3):
            rig.run("--manual")
        rig.node.ssh_down = False
        rc, out, _ = rig.run("--unblock", "--manual")
        assert rc == 0
        assert out["action"] == "delist"
        st = rd.load_state(str(rig.state))
        assert st.get("blocked") is False
        assert st["consecutive_failures"] == 0


# ── Case 10: atomicity — crash mid-write never observable ─────────────────
class TestAtomicStateWrites:
    @pytest.fixture(autouse=True)
    def _no_real_fsync(self, monkeypatch):
        """fsync durability is unassertable in-process, and this fleet
        host's disk can stall indefinitely inside fsync; the ATOMICITY the
        case guards is the tmp + os.replace protocol, which stays real."""
        monkeypatch.setattr(os, "fsync", lambda fd: None)

    def test_successful_save_swaps_whole_file_atomically(self, tmp_path,
                                                         monkeypatch):
        """At the instant of the swap (os.replace), the state path still
        holds the COMPLETE previous state and the tmp holds the COMPLETE
        new state — a reader can only ever observe old-or-new, never torn."""
        state_path = tmp_path / "state.json"
        old = {"ts": 1, "delisted": False, "snapshot": {"zai": 10.0}}
        assert rd.save_state(str(state_path), old) is True
        old_bytes = state_path.read_bytes()

        new = {"ts": 2, "delisted": True, "pulled_models": ADVERTISED}
        expected_new = json.dumps(new, indent=2, sort_keys=True).encode()
        real_replace, observed = os.replace, []

        def spying_replace(src, dst):
            if Path(dst) == state_path:
                observed.append({"pre_dst": Path(dst).read_bytes(),
                                 "tmp": Path(src).read_bytes()})
            return real_replace(src, dst)

        monkeypatch.setattr(os, "replace", spying_replace)
        assert rd.save_state(str(state_path), new) is True

        assert len(observed) == 1                     # exactly one swap
        assert observed[0]["pre_dst"] == old_bytes    # old intact at swap time
        assert observed[0]["tmp"] == expected_new     # new complete in tmp
        assert state_path.read_bytes() == expected_new
        assert list(tmp_path.glob(".*.tmp")) == []    # no tmp litter

    def test_crash_between_tmp_and_replace_keeps_previous_state(self, tmp_path,
                                                                monkeypatch):
        """Simulated crash after the tmp write, before the replace: the
        previous good state survives untouched and loadable — no partial or
        corrupt state file is ever observable."""
        state_path = tmp_path / "state.json"
        old = {"ts": 1, "delisted": False, "snapshot": {"zai": 10.0}}
        rd.save_state(str(state_path), old)
        real_replace = os.replace

        def crashing_replace(src, dst):
            if Path(dst) == state_path:
                raise OSError("simulated crash mid-state-write")
            return real_replace(src, dst)

        monkeypatch.setattr(os, "replace", crashing_replace)
        assert rd.save_state(str(state_path),
                             {"ts": 2, "delisted": True}) is False

        assert rd.load_state(str(state_path)) == old  # previous state intact
        assert list(tmp_path.glob(".*.tmp")) == []    # tmp cleaned up
        assert json.loads(state_path.read_text()) == old  # never torn


# ── Case 11: secret hygiene — no key/token in captured logs ───────────────
class TestSecretHygiene:
    SECRET = "nsec1TESTSECRETqxNEVERuseMEinPROD"

    @staticmethod
    def _patch_subprocess(monkeypatch):
        recorded = []

        def fake_run(argv, timeout=None, env=None, capture_output=False,
                     **kw):
            recorded.append({"argv": list(argv), "env": dict(env or {})})
            return subprocess.CompletedProcess(argv, 0)

        monkeypatch.setattr(rd.subprocess, "run", fake_run)
        return recorded

    def test_nsec_secret_never_leaks_into_logs_argv_or_state(self, rig, tmp_path,
                                                             monkeypatch,
                                                             capsys):
        """With --nsec wired, the secret reaches the publisher ONLY via the
        NOSTR_SECRET_KEY env var (--env-sec argv shape): it never appears in
        captured stdout logs, the durable state file, or any routstr API
        payload — and never on an argv (ps aux safe)."""
        nsec = tmp_path / "nsec"
        nsec.write_text(self.SECRET + "\n")
        recorded = self._patch_subprocess(monkeypatch)

        rc, out, _ = rig.run("--manual", "--nsec", str(nsec))
        assert rc == 0 and out["action"] == "delist"

        logs = capsys.readouterr().out + rig.state.read_text() + \
            json.dumps([p for _, p in rig.node.calls])
        assert self.SECRET not in logs                # no leak anywhere

        assert len(recorded) == 1                     # best-effort single publish
        argv, env = recorded[0]["argv"], recorded[0]["env"]
        assert self.SECRET not in argv                # never on the argv
        assert "--env-sec" in argv and "--sec" not in argv
        assert env.get("NOSTR_SECRET_KEY") == self.SECRET  # env-only path
        assert "30078" in [str(a) for a in argv]      # NIP-78 kind
        assert "d:routstr-delist" in argv

    def test_dry_run_publishes_no_event_and_flips_no_flag(self, rig, tmp_path,
                                                          monkeypatch):
        """Dry-run is intent-only: no nak subprocess, no durable delist
        flag — so no secret-bearing process is ever spawned."""
        nsec = tmp_path / "nsec"
        nsec.write_text(self.SECRET + "\n")
        recorded = self._patch_subprocess(monkeypatch)

        rc, out, _ = rig.run("--manual", "--dry-run", "--nsec", str(nsec))
        assert rc == 0
        assert recorded == []                         # nothing spawned
        st = rd.load_state(str(rig.state))
        assert "delisted" not in st   # fresh state: no durable flag introduced
        assert "last_dry_run" in st

        # a PRE-EXISTING delist flag must survive a dry run untouched
        assert rd.save_state(str(rig.state),
                             {"ts": 1, "delisted": True, "snapshot": {}})
        rc2, _, _ = rig.run("--manual", "--dry-run", "--nsec", str(nsec))
        assert rc2 == 0
        assert recorded == []                         # still nothing spawned
        assert rd.load_state(str(rig.state)).get("delisted") is True
