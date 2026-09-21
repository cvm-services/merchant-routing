#!/usr/bin/env python3
"""src/routstr_delist.py — T-D routstr dynamic delist (ADR-007 Gate 4).

Pulls the routstr SALE (the advertised model listing on the routstr sell node)
programmatically within 5 minutes of a trigger, WITHOUT disabling the routstr
provider in the T470 flat-router ladder.

Distinction that matters (task body):
    delisting the routstr SALE  !=  disabling the routstr provider.
    The provider stays in the ladder (still routable / still a candidate);
    only the PUBLIC advertisement of models-for-sale is pulled.

Triggers (ADR-007):
    1. Burn-rate accelerates  — predicted exhaustion moves FORWARD
       (hours-to-exhaustion decreases) past a threshold between consecutive
       readings of burn_predictor.predict_exhaustion().
    2. Kalman variance elevated — a prediction window's `uncertainty` (the
       Kalman filter's variance/uncertainty term) exceeds a threshold.
       Level-based by design: while the condition persists the run keeps
       asserting delist, so a manual --relist is not sticky. (Cold-review
       finding 5, accepted semantics — see docs/routstr-delist.md.)
    3. Manual override        — a marker file / --manual flag.

Implementation (task note): "a flag in the objects that publishes the listing,
plus a websocket/event-based delist." Concretely:
  * flag  — a durable delist flag in the state the listing publisher
            publishes, so the publisher's advertisement reflects
            delisted=true.
  * event — an event-based delist: the script emits a kind-30078
            `d=routstr-delist` Nostr event (NIP-78 application data, via nak)
            that sell-side consumers react to, in addition to the direct SSH
            delist of the sell node.

The remote delist targets the sell node's `models` table only (the advertised
listing) — it never touches upstream_providers or the T470 router. Relist is
the exact inverse: the pull captures which model names were advertised and
the relist re-enables only those.

Failure semantics (cold-review findings 2/3): a FAILED pull never consumes
the acceleration baseline, never records delisted=true, and exits non-zero so
cron/monitoring sees it. An unreadable --preds feed never wipes the stored
baseline; it surfaces `preds_error` and exits non-zero when no trigger fired.

The module is deliberately split so every trigger/decision/state/helper is
pure and unit-testable (Gate 1 TDD); the only side-effecting function is the
backend (SSH docker exec on the sell node), which is injected so tests stay
hermetic.
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import time

# ── Thresholds / constants ────────────────────────────────────────────────
EXHAUST_MOVE_HOURS = 2.0       # predicted exhaustion moved forward by >= this many
                               # hours -> burn-acceleration trigger (default)
VARIANCE_THRESHOLD = 0.30      # Kalman `uncertainty` above this -> variance trigger

# 5-minute SLA arithmetic (cold-review finding 5 — these are now wired, not
# decorative): worst-case detection is one full poll cadence (cron */4 =
# POLL_CADENCE_S), and the in-run action must fit the remaining budget.
#   POLL_CADENCE_S + ACTION_BUDGET_S == TRIGGER_ACTION_WINDOW_S (== 300 s)
# The action budget is enforced as a real monotonic deadline inside main():
# every remote round-trip is timeout-clamped to the remaining budget, so a
# run can never spend more than ACTION_BUDGET_S acting.
TRIGGER_ACTION_WINDOW_S = 300  # 5 minutes: pull must happen within this of a trigger
POLL_CADENCE_S = 240           # documented cron cadence: */4 minutes
ACTION_BUDGET_S = TRIGGER_ACTION_WINDOW_S - POLL_CADENCE_S   # 60 s
SSH_TIMEOUT_S = 30             # per round-trip; pull + verify = 2*30 <= budget
MAX_PULL_ATTEMPTS = 2          # initial + one bounded in-run retry

BREAKER_THRESHOLD = 3          # task body: 3 consecutive failed runs -> BLOCKED
STALENESS_S = 1800             # --preds feed older than 30 min is dead data
DELIST_EVENT_KIND = 30078      # NIP-78 application data (parametrized replaceable)
                               # — NOT a squatted registered 303xx live-event kind
DELIST_EVENT_TAG = "routstr-delist"
_SNAP_SEP = "\x1f"             # snapshot key separator (safe for keys containing '|')

_DEFAULT_STATE_PATH = os.path.expanduser("~/.hermes/bot/routstr_delist_state.json")
_DEFAULT_OVERRIDE_PATH = os.path.expanduser("~/.hermes/bot/routstr_delist.override")
_DEFAULT_SSH_TARGET = "debian@23.182.128.51"   # VPS2 (routstr-public sell node)
_DEFAULT_CONTAINER = "routstr-public"
_DEFAULT_NAK = os.path.expanduser("~/.local/bin/nak")


# ── Trigger 1: burn-rate accelerates (predicted exhaustion moves forward) ──
def exhaustion_accelerated(preds_now, preds_prev, *, move_hours=EXHAUST_MOVE_HOURS):
    """List of windows whose predicted exhaustion moved FORWARD (hours left
    decreased) by `move_hours` or more between the previous and current
    prediction sets.

    Args:
        preds_now:  list of prediction dicts (burn_predictor.predict_exhaustion
                    shape: key, window, exhausts_in_hours, uncertainty, ...).
        preds_prev: previous list of prediction dicts, or [] / None if none.
        move_hours: minimum hours-forward movement to count as acceleration.

    Returns a list of dicts:
        {"key", "window", "prev_hours", "now_hours"}
    Empty when there is no acceleration (or no baseline to compare).
    """
    if not preds_now or not preds_prev:
        return []

    prev_map = {_pred_key(p): _hours(p) for p in preds_prev if _hours(p) is not None}
    fired = []
    for p in preds_now:
        h_now = _hours(p)
        if h_now is None:
            continue
        h_prev = prev_map.get(_pred_key(p))
        if h_prev is None:
            continue
        # hours left went DOWN => exhaustion got SOONER => moved forward.
        moved = h_prev - h_now
        if moved >= move_hours:
            fired.append({
                "key": p.get("key"),
                "window": p.get("window"),
                "prev_hours": h_prev,
                "now_hours": h_now,
            })
    return fired


# ── Trigger 2: Kalman variance elevated ───────────────────────────────────
def variance_jumped(preds, *, threshold=VARIANCE_THRESHOLD, key=None):
    """List of prediction windows whose Kalman `uncertainty` (variance term)
    exceeds `threshold`. Level-based: fires every run while elevated.

    Args:
        preds:     list of prediction dicts.
        threshold: uncertainty above which the trigger fires.
        key:       optional filter — only check predictions for this key.

    Returns list of dicts {"key", "window", "uncertainty"}.
    """
    if not preds:
        return []
    fired = []
    for p in preds:
        if key is not None and p.get("key") != key:
            continue
        unc = p.get("uncertainty")
        # type-guarded like exhausts_in_hours (cold-review should-fix):
        # bool is an int subclass — excluded explicitly.
        if not isinstance(unc, (int, float)) or isinstance(unc, bool):
            continue
        if unc > threshold:
            fired.append({
                "key": p.get("key"),
                "window": p.get("window"),
                "uncertainty": unc,
            })
    return fired


# ── Trigger 3: manual override ────────────────────────────────────────────
def manual_override(override_path):
    """True when a manual-override marker file exists.

    Presence of the marker (not its contents) is the override. A None path
    or a missing/unreadable path is never an override.
    """
    if not override_path:
        return False
    return os.path.isfile(override_path)


# ── Snapshot / state helpers ──────────────────────────────────────────────
def _snap_key(p):
    return f"{p.get('key')}{_SNAP_SEP}{p.get('window')}"


def _parse_snap_key(k):
    """Inverse of _snap_key; tolerates legacy '|' separated state files."""
    sep = _SNAP_SEP if _SNAP_SEP in k else ("|" if "|" in k else None)
    if sep is None:
        return k, "unknown"
    key, _, window = k.partition(sep)
    return key, window if window else "unknown"


def _pred_key(p):
    return _snap_key(p)


def _hours(p):
    """Return exhausts_in_hours or None when unusable."""
    h = p.get("exhausts_in_hours")
    return h if isinstance(h, (int, float)) else None


def snapshot_preds(preds):
    """Collapse a prediction list into {key<sep>window: exhausts_in_hours} for
    a durable per-window baseline used on the NEXT comparison."""
    snap = {}
    if preds:
        for p in preds:
            h = _hours(p)
            if h is not None:
                snap[_snap_key(p)] = h
    return snap


def load_state(path):
    """Load the durable state dict; never raises — returns {} on any failure."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_state(path, state):
    """Persist state dict ATOMICALLY (cold-review finding 4): tmp file in the
    same directory + fsync + os.replace, so a concurrent reader never
    observes a torn/partial file and a crash mid-write leaves the previous
    state fully intact. Returns True on success, False on any error."""
    tmp = None
    try:
        d = os.path.dirname(path) or "."
        os.makedirs(d, exist_ok=True)
        tmp = os.path.join(d, f".{os.path.basename(path)}.{os.getpid()}.tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=2, sort_keys=True)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
        tmp = None
        return True
    except Exception:
        return False
    finally:
        if tmp is not None:
            try:
                os.unlink(tmp)
            except OSError:
                pass


def update_state(state, *, ts, preds, delisted, last_reason=None, extra=None):
    """Return a NEW state dict carrying the next baseline + delist flag.

    The `delisted` field is the "flag in the objects that publishes the
    listing": the listing publisher reads this durable flag so its
    advertisement reflects delisted=true.

    An EMPTY preds list never overwrites the stored baseline snapshot — a
    missing/corrupt feed must not blind the acceleration trigger (cold-review
    finding 3).
    """
    new = dict(state or {})
    new["ts"] = ts
    if preds:
        new["snapshot"] = snapshot_preds(preds)
    new["delisted"] = bool(delisted)
    if last_reason is not None:
        new["last_reason"] = last_reason
    if extra:
        new.update(extra)
    return new


# ── Decision assembly ─────────────────────────────────────────────────────
def evaluate_triggers(preds_now, prev_state, *, override=False,
                      move_hours=EXHAUST_MOVE_HOURS,
                      variance_threshold=VARIANCE_THRESHOLD):
    """Assemble a single delist decision from all three trigger sources.

    Args:
        preds_now:  current burn predictor predictions (list of dicts).
        prev_state: prior run's state dict ({"snapshot": {...}} or None on
                    first run / no baseline).
        override:   whether a manual override is active.
        move_hours / variance_threshold: trigger thresholds.

    Returns a decision dict:
        {"fire": bool, "reasons": [str, ...], "triggers": {...}}
    A first run with no baseline NEVER fires on acceleration (it would be a
    false positive); it can still fire on variance or manual override.
    """
    prev_snapshot = {}
    if isinstance(prev_state, dict):
        s = prev_state.get("snapshot")
        if isinstance(s, dict):
            prev_snapshot = s
    # Rebuild a list of previous pred dicts from the snapshot so the pure
    # comparison function needs no special casing.
    preds_prev = []
    for k, v in prev_snapshot.items():
        key, window = _parse_snap_key(k)
        preds_prev.append({"key": key, "window": window,
                           "exhausts_in_hours": v})

    accel = exhaustion_accelerated(preds_now, preds_prev, move_hours=move_hours)
    var = variance_jumped(preds_now, threshold=variance_threshold)

    reasons = []
    if accel:
        reasons.append(f"exhaustion accelerated ({len(accel)} window(s): "
                       + ", ".join(f"{a['key']}/{a['window']} {a['now_hours']:.1f}h"
                                   for a in accel) + ")")
    if var:
        reasons.append(f"kalman variance jumped ({len(var)} window(s), max "
                       + f"{max(v['uncertainty'] for v in var):.2f})")
    if override:
        reasons.append("manual override")

    return {
        "fire": bool(accel or var or override),
        "reasons": reasons,
        "triggers": {"accel": accel, "variance": var, "manual": override},
    }


# ── Listing action (backend-injected; provider stays in ladder) ───────────
def pull_listing(backend, *, dry_run=False, deadline=None):
    """Pull the routstr SALE listing on the sell node.

    Delegates to `backend` so the remote/SSH path is swappable in tests.
    `backend` must expose pull(**kw) and (for dry-run) dry_run_pull(**kw).
    `deadline` is a monotonic clock deadline for the SLA budget.

    Returns backend result dict.
    """
    if dry_run and hasattr(backend, "dry_run_pull"):
        return backend.dry_run_pull(dry_run=True)
    return backend.pull(dry_run=dry_run, deadline=deadline)


def relist(backend, *, names=None, dry_run=False, deadline=None):
    """Restore the routstr SALE listing on the sell node (scoped to the
    model names captured by the pull when known)."""
    if dry_run and hasattr(backend, "dry_run_relist"):
        return backend.dry_run_relist(names=names or [], dry_run=True)
    return backend.relist(names=names or [], dry_run=dry_run,
                          deadline=deadline)


# ── SQL / command shaping (hermetic — no network) ─────────────────────────
def pull_listing_sql():
    """SQL that pulls the advertised listing: disable every advertised model.

    Scoped STRICTLY to the `models` table's `enabled` flag. It deliberately
    does NOT touch upstream_providers or any router provider row — the
    provider stays in the ladder (task body).
    """
    return "UPDATE models SET enabled=0 WHERE enabled=1;"


def relist_sql():
    """SQL that restores the listing when no captured name set exists
    (legacy fallback; the scoped path is parameterized, see relist_payload)."""
    return "UPDATE models SET enabled=1;"


def pull_listing_payload():
    """python -c payload: capture the advertised model NAMES, disable exactly
    those rows, and report the captured names as JSON so the caller can store
    them for a scoped relist."""
    return (
        "import sqlite3,json;"
        "db=sqlite3.connect('/app/data/keys.db');"
        "rows=[r[0] for r in db.execute('SELECT name FROM models WHERE enabled=1')];"
        f"db.execute({pull_listing_sql()!r});"
        "db.commit();"
        "print(json.dumps({'ok':True,'pulled':rows}))"
    )


def relist_payload(names):
    """python -c payload restoring only the previously-pulled model names.
    Parameterized (no string interpolation of DB values into SQL)."""
    names = list(names or [])
    if not names:
        return (
            "import sqlite3,json;"
            "db=sqlite3.connect('/app/data/keys.db');"
            f"db.execute({relist_sql()!r});"
            "db.commit();"
            "print(json.dumps({'ok':True}))"
        )
    placeholders = ",".join("?" * len(names))
    return (
        "import sqlite3,json;"
        "db=sqlite3.connect('/app/data/keys.db');"
        f"c=db.execute('UPDATE models SET enabled=1 WHERE name IN ({placeholders})',{names!r});"
        "db.commit();"
        "print(json.dumps({'ok':True,'restored':c.rowcount}))"
    )


def verify_pull_payload():
    """python -c payload for the post-pull RE-FETCH (cold-review finding 2):
    an independent read-only round-trip counting still-advertised models.
    Success of a delist is gated on this count being 0 — never on the pull
    round-trip's own self-report. Read-only: SELECT only, never mutates."""
    return (
        "import sqlite3,json;"
        "db=sqlite3.connect('/app/data/keys.db');"
        "n=db.execute('SELECT COUNT(*) FROM models WHERE enabled=1')"
        ".fetchone()[0];"
        "print(json.dumps({'ok':True,'count':n}))"
    )


def build_ssh_docker_cmd(ssh_target, container, payload):
    """Build the argv that runs a python3 payload inside the sell node
    container, as a SINGLE ssh remote-command argument.

    ssh joins everything after the host into one string that the REMOTE shell
    parses, so the remote command must be shell-quoted as one element
    (cold-review finding 1): shlex.quote the container and the payload.
    Returns a list suitable for subprocess (no LOCAL shell involved).
    """
    remote = " ".join(["docker", "exec", shlex.quote(container),
                       "python3", "-c", shlex.quote(payload)])
    return ["ssh", ssh_target, remote]


# ── Event-based delist signal (kind-30078 via nak) ────────────────────────
def build_delist_event(sec_file, *, nsec_env="NOSTR_SECRET_KEY",
                       nak=_DEFAULT_NAK, relays=None, delisted=True):
    """Return the argv for a `nak` kind-30078 `d=routstr-delist` publish.

    Uses the env-var secret path (never --sec — see routstr-node-ops skill:
    --sec exposes the key in ps aux). Returns None when the nsec file is
    missing. Hermetic — only builds argv, does not run it.
    """
    if not sec_file or not os.path.isfile(sec_file):
        return None
    rel = relays or ["wss://relay.primal.net", "wss://nos.lol", "wss://relay.damus.io"]
    content = json.dumps({"delisted": delisted, "ts": time.time(),
                          "tag": DELIST_EVENT_TAG}, separators=(",", ":"))
    argv = [nak, "event", "--kind", str(DELIST_EVENT_KIND),
            "--tag", f"d:{DELIST_EVENT_TAG}",
            "--tag", "t:routstr",
            "--content", content,
            "--env-sec"]
    argv += rel
    return argv


def publish_delist_event(sec_file, *, delisted=True):
    """Best-effort kind-30078 publish (never raises, returns argv or None)."""
    argv = build_delist_event(sec_file, delisted=delisted)
    if not argv:
        return None
    try:
        with open(sec_file) as fh:
            nsec = fh.read().strip()
        subprocess.run(argv, timeout=30,
                       env=dict(os.environ, NOSTR_SECRET_KEY=nsec),
                       capture_output=True)
    except Exception:
        pass
    return argv


# ── CLI ───────────────────────────────────────────────────────────────────
def _read_preds(pred_input):
    """Parse current predictions: a JSON list of prediction DICTS from a file
    path, or [] (caller treats an explicitly-given-but-unusable path as a
    feed error). Non-dict entries are dropped (never crash on a bad feed).
    Never raises."""
    if not pred_input:
        return []
    try:
        with open(pred_input, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, list):
            return [d for d in data if isinstance(d, dict)]
        return []
    except Exception:
        return []


def feed_is_stale(pred_input, *, max_age_s=STALENESS_S, now=None):
    """True when the --preds file is older than max_age_s (mtime-based).

    Fail-safe direction (cold-review finding 3, HIGH): a feed whose age
    cannot be determined is treated as STALE — dead data must never drive a
    delist. Returns False only for a file that provably is fresh."""
    try:
        age = (now if now is not None else time.time()) - \
            os.path.getmtime(pred_input)
        return not (0 <= age <= max_age_s)
    except OSError:
        return True


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="routstr_delist.py",
        description="Pull the routstr SALE listing within 5 min of a trigger "
                    "(burn acceleration / kalman variance / manual override). "
                    "The routstr provider stays in the ladder.",
    )
    ap.add_argument("--state", default=_DEFAULT_STATE_PATH,
                    help="durable trigger-baseline state JSON")
    ap.add_argument("--override", default=_DEFAULT_OVERRIDE_PATH,
                    help="manual override marker path")
    ap.add_argument("--preds", default=None,
                    help="path to a JSON list of current predictions "
                         "(omit to run with no live baseline)")
    ap.add_argument("--preds-key", default=None,
                    help="only evaluate predictions with this `key` (scopes "
                         "triggers to the routstr-relevant feed entries)")
    ap.add_argument("--move-hours", type=float, default=EXHAUST_MOVE_HOURS,
                    help="exhaustion must move forward by this many hours to fire")
    ap.add_argument("--variance", type=float, default=VARIANCE_THRESHOLD,
                    help="kalman uncertainty above this fires")
    ap.add_argument("--manual", action="store_true",
                    help="force a manual delist trigger")
    ap.add_argument("--delist", action="store_true",
                    help="force-pull the listing now (ignore triggers)")
    ap.add_argument("--relist", action="store_true",
                    help="restore the listing (scoped to the pulled names)")
    ap.add_argument("--relist-any", action="store_true",
                    help="EXPLICIT opt-in: allow the blanket relist when no "
                         "pulled names are stored (enables every model row)")
    ap.add_argument("--unblock", action="store_true",
                    help="clear a BLOCKED circuit breaker and proceed")
    ap.add_argument("--status", action="store_true",
                    help="print current delist state and exit")
    ap.add_argument("--dry-run", action="store_true",
                    help="do not execute the remote delist (print intent; "
                         "flips no durable delist flag, publishes nothing)")
    ap.add_argument("--ssh-target", default=_DEFAULT_SSH_TARGET)
    ap.add_argument("--container", default=_DEFAULT_CONTAINER)
    ap.add_argument("--nsec", default=None,
                    help="path to a Nostr nsec file for the event-based delist "
                         "signal (optional)")
    args = ap.parse_args(argv)

    state = load_state(args.state)
    fails = state.get("consecutive_failures", 0)
    fails = fails if isinstance(fails, int) else 0
    blocked = bool(state.get("blocked"))

    if args.status:
        print(json.dumps({"delisted": state.get("delisted", False),
                          "ts": state.get("ts"),
                          "last_reason": state.get("last_reason"),
                          "pulled_models": state.get("pulled_models", []),
                          "snapshot_windows": len(state.get("snapshot", {})),
                          "consecutive_failures": fails,
                          "blocked": blocked},
                         indent=2, sort_keys=True))
        return 0

    # Circuit breaker (task body: 3x fail -> BLOCKED). --unblock is the
    # operator's explicit clear; it lets the same run proceed.
    if args.unblock and blocked:
        state.pop("blocked", None)
        state.pop("consecutive_failures", None)
        state["ts"] = time.time()
        save_state(args.state, state)
        blocked = False
        fails = 0

    if blocked:
        # Attempt 4 never runs: every remote action is refused (relist and
        # delist alike) until the operator clears the breaker.
        print(json.dumps({"action": "blocked", "ok": False, "blocked": True,
                          "consecutive_failures": fails,
                          "reason": "circuit breaker open after "
                                    f"{BREAKER_THRESHOLD} consecutive failed "
                                    "runs; re-run with --unblock to clear",
                          "ts": time.time()}, indent=2, sort_keys=True))
        return 3

    override = args.manual or manual_override(args.override)
    raw_preds = _read_preds(args.preds)
    # An explicitly requested feed that yields nothing is a FEED ERROR: keep
    # going (manual override must still work) but never treat it as "quiet"
    # (cold-review finding 3).
    preds_error = bool(args.preds) and not raw_preds
    # Freshness guard (cold-review finding 3, HIGH): a stale feed is dead
    # data — it must never trigger (level-based variance especially) and
    # must never refresh the acceleration baseline.
    preds_stale = bool(args.preds) and bool(raw_preds) and \
        feed_is_stale(args.preds)
    if preds_stale:
        raw_preds = []
    preds = raw_preds
    if args.preds_key:
        # Scope triggers to the routstr-relevant entries (review finding 3):
        # another provider's variance spike must not pull the routstr SALE.
        preds = [p for p in raw_preds if p.get("key") == args.preds_key]

    # Re-enable: --relist overrides everything.
    if args.relist:
        names = state.get("pulled_models") or []
        if not names and not args.relist_any:
            # Blanket relist REFUSED (cold-review finding 4): without the
            # captured name set, `UPDATE models SET enabled=1` would enable
            # rows the operator had deliberately disabled before the delist.
            print(json.dumps({"action": "relist_refused", "ok": False,
                              "reason": "no pulled_models captured; pass "
                                        "--relist-any to force the blanket "
                                        "relist",
                              "ts": time.time()}, indent=2, sort_keys=True))
            return 1
        deadline = time.monotonic() + ACTION_BUDGET_S
        res = relist(_SshBackend(args.ssh_target, args.container),
                     names=names, dry_run=args.dry_run, deadline=deadline)
        if args.dry_run:
            # Intent only (purity): flip no durable flag, publish no event.
            state = dict(state)
            state["ts"] = time.time()
            state["last_dry_run"] = {"ts": state["ts"], "action": "relist",
                                     "ok": bool(res.get("ok")),
                                     "names": names}
            save_state(args.state, state)
            print(json.dumps({**res, "action": "relist"}, indent=2,
                             sort_keys=True))
            return 0 if res.get("ok") else 1
        if not res.get("ok"):
            state["ts"] = time.time()
            state["last_pull_error"] = {"action": "relist", "res": res}
            save_state(args.state, state)
            print(json.dumps({**res, "action": "relist_failed"}, indent=2,
                             sort_keys=True))
            return 1
        state = update_state(state, ts=time.time(), preds=preds,
                             delisted=False, last_reason="relist")
        state.pop("pulled_models", None)
        state["consecutive_failures"] = 0        # explicit action clears breaker
        state["blocked"] = False                 # keep the key greppable
        save_state(args.state, state)
        if args.nsec:
            publish_delist_event(args.nsec, delisted=False)
        # NOTE: spread res FIRST — the backend result carries its own "action"
        # field which must not clobber the top-level relist action.
        print(json.dumps({**res, "action": "relist"}, indent=2, sort_keys=True))
        return 0

    dec = evaluate_triggers(preds, state, override=override,
                            move_hours=args.move_hours,
                            variance_threshold=args.variance)
    fire = args.delist or dec["fire"]

    if not fire:
        state = update_state(state, ts=time.time(), preds=preds,
                             delisted=state.get("delisted", False))
        save_state(args.state, state)
        print(json.dumps({"action": "none", "fire": False,
                          "preds_error": preds_error,
                          "preds_stale": preds_stale,
                          "reasons": [], "ts": time.time()}, indent=2,
                         sort_keys=True))
        return 1 if (preds_error or preds_stale) else 0

    # Fire: pull the listing, then CONFIRM by an independent re-fetch
    # (cold-review finding 2) within the action budget (finding 5). One
    # bounded in-run retry absorbs a transient ssh blip; the whole loop —
    # both attempts — counts as a single run for the circuit breaker.
    backend = _SshBackend(args.ssh_target, args.container)
    deadline = time.monotonic() + ACTION_BUDGET_S
    res: dict = {"ok": False}
    confirmed = False
    attempts = 0
    while attempts < MAX_PULL_ATTEMPTS:
        attempts += 1
        res = pull_listing(backend, dry_run=args.dry_run, deadline=deadline)
        if not res.get("ok"):
            if not args.dry_run and attempts < MAX_PULL_ATTEMPTS and \
                    time.monotonic() < deadline:
                continue                       # bounded in-run retry
            break
        if args.dry_run:
            confirmed = True                   # intent only: no remote verify
            break
        vres = backend.verify(deadline=deadline)
        if vres.get("ok") is True and vres.get("count") == 0:
            # RE-FETCHED confirmation: zero models still advertised.
            res["confirmed"] = True
            res["verified_count"] = vres.get("count")
            confirmed = True
            break
        # Pull self-reported ok but the re-fetch refuted it (or failed):
        # the attempt is a failure no matter what the pull round-trip said.
        res = dict(res)
        res["ok"] = False
        res["confirmed"] = False
        res["verify"] = {k: vres.get(k) for k in ("ok", "count", "error", "rc")}
        if attempts < MAX_PULL_ATTEMPTS and time.monotonic() < deadline:
            continue                           # bounded in-run retry
        break

    if args.dry_run:
        # Dry-run is intent-only (verification-pass finding 7c): record the
        # intent, flip NO durable delist flag, publish NO event, count NO
        # breaker failure, consume NO acceleration baseline.
        state = dict(state)
        state["ts"] = time.time()
        state["last_dry_run"] = {"ts": state["ts"],
                                 "action": "delist" if confirmed
                                           else "delist_failed",
                                 "ok": bool(res.get("ok")),
                                 "reasons": dec["reasons"]}
        save_state(args.state, state)
        print(json.dumps({**res, "action": "delist" if confirmed
                                           else "delist_failed",
                          "fire": True, "preds_error": preds_error,
                          "preds_stale": preds_stale,
                          "reasons": dec["reasons"]}, indent=2,
                         sort_keys=True))
        return 0 if confirmed else 1

    if not confirmed:
        # FAILED pull: do NOT consume the acceleration baseline (the trigger
        # must re-fire next run), do NOT set delisted=true, exit non-zero so
        # cron/monitoring sees the failure (cold-review finding 2). The
        # circuit breaker counts consecutive failed RUNS (task body).
        fails += 1
        state["ts"] = time.time()
        state["delisted"] = False                # keep the key greppable
        state["consecutive_failures"] = fails
        state["last_pull_error"] = {"action": "delist",
                                    "ts": state["ts"], "res": res}
        newly_blocked = fails >= BREAKER_THRESHOLD
        state["blocked"] = newly_blocked
        save_state(args.state, state)
        print(json.dumps({**res, "action": "delist_failed", "fire": True,
                          "preds_error": preds_error,
                          "preds_stale": preds_stale,
                          "reasons": dec["reasons"],
                          "consecutive_failures": fails,
                          "blocked": newly_blocked}, indent=2, sort_keys=True))
        return 3 if newly_blocked else 1

    # Confirmed delist: merge the captured names with any prior capture
    # (cold-review finding 4 — a re-delist's now-empty capture must never
    # clobber the stored names) and reset the breaker on success.
    prior = state.get("pulled_models") or []
    pulled = res.get("pulled") or []
    merged = list(prior) + [n for n in pulled if n not in prior]
    state = update_state(state, ts=time.time(), preds=preds, delisted=True,
                         last_reason="; ".join(dec["reasons"] or ["--delist"]),
                         extra={"pulled_models": merged})
    state["consecutive_failures"] = 0
    state["blocked"] = False                     # keep the key greppable
    save_state(args.state, state)

    # Event-based delist signal (best-effort, never blocks the pull result).
    if args.nsec:
        publish_delist_event(args.nsec, delisted=True)

    # NOTE: spread res FIRST — the backend result carries its own "action"
    # field which must not clobber the top-level delist action.
    print(json.dumps({**res, "action": "delist", "fire": True,
                      "preds_error": preds_error,
                      "preds_stale": preds_stale,
                      "reasons": dec["reasons"]}, indent=2, sort_keys=True))
    return 0


class _SshBackend:
    """Production backend: docker exec python3 against the sell node over ssh.

    Only ever mutates the `models` table (the advertised listing). Never
    touches upstream_providers — the provider stays in the ladder.

    Every remote round-trip is bounded by min(SSH_TIMEOUT_S, remaining
    action-budget deadline) so a fired trigger can never exceed the
    5-minute window's action slice (cold-review finding 5).
    """

    def __init__(self, ssh_target, container):
        self.ssh_target = ssh_target
        self.container = container

    def pull(self, dry_run=False, deadline=None):
        return self._run(pull_listing_payload(), dry_run=dry_run,
                        action="pull", deadline=deadline)

    def relist(self, names=None, dry_run=False, deadline=None):
        return self._run(relist_payload(names or []), dry_run=dry_run,
                         action="relist", deadline=deadline)

    def verify(self, dry_run=False, deadline=None):
        """Independent post-pull RE-FETCH (cold-review finding 2)."""
        return self._run(verify_pull_payload(), dry_run=dry_run,
                         action="verify", deadline=deadline)

    def _run(self, payload, *, dry_run, action, deadline=None):
        cmd = build_ssh_docker_cmd(self.ssh_target, self.container, payload)
        if dry_run:
            return {"ok": True, "dry_run": True, "action": action,
                    "cmd": " ".join(cmd[:2]) + " … " + cmd[2][:120]}
        timeout = SSH_TIMEOUT_S
        if deadline is not None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return {"ok": False, "action": action,
                        "error": "action budget exhausted"}
            timeout = min(SSH_TIMEOUT_S, remaining)
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True,
                                  timeout=timeout)
            data = {}
            out = proc.stdout.strip()
            if out:
                try:
                    data = json.loads(out.splitlines()[-1])
                    if not isinstance(data, dict):
                        data = {}
                except Exception:
                    data = {}
            res = {"action": action, "rc": proc.returncode,
                   "stdout": out[:200], "stderr": proc.stderr.strip()[:200]}
            res.update(data)
            res["ok"] = proc.returncode == 0 and data.get("ok") is True
            return res
        except Exception as exc:  # ssh/docker unavailable or slow
            return {"ok": False, "action": action, "error": str(exc)}


if __name__ == "__main__":
    raise SystemExit(main())
