# Findings 1–3 Review: routstr_delist — forty-second independent offload pass

Scope (per the original task): finding 1 safety (delisting the routstr SALE
must never disable the routstr provider or touch the T470 flat-router ladder),
finding 2 post-delisting confirmation via an independent re-fetch, finding 3
fail-safe behaviour on an absent / garbage / stale `--preds` monitor feed.

**Artifact-path status (required immediate report).** The task names three
artifacts. `~/.hermes/bot/scripts/routstr_delist.py` (829 lines, md5
`2ea724ef08d857cd7b88a957300e70b4`) and
`~/.hermes/bot/tests/test_routstr_delist.py` (752 lines, md5
`031851b356f0de4089512f02f13f05cc`) are present and byte-identical to repo
`src/routstr_delist.py` and `tests/test_routstr_delist_contract.py`
respectively (re-measured this pass with `md5sum` on both pairs — both
digests match). **`~/.hermes/bot/docs/routstr_delist_contract.md` is MISSING —
HIGH.** `~/.hermes/bot/docs/` holds only `routstr-delist.md` (197 lines, md5
`e385af98b9c142eec736672d4dcca290`, byte-identical to repo
`docs/routstr-delist.md`) plus `reviews/`; the contract role is filled by that
stand-in doc, read end-to-end this pass. Re-measured this pass: `ls` of the
exact path returns `No such file or directory`, and the probe re-asserts the
absence (`E:contract-path-missing`). **Disclosed deviation:** the UNSCOPED
`find ~/.hermes/bot -iname '*contract*'` exceeded the 180 s tool timeout on
this host's large bot tree, so absence rests on the exact path's `ls` ENOENT,
the probe check, and a scoped sweep of `~/.hermes/bot/docs`, not on a
completed unbounded sweep. This is an artifact-provisioning defect,
deliberately reported here in the preamble and **not** promoted into one of
the three findings — it is not a defect in the script or its tests.

**Duplicate-dispatch disclosure.** This card (`worker-base/F45-review-16`) has
been re-dispatched many times; the deliverable already exists at
`docs/reviews/findings_1_3.md` (creating commit `11e40f9`, `git log
--diff-filter=A`) and its last committed revision is the 41st (`9cd9b43`,
md5 `e985012dca6c7be46340877a606ddec6`, 399 lines / 25 936 B). `git log
--oneline -- <path> | wc -l` → **59** touches (measured this pass pre-write).
Its own convention — and this card's acceptance criterion — is exactly three
`## Finding` sections, so every prior pass **rewrote** the file in place
rather than appending a §N section. This pass does the same: it re-derives the
three findings from the current artifacts, whose md5s were measured unchanged
this pass (`2ea724ef08d857cd7b88a957300e70b4`,
`031851b356f0de4089512f02f13f05cc`, `e385af98b9c142eec736672d4dcca290` —
not assumed). The finding bodies are carried over **byte-identical** (the
builder splits on the first `---`/`## Finding 1` marker and re-emits only the
preamble); every `path:N` citation inside them is independently re-asserted by
the probe's 130-check A section.

**Uncommitted and orphaned work found this pass (disclosed).** Unlike the 41st
pass, this pass found the working copy **diverged** from the committed blob: an
uncommitted `+2/-1` edit (working md5 `940319a674623a64ab41c5f15758e917`,
401 lines / 26 101 B) re-measuring the `/tmp`-tmpfs sentence, while the bot
mirror was byte-equal to the committed 41st blob (`e985012d…`). That edit's
intent (point-in-time `df -h` snapshots, marked volatile) is folded into this
revision. A prior dispatch also left an **untracked probe**,
`docs/reviews/routstr_f13_probes/probe_f13_pass42.py`, written for a revision
that was never produced; this pass adopts it, re-reads it, and carries it into
this commit so the lineage is not orphaned again. **Two probe bugs in it were
found and fixed this pass (PROBE bugs — the artifacts never drifted):** its
first run read `236 checks: 233 PASS, 3 FAIL` — the expected
`E:ordinal-preamble` plus two NEW structural checks absent from the pass-41
probe (`A:source-update-count-3`, `A:source-select-count-2`) that counted raw
`"UPDATE "`/`"SELECT "` substrings and so also counted one **comment**
mention (`routstr_delist.py:604`) and one **docstring** mention
(`routstr_delist.py:404`) — 4 / 3 measured against the correct 3 / 2
statements. They were replaced with `ast`+`tokenize` executable-literal
counts; the first rewrite still false-FAILed (`[371, 401, 408]`) because the
docstring is ONE STRING token that STARTS at 401 while it mentions `SELECT` on
404, so docstring spans are now excluded via `ast`. The fixed checks read the
correct statement sets `[355, 361, 394]` and `[371, 408]`. The source md5 was
`2ea724ef…` (829 lines) throughout and every other A check passed, so both
rounds were verifier bugs, never artifact drift. **A leftover scratch dir the
consent guard would not let me remove (disclosed, untracked, NOT committed):**
`.scratch_p42/tok_probe.py` (1 341 B) was authored inside the repo while
designing the tokenize fix; the `rm -rf .scratch_p42` cleanup was **denied by
the operator consent guard**, and a denial is not retried, rephrased or routed
around, so the directory remains in the worktree and the manager should
authorize its removal. Excluding it, the pre-write `git status --porcelain`
named exactly two paths (` M docs/reviews/findings_1_3.md`,
`?? docs/reviews/routstr_f13_probes/probe_f13_pass42.py`).

Ordinal convention: the last *committed* revision titled itself the *forty-first*
independent offload pass (`9cd9b43`), so this pass is the **forty-second** by
that (the file's own preamble) convention. The other candidate ordinal tokens
are **inapplicable, not merely zero**, and were re-measured this pass against
the PINNED pre-write blob (`git show 9cd9b43:<path>`, md5 `e985012d…`), not
against the live file which this prose itself perturbs: `fleet offload queue`
→ 1, `fleet offload` → 1, `offload queue` → 1, `offload-note` → 0 — all
single hits sit on line 69, the 41st revision's own sentence *asserting* those
counts, so the convention inflates its own count and can never be keyed on.
The subsidiary token `independent offload pass` occurs **2** times on that blob
(line 1 and line 65's historical note), so it is **not** single-valued either.
The operative integer is line 1's ordinal word, which the probe's
`E:ordinal-preamble` check asserts directly.

Verification performed this pass (all hermetic; scratch off `/tmp`, on
`/dev/shm`): the script (829 lines), both suites and the stand-in doc read
end-to-end; the probe for this pass,
`docs/reviews/routstr_f13_probes/probe_f13_pass42.py` (the adopted pass-42 probe
with the two statement-count checks fixed; 592 lines, md5
`a104e4f424d1d49208596f3b615d8f84`; `SCRATCH=/dev/shm/f13-pass42`),
exercising **238 checks** (A citation audit ×130 + 11 structural A checks,
B safety ×32, C confirmation ×25, D fail-safe ×35, E review-record integrity
×5). A PRE-write run of the same probe against the 41st revision read
**237/238**, its single FAIL being `E:ordinal-preamble` (the file still carried
the 41st title), with transcript sha256
`eec3a1ee9528de5f7da44e8483afa467b6ffc11f60596f155c4a9bfc06b50ae0` reproduced
byte-identically across two consecutive runs; it was also reproduced against a
pristine copy of the pinned 41st blob. The POST-write run read **238/238**,
zero FAIL lines, transcript sha256
`0ad49bcb4f77f3956663c4c86a82621ca90bcd48880edec85e70756e23e0f1e4` reproduced byte-identically across two
consecutive runs. The ordinal check is POST-only by construction (it asserts
line 1's ordinal word), so the pre-write FAIL is expected and disclosed, not a
defect; the POST transcript is invariant across passes for a fixed check set. The
repo file is then mirrored byte-for-byte to
`~/.hermes/bot/docs/reviews/findings_1_3.md`, and the two copies' md5s are
re-measured equal after the copy.

**Correction carried forward.** The 35th revision's headline “executed twice”
digest `f5d9ec89…` was its PRE-write transcript (the ordinal check reading 0),
not its POST-write digest `55e95221…`; the two differ by exactly the ordinal
bit. Both digests changed at this pass because the adopted probe's check set
grew (196/198 → 236 → 238 checks), so the historical digits are recorded as
history only — the acceptance runs are this pass's own POST transcript.

Suite runs (this host's `os.fsync` can stall, so the main suite was run ALONE,
not beside the contract suite) — all with `TMPDIR` off this host's `/tmp`
tmpfs: repo main `python3 -m pytest tests/test_routstr_delist.py -q` → **96
passed** (0.62 s, and 17.13 s on the final-artifact re-run — this host's `fsync`
variance, cf. the 41st pass's 17.6 s / 66 s); repo contract `python3 -m pytest
tests/test_routstr_delist_contract.py -q` → **25 passed** (0.27 s, 0.50 s on
re-run); the
byte-identical deployed bot copy `~/.hermes/bot/tests/test_routstr_delist.py`
→ **25 passed** (0.34 s); repo total 96 + 25 = **121 passed**. Point-in-time
environment snapshot (`df -h` / `df -B1`, re-measured this pass): `/tmp` 44 %
— 2 560 565 248 B of 5 867 642 880 B; `/dev/shm` 1 % — 3 878 912 B; `/` 93 %
— 411 G of 468 G. These are volatile snapshots of a live tmpfs — re-measure,
never carry them forward. Timings are environment-dependent; do not carry them
forward either.

Operational note: no `.git/index.lock` was present for most of this pass (the
35th and 38th passes each cleared a stale one); before the rewrite `git status`
named exactly two paths plus the disclosed scratch directory (above). The task
body says “do not push unless instructed in the task body” and carries no push
clause, so this pass commits locally only (precedent: the 38th, 40th and 41st
passes).

**Correction recorded by the dispatch that landed this revision (same card).**
This 42nd revision was authored but left **uncommitted** — its only copy was the
worktree, mirrored byte-identically to the bot copy (`md5
2b838947c1876e8eba78413a5fc199ef`, 416 lines / 26 970 B). The dispatching
landing pass found a STALE 0-byte `.git/index.lock` (`mtime 11:47`, no `git`
process touching this repo, no `lsof` holder — the standard three-check test) and
cleared it before committing, so a lock *was* in the worktree at landing time and
the sentence above describes an earlier moment in the pass; the 35th, 38th and
42nd passes each contended with a stale lock. The landing independently
reproduced this pass's evidence before committing: POST `238/238` (transcript
sha256 `0ad49bcb…`, reproduced twice), PRE-write `237/238` against a pristine copy
of the pinned 41st blob `9cd9b43` (single expected `E:ordinal-preamble` FAIL,
sha256 `eec3a1ee…`), suites green (main 96, contract 25, deployed 25), and the
three artifact md5s re-measured unchanged. No finding body was altered; the only
prose added is this correction.

**Disclosed probe deviations (artifact correct in every case).** Section B
re-executes the module's real payload builders against a live two-table SQLite
node and reads the *emitted* strings, rather than walking `ast.Constant`
nodes: the mutating `UPDATE`s live inside f-strings (`ast.JoinedStr`), which a
constant-only walk cannot see — an AST walk of that shape would silently
undercount the mutation surface. Section C drives `main()` through a
`FakeBackend` substituted for `rd._SshBackend` and records the *kinds* of
round-trips (pull / verify / relist); Section D's `--dry-run` / staleness drives
replace `rd.time` and `rd._SshBackend` with a fake clock and a payload-executing
fake backend so the durable-state assertions observe real `save_state`/
`load_state` behaviour without ssh; `os.fsync` is monkeypatched to a no-op for
the duration of the probe (the ATOMICITY the suite guards is the tmp +
`os.replace` protocol, which stays real).

**Disclosed cost / who decides.** The named artifact
`~/.hermes/bot/docs/routstr_delist_contract.md` does not exist, so the review
cannot be performed against the artifact the task names and falls back to the
stand-in `docs/routstr-delist.md`; that named-artifact criterion is therefore
deliberately UNMET and needs a manager decision (provision the contract doc, or
amend the task body to name the stand-in). The manager likewise owns the
repeated-uncommitted-work and consent-denial problems this pass disclosed (the
lost 39th revision; the orphaned 41st and 42nd probes; the authorized removal
of `.scratch_p42/`).

Citation legend: `routstr_delist.py:N` = the script (both copies,
byte-identical); `contract:N` = repo `tests/test_routstr_delist_contract.py`
(the 25-case deployed suite, byte-identical to
`~/.hermes/bot/tests/test_routstr_delist.py`); `tests:N` = repo
`tests/test_routstr_delist.py` (the 96-case main suite); `docs:N` =
`docs/routstr-delist.md`.
---

## Finding 1 — Safety: SALE-delisting never disables the routstr provider or touches the T470 ladder

severity: **OK** (gaps: **LOW** ×3)

Every write path the module can take was re-enumerated from source and from
executed payloads this pass:

- **Remote DB — only the `models` (advertisement) table is mutated.** Exactly
  three UPDATE statements exist, all models-only: `routstr_delist.py:355`
  (`UPDATE models SET enabled=0 WHERE enabled=1`), `routstr_delist.py:361`
  (blanket `UPDATE models SET enabled=1`, legacy fallback), `routstr_delist.py:394`
  (parameterized `UPDATE models SET enabled=1 WHERE name IN (?,…)`). Two SELECTs
  exist (`routstr_delist.py:371` advertised-name capture,
  `routstr_delist.py:408` verify COUNT). Probes
  B:pull-names-models / B:pull-no-providers / B:relist-blanket-names-models /
  B:relist-scoped-names-models / B:verify-read-only / B:pull-one-update /
  B:relist-scoped-one-update / B:relist-blanket-one-update: every built payload
  names `models`, none names `upstream_providers`, and no payload contains
  INSERT/DELETE/DROP/ALTER/REPLACE (the verify payload is UPDATE-free).
- **`upstream_providers` / T470 ladder — docstring mentions only.** The string
  occurs exactly three times in the source (`routstr_delist.py:35`,
  `routstr_delist.py:352`, `routstr_delist.py:771`), all inside docstrings
  asserting it is NOT touched (probe A:upstream-mentions-exactly-3: measured
  line set `[35, 352, 771]`); zero executable references.
- **The remote command is one shlex-quoted argv element.** `build_ssh_docker_cmd`
  (`routstr_delist.py:414-425`) quotes the container (`routstr_delist.py:423`)
  and the payload (`routstr_delist.py:424`) and returns
  `["ssh", ssh_target, remote]` (`routstr_delist.py:425`). Probes
  B:ssh-argv-len3 / B:ssh-argv0-1 / B:ssh-remote-decompose /
  B:hostile-round-trips: the argv is 3 elements and `shlex.split(cmd[2])`
  round-trips to `docker exec <container> python3 -c <payload>` intact even with
  a hostile container name (`evil'; rm -rf / #`), and that name survives as
  exactly one remote token absent from argv[0]/argv[1]. No local shell is
  involved; only two `subprocess.run` sites exist (`routstr_delist.py:459` nak
  publish, `routstr_delist.py:808` ssh), `shell=True` occurs nowhere (probes
  B:subprocess-run-2-sites / B:no-shell-true), and the regression is pinned by
  `tests:345` (`test_ssh_cmd_is_single_shlex_safe_remote_command`).
- **Blanket relist is refused by default.** With no captured names, `--relist`
  refuses before any remote call (`routstr_delist.py:600`, `relist_refused` at
  `routstr_delist.py:606`, rc 1 at
  `routstr_delist.py:611`). The blanket SQL is reachable
  only via the explicit `--relist-any` opt-in, pinned `tests:1039` +
  `tests:1056`.
- **The ladder guard is TESTED semantically, not by substring alone.**
  `contract:468` (`TestSemanticGuardLadderUntouched`) builds a real ladder
  artifact (`contract:108`) alongside a live `upstream_providers` table
  (`contract:129`), reads provider rows from `contract:160`, executes the
  script's real payloads against it, and asserts the ladder file is
  byte-identical (`contract:480`), the provider rows are unchanged, the routstr
  provider is still an enabled candidate, and that no executed payload even
  names the table (`contract:483`). The scoped-relist direction re-asserts ladder
  byte-identity (`contract:504`) and that operator-disabled rows stay disabled.
  This pass re-executed the same semantics in-probe (probes
  B:semantic-pull-captures-names, B:semantic-pull-disabled-all,
  B:semantic-verify-count0, B:semantic-relist-restores-2,
  B:semantic-providers-unchanged, B:semantic-ladder-identical,
  B:semantic-routstr-still-candidate, B:semantic-operator-row-stays-off): pull
  captured exactly the three advertised names and disabled all rows, verify
  counted 0, the scoped relist restored exactly 2 of the captured names while
  the operator-disabled row stayed off, `upstream_providers` was row-identical,
  the ladder file was byte-identical, and the routstr provider remained an
  enabled ladder candidate. Static scoping pins: `tests:303` (pull SQL),
  `tests:311` (relist SQL), `tests:336` (verify payload read-only).

Gaps (**LOW**, non-blocking, all re-measured):

- (**LOW**) (a) `--ssh-target` / `--container` (`routstr_delist.py:536`,
  `routstr_delist.py:537`) are unvalidated — an operator can point the mutating
  payload at another host/container by design. Because the value is a standalone
  argv element with no local shell (probes B:ssh-argv-len3 /
  B:hostile-round-trips), this is a
  target-redirection / option-injection surface, **not** command injection.
- (**LOW**) (b) The payloads hard-code `/app/data/keys.db` ×4
  (`routstr_delist.py:370`, `routstr_delist.py:385`, `routstr_delist.py:393`,
  `routstr_delist.py:407`) — a container layout
  change would mutate whatever DB lives at that path.
- (**LOW**) (c) `save_state`'s return value is ignored at all eight call sites
  (`routstr_delist.py:565`, `:622`, `:629`, `:638`, `:654`, `:710`, `:732`,
  `:752`) — a failed write after a
  CONFIRMED delist (`routstr_delist.py:752`) would silently diverge local state
  from remote reality (cross-ref finding 4).

---

## Finding 2 — Confirmation: delist success is gated on an independent read-only re-fetch

severity: **OK** — requirement MET; residual **MEDIUM** ×1, **LOW** ×2

- **The confirmation mechanism.** `verify_pull_payload()` (`routstr_delist.py:400-411`)
  is a read-only `SELECT COUNT(*) FROM models WHERE enabled=1`
  (`routstr_delist.py:408`) with no UPDATE anywhere (probes B:verify-read-only /
  B:semantic-verify-count0). It runs as a SEPARATE ssh round-trip via
  `_SshBackend.verify` (`routstr_delist.py:790-793`), invoked at
  `routstr_delist.py:682` after the pull inside the attempt loop
  (`routstr_delist.py:671-697`). Success requires
  `vres.get("ok") is True and vres.get("count") == 0` (`routstr_delist.py:683`);
  only then is the flag set (`routstr_delist.py:687`) and the durable
  `delisted=true` written (`routstr_delist.py:747-752`, rc 0 at
  `routstr_delist.py:764`).
- **The happy path is exactly one pull + one verify.** Probes C:happy-rc0,
  C:happy-action-delist, C:happy-confirmed, C:happy-verified-count0,
  C:happy-kinds, C:happy-durable-delisted: rc 0, `action delist`,
  `confirmed true`, `verified_count 0`, executed kinds `["pull","verify"]`,
  durable `delisted=true`; pinned `tests:567` (`test_verify_gates_success`).
- **A lying pull is refuted.** Probes C:lying-rc1 / C:lying-action /
  C:lying-kinds / C:lying-no-flag / C:lying-breaker-tick: a pull that
  self-reports ok while the re-fetch still counts advertised models is forced to
  failure (`routstr_delist.py:691-694`), retried once in-run
  (`MAX_PULL_ATTEMPTS = 2`, `routstr_delist.py:75`), and on exhaustion takes the
  failure branch (`routstr_delist.py:719-739`: `delisted` stays false at
  `routstr_delist.py:726`, baseline not consumed, breaker tick, rc 1/3 at
  `routstr_delist.py:739`). Measured: rc 1, `action delist_failed`, kinds
  `["pull","verify","pull","verify"]`, `consecutive_failures == 1`. Pinned
  `contract:346` (`test_unverified_pull_is_a_failed_delist`), `tests:603`
  (`test_verify_failure_is_attempt_failure`).
- **Parse/transport robustness fails safe.** `_SshBackend._run`
  (`routstr_delist.py:795-825`) accepts only
  `proc.returncode == 0 and data.get("ok") is True` (`routstr_delist.py:822`)
  after parsing the LAST stdout line as JSON (`routstr_delist.py:814`), so a
  non-zero rc, unparseable stdout, or a missing `ok`/`count` key yields a
  non-confirming result — garbage can only fail the run, never confirm it
  (pinned `tests:1107`, `tests:1116`, `tests:1123`, `tests:1146`).

- (**MEDIUM**) **The relist path has no symmetric re-fetch** (re-measured this
  pass, probes C:relist-rc0 / C:relist-no-verify-roundtrip /
  C:relist-gated-on-selfreport / C:relist-clears-flag / C:relist-pops-names).
  Relist success is gated on the round-trip self-report alone
  (`routstr_delist.py:626`), and on that self-report the run sets
  `delisted=false` and pops `pulled_models`
  (`routstr_delist.py:634`, `routstr_delist.py:635`). Measured: a relist executes
  `kinds == ["relist"]` only — **no verify round-trip** — yet clears the flag and
  destroys the stored scoped name set. A lying relist (rc 0, ok printed, UPDATE
  not landed — the same fault class the contract deemed must-fix for delist)
  would therefore fake a restored listing AND destroy the scoped names, forcing a
  subsequent scoped `--relist` to be refused (`routstr_delist.py:600`,
  `routstr_delist.py:606`) and recovery through `--relist-any`, which re-enables
  rows the operator had deliberately disabled (`docs:29`). The contract mandates
  the re-fetch only for "a fired delist" (`docs:69`, `docs:71`), so this is an
  asymmetry, not a contract breach; the fix is cheap (verify `COUNT(*)>0`, or
  re-read the names before popping).
- (**LOW**) (a) dry-run sets the local `confirmed` flag with no remote verify
  (`routstr_delist.py:680`) — intent-only, nothing remote to confirm
  (`docs:87`; probe D:firing-dryrun-pull-only confirms the dry-run delist
  executes `["pull"]` only, with no `verify` round-trip).
- (**LOW**) (b) the verify round-trip shares the ssh transport and last-line JSON
  parsing with the pull (`routstr_delist.py:810`, `routstr_delist.py:814`,
  `routstr_delist.py:822`), so a systematic transport-level fault could satisfy
  both — the failure direction remains safe (a fooled verify only keeps the run
  failing toward the breaker).

---

## Finding 3 — Fail-safe: absent, garbage, and stale monitor feed

severity: **OK** — residual **MEDIUM** ×1, **LOW** ×4

Every branch that can reach a delist runs through
`fire = args.delist or dec["fire"]` (`routstr_delist.py:649`). Enumerated and
probed:

- **Absence — OK.** No `--preds` → `raw_preds=[]`; acceleration requires
  non-empty preds on both sides (`routstr_delist.py:107`), variance requires
  non-empty preds (`routstr_delist.py:143`); a first run with no baseline can
  never fire acceleration (pinned `tests:176`, `contract:308`). Manual
  override remains available by design (`routstr_delist.py:580`).
- **Garbage — OK.** `_read_preds` never raises, drops non-dict entries
  (`routstr_delist.py:479`) and returns `[]` on any parse failure
  (`routstr_delist.py:481`, `routstr_delist.py:482`). Probes D:garbage-read-preds-empty /
  D:garbage-none-empty / D:garbage-drops-nondict / D:garbage-rc1 /
  D:garbage-preds-error / D:garbage-action-none / D:garbage-no-remote /
  D:garbage-baseline-intact
  (driven through `main()`): a malformed feed → rc 1, `preds_error=true`
  (computed at `routstr_delist.py:585`), `action none`, no remote action, and the
  stored baseline `{"zai\x1f1h": 12.0}` intact (`update_state` only overwrites
  the snapshot when preds is non-empty, `routstr_delist.py:261`,
  `routstr_delist.py:262`; pinned `tests:243`, `tests:547`). Type guards:
  `uncertainty` is isinstance-guarded with bool explicitly excluded
  (`routstr_delist.py:152`; pinned `tests:146`), and
  `exhausts_in_hours` is guarded (`routstr_delist.py:193`,
  `routstr_delist.py:196`).
- **Stale — OK.** `STALENESS_S = 1800` (`routstr_delist.py:78`); `feed_is_stale`
  (`routstr_delist.py:485-496`) is mtime-based and fails closed — undeterminable
  age (`OSError`) returns True (`routstr_delist.py:495`,
  `routstr_delist.py:496`), and the age expression
  `not (0 <= age <= max_age_s)` (`routstr_delist.py:494`) makes a future mtime
  stale. Probes D:stale-fresh-false, D:stale-boundary-inclusive-false (clock
  injected via the `now=` kwarg: **exact boundary 1800 s → False, inclusive**),
  D:stale-1801-true, D:stale-future-mtime-true, D:stale-missing-path-true.
  Wiring: a stale feed zeroes the preds before trigger
  evaluation (`routstr_delist.py:589`, `routstr_delist.py:591`,
  `routstr_delist.py:592`), so even the level-based variance trigger cannot fire
  on dead data, and before any baseline refresh. Probes D:stale-rc1 /
  D:stale-flag / D:stale-action-none / D:stale-no-remote / D:stale-baseline-intact:
  variance-elevated (0.99) but 2 h-old feed → rc 1, `action none`,
  `preds_stale=true`, zero remote calls, baseline intact; pinned `tests:937`,
  `tests:968`, `tests:995`.
  `preds_stale` is surfaced in every output branch (`routstr_delist.py:656`,
  `:714`, `:735`, `:762`) with rc 1 when quiet (`routstr_delist.py:660`). The
  manual override is deliberately never gated on freshness
  (`routstr_delist.py:580` ordering; probes D:manual-not-gated-rc0 /
  D:manual-stale-observed → rc 0, `preds_stale=true`; pinned `tests:980`,
  `docs:60`).
- **Breaker interaction (cross-ref finding 6).** Repeated failed runs refuse all
  further remote action (`routstr_delist.py:724`, `:727`, `:731`; refuse-all at
  `routstr_delist.py:569`, exit 3 at `routstr_delist.py:578`) until `--unblock`
  (`routstr_delist.py:561`, `routstr_delist.py:567`); a dry run never counts
  toward it (`routstr_delist.py:699`).

- (**MEDIUM**) **dry-run purity is conditional on firing** (re-measured this
  pass, probes D:quiet-dryrun-rc0 / D:quiet-dryrun-refreshes-baseline /
  D:quiet-dryrun-no-last-run). `docs:87` and the firing path
  (`routstr_delist.py:699-717`) promise a dry run consumes no acceleration
  baseline and records `last_dry_run`. The QUIET branch
  (`routstr_delist.py:651`, `routstr_delist.py:652`, `routstr_delist.py:654`)
  has **no** `--dry-run` guard: passing `--dry-run` with a quiet (11 h)
  feed against a 12 h baseline → rc 0, and the stored snapshot is refreshed from
  12.0 to 11.0 with **no** `last_dry_run` recorded — the dry run silently
  perturbed durable state and left no trace. The contrast is exact: the
  *firing* dry run records `last_dry_run` (`routstr_delist.py:705`), sets no
  durable delist flag and runs `pull` only (probes
  D:firing-dryrun-records-intent, D:firing-dryrun-pull-only,
  D:firing-dryrun-no-flag). Impact is loss of protection (a baseline can move
  under a "no side effects" run), never an unsafe delist.
- (**LOW**) (a) `--preds-key` scoping is opt-in and defaults UNSCOPED — filtering
  happens only when the flag is passed (`routstr_delist.py:594`,
  `routstr_delist.py:597`), and `evaluate_triggers` passes no `key` to
  `variance_jumped` (`routstr_delist.py:303`) although the parameter exists for
  that purpose. Probes D:unscoped-default-fires / D:scoped-filter-quiets drive
  `main()` with a foreign `openrouter` variance spike: with no `--preds-key` the
  foreign spike fires the delist, while the filter quiets it when the key is
  given; pinned `tests:776`, documented at `docs:54`–`docs:55`.
- (**LOW**) (b) mtime-only freshness (`routstr_delist.py:485`,
  `routstr_delist.py:494`): a writer that rewrites `preds.json` with old data
  refreshes the mtime and bypasses the guard.
- (**LOW**) (c) Cosmetic: `_hours` accepts bool (`routstr_delist.py:193`,
  `routstr_delist.py:196`) while the variance guard excludes it
  (`routstr_delist.py:152`) — arithmetic-safe; the override marker is
  presence-based with no TTL (`routstr_delist.py:164`,
  `routstr_delist.py:172`), operator-controlled by design.
- (**LOW**) (d) Cross-ref finding 4: the quiet-run state write
  (`routstr_delist.py:654`) ignores the `save_state` return value.
