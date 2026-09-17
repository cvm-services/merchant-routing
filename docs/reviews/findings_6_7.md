# Offload review — routstr delist, findings 6–7 (circuit breaker, hygiene)

Second independent verification pass for findings 6–7 (re-dispatch, 2026-09-17).
Scope: original task items 6 (circuit breaker: 3 failed attempts → BLOCKED,
exit code 3) and 7 (hygiene: secrets, loops). Nothing below was carried over
unverified: this session re-read the script end-to-end in both copies (`cmp`:
byte-identical), re-read the contract stand-in `docs/routstr-delist.md` (129
lines) and all 546 test lines end-to-end, re-ran every grep, read the live
state file and its permissions, re-executed the suite
(`python3 -m pytest tests/test_routstr_delist.py -q` → **55 passed in
0.17s**, hermetic), and — new this pass — ran two hermetic dynamic probes with
`subprocess.run`/`_SshBackend` mocked (no network, no artifacts touched).

**Artifact-path status (required report per task instructions):**

- `~/.hermes/bot/docs/routstr_delist_contract.md` — **MISSING — HIGH**
  (re-verified this session: `~/.hermes/bot/docs/` exists but contains only
  `reviews/`; no `*contract*` file anywhere under `~/.hermes/bot`). The
  contract role is filled by repo `docs/routstr-delist.md` — the document the
  script itself cites at routstr_delist.py:21 — read end-to-end as stand-in.
- `~/.hermes/bot/tests/test_routstr_delist.py` — **MISSING — HIGH** (no
  `tests/` directory exists under `~/.hermes/bot`). Repo counterpart
  `tests/test_routstr_delist.py` (546 lines, 55 tests) read end-to-end instead.
- `~/.hermes/bot/scripts/routstr_delist.py` — present (602 lines), verified
  byte-identical to repo `src/routstr_delist.py` this session (`cmp`: clean).

Conventions: `routstr_delist.py:N` = the script (both copies identical);
`tests:N` = repo tests; `docs:N` = repo `docs/routstr-delist.md`. Live
evidence read (not modified): `~/.hermes/bot/routstr_delist_state.json`.

## Finding 6 — Circuit breaker (3 failed attempts → BLOCKED, exit 3) — **REFUTED (HIGH)**

**Explicit statement required by the task: the circuit-breaker claim "3 failed
attempts → BLOCKED state, exit code 3" is REFUTED — no circuit breaker exists
in the artifact.** Every item re-derived this session:

1. **No breaker vocabulary in the code.** `grep -nEi
   'breaker|blocked|consecutive|attempt|circuit'` over the module returns
   exactly one hit: "consecutive" in an unrelated docstring sentence about
   prediction readings (routstr_delist.py:15). No counter, no threshold, no
   BLOCKED state, no attempt cap.
2. **Exit code 3 does not exist.** `main()` returns only 0 or 1, at every
   return site: routstr_delist.py:480 (`--status`), :500 (relist failed),
   :510 (relist ok), :524 (`return 1 if preds_error else 0`), :539 (delist
   failed), :555 (delist ok); entry point `raise SystemExit(main())`
   (routstr_delist.py:601-602). Measured this session, the CLI's complete
   exit-code space is **{0, 1, 2}** (0 = success paths, 1 = pull/relist
   failure or preds error, 2 = argparse usage error on a bad flag) — 3 is
   unreachable, so the process can never signal BLOCKED by exit code.
3. **The durable state carries no failure counter.** Complete set of keys
   ever written: `ts`, `snapshot`, `delisted`, `last_reason` (`update_state`,
   routstr_delist.py:215-235, assignments :227-232), `pulled_models`
   (routstr_delist.py:503, :543), `last_pull_error` (routstr_delist.py:496,
   :534). `last_pull_error` is a single slot **overwritten** on each failure
   (delist path routstr_delist.py:533-535, relist path :495-497) — latest
   error, not a consecutive count; there is no counter to reset. Live
   evidence: the deployed `~/.hermes/bot/routstr_delist_state.json` reads
   `{"delisted": true, "last_reason": "manual override", "snapshot": {},
   "ts": 1788883877.3967388}` — no counter key in the running deployment.
4. **Can attempt 4 run? Yes — attempt N runs, proven dynamically.** Hermetic
   probe (this session): a permanently-failing backend driven through the
   real CLI path 5 times consecutively → return codes `[1, 1, 1, 1, 1]`,
   output `action: "delist_failed"` identical on the 5th attempt, state keys
   after 5 failures exactly `['last_pull_error', 'ts']`, zero
   counter/blocked keys. Nothing halts, by construction: the failure branch
   deliberately preserves the acceleration baseline (routstr_delist.py:529-539
   mutates only `ts`/`last_pull_error`; intent commented at :530-532), trigger
   2 is level-based and re-fires every tick while elevated
   (routstr_delist.py:117-143, docstring :118-119; docs:41-44), the fire gate
   `fire = args.delist or dec["fire"]` (routstr_delist.py:515) feeds the same
   pull path each tick, and the documented cadence is cron `*/5`
   (docs:59-63). No counting, no halt, no cooldown, no backoff.
5. **No BLOCKED is ever surfaced to the operator.** Failure-path output is
   `{"action": "delist_failed", "fire": true, ...}` with rc 1
   (routstr_delist.py:536-539) — identical JSON on the 1st and 100th
   consecutive failure (probe above: identical on attempts 1–5); monitoring
   cannot distinguish "first failure" from "persistently failing".
6. **Contract and tests are silent too.** In `docs/routstr-delist.md` the only
   "blocked" is unrelated dq05 outbound-SSH prose (docs:72); the
   failure-semantics section (docs:46-55) documents exit non-zero +
   `last_pull_error` and nothing more. Grep over all 546 test lines for
   breaker/BLOCKED/exit-3: zero hits; the failure-path test actually pins
   `rc == 1` (tests:351-375, assertion at tests:368).

**Verdict 6: HIGH — must-fix.** Implement: consecutive-failure counter in the
durable state; halt after exactly 3; surface `BLOCKED` in the output JSON;
exit code 3; reset on success; and define explicitly whether a manual
`--delist` resets the counter (forcing past a breaker must be a documented
decision, not an accident).

## Finding 7 — Hygiene (secrets, loops) — **OK in-process (MEDIUM: dry-run side effects, operational loop)**

### 7a. Secrets — **OK**

- The nsec is read from a file only inside `publish_delist_event()`
  (routstr_delist.py:408-409) and reaches `nak` exclusively via child
  environment `NOSTR_SECRET_KEY` (routstr_delist.py:410-412) with `--env-sec`
  (routstr_delist.py:397). The built argv (routstr_delist.py:393-398) carries
  kind/tags/content/relays only — no secret material. Regression-pinned by
  tests:316-317 (`--env-sec` present, `--sec` absent); missing sec file →
  `None` before any subprocess (routstr_delist.py:388-389; tests:302-303);
  the contract mandates `--env-sec` over `--sec` for ps-leak reasons
  (docs:82-84). Confirmed dynamically this session: in the dry-run probe the
  secret appeared only in the mocked child env, never in argv.
- Never printed: nak runs `capture_output=True` (routstr_delist.py:412) and
  the captured output is discarded; the function returns only the secret-free
  argv (routstr_delist.py:415); `main()` never prints env or file contents.
- Never persisted: the state key set (enumerated in Finding 6, item 3) has no
  secret-bearing field; `last_pull_error` stores only the backend result dict
  (routstr_delist.py:534, :496).
- Exception surfaces are clean: `_run`'s except branch returns `str(exc)`
  (routstr_delist.py:597-598) — worst case a TimeoutExpired carrying the ssh
  argv (host + SQL payload), no credential; echoed `stdout`/`stderr` are
  truncated to 200 chars (routstr_delist.py:592-593) and come from the
  payload's own prints.

### 7b. Loops in-process — **OK**

Every in-process iteration is a finite `for`/comprehension over an in-memory
list, grep-enumerated this session: routstr_delist.py:97, :131, :187, :264
(for) and :95, :276, :279, :430 (comprehensions), plus the comprehension
embedded in the remote payload string (:336). The only `while` tokens are
docstring prose (routstr_delist.py:19, :119) — no `while` loop exists. Both
subprocesses are timeout-bounded (ssh 60 s at :582; nak 30 s at :410); no
in-process retry of either.

### 7c. Dry-run is NOT side-effect-free — **MEDIUM (new this pass)**

`--dry-run` help promises "do not execute the remote delist" and the contract
says "Dry-run: performs no remote action" (docs:55) / "All remote actions take
`--dry-run` (prints intent, executes nothing)" (docs:107). Two real side
effects slip through:

1. **A real Nostr publish fires in dry-run.** `publish_delist_event()`
   (routstr_delist.py:402-415) has no `dry_run` parameter, and its only two
   call sites — relist path routstr_delist.py:505-506 and delist success path
   :547-548 — are gated solely on `args.nsec`, never on `args.dry_run`; the
   function unconditionally runs the `nak` subprocess
   (routstr_delist.py:410-412) against public relays (:390). Proven
   dynamically this session: `--manual --dry-run --nsec <file>` reached
   `subprocess.run` with the real argv (`nak event --kind 30078 …`) and the
   secret in the child env, rc 0 — only the mock prevented an actual network
   publish. There is no argparse guard against combining `--dry-run` with
   `--nsec` (argument definitions routstr_delist.py:462-468), and no test
   covers the combination (grep over tests: the only publish assertions mock
   `publish_delist_event` out entirely — tests:438, :450).
2. **The durable publisher flag flips in dry-run.** After the (dry) pull the
   run writes `delisted=true` to the state JSON
   (routstr_delist.py:541-544) — and that flag is the operative input "the
   listing publisher reads" (docs:79-80), so a dry-run can change the real
   advertisement through the flag channel. This half is doc-blessed
   ("records local intent state", docs:55) and even test-pinned
   (tests:332-346 asserts `st["delisted"]` true after `--manual --dry-run`;
   probe confirmed `delisted: true` + `action: "delist"`, distinguished from
   a real run only by `dry_run: true` in the printed JSON, not in state).

Mitigation: kind-30078 `d=routstr-delist` is parametrized-replaceable, so a
later real delist/relist event replaces a mistakenly published one — but
sell-side consumers may already have reacted, and a mis-flipped flag stands
until the next real run. Must-fix: gate both publish call sites on
`not args.dry_run` (or thread a `dry_run` parameter through
`publish_delist_event`) and add a regression test for `--dry-run --nsec`.
(Scope note: the flag-flip half is documented behaviour, so the MEDIUM rests
primarily on the real-event publish.)

### 7d. The operational loop — **MEDIUM**

The one uncapped loop lives outside the process: cron re-attempts a failed
pull every 5 minutes forever (documented cadence docs:59-63) with no cap,
deadline, backoff, or breaker — Finding 6 viewed from the scheduler side;
its must-fix is the remedy. Mitigating context, verified live this session:
no crontab entry is wired at all yet (docs:69-72), so the unbounded retry is
currently latent, not running.

### 7e. Permissions / housekeeping — **LOW**

`save_state()` (routstr_delist.py:204-212) writes with default umask — the
live state file is observed `-rw-rw-r--` this session — and without atomic
replace/fsync (that gap is Finding 4a, cross-ref findings_4_5.md). Impact nil:
the state contains no credentials (key enumeration in Finding 6/7a); the
`--preds` feed and override marker carry no secrets either.

**Verdict 7: OK in-process on secrets and loops; MEDIUM on dry-run side
effects (7c, new this pass) and the uncapped operational retry loop (7d,
shared root cause with Finding 6); LOW permissions note (7e).**

---

Provenance: second independent verification pass for findings 6–7. The Gate
2.5 cold review (commit 69d489c) and the first offload pass (commit 03c1d15)
both reached: 6 REFUTED-HIGH, 7 OK-in-process with a MEDIUM operational loop.
This pass re-derived every claim independently (both script copies read and
`cmp`-identical; contract stand-in and all 546 test lines read; greps re-run;
live state + permissions read; 55/55 suite green in 0.17 s) and **confirms
both verdicts**, upgrading Finding 7's detail with a new MEDIUM sub-finding
(7c: `--dry-run --nsec` performs a real Nostr publish and flips the durable
`delisted` flag) that neither prior pass detected, backed by hermetic dynamic
probes. No artifacts were modified. `~/.hermes/bot` is not a git repository,
so the required local commit lands in the workspace repo (merchant-routing)
at `docs/reviews/findings_6_7.md`, with this identical copy at the
task-mandated bot path `~/.hermes/bot/docs/reviews/findings_6_7.md`.
