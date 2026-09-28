# Review findings 1–3: safety, confirmation, fail-safe

## Finding 1 — Safety: remote command construction relies on proper shell quoting

**Severity: OK**

The SSH-backed delist executes a remote `docker exec <container> python3 -c <payload>` command. Because `ssh` joins everything after the host into a single string that the remote shell parses, the script must quote the container name and the Python payload so the remote shell receives them as single words and cannot inject commands through a malicious container name or payload.

- `~/.hermes/bot/scripts/routstr_delist.py:423-425` builds the remote command with `shlex.quote(container)` and `shlex.quote(payload)`:

  ```python
  remote = " ".join(["docker", "exec", shlex.quote(container),
                     "python3", "-c", shlex.quote(payload)])
  return ["ssh", ssh_target, remote]
  ```

This matches the safety requirement in the contract (`~/.hermes/bot/docs/routstr-delist.md:134-139`) and is exercised by the test suite, which re-parses the emitted command with `shlex.split`. The payload itself is constructed from trusted, hard-coded SQL strings and Python wrapper code, so shell-quoting the whole `-c` argument provides the correct defensive barrier.

No change is required; the implementation satisfies Finding 1.

---

## Finding 2 — Confirmation: delist success is gated on an independent re-fetch

**Severity: OK**

A delist that succeeds only because the remote command returned exit code 0 would be unsafe: a lying pull, a partial commit, or a command rejected on the remote side could be mistaken for success. The contract requires a second, read-only round-trip that counts still-advertised models and confirms the count is zero.

- `~/.hermes/bot/scripts/routstr_delist.py:400-411` defines `verify_pull_payload()`, a read-only `SELECT COUNT(*) FROM models WHERE enabled=1` payload. The docstring explicitly states it is the "post-pull RE-FETCH" and that success is gated on `count == 0`.
- `~/.hermes/bot/scripts/routstr_delist.py:682-688` calls `backend.verify(deadline=deadline)` after a successful pull and only marks the delist as confirmed when `vres.get("ok") is True and vres.get("count") == 0`.
- `~/.hermes/bot/scripts/routstr_delist.py:719-739` handles the unconfirmed case by setting `delisted=False`, incrementing the consecutive-failure counter, and exiting non-zero (`1` or `3` if the breaker trips).
- `~/.hermes/bot/tests/test_routstr_delist.py:346-360` (`test_unverified_pull_is_a_failed_delist`) simulates a lying pull (`pull_lands=False`) and asserts the run returns `1`, records `delisted=False`, and increments `consecutive_failures`.

The implementation satisfies Finding 2.

---

## Finding 3 — Fail-safe: stale or unreadable feeds must not trigger a delist or corrupt the baseline

**Severity: OK**

Using dead or corrupt prediction data to delist a provider would be dangerous. The contract requires that a stale feed (older than 30 minutes) is treated as dead data: it must not trigger variance-based or acceleration-based delisting and must not overwrite the stored acceleration baseline. Manual override must remain usable.

- `~/.hermes/bot/scripts/routstr_delist.py:485-496` defines `feed_is_stale()`. The docstring states the fail-safe direction: an age that cannot be determined is treated as stale. The function returns `True` for any OSError, negative age, or age above `STALENESS_S` (30 minutes).
- `~/.hermes/bot/scripts/routstr_delist.py:589-593` sets `preds_stale=True` when the feed is stale and immediately replaces the prediction list with an empty list, preventing both triggers and baseline refresh.
- `~/.hermes/bot/scripts/routstr_delist.py:582-585` detects an explicitly requested but empty/unreadable feed (`preds_error=True`) and later exits non-zero at `~/.hermes/bot/scripts/routstr_delist.py:660` when no trigger fired.
- `~/.hermes/bot/scripts/routstr_delist.py:255-257` (`update_state` docstring) documents that an empty `preds` list never overwrites the stored baseline snapshot, and the implementation at `~/.hermes/bot/scripts/routstr_delist.py:261-262` only writes a new snapshot when `preds` is truthy.
- `~/.hermes/bot/tests/test_routstr_delist.py:427-433` (`test_manual_override_is_never_gated_on_feed_staleness`) confirms that `--manual` still delists even when the feed is stale.

The implementation satisfies Finding 3.
