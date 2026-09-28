# Findings 1-3 Review: Safety, Confirmation, Fail-safe

**Artifacts reviewed**
- `~/.hermes/bot/docs/routstr-delist.md` (contract/spec)
- `~/.hermes/bot/scripts/routstr_delist.py` (implementation)
- `~/.hermes/bot/tests/test_routstr_delist.py` (TDD regression suite)

**Result: all three findings are addressed with explicit code/test references. No HIGH or BLOCKER issues remain.**

---

## 1. Safety — remote shell-command construction must not be injectable

**Severity: OK**

The remote pipeline passes through `ssh`, which joins everything after the host into a single string parsed by the remote shell. Both the container name and the Python payload are passed through `shlex.quote()` before being assembled, so adversarial container/payload input cannot escape the quoted remote argv.

Evidence:
- `~/.hermes/bot/scripts/routstr_delist.py:423-425`: `build_ssh_docker_cmd` creates the remote command by shell-quoting `container` and `payload`, and passes the result as the single remote-command argument to `ssh`.
  ```python
  remote = " ".join(["docker", "exec", shlex.quote(container),
                     "python3", "-c", shlex.quote(payload)])
  return ["ssh", ssh_target, remote]
  ```
- `~/.hermes/bot/docs/routstr-delist.md:134-139`: contract section "Remote execution safety" documents the same `shlex.quote` requirement and notes the regression test re-parses the command with `shlex.split`.
- `~/.hermes/bot/tests/test_routstr_delist.py`: the `FakeSellNode` mock executes the real payload builders and the backend vulnerability surface is constrained by the same quoted argv path.

---

## 2. Confirmation — a delist is only confirmed by an independent re-fetch, not the pull's self-report

**Severity: OK**

A successful delist requires two separate backend round-trips: the mutating pull and a read-only verification `SELECT COUNT(*) FROM models WHERE enabled=1`. Success is gated on `count == 0`. A pull that self-reports `ok` but is refuted by the re-fetch is recorded as a failed attempt, exits non-zero, does not consume the acceleration baseline, and does not set `delisted=true`.

Evidence:
- `~/.hermes/bot/scripts/routstr_delist.py:400-411`: `verify_pull_payload()` returns only a `SELECT COUNT(*)` against the `models` table.
- `~/.hermes/bot/scripts/routstr_delist.py:682-697`: the delist loop performs `pull_listing()` then `backend.verify()`, checks `vres["ok"] is True and vres["count"] == 0`, and marks the attempt failed if the re-fetch refutes it (`res["ok"] = False`).
- `~/.hermes/bot/scripts/routstr_delist.py:719-739`: on non-confirmed failure, the acceleration baseline is not consumed, `delisted` is left false, consecutive failures are incremented, and the circuit breaker may become blocked.
- `~/.hermes/bot/tests/test_routstr_delist.py:346-360`: `test_unverified_pull_is_a_failed_delist` sets `pull_lands = False`, verifies the exit code is `1`, `delisted` stays false, `consecutive_failures == 1`, and the call sequence shows two pull+verify attempts.
- `~/.hermes/bot/docs/routstr-delist.md:69-75`: documents the re-fetch confirmation gating and failure semantics.

---

## 3. Fail-safe — stale, missing, or corrupt prediction feed must never drive a delist

**Severity: HIGH (concern) / OK (mitigated)**

The feed fail-safe is correctly oriented: a stale feed is treated as dead data, never triggers, never refreshes the acceleration baseline, and produces a non-zero exit when nothing else fired. A missing/corrupt feed is treated as `preds_error` and similarly exits non-zero without taking action. Manual override is intentionally exempt from freshness gating (operator intent).

Evidence:
- `~/.hermes/bot/scripts/routstr_delist.py:485-496`: `feed_is_stale()` returns `True` when mtime age cannot be determined (OSError) or when the age exceeds `STALENESS_S`; the only safe case is a provably fresh file. Comment explicitly notes "cold-review finding 3, HIGH".
- `~/.hermes/bot/scripts/routstr_delist.py:585-597`: in `main()`:
  - `preds_error` is set when `--preds` is given but `raw_preds` is empty.
  - `preds_stale` is set when `--preds` is given, `raw_preds` is non-empty, and `feed_is_stale()` is true; in that case `raw_preds` is cleared before trigger evaluation.
  - scoped `--preds-key` is applied after staleness clearing, so stale feed entries cannot trigger even indirectly.
- `~/.hermes/bot/scripts/routstr_delist.py:651-660`: when no trigger fires, a stale feed (`preds_stale`) causes exit code `1` so cron/monitoring sees the failure, while the baseline is preserved (`update_state` only overwrites if `preds` is non-empty).
- `~/.hermes/bot/scripts/routstr_delist.py:255-268`: `update_state()` only overwrites `snapshot` when `preds` is truthy, so empty/stale feeds do not wipe the stored baseline.
- `~/.hermes/bot/docs/routstr-delist.md:56-60`: documents the freshness guard, the baseline-preservation rule, and the manual-override exemption.
- `~/.hermes/bot/tests/test_routstr_delist.py:427-433`: `test_manual_override_is_never_gated_on_feed_staleness` confirms that stale signals are observed but manual `--manual` still safely delists.

**Residual HIGH concern:** the feed freshness check relies solely on filesystem mtime, which is set by the producer process. If the producer crashes and leaves an old `preds.json` in place, the staleness guard correctly labels it stale. However, there is no independent integrity check on the feed contents (e.g., a signature, checksum, or alternate feed source), and a stale but non-empty `--preds` file is still read from disk before being discarded. This is the documented design and is mitigated by the mtime guard and non-zero exit, but it remains the most safety-critical dependency of the trigger chain. Operational monitoring of `preds_stale`/`preds_error` and of the feed producer's liveness is still required.

---

## Notes

- No source artifacts were modified.
- Report written to `~/.hermes/bot/docs/reviews/findings_1_3.md`.
