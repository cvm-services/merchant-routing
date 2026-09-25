# Offload review — routstr delist, finding 8 (test rigour)

Third independent analysis pass for finding 8 (2026-09-25). Scope: original
task item 8 — test rigour: would the existing tests catch a broken
implementation, and what do they fail to pin? The artifact set CHANGED since
the second pass (2026-09-17): the script grew 602 → 829 lines (round-2
fixes), the bot tests path now EXISTS (second pass reported it missing) with
the 25-case TDD contract suite, and the repo grew a 96-test main suite that
is NOT deployed at the bot path. Nothing is carried over unverified: this
session re-read the deployed script end-to-end (829 lines) and the deployed
suite end-to-end (752 lines), confirmed both byte-identical to their repo
counterparts (`diff -q` clean), read the contract stand-in
`docs/routstr-delist.md` (197 lines) end-to-end, re-ran both suites
(deployed contract suite on a hermetic /tmp copy of the exact bot bytes:
**25 passed in 0.26s**; repo full suite: **121 passed in 0.50s**), and
executed **seventeen hermetic mutation probes** on the /tmp copy (every
mutant's target string was verified to occur exactly once before patching;
two further gap classes are proven by programmatic zero-hit counts;
/tmp copy destroyed after the run; no artifact touched, no network).

**Artifact-path status (required report per task instructions):**

- `~/.hermes/bot/docs/routstr_delist_contract.md` — **MISSING — HIGH**
  (third consecutive pass; `find ~/.hermes/bot -iname '*contract*'` → zero
  hits this session). The contract role is filled by repo
  `docs/routstr-delist.md` — cited by the script itself at
  routstr_delist.py:21 — read end-to-end as the stand-in. Note the bot's
  own copy of the stand-in (`~/.hermes/bot/docs/routstr-delist.md`) is 14
  changed lines STALE vs the repo copy.
- `~/.hermes/bot/scripts/routstr_delist.py` — present (829 lines), verified
  byte-identical to repo `src/routstr_delist.py` this session.
- `~/.hermes/bot/tests/test_routstr_delist.py` — present (752 lines),
  verified byte-identical to repo `tests/test_routstr_delist_contract.py`;
  its loader (tests:47-54) resolves `../src` first, `../scripts` second, so
  the bot copy runs against the deployed script. IMPORTANT: the bot path
  deploys ONLY this 25-case contract suite — the 96-test repo main suite
  (`tests/test_routstr_delist.py`, 1172 lines) is not deployed there.

Conventions: `routstr_delist.py:N` = the script (both copies identical);
`tests:N` = the bot-deployed contract suite (752 lines); `main:N` = repo
main suite `tests/test_routstr_delist.py` (1172 lines, NOT deployed);
`docs:N` = repo `docs/routstr-delist.md`.

## Finding 8 — test rigour — **MEDIUM (decision core strongly pinned by payload-executing fakes; production backend result computation and deadline clamp never executed, and eight contract hard rules are pinned only in the non-deployed main suite)**

Suite facts re-measured this session: **25 tests, 11 classes** (one per
required case), hermetic as claimed: the FakeSellNode is a named
shared-cache in-memory sqlite (tests:114-121) that EXECUTES the script's
real payload builders (tests:175-190) instead of shelling out; `rd.time` is
swapped for a FakeTime whose wall clock stays REAL so the mtime freshness
guard sees just-written fixture feeds as fresh (tests:27-29, 71-89); fsync
is no-op'd with a documented host-stall justification (tests:252-257,
629-634). No test touches the network.

Method: mutation analysis on a pristine /tmp copy of the exact deployed
bytes. A **gap-probe** is a production-code mutant that yields 25/25 if a
pin is missing; a **control** must be caught. Results this session:

| id | mutant (production code) | result | verdict |
|----|--------------------------|--------|---------|
| G1 | `_run` ok-gate `rc==0 and data ok` → forced `True` (routstr_delist.py:822) | 25/25 green | gap CONFIRMED |
| G2 | last-line stdout parse → `[0]` (routstr_delist.py:814) | 25/25 green | gap CONFIRMED |
| G3 | `_run` deadline clamp block deleted (routstr_delist.py:801-806) | 25/25 green | gap CONFIRMED |
| G4 | blanket-relist refusal bypassed `if False:` (routstr_delist.py:602) | 25/25 green | gap CONFIRMED |
| G5 | stale-feed zeroing dropped (routstr_delist.py:591-592) | 25/25 green | gap CONFIRMED |
| G6 | re-delist `pulled_models` clobber (routstr_delist.py:746) | 1 failed | caught by tests:524-538 (merge preserved) |
| G7 | verify `count == 0` gate dropped (routstr_delist.py:683) | 1 failed | caught by tests:346-360 (lying pull refuted) |
| G8 | variance `>` → `>=` (routstr_delist.py:154) | 1 failed | caught by tests:379-387 (0.30 exact is quiet) |
| G9 | acceleration `>=` → `>` boundary (routstr_delist.py:121) | 25/25 green | gap CONFIRMED |
| G10 | `manual_override` `isfile` → `exists` (routstr_delist.py:172) | 25/25 green | gap CONFIRMED |
| G11 | `load_state` non-dict guard dropped (routstr_delist.py:216) | 25/25 green | gap CONFIRMED |
| G12 | CLI `--move-hours`/`--variance` wiring swapped (routstr_delist.py:647-648) | 1 failed | caught (swapped DEFAULTS break tests:364-377) |
| G13 | event content `delisted` hardwired `True` (routstr_delist.py:440) | 25/25 green | gap CONFIRMED |
| G14 | dry-run flips durable `delisted` flag (routstr_delist.py:705) | 1 failed | caught by tests:731-744 (dry-run purity) |
| G15 | `MAX_PULL_ATTEMPTS` 2 → 3 (routstr_delist.py:75) | 2 failed | caught by tests:346-360 + 582-599 (exact kind counts) |
| G16 | `--preds-key` filter dropped (routstr_delist.py:597) | 1 failed | caught by tests:389-399 (scoping) |
| G17 | failed relist returns 0 (routstr_delist.py:630-632) | 25/25 green | gap CONFIRMED |

Two further gap classes are proven WITHOUT a run by programmatic zero-hit
counts in the deployed suite: `--status` (0 occurrences → any --status
mutant is green) and explicit `--move-hours`/`--variance` values (0
occurrences → a mutant that ignores explicitly-passed thresholds and uses
defaults is green; G12 shows only the DEFAULT plumbing is pinned).

**Strongly pinned — OK (7/7 catchable mutants caught; "mentally break it
and tests fail"):**

1. **Re-fetch confirmation — OK.** The suite's standout: FakeSellNode can
   simulate a LYING pull (rc 0, ok printed, UPDATE never lands,
   tests:101-104, 177-189) and only the independent read-only re-fetch
   refutes it — G7 proves the `count == 0` gate (routstr_delist.py:683) is
   load-bearing, with exact round-trip sequence `[pull, verify, pull,
   verify]` (tests:357).
2. **SALE-vs-provider scoping — OK, now at executed-SQL level.** Real
   payloads run against a schema with BOTH `models` and
   `upstream_providers` (tests:107-135); the ladder artifact is asserted
   byte-identical and the providers table row-identical across a delist
   (tests:469-488), and the scoped relist provably restores exactly the
   advertised names while operator-disabled rows stay disabled
   (tests:490-507). This is stronger than the old suite's substring pins.
3. **Multi-run semantics — OK.** Re-delist merge no-clobber
   (routstr_delist.py:744-746; G6 via tests:524-538 — the second pass's
   M12 gap is closed in the deployed suite), debounce via baseline
   consumption (tests:437-464), idempotent quiet re-run (tests:512-522).
4. **Retry/breaker accounting — OK.** `MAX_PULL_ATTEMPTS` pinned by exact
   kind counts: 2 round-trips per refuted run (tests:357), 6 pulls across
   3 failing runs with verify never reached (tests:599); exit sequence
   `[1, 1, 3]`, durable `"blocked": true` marker, blocked-refusal with
   zero remote calls, `--unblock` recovery (tests:582-624).
5. **Trigger edges — OK.** Variance strictly-greater (G8, tests:379-387),
   first-run false-positive guard (tests:308-314), `--preds-key` scoping
   (G16, tests:389-399).
6. **Dry-run purity — OK.** No subprocess, no durable flag, pre-existing
   flag survives (G14, tests:731-752).
7. **Atomic-write protocol — OK.** Swap-instant observation (old state
   intact at dst, complete new state in tmp, exactly one replace) and
   crash-between-tmp-and-replace simulation (tests:636-686).
8. **Secret hygiene — OK.** Env-only transport asserted end-to-end: secret
   never in argv/logs/state, `--env-sec` present, `--sec` absent, kind
   30078 and `d:routstr-delist` on the argv (tests:705-729).

**Gaps (numbered for should-fix; each dynamically probed or statically
zero-hit-proven this session):**

1. **Production `_SshBackend._run` never executed by the deployed suite —
   MEDIUM (largest; the second pass's M1/M2 gap persists in the deployed
   rig).** The Rig replaces `rd._SshBackend` wholesale (tests:249-250) with
   `_NodeBackend`, which REIMPLEMENTS the production result semantics: the
   last-line JSON parse at tests:190 mirrors routstr_delist.py:814, the
   ok-gate at tests:237 mirrors routstr_delist.py:822, the deadline clamp
   at tests:225 mirrors routstr_delist.py:800-806. Mutants G1 (ok forced
   True), G2 (first-line parse), G3 (clamp deleted) are all 25/25 green —
   every real-world delist/relist success decision flows through exactly
   this dead-to-the-suite code, and a mock that mirrors production
   semantics cannot detect production drift. The repo main suite closed
   the parse/ok-gate half (main:1100-1145 — the class docstring literally
   cites this review's prior "mock-only gap"), but that suite is not
   deployed at the bot path.
2. **Backend deadline clamp unpinned ANYWHERE — MEDIUM (cross-ref finding
   5).** G3's target (routstr_delist.py:800-806: `timeout =
   min(SSH_TIMEOUT_S, remaining)` and the "action budget exhausted"
   early-return at :803-805) is dead code to BOTH suites: the deployed
   suite never runs `_run` at all, and main's real-backend tests call
   `pull()`/`verify()` with NO deadline (main:1107-1144) while main's
   deadline test exercises main()'s retry-cap consumption through a FAKE
   backend (main:450-463). No test captures the `timeout` kwarg handed to
   `subprocess.run` (routstr_delist.py:808-809). A dropped clamp lets a
   hung ssh burn up to SSH_TIMEOUT_S=30 s past the action budget — the
   exact zero-slack boundary finding 5 already flagged.
3. **Eight contract hard rules pinned only in the non-deployed main suite —
   MEDIUM (deployment asymmetry).** Each is a documented hard rule
   (docs:27-36, 56-60, 76-83) that stays 25/25 green at the bot path:
   blanket-relist refusal (routstr_delist.py:602-611; G4 — deployed suite's
   only `--relist` use is the success path, tests:496; main pins refusal ×3
   + `--relist-any` ×5); stale-feed zeroing (routstr_delist.py:589-592; G5
   — deployed suite proves only the INVERSE, that manual override ignores
   staleness, tests:427-433; main pins stale-blocks-triggers ×8);
   failed-relist exit 1 + state honesty (routstr_delist.py:626-632; G17;
   main:538-545); relist-event content `delisted: false`
   (routstr_delist.py:440; G13 — deployed Case 11 asserts argv shape but
   never the `--content` payload; main:408-416); `--status` key set
   (routstr_delist.py:548-557; static zero-hit; main:679, 740-742);
   explicit `--move-hours`/`--variance` values (static zero-hit; main:
   755-773); acceleration boundary inclusivity (routstr_delist.py:121; G9;
   main:97-100); `load_state` non-dict guard (routstr_delist.py:216; G11;
   main:266-271). Net effect: docs:187-189 presents the bot-path copies as
   the deployed verification rig, yet an operator running only the bot
   tests gets 25/25 green with any of these eight broken.
4. **Marker-as-directory unpinned repo-wide — LOW (second pass's F1, still
   open both suites).** G10: `isfile` → `exists`
   (routstr_delist.py:172) is green; `isdir` has ZERO hits in either
   suite. A stray directory at the override path silently arms a permanent
   manual delist and nothing fails.
5. **fsync call-presence unpinned repo-wide — LOW (new this pass).** Both
   contract-suite fixtures no-op `os.fsync` without observing calls
   (tests:257, 634), and the main suite contains zero `fsync` references
   at all — so deleting the `os.fsync(fh.fileno())` call
   (routstr_delist.py:234) is green everywhere. The ATOMICITY half of the
   docs:80-83 claim is genuinely pinned (tests:636-686), but its
   durability half rests on code no test observes executing.

**Acceptable hermetic choices (not gaps):** wall time deliberately left
real under FakeTime so the mtime freshness guard works (tests:27-29);
in-memory shared-cache sqlite instead of file-backed (tests:114-121 —
file-sqlite lock acquisition can stall indefinitely on this fleet host,
a real constraint this session's prior passes hit); `subprocess` mocked
only where nak would spawn (tests:694-703); FakeTime's monotonic-only
patch keeping SLA tests deterministic (tests:71-89).

**Overall verdict: MEDIUM.** The deployed 25-case contract suite is a
major rigour upgrade over the 55-test suite the earlier passes reviewed:
it executes the real payloads against a real two-table schema, observes
actual SQL effects, refutes lying pulls, asserts ladder byte-identity,
and pins retry/breaker/dry-run/atomic-write semantics exactly (7/7
catchable mutants caught; even CLI default wiring is implicitly pinned —
G12). The residual is concentrated and enumerable: the production
backend's own result computation and clamp (gaps 1-2 — three probes),
eight hard rules reachable only via the non-deployed main suite (gap 3),
and two repo-wide weak pins (gaps 4-5). No gap endangers the
SALE-vs-provider distinction itself. Artifact status partially healed
since the second pass (bot tests path now exists, contract suite
deployed); the contract md remains missing (HIGH above).

**Should-fix (non-blocking, maps 1:1 to the numbered gaps):** (1) deploy
the main suite alongside the contract suite at the bot path (or fold
`TestRealBackendRun` into the deployed copy) so a bot-path green run
certifies what docs:187-189 implies; (2) one mocked-`subprocess.run`
test asserting `_run`'s `timeout=min(SSH_TIMEOUT_S, remaining)` clamp and
budget-exhausted early-return; (3) extend the deployed suite with the
eight gap-3 cases (refusal, stale-blocks-triggers, failed-relist rc,
relist-event content, --status keys, explicit thresholds, accel boundary,
non-dict state); (4) tmpdir-as-marker negative test for
`manual_override`; (5) assert the (faked) fsync is called in Case 10.
