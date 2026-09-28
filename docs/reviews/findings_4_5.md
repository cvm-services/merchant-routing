# Offload review — routstr delist, findings 4–5 (atomicity/idempotence, SLA)

Independent re-derivation for this session (25th offload pass). Item **4
(atomicity + idempotence)** and item **5 (5-minute SLA arithmetic)** as
specified in `docs/reviews/routstr_delist_review.md:158` and `:196`. Every
`file:line` below was read this session; every behavioural claim was
re-executed against the current artifacts by
`docs/reviews/routstr_f45_probes/probe_f45_pass25.py` (driving the DEPLOYED
script in-process: the contract suite's real `FakeSellNode` executing the real
payload builders against a named in-memory sqlite sell node, a fake monotonic
clock, real on-disk state in tempdirs, forced `os.replace` failures, real
`os.fsync` inspection, AST name-load analysis). Raw output:
`docs/reviews/routstr_f45_probes/probe_f45_pass25.out`.

**Revision status.** All three artifacts are **byte-identical** to the
revision the previous pass reviewed (md5 re-checked this session, unchanged):
`routstr_delist.py` `2ea724ef08d857cd7b88a957300e70b4`,
`test_routstr_delist.py` `031851b356f0de4089512f02f13f05cc`,
`routstr-delist.md` `e385af98b9c142eec736672d4dcca290`. This pass is therefore
a *verification* pass: verdicts are re-derived from fresh execution, not
carried over.

**Artifact-path status (required report) — HIGH.**
`~/.hermes/bot/docs/routstr_delist_contract.md` **does not exist**.
`ls ~/.hermes/bot/docs/` → ENOENT for that name; the directory holds only
`routstr-delist.md` and `reviews/`. The mandated contract document is
**unreviewable at that path**. The design document that exists — and that the
suite itself calls the frozen contract (`tests/test_routstr_delist_contract.py:1`)
— is `~/.hermes/bot/docs/routstr-delist.md`, 197 L, md5
`e385af98b9c142eec736672d4dcca290`, byte-identical to repo
`docs/routstr-delist.md`; cited below as `docs:N`. This is a path/naming
defect in the task or the layout, not a missing design.

**Other artifacts (read end-to-end).**
`~/.hermes/bot/scripts/routstr_delist.py` — 829 L, md5
`2ea724ef08d857cd7b88a957300e70b4`, byte-identical to repo
`src/routstr_delist.py`; cited as `src:N`.
`~/.hermes/bot/tests/test_routstr_delist.py` — 752 L, md5
`031851b356f0de4089512f02f13f05cc`, byte-identical to repo
`tests/test_routstr_delist_contract.py`; cited as `contract:N`.

**Baselines (re-run this session).** repo
`python3 -m pytest tests/test_routstr_delist_contract.py -q` → **25 passed**
(0.40 s); deployed
`cd ~/.hermes/bot && python3 -m pytest tests/test_routstr_delist.py -q` →
**25 passed** (0.37 s). Live `~/.hermes/bot/routstr_delist_state.json`
re-read: keys `delisted`(true), `last_dry_run`, `last_reason`, `snapshot`({}),
`ts` — **no** `pulled_models`, no `blocked`. `crontab -l` holds **0** routstr
entries. **No artifact was modified**; all three md5 sums re-checked after the
probes and unchanged.

---

## Finding 4 — Atomicity and idempotence — MEDIUM

**The three original finding-4 defects are resolved; one durability defect
remains.** Re-derived by execution this session:

- **4.a Atomic write — OK.** `save_state()` (src:221-245) writes
  `.{basename}.{pid}.tmp` in the same directory (src:230), `flush` +
  `os.fsync` (src:233-234), then `os.replace` (src:235), and unlinks the tmp
  on any error (src:240-245). Probes P1/P2 (spying/forcing `os.replace`):
  exactly one swap; at the swap instant the destination still holds the
  COMPLETE old bytes and the tmp the COMPLETE new bytes; the final file is the
  new state; no `.*.tmp` litter. A forced failure before the replace returns
  `False`, leaves the previous state intact and loadable, and cleans the tmp.
  A reader can only ever observe old-or-new, never torn.
- **4.b Re-delist merge (idempotence defect 1) — OK FIXED.** src:744-749:
  `prior = state.get("pulled_models") or []`, `pulled = res.get("pulled") or []`,
  `merged = list(prior) + [n for n in pulled if n not in prior]`. Probe P7: a
  first `--manual` captures all 3 advertised names; a second `--delist` (the
  node now advertises nothing, so its capture is `[]`) leaves
  `pulled_models` unchanged. No clobber; the scoped relist can still restore
  the original names.
- **4.c Blanket-relist refusal (idempotence defect 2) — OK FIXED.**
  src:600-611: with no stored names and no `--relist-any`, `--relist` prints
  `relist_refused` and returns 1 **before any remote call**. Probe P8: rc=1,
  `remote_calls=0`, and the node's models map is untouched — including the
  operator-disabled row, which stays `0`. `--relist-any` is the explicit
  opt-in (src:526-528). The pre-existing live state file (no `pulled_models`,
  above) now takes this safe path instead of the old blanket `UPDATE`.
- **4.d Re-delist on an absent listing — OK.** Probe P7: `--delist` with
  nothing advertised still succeeds (`ok=true`, `confirmed=true`,
  `pulled=[]`), does not clobber `pulled_models`, and does not arm the
  breaker.
- **4.e Persist failure is SILENT on the success path — MEDIUM.** `save_state`
  returns a bool (src:236/239) but **all 8 call sites discard it** (src:565,
  622, 629, 638, 654, 710, 732, 752; probe F4.4 `assignment_sites=[]`). Probe
  P3, forcing `os.replace` to raise during a `--manual` run:
  rc=**0**, `action=delist`, `confirmed=true`, `ok=true`, and the remote pull
  **actually landed** (`models` all 0) — yet the state file is byte-unchanged,
  `delisted` is absent/false and `pulled_models` is absent. There is no
  exit-code change and no JSON field reporting the lost write. The consequence
  is exactly the mechanism the design leans on: the "flag in the objects that
  publishes the listing" (src:24-28, docs:122-123) is not durable, so the
  publisher advertises `delisted=false` while the listing is in fact pulled.
- **4.f No reconciliation of a lost flag — MEDIUM.** Probe P11: a
  variance-spike delist whose state write silently fails leaves the remote
  listing pulled; the trigger then goes quiet and the next run is
  `action=none` with durable `delisted=false`. Nothing ever reconciles the
  flag against the node: the only re-fetch (`verify_pull_payload()`,
  src:400-411) is a read-only `SELECT COUNT(*) FROM models WHERE enabled=1`
  and never reads any delist/state field (probe
  `verify_used_for_reconciliation=false`). The stale flag therefore persists
  indefinitely.
- **4.g The "durable BLOCKED marker" inherits the same hole — MEDIUM.**
  Probe P10: with ssh down and every persist failing, four consecutive runs
  return `[1, 1, 1, 1]`; `blocked` and `consecutive_failures` are absent from
  disk, so run 4 is **not** refused. Exit 3 and the durable breaker
  (docs:76-79) depend on the same ignored bool as 4.e.
- **4.h fsync durability is unasserted — LOW.** Both the shared `Rig`
  (contract:257) and `TestAtomicStateWrites` (contract:634) monkeypatch
  `os.fsync` to a no-op, so the durability half of the atomic protocol has no
  test. `save_state` does call it (probe F4.P5: 1 fsync, and the real fsync
  returned in <5 s on this host, i.e. the suppression is a host-workaround
  rather than a necessity here).
- **4.i No interlock between concurrent runs — LOW by design/scope.** `fcntl`
  / `flock` / `LockFile` occurrences in the module: 0 (probe F4.1/F4.9).
  Concurrent invocations are last-writer-wins; atomicity (4.a) guarantees
  readers never see a torn file, but a lost update is still possible.

**Severity driver = MEDIUM.** Not BLOCKER: the remote action is a single
sqlite transaction and the re-fetch gate means a delist is never *reported*
successful without the node confirming (src:682-688), so this cannot corrupt
the sell node — the delist itself is correct. It is a coordination/reporting
defect that needs a crash or write failure to trigger. It stays MEDIUM (not
LOW) because it silently defeats two documented safety mechanisms — the
publisher-read delist flag (docs:122-123) and the durable circuit breaker
(docs:76-79) — with no signal to the operator. **Must-fix: surface
`save_state`'s return (non-zero exit + a JSON field) on the success path, and
add a reconciliation read of the node's actual listing state.**

## Finding 5 — 5-minute SLA arithmetic — MEDIUM

The constants are now wired (this was the prior pass's headline defect), but
the bound still does not hold in the real worst case, and one constant remains
decorative. Measured this session:

- **5.a Constants and internal arithmetic — OK.** src:71-75:
  `TRIGGER_ACTION_WINDOW_S=300`, `POLL_CADENCE_S=240`,
  `ACTION_BUDGET_S=60`, `SSH_TIMEOUT_S=30`, `MAX_PULL_ATTEMPTS=2`; the
  arithmetic `240 + 60 = 300` and `2×30 ≤ 60` hold (probe F5.0). Unlike the
  prior revision these are consumed: `ACTION_BUDGET_S` is read at src:612 and
  src:667, `SSH_TIMEOUT_S` at src:800/806, `MAX_PULL_ATTEMPTS` at src:671/675/695
  (AST name-load analysis, probe F5.1b).
- **5.b The per-round-trip deadline clamp works — OK.** `_SshBackend._run`
  computes `timeout = min(SSH_TIMEOUT_S, remaining)` and refuses when the
  budget is exhausted (src:800-806). Probe Q3 (worst-case detection + 25 s
  round-trips): pull at t=240 with `remaining=60, timeout=30`; verify at
  t=265 with `remaining=35, timeout=30`; action phase 50 s ≤ 60 s budget;
  detection + action 290 s < 300 s.
- **5.c `POLL_CADENCE_S` is DEAD at runtime — LOW/MEDIUM.** It is never read
  by any logic. Its only AST load is src:73 (its own use to *derive*
  `ACTION_BUDGET_S`); the documented cadence lives only in the comment at
  src:72 and in the external crontab line (docs:106). Changing 240 changes no
  behaviour; the real cadence is an out-of-band cron setting the script
  neither reads nor can enforce. The claim "now wired to real constants"
  (docs:93) is true for the action budget, not for the poll cadence.
- **5.d Worst case is exactly 300 s, not "within 5 minutes" — MEDIUM.** Probe
  Q4b with each round-trip at the full `SSH_TIMEOUT_S=30`: sample at t=0 →
  worst-case detection charges the full `POLL_CADENCE_S` (t=240) → pull 30 s
  → verify 30 s → **confirmed delist at exactly t=300.0**
  (`strictly_under_300=false`). The contract says "within **5 minutes**"
  (docs:9) and the test asserts `confirmed_t - sample_t < 300`
  (contract:568) — that test passes only because it simulates a 25 s
  round-trip (contract:559) rather than 30 s, i.e. it spends a 2×5 s slack
  that a real slow ssh erases. So the minimal verified path sits exactly on
  the boundary; it is not strictly inside it.
- **5.e The nak publish is NOT deadline-clamped and breaches budget and
  window — MEDIUM.** `publish_delist_event` runs
  `subprocess.run(argv, timeout=30, …)` (src:459-461) with **no deadline**,
  on the success path (src:755-756). Probe Q4 (detection 240 + pull 30 +
  verify 30 + nak 30): the run prints rc=0 `action=delist` at **t=330**;
  action phase **90 s > ACTION_BUDGET_S (60)**;
  `breaches_action_budget=true`, `breaches_window=true`. Probe Q4c isolates
  the missing clamp: after a 25 s+25 s delist, **10 s of budget remain** but
  the publish is still handed the nominal `timeout=30` (10 < 30) — so the
  docstring claim "every remote round-trip is timeout-clamped to the remaining
  budget" (src:69-70, src:773-775) is FALSE for the event publish.
- **5.f The bounded in-run retry is unreachable at worst-case latency —
  MEDIUM.** Probe Q5 (round-trip 30 s, a pull that self-reports ok but is
  refuted by the re-fetch): pull 30 s + verify 30 s consumes the entire 60 s
  budget, so the `time.monotonic() < deadline` guard at src:695 is false and
  the retry never runs — `retry_ran=false`, `attempts_used=1` of
  `MAX_PULL_ATTEMPTS=2`. The documented "one bounded in-run retry absorbs a
  transient ssh blip" (docs:73-75) does not exist when round-trips are slow;
  the script falls straight to `delist_failed` / exit 1 and waits for the next
  tick.
- **5.g Deployment — informational.** `crontab -l` holds **0** routstr
  entries, matching docs:112-115 ("no crontab entry is wired yet"). The SLA is
  therefore not yet in force; the arithmetic defect above is latent, not
  live.

**Verdict: the documented ≤5-minute bound does not hold in the real worst
case.** The minimal verified delist lands at exactly 300 s (5.d), and with
`--nsec` the run can finish at 330 s with the action phase at 90 s —
both breaching the 300 s window and the 60 s action budget (5.e). The
contract test passes only on a simulated 25 s round-trip, which supplies 10 s
of unearned slack. **Severity driver = MEDIUM.** Not BLOCKER: no crontab entry
is wired (5.g), the action *is* re-fetched and the failure path is fail-safe
(exit non-zero, no `delisted` flip), so there is no live breach and no data
loss. **Must-fix: clamp the nak publish to the same deadline; set the
documented cadence so that `POLL_CADENCE_S + pull + verify + nak ≤ 300 s`
(e.g. `*/4` with `SSH_TIMEOUT_S=15`), or state the window as "≤ 300 s" to
match the boundary; and consume or delete `POLL_CADENCE_S`.**
