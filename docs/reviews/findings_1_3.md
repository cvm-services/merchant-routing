# Offload review — routstr delist, findings 1–3 (safety, confirmation, fail-safe)

Thirteenth offload pass for findings 1–3, re-derived from primary sources in this
session against the CURRENT artifacts. Scope, per the original task: **item 1**
safety (delisting the SALE must never disable the routstr provider or touch the
T470 flat-router ladder), **item 2** post-delisting confirmation via re-fetch,
**item 3** fail-safe behaviour on absent, garbage and stale monitor signals.

This dispatch repeated a task whose deliverable already existed from twelve
earlier passes at this path, so the pass was handled as a re-derivation: the
document below was rewritten in place from primary evidence collected in this
session, not appended to. Verdicts are unchanged because the evidence
re-derived them unchanged; four corrections and three new observations are
recorded, each with the measurement that produced it.

Method this pass: the script was read end-to-end in both copies, the contract
suite read end-to-end, every cited line re-checked against its file, all
write-path/SQL/subprocess inventories re-run on the parsed source (AST, not grep
prose), both suites executed, and a fresh hermetic probe harness
(`docs/reviews/routstr_f13_probes/probe_f13_pass13.py`, written for this pass, not
reused from any earlier one) executed **73 checks**. Final run: **73/73 PASS**,
output archived at `docs/reviews/routstr_f13_probes/pass13_output.txt`. The same
harness was first run against the previous (twelfth-pass) copy of this document
and reported `D5` FAIL — that pre-fix transcript, which is the evidence for
correction (1) below, is archived at
`docs/reviews/routstr_f13_probes/pass13_output_predeliverable.txt`. The probe
replaces only the ssh boundary: it EXECUTES the module's own payloads against a
stand-in node holding a live `models` (SALE listing) table, a live
`upstream_providers` (provider ladder) table and a ladder-artifact file on disk.
No network, no subprocess, no file-backed sqlite. Nothing below is carried over
unverified from an earlier pass.

**Artifact-path status (required report per task instructions):**

- `~/.hermes/bot/docs/routstr_delist_contract.md` — **MISSING — HIGH**.
  Re-verified this pass, twice: `find`-style probe A0d asserts the path is absent
  (`exists=False`), and `ls -la ~/.hermes/bot/docs/` returns exactly two
  entries — `reviews/` and `routstr-delist.md`. The contract role is filled by
  the two stand-ins below, both read end-to-end this pass. This is the third
  consecutive pass to report the same absent path; the finding is not a
  transient.
- `~/.hermes/bot/docs/routstr-delist.md` — present, 197 lines, md5
  `e385af98b9c142eec736672d4dcca290`, **byte-identical** to the repo copy
  (probe A0c), so `docs:N` below applies to both. The staleness residual
  reported by passes ≤ 11 is closed.
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
`pytest tests/ -q` → **121 passed in 6.95s**; deployed copy
`cd ~/.hermes/bot && pytest tests/test_routstr_delist.py -q` → **25 passed in
5.68s**; `crontab -l | grep -ci routstr` → **0** (no cron wiring live, so no
live exposure). No artifact was modified: the only paths written by this pass are
this file and the probe harness/output under `docs/reviews/routstr_f13_probes/`.
`~/.hermes/bot` is not a git repository, so the required local commit lands in
the workspace repo (`merchant-routing`).

**Corrections carried in this pass** (all found by re-deriving, none carried
from another pass's prose):

1. **Citation mis-filed — MEDIUM (defect in the review record, not in the
   code).** The twelfth-pass text pinned `test_manual_override_is_never_gated_on_feed_staleness`
   at `tests:427`. That test name does not occur anywhere in the main suite:
   `tests:427` is `self.assertEqual(rd.ACTION_BUDGET_S,` inside
   `TestSlaWiring`, while the named test lives in the **contract** suite at
   `contract:427`. Verified independently by `grep -n` (one hit, in the contract
   file), by probe D5, and by probe D1. The claim the pin supports is true and
   was re-measured this pass (Finding 3 item 4); the file label was wrong. Fixed
   below. `tests:980`, the other half of that same pin, is correct.
2. **Two line conventions for the five SQL references were conflated.** The
   AST statement-start lines are `355/361/369/392/406` (probe A1a); the raw-source
   lines bearing the SQL text are `355/361/371/394/408` (probe A2a). Both sets
   are five, both name only `models`, but they are not the same numbers — the two
   multiline payloads open at 369/392 and carry their SQL at 371/394. Earlier
   passes printed the text lines while labelling the check A1a. Both are now
   stated explicitly.
3. **The filesystem-write claim was one call short.** `os.makedirs(d, exist_ok=True)`
   at `routstr_delist.py:229` creates the state directory, so the write surface is
   the state file **and its parent directory** — not "the state file" alone
   (probe A5a enumerates the complete `os` write surface as exactly
   `makedirs/229`, `replace/235`, `unlink/243`). No behaviour changes; the
   sentence was imprecise.
4. **A `confirmed=True` dry-run was cited as `routstr_delist.py:679-681`.** Line
   679 is `if args.dry_run:` and the assignment is at `:680`, which reverses an
   inverted condition (`if not args.dry_run:`) at `:680` — the citation is right
   about the region; noted here only so the region is not read as an
   unconditional early confirm.

New observations this pass (each LOW; all in the fail-safe direction or
evidence-only):

- an empty but valid `--preds` array is classified as a FEED ERROR (Finding 3,
  residual (e));
- a `--preds-key`-scoped run replaces the durable baseline with the scoped key's
  windows only (Finding 3, residual (f));
- the manual-override path is now shown to leave the baseline unrefreshed, not
  merely the quiet path (Finding 3 item 3 and probe C7b).

## Finding 1 — Safety: SALE-delisting never disables the provider or touches the ladder — severity: **OK** (gaps: LOW)

1. **Every write path enumerated on the parsed source.** The SQL inventory over
   the parsed AST (probe A1a/A1c, which stops at every string literal so an
   implicitly concatenated f-string payload is counted once) finds exactly **5**
   SQL table references, all on `models`: statement starts
   `routstr_delist.py:355` (`UPDATE models SET enabled=0 WHERE enabled=1;`),
   `:361` (`UPDATE models SET enabled=1;`, legacy blanket builder), `:369`
   (`SELECT name FROM models WHERE enabled=1`, SQL text at `:371`), `:392`
   (`UPDATE models SET enabled=1 WHERE name IN (…)`, SQL text at `:394`) and
   `:406` (`SELECT COUNT(*) FROM models WHERE enabled=1`, SQL text at `:408`).
   The materialised table set is exactly `['models']`; zero statements reference
   any other table. In particular `upstream_providers` (the provider ladder) has
   **3 occurrences, all inside docstrings** (`:35`, `:352`, `:771`), **zero in
   executable code** (probe A3a/A3b: 285 executable string literals inspected,
   none naming it). Raw-source confirmation of the same five SQL texts at lines
   355/361/371/394/408 (probe A2a). Mutating verbs are exactly 3 UPDATEs; the
   other 2 are read-only SELECTs.
2. **Executed, not merely asserted.** Probe A6 runs the module's REAL pull
   payload against the stand-in node: the ladder artifact is **byte-identical**
   after the delist (A6b, 340 B), `upstream_providers` is **row-identical**
   (A6c), the `routstr` provider is still enabled and a candidate (A6d), all 3
   advertised models are disabled and a pre-disabled operator row stays disabled
   (A6e), and no executed payload ever names `upstream_providers` (A6f). The same
   property is pinned semantically by `contract:468`
   (`TestSemanticGuardLadderUntouched`, ladder fixture built at `contract:108`,
   payload assertion at `contract:483-485`, provider-still-enabled assertion at
   `contract:487-489`) and, in the main suite, by `tests:302` (`TestSaleNotProvider`).
3. **Scoped relist cannot resurrect operator-disabled rows.** Probe A7: after a
   confirmed delist, `--relist` restores exactly the 3 captured names
   (`restored=3`), leaves the pre-disabled row at 0, and the ladder artifact is
   still byte-identical. The parameterized builder is `routstr_delist.py:394`,
   asserted end-to-end at `tests:1166` (`assertIn("name IN (?,?)", remote)`).
4. **Blanket relist is refused before any remote call.** With no captured names,
   `routstr_delist.py:602` (`if not names and not args.relist_any:`) refuses —
   probe A8: rc 1, `action=relist_refused`, **zero** backend calls, and the state
   file was not even created (no `delisted` flag written). The blanket SQL is
   reachable only via the explicit opt-in argument at `routstr_delist.py:526`;
   documented at `docs:29-32` ("**No blanket relist.**" … "Pass `--relist-any`
   for the explicit operator opt-in."). Probe B7f shows the cost of taking that
   opt-in while the scoped set is gone: every row, including a pre-disabled
   operator row, comes back enabled (see Finding 2).
5. **Command-injection surface is closed.** Exactly **2** `subprocess.run` sites
   exist (`routstr_delist.py:459` nak publish, `:808` ssh docker-exec), with
   **`shell=True` count = 0**; `eval`/`exec` call sites = 0 (probe A4a/A4b). The
   remote pipeline is built at `routstr_delist.py:414`/`:423` as a single
   shlex-quoted argv element; probe A9 confirms the argv is 3 elements and that
   `shlex.split(cmd[2])` round-trips to
   `["docker", "exec", "routstr public", "python3", "-c", "print('x')"]` intact
   even with a space in the container name. Pinned at `tests:345`/`tests:353` and
   `docs:137`.
6. **Filesystem writes are confined to the state path.** The complete `os` write
   surface is `os.makedirs` of the state directory (`routstr_delist.py:229`),
   `os.replace` of the tmp file (`:235`) and `os.unlink` of a stale tmp
   (`:243`) — all inside `save_state`'s atomic tmp-swap (probe A5a); nothing
   outside the state path is written, and the override marker is only
   `isfile`-probed (`:172`).
7. **Dry-run is intent-only.** Probe A10: `--manual --dry-run` performs **zero**
   remote round-trips and introduces **no** durable `delisted` flag (state keys
   are only `ts`, `last_dry_run`). Wired at `routstr_delist.py:699`; pinned by
   `contract:731` and `tests:1072` (`TestDryRunPurity`).

Gaps (LOW, non-blocking): (a) `--ssh-target`/`--container`
(`routstr_delist.py:536`, `:537`) let an operator point the mutating payload at
any host/container — by design, nothing validates that the target is the sell
node; (b) the payloads hard-code `/app/data/keys.db` ×4
(`routstr_delist.py:370`, `:385`, `:393`, `:407`) — a container layout change
would mutate whatever DB lives at that path; (c) `save_state`'s return value is
ignored at all 8 call sites (`routstr_delist.py:565`, `:622`, `:629`, `:638`,
`:654`, `:710`, `:732`, `:752`; probe A5b confirms no call site consumes the
return), so a failed write after a CONFIRMED delist (`:752`) would silently
diverge local state from remote reality (cross-ref findings 4–5); (d) the pull
payload reads the enabled set and disables it in two statements separated by a
`commit` (`routstr_delist.py:371` then `:372`), so a row enabled by another
writer inside that microsecond window is disabled without being captured and
would not be restored by a scoped relist — narrower than any operator action
and fail-safe in the protection direction, but real.

**Verdict 1: OK** — no path disables the routstr provider or leaves the
`models` listing table, the ladder protection is proven by execution and by a
semantic test, and every remaining gap is LOW.

## Finding 2 — Post-delisting confirmation via re-fetch — severity: **OK** (delist requirement MET; residual: MEDIUM relist asymmetry, LOWs itemized)

1. **The required independent re-fetch exists.** `verify_pull_payload()`
   (`routstr_delist.py:400`, SQL text at `:408`) is a read-only
   `SELECT COUNT(*) FROM models WHERE enabled=1` — probe B1 confirms the payload
   contains **no** mutating verb (B1a) and is exactly that COUNT (B1b). It runs
   as a SEPARATE ssh round-trip via `_SshBackend.verify`
   (`routstr_delist.py:790`), invoked after the pull at `routstr_delist.py:682`
   inside the attempt loop (`:671`). Success requires
   `vres.get("ok") is True and vres.get("count") == 0`
   (`routstr_delist.py:683`, matched in source by probe B2a); `confirmed` is only
   then set (`:687`), and only `confirmed` unlocks the `delisted=True` write
   (`:747`) and rc 0. Suite pins: `contract:334` (happy path is exactly
   `["pull", "verify"]`), `tests:566` (`TestRefetchConfirmation`).
2. **A lying pull is refuted by execution.** Probe B4 simulates a pull that
   self-reports `ok` but whose UPDATE never lands: rc 1, `action=delist_failed`,
   `verify.count == 3`, **no** `delisted` flag, `consecutive_failures == 1`, and
   the retry sequence is exactly `["pull", "verify", "pull", "verify"]`
   (`MAX_PULL_ATTEMPTS = 2`, `routstr_delist.py:75`). Pinned end-to-end at
   `contract:346` (`test_unverified_pull_is_a_failed_delist`) and the breaker
   path at `tests:816` (`TestCircuitBreaker`).
3. **Happy path is verified and recorded.** Probe B3: rc 0, `confirmed=True`,
   `verified_count == 0`, exactly one pull + one verify, durable `delisted=true`
   with the captured advertised names in `pulled_models`. Probe B6 shows the
   converse — a verify reporting `count=3` refutes an ok pull (rc 1, no flag,
   breaker tick) — and probe B5 shows a verify **transport** failure is an
   attempt failure, not a success (rc 1, no flag, breaker tick).
4. **Garbage cannot confirm.** The verify result passes through
   `_SshBackend._run` (`routstr_delist.py:801-806` bounds every round-trip by
   `min(SSH_TIMEOUT_S, remaining)`; result shape settled at `:822`); a non-zero
   rc, unparseable stdout or a missing `ok`/`count` key all yield a
   non-confirming result, because `None == 0` is False at `:683` (probe B8).
   Failure direction is therefore always safe: garbage can only fail the run,
   never confirm it.
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
   `pulled_models` → None). A subsequent scoped `--relist` is then refused
   (`routstr_delist.py:602`; probe B7e), so recovery forces `--relist-any`
   (`:526`), which in probe B7f re-enables **every** row — including the
   operator-disabled one — or a fresh delist/relist cycle. The contract mandates
   the re-fetch only for a fired delist (`docs:69-70`), so this is an asymmetry
   rather than a contract breach, but the fix is cheap: verify after relist (e.g.
   a per-name re-read, or COUNT(*) > 0) before popping `pulled_models`.
6. LOW notes: (a) the dry-run path sets `confirmed=True` without any remote
   verify (`routstr_delist.py:679-680`) — intent-only, there is nothing to
   confirm; (b) the verify round-trip shares the ssh transport, timeout bound
   and last-line JSON parsing with the pull (`routstr_delist.py:806-822`), so it
   is independent in the contract's sense of a separate round-trip (`docs:69`)
   but a systematic transport-level fault (wrong container, shadowed DB path)
   could satisfy both — directionally safe, since a fooled verify can only keep
   the run failing into the breaker.

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
   (`:143`), so a first run with no stored baseline can never fire
   (`contract:308`, `test_first_run_without_baseline_is_quiet`). Manual override
   stays available by design.
2. **Garbage — OK.** `_read_preds` (`routstr_delist.py:468`) never raises, drops
   non-dict entries and returns `[]` on any parse failure. An explicitly
   requested but unusable feed is a FEED ERROR (`preds_error`,
   `routstr_delist.py:585`) with rc 1 when nothing fired (`:660`). Probes:
   invalid JSON → rc 1, `preds_error=true`, `action=none`, zero remote calls
   (C4a); a feed that is both garbage AND aged surfaces as `preds_error=true`
   with `preds_stale=false`, because `raw_preds` is empty at `:589` (C4c), both
   exiting 1. **The stored baseline is never wiped** — `update_state` only
   overwrites the snapshot when preds is non-empty (`routstr_delist.py:261`);
   probes C2b/C4b confirm the snapshot survives byte-for-byte, including on the
   path where a delist actually FIRES (C7b). Type-guards: `uncertainty` is
   isinstance-guarded with bool explicitly excluded (`routstr_delist.py:152`,
   pinned `tests:146` `test_non_numeric_uncertainty_ignored_not_crash`) and
   `exhausts_in_hours` is guarded too; probe C6a/C6b show string, bool, None and
   non-dict entries produce no fire, no crash, and an all-empty trigger set.
3. **Stale — OK.** `STALENESS_S = 1800` (`routstr_delist.py:78`);
   `feed_is_stale` (`routstr_delist.py:485`) ends in
   `return not (0 <= age <= max_age_s)` (`:494`), i.e. undeterminable age
   (missing file, OSError) and a future mtime are BOTH treated as stale. Probe
   C1 measures the matrix: missing → stale, aged 3600 s → stale, future mtime →
   stale, fresh → not stale, **age exactly 1800 s → not stale** (boundary
   inclusive), age 1800.5 s → stale. Wiring: a stale feed zeroes the preds
   **before** trigger evaluation (`routstr_delist.py:589`) so the level-based
   variance trigger cannot fire on dead data, and before any baseline refresh —
   probe C2: stale feed → rc 1, `preds_stale=true`, `action=none`, zero remote
   calls, snapshot untouched; probe C2c is the control showing the identical
   numbers with a FRESH mtime DO delist, which proves the guard rather than mere
   absence of input. Suite pins: `tests:928` (`TestStalenessGuard`), `tests:937`
   (`test_stale_feed_never_triggers`), `tests:968`
   (`test_staleness_threshold_boundary`), `tests:995`
   (`test_stale_feed_baseline_not_consumed`). The guard is documented at
   `docs:56-58` ("never triggers (variance especially), never refreshes the
   acceleration baseline").
4. **Manual override is deliberately never gated on freshness — verified.**
   Probe C7: a stale feed plus `--manual` delists (rc 0, `preds_stale=true`
   observed but not obeyed, exactly `["pull","verify"]` executed) **and leaves
   the stored baseline unrefreshed** (C7b, snapshot stays absent), so overriding
   the freshness guard does not let dead data pollute the acceleration baseline.
   Pinned at `contract:427` (`test_manual_override_is_never_gated_on_feed_staleness`
   — corrected pin, see preamble correction 1) and `tests:980`
   (`test_stale_feed_exit_zero_when_override_fires`); documented at `docs:60`
   ("The manual override is never gated on freshness.").
5. **Budget and breaker fail closed.** Probe C10: an exhausted action budget
   returns `ok=false` with an `action budget exhausted` error and spawns **zero**
   subprocesses (bound at `routstr_delist.py:801-806`); with 5 s of budget left
   the per-round-trip timeout is clamped to exactly 5.0 s (C10b). Probe C11:
   three consecutive failed runs give rc `[1, 1, 3]`, a durable `blocked=true`
   at `consecutive_failures == BREAKER_THRESHOLD`, and a blocked run then refuses
   **all** remote action (`action=blocked`, zero new backend calls before
   contacting the node) until `--unblock` (`routstr_delist.py:529`). Probe C12:
   dry-run never counts toward the breaker.

Residuals (LOW):

- **(a) `--preds-key` scoping is opt-in, default unscoped.** Filtering happens
  only when the flag is passed; `evaluate_triggers` itself passes **no** key to
  `variance_jumped` (`routstr_delist.py:303`, confirmed by signature at
  `:317`). Probe C8 reproduces it on the deployed copy: an openrouter-only feed
  with `uncertainty 0.95` fires the routstr delist with no flag (C8a) while the
  same feed with `--preds-key zai` is quiet (C8b); `evaluate_triggers` applies no
  implicit filter (C8c). Scoping is documented (`docs:54-55`) and carried in the
  runbook cron example (`docs:106`), so the residual is operator-omission risk.
  Caveat: `docs:55` states the guarantee unconditionally ("another provider's
  variance spike can never pull the routstr SALE") — the doc should say "with
  `--preds-key`".
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
- **(e) NEW — an empty but valid `--preds` array is reported as a feed ERROR.**
  `preds_error = bool(args.preds) and not raw_preds` (`routstr_delist.py:585`)
  treats `[]` exactly like unreadable JSON, so a predictor that legitimately
  produced no rows makes every run exit 1 with `preds_error=true`
  (probe C5a: rc 1, `preds_error=true`, `action=none`, zero calls). The contract
  describes the error state as an "**unreadable/corrupt** `--preds` feed"
  (`docs:86`), which `[]` is not. Direction is safe — it can only suppress a
  fire — so this is a monitoring/exit-code wart, not a hazard.
- **(f) NEW — a scoped run narrows the durable baseline to the scoped key.**
  `evaluate_triggers` is handed the filtered list, and a run that fires writes
  `snapshot_preds(filtered_preds)` (`routstr_delist.py:747` → `:261`/`:262`), so
  after `--preds-key zai` the snapshot holds only that key's windows — probe C9a
  measures `snapshot == {"zai\x1f1h"}` while the feed carried both keys. Other
  keys then have no baseline until a fresh unscoped baseline exists, which can
  only *suppress* a later acceleration fire. Fail-safe direction; worth a line of
  documentation, since the runbook cron example (`docs:106`) is permanently
  scoped.

**Verdict 3: OK** — absence and garbage are safe, staleness is guarded in the
fail-safe direction with a fresh-input control, the override is intentionally
ungated and does not pollute the baseline, and budget/breaker semantics fail
closed; residuals are LOW as itemized.

---

Provenance: thirteenth offload pass for findings 1–3. Earlier passes (files at
this path; Gate 2.5 cold review `docs/reviews/routstr_delist_review.md`)
correctly found Finding 2 REFUTED-HIGH (no re-fetch) and Finding 3 PARTIAL-HIGH
(no freshness guard) against the pre-fix 602-line script, and subsequent passes
re-adjudicated both OK against the current 829-line artifacts. This pass
independently re-derives the same three verdicts: script read end-to-end in both
copies (byte-identical, md5 `2ea724ef08d857cd7b88a957300e70b4`, 829 lines),
contract suite read end-to-end and executed against the deployed copy, **58**
cited file:line pairs re-verified against their files (probe D1), all **72**
`file:line` citations in this document re-checked to resolve in the file they
name (probe D2), write-path/SQL/subprocess inventories re-run on the AST, **73**
hermetic probe checks PASS (`docs/reviews/routstr_f13_probes/pass13_output.txt`;
the pre-fix transcript that caught correction 1 is
`pass13_output_predeliverable.txt`), suites 121 + 25 green, `crontab -l`
re-checked (zero routstr entries). Verdicts: **1 OK** (gaps LOW), **2 OK**
(MEDIUM relist-asymmetry residual), **3 OK** (LOW residuals). Artifact-path
report: the contract markdown is STILL MISSING at the bot path (**HIGH**), now
for the third consecutive pass; the bot `routstr-delist.md` copy is
byte-identical to the repo copy. Four corrections to the earlier record and
three new fail-safe-direction observations are itemized in the preamble. No
artifact was modified. `~/.hermes/bot` is not a git repository, so the required
local commit lands in the workspace repo (`merchant-routing`) covering
`docs/reviews/findings_1_3.md` and the probe harness, with an identical copy of
this file at the task-mandated path
`~/.hermes/bot/docs/reviews/findings_1_3.md`.
