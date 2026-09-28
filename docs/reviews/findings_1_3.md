# Review findings 1-3: merchant-routing / routstr delist

Artifacts reviewed:
- ~/.hermes/bot/docs/routstr-delist.md (contract)
- ~/.hermes/bot/scripts/routstr_delist.py
- ~/.hermes/bot/tests/test_routstr_delist.py

Note: the original path `~/.hermes/bot/docs/routstr_delist_contract.md` was missing; the existing contract `routstr-delist.md` was used instead. No artifact modification was performed.

---

## Finding 1: Remote command construction is shell-safe and SQL is scoped to the listing table only

Severity: OK

Evidence:
- routstr_delist.py:423-425 — `build_ssh_docker_cmd()` builds the ssh argv with `shlex.quote()` on both the container name and the inline Python payload, so the remote shell parses the whole `docker exec ... python3 -c ...` pipeline as a single quoted command.
- routstr_delist.py:348-355 — `pull_listing_sql()` is `UPDATE models SET enabled=0 WHERE enabled=1;` and explicitly does not touch `upstream_providers` or any router row.
- routstr_delist.py:400-411 — `verify_pull_payload()` performs a read-only `SELECT COUNT(*) FROM models WHERE enabled=1` against `/app/data/keys.db`, with no UPDATE/INSERT/DELETE.
- routstr_delist.py:767-775 — `_SshBackend.__doc__` restates that it only mutates the `models` table; the provider stays in the ladder.
- test_routstr_delist.py:468-488 — `TestSemanticGuardLadderUntouched` asserts the ladder artifact is byte-identical across a delist, the `upstream_providers` table is row-identical, and no executed payload ever names `upstream_providers`.

Conclusion: the safety controls for remote shell escaping and SQL scoping are present and tested.

---

## Finding 2: Delist success is confirmed by an independent re-fetch, not the pull's self-report

Severity: OK

Evidence:
- routstr_delist.py:680-688 — after a pull that self-reports `ok`, the code calls `backend.verify()` and only treats the delist as confirmed when `vres.get("ok") is True and vres.get("count") == 0`.
- routstr_delist.py:689-697 — if the re-fetch shows non-zero still-advertised models (or fails), the attempt is recorded as `confirmed=False`, `ok` is forced to `False`, and one bounded in-run retry is attempted.
- routstr_delist.py:719-739 — an unconfirmed delist exits non-zero, preserves the acceleration baseline, does NOT set `delisted=true`, ticks the circuit breaker, and records `last_pull_error`.
- routstr_delist.md:69-75 — contract text explicitly states the re-fetch gates success on `count == 0`, never on the pull round-trip's self-report.
- test_routstr_delist.py:346-360 — `test_unverified_pull_is_a_failed_delist()` proves a pull that self-reports ok but is refuted by the re-fetch results in exit 1, `delisted=False`, and a breaker tick.
- test_routstr_delist.py:319-344 — `test_acceleration_fires_exactly_one_delist_verified_by_refetch()` asserts `confirmed=True`, `verified_count==0`, and that the verify payload contains `SELECT COUNT(*) FROM models WHERE enabled=1` with no `UPDATE`.

Conclusion: the independent confirmation requirement is implemented, exercised, and enforced in failure semantics.

---

## Finding 3: Stale or missing prediction feed is fail-safe — it cannot trigger a delist or wipe the baseline

Severity: OK

Evidence:
- routstr_delist.py:485-496 — `feed_is_stale()` treats any failure to determine age as STALE (`except OSError: return True`) and only returns False for a file provably fresh. This is documented as fail-safe in the implementation docstring.
- routstr_delist.py:589-592 — when the feed is stale, `raw_preds` is set to `[]` before triggers are evaluated, so no variance/acceleration trigger can fire.
- routstr_delist.py:255-267 — `update_state()` only overwrites the stored acceleration baseline snapshot when `preds` is truthy; an empty/corrupt feed leaves the previous `snapshot` intact.
- routstr_delist.py:585-586 — an explicitly requested feed that yields nothing is flagged as `preds_error` and causes a non-zero exit when no trigger fired, preventing a silent "quiet" misclassification.
- routstr_delist.md:56-60 — contract explicitly defines the freshness guard: stale feed never triggers, never refreshes baseline, and reports `preds_stale: true` with non-zero exit; manual override is never gated on freshness.
- test_routstr_delist.py:427-433 — `test_manual_override_is_never_gated_on_feed_staleness()` proves `--manual` still delists even when `preds_stale` is true.
- test_routstr_delist.py:289-315 — steady-burn / no-baseline cases confirm the baseline is not consumed and no delist occurs on quiet or first-run inputs.

Conclusion: stale/corrupt feed handling is fail-safe in both directions: it blocks automatic triggers and preserves the acceleration baseline.
