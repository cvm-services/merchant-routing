# Cross-family cold review — routstr v4.1 lane wiring + routstrd service/guard IaC

reviewer_model: tier/review-kimi
author_family: deepseek
review_date: 2026-09-27
review_pass: 5 (independent re-derivation; supersedes the pass-3/pass-4 drafts in the workspace repo)
verdict: CHANGES-REQUESTED (3 MAJOR: the deploy cannot converge on the target host, the buy-lane unit is dead, the restored guard cron is inert — plus 2 shipped tests RED at their own heads)

Evidence dir for this pass (probes, verbatim logs, live captures):
`/home/c03rad0r/reports/reviews/routstr-v41-laneservice-kimi-probes/`

---

## 1. Heads reviewed (resolved, not taken from the brief)

| repo | ref | resolution | what it touches |
|---|---|---|---|
| hermes-orchestration | `34aa21ac` | exists, reachable from `master` | `scripts/engine/flat_router.py` (+22/-1), `scripts/engine/zai_proxy.py` (+23), `scripts/engine/test_routstr_v41_lane_wiring.py` (+285), `scripts/ops/routstr_measure.py` (+596), 2 docs |
| hermes-orchestration | `a81041ee` (= `origin/master` tip) | exists, tip of `master` | `playbook-live-router.yml`, `playbook.yml`, `roles/51-routstrd-lane/**` (README/defaults/handlers/tasks/template), `scripts/fleet/routstrd_lane_guard.sh`, `state/fleet/routstr_parked.json`, `tests/run_routstrd_lane_idempotency.sh`, `tests/test_routstrd_lane_role.py` (11 files, +1368/-3) |
| merchant-routing-engine | `8b91148` | exists on `main` (fresh clone `/home/c03rad0r/mre-rev5`) | `scripts/routstrd_funding_guard.py`, `scripts/routstrd_balance_cron.sh`, `tests/test_routstrd_funding_guard.py`, `tests/test_routstrd_balance_cron.py` |

Blob identity (the two landing commits are *not* byte-identical to the tip — verified, so nobody can claim "same file"):

```
34aa21ac       flat_router=449ddbc1  zai_proxy=57e11a80
a81041ee       flat_router=449ddbc1  zai_proxy=57e11a80
origin/master  flat_router=449ddbc1  zai_proxy=4c4afa17   <- 4 ins / 3 del of zai_proxy drift after the reviewed commit
```

`flat_router.py` is byte-identical across both reviewed commits and the tip; `zai_proxy.py` moved on, but the routstr/routstrd entries under review survive at the tip (verified by reading them at `origin/master`).

**Lane host (where the changed code is deployed):** `md5 ~/.hermes/bot/flat_router.py` on `c03rad0r@100.90.101.9` = `1dc1091bd4d264edbfe2c0e9cae89454` = md5 of the `origin/master` working-tree copy. The deployed proxy *does* carry the reviewed wiring (`PROVIDER_MODELS["routstrd"]` incl. `deepseek/deepseek-flash`, 13× `deepseek-v4.1-flash` in the deployed `zai_proxy.py`). → the brief's "deployed md5 == origin/master blob" is VERIFIED.

---

## 2. Per-claim verdict table

Legend: **V** = verified from code/execution by this reviewer · **R** = refuted · **U** = unverifiable / unknown.

| # | claim (from the brief) | verdict | evidence |
|---|---|---|---|
| 1a | canonical `deepseek/deepseek-flash` added to `PROVIDER_MODELS` for **routstr** | **V** | `flat_router.py:314` (`"deepseek/deepseek-flash",`); blob `449ddbc1` at both reviewed commits **and** at the tip |
| 1b | … for **routstrd** | **V** | `flat_router.py:321-325`; same blob at tip; deployed copy on the lane host also has it |
| 1c | `_PROVIDER_MODEL_NAMES` translates that canonical → network id `deepseek-v4.1-flash` (**DOT**) | **V** | `zai_proxy.py:968-971` (`"routstr"`) and `972-974` (`"routstrd"`) — both map to `deepseek-v4.1-flash`; also present at the tip |
| 1d | the id matches the **live lane** (`curl :8008/v1/models`) | **U (now R-by-state)** | I ran it on the lane host: `curl: (7) Failed to connect to localhost port 8008 … http=000` — no listener on 8008/8009 and `routstrd.service` is `failed`. The live-id check cannot be repeated today because the lane is dead (see F2). Pass 3 recorded it verified while the daemon was up. |
| 2a | a dispatch arm exists for both lanes (no `ollama_cloud_4`-class trap) | **V** | executed in-process at the tip: `_make_dispatch_fn('routstr') -> _dispatch_external`, `_make_dispatch_fn('routstrd') -> _dispatch_external` (probe log `select_provider_probe_master.log`); arm is the catch-all `_dispatch_external` → `handler._try_external_single(name, …)` |
| 2b | … and the registry entry the arm needs exists | **V** | `zai_proxy.EXTERNAL_PROVIDERS["routstrd"].base_url` = `http://localhost:8008/v1`, `["routstr"]` = `http://23.182.128.51:8009/v1` (the shipped test asserts this; I read both entries) |
| 2c | both lanes are candidates for the canonical id ("eligible but **never chosen**, effective_cost=**inf**") | **V for candidacy / R for `inf`** | probe: 10 candidates, `routstr` and `routstrd` both present — but at `effective_cost=1.0` (**finite**, the `_SEED_RATES` value), while `ollama_cloud*`/`neuralwatt`/`deepinfra`/`openrouter` are `inf`. They lose the argmin to `deepseek` (0.05), so "never chosen" holds — but for *price*, not for `inf`. |
| 3a | `systemd --user` unit, bounded restart | **V** | template `roles/51-routstrd-lane/templates/routstrd.service.j2:15-16,38-39` (`StartLimitIntervalSec`/`StartLimitBurst` + `Restart=always`/`RestartSec`); live unit shows `StartLimitIntervalSec=300 StartLimitBurst=5 Restart=always RestartSec=5` |
| 3b | linger | **V** | live `loginctl show-user c03rad0r -p Linger` → `Linger=yes` |
| 3c | wallet pinned to `~/.routstrd/wallet` | **V** | template lines 32-33 `Environment=ROUTSTRD_DIR=%h/.routstrd` + `ROUTSTRD_WALLET_DIR=%h/.routstrd/wallet`; same lines in the deployed unit |
| 3d | `RequiresMountsFor` = the **resolved** mount | **V (technique)** | template line 12 uses the roles' resolved vars; deployed unit: `RequiresMountsFor=/mnt/dq05-lexar /mnt/dq05-lexar/cw-offload/bun` — resolved at converge time from `readlink -f ~/.bun`, and it *is* the true backing mount… which does not exist on this host (F2) |
| 3e | a **second** apply is `changed=0` | **V, with a caveat** | I re-ran the shipped harness at `a81041ee`: `run1: changed=4 failed=0` / `run2: changed=0 failed=0` / `RESULT: PASS — unit renders and verifies, run2 changed=0, all files landed.` **Caveat:** the fixture runs with `routstrd_lane_manage_service=false` + `routstrd_lane_manage_crontab=false`, so `skipped=8` — the unit-install/linger/cron branches are *not* covered by the idempotency proof (F5) |
| 3f | no path can fall back to the empty `~/.cocod/coco.db` | **V** | every `cocod` hit in `a81041ee`'s role is a comment/README (template lines 31/34/40, defaults line 57, README 16/93); no functional path. Guard side: `WALLET_DB = HOME/".routstrd"/"wallet"/"coco.db"` |
| 3g | service is live / the change is operational | **R** | `routstrd.service`: `ActiveState=failed Result=exit-code ExecMainStatus=203 NRestarts=9`; `ExecStart`'s bun (`/mnt/dq05-lexar/cw-offload/bun/bin/bun`) **does not exist** on the host. 203 = `203/EXEC`. See F2. |
| 4a | guard reads the migrated wallet | **V** | `8b91148` is exactly this repoint (`WALLET_DIR = HOME/".routstrd"/"wallet"`, `WALLET_DB_ENV` override) |
| 4b | per-mint, orangesync testnut excluded from `network_sats` | **V** | `TESTNUT_MINT = "https://mint.orangesync.tech"`; `network_sats_from()` sums all mints except it; live wallet: minibits `35514` ready + orangesync `5000` → `network_sats = 35514` (testnut reported per-mint, excluded from the post) |
| 4c | FAILS LOUD (non-zero) on unreadable/empty wallet instead of reporting 0 | **V (with a documented carve-out)** | I executed the shipped guard: with `~/.routstrd/wallet` present and the DB missing → `⚠️ funding guard: routstrd wallet read FAILED — daemon: … \| db: wallet db missing: …`, **rc=2** (`READ_FAILED_EXIT`). Missing table / zero proofs raise the same `WalletReadError`. **Carve-out:** on a host with **no `~/.routstrd` at all** `main()` takes the deliberate "not installed" skip-gate → prints `routstrd wallet not present on this host` and returns **rc 0**. Both cases captured in `guard_loudfail_probe.log` |
| 4d | "a read-only sqlite URI does not replay WAL — check the technique" | **V for the technique, R for the wording** | The guard does **not** use a read-only/immutable URI: it copies `db`+`-wal`+`-shm` into a temp dir and opens the **copy read-write** + `PRAGMA wal_checkpoint(TRUNCATE)` → WAL *is* replayed (`_read_balance_db`, lines 155-203). That is the correct technique. The **docstring** (lines 36-38) generalises wrongly: *"A read-only/`immutable=1` reader does NOT replay the WAL"* — measured on the live wallet, `mode=ro` **does** replay it: `ro`=98 proofs / minibits-ready `35514` vs `immutable=1`=96 / `35508`. Only `immutable=1` skips the WAL. |
| 5a | `scripts/engine/test_routstr_v41_lane_wiring.py` | **V** | `28 passed in 1.21s` @ `a81041ee` (clean worktree `t_61679837-gate`) |
| 5b | `tests/test_routstrd_lane_role.py` | **V, but RED at the tip** | `27 passed` @ `a81041ee`; **`1 failed, 26 passed` @ `master`** (`test_funding_guard_paths_are_the_restored_ones`, assertion at `tests/test_routstrd_lane_role.py:239`) → the test is GREEN only at its own commit, RED at the merged tip (F4) |
| 5c | `tests/run_routstrd_lane_idempotency.sh` | **V** | `run1 changed=4 failed=0` / `run2 changed=0 failed=0` / `RESULT: PASS` (re-run by me; see caveat 3e) |
| 5d | the merchant-routing-engine guard test | **V, but 1 RED here** | `1 failed, 34 passed in 2.75s` @ `8b91148` — the failing one is `test_routstrd_balance_cron.py::test_missing_wallet_fails_loudly_and_writes_no_row`, and it is **host-dependent** (F5/F6): it fails on any host without `~/.routstrd` |
| 5e | RED-first: the test fails without the fix | **V (executed, not carried)** | wiring: `a81041ee` test against `34aa21ac^` code → `9 failed, 19 passed in 1.07s` (all 9 are the wiring assertions; the file's pre-existing assertions still pass, so the signal is attributable to the production change). guard: `8b91148` tests against `4429060` (= `8b91148^`) → `28 failed, 2 passed, 5 errors in 1.24s` |

---

## 3. Findings

**F1 — MAJOR (reproduced live by me at the tip `9bdb2a0b`): role 51 cannot converge on the shipped deploy shape.**
`roles/51-routstrd-lane/defaults/main.yml:101-102` define

```
routstrd_funding_guard_script: "{{ ansible_user_dir | default('/home/' + ansible_user_id) }}/merchant-routing-engine/scripts/routstrd_funding_guard.py"
```

but `playbook-live-router.yml` (the only playbook that runs this role) is `gather_facts: false`. Templating the *argument* of `default()` is enough to explode: `'ansible_user_id' is undefined` at `tasks/main.yml:245` (`ansible.builtin.stat`). Reproduced this pass with the shipped playbook shape against the tip:

```
fatal: [localhost]: FAILED! => {"changed": false, "msg": "Task failed: Finalization of task args for 'ansible.builtin.stat' failed: Error while resolving value for 'path': 'ansible_user_id' is undefined"}
localhost : ok=11 changed=4 unreachable=0 failed=1 skipped=8
PLAYBOOK rc=2
```

(log: `role_path_probe_master.log`; probe: `role_probe_master.sh`). Note the partial-apply shape: `changed=4` files land, then the guard-stat task aborts — so the role has *already* mutated the host before it dies (non-atomic), and the cron it was supposed to restore is not the one installed. **The change under review (a81041ee) shipped this expression while also shipping the `gather_facts: no` harness that hides it** — pass 3's idempotency harness only passes because it *overrides* `routstrd_funding_guard_script/_log` (see `run_routstrd_lane_idempotency.sh` fixture vars), i.e. the harness tests a shape production never runs.

**F2 — MAJOR: the buy lane has never run under the new unit.**
Deployed unit (`~/.config/systemd/user/routstrd.service` on CobradorWave):

```
ExecStart=/mnt/dq05-lexar/cw-offload/bun/bin/bun /mnt/dq05-lexar/cw-offload/bun/install/global/node_modules/routstrd/dist/daemon/index.js --port 8008 --host 127.0.0.1
RequiresMountsFor=/mnt/dq05-lexar /mnt/dq05-lexar/cw-offload/bun
```
Path probe on the same host: `/mnt/dq05-lexar` **exists**, `/mnt/dq05-lexar/cw-offload/bun` and everything under it **does not**. `systemctl --user show` → `ActiveState=failed SubState=failed Result=exit-code ExecMainStatus=203 NRestarts=9`; `ss -ltn` shows no listener on 8008/8009; `journalctl --user -u routstrd.service` is empty. So: `203/EXEC` because `ExecStart` points at DQ05's Lexar toolchain that is not present on the box now running the lane; `RequiresMountsFor` is satisfied *vacuously* (the mountpoint exists), so the pin does not protect against exactly this case. The brief's "routstrd.service active+enabled+linger" is **false on the `active`** leg (enabled+linger are true). As long as this holds, claim 1d (live `:8008/v1/models` id) cannot be re-verified at all, and the `routstrd` lane cannot serve.

**F3 — MAJOR: the restored funding-guard cron is inert (fires 127 every 5 min).**
Crontab on the lane host does contain the restored entry (with the Ansible marker), but its payload resolves through a **broken symlink**:

```
*/5 * * * * /home/c03rad0r/merchant-routing-engine/scripts/routstrd_funding_guard.py >> /home/c03rad0r/merchant-routing-engine/logs/routstrd_funding_guard.log 2>&1
~/merchant-routing-engine -> /mnt/dq05-lexar/cw-offload/merchant-routing-engine   (target absent)
ls: cannot access '…/scripts/routstrd_funding_guard.py': No such file or directory
```
`a81041ee` re-enabled this cron without checking that the referenced path resolves on the target host (and without `creates`/preflight). So the guard that "keeps the now live wallet funded" did not execute in the window it was introduced to protect, and writes no log. Same class of defect as F1/F2: the IaC pins *where the file should be* rather than *where it is*.

**F4 — MAJOR: `tests/test_routstrd_lane_role.py` is RED at the head that matters.**
`27 passed` at its own commit `a81041ee`, but `1 failed, 26 passed` at the merged tip (`master` = `9bdb2a0b`): `test_funding_guard_paths_are_the_restored_ones` asserts the guard path is `/home/c03rad0r/…`, while the tip's role resolves it via the F1 expression. The delivered change set is therefore green only *before* the follow-up commit that is now the tip — the review target and the test's green point are different heads.

**F5 — MINOR/MAJOR: the guard's loud-failure test is host-dependent, so its RED/GREEN says nothing about the code.**
`test_missing_wallet_fails_loudly_and_writes_no_row` sets `ROUTSTRD_WALLET_DB=<missing>` and asserts `"read FAILED" in output`, but the guard's *first* branch wins on a host without `~/.routstrd` (proved both ways, `guard_loudfail_probe.log`):

```
case A  HOME has ~/.routstrd/wallet   -> "⚠️ funding guard: routstrd wallet read FAILED — …"   rc=2
case B  HOME has no ~/.routstrd       -> "routstrd wallet not present on this host"            rc=0
```

The fixture never neutralises `HOME`/`WALLET_DIR`, so the test is RED wherever `~/.routstrd` is absent (this dq05 worker host) and GREEN on the lane host. The assertion is *right*; the fixture is under-specified. This is a sharper diagnosis than pass 4's "stale assertion".

**F6 — MINOR: the "second apply = changed=0" proof skips the branches that actually failed.**
The harness runs with `routstrd_lane_manage_service=false` + `routstrd_lane_manage_crontab=false` (`skipped=8` of ~19 tasks). Everything that touches the user systemd manager, linger and the crontab — the three things that are broken in production (F2/F3) — is excluded by construction. Pass 3 conceded this as its own caveat (m6); it survives into the reviewed IaC as the *only* idempotency evidence.

**F7 — MINOR: the brief's cited cost measurement is unreachable and off-target.**
`~/reports/routstr-measure-2026-09-26.json` exists on **neither** the worker host nor the lane host (`find`/`ls` both empty). The 208.7 / 740.7 sats-per-M figures therefore cannot be checked against the cited artifact. Separately, `scripts/ops/routstr_measure.py` (added by `34aa21ac`) drives `localhost:8008` **directly with the translated network id**, bypassing the router — so even when it runs it measures *the lane's* price, never the router's selection or end-to-end cost. It is not evidence about routing.

**F8 — MINOR: the brief's wallet figure is the WAL-blind one.**
"wallet 35,508 sats minibits" is exactly what `immutable=1` returns (96 proofs, minibits-ready 35508). The WAL-replaying read — which is what the guard itself uses — gives **35514** (98 proofs, 29 minibits-ready proofs), i.e. the quoted figure **understates by 6 sats**. Measured both ways on the live wallet this pass (log `live_state_cobradorwave.log`); `+5,000 orangesync` is correct.

**F9 — MINOR: the docstring's WAL claim is wrong in a way that invites a future regression.**
`routstrd_funding_guard.py:36-38` says a "read-only/`immutable=1` reader does NOT replay the WAL". `mode=ro` **does**; only `immutable=1` does not (98 vs 96 proofs live). The code is fine, the sentence is not — and it is the sentence the next maintainer will read.

---

## 4. Corrections to earlier passes

- **pass 4 M4 (direction)** — pass 4 concluded the WAL-blind read *overstates* the balance (40508 vs 35514) by comparing the `immutable` **total over all mints** with the `ro` **minibits-only** number. Like-for-like, the WAL-blind view **understates**: 35508 < 35514 minibits-ready, 40508 < 40514 total. Same wallet, same instant, both readers run back to back. F8.
- **pass 4's "stale assertion"** on the balance-cron test — recharacterised in F5: the assertion is correct for the case it means to test; the fixture's missing `HOME`/`WALLET_DIR` neutralisation is the defect, which makes the test host-dependent rather than simply stale.
- **pass 4's m7** (measure harness is not a router measurement) — re-derived and confirmed with the added datapoint that the cited JSON does not exist on either host (F7).

---

## 5. What I executed (verify-able handles)

| artifact | what |
|---|---|
| `routstr-v41-laneservice-kimi-probes/green_a81041ee.log` | `28 passed` wiring + `27 passed` role @ `a81041ee` |
| `…/green_role_master.log` | `1 failed, 26 passed` role @ `master` `9bdb2a0b` |
| `…/green_guard_mre.log` | `1 failed, 34 passed` guard+cron @ `8b91148` |
| `…/red_first_wiring.log` | `9 failed, 19 passed` (`a81041ee` test vs `34aa21ac^` code) |
| `…/red_first_guard_mre.log` | `28 failed, 2 passed, 5 errors` (`8b91148` tests vs `4429060`) |
| `…/idem.log` | full `run_routstrd_lane_idempotency.sh` transcript (run1/run2 + `systemd-analyze --user verify rc=0`) |
| `…/role_path_probe_master.log` + `…/role_probe_master.sh` | **F1** reproduction at the tip (`PLAYBOOK rc=2`, `failed=1`) |
| `…/select_provider_probe_master.log` + `…/select_probe.py` | candidate list + effective costs + `_make_dispatch_fn` for both lanes |
| `…/live_state_cobradorwave.log` | first-hand lane-host unit/cron/listener/curl/path-existence capture |
| `…/guard_loudfail_probe.log` | case A (`rc=2`, "read FAILED") vs case B (`rc=0`, skip-gate) |
| `…/find_card*.py`, `…/dump_card.py` | the card-resolution sweep (below) |

The **card itself could not be resolved** — 5th pass, same as passes 3/4. I scanned every `kanban.db` under `~/.hermes/kanban/boards/` and `~/hermes-kanban/boards/` (110+ boards) for task titles/bodies/results matching `cross-family`, `routstr v4.1`, `lane wiring`, `routstrd service`, `guard iac`, `deleg_17f47ac6`, `routstrd-lane`, `routstr-v41`, and then for *any* title containing `routstr`: no card for this review brief exists in any board DB on this host. `hermes kanban attach` also does not exist in this build. This artifact is therefore delivered by path, and named by scope rather than by `tid`.

---

## 6. Verdict

**CHANGES-REQUESTED.** The wiring half of the change set is genuinely correct and load-bearing (claims 1a-1c, 2a-2b, all VERIFIED, with a real RED-first signal of 9 failing assertions on pre-fix code). The IaC half is not deployable as shipped and is not running: the role fails to converge on the only playbook that runs it (F1), the unit it installs points its `ExecStart` at a mount that does not exist on the target, so the buy lane is `203/EXEC`-dead and has never served under it (F2), and the cron it "restored" cannot execute its payload (F3). Two shipped tests are RED at their own heads (F4, F5), and the only idempotency evidence excludes the branches that are actually broken (F6).

Recommended minimal fixes, in order: (1) resolve the guard path from `routstrd_lane_home` (or `lookup('env','HOME')`), never `ansible_user_id`, and run the role with the shipped `gather_facts: false` shape in CI; (2) make the role verify `routstrd_lane_daemon_entry` exists *before* writing/starting the unit, and fail with a named message (the `guard` script already has the pid/cgroup machinery to do it); (3) preflight the guard script path in the cron task and skip-with-warning instead of installing a 127-ing entries; (4) fix the two tests' fixtures (`HOME`, `WALLET_DIR`) and pin the role test to the resolved expression; (5) extend the idempotency harness to the service/cron branches or state explicitly in the README that they are untested; (6) correct the docstring's `mode=ro` claim.

## 7. Unknowns (explicitly not resolvable from this seat)

- Live `GET :8008/v1/models` (claim 1d) — the daemon is down; no listener. **U.**
- Live router selection / the observed `effective_cost=inf` — needs live process state I must not perturb; the repo code path yields finite `1.0`. **U.**
- The 208.7 / 740.7 sats-per-M figures — cited artifact absent on both hosts. **U.**
- Whether the VPS2 `routstr` lane (`23.182.128.51:8009`) is reachable — out of reach of this host's ssh; not probed. **U.**
- Whether another stale clone of `merchant-routing-engine` elsewhere on the fleet could mask F3 — only the lane host matters and it is checked. **U.**
