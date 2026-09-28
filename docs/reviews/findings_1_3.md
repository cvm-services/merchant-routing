# Offload review — routstr delist, findings 1–3 (safety, confirmation, fail-safe)

<!-- citation-count: total=175 script=133 contract=12 tests=14 docs=16 -->

Fifteenth offload pass for findings 1–3, re-derived from primary sources in this
session against the CURRENT artifacts. Scope, per the original task: **item 1**
safety (delisting the SALE must never disable the routstr provider or touch the
T470 flat-router ladder), **item 2** post-delisting confirmation via re-fetch,
**item 3** fail-safe behaviour on absent, garbage and stale monitor signals.

The deliverable already existed at this path from fourteen earlier passes, so the
dispatch was handled as a **re-derivation**: the document below was rewritten in
place from evidence collected in this session, not appended to, and nothing in it
is carried over unverified. All three deployed artifacts were confirmed
byte-identical to their repo copies before any analysis (md5, probe A0a/A0b/A0c —
`2ea724ef08d857cd7b88a957300e70b4`, `031851b356f0de4089512f02f13f05cc`,
`e385af98b9c142eec736672d4dcca290`), so the verdicts are re-derived against the
same bytes the earlier passes saw. **They came out unchanged: 1 OK, 2 OK, 3 OK.**
What this pass did change is the review record: three record defects are corrected
(two of them substantive — a state-shape claim about the quiet path that the
fourteenth pass asserted and that measurement refutes, and an unqualified
"dry-run is intent-only" guarantee that holds only on the firing path), and **two
new observations** are measured, one of which carries a MEDIUM severity because
its failure direction is loss-of-protection rather than safe.

Method this pass: the script was read end-to-end in both copies, the contract
suite read end-to-end, the doc read end-to-end, every cited line re-checked
against its file, all SQL/subprocess/write-path inventories re-run on the parsed
source (AST, not grep prose), both suites executed, and a **fresh** hermetic probe
harness — `docs/reviews/routstr_f13_probes/probe_f13_pass15.py`, written for this
pass, not reused from any earlier one — executed **74 checks: 74/74 PASS**. The
same harness was first run against the previous (fourteenth-pass) copy of this
document, which also scored **74/74 PASS**: unlike the thirteenth→fourteenth
handoff, that pre-rewrite run caught no *mis-filed citation* (its D1 pair audit
and D2 resolution checks were both clean), so the corrections below come from
re-measuring the inventory and from reading the quiet-path code against the claim
made about it. **No transcript file was archived for this pass** (the earlier
passes' `pass12/13/14_output*.txt` remain in the probe directory); the harness is
committed, prints its measurements, and reproduces the full transcript
byte-for-byte on re-run. It replaces only the ssh boundary: it EXECUTES the
module's own payloads against a stand-in node holding a live `models` (SALE
listing) table, a live `upstream_providers` (provider ladder) table and a
ladder-artifact file on disk. No network, no subprocess, no file-backed sqlite.

**Artifact-path status (required report per task instructions):**

- `~/.hermes/bot/docs/routstr_delist_contract.md` — **MISSING — HIGH**.
  Re-verified this pass: probe A0d asserts the path is absent (`exists=False`).
  The contract role is filled by the three stand-ins below, all read end-to-end
  this pass. This is the **fifth consecutive** pass to report the same absent
  path; the finding is not a transient.
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
contract suite (752 lines, 25 cases); `tests:N` = repo `tests/test_routstr_delist.py`
(1172 lines, the main suite); `docs:N` = repo `docs/routstr-delist.md` (197 lines).
Citation counting rule (probe D2/D4): every occurrence of an artifact file name or
doc alias immediately followed by `:NNN`; a range `A-B` is counted at `A` only.
The `citation-count` comment at the top of this file is machine-checked against
that measurement by probe D4, so the count cannot drift silently again.

Execution evidence this pass (TMPDIR moved off `/tmp` to
`~/.cache/tmp-f13-pass15` for every run):
`pytest tests/ -q` → **121 passed in 4.79s**; `pytest tests/test_routstr_delist_contract.py -q`
→ **25 passed in 2.18s**; `pytest tests/test_routstr_delist.py -q` → **96 passed in
4.82s**; `python3 -m unittest discover -s tests` → **Ran 96 tests, OK**; deployed
copy `cd ~/.hermes/bot && pytest tests/test_routstr_delist.py -q` → **25 passed in
1.40s**; `crontab -l | grep -ci routstr` → **0** (3 crontab lines total, none
referencing routstr, so the 5-minute SLA has no live caller and the fail-safe
apparatus is latent — a documented deferral at `docs:112-115`, not a regression).
No reviewed artifact was modified: all three md5s unchanged before and after
(A0a/A0b/A0c), and the only paths written by this pass are this file and the probe
harness under `docs/reviews/routstr_f13_probes/`. `~/.hermes/bot` is not a git
repository, so the required local commit lands in the workspace repo
(`merchant-routing`).

**Corrections new in this pass** (all defects in the *review record*; none in the
reviewed code, and none in the deployed artifacts, whose md5s did not move):

1. **The fourteenth pass's own citation total does not reproduce against the
   document that states it — LOW (record defect, now structurally prevented).**
   Its preamble recorded "**158** in the document below (119 `routstr_delist.py`
   + 11 `contract` + 13 `tests` + 15 `docs`)". Measured against that very text
   with the counting rule above (probe D2, and independently by classified
   extraction): **153** citations — **114** `routstr_delist.py` + **11**
   `contract` + **13** `tests` + **15** `docs`. The three non-script buckets
   reproduce **exactly**, which isolates the drift to the script bucket (119
   claimed, 114 present) and to the total; the earlier figure is treated as
   superseded by measurement rather than as a fabrication, since the fourteenth
   pass's own pair list is not available to compare against. This is the third
   consecutive pass to record drift in a provenance count (the fourteenth pass
   made the same observation about the thirteenth), which is why this pass makes
   the number **machine-checked**: probe D4 parses the `citation-count` comment
   above and fails if it disagrees with the measurement.
2. **A quiet run's state shape is mis-described, and the probe label attached to
   it is wrong — MEDIUM (record defect; it misstates a fail-safe-relevant
   invariant).** The fourteenth pass's Finding 3 item 1 read: "With no `--preds`
   the feed is empty (probe **C12**: a quiet run stores only `ts`/`last_dry_run`)".
   Both halves are wrong. (i) `C12` is defined *elsewhere in the same document*
   (its Finding 3 item 5) as "dry-run never counts toward the breaker", so the
   label does not denote the probe that measures a quiet run's state. (ii) The
   claimed shape is false: a state written by a **quiet** run contains
   `delisted`, `snapshot` and `ts` — measured this pass as
   `['delisted', 'snapshot', 'ts']` (probes A11b/A11d) — and
   **never** `last_dry_run`, which is written only by the FIRED dry-run path
   (`routstr_delist.py:705`). The parenthetical describes the fired dry-run state
   (probe A10, whose keys really are only `ts` + `last_dry_run`), not a quiet
   run. This is the same conflation that correction 3 turns into a live finding.
3. **"Dry-run is intent-only" is stated unqualified, but the purity guarantee
   holds only on the firing path — MEDIUM (behaviour + doc defect).** See
   Finding 1 item 8 and gap (e): on the non-firing path `--dry-run` writes the
   state file and consumes the acceleration baseline, which falsifies the
   contract's flat "no baseline consumption" claim at `docs:87-89` and means a
   diagnostic run can silently disarm a real trigger (loss-of-protection
   direction). The fourteen-pass text asserted the guarantee without the
   qualifier in both its Finding 1 item 7 and its Finding 3 item 1.

**Standing corrections re-verified this pass** (kept so the record is
self-contained; each was re-measured, not copied):

- the `test_manual_override_is_never_gated_on_feed_staleness` name bus lives in
  the **contract** suite at `contract:427`, not in the main suite (probe D1
  carries it with its expected text; its sibling `tests:980` is the main-suite
  equivalent and both were read back);
- the five SQL references have two line conventions, and this pass states both
  explicitly: raw SQL text at `routstr_delist.py:355`, `routstr_delist.py:361`,
  `routstr_delist.py:371`, `routstr_delist.py:394`, `routstr_delist.py:408`
  (probe A2a, comment lines excluded — identical to the AST string-literal start
  lines measured by probe A1a), carried by payload builders whose first fragment
  begins at `routstr_delist.py:369`, `routstr_delist.py:392` and
  `routstr_delist.py:406`;
- the filesystem write surface includes the state **directory** created at
  `routstr_delist.py:229` (probe A5a), not just the state file.

**New observations this pass** (one MEDIUM, one LOW):

- **MEDIUM:** dry-run purity is conditional on firing — a non-firing `--dry-run`
  writes state and consumes the acceleration baseline (Finding 1 item 8, gap (e),
  probes A11a–A11d);
- **LOW:** a `--preds-key` that matches no feed row is silently indistinguishable
  from a healthy quiet run — rc 0, `preds_error=false`, `preds_stale=false`, zero
  round-trips (Finding 3, residual (j), probe C14).

## Finding 1 — Safety: SALE-delisting never disables the provider or touches the ladder — severity: **OK** (gaps: one MEDIUM dry-run-purity gap, rest LOW)

1. **Every write path enumerated on the parsed source.** The SQL inventory over
   the parsed AST (probe A1a/A1c, which stops at every string literal so an
   implicitly concatenated f-string payload is counted once) finds exactly **5**
   SQL table references, all on `models`: `routstr_delist.py:355`
   (`UPDATE models SET enabled=0 WHERE enabled=1;`), `routstr_delist.py:361`
   (`UPDATE models SET enabled=1;`, legacy blanket builder),
   `routstr_delist.py:371` (the pull payload's
   `SELECT name FROM models WHERE enabled=1`, payload starting at
   `routstr_delist.py:369`), `routstr_delist.py:394` (the scoped relist payload's
   `UPDATE models SET enabled=1 WHERE name IN (…)`, payload starting at
   `routstr_delist.py:392`) and `routstr_delist.py:408` (the verify payload's
   `SELECT COUNT(*) FROM models WHERE enabled=1`, payload starting at
   `routstr_delist.py:406`). The materialised table set is exactly `['models']`
   (probe A1b); zero statements reference any other table. In particular
   `upstream_providers` (the provider ladder) has **3 occurrences, all inside
   docstrings** — text at `routstr_delist.py:35`, `routstr_delist.py:352` and
   `routstr_delist.py:771` — and **zero in executable code** (probe A3a: all
   three literal start lines fall inside docstring spans; probe A3b: **285**
   executable string literals inspected, none naming it). Mutating verbs are
   exactly 3 UPDATEs (`routstr_delist.py:355`, `routstr_delist.py:361`,
   `routstr_delist.py:394`); the other 2 are read-only SELECTs.
2. **Executed, not merely asserted.** Probe A6 runs the module's REAL pull
   payload against the stand-in node: the ladder artifact is **byte-identical**
   after the delist (A6b, 340 B), `upstream_providers` is **row-identical** (A6c,
   rows `openrouter`/`routstr`/`zai`), the `routstr` provider is still enabled
   and a ladder candidate (A6d), all 3 advertised models are disabled and a
   pre-disabled operator row stays disabled (A6e), and no executed payload ever
   names `upstream_providers` (A6f). The same property is pinned semantically by
   `contract:468` (`TestSemanticGuardLadderUntouched`; ladder fixture written at
   `contract:108`, payload assertion at `contract:483`, provider-still-enabled
   assertion at `contract:487`) and, in the main suite, by `tests:302`
   (`TestSaleNotProvider`).
3. **Scoped relist cannot resurrect operator-disabled rows.** Probe A7: after a
   confirmed delist, `--relist` restores exactly the 3 captured names, leaves the
   pre-disabled row at 0, and the ladder artifact is still byte-identical. The
   parameterized builder is `routstr_delist.py:394`, asserted end-to-end at
   `tests:1166`.
4. **Blanket relist is refused before any remote call.** With no captured names,
   `routstr_delist.py:602` refuses — probe A8: rc 1, `action=relist_refused`,
   **zero** backend round-trips, and the state file was not even created (A8b).
   The blanket SQL is reachable only via the explicit opt-in at
   `routstr_delist.py:526`; documented at `docs:29`. Probe B7f shows the cost of
   taking that opt-in while the scoped set is gone: every row, including a
   pre-disabled operator row, comes back enabled (Finding 2 item 5).
5. **Command-injection surface is closed.** Exactly **2** `subprocess.run` sites
   exist (`routstr_delist.py:459` nak publish, `routstr_delist.py:808` ssh
   docker-exec), with **`shell=True` count = 0** and **`eval`/`exec` call sites =
   0** (probe A4a/A4b). The remote pipeline is built across
   `routstr_delist.py:414` and `routstr_delist.py:423` as a single shlex-quoted
   argv element; probe A9 confirms the argv is 3 elements and that
   `shlex.split(cmd[2])` round-trips to
   `["docker", "exec", "routstr public", "python3", …]` intact even with a space
   in the container name. Pinned at `tests:345` (the round-trip itself at
   `tests:354`) and documented at `docs:137`.
6. **Filesystem writes are confined to the state path.** The complete write
   surface is `os.makedirs` of the state directory (`routstr_delist.py:229`), the
   single write-mode `open()` of the tmp file (`routstr_delist.py:231`),
   `os.replace` of that tmp file (`routstr_delist.py:235`) and `os.unlink` of a
   stale tmp (`routstr_delist.py:243`) — all inside `save_state`'s atomic
   tmp-swap. Probe A5a enumerates every `os.*` write call AND every `open()` mode
   in the module: exactly one write (`:231`) against three reads
   (`routstr_delist.py:214`, `routstr_delist.py:457`, `routstr_delist.py:476`).
   Nothing outside the state path is written, and the override marker is only
   `isfile`-probed (`routstr_delist.py:172`).
7. **Dry-run is intent-only — on the firing path.** Probe A10: `--manual
   --dry-run` performs **zero** remote round-trips (A10a), introduces **no**
   durable `delisted` flag, and leaves state keys `ts` + `last_dry_run` only
   (A10b). Wired at `routstr_delist.py:699`; pinned by `contract:731`
   (`test_dry_run_publishes_no_event_and_flips_no_flag`) and `tests:1072`
   (`TestDryRunPurity`). **This guarantee is conditional — see item 8**; both
   suite pins exercise `--manual --dry-run`, i.e. only the firing path.
8. **NEW — dry-run purity does NOT extend to the non-firing path (MEDIUM).** The
   quiet path at `routstr_delist.py:651` is reached whenever `fire` is false, and
   it does not test `args.dry_run`: it calls `update_state(...)` and
   `save_state(...)` at `routstr_delist.py:651-654` exactly as a real run does.
   Probe A11 measures it end-to-end with a fresh feed and a pre-existing
   `snapshot` of `{"zai␟1h": 11.0}` whose successor value (10.0 h) is a 1.0 h
   move — below the 2.0 h threshold, so the run is genuinely quiet:
   **A11a** rc 0, `action=none`, zero remote round-trips (purity holds for
   *remote* action); **A11b** the persisted `snapshot` is **refreshed to
   `{"zai␟1h": 10.0}`**, i.e. the acceleration baseline **IS consumed**;
   **A11c** no `last_dry_run` key is written, so the dry run leaves **no trace
   at all** of having happened; **A11d** the resulting state is *identical*
   (modulo `ts`) to the state a real quiet run leaves — measured
   `['delisted', 'snapshot', 'ts']` in both. Consequences: (i) `docs:87-89`
   claims dry-run does "no baseline consumption", which is false on this path, so
   an operator who previews a run with `--dry-run` while a live feed is present
   has, in the protection-relevant case, consumed the very movement the next cron
   tick would have fired on — a **loss-of-protection** direction, not a safe one;
   (ii) `last_dry_run` is not even written, so the disarm is invisible. Not a
   BLOCKER: no remote mutation occurs, the quiet path is the normal cron path,
   and an operator must invoke `--dry-run` with a live feed between ticks to
   trigger it. Fix is either one word of documentation (qualify `docs:87-89`) or
   one line of code (guard the quiet-path state write behind `not args.dry_run`,
   and record `last_dry_run` on it).

Gaps (non-blocking): **(e) MEDIUM** is item 8 above. All others LOW:
**(a)** `--ssh-target`/`--container` (`routstr_delist.py:536`,
`routstr_delist.py:537`) let an operator point the mutating payload at any
host/container — by design, nothing validates that the target is the sell node;
**(b)** the payloads hard-code `/app/data/keys.db` ×4 (`routstr_delist.py:370`,
`routstr_delist.py:385`, `routstr_delist.py:393`, `routstr_delist.py:407`) — a
container layout change would mutate whatever DB lives at that path;
**(c)** `save_state`'s return value is ignored at all **8** call sites
(`routstr_delist.py:565`, `routstr_delist.py:622`, `routstr_delist.py:629`,
`routstr_delist.py:638`, `routstr_delist.py:654`, `routstr_delist.py:710`,
`routstr_delist.py:732`, `routstr_delist.py:752`; probe A5b confirms no call site
consumes it), so a failed write after a CONFIRMED delist
(`routstr_delist.py:752`) would silently diverge local state from remote reality
(cross-ref findings 4–5); **(d)** the pull payload reads the enabled set and then
disables it in a separate statement (`routstr_delist.py:371` then
`routstr_delist.py:372`), so a row enabled by another writer inside that window
is disabled without being captured and would not be restored by a scoped relist —
narrower than any operator action and fail-safe in the protection direction, but
real.

**Verdict 1: OK** — no path disables the routstr provider or leaves the `models`
listing table, the ladder protection is proven by execution and by a semantic
test, and every gap is LOW except the newly measured MEDIUM dry-run-purity gap
(item 8 / gap (e)), which is a diagnostic-path guarantee defect rather than a
safety hazard.

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
   `contract:346` (`test_unverified_pull_is_a_failed_delist`) and on the breaker
   path at `tests:816` (`TestCircuitBreaker`).
3. **Happy path is verified and recorded.** Probe B3: rc 0, `confirmed=true`,
   `verified_count == 0`, exactly one pull + one verify, and a durable
   `delisted=true` (B3b) carrying the captured advertised names in
   `pulled_models` — the pre-disabled operator row is *not* captured, which is
   what makes the scoped relist of item 3 in Finding 1 exact.
4. **Garbage cannot confirm.** The verify result passes through
   `_SshBackend._run` (the round-trip is bounded by `min(SSH_TIMEOUT_S,
   remaining)` at `routstr_delist.py:801-806`; the result shape is settled at
   `routstr_delist.py:822`); a non-zero rc, unparseable stdout, or a missing
   `ok`/`count` key all yield a non-confirming result, because `None == 0` is
   False at `routstr_delist.py:683` (probe B8a). Probe B5a shows a verify
   **transport** failure is an attempt failure, not a success: rc 1, kinds
   `["pull", "pull"]` (the verify never reaches the node, so nothing is
   recorded), no flag, `consecutive_failures == 1`. Failure direction is
   therefore always safe: garbage can only fail the run, never confirm it.
5. **Residual — MEDIUM: the relist direction has no symmetric re-fetch.**
   Relist success is gated on the round-trip self-report alone
   (`routstr_delist.py:626`), and on that self-report the run clears
   `delisted` and pops `pulled_models` (`routstr_delist.py:635`). Probe B7
   measures the asymmetry end-to-end: after a confirmed delist, `--relist`
   yields `kinds == ["relist"]` — **no verify follows** (B7a). A lying relist
   (rc 0, ok printed, UPDATE not landed — the same fault class the contract
   deemed must-fix for delist) is reported as `action=relist`, **rc 0** (B7b),
   while the listing is measurably **NOT** restored (B7c) and the scoped name set
   is destroyed (B7d, `pulled_models` → absent). A subsequent scoped `--relist`
   is then refused (`routstr_delist.py:602`; probe B7e), so recovery forces
   `--relist-any` (`routstr_delist.py:526`), which in probe B7f re-enables
   **every** row — including the operator-disabled one — or a fresh
   delist/relist cycle. The contract mandates the re-fetch only for a fired
   delist (`docs:69`), so this is an asymmetry rather than a contract breach, but
   the fix is cheap: verify after relist (e.g. a per-name re-read, or
   `COUNT(*) > 0`) before popping `pulled_models`.
6. LOW notes: **(a)** the dry-run firing path sets `confirmed=True` without any
   remote verify (`routstr_delist.py:679` is `if args.dry_run:`,
   `routstr_delist.py:680` is `confirmed = True  # intent only: no remote
   verify`) — intent-only, there is nothing to confirm; **(b)** the verify
   round-trip shares the ssh transport, timeout bound and last-line JSON parsing
   with the pull (the parse/clamp live at `routstr_delist.py:806` and
   `routstr_delist.py:822`), so it is independent in the contract's sense of a
   separate round-trip (`docs:69`) but a systematic transport-level fault (wrong
   container, shadowed DB path) could satisfy both — directionally safe, since a
   fooled verify can only keep the run failing into the breaker.

**Verdict 2: OK** — the required post-delisting confirmation exists, is a
separate read-only round-trip, gates the durable flag, and is pinned by both
suites; one MEDIUM residual (relist asymmetry) and two LOW notes above.

## Finding 3 — Fail-safe on absent, garbage and stale monitor signals — severity: **OK** (residuals: LOW)

Everything that can reach a delist funnels through
`fire = args.delist or dec["fire"]` (`routstr_delist.py:649`), where
`dec["fire"] = bool(accel or var or override)` (`routstr_delist.py:317`).

1. **Absence — OK.** With no `--preds` the feed is empty (`_read_preds`,
   `routstr_delist.py:468`, returns `[]` for a falsy argument), acceleration
   requires non-empty preds on both sides (`routstr_delist.py:107`) and variance
   requires non-empty preds (`routstr_delist.py:143`), so a first run with no
   stored baseline can never fire (`contract:308`,
   `test_first_run_without_baseline_is_quiet`). Manual override stays available
   by design. **Correction:** the fourteenth pass supported this item with "probe
   C12: a quiet run stores only `ts`/`last_dry_run`". That is wrong twice over —
   `C12` denotes the breaker/dry-run probe, and a quiet run's state keys are
   `['delisted', 'snapshot', 'ts']`, never `last_dry_run` (probes A11b/A11d;
   `last_dry_run` is written only at `routstr_delist.py:705`, on the FIRED
   dry-run path). The absent-feed conclusion stands on `routstr_delist.py:107`
   and `routstr_delist.py:143` plus `contract:308`, which is why it is restated
   here with those citations instead of the mis-attributed probe.
2. **Garbage — OK.** `_read_preds` (`routstr_delist.py:468`) never raises, drops
   non-dict entries (`routstr_delist.py:479`) and returns `[]` on any parse
   failure. An explicitly requested but unusable feed is a FEED ERROR
   (`preds_error`, `routstr_delist.py:585`) with rc 1 when nothing fired
   (`routstr_delist.py:660`). Probes: invalid JSON → rc 1, `preds_error=true`,
   `action=none`, zero remote round-trips (C4a); a feed that is both garbage AND
   aged surfaces as `preds_error=true` with `preds_stale=false`, because
   `raw_preds` is empty at `routstr_delist.py:589` (C4c), both exiting 1. **The
   stored baseline is never wiped** — `update_state` only overwrites the snapshot
   when preds is non-empty (`routstr_delist.py:261`); probe C2 shows the snapshot
   surviving byte-for-byte on the stale path, and probe C7 on the path where a
   delist actually FIRES. Type-guards: `uncertainty` is isinstance-guarded with
   bool explicitly excluded (`routstr_delist.py:152`, pinned by `tests:146`) and
   `exhausts_in_hours` is guarded too (`routstr_delist.py:196`); probes C6a/C6b
   show string, bool, None and non-dict entries produce no fire, no crash, and an
   all-empty trigger set through the CLI. (Probe C6d, residual (g), shows the
   same malformed rows DO raise `AttributeError` if the pure helpers are called
   directly.)
3. **Stale — OK.** `STALENESS_S = 1800` (`routstr_delist.py:78`);
   `feed_is_stale` (`routstr_delist.py:485`) ends in
   `return not (0 <= age <= max_age_s)` (`routstr_delist.py:494`), with an
   `OSError` (missing file / unreadable) short-circuiting to `True`
   (`routstr_delist.py:495-496`), i.e. undeterminable age and a future mtime are
   BOTH treated as stale. Probe C1 measures the matrix: missing → stale, aged
   3600 s → stale, future mtime → stale, fresh → not stale, **age exactly 1800 s
   → not stale** (boundary inclusive), age 1800.5 s → stale. Wiring: a stale feed
   zeroes the preds **before** trigger evaluation (`routstr_delist.py:589`,
   `routstr_delist.py:591-592`) so the level-based variance trigger cannot fire
   on dead data, and before any baseline refresh. Probe C2: stale feed → rc 1,
   `preds_stale=true`, `action=none`, zero remote round-trips, snapshot untouched;
   probe C2c is the control showing the identical numbers with a FRESH mtime DO
   delist, which proves the guard rather than mere absence of input. Suite pins:
   `tests:928` (`TestStalenessGuard`), `tests:937` (`test_stale_feed_never_triggers`),
   `tests:968` (`test_staleness_threshold_boundary`), `tests:995`
   (`test_stale_feed_baseline_not_consumed`). The guard is documented at
   `docs:56-58`.
4. **Manual override is deliberately never gated on freshness — verified.**
   Probe C7: a stale feed plus `--manual` delists (rc 0, `preds_stale=true`
   observed but not obeyed, exactly `["pull","verify"]` executed) **and leaves
   the stored baseline unrefreshed** (the snapshot measured before the run is
   present unchanged after it, `{"zai␟1h": 100.0}`), so overriding the freshness
   guard does not let dead data pollute the acceleration baseline. The same
   override behaviour holds when the feed is unparseable rather than merely old
   (C7c: rc 0, `preds_error=true`, `action=delist`). Pinned at `contract:427`
   (`test_manual_override_is_never_gated_on_feed_staleness`) and `tests:980`
   (`test_stale_feed_exit_zero_when_override_fires`); documented at `docs:60`.
5. **Budget and breaker fail closed.** Probe C10: an exhausted action budget
   returns `ok=false` with an `action budget exhausted` error and spawns **zero**
   subprocesses (bound at `routstr_delist.py:801-806`); with 5 s of budget left
   the per-round-trip timeout is clamped to the remaining budget (C10b measures
   within **0.01 s** of the 5 s deadline — 4.99996–4.99999 s across runs — i.e.
   `min(SSH_TIMEOUT_S, remaining)`).
   Probe C11: three consecutive failed runs give rc `[1, 1, 3]`, a durable
   `blocked=true` at `consecutive_failures == BREAKER_THRESHOLD`
   (`routstr_delist.py:730`, `routstr_delist.py:739`), and a blocked run then
   refuses **all** remote action (`action=blocked` at `routstr_delist.py:569`,
   returning 3 at `routstr_delist.py:578`, zero new backend round-trips) until
   `--unblock` (`routstr_delist.py:529`). Probe C12: dry-run never counts toward
   the breaker.

Residuals (LOW):

- **(a) `--preds-key` scoping is opt-in, default unscoped.** Filtering happens
  only when the flag is passed (`routstr_delist.py:597`); `evaluate_triggers`
  itself passes **no** key to `variance_jumped` (`routstr_delist.py:303`), as its
  signature confirms — `def evaluate_triggers(preds_now, prev_state, *, override=…,
  move_hours=…, variance_threshold=…)` at `routstr_delist.py:272` has no `key`
  parameter, while the optional filter it never passes lives in the callee at
  `routstr_delist.py:132` (`def variance_jumped(preds, *, threshold=…, key=None)`).
  Probe C8 reproduces it: an openrouter-only feed with `uncertainty 0.95` fires
  the routstr delist with no flag (C8a) while the same feed with `--preds-key zai`
  is quiet (C8b); `inspect.signature` confirms no implicit filter (C8c). Scoping
  is documented (`docs:54`) and carried in the runbook cron example
  (`docs:106`), so the residual is operator-omission risk. Caveat: `docs:55`
  states the guarantee unconditionally ("another provider's variance spike can
  never pull the routstr SALE") — the doc should say "with `--preds-key`".
- **(b) mtime-only freshness** (`routstr_delist.py:485`, `routstr_delist.py:494`):
  a writer that rewrites the feed with OLD data refreshes the mtime and bypasses
  the guard (content-stale / mtime-fresh is undetectable). The contract accepts
  mtime (`docs:57`); an embedded `generated_at` check would be stronger.
- **(c) Cosmetic**: `_hours` accepts a bool while the variance guard excludes it
  (`routstr_delist.py:152` vs the hours helper at `routstr_delist.py:196`) —
  arithmetic-safe, no crash path (probe C6c); the override marker is
  presence-based with no TTL (`routstr_delist.py:172`), which is
  operator-controlled by design.
- **(d) Cross-ref findings 4–5**: the quiet-run state write
  (`routstr_delist.py:654`), like all 8 `save_state` call sites, ignores the
  return value (probe A5b).
- **(e) An empty but valid `--preds` array is reported as a feed ERROR.**
  `preds_error = bool(args.preds) and not raw_preds` (`routstr_delist.py:585`)
  treats `[]` exactly like unreadable JSON, so a predictor that legitimately
  produced no rows makes every run exit 1 with `preds_error=true` (probe C5a:
  rc 1, `preds_error=true`, `action=none`, zero round-trips). The contract
  describes the error state as an "**unreadable/corrupt** `--preds` feed"
  (`docs:84`), which `[]` is not. Direction is safe — it can only suppress a
  fire — so this is a monitoring/exit-code wart, not a hazard.
- **(f) A scoped run narrows the durable baseline to the scoped key.**
  `evaluate_triggers` is handed the filtered list (`routstr_delist.py:597`), and
  a run that continues writes `snapshot_preds(filtered_preds)`
  (`routstr_delist.py:747` → `routstr_delist.py:261`), so after `--preds-key zai`
  the snapshot holds only that key's windows — probe C9a measures
  `snapshot == {"zai␟1h": 10.0}` while the feed carried both keys. Other keys then
  have no baseline until a fresh unscoped baseline exists, which can only
  *suppress* a later acceleration fire. Fail-safe direction; worth a line of
  documentation, since the runbook cron example (`docs:106`) is permanently
  scoped.
- **(g) The pure trigger helpers are not type-hardened.** The non-dict guard lives
  only at the `_read_preds` boundary (`routstr_delist.py:479`), not in the helpers
  the module documents as pure and unit-testable: calling
  `evaluate_triggers([None, "x", 1], None)` directly raises
  `AttributeError: 'NoneType' object has no attribute 'get'` (probe C6d), reached
  via the call at `routstr_delist.py:303` from `routstr_delist.py:272`. Not
  reachable through the CLI, which normalises first (C6a/C6b), so this is a
  defence-in-depth note for any future in-process caller (e.g. a monitor
  importing the module): hardening the helpers against non-dict rows, or
  documenting the "normalised input" precondition, would close it.
- **(h) A failed RELIST never ticks the circuit breaker.** The delist failure path
  increments and escalates (`routstr_delist.py:724` `fails += 1`;
  `routstr_delist.py:730` `newly_blocked = fails >= BREAKER_THRESHOLD`;
  `routstr_delist.py:739` rc 3 when blocked), but the relist failure path
  (`routstr_delist.py:626`) only records `last_pull_error` and returns 1. Probe
  C13a: after a confirmed delist, four consecutive transport-dead `--relist` runs
  give rc `[1, 1, 1, 1]` with `blocked` never set and `consecutive_failures` never
  written — so a permanently broken relist (the exact mechanism an operator needs
  to *undo* a delist) loops at rc 1 with no escalation to BLOCKED and no
  `--unblock` hint. Fail-safe-adjacent in the other direction from the rest of
  this list: the escalation that protects the remote node from repeated mutation
  is asymmetrically unavailable for the restore path. **LOW** (the relist is
  operator-initiated, and each failed run is visible in `last_pull_error`), but it
  is a real gap in the fail-safe story.
- **(i) A BLOCKED state refuses `--relist`, so the "explicit action clears the
  breaker" reset is reachable only while unblocked.** The blocked gate
  (`routstr_delist.py:569`, returning 3 at `routstr_delist.py:578`) precedes the
  relist branch, so the reset at `routstr_delist.py:636` can only run for a relist
  that was already unblocked. Probe C13c: with a durable `blocked=true`,
  `--relist` exits 3 with `action=blocked` and **zero** new backend round-trips.
  Probe C13b shows the reset does work in its intended range — a successful relist
  takes accumulated delist failures from 2 back to 0. So the operator must use
  `--unblock`, then `--relist`. **LOW** (reachability/documentation, not a hazard:
  refusing is the fail-safe direction).
- **(j) NEW — a `--preds-key` that matches no feed row is silent.** The filter at
  `routstr_delist.py:597` can empty an otherwise valid feed, but `preds_error` is
  computed at `routstr_delist.py:585` from the UNFILTERED list, so a scoped run
  whose key matches nothing is reported as a healthy quiet run. Probe C14: an
  openrouter-only feed with `--preds-key zai` gives rc **0**, `action=none`,
  `preds_error=false`, `preds_stale=false` and zero round-trips — byte-for-byte
  the output of a genuinely quiet run. A typo'd or renamed `--preds-key`
  therefore disables the trigger permanently and invisibly (no error flag, no
  non-zero exit for cron to catch), which is a monitoring-direction gap rather
  than a hazard — the damage is a delist that never happens, never a delist that
  shouldn't. **LOW**; a one-line fix would surface a distinct
  `preds_key_unmatched` flag (or an rc-1) when a given `--preds-key` filters the
  feed to nothing.
- **Cross-ref:** the MEDIUM dry-run-purity gap is stated once, as Finding 1 item 8
  / gap (e); it is listed here only for completeness because its failure direction
  (a consumed acceleration baseline that never fires) is fail-safe-relevant.

**Verdict 3: OK** — absence and garbage are safe, staleness is guarded in the
fail-safe direction with a fresh-input control, the override is intentionally
ungated and does not pollute the baseline, and budget/breaker semantics fail
closed; residuals are LOW as itemized, with the two MEDIUM/LOW new observations
cross-referenced to Finding 1 and residual (j).

---

Provenance: fifteenth offload pass for findings 1–3. Earlier passes (files at
this path; Gate 2.5 cold review `docs/reviews/routstr_delist_review.md`)
correctly found Finding 2 REFUTED-HIGH (no re-fetch) and Finding 3 PARTIAL-HIGH
(no freshness guard) against the pre-fix script, and subsequent passes
re-adjudicated both OK against the current 829-line artifacts. This pass
independently re-derives the same three verdicts: script read end-to-end in both
copies (byte-identical, md5 `2ea724ef08d857cd7b88a957300e70b4`, 829 lines),
contract suite read end-to-end and executed against the deployed copy,
**104** cited file:line pairs re-verified against their files with their expected
text (probe D1), all **175** `file:line` citations in this document re-checked to
resolve in the file they name (probe D2, zero unresolved; count machine-checked
by probe D4 against the `citation-count` comment above), **74** hermetic probe
checks PASS (probe `docs/reviews/routstr_f13_probes/probe_f13_pass15.py`, run
twice — against the fourteenth-pass text and against this text — with **74/74**
both times; no transcript file archived this pass, the harness prints its own
measurements and is committed), suites 121 + 96 + 25 green plus the deployed copy
25 green, `crontab -l` re-checked (zero routstr entries, 3 lines total). Verdicts:
**1 OK** (one MEDIUM dry-run-purity gap, rest LOW), **2 OK** (MEDIUM
relist-asymmetry residual), **3 OK** (LOW residuals, two new). Artifact-path
report: the contract markdown is STILL MISSING at the bot path (**HIGH**), now for
the fifth consecutive pass; the bot `routstr-delist.md` copy is byte-identical to
the repo copy. Three corrections to the earlier record — the non-reproducing
citation total, the mis-described quiet-run state shape with its wrong probe
label, and the unqualified dry-run guarantee — plus two new observations are
itemized in the preamble. No reviewed artifact was modified. `~/.hermes/bot` is
not a git repository, so the required local commit lands in the workspace repo
(`merchant-routing`) covering `docs/reviews/findings_1_3.md` and the probe
harness, with an identical copy of this file at the task-mandated path
`~/.hermes/bot/docs/reviews/findings_1_3.md`.
