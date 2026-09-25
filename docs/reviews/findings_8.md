# Offload review — routstr delist, finding 8 (test rigour)

Fourth independent analysis pass for finding 8 (2026-09-25). Scope: original
task item 8 — test rigour: would the existing tests catch a broken
implementation, and what do they fail to pin? The artifact set is UNCHANGED
since the round-2 deployment commit (1c77910, 2026-09-25 01:11): this session
re-verified the deployed script and suite byte-identical to their repo
counterparts before review, so this pass is an independent re-derivation of
the third pass's catalogue — nothing carried over unverified. The deployed
script was re-read end-to-end (829 lines), the deployed suite end-to-end
(752 lines), the contract stand-in `docs/routstr-delist.md` (197 lines)
end-to-end, and all main-suite cross-references were re-opened at their
cited lines. Both suites were re-run (deployed contract suite on a hermetic
/tmp copy of the exact bot bytes: **25 passed in ~0.3 s**; repo full suite:
**121 passed**), and **twenty-four hermetic mutation probes** were executed
on the /tmp copy (every mutant's target string was verified to occur exactly
once before patching; the rig was destroyed after the run; no artifact
touched, no network).

**Artifact-path status (required report per task instructions):**

- `~/.hermes/bot/docs/routstr_delist_contract.md` — **MISSING — HIGH**
  (fourth consecutive pass; `find ~/.hermes/bot -iname '*contract*'` → zero
  hits this session; no such file exists anywhere in the repo either). The
  contract role is filled by repo `docs/routstr-delist.md` — cited by the
  script itself at routstr_delist.py:21 — read end-to-end as the stand-in.
  The bot's own copy of the stand-in (`~/.hermes/bot/docs/routstr-delist.md`)
  remains STALE: exactly the 14-line paragraph describing the TDD contract
  suite is missing (diff hunk 176a177,190) — i.e. the bot copy lacks the very
  paragraph that documents the suite under review here.
- `~/.hermes/bot/scripts/routstr_delist.py` — present (829 lines, md5
  2ea724ef08d857cd7b88a957300e70b4), verified byte-identical to repo
  `src/routstr_delist.py` this session.
- `~/.hermes/bot/tests/test_routstr_delist.py` — present (752 lines, md5
  031851b356f0de4089512f02f13f05cc), verified byte-identical to repo
  `tests/test_routstr_delist_contract.py`. Its loader (tests:47-54) resolves
  `../src` first, `../scripts` second; `~/.hermes/bot/src/` contains no
  routstr_delist.py (verified), so the bot copy runs against the deployed
  script. The bot path deploys ONLY this 25-case contract suite — the
  96-test repo main suite (`tests/test_routstr_delist.py`, 1172 lines) is
  not deployed there.

Conventions: `routstr_delist.py:N` = the script (both copies identical);
`tests:N` = the bot-deployed contract suite (752 lines); `main:N` = repo
main suite `tests/test_routstr_delist.py` (1172 lines, NOT deployed);
`docs:N` = repo `docs/routstr-delist.md`.

## Finding 8 — test rigour — **MEDIUM (decision core strongly pinned by payload-executing fakes — 12/12 catchable mutants caught this pass; production backend result computation and deadline clamp still never executed anywhere, and TEN documented hard rules are pinned only in the non-deployed main suite, two of them newly identified this pass)**

Suite facts re-measured this session: **25 tests, 11 classes** (one per
required case), hermetic as claimed. The FakeSellNode is a named
shared-cache in-memory sqlite (tests:114-121) that EXECUTES the script's
real payload builders (tests:175-190) instead of shelling out; `rd.time` is
swapped for a FakeTime whose wall clock stays REAL so the mtime freshness
guard sees just-written fixture feeds as fresh (tests:27-29, 71-89); fsync
is no-op'd with a documented host-stall justification (tests:252-257,
629-634). No test touches the network. The deployed-suite load path was
re-confirmed end-to-end this session.

Method: mutation analysis on a pristine /tmp copy of the exact deployed
bytes. A **gap-probe** is a production-code mutant that yields 25/25 when a
pin is missing; a **control** must be caught. Twenty-four probes this pass:
eleven designed controls, ten gap-probes re-deriving the third pass's
catalogue, and three fresh probes targeting the breaker-reset /
baseline-preservation rules documented at docs:79 and docs:84-86.

| id | mutant (production code) | result | verdict |
|----|--------------------------|--------|---------|
| C1 | verify `count == 0` gate dropped (routstr_delist.py:683) | 1 failed | caught by tests:346-360 (lying pull refuted) |
| C2 | re-delist `pulled_models` clobber (routstr_delist.py:746) | 1 failed | caught by tests:524-538 (merge preserved) |
| C3 | variance `>` → `>=` (routstr_delist.py:154) | 1 failed | caught by tests:379-387 (0.30 exact is quiet) |
| C4 | CLI `--move-hours`/`--variance` DEFAULTS swapped (routstr_delist.py:516-518) | 22 failed | caught (variance default 2.0 silences tests:365-377 and cascades) |
| C5 | dry-run flips durable `delisted` flag (routstr_delist.py:703-705) | 1 failed | caught by tests:731-752 (dry-run purity) |
| C6 | `MAX_PULL_ATTEMPTS` 2 → 3 (routstr_delist.py:75) | 2 failed | caught by tests:346-360 + 582-599 (exact kind counts) |
| C7 | `--preds-key` filter dropped (routstr_delist.py:597) | 1 failed | caught by tests:389-399 (scoping) |
| C8 | `SSH_TIMEOUT_S` 30 → 60 (routstr_delist.py:74) — NEW control | 1 failed | caught by tests:543-551 (2×30 ≤ 60 arithmetic) |
| C9 | `STALENESS_S` 1800 → 99999 (routstr_delist.py:78) — NEW control | 1 failed | caught by tests:427-433 (`preds_stale` observed) |
| C10 | `DELIST_EVENT_KIND` 30078 → 30333 (routstr_delist.py:79) — NEW control | 1 failed | caught by tests:705-729 (kind on argv) |
| C11 | `BREAKER_THRESHOLD` 3 → 2 (routstr_delist.py:77) — NEW control | 1 failed | caught by tests:582-597 (rc sequence [1,1,3]) |
| K11 | delist-success breaker reset dropped (routstr_delist.py:750-751) — NEW probe, expected green | 2 failed | **caught — a pin the third pass did not list**: tests:538 and :624 access `st["consecutive_failures"]` directly, so dropping the write KeyErrors |
| G1 | `_run` ok-gate forced `True` (routstr_delist.py:822) | 25/25 green | gap CONFIRMED |
| G2 | last-line stdout parse → first line (routstr_delist.py:814) | 25/25 green | gap CONFIRMED |
| G3 | `_run` deadline clamp block deleted (routstr_delist.py:801-806) | 25/25 green | gap CONFIRMED |
| G4 | blanket-relist refusal bypassed `if False:` (routstr_delist.py:602) | 25/25 green | gap CONFIRMED |
| G5 | stale-feed zeroing dropped (routstr_delist.py:591-592) | 25/25 green | gap CONFIRMED |
| G9 | acceleration `>=` → `>` boundary (routstr_delist.py:121) | 25/25 green | gap CONFIRMED |
| G10 | `manual_override` `isfile` → `exists` (routstr_delist.py:172) | 25/25 green | gap CONFIRMED |
| G11 | `load_state` non-dict guard dropped (routstr_delist.py:216) | 25/25 green | gap CONFIRMED |
| G13 | event content `delisted` hardwired `True` (routstr_delist.py:440) | 25/25 green | gap CONFIRMED |
| G17 | failed relist returns 0 (routstr_delist.py:630-632) | 25/25 green | gap CONFIRMED |
| K12 | relist-success breaker clear dropped (routstr_delist.py:636-637) — **NEW gap** | 25/25 green | gap CONFIRMED (docs:79 "any confirmed success … resets") |
| K13 | `update_state` empty-preds snapshot guard dropped (routstr_delist.py:261-262) — **NEW gap** | 25/25 green | gap CONFIRMED (docs:84-86 "baseline is never wiped") |

Three further gap classes are proven WITHOUT a run by programmatic zero-hit
counts re-measured this session on the deployed suite: `--status` (0
occurrences), explicit `--move-hours`/`--variance` values (0 occurrences —
G12/C4 shows only the DEFAULT plumbing is pinned), and `--relist-any` /
`relist_refused` (0 occurrences each).

**Strongly pinned — OK (12/12 catchable mutants caught; "mentally break it
and the tests fail"):**

1. **Re-fetch confirmation — OK.** FakeSellNode simulates a LYING pull
   (rc 0, ok printed, UPDATE never lands; tests:101-104, 177-189) and only
   the independent read-only re-fetch refutes it — C1 proves the
   `count == 0` gate (routstr_delist.py:683) is load-bearing, with the
   exact round-trip sequence `[pull, verify, pull, verify]` (tests:357).
2. **SALE-vs-provider scoping — OK, at executed-SQL level.** Real payloads
   run against a schema with BOTH `models` and `upstream_providers` tables
   (tests:107-135); the ladder artifact is asserted byte-identical and the
   providers table row-identical across a delist (tests:469-488), and the
   scoped relist restores exactly the advertised names while
   operator-disabled rows stay disabled (tests:490-507).
3. **Multi-run semantics — OK.** Re-delist merge no-clobber
   (routstr_delist.py:744-746; C2 via tests:524-538), debounce via baseline
   consumption (tests:437-464), idempotent quiet re-run (tests:512-522).
4. **Retry/breaker accounting — OK.** `MAX_PULL_ATTEMPTS` pinned by exact
   kind counts (C6; tests:357, 599), threshold VALUE pinned by the rc
   sequence (C11; tests:591), blocked-refusal with zero remote calls
   (tests:601-612), `--unblock` recovery (tests:614-624), and — newly
   proven this pass (K11) — the delist-success breaker reset
   (routstr_delist.py:750-751) is pinned at key-presence level by the two
   direct `st["consecutive_failures"]` reads (tests:538, :624).
5. **Trigger edges and constants — OK.** Variance strictly-greater (C3,
   tests:379-387), first-run false-positive guard (tests:308-314),
   `--preds-key` scoping (C7, tests:389-399), staleness constant C9
   (tests:427-433), SLA arithmetic C8 (tests:543-551).
6. **Dry-run purity — OK.** No subprocess, no durable flag, pre-existing
   flag survives (C5, tests:731-752).
7. **Atomic-write protocol — OK.** Swap-instant observation and
   crash-between-tmp-and-replace simulation (tests:636-686).
8. **Secret hygiene — OK.** Env-only transport asserted end-to-end:
   secret never in argv/logs/state, `--env-sec` present, `--sec` absent,
   kind 30078 (C10) and `d:routstr-delist` on the argv (tests:705-729).

**Gaps (numbered for should-fix; each dynamically probed or statically
zero-hit-proven this session):**

1. **Production `_SshBackend._run` never executed by the deployed suite —
   MEDIUM.** The Rig replaces `rd._SshBackend` wholesale (tests:249-250)
   with `_NodeBackend`, which REIMPLEMENTS the production result
   semantics: last-line JSON parse at tests:190 mirrors
   routstr_delist.py:814, the ok-gate at tests:237 mirrors
   routstr_delist.py:822, the clamp view at tests:219-226 mirrors
   routstr_delist.py:800-806. Mutants G1 (ok forced True), G2 (first-line
   parse), G3 (clamp deleted) are all 25/25 green — every real-world
   delist/relist success decision flows through exactly this
   dead-to-the-suite code, and a mock that mirrors production semantics
   cannot detect production drift. The repo main suite closed the
   parse/ok-gate half (main:1100-1147 — the class docstring cites this
   review lineage), but that suite is not deployed at the bot path.
2. **Backend deadline clamp unpinned ANYWHERE — MEDIUM (cross-ref finding
   5).** G3's target (routstr_delist.py:801-806: `timeout =
   min(SSH_TIMEOUT_S, remaining)` and the budget-exhausted early-return)
   is dead code to BOTH suites: the deployed suite never runs `_run` at
   all, and main's only `timeout` references are the constant-arithmetic
   assertion (main:430), a FakeBackend error string (main:610), and a
   TimeoutExpired-exception test (main:1148) — no test inspects the
   `timeout=` kwarg handed to `subprocess.run` (routstr_delist.py:808-809;
   main's real-backend tests at main:1110/1119/1126/1134/1141 mock
   `subprocess.run` with bare `return_value=`). A dropped clamp lets a
   hung ssh burn up to SSH_TIMEOUT_S=30 s past the action budget.
3. **TEN contract hard rules pinned only in the non-deployed main suite —
   MEDIUM (deployment asymmetry; two NEW this pass).** Each is a
   documented hard rule that stays 25/25 green at the bot path:
   blanket-relist refusal (routstr_delist.py:602-611; G4 — the deployed
   suite's only `--relist` use is the success path, tests:496; main pins
   refusal plus `--relist-any` opt-in); stale-feed zeroing
   (routstr_delist.py:589-592; G5 — the deployed suite proves only the
   INVERSE, that manual override ignores staleness, tests:427-433; main
   pins stale-blocks-triggers at main:937-995); failed-relist exit 1 +
   state honesty (routstr_delist.py:626-632; G17; main:536-545);
   relist-event content `delisted: false` (routstr_delist.py:440-441;
   G13 — deployed Case 11 asserts argv shape but never the `--content`
   payload; main:406-416); `--status` key set (routstr_delist.py:548-557;
   static zero-hit; main:678-681); explicit `--move-hours`/`--variance`
   values (static zero-hit; main:753-774); acceleration boundary
   inclusivity (routstr_delist.py:121; G9; main:97-100); `load_state`
   non-dict guard (routstr_delist.py:216; G11; main:266-271); **NEW —
   relist-success breaker clear** (routstr_delist.py:636-637; K12 —
   docs:79 "Any confirmed success (delist or relist) resets the counter";
   the deployed suite's single relist test runs from clean state, and the
   delist-half pin (K11 caught) does not cover the relist branch;
   main:909-924); **NEW — empty/stale feed never wipes the stored
   baseline** (routstr_delist.py:261-262; K13 — docs:84-86; the deployed
   suite never re-reads the snapshot after a preds-empty save;
   main:243-247 and main:995). One further static-only observation in the
   same class: the staleness boundary inclusivity (`0 <= age <=
   STALENESS_S`, routstr_delist.py:494) — the deployed suite ages feeds
   only by 3600 s vs the 1800 s threshold (tests:264-267, :428), so an
   off-by-one at the boundary is green; main:968 pins it. Net effect:
   docs:187-189 presents the bot-path copies as the deployed verification
   rig, yet an operator running only the bot tests gets 25/25 green with
   any of these ten broken.
4. **Marker-as-directory unpinned repo-wide — LOW.** G10: `isfile` →
   `exists` (routstr_delist.py:172) is green; `isdir` has ZERO hits in
   either suite (re-measured: 0 in deployed, 0 in main). A stray directory
   at the override path silently arms a permanent manual delist and
   nothing fails.
5. **fsync call-presence unpinned repo-wide — LOW.** Both contract-suite
   fixtures no-op `os.fsync` without observing calls (tests:257, :634),
   and the main suite contains ZERO `fsync` references (re-measured this
   session) — deleting the `os.fsync(fh.fileno())` call
   (routstr_delist.py:234) is green everywhere. The ATOMICITY half of the
   docs:80-83 claim is genuinely pinned (tests:636-686); its durability
   half rests on code no test observes executing. (Related LOW, finding-6
   cross-ref: `main()` ignores `save_state`'s return at all eight call
   sites — routstr_delist.py:565, :622, :629, :638, :654, :710, :732,
   :752 — and no test forces a failed write on a `main()` path.)

**Acceptable hermetic choices (not gaps):** wall time deliberately left
real under FakeTime so the mtime freshness guard works (tests:27-29);
named in-memory shared-cache sqlite instead of file-backed (tests:114-121 —
file-sqlite lock acquisition can stall indefinitely on this fleet host, a
constraint prior passes hit for real); `subprocess` mocked only where nak
would spawn (tests:694-703); FakeTime's monotonic-only patch keeping SLA
tests deterministic (tests:71-89).

**Overall verdict: MEDIUM (unchanged from the third pass — the artifact
set is unchanged, and this pass's 24 probes independently re-derive the
same shape with two refinements).** The deployed 25-case contract suite
executes the real payloads against a real two-table schema, observes
actual SQL effects, refutes lying pulls, asserts ladder byte-identity, and
pins retry/breaker/dry-run/atomic-write/secret-hygiene semantics exactly
(12/12 catchable mutants caught this pass, including four fresh constant
controls and the newly-proven delist-success breaker reset). The residual
is concentrated and enumerable: the production backend's own result
computation and clamp (gaps 1-2 — three probes), TEN hard rules reachable
only via the non-deployed main suite (gap 3 — eight re-confirmed plus two
new: relist-success breaker clear K12, empty-preds baseline preservation
K13), and two repo-wide weak pins (gaps 4-5). No gap endangers the
SALE-vs-provider distinction itself. Artifact status unchanged since the
third pass: contract md still missing at the bot path (HIGH, 4th pass),
bot stand-in doc still 14 lines stale.

**Should-fix (non-blocking, maps 1:1 to the numbered gaps):** (1) deploy
the main suite alongside the contract suite at the bot path (or fold
`TestRealBackendRun`, main:1100-1147, into the deployed copy) so a
bot-path green run certifies what docs:187-189 implies; (2) one
mocked-`subprocess.run` test asserting `_run`'s
`timeout=min(SSH_TIMEOUT_S, remaining)` clamp and budget-exhausted
early-return (routstr_delist.py:801-806); (3) extend the deployed suite
with the ten gap-3 cases (refusal, stale-blocks-triggers, failed-relist
rc, relist-event content, --status keys, explicit thresholds, accel
boundary, non-dict state, relist-success breaker clear, empty-preds
baseline preservation — plus the at-boundary staleness case); (4)
tmpdir-as-marker negative test for `manual_override`; (5) assert the
(faked) fsync is called in Case 10.
