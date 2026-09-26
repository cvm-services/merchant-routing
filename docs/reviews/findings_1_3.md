# Offload review — routstr delist, findings 1–3 (safety, confirmation, fail-safe)

Ninth independent offload pass for findings 1–3, re-derived against the CURRENT
artifacts. Nothing below is carried over unverified from earlier passes: the
deployed script was read end-to-end (829 lines, md5 `2ea724ef08d857cd…`),
verified byte-identical to the repo copy by hash, not by assumption; the
deployed suite (752 lines, md5 `031851b356f0de40…`) was read end-to-end and is
byte-identical to repo `tests/test_routstr_delist_contract.py`; the 96-case
repo main suite (1172 lines) was read end-to-end for the pinning citations; the
stand-in contract doc was read end-to-end; write-path/SQL/subprocess
inventories were re-run by grep this session; and 9 hermetic probe families
were executed against the DEPLOYED bot script copy (no network, no subprocess
spawn, no ssh) — see Verdicts and the probe notes inline.

Scope, per the original task: item 1 (safety: delisting the SALE must never
disable the routstr provider or touch the T470 flat-router ladder), item 2
(post-delisting confirmation via re-fetch), item 3 (fail-safe behaviour on
absent, garbage, and stale monitor signals). "Monitor file" maps to the
script's `--preds` feed; "T-A signal" maps to `predict_exhaustion()`-shaped
feed entries.

**Artifact-path status (required report per task instructions):**

- `~/.hermes/bot/docs/routstr_delist_contract.md` — **MISSING — HIGH**.
  Re-verified this session: no such file; `~/.hermes/bot/docs/` contains only
  `routstr-delist.md` and `reviews/` (6 files); a tree-wide search for any
  `*contract*` artifact under `~/.hermes` returns only unrelated hits
  (pyright/networkx `.pyi` stubs, other skills' reference docs). The contract
  role is filled by TWO stand-ins: repo `docs/routstr-delist.md` (197 lines)
  and `~/.hermes/bot/docs/routstr-delist.md`.
- `~/.hermes/bot/scripts/routstr_delist.py` — present (829 lines), verified
  **byte-identical** to repo `src/routstr_delist.py` this session (md5 equal).
  All `routstr_delist.py:N` references below apply to both copies.
- `~/.hermes/bot/tests/test_routstr_delist.py` — present (752 lines), verified
  **byte-identical** to repo `tests/test_routstr_delist_contract.py` (the
  25-case TDD contract suite). Its loader fallback (`contract:47-54`) resolves
  `../scripts` in the deployed layout, so the bot copy runs against the
  deployed script (confirmed: no `routstr_delist.py` under `~/.hermes/bot/src`).
- **Change vs the eighth pass (re-derived, not carried):** the bot stand-in
  doc is **no longer stale**. `diff ~/.hermes/bot/docs/routstr-delist.md
  ~/repos/merchant-routing/docs/routstr-delist.md` → rc 0; both 197 lines,
  md5 `e385af98b9c142ee…`. The eighth pass's "14 lines behind (repo
  177–190)" residual is not reproducible today. No other doc drift observed.

Conventions: `routstr_delist.py:N` = the script (both copies); `contract:N` =
the 25-case deployed/repo contract suite; `tests:N` = repo
`tests/test_routstr_delist.py` (the 96-case main suite that keeps the real-backend
and freshness pins; repo total 121 cases); `docs:N` = `docs/routstr-delist.md`.

Suite evidence (this pass): repo `python3 -m pytest tests/ -q` → **121 passed
in 0.78s**; deployed `cd ~/.hermes/bot && python3 -m pytest
tests/test_routstr_delist.py -q` → **25 passed in 0.34s** (hermetic; no
network). Live exposure: `crontab -l | grep -ci routstr` → **0** — no cron
wiring is live (matches docs:112). `~/.hermes/bot` is still **not** a git
repository (`git rev-parse` → fatal, rc 128), so the required local commit
lands in the workspace repo. Environment note: `/tmp` is a 5.5 G tmpfs at 100%
(1.7 G `/tmp/d128-red`, 783 M `pytest-of-c03rad0r`) and ENOSPC'd a probe write
this pass; all probes were run from `~/worktrees/rp9-probe/` instead.

---

## Finding 1 — Safety: SALE-delisting vs disabling the routstr provider — severity: **OK** (gaps: **LOW**)

Every write path the module can take, re-enumerated by grep this session
(`open(`, SQL-verb regex, `subprocess.`, `shell=True`,
`eval(|exec(|os.system|os.remove|os.rmdir|os.rename`, `upstream_providers`):

1. **Local filesystem — exactly 4 `open()` sites.** routstr_delist.py:214
   (state read, `"r"`), :231 (**the ONLY write in the module** — `save_state`'s
   tmp file, `"w"`), :457 (nsec read), :476 (preds read). `save_state` is
   defined at :221 and called from exactly 8 sites (:565, :622, :629, :638,
   :654, :710, :732, :752); it writes only the trigger-baseline /
   `delisted`-flag JSON. Zero `eval(`/`exec(`/`os.system`/`os.remove`/
   `os.rmdir`/`os.rename` in the module (grep clean; `exec(` appears only in
   the test rig, which executes our own payload builders). The only
   `os.unlink` (:243) targets the save_state tmp file itself (:230);
   `os.replace` (:235) is the atomic-swap step; `os.fsync` (:234) precedes it.
2. **Remote DB — exactly 3 mutating statements.** routstr_delist.py:355
   (`UPDATE models SET enabled=0 WHERE enabled=1`), :361 (blanket
   `UPDATE models SET enabled=1`, legacy fallback builder), :394
   (parameterized `UPDATE models SET enabled=1 WHERE name IN (?,…)`). Exactly
   2 SELECTs (:371 name capture, :408 verify COUNT). All five statements
   target only the `models` (advertisement) table of `/app/data/keys.db`
   inside the `routstr-public` container (path literals :370, :385, :393,
   :407; defaults :86-87). Zero INSERT/DELETE/DROP/ALTER/REPLACE INTO —
   grep-verified.
3. **`upstream_providers` / T470 ladder — zero executable references.** The
   string occurs exactly 3× (routstr_delist.py:35, :352, :771) and all three
   are docstring sentences asserting it is NOT touched. Probe (deployed copy):
   `"upstream_providers" in {pull, verify, relist-scoped, relist-blanket}`
   → `false, false, false, false`. The only two subprocess sites are :459
   (nak publish) and :808 (ssh docker-exec); `shell=True` count is **0**, and
   a probe recording the real `subprocess.run` kwargs shows
   `["capture_output", "text", "timeout"]` — no `shell` key at all. Neither
   site writes a repo/ladder artifact.
4. **Remote command injection — single shlex-quoted argv element.** The remote
   pipeline is emitted as one argv element (routstr_delist.py:414-425);
   probe: `len(build_ssh_docker_cmd(...)) == 3` (ssh + host + one remote
   command). Regression-pinned by tests:345-358 (3-element argv;
   `shlex.split(cmd[2])` round-trips to `docker exec <container-with-space>
   python3 -c <payload>` intact). No local shell is involved.
5. **Blanket relist refused by default.** With no captured names, `--relist`
   refuses BEFORE any remote call (routstr_delist.py:602-611:
   `relist_refused`, exit 1); probe on the deployed copy with the live
   no-`pulled_models` state shape → `rc 1`, `action relist_refused`, state's
   `delisted` untouched. The blanket SQL is reachable only via the explicit
   `--relist-any` opt-in (:526-528), exercised at tests:1056-1068. Even then
   it mutates only the `models` table — the SALE/provider separation holds on
   every path (the live state file `~/.hermes/bot/routstr_delist_state.json`
   is exactly the no-`pulled_models` shape: `delisted: true`, `snapshot: {}`,
   so this refusal is the operative protection today).
6. **Dry-run is intent-only.** The delist dry-run records `last_dry_run` and
   flips NO durable `delisted` flag, publishes nothing, counts no breaker
   failure, consumes no baseline (routstr_delist.py:699-717); relist dry-run
   likewise (:615-625). Probe on a fresh state: the dry run writes exactly
   `["last_dry_run", "ts"]` — no `delisted` key introduced. Pinned by
   tests:514-530 (no breaker count, no `last_pull_error`), tests:1072-1097
   (no nak publish in either direction), and contract:731-752 — including
   that a PRE-EXISTING `delisted=true` flag survives a dry run untouched
   (contract:746-752).
7. **The ladder guard is TESTED semantically in the DEPLOYED suite.** The
   deployed contract suite's Case 6 (contract:468-507) executes the script's
   REAL pull/verify/relist payloads against a shared-cache sqlite stand-in
   that has a live `upstream_providers` table plus a ladder-artifact file
   (contract:129-134, :175-190), then asserts the artifact is byte-identical
   (:480), the provider table row-identical (:481), the routstr provider still
   enabled (:487-488), and that no executed payload even names
   `upstream_providers` (:482-483); the relist direction asserts only captured
   names come back and the ladder stays byte-identical (:490-507). This closes
   the cold review's original LOW gap ("no test names or touches an actual
   ladder artifact"). Repo-side static pins: tests:302-343 (incl. the
   verify-payload read-only check, :336-343).
8. **Secret hygiene.** The nak argv uses `--env-sec`, never `--sec`
   (routstr_delist.py:442-448); the key travels only via the `NOSTR_SECRET_KEY`
   env (:459-461). Pinned by contract:705-729 (secret absent from stdout,
   state file, payloads, and argv).

Gaps (LOW, non-blocking; unchanged in kind from earlier passes): (a)
`--ssh-target`/`--container` (routstr_delist.py:536-537) let an operator point
the mutating payload at any host/container — by design, nothing validates the
target is the sell node; (b) the payloads hard-code `/app/data/keys.db` ×4
(:370, :385, :393, :407) — a container layout change would mutate whatever DB
lives at that path; (c) `save_state`'s return value is ignored at all 8 call
sites — finding-4 residual (see findings_4_5.md); noted here only because a
failed write after a CONFIRMED delist (:752) would silently diverge local state
from remote reality.

**Verdict 1: OK** — no code path disables the routstr provider or leaves the
advertisement outside the `models` table; the ladder protection has a semantic
guard in the deployed suite; gaps LOW as itemized.

## Finding 2 — Post-delisting confirmation via re-fetch — severity: **OK** (requirement **MET**; residual **MEDIUM**: relist has no symmetric re-fetch; LOWs itemized)

The pre-fix script had no re-fetch (correctly REFUTED-HIGH by the cold
review); the required independent re-fetch **exists** in the current artifact.
Re-derived this session:

1. **The confirmation mechanism.** `verify_pull_payload()`
   (routstr_delist.py:400-411) is a read-only `SELECT COUNT(*) FROM models
   WHERE enabled=1` (probe: payload contains no `UPDATE`, contains the SELECT
   and `/app/data/keys.db`; pinned tests:336-343). It executes as a SEPARATE
   ssh round-trip via `_SshBackend.verify` (:790-793), called at :682 after the
   pull inside the attempt loop (:671-697). Success requires
   `vres.get("ok") is True and vres.get("count") == 0` (:683); only then is
   `confirmed` set (:687), which is what unlocks the durable `delisted=true`
   write (:747-752) and rc 0 (:764).
2. **A lying pull is refuted — re-probed end-to-end on the deployed copy this
   pass.** With a stub backend whose pull self-reports ok and carries
   `pulled: ["gpt-4o"]` while `verify` returns `count 1`: `rc 1`, `action
   delist_failed`, executed kinds `["pull","verify","pull","verify"]`,
   `delisted false`, `consecutive_failures 1`, and the output carries
   `verify: {count: 1, ok: true}`. The symmetric probe with `count 0`: `rc 0`,
   `action delist`, kinds `["pull","verify"]`, `delisted true`,
   `pulled_models ["gpt-4o"]`, `verified_count 0`, `consecutive_failures 0`,
   `blocked false`. Matches the committed pins contract:346-360 and
   tests:567-584 (verify count=1 → rc 1, no flag, 2 verifies across 2
   attempts) plus tests:603-617 (verify transport failure counts as attempt
   failure). Bounded retry is `MAX_PULL_ATTEMPTS = 2` (:75; loop :671-697);
   on exhaustion the failure branch (:719-739) sets no `delisted` flag,
   consumes no baseline, ticks the breaker, exits 1/3.
3. **Parse/transport robustness fails safe — re-probed against the REAL
   `_SshBackend._run` this pass** (in-process monkeypatch of
   `subprocess.run`; no spawn). :795-825: non-zero ssh rc with an ok-looking
   payload → `ok false`; unparseable stdout (`bash: warning`) → `ok false`;
   empty stdout rc 1 (payload died after `commit()`) → `ok false`; non-dict
   JSON (`[]`) → `ok false` (guard :815-816); multi-line stdout with noise
   before the JSON → last-line parse (:814) still yields `ok true, count 0`;
   a verify payload returning `count 3` yields `ok true, count 3`, which
   `count == 0` at :683 rejects. Garbage can therefore only fail the run,
   never confirm it. Happy path is exactly one pull + one verify (contract:334),
   with `verified_count` recorded (:686) and the breaker reset on confirmed
   success (tests:586-601).
4. **Residual — MEDIUM: the relist path has NO symmetric re-fetch.**
   Re-probed this pass: a confirmed-relist run executes kinds `["relist"]`
   only — no verify round-trip — and on the round-trip's self-report alone
   (routstr_delist.py:626) the run sets `delisted=false` AND pops
   `pulled_models` (:633-635); the probe's stub `verify` (which would have
   reported 99 still-advertised models) was never consulted, and the stored
   name set was destroyed while `delisted` flipped false. A lying relist (rc 0,
   ok printed, UPDATE not landed — the same fault class the contract deemed
   must-fix for delist) therefore both fakes a restored listing and destroys
   the scoped name set; a subsequent scoped `--relist` is then refused
   (:602-611) and recovery forces `--relist-any`, which re-enables rows the
   operator had deliberately disabled (docs:29-32), or a fresh delist/relist
   cycle. The contract mandates the re-fetch only for "a fired delist"
   (docs:69-75), so this is an asymmetry, not a contract breach — but the fix
   is cheap: verify after relist (e.g. `COUNT(*)>0` or per-name re-read)
   BEFORE popping `pulled_models`.
5. **LOW notes.** (a) Dry-run sets `confirmed=True` with no remote verify
   (:679-681); probe: the dry-run output has no `confirmed` key and only
   `action: delist` — intent-only, nothing remote to confirm; documented
   docs:87-89. (b) The verify round-trip shares the ssh transport and
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

- **Absence — OK.** No `--preds` → `raw_preds=[]` (:581), quiet run;
  acceleration requires non-empty preds on BOTH sides (:107), variance requires
  non-empty preds (:143); probe: `exhaustion_accelerated(now, [])` → `[]`. A
  first run without a stored baseline can never fire acceleration (pinned
  contract:308-314). Manual override remains available by design.
- **Garbage — OK.** `_read_preds` never raises, drops non-dict entries
  (routstr_delist.py:479) and returns [] on any parse failure (:481-482).
  Probe (deployed copy): `{mid-write` feed → `rc 1`, `preds_error true`,
  `action none`, stored snapshot `{"zai\x1f1h": 10.0}` intact. An explicitly
  requested but unusable feed is a FEED ERROR (`preds_error`, :585) with rc=1
  when nothing fired (:660); the stored baseline is never wiped —
  `update_state` only overwrites the snapshot when preds is non-empty
  (:261-262), pinned tests:547-562 and tests:797-812. Type-guards:
  `uncertainty` is isinstance-guarded with bool explicitly excluded (:152-153)
  — probe: string `"0.9"` and `True` → `[]`, no crash; `exhausts_in_hours` is
  isinstance-guarded (:193-196). Precision note (probe): a feed that is BOTH
  garbage AND old surfaces as `preds_error` with `preds_stale false` (raw_preds
  is empty at :589, so `preds_stale` cannot also be set); both exit 1.
- **Stale — OK; was the HIGH hole, now GUARDED.** `STALENESS_S = 1800` (:78);
  `feed_is_stale` is mtime-based and fails safe in direction — undeterminable
  age (OSError, missing file) returns True (routstr_delist.py:485-496), and a
  future mtime (negative age) is treated as stale (:494). Probe (deployed
  copy): missing path → `True`; 1 h-old → `True`; future mtime → `True`; fresh
  → `False`. Note on the boundary: the expression is inclusive
  (`not (0 <= age <= max_age_s)`), so an age of exactly `STALENESS_S` is
  FRESH; my probe reported `True` there only because the few-ms evaluation
  delay pushed the measured age just past the threshold — flagged as a
  test-coverage gap below, not a behavioural bug. Wiring: a stale feed zeroes
  the preds BEFORE trigger evaluation (:589-592), so the level-based variance
  trigger cannot fire on dead data, and BEFORE any baseline refresh (snapshot
  preserved). Probe: variance-elevated (unc 0.9) but 6 h-old feed → `rc 1`,
  `action none`, `preds_stale true`; the same rows fresh (30 s) → `action
  delist`, `preds_stale false`. `preds_stale` is surfaced in every output
  branch (:657, :714, :735, :762) with rc=1 when quiet (:660). The manual
  override is deliberately never gated on freshness (:580 order, docs:60;
  probe: stale feed + `--manual` → `rc 0`, `action delist`, `preds_stale true`
  observed but not obeyed; pinned tests:980-993 and contract:427-433). Full pin
  set: tests:928-1006.
- **Breaker interaction (cross-ref finding 6).** Repeated failed runs refuse
  ALL further remote action (routstr_delist.py:724-731, :569-578, exit 3)
  until `--unblock` (:561-567); dry-run never counts toward it (:699-717,
  tests:514-530).

Residuals (LOW):

- **(a) `--preds-key` scoping is opt-in, default unscoped.** Filtering happens
  only when the flag is passed (routstr_delist.py:594-597); `evaluate_triggers`
  itself still passes no `key` to `variance_jumped` (:303) although the
  parameter exists for that purpose (:132, :147). Probe (deployed copy,
  dry-run): an openrouter-only feed with `uncertainty 0.95` and NO
  `--preds-key` → `fire true`, action delist; the same feed with
  `--preds-key zai` → `fire false`, action none. Scoping is wired at the CLI,
  documented (docs:54-55) and carried in the runbook cron example (docs:106);
  the residual is operator-omission risk on a deployment that is not yet wired
  (zero routstr crontab entries live this pass). Caveat: docs:54-55 states the
  guarantee unconditionally ("another provider's variance spike can never pull
  the routstr SALE") — the doc should say "with `--preds-key`".
- **(b) mtime-only freshness** (routstr_delist.py:485-494): a writer that
  rewrites `preds.json` with OLD data refreshes the mtime and bypasses the
  guard (content-stale / mtime-fresh is undetectable). The contract accepts
  mtime (docs:57); an embedded `generated_at` check would be stronger.
- **(c) Cosmetic / test-coverage.** `_hours` accepts bool (:193-196, probe:
  `True` returned as-is) while the variance guard excludes it (:152-153) —
  arithmetic-safe, no crash path. The staleness boundary itself is unpinned:
  no committed test exercises `age == STALENESS_S` (tests:968-978 uses
  `STALENESS_S + 60`), so the inclusive-boundary semantics I measured above
  rest on probe evidence only. The override marker is presence-based with no
  TTL (:164-172) — operator-controlled, by design.
- **(d) Cross-ref finding 4/5.** The quiet-run state write (:654), like all 8
  `save_state` call sites, ignores the return value. The deadline clamp
  (:800-806) is behaviourally correct under direct probe (exhausted deadline →
  `{"ok": false, "error": "action budget exhausted"}` and **zero** spawns;
  generous deadline → `timeout 30`; 5 s remaining → `timeout ≈ 5.0`; no
  deadline → `30`), but neither suite inspects the `subprocess.run` timeout
  kwarg, so that behaviour remains unpinned — see finding 8.

**Verdict 3: OK** — absence safe, garbage safe (incl. the type guards),
staleness guarded with a fail-safe direction and full test pinning; residuals
LOW as itemized.

---

Provenance: ninth offload pass for findings 1–3. Prior passes (eighth-pass file
at this path; Gate 2.5 cold review `docs/reviews/routstr_delist_review.md`;
commits 69d489c … 244b4ba) correctly found Finding 2 REFUTED-HIGH (no re-fetch)
and Finding 3 PARTIAL-HIGH (no freshness guard) against the pre-fix 602-line
script, then re-adjudicated both OK against the current 829-line artifacts
after the round-2 fixes. This pass independently re-derives the same verdicts
against unchanged artifacts and records one delta: the bot stand-in doc is now
byte-identical to the repo copy (the eighth pass's 14-line drift residual is
gone). Evidence executed this session: script read end-to-end in both copies
(byte-identical by md5, 829 lines), deployed suite read end-to-end (752 lines,
md5-equal to the repo contract suite) and run against the deployed copy, repo
main suite read end-to-end (1172 lines, all pin ranges above sighted directly),
write-path inventories re-run by grep (open/SQL/subprocess/shell/eval-exec/os.*
— counts cited above), 9 hermetic probe families executed on the deployed copy
(staleness fail-safe ×5 states, type guards, absence, garbage-feed baseline
preservation, garbage+aged precision, `--preds-key` scoped vs unscoped, manual
override vs staleness, relist refusal, `--status` read-only, dry-run write set,
REAL `_run` parse/ok-gate ×6, deadline clamp ×3 with zero spawns, and
main()-level confirm gate refuted/confirmed/relist), suites 121 + 25 green,
`crontab -l` re-checked (zero routstr entries). Verdicts: 1 OK (gaps LOW), 2 OK
(MEDIUM relist-asymmetry residual), 3 OK (LOW residuals). Artifact-path report:
the contract md is STILL MISSING at the bot path (HIGH). Artifacts untouched;
`~/.hermes/bot` is not a git repository (re-verified, rc 128), so the required
local commit lands in the workspace repo (merchant-routing) at
`docs/reviews/findings_1_3.md`, with this identical copy at the task-mandated
bot path `~/.hermes/bot/docs/reviews/findings_1_3.md`.
