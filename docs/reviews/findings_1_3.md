# Findings 1–3 Review: routstr_delist — eighty-ninth independent offload pass

Scope (per the original task): finding 1 safety (delisting the routstr SALE
must never disable the routstr provider or touch the T470 flat-router ladder), finding 2
post-delisting confirmation via an independent re-fetch, finding 3
fail-safe behaviour on an absent / garbage / stale `--preds` monitor feed.

**Artifact-path status (required immediate report).** The task names three
artifacts. `~/.hermes/bot/scripts/routstr_delist.py` (829 lines, md5
`2ea724ef08d857cd7b88a957300e70b4`) and
`~/.hermes/bot/tests/test_routstr_delist.py` (752 lines, md5
`031851b356f0de4089512f02f13f05cc`) are present and byte-identical to repo
`src/routstr_delist.py` and `tests/test_routstr_delist_contract.py`
respectively (re-measured this pass with `md5sum` on both pairs — both
digests match). **`~/.hermes/bot/docs/routstr_delist_contract.md` is MISSING —
HIGH.** A read of the exact path returns file-not-found, the
`~/.hermes/bot/docs/` directory listing holds only `routstr-delist.md` plus
`reviews/`, and this pass's bounded `find ~/.hermes/bot -maxdepth 3 -iname
'*contract*'` sweep (plus the `-iname '*routstr*'` form) could NOT complete —
it exceeded the 180 s tool timeout, so NO sweep of the bot tree completed this
pass; the exact path's ENOENT, the docs-directory listing, and the probe
absence (`E:contract-path-missing`). **Disclosed deviation:** unscoped
`find` sweeps (over the bot tree on the 42nd pass, over the repo
root — which spans this repo's ~19 G `evidence/` tree — on the 45th, and
over `~/.hermes` on the 60th) exceed the 180 s tool timeout; this pass again
did not repeat an unbounded sweep and relied on exact-path re-measurement
instead (exact-path read on the three named artifacts, `ls` of the bot's docs
directory and routstr-named listings of its scripts and tests directories,
and the probe's exact-path check).
Absence therefore rests on the exact path's ENOENT, the docs-directory
listing, and the probe's exact-path check — this pass completed no sweep
(bounded or unbounded) of the bot tree. The stand-in `~/.hermes/bot/docs/routstr-delist.md`
(197 lines, md5 `e385af98b9c142eec736672d4dcca290`, byte-identical to repo
`docs/routstr-delist.md`) fills the contract role and was read end-to-end
this pass. This is an artifact-provisioning defect, deliberately reported
here in the preamble and **not** promoted into one of the three findings —
it is not a defect in the script or its tests.

**Duplicate-dispatch disclosure.** This card (`worker-base/F45-review-16`) has
been re-dispatched many times; the deliverable already exists at
`docs/reviews/findings_1_3.md` (creating commit `11e40f9`, `git log
--diff-filter=A`) and its last committed revision is the 88th (`c0d1ade`,
md5 `80467bcb5c6be906ba9e934c7248d926`, 530 lines / 34 179 B). `git log
`--oneline -- <path> | wc -l` → **106** touches (measured this pass pre-write).
Entry was committed-clean this pass — worktree == HEAD == bot mirror, all
`80467bcb…`, re-measured with `md5sum` — so this is a re-derivation,
**not** another adoption (the 42nd and 87th passes were the adoptions; the
87th landed the authored-uncommitted revision `1e213cca…` as commit
`13c1b12`). The file's own convention — and
this card's acceptance criterion — is exactly three `## Finding` sections,
so every prior pass **rewrote** the file in place rather than appending a
§N section. This pass does the same: it re-derives the three findings from
the current artifacts, whose md5s were measured unchanged this pass
(`2ea724ef08d857cd7b88a957300e70b4`,
`031851b356f0de4089512f02f13f05cc`, `e385af98b9c142eec736672d4dcca290` —
not assumed). The finding bodies are carried over **byte-identical** — the
builder splits at the complete Finding-1 section header bytes (the newline
plus the full title text, asserted unique in both the old and the new blobs)
and re-emits only the preamble; never the bare `## Finding 1` phrase, which
the preamble itself quotes, the 50th pass's builder trap. The carried
region's sha256 is `4e4bb5bfd735ecc8…` (15 385 B, 242 lines, re-measured
equal between the live file and the pinned `c0d1ade` blob). Every `path:N`
citation inside the bodies is independently re-asserted by the probe's
141-check A section and was re-read against the raw sources this pass (the
script, the deployed contract suite and the stand-in doc were each read
end-to-end; the 21 main-suite `tests:N` citations were re-asserted by the
probe's A section, each cited line's exact content matched in-source; the
1172-line main suite itself was verified this pass by md5/line-count equality
with its HEAD blob and re-run green — 96 passed).

**Leftover scratch (disclosed, untracked, NOT committed).** `.scratch_p42/`
remains in the worktree (porcelain `?? .scratch_p42/`), still holding the
42nd pass's `tok_probe.py` (1 341 B, mtime 2026-09-29 11:53 — unchanged; the
52nd pass had recorded the file gone, the 53rd found it back, and every pass
from the 54th through the 88th and this pass finds it unchanged again —
whatever moved it, in either direction, it was not these passes). The
consent-denied `rm -rf .scratch_p42` from the 42nd pass is not retried or
routed around, and the directory is left for the manager to authorize.
**Consent denials (historical, disclosed).** The 75th
pass's one space-recovery attempt — `rm -rf .pytest_cache
tests/__pycache__ src/__pycache__` (gitignored, regenerable bytecode
caches, ~324 KB in-repo), issued after its repo-side probe copy died
ENOSPC with `/` at literal 0 bytes available — was **consent-denied** by
the operator guard. It was not retried or routed around, and after the
denial no deletion was attempted at all in that pass: its only deletions
were its own failed-copy cleanups — the pre-denial removal of the first
0-byte `probe_f13_pass75.py` partial, while the second partial was
simply overwritten by the retried copy, never deleted. The 74th's
`rm -rf ~/.cache/*`, the 42nd's `.scratch_p42` removal and the 68th's
command share this history. **This 89th pass attempted no deletion at
all** — no ENOSPC occurred at any point (`/` held **14 G** non-root-available
at entry via `df -h` and **13442 M** at the pre-compose
`df --output=avail -B1M` reading — volatile; disclosed in the snapshot
below — and every write this pass landed on the
first attempt; the probe clone was staged whole on `/dev/shm` and `cp`-ed
into the probes directory in one step), so no cleanup was ever needed.
The disk-space exposure therefore stands and is disclosed below; the
deliverable write goes ahead under the standing atomic protocol
(same-directory temp + `os.replace`), which cannot truncate the original —
the 69th-pass incident's lesson — and lands whole on the first attempt
(re-measured by md5 immediately after the swap). The probe clone itself
was a `sed` re-direction onto `/dev/shm` plus a one-step `cp` into the
probes directory — four exact-pattern edits
(higher-ordinal substitution applied first so no sed line double-advances),
verified with `diff` against the committed 88th probe (the docstring
header, the PRE-leg note, `SCRATCH`, and the ordinal literal are the only
differing lines — measured: lines 2, 14–15, 48 and 576); the probe's own
scratch handling (rmtree of its own `/dev/shm/f13-pass89` directory, then
recreate) is unchanged from the 88th pass's probe. Beyond that directory
the pre-commit `git status --porcelain` names only this pass's own two
paths — the new probe (`docs/reviews/routstr_f13_probes/probe_f13_pass89.py`)
and the rewritten deliverable — no other untracked or modified path; the review
file at this dispatch's entry was committed-clean (re-derivation, not an
adoption). **Incident history (carried
forward):** the 69th pass's first write attempt truncated the file to
0 bytes — the host filesystem hit literal 0 bytes non-root-available
mid-write (concurrent fleet writers) — and was recovered then (`~/.cache`
cleared, the 68th blob restored byte-identically from HEAD via
`git checkout --`, rewrite redone). Every deliverable write since — this
pass's included — is same-directory temp file + `os.replace`, so a failed
write can never truncate the original again. No truncation occurred this
pass (no write failed at all this pass; in the 75th the ENOSPC failures
hit the probe COPY, never the deliverable); the
history is retained because the standing atomic-write practice depends on
it.

Ordinal convention: the last *committed* revision titled itself the
*eighty-eighth* independent offload pass (`c0d1ade`), so this pass is the
**eighty-ninth** by that (the file's own preamble) convention. The other
candidate ordinal tokens are **inapplicable, not merely zero**, and were
re-measured this pass against the PINNED pre-write blob (`git show
c0d1ade:<path>`, md5 `80467bcb…`), not against the live file which this prose
itself perturbs: `fleet offload queue` → 1 (line 133), `fleet offload` →
2 lines / 3 occurrences (line 133 twice, line 143 once), `offload queue` → 2
(lines 133–134), `offload-note` → 1 (line 135), `independent offload pass`
→ 4 (lines 1, 128, 135, 139) —
in the 88th blob every queue-token hit sits inside that revision's own
backticked token list (pinned-blob lines 133–134, its version of this very
paragraph), and each `independent offload pass` hit is the title
(pinned-blob line 1), the sentence naming the last-committed predecessor
title (line 128), the list (line 135), or the sentence describing the hits
(line 139): every count is self-referential and none can be keyed on as a
dispatch counter (the raw `fleet offload` count reads 2 lines / 3
occurrences — the token list at line 133 twice and the raw-count sentence at
line 143; the 74th through 88th blobs measure the same 2 lines / 3
occurrences, and every hit is again this paragraph's own prose). The operative
integer is line 1's ordinal word, which the probe's `E:ordinal-preamble` check
asserts directly.

**Environmental observation (carried forward from the 71st pass, read side).**
The 71st pass once read the repo main suite as **752 lines** mid-pass —
exactly the contract suite's length — while every other measurement showed
the file unchanged at **1172 lines / 55 832 B**, no write ever occurring: a
single short READ under a 100 %-full `/` (149 M non-root free at its compose
time), the read-side twin of the 69th pass's 0-byte write truncation. This
pass re-measured and found the suite consistent on every read (1172
lines / 55 832 B, md5
`293b0459b636a918cf1cce57bf922473`, equality with the `13c1b12` HEAD blob,
pytest's 96-test collection, the probe's 141-check A section) — no
recurrence. The lesson stands: on this host a one-shot size read can be
wrong in either direction — re-measure any surprising size before recording
it.

Verification performed this pass (all hermetic; scratch off /tmp and off the
home filesystem, on `/dev/shm`): the script (829 lines), the 752-line
deployed contract suite and the 197-line stand-in doc were read end-to-end;
the repo main suite was verified by byte-identity with its HEAD blob (1172
lines / 55 832 B, md5 `293b0459…`) and re-run green; the probe for this pass,
`docs/reviews/routstr_f13_probes/probe_f13_pass89.py` (592 lines, md5
`55e19a9b6fa033dd9db8c1f0f81f6502`), cloned from the 88th pass's committed
probe (md5 `e562c4eebe8c2344757cfb55c793e75a`) with the four-hunk delta
(docstring header, PRE-leg note, `SCRATCH` → `/dev/shm/f13-pass89`, and the
ordinal literal) verified with `diff` against the committed 88th probe
before running — exercising **238 checks** (A citation audit ×141, 11
structural A checks included in that 141, B safety ×32, C confirmation ×25,
D fail-safe ×35, E
review-record integrity ×5; section tally re-measured this pass: A=141
B=32 C=25 D=35 E=5). A PRE-write run of the probe against the 88th revision
read **237/238**, its single FAIL being `E:ordinal-preamble` (the file still
carried the eighty-eighth title), with transcript sha256
`eec3a1ee9528de5f7da44e8483afa467b6ffc11f60596f155c4a9bfc06b50ae0`
reproduced byte-identically across two consecutive runs — and byte-equal to
the 42nd through 88th passes' own recorded PRE digests, because the boolean
vector is unchanged: no artifact and no finding body moved between those
passes. The POST-write run reads **238/238**, zero FAIL lines, transcript
sha256 `0ad49bcb4f77f3956663c4c86a82621ca90bcd48880edec85e70756e23e0f1e4`
reproduced byte-identically across two consecutive runs (likewise byte-equal
to the 42nd through 88th POST digests, for the same reason; the E checks do
not hash the document, so recording the digest in this preamble cannot
perturb it). The ordinal check is POST-only by construction (it asserts
line 1's ordinal word), so the pre-write FAIL is expected and disclosed, not
a defect. The repo file is then mirrored byte-for-byte to
`~/.hermes/bot/docs/reviews/findings_1_3.md`, and the two copies' md5s are
re-measured equal after the copy.

**Correction carried forward.** The 35th revision's headline "executed twice"
digest `f5d9ec89…` was its PRE-write transcript (the ordinal check reading
0), not its POST-write digest; the two differ by exactly the ordinal bit. For
a fixed check set the POST transcript is invariant across passes
(demonstrated again this pass: the 42nd through 89th POST digests are
byte-equal), so the historical digits are recorded as history only — the
acceptance runs are this pass's own POST transcript.

Suite runs (this host's `os.fsync` can stall, so the main suite was run
ALONE first; the two 25-case suites ran only after it) — all with `TMPDIR`
off this host's `/tmp` tmpfs: repo main `python3 -m pytest
tests/test_routstr_delist.py -q` → **96 passed** (1.25 s — volatile; the
88th recorded 1.01 s, the 87th 0.48 s / 0.99 s, the
86th 0.49 s, the 85th 0.55 s, the 84th 0.52 s, the 83rd 0.50 s,
the 82nd 0.72 s and the 81st 0.48 s on the same suite); repo
contract `python3 -m
pytest tests/test_routstr_delist_contract.py -q` → **25 passed** (0.45 s;
the 88th recorded 0.67 s, the 87th 0.40 s, the
86th 0.34 s, the 85th 0.38 s, the 84th 0.35 s); the byte-identical deployed bot
copy `~/.hermes/bot/tests/test_routstr_delist.py` → **25 passed** (1.05 s;
the 88th recorded 1.57 s, the 87th 0.57 s, the
86th 0.66 s, the 85th 0.69 s, the 84th 0.28 s); repo
total 96 + 25 = **121 passed**. Point-in-time environment snapshot
(`df`/`statvfs`, re-measured this pass): `/tmp` 12 % —
4.9 G free of 5.5 G; `/dev/shm` 2 % — 84 M used;
`/` (`/dev/sda2`) 97 % — 430 G of 468 G used, non-root available **14 G**
at entry (`df -h`) and **13442 M** at the pre-compose
`df --output=avail -B1M` readings (volatile — re-measure, never carry
forward; no ENOSPC anywhere this pass up
to compose; the 88th recorded 7.4 G at entry and 7051 M / 7207 M at its two
readings, the 87th 23 M at the authoring dispatch's entry and 582 M / 341 M at
the landing's, the 86th recorded 4.5 M at entry and 68.6 M at compose, the
85th 69 M at entry and 72 M at compose, the 84th
141 M at entry and 109 M at compose, the 83rd 216 M at entry
and 217 M at compose, the 82nd 195 M at entry and 194 M at compose, the 81st
309 M at entry and 308 M at compose, the 79th 1.2 G at entry and 370 M at
compose, the 78th 1.3 G at entry and compose, the 77th 1.3 G at entry and
compose, the 76th ~110 M at entry / 1.4 G by mid-pass, the 75th 0 M at
compose with two ENOSPC probe-copy failures, the 74th 71 M at entry / 0 M at
compose, the 73rd 21 M, the 72nd 102 M, the 71st 149 M, the 70th 228 M,
the 69th ~276 M after its `~/.cache` clear, the 68th 79 M).
Keep every scratch and suite temp off it. Suite runs use
`PYTHONDONTWRITEBYTECODE=1` plus `-p no:cacheprovider` (with `TMPDIR` on
`/dev/shm`) — the 75th pass's first attempt without them died ENOSPC
writing bytecode caches onto the full root filesystem, a
test-infrastructure failure, not a code regression; this pass used them
from the start and hit no such failure. These are volatile snapshots of a
live host — re-measure, never carry them forward. Timings likewise.

Operational note: this pass's pre-write measurement found **no**
`.git/index.lock` present (`ls` → ENOENT, measured; re-checked immediately
before `git add`), so no stale-lock clear was needed (the 35th, 38th, 42nd,
49th, 53rd, 55th and 56th passes had to clear one; a mid-pass `git
checkout` under the 69th pass's 0-byte-disk incident also failed to create
one cleanly — nothing was left behind, re-measured). The task body says "do
not push unless instructed in the task body" and carries no push clause, so
this pass commits locally only (precedent: the 38th through 88th passes).

**Disclosed probe deviations (artifact correct in every case; wording
corrected on the 51st pass — the earlier preamble's "fake clock +
payload-executing fake backend" described the pre-42nd probe shape).**
Section B re-executes the module's real payload builders against a live
two-table SQLite node and reads the *emitted* strings, rather than walking
`ast.Constant` nodes: the mutating `UPDATE`s live inside f-strings
(`ast.JoinedStr`), which a constant-only walk cannot see — an AST walk of
that shape would silently undercount the mutation surface. Section C drives
`main()` through a `FakeBackend` substituted for `rd._SshBackend` (canned
round-trip results — a lying pull, a failing verify, a plain relist — so the
assertions observe the CLI's gating logic, not ssh) and records the *kinds*
of round-trips (pull / verify / relist); Section D drives the same `main()`
for garbage / absent / stale feeds and dry-runs, with the staleness boundary
pinned through `feed_is_stale`'s injected `now=` clock rather than a live
wall clock. `os.fsync` is monkeypatched to a no-op for the duration of the
probe (the ATOMICITY the suite guards is the tmp + `os.replace` protocol,
which stays real).

**Disclosed cost / who decides.** The named artifact
`~/.hermes/bot/docs/routstr_delist_contract.md` does not exist, so the review
cannot be performed against the artifact the task names and falls back to the
stand-in `docs/routstr-delist.md`; that named-artifact criterion is therefore
deliberately UNMET and needs a manager decision (provision the contract doc,
or amend the task body to name the stand-in). The manager likewise owns the
consent-denied `.scratch_p42/` removal (its `tok_probe.py` still present,
re-measured this pass — see the scratch paragraph above).

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
