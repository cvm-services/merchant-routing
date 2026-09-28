# Offload review — routstr delist, findings 4–5 (atomicity/idempotence, SLA)

Independent re-derivation for this session (22nd offload pass). Item **4
(atomicity + idempotence)** and item **5 (5-minute SLA arithmetic)** as
specified in `docs/reviews/routstr_delist_review.md:158` and `:196`. Every
`file:line` below was read this session; every behavioural claim was
re-executed against the current artifacts by
`docs/reviews/routstr_f45_probes/probe_f45_consolidated.py` (21 probes,
driving the DEPLOYED script in-process: fake backend, fake monotonic clock,
real on-disk state in tempdirs, forced `os.replace` failures, real `os.fsync`).
Raw output: `docs/reviews/routstr_f45_probes/probe_f45_consolidated.out`.

**Artifact-path status (required report) — HIGH.**
`~/.hermes/bot/docs/routstr_delist_contract.md` **does not exist**. `ls`
→ ENOENT this session; `~/.hermes/bot/docs/` holds only `routstr-delist.md`
and `reviews/`; a bounded recursive search of `~/.hermes` and `~/repos`
(maxdepth 6) for `routstr_delist_contract*` returns **zero hits**. The
mandated contract document is **unreviewable at that path**. The design
document that exists — and that the suite itself calls the frozen contract
(`contract:1`) — is `~/.hermes/bot/docs/routstr-delist.md`, 197 L, md5
`e385af98b9c142eec736672d4dcca290`, byte-identical to repo
`docs/routstr-delist.md`; cited below as `docs:N`. This is a path/naming
defect in the task or the layout, not a missing design.

**Other artifacts.** `~/.hermes/bot/scripts/routstr_delist.py` — 829 L, read
end-to-end, md5 `2ea724ef08d857cd7b88a957300e70b4`, byte-identical to repo
`src/routstr_delist.py`; cited as `src:N`.
`~/.hermes/bot/tests/test_routstr_delist.py` — 752 L, read end-to-end, md5
`031851b356f0de4089512f02f13f05cc`, byte-identical to repo
`tests/test_routstr_delist_contract.py`; cited as `contract:N`. Its loader
fallback (`contract:50-54`) resolves `../scripts`, so the deployed suite
exercises the deployed script.

**Baselines (re-run this session).** repo `python3 -m pytest
tests/test_routstr_delist_contract.py -q` → **25 passed** (0.49 s); deployed
`cd ~/.hermes/bot && python3 -m pytest tests/test_routstr_delist.py -q` →
**25 passed** (0.34 s). Live `~/.hermes/bot/routstr_delist_state.json`
re-read: 245 B, keys `delisted`(true), `last_dry_run`, `last_reason`,
`snapshot`({}), `ts` — **no** `pulled_models`, no `blocked`. `crontab -l`
holds **0** routstr entries. **No artifact was modified**; all three md5 sums
re-checked after the probes and unchanged.

## Finding 4 — Atomicity and idempotence — MEDIUM

The original finding-4 defects (`routstr_delist_review.md:158-194`) are
resolved: the write is now atomic and both idempotence defects are fixed
(re-delist merge, blanket-relist refusal). What keeps the item at MEDIUM is a
durability defect that is *worse than the prior pass reported*: a failed
persist is reported as success **and** the durable advertisement flag it was
supposed to deliver is not written — the same silent-failure channel that
already freezes the circuit breaker.

**4.1 — Atomic state write protocol — OK.**
`save_state()` (`src:221-245`) writes a same-directory tmp
`.{basename}.{pid}.tmp` (`src:230`), `json.dump` (`src:232`) + `flush()`
(`src:233`) + `os.fsync()` (`src:234`), then `os.replace()` (`src:235`);
`return True` (`src:237`), `except → return False` (`src:238-239`), `finally`
unlinks the tmp (`src:240-245`). Probe `4a` → `ret=True fsync_calls=1
replace_calls=1 litter=[] on_disk={'delisted': True, 'ts': 1}`. A concurrent
reader can only observe old-or-new. Pinned by `TestAtomicStateWrites`
(`contract:628-686`), which spies on `os.replace` and asserts old-intact /
new-complete at swap time (`contract:636-663`) and previous-state survival
when the replace raises (`contract:665-686`). Resolves the original "plain
`open(path,"w")`, no tmp/replace/fsync" complaint.

**4.2 — `save_state()` failure is silent: a failed persist is reported as success and the delivered advertisement flag is never written — MEDIUM.**
`save_state()` returns `True`/`False` (`src:237` / `:238-239`) but **all eight
call sites discard the return** (`src:565,:622,:629,:638,:654,:710,:732,:752`;
this session's static count reproduces the bare-expression-statement set) and
`main()` never inspects it. A persist failure (ENOSPC, EROFS, EACCES, replace
failure) yields a run that prints `"action":"delist"`, `"ok":true`,
`"confirmed":true` and exits **0** while disk state is stale. Probe `4b`
(state seeded `delisted:false`, `snapshot:{zai<US>1h:10.0}`,
`consecutive_failures:2`; forced `os.replace` failure on the state path) →
`rc=0 action='delist' ok=True confirmed=True disk_unchanged=True
disk_delisted=False`. Probe `4b2` isolates the design consequence: because the
"flag in the objects that publishes the listing" **is** the persisted
`delisted` field (`src:248-253` / `:263`, `docs:122-123`), the same
forced-failure delist leaves `disk_delisted=False` while `listing_pulled=True`
— the publisher's advertisement silently diverges from a listing that WAS
pulled, and cron sees a clean exit. Must-fix: check the return at all 8 sites
and exit non-zero (or at least warn) when a delist/relist/breaker transition
fails to persist. Contradicts `docs:64-68` in the persist-failure case.

**4.3 — The durable BLOCKED marker is never written when persists fail, yet exit 3 still fires — MEDIUM.**
`fails` is read from disk (`src:544`), written by a discarded-return
`save_state` (`src:732`); `newly_blocked = fails >= BREAKER_THRESHOLD`
(`src:730`) is derived in memory and `return 3 if newly_blocked else 1`
(`src:739`) fires from it. With persists failing, every run emits **exit 3 /
`"blocked":true`** in its JSON while `state["blocked"] = True` (`src:731`)
never lands. Probe `4b3` (seeded `consecutive_failures:2`, `blocked:false`;
4 forced-failure delist runs) → `rcs=[3,3,3,3]
disk_consecutive_failures=2 disk_blocked=False`. Two harms: (a) `docs:76-79`'s
"`blocked: true` (**durable**)" is violated — the marker lives only in the
process; (b) no `--unblock` is possible while the marker is absent (`--unblock`
clears only when the disk-read `blocked` is truthy, `src:561-567`, and the
next run re-reads `blocked:false` at `src:546`), and the operator's durable
signal (`--status`, `src:548-557`) reports the breaker *closed*. Restart
never converges — this is why the item is MEDIUM, not LOW.

**4.4 — No inter-process lock around the read-modify-write — LOW.**
Static count of `flock|fcntl|lockf|O_EXCL|threading|multiprocessing` over the
script = **0** (`4g2_no_lock_primitives_static: hits=0`). `load_state`
(`src:543`) is followed by whole-dict writes; two overlapping cron invocations
each write last-writer-wins, so a concurrent relist/delist can lose an update.
Probe `4g` (two runs reading the same snapshot; A commits
`{ts:3, delisted:True, pulled_models:['m1']}`, then B commits the stale
snapshot it read beforehand) → `final_delisted=False final_ts=2
a_transition_lost=True`. `os.replace` guarantees each write is atomic, not
that the read-modify-write is serialised. Impact bounded (remote actions are
idempotent, `*/4` cadence, short runs) but the original "no locking … last
writer wins" remnant holds.

**4.5 — No directory fsync: the rename is atomic but not crash-durable — LOW.**
`save_state` fsyncs the tmp file (`src:234`) but never opens/fsyncs the
containing directory after `os.replace` (`src:235`): `O_DIRECTORY` count = 0,
`os.open(` count = 0. Probe `4h` → `ret=True fsync_targets_dir=[False]
O_DIRECTORY_hits=0 os_open_hits=0` (the single fsync targets a regular file,
`stat.S_ISDIR` false). A power loss immediately after the swap can lose the
directory entry while the data blocks were flushed, leaving the previous
state. Reader-visible atomicity is intact; only crash-durability of the rename
is unbounded. Related doc defect (also LOW): `contract:252-256` claims fsync
durability is behaviourally pinned by Case 10 with a *real* fsync — inaccurate,
because Case 10's own autouse fixture (`contract:629-634`) no-ops `os.fsync`
exactly as the rig does (`contract:257`). Probe `5e` shows a real `os.fsync`
call only when the rig is NOT in play, so no test exercises the real path.

**4.6 — Idempotence: re-delist MERGES `pulled_models`, never clobbers — OK.**
`prior` (`src:744`), `pulled` (`src:745`), `merged = list(prior) + [n for n in
pulled if n not in prior]` (`src:746`), persisted via `update_state(...,
extra={"pulled_models": merged})` (`src:747-749`). Probe `4c` (state seeded
`pulled_models:["m1","m2"]`, `--delist` against a node advertising nothing) →
`rc=0 pulled=[] pulled_models=['m1','m2'] clobbered=False`. Pinned by
`test_forced_delist_on_absent_listing_is_idempotent_success`
(`contract:524-538`, assertion `:537`). Resolves the "second delist overwrites
with the empty capture, arming a blanket relist" complaint.

**4.7 — Idempotence: no-names relist REFUSES the blanket enable — OK.**
`src:600-611`: with no stored `pulled_models` (`src:601`) and no `--relist-any`
(`src:602`), `--relist` prints `relist_refused` and exits 1 (`src:611`)
**before any remote round-trip** (the `relist()` call is at `src:613`). Probe
`4d` → `rc=1 action='relist_refused' backend_calls=[]`. The scoped relist
restores only captured names via the parameterized payload (`src:390-397`).
Residual asymmetry (LOW): the live deployed state (`delisted:true`, **no**
`pulled_models` — probe `4d2`) would be refused rather than no-op'd, the safe
direction, at the cost that an operator must pass the intended explicit opt-in
(`docs:29-32`). Resolves the "blanket `UPDATE models SET enabled=1` arms
operator-disabled rows" complaint.

**4.8 — Idempotence: a FAILED relist does not tick the breaker — LOW.**
Asymmetric failure handling: a failed **delist** increments
`consecutive_failures` (`src:724`) and can trip the breaker (`src:730-731`); a
failed **relist** (`src:626-632`) only records `last_pull_error` (`src:628`)
and exits 1 (`src:632`) — no counter increment, while a successful relist
resets it (`src:636-637`). Probe `4e` (seed `consecutive_failures=2`, failing
relist backend) → `rc=1 action='relist_failed' disk_consecutive_failures=2
blocked_key_present=False` (key ABSENT, not normalised to False on this path).
A persistently failing relist can loop without the breaker opening, though
`docs:76-79` describes the breaker over "failed runs" generically. Residual
LOW (delisting is the safety-critical direction, which IS counted).

**4.9 — Idempotence: bool counter hole at the breaker read — LOW.**
`fails = state.get("consecutive_failures", 0)` then `fails if
isinstance(fails, int) else 0` (`src:544-545`). `bool` is an `int` subclass, so
a hand-edited `"consecutive_failures": true` is accepted as 1 (contrast the
explicit bool exclusion in `variance_jumped`, `src:152`) and a following
failure yields 2. Probe `4f` (seed JSON literal `true`, failing delist) →
`rc=1 consecutive_failures=2 bool_accepted_as_one=True`. Cosmetic; needs a
corrupted/edited state file.

**4.10 — A failed delist CLEARS the durable advertisement flag while the listing stays pulled — MEDIUM (new this pass).**
On the unconfirmed path `state["delisted"] = False` (`src:726`) is written
unconditionally, with the comment "keep the key greppable". This is not
neutral. Probe `4i`: a confirmed `--manual` delist sets `delisted=True`
(`src:747`); the next `--manual` run with the node unreachable (every attempt
fails, `src:719-732`) writes `delisted=False`, keeps
`pulled_models=['advertised-a','advertised-b']`, and the node still advertises
nothing →
`flag_after_success=True flag_after_failure=False pulled_models_kept=[...]
listing_still_pulled_on_node=True advertisement_flapped=True`. Because
`delisted` **is** the flag the listing publisher reads (`src:248-253`/`:263`,
`docs:122-123`), a single transient ssh failure flips the publisher's
advertisement back on while the SALE remains pulled — the exact
flag-vs-reality divergence `docs:80-83` says the atomic write protocol
prevents (that protocol only guarantees a clean *write*, not that the written
value is consistent with the remote listing). The failed run exits non-zero
(`docs:64-68`), but nothing re-asserts the flag and no test pins it; the two
calls are one tick apart, and the intermediate window is the one where the
delist is still in force. Must-fix: preserve `delisted` on a failed attempt
(the acceleration baseline is correctly *not* consumed — the same reasoning
applies to the flag), or gate the flag on `pulled_models`/last-confirmed state.

**4.11 — A dry-run persist failure is silent too — LOW.**
The dry-run branch records intent via a discarded-return `save_state`
(`src:710`). Probe `4j` (forced `os.replace` failure) → `rc=0
action='delist' intent_persisted=False disk_unchanged=True` (seeded state was
`delisted:false`). A dry run that could not record intent exits 0 and the
intent is unobservable, so an operator cannot distinguish "no intent recorded"
from "nothing to record". Same root cause as 4.2, same fix.

**4.12 — Breaker holds for the event path too, but the contract test cannot see it — LOW.**
The `blocked` branch (`src:569-578`) returns 3 before the `--nsec` publish
(`src:755-756`), so a blocked run spawns neither an API round-trip nor a nak
process. The gap is in the guard: `test_blocked_run_refuses_all_remote_action`
(`contract:601-612`) asserts only on `rig.node.calls`, which never records the
nak subprocess, so a regression that moved the publish above the breaker would
leave that test green. Test-coverage gap, no live defect.

## Finding 5 — 5-minute SLA arithmetic — MEDIUM (was OK)

The original finding-5 complaint (`routstr_delist_review.md:196-234`) is
resolved: `TRIGGER_ACTION_WINDOW_S` is no longer dead — it derives
`ACTION_BUDGET_S` (`src:73`) and every remote round-trip is deadline-clamped
(`src:800-806`). The in-run arithmetic holds and is enforced. What changes the
verdict from OK to MEDIUM this pass is the same persist-silence as 4.2, now
shown to be on the SLA path: a confirmed delist whose state write fails exits
**0** and never becomes durable, so the next run's baseline/flag state is
stale — the 300 s property is asserted only for the process, not for the
persisted outcome cron and the publisher actually read.

**5.1 — The constants are non-decorative and internally consistent — OK.**
`TRIGGER_ACTION_WINDOW_S = 300` (`src:71`), `POLL_CADENCE_S = 240` (`src:72`),
`ACTION_BUDGET_S = TRIGGER_ACTION_WINDOW_S - POLL_CADENCE_S` (`src:73`),
`SSH_TIMEOUT_S = 30` (`src:74`), `MAX_PULL_ATTEMPTS = 2` (`src:75`). Probe
`5a` → `window=300 cadence=240 budget=60 ssh=30 max_attempts=2
sums_to_window=True two_trips_fit=True`. `ACTION_BUDGET_S` is consumed at
`src:612` (relist) and `src:667` (delist) to arm a `time.monotonic()`
deadline; `_SshBackend._run` clamps each round-trip to
`min(SSH_TIMEOUT_S, remaining)` (`src:800-806`) and refuses with
`"action budget exhausted"` **without spawning** when `remaining <= 0`
(`src:803-805`). Arithmetic pinned by
`test_poll_cadence_config_satisfies_the_window` (`contract:543-551`).

**5.2 — Every remote round-trip is clamped; the expired case spawns nothing — OK.**
Because the timeout is `min(30, remaining)` with a pre-flight `remaining <= 0`
refusal, a fired run spends at most `ACTION_BUDGET_S = 60 s` acting by
construction. Probe `5b` (expired deadline, the real `_SshBackend._run`) →
`error='action budget exhausted' ok=False`, zero spawns. Happy path pinned by
`test_trigger_sample_to_verified_delist_under_300s` (`contract:553-577`): a
full cadence is charged, each pull/verify costs 25 s, the verified delist
(240 + 50 = 290 s) completes < 300 s with every logged `timeout <=
SSH_TIMEOUT_S`.

**5.3 — Worst-case detection + action ≤ 300 s, but the equality is exactly at the */4 cadence — LOW (zero-margin boundary).**
Model: detection ≤ `POLL_CADENCE_S` + action ≤ `ACTION_BUDGET_S`, per
`docs:96-98` and `docs:100-103`. Probe `5c` → `*/4` worst case `240 + 60 =
300 s`, `slack=0` — **exactly** the contract, not a strict margin; `*/5` →
`360 s` (`slack=-60`, breaches); `*/2` → `180 s`. The script never
self-imposes the cadence (one-shot CLI), so the bound holds only under the
documented `*/4` deployment (`docs:96`, `docs:100`, `docs:106`). Any per-run
local overhead beyond the clamped remote calls erodes it (5.5, 5.6).

**5.4 — The cadence half is documentary only: no crontab entry enforces it — LOW.**
Probe `5d` → `routstr_crontab_entries=0`; `docs:112-115` states the runner is
not wired yet. The in-run arithmetic is enforced by code, but the "≤ 5 min
from trigger" property in production depends entirely on an operator wiring
`*/4` or faster; a `*/5` wiring would silently reintroduce the 360 s breach
(5.3). The deployment gap itself is finding 6's remit.

**5.5 — Local work is outside the deadline: the un-clamped `fsync` can blow the zero margin — LOW.**
`save_state` is called on every path (`src:565,:622,:629,:638,:654,:710,:732,
:752`) and its `os.fsync` (`src:234`) is a real, un-clamped synchronous disk
operation — the deadline at `src:667` bounds only `_SshBackend._run`
round-trips (`src:800-806`). Probe `5e` (real `os.fsync`, no stub) →
`ret=True real_fsync_calls=1`. The rigs document the pathology: "this host's
disk can stall indefinitely inside fsync" (`contract:252-254`), which is why
both the rig (`contract:257`) and Case 10 (`contract:629-634`) stub `os.fsync`
out. With the arithmetic at exactly 300 s and zero margin (5.3), any local
stall — `fsync`, interpreter startup, `evaluate_triggers` over a large feed —
is spent from the same budget and is unaccounted for by the clamp. Not
demonstrable as a breach here (the fsync is stubbed in every test precisely
because it hangs on this host), so a residual observation, not a reproduced
defect.

**5.6 — `--nsec` publish runs after the success path, outside the deadline — LOW.**
The best-effort kind-30078 publish (`src:755-756`, `publish_delist_event`
`src:451-464`) runs after the confirmed delist and its `save_state` (`src:752`),
outside the action deadline; its own `subprocess.run(..., timeout=30)`
(`src:459`) is not budget-clamped. Probe `5g` (confirmed delist with `--nsec`,
publish charged a full 30 s on the fake clock) → `rc=0 confirmed=True
publish_timeouts=[30] budget=60 total_elapsed=90.0s` (pull 30 + verify 30 =
the 60 s clamped slice, then 30 s of un-clamped publish). This does not breach
the ≤ 300 s detection-to-confirmed property (confirmation happened at the 60 s
boundary), but it is the one measurable place where total run wall clock
exceeds `ACTION_BUDGET_S`, so "a run can never spend more than
`ACTION_BUDGET_S` acting" holds only for the clamped API slices.

**5.7 — The bounded in-run retry is opportunistic, not guaranteed — LOW.**
Both retry guards include `time.monotonic() < deadline` (`src:675-677`,
`:695-696`), and one worst-behaved attempt can consume the entire budget: a
LYING pull (self-reports ok, forcing a verify) costs pull 30 + verify 30 =
60 s. Probe `5f` (lying pull, fake clock charged at `SSH_TIMEOUT_S` per
round-trip) → `rc=1 calls=['pull','verify'] elapsed=60.0s budget=60
attempts_ran=1` — only ONE attempt ran; the retry was refused because the
first attempt spent the whole budget, so `MAX_PULL_ATTEMPTS` is structurally
inert in the worst case. It does fire while budget remains
(`contract:599` counts 3 runs × attempt+retry = 6 pulls on an ssh-down node,
where a failing pull costs no clock), absorbing blips that arrive early — the
safe direction, but not a guaranteed second attempt.

**5.8 — A confirmed delist whose persist fails exits 0 and never becomes durable — MEDIUM (new this pass).**
The success path writes the durable `delisted`/`pulled_models`/breaker reset
through a discarded-return `save_state` (`src:752`), then returns 0 (`src:764`)
and prints `"confirmed": true`. Probe `4b` is exactly this case →
`rc=0 action='delist' ok=True confirmed=True disk_unchanged=True`. The ≤ 300 s
property is therefore asserted for the process outcome only: cron records a
success, the next tick re-reads a stale `delisted`/baseline/snapshot
(`src:543`), and — on the failed delist path — the advertisement flag
diverges (4.10). This is the SLA-side manifestation of 4.2, and the reason
this finding is no longer OK. Must-fix: exit non-zero on a failed persist so the
5-minute window is enforced on the durable outcome, not just on process exit.
