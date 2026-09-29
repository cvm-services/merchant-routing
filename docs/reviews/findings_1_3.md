# Findings 1–3 Review: routstr_delist — twenty-third independent offload pass

Scope (per the original task): finding 1 safety (delisting the routstr SALE must
never disable the routstr provider or touch the T470 flat-router ladder),
finding 2 post-delisting confirmation via an independent re-fetch, finding 3
fail-safe behaviour on an absent / garbage / stale `--preds` monitor feed.

**Artifact-path status (required immediate report).** The task names three
artifacts. `~/.hermes/bot/scripts/routstr_delist.py` (829 lines, md5
`2ea724ef08d857cd…`) and `~/.hermes/bot/tests/test_routstr_delist.py` (752 lines,
md5 `031851b356f0de40…`) are present and byte-identical to repo
`src/routstr_delist.py` and `tests/test_routstr_delist_contract.py`
respectively (probe E:bot-parity-src / E:bot-parity-tests). **`~/.hermes/bot/docs/routstr_delist_contract.md`
is MISSING — HIGH.** `~/.hermes/bot/docs/` holds only `routstr-delist.md` (197
lines, md5 `e385af98b9c142ee…`, byte-identical to repo `docs/routstr-delist.md`,
probe E:bot-parity-docs) and `reviews/`; the contract role is filled by that
stand-in doc, read end-to-end this pass. Re-measured this pass: the path does
not exist (probe E:contract-path-missing-HIGH). This is an artifact-provisioning
defect, deliberately reported here in the preamble and **not** promoted into one
of the three findings — it is not a defect in the script or its tests.

**Duplicate-dispatch disclosure.** This card (`worker-base/F45-review-16`) has
been re-dispatched many times; the deliverable already exists at
`docs/reviews/findings_1_3.md` (creating commit `11e40f9`; 41 commits touch the
path to date) and is committed-clean with its bot mirror byte-identical (probe
E:bot-deliv-parity). Its own convention — and this card's acceptance
criterion — is exactly three `## Finding` sections, so every prior pass
**rewrote** the file in place rather than appending a §N section (the append
convention used on other boards would break the exactly-three rule). This pass
does the same: it re-derives the three findings from the current artifacts —
whose md5s were measured unchanged this pass, not assumed — and rewrites the
file. Ordinal convention: the immediately prior revision titled itself the
*twenty-second* independent offload pass and committed as `6d73660`; this pass
is therefore the **twenty-third** by that (the file's own preamble) convention.
There is no usable `fleet offload` note sequence in this file, so the preamble
ordinal is the operative integer. **Result of the re-derivation: no correction
to the prior revision was required** — all three findings re-measured to the
same vector (F1 OK with LOW ×3; F2 OK with a MEDIUM ×1 + LOW ×2; F3 OK with a
MEDIUM ×1 + LOW ×4), and every `path:N` citation in this file is audited
line-by-line by the fresh probe below. Artifacts untouched.

Citation legend: `routstr_delist.py:N` = the script (both copies, byte-identical);
`contract:N` = repo `tests/test_routstr_delist_contract.py` (the 25-case
deployed suite); `tests:N` = repo `tests/test_routstr_delist.py` (the 96-case
main suite); `docs:N` = `docs/routstr-delist.md`.

Verification performed this pass (all hermetic; scratch outside `/tmp`): the
script, both suites and the stand-in doc read end-to-end; a fresh probe,
`docs/reviews/routstr_f13_probes/probe_f13_pass23.py`, exercising **204 checks**
(A citation audit, B safety, C confirmation, D fail-safe, E review-record
integrity) executed **twice with byte-identical transcript sha256
`5925376989f1c946…` → 204/204 PASS**, zero FAIL lines; repo suite
`python3 -m pytest tests/test_routstr_delist.py tests/test_routstr_delist_contract.py -q`
→ **121 passed** (96 main + 25 contract); deployed suite
`cd ~/.hermes/bot && python3 -m pytest tests/test_routstr_delist.py -q` →
**25 passed**; both with `TMPDIR` off this host's `/tmp` tmpfs (41 % used this
pass).

**Disclosed probe deviations (artifact correct in every case).** The first draft
of this pass's section-B DML check enumerated executable SQL by walking
`ast.Constant` nodes — which cannot see the two payload `UPDATE`s, because those
live in f-strings (`ast.JoinedStr`), not plain string constants. That check
would have silently undercounted and so understated the mutation surface. It was
replaced, before the probe's first run, with payload-level assertions (execute
the real builder outputs and count `UPDATE ` / scan for
INSERT/DELETE/DROP/ALTER/REPLACE) that measure the strings the module actually
emits. The artifacts were correct throughout; the corrected probe runs to
204/204. Citing this because a verifier that hides its own bug is worse than
none.

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
  `routstr_delist.py:408` verify COUNT). Probes B:pull-sql-models,
  B:blanket-sql-models-only, B:pull-payload-one-update,
  B:relist-scoped-one-update, B:relist-blanket-one-update and
  B:no-payload-names-upstream: every built payload names `models`, none names
  `upstream_providers`, and no payload contains INSERT/DELETE/DROP/ALTER/REPLACE
  (the verify payload is UPDATE-free — probe B:verify-read-only).
- **`upstream_providers` / T470 ladder — docstring mentions only.** The string
  occurs exactly three times in the source (`routstr_delist.py:35`,
  `routstr_delist.py:352`, `routstr_delist.py:771`), all inside docstrings
  asserting it is NOT touched (probe B:upstream-mentions-exactly-3: measured
  line set `[35, 352, 771]`); zero executable references.
- **The remote command is one shlex-quoted argv element.** `build_ssh_docker_cmd`
  (`routstr_delist.py:414-425`) quotes the container (`routstr_delist.py:423`)
  and the payload (`routstr_delist.py:424`) and returns
  `["ssh", ssh_target, remote]` (`routstr_delist.py:425`). Probes
  B:ssh-argv-len3, B:remote-roundtrip and B:hostile-container-single-token: the
  argv is 3 elements and `shlex.split(cmd[2])` round-trips to
  `docker exec <container> python3 -c <payload>` intact even with a hostile
  container name (`evil'; rm -rf / #`), and that name survives as exactly one
  remote token absent from argv[0]/argv[1]. No local shell is involved; only two
  `subprocess.run` sites exist (`routstr_delist.py:459` nak publish,
  `routstr_delist.py:808` ssh), `shell=True` occurs nowhere (probes
  B:subprocess-run-sites / B:no-shell-true), and
  the regression is pinned by `tests:345`
  (`test_ssh_cmd_is_single_shlex_safe_remote_command`).
- **Blanket relist is refused by default.** With no captured names, `--relist`
  refuses before any remote call (`routstr_delist.py:600`, `relist_refused` at
  `routstr_delist.py:606`, rc 1 at `routstr_delist.py:611`); probes
  B:blanket-relist-refused / B:blanket-relist-no-remote confirm rc 1,
  `action relist_refused`, zero remote calls. The blanket SQL is reachable
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
  B:semantic-verify-count0, B:semantic-relist-restores3,
  B:semantic-operator-row-stays-off, B:semantic-providers-unchanged,
  B:semantic-ladder-bytes-identical): pull captured exactly the three advertised
  names and disabled all rows, verify counted 0, the scoped relist restored
  exactly 3, the operator-disabled row stayed off, `upstream_providers` was
  row-identical, and the ladder file was byte-identical. Static scoping pins:
  `tests:303` (pull SQL), `tests:311` (relist SQL), `tests:336` (verify payload
  read-only).

Gaps (**LOW**, non-blocking, all re-measured):

- (**LOW**) (a) `--ssh-target` / `--container` (`routstr_delist.py:536`,
  `routstr_delist.py:537`) are unvalidated — an operator can point the mutating
  payload at another host/container by design. Because the value is a standalone
  argv element with no local shell (probes B:ssh-argv-len3 /
  B:hostile-container-single-token; probe D:ssh-target-unvalidated), this is a
  target-redirection / option-injection surface, **not** command injection.
- (**LOW**) (b) The payloads hard-code `/app/data/keys.db` ×4
  (`routstr_delist.py:370`, `routstr_delist.py:385`, `routstr_delist.py:393`,
  `routstr_delist.py:407`; probe D:keysdb-hardcoded-4) — a container layout
  change would mutate whatever DB lives at that path.
- (**LOW**) (c) `save_state`'s return value is ignored at all eight call sites
  (`routstr_delist.py:565`, `:622`, `:629`, `:638`, `:654`, `:710`, `:732`,
  `:752`; probe D:save-return-ignored-8-sites) — a failed write after a
  CONFIRMED delist (`routstr_delist.py:752`) would silently diverge local state
  from remote reality (cross-ref finding 4).

---

## Finding 2 — Confirmation: delist success is gated on an independent read-only re-fetch

severity: **OK** — requirement MET; residual **MEDIUM** ×1, **LOW** ×2

- **The confirmation mechanism.** `verify_pull_payload()` (`routstr_delist.py:400-411`)
  is a read-only `SELECT COUNT(*) FROM models WHERE enabled=1`
  (`routstr_delist.py:408`) with no UPDATE anywhere (probes C:verify-select-only /
  B:verify-read-only). It runs as a SEPARATE ssh round-trip via `_SshBackend.verify`
  (`routstr_delist.py:790-793`), invoked at `routstr_delist.py:682` after the
  pull inside the attempt loop (`routstr_delist.py:671-697`). Success requires
  `vres.get("ok") is True and vres.get("count") == 0` (`routstr_delist.py:683`);
  only then is the flag set (`routstr_delist.py:687`) and the durable
  `delisted=true` written (`routstr_delist.py:747-752`, rc 0 at
  `routstr_delist.py:764`).
- **The happy path is exactly one pull + one verify.** Probes C:happy-rc0,
  C:happy-action-delist, C:happy-confirmed, C:happy-verified-count0,
  C:happy-kinds, C:happy-durable-delisted: rc 0, `action delist`,
  `confirmed true`, `verified_count 0`, executed kinds `["pull","verify"]`,
  durable `delisted=true` with `pulled_models` captured; pinned `tests:567`
  (`test_verify_gates_success`).
- **A lying pull is refuted.** Probes C:lying-pull-rc1 / C:lying-pull-action /
  C:lying-pull-kinds / C:lying-pull-no-flag: a pull that self-reports ok while
  the re-fetch still counts advertised models is forced to failure
  (`routstr_delist.py:691-694`), retried once in-run
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
  (probes C:run-parses-count, C:run-garbage-fails, C:run-nonzero-rc-fails,
  C:run-missing-ok-key-fails; pinned `tests:1107`, `tests:1116`, `tests:1123`,
  `tests:1146`).

- (**MEDIUM**) **The relist path has no symmetric re-fetch** (re-measured this
  pass, probes C:relist-no-verify-roundtrip / C:relist-gated-on-selfreport /
  C:relist-clears-flag / C:relist-pops-names). Relist success is gated on the
  round-trip self-report alone (`routstr_delist.py:626`), and on that self-report
  the run sets `delisted=false` and pops `pulled_models`
  (`routstr_delist.py:633`, `routstr_delist.py:635`). Measured: a relist executes
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
  (`docs:87`; probe C:dryrun-no-confirmed-key confirms the output shape carries
  no `confirmed` key).
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
  never fire acceleration (probes D:absence-quiet-rc0, D:absence-no-remote,
  D:absence-no-preds-error; pinned `tests:176`, `contract:308`). Manual
  override remains available by design (`routstr_delist.py:580`).
- **Garbage — OK.** `_read_preds` never raises, drops non-dict entries
  (`routstr_delist.py:479`) and returns `[]` on any parse failure
  (`routstr_delist.py:481`, `routstr_delist.py:482`). Probes D:garbage-rc1 /
  D:garbage-preds-error / D:garbage-action-none / D:garbage-baseline-intact
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
  stale. Probes D:stale-fresh-false, D:stale-exact-boundary-false (clock
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
  D:manual-not-gated-delist / D:manual-stale-observed → rc 0, `action delist`;
  pinned `tests:980`, `docs:60`).
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
  durable delist flag and runs `pull` only. Impact is loss of protection (a
  baseline can move under a "no side effects" run), never an unsafe delist.
- (**LOW**) (a) `--preds-key` scoping is opt-in and defaults UNSCOPED — filtering
  happens only when the flag is passed (`routstr_delist.py:594`,
  `routstr_delist.py:597`), and `evaluate_triggers` passes no `key` to
  `variance_jumped` (`routstr_delist.py:303`) although the parameter exists for
  that purpose. Probes D:unscoped-default-fires / D:scoped-filter-quiets drive
  `main()` with a mixed feed: with no `--preds-key` the foreign `openrouter`
  variance spike fires the delist, while the pure filter scopes correctly when
  given a key; pinned `tests:776`, documented unconditionally at `docs:56`.
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
