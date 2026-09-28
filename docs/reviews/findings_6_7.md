# Offload review — routstr delist, findings 6–7 (circuit breaker, hygiene)

Twenty-eighth independent offload pass on this card, re-derived from scratch this
session. The deployed script was re-read end-to-end (all 829 lines), the deployed
contract suite end-to-end (all 752 lines) and the design/contract document
end-to-end (all 197 lines). Every behavioural claim below was re-executed against
the current artifacts by `docs/reviews/routstr_f67_probes/probe_f67_pass28.py` →
raw output `probe_f67_pass28.out` — **42/42 checks passed**, zero network, zero
artifact mutation, all state on disk-backed tmp under `~/.cache` (host `/tmp` is
100 % full, `df` 5.5G/5.5G). Finding 6 was probed three ways: in-process through
the real `rd.main()` CLI surface, through the real deployed script driven as a
**subprocess** with only `ssh` intercepted by a logging PATH shim (modes
`dead`/`lying`/healthy), and structurally via AST. No internal is faked.

**Duplicate-dispatch note.** This deliverable already exists and is
committed-clean; this is the eleventh consecutive re-dispatch of the same body.
Per the standing convention on this board for a re-dispatched prose report, the
file is re-derived in place (self-contained, current pass ordinal) rather than
appended — the sibling files `findings_4_5.md` (now at its 25th pass) and
`findings_1_3.md` follow the same convention.

**Artifact-path status (the report the task instructions require).**
`~/.hermes/bot/docs/routstr_delist_contract.md` — **MISSING — HIGH.**
Re-verified this session: `ls` on that exact path → `No such file or directory`;
`find ~/.hermes/bot -iname '*contract*'` → **zero hits** (probe A1). The
task-mandated contract document is **unreviewable at that path**. The design
document that does exist — and that the suite itself names the frozen contract
(`contract:1`, "frozen contract: docs/routstr-delist.md") — is
`~/.hermes/bot/docs/routstr-delist.md`, 197 L, md5
`e385af98b9c142eec736672d4dcca290`, byte-identical to repo `docs/routstr-delist.md`
(probe A4/A7). It is cited below as `docs:N`. This is a task-path/layout defect
(or an unnoticed rename), **not** a missing design: the substance the task asks
me to review against is present under a different filename.

`~/.hermes/bot/scripts/routstr_delist.py` — present, 829 L, md5
`2ea724ef08d857cd7b88a957300e70b4`, byte-identical to repo `src/routstr_delist.py`
(probes A2/A5); cited as `src:N`. `~/.hermes/bot/tests/test_routstr_delist.py` —
present, 752 L, md5 `031851b356f0de4089512f02f13f05cc`, byte-identical to repo
`tests/test_routstr_delist_contract.py` (probes A3/A6); cited as `contract:N`. Its
loader (`contract:50-54`) resolves `../src` first then `../scripts`, and
`~/.hermes/bot/src/routstr_delist.py` **does not exist** (probe A10), so the
deployed-layout run provably exercises the DEPLOYED script copy.

Suites re-run this session after probing, all green, all md5 sums unchanged
afterwards: repo `pytest tests/test_routstr_delist_contract.py -q` → **25 passed**
(0.61 s); deployed-layout `cd ~/.hermes/bot && pytest tests/test_routstr_delist.py
-q` → **25 passed** (0.46 s); repo full `TMPDIR=~/.cache/pytest_tmp pytest tests/
-q` → **121 passed** (1.44 s; main 96 + contract 25). Live
`~/.hermes/bot/routstr_delist_state.json` re-read read-only (240 B, mode 0o664,
keys `[delisted, last_dry_run, last_reason, snapshot, ts]` — inside the
credential-free allowlist); `crontab -l` holds **0** routstr entries.
*Environmental note (not an artifact defect):* a plain repo-wide `pytest tests/`
fails on this host because pytest's default `tmp_path` roots in `/tmp` (100 %
full, `Errno 28`); the disk-backed `TMPDIR` run is the valid baseline.

---

## Finding 6 — circuit breaker (3 failed attempts → BLOCKED, exit code 3) — **OK** (residuals **LOW**)

**Explicit statement required by the task: the claim HOLDS on the deployed
artifact.** A breaker exists, trips at the configured threshold, writes a durable
BLOCKED marker, and exits 3. Requirement met; six residuals, all LOW, itemized at
the end.

1. **Breaker vocabulary and durable state exist.** `BREAKER_THRESHOLD = 3`
   (src:77); the counter is loaded with an isinstance guard (src:544-545) alongside
   `blocked = bool(state.get("blocked"))` (src:546). A failed run increments and
   writes BLOCKED at src:724-732 — `fails += 1` (src:724), `delisted = False`
   (src:726), `consecutive_failures = fails` (src:727), `newly_blocked = fails >=
   BREAKER_THRESHOLD` (src:730), `state["blocked"] = newly_blocked` (src:731)
   before `save_state` (src:732). Reset on a confirmed delist (src:750-751) and on
   a successful relist (src:636-637); operator clear via `--unblock` (src:561-567),
   which pops both keys and lets the same run proceed. Probe B4: after the third
   failing run the durable file reads `blocked: true`, `consecutive_failures: 3`.
2. **Exit code 3 exists, means exactly BLOCKED, and the exit space is
   {0,1,2,3}.** Trip returns `3 if newly_blocked else 1` (src:739); the blocked
   refusal returns 3 (src:578); process exit is via `raise SystemExit(main())`
   (src:828-829). Probe B1: 5 failing real-CLI runs → rcs `[1,1,3,3,3]`. Probe B8:
   `--bogus` → 2 (argparse, real subprocess); quiet run → 0 (src:660);
   garbage `--preds` → 1; healthy `--manual --dry-run` → 0. Documented at
   docs:153-154.
3. **Attempt 4 never runs — proven on the real CLI.** Probe B2: per-run ssh
   invocations `[2,2,2,0,0]` — runs 4 and 5 made **zero** remote calls. Probe B3:
   all 6 pre-trip round-trips carried the pull payload
   (`UPDATE models SET enabled=0`) and the verify re-fetch (`SELECT COUNT(*)`) was
   never reached. The refusal (src:569-578) precedes backend construction
   (src:666), trigger evaluation (src:646) and every dry-run branch. Probe B5: with
   the breaker open, `--relist`, `--manual`, `--manual --dry-run` and
   `--relist --relist-any` each return rc 3 / `action: "blocked"` with **zero**
   round-trips. Probe B6: `--status` (src:548-557) reports both breaker fields
   read-only (rc 0) and does **not** clear. Probe B7: `--unblock --manual` heals
   (`blocked: false`, `consecutive_failures: 0`, `delisted: true`).
4. **Counter ticks once per RUN, not per attempt.** The whole bounded retry loop
   counts once: `while attempts < MAX_PULL_ATTEMPTS` (src:671) with
   `MAX_PULL_ATTEMPTS = 2` (src:75) and `attempts += 1` as the body's first
   statement (src:672); both `continue` branches are additionally deadline-guarded
   (src:675-676, src:695). Probe B3: 3 dead runs produced exactly 6 pull payloads
   and zero verify calls — so the trip lands after up to 6 remote attempts, not 3
   (interpretation note below). AST probe B15/B15b confirms exactly one `while`,
   zero `while True`.
5. **BLOCKED is surfaced to the operator, not silent.** The refusal JSON carries
   `action: "blocked"`, `ok: false`, `blocked: true`, the count and the literal
   `--unblock` remedy (src:572-577); the trip output carries `consecutive_failures`
   and `blocked` (src:733-738); `--status` reports both (src:548-557). Contract doc
   docs:76-79; pinned by `contract:593-597` (`'"blocked": true' in raw`).
6. **Pinned by dedicated tests.** Contract Case 9 (`contract:581-624`) covers the
   trip (`contract:582-599`, `assert rcs == [1, 1, 3]` at contract:591, `'"blocked":
   true' in raw` at contract:594, `kinds() == ["pull"] * 6` at contract:599), the
   refusal-before-any-call (`contract:601-612`, zero new calls at contract:612) and
   the `--unblock` reset (`contract:614-624`). Plus the main-suite breaker tests.

**Residuals — all LOW, all re-probed this session:**

- **(a) The counter never decays across non-firing runs.** src:651-660 preserves
  prior keys and never touches the counter, so stale failure debt survives. Probe
  B11: fail ×2 → quiet run (rc 0, counter still 2) → ONE new failure trips rc 3
  (`consecutive_failures: 3`, `blocked: true`). A stale count plus one new failure
  blocks the first failure of a *new* incident, delaying a protective delist until
  an operator notices rc 3. The documented reset rule (docs:79) does not cover this.
- **(b) Fail-open if the BLOCKED write cannot persist.** `save_state`'s return is
  ignored at src:732 — one of 8 bare `Expr` call sites (src:565, :622, :629, :638,
  :654, :710, :732, :752; AST-enumerated with a parent map, probe B16: 8/8 returns
  ignored). Probe B13: with the state directory chmod 0500 for the tripping run,
  the CLI printed rc 3 / `blocked: true` while disk kept `consecutive_failures: 2`
  / no `blocked` key. Bounded (≤2 attempts per cadence tick) and self-healing on
  the first successful write, but a breaker that can fail open. Cross-ref
  findings_4_5 residual.
- **(c) Asymmetric relist accounting, unstated in docs.** A FAILED `--relist`
  never increments the counter (src:626-632 touches no breaker key; probe B9: seeded
  fails=2 + dead node → rc 1, still 2, no `blocked` key) while a successful relist
  DOES reset it (src:636-637; probe B10: rc 0 → counter 0, `pulled_models` poppped).
  docs:76-79 is silent on this. Harmless under documented usage (relist is manual),
  worth one doc sentence.
- **(d) Dry-run interaction, over-strict one way and under-strict the other.**
  A BLOCKED state refuses even `--dry-run` previews (refusal src:569 precedes
  everything except `--status`/`--unblock`; probe B5: `--manual --dry-run` rc 3,
  zero round-trips) — no rehearsal of the clearing run without actually clearing;
  and `--unblock --dry-run` performs a REAL durable clear (the `--unblock` block at
  src:561-565 executes before the dry-run early-returns), a dry run with a durable
  side effect, in mild tension with docs:87-89.
- **(e) Cosmetic type-guard hole.** `isinstance(fails, int)` at src:545 admits
  `True` (bool ⊂ int): probe B12 with a seeded `{"consecutive_failures": true}`
  plus one failure → disk counter 2. The sibling variance guard excludes bool
  explicitly (src:152, `isinstance(unc, bool)`); this one should too. Impact nil in
  practice.
- **(f) A failed fired run force-clears the durable `delisted` flag.** The failure
  path writes `state["delisted"] = False` unconditionally (src:726, "keep the key
  greppable"), so a failed re-delist over a prior confirmed delist flips the
  publisher-read flag to `delisted=false` even though the remote listing is still
  pulled. Probe B14: confirmed delist (`delisted: true`) → one dead-node fired run
  → `delisted: false` on disk at rc 1, while the `snapshot` baseline is correctly
  preserved. A quiet run correctly preserves the flag (src:651-653), so the
  asymmetry is specific to the failure branch. Impact LOW (the publisher only
  over-advertises during an outage, and the next success re-asserts), but the flag
  is the ADR-007 "flag in the objects that publishes the listing" (docs:122-123)
  and this is a real divergence between flag and reality.
- **Interpretation note (LOW).** The task wording "3 failed *attempts*" is
  implemented as 3 consecutive failed **RUNS**, each of which may spend
  `MAX_PULL_ATTEMPTS = 2` ssh round-trips (src:75, src:671) — so the trip lands
  after up to 6 remote attempts, not 3. This reading is explicit and consistent:
  docs:76 ("3 consecutive failed runs"), pinned by contract:591
  (`rcs == [1, 1, 3]` over three runs).

**Verdict 6: OK — the requirement is met on the deployed artifact**, pinned by
Contract Case 9 (contract:581-624) and the main-suite breaker tests. Residuals LOW
as itemized.

---

## Finding 7 — hygiene (secrets, loops) — **OK** (residuals **LOW**)

### 7a. Secrets — OK (residual LOW)

The nsec is read from a file only inside `publish_delist_event()` (src:457-458) and
reaches `nak` exclusively via the child environment variable `NOSTR_SECRET_KEY`
(src:459-460) with `--env-sec` (src:446); the identifier text appears at exactly
two source sites (src:429, src:460). Probe C1 against the deployed module, full
`--manual --nsec` cycle with the real `subprocess.run` captured: exactly ONE nak
spawn; `--env-sec` present and `--sec` absent from argv; `NOSTR_SECRET_KEY` present
ONLY in the child env with the exact secret value. Probe C2: the secret is absent
from captured stdout, from the argv dump and from the durable state file; the argv
carries `30078` and `d:routstr-delist` and the three `wss://` relays; the live
state keys and the written state keys are within the credential-free allowlist
(`ts`/`delisted`/`snapshot`/`last_reason`/`pulled_models`/`consecutive_failures`/
`blocked`/`last_pull_error`/`last_dry_run`; probes A12, C10). Probe C3:
`build_delist_event` returns None when the sec file is missing (src:437-438) and
when it is None. The doc explicitly rejects `--sec` for ps-leak reasons
(docs:126-127). Exception surfaces are `str(exc)` of subprocess failures (src:825)
— ssh argv + payload, which carry no credential. Pinned: contract:690-752
(`--env-sec`/`--sec` at contract:726, env-only secret at contract:727, kind 30078 at
contract:728, `d:routstr-delist` at contract:729).

Residual LOW: a failed publish is swallowed AND indistinguishable from success —
`except Exception: pass` then `return argv` (src:462-464, probe C4); callers ignore
the return (src:640, src:756); no state note is written. Doc-blessed best-effort
(docs:128), but operators get zero signal that the event channel is dead.

### 7b. Loops in-process — OK

AST re-inventory over the deployed source (probes B15/B15b/C12): exactly ONE
`while` (src:671), bounded by `attempts < MAX_PULL_ATTEMPTS` (= 2, src:75) with
`attempts += 1` body-first (src:672) and both `continue` branches deadline-guarded
(src:675-676, src:695) — verified structurally, not just by grep: **zero
`while True`** exists. Four `for` loops (src:112, :146, :204, :297) and seven
comprehensions (src:110, :308, :312, :479, :597, :694, :746), all finite over
in-memory lists. `subprocess.run` sites: exactly 2 (src:459, :808), both carrying
`timeout=` (nak 30 s at src:459; ssh `min(SSH_TIMEOUT_S, remaining)` from
src:800-806, passed at src:808); `shell=True` count 0; no `os.system`/`os.popen`/
`os.spawn`. Probe C9 (real CLI, healthy node): exactly 2 round-trips (1 pull +
1 verify). Probe C9b (real CLI, lying node): bounded to 4 round-trips (2 attempts ×
[pull+verify]) then rc 1 / `delist_failed`. No unbounded iteration exists.

### 7c. Dry-run purity — OK (residual LOW)

Re-probed in-process against the deployed module with **all** subprocess spawns
intercepted (an exploding stub that records and raises on ANY spawn — stronger than
the suite's backend swap). Probe C5: a `--manual --dry-run --nsec` run spawned ZERO
subprocesses — not even ssh (the dry stub at src:797-799 returns before src:808)
and no nak (both publish sites src:639-640 / src:755-756 sit after the dry
early-returns src:615-625 / src:699-717). State effects: probe C7 — a fresh-state dry
delist writes exactly `["last_dry_run", "ts"]` (no `delisted` flip, no
`pulled_models`, no breaker keys); probe C6 — a seeded `delisted: true` +
`pulled_models` + `consecutive_failures: 1` + `snapshot` state survived
`--relist --dry-run` with all four intact (the `pop` lives only in the real success
path, src:635); probe C8 — the dry-FAILURE branch (src:717) exits 1 and writes only
`last_dry_run`/`ts` plus the preserved seeded keys (no breaker keys, no
`last_pull_error`). Pinned: contract:731-752.

Residual LOW: the dry run still bumps `ts` and writes `last_dry_run` — documented
intent recording (docs:87-89), benign; and `--unblock --dry-run` clears the breaker
for real (finding-6 residual (d)).

### 7d. The operational loop — OK (capped by the breaker; latent anyway)

Cron re-attempting a failed pull is capped from the scheduler side by the breaker:
real-CLI probe per-run deltas `[2,2,2,0,0]` (B2), so a dead node sees at most
3 runs × 2 bounded attempts = 6 round-trips before the breaker holds, each
subsequent tick exiting 3 with the `--unblock` remedy in the JSON — cron-visible,
not silent. Re-verified live: `crontab -l` has ZERO routstr entries (probe A11) —
the loop remains latent, as documented (docs:112-115).

Residual LOW: while blocked, cron would wake per cadence and exit 3 indefinitely
until an operator intervenes — correct signalling, but nothing escalates beyond the
exit code; and a dead event channel (7a residual) is indistinguishable from a live
one.

### 7e. Permissions / housekeeping — LOW

`save_state` (src:221-245) writes with the default umask — probe C10: state file
mode 0o664 (umask 0o2) and credential-free (7a allowlist), so impact nil; AST/text
check C11 confirms no `os.chmod` anywhere in the module. `save_state`'s return is
ignored at all 8 call sites (src:565, :622, :629, :638, :654, :710, :732, :752 — AST
enumerated with a parent map, probe B16: every one a bare `Expr` statement, none
assigned or checked); the breaker-specific consequence is finding-6 residual (b),
the standing findings-4/5 residual otherwise. No `TODO`/`FIXME`/`XXX`/`HACK` marker
exists in the script (probe C11: 0 hits); the `--preds`/`--override`/`--nsec` paths
carry no secret material into state or logs (7a).

**Verdict 7: OK — secrets (7a) env-only and nowhere else, loops (7b) all bounded by
construction, dry-run (7c) intent-only in both directions and spawn-free,
operational loop (7d) breaker-capped and latent; residuals LOW as itemized.**

---

**Provenance.** Twenty-eighth independent offload pass for findings 6–7, against
the unchanged artifact set (script md5 `2ea724ef…`, suite md5 `031851b3…`, doc md5
`e385af98…` — all byte-identical to repo, re-checked after probing). Fresh probe
code written this session (nothing reused from the prior passes):
`probe_f67_pass28.py` → `.out`, **42/42 PASS** — 12 artifact-identity checks
(group A), 17 breaker checks (group B, including 13 real-CLI subprocess probes on
the deployed script with only `ssh` PATH-shimmed, in modes `dead`/`lying`/healthy),
13 hygiene checks (group C). Five probe-side bugs were found and fixed before the
green run (a stale-buffer line-delta for the ssh log, a backend not swapped for the
post-quiet failure leg, two `None`-vs-`False` key-presence assertions, a missing
shim-mode switch for the lying-node leg) — all five were harness defects, not
artifact defects; the FAIL→PASS details are in `.out`. Suites: repo contract 25/25,
deployed-layout contract 25/25 against the deployed script, repo full 121/121
(disk-backed `TMPDIR`; the default `/tmp` run fails on Errno 28 — host disk
exhaustion, not an artifact defect). Required artifact-path report:
`routstr_delist_contract.md` **MISSING at the bot path — HIGH** (re-verified);
`routstr-delist.md` byte-identical to repo. `~/.hermes/bot` is not a git repository,
so the required local commit lands in the workspace repo (`merchant-routing`) at
`docs/reviews/findings_6_7.md`, with the identical copy at the task-mandated bot
path `~/.hermes/bot/docs/reviews/findings_6_7.md`. No push was performed.
