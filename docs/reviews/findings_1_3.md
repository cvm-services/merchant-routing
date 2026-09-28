# Findings 1–3 — routstr dynamic delist: safety, confirmation, fail-safe

Artifacts reviewed end-to-end this session:

* `~/.hermes/bot/scripts/routstr_delist.py` (829 lines)
* `~/.hermes/bot/tests/test_routstr_delist.py` (752 lines)
* `~/.hermes/bot/docs/routstr-delist.md` (197 lines)

**Artifact-path status — HIGH.** The path named in the task,
`~/.hermes/bot/docs/routstr_delist_contract.md`, does **not exist**. The
contract role is filled by the stand-in `~/.hermes/bot/docs/routstr-delist.md`
(which the test suite itself calls the frozen contract at
`tests/test_routstr_delist.py:1`). This is an artifact-provisioning defect, not a
script defect; the analysis below uses the existing design doc and executable
contract suite.

Citations below use `routstr_delist.py:N` for the deployed script copy; the repo
`src/routstr_delist.py` is byte-identical.

---

## Finding 1 — Safety: delisting the SALE never disables the routstr provider, and remote execution is shell-safe — severity: **OK** (residuals: 1 MEDIUM, 2 LOW)

1. **SQL scope is strictly the `models` listing table** (`routstr_delist.py:355`,
   `:361`, `:369-375`, `:392-397`, `:406-411`). Every remote payload targets
   `/app/data/keys.db` and names only `models`. The verb inventory is three
   `UPDATE`s and two `SELECT`s; no payload names `upstream_providers`, the
   T470 ladder, or any router table.

2. **`upstream_providers` appears only in docstrings** (`routstr_delist.py:35`,
   `:352`, `:771`). No executable literal references it.

3. **No local shell is invoked.** `subprocess.run` is used at `:459` (nak) and
   `:808` (ssh docker exec) with `shell=False`. There are no `eval`, `exec`, or
   `os.system` call sites in the module.

4. **Remote command is a single shell-quoted argv.** `build_ssh_docker_cmd`
   (`routstr_delist.py:414-425`) joins `docker exec <quoted container> python3
   -c <quoted payload>` into the single remote-command string passed to ssh.
   Both the container name and the python payload are passed through
   `shlex.quote`, preventing remote-shell metacharacter injection.

5. **The only local write surface is the state file.** `save_state`
   (`routstr_delist.py:221-245`) uses a tmp-file + `os.fsync` + `os.replace`
   protocol. No router config or provider row is ever written locally.

6. **Relist is the scoped inverse.** `--relist` restores only the captured
   names (`routstr_delist.py:601`, `:635`). With no captured names the blanket
   relist is **refused** before any remote call (`routstr_delist.py:602-611`).

**Residuals:**

* **MEDIUM:** Dry-run on the quiet path consumes the acceleration baseline.
  `routstr_delist.py:651-654` refreshes the stored snapshot even when
  `--dry-run` is set, and records no `last_dry_run`. A firing dry run does
  record intent (`routstr_delist.py:699-709`); the quiet path should mirror it.
  Fail direction is loss of protection, never an unsafe delist.

* **LOW:** `--ssh-target` and `--container` are unvalidated free-form strings
  (`routstr_delist.py:536-537`). A typo can point the fixed payload at another
  sell node, but it cannot reach the T470 ladder.

* **LOW:** The database path `/app/data/keys.db` is duplicated across the five
  payload builders (`routstr_delist.py:370`, `:385`, `:393`, `:407`, `:322`), so a
  future path change must be coordinated in five places.

---

## Finding 2 — Post-delisting confirmation must come from an independent re-fetch — severity: **OK** (requirement MET; residuals: 1 MEDIUM, 1 LOW)

1. **The confirming read is independent and read-only.**
   `verify_pull_payload()` (`routstr_delist.py:400-411`) runs
   `SELECT COUNT(*) FROM models WHERE enabled=1` and contains no mutating verb.
   It is invoked through `backend.verify()` at `routstr_delist.py:682`, a
   separate ssh/docker round-trip from the mutating pull.

2. **Success is gated on the re-fetched count, not the pull's self-report.**
   `routstr_delist.py:683` requires `vres.get("ok") is True and
   vres.get("count") == 0`. Only then does the run set `confirmed=True`
   (`routstr_delist.py:685-687`) and write `delisted=True`
   (`routstr_delist.py:747-752`).

3. **A lying pull is refuted.** If the pull self-reports `ok` but the listing is
   still enabled, the run returns rc 1, `action=delist_failed`, zero durable
   flag, and `consecutive_failures` ticks (`routstr_delist.py:719-739`). The
   in-run retry is bounded by `MAX_PULL_ATTEMPTS = 2`
   (`routstr_delist.py:75`, loop `:671-697`).

4. **Failure direction preserves the trigger.** The failure path keeps the
   stored acceleration baseline intact (`routstr_delist.py:719-739` does not
   consume it) so the same trigger re-fires on the next tick, matching
   `docs/routstr-delist.md:62-68`.

**Residuals:**

* **MEDIUM:** The relist direction has no symmetric re-fetch.
  `routstr_delist.py:613-614` sends the relist payload and gates success only
  on its self-report (`routstr_delist.py:626`). A lying relist can return
  `action=relist` while models remain disabled. Fail direction is loss of
  recovery, never an unsafe delist.

* **LOW:** Pull and verify share the same ssh target/container backend
  (`routstr_delist.py:666`, `:682`). The confirmation is independent of the SQL
  statement but not of the host; this is bounded by the single-sourced target
  config.

---

## Finding 3 — Fail-safe on absent, garbage and stale monitor signals — severity: **OK** (residuals: 3 LOW)

1. **Absence is inert.** With no `--preds`, the run exits 0 with
   `action=none` and zero remote calls. With a feed but no stored baseline, the
   acceleration trigger cannot fire (`exhaustion_accelerated` returns `[]` at
   `routstr_delist.py:107-108`), preventing a first-run false positive.

2. **Garbage/unreadable feed is reported.** `_read_preds()`
   (`routstr_delist.py:468-482`) returns `[]` on any parse failure.
   `preds_error` is set at `routstr_delist.py:585` and the run exits 1 at
   `:660`. Non-dict rows are dropped (`routstr_delist.py:478-479`) rather than
   crashing.

3. **Staleness fails closed.** `feed_is_stale()` (`routstr_delist.py:485-496`)
   treats any `OSError` (missing/unreadable file) as stale and uses an
   inclusive `0 <= age <= STALENESS_S` boundary (`STALENESS_S = 1800` at
   `:78`). A stale feed is emptied at `routstr_delist.py:592` before trigger
   evaluation, so it can neither fire nor refresh the acceleration baseline
   (`update_state` only writes the snapshot when `preds` is truthy at
   `routstr_delist.py:261`).

4. **Manual override remains ungated by design.** A stale feed plus `--manual`
   still delists, with `preds_stale: true` reported, and the dead feed does not
   refresh the baseline (`routstr_delist.py:580`, `:589-592`, `:652-653`).

5. **Budget and breaker fail closed.** An exhausted action budget refuses to
   spawn a subprocess (`routstr_delist.py:800-806`). Once the breaker opens,
   all remote actions are refused before any round-trip with rc 3
   (`routstr_delist.py:569-578`).

**Residuals:**

* **LOW:** A valid but empty `[]` feed is reported as `preds_error: true`
  (`routstr_delist.py:585`), making it indistinguishable from corruption in
  the output. The fail direction is still safe (exit 1, no action).

* **LOW:** `--preds-key` can silently disable triggers. If the key does not
  match any row, the filtered feed is empty while `preds_error` is computed
  from the unfiltered list (`routstr_delist.py:585` vs `:594-597`), producing a
  healthy-looking quiet run. This is loss of protection, not unsafe action.

* **LOW:** Switching `--preds-key` between runs narrows the stored baseline to
  that key (`routstr_delist.py:594-597` feeding `:652-653`), discarding other
  keys' snapshots and possibly resetting the acceleration comparison.
