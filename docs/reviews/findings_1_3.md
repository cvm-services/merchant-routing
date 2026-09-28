# Findings 1-3 Review: routstr delist

**Severity legend:** BLOCKER / HIGH / MEDIUM / LOW / OK  
**Artifacts reviewed:**
- `~/.hermes/bot/docs/routstr-delist.md` (contract; the requested `routstr_delist_contract.md` was MISSING)
- `~/.hermes/bot/scripts/routstr_delist.py`
- `~/.hermes/bot/tests/test_routstr_delist.py`

**Meta-finding:** The requested artifact path `~/.hermes/bot/docs/routstr_delist_contract.md` does not exist. The contract is present under the slug-style name `~/.hermes/bot/docs/routstr-delist.md` at revision matching the script/tests. This path mismatch is reported as HIGH on the doc inventory; the review was performed against the available file and did not block analysis.

---

## Finding 1: Safety / remote-command shell-injection hardening

**Severity: OK**

`build_ssh_docker_cmd` treats the entire remote command as a single `ssh` remote-command argument and quotes both the container name and the Python payload (`scripts/routstr_delist.py:423-425`). The regression suite re-parses the emitted argv with `shlex.split` and asserts it round-trips to the intended argv (`tests/test_routstr_delist.py` exercises the real backend argv shape; the contract doc references this as the regression test at `docs/routstr-delist.md:138-139`).

Evidence:
- `scripts/routstr_delist.py:414-425` — `build_ssh_docker_cmd` joins `docker exec <quoted container> python3 -c <quoted payload>` into one string and returns `["ssh", ssh_target, remote]`, preventing local shell expansion.
- `scripts/routstr_delist.py:423` — `shlex.quote(container)` and `shlex.quote(payload)` are applied to values that reach the remote shell.
- `scripts/routstr_delist.py:808-809` — `subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)` runs the argv list directly with no shell.
- `docs/routstr-delist.md:132-139` — contract explicitly references cold-review finding 1 and the `shlex.split` round-trip test.

No gap identified. The safety posture is consistent with the contract and tested.

---

## Finding 2: Confirmation / independent re-fetch gating

**Severity: OK**

A fired delist performs one mutating pull, then one independent read-only re-fetch (`verify_pull_payload`). Success is gated on the re-fetch reporting `count == 0`, not on the pull's self-report. A pull that self-reports okay but fails verification is treated as a failed attempt, triggers a bounded in-run retry, and does not set `delisted=true` or consume the acceleration baseline.

Evidence:
- `scripts/routstr_delist.py:400-411` — `verify_pull_payload()` returns a read-only `SELECT COUNT(*) FROM models WHERE enabled=1` payload with no `UPDATE`.
- `scripts/routstr_delist.py:671-697` — delist loop: `pull_listing`, then on success `backend.verify(deadline=...)`, and `confirmed` is only set when `vres.get("ok") is True and vres.get("count") == 0`. If refuted, `res["ok"]` is forced to `False` and a bounded retry runs if budget remains.
- `scripts/routstr_delist.py:719-739` — on `not confirmed`, `delisted` stays `False`, `consecutive_failures` is incremented, and the circuit breaker may open; the acceleration baseline is NOT consumed because `update_state` is not called with the new `preds` in this branch.
- `scripts/routstr_delist.py:741-752` — only after confirmed delist does the state update to `delisted=True` and capture `pulled_models`.
- `tests/test_routstr_delist.py:318-360` — `TestBurnAccelerationDelist` confirms exactly one `pull` + one `verify`, confirmed by `verified_count == 0`, and the lying-pull test (`tests/test_routstr_delist.py:346-360`) asserts failure semantics when verification refutes the pull.
- `docs/routstr-delist.md:69-75` — contract text matches the implemented behavior exactly.

No gap identified. Confirmation gating is implemented and regression-covered.

---

## Finding 3: Fail-safe / prediction feed freshness + scoping

**Severity: OK**

The script treats stale or unreadable `--preds` feeds as dead data: variance/acceleration cannot fire from stale data, the baseline snapshot is not refreshed from stale data, and the run exits non-zero when nothing fired. Manual override is never gated on freshness. In addition, `--preds-key` scopes variance evaluation to the relevant provider, preventing another provider's variance spike from pulling the routstr SALE.

Evidence:
- `scripts/routstr_delist.py:485-496` — `feed_is_stale` returns `True` when the file is older than `STALENESS_S` (30 min) or when the mtime cannot be determined (fail-safe toward stale).
- `scripts/routstr_delist.py:589-593` — when `preds_stale` is true, `raw_preds` is emptied before trigger evaluation and before supplying `preds` to `update_state`, so stale data neither triggers nor refreshes the baseline.
- `scripts/routstr_delist.py:585` — an explicitly requested but empty/bad feed sets `preds_error = True`, which causes a non-zero exit on quiet runs.
- `scripts/routstr_delist.py:580-597` — manual override (`args.manual` or marker file) is computed before freshness gating and is not affected by `preds_stale`/`preds_error`.
- `scripts/routstr_delist.py:132-160` — `variance_jumped` accepts `key` filter; `scripts/routstr_delist.py:594-597` filters predictions by `--preds-key` before trigger evaluation.
- `scripts/routstr_delist.py:648` — `evaluate_triggers` is called with the scoped `preds` and the supplied `variance_threshold`.
- `tests/test_routstr_delist.py:389-399` — `test_other_providers_variance_cannot_pull_routstr_sale` confirms `--preds-key` prevents cross-provider variance from firing.
- `tests/test_routstr_delist.py:427-433` — `test_manual_override_is_never_gated_on_feed_staleness` confirms the override fires despite stale feed.
- `docs/routstr-delist.md:56-60` — contract documents the freshness guard and manual-override exclusion.

No gap identified. The fail-safe direction, fail-closed freshness handling, and `--preds-key` scoping are implemented and tested.
