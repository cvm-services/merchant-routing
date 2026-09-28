# Findings 1–3 Review: routstr_delist

Scope: safety, confirmation, fail-safe.
Artifacts reviewed:
- `~/.hermes/bot/docs/routstr-delist.md` (contract/spec)
- `~/.hermes/bot/scripts/routstr_delist.py`
- `~/.hermes/bot/tests/test_routstr_delist.py`

Note: the requested `~/.hermes/bot/docs/routstr_delist_contract.md` was **missing**. The equivalent contract is present as `routstr-delist.md` and was reviewed instead; this filename mismatch is reported as HIGH under Finding 1.

---

## Finding 1 — Safety: remote shell command built by string concatenation without quoting the SSH target

Severity: **HIGH**

The production SSH command is constructed in `build_ssh_docker_cmd` by joining `ssh_target`, `container`, and `payload` into a single remote command string. While `container` and `payload` are correctly `shlex.quote`d, the SSH target (`debian@23.182.128.51` by default) is interpolated directly into the argv array and then into the remote shell string without validation or quoting.

Evidence:
- `~/.hermes/bot/scripts/routstr_delist.py:423-425`:
  ```python
  remote = " ".join(["docker", "exec", shlex.quote(container),
                     "python3", "-c", shlex.quote(payload)])
  return ["ssh", ssh_target, remote]
  ```
- `~/.hermes/bot/scripts/routstr_delist.py:86`: `_DEFAULT_SSH_TARGET = "debian@23.182.128.51"` is a single hard-coded host string; if overridden via `--ssh-target` with user-supplied input containing shell metacharacters, the command vector remains `["ssh", <unquoted>, <remote command>]`, which `ssh` will pass to the remote shell as a multi-token command prefix.

Impact: a crafted `--ssh-target` could break out of the intended single-remote-command semantics and cause the remote shell to execute unintended tokens. The contract at `routstr-delist.md:132-139` claims the remote pipeline is emitted as a single argv element with quoting, but the SSH target itself is not covered by that quoting.

Recommended fixes:
1. Validate or shell-quote `ssh_target` before inserting it into the argv.
2. Prefer `ssh_target` split into `[user@host]` (still a single argv token) and document that `--ssh-target` must be a bare `user@host` or host.
3. Add a regression test in `test_routstr_delist.py` asserting malicious `--ssh-target` values cannot inject extra remote tokens.

---

## Finding 2 — Confirmation: delist success is gated on an independent read-only re-fetch

Severity: **OK**

The delist path performs a mutation round-trip (`pull`) followed by a separate read-only verification round-trip (`verify`) and only treats the operation as successful when `verify` reports `count == 0`. A pull that self-reports `ok` but leaves rows enabled is correctly treated as a failure, with bounded in-run retry.

Evidence:
- `~/.hermes/bot/scripts/routstr_delist.py:671-697`: the delist retry loop calls `pull_listing(backend, ...)` then `backend.verify(...)`, sets `confirmed = True` only when `vres.get("ok") is True and vres.get("count") == 0`, and resets `res["ok"] = False` if verification refutes the pull.
- `~/.hermes/bot/scripts/routstr_delist.py:719-739`: on `not confirmed`, the code exits non-zero (1 or 3), leaves `delisted` as `False`, increments `consecutive_failures`, and records `last_pull_error` — satisfying the failure-semantics requirement.
- `~/.hermes/bot/scripts/routstr_delist.py:400-411`: `verify_pull_payload()` issues `SELECT COUNT(*) FROM models WHERE enabled=1` only, with no `UPDATE`.
- `~/.hermes/bot/tests/test_routstr_delist.py:346-360`: `test_unverified_pull_is_a_failed_delist` asserts that a lying pull is retried, then fails with exit 1, `delisted=False`, and a breaker tick.
- `~/.hermes/bot/tests/test_routstr_delist.py:319-344`: `test_acceleration_fires_exactly_one_delist_verified_by_refetch` asserts `confirmed=True`, `verified_count=0`, and verifies the payload is read-only.

No issue; the confirmation gate is correctly implemented and tested.

---

## Finding 3 — Fail-safe: stale or missing prediction feed is handled defensively

Severity: **OK**

The script defends against bad feed data in the fail-safe direction: an explicitly provided but empty/unreadable feed is flagged (`preds_error`), a stale feed older than `STALENESS_S` is treated as dead data (`preds_stale`), and neither condition refreshes the acceleration baseline. Manual override continues to work regardless of feed state, and the run exits non-zero when nothing fired so monitoring can react.

Evidence:
- `~/.hermes/bot/scripts/routstr_delist.py:585`: `preds_error = bool(args.preds) and not raw_preds`.
- `~/.hermes/bot/scripts/routstr_delist.py:589-592`: `preds_stale = bool(args.preds) and bool(raw_preds) and feed_is_stale(args.preds)`; if true, `raw_preds = []`.
- `~/.hermes/bot/scripts/routstr_delist.py:248-268`: `update_state` only overwrites `snapshot` when `preds` is truthy (`if preds:`), preserving the previous baseline on empty/stale feeds.
- `~/.hermes/bot/scripts/routstr_delist.py:485-496`: `feed_is_stale` returns `True` on any `OSError` (fail-closed: unstatable feed = stale feed).
- `~/.hermes/bot/scripts/routstr_delist.py:650-660`: when not firing, the script exits `1` if `preds_error` or `preds_stale` is true.
- `~/.hermes/bot/scripts/routstr_delist.py:580`: `override = args.manual or manual_override(args.override)` is computed before and independent of the feed checks.
- `~/.hermes/bot/tests/test_routstr_delist.py:427-433`: `test_manual_override_is_never_gated_on_feed_staleness` confirms `--manual` still delists despite `preds_stale=True`.

No issue; the fail-safe behavior matches the contract and is covered by tests.

---

## Additional note: missing contract filename

Severity: **HIGH**

The requested artifact `~/.hermes/bot/docs/routstr_delist_contract.md` does not exist. The functional contract document is `~/.hermes/bot/docs/routstr-delist.md`. Any downstream tooling or fleet dispatch expecting the `_contract.md` filename will fail to locate the source of truth.

Recommended fix: create a symlink or rename the file so the requested path resolves, or update the dispatch/task body to reference the existing `routstr-delist.md`.
