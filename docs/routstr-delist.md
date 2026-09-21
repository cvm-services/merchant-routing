# routstr dynamic delist (T-D, ADR-007 Gate 4)

`src/routstr_delist.py` — deployed executable copy at
`~/.hermes/bot/scripts/routstr_delist.py` (byte-identical, `chmod +x`).

## Purpose

Programmatically pull the **routstr SALE** (the advertised model listing on the
routstr-public sell node, VPS2) within **5 minutes** of a trigger.

## The distinction that matters

> Delisting the routstr **SALE** (the advertised listing) is **distinct** from
> disabling the routstr **provider**. The provider stays in the T470
> flat-router ladder — still routable, still a candidate. Only the public
> advertisement of models-for-sale is pulled.

Enforced in code: the remote delist payload runs against the sell-node
container's `/app/data/keys.db` and mutates strictly the `models` (listing)
table. It never touches `upstream_providers` or any router provider row.
Tests assert this scoping (`TestSaleNotProvider`).

Relist is the exact inverse: the pull first `SELECT`s the advertised model
names, disables exactly those rows, and reports the names; they are stored in
the state file (`pulled_models`) and the relist re-enables only those
(parameterized `WHERE name IN (?,...)`) — never rows the operator had
disabled before the delist. Two hard rules (cold-review round 2):

- **No blanket relist.** With no captured names (legacy state, or a state
  written by an older version), `--relist` **refuses** (`relist_refused`,
  exit 1, nothing executed remotely) instead of enabling every row. Pass
  `--relist-any` for the explicit operator opt-in.
- **Re-delist merges.** A delist fired while already delisted captures an
  empty name set (nothing was advertised); it **merges** into the stored
  `pulled_models` instead of clobbering them, so the scoped relist still
  restores the original names.

## Triggers (ADR-007)

| # | Trigger | Rule | Default |
|---|---------|------|---------|
| 1 | Burn-rate accelerates | predicted exhaustion moves **forward** (hours-to-exhaustion decreases) between consecutive readings of `burn_predictor.predict_exhaustion()` | ≥ `2.0` h movement (`--move-hours`) |
| 2 | Kalman variance elevated | a prediction window's `uncertainty` (Kalman variance term) exceeds threshold | `> 0.30` (`--variance`) |
| 3 | Manual override | marker file exists, or `--manual` | `~/.hermes/bot/routstr_delist.override` |

Notes:
- First run has no baseline — acceleration can never fire on the first
  comparison (false-positive guard); variance and manual still can.
- Burn slowing down (exhaustion pushed back) is explicitly NOT a trigger.
- Trigger 2 is level-based **by design**: while the variance condition
  persists, every run keeps asserting delist. A manual `--relist` is therefore
  NOT sticky while a trigger condition still holds — that is the intended
  protection (delisting protects sold-traffic capacity).
- `--preds-key <key>` scopes evaluation to predictions with that `key`
  only: another provider's variance spike can never pull the routstr SALE.
- **Freshness guard (cold-review finding 3):** a `--preds` feed older than
  `STALENESS_S` (30 min, mtime-based) is dead data — it never triggers
  (variance especially), never refreshes the acceleration baseline, and the
  run reports `preds_stale: true` with a non-zero exit when nothing fired.
  The manual override is never gated on freshness.

## Failure semantics

- A **failed pull/relist** (ssh down, non-zero rc, bad payload, **or a
  re-fetch that fails to confirm**): exits non-zero (cron/monitoring sees
  it), does NOT set `delisted=true`, does NOT consume the acceleration
  baseline (the same trigger re-fires next run), and records `last_pull_error`
  in the state file.
- **Re-fetch confirmation (cold-review finding 2):** a fired delist is one
  pull + one *independent read-only re-fetch* (`verify`) counting still-
  advertised models. Success is gated on the re-fetch reporting `count == 0`
  — never on the pull round-trip's self-report. A pull that self-reports ok
  but cannot be confirmed is a **failed attempt**. One bounded in-run retry
  (`MAX_PULL_ATTEMPTS = 2`) absorbs a transient ssh blip; the whole loop
  counts as one run for the breaker.
- **Circuit breaker (task body):** 3 consecutive failed runs → `blocked:
  true` (durable), exit code **3**, and every subsequent run refuses *all*
  remote action (relist included) until the operator re-runs with
  `--unblock`. Any confirmed success (delist or relist) resets the counter.
- **Atomic state writes (cold-review finding 4):** `save_state` writes a
  tmp file in the same directory, fsyncs, then `os.replace`s — a concurrent
  reader never sees a torn file, and a crash mid-write leaves the previous
  state intact.
- An **unreadable/corrupt `--preds` feed** (`preds_error: true` in output):
  triggers are still evaluated (manual override keeps working), the stored
  baseline is never wiped, and the run exits non-zero when nothing fired.
- **Dry-run is intent-only (verification finding 7c):** no remote execution,
  no durable `delisted` flip, no Nostr publish, no breaker counting, no
  baseline consumption. The intent is recorded in `last_dry_run` only.

## 5-minute window

SLA arithmetic (cold-review finding 5 — now wired to real constants):

    TRIGGER_ACTION_WINDOW_S = 300      # the contract
    POLL_CADENCE_S         = 240       # documented cron cadence: */4 minutes
    ACTION_BUDGET_S        = 300 - 240 # = 60 s the run may spend acting
    SSH_TIMEOUT_S          = 30        # per round-trip; pull + verify <= budget

Worst-case detection is one full poll cadence (cron `*/4`), and every remote
round-trip inside a fired run is timeout-clamped to the **remaining** action
budget (`time.monotonic()` deadline), so a fired trigger can never breach the
5-minute window: detection (≤ 240 s) + action (≤ 60 s) ≤ 300 s. The script
acts **in-run** the moment a trigger evaluates true (no background queue), e.g.:

    */4 * * * *  routstr_delist.py --preds /path/to/preds.json --preds-key zai

Triggers are evaluated against the durable baseline snapshot written by the
previous run (`~/.hermes/bot/routstr_delist_state.json`), so consecutive runs
detect acceleration with full cadence resolution.

**Deployment note (cold-review finding 6):** no crontab entry is wired yet.
The runner must be a host with SSH access to `debian@23.182.128.51` and a
`predict_exhaustion()` feed producing `preds.json` on the same cadence.
(dq05 cannot host it: outbound SSH is blocked by policy there.)

## Mechanism (flag + event)

Per ADR-007: a flag in the objects that publish the listing, plus an
event-based delist.

- **Flag** — `delisted: true` is persisted in the state JSON that the listing
  publisher reads, so the publisher's advertisement reflects `delisted=true`.
- **Event** — optional **kind-30078** (NIP-78 application data,
  parametrized-replaceable) event `d=routstr-delist` published via
  `nak --env-sec` (never `--sec`: it leaks the key via `ps aux`), passed with
  `--nsec <file>`. Relist publishes the countering `delisted:false` event.
  Best-effort: a publish failure never blocks the pull. (Kind 30078 is used
  rather than squatting a registered 303xx live-event kind — cold-review
  finding 8.)

## Remote execution safety

`ssh` joins everything after the host into ONE string parsed by the remote
shell, so `build_ssh_docker_cmd()` emits the entire remote pipeline
(`docker exec <container> python3 -c <payload>`) as a single argv element
with `shlex.quote` on the container and payload (cold-review finding 1).
The regression test re-parses the remote command with `shlex.split` and
asserts it round-trips to the intended argv.

## Usage

    routstr_delist.py --preds preds.json            # evaluate triggers (cron path)
    routstr_delist.py --status                      # show durable delist state
    routstr_delist.py --manual --dry-run            # force trigger, dry run
    routstr_delist.py --delist                      # force-pull the listing now
    routstr_delist.py --relist                      # restore the listing (scoped)
    routstr_delist.py --relist --relist-any         # forced blanket relist (opt-in)
    routstr_delist.py --unblock                     # clear a BLOCKED breaker, then act
    routstr_delist.py --preds-key zai --preds p.json # scope triggers to one key
    routstr_delist.py --override PATH               # custom override marker path

Exit codes: `0` success/quiet · `1` failure/refused (retried next run) ·
`3` **BLOCKED** (circuit breaker open; needs `--unblock`).

All remote actions take `--dry-run` (prints intent, executes nothing) and
`--ssh-target`/`--container` overrides (defaults: `debian@23.182.128.51`,
`routstr-public`).

## Testing (Gates 1–2)

    python3 -m unittest discover -s tests -v
    python3 -m pytest tests/ -v

96 tests, hermetic (faked SSH backend, tmpdir state, no network). Covers: all
three triggers + thresholds/edge cases, first-run baseline guard, durable
state round-trip, atomic-write (torn-write never replaces good state), SALE-
vs-provider SQL scoping + re-fetch payload scoping, remote-command
shell-safety, scoped relist round-trip + blanket-relist refusal + re-delist
merge, failure semantics (failed pull/relist, corrupt feed, non-dict feed
entries, stale feed), re-fetch confirmation gating, circuit breaker
(3-strikes → exit 3 → `--unblock`), dry-run purity (no publish, no flag
flip), SLA deadline arithmetic + bounded in-run retry, real `_SshBackend._run`
parsing (mocked subprocess), event argv shape (`--env-sec`, kind 30078), and
full CLI paths.

## Dependencies

- **T-A** (caller-class capture): the sold-429 gate and `predict_exhaustion`
  feeds this script consumes come from T-A's routing work. The script itself
  is standalone: its input contract is a JSON list of
  `predict_exhaustion()`-shaped dicts (`key`, `window`, `exhausts_in_hours`,
  `uncertainty`).
