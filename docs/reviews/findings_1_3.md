# Offload review — routstr delist, findings 1–3 (safety, confirmation, fail-safe)

Twelfth offload pass for findings 1–3, re-derived from primary sources in this
session against the CURRENT artifacts. Scope, per the original task: **item 1**
safety (delisting the SALE must never disable the routstr provider or touch the
T470 flat-router ladder), **item 2** post-delisting confirmation via re-fetch,
**item 3** fail-safe behaviour on absent, garbage and stale monitor signals.

Method this pass: the script was read end-to-end in both copies, the contract
suite read end-to-end, every cited line re-checked against its file, all
write-path/SQL/subprocess inventories re-run on the parsed source (AST, not
grep prose), both suites executed, and a fresh hermetic probe harness
(`docs/reviews/routstr_f13_probes/probe_f13_pass12.py`, written for this pass,
not reused from any earlier one) executed **53 checks, all PASS** — output
archived at `docs/reviews/routstr_f13_probes/pass12_output.txt`. The probe
replaces only the ssh boundary: it EXECUTES the module's own payloads against a
stand-in node holding a live `models` (SALE listing) table, a live
`upstream_providers` (provider ladder) table and a ladder-artifact file. No
network, no subprocess, no file-backed sqlite. Nothing below is carried over
unverified from an earlier pass.

**Artifact-path status (required report per task instructions):**

- `~/.hermes/bot/docs/routstr_delist_contract.md` — **MISSING — HIGH**.
  Re-verified this pass: `~/.hermes/bot/docs/` contains only `reviews/` and
  `routstr-delist.md`. The contract role is filled by two stand-ins, both read
  this pass: repo `docs/routstr-delist.md` (197 lines, `docs:N` below) and the
  bot copy `~/.hermes/bot/docs/routstr-delist.md` — this pass `diff` shows the
  bot copy **byte-identical** to the repo copy (both 197 lines), so the
  "14-line-stale bot doc" residual reported by earlier passes is **resolved**;
  only the path itself is still absent.
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
`pytest tests/ -q` → **121 passed in 0.50s**; deployed copy
`cd ~/.hermes/bot && pytest tests/test_routstr_delist.py -q` → **25 passed in
0.23s**; `crontab -l | grep -ci routstr` → **0** (no cron wiring live, so no
live exposure). No artifact was modified: the only paths written by this pass
are this file and the probe harness/output under
`docs/reviews/routstr_f13_probes/`.

## Finding 1 — Safety: SALE-delisting never disables the provider or touches the ladder — severity: **OK** (gaps: LOW)

1. **Every write path enumerated on the parsed source.** SQL inventory (probe
   A1a/A1c) finds exactly **5** SQL table references, all on `models`:
   `routstr_delist.py:355` (`UPDATE models SET enabled=0 WHERE enabled=1;`),
   `:361` (`UPDATE models SET enabled=1;`, legacy blanket builder), `:371`
   (`SELECT name FROM models WHERE enabled=1`), `:394` (`UPDATE models SET
   enabled=1 WHERE name IN (…)`) and `:408` (`SELECT COUNT(*) FROM models WHERE
   enabled=1`). Zero statements reference any other table — in particular
   `upstream_providers` (the provider ladder) has **3 occurrences, all inside
   docstrings** (`:35`, `:352`, `:771`), zero in executable code (probe A2).
   Raw-source confirmation of the same five SQL texts at lines
   355/361/371/394/408 (probe A1b). Mutating verbs are exactly 3 UPDATEs; the
   other 2 are read-only SELECTs.
2. **Executed, not merely asserted.** Probe A4 runs the module's REAL pull
   payload against the stand-in node: the ladder artifact is **byte-identical**
   after the delist (A4b), `upstream_providers` is **row-identical** (A4c), the
   `routstr` provider is still enabled and a candidate (A4d), all 3 advertised
   models are disabled and a pre-disabled operator row stays disabled (A4e),
   and no executed payload ever names `upstream_providers` (A4f). The same
   property is pinned semantically by `contract:468-507`
   (`TestSemanticGuardLadderUntouched`, ladder fixture built at `contract:108`,
   payload assertion at `contract:483`, provider-still-enabled assertion at
   `contract:487`) and, in the main suite, by `tests:302` (`TestSaleNotProvider`).
3. **Scoped relist cannot resurrect operator-disabled rows.** Probe A5: after a
   confirmed delist, `--relist` restores exactly the 3 captured names, leaves
   the pre-disabled row at 0, and the ladder artifact is still byte-identical.
   The parameterized builder is `routstr_delist.py:394`, asserted end-to-end at
   `tests:1166` (`assertIn("name IN (?,?)", remote)`).
4. **Blanket relist is refused before any remote call.** With no captured names,
   `routstr_delist.py:602` (`if not names and not args.relist_any:`) refuses —
   probe A6: rc 1, `action=relist_refused`, **zero** backend calls, no
   `delisted` flag written. The blanket SQL is reachable only via the explicit
   opt-in argument at `routstr_delist.py:526`; documented at `docs:29-30`
   ("**No blanket relist.**").
5. **Command-injection surface is closed.** Exactly **2** `subprocess.run` sites
   exist (`routstr_delist.py:459` nak publish, `:808` ssh docker-exec), with
   **`shell=True` count = 0**; `eval`/`exec` call sites = 0 (probe A3a/A3b).
   The remote pipeline is a single shlex-quoted argv element
   (`routstr_delist.py:414`, `:423`); probe A7 confirms the argv is 3 elements
   and that `shlex.split(cmd[2])` round-trips to
   `docker exec routstr public python3 -c …` intact even with a space in the
   container name. Pinned at `tests:345`/`tests:353` and `docs:137`.
6. **Filesystem writes are limited to the state file.** `os.*` mutation is only
   `replace` (`routstr_delist.py:235`) and `unlink` (`:243`), both in
   `save_state`'s atomic tmp-swap (probe A3c); the override marker is only
   `isfile`-probed (`:172`).
7. **Dry-run is intent-only.** Probe A8: `--manual --dry-run` performs **zero**
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
`:654`, `:710`, `:732`, `:752`), so a failed write after a CONFIRMED delist
(`:752`) would silently diverge local state from remote reality (cross-ref
findings 4–5).

**Verdict 1: OK** — no path disables the routstr provider or leaves the
`models` listing table, the ladder protection is proven by execution and by a
semantic test, and every remaining gap is LOW.

## Finding 2 — Post-delisting confirmation via re-fetch — severity: **OK** (delist requirement MET; residual: MEDIUM relist asymmetry, LOWs itemized)

1. **The required independent re-fetch exists.** `verify_pull_payload()`
   (`routstr_delist.py:400`, body `:401-411`, SQL text at `:408`) is a
   read-only `SELECT COUNT(*) FROM models WHERE enabled=1` — probe B1 confirms
   the payload contains **no** mutating verb (B1a) and is exactly that COUNT
   (B1b). It runs as a SEPARATE ssh round-trip via `_SshBackend.verify`
   (`routstr_delist.py:790`), invoked after the pull at `routstr_delist.py:682`
   inside the attempt loop (`:671`). Success requires
   `vres.get("ok") is True and vres.get("count") == 0`
   (`routstr_delist.py:683`, also matched in source by probe B7); `confirmed` is
   only then set (`:687`), and only `confirmed` unlocks the `delisted=True`
   write (`:747`) and rc 0. Suite pins: `contract:334` (happy path is exactly
   `["pull", "verify"]`), `tests:566` (`TestRefetchConfirmation`).
2. **A lying pull is refuted by execution.** Probe B2 simulates a pull that
   self-reports `ok` but whose UPDATE never lands: rc 1, `action=delist_failed`,
   `verify.count == 3`, **no** `delisted` flag, `consecutive_failures == 1`, and
   the retry sequence is exactly `["pull", "verify", "pull", "verify"]`
   (`MAX_PULL_ATTEMPTS = 2`, `routstr_delist.py:75`). Pinned end-to-end at
   `contract:346` (`test_unverified_pull_is_a_failed_delist`) and the breaker
   path at `tests:816` (`TestCircuitBreaker`).
3. **Happy path is verified and recorded.** Probe B3: rc 0, `confirmed=True`,
   `verified_count == 0`, exactly one pull + one verify, durable `delisted=true`
   with the captured advertised names in `pulled_models`. Probe B4 shows the
   converse — a verify reporting `count=3` refutes an ok pull (rc 1, no flag,
   breaker tick) — and probe B5 shows a verify **transport** failure is an
   attempt failure, not a success (rc 1, no flag, 4 round-trips).
4. **Garbage cannot confirm.** The verify result passes through
   `_SshBackend._run` (`routstr_delist.py:806` bounds every round-trip by
   `min(SSH_TIMEOUT_S, remaining)`); a non-zero rc, unparseable stdout or a
   missing `ok`/`count` key all yield a non-confirming result, because
   `None == 0` is False at `:683`. Failure direction is therefore always safe:
   garbage can only fail the run, never confirm it.
5. **Residual — MEDIUM: the relist direction has no symmetric re-fetch.**
   Relist success is gated on the round-trip self-report alone
   (`routstr_delist.py:626`, `if not res.get("ok"):`), and on that self-report
   the run writes `delisted=false` and pops `pulled_models`
   (`routstr_delist.py:635`). Probe B6 measures the asymmetry directly: after a
   confirmed delist, `--relist` yields `kinds == ["relist"]` — **no verify
   follows**. A lying relist (rc 0, ok printed, UPDATE not landed — the same
   fault class the contract deemed must-fix for delist) therefore both fakes a
   restored listing and destroys the scoped name set; a subsequent scoped
   `--relist` is then refused (`routstr_delist.py:602`) and recovery forces
   `--relist-any` (`:526`), which re-enables rows the operator had deliberately
   disabled (`docs:29-30`), or a fresh delist/relist cycle. The contract
   mandates the re-fetch only for a fired delist (`docs:69`), so this is an
   asymmetry rather than a contract breach — but the fix is cheap: verify after
   relist (e.g. COUNT(*) > 0, or a per-name re-read) before popping
   `pulled_models`.
6. LOW notes: (a) the dry-run path sets `confirmed=True` without any remote
   verify (`routstr_delist.py:679-681`) — intent-only, there is nothing to
   confirm; (b) the verify round-trip shares the ssh transport and last-line
   JSON parsing with the pull (`routstr_delist.py:806-822`), so it is
   independent in the contract's sense of a separate round-trip (`docs:69`) but
   a systematic transport-level fault (wrong container, shadowed DB path) could
   satisfy both — directionally safe, since a fooled verify can only keep the
   run failing into the breaker.

**Verdict 2: OK** — the required post-delisting confirmation exists, is a
separate read-only round-trip, gates the durable flag, and is pinned by both
suites; one MEDIUM residual (relist asymmetry) and two LOW notes above.

## Finding 3 — Fail-safe on absent, garbage and stale monitor signals — severity: **OK** (residuals: LOW)

Everything that can reach a delist funnels through
`fire = args.delist or dec["fire"]` (`routstr_delist.py:649`), where
`dec["fire"] = bool(accel or var or override)` (`routstr_delist.py:317`).

1. **Absence — OK.** No `--preds` leaves the feed empty; acceleration requires
   non-empty preds on both sides (`routstr_delist.py:107`) and variance requires
   non-empty preds (`:143`), so a first run with no stored baseline can never
   fire (`contract:308`, `test_first_run_without_baseline_is_quiet`). Manual
   override stays available by design.
2. **Garbage — OK.** `_read_preds` (`routstr_delist.py:468`) never raises, drops
   non-dict entries and returns `[]` on any parse failure. An explicitly
   requested but unusable feed is a FEED ERROR (`preds_error`,
   `routstr_delist.py:585`) with rc 1 when nothing fired (`:660`). Probes C3/C4:
   an invalid-JSON feed yields rc 1, `preds_error=true`, `action=none`, zero
   remote calls; a feed that is both garbage AND aged surfaces as
   `preds_error=true` with `preds_stale=false` (raw_preds is empty at `:589`),
   both exiting 1. **The stored baseline is never wiped** —
   `update_state` only overwrites the snapshot when preds is non-empty
   (`routstr_delist.py:261`); probes C3b/C2b confirm the snapshot survives
   byte-for-byte. Type-guards: `uncertainty` is isinstance-guarded with bool
   explicitly excluded (`routstr_delist.py:152`, pinned `tests:146`
   `test_non_numeric_uncertainty_ignored_not_crash`) and `exhausts_in_hours` is
   guarded too; probe C5a/C5b/C5c show string, bool, None and non-dict entries
   produce no fire and no crash.
3. **Stale — OK.** `STALENESS_S = 1800` (`routstr_delist.py:78`);
   `feed_is_stale` (`routstr_delist.py:485`) ends in
   `return not (0 <= age <= max_age_s)` (`:494`), i.e. undeterminable age
   (missing file, OSError) and a future mtime are BOTH treated as stale. Probe
   C1 measures seven states: missing → True, aged 3600 s → True, future mtime →
   True, fresh → False, age exactly 1800 s → False, age 1800.5 s → True, age 0 →
   False. Wiring: a stale feed zeroes the preds **before** trigger evaluation
   (`routstr_delist.py:589`) so the level-based variance trigger cannot fire on
   dead data, and before any baseline refresh — probe C2: stale feed → rc 1,
   `preds_stale=true`, `action=none`, zero remote calls, snapshot untouched;
   probe C2c is the control showing the identical numbers with a FRESH mtime DO
   delist, which proves the guard rather than mere absence of input. Suite pins:
   `tests:928` (`TestStalenessGuard`), `tests:937`
   (`test_stale_feed_never_triggers`), `tests:968`
   (`test_staleness_threshold_boundary`), `tests:995`
   (`test_stale_feed_baseline_not_consumed`).
4. **Manual override is deliberately never gated on freshness — verified.**
   Probe C6: a stale feed plus `--manual` delists (rc 0, `preds_stale=true`
   observed but not obeyed, `["pull","verify"]` executed). Pinned at
   `tests:427` (`test_manual_override_is_never_gated_on_feed_staleness`) and
   `tests:980` (`test_stale_feed_exit_zero_when_override_fires`); documented at
   `docs:60` ("The manual override is never gated on freshness.").
5. **Budget and breaker fail closed.** Probe C8: an exhausted action budget
   returns `ok=false` with an `action budget exhausted` error and spawns **zero**
   subprocesses (bound at `routstr_delist.py:801-806`). Repeated failed runs
   refuse all further remote action until `--unblock`
   (`routstr_delist.py:529`), and dry-run never counts toward the breaker.

Residuals (LOW):

- **(a) `--preds-key` scoping is opt-in, default unscoped.** Filtering happens
  only when the flag is passed; `evaluate_triggers` itself passes **no** key to
  `variance_jumped` (`routstr_delist.py:303`). Probe C7 reproduces it on the
  deployed copy: an openrouter-only feed with `uncertainty 0.95` fires the
  routstr delist with no flag (C7b) while the same feed with `--preds-key zai`
  is quiet (C7c); `evaluate_triggers` applies no implicit filter (C7a). Scoping
  is documented (`docs:54-55`) and carried in the runbook cron example
  (`docs:106`), so the residual is operator-omission risk. Caveat: `docs:55`
  states the guarantee unconditionally ("another provider's variance spike can
  never pull the routstr SALE") — the doc should say "with `--preds-key`".
- **(b) mtime-only freshness** (`routstr_delist.py:485-494`): a writer that
  rewrites the feed with OLD data refreshes the mtime and bypasses the guard
  (content-stale / mtime-fresh is undetectable). The contract accepts mtime
  (`docs:56`); an embedded `generated_at` check would be stronger.
- **(c) Cosmetic**: `_hours` accepts a bool while the variance guard excludes it
  (`routstr_delist.py:152` vs the hours helper) — arithmetic-safe, no crash
  path (probe C5d); the override marker is presence-based with no TTL
  (`routstr_delist.py:172`), which is operator-controlled by design.
- **(d) Cross-ref findings 4–5**: the quiet-run state write (`routstr_delist.py:654`),
  like all 8 `save_state` call sites, ignores the return value.

**Verdict 3: OK** — absence and garbage are safe, staleness is guarded in the
fail-safe direction with a fresh-input control, the override is intentionally
ungated, and budget/breaker semantics fail closed; residuals are LOW as
itemized.

---

Provenance: twelfth offload pass for findings 1–3. Earlier passes (files at
this path; Gate 2.5 cold review `docs/reviews/routstr_delist_review.md`)
correctly found Finding 2 REFUTED-HIGH (no re-fetch) and Finding 3
PARTIAL-HIGH (no freshness guard) against the pre-fix 602-line script, and
subsequent passes re-adjudicated both OK against the current 829-line
artifacts. This pass independently re-derives the same three verdicts: script
read end-to-end in both copies (byte-identical), contract suite read end-to-end
and executed against the deployed copy, 65 cited file:line pairs re-verified
against their files (probe D1), write-path inventories re-run on the AST, 53
hermetic probe checks all PASS (`docs/reviews/routstr_f13_probes/pass12_output.txt`),
suites 121 + 25 green, `crontab -l` re-checked (zero routstr entries). Verdicts:
**1 OK** (gaps LOW), **2 OK** (MEDIUM relist-asymmetry residual), **3 OK** (LOW
residuals). Artifact-path report: the contract markdown is STILL MISSING at the
bot path (**HIGH**), and — correction to earlier passes — the bot's
`routstr-delist.md` copy is now byte-identical to the repo copy, so that
staleness residual is closed. No artifact was modified. `~/.hermes/bot` is not
a git repository, so the required local commit lands in the workspace repo
(`merchant-routing`) covering `docs/reviews/findings_1_3.md` and the probe
harness, with an identical copy of this file at the task-mandated path
`~/.hermes/bot/docs/reviews/findings_1_3.md`.
