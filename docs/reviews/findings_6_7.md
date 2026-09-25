# Offload review — routstr delist, findings 6–7 (circuit breaker, hygiene)

Sixth independent verification pass for findings 6–7, and the first AFTER the
round-2 fix commits: b879354 ("close cold-review round-2 must-fixes —
re-fetch confirmation, breaker, atomic writes, staleness guard, SLA wiring")
implemented the breaker this finding demanded, and 1c77910 deployed the TDD
contract suite to the bot paths. The fifth pass (commit abfdb8c) verified the
PRE-fix artifact and adjudicated 6 REFUTED-HIGH / 7 MEDIUM; nothing from that
verdict is carried over unverified. This session re-derived every claim
against the CURRENT deployed 829-line script.

Scope: original task item 6 (circuit breaker: 3 failed attempts → BLOCKED
state, exit code 3) and item 7 (hygiene: secrets, loops; with the series'
established 7c dry-run purity, 7d operational loop, 7e housekeeping sub-items).

**Artifact-path status (required report per task instructions):**

- `~/.hermes/bot/docs/routstr_delist_contract.md` — **MISSING — HIGH**
  (re-verified this session: `~/.hermes/bot/docs/` contains only `reviews/`
  and `routstr-delist.md`; no `*contract*` file anywhere under `~/.hermes/bot`).
  The contract role is filled by `docs/routstr-delist.md` — cited by the
  script itself at routstr_delist.py:2 — read end-to-end (197 lines) as the
  stand-in. This is the same standing HIGH reported by every prior pass.
- `~/.hermes/bot/scripts/routstr_delist.py` — present (829 lines), verified
  byte-identical to repo `src/routstr_delist.py` this session (`diff`: clean).
- `~/.hermes/bot/tests/test_routstr_delist.py` — present (752 lines): the
  25-case TDD contract suite, whose loader (contract:47-54) resolves
  `../scripts/routstr_delist.py` and therefore runs against the DEPLOYED
  script copy. 25/25 green this session. It is not (by design, docs:177-190)
  a copy of the repo main suite `tests/test_routstr_delist.py` (1172 lines,
  96 tests, also re-run this session: 96/96 green).
- `~/.hermes/bot/docs/routstr-delist.md` — 183 lines vs repo 197: stale ONLY
  in the contract-suite inventory paragraph (single diff hunk `176a177,190`;
  repo docs:177-190). Every section this review cites — breaker docs:76-79,
  dry-run docs:87-89, exit codes docs:153-154 — is byte-identical in both
  copies. LOW for this scope; the standing staleness note stands.

Conventions: `routstr_delist.py:N` = the script (both copies identical);
`contract:N` = bot deployed contract suite; `main:N` = repo main suite;
`docs:N` = repo `docs/routstr-delist.md`. Evidence basis, all this session:
all 829 script lines, all 752 contract-suite lines, and the full contract doc
read end-to-end; all three suites re-run — repo main 96/96, repo contract
25/25, bot-path contract 25/25 against the DEPLOYED script; 13 hermetic dynamic
probes (faked `_SshBackend`, tmpdir state, mocked `subprocess.run`, one real
CLI subprocess pair — no network, no artifact touched); live state file and
crontab re-read (read-only).

## Finding 6 — Circuit breaker (3 failed attempts → BLOCKED, exit 3) — **OK (residuals LOW)** — downgraded from REFUTED-HIGH

**Explicit statement: the fifth pass's REFUTATION is no longer true — the
circuit breaker now EXISTS in the deployed artifact and behaves as the task
body specifies.** Every element re-derived and probe-confirmed:

1. **Breaker vocabulary and state now exist.** `BREAKER_THRESHOLD = 3`
   (routstr_delist.py:77); durable `consecutive_failures` loaded with an
   isinstance guard and `blocked` flag at routstr_delist.py:543-546;
   incremented on a failed run at routstr_delist.py:724-731 with the BLOCKED
   marker written at :731 (`state["blocked"] = newly_blocked` where
   `newly_blocked = fails >= BREAKER_THRESHOLD`, :730); counter reset on a
   confirmed delist at routstr_delist.py:750-751 and on a successful relist
   at :636-637; explicit operator clear `--unblock` at routstr_delist.py:559-567
   (pops both keys, saves, lets the same run proceed).
2. **Exit code 3 exists and is reachable — measured on the real CLI.** The
   tripping failure returns `3 if newly_blocked else 1` (routstr_delist.py:739)
   and the blocked refusal returns 3 at routstr_delist.py:578 (process exit
   via `raise SystemExit(main())`, :829). Real-subprocess probe this session:
   a seeded `{"blocked": true, "consecutive_failures": 3}` state + `--manual`
   → rc 3, `action: "blocked"`, in 0.05 s — the refusal at :569-578 precedes
   backend construction, so an unreachable `--ssh-target` was never contacted;
   `--bogus` → rc 2 (argparse); `--status` → rc 0. Complete exit space
   **{0, 1, 2, 3}**, and 3 means exactly BLOCKED, documented at docs:153-154.
3. **Attempt 4 never runs — proven dynamically, both directions.** Hermetic
   probe: a permanently-failing backend driven through the real `rd.main()`
   five times on one persistent state → return codes `[1, 1, 3, 3, 3]` with
   per-run remote calls `[2, 2, 2, 0, 0]` (each failing run = initial pull +
   the one bounded in-run retry, routstr_delist.py:671-697; runs 4-5 refused
   before any backend call). Second probe: after tripping the breaker, the
   backend was HEALED and `--delist`, `--relist`, and `--manual` all still
   returned rc 3 `action: "blocked"` with ZERO backend calls. Pinned in the
   suites: main:845-860 (attempt 4 never runs, healed backend, `fb.calls ==
   []`), contract:601-612, and the relist path is guarded too
   (routstr_delist.py:569 precedes :600; main:877-892; probe: `--relist
   --relist-any --dry-run` on blocked state → rc 3, zero calls).
4. **Counter semantics: increment per RUN, not per attempt; reset on
   confirmed success.** The whole retry loop counts once (comment
   routstr_delist.py:664-665; pinned main:432-448 — transient failure retried
   in-run, 3 backend calls, counter still 0 after success). Probe: 2 failures
   then a healing `--manual` → rc 0, state `consecutive_failures: 0`,
   `blocked: false`. Pinned main:862-875 (delist success resets) and
   main:909-924 + probe (relist success also resets, :636-637). `--unblock`
   clears and the same run proceeds (main:894-907; contract:614-624). A
   verify-refuted lying pull counts as the failed attempt it is
   (contract:346-360, `consecutive_failures == 1`).
5. **BLOCKED is surfaced to the operator.** Trip output carries
   `consecutive_failures` and `blocked` in the JSON (routstr_delist.py:733-738);
   the refusal prints `action: "blocked"`, `ok: false`, `blocked: true`, the
   count, and the `--unblock` remedy (routstr_delist.py:572-577); `--status`
   reports both breaker fields read-only (routstr_delist.py:548-557, rc 0 —
   probe-confirmed while blocked). Durable-state BLOCKED marker pinned by the
   raw-file assertion contract:593-597 and main:841-843. Contract docs:
   docs:76-79.

Residual gaps, all LOW:

- **(a) The counter never decays across non-firing runs** — "3 consecutive
  failed runs" is in effect "3 cumulative failures since the last confirmed
  remote success or `--unblock`". Probes: fail ×2 → a QUIET run (rc 0,
  `action: none`) → counter still 2 → the next failure trips rc 3; same with
  a `preds_error` run (rc 1, `action: none`) interleaved. Mechanism: the
  quiet path routstr_delist.py:651-660 preserves prior keys via `update_state`
  and never touches the counter. This follows the doc's own reset rule ("Any
  confirmed success (delist or relist) resets the counter", docs:79), so it
  is documented behaviour — but stale failure debt from an old incident plus
  ONE new failure blocks on the first failure of a new incident, delaying a
  protective delist until an operator notices rc 3. Consider resetting (or
  decaying) the counter on any run that does not attempt a remote action.
- **(b) The halt depends on the BLOCKED write persisting** — `save_state`'s
  return is ignored at routstr_delist.py:732 (one of 8 ignored sites :565,
  :622, :629, :638, :654, :710, :732, :752; cross-ref findings_4_5.md
  residual). Probe: with the state directory made unwritable exactly at the
  tripping run, the CLI printed rc 3 / `blocked: true` but disk kept
  `consecutive_failures: 2` and no `blocked` key — and the next run made 2
  more remote pull attempts before re-tripping. Bounded (≤2 attempts per
  cadence tick) and self-healing on the first successful write, but the
  breaker is fail-open under persistent state-write failure.
- **(c) Asymmetric relist accounting, unstated in the docs** — a FAILED
  `--relist` never increments the counter (routstr_delist.py:626-632 touches
  none of the breaker keys; probe: seeded fails=2, failing relist → still 2,
  not blocked), while a successful relist DOES reset it (:636-637). docs:76-79
  defines reset but is silent on relist failures not counting. Harmless under
  documented usage (the cron path evaluates triggers; relist is manual,
  docs:143-151), worth one doc sentence.
- **(d) Dry-run interaction is over-strict one way, under-strict the other:**
  a BLOCKED state refuses even `--dry-run` previews (the :569 refusal
  precedes everything except `--status`/`--unblock`; probes: rc 3 on
  `--manual --dry-run` while blocked) — an operator cannot rehearse the
  clearing run without actually clearing; and `--unblock --dry-run` performs
  a REAL durable clear (probe: breaker keys absent from state afterwards, and
  a subsequent failing `--manual` run got rc 1, not 3) — a dry-run run with a
  durable side effect, in mild tension with docs:156 ("prints intent,
  executes nothing" — true for remote actions, not for breaker state).
- **(e) Cosmetic type-guard hole:** `isinstance(fails, int)` at
  routstr_delist.py:545 admits `True` (bool ⊂ int): a hand-corrupted state
  `{"consecutive_failures": true}` + one failure → counter 2 (probe). The
  variance guard excludes bool explicitly at :152; this one should too.
  Impact nil in practice.

**Verdict 6: OK — the must-fix is closed and regression-pinned on both
suites (main:815-924, contract:580-624). Residuals LOW as itemized.**

## Finding 7 — Hygiene (secrets, loops) — **OK (residuals LOW)** — downgraded from MEDIUM

### 7a. Secrets — **OK** (residual LOW)

Mechanisms unchanged from the fifth pass and now regression-pinned by
contract Case 11: the nsec is read from a file only inside
`publish_delist_event()` (routstr_delist.py:456-458) and reaches `nak`
exclusively via child env `NOSTR_SECRET_KEY` (routstr_delist.py:459-461) with
`--env-sec` (routstr_delist.py:446); the built argv (routstr_delist.py:442-448)
carries kind/tags/content/relays only. Probe this session: `--env-sec`
present, `--sec` absent, secret string NOT in argv; the identifier
`NOSTR_SECRET_KEY` appears at exactly two source sites (:429 default param
name, :460 env assembly). Never printed (nak output captured and discarded,
:461; `main()` prints only backend-result/state JSON). Never persisted: live
state file read this session — keys `delisted`/`last_reason`/`snapshot`/`ts`
only; every probe's full-cycle state key set (`ts`, `last_reason`,
`pulled_models`, `delisted`, `consecutive_failures`, `blocked`,
`last_dry_run`, `last_pull_error`) is credential-free; `last_pull_error`
stores only the backend result dict (stdout/stderr truncated to 200 chars,
routstr_delist.py:820). Exception surfaces are `str(exc)` of subprocess
failures (routstr_delist.py:825) — ssh argv + payload, no credential; the
dry-run stub echoes only `cmd[:2]` + a 120-char payload prefix
(routstr_delist.py:798-799). Pinned: contract:705-729 (secret absent from
captured logs, argv, and state; env-only delivery; kind 30078) and main:399.
Residual LOW: a failed publish is swallowed AND indistinguishable from
success — `except Exception: pass` then `return argv`
(routstr_delist.py:462-464); probe: a `nak` that raises still yields the argv
return. Callers ignore the return, no state note exists, doc-blessed
best-effort (docs:128) — operators get zero signal that the event channel is
dead.

### 7b. Loops in-process — **OK** (now including the new bounded while)

AST-enumerated over the deployed source this session: exactly ONE `while`
loop — routstr_delist.py:671, test `attempts < MAX_PULL_ATTEMPTS`
(`MAX_PULL_ATTEMPTS = 2`, :75), with `attempts += 1` first in the body
(:672) → at most 2 iterations by construction, and both `continue` branches
additionally guarded by `attempts < MAX_PULL_ATTEMPTS and
time.monotonic() < deadline` (:675-677, :695-696) — the deadline cap pinned
by main:450-463 (budget spent → exactly 1 attempt). Four `for` loops
(:112, :146, :204, :297) and seven comprehensions (:110, :308, :312, :479,
:597, :694, :746), all finite over in-memory lists; the payload-embedded
comprehension (:371) executes remotely inside a bounded round-trip. Both
subprocesses timeout-bounded: ssh `min(SSH_TIMEOUT_S, remaining)` with a
pre-check for an exhausted budget (routstr_delist.py:800-806), nak
`timeout=30` (:459). No unbounded iteration exists in-process.

### 7c. Dry-run purity — **OK** (all four fifth-pass side effects closed; residual LOW)

Re-probed independently, seeded-state and fresh-state:

1. **No publish in dry-run, either direction.** Both publish call sites
   (routstr_delist.py:639-640 relist, :755-756 delist) sit AFTER the dry-run
   early-returns (:615-625 relist, :699-717 delist). Pinned: contract:731-741
   — `--manual --dry-run --nsec <file>` spawns ZERO subprocesses
   (`recorded == []` with `subprocess.run` mocked).
2. **No durable `delisted` flip.** The dry paths write only `ts` +
   `last_dry_run` (:617-622, :703-710). Probe: seeded `delisted: true`
   survived both a dry delist and a dry relist untouched (a real relist
   would set it false); fresh-state dry delist leaves the key absent.
   Pinned: contract:743, :746-752; main:481-483.
3. **Dry relist does NOT pop `pulled_models`.** The pop lives only in the
   real success path (:635). Probe: seeded `pulled_models: ["gpt-4o",
   "llama-3"]` intact after `--relist --dry-run`.
4. **Dry delist does NOT write `pulled_models: []`.** The dry path never
   calls `update_state` (merge/capture only at :744-749, real path). Probe:
   fresh-state dry delist → state keys exactly `["last_dry_run", "ts"]`.

Together these close the fifth pass's blanket-relist arming chain (its items
3 and 4 fed finding 4's hazard; that hazard is independently closed by the
relist refusal at routstr_delist.py:602-611 + `--relist-any` opt-in, verified
by findings_4_5.md's re-adjudication). Dry-run failures are intent-only too:
no breaker tick, no `last_pull_error` (main:514-530). Residual LOW: a dry run
still bumps `ts` and writes `last_dry_run` to durable state — documented
intent recording (docs:87-89), benign; and `--unblock --dry-run` clears the
breaker for real (probe; see finding 6 residual (d)).

### 7d. The operational loop — **OK** (capped by the breaker; latent anyway)

The fifth pass's MEDIUM — cron re-attempting a failed pull forever — is
capped from the scheduler side by the now-implemented breaker: probe shows
runs 4+ make ZERO remote calls (rc 3 refusals), so a dead node sees at most
3 runs × 2 bounded attempts = 6 ssh round-trips before the breaker holds,
versus unlimited before; each refusal exits 3 with the `--unblock` remedy in
the JSON — cron-visible, not silent. The success-direction repeat publish
(every fired run while a level-based trigger holds, routstr_delist.py:755-756
behind the every-run fire gate :649) remains, mitigated by the
parametrized-replaceable kind-30078 (same `d` tag replaces, docs:124-130).
Re-verified live this session: `crontab -l` has ZERO routstr entries and
`/etc/cron.d` contains only anacron/e2scrub_all/sysstat — both loops remain
latent, as documented (docs:112-115). Residual LOW: while blocked, cron would
wake per cadence and exit 3 indefinitely until an operator intervenes —
correct signalling, but nothing escalates beyond the exit code.

### 7e. Permissions / housekeeping — **LOW**

`save_state` (routstr_delist.py:221-245) writes with default umask — live
state file observed mode 0o664 this session — and no chmod 600; impact nil,
the state is credential-free (7a). `save_state` return ignored at all 8 call
sites (:565, :622, :629, :638, :654, :710, :732, :752) — standing findings
4/5 residual, breaker-specific consequence covered in finding 6 residual
(b). Publish-failure swallow covered in 7a. The `--preds` feed, override
marker, and nsec file path carry no secret material into state or logs.

**Verdict 7: OK — secrets (7a) and loops (7b) clean and pinned; the 7c
dry-run side-effect chain and the 7d uncapped operational retry are closed
and regression-pinned (contract Case 11, main:466-530); residuals LOW as
itemized.**

---

Provenance: sixth independent verification pass for findings 6–7, first after
the round-2 fixes. Prior verdicts — Gate 2.5 cold review (commit 69d489c),
first offload pass (03c1d15), second (9e1bb1a), third (1cef973), fourth
(1655892), fifth (abfdb8c) — all adjudicated the PRE-fix artifact: 6
REFUTED-HIGH (no breaker, exit space {0,1,2}), 7 MEDIUM (dry-run side
effects, uncapped operational loop). This pass re-derived everything against
the current deployed 829-line script (byte-identical to repo src this
session): **both findings downgrade to OK** — the breaker exists, trips at
exactly 3, refuses attempt 4 and every remote action until `--unblock`, exits
3, resets on confirmed success, and is pinned by six dedicated tests
(main:815-924) plus contract Case 9; dry-run is intent-only in both
directions and secrets stay env-only. Suites this session: 96/96 (repo main)
and 25/25 (bot contract vs the deployed script). 13 hermetic probes, zero
network, zero artifact modification. `~/.hermes/bot` is not a git repository,
so the required local commit lands in the workspace repo (merchant-routing)
at `docs/reviews/findings_6_7.md`, with this identical copy at the
task-mandated bot path `~/.hermes/bot/docs/reviews/findings_6_7.md`.
