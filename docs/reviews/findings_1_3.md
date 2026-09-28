# Review Findings 1–3: routstr delist contract

Artifact status:
- `~/.hermes/bot/docs/routstr_delist_contract.md` — **MISSING** (HIGH)
- `~/.hermes/bot/docs/routstr-delist.md` — present, used as the contract artifact
- `~/.hermes/bot/scripts/routstr_delist.py` — present
- `~/.hermes/bot/tests/test_routstr_delist.py` — present

---

## Finding 1 — safety: remote command shell-injection / quoting

Severity: **OK**

Evidence:
- `~/.hermes/bot/scripts/routstr_delist.py:414-425` defines `build_ssh_docker_cmd(ssh_target, container, payload)`.
- It builds the remote command as one string and applies `shlex.quote` to both the container name and the python payload:
  - `remote = " ".join(["docker", "exec", shlex.quote(container), "python3", "-c", shlex.quote(payload)])`
  - `return ["ssh", ssh_target, remote]`
- The local invocation uses `subprocess.run(cmd, ...)` without `shell=True` at `~/.hermes/bot/scripts/routstr_delist.py:808`, so the local shell is not involved.
- The contract doc at `~/.hermes/bot/docs/routstr-delist.md:132-139` calls out this exact mitigation: "`ssh` joins everything after the host into ONE string parsed by the remote shell, so `build_ssh_docker_cmd()` emits the entire remote pipeline … as a single argv element with `shlex.quote` … The regression test re-parses the remote command with `shlex.split` and asserts it round-trips".
- Tests at `~/.hermes/bot/tests/test_routstr_delist.py:336-338` assert that the produced pull/verify payloads match the payload builders exactly, and the test suite includes shell-safety/round-trip assertions.

Conclusion: the SSH/docker command is constructed safely for the intended API boundary. No issue.

---

## Finding 2 — confirmation: delist success must be independently verified

Severity: **OK**

Evidence:
- The `verify_pull_payload()` function at `~/.hermes/bot/scripts/routstr_delist.py:400-411` returns a read-only payload:
  - `"n=db.execute('SELECT COUNT(*) FROM models WHERE enabled=1').fetchone()[0];"`
  - The payload is `SELECT`-only and never mutates.
- Main calls `backend.verify()` at `~/.hermes/bot/scripts/routstr_delist.py:682` after a successful pull.
- Success is gated on `vres.get("ok") is True and vres.get("count") == 0` at `~/.hermes/bot/scripts/routstr_delist.py:683`, not on the pull's own `ok` flag.
- If the re-fetch refutes the pull, the code sets `res["ok"] = False` and `res["confirmed"] = False` at `~/.hermes/bot/scripts/routstr_delist.py:691-694`.
- Failure semantics document at `~/.hermes/bot/docs/routstr-delist.md:62-75`: "Success is gated on the re-fetch reporting `count == 0` — never on the pull round-trip's self-report. A pull that self-reports ok but cannot be confirmed is a failed attempt."
- Tests at `~/.hermes/bot/tests/test_routstr_delist.py:346-361` (`test_unverified_pull_is_a_failed_delist`) simulate a lying pull and assert exit 1, `delisted=False`, and a breaker tick.
- Tests at `~/.hermes/bot/tests/test_routstr_delist.py:319-344` (`test_acceleration_fires_exactly_one_delist_verified_by_refetch`) assert one pull + one verify, `confirmed=True`, `verified_count==0`.

Conclusion: confirmation-by-independent-re-fetch is implemented and tested. No issue.

---

## Finding 3 — fail-safe: stale / missing / corrupt `--preds` feed must not trigger, must not wipe the acceleration baseline, and must be reported

Severity: **OK**

Evidence:
- `feed_is_stale(pred_input, ...)` at `~/.hermes/bot/scripts/routstr_delist.py:485-496` returns `True` on any OSError or whenever age cannot be proven fresh (fail-closed). It returns `False` only when `0 <= age <= max_age_s`.
- In `main()` at `~/.hermes/bot/scripts/routstr_delist.py:589-592`, when the feed is stale the predictions are replaced with `[]`:
  - `preds_stale = bool(args.preds) and bool(raw_preds) and feed_is_stale(args.preds)`
  - `if preds_stale: raw_preds = []`
- An explicitly requested feed that yields nothing is flagged as `preds_error = bool(args.preds) and not raw_preds` at `~/.hermes/bot/scripts/routstr_delist.py:585`.
- `update_state(...)` only writes the snapshot when `preds` is truthy at `~/.hermes/bot/scripts/routstr_delist.py:261-262`; with `preds=[]` the stored acceleration baseline is preserved.
- The no-fire output at `~/.hermes/bot/scripts/routstr_delist.py:655-660` includes `"preds_error": preds_error, "preds_stale": preds_stale` and exits `1` when either flag is set.
- Manual override is gated independently at `~/.hermes/bot/scripts/routstr_delist.py:580` and can still fire when the feed is stale (tested at `~/.hermes/bot/tests/test_routstr_delist.py:427-433`).
- Contract doc at `~/.hermes/bot/docs/routstr-delist.md:56-60` and `~/.hermes/bot/docs/routstr-delist.md:84-86` document both the stale/dead-data guard and the corrupt-feed guard.
- Tests cover stale feed (`test_manual_override_is_never_gated_on_feed_staleness`) and steady-state baseline preservation.

Conclusion: stale/dead/corrupt feed handling is fail-safe and observable. No issue.
