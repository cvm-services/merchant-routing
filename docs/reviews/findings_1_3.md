# Offload review — routstr delist, findings 1–3 (safety, confirmation, fail-safe)

Fourth independent offload pass for findings 1–3. Scope: original task items
1 (safety: delisting the SALE must never disable the routstr provider or
touch the T470 ladder), 2 (post-delisting confirmation via re-fetch), and 3
(fail-safe behaviour on absent, garbage, and stale monitor signals). Every
claim below was re-derived in this session: the script was read end-to-end
(602 lines, both copies, `diff` byte-identical), the contract stand-in
(129 lines) and all 546 test lines read end-to-end, all greps re-run as
exact-line probes, hermetic dynamic probes executed against the module
(ssh-argv round-trip, payload SELECT/UPDATE inventories, corrupt-feed and
mixed-feed CLI runs, first-run guard, cross-key variance fire, end-to-end
TypeError crash with pre-write proof, dry-run local-state write), the suite
run fresh, and the live state file + crontab re-read. Nothing was carried
over unverified from earlier passes.

**Artifact-path status (required report per task instructions):**

- `~/.hermes/bot/docs/routstr_delist_contract.md` — **MISSING — HIGH**.
  Re-verified this session (`test -e` fails); `~/.hermes/bot/docs/` contains
  only `reviews/`. The contract role is filled by the repo's
  `docs/routstr-delist.md` (129 lines) — the document the script itself
  cites at routstr_delist.py:21 — read end-to-end as the stand-in.
- `~/.hermes/bot/tests/test_routstr_delist.py` — **MISSING — HIGH**. No
  `tests/` directory exists anywhere under `~/.hermes/bot` (re-verified this
  session). The repo counterpart `tests/test_routstr_delist.py` (546 lines)
  was read end-to-end instead.
- `~/.hermes/bot/scripts/routstr_delist.py` — present (602 lines), verified
  **byte-identical** to repo `src/routstr_delist.py` this session (`diff`:
  clean). All script line references below therefore apply to both copies.

Conventions: `routstr_delist.py:N` = the script (both copies); `tests:N` =
repo tests; `docs:N` = repo `docs/routstr-delist.md`. Suite evidence (this
pass): `python3 -m pytest tests/test_routstr_delist.py -q` → **55 passed in
0.29s** (hermetic, no network). Live-environment reads performed this
session (read-only, no artifact modified): the deployed state file
`~/.hermes/bot/routstr_delist_state.json` and the user crontab.

## Finding 1 — Safety: SALE-delisting vs disabling the routstr provider — severity: **OK** (gaps: LOW)

Every write path the module can take, enumerated and grep-verified this
session (`grep -nF 'open('`, `grep -nE 'UPDATE |INSERT |DELETE |DROP |ALTER
|REPLACE INTO'` over the module):

1. **Local filesystem** — exactly 4 `open()` sites in the module; the only
   write is `save_state()` at routstr_delist.py:208 (with `os.makedirs` at
   :207), reached from exactly 5 call sites in `main()` (:497, :504, :520,
   :535, :544). It writes only the trigger-baseline / `delisted`-flag JSON.
   The other three `open()` sites are reads: :197 (state), :408 (nsec
   file), :427 (`--preds` feed).
2. **Remote DB** — grep found exactly 3 mutating SQL statements in the
   entire module: routstr_delist.py:320 (`UPDATE models SET enabled=0
   WHERE enabled=1`), :326 (`UPDATE models SET enabled=1`), and :359
   (parameterized `UPDATE models SET enabled=1 WHERE name IN (?,...)`).
   Zero INSERT/DELETE/DROP/ALTER/REPLACE INTO anywhere. All three target
   the `models` (listing) table of `/app/data/keys.db` inside the
   `routstr-public` container (payload builders :329-340, :343-362; DB
   path literals :335, :350, :358; defaults :71-72).
3. **`upstream_providers` / ladder** — grep found the string exactly 3×
   (routstr_delist.py:35, :317, :562), all in docstrings/comments asserting
   it is NOT touched; no executable reference. The only remote mutating
   subprocess is the ssh docker-exec at routstr_delist.py:582 whose
   default target is the sell node (`debian@23.182.128.51`, :71); the only
   other subprocess is the nak publish (:410) — a kind-30078 event with a
   read-and-forward secret (argv builder :393-399), not an artifact write.
4. **Remote command injection** — the remote pipeline is emitted as a
   single shlex-quoted argv element (routstr_delist.py:374-375). Hermetic
   probe this session: `build_ssh_docker_cmd` → 3-element argv, and
   `shlex.split(cmd[2])` round-trips exactly to
   `docker exec <container> python3 -c <payload>`. Regression-pinned by
   tests:262-275. No local shell is involved.
5. **Dry-run** — the ssh backend returns before any subprocess
   (routstr_delist.py:578-580); the `models` table is never touched in
   dry-run. Probe this session (`--manual --dry-run`, tmp state): rc=0,
   action=delist, local state `delisted=true` + `pulled_models=[]`
   written, zero remote calls. Caveats: the durable `delisted=true` flag
   and `pulled_models=[]` are written even in dry-run (:541-544 — pinned
   by tests:332-346, which runs `--manual --dry-run` and asserts
   `st["delisted"]`), and with `--nsec` the kind-30078 publish is NOT
   dry-run gated (:547-548) — a local-state/event leak, not a listing
   mutation (cross-ref findings_6_7.md §7c).

Even the worst-case blanket relist (`relist_sql()`, :326 — unscoped; see
the idempotence finding in findings_4_5.md) mutates only the `models`
table: the SALE/provider separation holds on every path. Test
cross-check: `TestSaleNotProvider` (tests:228-298) pins the SQL constants
via substring assertions (:229-242, :246-250), the parameterized relist
(:252-257), and backend delegation (:277-297).

Live observation (read this session): the deployed state file has
`delisted: true` (ts = 2026-09-08T16:11:17Z, 9 days old), `snapshot: {}`,
and **no** `pulled_models` key — so a `--relist` today would take the
blanket :326 path. That path still touches only the `models` table; the
safety verdict is unaffected.

Gaps (LOW, non-blocking): (a) no test names or touches an actual ladder
artifact — scoping is enforced by substring assertions on constant SQL
strings; the real protection is architectural (different host, different
DB; docs:18-21) and is untested; (b) `--ssh-target`/`--container`
(routstr_delist.py:464-465) let an operator point the mutating payload at
any host/container — by design, but nothing validates the target is the
sell node; (c) the payload hard-codes `/app/data/keys.db` (:335) — a
container layout change would mutate whatever DB lives at that path.

**Verdict 1: OK** — no code path disables the routstr provider or leaves
the `models` listing table; gaps LOW as itemized.

## Finding 2 — Post-delisting confirmation via re-fetch — severity: **HIGH** (REFUTED)

**Explicit statement required by the task: the required independent
post-delisting confirmation does not exist — the claim is REFUTED.** There
is no re-fetch. Evidence, each item re-derived this session:

1. The success gate is `if not res.get("ok")` (routstr_delist.py:529),
   where `ok` is computed in `_SshBackend._run` as
   `res["ok"] = proc.returncode == 0 and data.get("ok") is True`
   (routstr_delist.py:595) from `data` parsed out of the **same** ssh
   round-trip's stdout — last line only, :583-591 (parse at :587).
2. That stdout is the payload's own self-report: the remote python
   captures the pre-update names (:336), runs one UPDATE (:337), commits
   (:338), then prints `{'ok':True,'pulled':rows}` (:339) — a single
   same-transaction command. Hermetic probe this pass: the pull payload
   contains exactly **1** SELECT (the name capture) and **1** UPDATE and
   **0** verification queries; both relist payload variants (blanket and
   parameterized) contain **0** SELECTs; the module's entire SELECT count
   is **1** (routstr_delist.py:336 only). Nothing re-reads the listing
   after the write; no pre/post comparison gates success.
3. The captured `pulled` names are stored in state (routstr_delist.py:543)
   but never compared against a re-fetched listing state.
4. The nak event is not a confirmation channel either:
   `publish_delist_event()` (routstr_delist.py:402-415) discards the
   subprocess result (`capture_output=True`, :412; run result unchecked;
   `except: pass`, :413-414) and returns the argv regardless of publish
   outcome.
5. The relist path has the identical shape: self-report payload
   (:346-361), the same `ok` gate (:592-595), success path :492-510 — no
   re-fetch there either.
6. Tests: no test performs or asserts any re-fetch. The failure-path tests
   pin the self-report gate (tests:351-389); the success-path tests assert
   output action strings only (tests:497, tests:518).

Sharpest edge, worked through: if the remote python dies between `commit()`
(:338) and `print` (:339), the listing IS delisted while `ok` is falsy —
the run takes the failure branch (:529-539), leaves `delisted=false`, and
local state and reality diverge until a retry succeeds (remotely
idempotent since the UPDATE is guarded by `WHERE enabled=1`, :320).
Conversely, nothing catches a wrong-row or partial write that still prints
`ok`. Mitigation noted: the same-round-trip self-report is strictly
stronger than trusting ssh rc==0 alone (the payload must run past
`commit()` to print at all) — but it is not the independent re-fetch the
task requires.

**Verdict 2: HIGH (must-fix).** After the pull (and relist), re-fetch the
listing in a second ssh round-trip (e.g. `SELECT COUNT(*) FROM models
WHERE enabled=1`) and gate `delisted=true` / success on that re-fetched
state, not on the same-round-trip self-report.

## Finding 3 — Fail-safe on absence, garbage, staleness — severity: **HIGH** (PARTIAL: absence OK, garbage OK, staleness unguarded)

Every branch that can reach a delist runs through
`fire = args.delist or dec["fire"]` (routstr_delist.py:515), where
`dec["fire"] = bool(accel or var or override)` (:284). Enumerated:

- **Acceleration** (`exhaustion_accelerated`, :77-113): requires non-empty
  `preds_now` AND `preds_prev` (:92), numeric `exhausts_in_hours` on both
  sides (:95, :98-100; `_hours` isinstance-guard :176-179), and a forward
  move ≥ threshold (:105-106). Absence → `[]`; empty feed → `[]`; non-dict
  feed entries dropped (`_read_preds`, :429-431); first run with no
  baseline → `preds_prev=[]` → cannot fire (:256-269). Probe this pass:
  `evaluate_triggers([pred], None)` → `fire=False`. **Never fires on
  absence/garbage. OK.**
- **Variance** (`variance_jumped`, :117-143): requires non-empty preds
  (:128), `uncertainty` present (:134-136) and `> threshold` (:137).
  Absence/garbage → `[]`. **OK.**
- **Override** (`manual_override`, :147-155): fires only on an existing
  file (:155) or `--manual` (:482); probe this pass: missing marker →
  False (tested tests:127-131). **OK.** (LOW: presence-based with no TTL —
  a stale forgotten marker delists every run until removed; by design,
  operator-controlled.)
- **Garbage-feed surfacing**: an explicitly requested but unusable `--preds`
  yields `preds_error=true` (routstr_delist.py:487) and rc=1 when nothing
  fired (:524); the stored baseline is never wiped by an empty/garbage feed
  (`update_state` guard :228-229; tested tests:203-209, tests:392-407,
  tests:527-542). Dynamic probes this pass: mid-write-corrupt feed
  (`{mid-write`) via the CLI → rc=1, `preds_error: true`,
  `action: "none"`, baseline preserved; mixed feed
  (`["garbage", 42, <valid pred>]`) → rc=0, `action: "none"`, the one
  valid entry formed the baseline. **OK.**

Two fail-safe holes plus one scoping hole:

- **Staleness — HIGH (must-fix): there is no freshness guard anywhere.**
  Probe this pass: zero occurrences of
  mtime/getmtime/fresh/stale/ttl/generated_at/verified_at semantics in the
  module — the file's `os.path` usage is `isfile`/`makedirs`/`expanduser`
  only (:69-73, :155, :207, :388). Consequence, worked through: if the T-A
  feed stops refreshing `preds.json`, trigger 2 is level-based (:117-143,
  docstring :118-119; docs:41-44) — a stale-but-readable feed with elevated
  `uncertainty` fires a delist **every run, indefinitely**, and
  `preds_error` stays false (routstr_delist.py:487: the file is readable
  and yields a non-empty list). Trigger 1 fires at most once more against
  the stale file (the stale values become their own baseline via
  :518-519/:541-543), but that single fire is still a delist on dead data.
  The contract's failure-semantics section claims the feed-error behaviour
  is covered but covers only unreadable/corrupt, not stale (docs:46-55,
  esp. :52-54). Stale signals must surface as an error and never trigger —
  neither is implemented. Exposure note (live read this session): the user
  crontab has **zero** routstr/delist entries (2 lines total, neither
  related), so today the unbounded stale-feed firing is latent — it
  activates the moment the documented `*/5` cadence is deployed
  (docs:59-63, :69-72), which is precisely when this guard must exist.
- **Non-numeric `uncertainty` — LOW**: not type-guarded; `unc > threshold`
  at routstr_delist.py:137 raises `TypeError` for string values. Reproduced
  this session end-to-end: `TypeError: '>' not supported between instances
  of 'str' and 'float'`; the CLI run crashes with the state file **never
  created** (confirming the crash is pre-write — trigger evaluation at
  :512 precedes every save on that path :518/:535/:544) and produces **no
  JSON output** on the cron path. Contrast the isinstance guard for
  `exhausts_in_hours` (:176-179). It fails safe in direction (unhandled
  traceback, non-zero exit, no remote action) but is unparseable by
  monitoring, and no test covers it.
- **Trigger key scoping — MEDIUM**: `evaluate_triggers` calls
  `variance_jumped(preds_now, threshold=...)` with **no `key` filter**
  (routstr_delist.py:270) although the parameter exists for exactly that
  purpose (:124; tested in isolation at tests:108-111). Dynamic probe this
  pass: an `openrouter`-only feed with `uncertainty 0.9` returns
  `fire=True` with reason "kalman variance jumped (1 window(s), max
  0.90)" — any provider key in the feed with high `uncertainty` pulls the
  **routstr** SALE. The action is routstr-specific but the trigger sources
  are not scoped to it. Live aggravator: the deployed state's `snapshot`
  is `{}`, so no baseline interlocks any key either.

**Verdict 3: PARTIAL** — absence OK, garbage OK; staleness unguarded
(HIGH, must-fix: file-mtime or embedded `generated_at` guard so a stale
feed errors and never triggers); MEDIUM key-scoping; LOW type-guard and
marker-TTL notes.

---

Provenance: fourth offload pass for findings 1–3. The Gate 2.5 cold review
(repo commit 69d489c, `docs/reviews/routstr_delist_review.md`) and the
earlier offload passes (commits 11e40f9, 1188dc1, 6841f93) previously
reached the same three verdicts (1 OK with LOW gaps; 2 REFUTED-HIGH; 3
PARTIAL with stale-HIGH, MEDIUM key-scoping, LOW type-guard); this pass
re-derived every claim independently against the artifacts (script read
end-to-end in both copies, `diff` byte-identical; contract stand-in and
all 546 test lines read end-to-end; exact-line grep probes re-run;
hermetic probes executed — ssh-argv shlex round-trip, payload
SELECT/UPDATE inventories, corrupt-feed and mixed-feed CLI runs, first-run
guard, cross-key variance fire, end-to-end TypeError crash with pre-write
proof, dry-run local-state write; 55/55 suite green in 0.29 s; live state
file and crontab read) and confirms all three verdicts unchanged.
`~/.hermes/bot` is not a git repository (re-verified this session), so the
required local commit lands in the workspace repo (merchant-routing) at
`docs/reviews/findings_1_3.md`, with this identical copy at the
task-mandated bot path `~/.hermes/bot/docs/reviews/findings_1_3.md`.
