# Offload review — routstr delist, findings 4–5 (atomicity/idempotence, SLA)

Independent re-derivation, this session, of item **4 (atomicity + idempotence)**
and item **5 (5-minute SLA arithmetic)** as specified in the original task
(`docs/reviews/routstr_delist_review.md:158` and `:196` — the two REFUTED (HIGH)
findings and their must-fix lists). Nothing below is carried over from an
earlier pass; every file:line reference was re-read this session and every
behavioural claim re-executed against the CURRENT artifact set.

**Artifact-path status (required report).**
- `~/.hermes/bot/docs/routstr_delist_contract.md` — **MISSING — HIGH.** The exact
  path named in the task does not exist. `~/.hermes/bot/docs/` contains only
  `routstr-delist.md` and `reviews/`, and a recursive search for any
  `*contract*` artifact under `~/.hermes/bot` returns the empty set (only the
  python bytecode/test name `tests/test_routstr_delist.py` matches, no `.md`).
  The mandated contract document is therefore unreviewable; the design/contract
  stand-in actually reviewed is `~/.hermes/bot/docs/routstr-delist.md` — 197
  lines, md5 `e385af98b9c142eec736672d4dcca290`, byte-identical to repo
  `docs/routstr-delist.md` — cited below as `docs:N`.
- `~/.hermes/bot/scripts/routstr_delist.py` — exists, 829 lines, read
  end-to-end, md5 `2ea724ef08d857cd7b88a957300e70b4` = repo `src/routstr_delist.py`
  (byte-identical), cited below as `routstr_delist.py:N`.
- `~/.hermes/bot/tests/test_routstr_delist.py` — exists, 752 lines, read
  end-to-end, md5 `031851b356f0de4089512f02f13f05cc` = repo
  `tests/test_routstr_delist_contract.py` (byte-identical), cited below as
  `contract:N`. Its loader fallback (`contract:47-54`) resolves `../scripts`, so
  the deployed suite tests the deployed script. The repo unit suite
  (`tests/test_routstr_delist.py`, 1172 lines, md5 `293b0459b636a918cf1cce57bf922473`)
  is cited as `unit:N`.

**Executed this session (read-only; no artifact modified):**
- repo `python3 -m pytest tests/test_routstr_delist.py tests/test_routstr_delist_contract.py -q`
  → **121 passed** (1.75 s).
- deployed `cd ~/.hermes/bot && python3 -m pytest tests/test_routstr_delist.py -q`
  → **25 passed** (0.97 s).
- hermetic probe `~/worktrees/f45-probe-pass12/probe_f45.py` — drives the
  DEPLOYED `rd.main()` / `rd._SshBackend._run` in-process with a fake backend,
  tempdir state only, no network, no subprocess, no artifact touched →
  **13/13 probes PASS** (4a, 4a2, 4b, 4b2, 4c, 4d, 4e, 4f, 5a, 5b, 5b2, 5c, 5d).
- greps: lock primitives (`flock|fcntl|lockf|O_EXCL|threading|multiprocessing`)
  in the script = **0 hits**; `save_state(` = 1 def (`:221`) + **8 bare call
  sites** (`:565,:622,:629,:638,:654,:710,:732,:752`), return value discarded at
  all 8; `os.replace|fsync|tempfile` only at `:234/:235`; `crontab -l` =
  **zero routstr entries**; live `~/.hermes/bot/routstr_delist_state.json` keys
  = `delisted`(true), `last_dry_run`, `last_reason`, `snapshot`({}), `ts` —
  **no `pulled_models`, no `consecutive_failures`/`blocked`**.

## Finding 4 — Atomicity and idempotence — **MEDIUM** (both original must-fixes implemented; one MEDIUM durability residual)

**4.1 — Atomic state write protocol — implemented and behaviourally pinned — OK.**
`save_state()` (`routstr_delist.py:221-245`) writes a same-directory tmp file
`.{basename}.{pid}.tmp` (`:230`), `json.dump` + `flush()` + `os.fsync()`
(`:232-234`), then `os.replace()` (`:235`); the `finally` unlinks the tmp on any
error (`:240-245`), and the function returns `True`/`False` (`:237`/`:238-239`).
A concurrent reader can only observe old-or-new, never a torn file. Pinned by
`TestAtomicStateWrites` (`contract:628-686`), which spies on `os.replace` and
asserts the destination still holds the whole previous state and the tmp holds
the whole new state at swap time (`contract:636-663`), and that a crash
(destination `os.replace` raising) leaves the previous state loadable and
litter-free (`contract:665-686`). Probe `4a_save_state_ok` confirms the swap
succeeds with no `.tmp` litter; `4a2_save_state_false_on_error` confirms a
failing `os.replace` makes `save_state` return `False` and leaves the tmp
cleaned up.

**4.2 — `save_state()` failure is silent: a failed persist is reported as success — MEDIUM.**
`save_state()` returns `True`/`False` (`:237`/`:238-239`), but **all eight call
sites discard the return value** (`grep` verified: `:565,:622,:629,:638,:654,
:710,:732,:752`); `main()` never checks it. A persist failure (ENOSPC, EROFS,
permission, the destination rename failing) therefore yields a run that prints
`"action":"delist"`, `"ok":true`, `"confirmed":true` and exits **0**, while the
durable state on disk is unchanged. Probe `4b_silent_persist_failure`
reproduced exactly this with `os.replace` forced to raise: rc=0, action=delist,
confirmed=true, `state_on_disk={"delisted": false, "ts": 1}` (stale). Because
the "flag in the objects that publishes the listing" IS the persisted
`delisted` field (`routstr_delist.py:248-253`, `docs:122-123`), a silent persist
failure means the advertisement flag the design depends on is never flipped,
`--status` (`:549-556`) reports the stale value (probe `4b2_status_reads_stale`:
`delisted=false`), and cron sees exit 0 — the failure is invisible. Neither the
deployed suite nor the unit suite asserts that `main()` surfaces a `save_state`
failure (the only return-value assertions live inside `TestAtomicStateWrites`,
`contract:643/:657/:682`). Must-fix: have the 8 call sites check the return and
exit non-zero (or at least emit a warning) on a failed persist of a
delist/relist/breaker transition.

**4.3 — No inter-process lock around the read-modify-write of the state file — LOW.**
The script has **zero** lock primitives (grep `flock|fcntl|lockf|O_EXCL|
threading|multiprocessing` = 0 hits). Each run does `load_state` (`:543`) then
one or more `save_state` writes; two overlapping cron invocations (a run that
hangs inside an ssh round-trip while the next tick fires) each write the whole
dict last-writer-wins, so a concurrent relist and delist can lose an update.
`os.replace` guarantees each individual write is atomic but not that the
read-modify-write is serialised. Impact is bounded (the remote actions are
themselves idempotent, and the `*/4` cadence with short runs makes overlap
unlikely), but the original finding's "no locking … last writer wins" remnant
is still true. Residual LOW.

**4.4 — Directory entry not fsynced: the rename is atomic but not durable — LOW.**
`save_state` fsyncs the tmp file (`:234`) but never fsyncs the containing
directory after `os.replace` (`:235`). A power loss immediately after the swap
can lose the directory entry even though the data blocks were flushed, leaving
the previous state. Atomicity (reader-visible) is intact; only crash-durability
of the rename is unbounded. Residual LOW (and unassertable in-process, which
`contract:629-634` documents). Also note the rig globally stubs `os.fsync`
(`contract:257`), so no test exercises the real fsync call path.

**4.5 — Idempotence: re-delist MERGES `pulled_models`, never clobbers — OK (fixed).**
The original finding 4 defect (a second level-based delist overwrote
`pulled_models` with the now-empty capture, arming a blanket relist) is fixed:
`routstr_delist.py:744-749` merges `prior + new` before persisting. Probe
`4c_redelist_merge` seeds `pulled_models=["m1","m2"]`, runs `--delist` against a
node advertising nothing, and the stored `pulled_models` survives as
`["m1","m2"]`. Pinned by `test_forced_delist_on_absent_listing_is_idempotent_success`
(`contract:524-538`, assertion `st["pulled_models"] == st_before["pulled_models"]`
at `:537`) and `unit:1017-1031`. A forced re-delist on an already-absent
listing is therefore an idempotent success (`contract:524-538`). Symmetric
read-only: `test_already_delisted_quiet_run_is_a_noop` (`contract:512-522`).

**4.6 — Idempotence: no-names relist REFUSES the blanket enable — OK (fixed).**
`routstr_delist.py:600-611`: with no stored `pulled_models` and no explicit
`--relist-any`, `--relist` prints `relist_refused` and exits 1 **before any
remote round-trip**. Probe `4d_relist_refused` produced rc=1, action
`relist_refused`, 0 backend calls. The scoped relist restores only the captured
names (`:390-397`; `contract:490-507`). Residual asymmetry: the live deployed
state (`delisted:true`, **no** `pulled_models`, verified this session) would be
refused rather than no-op'd, which is the safe direction but means an operator
must pass `--relist-any` — the intended explicit opt-in (`docs:29-32`).

**4.7 — Idempotence: a FAILED relist does not tick the breaker — LOW.**
Failure handling is asymmetric. A failed **delist** increments
`consecutive_failures` and can trip the breaker (`:724-731`); a failed
**relist** (`:626-632`) only records `last_pull_error` and exits 1 — it never
increments the counter, and a successful relist resets it (`:636-637`). Probe
`4e_failed_relist_no_breaker_tick` seeds `consecutive_failures=2` with a failing
relist backend: rc=1 and the stored counter is still 2. So a persistently
failing relist can loop forever without the breaker opening, and a relist that
fails is not counted even though `docs:76-79` describes the breaker over "failed
runs" generically. Residual LOW (delisting is the safety-critical direction,
which IS counted).

**4.8 — Idempotence: bool counter hole at the breaker read — LOW.**
`fails = state.get("consecutive_failures", 0)` then `fails if isinstance(fails,
int) else 0` (`:544-545`). `bool` is an `int` subclass, so a hand-edited
`"consecutive_failures": true` is accepted as 1 and a following failure yields
2. Probe `4f_bool_counter_hole` (seed `true`, failing delist) → stored
`consecutive_failures=2`, rc=1. Cosmetic, requires a corrupted/edited state
file. Residual LOW.

## Finding 5 — 5-minute SLA arithmetic — **OK** (arithmetic holds and is enforced in-run; cadence half is documentary only — residual LOW)

**5.1 — The constants are now non-decorative and internally consistent — OK.**
`TRIGGER_ACTION_WINDOW_S = 300` (`:71`), `POLL_CADENCE_S = 240` (`:72`),
`ACTION_BUDGET_S = TRIGGER_ACTION_WINDOW_S - POLL_CADENCE_S = 60` (`:73`),
`SSH_TIMEOUT_S = 30` (`:74`), `MAX_PULL_ATTEMPTS = 2` (`:75`). Probe
`5a_constants_arithmetic` confirms `240 + 60 == 300` and `2*30 == 60 <= 60`.
The original finding's core complaint — `TRIGGER_ACTION_WINDOW_S` was a dead
constant read only by docstring/doc/tests — is resolved: the budget is consumed
at `routstr_delist.py:612` (relist) and `:667` (delist) to arm a
`time.monotonic()` deadline, and `_SshBackend._run` clamps every remote
round-trip to `min(SSH_TIMEOUT_S, remaining)` (`:800-806`), returning
`"action budget exhausted"` (without spawning) when `remaining <= 0`
(`:803-805`). Arithmetic pinned by `test_poll_cadence_config_satisfies_the_window`
(`contract:543-551`).

**5.2 — Every remote round-trip is deadline-clamped; the whole action fits the budget — OK.**
Because the timeout is `min(30, remaining)` and a pre-flight `remaining <= 0`
refuses the call, the fired run can spend at most `ACTION_BUDGET_S = 60 s`
acting **by construction** — the bounded in-run retry (`:671-697`, guard at
`:675-677`/`:695-696`) cannot push past it: the second attempt is refused once
the budget is gone. Probe `5b_budget_exhausted_no_spawn` drives
`_SshBackend._run` with an expired deadline and gets
`{"ok": false, "error": "action budget exhausted"}` with **zero** subprocess
spawns; probe `5b2_no_deadline_timeout` confirms the no-deadline path still
bounds each round-trip at `timeout == SSH_TIMEOUT_S == 30`. The observable path
is pinned by `test_trigger_sample_to_verified_delist_under_300s`
(`contract:553-577`): a full poll cadence is charged, each pull/verify costs
25 s, and the verified delist (240 + 50 = 290 s) completes < 300 s with each
logged `timeout <= SSH_TIMEOUT_S and <= ACTION_BUDGET_S`.

**5.3 — Worst-case detection + action ≤ 300 s, but the equality is exactly at the */4 cadence — OK (boundary).**
The model is detection ≤ `POLL_CADENCE_S` (one full tick) + action ≤
`ACTION_BUDGET_S` (60). Probe `5c_cadence_arithmetic`: with `*/4` (240 s) the
worst case is `240 + 60 = 300 s` — **exactly** the contract, not a strict
margin; with `*/5` (300 s) it is `360 s > 300 s` and breaches. The script never
self-imposes the cadence (it is a one-shot CLI), so the bound holds only under
the documented `*/4` deployment (`docs:96`, `docs:106` example crontab). This is
the same "the constant pair is correct but the cadence is an external
assumption" boundary the original finding exposed; it is now at least
documented as `*/4` rather than `*/5`. Residual: the margin is zero — any
per-run local overhead beyond the clamped remote calls erodes it.

**5.4 — The cadence half is documentary only: no crontab entry enforces it — LOW.**
`crontab -l` contains **zero** routstr entries this session, and `docs:112-115`
states the runner is not wired. So while the in-run arithmetic is enforced by
code, the "≤ 5 min from trigger" property in production depends entirely on an
operator wiring `*/4` (or faster) — nothing pins the actual cadence to
`POLL_CADENCE_S`. A `*/5` wiring (the cadence the original finding assumed)
would silently reintroduce the 360 s breach in 5.3. Residual LOW for this
finding (the deployment gap is finding 6's remit); the actionable mitigation is
to make the runner assert/emit the cadence it is invoked at.

**5.5 — `--nsec` publish runs after the success path and is not inside the deadline — LOW.**
The best-effort kind-30078 publish (`:754-756`, `publish_delist_event`
`:451-464`) runs after the confirmed delist and saves, outside the action
deadline; its own `subprocess.run(..., timeout=30)` (`:459`) is not
budget-clamped. Probe `5d_publish_timeout_unclamped` runs a confirmed delist
with `--nsec` and observes the single publish call carrying
`timeout == 30` (not the remaining budget) after `confirmed` is already true.
In the worst case a fired run spends an extra up-to-30 s after the verified
delist prints. This does not breach the ≤ 300 s detection-to-confirmed property
(confirmation already happened), but it inflates job wall-time and, combined
with a zero-margin 5.3, is the residual that most deserves a note. Residual LOW.
