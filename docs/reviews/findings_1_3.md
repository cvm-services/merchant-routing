# Offload review — routstr delist, findings 1–3 (safety, confirmation, fail-safe)

Fourteenth offload pass for findings 1–3, re-derived from primary sources in this
session against the CURRENT artifacts. Scope, per the original task: **item 1**
safety (delisting the SALE must never disable the routstr provider or touch the
T470 flat-router ladder), **item 2** post-delisting confirmation via re-fetch,
**item 3** fail-safe behaviour on absent, garbage and stale monitor signals.

This dispatch repeated a task whose deliverable already existed from thirteen
earlier passes at this path, so the pass was handled as a re-derivation: the
document below was rewritten in place from primary evidence collected in this
session, not appended to. Both deployed artifacts were confirmed byte-identical
to the repo copies before any analysis (md5, probe A0a/A0b/A0c), so the verdicts
are re-derived against the same bytes the earlier passes saw; they came out
unchanged, and the corrections below are all defects in the *review record*, not
in the reviewed code. Three new fail-safe-direction observations were measured
this pass (residuals (g)–(i) in Finding 3).

Method this pass: the script was read end-to-end in both copies, the contract
suite read end-to-end, every cited line re-checked against its file, all
SQL/subprocess/write-path inventories re-run on the parsed source (AST, not grep
prose), both suites executed, and a fresh hermetic probe harness
(`docs/reviews/routstr_f13_probes/probe_f13_pass14.py`, written for this pass, not
reused from any earlier one) executed **79 checks**: **79/79 PASS**, output
archived at `docs/reviews/routstr_f13_probes/pass14_output.txt`. The same harness
was first run against the previous (thirteenth-pass) copy of this document and
scored **76/76 PASS** — that pre-rewrite transcript is archived at
`docs/reviews/routstr_f13_probes/pass14_output_predeliverable.txt`. Unlike the
thirteenth pass, the pre-deliverable run caught **no** new record defect
(its `D5` name pin audit was clean, because the thirteenth pass had just fixed
that pin); the corrections below come from re-reading the cited source regions
and from re-measuring the citation inventory, and each is stated with the
measurement that produced it. The probe replaces only the ssh boundary: it
EXECUTES the module's own payloads against a stand-in node holding a live
`models` (SALE listing) table, a live `upstream_providers` (provider ladder)
table and a ladder-artifact file on disk. No network, no subprocess, no
file-backed sqlite. Nothing below is carried over unverified from an earlier
pass.

**Artifact-path status (required report per task instructions):**

- `~/.hermes/bot/docs/routstr_delist_contract.md` — **MISSING — HIGH**.
  Re-verified this pass, twice: probe A0d asserts the path is absent
  (`exists=False`), and `ls -a ~/.hermes/bot/docs/` returns exactly two entries
  besides `.`/`..` — `reviews/` and `routstr-delist.md`. The contract role is
  filled by the two stand-ins below, both read end-to-end this pass. This is the
  **fourth consecutive** pass to report the same absent path; the finding is not
  a transient.
- `~/.hermes/bot/docs/routstr-delist.md` — present, 197 lines, md5
  `e385af98b9c142eec736672d4dcca290`, **byte-identical** to the repo copy
  (probe A0c), so `docs:N` below applies to both.
- `~/.hermes/bot/scripts/routstr_delist.py` — present, 829 lines, md5
  `2ea724ef08d857cd7b88a957300e70b4`, verified **byte-identical** to repo
  `src/routstr_delist.py` (probe A0a). All `routstr_delist.py:N` references
  apply to both copies.
- `~/.hermes/bot/tests/test_routstr_delist.py` — present, 752 lines, md5
  `031851b356f0de4089512f02f13f05cc`, verified **byte-identical** to repo
  `tests/test_routstr_delist_contract.py` (probe A0b). Its loader falls back to
  the DEPLOYED script (`contract:50`), so it exercises both copies. Referenced
  below as `contract:N`.

Conventions: `routstr_delist.py:N` = the script (both copies); `contract:N` =
contract suite (752 lines, 25 cases); `tests:N` = repo
`tests/test_routstr_delist.py` (1172 lines, the main suite); `docs:N` = repo
`docs/routstr-delist.md` (197 lines). Execution evidence this pass:
`pytest tests/ -q` → **121 passed in 2.01s**; deployed copy
`cd ~/.hermes/bot && pytest tests/test_routstr_delist.py -q` → **25 passed in
0.90s**; `crontab -l | grep -ci routstr` → **0** (no cron wiring live, so no
live exposure). No reviewed artifact was modified: md5s unchanged before and
after (A0a/A0b/A0c), and the only paths written by this pass are this file and
the probe harness/output under `docs/reviews/routstr_f13_probes/`.
`~/.hermes/bot` is not a git repository (`git -C ~/.hermes/bot rev-parse` →
"fatal: not a git repository"), so the required local commit lands in the
workspace repo (`merchant-routing`).

**Corrections new in this pass** (all defects in the review record, none in the
reviewed code):

1. **A source line was cited as a "signature" that is not one — MEDIUM (record
   defect).** The thirteenth-pass text justified the "`evaluate_triggers` applies
   no key filter" claim with "(confirmed by signature at
   `routstr_delist.py:317`)". Line 317 is `fire = bool(accel or var or override)`
   — a statement inside `evaluate_triggers`'s body, not a signature. The
   signature is defined at `routstr_delist.py:272` (`def evaluate_triggers(preds_now,
   prev_state, *, override=False, move_hours=…, variance_threshold=…)`): it has
   **no** `key` parameter, which is what probe C8c measures via
   `inspect.signature`. The unused optional filter lives in the CALLEE at
   `routstr_delist.py:132` (`def variance_jumped(preds, *, threshold=…, key=None)`).
   The claim is true and was re-measured (probe C8a/C8b/C8c); only the citation
   label was wrong. Corrected in Finding 3 residual (a).
2. **The thirteenth pass's own correction 4 was self-contradictory.** It said
   line `:680` "reverses an inverted condition (`if not args.dry_run:`) at
   `:680`". There is no `if not args.dry_run:` at 680: `routstr_delist.py:679`
   is `if args.dry_run:`, `:680` is `confirmed = True  # intent only: no remote
   verify`, `:681` is `break`. (The inverted condition `if not args.dry_run and
   attempts < MAX_PULL_ATTEMPTS` is at `:675`, in the retry path.) The region
   cited was right, the explanation was not. Restated plainly in Finding 2 note
   (a); the same region is verified by probe D1.
3. **The provenance citation counts are superseded by direct measurement.** The
   thirteenth pass's provenance recorded "58 cited file:line pairs" and "72
   `file:line` citations in this document". Both figures fail to reproduce
   against the thirteenth-pass text: this pass measures **106** load-bearing
   pairs with their expected text (probe D1, against the artifacts) and, with
   the citation regex now in the harness, **127** in-document citations in that
   text (88 `routstr_delist.py` + 11 `contract` + 16 `tests` + 12 `docs`) and
   **158** in the document below (119 `routstr_delist.py` + 11 `contract` +
   13 `tests` + 15 `docs`), zero unresolved in either (probe D2). The earlier
   figures are treated as superseded rather than as a defect (the earlier
   probe's pair list is not available to compare against). Same hygiene check
   caught one anchor that was 2 lines off: the "**unreadable/corrupt `--preds`
   feed**" phrase begins at `docs:84`, not `docs:86` (line 86 is the
   continuation "baseline is never wiped …"); the bullet spans `docs:84-86` and
   residual (e) now cites it that way.

**Standing corrections re-verified this pass** (kept so the record is
self-contained; each was re-measured, not copied):

- the `test_manual_override_is_never_gated_on_feed_staleness` name bus lives in
  the **contract** suite at `contract:427`, not in the main suite (probe D5
  audits every such pin; 9 pins, 0 mis-filed);
- the five SQL references have two line conventions — AST statement starts
  `355/361/369/392/406` (A1a) vs raw-source SQL text `355/361/371/394/408`
  (A2a) — both five, both `models`-only, and both are now stated explicitly;
- the filesystem write surface includes the state **directory** created at
  `routstr_delist.py:229` (A5a), not just the state file.

**New observations this pass** (each LOW; two in the fail-safe direction):

- the pure trigger helpers are not type-hardened — the non-dict guard lives only
  at the `_read_preds` boundary (Finding 3, residual (g), probe C6d);
- a failed **relist** never ticks the circuit breaker, so a permanently broken
  relist loops at rc 1 forever with no BLOCKED escalation (residual (h), probe
  C13a);
- a BLOCKED state refuses `--relist` as well, so the "explicit action clears
  breaker" reset at `routstr_delist.py:636` is reachable only while unblocked
  (residual (i), probe C13c).

## Finding 1 — Safety: SALE-delisting never disables the provider or touches the ladder — severity: **OK** (gaps: LOW)

1. **Every write path enumerated on the parsed source.** The SQL inventory over
   the parsed AST (probe A1a/A1c, which stops at every string literal so an
   implicitly concatenated f-string payload is counted once) finds exactly **5**
   SQL table references, all on `models`: statement starts
   `routstr_delist.py:355` (`UPDATE models SET enabled=0 WHERE enabled=1;`),
   `routstr_delist.py:361` (`UPDATE models SET enabled=1;`, legacy blanket
   builder), `routstr_delist.py:369` (pull payload; its `SELECT name FROM
   models WHERE enabled=1` is at `routstr_delist.py:371`),
   `routstr_delist.py:392` (scoped relist payload; `UPDATE models SET enabled=1
   WHERE name IN (…)` at `routstr_delist.py:394`) and `routstr_delist.py:406`
   (verify payload; `SELECT COUNT(*) FROM models WHERE enabled=1` at
   `routstr_delist.py:408`). The materialised table set is exactly `['models']`
   (probe A1b); zero statements reference any other table. In particular
   `upstream_providers` (the provider ladder) has **3 occurrences, all inside
   docstrings** (`routstr_delist.py:35`, `routstr_delist.py:352`,
   `routstr_delist.py:771`), **zero in executable code** (probe A3a/A3b: 285
   executable string literals inspected, none naming it). Raw-source
   confirmation of the same five SQL texts at lines 355/361/371/394/408 (probe
   A2a, comment lines excluded). Mutating verbs are exactly 3 UPDATEs
   (`routstr_delist.py:355`, `routstr_delist.py:361`, `routstr_delist.py:392`);
   the other 2 are read-only SELECTs.
2. **Executed, not merely asserted.** Probe A6 runs the module's REAL pull
   payload against the stand-in node: the ladder artifact is **byte-identical**
   after the delist (A6b, 340 B), `upstream_providers` is **row-identical**
   (A6c), the `routstr` provider is still enabled and a ladder candidate (A6d),
   all 3 advertised models are disabled and a pre-disabled operator row stays
   disabled (A6e), and no executed payload ever names `upstream_providers`
   (A6f). The same property is pinned semantically by `contract:468`
   (`TestSemanticGuardLadderUntouched`; ladder fixture written at `contract:108`,
   payload assertion at `contract:483-485`, provider-still-enabled assertion at
   `contract:487-489`) and, in the main suite, by `tests:302`
   (`TestSaleNotProvider`).
3. **Scoped relist cannot resurrect operator-disabled rows.** Probe A7: after a
   confirmed delist, `--relist` restores exactly the 3 captured names
   (`restored=3`), leaves the pre-disabled row at 0, and the ladder artifact is
   still byte-identical. The parameterized builder is
   `routstr_delist.py:394`, asserted end-to-end at `tests:1166`
   (`assertIn("name IN (?,?)", remote)`).
4. **Blanket relist is refused before any remote call.** With no captured names,
   `routstr_delist.py:602` (`if not names and not args.relist_any:`) refuses —
   probe A8: rc 1, `action=relist_refused`, **zero** backend calls, and the state
   file was not even created (A8b: no `delisted` flag written). The blanket SQL
   is reachable only via the explicit opt-in argument at `routstr_delist.py:526`;
   documented at `docs:29-32` ("**No blanket relist.**" … "Pass `--relist-any`
   for the explicit operator opt-in."). Probe B7f shows the cost of taking that
   opt-in while the scoped set is gone: every row, including a pre-disabled
   operator row, comes back enabled (see Finding 2).
5. **Command-injection surface is closed.** Exactly **2** `subprocess.run` sites
   exist (`routstr_delist.py:459` nak publish, `routstr_delist.py:808` ssh
   docker-exec), with **`shell=True` count = 0**; `eval`/`exec` call sites = 0
   (probe A4a/A4b). The remote pipeline is built at `routstr_delist.py:414` and
   `routstr_delist.py:423` as a single shlex-quoted argv element; probe A9
   confirms the argv is 3 elements (A9a) and that `shlex.split(cmd[2])`
   round-trips to `["docker", "exec", "routstr public", "python3", "-c",
   "print('x')"]` intact even with a space in the container name (A9b). Pinned
   at `tests:345` (`test_ssh_cmd_is_single_shlex_safe_remote_command`, the
   round-trip itself at `tests:354`) and documented at `docs:137`.
6. **Filesystem writes are confined to the state path.** The complete write
   surface is `os.makedirs` of the state directory
   (`routstr_delist.py:229`), the single write-mode `open()` of the tmp file
   (`routstr_delist.py:231`), `os.replace` of that tmp file
   (`routstr_delist.py:235`) and `os.unlink` of a stale tmp
   (`routstr_delist.py:243`) — all inside `save_state`'s atomic tmp-swap (probe
   A5a enumerates every `os.*` write call AND every `open()` mode in the module:
   one write, three reads). Nothing outside the state path is written, and the
   override marker is only `isfile`-probed (`routstr_delist.py:172`).
7. **Dry-run is intent-only.** Probe A10: `--manual --dry-run` performs **zero**
   remote round-trips (A10a) and introduces **no** durable `delisted` flag (A10b:
   state keys are only `ts`, `last_dry_run`). Wired at `routstr_delist.py:699`;
   pinned by `contract:731`
   (`test_dry_run_publishes_no_event_and_flips_no_flag`) and `tests:1072`
   (`TestDryRunPurity`).

Gaps (LOW, non-blocking): (a) `--ssh-target`/`--container`
(`routstr_delist.py:536`, `routstr_delist.py:537`) let an operator point the
mutating payload at any host/container — by design, nothing validates that the
target is the sell node; (b) the payloads hard-code `/app/data/keys.db` ×4
(`routstr_delist.py:370`, `routstr_delist.py:385`, `routstr_delist.py:393`,
`routstr_delist.py:407`) — a container layout change would mutate whatever DB
lives at that path; (c) `save_state`'s return value is ignored at all 8 call
sites (`routstr_delist.py:565`, `routstr_delist.py:622`,
`routstr_delist.py:629`, `routstr_delist.py:638`, `routstr_delist.py:654`,
`routstr_delist.py:710`, `routstr_delist.py:732`, `routstr_delist.py:752`;
probe A5b confirms no call site consumes the return), so a failed write after a
CONFIRMED delist (`routstr_delist.py:752`) would silently diverge local state
from remote reality (cross-ref findings 4–5); (d) the pull payload reads the
enabled set and disables it in two statements separated by a `commit`
(`routstr_delist.py:371` then `routstr_delist.py:372`), so a row enabled by
another writer inside that microsecond window is disabled without being captured
and would not be restored by a scoped relist — narrower than any operator action
and fail-safe in the protection direction, but real.

**Verdict 1: OK** — no path disables the routstr provider or leaves the
`models` listing table, the ladder protection is proven by execution and by a
semantic test, and every remaining gap is LOW.

## Finding 2 — Post-delisting confirmation via re-fetch — severity: **OK** (delist requirement MET; residual: MEDIUM relist asymmetry, LOWs itemized)

1. **The required independent re-fetch exists.** `verify_pull_payload()`
   (`routstr_delist.py:400`, SQL text at `routstr_delist.py:408`) is a read-only
   `SELECT COUNT(*) FROM models WHERE enabled=1` — probe B1 confirms the payload
   contains **no** mutating verb (B1a) and is exactly that COUNT (B1b). It runs
   as a SEPARATE ssh round-trip via `_SshBackend.verify`
   (`routstr_delist.py:790`), invoked after the pull at `routstr_delist.py:682`
   inside the attempt loop (`routstr_delist.py:671`). Success requires
   `vres.get("ok") is True and vres.get("count") == 0`
   (`routstr_delist.py:683`, matched in source by probe B2a); `confirmed` is only
   then set (`routstr_delist.py:687`), and only `confirmed` unlocks the
   `delisted=True` write (`routstr_delist.py:747`) and rc 0. Suite pins:
   `contract:334` (happy path is exactly `["pull", "verify"]`), `tests:566`
   (`TestRefetchConfirmation`).
2. **A lying pull is refuted by execution.** Probe B4 simulates a pull that
   self-reports `ok` but whose UPDATE never lands: rc 1, `action=delist_failed`,
   `verify.count == 3`, **no** `delisted` flag, `consecutive_failures == 1`, and
   the retry sequence is exactly `["pull", "verify", "pull", "verify"]`
   (`MAX_PULL_ATTEMPTS = 2`, `routstr_delist.py:75`). Pinned end-to-end at
   `contract:346` (`test_unverified_pull_is_a_failed_delist`) and the breaker
   path at `tests:816` (`TestCircuitBreaker`).
3. **Happy path is verified and recorded.** Probe B3: rc 0, `confirmed=True`,
   `verified_count == 0`, exactly one pull + one verify (B3b), durable
   `delisted=true` carrying the captured advertised names in `pulled_models`
   (B3c). Probe B4d is the converse measured from the same run — a verify
   reporting `count=3` refutes an `ok` pull even though the verify result itself
   says `ok: True` (rc 1, no flag, breaker tick) — and probe B5a shows a verify
   **transport** failure is an attempt failure, not a success (rc 1, kinds
   `["pull", "pull"]` because the verify is never reached, no flag,
   `consecutive_failures == 1`).
4. **Garbage cannot confirm.** The verify result passes through
   `_SshBackend._run` (the round-trip is bounded by `min(SSH_TIMEOUT_S,
   remaining)` at `routstr_delist.py:801-806`; the result shape is settled at
   `routstr_delist.py:822`, `res["ok"] = proc.returncode == 0 and
   data.get("ok") is True`); a non-zero rc, unparseable stdout, or a missing
   `ok`/`count` key all yield a non-confirming result, because `None == 0` is
   False at `routstr_delist.py:683` (probe B8a). Failure direction is therefore
   always safe: garbage can only fail the run, never confirm it.
5. **Residual — MEDIUM: the relist direction has no symmetric re-fetch.**
   Relist success is gated on the round-trip self-report alone
   (`routstr_delist.py:626`, `if not res.get("ok"):`), and on that self-report
   the run writes `delisted=false` and pops `pulled_models`
   (`routstr_delist.py:635`). Probe B7 measures the asymmetry end-to-end: after a
   confirmed delist, `--relist` yields `kinds == ["pull", "verify", "relist"]` —
   **no verify follows** (B7a). A lying relist (rc 0, ok printed, UPDATE not
   landed — the same fault class the contract deemed must-fix for delist) is
   reported as `action=relist`, **rc 0** (B7b), while the listing is measurably
   **NOT** restored (B7c) and the scoped name set is destroyed (B7d,
   `pulled_models` → absent). A subsequent scoped `--relist` is then refused
   (`routstr_delist.py:602`; probe B7e), so recovery forces `--relist-any`
   (`routstr_delist.py:526`), which in probe B7f re-enables **every** row —
   including the operator-disabled one — or a fresh delist/relist cycle. The
   contract mandates the re-fetch only for a fired delist (`docs:69-70`), so this
   is an asymmetry rather than a contract breach, but the fix is cheap: verify
   after relist (e.g. a per-name re-read, or COUNT(*) > 0) before popping
   `pulled_models`.
6. LOW notes: (a) the dry-run path sets `confirmed=True` without any remote
   verify (`routstr_delist.py:679` is `if args.dry_run:`, `routstr_delist.py:680`
   is `confirmed = True  # intent only: no remote verify`, `routstr_delist.py:681`
   is `break`) — intent-only, there is nothing to confirm; (b) the verify
   round-trip shares the ssh transport, timeout bound and last-line JSON parsing
   with the pull (`routstr_delist.py:806-822`), so it is independent in the
   contract's sense of a separate round-trip (`docs:69`) but a systematic
   transport-level fault (wrong container, shadowed DB path) could satisfy both —
   directionally safe, since a fooled verify can only keep the run failing into
   the breaker.

**Verdict 2: OK** — the required post-delisting confirmation exists, is a
separate read-only round-trip, gates the durable flag, and is pinned by both
suites; one MEDIUM residual (relist asymmetry) and two LOW notes above.

## Finding 3 — Fail-safe on absent, garbage and stale monitor signals — severity: **OK** (residuals: LOW)

Everything that can reach a delist funnels through
`fire = args.delist or dec["fire"]` (`routstr_delist.py:649`), where
`dec["fire"] = bool(accel or var or override)` (`routstr_delist.py:317`).

1. **Absence — OK.** With no `--preds` the feed is empty (probe C12: a quiet run
   stores only `ts`/`last_dry_run`); acceleration requires non-empty preds on
   both sides (`routstr_delist.py:107`) and variance requires non-empty preds
   (`routstr_delist.py:143`), so a first run with no stored baseline can never
   fire (`contract:308`, `test_first_run_without_baseline_is_quiet`). Manual
   override stays available by design.
2. **Garbage — OK.** `_read_preds` (`routstr_delist.py:468`) never raises, drops
   non-dict entries (`routstr_delist.py:479`) and returns `[]` on any parse
   failure. An explicitly requested but unusable feed is a FEED ERROR
   (`preds_error`, `routstr_delist.py:585`) with rc 1 when nothing fired
   (`routstr_delist.py:660`). Probes: invalid JSON → rc 1, `preds_error=true`,
   `action=none`, zero remote calls (C4a); a feed that is both garbage AND aged
   surfaces as `preds_error=true` with `preds_stale=false`, because `raw_preds`
   is empty at `routstr_delist.py:589` (C4c), both exiting 1. **The stored
   baseline is never wiped** — `update_state` only overwrites the snapshot when
   preds is non-empty (`routstr_delist.py:261`); probes C2b/C4b confirm the
   snapshot survives byte-for-byte, including on the path where a delist
   actually FIRES (C7b). Type-guards: `uncertainty` is isinstance-guarded with
   bool explicitly excluded (`routstr_delist.py:152`, pinned by `tests:146`
   `test_non_numeric_uncertainty_ignored_not_crash`) and `exhausts_in_hours` is
   guarded too; probe C6a/C6b show string, bool, None and non-dict entries
   produce no fire, no crash, and an all-empty trigger set through the CLI.
   (Probe C6d, new observation (g), shows the same malformed rows DO raise
   `AttributeError` if the pure helpers are called directly — see residuals.)
3. **Stale — OK.** `STALENESS_S = 1800` (`routstr_delist.py:78`);
   `feed_is_stale` (`routstr_delist.py:485`) ends in
   `return not (0 <= age <= max_age_s)` (`routstr_delist.py:494`), with an
   `OSError` (missing file / unreadable) short-circuiting to `True`
   (`routstr_delist.py:495-496`), i.e. undeterminable age and a future mtime are
   BOTH treated as stale. Probe C1 measures the matrix: missing → stale, aged
   3600 s → stale, future mtime → stale, fresh → not stale, **age exactly
   1800 s → not stale** (boundary inclusive), age 1800.5 s → stale. Wiring: a
   stale feed zeroes the preds **before** trigger evaluation
   (`routstr_delist.py:589`, `routstr_delist.py:591-592`) so the level-based
   variance trigger cannot fire on dead data, and before any baseline refresh —
   probe C2: stale feed → rc 1, `preds_stale=true`, `action=none`, zero remote
   calls, snapshot untouched (C2a/C2b); probe C2c is the control showing the
   identical numbers with a FRESH mtime DO delist, which proves the guard rather
   than mere absence of input. Suite pins: `tests:928` (`TestStalenessGuard`),
   `tests:937` (`test_stale_feed_never_triggers`), `tests:968`
   (`test_staleness_threshold_boundary`), `tests:995`
   (`test_stale_feed_baseline_not_consumed`). The guard is documented at
   `docs:56-58` ("never triggers (variance especially), never refreshes the
   acceleration baseline").
4. **Manual override is deliberately never gated on freshness — verified.**
   Probe C7: a stale feed plus `--manual` delists (rc 0, `preds_stale=true`
   observed but not obeyed, exactly `["pull","verify"]` executed) **and leaves
   the stored baseline unrefreshed** (C7b: the snapshot measured before the run
   is present unchanged after it), so overriding the freshness guard does not let
   dead data pollute the acceleration baseline. The same override behaviour holds
   when the feed is unparseable rather than merely old (C7c: rc 0,
   `preds_error=true`, `action=delist`). Pinned at `contract:427`
   (`test_manual_override_is_never_gated_on_feed_staleness`) and `tests:980`
   (`test_stale_feed_exit_zero_when_override_fires`); documented at `docs:60`
   ("The manual override is never gated on freshness.").
5. **Budget and breaker fail closed.** Probe C10: an exhausted action budget
   returns `ok=false` with an `action budget exhausted` error and spawns **zero**
   subprocesses (bound at `routstr_delist.py:801-806`); with 5 s of budget left
   the per-round-trip timeout is clamped to the remaining budget (C10b measures
   **4.99999 s** against a 5 s deadline, i.e. `min(SSH_TIMEOUT_S, remaining)`).
   Probe C11: three consecutive failed runs give rc `[1, 1, 3]`, a
   durable `blocked=true` at `consecutive_failures == BREAKER_THRESHOLD`
   (`routstr_delist.py:730`, `routstr_delist.py:739`), and a blocked run then
   refuses **all** remote action (`action=blocked`, zero new backend calls
   before contacting the node) until `--unblock` (`routstr_delist.py:529`).
   Probe C12: dry-run never counts toward the breaker.

Residuals (LOW):

- **(a) `--preds-key` scoping is opt-in, default unscoped.** Filtering happens
  only when the flag is passed (`routstr_delist.py:597`); `evaluate_triggers`
  itself passes **no** key to `variance_jumped` (`routstr_delist.py:303`), as its
  signature confirms — `def evaluate_triggers(preds_now, prev_state, *,
  override=False, move_hours=…, variance_threshold=…)` at
  `routstr_delist.py:272` has no `key` parameter, while the optional filter it
  never passes lives in the callee at `routstr_delist.py:132`
  (`def variance_jumped(preds, *, threshold=…, key=None)`). Probe C8 reproduces
  it: an openrouter-only feed with `uncertainty 0.95` fires the routstr delist
  with no flag (C8a) while the same feed with `--preds-key zai` is quiet (C8b);
  `inspect.signature` confirms no implicit filter (C8c). Scoping is documented
  (`docs:54-55`) and carried in the runbook cron example (`docs:106`), so the
  residual is operator-omission risk. Caveat: `docs:55` states the guarantee
  unconditionally ("another provider's variance spike can never pull the routstr
  SALE") — the doc should say "with `--preds-key`".
- **(b) mtime-only freshness** (`routstr_delist.py:485-494`): a writer that
  rewrites the feed with OLD data refreshes the mtime and bypasses the guard
  (content-stale / mtime-fresh is undetectable). The contract accepts mtime
  (`docs:57`); an embedded `generated_at` check would be stronger.
- **(c) Cosmetic**: `_hours` accepts a bool while the variance guard excludes it
  (`routstr_delist.py:152` vs the hours helper) — arithmetic-safe, no crash path
  (probe C6c); the override marker is presence-based with no TTL
  (`routstr_delist.py:172`), which is operator-controlled by design.
- **(d) Cross-ref findings 4–5**: the quiet-run state write
  (`routstr_delist.py:654`), like all 8 `save_state` call sites, ignores the
  return value (probe A5b).
- **(e) An empty but valid `--preds` array is reported as a feed ERROR.**
  `preds_error = bool(args.preds) and not raw_preds` (`routstr_delist.py:585`)
  treats `[]` exactly like unreadable JSON, so a predictor that legitimately
  produced no rows makes every run exit 1 with `preds_error=true`
  (probe C5a: rc 1, `preds_error=true`, `action=none`, zero calls). The contract
  describes the error state as an "**unreadable/corrupt** `--preds` feed"
  (`docs:84-86`), which `[]` is not. Direction is safe — it can only suppress a
  fire — so this is a monitoring/exit-code wart, not a hazard.
- **(f) A scoped run narrows the durable baseline to the scoped key.**
  `evaluate_triggers` is handed the filtered list (`routstr_delist.py:597`), and
  a run that fires writes `snapshot_preds(filtered_preds)`
  (`routstr_delist.py:747` → `routstr_delist.py:261-262`), so after
  `--preds-key zai` the snapshot holds only that key's windows — probe C9a
  measures `snapshot == {"zai\x1f1h"}` while the feed carried both keys. Other
  keys then have no baseline until a fresh unscoped baseline exists, which can
  only *suppress* a later acceleration fire. Fail-safe direction; worth a line of
  documentation, since the runbook cron example (`docs:106`) is permanently
  scoped.
- **(g) NEW — the pure trigger helpers are not type-hardened.** The non-dict
  guard lives only at the `_read_preds` boundary
  (`routstr_delist.py:479`), not in the helpers the module documents as pure and
  unit-testable: calling `evaluate_triggers([None, "x", 1], None)` directly
  raises `AttributeError: 'NoneType' object has no attribute 'get'` from
  `variance_jumped` (`routstr_delist.py:149`) via
  `routstr_delist.py:303` (probe C6d). Not reachable through the CLI, which
  normalises first (C6a/C6b), so this is a defence-in-depth note for any future
  in-process caller (e.g. a monitor importing the module): hardening `_pred_key`
  / `variance_jumped` / `exhaustion_accelerated` against non-dict rows, or
  documenting the "normalised input" precondition, would close it. **LOW.**
- **(h) NEW — a failed RELIST never ticks the circuit breaker.** The delist
  failure path increments and escalates (`routstr_delist.py:724`
  `fails += 1`; `routstr_delist.py:730` `newly_blocked = fails >=
  BREAKER_THRESHOLD`; `routstr_delist.py:739` rc 3 when blocked), but the relist
  failure path (`routstr_delist.py:626-632`) only records `last_pull_error` and
  returns 1. Probe C13a: after a confirmed delist, four consecutive
  transport-dead `--relist` runs give rc `[1, 1, 1, 1]` with `blocked` never
  true and `consecutive_failures` still 0 — so a permanently broken relist (the
  exact mechanism an operator needs to *undo* a delist) loops at rc 1 with no
  escalation to BLOCKED and no `--unblock` hint. Fail-safe-adjacent in the other
  direction from (a)–(g): the escalation that protects the remote node from
  repeated mutation is asymmetrically unavailable for the restore path.
  **LOW** (the relist is operator-initiated, and each failed run is visible in
  `last_pull_error`), but it is a real gap in the fail-safe story.
- **(i) NEW — a BLOCKED state refuses `--relist`, so the "explicit action clears
  the breaker" reset is reachable only while unblocked.** The blocked gate
  (`routstr_delist.py:569`, returning 3 at `routstr_delist.py:578`) precedes the
  relist branch, so the reset at `routstr_delist.py:636`
  (`state["consecutive_failures"] = 0` … `state["blocked"] = False`) can only run
  for a relist that was already unblocked. Probe C13c: with a durable
  `blocked=true`, `--relist` exits 3 with `action=blocked` and **zero** new
  backend calls. Probe C13b shows the reset does work in its intended range — a
  successful relist takes accumulated delist failures from 2 back to 0. So the
  operator must use `--unblock`, then `--relist`; the code comment on
  `routstr_delist.py:636` reads more broadly than the reachable behaviour.
  **LOW** (documentation/reachability, not a hazard: refusing is the fail-safe
  direction).

**Verdict 3: OK** — absence and garbage are safe, staleness is guarded in the
fail-safe direction with a fresh-input control, the override is intentionally
ungated and does not pollute the baseline, and budget/breaker semantics fail
closed; residuals are LOW as itemized, including the three new ones.

---

Provenance: fourteenth offload pass for findings 1–3. Earlier passes (files at
this path; Gate 2.5 cold review `docs/reviews/routstr_delist_review.md`)
correctly found Finding 2 REFUTED-HIGH (no re-fetch) and Finding 3 PARTIAL-HIGH
(no freshness guard) against the pre-fix script, and subsequent passes
re-adjudicated both OK against the current 829-line artifacts. This pass
independently re-derives the same three verdicts: script read end-to-end in both
copies (byte-identical, md5 `2ea724ef08d857cd7b88a957300e70b4`, 829 lines),
contract suite read end-to-end and executed against the deployed copy, **106**
cited file:line pairs re-verified against their files with their expected text
(probe D1), all **158** `file:line` citations in this document re-checked to
resolve in the file they name (probe D2, zero unresolved), **79** hermetic probe
checks PASS (`docs/reviews/routstr_f13_probes/pass14_output.txt`; the
pre-rewrite transcript against the thirteenth-pass text is
`docs/reviews/routstr_f13_probes/pass14_output_predeliverable.txt`, 76/76),
suites 121 + 25 green, `crontab -l` re-checked (zero routstr entries). Verdicts:
**1 OK** (gaps LOW), **2 OK** (MEDIUM relist-asymmetry residual), **3 OK** (LOW
residuals). Artifact-path report: the contract markdown is STILL MISSING at the
bot path (**HIGH**), now for the fourth consecutive pass; the bot
`routstr-delist.md` copy is byte-identical to the repo copy. Three corrections to
the earlier record and three new fail-safe-direction observations are itemized in
the preamble. No reviewed artifact was modified. `~/.hermes/bot` is not a git
repository, so the required local commit lands in the workspace repo
(`merchant-routing`) covering `docs/reviews/findings_1_3.md` and the probe
harness, with an identical copy of this file at the task-mandated path
`~/.hermes/bot/docs/reviews/findings_1_3.md`.
