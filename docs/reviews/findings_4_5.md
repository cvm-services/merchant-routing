# Offload review — routstr delist, findings 4–5 (atomicity/idempotence, SLA)

Fifth independent pass (re-dispatch, 2026-09-25). Scope: original task items 4
(atomicity + idempotence) and 5 (5-minute SLA arithmetic). Every claim below
was re-derived in this session against the CURRENT artifacts: the script read
end-to-end in both copies (829 lines), the bot-path test file read end-to-end
(752 lines), the repo unit suite swept for the finding-relevant regressions
(96 tests), the docs read in both copies, greps and byte-diffs re-run, the
live state file and the live crontab read, and all three suites executed
fresh. Nothing was carried over unverified from earlier passes.

**Material change since pass 4 (2026-09-17):** both findings were adjudicated
HIGH/HIGH against the pre-fix script (602 lines). Repo commits `b879354`
("close cold-review round-2 must-fixes — re-fetch confirmation, breaker,
atomic writes, staleness guard, SLA wiring") and `1c77910` (TDD contract
suite + bot-path deployed copies) land exactly the pass-4 must-fixes for
these two findings. This pass re-adjudicates both verdicts against the fixed
artifacts — each pass-4 must-fix is checked as implemented, and the residuals
are graded on their own merit.

**Artifact-path status (required report per task instructions):**

- `~/.hermes/bot/docs/routstr_delist_contract.md` — **MISSING — HIGH**.
  Re-verified this session: the path does not exist; `~/.hermes/bot/docs/`
  contains only `reviews/` and `routstr-delist.md`. The contract role is
  filled by (a) the design doc `routstr-delist.md` — the bot copy (197
  lines) read end-to-end as the stand-in; note it is 14 lines STALE against
  the repo copy, which alone documents the contract TDD suite at
  docs:177-190 — and (b) the TDD contract suite now deployed at the bot
  tests path (below), which encodes the contract as executable cases.
- `~/.hermes/bot/scripts/routstr_delist.py` — present (829 lines), verified
  **byte-identical** to repo `src/routstr_delist.py` this session (`diff`:
  clean). All script line references below apply to both copies.
- `~/.hermes/bot/tests/test_routstr_delist.py` — present again as of
  `1c77910` (752 lines, 25 pytest cases, read end-to-end). Verified
  byte-identical (md5 `031851b3…`) to repo `tests/test_routstr_delist_contract.py`
  — i.e. the deployed bot file is the CONTRACT suite, not the repo unit
  suite `tests/test_routstr_delist.py` (96 tests, different md5). Both
  suites were used as evidence: `tests:N` = repo unit suite,
  `contract:N` = bot-path/repo contract suite, `docs:N` = repo
  `docs/routstr-delist.md`.

Live evidence read (not modified): state file
`~/.hermes/bot/routstr_delist_state.json` (still the pass-4 shape:
`{"delisted": true, "last_reason": "manual override", "snapshot": {},
"ts": 1788883877.3967388}` — no `pulled_models` key) and `crontab -l`
(readable this pass): **no routstr_delist entry exists** — only the
worker watchdog `*/3` job. Suite evidence (this pass): repo unit suite
`96 passed in 0.32s`; repo contract suite `25 passed in 0.20s`; bot-path
contract suite against the deployed script `25 passed in 0.19s`. No
artifacts were modified by this review.

## Finding 4 — Atomicity and idempotence — **MEDIUM (core fixed in b879354; residuals graded below)**

### 4a. Atomicity — tmp+fsync+os.replace implemented and test-pinned — **OK core / MEDIUM residuals**

- **Fixed (pass-4 4a torn-write hole):** `save_state()` routstr_delist.py:221-245
  now writes a same-directory tmp file (routstr_delist.py:230), `json.dump` +
  `flush()` + `os.fsync()` (routstr_delist.py:231-234), then `os.replace()`
  (routstr_delist.py:235) — atomic on POSIX — with tmp cleanup in `finally`
  (routstr_delist.py:240-245). A concurrent reader can now only ever observe
  old-or-new, never torn.
- **Pinned by tests:** contract `TestAtomicStateWrites` proves the swap
  instant holds complete-old-at-dst + complete-new-in-tmp (contract:636-663)
  and that a simulated crash between tmp and replace leaves the previous
  state intact and loadable with no tmp litter (contract:665-686); unit
  `test_save_state_atomic_no_tmp_left_behind` (tests:273) pins the same.
- **Residual 1 — persistence failures remain silent — MEDIUM.**
  `save_state()` still returns True/False (routstr_delist.py:237, 239) and
  ALL EIGHT call sites invoke it as a bare statement (grep-enumerated this
  session: routstr_delist.py:565, 622, 629, 638, 654, 710, 732, 752). The
  pass-4 worked consequence stands in reduced form: remote pull confirmed,
  local persist fails (disk full, permissions), run still prints
  `action: delist` and exits 0 (routstr_delist.py:760-764) while the durable
  `delisted` flag — the flag the listing publisher reads
  (routstr_delist.py:251-253) — stays false and `pulled_models` is never
  stored. Atomic writes make this rarer (no torn middle state) but not
  surfaced: no test pins a `False` return propagating to exit status.
- **Residual 2 — no mutual exclusion between concurrent runs — MEDIUM.**
  Grep re-verified: zero lock primitives (`flock`/`fcntl`/lockfile) in the
  module; imports at routstr_delist.py:51-57 cannot lock. The
  load→modify→save sequence (e.g. merge at routstr_delist.py:744-749,
  breaker increment at routstr_delist.py:724-727) is still last-writer-wins:
  a manual `--relist` racing a cron delist tick can lose the other's write
  (lost `pulled_models` merge or lost breaker count). Now atomically
  last-writer-wins — torn reads are gone — but lost updates remain. No
  concurrency test exists in either suite (grep: 0 hits for
  thread/concurrent/flock/parallel in both).
- **Residual 3 — crash window between remote confirmation and local save —
  LOW.** The captured names exist only in the pull round-trip's stdout; a
  crash after confirmation (routstr_delist.py:682-688) but before
  routstr_delist.py:747-752 loses them irrecoverably (a later
  `SELECT … WHERE enabled=0` cannot distinguish pulled from
  operator-disabled rows). The 4b refusal guard (below) converts this from
  silent blanket-enable into an explicit `relist_refused` + operator
  `--relist-any` decision — acceptable, but the names are gone.
- **Residual 4 — no directory fsync after `os.replace` — LOW.** Post-crash
  durability of the rename itself is not guaranteed by POSIX without an
  fsync of the directory; practical risk is negligible on ext4 and this is
  pedantic, recorded for completeness.
- Remote-side atomicity unchanged and still holds: one connection, one
  UPDATE, one commit per payload (routstr_delist.py:364-397).

Must-fix (residuals): check `save_state()`'s return at all eight call sites
and exit non-zero on persist failure (Residual 1); add a lock file or
`fcntl.flock` around load/modify/save (Residual 2); add regressions for
both.

### 4b. Idempotence — repeat delist merges, blanket relist refused — **OK core / LOW residuals**

- **Fixed (pass-4 4b clobber hole):** a confirmed re-delist no longer
  clobbers `pulled_models`. The success path merges: `prior + [n for n in
  pulled if n not in prior]` (routstr_delist.py:744-749), so the re-delist's
  now-empty capture (nothing advertised — the pull SELECT at
  routstr_delist.py:371 returns `[]`) is absorbed. Pinned by unit
  `test_double_delist_merges_pulled_models` (tests:1017) and contract
  `test_forced_delist_on_absent_listing_is_idempotent_success`
  (contract:524-538, asserts `pulled_models` unchanged and breaker at 0).
- **Fixed (pass-4 4b blanket-relist hole):** `--relist` with no stored names
  now REFUSES — `relist_refused`, exit 1, zero remote calls
  (routstr_delist.py:600-611) — and the blanket `UPDATE models SET
  enabled=1` (routstr_delist.py:361) is reachable only via the explicit
  `--relist-any` operator opt-in (flag at routstr_delist.py:526-528; docs
  rule at docs:29-32). This closes the exact live-state hazard pass 4
  reported: the deployed state file still has no `pulled_models` key (read
  again this session), so a `--relist` today refuses instead of
  blanket-enabling operator-disabled rows. Pinned by unit
  `test_relist_refuses_blanket_without_opt_in` (tests:1039-1054) and the
  opt-in path by `test_relist_any_executes_blanket` (tests:1056-1067).
- **Fixed (pass-4 repeat-relist hole):** a successful relist pops
  `pulled_models` (routstr_delist.py:635), so a second `--relist` finds no
  names and takes the refusal path (exit 1) rather than the blanket path.
  The scoped relist itself is pinned in both suites (tests:622+,
  contract:490-507 — restores exactly ADVERTISED, never OPERATOR_DISABLED).
- Remote idempotence unchanged: `UPDATE models SET enabled=0 WHERE
  enabled=1` (routstr_delist.py:355) matches 0 rows on a repeat; the
  level-based variance re-fire is documented accepted semantics
  (routstr_delist.py:19-21, docs table :43) and its re-pull is a no-op
  whose empty capture now merges (4b bullet 1).
- **Residual 1 — no double-relist regression test — LOW.** The
  relist→relist sequence (success pops names → second run must refuse) is
  implemented (routstr_delist.py:635 + :601-611) but no test executes two
  consecutive `--relist` runs (grep for double/second/repeat: only the
  delist-merge test exists, tests:1017). Mutation-vulnerable: popping
  :635 would leave a stale `pulled_models` and the second relist would
  silently succeed scoped — low harm, but unpinned.
- **Residual 2 — the deployed (bot-path) suite never exercises the refusal
  paths — LOW.** The contract suite at `~/.hermes/bot/tests/` has ZERO
  occurrences of `relist_refused`/`relist_any` (grep this session: 0 hits);
  the refusal and opt-in behaviours are pinned only by the repo unit suite
  (tests:1039, tests:1056), which is NOT deployed to the bot path. A
  regression in routstr_delist.py:600-611 would pass all 25 bot-path tests.

**Verdict 4: MEDIUM** (down from HIGH). Both required properties are now
substantively implemented and pinned (atomic swap protocol; merge; refusal +
opt-in; remote UPDATE idempotence). Remaining exposure is the silent
persist-failure path, the absent inter-process lock, and two test-coverage
gaps — none of which can silently blanket-enable or tear state today.

## Finding 5 — 5-minute SLA arithmetic — **MEDIUM (wired and enforced in-run; boundary-tight and cadence not deployed)**

Per the original task's required breakdown, re-derived against the fixed
script:

- **Configured poll interval:** documented as cron `*/4` = 240 s
  (`POLL_CADENCE_S`, routstr_delist.py:72; crontab example docs:106). The
  docs SLA section (docs:91-114) now carries the full arithmetic matching
  the code. **Deployment status re-verified live this pass: `crontab -l`
  contains NO routstr_delist entry** (only the worker watchdog `*/3`) —
  the docs' own admission stands (docs:112). The cadence exists on paper
  only; until a crontab is wired the SLA is unoperational — carried here
  because the poll interval is a required breakdown item (full deployment
  gap remains finding 6's scope).
- **Polls/retries needed to confirm:** TWO in-run attempts
  (`MAX_PULL_ATTEMPTS = 2`, routstr_delist.py:75; loop
  routstr_delist.py:671-697), each attempt = pull + independent verify,
  and every round-trip is clamped to the remaining budget
  (routstr_delist.py:800-806: `timeout = min(SSH_TIMEOUT_S, remaining)`,
  with an immediate `action budget exhausted` return at
  routstr_delist.py:803-805 once the deadline passes). Both attempts count
  as ONE run for the circuit breaker (increment happens once at
  routstr_delist.py:724, outside the loop). Beyond the in-run pair, the
  next retry waits for the next cron tick.
- **Re-fetch round-trip:** now EXISTS (pass-4 gap closed): the read-only
  `SELECT COUNT(*) FROM models WHERE enabled=1` payload
  (routstr_delist.py:400-411), executed at routstr_delist.py:682, gated at
  routstr_delist.py:683 (`count == 0` required for `confirmed`). Success is
  no longer the pull's self-report; a lying pull is refuted and retried or
  failed (pinned: contract:346-360 with the `pull_lands=False` lying-pull
  rig; unit `test_no_retry_past_deadline` tests:450-463 pins the budget
  cap with `ACTION_BUDGET_S` patched to 0.001 → exactly one pull).
- **Action round-trip bound:** two-layer. Per round-trip
  `SSH_TIMEOUT_S = 30` (routstr_delist.py:74) via `subprocess.run(timeout=…)`
  (routstr_delist.py:808-809); across the run, the monotonic deadline
  `time.monotonic() + ACTION_BUDGET_S` (routstr_delist.py:667, and :612 for
  relist) caps TOTAL acting time at 60 s. The ssh argv still carries no
  `ConnectTimeout`/`BatchMode` (grep: zero hits; builder
  routstr_delist.py:414-425) — acceptable because the subprocess timeout
  clamp bounds a hung ssh at ≤ 30 s regardless. The optional nak publish
  (timeout 30, routstr_delist.py:459) runs AFTER confirmation
  (routstr_delist.py:755-756), outside the deadline and outside the
  SLA-critical path: it inflates total job duration to ≤ 90 s but not the
  trigger→confirmed-delist time.
- **Worst-case detection → confirmed delist:** trigger just after a tick →
  detection ≤ 240 s + in-run evaluation ~0 s + pull ≤ 30 s + verify ≤ 30 s
  = **≤ 300 s = exactly `TRIGGER_ACTION_WINDOW_S`** — the SLA now holds BY
  CONSTRUCTION under the documented `*/4` cadence, where pass 4 measured
  360 s worst case under `*/5` with a 60 s unbounded ssh. Pinned
  behaviourally by the fake-clock end-to-end test
  `test_trigger_sample_to_verified_delist_under_300s` (contract:553-577:
  25 s round-trips → confirmed at t=290 < 300, deadline log shows every
  round-trip clamped ≤ SSH_TIMEOUT_S and ≤ ACTION_BUDGET_S) and the config
  identities (contract:543-551, unit tests:421-431:
  `POLL_CADENCE_S + ACTION_BUDGET_S == TRIGGER_ACTION_WINDOW_S`,
  `2*SSH_TIMEOUT_S <= ACTION_BUDGET_S`).
- **Residual 1 — boundary-tight, zero slack — MEDIUM.** The identities hold
  with EQUALITY: 240 + (30 + 30) = 300 with zero margin for cron scheduling
  jitter, process start, trigger evaluation, or the post-confirmation state
  write (routstr_delist.py:747-752) before the durable flag exists. Any
  overshoot of the assumed exactly-240 s cadence breaches the window; pass
  4's must-fix itself noted `*/4` was "still boundary" and suggested `*/2`.
  The pass-4 dead-constant problem is gone (`TRIGGER_ACTION_WINDOW_S`
  feeds `ACTION_BUDGET_S` at routstr_delist.py:73 and the deadline at
  :667), but the margin problem persists by choice.
- **Residual 2 — the in-run retry cannot absorb a slow failure — LOW.** A
  first attempt that burns its full timeouts (30 + 30 = 60 s) exhausts the
  budget, so attempt 2 short-circuits at routstr_delist.py:803-805; the
  "bounded in-run retry absorbs a transient ssh blip"
  (routstr_delist.py:664-665) is true only for FAST failures (connection
  refused ≈ instant). A slow-timeout first attempt still waits for the next
  cron tick (worst case with one such failed run: 240 + 60 + 240 + 60 =
  600 s). Disclosed by the comment at routstr_delist.py:74; pinned as
  intended by tests:450-463.
- **Residual 3 — cadence assumption unverified by enforcement — LOW.**
  Nothing at runtime checks that the actual cron interval equals
  `POLL_CADENCE_S` (e.g. comparing consecutive state `ts` deltas); the
  arithmetic is only as good as the unwired crontab (breakdown item 1).

**Verdict 5: MEDIUM** (down from HIGH). The SLA is now real code: a monotonic
action budget clamps every round-trip, success requires an independent
re-fetch, retries are bounded, and the docs carry matching `*/4` arithmetic
pinned by fake-clock and config-identity tests in both suites. It does NOT
yet hold operationally: no crontab entry exists (verified live), and the
240+60 split consumes the entire 300 s window with zero slack. To finish:
wire the `*/4` (or `*/2`) crontab, and either drop `SSH_TIMEOUT_S` or shrink
`POLL_CADENCE_S` to buy margin.

---

Provenance: fifth offload pass. Pass 4 (2026-09-17, this file's prior
content, preserved in repo history) graded 4 HIGH / 5 HIGH against the
pre-fix script; the round-2 fix commits `b879354` + `1c77910` landed between
passes. This pass re-derived every claim independently against the current
artifacts: script read end-to-end in both copies (byte-diff clean, 829
lines), bot-path contract suite read end-to-end (752 lines), repo unit suite
swept (96 tests), both docs copies read and diffed (bot copy 14 lines
stale), greps re-run (save_state call sites, lock primitives, ssh options,
refusal keywords, SLA constant uses), live state file and crontab read, and
all three suites executed green (96 + 25 + 25). `~/.hermes/bot` is not a git
repository (re-verified), so the required local commit lands in the
workspace repo (merchant-routing) at `docs/reviews/findings_4_5.md`, with
this identical copy at the task-mandated bot path
`~/.hermes/bot/docs/reviews/findings_4_5.md`.
