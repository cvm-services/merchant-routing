# Review Findings 1–3: routstr dynamic delist

**Artifact status**
- `~/.hermes/bot/scripts/routstr_delist.py` — present
- `~/.hermes/bot/tests/test_routstr_delist.py` — present
- `~/.hermes/bot/docs/routstr_delist_contract.md` — **MISSING** (HIGH). The frozen contract is available at `~/.hermes/bot/docs/routstr-delist.md` instead. This review uses the hyphenated file as the authoritative contract.

---

## Finding 1 — Safety: remote shell-command quoting

**Verdict:** OK

The production backend builds an SSH remote command whose container name and Python payload are both passed through `shlex.quote` before being joined into the single remote command string.

Evidence:
- `~/.hermes/bot/scripts/routstr_delist.py:414-425` — `build_ssh_docker_cmd` constructs the command as one argv element and quotes both the container and the payload:
  - Line 423-424: `remote = " ".join(["docker", "exec", shlex.quote(container), "python3", "-c", shlex.quote(payload)])`
  - Line 425: `return ["ssh", ssh_target, remote]`
- The `ssh_target` is the SSH host argument and is not parsed by the remote shell, so quoting is unnecessary and correctly omitted.
- The contract documents this explicitly at `~/.hermes/bot/docs/routstr-delist.md:132-139`.
- Regression coverage exists at `~/.hermes/bot/tests/test_routstr_delist.py` in the hermetic backend round-trips (e.g., `_NodeBackend._round_trip` builds the same command shape and the FakeSellNode executes the payload).

No arbitrary remote-command injection path was identified in the SSH dispatch.

---

## Finding 2 — Confirmation: independent re-fetch gates delist success

**Verdict:** OK

A fired delist is not accepted on the pull round-trip's self-report. The code performs an independent read-only re-fetch (`verify`) that counts still-advertised models and only succeeds when the count is zero.

Evidence:
- `~/.hermes/bot/scripts/routstr_delist.py:400-411` — `verify_pull_payload` returns a read-only SQL payload:
  - Line 408-409: `SELECT COUNT(*) FROM models WHERE enabled=1`
  - Line 403-404 comment states success is gated on this count being 0 and that the payload never mutates.
- `~/.hermes/bot/scripts/routstr_delist.py:666-697` — the fired action loop in `main`:
  - Line 673: `res = pull_listing(backend, dry_run=args.dry_run, deadline=deadline)`
  - Line 682: `vres = backend.verify(deadline=deadline)`
  - Line 683: success requires `vres.get("ok") is True and vres.get("count") == 0`
  - Lines 671-697: bounded retry (`MAX_PULL_ATTEMPTS = 2`) absorbs a transient failed/refuted pull; if verify still refutes, the run is a failure.
- Failure semantics are fail-closed:
  - Lines 719-739: on unconfirmed delist, `delisted` stays False, the acceleration baseline is **not** consumed, `consecutive_failures` increments, and the run exits non-zero (or 3 if the breaker trips).
- Tests:
  - `~/.hermes/bot/tests/test_routstr_delist.py:319-345` — acceleration fires exactly one delist and confirms via re-fetch.
  - `~/.hermes/bot/tests/test_routstr_delist.py:346-360` — a pull that self-reports ok but is refuted by verify is treated as a failed delist.

---

## Finding 3 — Fail-safe: stale/corrupt feed handling and baseline preservation

**Verdict:** OK

Dead or unreadable prediction data cannot accidentally trigger a delist, and a missing/corrupt feed never wipes the stored acceleration baseline. Manual override remains available regardless of feed health.

Evidence:
- Stale feed guard (`~/.hermes/bot/scripts/routstr_delist.py:485-496`):
  - Lines 491-496: `feed_is_stale` treats an unreadable or unstatable file as STALE (`except OSError: return True`).
- Stale preds are neutralized in `main`:
  - Lines 589-592: `preds_stale = bool(args.preds) and bool(raw_preds) and feed_is_stale(args.preds)`; if stale, `raw_preds = []` before trigger evaluation.
  - Line 660: a stale feed causes exit 1 when no trigger fires.
- Corrupt/unreadable feed handling:
  - Lines 468-482: `_read_preds` returns `[]` on any exception.
  - Line 585: `preds_error = bool(args.preds) and not raw_preds` flags the error.
  - Line 660: a feed error exits non-zero.
- Baseline preservation:
  - Lines 248-268: `update_state` only writes `new["snapshot"] = snapshot_preds(preds)` when `preds` is truthy; an empty list leaves the previous baseline intact.
  - Lines 719-739: a failed delist does not consume the baseline, so the same trigger will re-fire on the next run.
- Manual override is never gated on freshness:
  - Line 580: `override = args.manual or manual_override(args.override)` is evaluated before stale/error handling.
  - Lines 646-649: `dec["fire"]` includes manual override; `fire = args.delist or dec["fire"]`.
  - `~/.hermes/bot/tests/test_routstr_delist.py:427-433` asserts that `--manual` with a stale feed still delists.
- Full coverage also exists for first-run baseline guard (`~/.hermes/bot/tests/test_routstr_delist.py:308-314`) and quiet steady-state behavior (`~/.hermes/bot/tests/test_routstr_delist.py:292-306`).
