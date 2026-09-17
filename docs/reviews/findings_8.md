# Offload review — routstr delist, finding 8 (test rigour)

First independent analysis pass for finding 8 (2026-09-17 night). Scope:
original task item 8 — test rigour: would the existing tests catch a broken
implementation, and what do they fail to pin? Nothing below is carried over
unverified: this session read the script end-to-end (602 lines) in both copies
(`diff -q`: byte-identical), the tests end-to-end (546 lines) and the contract
stand-in `docs/routstr-delist.md` (129 lines), re-ran every grep
programmatically, re-ran the suite under both runners
(`python3 -m pytest tests/ -q` → **55 passed in 0.24s**;
`python3 -m unittest discover -s tests` → **Ran 55 tests in 0.022s, OK**),
and executed **ten hermetic mutation probes** on a /tmp copy of src+tests
(six gap-probes + four positive controls; no artifact touched, no network).

**Artifact-path status (required report per task instructions):**

- `~/.hermes/bot/docs/routstr_delist_contract.md` — **MISSING — HIGH**
  (re-verified this session: `~/.hermes/bot/docs/` contains only `reviews/`;
  no `*contract*` file under `~/.hermes/bot`). The contract role is filled by
  repo `docs/routstr-delist.md` — cited by the script itself at
  routstr_delist.py:21 — read end-to-end as the stand-in.
- `~/.hermes/bot/tests/test_routstr_delist.py` — **MISSING — HIGH** (no
  `tests/` directory exists under `~/.hermes/bot`; checked this session).
  Repo counterpart `tests/test_routstr_delist.py` (546 lines, 55 tests) read
  end-to-end and reviewed instead.
- `~/.hermes/bot/scripts/routstr_delist.py` — present (602 lines), verified
  byte-identical to repo `src/routstr_delist.py` this session (`diff -q`
  clean).

Conventions: `routstr_delist.py:N` = the script (both copies identical);
`tests:N` = repo tests; `docs:N` = repo `docs/routstr-delist.md`.

## Finding 8 — test rigour — **MEDIUM (decision core strong; production result-computation and multi-run semantics unpinned)**

Suite facts re-measured this session: **55 tests, 12 classes** (the original
cold review's "13 classes" is an erratum; `grep -c '^class Test'` = 12),
hermetic as claimed (tests:3-6): every remote path is either faked
(`FakeBackend` tests:32-46), monkeypatched (`mock.patch.object(rd,
"_SshBackend", ...)` at tests:360, 385, 417, 423, 437, 448), or driven only
through the dry-run early-return (routstr_delist.py:578-580). All state lives
in tmpdirs; no test touches the network.

Method: mutation analysis on a pristine /tmp copy. A **gap-probe** is a
production-code mutant that should still yield 55/55 if a coverage claim is
real; a **control** is a mutant the suite must catch, proving the harness
detects regressions where tests are strong. Results:

| id | mutant (production code) | result | verdict |
|----|--------------------------|--------|---------|
| M1 | `res["ok"] = proc.returncode == 0 and data.get("ok") is True` → forced `True` (routstr_delist.py:595) | 55/55 green | gap CONFIRMED |
| M2 | last-line stdout parse `out.splitlines()[-1]` → `[0]` (routstr_delist.py:587) | 55/55 green | gap CONFIRMED |
| M3 | event `content` hardcodes `"delisted": True`, ignoring the parameter (routstr_delist.py:391) | 55/55 green | gap CONFIRMED |
| M7 | `--status` drops `ts`/`last_reason`/`pulled_models`/`snapshot_windows` keys (routstr_delist.py:473-479) | 55/55 green | gap CONFIRMED |
| M8 | CLI `--move-hours`/`--variance` wiring swapped at the `evaluate_triggers` call (routstr_delist.py:512-514) | 55/55 green | gap CONFIRMED |
| M12 | finding-4 `pulled_models` clobber (routstr_delist.py:543) replaced by a preserve-fix | 55/55 green | gap CONFIRMED |
| M4 | variance `unc > threshold` → `>=` (routstr_delist.py:137) | 1 failed | caught by `TestVarianceJump::test_threshold_is_strict` (tests:105-106) |
| M5 | acceleration `moved >= move_hours` → `>` (routstr_delist.py:106) | 1 failed | caught by `TestBurnAcceleration::test_threshold_is_inclusive` (tests:69-72) |
| M6 | `shlex.quote(payload)` dropped (routstr_delist.py:375) | 1 failed | caught by `test_ssh_cmd_is_single_shlex_safe_remote_command` (tests:262-275) |
| M10 | pull SQL drops `WHERE enabled=1` (routstr_delist.py:320) | 1 failed | caught by `test_pull_payload_scoped_to_models_table` (tests:244-251) |

**Strongly pinned (controls all caught, "mentally break it and tests fail"):**

- **Trigger logic — OK.** Direction inversion and both threshold edges
  (tests:59-72, 97-106), first-run false-positive guard (tests:136-141),
  per-key/window separation (tests:78-88), non-numeric `exhausts_in_hours`
  (tests:90-92), missing `uncertainty` (tests:113-116), legacy `|` and `\x1f`
  snapshot keys (tests:143-151, 178-190).
- **Failure semantics — OK.** Failed pull: rc==1, `delisted` stays false,
  `last_pull_error` recorded, baseline preserved and re-fires (tests:351-375);
  failed relist rc==1 (tests:377-390); corrupt feed: `preds_error` + baseline
  survives (tests:392-407); empty-preds baseline guard (tests:203-209).
- **Shell safety — OK.** shlex round-trip re-parse (tests:262-275).
- **SQL scoping — pinned at payload level.** The full
  `UPDATE models SET enabled=0 WHERE enabled=1` string is asserted inside the
  payload (tests:246), which is what caught M10; parameterized relist and
  no-interpolation are pinned (tests:252-257).

**Gaps (each probe-confirmed still-green; numbered for should-fix):**

1. **The production success/failure computation is entirely unpinned
   (MEDIUM — the largest gap).** The subprocess branch of
   `_SshBackend._run` (routstr_delist.py:581-598) is never executed by any
   test — every remote action is faked or dry-run. Consequently its two
   load-bearing behaviours mutate freely: the rc+payload ok-gate
   (routstr_delist.py:595, M1) and the last-line JSON parse
   (routstr_delist.py:587, M2) can be arbitrarily broken with the suite
   staying 55/55. Every real-world delist/relist success decision flows
   through exactly this code. Note the nuance vs the cold review's wording:
   the dry-run early-return (routstr_delist.py:578-580) IS exercised by ten
   main-path tests (`test_triggered_run_pulls_within_window`,
   `test_unreadable_preds_feed_is_error_not_quiet`,
   `test_status_prints_state`, `test_quiet_run_without_preds…`,
   `test_baseline_then_acceleration_fires`, `test_manual_marker_file_fires`,
   `test_delist_flag_forces_fire`, `test_relist_restores`,
   `test_missing_preds_file…`, `test_non_dict_preds…`) — it is the
   network/rc/parse branch that is dead to the suite. `main()`'s handling of
   an `ok:False` result IS tested (tests:351-375); what is unpinned is the
   computation of `ok` itself. A hermetic fix exists: mock
   `subprocess.run` and feed stdout/rc pairs into the real `_run`.
2. **Multi-run delist semantics unpinned (MEDIUM, feeds finding 4's HIGH).**
   No test performs two consecutive successful delists; M12 shows the
   `pulled_models` clobber (routstr_delist.py:543 → blanket-relist arming at
   routstr_delist.py:491) and its fix are indistinguishable to the suite
   (both 55/55). The scoped-relist round-trip (tests:412-428) has no second
   delist in the gap, and its `fb2.calls` assertion would pass even with the
   clobber in between. Add a delist→delist→relist test.
3. **Two tautological tests (LOW).** `test_window_constant_is_300`
   (tests:329-330) asserts a literal equals a literal;
   `TRIGGER_ACTION_WINDOW_S` has exactly one occurrence in the script (the
   definition, routstr_delist.py:63 — grep re-run this session), so no
   behaviour can attach to it and the test pins nothing behavioural.
   `test_event_content_reflects_relist` (tests:322-324) calls
   `build_delist_event("/nonexistent", delisted=False)`, which returns None
   at the missing-file guard (routstr_delist.py:388-389) before the
   `delisted` parameter is ever read — M3 proves the content parameter is
   unpinned. It is a duplicate of tests:302-303 under a misleading name.
4. **SLA test proves only absence of sleep (LOW, cross-ref finding 5).**
   `test_triggered_run_pulls_within_window` (tests:332-344) wall-clocks a
   dry-run main call; nothing in the script consumes
   `TRIGGER_ACTION_WINDOW_S`, so no test can fail while the ≤5-minute
   contract is violated in deployment.
5. **CLI threshold plumbing untested (LOW, M8).** No test passes
   `--move-hours` or `--variance` (grep: zero hits); swapped wiring at
   routstr_delist.py:512-514 stays green. The pure functions are tested with
   explicit thresholds, so the argparse→evaluate handoff is the blind spot.
6. **`--status` output contract weakly pinned (LOW, M7).**
   `test_status_prints_state` (tests:468-471) asserts only `"delisted" in
   out`; dropping four of the five printed keys
   (routstr_delist.py:473-479) stays green.
7. **Untested fail-safe input branches (LOW).** Non-numeric `uncertainty`
   (the TypeError path at routstr_delist.py:137 — every `unc=` literal in
   the tests is numeric; grep re-run); a well-formed empty-list feed `[]`
   via CLI (`_read_preds` returns [] at routstr_delist.py:429-431 →
   `preds_error` rc=1 at routstr_delist.py:487,524 — only corrupt
   (tests:392-407) and garbage-entry (tests:527-542) feeds are tested); a
   valid-JSON non-list feed (dict); the argparse rc=2 space.
8. **Constant-level SQL assertions are substring-only (LOW).**
   `test_pull_sql_touches_only_models_listing` (tests:229-235) checks
   `"models"` and `"enabled=0"` substrings — M10 shows a dropped `WHERE`
   escapes THAT test; it survives only because the payload-level pin
   (tests:246) embeds the same constant. The protection is real but
   incidental; a dedicated full-string assert on `pull_listing_sql()` would
   make it direct.

**Acceptable hermetic choices (not gaps):** `publish_delist_event`'s
subprocess path (routstr_delist.py:402-415) is mocked at both call sites
(tests:437-438, 448-450) while the argv it would run IS shape-tested
(tests:305-320, including `--env-sec`/never-`--sec` and kind 30078); the
secret never enters any assertion-visible argv. Call-site behaviour
(delisted=True on pull, delisted=False on relist) is behaviourally pinned
(tests:430-442, 444-453).

**Overall verdict: MEDIUM.** The pure decision core — the code that decides
WHEN to delist — is strongly pinned (4/4 controls caught; direction, edges,
first-run guard, baseline preservation all fail-on-break). The unpinned
surface is concentrated and identifiable: the one network-touching function's
result computation (item 1), multi-run `pulled_models` semantics (item 2,
which is why finding 4's HIGH escaped the suite), and a set of
tautology/weak-pin tests that make "55 tests" overstate the effective pin
set. No gap endangers the SALE-vs-provider distinction itself (pinned at
payload level, tests:244-251, 262-275).

**Should-fix (non-blocking, maps 1:1 to the numbered gaps):** (1) exercise
the real `_SshBackend._run` with mocked `subprocess.run` stdout/rc pairs;
(2) add a delist→delist→relist idempotence test; (3) replace the two
tautological tests (tests:322-324, 329-330) — the window test only after
finding 5 wires the constant to real logic or deletes it; (5) add CLI tests
passing `--move-hours`/`--variance`; (6) pin the `--status` key set;
(7) add non-numeric-`uncertainty`, empty-`[]`-feed, and non-list-feed tests;
(8) assert the full SQL constant string directly.
