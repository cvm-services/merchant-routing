# Offload review — routstr delist, findings 6–7 (circuit breaker, hygiene)

First independent offload pass for findings 6–7 (re-dispatch, 2026-09-17).
Scope: original task items 6 (circuit breaker: 3 failed attempts → BLOCKED,
exit code 3) and 7 (hygiene: secrets, loops). Every claim below was re-derived
in this session: the script was read end-to-end (both copies), the contract
stand-in and the full test suite read end-to-end, all greps re-run, the live
state file read, and the suite executed fresh. Nothing was carried over
unverified from the Gate 2.5 review or the findings 4–5 passes.

**Artifact-path status (required report per task instructions):**

- `~/.hermes/bot/docs/routstr_delist_contract.md` — **MISSING — HIGH**.
  Re-verified this session: the path does not exist; `~/.hermes/bot/docs/`
  contains only `reviews/`. The contract role is filled by the repo's
  `docs/routstr-delist.md` (129 lines) — the document the script itself cites
  at routstr_delist.py:21 — and it was read end-to-end as the stand-in.
- `~/.hermes/bot/tests/test_routstr_delist.py` — **MISSING — HIGH**. No
  `tests/` directory exists anywhere under `~/.hermes/bot` (re-verified this
  session). The repo counterpart `tests/test_routstr_delist.py` (546 lines,
  55 tests) was read end-to-end instead.
- `~/.hermes/bot/scripts/routstr_delist.py` — present (602 lines), verified
  **byte-identical** to repo `src/routstr_delist.py` this session (`cmp`:
  clean). All script line references below therefore apply to both copies.

Conventions: `routstr_delist.py:N` = the script (both copies); `tests:N` =
repo tests; `docs:N` = repo `docs/routstr-delist.md`. Live evidence read (not
modified): the deployed state file `~/.hermes/bot/routstr_delist_state.json`.
Suite evidence (this pass): `python3 -m pytest tests/test_routstr_delist.py -q`
→ **55 passed in 0.17s** (hermetic, no network). No artifacts were modified by
this review.

## Finding 6 — Circuit breaker (3 failed attempts → BLOCKED, exit 3) — **REFUTED (HIGH)**

**Explicit statement required by the task: the circuit-breaker claim "3 failed
attempts → BLOCKED state, exit code 3" is REFUTED — no circuit breaker exists
in the artifact.** Evidence, each item re-derived this session:

1. **No breaker vocabulary anywhere in the code.** `grep -nEi
   'breaker|blocked|consecutive|attempt|circuit'` over the module returns
   exactly one hit: the word "consecutive" in an unrelated docstring sentence
   about prediction readings (routstr_delist.py:15). No counter, no threshold,
   no BLOCKED state, no attempt cap.
2. **Exit code 3 does not exist.** `main()` returns only 0 or 1, at every
   return site: routstr_delist.py:480 (`--status`), :500 (relist failed),
   :510 (relist ok), :524 (`return 1 if preds_error else 0`), :539 (delist
   failed), :555 (delist ok); entry point is `raise SystemExit(main())`
   (routstr_delist.py:601-602). Grep for `return 3` / `sys.exit(3)`: zero
   hits. The process can therefore never signal BLOCKED by exit code.
3. **The durable state carries no failure counter.** The complete set of keys
   ever written to state: `ts`, `snapshot`, `delisted`, `last_reason`
   (`update_state`, routstr_delist.py:215-235 — assignments at :227-232),
   `pulled_models` (routstr_delist.py:503, :543), and `last_pull_error`
   (routstr_delist.py:496, :534). `last_pull_error` is a single slot
   **overwritten** on each failure (delist path routstr_delist.py:533-535,
   relist path routstr_delist.py:495-497) — it records the latest error, not a
   consecutive-failure count. There is no reset semantics to state because
   there is no counter to reset.
4. **Can attempt 4 ever run? Yes — attempt 40 can.** Nothing halts repeated
   attempts, by construction on both trigger paths:
   - A failed pull deliberately preserves the acceleration baseline: the
     failure branch (routstr_delist.py:529-539) mutates only `ts` and
     `last_pull_error` and never calls `update_state`, so the prior
     `snapshot` survives and trigger 1 re-fires identically on the next cron
     tick (the code comments this intent at routstr_delist.py:530-532).
   - Trigger 2 is level-based (`variance_jumped`, routstr_delist.py:117-143,
     docstring :118-119; docs:41-44): while `uncertainty` stays elevated the
     run re-fires every tick, indefinitely.
   - The fire gate `fire = args.delist or dec["fire"]`
     (routstr_delist.py:515) feeds the same pull path each time, and the
     documented cadence is cron `*/5` (docs:59-63, example crontab at
     docs:63). No attempt counting, no halt, no cooldown.
5. **No BLOCKED is ever surfaced to the operator.** The failure-path output
   is `{"action": "delist_failed", "fire": true, ...}` with rc 1
   (routstr_delist.py:536-539) — byte-identical JSON on the 1st and the 100th
   consecutive failure. Monitoring cannot distinguish "first failure" from
   "persistently failing"; the only durable trace is the single-slot
   `last_pull_error`.
6. **Contract and tests are silent too.** Grep over `docs/routstr-delist.md`:
   the only "blocked" is unrelated prose about dq05 outbound-SSH policy
   (docs:72); the failure-semantics section (docs:46-55) documents exit
   non-zero + `last_pull_error` and nothing more. Grep over all 546 test
   lines for breaker/BLOCKED/exit-3: zero hits; the failure-path test
   actually pins `rc == 1` (tests:351-375, assertion at tests:368).
7. **Live evidence:** the deployed state file
   `~/.hermes/bot/routstr_delist_state.json` reads `{"delisted": true,
   "last_reason": "manual override", "snapshot": {}, "ts": 1788883877.3967388}`
   — no counter key exists in the running deployment either.

**Verdict 6: HIGH.** Must-fix: a consecutive-failure counter in the durable
state; halt after exactly 3; surface `BLOCKED` in the output JSON; exit code
3; reset the counter on success; and define explicitly whether a manual
`--delist` resets it (an operator forcing past a breaker must be a documented
decision, not an accident).

## Finding 7 — Hygiene (secrets, loops) — **OK in-process (MEDIUM on the operational loop)**

### 7a. Secrets — **OK**

- The nsec is read from a file only inside `publish_delist_event()`
  (routstr_delist.py:408-409) and reaches `nak` exclusively via the child
  environment `NOSTR_SECRET_KEY` (routstr_delist.py:410-412) with the
  `--env-sec` flag (routstr_delist.py:397). The constructed argv
  (routstr_delist.py:393-398) contains kind, tags, content JSON, and relay
  URLs — no secret material. This is regression-pinned by tests:316-317
  (`--env-sec` present, `--sec` absent); a missing sec file yields `None`
  before any subprocess (routstr_delist.py:388-389; tested tests:302-303),
  and the contract mandates `--env-sec` over `--sec` for ps-leak reasons
  (docs:82-84).
- The secret is never printed: the nak subprocess runs with
  `capture_output=True` (routstr_delist.py:412) and the captured output is
  discarded; `publish_delist_event` returns only the secret-free argv
  (routstr_delist.py:415); `main()` never prints env or file contents.
- The secret is never persisted: grep for nsec/NOSTR/secret intersected with
  the state-write paths → zero hits; the state schema (keys enumerated in
  Finding 6, item 3) has no secret-bearing field.
- Exception surfaces are clean: `_run`'s except branch returns
  `str(exc)` (routstr_delist.py:597-598) — worst case a TimeoutExpired whose
  text carries the ssh argv (host + SQL payload), which contains no
  credential; remote `stdout`/`stderr` echoed into results are truncated to
  200 chars (routstr_delist.py:592-593) and originate from the payload's own
  prints.

### 7b. Loops — **OK in-process**

- Every in-process iteration is a finite `for` loop or comprehension over an
  in-memory list, grep-enumerated this session: routstr_delist.py:97, :131,
  :187, :264 (for-loops) and :95, :276, :279, :430 (comprehensions), plus the
  payload-internal comprehension embedded in the remote python string
  (routstr_delist.py:336). The only `while` tokens in the module are prose in
  docstrings (routstr_delist.py:19, :119) — no `while` loop exists.
- Both subprocesses are timeout-bounded: the ssh docker-exec at 60 s
  (routstr_delist.py:582) and the nak publish at 30 s
  (routstr_delist.py:410). There is no in-process retry of either.

### 7c. The operational loop — **MEDIUM**

The one uncapped loop in the system lives outside the process: cron re-attempts
a failed pull every 5 minutes forever (documented cadence docs:59-63) with no
cap, deadline, backoff, or breaker — this is Finding 6 viewed from the
scheduler side, and its must-fix (halt-after-3 + BLOCKED + exit 3) is the
remedy. Mitigating context, verified this session: no crontab entry is wired
at all yet (docs:69-72), so the unbounded retry is currently latent rather
than running.

### 7d. Permissions / housekeeping — **LOW**

`save_state()` (routstr_delist.py:204-212) creates the state file with default
umask and no fsync/atomic-replace (the atomicity gap is Finding 4a, cross-ref
findings_4_5.md §4a); the live state file is observed group/world-readable
(`-rw-rw-r--`). Impact is nil because the state contains no credentials (key
enumeration above), and the `--preds` feed / override marker carry no secrets
either.

**Verdict 7: OK in-process; MEDIUM operationally** (uncapped cron retry,
shared root cause with Finding 6; LOW permissions note).

---

Provenance: first offload pass for findings 6–7. The Gate 2.5 cold review
(repo commit 69d489c, `docs/reviews/routstr_delist_review.md`) previously
reached the same two verdicts (6 REFUTED-HIGH; 7 OK-in-process with a MEDIUM
operational loop); this pass re-derived every claim independently against the
artifacts (script read end-to-end in both copies, `cmp` byte-identical;
contract stand-in and all 546 test lines read; greps re-run; live state file
read; 55/55 suite green in 0.17 s) and confirms both. `~/.hermes/bot` is not
a git repository (re-verified this session), so the required local commit
lands in the workspace repo (merchant-routing) at `docs/reviews/findings_6_7.md`,
with this identical copy at the task-mandated bot path
`~/.hermes/bot/docs/reviews/findings_6_7.md`.
