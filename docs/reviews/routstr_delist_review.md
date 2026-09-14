# Gate 2.5 cold review — routstr dynamic delist (T-D, ADR-007 Gate 4)

**VERDICT: CHANGES-REQUESTED**

Reviewed: `src/routstr_delist.py` (602 lines), `tests/test_routstr_delist.py`
(546 lines, 55 tests), `docs/routstr-delist.md` (129 lines, the design/contract
document). Review evidence: `python3 -m pytest tests/test_routstr_delist.py -q`
→ **55 passed in 0.40s** (hermetic, no network).

## Artifact-path status (report per task instructions)

- `~/.hermes/bot/docs/routstr_delist_contract.md` — **MISSING (HIGH)**. No
  `~/.hermes/bot/docs/` directory exists at all; no file matching `*contract*`
  exists under `~/.hermes` or anywhere in this repo (searched both trees).
- `~/.hermes/bot/tests/test_routstr_delist.py` — **MISSING (HIGH)**. No
  `~/.hermes/bot/tests/` directory exists.
- `~/.hermes/bot/scripts/routstr_delist.py` — present (602 lines), verified
  byte-identical to `src/routstr_delist.py` (clean `diff`).

Per instructions I reviewed the existing counterparts rather than stopping:
the contract role is filled by `docs/routstr-delist.md` (cited by the script
itself at src/routstr_delist.py:21), and the tests by
`tests/test_routstr_delist.py`. All `file:line` references below use the repo
copies; they apply equally to the bot-scripts copy. "Monitor file" in the
required findings maps to the script's `--preds` feed; "T-A signal" maps to
the `predict_exhaustion()`-shaped feed entries (docs/routstr-delist.md:123-129).

---

## Finding 1 — SALE-delisting vs disabling the routstr provider — **OK (gaps: LOW)**

Every path opened for write in `routstr_delist.py`, enumerated:

1. **Local state file** — the only `open(..., "w")` in the module is
   `save_state()` at src/routstr_delist.py:208, reached from exactly 5 call
   sites in `main()` (lines 497, 504, 520, 535, 544). It writes the trigger
   baseline / `delisted` flag JSON only.
2. **Remote DB** — the SSH docker-exec payloads
   (`pull_listing_payload()` src:329-340; `relist_payload()` src:343-362) run
   against `/app/data/keys.db` inside the `routstr-public` container on VPS2
   (`_DEFAULT_SSH_TARGET` src:70-72). The only mutating statements are
   `UPDATE models SET enabled=0 WHERE enabled=1;` (src:320) and
   `UPDATE models SET enabled=1 [WHERE name IN (?,...)]` (src:326, 359) —
   the `models` (listing) table only.
3. **Nostr event** — `build_delist_event()` argv (src:393-399) publishes a
   kind-30078 `d=routstr-delist` event; not a local artifact write.
4. **Dry-run** — returns without any subprocess (src:578-580); no writes.

The T470 flat-router **ladder artifact is not among them**: no code path in
the module addresses any router config, provider row, or `upstream_providers`
table (the string appears only in comments/docstrings at src:35, 317-318,
562), and the only remote host contacted is the sell node, not the router
host (docs/routstr-delist.md:70-72). The distinction is also carried in the
docstring (src:8-11), CLI help (src:439-441), and backend docstring
(src:561-563).

Test cross-check — the ladder-artifact assertion the task asks for does not
exist at artifact level; the closest assertions are SQL-substring checks in
`TestSaleNotProvider`, quoted verbatim (tests/test_routstr_delist.py:233-235):

```python
        low = sql.lower()
        self.assertNotIn("upstream_providers", low)
        self.assertNotIn("provider", low)
```

and for the payload (tests:246-247):

```python
        self.assertIn("UPDATE models SET enabled=0 WHERE enabled=1", p)
        self.assertNotIn("upstream_providers", p)
```

Gap (LOW): no test names or touches an actual ladder artifact file — the
scoping is enforced by substring assertions on constant SQL strings. Those
would catch an accidental edit of the constant (real regression value) but
are not evidence about the ladder itself; the architectural separation
(different host, different DB) is the actual protection and is untested.
Related: the relist inverse is NOT strictly the "exact inverse" the doc
claims — see Finding 4.

## Finding 2 — post-delisting confirmation via re-fetch — **REFUTED (HIGH)**

There is **no re-fetch**. The success gate is
`if not res.get("ok")` (src:529), where `ok` is computed in `_SshBackend._run`
as `res["ok"] = proc.returncode == 0 and data.get("ok") is True` (src:595)
with `data` parsed from the **same** ssh round-trip's stdout (src:583-591).
That stdout is the payload's own self-report: the remote python captures the
pre-update names, runs one `UPDATE`, commits, then prints
`{'ok':True,'pulled':rows}` (src:336-339) — all inside a single command.
Nothing re-reads the listing afterwards; no pre/post comparison gates
success; the `pulled` names are stored (src:543) but never compared against a
re-fetched state.

This is strictly stronger than trusting ssh rc==0 alone (the payload must
also run to completion past `commit()` and print), but it is a same-transaction
self-report, not the required independent re-fetch. Edge case worth noting: if
the remote python died between `commit()` and `print`, the listing would be
delisted while `ok` is falsy — the run takes the failure path (src:529-539),
leaves `delisted=false`, and re-fires next run (idempotent remotely since the
UPDATE is guarded by `WHERE enabled=1`, but local state and reality diverge
until the retry succeeds). **Required behaviour not implemented — must-fix.**

## Finding 3 — fail-safe on absence, garbage, staleness — **PARTIAL (stale: HIGH)**

Every branch that can reach a delist: `fire = args.delist or dec["fire"]`
(src:515), where `dec["fire"] = bool(accel or var or override)` (src:284).
Enumerated:

- **Acceleration** (`exhaustion_accelerated`, src:77-113): requires
  non-empty `preds_now` AND `preds_prev` (src:92), numeric
  `exhausts_in_hours` on both sides (src:95, 98-100; `_hours` type-guards at
  src:176-179), and a forward move ≥ threshold (src:105-106). Absence → `[]`
  (src:92); empty feed → `[]`; non-dict feed entries are dropped
  (`_read_preds`, src:430); non-numeric hours → skipped (src:179). First run
  with no baseline → `prev_snapshot = {}` → `preds_prev=[]` → cannot fire
  (src:256-269). **Never fires on absence/garbage. OK.**
- **Variance** (`variance_jumped`, src:117-143): requires non-empty preds
  (src:128) and `uncertainty > threshold` (src:137). Missing `uncertainty` →
  skipped (src:134-136). Absence/garbage → `[]`. **OK.**
- **Override** (`manual_override`, src:147-155): fires only on an existing
  file (src:155) or `--manual` (src:482). Missing marker → False (src:153-154;
  tested tests:127-131). **OK.** (LOW: the marker is presence-based with no
  TTL — a stale forgotten marker delists every run until removed; by design,
  operator-controlled.)
- **Feed error surfacing**: an explicitly requested but unusable `--preds`
  yields `preds_error=true` (src:487) and rc=1 when nothing fired (src:524);
  the stored baseline is never wiped by an empty/garbage feed
  (`update_state` guard, src:228-229; tested tests:203-209, 392-407). **OK.**

Two fail-safe holes:

- **Staleness (HIGH, must-fix): there is no freshness guard anywhere.** No
  mtime check on the preds file, no timestamp validation of feed entries, no
  age check on the stored baseline. Consequence, worked through: if T-A stops
  refreshing `preds.json`, trigger 2 is level-based (src:117-143, docstring
  src:118-119, docs:41-44) — a stale feed with elevated `uncertainty` fires a
  delist **every run, indefinitely**, and `preds_error` stays false (the file
  is readable and non-empty, src:487). Trigger 1 fires at most once more
  against the stale file (it becomes its own baseline) but that single fire
  is still a delist on dead data. The task requires stale signals to not
  trigger; the artifact implements no such guard. **Negative signal:** the
  doc (docs:52-54) claims the failure semantics are covered, but only covers
  unreadable/corrupt, not stale.
- **Non-numeric `uncertainty` (LOW): not type-guarded** — `unc > threshold`
  at src:137 raises `TypeError` for e.g. `"0.9"` (string), unlike
  `exhausts_in_hours` which is isinstance-guarded (src:179). The crash is
  pre-write (evaluate at src:512 happens before any save on that path) and
  exits non-zero, so it is fail-safe in direction, but it is an unhandled
  traceback on the cron path with no JSON output. No test covers it.
- **Trigger key scoping (MEDIUM)**: `evaluate_triggers` calls
  `variance_jumped(preds_now, threshold=...)` with no `key` filter (src:270),
  although the `key` parameter exists for exactly that purpose (src:124). Any
  provider key in the feed (e.g. an `openrouter` window) with high
  `uncertainty` pulls the **routstr** SALE. The delist action is routstr-
  specific but the trigger sources are not scoped to it.

## Finding 4 — atomicity and idempotence — **REFUTED on both (HIGH)**

**Atomicity — not implemented.** `save_state()` (src:204-212) writes with a
plain `open(path, "w")` (src:208) — no temp file, no `os.replace`, no `fsync`
(grep for `os.replace|tempfile|rename|fsync` in the module: zero hits). A crash
mid-write or a concurrent reader can observe a truncated/partial file.
`load_state()` never raises and returns `{}` on any parse failure (src:194-201),
so a torn write is silently read as *no state*: `--status` would report
`delisted: false` (src:474) and — per the design's "flag" mechanism
(docs:79-80, src:216-230) — a listing publisher reading the flag would see
`delisted=false` while the listing is actually pulled. No locking between
concurrent cron invocations either (last writer wins). The remote side is fine
(each payload is a single sqlite transaction, src:336-339 / 355-361); the local
state write is the non-atomic component. **Must-fix: tmp + `os.replace` +
`fsync`.**

**Idempotence — re-running on already-delisted input is NOT a no-op.** On a
successful delist the state stores `pulled_models: res.get("pulled", [])`
(src:541-543). Because trigger 2 is level-based, a second delist run while
the condition holds re-fires (src:515), re-runs the pull payload — whose
`SELECT name FROM models WHERE enabled=1` now returns `[]` (src:336) — and
**overwrites `pulled_models` with the empty list** (src:543). From then on
`--relist` reads `names = state.get("pulled_models") or []` (src:491), gets
`[]`, and falls back to the **unscoped blanket**
`UPDATE models SET enabled=1;` (src:326, 346-354) — enabling every model row,
including any the operator had deliberately disabled before the delist. This
contradicts docs:23-27 ("never rows the operator had disabled before the
delist") and the script docstring (src:36-37). This state is not
hypothetical: the live deployed state file
`~/.hermes/bot/routstr_delist_state.json` currently reads
`{"delisted": true, "last_reason": "manual override", "snapshot": {}, "ts":
1788883877.4}` with **no `pulled_models` key** — a `--relist` from it would
take the blanket path today. Also note the blanket relist itself has no
`WHERE` at all (src:326) and its fallback is blessed by a test
(tests:259-260). **Must-fix: preserve prior `pulled_models` on re-delist (or
merge), and make the no-names relist refuse or require an explicit flag
rather than blanket-enable.**

## Finding 5 — 5-minute SLA arithmetic — **DOES NOT HOLD as documented (HIGH)**

The numbers, written out:

- **Configured poll interval**: none in the script — it is a one-shot CLI.
  The documented deployment cadence is cron `*/5` = **300 s**
  (docs/routstr-delist.md:59-63, example crontab at docs:63).
- **Polls/retries needed to confirm**: **0** — there is no re-fetch
  (Finding 2) and no in-run retry: a single ssh attempt (src:582), and on
  failure the script exits 1 (src:539) and waits for the next cron tick.
- **Re-fetch round-trip**: **0 s / nonexistent** (no such code path).
- **Action round-trip bound**: `subprocess.run(..., timeout=60)` (src:582);
  typical ssh + docker exec ≈ 1-3 s, worst-case bounded at 60 s.
- **Worst-case detection-to-confirmed-delist**: trigger occurs at ε just
  after a cron tick → detection latency = 300 s (next tick) + in-run
  evaluation (~0 s) + ssh round-trip (≤ 60 s) = **360 s = 6 m 00 s**.
  **360 s > 300 s → the ≤5-minute bound is violated in the worst case by
  construction.** Even in the expected case (ssh ≈ 2 s) the total is
  ≈ 302 s > 300 s: with `*/5`, detection alone consumes the entire window
  and leaves 0 s for the action.
- **With k failed attempts**: (k+1)·300 s + 60 s — one transient ssh failure
  pushes confirmed delist to 660 s (11 min); there is no in-run retry to
  compress this.
- **`--nsec` path**: the nak publish (`timeout=30`, src:410) runs after the
  pull on the success path (src:547-548), so an in-run worst case is
  60 + 30 = 90 s before the success line prints — still under one cron
  period, but it inflates job duration.

`TRIGGER_ACTION_WINDOW_S = 300` (src:63) is a **dead constant**: grep shows it
is never consumed by any script logic — only by the docstring, the design doc,
and the tests (tests:330, 343). No code path measures or enforces the window;
the SLA is enforced nowhere. That is the "no signal" case precisely: the
constant looks like enforcement but nothing reads it. **Verdict: ≤5 minutes
does NOT hold with the documented `*/5` cadence.** It holds only under a
charitable "within 5 min of the script's own start" reading, or with a faster
cadence: `*/4` (240 s) + 60 s worst-case ssh = 300 s exactly; `*/2` gives
180 s worst case. Must-fix: either change the documented cadence to `*/4` or
faster, or add a bounded in-run retry, and wire the constant to something
real (or delete it).

## Finding 6 — circuit breaker (3 failures → BLOCKED, exit 3) — **REFUTED (HIGH)**

**Explicit statement required by the task: the circuit-breaker claim "3 failed
attempts → BLOCKED state, exit code 3" is REFUTED — no circuit breaker
exists in the artifact.**

Evidence:

- grep for `breaker|blocked|consecutive|attempt|circuit` across the script:
  the only hit is the word "consecutive" in an unrelated docstring sentence
  about prediction readings (src:15). No counter, no threshold, no BLOCKED
  state.
- `main()` returns only 0 or 1 (src:480, 500, 510, 524, 539, 555); there is
  no `return 3` / `sys.exit(3)` anywhere (grep of exit/return codes shown
  above).
- The durable state carries a single `last_pull_error` overwritten on each
  failure (src:533-535, 495-497) — not a consecutive-failure counter, so no
  reset semantics exist to state.
- **Can attempt 4 ever run? Yes — attempt 40 can.** Nothing halts repeated
  attempts: every cron tick re-fires the trigger and re-runs the ssh pull
  (level-based variance makes this indefinite, src:117-143), and no
  BLOCKED state is ever surfaced to the operator (output on the failure path
  is `action: delist_failed` with rc 1, src:536-539 — identical on the 1st
  and the 100th consecutive failure).

**Must-fix: implement the breaker** — consecutive-failure counter in the
durable state, halt after exactly 3, surface `BLOCKED` in the output JSON,
exit 3, reset the counter on success (and define whether a manual `--delist`
resets it).

## Finding 7 — hygiene — **OK in-process (MEDIUM on the operational loop)**

- **Secrets**: the nsec is read from a file (src:409) and passed to nak via
  child env `NOSTR_SECRET_KEY` with `--env-sec` (src:393-397, 410-412); the
  secret never appears in any argv (tested tests:316-317), is never printed,
  and is never persisted to state. `build_delist_event` returns None when
  the sec file is missing (src:388-389). The doc explicitly rejects `--sec`
  for ps-leak reasons (docs:82-84). Exception surfaces are `str(exc)` of
  `subprocess` failures (src:598) — these contain the ssh argv (host +
  payload), which contains no secret. `stdout`/`stderr` echoed into results
  are truncated to 200 chars (src:592-593) and come from the payload's own
  prints — no secrets. **OK.**
- **Loops**: all 5 loops in the module are finite `for` iterations over
  in-memory lists (src:97, 131, 187, 264, 276); there is no `while` loop;
  both subprocesses are timeout-bounded (60 s ssh, src:582; 30 s nak,
  src:410). **OK.**
- **MEDIUM**: the *operational* retry loop is unbounded — cron retries the
  failed pull every 5 minutes forever with no cap, deadline, backoff, or
  breaker (Finding 6). That is the only uncapped loop in the system, and it
  lives outside the process.
- LOW: `save_state` does not restrict file permissions (no chmod 600), but
  the state contains no credentials, so impact is nil.

## Finding 8 — test rigour — **MEDIUM (gaps concentrated in the required mechanisms)**

55 tests, 13 classes, all hermetic, 0.40 s. "If I mentally broke this
behaviour, would the existing tests fail?" — applied per claim:

- **Trigger logic — strong.** Inverting the acceleration direction
  (src:105) fails tests:59-62; off-by-one on either threshold fails
  tests:64-71 / 105-106; first-run false positive fails tests:136-141;
  missing-`uncertainty` handling fails tests:113-116; legacy `|` snapshot
  keys and `\x1f` round-trip fail tests:143-151, 178-190. **OK.**
- **Failure semantics — strong.** Consuming the baseline on a failed pull
  fails tests:351-375 (asserts rc==1, `delisted` false, `last_pull_error`
  present, and re-fire of the same acceleration); setting `delisted=true` on
  failure fails tests:371; wiping the baseline on a corrupt feed fails
  tests:392-407. **OK.**
- **Shell-safety — strong.** Dropping the single-arg quoting fails
  tests:262-275 (shlex round-trip re-parse). **OK.**
- **SQL scoping — substring-level only** (Finding 1): the assertions pin the
  constant strings, which is real regression value against accidental
  edits, but no artifact-level test exists.
- **Tautological tests (flagged):**
  - `test_window_constant_is_300` (tests:329-330) asserts
    `rd.TRIGGER_ACTION_WINDOW_S == 300` — a constant equal to a literal. It
    cannot fail while the SLA behaviour is deleted entirely; it pins
    nothing behavioural.
  - `test_event_content_reflects_relist` (tests:322-324) calls
    `build_delist_event("/nonexistent")`, gets None because the sec file is
    missing, and asserts None — the `delisted=False` parameter it claims to
    test is never exercised. Duplicate of tests:302-303 under a misleading
    name.
- **Mock-only assertions that would pass against a wrong implementation:**
  every pull/relist flow test injects `FakeBackend` (tests:32-46) or patches
  `_SshBackend` (tests:360, 417, 423, 437, 448). The production
  `_SshBackend._run` — last-line JSON parsing, rc+payload gating
  (src:583-595) — is **never executed by any test**. If `res["ok"]` were
  changed to `True` unconditionally (src:595), the suite still passes 55/55.
  Likewise `test_triggered_run_pulls_within_window` (tests:332-344) measures
  wall-clock of a dry run against the default backend — it proves the
  script doesn't sleep, nothing about the SLA.
- **Untested fail-safe branches:** stale feed (no guard exists, no test —
  Finding 3); non-numeric `uncertainty` crash (src:137 — no test); a
  well-formed `[]` JSON feed via CLI (only corrupt and garbage-entry feeds
  are tested, tests:392-407, 527-542).
- **Untested key claims:** re-fetch confirmation (absent, Finding 2);
  atomicity/torn-write (absent, Finding 4); idempotence — **no test runs two
  consecutive delists**, which is exactly why the `pulled_models` clobber
  (Finding 4) escapes the suite: the scoped-relist round-trip
  (tests:412-428) pulls and relists with no second delist in between, and
  its `fb2.calls` assertion would pass even though a re-delist in the gap
  destroys the names; circuit breaker (absent, Finding 6); ladder artifact
  untouchedness (no artifact named in any test).
- Event publish call-sites are mock-verified (tests:442, 453:
  `pub.assert_called_once_with(...)`), which is behavioural for the call
  but leaves the real `publish_delist_event` subprocess path untested
  (acceptable hermetic choice; the argv shape itself IS tested at
  tests:305-320). **OK with the noted gap.**

---

## Must-fix before merge

1. **Re-fetch confirmation (Finding 2, HIGH):** after the pull, re-fetch the
   listing in a second ssh round-trip (e.g. `SELECT COUNT(*) FROM models
   WHERE enabled=1`) and gate `delisted=true`/success on the re-fetched
   comparison — not on the same-round-trip self-report.
2. **Atomic state writes (Finding 4, HIGH):** `save_state()` must write
   tmp-file + `os.replace` (+ fsync) so no concurrent reader can observe
   partial state.
3. **Idempotence (Finding 4, HIGH):** stop overwriting `pulled_models` with
   `[]` on a repeat delist (merge with prior names); make the no-names
   relist refuse (or require explicit opt-in) instead of the blanket
   `UPDATE models SET enabled=1` — and note the live state file
   `~/.hermes/bot/routstr_delist_state.json` is already in the
   no-`pulled_models` state that triggers the blanket path.
4. **Feed freshness (Finding 3, HIGH):** add a staleness guard (file mtime or
   embedded `generated_at`) — a stale feed must surface as an error and must
   never trigger, level-based variance especially.
5. **Circuit breaker (Finding 6, HIGH):** implement 3-consecutive-failures →
   BLOCKED surfaced in output + exit code 3, counter in durable state, reset
   on success. Currently entirely absent (no counter, no BLOCKED, no exit 3).
6. **SLA (Finding 5, HIGH):** with the documented `*/5` cadence the worst
   case is 300 s detection + up to 60 s action = 360 s > 300 s. Either
   document/run `*/4` or faster (240+60=300 exactly), or add a bounded
   in-run retry; wire `TRIGGER_ACTION_WINDOW_S` to real logic or remove it.

Should-fix (non-blocking): type-guard `uncertainty` like `exhausts_in_hours`
(src:137 vs 179); scope the variance trigger to routstr-relevant keys (the
`key` param exists but is unused at src:270); exercise the real
`_SshBackend._run` parsing in tests; replace the two tautological tests
(tests:322-324, 329-330); add a double-delist idempotence test; add a
freshness/staleness test.

Note on the contract artifact: the stated
`~/.hermes/bot/docs/routstr_delist_contract.md` does not exist; this review
treated `docs/routstr-delist.md` as the contract. If a separate contract
document is intended, it must be delivered before the next gate.