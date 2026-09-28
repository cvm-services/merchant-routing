# Offload review — routstr delist, findings 6–7 (circuit breaker, hygiene)

Ninth independent offload pass for findings 6–7, re-derived from scratch this
session (nothing carried over): the deployed script was re-read end-to-end (all
829 lines), the deployed contract suite end-to-end (all 752 lines), and the
contract document end-to-end (197 lines). Every behavioural claim below was
re-executed against the current artifacts by
`docs/reviews/routstr_f67_probes/probe_f67_pass26.py` → raw output
`docs/reviews/routstr_f67_probes/probe_f67_pass26.out` (**47/47 checks
passed**, zero network, zero artifact mutation, all state on disk-backed tmp
under `~/.cache` — host `/tmp` is 100 % full). Finding 6 was probed both
in-process through the real `rd.main()` CLI surface and by driving the
**real deployed script as a subprocess** with only `ssh` intercepted by a
logging PATH shim (rc 255); no internal is faked.

## Artifact-path status (required report per task instructions)

- `~/.hermes/bot/docs/routstr_delist_contract.md` — **MISSING — HIGH**
  (re-verified this session: `find ~/.hermes/bot -iname '*contract*'` → zero
  hits; `ls ~/.hermes/bot/docs/` → only `reviews/` and `routstr-delist.md`).
  The mandated contract document is unreviewable at that path. The design doc
  that exists — and that the suite itself names the frozen contract
  (`test_routstr_delist.py:1`) — is `~/.hermes/bot/docs/routstr-delist.md`,
  197 L, md5 `e385af98b9c142eec736672d4dcca290`, byte-identical to repo
  `docs/routstr-delist.md`; cited below as `docs:N`. This is a task-path/
  layout defect (or rename), not a missing design.
- `~/.hermes/bot/scripts/routstr_delist.py` — present, 829 L, md5
  `2ea724ef08d857cd7b88a957300e70b4` — byte-identical to repo
  `src/routstr_delist.py`; cited as `src:N`.
- `~/.hermes/bot/tests/test_routstr_delist.py` — present, 752 L, md5
  `031851b356f0de4089512f02f13f05cc` — byte-identical to repo
  `tests/test_routstr_delist_contract.py`; cited as `contract:N`. Its loader
  (`contract:50-54`) resolves `../src` first, then `../scripts`, so the
  deployed-layout run exercises the DEPLOYED script copy.

Baselines re-run this session: repo `pytest tests/test_routstr_delist_contract.py -q`
→ **25 passed** (0.37 s); deployed-layout `cd ~/.hermes/bot && pytest tests/test_routstr_delist.py -q`
→ **25 passed** (0.40 s); repo full `pytest tests/ -q` → **121 passed** (1.38 s;
main 96 + contract 25). All three md5 sums were re-checked after probing and
are unchanged. Live `~/.hermes/bot/routstr_delist_state.json` re-read
read-only (240 B, mode 0o664, keys `delisted`/`last_dry_run`/`last_reason`/
`snapshot`/`ts`); `crontab -l` holds **0** routstr entries.

---

## Finding 6 — circuit breaker (3 failed attempts → BLOCKED, exit code 3) — OK (residuals LOW)

**Explicit statement required by the task: the claim HOLDS on the deployed
artifact.** A breaker exists, trips at the configured threshold, writes a
durable BLOCKED marker, and exits 3. Requirement met; five residuals, all LOW,
itemized at the end.

1. **Breaker vocabulary and durable state exist.**
   `BREAKER_THRESHOLD = 3` (src:77); the counter is loaded with an isinstance
   guard (`src:544-546`) alongside `blocked = bool(state.get("blocked"))`
   (src:546); a failed run increments and writes BLOCKED at `src:724-732`
   (`newly_blocked = fails >= BREAKER_THRESHOLD` at `src:730-731`, then
   `state["blocked"] = newly_blocked` at `src:731`); reset on a confirmed
   delist (`src:750-751`) and on a successful relist (`src:636-637`); operator
   clear via `--unblock`, which pops both keys and lets the same run proceed
   (`src:561-567`). Probe: after 3 failing runs the durable file reads
   `blocked: true`, `consecutive_failures: 3`.
2. **Exit code 3 exists, means exactly BLOCKED, and the exit space is
   {0,1,2,3}.** Trip returns `3 if newly_blocked else 1` (`src:739`); the
   blocked refusal returns 3 (`src:578`); process exit is via
   `raise SystemExit(main())` (`src:828-829`). Probes this session: 5 failing
   real-CLI runs → rcs `[1,1,3,3,3]`; quiet run → 0 (`src:660`); `--dry-run`
   success → 0 (`src:717`); `--bogus` → 2 (argparse). Documented at
   `docs:153-154`.
3. **Attempt 4 never runs — proven on the real CLI.** Deployed script driven
   as a subprocess against a logging PATH-shimmed `ssh`: per-run ssh
   invocations `[2,2,2,0,0]`; all 6 pre-trip round-trips were pull payloads
   (`UPDATE models SET enabled=0`), the verify re-fetch was never reached
   (zero `SELECT COUNT` lines in the shim log); runs 4-5 made **zero** remote
   calls. The refusal (`src:569-578`) precedes backend construction (`src:666`),
   trigger evaluation (`src:646`) and every dry-run branch. On a healed node,
   `--manual`, `--relist`, `--relist --relist-any`, `--delist` and
   `--manual --dry-run` all return rc 3 / `action: "blocked"` with zero
   spawns; `--status` (`src:548-557`) reports both breaker fields read-only
   (rc 0, zero spawns) and does **not** clear.
4. **Counter ticks once per RUN, not per attempt.** The whole bounded retry
   loop counts once: `while attempts < MAX_PULL_ATTEMPTS` (`src:671`) with
   `MAX_PULL_ATTEMPTS = 2` (`src:75`) and `attempts += 1` as the body's first
   statement (`src:672`); both `continue` branches are additionally
   deadline-guarded (`src:675-677`, `src:695-696`). Probe: `--unblock --manual`
   on a tripped state with a healed node → rc 0 confirmed delist,
   `consecutive_failures: 0`, `blocked: false`.
5. **BLOCKED is surfaced to the operator, not silent.** Refusal JSON carries
   `action: "blocked"`, `ok: false`, `blocked: true`, the count and the literal
   `--unblock` remedy (`src:572-577`); the trip output carries
   `consecutive_failures` and `blocked` (`src:733-738`); `--status` reports
   both (`src:548-557`). Contract doc `docs:76-79`; pinned by
   `contract:593-597` (`'"blocked": true' in raw`).

**Residuals — all LOW, all re-probed this session:**

- **(a) The counter never decays across non-firing runs.** `src:651-660`
  preserves prior keys and never touches the counter, so stale failure debt
  survives. Probe: fail ×2 → quiet run (rc 0, `action: none`, counter still 2)
  → `preds_error` run (rc 1, `action: none`, counter still 2) → one new
  failure trips rc 3. A stale count plus ONE new failure blocks the first
  failure of a *new* incident, delaying a protective delist until an operator
  notices rc 3. Documented reset rule (`docs:79`) does not cover this.
- **(b) Fail-open if the BLOCKED write cannot persist.** `save_state`'s return
  is ignored at `src:732` — one of 8 bare `Expr` call sites
  (`src:565, :622, :629, :638, :654, :710, :732, :752`, AST-enumerated: 8/8
  returns ignored). Probe: with the state directory chmod 0500 exactly at the
  tripping run, the CLI printed rc 3 / `blocked: true` while disk kept
  `consecutive_failures: 2` / `blocked: false`. Bounded (≤2 attempts per
  cadence tick) and self-healing on the first successful write, but a breaker
  that can fail open. Cross-ref findings_4_5 residual.
- **(c) Asymmetric relist accounting, unstated in docs.** A FAILED `--relist`
  never increments the counter (`src:626-632` touches no breaker key; probe:
  seeded fails=2 + dead node → rc 1, still 2, not blocked) while a successful
  relist DOES reset it (`src:636-637`; probe: rc 0 → counter 0). `docs:76-79`
  is silent on this. Harmless under documented usage (relist is manual), worth
  one doc sentence.
- **(d) Dry-run interaction, over-strict one way and under-strict the other.**
  A BLOCKED state refuses even `--dry-run` previews (refusal `src:569`
  precedes everything except `--status`/`--unblock`; probe rc 3, zero spawns)
  — no rehearsal of the clearing run without actually clearing; and
  `--unblock --dry-run` performs a REAL durable clear (probe: breaker keys
  absent from state afterwards) — a dry run with a durable side effect, in
  mild tension with `docs:87-89`.
- **(e) Cosmetic type-guard hole.** `isinstance(fails, int)` at `src:545`
  admits `True` (bool ⊂ int): probe with a seeded
  `{"consecutive_failures": true}` plus one failure → disk counter 2. The
  sibling variance guard excludes bool explicitly (`src:152-153`); this one
  should too. Impact nil in practice.
- **Interpretation note (LOW).** The task wording "3 failed *attempts*" is
  implemented as 3 consecutive failed **RUNS**, each of which may spend
  `MAX_PULL_ATTEMPTS = 2` ssh round-trips (`src:75`, `src:671`) — so the trip
  lands after up to 6 remote attempts, not 3. This reading is explicit and
  consistent: `docs:76-79` ("3 consecutive failed runs"), pinned by
  `contract:591` (`rcs == [1, 1, 3]` over three runs).

**Verdict 6: OK — the requirement is met on the deployed artifact** and pinned
by six dedicated main-suite tests (`main:816-925`; tests at `main:828`,
`main:845`, `main:877`, `main:894`, `main:909`, plus the `--unblock` reset at
`main:586-600`) and contract Case 9 (`contract:581-624`). Residuals LOW as
itemized.

## Finding 7 — hygiene (secrets, loops) — OK (residuals LOW)

### 7a. Secrets — OK (residual LOW)

The nsec is read from a file only inside `publish_delist_event()`
(`src:456-458`) and reaches `nak` exclusively via the child environment
variable `NOSTR_SECRET_KEY` (`src:459-461`) with `--env-sec` (`src:446`); the
identifier text appears at exactly two source sites (`src:458`, `src:460`,
AST-enumerated). Probe against the deployed module, full `--manual --nsec`
cycle: exactly ONE nak spawn; `--env-sec` present and `--sec` absent from
argv; the secret present ONLY in the child env; the argv carries kind 30078,
`d:routstr-delist` and the three `wss://` relays; the secret is absent from
captured stdout, from the argv dump and from the durable state file; the state
keys are within the credential-free allowlist
(`ts`/`delisted`/`snapshot`/`last_reason`/`pulled_models`/`consecutive_failures`/`blocked`/
`last_pull_error`/`last_dry_run`). `build_delist_event` returns None when the
sec file is missing (`src:437-438`); the doc explicitly rejects `--sec` for
ps-leak reasons (`docs:126-127`); nak output is captured and discarded
(`src:461`). Exception surfaces are `str(exc)` of subprocess failures
(`src:824`) — ssh argv + payload, which carry no credential. Pinned:
`contract:689-752`, argv shape `main:399-400`.

Residual LOW: a failed publish is swallowed AND indistinguishable from success
— `except Exception: pass` then `return argv` (`src:462-464`; probe: a RAISING
nak still yields a clean rc 0 `action: delist` run). Callers ignore the return,
no state note is written; doc-blessed best-effort (`docs:128`), but operators
get zero signal that the event channel is dead. Cross-ref 7d.

### 7b. Loops in-process — OK

AST re-inventory over the deployed source: exactly ONE `while`
(`src:671`), bounded by `attempts < MAX_PULL_ATTEMPTS` (= 2, `src:75`) with
`attempts += 1` body-first (`src:672`) and both `continue` branches
deadline-guarded (`src:675-677`, `src:695-696`) — verified structurally, not
just by grep: no `while True` exists. Four `for` loops (`src:112`, `:146`,
`:204`, `:297`) and seven comprehensions (`src:110`, `:308`, `:312`, `:479`,
`:597`, `:694`, `:746`), all finite over in-memory lists. `subprocess.run`
sites: exactly 2 (`src:459`, `src:808`), both carrying `timeout=` (nak 30 s at
`src:459`; ssh `min(SSH_TIMEOUT_S, remaining)` from `src:800-806`, passed at
`src:808-809`); `shell=True` count 0. Probe: a fired run's round-trips are
timeout-clamped to the remaining 60 s action budget
(`timeouts=[30, 30]`, `ACTION_BUDGET_S == 60`). No unbounded iteration exists.

### 7c. Dry-run purity — OK (residual LOW)

Re-probed in-process against the deployed module with **all** subprocess
spawns intercepted (an exploding stub that raises on ANY spawn — stronger than
the suite's backend swap): a `--manual --dry-run --nsec` run spawned ZERO
subprocesses, not even ssh (the dry stub at `src:797-799` returns before
`src:808`) and no nak (both publish sites `src:639-640`/`src:755-756` sit
after the dry early-returns `src:615-625`/`src:699-717`). State effects: a
fresh-state dry delist writes exactly `["last_dry_run", "ts"]` — no `delisted`
flip, no `pulled_models`, no breaker keys; a seeded `delisted: true` +
`pulled_models` + `consecutive_failures: 1` + `snapshot` state survived
`--relist --dry-run` with all four intact (the pop lives only in the real
success path, `src:635`); a dry run against a DEAD node still exits 0 and
spawns nothing; the dry-FAILURE branch (`src:717`) exits 1 and writes only
`last_dry_run`/`ts` (no breaker keys, no `last_pull_error`). Pinned:
`contract:731-752`, `main:1072`.

Residual LOW: the dry run still bumps `ts` and writes `last_dry_run` —
documented intent recording (`docs:87-89`), benign; and `--unblock --dry-run`
clears the breaker for real (finding-6 residual (d)).

### 7d. The operational loop — OK (capped by the breaker; latent anyway)

Cron re-attempting a failed pull is capped from the scheduler side by the
breaker: real-CLI probe per-run deltas `[2,2,2,0,0]`, so a dead node sees at
most 3 runs × 2 bounded attempts = 6 round-trips before the breaker holds, each
subsequent tick exiting 3 with the `--unblock` remedy in the JSON — cron-visible,
not silent. Re-verified live: `crontab -l` has ZERO routstr entries — the loop
remains latent, as documented (`docs:112-115`).

Residual LOW: while blocked, cron would wake per cadence and exit 3
indefinitely until an operator intervenes — correct signalling, but nothing
escalates beyond the exit code; and a dead event channel (7a residual) is
indistinguishable from a live one.

### 7e. Permissions / housekeeping — LOW

`save_state` (`src:221-245`) writes with the default umask — probe state file
mode 0o664 (umask 0o2) and credential-free (7a allowlist), so impact nil; the
deployed script is 0o775 (executable as documented), test/doc copies 0o600.
`save_state`'s return is ignored at all 8 call sites (`src:565`, `:622`,
`:629`, `:638`, `:654`, `:710`, `:732`, `:752` — AST-enumerated, every one a
bare `Expr` statement, none assigned or checked); the breaker-specific
consequence is finding-6 residual (b), the standing findings-4/5 residual
otherwise. No `TODO`/`FIXME`/`XXX`/`HACK` marker exists in the script (grep: 0
hits); the `--preds`/`--override`/`--nsec` paths carry no secret material into
state or logs (7a).

**Verdict 7: OK — secrets (7a) env-only and nowhere else, loops (7b) all
bounded by construction, dry-run (7c) intent-only in both directions and
spawn-free, operational loop (7d) breaker-capped and latent; residuals LOW as
itemized.**

---

## Provenance

Ninth independent offload pass for findings 6–7, against the unchanged
artifact set (script md5 `2ea724ef…`, suite md5 `031851b3…`, doc md5
`e385af98…` — all byte-identical to repo, re-checked after probing).
Evidence this session: all 829 script lines, all 752 suite lines and all 197
doc lines read end-to-end; 47 hermetic probe checks
(`docs/reviews/routstr_f67_probes/probe_f67_pass26.py` →
`probe_f67_pass26.out`), comprising 6 real-CLI subprocess probes on the
deployed script (only `ssh` PATH-shimmed) and 41 in-process/AST probes; zero
network; zero artifact modification — every `--state`/`--override` path landed
in a disk-backed tmp tree under `~/.cache` (host `/tmp` is 100 % full).
Suites: repo contract 25/25 (0.37 s), deployed-layout contract 25/25 (0.40 s)
against the deployed script, repo full 121/121 (1.38 s). Required
artifact-path report: `routstr_delist_contract.md` **MISSING at the bot path —
HIGH** (re-verified); `routstr-delist.md` byte-identical to repo. `~/.hermes/bot`
is not a git repository, so the required local commit lands in the workspace
repo (`merchant-routing`) at `docs/reviews/findings_6_7.md`, with the
identical copy at the task-mandated bot path
`~/.hermes/bot/docs/reviews/findings_6_7.md`. No push was performed.
