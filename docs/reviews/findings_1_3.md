# Offload review — routstr delist, findings 1–3 (safety, confirmation, fail-safe)

Sixth independent offload pass for findings 1–3. Scope: original task items
1 (safety: delisting the SALE must never disable the routstr provider or
touch the T470 flat-router ladder), 2 (post-delisting confirmation via
re-fetch), and 3 (fail-safe behaviour on absent, garbage, and stale monitor
signals). Every claim below was re-derived in this session: the script was
read end-to-end (602 lines, both copies, `diff` byte-identical), the
contract stand-in (129 lines) and all 546 test lines read end-to-end, all
write-path/SQL/exec inventories re-run as exact-line greps, and 12 hermetic
probes executed (ssh-argv shlex round-trip, payload SELECT/UPDATE
inventories, parameterized-relist shape, first-run guard, cross-key
variance fire, end-to-end TypeError crash on the deployed bot copy with
pre-write proof, corrupt-feed CLI run, dry-run local-state write, backend
dry-run zero-subprocess proof, freshness keyword scan, no-op re-pull →
blanket-relist arming, mocked nak-publish failure). Nothing was carried
over unverified from earlier passes.

**Artifact-path status (required report per task instructions):**

- `~/.hermes/bot/docs/routstr_delist_contract.md` — **MISSING — HIGH**.
  Re-verified this session (`read_file`: file not found; directory listing
  shows `~/.hermes/bot/docs/` contains only `reviews/`). The contract role
  is filled by the repo's `docs/routstr-delist.md` (129 lines) — the
  document the script itself cites at routstr_delist.py:21 — read
  end-to-end as the stand-in.
- `~/.hermes/bot/tests/test_routstr_delist.py` — **MISSING — HIGH**. No
  `tests/` directory exists anywhere under `~/.hermes/bot` (verified this
  session: `ls` reports "No such file or directory"). The repo counterpart
  `tests/test_routstr_delist.py` (546 lines) was read end-to-end instead
  and its suite executed.
- `~/.hermes/bot/scripts/routstr_delist.py` — present (602 lines), verified
  **byte-identical** to repo `src/routstr_delist.py` this session (`diff`:
  clean, rc=0). All script line references below therefore apply to both
  copies.

Conventions: `routstr_delist.py:N` = the script (both copies); `tests:N` =
repo tests; `docs:N` = repo `docs/routstr-delist.md`. Suite evidence (this
pass): `python3 -m pytest tests/test_routstr_delist.py -q` → **55 passed in
0.22s** (hermetic, no network).

Disclosure: live-environment reads (user crontab + deployed state file
`~/.hermes/bot/routstr_delist_state.json`) were denied by the operator in
the fifth-pass session and, per that session's disclosure, were **not
retried** this session. Live-exposure statements below therefore cite the
contract text (which itself records that no crontab entry is wired yet,
docs:69-72), labeled as such; no verdict below depends on live state.

## Finding 1 — Safety: SALE-delisting vs disabling the routstr provider — severity: **OK** (gaps: LOW)

Every write path the module can take, enumerated and grep-verified this
session (`grep -nF 'open('`, `grep -nE 'UPDATE |INSERT INTO|DELETE |DROP |
ALTER |REPLACE INTO'`, `grep -nF 'SELECT'`, `grep -nE
'subprocess\\.(run|Popen|call|check_output)'`, `grep -cF 'shell=True'`,
`grep -nE 'os\\.(remove|unlink|rmdir|rename|system)|eval\\(|exec\\('`):

1. **Local filesystem** — exactly 4 `open()` sites in the module
   (routstr_delist.py:197, :208, :408, :427); the only write is
   `save_state()` at routstr_delist.py:208 (with `os.makedirs` at :207),
   reached from exactly 5 call sites in `main()` (:497, :504, :520, :535,
   :544 — grep-verified). It writes only the trigger-baseline /
   `delisted`-flag JSON. The other three `open()` sites are reads: :197
   (state), :408 (nsec file), :427 (`--preds` feed). Zero
   `os.remove/unlink/rmdir/rename/system` and zero local `eval(`/`exec(`
   anywhere (grep: clean, this pass added that inventory) — the override
   marker is only ever `isfile`-probed (:155).
2. **Remote DB** — exactly 3 mutating SQL statements in the entire module:
   routstr_delist.py:320 (`UPDATE models SET enabled=0 WHERE enabled=1`),
   :326 (`UPDATE models SET enabled=1`), and :359 (parameterized
   `UPDATE models SET enabled=1 WHERE name IN (?,...)`). Zero
   INSERT/DELETE/DROP/ALTER/REPLACE INTO (grep: clean). All three target
   the `models` (listing) table of `/app/data/keys.db` inside the
   `routstr-public` container (payload builders :329-340, :343-362; DB path
   literals :335, :350, :358; defaults :71-72). The module's only SELECT
   (:336) is a read-only name capture — module-wide SELECT count is
   exactly 1 (probe P2, grep: :336 only).
3. **`upstream_providers` / ladder** — the string occurs exactly 3×
   (routstr_delist.py:35, :317, :562), all in docstrings/comments asserting
   it is NOT touched; zero executable references. Only 2 subprocess sites
   exist (grep: :410, :582): the ssh docker-exec at :582 (default target =
   the sell node `debian@23.182.128.51`, :71) and the nak publish at :410
   (kind-30078 event; argv builder :393-399) — neither writes repo/ladder
   artifacts. `shell=True`: zero occurrences (grep count 0).
4. **Remote command injection** — the remote pipeline is emitted as a
   single shlex-quoted argv element (routstr_delist.py:374-375). Hermetic
   probe P1 this session: `build_ssh_docker_cmd` → 3-element argv
   (`ssh`, host, one remote string); `shlex.split(cmd[2])` round-trips
   exactly to `docker exec <container> python3 -c <payload>` (container
   containing a space tested). Regression-pinned by tests:262-275. No
   local shell is involved.
5. **Dry-run** — the ssh backend returns before any subprocess
   (routstr_delist.py:578-580); probe P8 this session (spy on
   `subprocess.run`): `pull(dry_run=True)` → **0** subprocess calls,
   returns `{'ok': True, 'dry_run': True, ...}`. CLI probe P7
   (`--manual --dry-run`, tmp state): rc=0, action=delist, local state
   `delisted=true` + `pulled_models=[]` written. Caveats: the durable
   `delisted=true` flag and `pulled_models=[]` are written even in dry-run
   (:541-544 — pinned by tests:332-346, which runs `--manual --dry-run`
   and asserts `st["delisted"]`), and `--nsec` publishes are NOT dry-run
   gated (:547-548 delist, :505-506 relist — `publish_delist_event`
   unconditionally runs `nak` at :410) — local-state/event leaks, not
   listing mutations (cross-ref findings_6_7.md §7c).

Even the worst-case blanket relist (`relist_sql()`, :326 — unscoped; see
findings_4_5.md) mutates only the `models` table: the SALE/provider
separation holds on every path. Test cross-check: `TestSaleNotProvider`
(tests:228-297) pins the SQL constants via substring assertions
(:229-242, :246-250), the parameterized relist (:252-257), the shlex
round-trip (:262-275), and backend delegation incl. dry-run preference
(:277-297). Contract: docs:13-21 states the distinction and the
models-table-only enforcement; docs:89-96 documents the remote-execution
shlex safety.

Gaps (LOW, non-blocking): (a) no test names or touches an actual ladder
artifact — scoping is enforced by substring assertions on constant SQL
strings; the real protection is architectural (different host, different
DB; docs:18-21) and is untested; (b) `--ssh-target`/`--container`
(routstr_delist.py:464-465) let an operator point the mutating payload at
any host/container — by design, but nothing validates the target is the
sell node; (c) the payload hard-codes `/app/data/keys.db` (:335, :350,
:358) — a container layout change would mutate whatever DB lives at that
path.

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
   round-trip's stdout — last line only (:587).
2. That stdout is the payload's own self-report: the remote python
   captures the pre-update names (:336), runs one UPDATE (literal :320,
   embedded at :337), commits (:338), then prints `{'ok':True,'pulled':
   rows}` (:339) — a single same-transaction command. Hermetic inventory
   probe P2 this pass: the pull payload contains exactly **1** SELECT (the
   name capture) and **1** UPDATE and **0** verification queries; both
   relist payload variants (blanket and parameterized) contain **0**
   SELECTs; the module's entire SELECT count is **1** (routstr_delist.py:336
   only, grep-confirmed). Nothing re-reads the listing after the write; no
   pre/post comparison gates success.
3. The captured `pulled` names are stored in state (routstr_delist.py:543)
   but never compared against a re-fetched listing state.
4. The nak event is not a confirmation channel either — strengthened this
   pass with a direct mock probe (P11): `publish_delist_event()`
   (routstr_delist.py:402-415) was invoked with `subprocess.run` mocked to
   return rc=1/stderr="boom"; the function still returned the argv
   normally — the subprocess result is discarded (`capture_output=True`,
   :412; run result unchecked; `except: pass`, :413-414), so a failed
   publish is indistinguishable from a successful one. (Positive note from
   the same probe: the argv uses `--env-sec`, never `--sec` — the key is
   not exposed in `ps`; matches tests:316-317.)
5. The relist path has the identical shape: self-report payload
   (:346-361), the same `ok` gate (:592-595), success path :492-510 — no
   re-fetch there either.
6. Tests: no test performs or asserts any re-fetch. The failure-path tests
   pin the self-report gate (tests:351-390); the success-path tests assert
   output action strings only (tests:497, tests:518).

Sharpest edges, worked through and probed this pass:

- **Post-commit divergence family.** If the remote python dies between
  `commit()` (:338) and `print` (:339) — or anything after the JSON line
  breaks the last-line parse at :587 (trailing warnings, channel noise) —
  the listing IS delisted while `ok` is falsy: the run takes the failure
  branch (:529-539), reports `delist_failed`, leaves `delisted=false`.
  Local state and reality diverge, and with no circuit breaker (finding 6)
  retries continue indefinitely.
- **No-op re-pull degrades to blanket relist (probe-confirmed end-to-end,
  P9).** On a retry after the table is already delisted, the name capture
  (`SELECT ... WHERE enabled=1`, :336) returns `[]`; the payload still
  reports `ok`, and `pulled_models=[]` is stored (:543). The next
  `--relist` then takes `names = state.get("pulled_models") or []`
  (:491) → empty → the blanket branch (:347-354, `UPDATE models SET
  enabled=1` unscoped). End-to-end probe P9 this pass through `main()`
  with faked backends: pull-with-`pulled=[]` → state stores `[]`;
  subsequent `--relist` invoked the backend with `names=[]` (recorded
  call: `('relist', [], False)`) and the executed payload is the blanket
  branch (no `WHERE`), rc=0. The missing independent confirmation thus
  not only fails to verify the write — it structurally collapses the
  scoped-relist guarantee after any double fire (cross-ref
  findings_6_7.md §7c, findings_4_5.md idempotence).

Mitigation noted: the same-round-trip self-report is strictly stronger
than trusting ssh rc==0 alone (the payload must run past `commit()` to
print at all) — but it is not the independent re-fetch the task requires,
and it cannot distinguish "0 rows advertised now" from "already delisted".

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
  baseline → `preds_prev=[]` → cannot fire (:256-269). Probe P3 this
  pass: `evaluate_triggers([pred], None)` → `fire=False`. **Never fires
  on absence/garbage. OK.**
- **Variance** (`variance_jumped`, :117-143): requires non-empty preds
  (:128), `uncertainty` present (:134-136) and `> threshold` (:137).
  Absence/garbage-with-missing-uncertainty → `[]`. **OK.**
- **Override** (`manual_override`, :147-155): fires only on an existing
  file (:155) or `--manual` (:482); missing marker → False (tested
  tests:127-131). **OK.** (LOW: presence-based with no TTL — a stale
  forgotten marker delists every run until removed; by design,
  operator-controlled.)
- **Garbage-feed surfacing**: an explicitly requested but unusable
  `--preds` yields `preds_error=true` (routstr_delist.py:487) and rc=1
  when nothing fired (:524); the stored baseline is never wiped by an
  empty/garbage feed (`update_state` guard :228-229; tested tests:203-209,
  tests:392-407, tests:527-542). Dynamic probe P6 this pass: mid-write-
  corrupt feed (`{mid-write`) via the CLI → rc=1, `preds_error: true`,
  `action: "none"`, baseline preserved verbatim in state. **OK.**

Two fail-safe holes plus one scoping hole:

- **Staleness — HIGH (must-fix): there is no freshness guard anywhere.**
  Probe P10 this pass: zero occurrences of
  mtime/getmtime/fresh/stale/ttl/generated_at/verified_at semantics in
  the module (case-insensitive regex over all 602 lines; the file's
  `os.path` usage is `isfile`/`makedirs`/`expanduser` only — :69-73,
  :155, :207, :388). Consequence, worked through: if the T-A feed stops
  refreshing `preds.json`, trigger 2 is level-based (:117-143, docstring
  :118-119; docs:41-44) — a stale-but-readable feed with elevated
  `uncertainty` fires a delist **every run, indefinitely**, and
  `preds_error` stays false (routstr_delist.py:487: the file is readable
  and yields a non-empty list). Trigger 1 fires at most once more against
  the stale file (the stale values become their own baseline via
  :518-519/:541-543), but that single fire is still a delist on dead
  data. The contract's failure-semantics section claims feed-error
  coverage but covers only unreadable/corrupt, not stale (docs:46-55,
  esp. :52-54). Stale signals must surface as an error and never trigger
  — neither is implemented. Exposure note: live crontab/state reads were
  denied (fifth pass) and not retried (disclosure above); the contract
  itself documents that no crontab entry is wired yet (docs:69-72) with
  the intended `*/5` cadence at docs:59-63 — i.e. the unbounded
  stale-feed firing is latent until that deployment, which is precisely
  when this guard must exist.
- **Non-numeric `uncertainty` — LOW**: not type-guarded;
  `unc > threshold` at routstr_delist.py:137 raises `TypeError` for string
  values. Reproduced this pass (P5) end-to-end via the CLI against the
  **deployed bot copy**: rc=1, stderr carries `TypeError: '>' not
  supported between instances of 'str' and 'float'`, the state file is
  **never created** (the crash is pre-write — trigger evaluation at :512
  precedes every save on that path :518/:535/:544) and **no JSON output**
  (stdout unparseable by monitoring). Contrast the isinstance guard for
  `exhausts_in_hours` (:176-179). Fails safe in direction (non-zero exit,
  no remote action) but no test covers it.
- **Trigger key scoping — MEDIUM**: `evaluate_triggers` calls
  `variance_jumped(preds_now, threshold=...)` with **no `key` filter**
  (routstr_delist.py:270) although the parameter exists for exactly that
  purpose (:124; tested in isolation at tests:108-111). Dynamic probe P4
  this pass: an `openrouter`-only feed with `uncertainty 0.9` returns
  `fire=True` with reason "kalman variance jumped (1 window(s), max
  0.90)" — any provider key in the feed with high `uncertainty` pulls the
  **routstr** SALE. The action is routstr-specific but the trigger sources
  are not scoped to it.

**Verdict 3: PARTIAL** — absence OK, garbage OK; staleness unguarded
(HIGH, must-fix: file-mtime or embedded `generated_at` guard so a stale
feed errors and never triggers); MEDIUM key-scoping; LOW type-guard and
marker-TTL notes.

---

Provenance: sixth offload pass for findings 1–3. The Gate 2.5 cold review
(repo commit 69d489c, `docs/reviews/routstr_delist_review.md`) and the
earlier offload passes (11e40f9, 1188dc1, 6841f93, 4ae83d1, 5be0b99)
previously reached the same three verdicts (1 OK with LOW gaps; 2
REFUTED-HIGH; 3 PARTIAL with stale-HIGH, MEDIUM key-scoping, LOW
type-guard); this pass re-derived every claim independently against the
artifacts (script read end-to-end in both copies, `diff` byte-identical;
contract stand-in and all 546 test lines read end-to-end; exact-line grep
inventories re-run incl. a new eval/exec/os.system zero-site inventory; 12
hermetic probes executed — ssh-argv shlex round-trip, payload SELECT/UPDATE
inventories, parameterized-relist shape, first-run guard, cross-key
variance fire, end-to-end TypeError crash on the deployed bot copy with
pre-write proof, corrupt-feed CLI run, dry-run local-state write, backend
dry-run zero-subprocess proof, freshness keyword scan, no-op re-pull →
blanket-relist arming, mocked nak-publish failure; 55/55 suite green in
0.22s) and confirms all three verdicts unchanged. New this pass: the
mocked nak-publish-failure probe (finding 2 item 4 — argv returned
normally despite rc=1, publish outcome fully opaque) and the
eval/exec/os.system zero-site safety inventory (finding 1 item 1). Live
crontab/state reads were denied in the fifth-pass session and are not
retried (disclosure above). `~/.hermes/bot` is not a git repository
(recorded by every prior pass), so the required local commit lands in the
workspace repo (merchant-routing) at `docs/reviews/findings_1_3.md`, with
this identical copy at the task-mandated bot path
`~/.hermes/bot/docs/reviews/findings_1_3.md`.
