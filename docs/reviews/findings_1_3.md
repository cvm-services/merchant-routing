# Review Findings 1-3: routstr delist (safety, confirmation, fail-safe)

Scope: `~/.hermes/bot/scripts/routstr_delist.py` and `~/.hermes/bot/tests/test_routstr_delist.py`.
The requested contract file `~/.hermes/bot/docs/routstr_delist_contract.md` does NOT exist. The closest contract is `~/.hermes/bot/docs/routstr-delist.md`, which was used as the reference. Missing file severity: HIGH.

---

## Finding 1 — Safety: remote command construction

Severity: **OK**

Evidence:
- `scripts/routstr_delist.py:414-425`: `build_ssh_docker_cmd()` joins the remote pipeline (`docker exec <container> python3 -c <payload>`) into a single ssh argument and applies `shlex.quote` to both the container name and the Python payload.
- `scripts/routstr_delist.py:767-825`: `_SshBackend._run()` passes the argv directly to `subprocess.run` with no local shell involved.
- `tests/test_routstr_delist.py:469-488`: `TestSemanticGuardLadderUntouched.test_provider_ladder_byte_identical_across_delist` asserts that `upstream_providers` is never named in any payload and that the provider ladder file is byte-identical after a delist.

The delist mutates only the `models` (advertised listing) table; the routstr provider stays in the ladder.

---

## Finding 2 — Confirmation: delist success gated on independent re-fetch

Severity: **OK**

Evidence:
- `scripts/routstr_delist.py:400-411`: `verify_pull_payload()` is a read-only `SELECT COUNT(*) FROM models WHERE enabled=1` intended as the post-pull re-fetch.
- `scripts/routstr_delist.py:666-697`: the fired-delist loop calls `backend.verify()` after `pull_listing()` and only marks the delist confirmed when `vres.get("ok") is True and vres.get("count") == 0`.
- `scripts/routstr_delist.py:719-739`: if not confirmed, the run exits non-zero, does not set `delisted=true`, does not consume the acceleration baseline, and increments/trips the circuit breaker.
- `tests/test_routstr_delist.py:346-361`: `test_unverified_pull_is_a_failed_delist` sets `pull_lands = False`, proving that a self-reporting-but-unverified pull performs the bounded in-run retry, ultimately exits `1`, and leaves `delisted=false`.

---

## Finding 3 — Fail-safe: input-feed failures never trigger or blind the baseline

Severity: **OK**

Evidence:
- `scripts/routstr_delist.py:485-496`: `feed_is_stale()` treats any age-determination failure as stale (fail-closed) and only returns fresh when `0 <= age <= max_age_s`.
- `scripts/routstr_delist.py:580-593`: `main()` sets `preds_error` when `--preds` was given but produced no readable list, sets `preds_stale` when the readable feed is stale, and blanks the pred list if stale so it cannot trigger or refresh the baseline. Manual override is computed before this logic and is never gated on freshness.
- `scripts/routstr_delist.py:258-268`: `update_state()` only overwrites the `snapshot` baseline when `preds` is truthy; an empty/corrupt/stale feed therefore cannot wipe the prior acceleration baseline.
- `scripts/routstr_delist.py:651-660`: in the quiet path the run exits `1` when `preds_error` or `preds_stale` is true, making feed failures observable to cron/monitoring.
- `tests/test_routstr_delist.py:427-434`: `test_manual_override_is_never_gated_on_feed_staleness` confirms a stale feed is reported but the manual delist still executes.
