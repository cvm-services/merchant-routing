# Offload review — routstr delist, findings 4–5 (atomicity/idempotence, SLA)

Fourth independent pass (re-dispatch, 2026-09-17). Scope: original task items 4
(atomicity + idempotence) and 5 (5-minute SLA arithmetic). Every claim below
was re-derived in this session: the script was read end-to-end (both copies),
the contract stand-in and test suite read end-to-end, greps and the byte-diff
re-run, the live state file read, and the suite executed fresh. Nothing was
carried over unverified from the Gate 2.5 review or passes 1–3.

**Artifact-path status (required report per task instructions):**

- `~/.hermes/bot/docs/routstr_delist_contract.md` — **MISSING — HIGH**.
  Re-verified this session: the path does not exist; `~/.hermes/bot/docs/`
  contains only `reviews/`. The contract role is filled by the repo's
  `docs/routstr-delist.md` (129 lines) — the document the script itself cites
  at routstr_delist.py:21 — and it was read end-to-end as the stand-in.
- `~/.hermes/bot/tests/test_routstr_delist.py` — **MISSING — HIGH**. No
  `tests/` directory exists anywhere under `~/.hermes/bot` (verified this
  session). The repo counterpart `tests/test_routstr_delist.py` (546 lines,
  55 tests) was read end-to-end instead.
- `~/.hermes/bot/scripts/routstr_delist.py` — present (602 lines), verified
  **byte-identical** to repo `src/routstr_delist.py` this session (`diff`:
  clean). All script line references below therefore apply to both copies.

Conventions: `routstr_delist.py:N` = the script (both copies); `tests:N` =
repo tests; `docs:N` = repo `docs/routstr-delist.md`. Live evidence read (not
modified): the deployed state file `~/.hermes/bot/routstr_delist_state.json`.
Suite evidence (this pass): `python3 -m pytest tests/test_routstr_delist.py -q`
→ **55 passed in 0.33s** (hermetic, no network). No artifacts were modified by
this review.

## Finding 4 — Atomicity and idempotence — **HIGH (both required properties refuted)**

### 4a. Atomicity — not implemented — **HIGH**

- The only local persistence is `save_state()`, routstr_delist.py:204-212,
  which writes with a plain `open(path, "w")` at routstr_delist.py:208 — no
  temp file, no `os.replace`, no `fsync`, no lock. Verified this session:
  `grep -nE 'os\.replace|fsync|tempfile|rename|flock|fcntl'` over the module
  → zero hits.
- A crash mid-write, or a reader racing the writer, can observe a
  truncated/partial file. The failure is silent because `load_state()` never
  raises and returns `{}` on any parse failure (routstr_delist.py:194-201). A
  torn state file is therefore read as *no state*: `--status` would report
  `delisted: false` (routstr_delist.py:473-480, every field via
  `state.get(...)` defaults), and per the design's flag mechanism (docs:79-80;
  `update_state` routstr_delist.py:215-230) a listing publisher reading the
  flag would advertise `delisted=false` while the remote listing is actually
  pulled — exactly the state/reality divergence atomic writes exist to
  prevent.
- No mutual exclusion between concurrent invocations (same grep: no lock
  anywhere) and there are five `save_state()` call sites in `main()`
  (routstr_delist.py:497, 504, 520, 535, 544 — grep-enumerated this session).
  A manual `--relist` racing a cron delist tick is last-writer-wins, with no
  ordering guarantee between the local `delisted` flag and the remote
  `models` table.
- The persistence result is never checked: `save_state()` returns True/False
  (routstr_delist.py:210, 212) but all five call sites invoke it as a bare
  statement. A failed persist (disk full, permissions) is silent. Worked
  consequence: the remote pull succeeds, the state write fails, and the run
  still prints `action: delist` and exits 0 (routstr_delist.py:552-555) while
  the durable `delisted` flag stays false; the mirror case after a successful
  remote `--relist` leaves `delisted: true` stuck. Same divergence class as
  the torn write, reachable with no crash at all.
- The remote side IS atomic: each SSH payload is one sqlite connection, one
  UPDATE, one commit (pull routstr_delist.py:329-340; relist
  routstr_delist.py:343-362), with the advertised names captured before the
  disable on the same connection (routstr_delist.py:336-339). The non-atomic
  component is the local state write.
- Test coverage: none for this property. The nearest tests cover a corrupt
  *input feed* (tests:392-407) and the read side of a corrupt state file
  (tests:219-224) — never a torn state write, a failed persist, or two
  concurrent runs.

Must-fix: temp file in the same directory + `fsync` + `os.replace` (atomic on
POSIX); lock around load/modify/save; treat a False `save_state()` as a run
failure (exit non-zero) so flag divergence is surfaced, not silent.

### 4b. Idempotence — a repeat delist is NOT a no-op — **HIGH**

- The remote UPDATE itself is idempotent (`UPDATE models SET enabled=0 WHERE
  enabled=1`, routstr_delist.py:320 — a second run matches 0 rows). The local
  bookkeeping is not.
- Trigger 2 is level-based by design (`variance_jumped` routstr_delist.py:117-
  143 fires every run while elevated; docs:41-44; fire gate
  routstr_delist.py:515). So a second delist run while the condition holds
  re-fires and re-runs the pull payload — whose capture
  `SELECT name FROM models WHERE enabled=1` (routstr_delist.py:336) now
  returns `[]` — and routstr_delist.py:543 overwrites `pulled_models` with
  that empty list (`extra={"pulled_models": res.get("pulled", [])}`). The
  four `pulled_models` touch points: routstr_delist.py:477, 491, 503, 543
  (grep-verified this session).
- From then on `--relist` reads `names = state.get("pulled_models") or []`
  (routstr_delist.py:491), gets `[]`, and `relist_payload([])`
  (routstr_delist.py:346-354) falls back to the blanket
  `UPDATE models SET enabled=1;` (`relist_sql`, routstr_delist.py:326) — no
  WHERE clause, re-enabling EVERY model row, including any the operator had
  deliberately disabled before the delist. This contradicts the contract
  docs:23-27 ("never rows the operator had disabled before the delist") and
  the script's own docstring routstr_delist.py:34-37 ("the relist re-enables
  only those").
- Repeat `--relist` is not idempotent either: a successful relist pops
  `pulled_models` (routstr_delist.py:503), so a second `--relist` (operator
  retry or a monitoring loop) reads `[]` and takes the same blanket-enable
  path.
- Live evidence (read this session, not hypothetical): the deployed state
  file `~/.hermes/bot/routstr_delist_state.json` reads
  `{"delisted": true, "last_reason": "manual override", "snapshot": {},
  "ts": 1788883877.3967388}` — no `pulled_models` key. A `--relist` from the
  current live state takes the blanket path today.
- Why the suite misses it: no test runs two consecutive delists. The
  scoped-relist round-trip (tests:412-428) pulls once and relists with no
  second delist in between; `FakeBackend`'s default `pull_res` always returns
  names (tests:37), masking the empty-capture clobber; and the blanket
  fallback is explicitly blessed by tests:259-260
  (`test_relist_payload_fallback_when_no_names`).

Must-fix: overwrite `pulled_models` only when the capture is non-empty (or
merge with the stored set); make an empty-names `--relist` refuse or require
an explicit opt-in flag rather than blanket-enabling; add double-delist and
double-relist regression tests.

**Verdict 4: HIGH** — both required properties (atomic state writes;
idempotent re-runs) are absent, persistence failures are silently ignored,
and the idempotence hole is reachable from the current live state file.

## Finding 5 — 5-minute SLA arithmetic — **HIGH (does not hold as documented)**

Per the original task's required breakdown:

- **Configured poll interval**: none in the script — it is a one-shot CLI
  (`main()` evaluates triggers once; no loop). The documented cadence is cron
  `*/5` = 300 s (docs:57-63; example crontab at docs:63), and the contract
  states the ≤5-minute bound is met "by running it on a cadence ≤5 min (cron
  `*/5` or faster)" (docs:59-61). Deployment note: no crontab entry is wired
  at all yet (docs:69-72).
- **Polls/retries needed to confirm**: 0 in-run. There is no re-fetch and no
  in-run retry — a single ssh attempt (routstr_delist.py:582) whose success
  signal is the payload's same-round-trip self-report (parsed at
  routstr_delist.py:587, gated at routstr_delist.py:595). On failure the run
  exits 1 (routstr_delist.py:539) and the next attempt waits for the next
  cron tick.
- **Re-fetch round-trip**: nonexistent (0 s). No code path re-reads the
  listing after the UPDATE; the only SELECT is the pre-update name capture
  (routstr_delist.py:336). "Confirmed delist" is a same-transaction
  self-report, never an independent observation.
- **Action round-trip bound**: `subprocess.run(..., timeout=60)` at
  routstr_delist.py:582 — the ONLY bound. `build_ssh_docker_cmd()`
  (routstr_delist.py:365-376) sets no ssh `ConnectTimeout`/`BatchMode`
  options (grep-verified this session: zero hits), so a hung TCP/TLS or auth
  stall burns the full 60 s before TimeoutExpired is caught
  (routstr_delist.py:597, reported `ok: False`). Typical ssh + docker exec
  ≈ 1-3 s; worst case 60 s. The optional nak publish (timeout=30,
  routstr_delist.py:410) runs after the pull on the success path
  (routstr_delist.py:547-548), so it does not delay the pull itself but
  inflates total job duration to ≤ 90 s.
- **Worst-case detection → confirmed delist**: trigger occurs at ε just
  after a cron tick → detection latency ≤ 300 s (next tick) + in-run
  evaluation ~0 s + ssh ≤ 60 s = **≤ 360 s = 6 m 00 s > 300 s. The
  ≤5-minute bound is violated in the worst case by construction.** Even the
  expected case (ssh ≈ 2 s) totals ≈ 302 s > 300 s: with `*/5`, detection
  alone consumes the entire window and leaves ~0 s of budget for the action.
  With k failed attempts: (k+1)·300 s + 60 s — one transient ssh failure
  pushes confirmed delist to ~660 s (11 min); no in-run retry exists to
  compress it.
- **Enforcement is absent**: `TRIGGER_ACTION_WINDOW_S = 300`
  (routstr_delist.py:63) is a dead constant — grep-verified this session:
  its only occurrence in the module is the definition line itself. No code
  path measures or enforces the window; it is consumed only by the module
  docstring (routstr_delist.py:5), the contract (docs:59), and the tests
  (tests:330, 343). The two SLA-adjacent tests pin nothing behavioural:
  tests:329-330 asserts the constant equals the literal 300 (tautological —
  it cannot fail while the SLA behaviour is deleted), and tests:332-344
  measures the wall-clock of a `--dry-run` run whose backend path performs
  no subprocess at all (routstr_delist.py:578-580) — proving only that the
  script does not sleep, nothing about cadence or the ssh bound.

**Verdict 5: HIGH** — the ≤5-minute SLA does NOT hold under the documented
`*/5` cadence (worst case 360 s, expected ~302 s) and is enforced nowhere.
It holds only under the charitable "within 5 min of the script's own start"
reading. To satisfy ≤ 300 s end-to-end: run `*/4` (240 s + 60 s = 300 s,
still boundary) or `*/2` (240 s worst case with margin), or keep `*/5` and
add a bounded in-run retry plus a shorter ssh ConnectTimeout; in all cases
wire `TRIGGER_ACTION_WINDOW_S` to real logic or delete it.

---

Provenance: fourth offload pass. Passes 1-3 (repo commits 6736d22, 1576844,
79e341f) all reached the same two HIGH verdicts; this pass re-derived every
claim independently against the artifacts (script read end-to-end in both
copies, byte-diff clean; contract stand-in and all 546 test lines read;
greps re-run; live state file read; 55/55 suite green) and confirms both
findings and all four sub-findings (4a torn-write/unchecked-persist, 4b
pulled_models clobber, repeat-relist blanket path). `~/.hermes/bot` is not a
git repository (re-verified this session), so the required local commit lands
in the workspace repo (merchant-routing) at `docs/reviews/findings_4_5.md`,
with this identical copy at the task-mandated bot path
`~/.hermes/bot/docs/reviews/findings_4_5.md`.
