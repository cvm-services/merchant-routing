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
disabled before the delist.

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

## Failure semantics

- A **failed pull/relist** (ssh down, non-zero rc, bad payload): exits
  non-zero (cron/monitoring sees it), does NOT set `delisted=true`, does NOT
  consume the acceleration baseline (the same trigger re-fires next run), and
  records `last_pull_error` in the state file.
- An **unreadable/corrupt `--preds` feed** (`preds_error: true` in output):
  triggers are still evaluated (manual override keeps working), the stored
  baseline is never wiped, and the run exits non-zero when nothing fired.
- Dry-run: performs no remote action, but records local intent state.

## 5-minute window

`TRIGGER_ACTION_WINDOW_S = 300`. The script acts **in-run** the moment a
trigger evaluates true (no background queue); the ≤5-minute contract is met
by running it on a cadence ≤5 min (cron `*/5` or faster), e.g.:

    */5 * * * *  routstr_delist.py --preds /path/to/preds.json

Triggers are evaluated against the durable baseline snapshot written by the
previous run (`~/.hermes/bot/routstr_delist_state.json`), so consecutive runs
detect acceleration with full 5-minute resolution.

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
    routstr_delist.py --override PATH               # custom override marker path

All remote actions take `--dry-run` (prints intent, executes nothing) and
`--ssh-target`/`--container` overrides (defaults: `debian@23.182.128.51`,
`routstr-public`).

## Testing (Gates 1–2)

    python3 -m unittest discover -s tests -v
    python3 -m pytest tests/ -v

55 tests, hermetic (faked SSH backend, tmpdir state, no network). Covers: all
three triggers + thresholds/edge cases, first-run baseline guard, durable
state round-trip, SALE-vs-provider SQL scoping, remote-command shell-safety,
scoped relist round-trip, failure semantics (failed pull/relist, corrupt
feed, non-dict feed entries), event argv shape (`--env-sec`, kind 30078) and
countering publish, the 5-minute window, and full CLI paths.

## Dependencies

- **T-A** (caller-class capture): the sold-429 gate and `predict_exhaustion`
  feeds this script consumes come from T-A's routing work. The script itself
  is standalone: its input contract is a JSON list of
  `predict_exhaustion()`-shaped dicts (`key`, `window`, `exhausts_in_hours`,
  `uncertainty`).
