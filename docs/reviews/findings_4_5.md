# Offload review — routstr delist, findings 4–5 (atomicity/idempotence, SLA)

Independent re-derivation, this session (17th offload pass), of item **4
(atomicity + idempotence)** and item **5 (5-minute SLA arithmetic)** as
specified in the original task (`docs/reviews/routstr_delist_review.md:158`
and `:196`). Every `file:line` below was re-read this session and every
behavioural claim re-executed against the CURRENT artifact set. Nothing is
carried over from an earlier pass.

**Artifact-path status (required report).**
- `~/.hermes/bot/docs/routstr_delist_contract.md` — **MISSING — HIGH.** The
  exact path named in the task does not exist (`ls` → ENOENT this session);
  `~/.hermes/bot/docs/` contains only `routstr-delist.md` and `reviews/`. The
  mandated contract document is therefore unreviewable. The contract/design
  stand-in actually reviewed is `~/.hermes/bot/docs/routstr-delist.md` — 197
  lines, md5 `e385af98b9c142eec736672d4dcca290`, byte-identical to repo
  `docs/routstr-delist.md` (equal md5) — cited below as `docs:N`.
- `~/.hermes/bot/scripts/routstr_delist.py` — exists, **829 lines**, read
  end-to-end, md5 `2ea724ef08d857cd7b88a957300e70b4`, byte-identical to repo
  `src/routstr_delist.py` — cited as `routstr_delist.py:N`.
- `~/.hermes/bot/tests/test_routstr_delist.py` — exists, **752 lines**, read
  end-to-end, md5 `031851b356f0de4089512f02f13f05cc`, byte-identical to repo
  `tests/test_routstr_delist_contract.py` — cited as `contract:N`. Its loader
  fallback (`contract:47-54`) resolves `../scripts` when there is no
  `../src/routstr_delist.py`, so the deployed suite exercises the deployed
  script. The repo unit suite `tests/test_routstr_delist.py` (1172 lines) is
  cited as `unit:N`.
- **No artifact was modified.** All hashes above were re-checked after every
  probe and are unchanged; only this review document and its probe script were
  authored.

**Executed this session (read-only, no artifact touched).**
- repo `python3 -m pytest tests/test_routstr_delist.py
  tests/test_routstr_delist_contract.py -q` → **121 passed** (0.91 s).
- deployed `cd ~/.hermes/bot && python3 -m pytest tests/test_routstr_delist.py
  -q` → **25 passed** (0.42 s).
- hermetic probe
  `docs/reviews/routstr_f45_probes/probe_f45_pass17.py` drives the DEPLOYED
  script in-process (fake backend, tempdir state, no network, real `rd.main()`
  and the real `_SshBackend._run`) → **21/21 probes PASS**, exit 0. Raw probe
  lines are quoted per-item below.
- static/AST checks: lock primitives
  (`flock|fcntl|lockf|O_EXCL|threading|multiprocessing`) = **0 hits**;
  `os.open|O_DIRECTORY` = **0 hits**; AST count of bare `save_state(...)`
  expression statements = **8** (`routstr_delist.py` lines
  565,622,629,638,654,710,732,752), return discarded at all 8; `crontab -l` =
  **zero routstr entries**; live `~/.hermes/bot/routstr_delist_state.json` =
  keys `delisted`(true), `last_dry_run`, `last_reason`, `snapshot`({}), `ts` —
  **no `pulled_models`, no `consecutive_failures`, no `blocked`**.

## Finding 4 — Atomicity and idempotence — **MEDIUM**

The original finding-4 defect (`docs/reviews/routstr_delist_review.md:158-194`)
is resolved on both counts: the state write is now atomic
(`routstr_delist.py:221-245`) and both idempotence defects are fixed (merge on
re-delist, refuse the blanket relist). The residual that keeps this finding at
MEDIUM is a durability/observability one: a failed persist is reported to the
caller as success, and the breaker's durable marker is the specific thing that
goes missing.

**4.1 — Atomic state write protocol — implemented and behaviourally pinned — OK.**
`save_state()` (`routstr_delist.py:221-245`) writes a same-directory tmp
`.{basename}.{pid}.tmp` (`:230`), `json.dump` (`:232`) + `flush()` (`:233`) +
`os.fsync()` (`:234`), then `os.replace()` (`:235`); success `return True`
(`:237`), any exception `return False` (`:238-239`), `finally` unlinks the tmp
on failure (`:240-245`). A concurrent reader can only observe old-or-new, never
a torn file. Pinned by `TestAtomicStateWrites` (`contract:628-686`), which
spies on `os.replace` and asserts the destination still holds the whole
previous state and the tmp the whole new state at swap time
(`contract:636-663`), and that a destination `os.replace` raising leaves the
previous state loadable and litter-free (`contract:665-686`). Probes
`4a_save_state_ok` → `ret=True fsync_calls=1 replace=1 litter=[]`;
`4a2_save_state_false_on_error` → `ret=False state_unchanged=True litter=[]`.
This resolves the original "plain `open(path,"w")`, no tmp/replace/fsync"
complaint.

**4.2 — `save_state()` failure is silent: a failed persist is reported as success — MEDIUM.**
`save_state()` returns `True`/`False` (`:237`/`:238-239`) but **all eight call
sites discard the return value** (`routstr_delist.py:565,:622,:629,:638,:654,
:710,:732,:752`; AST-confirmed this session as bare expression statements) and
`main()` never inspects it. A persist failure (ENOSPC, EROFS, permission,
rename failure) therefore yields a run that prints `"action":"delist"`,
`"ok":true`, `"confirmed":true` and exits **0** while the durable state on disk
is stale. Probe `4b_silent_persist_failure` (pre-existing state seeded
`delisted:false`, `snapshot:{zai:10.0}`, `consecutive_failures:2`; forced
`os.replace` failure on the state path) → `rc=0 action=delist confirmed=True
state_on_disk={'ts': 1, 'delisted': False, 'snapshot': {'zai\x1f1h': 10.0},
'consecutive_failures': 2}` — the file is bit-for-bit the pre-run state. Because
the "flag in the objects that publishes the listing" IS the persisted
`delisted` field (`routstr_delist.py:248-253`/`:263`, `docs:122-123`), the
advertisement flag the design depends on is never flipped; `--status`
(`:548-557`) then re-reads the stale value and cron sees exit 0 — the failure
is invisible. Neither suite asserts that `main()` surfaces a `save_state`
failure: the only return-value assertions live inside `TestAtomicStateWrites`
(`contract:643,:657,:682`) and the unit-suite hits (`unit:256,273-296`) call
`save_state` directly, never through `main()`. Must-fix: have the 8 call sites
check the return and exit non-zero (or at least warn) when a
delist/relist/breaker transition fails to persist. This contradicts
`docs:64-68` ("a failed pull … exits non-zero so cron/monitoring sees it") in
the persist-failure case.

**4.3 — The durable BLOCKED marker is never written when persists fail, yet exit 3 still fires — MEDIUM.**
The sharpest consequence of 4.2, isolated this session. The counter is read
from disk (`:544`) and written by a discarded-return `save_state` (`:732`);
`newly_blocked = fails >= BREAKER_THRESHOLD` (`:730`) is derived in memory and
`return 3 if newly_blocked else 1` (`:739`) fires from it. So with persists
failing: every run emits **exit 3 / `"blocked":true`** in its JSON, while the
durable marker `state["blocked"] = True` (`:731`) never lands. Probe
`4b3_persist_failure_freezes_breaker` (seeded `consecutive_failures:2`,
`blocked:false`; 4 forced-failure delist runs) →
`rcs=[3, 3, 3, 3] disk_consecutive_failures=2 disk_blocked=False`. Two
distinct harms: (a) `docs:76-79`'s "`blocked: true` (**durable**)" and
`contract:593-596`'s `'"blocked": true' in raw` are both violated — the marker
lives only in the process; (b) no `--unblock` is possible while the marker is
absent, and the operator's only durable signal (`--status`) says the breaker is
closed. Restart-from-disk never converges. Probe `4b3` is the reason this
finding is MEDIUM rather than LOW.

**4.4 — No inter-process lock around the read-modify-write of the state file — LOW.**
Grep `flock|fcntl|lockf|O_EXCL|threading|multiprocessing` over the script =
**0 hits** (re-run this session). Each run does `load_state` (`:543`) then one
or more whole-dict writes; two overlapping cron invocations (a run parked in
an ssh round-trip when the next tick fires) each write last-writer-wins, so a
concurrent relist and delist can lose an update. `os.replace` guarantees each
individual write is atomic, not that the read-modify-write is serialised.
Probe `4g_interleaved_lost_update` (two interleaved `load_state` → mutate →
`save_state` sequences on one path, mimicking two runs) →
`final={'delisted': False, 'ts': 2}` — run A's `delisted=True` +
`pulled_models` update is silently clobbered by run B. Impact is bounded (the
remote actions are idempotent; the `*/4` cadence with short runs makes overlap
unlikely), but the original "no locking … last writer wins" remnant holds.

**4.5 — Directory entry not fsynced: the rename is atomic but not crash-durable — LOW.**
`save_state` fsyncs the tmp file (`routstr_delist.py:234`) but never opens or
fsyncs the containing directory after `os.replace` (`:235`) — grep for
`os.open|O_DIRECTORY` in the script = **0 hits** (re-run this session). Probe
`4h_no_directory_fsync` → `os_open_or_O_DIRECTORY_hits=0 fsync_calls=1
dir_opens=0`. A power loss immediately after the swap can therefore lose the
directory entry even though the data blocks were flushed, leaving the previous
state. Reader-visible atomicity is intact; only crash-durability of the rename
is unbounded. Related documentation defect (also LOW): `contract:252-256`
claims "fsync durability is behaviourally pinned by Case 10's
TestAtomicStateWrites (real fsync, no rig)" — inaccurate, because Case 10's own
autouse fixture (`contract:629-634`) replaces `os.fsync` with a no-op exactly
as the rig does (`contract:257`). Confirmed this session: probe `5f` observes a
real `os.fsync` call (`local_fsync_calls=1`) only when the test rig is NOT in
play — so no test anywhere exercises the real fsync path, and the fsync is
additionally the un-clamped local cost noted at 5.5.

**4.6 — Idempotence: re-delist MERGES `pulled_models`, never clobbers — OK.**
The original defect (a second level-based delist overwrote `pulled_models`
with the now-empty capture, arming a blanket relist) is fixed:
`routstr_delist.py:744-749` computes `prior` (`:744`), `pulled` (`:745`) and
`merged = list(prior) + [n for n in pulled if n not in prior]` (`:746`) before
persisting via `update_state(...extra={"pulled_models": merged})` (`:747-749`).
Probe `4c_redelist_merge` (state seeded `pulled_models=["m1","m2"]`, `--delist`
against a node advertising nothing) → `rc=0 pulled=[] pulled_models=['m1',
'm2']`. Pinned by `test_forced_delist_on_absent_listing_is_idempotent_success`
(`contract:524-538`, assertion `st["pulled_models"] == st_before["pulled_models"]`
at `:537`) and `unit:1017-1031`. A forced re-delist on an already-absent
listing is an idempotent success.

**4.7 — Idempotence: no-names relist REFUSES the blanket enable — OK.**
`routstr_delist.py:600-611`: with no stored `pulled_models` (`:601`) and no
explicit `--relist-any` (`:602`), `--relist` prints `relist_refused` and exits
1 (`:611`) **before any remote round-trip** (the `relist(...)` call is at
`:613`). Probe `4d_relist_refused` → `rc=1 action=relist_refused calls=[]`
(zero backend calls). The scoped relist restores only the captured names via
the parameterized payload (`routstr_delist.py:390-397`, `contract:490-507`,
`out["restored"] == len(ADVERTISED)` at `contract:499`). Residual asymmetry
(LOW): the live deployed state (`delisted:true`, **no** `pulled_models`) would
be refused rather than no-op'd — the safe direction, at the cost that an
operator must pass `--relist-any`, the intended explicit opt-in (`docs:29-32`).
This resolves the "blanket `UPDATE models SET enabled=1` arms operator-disabled
rows" complaint.

**4.8 — Idempotence: a FAILED relist does not tick the breaker — LOW.**
Failure handling is asymmetric. A failed **delist** increments
`consecutive_failures` (`routstr_delist.py:724`) and can trip the breaker
(`:730-731`); a failed **relist** (`:626-632`) only records `last_pull_error`
(`:628`) and exits 1 (`:632`) — it never increments the counter, while a
successful relist resets it (`:636-637`). Probe
`4e_failed_relist_no_breaker_tick` (seed `consecutive_failures=2`, failing
relist backend) → `rc=1 action=relist_failed consecutive_failures=2
blocked=None`. A persistently failing relist can loop forever without the
breaker opening, though `docs:76-79` describes the breaker over "failed runs"
generically. Residual LOW (delisting is the safety-critical direction, which IS
counted).

**4.9 — Idempotence: bool counter hole at the breaker read — LOW.**
`fails = state.get("consecutive_failures", 0)` then
`fails if isinstance(fails, int) else 0` (`routstr_delist.py:544-545`). `bool`
is an `int` subclass, so a hand-edited `"consecutive_failures": true` is
accepted as 1 (contrast the explicit bool exclusion in `variance_jumped`,
`routstr_delist.py:152`) and a following failure yields 2. Probe
`4f_bool_counter_hole` (seed JSON `true`, failing delist) →
`rc=1 consecutive_failures=2`. Cosmetic; requires a corrupted/edited state
file.

**4.10 — Breaker holds for the event path too — OK, but the contract test cannot see it — LOW.**
The `blocked` branch (`routstr_delist.py:569-578`) returns 3 before the
`--nsec` publish (`:754-756`), so a blocked run spawns neither an API
round-trip nor a nak process. Probe `4i_blocked_refuses_publish_too` →
`rc=3 action=blocked api_calls=[] nak_publishes=0` — behaviour is correct for
both halves of "refuses ALL remote action". The gap is in the guard, not the
code: `test_blocked_run_refuses_all_remote_action` (`contract:601-612`) asserts
only on `rig.node.calls` (`FakeSellNode`), and `FakeSellNode` never records
the nak subprocess, so a future regression that moved the publish above the
breaker would leave that test green. Residual LOW (test-coverage gap, no live
defect).

## Finding 5 — 5-minute SLA arithmetic — **OK**

The original finding-5 complaint (`docs/reviews/routstr_delist_review.md:196-234`)
is resolved: `TRIGGER_ACTION_WINDOW_S` is no longer a dead constant — it is
consumed to derive `ACTION_BUDGET_S` (`routstr_delist.py:73`) and every remote
round-trip is deadline-clamped (`:800-806`). The arithmetic holds and is
enforced in-run. The cadence half is documentary only, the margin is zero, and
the retry is structurally opportunistic — all LOW residuals, detailed below.

**5.1 — The constants are non-decorative and internally consistent — OK.**
`TRIGGER_ACTION_WINDOW_S = 300` (`routstr_delist.py:71`), `POLL_CADENCE_S =
240` (`:72`), `ACTION_BUDGET_S = TRIGGER_ACTION_WINDOW_S - POLL_CADENCE_S = 60`
(`:73`), `SSH_TIMEOUT_S = 30` (`:74`), `MAX_PULL_ATTEMPTS = 2` (`:75`). Probe
`5a_constants_arithmetic` → `window=300 cadence=240 budget=60 ssh=30
max_attempts=2` (240+60==300, 2*30<=60). The original core complaint (the
window constant was read only by docstring/doc/tests) is resolved: the budget
is consumed at `routstr_delist.py:612` (relist) and `:667` (delist) to arm a
`time.monotonic() + ACTION_BUDGET_S` deadline, and `_SshBackend._run` clamps
every remote round-trip to `min(SSH_TIMEOUT_S, remaining)` (`:800-806`),
refusing with `"action budget exhausted"` **without spawning** when
`remaining <= 0` (`:803-805`). Arithmetic pinned by
`test_poll_cadence_config_satisfies_the_window` (`contract:543-551`).

**5.2 — Every remote round-trip is deadline-clamped; the whole action fits the budget — OK.**
Because the timeout is `min(30, remaining)` with a pre-flight `remaining <= 0`
refusal, a fired run can spend at most `ACTION_BUDGET_S = 60 s` acting **by
construction**. Probe `5b_budget_exhausted_no_spawn` (expired deadline, real
`_SshBackend._run` with a stubbed `subprocess.run`) → `res={'ok': False,
'action': 'pull', 'error': 'action budget exhausted'}
spawns_after_expired=0 live_clamped_timeout=0.999995742997271` — the expired
call spawned nothing and the live call was clamped to the ~1 s remaining, not
30. Probe `5b2_no_deadline_timeout` → `timeouts=[30]`, i.e. the no-deadline
path still bounds each round-trip at `SSH_TIMEOUT_S == 30`. The observable
happy path is pinned by `test_trigger_sample_to_verified_delist_under_300s`
(`contract:553-577`): a full poll cadence is charged, each pull/verify costs
25 s, and the verified delist (240 + 50 = 290 s) completes < 300 s with every
logged `timeout <= SSH_TIMEOUT_S and <= ACTION_BUDGET_S` (`contract:574-577`).

**5.3 — Worst-case detection + action ≤ 300 s, but the equality is exactly at the */4 cadence — OK (zero-margin boundary, residual LOW).**
The model is detection ≤ `POLL_CADENCE_S` (one full tick) + action ≤
`ACTION_BUDGET_S` (60). Probe `5c_cadence_arithmetic`: with `*/4` (240 s) the
worst case is `240 + 60 = 300 s` — **exactly** the contract, not a strict
margin (`slack */4=0s`); with `*/5` (300 s) it is `360 s > 300 s` (`slack
*/5=-60s`) and breaches; with `*/2` (120 s) it is 180 s (`slack */2=120s`).
The script never self-imposes the cadence (it is a one-shot CLI), so the bound
holds only under the documented `*/4` deployment (`docs:96`, `docs:100`,
`docs:106` example crontab — changed from `*/5`). This is the boundary the
original finding exposed; it is now documented as `*/4` rather than `*/5`, but
the margin is zero — any per-run local overhead beyond the clamped remote calls
erodes it (see 5.5).

**5.4 — The cadence half is documentary only: no crontab entry enforces it — LOW.**
`crontab -l` contains **zero** routstr entries this session (grep rc=1), and
`docs:112-115` states the runner is not wired yet. So while the in-run
arithmetic is enforced by code, the "≤ 5 min from trigger" property in
production depends entirely on an operator wiring `*/4` (or faster); nothing
pins the actual cadence to `POLL_CADENCE_S`. A `*/5` wiring (the cadence the
original finding assumed) would silently reintroduce the 360 s breach in 5.3.
Residual LOW for this finding (the deployment gap itself is finding 6's remit).

**5.5 — Local work is outside the deadline: the un-clamped `fsync` can blow the zero margin — LOW.**
`save_state` is called on every path (`routstr_delist.py:565,:622,:629,:638,
:654,:710,:732,:752`) and its `os.fsync` (`:234`) is a real, un-clamped
synchronous disk operation — the deadline at `:667` bounds only
`_SshBackend._run` round-trips (`:800-806`). Probe `5f_local_fsync_unclamped`
(run with a real `os.fsync`, no stub) → `rc=0 action=delist
local_fsync_calls=1`. The atomicity rigs document the pathology that makes this
material: "this fleet host's disk can stall indefinitely inside fsync"
(`contract:252-254`), which is why both the rig (`contract:257`) and Case 10
(`contract:629-634`) stub `os.fsync` out. With `docs:100-103`'s arithmetic at
exactly 300 s and zero margin (5.3), any local stall — `fsync`, interpreter
startup, `evaluate_triggers` over a large feed — is spent from the same budget
and is unaccounted for by the clamp. Not demonstrable as a breach here (the
fsync is stubbed in every test precisely because it hangs on this host), so
this is a residual observation rather than a reproduced defect.

**5.6 — `--nsec` publish runs after the success path and is not inside the deadline — LOW.**
The best-effort kind-30078 publish (`routstr_delist.py:754-756`,
`publish_delist_event` `:451-464`) runs after the confirmed delist and its
`save_state` (`:752`), outside the action deadline; its own
`subprocess.run(..., timeout=30)` (`:459`) is not budget-clamped. Probe
`5d_publish_timeout_unclamped` (confirmed delist with `--nsec`, stubbed
`subprocess.run`) → `rc=0 confirmed=True publish_timeouts=[30] budget=60`,
i.e. the publish carries the full 30 s constant (not the remaining budget)
after `confirmed` is already true. In the worst case a fired run spends an
extra up-to-30 s after the verified delist prints. This does not breach the
≤ 300 s detection-to-confirmed property (confirmation already happened), but
combined with the zero margin in 5.3 it is the residual that most deserves a
note.

**5.7 — The bounded in-run retry is opportunistic, not guaranteed — LOW.**
Both retry guards include `time.monotonic() < deadline`
(`routstr_delist.py:675-677`, `:695-696`), and a single worst-behaved attempt
can consume the entire budget: a LYING pull (self-reports ok, forcing a
verify) costs pull 30 s + verify 30 s = 60 s. Probe `5e_worst_case_eats_retry`
(fake monotonic clock; lying pull + verifying node) → `rc=1
calls=['pull', 'verify'] elapsed=60.0s budget=60s` — the guard is false
afterwards and the retry is refused. Probe `5g_inrun_retry_bounded` (plain 30 s
failing pull) → `rc=1 calls=['pull', 'pull'] one_deadline=True attempts=2
elapsed=60.0`, so the retry does fit when the first attempt leaves room, and
when the retry does fire it stays inside the single deadline armed at `:667`.
Net: `MAX_PULL_ATTEMPTS` only absorbs blips that arrive early in the budget —
exactly the safe direction, but it means the constant is structurally inert in
the worst case.
