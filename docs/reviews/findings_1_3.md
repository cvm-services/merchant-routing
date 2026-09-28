# Offload review — routstr delist, findings 1–3 (safety, confirmation, fail-safe)

Eleventh independent offload pass for findings 1–3, re-derived against the
CURRENT artifacts. Nothing below is carried over unverified from the earlier
passes: the deployed script was read end-to-end (829 lines, md5
`2ea724ef08d857cd7b88a957300e70b4`, measured this session), the deployed test
suite was read end-to-end (752 lines, md5 `031851b356f0de4089512f02f13f05cc`),
the freeze document was read end-to-end (197 lines), and **49 fresh hermetic
probe checks** were then executed against the DEPLOYED script copy — see
`docs/reviews/routstr_f13_probes/probe_f13_pass11.py`, run
`TMPDIR=$HOME/.cache/rp11-pass/tmp python3 …/probe_f13_pass11.py` → **49/49
PASS**, reproduced twice in a row (order-spanning). Group tally printed by the
harness, not typed by hand: `A=19 B=13 C=17 total=49`.

Scope, per the original task: item 1 (safety: delisting the SALE must never
disable the routstr provider or touch the T470 flat-router ladder), item 2
(post-delisting confirmation via re-fetch), item 3 (fail-safe behaviour on
absent, garbage, and stale monitor signals). "Monitor file" maps to the
script's `--preds` feed; "T-A signal" maps to `predict_exhaustion()`-shaped
feed entries.

**Why this is a re-derivation and not a fourth section — duplicate-dispatch
disclosure.** The deliverable already existed at dispatch time: repo
`docs/reviews/findings_1_3.md` is committed at `396a60f` ("tenth-pass offload
re-derivation"), byte-identical to the bot copy (both md5
`4ae24a1a37075490f6848bcb933219b2`, 25 541 B) — this is the 11th dispatch of
this card (`git log --diff-filter=A` → `11e40f9`, then 10 further commits on
the same path). The file's own convention keeps **exactly three `## Finding`
sections** and the acceptance criterion repeats that ("exactly three
sections"), so appending a `§N DUPLICATE-DISPATCH RE-VERIFICATION` block — the
convention used for the FD2/merge-pass series on other boards — would violate
the artifact's shape. The divergence is therefore recorded here, in the
preamble, and the three findings are **re-derived from primary sources** for
this pass. Disclosed cost: none — no number below is copied from a prior pass.

**Artifact-path status (required report per task instructions):**

- `~/.hermes/bot/docs/routstr_delist_contract.md` — **MISSING — HIGH.**
  Re-verified this session: the path does not exist and the directory listing
  of `~/.hermes/bot/docs/` contains only `routstr-delist.md` and `reviews/`.
  A tree-wide search (`find ~/.hermes/bot -maxdepth 3 -name '*contract*'`)
  returns zero hits. The contract role is filled by the stand-in
  `docs/routstr-delist.md` (repo copy `docs/routstr-delist.md` and bot copy
  `~/.hermes/bot/docs/routstr-delist.md`, both 197 lines, byte-identical).
  This is the same HIGH reported by every prior pass at this path; it is
  **not** re-litigated into one of the three findings below because it is an
  artifact-provisioning defect, not a defect in the script or its tests.
- `~/.hermes/bot/scripts/routstr_delist.py` — **present** (829 lines), md5
  `2ea724ef08d857cd7b88a957300e70b4`, equal to repo `src/routstr_delist.py`
  (probe A0a). All `routstr_delist.py:N` references below apply to both copies.
- `~/.hermes/bot/tests/test_routstr_delist.py` — **present** (752 lines), md5
  `031851b356f0de4089512f02f13f05cc`, equal to repo
  `tests/test_routstr_delist_contract.py` (probe A0b). The loader fallback at
  `:47-54` resolves `../scripts` when `../src` is absent, so the bot copy runs
  against the deployed script.

Conventions: `routstr_delist.py:N` = the script (both copies); `contract:N` =
repo `tests/test_routstr_delist_contract.py` (the 25-case deployed suite);
`tests:N` = repo `tests/test_routstr_delist.py` (the 96-case main suite);
`docs:N` = `docs/routstr-delist.md`.

**Suite evidence.** Repo `python3 -m pytest tests/ -q` → **121 passed in
1.37 s**; deployed `cd ~/.hermes/bot && python3 -m pytest
tests/test_routstr_delist.py -q` → **25 passed in 0.90 s**. Both numbers match
the tenth pass, and both are only obtainable **with `TMPDIR` off the default
tmpfs**: `/tmp` on this host is a 5.5 G tmpfs at **100 % (4.0K free)**.
Probes therefore ran from `~/.cache/rp11-pass`.

**Artifacts untouched.** No file under `~/.hermes/bot/docs/`,
`~/.hermes/bot/scripts/`, `~/.hermes/bot/tests/`, `src/`, `tests/`, or
`docs/routstr-delist.md` was modified by this pass.

---

## Finding 1 — Safety: SALE-delisting vs disabling the routstr provider — severity: **OK** (gaps: **LOW**)

**Claim under test.** Delisting the routstr SALE (the advertised model listing
on the sell node) must never disable the routstr *provider* and must never
touch the T470 flat-router ladder.

**Evidence (all re-measured this pass).**

1. **The only SQL the module can execute is scoped to `models`.** A fresh AST
   measure (not a hand-typed list) finds exactly **5** executable
   models-SQL literals in the deployed script and **0** naming
   `upstream_providers` (probe A1a/A1b, lines `[355, 361, 369, 392, 406]`):
   - `routstr_delist.py:355` — `pull_listing_sql()` →
     `UPDATE models SET enabled=0 WHERE enabled=1;`
   - `routstr_delist.py:361` — `relist_sql()` → `UPDATE models SET enabled=1;`
     (legacy blanket fallback, reachable only via `--relist-any`)
   - `routstr_delist.py:369-375` — `pull_listing_payload()` → `:371`
     `SELECT name FROM models WHERE enabled=1` then the `:355` UPDATE
   - `routstr_delist.py:392-397` — `relist_payload(names)` → `:394`
     `UPDATE models SET enabled=1 WHERE name IN (?,…)`
   - `routstr_delist.py:406-411` — `verify_pull_payload()` → `:408`
     `SELECT COUNT(*) FROM models WHERE enabled=1`
2. **`upstream_providers` is never mentioned in executable code.**
   It occurs 3× in the module — `:35`, `:352`, `:771` — and the probe
   classified **all three as docstring context**, zero as code (probe A2a).
3. **Executable semantic guard, not a code-reading claim.** The REAL pull
   payload was executed against a stand-in sell node carrying **both** tables.
   After a confirmed delist: the ladder artifact is **byte-identical**
   (340 B, probe A4b), the `upstream_providers` rows are identical
   `[('openrouter',1,20.0), ('routstr',1,10.0), ('zai',1,30.0)]` (A4c), the
   `routstr` provider is still an **enabled ladder candidate** (A4d), and —
   proving the delist really happened — every advertised `models` row is
   disabled while the pre-disabled row stayed disabled (A4e). The repo freeze
   suite pins the same property at `contract:468-488`
   (`TestSemanticGuardLadderUntouched`).
4. **No widened blast radius.** Exactly **2** `subprocess.run` sites
   (`routstr_delist.py:459` nak publish, `:808` ssh), **0** `shell=` keywords,
   **0** `eval`/`exec` call sites (probes A3a/A3b). The remote command is
   built once at `:414-425` and passed as argv with `shlex.quote` on the
   container and payload, so no local shell is involved.
5. **The inverse direction cannot enable operator-disabled rows by accident.**
   `:600-611` refuses with `relist_refused` / rc 1 / **zero remote calls** when
   no captured name set exists; `--relist-any` (`:526-528`) is the explicit
   opt-in. Measured (A5a: `rc=1 calls=[]`), the refusal leaves
   `operator-disabled-model` off (A5b) and writes no `delisted` flag (A5c).
   The scoped relist restores exactly the advertised set (A6a, `restored=3`),
   keeps the pre-disabled row off (A6b), and leaves the ladder byte-identical
   (A6c).
6. **`--dry-run` cannot disable anything**: the fired dry-run path executes no
   remote round-trip at all (`:699-717`; measured — zero recorded calls, probe
   B5a).

**LOW gaps (none severity-bearing).**

- **L1 — unvalidated remote target.** `--ssh-target` (`:536`) and
  `--container` (`:537`) are free text; a typo redirects the `docker exec` to
  a different container on the same host. Operator-side mitigation only.
- **L2 — hardcoded DB path.** `/app/data/keys.db` is inlined in 4 payloads
  (`:370`, `:385`, `:393`, `:407`).
- **L3 — the `models` predicate is table-wide, not routstr-row-scoped.**
  `:355` disables *every* enabled `models` row. On a sell node that also
  advertises non-routstr listings, those rows would be pulled too. The target
  here is the dedicated `routstr-public` container (`:87`), so this is latent,
  not live.
- **L4 — cleared, not a defect.** docs:21 cites `TestSaleNotProvider`; that
  class does exist, at `tests/test_routstr_delist.py:302`. Verified rather
  than assumed, in both directions.

---

## Finding 2 — Post-delisting confirmation via re-fetch — severity: **OK** (requirement **MET**; residual **MEDIUM**: relist has no symmetric re-fetch; LOWs itemized)

**Claim under test.** A delist must be confirmed by an independent read-back,
never by the pull round-trip's own self-report.

**Evidence (all re-measured this pass).**

1. **The confirmation round-trip is independent and read-only.**
   `routstr_delist.py:400-411` (`verify_pull_payload`) issues only
   `SELECT COUNT(*) FROM models WHERE enabled=1`; probe B1a confirms the
   payload contains **no** `UPDATE`/`INSERT`/`DELETE`/`DROP`/`ALTER`
   (B1b confirms the count query). It is reached via
   `_SshBackend.verify()` at `:790-793`, a separate round-trip from the pull.
2. **Success is gated on the re-fetch, not the self-report.** `:682-688`
   requires `vres.get("ok") is True and vres.get("count") == 0` before setting
   `res["confirmed"] = True`; `:689-694` overwrites a self-reported `ok` with
   `ok=False, confirmed=False` when the re-fetch refutes it.
3. **Executed refutation of a lying pull.** With the UPDATE never landing
   (rc 0 and `ok` printed anyway), the run ended `delist_failed`, **rc 1**,
   `verify.count == 3`, call kinds exactly
   `["pull", "verify", "pull", "verify"]` — one bounded in-run retry
   (`MAX_PULL_ATTEMPTS = 2`, `:75`) — with state `delisted=False` and
   `consecutive_failures=1` (probes B2a–B2d). The freeze suite pins the same
   at `contract:346-360`.
4. **Happy path.** rc 0, `confirmed=True`, `verified_count=0`, exactly one
   `pull` + one `verify` (B3a/B3b), durable `delisted=true` with
   `pulled_models` equal to the captured advertised set (B3c, `:747-752`).
5. **Failure semantics hold.** An unconfirmed delist does **not** consume the
   acceleration baseline and does **not** set `delisted=true` (`:719-739`).
   Dry-run confirmation is intent-only: `:679-681` sets `confirmed` locally
   with zero remote reads (B5a/B5b).

**Residual MEDIUM (re-measured by execution this pass, unchanged in substance).**

- **M1 — the relist direction has no symmetric re-fetch.** Probe **B4a**:
  `--relist` executed with call kinds exactly `["relist"]` — **no `verify`
  round-trip ever follows it**. Its success is gated only on the backend's own
  self-report (`:626` `if not res.get("ok")`), i.e. on the `{"ok":True,
  "restored":N}` line the relist payload prints at `:396`. A relist that
  reports success while the UPDATE does not land would set `delisted=False`
  (`:633-634`) and then `state.pop("pulled_models", None)` (`:635`),
  **destroying the scoped name set** — after which a corrective `--relist`
  hits the refusal at `:602-611` and requires the blanket `--relist-any`
  (`:526-528`). This is the exact mirror of the defect Finding 2 closed for the
  delist direction, so the asymmetry is a genuine, measured residual rather
  than an inference from prose. **Not a BLOCKER/HIGH**: the relist is an
  operator-initiated recovery action, whereas the delist is the automated
  path, and the failure is loud (rc 1 at `:632`) rather than silent.

**LOW.**

- **L5 — dry-run confirm is intent-only.** `:679-681` short-circuits before
  any remote read, so `--dry-run` reports `confirmed` purely from intent. This
  is deliberate (dry-run purity, `:699-702`) and correctly labelled in the
  output, but `confirmed` in a dry-run carries no verification meaning.

---

## Finding 3 — Fail-safe on absence, garbage, staleness — severity: **OK** (residuals: **LOW**)

**Claim under test.** An absent, garbage, or stale monitor signal must fail
safe: it must never drive a delist and must never wipe the stored baseline.

**Evidence (all re-measured this pass).**

1. **Absent feed.** `_read_preds` returns `[]` on any failure
   (`routstr_delist.py:473-482`). An explicitly-given feed that yields nothing
   sets `preds_error` at `:585`, and the run exits non-zero when nothing fired
   (`:651-660`).
2. **Staleness fails closed, not open.** `feed_is_stale` (`:485-496`) returns
   `not (0 <= age <= max_age_s)`, so an **undeterminable age is stale**. Five
   states measured with real mtimes (probe C1): absent → stale; aged 3600 s →
   stale; **future mtime → stale** (a negative age is not freshness); fresh →
   not stale; boundary exactly `STALENESS_S` → not stale (the range is
   inclusive).
3. **A stale feed can neither fire nor poison the baseline.** `:589-593`
   blanks the parsed preds when stale. Probe C3a: no fire, `preds_stale=true`,
   rc 1, **zero remote calls**. Probe C3b: the stored snapshot is **unchanged**
   — it still holds the prior 10.0 h, not the stale feed's 1.0 h — because
   `update_state` only rewrites the baseline `if preds:` (`:261-262`).
4. **A garbage feed cannot wipe the baseline either.** Probe C2a/C2b: rc 1,
   `preds_error=true`, `action="none"`, and the stored snapshot is **identical**
   to its pre-run value.
5. **Type guards stop a malformed feed from firing.** Non-dict entries are
   dropped (`:479`, probe C4a); `uncertainty` must be a non-bool number
   (`:152-153` — probe C4b: `str`/`bool`/`None` all yield **no** fire);
   non-numeric `exhausts_in_hours` yields no acceleration (`:193-196`, probe
   C4c). Pinned at `contract:146-151`.
6. **Manual override is deliberately not gated on freshness** (`:580`).
   Probe C5a: a stale feed plus `--manual` delists, with `preds_stale=true`
   observed but not obeyed — matching `docs:60`.
7. **An exhausted action budget fails closed before spawning.** Probe C7:
   `ok=False`, `error="action budget exhausted"`, **zero** subprocess calls
   (`:800-806`).

**Residuals LOW.**

- **L6 — `--preds-key` defaults to unscoped.** `:513-515` documents it as an
  opt-in, and `evaluate_triggers` passes **no** key to `variance_jumped`
  (`:303`), so with the flag omitted an unrelated provider's variance spike
  fires the routstr delist. Probe C6a measured a delist from an
  `openrouter`-only feed with no `--preds-key`; C6b confirmed
  `evaluate_triggers` applies no implicit key filter; C6c confirmed
  `--preds-key zai` makes that same feed quiet. `docs:54-55` states the
  scoping benefit without flagging that the default is unscoped. Deployment
  mitigates it: the documented cron line (`docs:106`) passes
  `--preds-key zai`.
- **L7 — freshness is mtime-only** (`:492-494`). A writer that touches or
  rewrites a file without changing its contents makes stale data look fresh.
- **L8 — the flag pair `preds_error=true` / `preds_stale=false`.** Staleness
  is only evaluated when the feed parsed to something (`:589-590`), so a
  garbage **and** aged feed reports `preds_stale=false`. Behaviour is still
  safe (rc 1 via `preds_error`), but the pair reads misleadingly in
  `--status`/log triage.
