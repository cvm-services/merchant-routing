#!/usr/bin/env python3
"""probe_f13_pass27.py — fresh independent verification for the 27th offload pass.

Re-derives findings 1 (safety), 2 (confirmation) and 3 (fail-safe) of the
routstr delist review from primary sources ONLY (the script, both suites, the
stand-in doc).  Read-only: never writes to any artifact, never touches the
network, scratch stays off /tmp.

Sections:
  A  citation audit          — every file:line citation checked against source
  B  safety semantics        — payload scoping + ladder byte-identity by execution
  C  confirmation            — verify gating + relist asymmetry (structural + drive)
  D  fail-safe               — absent/garbage/stale feed + dry-run quiet path
  E  review-record integrity — shape, severity, parity, digests, missing path

Run twice; both runs must print the same tally and the same transcript sha256.
"""
from __future__ import annotations

import builtins
import contextlib
import hashlib
import io
import json
import os
import sqlite3
import sys
import time
import types
from pathlib import Path

REPO = Path("/home/c03rad0r/repos/merchant-routing")
BOT = Path.home() / ".hermes" / "bot"

SCRIPT = REPO / "src" / "routstr_delist.py"
CONTRACT = REPO / "tests" / "test_routstr_delist_contract.py"
MAINSUITE = REPO / "tests" / "test_routstr_delist.py"
DOC = REPO / "docs" / "routstr-delist.md"
DELIV = REPO / "docs" / "reviews" / "findings_1_3.md"
MIRROR = BOT / "docs" / "reviews" / "findings_1_3.md"
BOT_SCRIPT = BOT / "scripts" / "routstr_delist.py"
BOT_TESTS = BOT / "tests" / "test_routstr_delist.py"
MISSING_CONTRACT = BOT / "docs" / "routstr_delist_contract.md"

sys.path.insert(0, str(SCRIPT.parent))
import routstr_delist as rd  # noqa: E402

CHECKS: list[tuple[str, bool, str]] = []


def check(cid: str, ok: bool, detail: str = "") -> None:
    CHECKS.append((cid, bool(ok), detail))


def md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").split("\n")


# ── Section A: citation audit ─────────────────────────────────────────────
L_SCRIPT = lines(SCRIPT)
L_CONTRACT = lines(CONTRACT)
L_MAIN = lines(MAINSUITE)
L_DOC = lines(DOC)

# (citation-id, table, 1-based line, required substring)
CITATIONS = [
    # Find the script: SQL / payload scoping (F1)
    ("A:src355", L_SCRIPT, 355, "UPDATE models SET enabled=0 WHERE enabled=1;"),
    ("A:src361", L_SCRIPT, 361, "UPDATE models SET enabled=1;"),
    ("A:src394", L_SCRIPT, 394, "UPDATE models SET enabled=1 WHERE name IN"),
    ("A:src371", L_SCRIPT, 371, "SELECT name FROM models WHERE enabled=1"),
    ("A:src408", L_SCRIPT, 408, "SELECT COUNT(*) FROM models WHERE enabled=1"),
    ("A:src35", L_SCRIPT, 35, "upstream_providers"),
    ("A:src352", L_SCRIPT, 352, "upstream_providers"),
    ("A:src771", L_SCRIPT, 771, "upstream_providers"),
    # ssh argv shaping (F1)
    ("A:src414", L_SCRIPT, 414, "def build_ssh_docker_cmd"),
    ("A:src423", L_SCRIPT, 423, "shlex.quote(container)"),
    ("A:src424", L_SCRIPT, 424, "shlex.quote(payload)"),
    ("A:src425", L_SCRIPT, 425, 'return ["ssh", ssh_target, remote]'),
    ("A:src459", L_SCRIPT, 459, "subprocess.run(argv, timeout=30"),
    ("A:src808", L_SCRIPT, 808, "subprocess.run(cmd, capture_output=True"),
    # blanket relist refusal (F1)
    ("A:src600", L_SCRIPT, 600, "if args.relist:"),
    ("A:src606", L_SCRIPT, 606, "relist_refused"),
    ("A:src611", L_SCRIPT, 611, "return 1"),
    # confirmation (F2)
    ("A:src400", L_SCRIPT, 400, "def verify_pull_payload"),
    ("A:src682", L_SCRIPT, 682, "vres = backend.verify(deadline=deadline)"),
    ("A:src683", L_SCRIPT, 683, 'vres.get("ok") is True and vres.get("count") == 0'),
    ("A:src685", L_SCRIPT, 685, 'res["confirmed"] = True'),
    ("A:src687", L_SCRIPT, 687, "confirmed = True"),
    ("A:src75", L_SCRIPT, 75, "MAX_PULL_ATTEMPTS = 2"),
    ("A:src726", L_SCRIPT, 726, 'state["delisted"] = False'),
    ("A:src739", L_SCRIPT, 739, "return 3 if newly_blocked else 1"),
    ("A:src790", L_SCRIPT, 790, "def verify(self, dry_run=False, deadline=None)"),
    ("A:src814", L_SCRIPT, 814, "json.loads(out.splitlines()[-1])"),
    ("A:src822", L_SCRIPT, 822, 'proc.returncode == 0 and data.get("ok") is True'),
    # relist asymmetry (F2 MEDIUM)
    ("A:src626", L_SCRIPT, 626, "if not res.get(\"ok\"):"),
    ("A:src634", L_SCRIPT, 634, 'delisted=False, last_reason="relist"'),
    ("A:src635", L_SCRIPT, 635, 'state.pop("pulled_models", None)'),
    ("A:src680", L_SCRIPT, 680, "confirmed = True                   # intent only"),
    # fail-safe (F3)
    ("A:src78", L_SCRIPT, 78, "STALENESS_S = 1800"),
    ("A:src485", L_SCRIPT, 485, "def feed_is_stale"),
    ("A:src494", L_SCRIPT, 494, "return not (0 <= age <= max_age_s)"),
    ("A:src495", L_SCRIPT, 495, "except OSError:"),
    ("A:src496", L_SCRIPT, 496, "return True"),
    ("A:src589", L_SCRIPT, 589, "preds_stale = bool(args.preds) and bool(raw_preds) and"),
    ("A:src591", L_SCRIPT, 591, "if preds_stale:"),
    ("A:src592", L_SCRIPT, 592, "raw_preds = []"),
    ("A:src107", L_SCRIPT, 107, "if not preds_now or not preds_prev:"),
    ("A:src143", L_SCRIPT, 143, "if not preds:"),
    ("A:src479", L_SCRIPT, 479, "[d for d in data if isinstance(d, dict)]"),
    ("A:src481", L_SCRIPT, 481, "except Exception:"),
    ("A:src482", L_SCRIPT, 482, "return []"),
    ("A:src585", L_SCRIPT, 585, "preds_error = bool(args.preds) and not raw_preds"),
    ("A:src594", L_SCRIPT, 594, "if args.preds_key:"),
    ("A:src597", L_SCRIPT, 597, 'p.get("key") == args.preds_key'),
    ("A:src152", L_SCRIPT, 152, "or isinstance(unc, bool)"),
    ("A:src193", L_SCRIPT, 193, "def _hours(p):"),
    ("A:src196", L_SCRIPT, 196, "return h if isinstance(h, (int, float)) else None"),
    ("A:src261", L_SCRIPT, 261, "if preds:"),
    ("A:src262", L_SCRIPT, 262, 'new["snapshot"] = snapshot_preds(preds)'),
    ("A:src303", L_SCRIPT, 303, "var = variance_jumped(preds_now, threshold=variance_threshold)"),
    ("A:src649", L_SCRIPT, 649, 'fire = args.delist or dec["fire"]'),
    ("A:src651", L_SCRIPT, 651, "if not fire:"),
    ("A:src652", L_SCRIPT, 652, "state = update_state(state, ts=time.time(), preds=preds,"),
    ("A:src654", L_SCRIPT, 654, "save_state(args.state, state)"),
    ("A:src660", L_SCRIPT, 660, "return 1 if (preds_error or preds_stale) else 0"),
    ("A:src656", L_SCRIPT, 656, '"preds_error": preds_error,'),
    ("A:src699", L_SCRIPT, 699, "if args.dry_run:"),
    ("A:src705", L_SCRIPT, 705, 'state["last_dry_run"] = {"ts": state["ts"],'),
    ("A:src536", L_SCRIPT, 536, 'ap.add_argument("--ssh-target"'),
    ("A:src537", L_SCRIPT, 537, 'ap.add_argument("--container"'),
    ("A:src370", L_SCRIPT, 370, "/app/data/keys.db"),
    ("A:src407", L_SCRIPT, 407, "/app/data/keys.db"),
    ("A:src164", L_SCRIPT, 164, "def manual_override(override_path):"),
    ("A:src172", L_SCRIPT, 172, "return os.path.isfile(override_path)"),
    ("A:src580", L_SCRIPT, 580, "override = args.manual or manual_override(args.override)"),
    ("A:src561", L_SCRIPT, 561, "if args.unblock and blocked:"),
    ("A:src569", L_SCRIPT, 569, "if blocked:"),
    ("A:src578", L_SCRIPT, 578, "return 3"),
    ("A:src731", L_SCRIPT, 731, 'state["blocked"] = newly_blocked'),
    # contract suite
    ("A:contract468", L_CONTRACT, 468, "class TestSemanticGuardLadderUntouched:"),
    ("A:contract108", L_CONTRACT, 108, "self.ladder_artifact = tmpdir /"),
    ("A:contract129", L_CONTRACT, 129, "CREATE TABLE upstream_providers"),
    ("A:contract160", L_CONTRACT, 160, "SELECT name, enabled, weight FROM upstream_providers"),
    ("A:contract480", L_CONTRACT, 480, "assert rig.node.ladder_bytes() == ladder_before"),
    ("A:contract483", L_CONTRACT, 483, '"upstream_providers" not in payload'),
    ("A:contract346", L_CONTRACT, 346, "def test_unverified_pull_is_a_failed_delist"),
    ("A:contract308", L_CONTRACT, 308, "def test_first_run_without_baseline_is_quiet"),
    ("A:contract504", L_CONTRACT, 504, "assert rig.node.ladder_bytes() == ladder_before"),
    # main suite (tests:N)
    ("A:tests303", L_MAIN, 303, "def test_pull_sql_touches_only_models_listing"),
    ("A:tests311", L_MAIN, 311, "def test_relist_sql_touches_only_models_listing"),
    ("A:tests336", L_MAIN, 336, "def test_verify_payload_scoped_to_models_listing"),
    ("A:tests345", L_MAIN, 345, "def test_ssh_cmd_is_single_shlex_safe_remote_command"),
    ("A:tests176", L_MAIN, 176, "def test_first_run_never_fires_on_acceleration"),
    ("A:tests567", L_MAIN, 567, "def test_verify_gates_success"),
    ("A:tests603", L_MAIN, 603, "def test_verify_failure_is_attempt_failure"),
    ("A:tests146", L_MAIN, 146, "def test_non_numeric_uncertainty_ignored_not_crash"),
    ("A:tests243", L_MAIN, 243, "def test_update_state_empty_preds_preserves_baseline"),
    ("A:tests547", L_MAIN, 547, "def test_unreadable_preds_feed_is_error_not_quiet"),
    ("A:tests937", L_MAIN, 937, "def test_stale_feed_never_triggers"),
    ("A:tests968", L_MAIN, 968, "def test_staleness_threshold_boundary"),
    ("A:tests995", L_MAIN, 995, "def test_stale_feed_baseline_not_consumed"),
    ("A:tests980", L_MAIN, 980, "def test_stale_feed_exit_zero_when_override_fires"),
    ("A:tests776", L_MAIN, 776, "def test_preds_key_scopes_triggers"),
    ("A:tests1039", L_MAIN, 1039, "def test_relist_refuses_blanket_without_opt_in"),
    ("A:tests1056", L_MAIN, 1056, "def test_relist_any_executes_blanket"),
    ("A:tests1107", L_MAIN, 1107, "def test_pull_parses_last_line_json_and_gates_on_ok"),
    ("A:tests1116", L_MAIN, 1116, "def test_pull_garbage_stdout_is_failure"),
    ("A:tests1123", L_MAIN, 1123, "def test_pull_nonzero_rc_is_failure_even_with_ok_payload"),
    ("A:tests1146", L_MAIN, 1146, "def test_exception_is_failure_not_crash"),
    # stand-in doc
    ("A:docs29", L_DOC, 29, "**No blanket relist.**"),
    ("A:docs54", L_DOC, 54, "`--preds-key <key>` scopes evaluation"),
    ("A:docs55", L_DOC, 55, "never pull the routstr SALE."),
    ("A:docs56", L_DOC, 56, "**Freshness guard (cold-review finding 3):**"),
    ("A:docs60", L_DOC, 60, "The manual override is never gated on freshness."),
    ("A:docs69", L_DOC, 69, "**Re-fetch confirmation (cold-review finding 2):**"),
    ("A:docs71", L_DOC, 71, "Success is gated on the re-fetch reporting `count == 0`"),
    ("A:docs87", L_DOC, 87, "**Dry-run is intent-only (verification finding 7c):**"),
]
for cid, table, lineno, needle in CITATIONS:
    got = table[lineno - 1] if 0 <= lineno - 1 < len(table) else "<out-of-range>"
    check(cid, needle in got, f"L{lineno} want {needle!r}")


# ── fake sell node executing the module's REAL payloads ───────────────────
ADVERTISED = ["gpt-4o", "claude-3-5-sonnet", "llama-3.1-405b"]
PROVIDERS = [("openrouter", 1, 20.0), ("routstr", 1, 10.0), ("zai", 1, 30.0)]


class Node:
    def __init__(self) -> None:
        self.uri = (f"file:probe27{os.getpid()}x{id(self):x}"
                    "?mode=memory&cache=shared")
        con = sqlite3.connect(self.uri, uri=True)
        con.execute("CREATE TABLE models (name TEXT PRIMARY KEY, enabled INTEGER NOT NULL)")
        for n in ADVERTISED:
            con.execute("INSERT INTO models VALUES (?,1)", (n,))
        con.execute("INSERT INTO models VALUES ('operator-disabled-model',0)")
        con.execute("CREATE TABLE upstream_providers "
                    "(name TEXT PRIMARY KEY, enabled INTEGER NOT NULL, weight REAL NOT NULL)")
        for r in PROVIDERS:
            con.execute("INSERT INTO upstream_providers VALUES (?,?,?)", r)
        con.commit()
        self.con = con
        self.shim = types.ModuleType("sqlite3")
        self.shim.connect = lambda _p=None: sqlite3.connect(self.uri, uri=True)

    def models(self) -> dict:
        return dict(self.con.execute("SELECT name,enabled FROM models"))

    def providers(self) -> list:
        return list(self.con.execute(
            "SELECT name,enabled,weight FROM upstream_providers ORDER BY name"))

    def exec_payload(self, payload: str) -> dict:
        out = io.StringIO()
        node = self
        g = {"__builtins__": {"__import__": node._imp, "print": print},
             "node": node}
        with contextlib.redirect_stdout(out):
            exec(payload, g)  # noqa: S102 — executing the module's own builders
        return json.loads(out.getvalue().strip().splitlines()[-1])

    def _imp(self, name, globals=None, locals=None, fromlist=(), level=0):
        if name == "sqlite3":
            return self.shim
        return builtins.__import__(name, globals, locals, fromlist, level)


_NODE = Node()


# ── Section B: safety semantics ───────────────────────────────────────────
pull_sql = rd.pull_listing_sql()
check("B:pull-sql-models-only", "upstream_providers" not in pull_sql
      and pull_sql.strip().startswith("UPDATE models"), pull_sql)
check("B:blanket-sql-models-only", "upstream_providers" not in rd.relist_sql())

pp = rd.pull_listing_payload()
check("B:pull-names-models", "models" in pp and "upstream_providers" not in pp)
check("B:pull-one-update", pp.count("UPDATE") == 1, f"UPDATE x{pp.count('UPDATE')}")
vp = rd.verify_pull_payload()
check("B:verify-read-only", "UPDATE" not in vp.upper() and "SELECT COUNT(*)" in vp)
rp = rd.relist_payload(["a", "b"])
check("B:relist-scoped-one-update", rp.count("UPDATE") == 1
      and "WHERE name IN (?,?)" in rp)
check("B:relist-blanket-one-update", rd.relist_payload([]).count("UPDATE") == 1)
for tag, pl in (("pull", pp), ("verify", vp), ("relist", rp)):
    check(f"B:{tag}-no-dml",
          not any(k in pl.upper() for k in ("INSERT ", "DELETE ", "DROP ", "ALTER ", "REPLACE ")))

src = SCRIPT.read_text()
execlines_up = [i + 1 for i, ln in enumerate(L_SCRIPT)
                if "upstream_providers" in ln]
check("B:upstream-mentions-exactly-3", execlines_up == [35, 352, 771], str(execlines_up))
check("B:no-shell-true", "shell=True" not in src)
check("B:subprocess-run-2-sites", src.count("subprocess.run(") == 2,
      f"count={src.count('subprocess.run(')}")

# ssh argv: single shlex-safe remote element
cmd = rd.build_ssh_docker_cmd("debian@x", "evil'; rm -rf / #", "print(1)")
check("B:ssh-argv-len3", len(cmd) == 3 and cmd[0] == "ssh")
import shlex  # noqa: E402
rt = shlex.split(cmd[2])
check("B:hostile-container-single-token",
      rt[:2] == ["docker", "exec"] and rt[2] == "evil'; rm -rf / #",
      f"rt[:3]={rt[:3]}")

# semantic: execute payloads against the live two-table node
ladder_before = _NODE.providers()
res_pull = _NODE.exec_payload(pp)
check("B:semantic-pull-captures-names", res_pull.get("pulled") == ADVERTISED,
      str(res_pull.get("pulled")))
check("B:semantic-pull-disabled-all",
      set(_NODE.models().values()) == {0}, str(_NODE.models()))
res_verify = _NODE.exec_payload(vp)
check("B:semantic-verify-count0", res_verify.get("count") == 0)
check("B:semantic-operator-row-stays-off",
      _NODE.models().get("operator-disabled-model") == 0)
res_relist = _NODE.exec_payload(rd.relist_payload(res_pull.get("pulled") or []))
check("B:semantic-relist-restores-2",
      res_relist.get("restored") == len(ADVERTISED), str(res_relist))
check("B:semantic-relist-restores-only-captured",
      _NODE.models().get("operator-disabled-model") == 0
      and all(_NODE.models()[n] == 1 for n in ADVERTISED),
      str(_NODE.models()))
check("B:semantic-providers-unchanged", _NODE.providers() == ladder_before,
      str(_NODE.providers()))
check("B:semantic-routstr-still-candidate",
      any(n == "routstr" and e == 1 for n, e, _ in _NODE.providers()))

# blanket relist refused, no remote call (structural: refusal returns before backend)
seg = "\n".join(L_SCRIPT[599:611])
check("B:blanket-relist-refused-before-backend",
      "relist_refused" in seg and "relist(" not in seg, seg[-80:])

# ladder guard is tested semantically, not by substring alone
check("B:contract-builds-ladder", "ladder_artifact" in "\n".join(L_CONTRACT[105:113]))
check("B:contract-asserts-ladder-bytes",
      L_CONTRACT[479].strip().startswith("assert rig.node.ladder_bytes()"))


# ── Section C: confirmation ───────────────────────────────────────────────
check("C:verify-is-separate-roundtrip",
      "def verify(self" in src and "verify_pull_payload()" in
      "\n".join(L_SCRIPT[789:794]))
cloop = "\n".join(L_SCRIPT[670:698])
check("C:success-gated-on-count0", 'vres.get("count") == 0' in cloop)
check("C:lying-pull-forced-fail",
      'res["ok"] = False' in "\n".join(L_SCRIPT[690:695]))
check("C:retry-bounded", "MAX_PULL_ATTEMPTS" in cloop)

# relist asymmetry: the relist branch has NO verify round-trip and pops names
relist_branch = "\n".join(L_SCRIPT[599:645])
check("C:relist-no-verify-roundtrip", ".verify(" not in relist_branch)
check("C:relist-gated-on-selfreport", 'if not res.get("ok"):' in relist_branch)
check("C:relist-clears-flag", "delisted=False" in relist_branch)
check("C:relist-pops-names", 'state.pop("pulled_models", None)' in relist_branch)
delist_branch = "\n".join(L_SCRIPT[661:764])
check("C:delist-has-verify-roundtrip", "backend.verify(" in delist_branch)
check("C:delist-merge-no-clobber", "prior = state.get(\"pulled_models\") or []" in delist_branch)


# ── drive main() with a minimal fake backend ──────────────────────────────
class Clock:
    def __init__(self) -> None:
        self._m = 100000.0

    def monotonic(self) -> float:
        return self._m

    @staticmethod
    def time() -> float:
        return time.time()

    def advance(self, s: float) -> None:
        self._m += s


class FakeBackend:
    def __init__(self, node: Node, clock: Clock, *, ssh_down=False,
                 pull_lands=True) -> None:
        self.node, self.clock = node, clock
        self.ssh_down, self.pull_lands = ssh_down, pull_lands
        self.kinds: list[str] = []

    def pull(self, dry_run=False, deadline=None):
        return self._rt("pull", rd.pull_listing_payload(), dry_run)

    def verify(self, dry_run=False, deadline=None):
        return self._rt("verify", rd.verify_pull_payload(), dry_run)

    def relist(self, names=None, dry_run=False, deadline=None):
        return self._rt("relist", rd.relist_payload(names or []), dry_run)

    def _rt(self, kind, payload, dry_run):
        if dry_run:
            return {"ok": True, "dry_run": True, "action": kind}
        self.kinds.append(kind)
        if self.ssh_down:
            return {"ok": False, "action": kind, "rc": 255, "error": "ssh down"}
        revert = self.node.models() if (kind == "pull" and not self.pull_lands) else None
        data = self.node.exec_payload(payload)
        if revert is not None:
            con = self.node.shim.connect()
            for n, e in revert.items():
                con.execute("UPDATE models SET enabled=? WHERE name=?", (e, n))
            con.commit()
            con.close()
        return {"action": kind, "rc": 0, **data, "ok": data.get("ok") is True}


_REAL_FSYNC = os.fsync
os.fsync = lambda fd: None  # host workaround: fsync can stall indefinitely
_REAL_BACKEND = rd._SshBackend
_REAL_TIME = rd.time


def drive(tmp: Path, argv, *, preds=None, feed=None, ssh_down=False,
          pull_lands=True, state=None, override=None):
    clock = Clock()
    node = Node()
    be = FakeBackend(node, clock, ssh_down=ssh_down, pull_lands=pull_lands)
    rd._SshBackend = lambda t, c: be
    rd.time = clock
    sp = tmp / "state.json"
    op = tmp / "override"          # absent by default
    if state is not None:
        sp.write_text(json.dumps(state))
    full = ["--state", str(sp), "--override", str(op)]
    pf = None
    if feed is not None:
        pf = tmp / "preds.json"
        pf.write_text(feed)
        full += ["--preds", str(pf)]
    elif preds is not None:
        full += ["--preds", str(preds)]
    full += list(argv)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = rd.main(full)
    raw = out.getvalue()
    return rc, (json.loads(raw) if raw.strip() else {}), node, be, sp


SCRATCH = Path.home() / ".cache" / "f13-pass27" / "scratch"
import shutil  # noqa: E402
shutil.rmtree(SCRATCH, ignore_errors=True)
SCRATCH.mkdir(parents=True, exist_ok=True)


def fresh(tmp: Path) -> Path:
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True, exist_ok=True)
    return tmp


# C-happy: baseline then acceleration -> confirm by refetch
t = fresh(SCRATCH / "c1")
import tempfile  # noqa: E402
feed_a = t / "a.json"
feed_a.write_text(json.dumps([{"key": "zai", "window": "1h",
                               "exhausts_in_hours": 10.0, "uncertainty": 0.05}]))
rc0, _, _, _, _ = drive(t, [], preds=feed_a)
feed_b = t / "b.json"
feed_b.write_text(json.dumps([{"key": "zai", "window": "1h",
                               "exhausts_in_hours": 4.5, "uncertainty": 0.05}]))
rc1, out1, node1, be1, sp1 = drive(t, [], preds=feed_b)
check("C:happy-rc0", rc1 == 0, f"rc={rc1}")
check("C:happy-action-delist", out1.get("action") == "delist")
check("C:happy-confirmed", out1.get("confirmed") is True)
check("C:happy-verified-count0", out1.get("verified_count") == 0)
check("C:happy-kinds", be1.kinds == ["pull", "verify"], str(be1.kinds))
check("C:happy-durable-delisted",
      json.loads(sp1.read_text()).get("delisted") is True)

# C-lying: pull self-reports ok but refetch refutes -> failure semantics
t2 = fresh(SCRATCH / "c2")
rc2, out2, node2, be2, sp2 = drive(t2, ["--manual"], pull_lands=False)
check("C:lying-rc1", rc2 == 1, f"rc={rc2}")
check("C:lying-action", out2.get("action") == "delist_failed")
check("C:lying-kinds", be2.kinds == ["pull", "verify", "pull", "verify"], str(be2.kinds))
st2 = json.loads(sp2.read_text())
check("C:lying-no-flag", st2.get("delisted") is False)
check("C:lying-breaker-tick", st2.get("consecutive_failures") == 1)

# C-relist: gated on self-report only, no verify round-trip, names popped
t3 = fresh(SCRATCH / "c3")
drive(t3, ["--manual"])
rrc, rout, rnode, rbe, rsp = drive(t3, ["--relist"])
check("C:relist-rc0", rrc == 0)
check("C:relist-kinds-no-verify", rbe.kinds == ["relist"], str(rbe.kinds))
rst = json.loads(rsp.read_text())
check("C:relist-cleared-flag", rst.get("delisted") is False)
check("C:relist-names-popped", "pulled_models" not in rst)


# ── Section D: fail-safe ──────────────────────────────────────────────────
# feed_is_stale boundaries with an injected clock
tf = SCRATCH / "stale.json"
tf.write_text("[]")
T = os.path.getmtime(tf)
check("D:stale-fresh-false", rd.feed_is_stale(str(tf), now=T) is False)
check("D:stale-boundary-inclusive-false",
      rd.feed_is_stale(str(tf), now=T + 1800) is False)
check("D:stale-1801-true", rd.feed_is_stale(str(tf), now=T + 1801) is True)
check("D:stale-future-mtime-true", rd.feed_is_stale(str(tf), now=T - 1) is True)
check("D:stale-missing-path-true",
      rd.feed_is_stale(str(SCRATCH / "nope.json")) is True)

# absent feed -> quiet, rc0, no remote
t4 = fresh(SCRATCH / "d1")
rcA, outA, nodeA, beA, spA = drive(t4, [])
check("D:absence-quiet-rc0", rcA == 0 and outA.get("action") == "none")
check("D:absence-no-remote", beA.kinds == [])
check("D:absence-no-preds-error", outA.get("preds_error") is False)

# garbage feed -> rc1, preds_error, baseline intact
t5 = fresh(SCRATCH / "d2")
sp5 = t5 / "state.json"
sp5.write_text(json.dumps({"ts": 1, "delisted": False,
                           "snapshot": {"zai\x1f1h": 12.0}}))
gfeed = t5 / "preds.json"
gfeed.write_text("{not json")
rcG, outG, nodeG, beG, _ = drive(t5, [], preds=gfeed)
check("D:garbage-rc1", rcG == 1, f"rc={rcG}")
check("D:garbage-preds-error", outG.get("preds_error") is True)
check("D:garbage-action-none", outG.get("action") == "none")
check("D:garbage-no-remote", beG.kinds == [])
check("D:garbage-baseline-intact",
      json.loads(sp5.read_text()).get("snapshot") == {"zai\x1f1h": 12.0},
      str(json.loads(sp5.read_text()).get("snapshot")))

# stale feed -> rc1, preds_stale, no remote, baseline intact
t6 = fresh(SCRATCH / "d3")
sp6 = t6 / "state.json"
sp6.write_text(json.dumps({"ts": 1, "delisted": False,
                           "snapshot": {"zai\x1f1h": 12.0}}))
sfeed = t6 / "preds.json"
sfeed.write_text(json.dumps([{"key": "zai", "window": "1h",
                              "exhausts_in_hours": 6.0, "uncertainty": 0.99}]))
old = time.time() - 7200
os.utime(sfeed, (old, old))
rcS, outS, nodeS, beS, _ = drive(t6, [], preds=sfeed)
check("D:stale-rc1", rcS == 1, f"rc={rcS}")
check("D:stale-flag", outS.get("preds_stale") is True)
check("D:stale-action-none", outS.get("action") == "none")
check("D:stale-no-remote", beS.kinds == [])
check("D:stale-baseline-intact",
      json.loads(sp6.read_text()).get("snapshot") == {"zai\x1f1h": 12.0})

# manual override not gated on staleness
t7 = fresh(SCRATCH / "d4")
rcM, outM, nodeM, beM, spM = drive(t7, ["--manual"], preds=sfeed)
check("D:manual-not-gated-rc0", rcM == 0, f"rc={rcM}")
check("D:manual-not-gated-delist", outM.get("action") == "delist")
check("D:manual-stale-observed", outM.get("preds_stale") is True)

# unscoped default: foreign key's variance spike fires (LOW)
t8 = fresh(SCRATCH / "d5")
mix = json.dumps([{"key": "zai", "window": "1h", "exhausts_in_hours": 10.0,
                   "uncertainty": 0.05},
                  {"key": "openrouter", "window": "1h", "exhausts_in_hours": 10.0,
                   "uncertainty": 0.95}])
rcU, outU, nodeU, beU, _ = drive(t8, [], feed=mix)
check("D:unscoped-default-fires",
      outU.get("action") == "delist"
      and any("variance" in r for r in outU.get("reasons", [])),
      f"action={outU.get('action')} reasons={outU.get('reasons')}")
t9 = fresh(SCRATCH / "d6")
rcK, outK, nodeK, beK, _ = drive(t9, ["--preds-key", "zai"], feed=mix)
check("D:scoped-filter-quiets", outK.get("action") == "none" and beK.kinds == [])

# quiet dry-run refreshes the baseline with no last_dry_run (MEDIUM)
t10 = fresh(SCRATCH / "d7")
sp10 = t10 / "state.json"
sp10.write_text(json.dumps({"ts": 1, "delisted": False,
                            "snapshot": {"zai\x1f1h": 12.0}}))
dfeed = t10 / "preds.json"
dfeed.write_text(json.dumps([{"key": "zai", "window": "1h",
                              "exhausts_in_hours": 11.0, "uncertainty": 0.05}]))
rcQ, outQ, nodeQ, beQ, _ = drive(t10, ["--dry-run"], preds=dfeed)
qst = json.loads(sp10.read_text())
check("D:quiet-dryrun-rc0", rcQ == 0, f"rc={rcQ}")
check("D:quiet-dryrun-refreshes-baseline",
      qst.get("snapshot") == {"zai\x1f1h": 11.0}, str(qst.get("snapshot")))
check("D:quiet-dryrun-no-last-run", "last_dry_run" not in qst)

# firing dry-run records last_dry_run and runs pull only
t11 = fresh(SCRATCH / "d8")
rcF, outF, nodeF, beF, spF = drive(t11, ["--manual", "--dry-run"])
fst = json.loads(spF.read_text())
check("D:firing-dryrun-records-intent", "last_dry_run" in fst)
check("D:firing-dryrun-pull-only", beF.kinds == [], str(beF.kinds))
check("D:firing-dryrun-no-flag", "delisted" not in fst)


# ── Section E: review-record integrity ────────────────────────────────────
dtxt = DELIV.read_text()
import re  # noqa: E402
heads = re.findall(r"^## Finding (\d+)", dtxt, re.M)
check("E:three-finding-sections", heads == ["1", "2", "3"], str(heads))
check("E:exactly-three-h2", dtxt.count("\n## ") == 3, f"count={dtxt.count(chr(10) + '## ')}")
check("E:no-appended-section", re.search(r"^## §", dtxt, re.M) is None)
sev = re.findall(r"^severity: \*\*(OK|BLOCKER|HIGH|MEDIUM|LOW)\*\*", dtxt, re.M)
check("E:three-severity-tags", len(sev) == 3 and set(sev) == {"OK"}, str(sev))
check("E:mirror-parity", md5(DELIV) == md5(MIRROR),
      "equal" if md5(DELIV) == md5(MIRROR) else "DIFFER")
check("E:contract-path-missing-HIGH", not MISSING_CONTRACT.exists())
check("E:bot-parity-src", md5(SCRIPT) == md5(BOT_SCRIPT))
check("E:bot-parity-tests", md5(CONTRACT) == md5(BOT_TESTS))
check("E:bot-parity-docs", md5(DOC) == md5(BOT / "docs" / "routstr-delist.md"))
check("E:script-md5", md5(SCRIPT).startswith("2ea724ef08d857cd"), md5(SCRIPT))
check("E:contract-md5", md5(CONTRACT).startswith("031851b356f0de40"), md5(CONTRACT))
check("E:docs-md5", md5(DOC).startswith("e385af98b9c142ee"), md5(DOC))
check("E:ordinal-preamble", "offload pass" in dtxt and
      re.search(r"twenty-\w+ independent offload pass", dtxt) is not None)


# ── tally ─────────────────────────────────────────────────────────────────
os.fsync = _REAL_FSYNC
rd._SshBackend = _REAL_BACKEND
rd.time = _REAL_TIME

GROUPS = {"A": 0, "B": 0, "C": 0, "D": 0, "E": 0}
for cid, ok, _ in CHECKS:
    GROUPS[cid[0]] += 1
passed = sum(1 for _, ok, _ in CHECKS if ok)
fails = [(c, d) for c, ok, d in CHECKS if not ok]

transcript = "\n".join(f"{c}: {'PASS' if ok else 'FAIL'} {d}"
                       for c, ok, d in CHECKS)
print(transcript)
print("GROUP TALLY: " + " ".join(f"{k}={v}" for k, v in GROUPS.items())
      + f" total={len(CHECKS)}")
print(f"RESULT: {passed}/{len(CHECKS)} PASS  fails={len(fails)}")
for c, d in fails:
    print(f"[FAIL] {c}: {d}")
print(f"TRANSCRIPT SHA256: {hashlib.sha256(transcript.encode()).hexdigest()}")
raise SystemExit(0 if not fails else 1)
