# Review findings 1-3: safety, confirmation, fail-safe

**Scope:** routstr dynamic delist (ADR-007 Gate 4) — review of safety, confirmation, and fail-safe behavior across the three requested artifacts.

**Requested artifacts:**
- `~/.hermes/bot/docs/routstr_delist_contract.md` — **MISSING** (HIGH severity documentation/audit item)
- `~/.hermes/bot/scripts/routstr_delist.py` — present
- `~/.hermes/bot/tests/test_routstr_delist.py` — present

The only available design contract is `~/.hermes/bot/docs/routstr-delist.md`, which was reviewed as the substitute for the missing contract path.

---

## Finding 1: Safety — remote command construction, SQL/secret scoping, and the missing contract path

**Severity:** OK

1.1. The requested contract file `~/.hermes/bot/docs/routstr_delist_contract.md` is **MISSING**. This is a **HIGH** documentation/audit-trail defect because it is the path named in the task body and in prior review references. The shipped contract is `~/.hermes/bot/docs/routstr-delist.md:1`, and the implementation is `~/.hermes/bot/scripts/routstr_delist.py`; runtime safety does not depend on the filename, but auditability does.

1.2. `build_ssh_docker_cmd()` at `~/.hermes/bot/scripts/routstr_delist.py:414-425` builds the ssh remote command as a single string passed as one ssh argv element. It `shlex.quote`s the container name at `~/.hermes/bot/scripts/routstr_delist.py:423` and the Python payload at `~/.hermes/bot/scripts/routstr_delist.py:424`, so `subprocess.run` at `~/.hermes/bot/scripts/routstr_delist.py:808` never invokes a local shell and the remote shell cannot inject through metacharacters in the container name or payload boundary.

1.3. The pulling logic is scoped to the `models` listing table only: `pull_listing_sql()` at `~/.hermes/bot/scripts/routstr_delist.py:348-355` is a constant `UPDATE models SET enabled=0 WHERE enabled=1;` and `verify_pull_payload()` at `~/.hermes/bot/scripts/routstr_delist.py:400-411` is read-only. No payload names `upstream_providers` or any router-ladder table, satisfying the SALE-vs-provider distinction.

1.4. The relist path is properly parameterized: `relist_payload()` at `~/.hermes/bot/scripts/routstr_delist.py:378-397` builds `UPDATE models SET enabled=1 WHERE name IN (?,...)` with the captured model names passed as a Python list repr used as the sqlite3 parameter tuple; no user/data value is interpolated into SQL.

1.5. Secret handling is safe: `build_delist_event()` at `~/.hermes/bot/scripts/routstr_delist.py:429-448` emits `--env-sec`, and `publish_delist_event()` at `~/.hermes/bot/scripts/routstr_delist.py:451-464` reads the nsec from the file and passes it only via the `NOSTR_SECRET_KEY` environment variable. The secret never appears in argv, stdout, or the state file. `~/.hermes/bot/tests/test_routstr_delist.py:705-728` asserts this.

**Overall:** Runtime safety requirements are satisfied; findings 1a-1e are OK. The missing requested contract path is tracked separately as the HIGH documentation defect in 1.1.

---

## Finding 2: Confirmation — independent re-fetch verifies the listing was pulled

**Severity:** OK

2.1. A separate, read-only verification payload exists: `verify_pull_payload()` at `~/.hermes/bot/scripts/routstr_delist.py:400-411` returns a `python3 -c` payload that runs only `SELECT COUNT(*) FROM models WHERE enabled=1` and prints the count. It contains no `UPDATE` or other mutation and is structurally independent of `pull_listing_payload()` at `~/.hermes/bot/scripts/routstr_delist.py:364-375`.

2.2. Success is gated on the re-fetch result, not on the pull's self-report. The fire/delist loop at `~/.hermes/bot/scripts/routstr_delist.py:671-697` calls `backend.verify()` at line 682 after `pull_listing()`. Confirmation is accepted only at `~/.hermes/bot/scripts/routstr_delist.py:683-687` when `vres.get("ok") is True and vres.get("count") == 0`.

2.3. A self-reporting "ok" pull that the re-fetch refutes is treated as a failed attempt. At `~/.hermes/bot/scripts/routstr_delist.py:691-694` the code sets `res["ok"] = False`, `res["confirmed"] = False`, records `verify` details, and falls through to the failure path at `~/.hermes/bot/scripts/routstr_delist.py:719-739`.

2.4. The failure path preserves the acceleration baseline by writing `delisted: false` and `consecutive_failures` at `~/.hermes/bot/scripts/routstr_delist.py:724-731` without calling `update_state()` with the current preds, so the trigger will re-fire on the next run.

2.5. Bounded in-run retry is implemented at `~/.hermes/bot/scripts/routstr_delist.py:675-677` and `~/.hermes/bot/scripts/routstr_delist.py:695-697` (`attempts < MAX_PULL_ATTEMPTS` and `time.monotonic() < deadline`), and the whole loop counts as one run for breaker accounting.

2.6. The test suite validates the contract: `~/.hermes/bot/tests/test_routstr_delist.py:319-345` shows a confirmed acceleration delist with `["pull", "verify"]` and `verified_count == 0`; `~/.hermes/bot/tests/test_routstr_delist.py:346-360` shows a lying pull (`pull_lands=False`) yielding `delist_failed`, exit 1, no durable `delisted` flip, and a breaker tick.

---

## Finding 3: Fail-safe — stale feeds, baseline preservation, and circuit breaker

**Severity:** OK

3.1. Stale or unreadable feeds are fail-closed: `feed_is_stale()` at `~/.hermes/bot/scripts/routstr_delist.py:485-496` returns `True` on any OSError and returns `False` only when `0 <= age <= STALENESS_S` (30 minutes). A stale feed forces `raw_preds = []` at `~/.hermes/bot/scripts/routstr_delist.py:591-592`, preventing variance and acceleration triggers and preventing baseline refresh; the run exits non-zero at `~/.hermes/bot/scripts/routstr_delist.py:660` when no override fired.

3.2. Missing or corrupt feeds are also fail-closed: `_read_preds()` at `~/.hermes/bot/scripts/routstr_delist.py:468-482` returns `[]` on any parse error, non-list input, or non-dict entries. `preds_error` is set at `~/.hermes/bot/scripts/routstr_delist.py:585` when an explicit `--preds` path yields nothing, and the run exits non-zero at `~/.hermes/bot/scripts/routstr_delist.py:660`.

3.3. The acceleration baseline is preserved across bad feeds: `update_state()` at `~/.hermes/bot/scripts/routstr_delist.py:248-268` overwrites the stored snapshot only when `preds` is truthy (`if preds:` at line 261), so an empty or failed feed cannot wipe the baseline used by `exhaustion_accelerated()` at `~/.hermes/bot/scripts/routstr_delist.py:92-128`.

3.4. The circuit breaker is durable and correctly counted: `BREAKER_THRESHOLD = 3` at `~/.hermes/bot/scripts/routstr_delist.py:77`; each failed RUN increments `consecutive_failures` and, once the threshold is reached, writes `blocked: true` and exits `3` at `~/.hermes/bot/scripts/routstr_delist.py:724-739`. While blocked, `main()` refuses all remote action and returns `3` at `~/.hermes/bot/scripts/routstr_delist.py:569-578`. `--unblock` clears both flags at `~/.hermes/bot/scripts/routstr_delist.py:561-567`. `~/.hermes/bot/tests/test_routstr_delist.py:582-624` exercises this.

3.5. Manual override is exempt from the freshness gate by design, preserving the humans-can-always-act rule: `~/.hermes/bot/scripts/routstr_delist.py:580` and `~/.hermes/bot/scripts/routstr_delist.py:660` show the trigger path evaluates `preds_stale` only for the no-fire non-zero exit, while manual override still fires through `dec["fire"]` at `~/.hermes/bot/scripts/routstr_delist.py:646-649`. `~/.hermes/bot/tests/test_routstr_delist.py:427-433` asserts that `--manual` fires on a stale feed and reports `preds_stale: true`.

3.6. The relist success path clears breaker state at `~/.hermes/bot/scripts/routstr_delist.py:636-637`, consistent with the delist success reset at `~/.hermes/bot/scripts/routstr_delist.py:750-751`, so an operator recovery action is not kept blocked.
