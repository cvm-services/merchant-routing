# Review Findings 1–3: Safety, Confirmation, Fail-safe

## Artifact status

- `~/.hermes/bot/docs/routstr_delist_contract.md`: **MISSING** (requested path not found).
  A similar file exists at `~/.hermes/bot/docs/routstr-delist.md` and was reviewed instead.
- `~/.hermes/bot/scripts/routstr_delist.py`: present (830 lines).
- `~/.hermes/bot/tests/test_routstr_delist.py`: present (753 lines).

The missing contract file is reported as **HIGH** severity under Finding 1 because the review task asked for an end-to-end read of the specified artifacts.

---

## Finding 1: Safety — remote command construction and SQL scoping

**Severity: HIGH**

### Evidence

- **1.1 Contract path missing.** `~/.hermes/bot/docs/routstr_delist_contract.md` does not exist (file read returned zero bytes / "File not found"). The contract documentation is instead located at `~/.hermes/bot/docs/routstr-delist.md`, lines 1–198. A downstream consumer or CI job referencing the requested path will fail. This is a documentation/artifact-integrity issue with safety impact because the contract file is the source of truth for behavior.

- **1.2 Shell injection risk in `build_ssh_docker_cmd` is mitigated.** `~/.hermes/bot/scripts/routstr_delist.py:423-425` quotes both the container name and the Python payload:
  ```python
  remote = " ".join(["docker", "exec", shlex.quote(container),
                     "python3", "-c", shlex.quote(payload)])
  return ["ssh", ssh_target, remote]
  ```
  This is the correct fail-safe shape: no user-controlled value reaches the remote shell unquoted.

- **1.3 SQL scope is strictly limited to the `models` listing table.** The delist payloads are defined at:
  - `~/.hermes/bot/scripts/routstr_delist.py:348-355`: `pull_listing_sql()` returns `UPDATE models SET enabled=0 WHERE enabled=1;`
  - `~/.hermes/bot/scripts/routstr_delist.py:358-361`: `relist_sql()` returns `UPDATE models SET enabled=1;` (legacy fallback only, see Finding 3).
  - `~/.hermes/bot/scripts/routstr_delist.py:364-375`: `pull_listing_payload()` captures advertised names from `models`, then disables exactly those rows.
  
  The contract confirms this intent at `~/.hermes/bot/docs/routstr-delist.md:18-20`: "mutates strictly the `models` (listing) table. It never touches `upstream_providers` or any router provider row."

- **1.4 Tests validate both shell-safety and SQL scope.**
  - `~/.hermes/bot/tests/test_routstr_delist.py:468-489` (`TestSemanticGuardLadderUntouched::test_provider_ladder_byte_identical_across_delist`) asserts that `upstream_providers` is never named in any executed payload, that the provider ladder artifact is byte-identical, and that the routstr provider remains `enabled == 1`.
  - Shell-quoting round-trip is exercised implicitly by `FakeSellNode.execute` parsing the payload as Python, and by `_SshBackend._run` (`~/.hermes/bot/scripts/routstr_delist.py:795-825`) which builds the real argv and parses the last line of JSON output.

- **1.5 Severity rationale.** The missing contract file is HIGH because the requested artifact is the canonical contract; its absence could cause integration or verification steps to reference stale/missing documentation. The implementation itself is safe, so the HIGH tag is tied to the artifact gap, not to active code vulnerability.

---

## Finding 2: Confirmation — independent re-fetch gating

**Severity: OK**

### Evidence

- **2.1 Verified by an independent read-only re-fetch.** After a pull, the code runs a separate `verify` round-trip using `verify_pull_payload()` (`~/.hermes/bot/scripts/routstr_delist.py:400-411`):
  ```python
  return (
      "import sqlite3,json;"
      "db=sqlite3.connect('/app/data/keys.db');"
      "n=db.execute('SELECT COUNT(*) FROM models WHERE enabled=1')"
      ".fetchone()[0];"
      "print(json.dumps({'ok':True,'count':n}))"
  )
  ```
  This payload is SELECT-only; it never mutates the database.

- **2.2 Success is gated on the re-fetch count being zero.** `~/.hermes/bot/scripts/routstr_delist.py:682-687`:
  ```python
  vres = backend.verify(deadline=deadline)
  if vres.get("ok") is True and vres.get("count") == 0:
      res["confirmed"] = True
      res["verified_count"] = vres.get("count")
      confirmed = True
      break
  ```
  A pull that self-reports `ok` but cannot be confirmed is treated as a failure.

- **2.3 Lying pull scenario is exercised and rejected.** `~/.hermes/bot/tests/test_routstr_delist.py:346-360` (`TestBurnAccelerationDelist::test_unverified_pull_is_a_failed_delist`) sets `rig.node.pull_lands = False` and asserts:
  - exit code `1`,
  - `action == "delist_failed"`,
  - `delisted` remains `False` in state,
  - `consecutive_failures` is incremented,
  - the verify count equals the number of still-advertised models.

- **2.4 Bounded retry absorbs transient blips.** The main loop at `~/.hermes/bot/scripts/routstr_delist.py:671-697` allows up to `MAX_PULL_ATTEMPTS = 2` attempts (`~/.hermes/bot/scripts/routstr_delist.py:75`), but success is still decided by the independent verify.

- **2.5 Contract documents the confirmation requirement.** `~/.hermes/bot/docs/routstr-delist.md:69-75` states: "a fired delist is one pull + one independent read-only re-fetch (`verify`) counting still-advertised models. Success is gated on the re-fetch reporting `count == 0` — never on the pull round-trip's self-report."

---

## Finding 3: Fail-safe — stale/corrupt feed handling and baseline preservation

**Severity: OK**

### Evidence

- **3.1 Stale feed is treated as dead data.** `~/.hermes/bot/scripts/routstr_delist.py:485-496` defines `feed_is_stale`:
  ```python
  def feed_is_stale(pred_input, *, max_age_s=STALENESS_S, now=None):
      try:
          age = (now if now is not None else time.time()) - \
              os.path.getmtime(pred_input)
          return not (0 <= age <= max_age_s)
      except OSError:
          return True
  ```
  The fail-safe direction is correct: any OSError (missing file, permission, clock issue) returns `True` (stale), so dead data cannot drive a delist.

- **3.2 Stale feed never refreshes the acceleration baseline.** `~/.hermes/bot/scripts/routstr_delist.py:589-593`:
  ```python
  preds_stale = bool(args.preds) and bool(raw_preds) and \
      feed_is_stale(args.preds)
  if preds_stale:
      raw_preds = []
  ```
  When stale, `raw_preds` is emptied before it reaches `evaluate_triggers` or `update_state`, so the snapshot baseline stored in state cannot be overwritten by stale data.

- **3.3 Empty prediction list preserves the stored baseline.** `~/.hermes/bot/scripts/routstr_delist.py:255-262`:
  ```python
  """An EMPTY preds list never overwrites the stored baseline snapshot — a
  missing/corrupt feed must not blind the acceleration trigger."""
  new = dict(state or {})
  new["ts"] = ts
  if preds:
      new["snapshot"] = snapshot_preds(preds)
  ```
  This prevents a quiet/empty feed from erasing the previous comparison baseline.

- **3.4 Corrupt or non-dict feed entries are dropped.** `~/.hermes/bot/scripts/routstr_delist.py:468-482` (`_read_preds`) returns `[]` if the file is unreadable, not a list, or contains only non-dict entries; it never raises. The caller then sets `preds_error = bool(args.preds) and not raw_preds` (`~/.hermes/bot/scripts/routstr_delist.py:585`) and exits non-zero when nothing else fired (`~/.hermes/bot/scripts/routstr_delist.py:660`).

- **3.5 Tests cover the fail-safe paths.**
  - `~/.hermes/bot/tests/test_routstr_delist.py:427-433` (`TestManualOverride::test_manual_override_is_never_gated_on_feed_staleness`) confirms that even with a stale feed, manual override still delists, while `preds_stale` is truthfully reported.
  - `~/.hermes/bot/tests/test_routstr_delist.py:379-387` (`TestKalmanVarianceDelist::test_variance_at_threshold_is_quiet`) confirms the strictly-greater-than threshold boundary.
  - `~/.hermes/bot/tests/test_routstr_delist.py:308-314` (`TestQuietNoTrigger::test_first_run_without_baseline_is_quiet`) confirms that no baseline means no false acceleration trigger.

- **3.6 Severity rationale.** The implementation and tests demonstrate correct fail-safe behavior for stale/corrupt feeds. The OK severity reflects that the code meets the requirement.

---

## Summary

| # | Finding | Severity |
|---|---------|----------|
| 1 | Safety: requested contract file is missing (review fell back to `routstr-delist.md`); implementation correctly quotes SSH payload and scopes SQL to `models` | HIGH |
| 2 | Confirmation: delist success is independently verified by a read-only re-fetch; lying pulls fail | OK |
| 3 | Fail-safe: stale/corrupt feeds are treated as dead data and do not overwrite the acceleration baseline; manual override still works | OK |
