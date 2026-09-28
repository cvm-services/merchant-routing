## Finding 1: Safety — remote shell command construction and secret handling

Severity: HIGH

- `~/.hermes/bot/docs/routstr_delist_contract.md` is **missing** (ENOENT). The live contract is at `~/.hermes/bot/docs/routstr-delist.md:1`, and the deployed `~/.hermes/bot/scripts/routstr_delist.py` matches it. A missing canonical contract path is a HIGH documentation/audit-trail defect.
- Remote ssh command is built as one quoted string passed as a single argv element at `~/.hermes/bot/scripts/routstr_delist.py:414-425`:
  `remote = " ".join(["docker", "exec", shlex.quote(container), "python3", "-c", shlex.quote(payload)])`.
  `shlex.quote` on both `--container` and `--payload` blocks remote-shell metacharacter injection via the container name or payload boundary.
- The ssh target is passed as a separate list element at `~/.hermes/bot/scripts/routstr_delist.py:425` (`return ["ssh", ssh_target, remote]`), so the local `subprocess.run` call never invokes a shell on the host side.
- The SQL payloads contain no user-interpolated literals: `pull_listing_sql()` at `~/.hermes/bot/scripts/routstr_delist.py:348-355` is a constant; `relist_payload()` at `~/.hermes/bot/scripts/routstr_delist.py:378-397` builds a parameterized `WHERE name IN (?,...)` clause and embeds the captured model names only as a Python repr (`{names!r}`) while the values are bound separately by sqlite3.
- The kind-30078 event builder uses `--env-sec` at `~/.hermes/bot/scripts/routstr_delist.py:429-448` and passes the nsec via the `NOSTR_SECRET_KEY` environment variable in `publish_delist_event()` at `~/.hermes/bot/scripts/routstr_delist.py:451-464`; the secret never appears on the argv surface. This is asserted by `~/.hermes/bot/tests/test_routstr_delist.py:689-729`.

## Finding 2: Confirmation — independent re-fetch verifies that the sale was pulled

Severity: OK

- The verification payload is a read-only `SELECT COUNT(*) FROM models WHERE enabled=1` at `~/.hermes/bot/scripts/routstr_delist.py:400-411`; it performs no mutation and is a separate, independently shaped round-trip from `pull_listing_payload()`.
- The fired delist loop at `~/.hermes/bot/scripts/routstr_delist.py:671-697` runs `pull_listing()` first, then calls `backend.verify()` at line 682. Success is gated at `~/.hermes/bot/scripts/routstr_delist.py:683-687` on `vres.get("ok") is True and vres.get("count") == 0`. The pull's own `ok` report is not trusted until the independent re-fetch confirms zero advertised models.
- If the re-fetch refutes the pull, the attempt is marked failed, the durable `delisted` flag is not set, and one bounded in-run retry is attempted while `time.monotonic() < deadline` at `~/.hermes/bot/scripts/routstr_delist.py:675-677,695-697`.
- The test suite codifies this at `~/.hermes/bot/tests/test_routstr_delist.py:319-360`: a confirmed acceleration delist produces exactly `["pull", "verify"]`, and a lying pull (`pull_lands=False`) results in `delist_failed`, exit 1, and zero durable state flip.

## Finding 3: Fail-safe — stale feeds, baseline preservation, and circuit breaker

Severity: MEDIUM

- **Stale/missing feed:** `feed_is_stale()` at `~/.hermes/bot/scripts/routstr_delist.py:485-496` is fail-closed: it returns `True` when the file's mtime cannot be determined and `False` only when the age is provably within `0 <= age <= STALENESS_S`. A stale feed forces `raw_preds = []` at line 592, so triggers cannot fire and the acceleration baseline is not refreshed; the run exits non-zero at line 660 when no override fired. Manual override is deliberately not gated on freshness, verified at `~/.hermes/bot/tests/test_routstr_delist.py:427-433`.
- **Baseline preservation:** `update_state()` at `~/.hermes/bot/scripts/routstr_delist.py:248-268` writes the prediction snapshot only when `preds` is truthy (`if preds:` at line 261). An empty or missing feed therefore cannot wipe the stored baseline used by `exhaustion_accelerated()`.
- **Circuit breaker:** `BREAKER_THRESHOLD = 3` at `~/.hermes/bot/scripts/routstr_delist.py:77`; three consecutive failed delist runs set `blocked: true` and exit code 3 at `~/.hermes/bot/scripts/routstr_delist.py:724-739`. `--unblock` clears the marker and counter at lines 561-567. This is exercised by `~/.hermes/bot/tests/test_routstr_delist.py:581-624`.
- **MEDIUM concern — relist failures do not count toward the breaker:** a failed `--relist` at `~/.hermes/bot/scripts/routstr_delist.py:626-632` records `last_pull_error` and exits 1, but it does **not** increment `consecutive_failures` or set `blocked`. Unlike delist failures, repeated relist failures could therefore retry indefinitely without entering the operator-visible BLOCKED state. The fix is to apply the same breaker accounting used for delist failures (lines 724-739) to the relist failure path.
