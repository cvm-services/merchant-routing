# Offload review — routstr delist, findings 4–5 (atomicity/idempotence, SLA)

Independent pass (re-dispatch). Scope, per the original task: item **4
(atomicity + idempotence)** and item **5 (5-minute SLA arithmetic)** as stated
in `docs/reviews/routstr_delist_review.md`. Everything below is re-derived in
this session against the CURRENT artifact set; nothing is carried over
unverified from earlier passes.

**Artifact-path status (required report per task instructions)**

- `~/.hermes/bot/docs/routstr_delist_contract.md` — **MISSING — HIGH.**
  Re-verified this session: the path does not exist; `~/.hermes/bot/docs/`
  holds only `routstr-delist.md` and `reviews/`; a tree search for any
  `*contract*` artifact under `~/.hermes/bot` returns the empty set. The
  mandated path is unreviewable; the stand-in reviewed is
  `~/.hermes/bot/docs/routstr-delist.md` (197 lines, md5
  `e385af98b9c142eec736672d4dcca290`, byte-identical to repo
  `docs/routstr-delist.md`). `docs:N` below applies to both copies.
- `~/.hermes/bot/scripts/routstr_delist.py` — 829 lines, read end-to-end;
  **byte-identical** to repo `src/routstr_delist.py` (both md5
  `2ea724ef08d857cd7b88a957300e70b4`). `routstr_delist.py:N` applies to both.
- `~/.hermes/bot/tests/test_routstr_delist.py` — 752 lines, read end-to-end;
  **byte-identical** to repo `tests/test_routstr_delist_contract.py` (both md5
  `031851b356f0de4089512f02f13f05cc`). The DEPLOYED suite is the 25-case
  **contract** suite (`contract:N`), NOT the repo 96-case unit suite
  `tests/test_routstr_delist.py` (md5 `293b0459b636a918cf1cce57bf922473`,
  cited as `unit:N`). Loader fallback `contract:49-54` resolves `../scripts`,
  so the deployed suite tests the deployed script.

**Executed this session (live, read-only):** repo `python3 -m pytest tests/ -q`
→ **121 passed** (96 unit + 25 contract); deployed rig
`cd ~/.hermes/bot && python3 -m pytest tests/test_routstr_delist.py -q` →
**25 passed**. Hermetic behavioural probes (`~/worktrees/probe_f45_rp10.py`,
`tempfile.mkdtemp()` only; no artifact touched) reproduced the discarded
`save_state` return (4.2), the durable-flag falsification + breaker chain (4.3),
the SLA boundary at exactly t=300 (5.3), and the string-typed `pulled_models`
wrong relist (4.8). Live re-reads: `crontab -l | grep -ci routstr` → **0**; state
file `~/.hermes/bot/routstr_delist_state.json` → `delisted: true`,
`last_reason: "manual override"`, **no `pulled_models` key**.

## Finding 4 — Atomicity and idempotence — **MEDIUM**

**4.1 — Atomic write protocol — SOURCE OK, PINNED — OK.**
`save_state()` (`routstr_delist.py:221-245`) writes a same-directory tmp file
(`.{basename}.{pid}.tmp`, `routstr_delist.py:230`), `json.dump` + `flush()` +
`os.fsync()` (`routstr_delist.py:231-234`), then `os.replace()`
(`routstr_delist.py:235`) — atomic on POSIX — with tmp cleanup in `finally`
(`routstr_delist.py:240-245`). Pinned at the swap instant by `contract:636-663`
(old bytes complete at dst + complete new bytes in tmp, exactly one `os.replace`,
no tmp litter) and by a simulated pre-replace crash `contract:665-686`. Torn
reads of the state file are no longer possible. Severity: **OK**.

**4.2 — Every persistence failure is silent: `save_state`'s False is discarded
at all eight call sites — MEDIUM.** `save_state` returns True/False
(`routstr_delist.py:237`, `routstr_delist.py:239`) and every caller invokes it as
a bare statement — re-enumerated by grep this session: `routstr_delist.py:565`,
`:622`, `:629`, `:638`, `:654`, `:710`, `:732`, `:752` (8 sites). Executed probe
(`probe_f45_rp10.py`, Probe 4.2) against the real `main()` with the state path
unmakeable:

    PROBE 4.2: rc=0 action=delist confirmed=True state_exists=False

The remote SALE **is** pulled (`confirmed=True`), yet no state file is created,
the durable `delisted` flag the whole flag-mechanism depends on
(`routstr_delist.py:251-253`, `docs:122-123`) is absent, and cron still sees
exit 0. Atomicity makes this rarer, not surfaced. Severity: **MEDIUM** (must-fix:
check the return at all eight sites and exit non-zero).

**4.3 — The failure path FALSIFIES a valid durable `delisted` flag — MEDIUM.**
`routstr_delist.py:726` assigns `state["delisted"] = False` **unconditionally**
on an unconfirmed delist, whatever the flag was before. Trigger 2 is level-based
by design (`docs:50-53`, `routstr_delist.py:19-21`), so a re-fire on an
already-delisted node is normal; if the pull lands but the independent re-fetch
flakes, the run takes the failure path and downgrades `delisted` from true to
false while the listing really is pulled. Executed probe (Probe 4.3):

    run1 rc=0 delisted=True  pulled=['A', 'B']
    run2 rc=1 action=delist_failed delisted=False fails=1
    run4 rc=3 blocked=True

`pulled_models` survives (the failure path never touches it,
`routstr_delist.py:725-729`), so recovery is possible — but the durable flag now
contradicts the remote reality the run itself established at
`routstr_delist.py:683`. Chained: a purely **verification-channel** flake
increments `fails` (`routstr_delist.py:724`) and opens the breaker
(`routstr_delist.py:730-731`); the open breaker then refuses the payload-`--relist`
recovery *before* any remote call (`routstr_delist.py:569-578` precedes the relist
branch at `routstr_delist.py:600-611`) — confirmed live, relist returned
`blocked`/rc 3. Not pinned: the only failure-path flag assertions start from a
FRESH state (`contract:346-360`), so no test starts from `delisted=true`. The
relist failure path is correct by contrast — it leaves `delisted=true` untouched
(`routstr_delist.py:626-632`). Severity: **MEDIUM** (must-fix: preserve the prior
flag on the failure path — only ever set `delisted` from an observed re-fetch
outcome).

**4.4 — No inter-process mutual exclusion: atomic ≠ serialized — MEDIUM.** Grep
of the module for `flock|fcntl|lockf|O_EXCL|threading|multiprocessing` returns
**zero hits** (imports `routstr_delist.py:51-57` cannot lock). Every load →
modify → save sequence is last-writer-wins: the name merge
(`routstr_delist.py:744-749`), the breaker increments (`routstr_delist.py:724-727`),
the unblock reset (`routstr_delist.py:561-567`) and the relist pop
(`routstr_delist.py:635`). A manual `--relist` racing a cron delist tick can lose
the other's write. No concurrency test exists in either suite. Severity:
**MEDIUM**.

**4.5 — No directory fsync; tmp mode/inode churn — LOW.** `os.replace`
(`routstr_delist.py:235`) is not followed by an fsync of the containing
directory, so the rename itself is not crash-durable on all filesystems
(pedantic on ext4). The tmp file is created with the process umask
(`routstr_delist.py:231`) and `os.replace` carries that mode to the state path,
so each save rewrites the deployed file's mode and inode. The state holds no
credentials: live keys are `delisted`, `last_dry_run`, `last_reason`, `snapshot`,
`ts` (live state re-read this session). Severity: **LOW**.

**4.6 — Idempotence core — IMPLEMENTED, PINNED — OK.** (a) Repeat delist merges
rather than clobbers: `merged = list(prior) + [n for n in pulled if n not in
prior]` (`routstr_delist.py:744-746`) stored via `extra={"pulled_models": merged}`
(`routstr_delist.py:747-749`) — pinned `contract:524-538`. (b) A blanket relist is
refused: with no stored names and no `--relist-any`, `--relist` prints
`relist_refused` and returns 1 with zero remote calls (`routstr_delist.py:600-611`;
the blanket `UPDATE models SET enabled=1;` at `routstr_delist.py:361` is reachable
only through the explicit opt-in at `routstr_delist.py:526-528`), rule documented
`docs:29-32`. (c) A successful relist pops `pulled_models`
(`routstr_delist.py:635`) so a second `--relist` refuses instead of
blanket-enabling — pinned `contract:490-507`. (d) Remote idempotence holds:
`UPDATE models SET enabled=0 WHERE enabled=1` (`routstr_delist.py:355`) matches 0
rows on a repeat; the relist payload is parameterized (`routstr_delist.py:378-397`).
Severity: **OK**.

**4.7 — The DEPLOYED suite pins none of the refusal paths — MEDIUM (deployment
asymmetry).** Grep this session: `relist_refused|relist_any|relist-any` → **10
hits in the repo unit suite, 0 hits in the deployed contract suite**. The refusal
(`routstr_delist.py:600-611`) and opt-in (`routstr_delist.py:602`) behaviours are
pinned only by a suite that is not deployed; a regression there ships green
through all 25 deployed tests — which are the tests that run on this host.
Separately, no test executes two consecutive `--relist` runs, so the pop at
`routstr_delist.py:635` is unpinned in both suites. Severity: **MEDIUM** as a
deployment asymmetry, because the live artifact set is the deployed copy.

**4.8 — No type validation of persisted values — LOW.** `load_state` validates
only the top-level container (`routstr_delist.py:216`) and `consecutive_failures`
only coarsely (`isinstance(fails, int)` at `routstr_delist.py:544-545` — note
`True` passes as `1`; `bool` excluded only for `uncertainty` at
`routstr_delist.py:152`). Every other persisted value is used unchecked. Executed
probe (Probe 4.8) with a hand-edited `{"delisted": true, "pulled_models": "AB"}`:

    rc=0  payload: ...UPDATE models SET enabled=1 WHERE name IN (?,?)',['A', 'B'])...

`list("AB")` silently becomes two model names `A`, `B` — no crash, no refusal, a
wrong scoped relist. Severity: **LOW**.

**4.9 — Crash window between remote confirmation and local save — LOW.** The
captured names exist only in the pull round-trip's stdout; a crash after
confirmation (`routstr_delist.py:682-688`) but before the save
(`routstr_delist.py:752`) loses them irrecoverably (a later `SELECT ... WHERE
enabled=0` cannot distinguish pulled rows from operator-disabled rows). The
4.6(b) refusal converts that from silent blanket-enable into an explicit
`relist_refused` + operator decision — acceptable, but the names are gone.
Severity: **LOW**.

**Verdict, Finding 4: MEDIUM.** Both required properties are substantively
implemented and independently pinned (tmp+fsync+replace swap protocol; merge on
re-delist; refusal + explicit opt-in; scoped relist pop; remote UPDATE
idempotence). Open exposure: silent persist failure (4.2), a failure path that
falsifies the durable flag and can self-trip the breaker (4.3), no inter-process
serialization (4.4), and a deployed suite that pins none of the idempotence
guards it is supposed to protect (4.7).

## Finding 5 — 5-minute SLA arithmetic — **MEDIUM**

**5.1 — The required breakdown, re-derived against the current script.**
- **Configured poll interval:** `POLL_CADENCE_S = 240` (`*/4`) at
  `routstr_delist.py:72`, documented `docs:96` with the crontab example
  `docs:106`. **Deployment re-verified live: `crontab -l` has no routstr_delist
  entry** — the cadence is a paper value; the docs' own note stands (`docs:112`).
- **Polls/retries needed to confirm:** TWO in-run attempts
  (`MAX_PULL_ATTEMPTS = 2`, `routstr_delist.py:75`; loop
  `routstr_delist.py:671-697`), each = pull + independent verify; the whole pair
  counts as ONE breaker run (increment once, outside the loop, at
  `routstr_delist.py:724`). Beyond the pair, retry waits for the next cron tick.
- **Re-fetch round-trip:** genuinely independent — read-only
  `SELECT COUNT(*) FROM models WHERE enabled=1` (`routstr_delist.py:400-411`),
  executed `routstr_delist.py:682`, gating success at `routstr_delist.py:683`
  (`count == 0`). Pinned by the lying-pull rig `contract:346-360`.
- **Action round-trip bound:** two layers — per round-trip `SSH_TIMEOUT_S = 30`
  (`routstr_delist.py:74`) passed to `subprocess.run(timeout=...)`
  (`routstr_delist.py:808-809`), clamped to the remaining budget at
  `routstr_delist.py:800`/`:806` with an immediate `action budget exhausted`
  return for `remaining <= 0` (`routstr_delist.py:803-805`); and a monotonic
  deadline `time.monotonic() + ACTION_BUDGET_S` (`routstr_delist.py:667` delist,
  `routstr_delist.py:612` relist). The in-run action can never exceed 60 s of
  subprocess time. The ssh argv carries no `ConnectTimeout`/`BatchMode` (builder
  `routstr_delist.py:414-425`) — acceptable, the clamp bounds a hung ssh anyway.
- **Worst case detection → confirmed delist:** 240 s detection + 30 s pull +
  30 s verify = **300 s = exactly `TRIGGER_ACTION_WINDOW_S`**
  (`routstr_delist.py:71`). Config identity pinned `contract:543-551`.

**5.2 — The constant is wired, not decorative — OK.** `TRIGGER_ACTION_WINDOW_S`
feeds `ACTION_BUDGET_S` (`routstr_delist.py:73`), consumed as a real deadline at
`routstr_delist.py:612`/`:667` and realised as the timeout clamp at
`routstr_delist.py:806`. `docs:91-114` carries arithmetic matching the code
(`docs:95-98` vs `routstr_delist.py:71-74`). Severity: **OK**.

**5.3 — The boundary is exact: zero slack, and the observable test never
exercises it — MEDIUM.** The identity holds with equality: 240 + (30 + 30) = 300.
Executed probe (Probe 5.3):

    POLL=240 BUDGET=60 SSH=30 WINDOW=300
    POLL+BUDGET=300  (== WINDOW? True)
    240 + 30 + 30 = 300 ; < 300? False

So `contract:568`'s assertion `confirmed_t - sample_t < 300` is **False** at the
true boundary; `contract:559` hard-codes `round_trip_s = 25.0`, i.e. the test
spends only 50 of the 60 s budget, which is why it passes. Worse, the durable
flag write (`routstr_delist.py:747-752`) and the event publish
(`routstr_delist.py:755-756`) both happen strictly *after* confirmation, so at
the boundary the flag the publisher reads is written past t=300. The window
holds as `≤ 300` only, with no margin for cron jitter, process start, trigger
evaluation, or the state write. Severity: **MEDIUM** (must-fix: shrink
`POLL_CADENCE_S` (e.g. `*/2`) or drop `SSH_TIMEOUT_S` to buy real margin).

**5.4 — The detection term is neither enforced at runtime nor deployed —
MEDIUM.** Nothing in the module measures the actual cadence: no comparison of
consecutive state `ts` values and no validation that the real cron interval
equals `POLL_CADENCE_S` (grep of `routstr_delist.py` for `ts`-delta logic and of
the crontab found none). Detection is charged at a full cadence as an
*assumption*; if the runner is wired at `*/5` instead, the worst case is
300 + 60 = 360 s and the SLA is breached by construction — reachable because no
crontab entry exists to pin the cadence. Severity: **MEDIUM**.

**5.5 — The event channel sits outside the window — LOW.** The optional
kind-30078 publish runs after confirmation with its own `timeout=30`
(`routstr_delist.py:459`, call sites `routstr_delist.py:640` and
`routstr_delist.py:756`) and is not covered by the deadline, so the worst-case
trigger → published event is 240 + 60 + 30 = 330 s. The durable flag lands before
the publish, so the flag path is unaffected; but sell-side consumers that react
to the event (`docs:124-127`, `routstr_delist.py:29-32`) can observe the delist
past the window in the worst case. Severity: **LOW**.

**5.6 — A first attempt that burns the full 60 s cannot be retried; 600 s worst
case — LOW.** When attempt 1 spends pull 30 + verify 30 = the whole
`ACTION_BUDGET_S`, the retry guard at `routstr_delist.py:695`
(`time.monotonic() < deadline`) short-circuits, so the run fails after one
attempt and waits for the next tick: 240 + 60 + 240 + 60 = 600 s. The narrower
case differs: if the *pull itself* times out (30 s burnt, no verify), the retry
guard at `routstr_delist.py:675-677` does pass and attempt 2 gets its own 30 s.
So the "bounded in-run retry absorbs a transient blip"
(`routstr_delist.py:664-665`) is true for fast failures and pull-only timeouts,
false for a pull-ok/verify-timeout first attempt. Severity: **LOW**.

**Verdict, Finding 5: MEDIUM.** The SLA is real code — a monotonic action budget
clamps every round-trip, success requires an independent re-fetch, retries are
bounded, and docs carry matching `*/4` arithmetic pinned by a fake-clock case
and config-identity cases in both suites. It does **not** yet hold robustly: the
240 + 60 split consumes the entire 300 s window with exactly zero slack (5.3),
the detection term is an unverified and undeployed assumption (5.4), and the
event signal can land up to 30 s past the window (5.5).

---

Provenance: offload pass on artifact set script md5 `2ea724ef`, contract suite
md5 `031851b3`, docs md5 `e385af98`; unit suite md5 `293b0459`. Evidence is
per-pass: both artifact copies read end-to-end, the loader fallback re-verified,
suites executed fresh (121 repo + 25 deployed rig), greps re-run (save_state call
sites = 8, lock primitives = 0, refusal keywords = 10 unit vs 0 deployed), the
live crontab and state file re-read, and four read-only behavioural probes run in
`tempfile.mkdtemp()` (`probe_f45_rp10.py`). 4.1/4.6/5.1/5.2 confirmed
implemented-and-pinned; 4.2, 4.3, 4.4, 4.7, 4.9, 5.4, 5.6 confirmed and
line-referenced afresh; 4.8 and 5.3 reproduced live. No artifact was modified.
`~/.hermes/bot` is not a git repository, so the local commit lands in the
workspace repo (`/home/c03rad0r/repos/merchant-routing`) at
`docs/reviews/findings_4_5.md`, with this identical copy at the task-mandated bot
path `~/.hermes/bot/docs/reviews/findings_4_5.md`. Not pushed, per the task body.
