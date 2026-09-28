# Review findings 1-3: routstr dynamic delist

Reviewed artifacts (worker-base, 2026-09-28):

- `~/.hermes/bot/scripts/routstr_delist.py`
- `~/.hermes/bot/tests/test_routstr_delist.py`
- **Requested contract file** `~/.hermes/bot/docs/routstr_delist_contract.md` — **MISSING**.
  The frozen contract is instead at `~/.hermes/bot/docs/routstr-delist.md`.
  Severity: **HIGH** (review artifact name mismatch; downstream automation or
  auditors looking for the requested path will not find the canonical contract).
  This review was performed against the existing `routstr-delist.md` contract.

---

## Finding 1 — Safety: remote command construction

Severity: **MEDIUM**

`build_ssh_docker_cmd()` correctly shell-quotes the container name and the
Python payload before handing them to the remote shell via a single ssh
command string (`~/.hermes/bot/scripts/routstr_delist.py:423-425`).

Evidence:

- `~/.hermes/bot/scripts/routstr_delist.py:423-425`:

```python
remote = " ".join(["docker", "exec", shlex.quote(container),
                   "python3", "-c", shlex.quote(payload)])
return ["ssh", ssh_target, remote]
```

- The payload string is built by `pull_listing_payload()`
  (`~/.hermes/bot/scripts/routstr_delist.py:364-375`),
  `relist_payload()` (`~/.hermes/bot/scripts/routstr_delist.py:378-397`), and
  `verify_pull_payload()` (`~/.hermes/bot/scripts/routstr_delist.py:400-411`).
  All of them are then quoted by `shlex.quote`, preventing injection from the
  model-name data pulled from the remote database.

- `test_routstr_delist.py:468-489` (`TestSemanticGuardLadderUntouched`) proves
  the executed payloads never name `upstream_providers` and only touch the
  `models` listing table — the provider ladder is left byte-identical.

Concern: `ssh_target` is inserted into the argv list without validation or
quoting. Because ssh parses leading `-` arguments as options, a malicious or
misconfigured `--ssh-target` beginning with `-oProxyCommand=...` would be
parsed by ssh as an option before the hostname is reached. The default target
is hard-coded and the CLI override is operator-controlled, so exploitation
requires a config compromise, but the script does not defend against it.

Recommendation: validate `ssh_target` with a strict parser (e.g.
`user@host[:port]` only) or pass the user separately via `ssh -l <user> <host>`
so a leading dash cannot be interpreted as an ssh option.

---

## Finding 2 — Confirmation: independent post-pull re-fetch

Severity: **OK**

The implementation satisfies the requirement that a delist is confirmed by an
independent read-only re-fetch rather than by the pull's self-report.

Evidence:

- `~/.hermes/bot/scripts/routstr_delist.py:400-411` defines the verify payload:

```python
def verify_pull_payload():
    return (
        "import sqlite3,json;"
        "db=sqlite3.connect('/app/data/keys.db');"
        "n=db.execute('SELECT COUNT(*) FROM models WHERE enabled=1')"
        ".fetchone()[0];"
        "print(json.dumps({'ok':True,'count':n}))"
    )
```

- `~/.hermes/bot/scripts/routstr_delist.py:671-697` performs up to
  `MAX_PULL_ATTEMPTS` pulls; after each successful pull it runs
  `backend.verify()` and only sets `confirmed = True` when the re-fetch reports
  `count == 0`.

- `~/.hermes/bot/scripts/routstr_delist.py:719-739` shows the failure path:
  unconfirmed pulls do **not** set `delisted=true`, do **not** consume the
  acceleration baseline, and exit non-zero so cron/monitoring sees the failure.

- `test_routstr_delist.py:318-345`
  (`TestBurnAccelerationDelist.test_acceleration_fires_exactly_one_delist_verified_by_refetch`)
  asserts `out["confirmed"] is True`, `out["verified_count"] == 0`, and that
  the second call is the verify payload containing `SELECT COUNT(*) FROM models`
  with no `UPDATE`.

- `test_routstr_delist.py:346-360`
  (`TestBurnAccelerationDelist.test_unverified_pull_is_a_failed_delist`) tests
  the lying-pull case: when `pull_lands=False`, the re-fetch refutes the pull,
  the run exits 1, and the state records `consecutive_failures` without setting
  `delisted=true`.

No defect identified.

---

## Finding 3 — Fail-safe: stale/corrupt feed handling and baseline preservation

Severity: **OK**

The fail-safe semantics documented in the contract are implemented and tested.

Evidence:

- Stale feed guard:

  `~/.hermes/bot/scripts/routstr_delist.py:485-497` (`feed_is_stale`) treats any
  failure to determine the file's age (OSError) as stale and returns `False`
  only for a file provably fresh (0 ≤ age ≤ `STALENESS_S`).

- Stale feed never drives a trigger or refreshes baseline:

  `~/.hermes/bot/scripts/routstr_delist.py:589-593` zeroes `raw_preds` when the
  feed is stale, and `update_state()` at `~/.hermes/bot/scripts/routstr_delist.py:248-268`
  only overwrites the stored `snapshot` when `preds` is truthy. The baseline is
  therefore preserved on stale or empty input.

- Explicit feed-error reporting:

  `~/.hermes/bot/scripts/routstr_delist.py:582-585` sets `preds_error = True`
  when `--preds` is supplied but yields no predictions, and `main()` at
  `~/.hermes/bot/scripts/routstr_delist.py:651-660` exits non-zero in that case
  while still preserving the stored baseline.

- Manual override is never gated on freshness:

  `~/.hermes/bot/scripts/routstr_delist.py:580` computes `override` before feed
  processing, and `~/.hermes/bot/tests/test_routstr_delist.py:427-433`
  (`TestManualOverride.test_manual_override_is_never_gated_on_feed_staleness`)
  confirms a stale feed still allows a manual delist.

- Circuit breaker protects against repeated failure:

  `~/.hermes/bot/scripts/routstr_delist.py:543-578` reads the `blocked` marker;
  three consecutive failures (`BREAKER_THRESHOLD`, line 77) cause exit code 3
  and refusal of all remote action until `--unblock` is used. A confirmed
  success resets the counter.

No defect identified.
