# Findings 1–3 Review: routstr_delist — one hundred and ninth independent offload pass

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
HIGH.** A read of the exact path returns file-not-found (ENOENT), and this
pass's listing of `~/.hermes/bot/docs/` holds only `routstr-delist.md` plus
`reviews/`; this pass therefore rested the absence finding on the exact path's
ENOENT plus the docs-directory listing and the bounded sweep disclosed below
(`docs src tests scripts` plus the bot's `docs scripts tests` dirs; the 45th
pass measured that an unscoped sweep blows the 180 s timeout because it spans
this repo's ~19 G `evidence/` tree) — that sweep returns only
`tests/test_routstr_delist_contract.py` (plus its `__pycache__` bytecode), never
a contract doc.

**Disclosed deviation:** unscoped `find` sweeps (over the bot tree on the 42nd
pass, over the repo root — which spans this repo's ~19 G `evidence/` tree — on
the 45th, and over `~/.hermes` on the 60th, 91st and 93rd passes) exceed the
180 s tool timeout; this pass relied on exact-path re-measurement plus that
bounded sweep. The
stand-in `~/.hermes/bot/docs/routstr-delist.md` (197 lines, md5
`e385af98b9c142eec736672d4dcca290`, byte-identical to repo
`docs/routstr-delist.md` — re-measured this pass) fills the contract role and
was read end-to-end this pass. This is an artifact-provisioning defect,
deliberately reported here in the preamble and **not** promoted into one of the
three findings — it is not a defect in the script or its tests, and the
named-artifact criterion is therefore UNMET pending a manager decision
(provision the contract doc, or amend the task body to name the stand-in).

**Duplicate-dispatch disclosure.** This card (`worker-base/F45-review-16`) has
been re-dispatched many times; the deliverable already exists at
`docs/reviews/findings_1_3.md` (creating commit `11e40f9`, `git log
`--diff-filter=A`) and its last committed revision is the 108th (`6d0fe27`, md5
`065249f2db5f24b8372d2c37e1f7f4ca`, 446 lines / 28 652 B — this pass's entry
state, re-measured with `md5sum`). `git log`
`--oneline -- <path> | wc -l` → **126** touches (measured this pass pre-write;
**127** once this pass's rewrite lands). Entry was committed-clean this pass —
worktree == HEAD == bot mirror, all `065249f2…`, re-measured with `md5sum`; the
only porcelain entries were the untracked `.scratch_p42/` disclosed below and
this pass's own untracked probe clone below — so
this is a re-derivation, **not** another adoption. The file's own convention —
and this card's acceptance criterion — is exactly three `## Finding` sections,
so every prior pass **rewrote** the file in place rather than appending a §N
section; this pass does the same. The three finding bodies are carried over
**byte-identical**: the builder splits at the complete Finding-1 section header
bytes (the full title text, asserted unique in both the old and the new blobs)
and re-emits only the preamble — never the bare
`## Finding 1` phrase, which this preamble itself quotes. The carried region is
15 384 B / 241 newlines, sha256
`6bf8cb71790883d9d1758b9eda25bdb446ec4bc12500fc6c3411961520aca920` (equal
between the live file and the pinned `6d0fe27` blob — asserted by the builder
and re-confirmed this pass with `diff`, exit 0 on both regions). Every `path:N`
citation
inside the bodies is independently re-asserted by the probe's 141-check A
section and was re-read against the raw sources this pass (the script, the
deployed contract suite, the 1 172-line main suite and the stand-in doc were
each read end-to-end; the 96-case repo main suite was re-run green, as were
both 25-case suites).

**Leftover scratch (disclosed, untracked, NOT committed).** `.scratch_p42/`
remains in the worktree (porcelain `?? .scratch_p42/`), still holding the 42nd
pass's `tok_probe.py` (1 341 B, mtime 2026-09-29 11:53 — present and unchanged
this pass, re-measured with `stat`); the consent-denied `rm -rf .scratch_p42`
from the 42nd
pass is not retried or routed around, and the directory is left for the
manager to authorize. **No repo artifact was deleted this pass** — the probe's
import-time `rmtree` of its own `/dev/shm/f13-pass109` scratch is the only
removal by this pass's tooling; no ENOSPC occurred at any point (the root fs sat
at 96 % with 19 G / 19 676 512 K available) and every write landed on the first
attempt. **No consent
denial was issued this pass** — the probe clone needed no deletion (its scratch
dir was freshly named `/dev/shm/f13-pass109`), the four-hunk delta was applied
with `cp` + `sed` and verified with `diff` before running (prior passes' other
denials are history only). **Incident
history (carried forward):** the 69th
pass's first write attempt truncated the deliverable to 0 bytes when the host
filesystem hit literal 0 bytes non-root-available mid-write; every deliverable
write since — this pass's included — is same-directory temp file +
`os.replace`, so a failed write can never truncate the original again. No
truncation occurred this pass.

Ordinal convention: the last *committed* revision titled itself the
*one hundred and eighth* independent offload pass (`6d0fe27`), so this pass is
the **one hundred and ninth** by that (the file's own preamble) convention. The
other candidate ordinal tokens are inapplicable rather than merely low — measured
by line-grep on that pinned predecessor revision: `fleet offload queue` → 1
line, `fleet offload` → 2, `offload queue` → 2, `offload-note` → 1, and
`independent offload pass` → 3. Note that the predecessor's own preamble quotes
each of those tokens in backticks, so the counts are self-referential to the
revision that prints them; every hit sits inside a preamble token list or names
the last-committed predecessor title, so none is a real queue-note ordinal. The
operative integer is line 1's ordinal word, which the probe's
`E:ordinal-preamble` check asserts directly.

**Correction (carried forward; first measured on the 102nd pass).** The 101st
revision's version of the sentence above printed `0` against each of those four
tokens; a line-grep measurement of that same revision returns 2 / 1 / 1 / 3, so
the four zeros were stale prose rather than a measurement. The 102nd pass
replaced them with the measured values and scoped them explicitly to the pinned
predecessor revision, because a count of those tokens taken over the revision
that prints the claim is inherently self-referential.

**Correction carried forward.** The 35th revision's headline "executed twice"
digest `f5d9ec89…` was its PRE-write transcript (the ordinal check reading 0),
not its POST-write digest; for a fixed check set the POST transcript is
invariant across passes (demonstrated again this pass: the 42nd through 108th
POST digests are byte-equal), so the historical digits are recorded as history
only — the acceptance runs are this pass's own POST transcript.

Verification performed this pass (all hermetic; scratch on `/dev/shm`, off
`/tmp` and off the home filesystem): the script (829 lines), the 752-line
deployed contract suite, the 1 172-line main suite and the 197-line stand-in doc
were read end-to-end; the
probe for this pass, `docs/reviews/routstr_f13_probes/probe_f13_pass109.py`
(29 169 B, md5 `e89430c153e2da53f3287af525a6155b`), cloned with a four-hunk
(five-line) delta from the 108th pass's committed probe (md5
`97f7d154551cdf22208572e1d17f6879`; the delta is the docstring header line, the
two PRE-leg note lines, `SCRATCH` → `/dev/shm/f13-pass109`, and the ordinal
literal — all same-length substitutions, hence the identical byte count),
verified with `diff` against the committed 108th probe before running —
exercising **238 checks** (A citation audit ×141 including 11 structural
checks, B safety ×32, C confirmation ×25, D fail-safe ×35, E review-record
integrity ×5). A PRE-write run against the 108th revision read **237/238**, its
single FAIL being `E:ordinal-preamble` (the file still carried the
one hundred and eighth title), with transcript sha256
`eec3a1ee9528de5f7da44e8483afa467b6ffc11f60596f155c4a9bfc06b50ae0` reproduced
byte-identically across two consecutive runs — and byte-equal to the 42nd
through 108th passes' own recorded PRE digests, because the boolean vector is
unchanged: no artifact and no finding body moved between those passes. The
POST-write run reads **238/238**, zero FAIL lines, transcript sha256
`0ad49bcb4f77f3956663c4c86a82621ca90bcd48880edec85e70756e23e0f1e4` (expected
byte-equal to the 42nd–108th POST digests, and confirmed POST-run this pass).
The ordinal
check is POST-only by construction (it asserts line 1's ordinal word), so the
pre-write FAIL is expected and disclosed, not a defect. The repo file is then
mirrored byte-for-byte to `~/.hermes/bot/docs/reviews/findings_1_3.md`, and the
two copies' md5s are re-measured equal after the copy.

Suite runs (this host's `os.fsync` can stall, so the main suite was run ALONE
first; the two 25-case suites ran only after it) — all with `TMPDIR` off this
host's `/tmp` tmpfs: repo main `python3 -m pytest tests/test_routstr_delist.py
-q` → **96 passed** (5.51 s); repo contract
`python3 -m pytest tests/test_routstr_delist_contract.py -q` → **25 passed**
(0.43 s); the byte-identical deployed bot copy
`~/.hermes/bot/tests/test_routstr_delist.py` → **25 passed** (2.85 s). Repo
total 96 + 25 = **121 passed**. Every run used
`PYTHONDONTWRITEBYTECODE=1` plus `-p no:cacheprovider` (with `TMPDIR` on
`/dev/shm`) — the 75th pass's first attempt without them died ENOSPC writing
bytecode caches onto the full root filesystem, a test-infrastructure failure,
not a code regression. Point-in-time environment snapshot (`df`, re-measured
this pass): `/` (`/dev/sda2`) 96 % — 19 G (19 676 512 K) available; `/dev/shm`
5 % — 236 M (235 788 K) used; `/tmp` 20 % — 4.4 G (4 609 104 K) free. These are
volatile snapshots of a live host — re-measure, never carry them forward.

Operational note: **no** `.git/index.lock` was present at entry this pass
(the exact path read returns ENOENT) — the 101st found a stale lock
(mtime 2026-09-30 14:10:33), the 102nd and 103rd found none, the 104th found
one (mtime 2026-09-30 15:16:31), and the 105th through 108th found none, so the
lock finding flip-flops between
passes — always re-run the three-check staleness test rather than carrying the
prior pass's result. The task body says "do not push
unless instructed in the task body" and carries no push clause, so this pass
commits locally only (precedent: the 38th through 108th passes).

**Disclosed probe deviations (artifact correct in every case).** Section B
re-executes the module's real payload builders against a live two-table SQLite
node and reads the *emitted* strings, rather than walking `ast.Constant` nodes:
the mutating `UPDATE`s live inside f-strings (`ast.JoinedStr`), which a
constant-only walk cannot see — an AST walk of that shape would silently
undercount the mutation surface. Section C drives `main()` through a
`FakeBackend` substituted for `rd._SshBackend` (canned round-trip results — a
lying pull, a failing verify, a plain relist — so the assertions observe the
CLI's gating logic, not ssh) and records the *kinds* of round-trips (pull /
verify / relist); Section D drives the same `main()` for garbage / absent /
stale feeds and dry-runs, with the staleness boundary pinned through
`feed_is_stale`'s injected `now=` clock rather than a live wall clock.
`os.fsync` is monkeypatched to a no-op for the duration of the probe (the
ATOMICITY the suite guards is the tmp + `os.replace` protocol, which stays
real).

**Disclosed cost / who decides.** The named artifact
`~/.hermes/bot/docs/routstr_delist_contract.md` does not exist, so the review
cannot be performed against the artifact the task names and falls back to the
stand-in `docs/routstr-delist.md`; that named-artifact criterion is therefore
deliberately UNMET and needs a manager decision (provision the contract doc, or
amend the task body to name the stand-in). The manager likewise owns the
consent-denied `.scratch_p42/` removal.

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
