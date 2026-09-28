# Review findings 1-3: routstr dynamic delist (safety, confirmation, fail-safe)

Scope: `~/.hermes/bot/scripts/routstr_delist.py` and `~/.hermes/bot/tests/test_routstr_delist.py`, with contract reference from `~/.hermes/bot/docs/routstr-delist.md` (note: the requested file `~/.hermes/bot/docs/routstr_delist_contract.md` does not exist).

## Finding 1 — Safety: remote payload shell-quoting prevents injection

Severity: OK

The script builds the SSH remote command as a single argv element passed to `ssh`, and `shlex.quote` is applied to both the Docker container name and the Python payload.

Evidence:
- `~/.hermes/bot/scripts/routstr_delist.py:423-425`: `build_ssh_docker_cmd` joins `"docker", "exec", shlex.quote(container), "python3", "-c", shlex.quote(payload)` into one remote string.
- `~/.hermes/bot/scripts/routstr_delist.py:414-425`: docstring explicitly documents the shell-quoting requirement and the no-local-shell design.
- `~/.hermes/bot/docs/routstr-delist.md:132-139`: contract describes the same remote-execution safety rule and cites cold-review finding 1.
- `~/.hermes/bot/tests/test_routstr_delist.py`: no dedicated `shlex.split` round-trip assertion is visible in the provided excerpt, but the contract docstring references one; if absent this would be a test-coverage gap, but the implementation itself is correct.

Conclusion: the safety mechanism is correctly implemented.

## Finding 2 — Confirmation: delist success is gated on an independent re-fetch, not the pull's self-report

Severity: OK

A fired delist performs one pull followed by a read-only verification re-fetch counting still-advertised models. Only `count == 0` confirms success. A pull that self-reports ok but fails verification is retried once and, if still unconfirmed, recorded as a failed run without consuming the acceleration baseline.

Evidence:
- `~/.hermes/bot/scripts/routstr_delist.py:400-411`: `verify_pull_payload()` returns a `SELECT COUNT(*) FROM models WHERE enabled=1` payload with no mutation.
- `~/.hermes/bot/scripts/routstr_delist.py:682-688`: `main()` calls `backend.verify()` after a successful pull and treats `vres.get("count") == 0` as the confirmation condition.
- `~/.hermes/bot/scripts/routstr_delist.py:689-697`: when verification refutes the pull, `res["ok"]` is forced to `False`, `confirmed` is `False`, and one bounded in-run retry is permitted.
- `~/.hermes/bot/scripts/routstr_delist.py:719-739`: an unconfirmed delist does NOT set `delisted=True`, does NOT consume the acceleration baseline (the snapshot is updated with current preds, so the same trigger will re-fire), increments `consecutive_failures`, and exits non-zero.
- `~/.hermes/bot/tests/test_routstr_delist.py:318-361`: `TestBurnAccelerationDelist` asserts exactly one pull + one verify, `confirmed=True`, `verified_count==0`, the verify SELECT, and that an unverified pull fails with exit 1.
- `~/.hermes/bot/docs/routstr-delist.md:69-75`: contract restates the re-fetch confirmation rule and the bounded retry.

Conclusion: confirmation is correctly gated on an independent read-only re-fetch.

## Finding 3 — Fail-safe: stale or corrupt prediction feed cannot trigger a delist or wipe the baseline

Severity: OK

Dead or stale prediction data is treated as unsafe and is prevented from firing triggers or refreshing the acceleration baseline. Manual override is explicitly exempt from freshness gating so an operator can still act during a feed outage.

Evidence:
- `~/.hermes/bot/scripts/routstr_delist.py:485-496`: `feed_is_stale()` returns `True` when the file age cannot be determined (OSError path), implementing the fail-closed direction documented in its docstring.
- `~/.hermes/bot/scripts/routstr_delist.py:589-593`: a stale feed is replaced with `raw_preds = []`, so neither acceleration nor variance can fire, and the next `update_state` call receives empty `preds`.
- `~/.hermes/bot/scripts/routstr_delist.py:255-257`: `update_state()` only writes a new `snapshot` when `preds` is non-empty, so stale/corrupt feeds never overwrite the stored baseline.
- `~/.hermes/bot/scripts/routstr_delist.py:580-585`: manual override is evaluated from the marker file or `--manual` BEFORE the stale-feed branch affects trigger logic; `TestManualOverride.test_manual_override_is_never_gated_on_feed_staleness` (`~/.hermes/bot/tests/test_routstr_delist.py:427-433`) verifies a `--manual` delist still fires even when `preds_stale=True`.
- `~/.hermes/bot/tests/test_routstr_delist.py:292-314`: steady-burn/no-trigger cases confirm zero API calls and no accidental delist.
- `~/.hermes/bot/docs/routstr-delist.md:56-60`: contract documents the freshness guard, dead-data behavior, and manual-override exemption.

Conclusion: the fail-safe for stale/corrupt feeds is correctly implemented and verified.

## Artifact note

The task requested reading `~/.hermes/bot/docs/routstr_delist_contract.md`. That path does not exist. The equivalent contract document is present at `~/.hermes/bot/docs/routstr-delist.md` and at the repo copy `docs/routstr-delist.md`. No implementation artifacts were modified during this review.
