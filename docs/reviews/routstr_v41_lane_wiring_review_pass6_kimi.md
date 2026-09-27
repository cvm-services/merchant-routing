# Cold cross-family review — routstr v4.1 lane wiring + routstrd service/guard IaC (pass 6)

reviewer_model: kimi-k3
reviewer_lane: tier/review-kimi (provider zai; tier map ~/.hermes/bot/model_tiers.yaml:139-148)
reviewer_family: kimi/moonshot
author_family: deepseek (workers deleg_17f47ac6 task0/1 + task2)
review_tier: cross-family cold review, execution-derived (read-only against live state)
reviewed_at: 2026-09-27 ~11:20 CEST
review_pass: 6 (passes 1-5 exist on this same scope; this pass re-derives rather than reads them)

## Heads reviewed (diff-vs-claim, not title-vs-diff)

| claimed | resolved identity | notes |
|---|---|---|
| hermes-orchestration `34aa21ac` "feat(router): wire deepseek-v4.1-flash into the routstr/routstrd lanes" | exists; parent `05a63432` | **not reachable from any branch** |
| hermes-orchestration `a81041ee` "feat(routstrd): manage the buy lane as a service + restore the funding-guard cron" | exists; parent is `34aa21ac` (the two are consecutive on the branch) | **not reachable from any branch** |
| "branch pr/routstr-v41-lane-wiring / pr/routstrd-lane-service, both merged to master" | landed on master as **different SHAs**: `67e0f1b7` (same subject as `34aa21ac`) and `c7be49ad` (same subject as `a81041ee`), both ancestors of `origin/master` | landed by rebase/squash, so the reviewed commit objects are unreachable while the content is on master |
| "latest master = a81041ee5" | **REFUTED**: `origin/master` tip at review time = `9bdb2a0b` ("feat(phase-q): PXE provisioning DNS + NAT"); the local clone's `master` branch = `74c010c2` (not an ancestor of origin/master — stale/diverged local ref) | master has moved on by many commits |
| merchant-routing-engine `8b91148` "fix(routstrd): read the migrated ~/.routstrd wallet, not the dead ~/.cocod path" | `git rev-parse HEAD main origin/main` = `8b911483538ecba53813cbf338750dc48844a8d1` (all three) | reviewed head **is** the tip of main; `8b91148^` = `4429060` |

### Content identity of the reviewed change on master (md5 of the blob at each ref)

| path | a81041ee | origin/master | verdict |
|---|---|---|---|
| scripts/engine/flat_router.py | `1dc1091bd4d264edbfe2c0e9cae89454` | `1dc1091b…` | identical |
| roles/51-routstrd-lane/tasks/main.yml | `f25621f63704d53acb9958e571ae0303` | `f25621f6…` | identical |
| roles/51-routstrd-lane/templates/routstrd.service.j2 | — | — | identical (`git diff` empty) |
| tests/test_routstrd_lane_role.py | `e34908471c7a54e4866eece279de5dbf` | `e3490847…` | identical |
| tests/run_routstrd_lane_idempotency.sh | `77d8b8fe826a530a2ee06e40e6056fbf` | `77d8b8fe…` | identical |
| scripts/engine/zai_proxy.py | `bcb2d9f0f9c7aee76becc3346b14c381` | `c2f13451b527acdba70861224a966287` | **differs** (later, unrelated edits) |
| roles/51-routstrd-lane/defaults/main.yml | `222523031ccd064337a9a67242523cd6` | `c9b83bf28afb358e439283b23c6f6d61` | **differs** — see M1 |

`git log --oneline a81041ee..origin/master -- roles/51-routstrd-lane` → `37d6b55f`, `c7be49ad` only. So the reviewed patch is on master, and everything that changed the role afterwards came from `37d6b55f` (2026-09-27 00:23:32 +0200, "feat(phase-q): MAAS laptop provisioning + target-user cleanup") — a **regression introduced after both reviewed heads**.

## Per-claim verdicts

| # | claim | verdict | evidence |
|---|---|---|---|
| 1a | canonical `deepseek/deepseek-flash` in `PROVIDER_MODELS` for routstr **and** routstrd | **VERIFIED** | in-process probe loading the repo copies of `zai_proxy`/`flat_router`: `PROVIDER_MODELS[routstr] has canonical: True`, `PROVIDER_MODELS[routstrd] has canonical: True` |
| 1b | `_PROVIDER_MODEL_NAMES` translates both lanes to the network id `deepseek-v4.1-flash` (dotted) | **VERIFIED** | `zai_proxy.py:969-974` at `origin/master` (identical at the reviewed head). No v4→v4.1 re-point (legacy id simply absent → explicit failure rather than silent substitution) |
| 1c | the dotted id matches the **live** lane (`curl -s http://localhost:8008/v1/models`) | **UNKNOWN — unverifiable by state** | on the lane host: `curl -m 6 localhost:8008/v1/models` → `http=000`, `ss -ltnp` → **no listener on 8008/8009** (the unit is dead, M2). Also `http=000` locally. Nothing is serving, so the id cannot be re-confirmed this pass. The code comment cites a 2026-09-26 measurement (21 ids) that I did not reproduce |
| 2a | a **dispatch arm** exists for both lanes (the `ollama_cloud_4` class bug: registry entry + price, no arm) | **VERIFIED** | `_make_dispatch_fn('routstrd') -> _dispatch_external`; `_make_dispatch_fn('routstr') -> _dispatch_external` (probe) |
| 2b | both lanes are registered externals with a reachable base_url | **VERIFIED** | `zai_proxy.py:1035-1046`: `routstr` → `http://23.182.128.51:8009/v1`; `routstrd` → `http://localhost:8008/v1`; both keyed from `_EXTERNAL_KEYS` |
| 2c | live `select_provider('deepseek/deepseek-flash')` candidates include routstr + routstrd, "both at effective_cost=inf, i.e. eligible but never chosen" | **PARTLY REFUTED** | candidacy **VERIFIED**: 10 candidates, both lanes present. `effective_cost=inf` **REFUTED in-process**: `routstr=1.0`, `routstrd=1.0` (finite, from the seeded rate), while `ollama_cloud*`, `neuralwatt`, `deepinfra`, `openrouter` are `inf`. "Never chosen" holds for a different reason: `deepseek` wins the argmin at `0.05`. The live process's own value was not read (no safe read path) → the `inf` figure is unverified and inconsistent with the shipped seed |
| 3a | systemd `--user routstrd.service` with **bounded** Restart | **VERIFIED** | live unit: `Restart=always`, `RestartSec=5`, `StartLimitIntervalSec=300`, `StartLimitBurst=5` (the park of 2026-09-20 recorded 27753 restarts) |
| 3b | linger enabled | **VERIFIED** | `loginctl show-user c03rad0r -p Linger` → `Linger=yes` |
| 3c | wallet pinned to `~/.routstrd/wallet` | **VERIFIED** | live unit: `Environment=ROUTSTRD_DIR=%h/.routstrd` + `Environment=ROUTSTRD_WALLET_DIR=%h/.routstrd/wallet` |
| 3d | `RequiresMountsFor` resolved mount | **VERIFIED** (+ reading note) | unit file: `RequiresMountsFor=/mnt/dq05-lexar /mnt/dq05-lexar/cw-offload/bun` (2 paths, = `routstrd_lane_bun_mount` + `routstrd_lane_bun_real`). `systemctl show -p RequiresMountsFor` reports **3** paths because systemd auto-adds `/home/c03rad0r` for `WorkingDirectory=%h`; that third path is **not** in the unit file and is **not** a defect |
| 3e | a **second apply** is `changed=0` | **VERIFIED as shipped — but the proof is narrower than it reads** | `tests/run_routstrd_lane_idempotency.sh` at `a81041ee`: `run1: changed=4 failed=0`, `run2: changed=0 failed=0`, `PLAY RECAP localhost: ok=15 changed=0 failed=0 skipped=8`, `RESULT: PASS — unit renders and verifies, run2 changed=0, all files landed.` The fixture (lines 76-77) sets `routstrd_lane_manage_service: false` + `routstrd_lane_manage_crontab: false` and (lines 70-71) **overrides both funding-guard path vars** → the 8 skips and the override mean the service, crontab and defaults branches are outside the proof. See M3 |
| 3f | no path can fall back to the empty `~/.cocod/coco.db` | **VERIFIED** | `git grep -n cocod a81041ee -- roles/51-routstrd-lane` → comments/README only, zero functional values; `tasks/main.yml` has no `cocod` hit at all; `tests/test_routstrd_lane_role.py:113-115` asserts the unit blob carries no `.cocod/wallet` value |
| 3g | the lane is up | **REFUTED LIVE** | `routstrd.service` = `failed`/`inactive`, `ExecMainStatus=203`, `NRestarts=9`, latched `since Sat 2026-09-26 23:25:48 CEST`; `UnitFileState=enabled`, so a reboot would retry, but nothing has retried in this boot. No listener on 8008 (see M2) |
| 4a | the guard reads the **migrated** wallet | **VERIFIED** | live `--balance-json`: `"wallet_db": "/home/c03rad0r/.routstrd/wallet/coco.db"`, `"source": "db"`. Deployed guard `md5 fec2e50a6840517f3f19f4e4a5a4d55f` == blob at `8b91148` == worktree copy |
| 4b | per-mint, and the orangesync testnut is excluded from `network_sats` | **VERIFIED (live)** | live: `network_sats=35514`, `per_mint {minibits: 35514, orangesync: 5000}`. Independently, the collector's rows in `api_burn.db`: `routstrd_network | 2026-09-27 09:15:08 (UTC) | 35.514 | {"network_sats": 35514, …, "per_mint": {…: 35514, …: 5000}, "source": "db"}` |
| 4c | FAILS LOUD (non-zero) on an unreadable/empty wallet instead of reporting 0 sats | **VERIFIED, with a documented carve-out** | lane host: `ROUTSTRD_CLI="" ROUTSTRD_WALLET_DB=/tmp/nope/coco.db … --balance-json` → `⚠️ funding guard: routstrd wallet read FAILED — daemon: … | db: wallet db missing: …`, `rc=2`. Carve-out (`main()` lines 330-335): a host with **no `~/.routstrd` and no CLI at all** exits **0 silently** by design ("routstrd not installed on this host") — correct for a no-op node, but see M4 |
| 4d | "a read-only sqlite URI does not replay WAL — check the technique" | **CODE VERIFIED / WORDING REFUTED** | measured on the live wallet: `sqlite3 "file:…coco.db?mode=ro" "select count(*) …"` → **98** proofs (WAL **is** replayed); `?immutable=1` → **96** (WAL skipped). The guard's technique is nonetheless correct and WAL-safe: it copies `db`+`-wal`+`-shm` to a private temp dir and opens the **copy read-write** with `PRAGMA wal_checkpoint(TRUNCATE)` (`_read_balance_db`, lines 155-203). The docstring conflates "read-only/immutable" into one class; `mode=ro` is not WAL-blind. Wording defect only — see M5 |
| 5a | `scripts/engine/test_routstr_v41_lane_wiring.py` | **VERIFIED** | at `a81041ee`: `28 passed in 2.70s` |
| 5b | `tests/test_routstrd_lane_role.py` | **VERIFIED at the reviewed head; REFUTED at the tip** | `a81041ee`: `27 passed in 0.76s`. `origin/master` tip `9bdb2a0b`: `1 failed, 26 passed` — `test_funding_guard_paths_are_the_restored_ones`, `assert '{{ ansible_u…ding_guard.py' == '/home/c03rad…ding_guard.py'` |
| 5c | `tests/run_routstrd_lane_idempotency.sh` | **VERIFIED** | `a81041ee`: `RESULT: PASS`.  Also `PASS` at the tip `9bdb2a0b` — which is the problem (M3) |
| 5d | the merchant-routing-engine guard test | **VERIFIED, 1 test RED at its own head — but host-dependently** | `8b91148`: `tests/test_routstrd_funding_guard.py tests/test_routstrd_balance_cron.py` → `1 failed, 34 passed`; the failure is `test_missing_wallet_fails_loudly_and_writes_no_row`. Differential proof (M4): the same guard, same flags, two hosts → host A (no `~/.routstrd`): `routstrd wallet not present on this host`, `rc=0`; host B (lane host, has `~/.routstrd`): `read FAILED`, `rc=2` |
| 5e | the RED-first claim is real (does the test fail without the fix?) | **VERIFIED for both suites** | wiring: head test file (`md5 7679824f` == blob at `34aa21ac` == at `67e0f1b7`) against pre-fix `flat_router.py` (`md5 38c3bbe5` == blob at `34aa21ac^` = `05a63432`) → `9 failed, 19 passed`. Guard: `8b91148` tests against the pre-fix guard + collector (`4429060`) → `28 failed, 2 passed, 5 errors` |

## Findings

### M1 — MAJOR (carried, re-derived, re-attributed): role `51-routstrd-lane` cannot converge at the tip; the regression is `37d6b55f`, not the reviewed patch

`roles/51-routstrd-lane/defaults/main.yml:101-102` at `origin/master`:

    routstrd_funding_guard_script: "{{ ansible_user_dir | default('/home/' + ansible_user_id) }}/merchant-routing-engine/scripts/routstrd_funding_guard.py"
    routstrd_funding_guard_log:    "{{ ansible_user_dir | default('/home/' + ansible_user_id) }}/merchant-routing-engine/logs/routstrd_funding_guard.log"

`playbook-live-router.yml` — the focused playbook that owns this lane (`hosts: fleet`, `gather_facts: false`, roles `29-live-router`, `51-routstrd-lane`) — defines neither fact, and `default()`'s argument is evaluated eagerly, so the expression raises before the default can apply. Re-derived independently (`f1_probe_p6.yml`, `gather_facts: false`):

    F1-A (37d6b55f form)  FAILED=True   "'ansible_user_id' is undefined"  (task-arg finalization error)
    F1-B (same role's shape: ansible_user_id | default(lookup('env','USER'))) FAILED=False  "c03rad0r"

First consumer is `tasks/main.yml:245` (`stat: path: "{{ routstrd_funding_guard_script }}"`) → the play dies there.

Attribution, by execution not by reading:
* `git grep "default('/home/' + ansible_user_id)" 34aa21ac` → the pattern is **absent** at the reviewed head; the reviewed head has the literal `/home/c03rad0r/merchant-routing-engine/scripts/routstrd_funding_guard.py`.
* `git grep` at `origin/master` → the two role-51 lines are the **only** `ansible_user_dir` uses in the repo; the other 9 call sites across 7 roles use `ansible_env.HOME | default('/home/' + ansible_user_id)`.
* `git merge-base --is-ancestor c7be49ad 37d6b55f` → true; `37d6b55f` = 2026-09-27 00:23:32 +0200.
* `git log a81041ee..origin/master -- roles/51-routstrd-lane` → `37d6b55f`, `c7be49ad`.

**Correction to pass 5**: pass 5 placed this on the reviewed head. It is not in the reviewed diff at all — both reviewed heads are clean here, and the defect arrived in a later, unrelated phase-q commit. Any "cannot converge" finding must be filed against `37d6b55f` (or the phase-q card), not against the routstr lane work.

### M2 — MAJOR (carried, mechanism corrected): the buy lane is dead, and the cause is no longer the mount

Live, lane host `CobradorWave` (100.90.101.9):

    routstrd.service  ActiveState=failed  SubState=failed  Result=exit-code
                      ExecMainStatus=203  NRestarts=9
                      ActiveEnterTimestamp: (never — it never came up)
                      InactiveEnterTimestamp: Sat 2026-09-26 23:25:48 CEST   (latched, ~12 h old)
                      UnitFileState=enabled      ExecStartPre=/home/c03rad0r/.hermes/scripts/routstrd_lane_guard.sh --port 8008
    ss -ltnp | grep -E ':8008|:8009'   → no listener

Correction to pass 5's mechanism: the mount is **back**. `/mnt/dq05-lexar` is an `fuse.sshfs` mount of `c03rad0r@100.90.22.201:/mnt`, `ActiveState=active`, `ActiveEnterTimestamp=Sun 2026-09-27 11:08:38 CEST` (previous `InactiveEnterTimestamp=Sat 2026-09-26 21:56:45 CEST`); the bun binary and the routstrd daemon entry both resolve now. The `203/EXEC` was latched during the outage window and nothing has retried since. So: the lane is still dead, but "the mount is gone" is no longer the reason.

Operational consequence worth flagging: `tasks/main.yml` ends with "Assert the routstrd buy lane is active (deploy-time guarantee)". The next converge of `playbook-live-router.yml` on this node will **hard-fail** until the unit is reset/reclaimed (or the node reboots with the mount up).

### M3 — MAJOR (new this pass): the shipped idempotency harness is GREEN exactly where the role is broken

`tests/run_routstrd_lane_idempotency.sh` runs at `RESULT: PASS` **both** at the reviewed head and at the tip `9bdb2a0b` — including at the tip where M1 makes a real converge impossible. Reason, from the harness's own fixture (lines 66-90): the fixture play sets `gather_facts: no` **and pins `routstrd_funding_guard_script` / `routstrd_funding_guard_log` itself** (via `lookup('env','HOME')`), overriding the very defaults that regressed; plus `routstrd_lane_manage_service: false` / `routstrd_lane_manage_crontab: false` (→ `skipped=8`). The pytest role test is the only shipped artifact that catches M1 (claim 5b), i.e. the "second apply changed=0" evidence offered for claim 3e does not cover the defaults branch, the service branch, or the crontab branch.

### M4 — MINOR (new this pass): one MRE test is host-dependent, so the MRE suite cannot be green on a clean box

`tests/test_routstrd_balance_cron.py::test_missing_wallet_fails_loudly_and_writes_no_row` asserts `"read FAILED" in (stdout+stderr)`. Its `_run()` helper overrides `ROUTSTRD_WALLET_DB` and `ROUTSTRD_CLI` but **not** `HOME`/`WALLET_DIR`, so the guard's not-installed-by-design carve-out (claim 4c) pre-empts the assertion on any host without `~/.routstrd`. Measured, same guard build, same env:

    host A (/home/c03rad0r/repos/…/mre-rev5, no ~/.routstrd): rc=0  "routstrd wallet not present on this host"   → test FAILS
    host B (CobradorWave, has ~/.routstrd):                    rc=2  "⚠️ funding guard: routstrd wallet read FAILED — daemon: … | db: wallet db missing: …" → test PASSES

The guard behaviour is intentional; the **test** is not hermetic. Practical impact: `pytest tests/test_routstrd_funding_guard.py tests/test_routstrd_balance_cron.py` at the reviewed head is `1 failed, 34 passed` on a clean runner and (expected) `35 passed` on the lane host — a spurious RED for anyone running the suite outside the lane box. (The full `pytest tests/` on this box also errors at collection on `tests/test_urgency_cost_estimator.py` — `ImportError: cannot import name 'display_urgency_costs'` — pre-existing and unrelated to this scope; I did not chase it.)

### M5 — MINOR: the WAL docstring overstates the failure mode (code is correct)

See 4d. `mode=ro` **does** replay the WAL (98 proofs vs 96 for `immutable=1`) on this wallet; only `immutable=1` is WAL-blind. `_read_balance_db`'s technique (private copy + read-write open + `wal_checkpoint(TRUNCATE)`) is right regardless, so nothing shipped is broken — but the comment will mislead the next reader, and the same wording is echoed in the test docstring ("a naive immutable/read-only reader misses them").

### M6 — MINOR: the deployed guard is a working-tree edit, not a checkout of main

The lane host's `~/merchant-routing-engine` is a symlink to `/mnt/dq05-lexar/cw-offload/merchant-routing-engine` on the sshfs mount. There, `git rev-parse HEAD` = `07a20dec` ("docs(routing): routstr sell-lane -> Kalman tracking design"), which is **not** an ancestor of `8b91148` (`git rev-list --count 07a20dec..8b91148` = 12), and `git status --short` shows `M scripts/routstrd_funding_guard.py` (staged/working-tree modification), while the last commit touching the guard is `4f3da5c`. Content is nevertheless byte-identical to the reviewed revision (`md5 fec2e50a…` = blob at `8b91148`), so claim 4a holds — but the running artifact was **not** produced by checking out the reviewed commit, and the box's tree is dirty. Correctness-by-md5, not correctness-by-provenance.

### M7 — MINOR: parts of the supplied live-state baseline do not survive re-measurement

* Wallet: the guard's WAL-safe read gives **35,514** minibits sats (+5,000 orangesync, excluded from `network_sats`); "35,508" is the WAL-blind (`immutable=1`) figure — the same number the review brief uses. Guard-driven rows in `api_burn.db` (`limit_remaining=35.514`) corroborate 35,514.
* `routstr`/`routstrd` `effective_cost`: finite `1.0` in-process, not `inf` (claim 2c).
* `origin/master` tip: `9bdb2a0b`, not `a81041ee` (head table).
* Deployed `~/.hermes/bot/flat_router.py` md5 `1dc1091bd4d264edbfe2c0e9cae89454` == blob at `origin/master` — **VERIFIED**, this part of the baseline holds.

### M8 — MINOR / open observation: the guard cron is present and firing, but not at a steady */5 cadence

Verbatim crontab on the lane host:

    #Ansible: routstrd-funding-guard
    */5 * * * * /home/c03rad0r/merchant-routing-engine/scripts/routstrd_funding_guard.py >> /home/c03rad0r/merchant-routing-engine/logs/routstrd_funding_guard.log 2>&1

Rows prove execution: `provider='routstrd_network'` rows at 2026-09-27 09:15:08 / 09:10:14 / 09:10:01 / 09:09:28 **UTC** (= 11:15 / 11:10 / 11:10 / 11:09 CEST — 1-7 min before measurement), all `source: "db"`, all `network_sats: 35514`. But the 25 h shape is bursts, not a steady 5-minute beat: 8 rows 2026-09-26 19:23:47→19:55:40, then nothing until 2026-09-27 11:09:28; total 109 rows in 25 h (≈1 per 14 min). The gap matches the sshfs outage exactly (mount `Inactive` 2026-09-26 **21:56:45** → `Active` 2026-09-27 **11:08:38**; first guard row 31 s after the mount returned) — the guard's own script path is inside that mount, so while the mount is down the cron entry cannot execute at all. Cause of the earlier 19:55→21:56 gap is **unknown** (mount was up then). Two further notes: (i) three writes land inside a 46 s window, which is not a `*/5` pattern, i.e. more than one caller writes the `routstrd_network` provider key; (ii) the guard log's mtime is `Aug 31 07:00` — **stale log mtime is not evidence of inertness** (a healthy guard prints nothing), so pass 5's "several consecutive */5 slots went by and the log never grew" inference is not sound. The log mtime plus the syslog/journal greps are simply the wrong instrument; `api_burn.db` rows are the instrument.

### Minor notes on the reviewed code, not defects

* The funding-guard cron task is correctly gated: `when: … routstrd_funding_guard_stat.stat.exists`, and the entry is deduped by `#Ansible: routstrd-funding-guard` (live proof above). The role preflights the **script** (gates the install) and the **log dir** (only drives a warning, `tasks/main.yml:252-266`). **Pass-5 finding "F3, the cron was installed with only a log-dir preflight" is REFUTED** — the script stat is in the `when:` list.
* No diagnostic exists if the guard script stat is false: the cron task is then silently skipped (`state: present` not reached) with no warn/fail. Minor gap in an otherwise well-instrumented role; relevant because that path is exactly what an sshfs outage produces.

## What pass 6 adds over pass 5

1. M1 re-attributed to `37d6b55f` with an independently reproduced failure (pass 5 filed it against the reviewed head).
2. M2 mechanism corrected: the sshfs mount is back; the unit is latched, not mount-starved.
3. M3 is new: the idempotency harness passes at a head where the role cannot converge, so claim 3e's evidence is narrower than presented.
4. M4 is new: the MRE suite's single RED is host-dependent (differential proof), not a plain shipped-test failure.
5. M8 is new: the guard cron **is** firing (rows in `api_burn.db` 1-7 min before measurement) — refuting the "inert cron" inference — with the sshfs outage identified as the cause of the multi-hour gaps.
6. Pass-5 F3's mechanism refuted from the task block.
7. Claim 4d's live measurement re-derived (98 vs 96 proofs).

## Unknowns (marked, not guessed)

* Live `:8008/v1/models` listing (claim 1c) — nothing listens on 8008/8009 on either host; not reproducible this pass.
* The live router process's own `effective_cost` for `routstr`/`routstrd` (claim 2c) — I read the in-process value of the repo code only; I did not introspect or perturb the running router.
* Cause of the 2026-09-26 19:55→21:56 row gap (M8) and of the sub-minute write clustering (M8).
* Whether `37d6b55f`'s defaults regression is the sole blocker to a clean converge on other nodes (only the lane host was inspected).
* No kanban card for this brief was resolvable in any board (no task title, body, result or comment matches the brief, its author dispatch id `deleg_17f47ac6`, or this review's scope), so the artefact could not be attached to a card; it is written to the reports path below.

## Evidence index (all paths durable)

* `~/reports/reviews/merchant-routing-routstr-v41-lane-wiring-kimi-pass6.md` (this file)
* `~/reports/reviews/routstr-v41-pass6-kimi-probes/idem_a81041ee.log` — harness output at the reviewed head
* `~/reports/reviews/routstr-v41-pass6-kimi-probes/find_card_p6.py` — card-resolution sweep
* `~/reports/reviews/routstr-v41-pass6-kimi-probes/card_sweep_p6.txt` — its output
* `~/reports/reviews/routstr-v41-pass6-kimi-probes/select_probe.py`-equivalent run (candidate/effective_cost probe; copy under `ho-redfirst/`)
* `~/reports/reviews/routstr-v41-pass6-kimi-probes/f1_probe_p6.yml` — the M1 Jinja re-derivation
* `~/reports/reviews/routstr-v41-pass6-kimi-probes/mre_redfirst/` — head tests vs pre-fix guard (`4429060`)

Reproduce the decisive runs: harness `cd <worktree> && bash tests/run_routstrd_lane_idempotency.sh`; wiring `python3 -m pytest scripts/engine/test_routstr_v41_lane_wiring.py -q`; role `python3 -m pytest tests/test_routstrd_lane_role.py -q`; MRE guard `python3 -m pytest tests/test_routstrd_funding_guard.py tests/test_routstrd_balance_cron.py -q`; M1 `ansible-playbook -i localhost, f1_probe_p6.yml`.
