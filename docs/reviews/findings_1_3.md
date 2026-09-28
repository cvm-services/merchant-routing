# Findings 1–3 Review: routstr_delist — nineteenth independent offload pass

Scope (per the original task): finding 1 safety (delisting the routstr SALE must
never disable the routstr provider or touch the T470 flat-router ladder),
finding 2 post-delisting confirmation via an independent re-fetch, finding 3
fail-safe behaviour on an absent / garbage / stale `--preds` monitor feed.

**Artifact-path status (required immediate report).** The task names three
artifacts. `~/.hermes/bot/scripts/routstr_delist.py` (829 lines, md5
`2ea724ef08d857cd…`) and `~/.hermes/bot/tests/test_routstr_delist.py` (752 lines,
md5 `031851b356f0de40…`) are present and byte-identical to repo
`src/routstr_delist.py` and `tests/test_routstr_delist_contract.py`
respectively. **`~/.hermes/bot/docs/routstr_delist_contract.md` is MISSING —
HIGH.** `~/.hermes/bot/docs/` holds only `routstr-delist.md` (197 lines, md5
`e385af98b9c142ee…`, byte-identical to repo `docs/routstr-delist.md`) and
`reviews/`; the contract role is filled by that stand-in doc, read end-to-end
this pass. The missing path is an artifact-provisioning defect, deliberately
reported here in the preamble rather than promoted into one of the three
findings.

**Duplicate-dispatch disclosure.** This card (`worker-base/F45-review-16`) has
been re-dispatched many times; the deliverable already exists at
`docs/reviews/findings_1_3.md` (creating commit `11e40f9`, 37 commits touching
the path to date). Its own convention — and this card's acceptance criterion —
is exactly three `## Finding` sections, so every prior pass **rewrote** the file
in place rather than appending a section. This pass does the same: it re-derives
the three findings from the current artifacts (verified unchanged by md5, not
assumed) and rewrites the file, correcting the immediately-prior revision, which
had drifted to four `## ` sections (an extra "Additional note" section breaking
the exactly-three rule) and had raised Finding 1 to HIGH on an unquoted
`--ssh-target` — a claim the evidence below does not support. Ordinal convention:
the newest commit naming an ordinal is the *eighteenth* pass (`9c67dc9`); this
pass is therefore the **nineteenth** by that convention. Artifacts untouched.

Citation legend: `routstr_delist.py:N` = the script (both copies, byte-identical);
`contract:N` = repo `tests/test_routstr_delist_contract.py` (the 25-case
deployed suite); `tests:N` = repo `tests/test_routstr_delist.py` (the 96-case
main suite); `docs:N` = `docs/routstr-delist.md`.

Verification performed this pass (all hermetic; scratch outside `/tmp`): the
script read end-to-end in both copies; a fresh probe,
`docs/reviews/routstr_f13_probes/probe_f13_pass18.py`, exercising **99 checks**
(A=47 citation audit, B=12 safety, C=12 confirmation, D=28 fail-safe) executed
**twice with byte-identical transcript sha256 `87f2fd8812044c8e…` → 99/99 PASS**;
repo suites `python3 -m pytest tests/ -q` → **121 passed**; deployed suite
`cd ~/.hermes/bot && python3 -m pytest tests/test_routstr_delist.py -q` →
**25 passed** (both with `TMPDIR` off the full `/tmp` tmpfs).

---

## Finding 1 — Safety: SALE-delisting never disables the routstr provider or touches the T470 ladder

severity: **OK** (gaps: LOW)

Every write path the module can take was re-enumerated from source and from
executed payloads this pass:

- **Remote DB — only the `models` (advertisement) table is mutated.** Exactly
  three UPDATE statements exist, all models-only: `routstr_delist.py:355`
  (`UPDATE models SET enabled=0 WHERE enabled=1`), `:361` (blanket
  `UPDATE models SET enabled=1`, legacy fallback), `:394` (parameterized
  `UPDATE models SET enabled=1 WHERE name IN (?,…)`). Two SELECTs exist
  (`:371` name capture, `:408` verify COUNT). Probe B1–B5/C2: all four built
  payloads target `models` and none names `upstream_providers`; no
  INSERT/DELETE/DROP/ALTER/REPLACE appears anywhere.
- **`upstream_providers` / T470 ladder — docstring mentions only.** The string
  occurs exactly three times (`routstr_delist.py:35`, `:352`, `:771`), all in
  docstrings asserting it is NOT touched (probe A5–A7); zero executable
  references.
- **Remote command is one shlex-quoted argv element.** `build_ssh_docker_cmd`
  (`routstr_delist.py:414-425`) quotes the container (`:423`) and payload
  (`:424`) and returns `["ssh", ssh_target, remote]` (`:425`). Probe B6/B7:
  the argv is 3 elements and `shlex.split(cmd[2])` round-trips to
  `docker exec <container> python3 -c <payload>` intact. No local shell is
  involved; only two `subprocess.run` sites exist (`:459` nak publish, `:808`
  ssh) and `shell=True` occurs nowhere (probe B8/B9); pinned by
  `tests:345` (`test_ssh_cmd_is_single_shlex_safe_remote_command`).
- **Blanket relist is refused by default.** With no captured names, `--relist`
  refuses before any remote call (`routstr_delist.py:600-611`, `relist_refused`,
  rc 1); the blanket SQL is reachable only via the explicit `--relist-any`
  opt-in (`:526-528`), pinned `tests:1039` + `tests:1056`.
- **The ladder guard is TESTED semantically.** `contract:468`
  (`TestSemanticGuardLadderUntouched`) builds a real ladder artifact
  (`contract:108`) alongside a live `upstream_providers` table (`contract:129`),
  executes the script's real payloads against it, and asserts the ladder file is
  byte-identical (`contract:480`), the provider rows are unchanged, the routstr
  provider is still an enabled candidate (`contract:486-488`), and that no
  executed payload even names the table (`contract:483`); the scoped-relist
  direction re-asserts ladder byte-identity (`contract:504`). Static scoping
  pins: `tests:303` (pull SQL), `tests:311` (relist SQL), `tests:336` (verify
  payload read-only).

Gaps (LOW, non-blocking): (a) `--ssh-target` / `--container`
(`routstr_delist.py:536-537`) are unvalidated — an operator can point the
mutating payload at another host/container by design; since the value is a
standalone argv element with no local shell, this is a
target-redirection/option-injection surface, not command injection (this is the
claim the prior revision overstated as HIGH; the cited evidence does not support
HIGH). (b) The payloads hard-code `/app/data/keys.db` ×4 (`:370`, `:385`, `:393`,
`:407`) — a container layout change would mutate whatever DB lives at that path.
(c) `save_state`'s return value is ignored at all eight call sites (`:565`,
`:622`, `:629`, `:638`, `:654`, `:710`, `:732`, `:752`) — a failed write after a
CONFIRMED delist (`:752`) would silently diverge local state from remote reality
(cross-ref finding 4).

---

## Finding 2 — Confirmation: delist success is gated on an independent read-only re-fetch

severity: **OK** — requirement MET; residual: **MEDIUM** (relist has no symmetric re-fetch), LOWs itemized

- **The confirmation mechanism.** `verify_pull_payload()` (`routstr_delist.py:400-411`)
  is a read-only `SELECT COUNT(*) FROM models WHERE enabled=1` (`:408`) with no
  UPDATE anywhere (probe C2). It runs as a SEPARATE ssh round-trip via
  `_SshBackend.verify` (`:790-793`), invoked at `:682` after the pull inside the
  attempt loop (`:671-697`). Success requires
  `vres.get("ok") is True and vres.get("count") == 0` (`:683`); only then is
  `confirmed` set (`:687`) and the durable `delisted=true` written (`:747-752`,
  rc 0 at `:764`).
- **A lying pull is refuted.** Probe C1: a pull that self-reports ok while the
  re-fetch still counts advertised models is forced to failure (`:691-694`),
  retried once in-run (`MAX_PULL_ATTEMPTS = 2`, `:75`), and on exhaustion takes
  the failure branch (`:719-739`: `delisted` stays false at `:726`, baseline not
  consumed, breaker tick) → rc 1, executed kinds `["pull","verify","pull","verify"]`,
  `consecutive_failures == 1`. Pinned `contract:346`
  (`test_unverified_pull_is_a_failed_delist`), `tests:567`
  (`test_verify_gates_success`), `tests:603`
  (`test_verify_failure_is_attempt_failure`). The happy path (probe C2) is
  exactly one pull + one verify → rc 0, `delisted=true`, `pulled_models`
  captured, `verified_count=0`.
- **Parse/transport robustness fails safe.** `_SshBackend._run` (`:795-825`)
  accepts only `proc.returncode == 0 and data.get("ok") is True` (`:822`), so a
  non-zero rc, unparseable stdout, or a missing `ok`/`count` key yields a
  non-confirming result (`None == 0` is False) — garbage can only fail the run,
  never confirm it (pinned `tests:1107-1151`).

Residual — **MEDIUM: the relist path has no symmetric re-fetch.** Relist success
is gated on the round-trip self-report alone (`routstr_delist.py:626`), and on
that self-report the run sets `delisted=false` and pops `pulled_models`
(`:633-635`). Probe C3: a confirmed relist executes `kinds == ["relist"]` only —
no verify round-trip — and destroys the stored scoped name set. A lying relist
(rc 0, ok printed, UPDATE not landed — the same fault class the contract deemed
must-fix for delist) therefore fakes a restored listing AND destroys the scoped
names, forcing a subsequent scoped `--relist` to be refused (`:600-611`) and
recovery through `--relist-any` (which re-enables rows the operator had
deliberately disabled, `docs:29-32`). The contract mandates the re-fetch only for
"a fired delist" (`docs:69-75`), so this is an asymmetry, not a contract breach;
the fix is cheap (verify `COUNT(*)>0` or re-read the names before popping).

LOW notes: (a) dry-run sets `confirmed=True` with no remote verify
(`:679-681`) — intent-only, nothing remote to confirm (`docs:87-89`);
(b) the verify round-trip shares the ssh transport and last-line JSON parsing
with the pull (`:810-822`), so a systematic transport-level fault could satisfy
both — failure direction remains safe (a fooled verify only keeps the run
failing toward the breaker).

---

## Finding 3 — Fail-safe: absent, garbage, and stale monitor feed

severity: **OK** — residuals: **MEDIUM** (dry-run quiet-path state write), LOWs itemized

Every branch that can reach a delist runs through
`fire = args.delist or dec["fire"]` (`routstr_delist.py:649`), where
`dec["fire"] = bool(accel or var or override)` (`:317`). Enumerated and probed:

- **Absence — OK.** No `--preds` → `raw_preds=[]` (`:581`), quiet run;
  acceleration requires non-empty preds on both sides (`:107`), variance
  requires non-empty preds (`:143`); a first run with no baseline can never fire
  acceleration (probe D10; pinned `tests:176`, `contract:308`). Manual override
  remains available by design.
- **Garbage — OK.** `_read_preds` never raises, drops non-dict entries (`:479`)
  and returns `[]` on any parse failure (`:481-482`). Probe D12 (deployed copy):
  a malformed feed → rc 1, `preds_error=true`, `action none`, no remote action,
  and the stored baseline `{"zai\x1f1h": 10.0}` intact (`update_state` only
  overwrites the snapshot when preds is non-empty, `:261-262`; pinned `tests:243`,
  `tests:547`, `tests:995`). Type guards: `uncertainty` is isinstance-guarded with
  bool explicitly excluded (`:152-153`; probe D6–D8; pinned `tests:146`), and
  `exhausts_in_hours` is guarded (`:193-196`).
- **Stale — OK (was the original HIGH hole; now guarded).** `STALENESS_S = 1800`
  (`:78`); `feed_is_stale` is mtime-based and fails closed — undeterminable age
  (`OSError`) returns True (`:495`), a future mtime is stale (`:494`, expression
  `not (0 <= age <= max_age_s)`). Probe D1–D5: fresh → False, **exact boundary
  1800 s → False (inclusive)**, 1801 s → True, future mtime → True, missing path
  → True. Wiring: a stale feed zeroes the preds before trigger evaluation
  (`:589-592`), so even the level-based variance trigger cannot fire on dead
  data, and before any baseline refresh. Probe D13: variance-elevated (0.99) but
  2 h-old feed → rc 1, `action none`, `preds_stale=true`, zero remote calls;
  pinned `tests:937`, `tests:995`. `preds_stale` is surfaced in every output
  branch (`:657`, `:714`, `:735`, `:762`) with rc 1 when quiet (`:660`). The
  manual override is deliberately never gated on freshness (`:580` order,
  `docs:60`; probe D14: stale feed + `--manual` → rc 0, `action delist`; pinned
  `tests:980`, `contract:427`).
- **Breaker interaction (cross-ref finding 6).** Repeated failed runs refuse all
  further remote action (`:724-731`, `:569-578`, exit 3) until `--unblock`
  (`:561-567`); dry-run never counts toward it (`:699-717`, `tests:514`).

Residual — **MEDIUM: dry-run purity is conditional on firing.** `docs:87-89`
and the firing path (`:699-717`) promise a dry run consumes no acceleration
baseline and records `last_dry_run`. The QUIET branch (`:651-654`) has no
`--dry-run` guard: probe D15 passes `--dry-run` with a quiet (11 h) feed against a
12 h baseline → rc 0, and the stored snapshot is refreshed to 11.0 with **no**
`last_dry_run` recorded, i.e. the dry run silently perturbed durable state and
left no trace. Impact is loss of protection (a baseline can move under a "no
side effects" run), never an unsafe delist.

Residuals (LOW): (a) `--preds-key` scoping is opt-in and defaults UNSCOPED —
filtering happens only when the flag is passed (`:594-597`), and
`evaluate_triggers` passes no `key` to `variance_jumped` (`:303`) although the
parameter exists for that purpose (`:132`, `:147`); probe D11 shows the function
does filter when given a key, so the residual is operator-omission on an
unwired deployment, and `docs:54-55` states the guarantee unconditionally where
it should say "with `--preds-key`". (b) mtime-only freshness (`:485-494`): a
writer that rewrites `preds.json` with old data refreshes the mtime and bypasses
the guard. (c) Cosmetic: `_hours` accepts bool (`:193-196`; probe D9) while the
variance guard excludes it (`:152-153`) — arithmetic-safe; the override marker is
presence-based with no TTL (`:164-172`), operator-controlled by design.
(d) Cross-ref finding 4: the quiet-run state write (`:654`) ignores the
`save_state` return value.
