# Offload review — routstr delist, findings 1–3 (safety, confirmation, fail-safe)

Tenth independent offload pass for findings 1–3, re-derived against the CURRENT
artifacts. Nothing below is carried over unverified from earlier passes: the
deployed script was read end-to-end (829 lines, md5 `2ea724ef08d857cd…`),
verified byte-identical to repo `src/routstr_delist.py` (md5 equal, measured
this session, not assumed); the deployed suite was read end-to-end (752 lines,
md5 `031851b356f0de40…`) and is byte-identical to repo
`tests/test_routstr_delist_contract.py`; the repo main suite (1172 lines, 96
cases in 20 classes) was read for the pin citations; the stand-in contract doc
was read end-to-end (197 lines); and **59 fresh hermetic probe checks** were
executed this session against the DEPLOYED bot script copy (no ssh, no network,
no subprocess spawn) — see the per-finding evidence below.

Scope, per the original task: item 1 (safety: delisting the SALE must never
disable the routstr provider or touch the T470 flat-router ladder), item 2
(post-delisting confirmation via re-fetch), item 3 (fail-safe behaviour on
absent, garbage, and stale monitor signals). "Monitor file" maps to the
script's `--preds` feed; "T-A signal" maps to `predict_exhaustion()`-shaped
feed entries.

**Artifact-path status (required report per task instructions):**

- `~/.hermes/bot/docs/routstr_delist_contract.md` — **MISSING — HIGH.**
  Re-verified this session: `read_file` returns "File not found" and the
  directory listing of `~/.hermes/bot/docs/` contains only `routstr-delist.md`
  and `reviews/`. The contract role is filled by the stand-in
  `docs/routstr-delist.md` (repo copy and bot copy, both 197 lines). This is
  the same HIGH reported by every prior pass 1–9 at this path.
- `~/.hermes/bot/scripts/routstr_delist.py` — **present** (829 lines), md5
  `2ea724ef08d857cd7b88a957300e70b4` this pass, equal to repo
  `src/routstr_delist.py`. All `routstr_delist.py:N` references below apply to
  both copies.
- `~/.hermes/bot/tests/test_routstr_delist.py` — **present** (752 lines), md5
  `031851b356f0de4089512f02f13f05cc` this pass, equal to repo
  `tests/test_routstr_delist_contract.py`. Loader fallback (`contract:50-54`)
  resolves `../scripts`, so the bot copy runs against the deployed script.

Conventions: `routstr_delist.py:N` = the script (both copies); `contract:N` =
the 25-case deployed/repo contract suite; `tests:N` = repo
`tests/test_routstr_delist.py` (the 96-case main suite); `docs:N` =
`docs/routstr-delist.md`.

**Suite evidence and one new environment delta.** Repo
`python3 -m pytest tests/ -q` → **121 passed in 0.61 s**; deployed
`cd ~/.hermes/bot && python3 -m pytest tests/test_routstr_delist.py -q` →
**25 passed in 0.36 s**. Both numbers match the ninth pass, but they are only
obtainable **with `TMPDIR` pointed off the default tmpfs**: `/tmp` on this host
is a 5.87 G tmpfs at **100 % (0 bytes free, measured this session via
`shutil.disk_usage`)**, and on the default `TMPDIR` the very same suites report
**16 failed / 105 passed** (repo) and **2 failed / 22 errors** (deployed). Every
one of those is ENOSPC in the tests' own temp dirs — e.g. the deployed suite's
ladder-artifact write dies at `contract:109` with `OSError [Errno 28]`, and the
repo main suite's `tempfile.mkdtemp()` state writes fail inside
`save_state` → `tests:952` reads a missing key → `KeyError: 'delisted'`. This is
a host condition, not an artifact defect, and it is *itself* live evidence for
the ignored-`save_state`-return residual in Finding 1 — see gap (c) there.
Nothing in the artifacts was modified by this pass.

Probe harness (fresh code, not the deployed suite):
`~/worktrees/f13-probe/probe_f13.py` (scratch off `/tmp` per standing policy),
**59/59 checks PASS on two consecutive runs** (deterministic; the harness
regenerates its scratch tree per run). Live exposure: `crontab -l | grep -ci
routstr` → **0** — no cron wiring is live (matches `docs:112`). `~/.hermes/bot`
is not a git repository, so the required local commit lands in the workspace
repo at `docs/reviews/findings_1_3.md`, with an identical copy at the
task-mandated bot path.

**Duplicate-dispatch provenance.** The deliverable already existed
(committed-clean, created by `11e40f9`, eight further passes in
`git log -- docs/reviews/findings_1_3.md`). Per the duplicate-dispatch
procedure: artifact present and committed-clean, but the dispatch mandates a
re-derived report at a fixed path with exactly three findings — so this pass
**replaces the report content** (prior text is preserved in git history; no
append into an append-only ledger) and re-derives every verdict from primary
sources rather than citing the previous pass.

---

## Finding 1 — Safety: SALE-delisting vs disabling the routstr provider — severity: **OK** (gaps: **LOW**)

Every write path the module can take, re-enumerated by grep this session
(`open(`, SQL-verb regex, `subprocess.`, `shell=True`,
`eval(|exec(|os.system|os.remove|os.rmdir|os.rename`, `upstream_providers`):

1. **Local filesystem — exactly 4 `open()` sites.** routstr_delist.py:214
   (state read, `"r"`), :231 (**the ONLY write in the module** — `save_state`'s
   tmp file, `"w"`), :457 (nsec read), :476 (preds read). `save_state` is
   defined at :221 and called from exactly 8 sites (:565, :622, :629, :638,
   :654, :710, :732, :752). Zero `eval(`/`exec(`/`os.system`/`os.remove`/
   `os.rmdir`/`os.rename` in the module — probe F1.3c re-confirms the grep.
   The only `os.unlink` (:243) targets the save_state tmp file itself (:230);
   `os.replace` (:235) is the atomic swap; `os.fsync` (:234) precedes it.
2. **Remote DB — exactly 3 mutating statements.** routstr_delist.py:355
   (`UPDATE models SET enabled=0 WHERE enabled=1`), :361 (blanket
   `UPDATE models SET enabled=1`, legacy fallback builder), :394
   (parameterized `UPDATE models SET enabled=1 WHERE name IN (?,…)`). Exactly 2
   SELECTs (:371 name capture, :408 verify COUNT). All five statements target
   only the `models` (advertisement) table of `/app/data/keys.db` inside the
   `routstr-public` container (path literals :370, :385, :393, :407; defaults
   :86-87). Zero INSERT/DELETE/DROP/ALTER/REPLACE INTO.
3. **`upstream_providers` / T470 ladder — zero executable references.** The
   string occurs exactly 3× (routstr_delist.py:35, :352, :771) and all three
   are prose asserting it is NOT touched (probe F1.3d prints those three
   two-line contexts). Probe F1.1a: `"upstream_providers" in {pull, verify,
   relist-scoped, relist-blanket}` → `False, False, False, False`. Probe
   F1.5b/F1.6b: with a stand-in node that EXECUTES the real payloads, the
   `upstream_providers` rows are identical (name, enabled, weight) across a
   confirmed delist **and** a scoped relist, and the routstr provider stays
   enabled (F1.5c).
4. **Remote command injection — single shlex-quoted argv element.** The remote
   pipeline is emitted as one argv element (routstr_delist.py:414-425). Probe
   F1.2a: `len(build_ssh_docker_cmd(...)) == 3`; F1.2b: `shlex.split(cmd[2])`
   round-trips to `docker exec <container-with-space> python3 -c <payload>`
   intact; F1.2c: the payload is ONE element, never word-split. Probe F1.3a
   records the real `subprocess.run` kwargs for both real-backend round-trips
   → `['capture_output', 'text', 'timeout']`, i.e. **no `shell` key at all**,
   and `argv[0] == "ssh"` (F1.3b), so no local shell is involved. Regression
   pin: tests:345-358.
5. **SQL/payload injection — names are `?`-bound, never concatenated.** The
   scoped relist binds names as parameters and puts the SQL text in a literal
   (routstr_delist.py:390-397); the names reach the remote python source via
   `repr()` (:394), not string concatenation. Probe F1.1e asserts the SQL
   literal carries only `(?,?)` placeholders while the names appear solely as
   the bound-argument list; probe F1.7 executes the payload with a hostile
   model name `x'); DROP TABLE models;--` → `restored=1`, the `models` table
   comes back with all 5 rows, and the pre-disabled operator row stays `0`
   (no breakout, no injection). Pins: tests:326-332 (parameterized), :333-335
   (fallback).
6. **Blanket relist refused by default.** With no captured names, `--relist`
   refuses BEFORE any remote call (routstr_delist.py:602-611). Probe F1.4a:
   `rc 1`, `action relist_refused`, **zero** round-trips, and — newly observed
   this pass — the refusal writes **no state file at all** (the fresh
   `--state` path does not come into existence), so it cannot corrupt state
   either. The blanket SQL is reachable only through the explicit opt-in
   `--relist-any` (:526-528), and only when no names are stored; probe F1.4b
   drives that path end-to-end: the blanket `UPDATE` lands, the
   operator-disabled row **does** come back enabled (the documented opt-in
   risk, docs:29-32), and `upstream_providers` is still row-identical. Pins:
   tests:1039-1070 (`:1039` refusal, `:1056` blanket opt-in).
7. **The ladder guard is TESTED semantically in the DEPLOYED suite.** Contract
   case 6 (`contract:468-507`) executes the script's REAL pull/verify/relist
   payloads against a shared-cache sqlite stand-in carrying a live
   `upstream_providers` table plus a ladder-artifact file (`contract:129-134`,
   `:175-190`), then asserts the artifact is byte-identical (:480), the
   provider table row-identical (:481), the routstr provider still enabled
   (:487-488), and that no executed payload even names `upstream_providers`
   (:482-483); the relist direction asserts only captured names return and the
   ladder stays byte-identical (:490-507). Repo-side static pins:
   tests:302-343, incl. the verify-payload read-only check (:336-343 = probe
   F1.1c's containment claim).
8. **Secret hygiene.** The nak argv uses `--env-sec`, never `--sec`
   (routstr_delist.py:442-448); the key travels only via the `NOSTR_SECRET_KEY`
   env (:459-461). Pinned by `contract:705-729` and tests:384-419.

Gaps (LOW, non-blocking): (a) `--ssh-target`/`--container`
(routstr_delist.py:536-537) let an operator point the mutating payload at any
host/container — by design, nothing validates that the target is the sell node;
(b) the payloads hard-code `/app/data/keys.db` ×4 (:370, :385, :393, :407) — a
container layout change would mutate whatever DB lives at that path; (c) the
return value of `save_state` is ignored at all 8 call sites. Gap (c) is the
finding-4 residual (see findings_4_5.md), but this pass produced **field
evidence** for its impact: the full-tmpfs suite run above shows a failed state
write surfacing only later as a *misleading* test failure, and probe F3.7 shows
a run that reports `action: delist, rc 0` while the state file was never
written — the durable `delisted` flag that the listing publisher reads is
silently lost while remote reality has changed. Failure direction is safe
(toward re-delist / toward `--relist-any`, never toward a silently-missed
delist), hence LOW, and it is owned by finding 4.

**Verdict 1: OK** — no code path disables the routstr provider or leaves the
advertisement outside the `models` table; the ladder protection has a semantic
guard in the deployed suite and is re-probed byte/row-identically this pass;
gaps LOW as itemized.

## Finding 2 — Post-delisting confirmation via re-fetch — severity: **OK** (requirement **MET**; residual **MEDIUM**: relist has no symmetric re-fetch; LOWs itemized)

The pre-fix script had no re-fetch (correctly REFUTED-HIGH by the cold review);
the required independent re-fetch exists in the current artifact. Re-derived
this session:

1. **The confirmation mechanism.** `verify_pull_payload()`
   (routstr_delist.py:400-411) is a read-only `SELECT COUNT(*) FROM models
   WHERE enabled=1` (probe F1.1c: no UPDATE/INSERT/DELETE/DROP/ALTER in the
   payload; pin tests:336-343). It executes as a SEPARATE ssh round-trip via
   `_SshBackend.verify` (:790-793), called at :682 after the pull inside the
   attempt loop (:671-697). Success requires `vres.get("ok") is True and
   vres.get("count") == 0` (:683); only then is `confirmed` set (:687), which
   is what unlocks the durable `delisted=true` write (:747-752) and rc 0 (:764).
   Probe F2.1a: round-trip kinds are exactly `["pull", "verify"]`; F2.1b:
   `rc 0`, `confirmed True`, `verified_count 0`, `delisted True`,
   `consecutive_failures 0`; F2.1c: the verify round-trip carries its own
   deadline (so it is also budget-clamped, :795-806).
2. **A lying pull is refuted — re-probed end-to-end on the deployed copy this
   pass.** Probe F2.2: a stub backend whose pull self-reports ok and carries
   `pulled: ["gpt-4o"]` while verify returns `count 1` → `rc 1`, `action
   delist_failed`, `ok False`, executed kinds `["pull","verify","pull",
   "verify"]`, `delisted False`, no `snapshot` written, `consecutive_failures
   1`. The symmetric probe with `count 0` is F2.1 (confirmed, rc 0). Bounded
   retry is `MAX_PULL_ATTEMPTS = 2` (:75; loop :671-697); on exhaustion the
   failure branch (:719-739) sets no `delisted` flag, consumes no baseline,
   ticks the breaker, exits 1/3. Pins: `contract:346-360` (lying pull),
   tests:567-584 (verify gates success; count=1 → rc 1, no flag, 2 verifies
   across 2 attempts), tests:603-617 (verify transport failure counts as an
   attempt failure).
3. **Parse/transport robustness fails safe — re-probed against the REAL
   `_SshBackend._run`** (in-process monkeypatch of `subprocess.run`; no spawn).
   Probes F2.3 cover: non-zero ssh rc with an ok-looking payload → `ok False`;
   unparseable stdout (`bash: warning`) → `ok False`; empty stdout after
   `commit()` → `ok False`; non-dict JSON (`[]`) → `ok False` (guard :815-816);
   noise-then-JSON last line → `ok True, count 0` (:814 last-line parse). F2.3f:
   a verify returning `count 3` yields `ok True, count 3`, which `count == 0`
   at :683 rejects. Garbage can therefore only fail the run, never confirm it.
   Pins: tests:1107-1151.
4. **Residual — MEDIUM: the relist path still has NO symmetric re-fetch.**
   Re-probed by execution this pass (F2.4): a confirmed-relist run executes
   kinds `["relist"]` **only** — no verify round-trip — and on the round-trip's
   self-report alone (`routstr_delist.py:626`) the run sets `delisted=false`
   and pops `pulled_models` (:633-635). In the probe the stub `verify` (which
   would have reported 99 still-advertised models) was never consulted, and the
   stored name set was destroyed while `delisted` flipped false. F2.4c: the
   consequence is concrete — the next scoped `--relist` is refused
   (:602-611), so recovery forces `--relist-any`, which re-enables rows the
   operator had deliberately disabled (docs:29-32), or a fresh
   delist/relist cycle. A lying relist (rc 0, ok printed, UPDATE not landed —
   the same fault class the contract deemed must-fix for delist) therefore both
   fakes a restored listing and destroys the scoped name set. The contract
   mandates the re-fetch only for "a fired delist" (docs:69-75), so this is an
   asymmetry, not a contract breach — but the fix is cheap: verify after the
   relist (e.g. `COUNT(*) > 0`, or a per-name re-read) BEFORE popping
   `pulled_models`.
5. **LOW notes.** (a) Dry-run sets `confirmed=True` with no remote verify
   (:679-681); probe F2.5 — driven against the REAL backend with a spying
   `subprocess.run` — records **zero spawns**, `action delist`, `rc 0`, and a
   state file whose keys are exactly `{last_dry_run, ts}` (no `delisted` key
   introduced); documented docs:87-89, pinned `contract:731-752` and
   tests:1072-1100. (b) The verify round-trip shares the ssh transport and
   last-line JSON parsing with the pull (:810-822) — it is an independent
   round-trip in the contract's sense (docs:69-71), but a systematic
   transport-level fault (wrong container, shadowed DB path) could satisfy
   both; the failure direction remains safe (a fooled verify can only keep the
   run failing → breaker).

**Verdict 2: OK** — the required post-delisting confirmation exists, is
independent, read-only, and gates the durable flag; bounded retry and failure
semantics are contract-pinned and were re-probed end-to-end on the deployed
copy. One MEDIUM residual (relist asymmetry) and two LOW notes above.

## Finding 3 — Fail-safe on absence, garbage, staleness — severity: **OK** (residuals: **LOW**)

Every branch that can reach a delist runs through
`fire = args.delist or dec["fire"]` (routstr_delist.py:649), where
`dec["fire"] = bool(accel or var or override)` (:317). Enumerated and probed:

- **Absence — OK.** No `--preds` → `raw_preds=[]` (:581), quiet run; probes
  F3.1a (`rc 0`, `action none`, **zero** remote calls), F3.1b
  (`exhaustion_accelerated(now, [])` → `[]`), F3.1c (a first run with a live
  feed is still quiet — no baseline, no false positive). Acceleration requires
  non-empty preds on BOTH sides (:107) and variance requires non-empty preds
  (:143). Pin: `contract:308-314`. Manual override remains available by design.
- **Garbage — OK.** `_read_preds` never raises, drops non-dict entries
  (routstr_delist.py:479) and returns `[]` on any parse failure (:481-482).
  Probes: F3.2a (a truncated `{"mid-write` feed → `rc 1`, `preds_error True`,
  `action none`, **zero** remote calls), F3.2b (the stored snapshot
  `{"zai\x1f1h": 10.0}` survives intact — `update_state` only overwrites the
  snapshot when preds is non-empty, :261-262), F3.2c (non-dict entries dropped),
  F3.2d (`uncertainty` guards: string `"0.9"` and `True` ignored, `0.95`
  fires — :152-153 excludes bool explicitly), F3.2e (`_hours` accepts a bool as
  `1.0` while a string is rejected — cosmetic, arithmetic-safe, matches the
  documented LOW note). An explicitly requested but unusable feed is a FEED
  ERROR (`preds_error`, :585) with rc=1 when nothing fired (:660). Pins:
  tests:547-562, tests:797-815, tests:146-151, tests:243-250.
- **Stale — OK.** `STALENESS_S = 1800` (:78); `feed_is_stale` is mtime-based
  and fails safe in direction — undeterminable age (OSError, missing file)
  returns True, a future mtime (negative age) is stale
  (routstr_delist.py:485-496). Probes: F3.3a missing path → `True`; F3.3b 1 h
  old → `True`; F3.3c future mtime → `True`; F3.3d provably fresh → `False`;
  F3.3e boundary — evaluated with an explicit `now=`, an age of exactly
  `STALENESS_S` is FRESH (the expression is inclusive: `not (0 <= age <=
  max_age_s)`), which reproduces the ninth pass's boundary observation without
  its few-ms measurement artefact. Wiring: a stale feed zeroes the preds BEFORE
  trigger evaluation (:589-592) — F3.3f: variance-elevated (unc 0.9) but 6 h
  old → `rc 1`, `action none`, `preds_stale True`, zero remote calls — and
  BEFORE any baseline refresh (F3.3g: snapshot preserved). F3.3h: the same
  feed fresh → `action delist`, `preds_stale False`, kinds
  `["pull","verify"]`, proving the guard is wired to a live trigger rather than
  a dead one. `preds_stale` is surfaced in every output branch (:657, :714,
  :735, :762) with rc=1 when quiet (:660). The manual override is deliberately
  never gated on freshness (:580 order, docs:60; F3.4: stale feed + `--manual`
  → `rc 0`, `action delist`, `preds_stale True` observed but not obeyed; pins
  `contract:427-433`, tests:980-993). Override detection is presence-based and
  treats None/absent as no-override (routstr_delist.py:164-172; probes F3.5,
  F3.5b; pins tests:155-174). Full pin set: tests:928-1009.
- **Breaker interaction (cross-ref finding 6).** Repeated failed runs refuse
  ALL further remote action (routstr_delist.py:724-731, :569-578, exit 3) until
  `--unblock` (:561-567); dry-run never counts toward it (:699-717). Cited as
  cross-reference only — the breaker pins (tests:816-927, `contract:580-624`)
  were sighted, not re-probed, in this pass.

Residuals (LOW):

- **(a) `--preds-key` scoping is opt-in, default unscoped.** Filtering happens
  only when the flag is passed (routstr_delist.py:594-597) and
  `evaluate_triggers` still passes no `key` to `variance_jumped` (:303) even
  though the parameter exists for that purpose (:132, :147). Re-probed this
  pass: F3.6a — an openrouter-only spike (`uncertainty 0.95`, no `--preds-key`)
  → `action delist`, kinds `["pull","verify"]`; F3.6b — the same feed with
  `--preds-key zai` → `action none`, zero calls. Scoping is wired at the CLI,
  documented (docs:54-55) and carried in the runbook cron example (docs:106);
  the residual is operator-omission risk on a deployment that is not yet wired
  (zero routstr crontab entries live this pass). Caveat: docs:54-55 states the
  guarantee unconditionally ("another provider's variance spike can never pull
  the routstr SALE") — the doc should say "with `--preds-key`".
- **(b) mtime-only freshness** (routstr_delist.py:485-494): a writer that
  rewrites `preds.json` with OLD data refreshes the mtime and bypasses the
  guard (content-stale / mtime-fresh is undetectable). The contract accepts
  mtime (docs:56-60); an embedded `generated_at` check would be stronger.
- **(c) Cosmetic / test-coverage.** `_hours` accepts bool
  (routstr_delist.py:193-196; probe F3.2e: `True` is returned as-is and a
  bool-hours acceleration does fire, computed as 1.0) while the variance guard
  excludes it (:152-153) — arithmetic-safe, no crash path. The staleness
  boundary itself remains unpinned: the committed boundary test
  (tests:968-979, `test_staleness_threshold_boundary`) uses
  `STALENESS_S + 60`, so the inclusive-boundary semantics above rest on probe
  evidence only. The override marker is presence-based with no TTL (:164-172)
  — operator-controlled, by design.
- **(d) `save_state`'s return value is ignored at all 8 call sites — now with
  field evidence.** Probe F3.7a: with `os.replace` forced to raise ENOSPC, a
  confirmed delist still prints `action delist` and exits **0** while the state
  file is never created; F3.7b: the durable `delisted` flag is lost, so the
  level-based variance trigger will re-fire on the next run and the listing
  publisher never observes `delisted=true`. The same class occurred for real in
  this pass's default-`TMPDIR` suite run: 16 repo-suite failures, all of them a
  swallowed state-write failure surfacing later as a misleading assertion error
  rather than an honest error. Failure direction is safe (re-delist, or a
  forced `--relist-any`), so **LOW**, and it is owned by finding 4
  (atomicity/idempotence) — cross-referenced, not re-adjudicated here.
- **(e) Deadline clamp** (:800-806) was exercised incidentally by probes F2.1c
  / F2.3 (a verify round-trip with a live deadline spawned with
  `timeout=30`); the exhausted-deadline path was not re-probed this pass and
  neither suite inspects the `subprocess.run` timeout kwarg — see finding 8.

**Verdict 3: OK** — absence safe, garbage safe (including the type guards),
staleness guarded with a fail-safe direction and full test pinning; residuals
LOW as itemized.

---

Provenance: tenth offload pass for findings 1–3. Prior passes (ninth-pass text
at this path; Gate 2.5 cold review `docs/reviews/routstr_delist_review.md`;
commits `11e40f9` … `8ac091f`) correctly found Finding 2 REFUTED-HIGH (no
re-fetch) and Finding 3 PARTIAL-HIGH (no freshness guard) against the pre-fix
602-line script, then re-adjudicated both OK against the current 829-line
artifacts after the round-2 fixes. This pass independently re-derives the same
three verdicts against unchanged artifacts (script md5
`2ea724ef08d857cd…`, suite md5 `031851b356f0de40…`, both byte-identical to
their repo copies) and records two deltas: (i) the suite numbers are only
reproducible with `TMPDIR` off a FULL `/tmp` tmpfs (0 bytes free) — on the
default tmpfs the same suites show ENOSPC-driven failures, which is itself
evidence for residual (d); (ii) probe F3.7 demonstrates by execution that a
failed state write is swallowed while the run reports a confirmed delist.
Evidence executed this session: script and both suites and the stand-in doc
read end-to-end; md5 equality of bot↔repo copies measured, not assumed; 59
hermetic probe checks on the DEPLOYED copy, 59/59 green twice (real payload
builders executed against a sqlite stand-in; real `_SshBackend._run` parse/ok
gate exercised in-process with `subprocess.run` monkeypatched; dry-run spawn
count observed with the real backend; hostile-name injection probe; SLA deadline
presence observed); suites re-run 121 + 25 green with `TMPDIR` off tmpfs;
`crontab -l` re-checked (zero routstr entries). One evidence gap is disclosed:
the md5 of the two `docs/routstr-delist.md` copies was NOT re-measured this
pass — the command bundle that would have measured it was denied by the
console consent guard, so the doc-drift claim above rests on the 197-line count
of both copies plus the bot copy read end-to-end (10837 B) this session, not on
a fresh digest. Artifact-path report: the contract md is STILL MISSING at the
bot path (HIGH, tenth consecutive pass). Artifacts untouched; `~/.hermes/bot`
is not a git repository, so the required local commit lands in the workspace
repo (merchant-routing) at `docs/reviews/findings_1_3.md`, with this identical
copy at the task-mandated bot path `~/.hermes/bot/docs/reviews/findings_1_3.md`.
Verdicts: 1 OK (gaps LOW), 2 OK (MEDIUM relist-asymmetry residual), 3 OK
(residuals LOW).
