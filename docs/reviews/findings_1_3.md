# Offload review — routstr delist, findings 1–3 (safety, confirmation, fail-safe)

Eighth independent offload pass for findings 1–3, re-adjudicated against the
CURRENT artifacts (post round-2 fixes, repo commits b879354 + 1c77910; the
829-line script is unchanged since the seventh pass — verified by content, not
assumed). Scope, per the original task: item 1 (safety: delisting the SALE
must never disable the routstr provider or touch the T470 flat-router ladder),
item 2 (post-delisting confirmation via re-fetch), item 3 (fail-safe behaviour
on absent, garbage, and stale monitor signals). Every claim below was
re-derived in this session: the script was read end-to-end in both copies
(829 lines, `diff` byte-identical), the contract suite (752 lines) read
end-to-end, the cited main-suite sections read directly, all
write-path/SQL/exec inventories re-run by grep, 5 hermetic probes executed
against the DEPLOYED bot script copy (no network, no subprocess), and all
three suites run green. Nothing was carried over unverified from earlier
passes.

**Artifact-path status (required report per task instructions):**

- `~/.hermes/bot/docs/routstr_delist_contract.md` — **MISSING — HIGH**.
  Re-verified this session: file-not-found; `~/.hermes/bot/docs/` holds only
  `reviews/` and `routstr-delist.md`; a repo-wide search for any
  `*contract*` doc finds only the pytest suite. The contract role is filled
  by TWO stand-ins, both read this session: repo `docs/routstr-delist.md`
  (197 lines, current) and the bot's own `~/.hermes/bot/docs/routstr-delist.md`
  (183 lines) — the latter is **stale**: `diff` shows it identical to the
  repo copy except it is missing exactly repo lines 177–190, the 14-line
  TDD-contract-suite description block (test inventory, FakeSellNode
  semantics, deployed-copy note). Documentation drift only; no code impact.
- `~/.hermes/bot/scripts/routstr_delist.py` — present (829 lines), verified
  **byte-identical** to repo `src/routstr_delist.py` this session (`diff`
  clean). All script line references below therefore apply to both copies.
- `~/.hermes/bot/tests/test_routstr_delist.py` — present (752 lines), verified
  **byte-identical** to repo `tests/test_routstr_delist_contract.py`
  (the 25-case TDD contract suite); its `../scripts` loader fallback
  (contract:47-54) runs it against the DEPLOYED bot script copy.

Conventions: `routstr_delist.py:N` = the script (both copies); `tests:N` =
repo `tests/test_routstr_delist.py` (121-case combined total with the
contract suite; the main suite itself is 96 cases); `contract:N` =
repo/bot contract suite; `docs:N` = repo `docs/routstr-delist.md`. Suite
evidence (this pass): `python3 -m pytest tests/test_routstr_delist.py
tests/test_routstr_delist_contract.py -q` → **121 passed in 0.46s**;
deployed copy `cd ~/.hermes/bot && python3 -m pytest tests/
test_routstr_delist.py -q` → **25 passed in 0.27s** (hermetic, no network).
Live exposure: `crontab -l | grep -ci routstr` → **0** this pass — no cron
wiring is live (matches the contract's deployment note, docs:112).

## Finding 1 — Safety: SALE-delisting vs disabling the routstr provider — severity: **OK** (gaps: LOW)

Every write path the module can take, enumerated and grep-verified this
session (`open(`, SQL-verb regex, `subprocess.`, `shell=True` count,
`eval(|exec(|os.system|os.remove|os.rmdir|os.rename`, `upstream_providers`):

1. **Local filesystem** — exactly 4 `open()` sites (routstr_delist.py:214
   state read, :231 the ONLY write — `save_state`'s tmp file, :457 nsec
   read, :476 preds read). `save_state` is called from exactly 8 sites
   (:565, :622, :629, :638, :654, :710, :732, :752) and writes only the
   trigger-baseline/`delisted`-flag JSON. Zero `eval(`/`exec(`/`os.system`/
   `os.remove|os.rmdir|os.rename` anywhere (grep clean); the only `os.unlink`
   (:243) targets the save_state tmp file itself (:230), and `os.replace`
   (:235) is the atomic-swap step. The override marker is only `isfile`-probed
   (:172).
2. **Remote DB** — exactly 3 mutating SQL statements in the module:
   routstr_delist.py:355 (`UPDATE models SET enabled=0 WHERE enabled=1`),
   :361 (blanket `UPDATE models SET enabled=1`, legacy fallback builder),
   :394 (parameterized `UPDATE models SET enabled=1 WHERE name IN (?,...)`).
   Exactly 2 SELECTs (:371 name capture, :408 verify COUNT) — all five
   statements target only the `models` (listing) table of
   `/app/data/keys.db` inside the `routstr-public` container (path literals
   :370, :385, :393, :407; defaults :86-87). Zero INSERT/DELETE/DROP/ALTER/
   REPLACE INTO (grep: clean).
3. **`upstream_providers` / T470 ladder** — the string occurs exactly 3×
   (routstr_delist.py:35, :352, :771), all inside docstrings asserting it
   is NOT touched; zero executable references. Only 2 subprocess sites
   exist (:459 nak publish, :808 ssh docker-exec); `shell=True` count is
   **0**; neither writes repo/ladder artifacts.
4. **Remote command injection** — the remote pipeline is emitted as a
   single shlex-quoted argv element (routstr_delist.py:414-425).
   Regression-pinned by tests:345-358 (3-element argv; `shlex.split(cmd[2])`
   round-trips to `docker exec <container-with-space> python3 -c
   <payload>` intact). No local shell is involved.
5. **Blanket relist is refused by default** — with no captured names,
   `--relist` refuses BEFORE any remote call (routstr_delist.py:602-611:
   `relist_refused`, exit 1); the blanket SQL is reachable only via the
   explicit `--relist-any` opt-in (:526-528 arg, exercised at
   tests:1065-1068). Even then it mutates only the `models` table — the
   SALE/provider separation holds on every path (cross-ref findings_4_5.md
   for the idempotence detail).
6. **Dry-run is fully intent-only** — the delist dry-run records
   `last_dry_run` and flips NO durable `delisted` flag, publishes nothing,
   counts no breaker failure, consumes no baseline (routstr_delist.py:699-
   717); relist dry-run likewise (:615-625). Pinned by tests:514-530 (no
   breaker count, no `last_pull_error`), tests:1072-1097 (no nak publish in
   either direction), and contract:731-752 — including that a PRE-EXISTING
   `delisted=true` flag survives a dry run untouched (contract:746-752).
7. **The ladder guard is TESTED semantically** — contract Case 6
   (:468-507) executes the script's REAL pull/verify/relist payloads
   against a sqlite stand-in that has a live `upstream_providers` table
   plus a ladder-artifact file, then asserts the artifact is
   byte-identical (:480), the provider table row-identical (:481), the
   routstr provider still enabled (:487-488), and that no executed payload
   even names `upstream_providers` (:482-483); the relist direction asserts
   only captured names come back and the ladder stays byte-identical
   (:490-507). Main-suite SQL-scoping assertions: tests:302-343 (incl.
   verify-payload read-only, :336-343).
8. **Secret hygiene** — the nak argv uses `--env-sec`, never `--sec`
   (routstr_delist.py:442-448); the key travels only via the
   `NOSTR_SECRET_KEY` env (:459-461); pinned by contract:705-729 (secret
   absent from stdout, state file, payloads, and argv).

Gaps (LOW, non-blocking, unchanged in kind from the prior pass): (a)
`--ssh-target`/`--container` (routstr_delist.py:536-537) let an operator
point the mutating payload at any host/container — by design, nothing
validates the target is the sell node; (b) the payloads hard-code
`/app/data/keys.db` ×4 (:370, :385, :393, :407) — a container layout
change would mutate whatever DB lives at that path; (c) `save_state`'s
return value is ignored at all 8 call sites — finding-4 residual (see
findings_4_5.md), noted here only because a failed write after a CONFIRMED
delist (:752) would silently diverge local state from remote reality.

**Verdict 1: OK** — no code path disables the routstr provider or leaves
the `models` listing table; the ladder protection has a semantic guard
(contract Case 6); gaps LOW as itemized.

## Finding 2 — Post-delisting confirmation via re-fetch — severity: **OK** (delist requirement MET since b879354; residual: MEDIUM relist asymmetry, LOWs itemized)

The pre-fix script had no re-fetch (correctly REFUTED by earlier passes);
the required independent re-fetch **exists** in the current artifacts.
Evidence, re-derived this session:

1. **The confirmation mechanism**: `verify_pull_payload()`
   (routstr_delist.py:400-411) is a read-only `SELECT COUNT(*) FROM models
   WHERE enabled=1` (probe this pass: payload contains no UPDATE; pinned
   contract:338-339, tests:336-343). It executes as a SEPARATE ssh
   round-trip via `_SshBackend.verify` (:790-793), called at :682 after
   the pull inside the attempt loop (:671-697). Success requires
   `vres.get("ok") is True and vres.get("count") == 0` (:683) — `confirmed`
   only then (:687), and only `confirmed` unlocks the `delisted=true`
   write (:747-752) and rc 0 (:764).
2. **A lying pull is refuted**: if the pull self-reports ok but the
   re-fetch still counts advertised models, the attempt is forced to
   failure no matter what the pull said (:689-694), retried once in-run
   (`MAX_PULL_ATTEMPTS = 2`, :75; loop :671-697), and on exhaustion takes
   the failure branch (:719-739: no `delisted` flag, baseline not
   consumed, breaker tick, exit 1/3). Pinned end-to-end by contract:346-360
   (FakeSellNode `pull_lands=False` — rc 1, `delist_failed`,
   kinds == pull,verify,pull,verify, `consecutive_failures == 1`) and
   tests:567-584 (verify count=1 → rc 1, no flag, 2 verifies across 2
   attempts) + tests:603-617 (verify transport failure counts as attempt
   failure).
3. **Parse/transport robustness fails safe**: the verify result goes
   through `_SshBackend._run` (:795-825) — non-zero ssh rc, unparseable
   stdout, or a missing `ok`/`count` key all yield a non-confirming
   result (`None == 0` is False), so garbage can only fail the run, never
   confirm it. Happy path is exactly one pull + one verify
   (contract:334), with `verified_count` recorded (:686) and the breaker
   reset on confirmed success (tests:586-601).
4. **Residual — MEDIUM: the relist path has NO symmetric re-fetch.**
   Relist success is gated on the round-trip self-report only
   (routstr_delist.py:626), and on that self-report the run sets
   `delisted=false` AND pops `pulled_models` (:633-635). A lying relist
   (rc 0, ok printed, UPDATE not landed — the same fault class the
   contract deemed must-fix for delist) therefore both fakes a restored
   listing and destroys the scoped name set; a subsequent scoped
   `--relist` is then refused (:602-611) and recovery forces
   `--relist-any` — which re-enables rows the operator had deliberately
   disabled (docs:29-32) — or a fresh delist/relist cycle. The contract
   mandates the re-fetch only for "a fired delist" (docs:69-75), so this
   is an asymmetry, not a contract breach — but the fix is cheap: verify
   after relist (e.g. COUNT(*)>0 or per-name re-read) before popping
   `pulled_models`.
5. LOW notes: (a) dry-run sets `confirmed=True` without any remote verify
   (:679-681) — intent-only with no remote action, so there is nothing to
   confirm; documented at docs:87-89; (b) the verify round-trip shares the
   ssh transport and last-line JSON parsing with the pull (:810-822) — it
   is an independent round-trip in the contract's sense (docs:69-71), but
   a systematic transport-level fault (wrong container, shadowed DB path)
   could satisfy both; the failure direction remains safe (a fooled verify
   can only keep the run failing → breaker).

**Verdict 2: OK** — the required post-delisting confirmation exists, is
independent, read-only, and gates the durable flag; bounded retry and
failure semantics are contract-pinned. One MEDIUM residual (relist
asymmetry) and two LOW notes above.

## Finding 3 — Fail-safe on absence, garbage, staleness — severity: **OK** (staleness GUARDED since b879354; residuals: LOW)

Every branch that can reach a delist runs through
`fire = args.delist or dec["fire"]` (routstr_delist.py:649), where
`dec["fire"] = bool(accel or var or override)` (:317). Enumerated:

- **Absence — OK.** No `--preds` → `raw_preds=[]`, quiet run;
  acceleration requires non-empty preds on BOTH sides (:107), variance
  requires non-empty preds (:143); first run without a stored baseline can
  never fire acceleration (pinned contract:308-314). Manual override
  remains available by design.
- **Garbage — OK.** `_read_preds` never raises, drops non-dict entries
  (routstr_delist.py:479) and returns [] on any parse failure (:481-482).
  An explicitly requested but unusable feed is a FEED ERROR
  (`preds_error`, :585) with rc=1 when nothing fired (:660); the stored
  baseline is never wiped — `update_state` only overwrites the snapshot
  when preds is non-empty (:261-262), pinned tests:547-562 (probe this
  pass reproduced it: garbage feed → rc 1, `preds_error` true, snapshot
  intact). Type-guards: `uncertainty` is isinstance-guarded with bool
  explicitly excluded (:152-153) — pinned tests:146-151; probe this pass:
  string and bool uncertainty → [], no crash — and `exhausts_in_hours`
  is isinstance-guarded (:193-196). Precision note: a feed that is both
  garbage AND stale surfaces as `preds_error` (raw_preds is empty at :589
  so `preds_stale` cannot also be set); both exit 1.
- **Stale — OK; was the HIGH hole, now GUARDED.** `STALENESS_S = 1800`
  (:78); `feed_is_stale` is mtime-based and fails safe in direction —
  undeterminable age (OSError, missing file) returns True
  (routstr_delist.py:485-496; probe this pass: missing path → True,
  future mtime → True, fresh file → False), and a future mtime (negative
  age) is treated as stale (:494). Wiring: a stale feed zeroes the preds
  BEFORE trigger evaluation (:589-592), so the level-based variance
  trigger can never fire on dead data, and BEFORE any baseline refresh
  (snapshot preserved, pinned tests:995-1006). `preds_stale` is surfaced
  in every output branch (:657, :714, :735, :762) with rc=1 when quiet
  (:660). The manual override is deliberately never gated on freshness
  (:580 order, docs:60; pinned tests:980-993 and contract:427-433 —
  stale feed + `--manual` delists, `preds_stale: true` observed but not
  obeyed). Full pin set: tests:928-1006.
- **Breaker interaction (cross-ref finding 6)** — repeated failed runs
  refuse ALL further remote action (routstr_delist.py:724-731, :569-578,
  exit 3) until `--unblock` (:561-567); dry-run never counts toward it
  (:699-717, tests:514-530).

Residuals (LOW):

- **(a) `--preds-key` scoping is opt-in, default unscoped.** Filtering
  happens only when the flag is passed (routstr_delist.py:594-597);
  `evaluate_triggers` itself still passes no `key` to `variance_jumped`
  (:303) although the parameter exists for that purpose (:132, :147).
  Probe this pass (deployed bot copy, dry-run): an openrouter-only feed
  with `uncertainty 0.95` and NO `--preds-key` → `fire=True`, action
  delist; the same feed with `--preds-key zai` → action none. Scoping is
  wired at the CLI, documented (docs:54-55), and carried in the runbook
  cron example (docs:106); the residual is operator-omission risk on a
  deployment that is not yet wired (zero routstr crontab entries live
  this pass). Caveat: docs:54-55 states the guarantee unconditionally
  ("another provider's variance spike can never pull the routstr SALE") —
  the doc should say "with `--preds-key`".
- **(b) mtime-only freshness** (routstr_delist.py:485-494): a writer that
  rewrites `preds.json` with OLD data refreshes the mtime and bypasses
  the guard (content-stale / mtime-fresh is undetectable). The contract
  accepts mtime (docs:57); an embedded `generated_at` check would be
  stronger.
- **(c) Cosmetic**: `_hours` accepts bool (:193-196, probe this pass:
  `True` returned as-is) while the variance guard excludes it (:152-153)
  — arithmetic-safe, no crash path; the override marker is presence-based
  with no TTL (:164-172) — operator-controlled, by design (prior-pass
  note, unchanged).
- **(d) Cross-ref finding 4**: the quiet-run state write (:654), like all
  8 `save_state` call sites, ignores the return value.

**Verdict 3: OK** — absence safe, garbage safe (incl. the type-guard),
staleness guarded with fail-safe direction and full test pinning; residuals
LOW as itemized.

---

Provenance: eighth offload pass for findings 1–3. Prior passes (seventh-pass
file at this path; Gate 2.5 cold review `docs/reviews/
routstr_delist_review.md`; commits 69d489c, 11e40f9, 1188dc1, 6841f93,
4ae83d1, 5be0b99, 244b4ba) correctly found Finding 2 REFUTED-HIGH (no
re-fetch) and Finding 3 PARTIAL-HIGH (no freshness guard) against the
pre-fix 602-line script, then re-adjudicated both OK against the current
829-line artifacts after the round-2 fixes (repo commits b879354 + 1c77910).
This pass independently re-derives the same verdicts against unchanged
artifacts: script read end-to-end in both copies (byte-identical, 829
lines), contract suite read end-to-end (752 lines) and executed against the
deployed copy, cited main-suite sections read directly (all pin ranges above
sighted this pass), write-path inventories re-run by grep (open/SQL/
subprocess/shell=True/eval-exec/os.*; all counts cited above), 5 hermetic
probes executed on the deployed copy (staleness fail-safe ×3 states,
type-guards, verify payload read-only, unscoped cross-key fire vs scoped,
garbage-feed baseline preservation), suites 121 + 25 green, `crontab -l`
re-checked (zero routstr entries). Verdicts unchanged: 1 OK (gaps LOW),
2 OK (MEDIUM relist-asymmetry residual), 3 OK (LOW residuals). Artifact-path
report unchanged where it matters: the contract md is STILL MISSING at the
bot path (HIGH), and the bot's `routstr-delist.md` copy is 14 lines stale
(missing repo docs:177-190). Artifacts untouched; `~/.hermes/bot` is not a
git repository (re-verified this pass, `git rev-parse` rc=128), so the
required local commit lands in the workspace repo (merchant-routing) at
`docs/reviews/findings_1_3.md`, with this identical copy at the
task-mandated bot path `~/.hermes/bot/docs/reviews/findings_1_3.md`.
