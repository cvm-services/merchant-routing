# Offload review — routstr delist, findings 6–7 (circuit breaker, hygiene)

Eighth independent verification pass for findings 6–7, on the artifact set the
sixth pass (commit 8c8f621) downgraded to OK/OK after the round-2 fixes
(b879354 breaker, 1c77910 contract-suite deploy) and the seventh pass
(commit 1f9e327) confirmed. Nothing is carried over unverified: every citation
below was re-read in the deployed artifacts this session, both suites were
re-run green, and every dynamic claim was re-probed — with the second pass in a
row driving the REAL deployed CLI as a subprocess for finding 6 (only `ssh`
intercepted by a logging PATH shim, no faked `_SshBackend`), so trip
sequencing, per-run remote-attempt counts, exit codes and durable-state effects
were observed on the deployed script itself.

Scope: original task item 6 (circuit breaker: 3 failed attempts → BLOCKED
state, exit code 3) and item 7 (hygiene: secrets, loops; with the series'
established 7c dry-run purity, 7d operational loop, 7e housekeeping sub-items).

**Artifact-path status (required report per task instructions):**

- `~/.hermes/bot/docs/routstr_delist_contract.md` — **MISSING — HIGH**
  (5th consecutive pass, re-verified this session: `find ~/.hermes/bot -name
  '*contract*'` → zero hits; `~/.hermes/bot/docs/` holds only `reviews/` and
  `routstr-delist.md`). The contract role is filled by the deployed
  `~/.hermes/bot/docs/routstr-delist.md` (197 lines) — cited by the script
  itself at routstr_delist.py:2 — read end-to-end as the stand-in, plus the
  byte-identical repo copy `docs/routstr-delist.md`.
- `~/.hermes/bot/scripts/routstr_delist.py` — present, 829 lines, md5
  `2ea724ef08d857cd7b88a957300e70b4`, sha256 `6a5774c07e23dcbd…` —
  byte-identical to repo `src/routstr_delist.py` this session.
- `~/.hermes/bot/tests/test_routstr_delist.py` — present, 752 lines, md5
  `031851b356f0de4089512f02f13f05cc` — byte-identical to repo
  `tests/test_routstr_delist_contract.py`; its loader (tests:47-54) resolves
  `../scripts` and therefore runs against the DEPLOYED script copy. 25/25
  green this session (0.28 s) in a hermetic `../scripts` layout.
- `~/.hermes/bot/docs/routstr-delist.md` — **now byte-identical** to repo
  `docs/routstr-delist.md` (197 lines, md5 `e385af98b9c142eec736672d4dcca290`;
  bot mtime 2026-09-25 22:35 vs repo 01:10). The LOW staleness residual
  standing since pass 5 (bot copy short by the contract-suite paragraph) is
  **HEALED** this session.

Conventions: `routstr_delist.py:N` = the script (both copies identical);
`contract:N` = deployed contract suite; `main:N` = repo main suite
`tests/test_routstr_delist.py` (1172 lines); `docs:N` = `docs/routstr-delist.md`
(repo copy == deployed copy). Evidence basis, all this session: all 829 script
lines and all 752 contract-suite lines read end-to-end; suites re-run — repo
full 121/121 (0.48 s: main 96 + contract 25), deployed-layout contract 25/25
(0.28 s) against the deployed script; 48 hermetic probe checks (28 real-CLI
breaker probes on a PATH-shimmed `ssh` + 20 in-process/AST hygiene probes),
zero network, zero artifact modification, all state under a disk-backed
TMPDIR. Host note: `/tmp` (tmpfs) was 100 % full mid-session, which produced
one spurious pytest run (`tmp_path` EIO: 5 failed / 21 errors); with TMPDIR on
disk the repo suite is 121/121 in 5/5 + 1/1 consecutive runs — an environment
artifact, not a suite defect. Live state file and crontab re-read read-only.

## Finding 6 — Circuit breaker (3 failed attempts → BLOCKED, exit 3) — **OK (residuals LOW)**

Re-adjudicated from scratch on real-CLI evidence. Every element of the
task-body requirement re-derived:

1. **Breaker vocabulary and state exist in the deployed artifact.**
   `BREAKER_THRESHOLD = 3` (routstr_delist.py:77); durable counter loaded with
   an isinstance guard and `blocked` flag (routstr_delist.py:543-546);
   increment + BLOCKED write on a failed run (routstr_delist.py:724-731, the
   marker `state["blocked"] = newly_blocked` with
   `newly_blocked = fails >= BREAKER_THRESHOLD` at :730-731); reset on a
   confirmed delist (routstr_delist.py:750-751) and on a successful relist
   (:636-637); operator clear `--unblock` pops both keys and lets the same run
   proceed (routstr_delist.py:559-567).
2. **Exit code 3 exists, means exactly BLOCKED, and the full exit space is
   {0,1,2,3}.** Trip returns `3 if newly_blocked else 1` (routstr_delist.py:739);
   the blocked refusal returns 3 at :578 (process exit via
   `raise SystemExit(main())`, :828-829). Real-CLI probes this session: five
   failing runs → rcs `[1,1,3,3,3]`; quiet run → rc 0; `preds_error` run →
   rc 1; `--dry-run` success → rc 0; `--bogus` → rc 2 (argparse). Documented at
   docs:153-154.
3. **Attempt 4 never runs — proven on the real CLI, both directions.**
   Probe: five `--manual` runs against a dead (shimmed) node on one durable
   state → per-run ssh invocations `[2,2,2,0,0]`; the 6 attempts before the
   trip were all pull payloads (`UPDATE models SET enabled=0`), the verify
   re-fetch was never reached (0 `SELECT COUNT` calls); runs 4-5 made ZERO
   remote calls. Healed-node probes on the tripped state: `--manual`,
   `--relist`, `--relist --relist-any` and `--manual --dry-run` all rc 3
   `action: "blocked"` with zero ssh calls — the refusal at
   routstr_delist.py:569-578 precedes backend construction (:666), trigger
   evaluation (:646), and every dry-run branch. `--status` surfaces
   `blocked`/`consecutive_failures` read-only (rc 0, zero calls) and does NOT
   clear (probe: the next run is still refused rc 3). Pinned: main:845-860,
   main:877-892, contract:601-612.
4. **Counter semantics: one tick per RUN, reset on confirmed success.** The
   whole bounded retry loop counts once (comment routstr_delist.py:664-665;
   the loop is one `while attempts < MAX_PULL_ATTEMPTS` (:671,
   `MAX_PULL_ATTEMPTS = 2` :75, `attempts += 1` body-first :672) with both
   `continue` branches additionally guarded by
   `attempts < MAX_PULL_ATTEMPTS and time.monotonic() < deadline` :675-677,
   :695-696). Real-CLI probe: `--unblock --manual` on a tripped state with a
   healed node → rc 0 confirmed delist, state `consecutive_failures: 0`,
   `blocked: false`. Pinned: main:432-448, main:450-463; verify-refuted lying
   pull counts as the failed attempt it is (routstr_delist.py:689-694;
   contract:346-360).
5. **BLOCKED is surfaced to the operator.** Trip output carries
   `consecutive_failures` and `blocked` (routstr_delist.py:733-738); the
   refusal prints `action: "blocked"`, `ok: false`, `blocked: true`, the
   count, and the literal `--unblock` remedy (:572-577 — probe-confirmed in
   the JSON); `--status` reports both breaker fields (:548-557). Durable
   marker pinned by the raw-file assertion `'"blocked": true' in raw`
   (contract:593-597). Contract docs:76-79.

Residual gaps, all LOW (all re-probed this session, all unchanged):

- **(a) The counter never decays across non-firing runs.** Probe: fail ×2 →
  QUIET run (rc 0, `action: none`, counter still 2) → `preds_error` run (rc 1,
  `action: none`, counter still 2) → one new failure trips rc 3. Mechanism: the
  quiet path routstr_delist.py:651-660 preserves prior keys and never touches
  the counter. Documented (reset rule docs:79) but stale failure debt plus ONE
  new failure blocks the first failure of a new incident, delaying a protective
  delist until an operator notices rc 3.
- **(b) The halt depends on the BLOCKED write persisting — fail-open under
  state-write failure.** `save_state`'s return is ignored at
  routstr_delist.py:732 (one of 8 bare sites :565, :622, :629, :638, :654,
  :710, :732, :752 — AST-enumerated this pass). Real-CLI probe: with the state
  directory chmod 0500 exactly at the tripping run, the CLI printed rc 3 /
  `blocked: true` while disk kept `consecutive_failures: 2` and
  `blocked: false`; after restoring the mode the next run made 2 more ssh
  attempts before re-tripping. Bounded (≤2 attempts per cadence tick) and
  self-healing on the first successful write; still a fail-open breaker.
  Cross-ref findings_4_5.md residual.
- **(c) Asymmetric relist accounting, unstated in docs.** A FAILED `--relist`
  never increments the counter (routstr_delist.py:626-632 touches no breaker
  key; probe: seeded fails=2, dead node, `--relist` → rc 1, still 2, not
  blocked, `pulled_models` kept) while a successful relist DOES reset it
  (:636-637; probe: seeded fails=1 → rc 0, counter 0). docs:76-79 is silent on
  this. Harmless under documented usage (relist is manual, docs:143-151);
  worth one doc sentence.
- **(d) Dry-run interaction: over-strict one way, under-strict the other.** A
  BLOCKED state refuses even `--dry-run` previews (refusal :569 precedes
  everything except `--status`/`--unblock`; probe rc 3, zero calls) — no
  rehearsal of the clearing run without actually clearing; and
  `--unblock --dry-run` performs a REAL durable clear (probe: breaker keys
  absent from state afterwards; a subsequent failing `--manual` run got rc 1
  with 2 attempts, not rc 3) — a dry run with a durable side effect, in mild
  tension with docs:156.
- **(e) Cosmetic type-guard hole.** `isinstance(fails, int)` at
  routstr_delist.py:545 admits `True` (bool ⊂ int): probe with seeded
  `{"consecutive_failures": true}` + one failure → disk counter 2. The variance
  guard excludes bool explicitly at :152-153; this one should too. Impact nil
  in practice.

**Verdict 6: OK — requirement met on the deployed artifact and pinned by six
dedicated main-suite tests (main:816-925, tests at :828/:845/:862/:877/:894/
:909) plus contract Case 9 (contract:581-624); residuals LOW as itemized.**

## Finding 7 — Hygiene (secrets, loops) — **OK (residuals LOW)**

### 7a. Secrets — **OK** (residual LOW)

The nsec is read from a file only inside `publish_delist_event()`
(routstr_delist.py:457-458) and reaches `nak` exclusively via child env
`NOSTR_SECRET_KEY` (routstr_delist.py:459-461) with `--env-sec`
(routstr_delist.py:446); the identifier appears at exactly two source sites
(:429 default param, :460 env assembly — AST/grep-enumerated). In-process probe
against the deployed module this session, full `--manual --nsec` cycle:
exactly one nak publish; `--env-sec` present and `--sec` absent from argv; the
secret present ONLY in the child env; argv carries kind 30078, `d:routstr-delist`
and the three wss:// relays; the secret absent from captured stdout, the
durable state file, and the argv dump; state keys are within the credential-free
allowlist (`ts`/`delisted`/`snapshot`/`last_reason`/`pulled_models`/
`consecutive_failures`/`blocked`). Never printed (nak output captured and
discarded, :461), never persisted — live state file re-read this session
(`~/.hermes/bot/routstr_delist_state.json`, 240 B, mode 0o664): keys
`delisted`/`last_dry_run`/`last_reason`/`snapshot`/`ts` only. Exception
surfaces are `str(exc)` of subprocess failures (:825) — ssh argv + payload, no
credential; the dry-run stub echoes only `cmd[:2]` + a 120-char payload prefix
(:798-799). Pinned: contract:705-729. Residual LOW: a failed publish is
swallowed AND indistinguishable from success — `except Exception: pass` then
`return argv` (routstr_delist.py:462-464; probe: a raising nak still yields a
clean rc 0 run and returns the argv); callers ignore the return, no state note,
doc-blessed best-effort (docs:128) — operators get zero signal the event channel
is dead.

### 7b. Loops in-process — **OK**

AST re-inventory over the deployed source this session: exactly ONE `while`
(routstr_delist.py:671) bounded by `attempts < MAX_PULL_ATTEMPTS` (=2, :75) with
`attempts += 1` body-first (:672) and both `continue` branches deadline-guarded
(:675-677, :695-696). Four `for` loops (:112, :146, :204, :297) and seven
comprehensions (:110, :308, :312, :479, :597, :694, :746), all finite over
in-memory lists; the payload-embedded comprehension (:371) executes remotely
inside a bounded round-trip. Both subprocess spawns timeout-bounded: nak
`timeout=30` (routstr_delist.py:459), ssh `min(SSH_TIMEOUT_S, remaining)` with a
pre-check for an exhausted budget (:800-806, `timeout=timeout` kwarg at :808-809)
— AST-confirmed `timeout=` on exactly those two calls. `shell=True` count 0;
`subprocess.run` sites exactly 2 (:459, :808). No unbounded iteration exists.

### 7c. Dry-run purity — **OK** (residual LOW)

Re-probed in-process against the deployed module with ALL subprocess spawns
intercepted (stronger than the suite's backend swap): a `--manual --dry-run
--nsec` run spawned ZERO subprocesses — not even ssh (the dry stub at
routstr_delist.py:797-799 returns before :808) and no nak (both publish sites
:639-640, :755-756 sit after the dry early-returns :615-625, :699-717). State
effects probed: fresh-state dry delist writes exactly `["last_dry_run", "ts"]` —
no `delisted` flip, no `pulled_models`, no breaker keys; a seeded `delisted:
true` + `pulled_models` + `consecutive_failures: 1` + `snapshot` state survived
`--relist --dry-run` with all intact (the pop lives only in the real success
path, :635). A dry FAILURE exits 1 and writes neither breaker keys nor
`last_pull_error` (probe: keys `["last_dry_run", "ts"]` only; cross-ref
main:514-530). Pinned: contract:731-752. Residual LOW: the dry run still bumps
`ts` and writes `last_dry_run` — documented intent recording (docs:87-89),
benign; and `--unblock --dry-run` clears the breaker for real (finding 6
residual (d)).

### 7d. The operational loop — **OK** (capped by the breaker; latent anyway)

Cron re-attempting a failed pull is capped from the scheduler side by the
breaker: real-CLI probe runs 4+ made ZERO ssh calls (per-run deltas
`[2,2,2,0,0]`), so a dead node sees at most 3 runs × 2 bounded attempts = 6
round-trips before the breaker holds, each subsequent tick exiting 3 with the
`--unblock` remedy in the JSON — cron-visible, not silent. The
success-direction repeat publish (every fired run while a level-based trigger
holds, routstr_delist.py:755-756 behind the every-run fire gate :649) remains,
mitigated by the parametrized-replaceable kind-30078 (same `d` tag replaces,
docs:124-130). Re-verified live: `crontab -l` has ZERO routstr entries — the
loop remains latent, as documented (docs:112-115). Residual LOW: while blocked,
cron would wake per cadence and exit 3 indefinitely until an operator
intervenes — correct signalling, but nothing escalates beyond the exit code.

### 7e. Permissions / housekeeping — **LOW**

`save_state` (routstr_delist.py:221-245) writes with default umask — probe
state file mode 0o664 (umask 0o2), credential-free (7a), so impact nil; the
deployed script is 0o775 (executable as documented), test/doc copies 0o600.
`save_state` return ignored at all 8 bare call sites (:565, :622, :629, :638,
:654, :710, :732, :752 — AST-enumerated, every site an `Expr` statement, none
assigned/checked); breaker-specific consequence in finding 6 residual (b),
standing findings 4/5 residual otherwise. No override marker exists live; the
`--preds`/`--override`/`--nsec` paths carry no secret material into state or
logs (7a).

**Verdict 7: OK — secrets (7a) env-only and nowhere else, loops (7b) all
bounded by construction, dry-run (7c) intent-only in both directions and
spawn-free, operational loop (7d) breaker-capped and latent; residuals LOW as
itemized.**

---

Provenance: eighth independent verification pass for findings 6–7. Prior
verdicts: passes 1-5 (pre-fix) adjudicated 6 REFUTED-HIGH / 7 MEDIUM; sixth
pass (8c8f621) downgraded both to OK; seventh pass (1f9e327) confirmed both.
This pass re-derived everything against the unchanged deployed 829-line script
(md5/sha256-verified byte-identical to repo src) and CONFIRMS both OK verdicts
on fresh evidence: breaker trips at exactly 3, refuses attempt 4 and every
remote action (including dry-run) until `--unblock`, exits 3, resets on
confirmed success; secrets stay env-only; dry-run spawns nothing. No deployment
asymmetry affects these two findings: the deployed contract suite independently
pins the breaker (Case 9, contract:581-624), dry-run purity (contract:731-752)
and secret hygiene (Case 11, contract:689-752), and it passed 25/25 against the
deployed script this session. Suites this session: deployed-layout contract
25/25 (0.28 s), repo full 121/121 (0.48 s). 48 hermetic probe checks (28
real-CLI breaker probes on a PATH-shimmed ssh, 20 in-process spawn/secret/AST
probes), zero network, zero artifact modification. Artifact report: contract md
STILL MISSING at the bot path (**HIGH**, 5th consecutive pass); bot
`routstr-delist.md` staleness **healed** (now byte-identical). `~/.hermes/bot`
is not a git repository, so the required local commit lands in the workspace
repo (merchant-routing) at `docs/reviews/findings_6_7.md`, with the identical
copy at the task-mandated bot path
`~/.hermes/bot/docs/reviews/findings_6_7.md`.
