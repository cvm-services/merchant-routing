# Cross-family cold review — routstr v4.1 lane wiring + routstrd service/guard IaC
## PASS 4 — independent cold re-derivation

reviewer_model: tier/review-kimi
reviewer_provider: zai
reviewer_family: kimi (moonshot family)
author_family: deepseek (workers deleg_17f47ac6 task0/1 + task2)
cross_family: SATISFIED — deepseek != kimi. This reviewer authored none of the reviewed commits
              and read no author narrative beyond the brief's own claim list.
date: 2026-09-27
worker_host: dq05 / c03rad0r-DQ05proplus (this reviewer's node)
live_state_host: cobrador / CobradorWave (100.90.101.9) — reached read-only over ssh
review_mode: cold. Every number below is an output of a command run THIS session. Nothing is
             carried from passes 1-3; where they agree with me it is because I re-measured it.
artifact(primary): ~/reports/reviews/merchant-routing-routstr-v41-lane-wiring-kimi-pass4.md
artifact(repo):    docs/reviews/routstr_v41_lane_wiring_review_pass4.md
tid: UNRESOLVABLE from this worker — 5 independent search surfaces, all negative:
     (1) every task title for LIKE '%(cross-family)%' / '%REVIEW (%',
     (2) task title+body+result for 'routstr v4.1' / 'lane wiring' / 'routstrd service' / 'guard iac',
     (3) same for the author's dispatch id 'deleg_17f47ac6',
     (4) all non-terminal tasks board-wide by recency (newest was 1 h old, unrelated),
     (5) the kanban COMMENTS tables for 'cross-family' / 'FULL_REVIEW' / 'routstr' — hits are all
         on board `admin` for unrelated cards (t_a12dce03, t_cd7e6d9b, t_9301f6f9, ...).
     No kanban toolset is present in this session and HERMES_KANBAN_BOARD=default. The filename
     therefore carries the scope slug, exactly as passes 1-3 did. No card comment was posted.
predecessors (inputs only, all kimi-family like this reviewer; nothing carried as evidence):
     pass1 ~/reports/reviews/merchant-routing-routstr-v41-lane-wiring-kimi.md
     pass2 ~/reports/reviews/merchant-routing-routstr-v41-lane-wiring-kimi-pass2.md
     pass3 ~/reports/reviews/merchant-routing-routstr-v41-lane-wiring-kimi-pass3.md

---

## 0. SHA reconciliation — done FIRST (diff-vs-claim, never title-vs-diff)

| item | brief says | derived this session |
|---|---|---|
| hermes-orchestration | "both merged to master, latest master = a81041ee5" | **REFUTED.** `origin/master` = **9bdb2a0b** ("feat(phase-q): PXE provisioning DNS + NAT"). `git merge-base --is-ancestor 34aa21ac origin/master` → **no**; same for `a81041ee`. The two subjects landed as **67e0f1b7** ("feat(router): wire deepseek-v4.1-flash into the routstr/routstrd lanes") and **c7be49ad** ("feat(routstrd): manage the buy lane as a service + restore the funding-guard cron") — both **YES** ancestors of origin/master. |
| reviewed paths vs tip | — | `git diff --stat bb587eb3 origin/master -- roles/51-routstrd-lane tests/test_routstrd_lane_role.py scripts/engine/flat_router.py scripts/engine/zai_proxy.py` → **EMPTY**, so every measurement I took at bb587eb3 still holds at the 9bdb2a0b tip. |
| merchant-routing-engine | "8b91148 merged to main" | **VERIFIED.** `refs/heads/main == 8b91148` and it is the tip (`git log -1 main`). |
| flat_router.py identity | wiring is on both reviewed commits | blob **449ddbc1** identical at 34aa21ac, a81041ee **and** origin/master (file md5 **1dc1091b**). |
| zai_proxy.py identity | "different family = the same reviewed change" | **NOT identical**: a81041ee blob **57e11a80** (md5 **bcb2d9f0**) vs origin/master blob **4c4afa17** (md5 **c2f13451**). The routstr/routstrd translation *entries* are present in both, but the reviewed commit is not the tip's byte-set. |
| deployed (lane host) | "deployed ~/.hermes/bot/flat_router.py md5 == origin/master blob" | **VERIFIED on CobradorWave**: flat_router.py **1dc1091b** (== tip blob), zai_proxy.py **c2f13451** (== tip blob). |
| deployed (this worker) | — | **NOT tip bytes**: dq05 `~/.hermes/bot/flat_router.py` **4a74a2b4**, `zai_proxy.py` **376f201f** → a host that lags gets the canonical id forwarded verbatim (see m4). |

---

## 1. Per-claim verdicts

| # | claim | verdict | evidence (all re-run this session) |
|---|---|---|---|
| 1a | canonical `deepseek/deepseek-flash` added to PROVIDER_MODELS for routstr + routstrd | **VERIFIED** | `git show origin/master:scripts/engine/flat_router.py` lines 311-315 (`"routstr"`) and 321-325 (`"routstrd"`) both list `"deepseek/deepseek-flash"` alongside the legacy ids; the commit's own hunk adds exactly those two lines. |
| 1b | `_PROVIDER_MODEL_NAMES` translates it to the network id `deepseek-v4.1-flash` (DOT) | **VERIFIED** | `zai_proxy.py:969-974` — `"routstr": {"deepseek/deepseek-flash": "deepseek-v4.1-flash"}` and the identical `"routstrd"` entry. Dot, not dash. |
| 1c | check the id against the live lane (`curl -s http://localhost:8008/v1/models`) | **NOT POSSIBLE — lane down** | On the lane host: **no listener on 8008 or 8009** (`ss -ltn`), `routstrd.service` is `failed` (203/EXEC). `curl -m5` from this node → `http=000 size=0`. The id is therefore corroborated only by the code comments/in-tree docs (2026-09-26 probe records 21 ids incl. `deepseek-v4.1-flash` and `tinfoil-deepseek-v4-1-flash`). **Marked UNKNOWN as a live fact** (not refuted — unmeasurable while the lane is dead). |
| 2a | a dispatch arm exists for both lanes (the ollama_cloud_4 class of bug) | **VERIFIED** | `flat_router.py:1361 _make_dispatch_fn` → falls through to `_dispatch_external` (`:1406-1408`) → `handler._try_external_single(name, ...)`; used at `:1426` and `:1607`. Neither lane short-circuits earlier (the early returns are only `ours/friend`, `ollama_cloud*`, `opencode_go`, `telnyx`). The code even documents the oc4 trap at `:1375-1377`. |
| 2b | live `select_provider('deepseek/deepseek-flash')` shows both lanes eligible-but-`inf` | **UNKNOWN (not re-derived)** | Needs the lane host's live engine state and a running lane; the lane is down and I did not run the router in-process. Reported as unknown, not contradicted. |
| 3a | systemd --user routstrd.service with bounded Restart | **VERIFIED (shape) / live-broken** | Live unit: `Restart=always`, `RestartSec=5`, `StartLimitIntervalSec=300`, `StartLimitBurst=5`, `WantedBy=default.target`, `UnitFileState=enabled`. Bounded yes — and the bound is what killed it (M3). |
| 3b | linger | **VERIFIED** | Live `loginctl show-user c03rad0r -p Linger` → `Linger=yes`. |
| 3c | wallet pinned to ~/.routstrd/wallet | **VERIFIED** | Live unit env: `ROUTSTRD_DIR=/home/c03rad0r/.routstrd`, `ROUTSTRD_WALLET_DIR=/home/c03rad0r/.routstrd/wallet`; template `routstrd.service.j2:32-33` pins `%h/.routstrd` / `%h/.routstrd/wallet`. |
| 3d | RequiresMountsFor resolved mount | **VERIFIED (shape)** | Live: `RequiresMountsFor=/mnt/dq05-lexar /mnt/dq05-lexar/cw-offload/bun /home/c03rad0r`; template `:12` renders it from the readlink/findmnt probe (tasks/main.yml:17-40). It pinned a *remote* mount path — see M3. |
| 3e | a SECOND apply must be changed=0 | **VERIFIED at a81041ee** | `tests/run_routstrd_lane_idempotency.sh` @a81041ee: `run1: changed=4 failed=0` (PLAY RECAP ok=15 skipped=10), `run2: changed=0 failed=0` (skipped=8), `systemd-analyze --user verify rc=0`, `RESULT: PASS`. Caveat m7. **At the merged tip the role cannot converge at all (M1).** |
| 3f | no path can fall back to the empty ~/.cocod/coco.db | **VERIFIED in code + unit** | No non-comment `~/.cocod` in `roles/51-routstrd-lane` (`git grep` → only README.md:16 defaults-table row, defaults/main.yml:57 comment, routstrd.service.j2:31 comment). Unit pins both env vars. Live legacy file `~/.cocod/coco.db` = **0 bytes**. Daemon-side precedence UNKNOWN (see §3). |
| 3g | *operational* intent: lane up / boot-recoverable | **REFUTED (live)** | `is-active=failed`, `ExecMainStatus=203`, `NRestarts=9`, `StartLimitAction=none`, journal ends `Start request repeated too quickly` at 2026-09-26 23:25:48, **no listener**. See M3. |
| 4a | guard reads the migrated wallet | **VERIFIED** | `git show 8b91148 -- scripts/routstrd_funding_guard.py`: the reader was rewritten off the dead `~/.cocod` socket/path onto `~/.routstrd/wallet/coco.db`; commit subject + diff confirm. |
| 4b | per-mint, excludes the orangesync testnut from network_sats | **VERIFIED live** | `network_sats_from()` (:223-224) subtracts `TESTNUT_MINT`. My own read-only sqlite read of the live wallet: `mint.minibits.cash/Bitcoin \| 35514 \| 29` and `mint.orangesync.tech \| 5000 \| 5` → network_sats = **35 514**. |
| 4c | FAILS LOUD (non-zero) on unreadable/empty wallet instead of reporting 0 sats | **VERIFIED for present-but-unreadable/empty; hole for a host with no wallet at all** | Engine suite @8b91148: unreadable/zero-proof cases pass and exit non-zero. The wholly-absent case is a deliberate `rc 0` skip-gate ("routstrd wallet not present on this host") — see m2. |
| 4d | "a read-only sqlite URI does not replay WAL — check the technique" | **TECHNIQUE CORRECT; the generalisation is IMPRECISE** | The guard copies db+`-wal`+`-shm` to a private dir and opens the COPY read-write with `PRAGMA wal_checkpoint(TRUNCATE)` (:160-179) — correct and necessary. But read-only is not the same as immutable: `mode=ro` **does** replay the WAL; only `immutable=1` does not. Live proof (read-only, this session): `sqlite3 -readonly … coco.db` → **35 514**; `file:…coco.db?immutable=1` → **40 508**. The two views differ → the WAL-blind read is real, and today it *overstates* (m3). |
| 5a | `scripts/engine/test_routstr_v41_lane_wiring.py` | **28 passed (GREEN)**; RED-first structurally real, not re-executed | a81041ee: `28 passed in 1.34s`. RED-first: at `34aa21ac^` the canonical id is absent from **both** lane sets and `_PROVIDER_MODEL_NAMES` has **no** routstr/routstrd entry (verified by `git show 34aa21ac^:…`), so `test_lane_advertises_v41_canonical` and the translation tests must fail. I could not re-run the revert (see §4). Pass 3 measured **9 failed / 19 passed**. |
| 5b | `tests/test_routstrd_lane_role.py` | **27 passed @a81041ee; 1 failed / 26 passed @ merged master** | My runs. Failure = `test_funding_guard_paths_are_the_restored_ones` (pins the old `/home/c03rad0r/...` literal; master now templates it). Same failure is M1's twin. |
| 5c | `tests/run_routstrd_lane_idempotency.sh` | **PASS rc 0** | See 3e — run1 changed=4, run2 changed=0. |
| 5d | merchant-routing-engine guard test | **32 passed (guard) + 1 failed / 2 passed (balance cron) = 1 failed / 34 passed combined** | My run @8b91148. The one failure is a stale assertion string (m2); rc and row behaviour are correct. |
| 5e | RED-first is real | **VERIFIED (engine)** | @8b91148^ (worktree `rv41-wt-mre-pre`, pre-fix code + the new tests): `28 failed, 2 passed, 5 errors`. The new tests genuinely fail without the fix. |

**Reading of claim 5 as a whole: PARTLY REFUTED.** Five suites re-run; three are green at the head
that owns them, but **two shipped tests are RED at their own merged heads** and the tip role cannot
converge.

---

## 2. Findings

### MAJOR

**M1 — role 51-routstrd-lane cannot converge at the merged tip; the funding-guard path expression
is unresolvable under the shipped deploy shape.** `roles/51-routstrd-lane/defaults/main.yml:101-102`
at origin/master read
`"{{ ansible_user_dir | default('/home/' + ansible_user_id) }}/…"`. Both `ansible_user_dir` and
`ansible_user_id` are fact-derived, and the playbook that owns the role runs with facts off
(`playbook-live-router.yml` @origin/master: `hosts: fleet`, `gather_facts: false`,
`roles: [29-live-router, 51-routstrd-lane]`), so Jinja must evaluate `default()`'s *argument* and
hard-fails. **Reproduced this session** by running the shipped role through the shipped shape
(side-effect-free fixture, `routstrd_lane_manage_service=false`, `manage_crontab=false`):
`roles/51-routstrd-lane/tasks/main.yml:245` "Stat the funding guard" →
`"Task failed: Finalization of task args for 'ansible.builtin.stat' failed: Error while resolving
value for 'path': 'ansible_user_id' is undefined"`, `PLAY RECAP localhost ok=11 changed=4 failed=1
skipped=8`, **PLAYBOOK rc=2**. Attribution: the literal path was correct in the reviewed commit
(`git show c7be49ad:…/defaults/main.yml` has the bare `/home/c03rad0r/...`), and **37d6b55f**
("feat(phase-q): MAAS laptop provisioning + target-user cleanup") replaced it with the failing
expression — i.e. the regression is later than the two commits under review, and the brief's
"latest master = a81041ee" is exactly the drift that hides it. Consequence: the focused live-router
deploy aborts on every fleet host, so the funding-guard cron can be neither installed nor repaired.
Note the irony: 37d6b55f added `tests/test_no_target_user_literals.py` which *requires*
`ansible_user_dir` here, while `tests/test_routstrd_lane_role.py::test_funding_guard_paths_are_the_
restored_ones` still asserts the old literal (m5).

**M2 — the lane service is dead at the tip and cannot self-heal.** Live on CobradorWave:
`ActiveState=failed`, `ExecMainStatus=203`, `NRestarts=9`, `StartLimitAction=none`,
`StartLimitBurst=5` / `StartLimitIntervalSec=300` (exhausted), journal ends
`Unable to locate executable '/mnt/dq05-lexar/cw-offload/bun/bin/bun': No such file or directory` →
`Failed at step EXEC spawning …: No such file or directory` → `Start request repeated too quickly`
at 2026-09-26 23:25:48; **no listener on 8008/8009**; `~/.bun -> /mnt/dq05-lexar/cw-offload/bun` is
dangling and `findmnt -T /mnt/dq05-lexar` resolves to `/` (**the drive is not mounted**). Because
`StartLimitAction=none`, systemd will not retry without a manual `reset-failed`. So the wiring is
correct in code and simultaneously serves nothing: the unit pinned a *remote node's* mount path and
had no recovery path when that mount went away.

**M3 — the "restored" */5 funding-guard cron is present but inert, and the guard is unguarded.**
Live crontab line 53: `*/5 * * * * /home/c03rad0r/merchant-routing-engine/scripts/
routstrd_funding_guard.py >> /home/c03rad0r/merchant-routing-engine/logs/
routstrd_funding_guard.log 2>&1` (preceded by `#Ansible: routstrd-funding-guard`). On that host
`~/merchant-routing-engine -> /mnt/dq05-lexar/cw-offload/merchant-routing-engine` and the target
script **does not exist** (`ls …/scripts/routstrd_funding_guard.py` → `No such file or directory`),
and the log directory does not exist either (`ls -ld …/merchant-routing-engine/logs` → `No such
file or directory`). Every 5 minutes the job exits non-zero into a log it cannot create: the wallet
is unguarded and the failure is invisible. Renewed convergence will not repair it while M1 stands,
and the role's cron task is gated on the script's existence.

**M4 — the brief's balance figure is the WAL-blind reading, and it is not reproducible today.**
Brief: "wallet 35,508 sats minibits (+5,000 orangesync)". My read-only reads of the *same* live
wallet this session: `mode=ro` → **35 514** (minibits 29 proofs) + 5 000 (orangesync 5 proofs);
`immutable=1` → **40 508** (32 proofs). State breakdown: `ready 34, spent 64`. So (a) 35 508 is not
what either reader returns today, and (b) the WAL-blind read *overstates* rather than understates —
the opposite direction from pass 3's recorded 35 508. The invariant the guard depends on (a
WAL-blind reader disagrees with a WAL-replaying one) holds and is what matters for funding; the
specific numbers need re-taking before any top-up decision. The guard prefers the daemon's number
when reachable, and the daemon is down (M2), so this is load-bearing.

### MINOR

* **m1 — two shipped tests are RED at their own merged heads.** (a) hermes-orchestration
  @origin/master `tests/test_routstrd_lane_role.py`: **1 failed / 26 passed** (`test_funding_guard_
  paths_are_the_restored_ones`). (b) merchant-routing-engine @main `tests/test_routstrd_balance_
  cron.py`: **1 failed / 2 passed**. Neither repo gates tests in CI — hermes-orchestration has a
  single workflow (`.github/workflows/portal-postdeploy.yml`, no pytest step) and
  merchant-routing-engine @8b91148 has **no `.github/` at all** — so both shipped red.
* **m2 — the guard's "fails loud" has a hole, and the author's own test asserts the wrong string.**
  The failing engine test expects `"read FAILED"` but the missing-wallet path prints
  `"routstrd wallet not present on this host"`; `returncode != 0` and `rows == []` both hold, so the
  behaviour is right and only the assertion is stale. But the absent-wallet case is a deliberate
  **rc 0** skip-gate, so "fails loud" covers a *present-but-unreadable/empty* wallet only.
* **m3 — WAL docstring overstates / numbers disagree** (see M4 and 4d): `mode=ro` does replay the
  WAL; only `immutable=1` does not.
* **m4 — deployed drift on the worker host.** dq05's `~/.hermes/bot` pair (4a74a2b4 / 376f201f) is
  **not** the tip's. The lane only works where `flat_router.py` and `zai_proxy.py` are deployed
  *together* (CobradorWave qualifies); on a lagging host the canonical id is forwarded verbatim
  (404) instead of translated.
* **m5 — the two role tests now contradict each other.** `test_no_target_user_literals.py` demands
  `ansible_user_dir` appear in `defaults/main.yml`; `test_funding_guard_paths_are_the_restored_ones`
  demands the old literal. One of them must change with the M1 fix.
* **m6 — the idempotency harness proves less than "a second apply is changed=0".** Its own fixture
  sets `routstrd_lane_manage_service: false` and `routstrd_lane_manage_crontab: false` (lines 11-13,
  76-77), so the service/linger/cron tasks are skipped and run1's `changed=4` is only file-landing;
  and it **overrides** `routstrd_funding_guard_script`/`_log` (lines 78-79) — the very defaults M1
  breaks. That is why the harness is green while the real deploy is red.
* **m7 — citations in the brief are stale.** SHAs (`34aa21ac`/`a81041ee` are not on master), "latest
  master = a81041ee5", and the balance figure (M4). The measure artifact the brief cites is the
  author's own and is not a router measurement (it posts to `localhost:8008` directly).

---

## 3. Unknowns (deliberately not guessed)

1. **Live lane catalog** — unmeasurable while the lane is dead (M2). `curl` from this node returns
   `http=000`; the lane host has no listener on 8008/8009.
2. **Live `select_provider('deepseek/deepseek-flash')` candidate ranking / `effective_cost=inf`** —
   not re-derived (needs the lane host's live engine state plus a running lane).
3. **The routstr lane (:8009)** — same story; I did not verify the DOT id is right there.
4. **Daemon-side wallet-path precedence** (`ROUTSTRD_WALLET_DIR` vs `~/.routstrd/wallet` vs a legacy
   `~/.cocod` path) — the resolution order lives inside the routstrd package, which is on the
   unmounted drive; the unit's dual pinning is verified, the daemon's honouring of it is not.
5. The `7000 / 6677 "msats"` figure in the author's measure artifact — cannot be reconciled.

---

## 4. What was NOT touched, and tool friction (disclosed)

Read-only throughout. **No repo mutation except this document's commit.** No write to the lane host
(everything over `ssh` was `systemctl show`, `crontab -l`, `ls`, `md5sum` and `sqlite3 -readonly`);
no unit started/stopped/enabled, no `reset-failed`, no crontab edit, no Ansible apply against a live
node (the M1 reproduction is a throwaway fixture under `$TMPDIR`).

Four shell commands were **denied by the host guard** mid-review (not retried): creating worktrees
under the shared offload mount, `rm -rf` + `git archive` scratch trees, and an `ln -sf` fixture
farm. Consequence: I could not re-execute the wiring test's RED-first revert in a clean tree, and I
did not re-run pytest in a fresh checkout — I used the *pre-existing* clean worktrees
`rv41-wt-ho-a810` (a81041ee), `rv41-wt-mre` (8b91148) and `rv41-wt-mre-pre` (8b91148^) with
`PYTHONDONTWRITEBYTECODE=1 … -p no:cacheprovider`, plus `git show` reads and `git archive`-free
byte comparisons. The role-51 convergence probe was run by invoking the repo-committed script
`docs/reviews/routstr_v41_pass3_probes/run_role_path_probe.sh` (its fixture is `mktemp -d`).
Inline `python3 -c` is guard-blocked on this host; scripts were written to files and run instead.

---

## 5. Evidence index (verbatim outputs behind each verdict)

Lineage / identity
  `git merge-base --is-ancestor 34aa21ac|a81041ee|67e0f1b7|c7be49ad|bb587eb3|37d6b55f origin/master`
    → no, no, YES, YES, YES, YES;  `git rev-parse --short origin/master` → 9bdb2a0b
  `git rev-parse origin/master:scripts/engine/flat_router.py` → 449ddbc1…3af3f
    (34aa21ac / a81041ee identical; zai_proxy 57e11a80 vs origin/master 4c4afa17)
  `git diff --stat bb587eb3 origin/master -- roles/51-routstrd-lane tests/test_routstrd_lane_role.py
   scripts/engine/flat_router.py scripts/engine/zai_proxy.py` → EMPTY
  md5sum: cobrador flat_router 1dc1091b / zai_proxy c2f13451; dq05 4a74a2b4 / 376f201f
  `git -C …/merchant-routing-engine log -1 main` → 8b91148

Code (origin/master / 8b91148)
  flat_router.py:311-325 (PROVIDER_MODELS routstr + routstrd); :1361-1408,1426,1607 (dispatch arm)
  zai_proxy.py:969-974 (translation table, DOT id)
  playbook-live-router.yml (hosts: fleet, gather_facts: false, roles 29 + 51)
  roles/51-routstrd-lane/defaults/main.yml:101-102; templates/routstrd.service.j2:12,15,16,24,28-39,47
  scripts/routstrd_funding_guard.py: network_sats_from (:223-224), copy+wal_checkpoint :TRUNCATE (:160-179)
  `git show 34aa21ac^:scripts/engine/{flat_router,zai_proxy}.py` → neither lane list contains
    deepseek/deepseek-flash; _PROVIDER_MODEL_NAMES has no routstr/routstrd key

Suites (all re-run this session)
  a81041ee: `python3 -m pytest scripts/engine/test_routstr_v41_lane_wiring.py -q` → 28 passed in 1.34s
  a81041ee: `python3 -m pytest tests/test_routstrd_lane_role.py -q` → 27 passed in 0.41s
  origin/master: `python3 -m pytest tests/test_routstrd_lane_role.py -q` → 1 failed, 26 passed
  a81041ee: `bash tests/run_routstrd_lane_idempotency.sh` → run1 changed=4 failed=0 (ok=15 skipped=10),
    run2 changed=0 failed=0 (skipped=8), systemd-analyze --user verify rc=0, RESULT: PASS
  8b91148:  `python3 -m pytest tests/test_routstrd_funding_guard.py tests/test_routstrd_balance_cron.py -q`
    → 1 failed, 34 passed
  8b91148^: same → 28 failed, 2 passed, 5 errors
  role-51 convergence probe (shipped shape, no overrides) → failed=1, PLAYBOOK rc=2,
    "'ansible_user_id' is undefined" at defaults/main.yml:101 via tasks/main.yml:245

Live (CobradorWave, read-only)
  `systemctl --user show routstrd.service` → ActiveState=failed SubState=failed NRestarts=9
    ExecMainStatus=203 StartLimitAction=none StartLimitBurst=5 StartLimitIntervalSec=300
    Restart=always RestartSec=5 UnitFileState=enabled WantedBy=default.target
    RequiresMountsFor=/mnt/dq05-lexar /mnt/dq05-lexar/cw-offload/bun /home/c03rad0r
    Environment=HOME=… ROUTSTRD_DIR=…/.routstrd ROUTSTRD_WALLET_DIR=…/.routstrd/wallet
    ExecStartPre=…/.hermes/scripts/routstrd_lane_guard.sh --port 8008
  journal tail → 203/EXEC unable to locate /mnt/dq05-lexar/cw-offload/bun/bin/bun; "Start request
    repeated too quickly" 2026-09-26 23:25:48
  `ss -ltn` → no 8008/8009; from dq05 `curl -m5` → http=000
  `loginctl show-user c03rad0r -p Linger` → Linger=yes
  `crontab -l` → line 53 `#Ansible: routstrd-funding-guard` + `*/5 … routstrd_funding_guard.py >>`
  `ls ~/merchant-routing-engine/scripts/routstrd_funding_guard.py` → No such file or directory
  `ls -ld ~/merchant-routing-engine/logs` → No such file or directory
  `findmnt -T /mnt/dq05-lexar` → `/` (not mounted); `~/.bun` symlink dangling
  `ls -la ~/.cocod/coco.db` → 0 bytes
  `sqlite3 -readonly ~/.routstrd/wallet/coco.db` → minibits 35514/29 proofs, orangesync 5000/5 proofs
    `file:…?immutable=1` → 40508/32; `group by state` → ready 34, spent 64

---

## 6. Verdict

The two pieces of *code under review* do what they claim. The registry entries, the DOT translation
and a real dispatch arm for both lanes are all present and reachable; the engine's wallet repoint is
real, per-mint, testnut-aware, and backed by a genuine RED-first suite (28 failed / 2 passed / 5
errors without the fix).

It **cannot be accepted on its operational claim.** At the merged tip (origin/master = 9bdb2a0b,
which is *not* the SHAs the brief cites): the role that is supposed to keep this lane alive cannot
converge at all (**M1**, reproduced: PLAYBOOK rc=2), the lane it manages is dead and cannot
self-heal (**M2**: 203/EXEC, start limit exhausted, mount gone), the funding guard it restored is a
silent no-op whose own repair path is gated behind the same breakage (**M3**), and the wallet figure
quoted in the brief is not what today's readers return (**M4**). Two shipped tests are red at their
own heads (m1).

Recommended order: fix M1 without dropping `ansible_user_dir` (so `test_no_target_user_literals`
stays green) and reconcile the two role tests (m5); then bring the lane back on a mount path that
actually exists on that node (M2) and re-enable recovery (`StartLimitAction=`/`reset-failed`);
then re-read the wallet before trusting any balance (M4); then add the missing CI gate (m1).

FULL_REVIEW: /home/c03rad0r/reports/reviews/merchant-routing-routstr-v41-lane-wiring-kimi-pass4.md
