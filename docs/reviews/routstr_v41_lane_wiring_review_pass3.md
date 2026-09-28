# Cross-family cold review — routstr v4.1 lane wiring + routstrd service/guard IaC
## PASS 3 — cross-family re-derivation (different family from the author)

reviewer_model: tier/review-kimi (provider: zai) — kimi family
author_family: deepseek (workers deleg_17f47ac6 task0/1 + task2) — deepseek family
cross_family: SATISFIED (author deepseek != reviewer kimi). This reviewer authored none of the
              reviewed commits and read no author narrative beyond the brief's own claim list.
date: 2026-09-27
worker_host: dq05 / c03rad0r-DQ05proplus (100.90.22.201)
live_state_host: cobrador / CobradorWave (100.90.101.9)
review_mode: cold. Every claim below was re-derived this session from git objects, deployed bytes,
             the live lane host, and re-run suites. Where the brief and my measurement disagree,
             both numbers are printed.
artifact: ~/reports/reviews/merchant-routing-routstr-v41-lane-wiring-kimi-pass3.md
          == repo docs/reviews/routstr_v41_lane_wiring_review_pass3.md
tid: NOT RESOLVABLE from this worker (same outcome as passes 1 and 2). No kanban toolset is present
     in the session; HERMES_KANBAN_BOARD=default holds only plebeian tasks, `hermes kanban list
     --mine` on the default board is empty, board llm-routing holds no routstr/v4.1 card, and the
     card-id sweep of the remaining boards was denied by the operator mid-run. The filename
     therefore carries the scope slug, exactly as passes 1 and 2 did. No card comment was posted.
predecessors (inputs, not outputs — both are also kimi-family, i.e. same family as this reviewer):
     pass 1 ~/reports/reviews/merchant-routing-routstr-v41-lane-wiring-kimi.md
     pass 2 ~/reports/reviews/merchant-routing-routstr-v41-lane-wiring-kimi-pass2.md
     Nothing from either pass is carried as evidence here; where they agree with me it is because I
     re-measured it, not because they asserted it.

---

## 0. SHA reconciliation — done FIRST (diff-vs-claim, never title-vs-diff)

Re-derived this session. Command + raw output: review-rv41/ev/final_facts.txt.

| item | brief says | git actually shows (2026-09-27) |
|---|---|---|
| hermes-orchestration tip | "both merged to master, latest master = a81041ee5" | origin/master = **bb587eb3** ("Merge pull request #172 … pr/reports-cred-watchdog-src"). The cited SHAs are **not** ancestors of origin/master; the same two subjects landed as **67e0f1b7** and **c7be49ad**, both ancestors of origin/master, both present on master. |
| merchant-routing-engine | "8b91148 merged to main" | refs/heads/main == refs/remotes/github/main == **8b91148**, and it is the tip. VERIFIED. |
| diff identity | — | flat_router.py blob is **identical** at 34aa21ac == a81041ee == origin/master (sha 449ddbc1, md5 1dc1091b). zai_proxy.py differs: a81041ee 57e11a80 vs origin/master 4c4afa17 — **4 insertions / 3 deletions**, and it is the Phase-M z.ai "friend" key removal in `_load_keys()` only; the routstr/routstrd translation table is byte-identical across both refs. roles/51-routstrd-lane/defaults/main.yml differs by **2 lines** (see M1). |

Deployed-artifact identity (md5):

| artifact | md5 | equal to origin/master blob? |
|---|---|---|
| cobrador ~/.hermes/bot/flat_router.py | 1dc1091bd4d264edbfe2c0e9cae89454 | YES |
| cobrador ~/.hermes/bot/zai_proxy.py | c2f13451b527acdba70861224a966287 | YES |
| dq05 (this worker) ~/.hermes/bot/flat_router.py | 4a74a2b49c2128023e822e873c4705d8 | **NO** |
| dq05 (this worker) ~/.hermes/bot/zai_proxy.py | 376f201f576b123c091ff15e8f577713 | **NO** |
| merchant-routing-engine scripts/routstrd_funding_guard.py | fec2e50a6840517f3f19f4e4a5a4d55f | == 8b91148 (blob 326c302c) |

The brief's "deployed md5 == origin/master blob" is true **for the lane host only** (CobradorWave);
it is false on dq05 (minor m3).

---

## 1. Per-claim verdicts

| # | claim | verdict | basis |
|---|---|---|---|
| 1a | canonical `deepseek/deepseek-flash` added to PROVIDER_MODELS for routstr + routstrd | **VERIFIED** | deployed bytes (== origin/master) flat_router.py:311-330; suites re-run |
| 1b | `_PROVIDER_MODEL_NAMES` translates it to the network id `deepseek-v4.1-flash` (DOT) | **VERIFIED** | zai_proxy.py:969-973 (deployed == master); wiring test 28 passed |
| 1c | check the id against the live lane (`curl http://localhost:8008/v1/models`) | **UNVERIFIABLE-NOW** (lane down) — corroborated | see §3 |
| 2a | a dispatch arm exists for both lanes (ollama_cloud_4 class of bug) | **VERIFIED** | `_make_dispatch_fn` → `_dispatch_external` (+ EXTERNAL_PROVIDERS base_url) for both lanes; wiring test §(d) |
| 2b | live `select_provider('deepseek/deepseek-flash')` shows both lanes as eligible-but-`inf` | **UNKNOWN** (author-reported; not re-derived) | see §3 |
| 3a | systemd --user routstrd.service with bounded Restart | **VERIFIED** | role template + live unit (`StartLimitIntervalSec=300`, `StartLimitBurst=5`, `Restart=always`) |
| 3b | linger | **VERIFIED** | role task + live `Linger=yes` |
| 3c | wallet pinned to ~/.routstrd/wallet | **VERIFIED** | unit `Environment=ROUTSTRD_DIR=%h/.routstrd` + `ROUTSTRD_WALLET_DIR=%h/.routstrd/wallet` (live unit :65-66) |
| 3d | RequiresMountsFor resolved mount | **VERIFIED (shape)**, see m2 | render probe reads `readlink -f` + `findmnt`; live unit pins `/mnt/dq05-lexar …` |
| 3e | a SECOND apply must be changed=0 | **VERIFIED at the cited head / REFUTED at merged master** | harness run1 changed=4 / run2 changed=0 (rc 0), but ~1/3 of the role is skipped and at master the role aborts — M1 |
| 3f | no path can fall back to the empty ~/.cocod/coco.db | **VERIFIED in code+unit**; daemon-side precedence UNKNOWN | unit pins both env vars; no non-comment `~/.cocod` in the repo; consumers repointed |
| 3g | *operational* intent: the lane is up / boot-recoverable on the lane host | **REFUTED (live)** | 203/EXEC, restart budget exhausted, `StartLimitAction=none`, port 8008 free — M2 |
| 4a | guard reads the migrated wallet | **VERIFIED** | live `--balance-json` rc 0, `wallet_db=~/.routstrd/wallet/coco.db`, `source=db` |
| 4b | per-mint, excludes the orangesync testnut from network_sats | **VERIFIED** | live payload: balances{minibits 35514, orangesync 5000}, `network_sats=35514`, `testnut_mint=…orangesync.tech` |
| 4c | FAILS LOUD (non-zero) on an unreadable/empty wallet instead of reporting 0 sats | **VERIFIED for unreadable/empty; hole for wholly-absent wallet** | rc 2 for missing DB (dir present) and for the 0-table legacy file; rc 0 for a host with no wallet at all (m6) |
| 4d | "a read-only sqlite URI does not replay WAL — check the technique" | **TECHNIQUE CORRECT**; the generalisation is imprecise | guard copies db+wal+shm, opens the copy RW, `wal_checkpoint(TRUNCATE)`. Measured on the live wallet: immutable=1 → 35 508 (96 proofs, **WAL-blind**), `mode=ro` → 35 514, copy+checkpoint → 35 514 (98 proofs) == the guard's own read |
| 5a | `scripts/engine/test_routstr_v41_lane_wiring.py` | **28 passed** (GREEN) and the RED-first claim is real | reverted the 2 hunks in a scratch worktree → **9 failed / 19 passed**, exactly the commit message's RED |
| 5b | `tests/test_routstrd_lane_role.py` | **27 passed at a81041ee; 1 failed / 26 passed at origin/master** | failure = `test_funding_guard_paths_are_the_restored_ones` (asserts the now-templated literal) |
| 5c | `tests/run_routstrd_lane_idempotency.sh` | **PASS rc 0** (run1 changed=4 failed=0, run2 changed=0 failed=0) | with the coverage caveats in m2 |
| 5d | merchant-routing-engine guard suite (`tests/test_routstrd_funding_guard.py`) | **32 passed**; RED-first real | new tests against 8b91148^ → **25 failed / 2 passed / 5 errors** |
| 5e | merchant-routing-engine guard test — balance cron (`tests/test_routstrd_balance_cron.py`) | **1 failed / 2 passed** (RED at 8b91148) | `test_missing_wallet_fails_loudly_and_writes_no_row`: expects "read FAILED", the code path prints "routstrd wallet not present on this host"; rc 1 and zero rows still hold, so the substance is fine and the assertion is stale |

Reading of claim 5 as a whole: **PARTLY REFUTED.** Five suites were re-run; three are green at the
head that owns them, but **two shipped tests are RED at their own merged heads**, and the
orchestration-side fault was introduced by 37d6b55f (a commit later than the ones under review,
which is what actually *shipped* in role 51).

---

## 2. Findings

### MAJOR

**M1 — role 51-routstrd-lane cannot converge at merged master; the funding-guard path expression
does not template under the shipped deploy shape.**
`roles/51-routstrd-lane/defaults/main.yml:101-102` at origin/master read
`"{{ ansible_user_dir | default('/home/' + ansible_user_id) }}/…"` (delta introduced by **37d6b55f**,
the Phase-Q "target-user cleanup"). Under `gather_facts: false` — which is exactly how the playbook
that owns this role runs it (`playbook-live-router.yml:13`, `hosts: fleet`, roles 29 + 51) —
`ansible_user_dir` is undefined, so Jinja evaluates `default()`'s argument, and `ansible_user_id` is
undefined too → hard error. Proven two ways this session:
  * expression probe (`probe_template.yml`): `fatal: … Error while resolving value for 'msg':
    'ansible_user_id' is undefined`; the same probe with `gather_facts: yes` renders fine. The
    sibling shape `ansible_user_id | default(lookup('env','USER'))` (what the role's own linger
    tasks use) works; the `ansible_env.HOME | default('/home/' + ansible_user_id)` shape used by
    roles 54/52/51-kanban-git fails identically under no-facts.
  * shipped-role probe (`run_role_path_probe.sh`, side-effect-free fixture, no var overrides):
    `roles/51-routstrd-lane/tasks/main.yml:245` "Stat the funding guard" →
    `fatal: … Error while resolving value for 'path': 'ansible_user_id' is undefined`,
    `failed=1`, **PLAYBOOK rc=2**.
Operator consequence: the focused live-router deploy aborts on every fleet host and the funding-guard
cron can neither be installed nor repaired. Note the irony: 37d6b55f added
`tests/test_no_target_user_literals.py` (4 passed) that *requires* `ansible_user_dir` to appear in
this file, and left the pre-existing `tests/test_routstrd_lane_role.py::test_funding_guard_paths_are_
the_restored_ones` behind asserting the old literal — so one test now demands the change and another
demands the old value. This is why the brief's "latest master = a81041ee" matters: at **a81041ee the
role's tests are 27/27 green and the role converges**; the failure belongs to the merged tip.

**M2 — the lane service on the lane host is dead AND cannot self-heal; the mount pin is a
host-specific path into a dead sshfs mount.**
Live on CobradorWave (ev/live_cobrador.txt, ev/live_probe2.txt):
`/home/c03rad0r/.bun -> /mnt/dq05-lexar/cw-offload/bun` (dangling; `mnt-dq05\x2dlexar.mount` is
`loaded inactive dead`), so `ExecStart=/mnt/dq05-lexar/cw-offload/bun/bin/bun …` →
`Unable to locate executable … (203/EXEC)`, `NRestarts=9`, journal ends with
`Start request repeated too quickly` / `Failed to start routstrd.service` at 2026-09-26 23:25:48.
`StartLimitAction=none` → systemd will not retry again without a manual `reset-failed`; port 8008 is
free and no routstrd process exists. So the wiring is correct in code and simultaneously serving
nothing. The role's mount resolution is honest (it pins what `readlink -f`+`findmnt` resolved at
converge time — live unit `RequiresMountsFor=/mnt/dq05-lexar /mnt/dq05-lexar/cw-offload/bun`, and
the harness's own render shows it following the toolchain), but it pinned a *remote host's* mount
path onto this node, and when that mount went away the unit had no recovery path.

**M3 — the restored funding-guard cron is present but inert, and its own gate prevents repair.**
Live crontab (ev/live_cobrador.txt:100-101):
`#Ansible: routstrd-funding-guard` / `*/5 * * * * /home/c03rad0r/merchant-routing-engine/scripts/
routstrd_funding_guard.py >> /home/c03rad0r/merchant-routing-engine/logs/…log 2>&1`.
On that host `~/merchant-routing-engine -> /mnt/dq05-lexar/cw-offload/merchant-routing-engine` is a
**dangling symlink** (target MISSING), the log path does not exist, and there is no
`~/.hermes/bot/routstrd_funding_guard.log` either. So the job exits non-zero into a log that cannot
be created: the wallet is unguarded and the failure is invisible. It also will not be repaired by a
re-converge, because the cron task is gated on `routstrd_funding_guard_stat.stat.exists` (role test
`test_cron_is_gated_on_the_script_existing_and_on_the_test_gate`) — the script does not exist, so the
task is skipped and the broken entry stays as-is. Combined with M1 the repair path is also blocked.
The guard's own state file is stale (`.routstrd_funding_guard_state.json`, 112 bytes, 2026-08-22).

**M4 — the balance evidence disagrees with itself and the brief quotes the WAL-blind number.**
Live wallet on the lane host: `coco.db` 630 784 B + `-wal` 168 952 B + `-shm` 32 768 B. Three readers
of the *same* file, this session: immutable=1 → **35 508** sats / 96 proofs; `mode=ro` → 35 514;
copy+checkpoint → **35 514** / 98 proofs (= the guard, = the brief's "+5 000 orangesync" neighbour).
The brief's "wallet 35,508 sats minibits" is therefore the WAL-blind reading; the authoritative one is
35 514. Separately, the author's own measurement artifact
(`~/reports/routstr-measure-2026-09-26.json`) records `wallet_before_msats: 7000` →
`wallet_after_msats: 6677` for the same wallet in the same week — that is 7.0 sats if msats is right,
or 7 000 sats if it is a mislabel. Either way it does not reconcile with 35 514, and the guard's
floor/top-up decision *prefers the daemon's number when it is reachable* (`_read_balance` tries the
daemon CLI first, DB second), so the disagreement is load-bearing for funding. Unresolvable while
the daemon is down (M2). Flagging the numbers, not the code: the code read is the correct one.

### MINOR

* **m1 — two shipped tests are RED at their own merged heads.** (a) merchant-routing-engine @8b91148
  `tests/test_routstrd_balance_cron.py` 1 failed / 2 passed — expects "read FAILED" for a missing
  wallet, gets the guard's "not present on this host" gate message; behaviour (rc 1, no row) is
  correct, the assertion is stale. (b) hermes-orchestration @origin/master
  `tests/test_routstrd_lane_role.py` 1 failed / 26 passed — M1's twin. Neither repo gates these in CI
  (`hermes-orchestration` has one workflow, portal-postdeploy.yml, no pytest step).
* **m2 — the idempotency harness proves less than "a second apply is changed=0".** It runs with
  `routstrd_lane_manage_service=false` and `routstrd_lane_manage_crontab=false`, so 8 tasks (enable,
  start, linger, cron, asserts) are skipped and run1's `changed=4` is only the file-landing tasks.
  It also **overrides** `routstrd_funding_guard_script`/`_log` in its own fixture playbook — i.e. it
  papers over exactly the defaults that M1 breaks. And with `~/.bun` synthetic (real mount absent on
  this worker) the "mount ordering pinned" check asserts on a `/tmp` pin, so the real-mount
  resolution is not exercised here.
* **m3 — deployed drift on the worker host.** dq05's `~/.hermes/bot` pair (4a74a2b4 / 376f201f) is
  *not* master's. Loading the lane host's `flat_router.py` against dq05's `zai_proxy.py` (ev/
  deployed_engine_probe.txt:24-25) gives `translation entry: None` and `_resolve_model_for_provider
  ('routstrd','deepseek/deepseek-flash') == 'deepseek/deepseek-flash'` → on a host that is behind,
  the canonical id is forwarded verbatim (404) instead of translated. The wiring only works where
  **both** files are deployed together; only CobradorWave currently qualifies.
* **m4 — the cost measurement is not a router measurement.** `routstr-measure-2026-09-26.json` posts
  to `http://localhost:8008` directly (12/12 ok, 460 in / 297 out tokens, charged 316 msats with
  `wallet_delta_msats` exactly equal), so it evidences the *lane*, not flat-router dispatch. Run 3
  (`git_head 34aa21ac`) is the brief's 208.7 / 740.7 sats/M — that is ~8.8x/~15.6x the lane's own
  published sats_pricing (23.77 / 47.54), as the author disclosed.
* **m5 — `routstrd_funding_guard.py:_espeak` hardcodes `/home/c03rad0r/.hermes/voices/say.sh`** — a
  controller-user literal in an engine script, outside the reach of the new
  `test_no_target_user_literals.py` (roles only). Harmless today, exactly the class of bug that test
  exists to catch. The ledger/state writers also swallow exceptions (`except Exception: …`) and still
  exit 0, so a failed balance row is invisible.
* **m6 — the guard's absent-wallet gate is rc 0 by design** (`wallet not present on this host`), so
  "fails loud" holds only for a *present-but-unreadable/empty* wallet. The author's own test for the
  missing case is the RED one in m1(a).
* **m7 — `.key_disabled_routstrd` (0 bytes, 2026-09-15)** exists in the lane host's bot dir. I could
  not re-derive the brief's "both lanes eligible at effective_cost=inf" live ranking (see §3), so the
  key-health gate is worth re-checking alongside it rather than assuming eligibility.

---

## 3. Unknowns (not evidenced, deliberately not guessed)

1. **Live lane catalog** (`curl http://localhost:8008/v1/models`): impossible now — no listener, no
   daemon (M2). Corroboration available, disclosed as second-hand: the author's measure artifact
   records `advertised_in_catalog: true`, `catalog_size: 21`, `network_model_id: deepseek-v4.1-flash`
   for the routstrd lane, and all 12 requests returned real completions for that id; flat_router.py:
   313-318 and zai_proxy.py:955-957 record the same 2026-09-26 21-id observation. Strong, but not a
   live re-read.
2. **The `routstr` lane (:8009)**: no listener either; I did not verify that the same DOT id is
   correct there. The wiring uses the same id for both lanes and the base_urls differ only by port.
3. **Live `select_provider('deepseek/deepseek-flash')` candidate list / effective_cost inf**: not
   re-derived. A read-only in-process probe needs the lane host's full engine dir (router_state,
   state DBs); the partial probe I could run (deployed cobrador `flat_router.py` + dq05's stale
   `zai_proxy.py`) answered the code-level questions but not live pricing.
4. **Daemon-side wallet-path precedence** (that `ROUTSTRD_WALLET_DIR` really beats
   `~/.routstrd/wallet` beats a legacy `~/.cocod` path): the resolution order lives inside the
   routstrd package on the dead mount, and the daemon cannot be started to observe it. The unit's
   dual pinning is verified; the daemon's honouring of it is not.
5. **The 7 000/6 363 "msats" figure** in the measure artifact (M4): cannot be reconciled while the
   daemon is down.

---

## 4. What was NOT touched

Read-only throughout: no repo mutation outside the review document commit, no write to the lane host
(guards were probed from `/tmp` on that host; wallet reads copy to private temp dirs), no crontab,
service or Ansible apply against a live node. Scratch worktrees at
/mnt/cw-offload/rv41-wt-{ho,mre,mre-pre,ho-a810} are removed after use.

## 5. Evidence index (all re-runnable)

/mnt/cw-offload/review-rv41/
  ev/final_facts.txt        lineage + blob/md5 identity + the role-51 master delta (final_facts.sh)
  ev/t1_wiring.txt          28 passed
  ev/t2_role.txt            a81041ee/model at head vs master (27P / 1F-26P), full failure trace
  ev/t3_idem.txt            idempotency harness run1/run2 + rendered unit + systemd-analyze verify
  ev/t4_guard.txt           32 passed
  ev/t5_balance.txt         1 failed / 2 passed (engine balance cron)
  ev/red_first_*.txt        reverted-hunks and pre-fix runs (9F/19P; 25F/2P/5E)
  ev/live_cobrador.txt      lane-host unit, linger, journal, crontab, listeners
  ev/live_probe2.txt        ~/.bun, dead mount, guard gate behaviour, state/invoice files
  ev/wallet_probe.txt       immutable vs mode=ro vs copy+checkpoint, guard payloads, rc codes
  ev/deployed_engine_probe.txt   deployed-bytes probe (and the drift it exposed)
  ev/role_path_probe.txt    the M1 reproduction: role 51 at master fails to converge (rc=2)
  ev/anchor_lines.txt       the file:line anchors quoted above
  probe_template.yml, probe_template2.yml, run_role_probe.sh, run_role_path_probe.sh,
  probe_wallet.py, run_tests.sh

## 6. Verdict

Not a merge-blocker for **34aa21ac / 67e0f1b7** (lane wiring) or **8b91148** (wallet repoint): both
do exactly what they claim, both carry real RED-first coverage, and the wiring is byte-identical to
master. It IS a blocker for the **operational** reading of the same work: at the merged tip the role
that is supposed to keep this lane alive cannot converge (M1), the lane it manages is dead and
unhealable on the only host that runs it (M2), and its funding guard is a silent no-op (M3). Two
shipped tests are red at their own heads. Recommended order: fix M1's expression (keeping
`ansible_user_dir` so `test_no_target_user_literals` stays green), reconcile the two role tests, then
bring the lane back with a mount path that exists on that node — and re-read the wallet balance
before trusting either 35 508 or 7 000 (M4).
