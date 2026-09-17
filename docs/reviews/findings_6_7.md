# Offload review — routstr delist, findings 6–7 (circuit breaker, hygiene)

Fourth independent verification pass for findings 6–7 (re-dispatch,
2026-09-17 evening). Scope: original task item 6 (circuit breaker: 3 failed
attempts → BLOCKED state, exit code 3) and item 7 (hygiene: secrets, loops).
Nothing below is carried over unverified: this session re-read the script
end-to-end in both copies (`cmp`: byte-identical, 602 lines), re-read the
contract stand-in `docs/routstr-delist.md` (129 lines) and all 546 test lines
end-to-end, re-ran every grep, read the live state file and its permissions
(read-only), re-ran the suite (`python3 -m pytest tests/test_routstr_delist.py
-q` → **55 passed in 0.23s**, hermetic), and executed six hermetic dynamic
probes (faked `_SshBackend`, mocked `subprocess.run`, tmpdir state — no
network, no artifact touched).

**Artifact-path status (required report per task instructions):**

- `~/.hermes/bot/docs/routstr_delist_contract.md` — **MISSING — HIGH**
  (re-verified this session: `~/.hermes/bot/docs/` contains only `reviews/`;
  no `*contract*` file anywhere under `~/.hermes/bot`). The contract role is
  filled by repo `docs/routstr-delist.md` — the document the script itself
  cites at routstr_delist.py:21 — read end-to-end as the stand-in.
- `~/.hermes/bot/tests/test_routstr_delist.py` — **MISSING — HIGH** (no
  `tests/` directory exists under `~/.hermes/bot`; checked this session). Repo
  counterpart `tests/test_routstr_delist.py` (546 lines, 55 tests) read
  end-to-end instead.
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
2. **Exit code 3 does not exist — measured, not just read.** `main()` returns
   only 0 or 1 at every return site: routstr_delist.py:480 (`--status`),
   :500 (relist failed), :510 (relist ok), :524 (`return 1 if preds_error
   else 0`), :539 (delist failed), :555 (delist ok); entry point is
   `raise SystemExit(main())` (routstr_delist.py:601-602); no other
   `sys.exit`/exit-code path exists (grep this session). Dynamic probe of the
   real CLI as a subprocess: bad flag → rc 2 (argparse), `--status` → rc 0,
   missing-`--preds`-feed quiet run → rc 1, `--manual --dry-run` → rc 0
   (rc 1 paths pinned by tests:368 and tests:403). The complete exit-code
   space is **{0, 1, 2}** — 3 is unreachable, so the process can never signal
   BLOCKED by exit code.
3. **The durable state carries no failure counter.** Complete set of keys ever
   written: `ts`, `snapshot`, `delisted`, `last_reason` (`update_state`,
   routstr_delist.py:215-235, assignments :227-232), `pulled_models`
   (routstr_delist.py:543, popped at :503), `last_pull_error`
   (routstr_delist.py:534 delist path, :496 relist path). `last_pull_error`
   is a single slot **overwritten** on each failure — latest error, not a
   consecutive count; there is no counter to reset. Live evidence: the
   deployed `~/.hermes/bot/routstr_delist_state.json` (mode `-rw-rw-r--`,
   104 bytes) reads `{"delisted": true, "last_reason": "manual override",
   "snapshot": {}, "ts": 1788883877.3967388}` — no counter key in the running
   deployment. Full success-cycle probe this session: final state keys
   exactly `['delisted', 'last_reason', 'ts']` — no counter ever appears.
4. **Can attempt 4 run? Yes — attempt N runs, proven dynamically.** Hermetic
   probe (this session): a permanently-failing backend driven through the
   real `rd.main()` CLI path 5 times consecutively on one persistent state
   file → return codes `[1, 1, 1, 1, 1]`, `action: "delist_failed"`
   identical on all 5 attempts, state key union after 5 failures exactly
   `['last_pull_error', 'ts']`, zero counter/blocked keys, `delisted` never
   set. Nothing halts, by construction: the failure branch deliberately
   preserves the acceleration baseline (routstr_delist.py:529-539 mutates
   only `ts`/`last_pull_error`; intent commented at :530-532), trigger 2 is
   level-based and re-fires every tick while elevated
   (routstr_delist.py:117-143, docstring :119; docs:41-44), the fire gate
   `fire = args.delist or dec["fire"]` (routstr_delist.py:515) feeds the same
   pull path each tick, and the documented cadence is cron `*/5`
   (docs:59-63). No counting, no halt, no cooldown, no backoff.
5. **No BLOCKED is ever surfaced to the operator.** Failure-path output is
   `{"action": "delist_failed", "fire": true, ...}` with rc 1
   (routstr_delist.py:536-539) — identical JSON on the 1st and 100th
   consecutive failure (probe: byte-identical action on attempts 1–5);
   monitoring cannot distinguish "first failure" from "persistently failing".
6. **Contract and tests are silent too.** In `docs/routstr-delist.md` the
   only "blocked" is unrelated dq05 outbound-SSH prose (docs:72); the
   failure-semantics section (docs:46-55) documents exit non-zero +
   `last_pull_error` and nothing more. Grep over all 546 test lines for
   breaker/BLOCKED/circuit/exit-3: zero hits; the failure-path test pins the
   opposite (`rc == 1`, tests:351-375, assertion at tests:368).

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
  (docs:82-84). Confirmed dynamically this session: in both publish
  directions the secret appeared ONLY in the mocked child env
  (`env["NOSTR_SECRET_KEY"] == nsec`, `secret in argv: False`), never in the
  nak argv.
- Never printed: nak runs with `capture_output=True` (routstr_delist.py:412)
  and the captured output is discarded; the function returns only the
  secret-free argv (routstr_delist.py:415); `main()` never prints env or file
  contents.
- Never persisted: full-cycle probe this session — state keys after a
  complete delist→relist cycle exactly `['delisted', 'last_reason', 'ts']`,
  secret absent from the serialized state; `last_pull_error` stores only the
  backend result dict (routstr_delist.py:534, :496). Live state file content
  (read this session) confirms: keys are `delisted`/`last_reason`/`snapshot`/
  `ts` only.
- Exception surfaces are clean: `_run`'s except branch returns `str(exc)`
  (routstr_delist.py:597-598) — worst case a TimeoutExpired carrying the ssh
  argv (host + SQL payload), no credential; echoed `stdout`/`stderr` are
  truncated to 200 chars (routstr_delist.py:592-593) and come from the
  payload's own prints.

### 7b. Loops in-process — **OK**

Every in-process iteration is a finite `for`/comprehension over an in-memory
list; grep-enumerated this session: routstr_delist.py:97, :131, :187, :264
(for) and :95, :276, :279, :430 (comprehensions), plus the comprehension
embedded in the remote payload string (:336). The only `while` tokens are
docstring prose (routstr_delist.py:19, :119) — no `while` loop exists. Both
subprocesses are timeout-bounded (ssh 60 s at routstr_delist.py:582; nak 30 s
at :410, probe-confirmed `timeout=30`); no in-process retry of either.

### 7c. Dry-run is NOT side-effect-free — **MEDIUM**

`--dry-run` help promises "do not execute the remote delist"
(routstr_delist.py:462-463) and the contract says "Dry-run: performs no
remote action" (docs:55) / "All remote actions take `--dry-run` (prints
intent, executes nothing)" (docs:107). Four real side effects slip through:

1. **A real Nostr publish fires in dry-run, in BOTH directions.**
   `publish_delist_event()` (routstr_delist.py:402-415) has no `dry_run`
   parameter, and its only two call sites — relist path
   routstr_delist.py:505-506 and delist success path :547-548 — are gated
   solely on `args.nsec`, never on `args.dry_run`; the function
   unconditionally runs the `nak` subprocess (routstr_delist.py:410-412)
   against public relays (:390). Proven dynamically this session:
   `--manual --dry-run --nsec <file>` reached `subprocess.run` with the real
   argv `[…/nak, 'event', '--kind', '30078', …, '--env-sec',
   wss://relay.primal.net, wss://nos.lol, wss://relay.damus.io]` (content
   `delisted: true`), and `--relist --dry-run --nsec <file>` likewise fired
   the countering event (content `delisted: false`) — only the mocks
   prevented actual network publishes. There is no argparse guard against
   combining `--dry-run` with `--nsec` (argument definitions
   routstr_delist.py:462-468), and no test covers the combination (the only
   publish assertions mock `publish_delist_event` out entirely — tests:438,
   :450).
2. **The durable publisher flag flips in dry-run.** After the (dry) pull the
   run writes `delisted=true` to the state JSON
   (routstr_delist.py:541-544) — and that flag is the operative input "the
   listing publisher reads" (docs:79-80), so a dry run changes the real
   advertisement through the flag channel (probe: `delisted = true` after
   `--manual --dry-run`). This half is doc-blessed ("records local intent
   state", docs:55) and test-pinned (tests:332-346, `st["delisted"]`
   asserted true at tests:346); the dry-ness marker exists only in the
   printed JSON (`dry_run: true`), not in state. The dry RELIST flips it
   back (`delisted = false` after `--relist --dry-run`, probe; pinned at
   tests:515-519) — equally real.
3. **A dry-run relist destroys the scoped-relist capture.** The relist
   success path pops `pulled_models` from durable state
   (routstr_delist.py:503) and runs in dry-run too (the dry-run backend stub
   returns `ok: true`, routstr_delist.py:578-580, so the success branch is
   taken). Probe: state seeded with `pulled_models: ["gpt-4o", "llama-3"]`,
   one `--relist --dry-run` → afterwards the key is gone; state reduced to
   `delisted: false, last_reason: relist, snapshot, ts`. Consequence: the
   next REAL `--relist` reads `names = state.get("pulled_models") or []`
   (routstr_delist.py:491), gets `[]`, and falls back to the unscoped
   blanket `UPDATE models SET enabled=1;` (routstr_delist.py:326, :346-354;
   probe re-derived the exact fallback payload) — arming exactly the
   blanket-relist hazard documented as Finding 4 in
   `docs/reviews/findings_4_5.md` and contradicting docs:23-27 ("never rows
   the operator had disabled before the delist"). First recorded by the
   third pass (commit 1cef973); re-confirmed independently here.
4. **NEW this pass — a dry-run DELIST writes `pulled_models: []` into
   durable state on a fresh state file.** The delist success path stores
   `extra={"pulled_models": res.get("pulled", [])}`
   (routstr_delist.py:541-543) — but the real backend's dry-run stub
   (routstr_delist.py:578-580) returns no `pulled` key, so a dry-run delist
   persists a PRESENT-BUT-EMPTY `pulled_models` even when no real pull ever
   ran. Probe (real `_SshBackend`, dry-run returns before any subprocess —
   network-free by construction): fresh state, one `--manual --dry-run` →
   state reads `delisted: true, pulled_models: []`; the next `--relist`
   then resolves `names = [] or []` (routstr_delist.py:491) and takes the
   blanket `UPDATE models SET enabled=1;` fallback (payload re-derived from
   the probe's post-state). Distinct mechanism from item 3 (empty-list
   WRITE vs pop-on-relist): between them, ANY dry-run excursion through
   delist or relist leaves the state armed for an unscoped blanket relist.
   Neither prior 6–7 pass recorded this write-side half.

Mitigation for the event half: kind-30078 `d=routstr-delist` is
parametrized-replaceable, so a later real delist/relist event replaces a
mistakenly published one — but sell-side consumers may already have reacted,
and a mis-flipped flag or destroyed/emptied capture stands until the next
real run. Must-fix: gate both publish call sites on `not args.dry_run` (or
thread a `dry_run` parameter through `publish_delist_event`), keep dry-run
from writing/popping `pulled_models` (and ideally from flipping `delisted`),
and add regression tests for `--dry-run --nsec` (both directions), dry-run
relist state preservation, and dry-run delist not persisting an empty
capture.

### 7d. The operational loop — **MEDIUM**

The one uncapped loop lives outside the process: cron re-attempts a failed
pull every 5 minutes forever (documented cadence docs:59-63) with no cap,
deadline, backoff, or breaker — Finding 6 viewed from the scheduler side;
its must-fix is the remedy. Related, also unbounded: while a level-based
trigger condition holds and pulls SUCCEED, a kind-30078 publish fires every
tick (routstr_delist.py:547-548 behind the every-run fire gate :515) —
mitigated by parametrized-replaceability (same `d` tag replaces,
docs:81-87) but still a per-5-minute network publish for as long as the
condition persists. Mitigating context, verified in docs:69-72: no crontab
entry is wired at all yet, so both loops are currently latent, not running.

### 7e. Permissions / housekeeping — **LOW**

`save_state()` (routstr_delist.py:204-212) writes with default umask — the
live state file is observed `-rw-rw-r--` (mode 664) this session — and
without atomic replace/fsync (that gap is Finding 4, cross-ref
`findings_4_5.md`). Impact nil: the state contains no credentials (key
enumeration in Finding 6 item 3 / 7a); the `--preds` feed and override
marker carry no secrets either. LOW also: `publish_delist_event` failures
are swallowed entirely (routstr_delist.py:413-414) — if `nak` is missing the
event channel silently does nothing while the run reports success;
doc-blessed as "best-effort" (docs:85) but worth a state note for operators.

**Verdict 7: OK in-process on secrets and loops; MEDIUM on dry-run side
effects (7c — real publish both directions, durable flag flip, the
pulled_models destruction, and the NEW empty-capture write that arms the
blanket relist) and the uncapped operational retry loop (7d, shared root
cause with Finding 6); LOW permissions/silent-publish notes (7e).**

---

Provenance: fourth independent verification pass for findings 6–7. Prior
verdicts — Gate 2.5 cold review (commit 69d489c), first offload pass (commit
03c1d15), second pass (commit 9e1bb1a), third pass (commit 1cef973) —
reached: 6 REFUTED-HIGH; 7 OK-in-process with MEDIUMs. This pass re-derived
every claim independently (both script copies read and cmp-identical;
contract stand-in and all 546 test lines read; greps re-run; live state +
permissions read; 55/55 suite green in 0.23 s; six hermetic dynamic probes)
and **confirms both verdicts**, adding one new MEDIUM consequence under 7c
item 4 (dry-run delist persists `pulled_models: []` → blanket-SQL relist
fallback on a fresh state file) that no prior pass detected. No artifacts
were modified. `~/.hermes/bot` is not a git repository (verified: `git
rev-parse` fails there), so the required local commit lands in the workspace
repo (merchant-routing) at `docs/reviews/findings_6_7.md`, with this
identical copy at the task-mandated bot path
`~/.hermes/bot/docs/reviews/findings_6_7.md`.
