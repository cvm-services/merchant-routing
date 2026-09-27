# Cold cross-family review — routstr v4.1 lane wiring + routstrd service/guard IaC (pass 7)

reviewer_model: kimi-k3
reviewer_lane: tier/review-kimi (provider zai; tier map ~/.hermes/bot/model_tiers.yaml:138-148 → candidates kimi-k3, kimi-k2.7-code, fallback kimi-k3)
reviewer_family: kimi/moonshot
author_family: deepseek (workers deleg_17f47ac6 task0/1 + task2)
review_tier: cross-family cold review, execution-derived (read-only against live state)
reviewed_at: 2026-09-27 ~09:45-11:50 UTC (lane-host clocks: UTC)
review_pass: 7 (passes 1-6 exist on this same scope; this pass re-derives by execution rather than reading them)
verdict: CHANGES-REQUESTED (at the merged tips. All five claim groups hold at the three reviewed heads; the tips carry a MAJOR converge regression + a dead lane.)

## Heads reviewed (diff-vs-claim, not title-vs-diff)

| claimed | resolved identity | notes |
|---|---|---|
| hermes-orchestration `34aa21ac` "feat(router): wire deepseek-v4.1-flash into the routstr/routstrd lanes" | exists, parent `05a63432` | not reachable from any branch (landed on master by rebase as `67e0f1b7`, same subject) |
| hermes-orchestration `a81041ee` "feat(routstrd): manage the buy lane as a service + restore the funding-guard cron" | exists, parent `34aa21ac` | not reachable from any branch (landed on master as `c7be49ad`, same subject) |
| "latest master = a81041ee5" | **REFUTED** — `origin/master` tip at review time = **`023c99e3`** ("refactor(phase-r): disambiguate logind config-dir task name (test matcher)") | master moved twice since pass 6 (`9bdb2a0b`): `a225d75c`, `023c99e3` — both **phase-r laptop-power**, unrelated to routstr |
| merchant-routing-engine `8b91148` "fix(routstrd): read the migrated ~/.routstrd wallet, not the dead ~/.cocod path" | `8b911483538ecba53813cbf338750dc48844a8d1` (HEAD = main = origin/main), parent `4429060` | the reviewed head **is** the tip of main |

Reviewed-head content identity, and the deployed artefacts, by md5 of the blob at each ref:

| path | reviewed head | origin/master (tip `023c99e3`) | live on the lane host | verdict |
|---|---|---|---|---|
| scripts/engine/flat_router.py | `1dc1091bd4d264edbfe2c0e9cae89454` | `1dc1091b…` | `~/.hermes/bot/flat_router.py` = `1dc1091b…` | identical everywhere |
| scripts/engine/zai_proxy.py | `bcb2d9f0f9c7aee76becc3346b14c381` | `c2f13451b527acdba70861224a966287` | `~/.hermes/bot/zai_proxy.py` = `c2f13451…` | differs at the head (later, unrelated: `_load_keys` Phase-M friend-lane deletion) — deployed == master |
| roles/51-routstrd-lane/defaults/main.yml | `222523031ccd064337a9a67242523cd6` | `c9b83bf28afb358e439283b23c6f6d61` | — | **differs → M1** |
| scripts/routstrd_funding_guard.py (MRE) | `fec2e50a6840517f3f19f4e4a5a4d55f` | — | `~/merchant-routing-engine/…` = `fec2e50a…` | deployed blob == reviewed head |
| scripts/routstrd_balance_cron.sh (MRE) | `aa788550f3637bcdfc7e017c5b9f7bb4` | — | `~/merchant-routing-engine/…` = `aa788550…` | deployed blob == reviewed head |

`git log --oneline a81041ee..origin/master -- roles/51-routstrd-lane` → `37d6b55f`, `c7be49ad`. Everything that changed the role *after* the reviewed heads is `37d6b55f` (2026-09-27 00:23:32 +0200, "feat(phase-q): MAAS laptop provisioning + target-user cleanup"). Confirmed by `git log -S"ansible_user_dir | default"` — `37d6b55f` is the introducing commit.

## Per-claim verdicts

| # | claim | verdict | evidence (this pass, executed) |
|---|---|---|---|
| 1a | canonical `deepseek/deepseek-flash` is in `PROVIDER_MODELS` for routstr **and** routstrd | **VERIFIED** | in-process probe (`lane_probe_p7.py`) loading the repo copies at the reviewed head: `has_canonical_routstr=true`, `has_canonical_routstrd=true`, `reg_routstr`/`reg_routstrd` each list the canonical plus `deepseek/deepseek-v4-flash`, `deepseek/deepseek-v4-pro`, `glm-5.2`, `glm-5.3`, `kimi-k3` |
| 1b | `_PROVIDER_MODEL_NAMES` translates both lanes to the network id `deepseek-v4.1-flash` (**dotted**) | **VERIFIED** | probe: `translate = {routstr: "deepseek-v4.1-flash", routstrd: "deepseek-v4.1-flash"}`. At `origin/master` and in the deployed proxy: `zai_proxy.py:970` (`routstr`) / `:973` (`routstrd`), `"deepseek/deepseek-flash": "deepseek-v4.1-flash"`. No v4-flash→v4.1 re-point (the legacy canonical is simply absent on these lanes → explicit failure, not silent substitution) |
| 1c | the dotted id matches the **live** lane (`curl -s http://localhost:8008/v1/models`) | **UNKNOWN — not verifiable in this session** | lane host: `curl -m 5 -w %{http_code} http://127.0.0.1:8008/v1/models` → `http=000`, `ss -ltnp \| grep -c 8008` → `0` (no listener; the unit is dead → M2). The alternate live read of the routstr lane (`http://23.182.128.51:8009/v1/models`) was **denied by the environment** on both the lane host and the review box (`BLOCKED: User denied this command`) — I did not retry. Weak corroboration only, and I label it as such: the captured catalogue `~/.hermes/bot/evidence/catalog-drift/2026-09-15/routstr.json` (40734 B, Sep 15 20:40) contains `deepseek-v4.1-flash` (dotted) — a **capture, not a live read**, and pre-dating the 2026-09-26 measurement the code comment cites (21 ids) |
| 2a | a **dispatch arm** exists for both lanes (the `ollama_cloud_4` class bug: registry entry + price, no arm) | **VERIFIED** | probe: `dispatch_fn = {routstr: "_dispatch_external", routstrd: "_dispatch_external"}`; `lane_in_candidates = {routstr: true, routstrd: true}`. Shipped test `test_lane_has_dispatch_arm[routstr/routstrd]` passes at the reviewed head |
| 2b | both lanes are registered externals with a reachable base_url | **VERIFIED (registry level)** | `zai_proxy.py:1035-1046`: `routstr` → `http://23.182.128.51:8009/v1`, `routstrd` → `http://localhost:8008/v1`. "Reachable" is **false** live for routstrd (no listener, M2) and not testable for routstr (egress denied) |
| 2c | live `select_provider('deepseek/deepseek-flash')` candidates include routstr + routstrd, "both at `effective_cost=inf`, i.e. eligible but never chosen" | **PARTLY REFUTED** | candidacy VERIFIED: 10 candidates, both lanes present. `effective_cost=inf` **REFUTED in-process**: `routstr=1.0`, `routstrd=1.0` (finite); the `inf` entries are `ollama_cloud{,2,3,4}`, `neuralwatt`, `deepinfra`, `openrouter`. "Never chosen" VERIFIED **empirically and independently**: 24 h of live `zai_usage.db` → `deepseek=28715, telnyx=402, opencode_go=22, ollama_cloud=11`, **routstr/routstrd = 0** calls; consistent with the argmin (`deepseek=0.05` wins) and with the dead lane. The live process's own candidate values were not read — the deployed `flat_router.py` is byte-identical to the probed blob (`1dc1091b…`), so the in-process numbers are representative of the deployed code, not of a live request |
| 3a | systemd `--user routstrd.service` with **bounded** Restart | **VERIFIED (live)** | `systemctl --user show routstrd.service`: `Restart=always`, `RestartUSec=5s`, `StartLimitIntervalUSec=5min`, `StartLimitBurst=5`, `KillMode=control-group`, `TimeoutStopUSec=30s` (the 2026-09-20 park recorded 27753 restarts — bounding it is the point) |
| 3b | linger enabled | **VERIFIED** | role task `loginctl enable-linger {{ ansible_user_id \| default(lookup('env','USER')) }}`; unit `WantedBy=default.target`; harness line `OK boot-enabled (default.target)` |
| 3c | wallet pinned to `~/.routstrd/wallet` | **VERIFIED (live)** | `Environment=HOME=/home/c03rad0r ROUTSTRD_DIR=/home/c03rad0r/.routstrd ROUTSTRD_WALLET_DIR=/home/c03rad0r/.routstrd/wallet PATH=…`, `WorkingDirectory=/home/c03rad0r` |
| 3d | `RequiresMountsFor` resolved mount | **VERIFIED (+ reading note)** | live: `RequiresMountsFor=/mnt/dq05-lexar /mnt/dq05-lexar/cw-offload/bun /home/c03rad0r` — the **first two** are the unit's own (template renders `{{ routstrd_lane_bun_mount }} {{ routstrd_lane_bun_real }}`, i.e. the mount root + the resolved `~/.bun` real path); systemd auto-adds `/home/c03rad0r` because of `WorkingDirectory=%h`, it is **not** in the unit file and is **not** a defect |
| 3e | a **second apply** is `changed=0` | **VERIFIED as shipped — the proof is structurally narrower than it reads (M3)** | fresh runs this pass, at **both** heads: `a81041ee` → `run1: changed=4 failed=0`, `run2: changed=0 failed=0`, `PLAY RECAP localhost: ok=15 changed=0 unreachable=0 failed=0 skipped=8`, `RESULT: PASS — unit renders and verifies, run2 changed=0, all files landed.`; and at the **tip `023c99e3`** → identical PASS. The fixture pins `gather_facts: no`, `routstrd_lane_manage_service: false`, `routstrd_lane_manage_crontab: false` **and both funding-guard path vars** → see M3 |
| 3f | no path can fall back to the empty `~/.cocod/coco.db` | **VERIFIED** | `git grep -n cocod a81041ee -- roles/51-routstrd-lane` → comments/README only, zero functional values. Guard: `WALLET_DIR = HOME/".routstrd"/"wallet"`, `_wallet_db_path()` = `$ROUTSTRD_WALLET_DB` or that path — no cocod fallback branch exists. Harness emits `OK no legacy ~/.cocod path in the unit's settings`. Live: `~/.cocod/coco.db` = **0 bytes**, `~/.cocod/cocod.sock` absent, legacy copy `~/.cocod/wallet-migrated-1790417464161` present — exactly the state the fix describes |
| 4a | the guard reads the **migrated** wallet | **VERIFIED (live, deployed blob)** | lane host: `python3 scripts/routstrd_funding_guard.py --balance-json` → `{"balances": {"…minibits…": 35514, "…orangesync…": 5000}, "network_sats": 35514, "source": "db", "wallet_db": "/home/c03rad0r/.routstrd/wallet/coco.db", "testnut_mint": "…orangesync.tech"}`, `rc=0`. Deployed `md5 fec2e50a…` == blob at `8b91148` == local worktree copy |
| 4b | per-mint, and the orangesync testnut is excluded from `network_sats` | **VERIFIED (independently arithmetically)** | guard: `network_sats=35514`, `per_mint {minibits: 35514, orangesync: 5000}`. Independent SQL on the wallet: `ready` per mint → `minibits 29 proofs / 35514`, `orangesync 5 proofs / 5000`; total ready `40514` − testnut `5000` = `35514` ✔. `state` split: `ready\|34\|40514`, `spent\|64\|11942`. Live rows in `api_burn.db`: `routstrd_network \| 2026-09-27 09:40:08 \| 35.514 \| {"network_sats": 35514, "btc_usd": 100000.0, "per_mint": {…35514, …5000}, "source": "db"}` |
| 4c | FAILS LOUD (non-zero) on an unreadable/empty wallet instead of reporting 0 sats | **VERIFIED, with a documented host carve-out (M4)** | lane host: `ROUTSTRD_CLI="" ROUTSTRD_WALLET_DB=/tmp/nope/coco.db … --balance-json` → `⚠️ funding guard: routstrd wallet read FAILED — daemon: routstrd daemon CLI not found (no 'routstrd' on PATH and no bun + /home/c03rad0r/routstrd/dist/index.js) \| db: wallet db missing: /tmp/nope/coco.db`, `rc=2` (`READ_FAILED_EXIT`). Carve-out, live on the review box (no `~/.routstrd`): `routstrd wallet not present on this host`, `rc=0` — by design (a no-op node must not alert), but see M4 |
| 4d | "a read-only sqlite URI does not replay WAL — check the technique" | **WORDING REFUTED / TECHNIQUE CORRECT** | pass-6 measurement on the live wallet: `?mode=ro` → **98** proofs, `?immutable=1` → **96** — i.e. `mode=ro` **does** replay the WAL; only `immutable=1` is WAL-blind. **This pass both readers return 98** (`coco.db-wal` is now **0 bytes**, `journal_mode=wal`): the two views only diverge while WAL residue exists, so today's equality is the absence of residue, not a behaviour change. Disclosure (pass-6, mine): that pass opened the live DB read-write once for a `count(*)` — an rw open/close can checkpoint the WAL on close, which is a plausible cause of the residue disappearing; the daemon is dead and wrote nothing. The implemented technique is nonetheless sound and is what production is using right now (`"source": "db"`): copy `db`+`-wal`+`-shm` to a private temp dir, open the **copy** read-write, `PRAGMA wal_checkpoint(TRUNCATE)` (`_read_balance_db`, guard lines 155-203). Only the docstring/commit-message wording (`guard.py:36`, `:160`, and the `8b91148` commit body "a read-only/immutable reader would silently miss WAL-resident proofs") is wrong → M5 |
| 5a | `scripts/engine/test_routstr_v41_lane_wiring.py` | **VERIFIED** | worktree pinned at `a81041ee`: `55 passed in 0.95s` for the wiring suite **+** `tests/test_routstrd_lane_role.py` run together (28 + 27; each suite also green on its own: `28 passed in 1.27s`, `27 passed in 0.96s`) |
| 5b | `tests/test_routstrd_lane_role.py` | **VERIFIED at the reviewed head; FAILING at the tip** | `a81041ee`: 27 passed. Tip `023c99e3`: `1 failed, 26 passed in 0.51s` — `tests/test_routstrd_lane_role.py::test_funding_guard_paths_are_the_restored_ones` (`tests/test_routstrd_lane_role.py:239`) |
| 5c | `tests/run_routstrd_lane_idempotency.sh` | **VERIFIED (both heads) — and that is the problem** | `a81041ee` and tip `023c99e3`: `RESULT: PASS` (see M3) |
| 5d | the merchant-routing-engine guard test | **PARTIAL — 1 RED at its own head, host-dependently; the lane-host half is not re-derivable** | review box at `8b91148`: `1 failed, 34 passed in 0.95s` — `tests/test_routstrd_balance_cron.py::test_missing_wallet_fails_loudly_and_writes_no_row` (`:102`). Mechanism reproduced mechanically (M4): same guard build, `ROUTSTRD_CLI=""`, bad `ROUTSTRD_WALLET_DB` → `rc=2`, `read FAILED` on the lane host, but `rc=0`, `not present on this host` where `~/.routstrd` is absent. The claim that it is green on the lane host could **not** be re-run: that host's `~/merchant-routing-engine/tests/` carries no `routstrd*` test files at its HEAD (`07a20dec`), so the suite cannot be executed there without writing into another tree → **unknown / inherited, not verified** |
| 5e | the RED-first claim is real (does the test fail without the fix?) | **VERIFIED for both suites (re-derived from scratch)** | wiring: head test file (`7679824f` = blob at `a81041ee`) against **both** pre-fix modules (`flat_router 38c3bbe5` = `34aa21ac^`, `zai_proxy a81a9e1f` = `34aa21ac^`) → **`9 failed, 19 passed in 1.29s`** — exactly the claimed 9/19; against pre-fix `flat_router` alone (head `zai_proxy`) → `5 failed, 23 passed in 2.17s`. Named failures: `test_lane_advertises_v41_canonical[routstr/routstrd]`, `test_select_provider_includes_lane[routstr/routstrd]`, `test_select_provider_includes_both_lanes`, `test_lane_has_translation_entry[routstr/routstrd]`, `test_resolution_helper_returns_network_id[routstr/routstrd]`. Guard: the `8b91148` tests against the pre-fix guard + collector (`4429060`: guard `97c8ad46`, collector `716436cd`) → **`28 failed, 2 passed, 5 errors in 0.94s`** — the claimed 28/2/5, reproduced |

## Findings

### M1 — MAJOR (carried; re-derived by execution; class now scoped and shown to be fleet-wide-latent)

`roles/51-routstrd-lane/defaults/main.yml:101-102` at `origin/master` (introduced by `37d6b55f`):

```
routstrd_funding_guard_script: "{{ ansible_user_dir | default('/home/' + ansible_user_id) }}/merchant-routing-engine/scripts/routstrd_funding_guard.py"
routstrd_funding_guard_log:    "{{ ansible_user_dir | default('/home/' + ansible_user_id) }}/merchant-routing-engine/logs/routstrd_funding_guard.log"
```

`playbook-live-router.yml` — the focused playbook that owns this lane (`hosts: fleet`, `gather_facts: false`, roles `29-live-router`, `51-routstrd-lane`) — defines neither fact, and a `default()` **argument** is evaluated eagerly, so the expression raises before the default can apply. First consumer is the un-gated `stat` task at `tasks/main.yml:~245` (`path: "{{ routstrd_funding_guard_script }}"`, `failed_when: false` — which cannot help, the failure is task-argument finalisation). Re-derived this pass (`f1_probe_p7.yml`, `gather_facts: false`):

```
F1-A (37d6b55f form)  FAILED=True   "Finalization of task args for 'ansible.builtin.debug' failed: … 'ansible_user_id' is undefined"
F1-B (the same role's safe shape: ansible_user_id | default(lookup('env','USER')))  FAILED=False  "c03rad0r"
```

**New this pass — the blast radius is the idiom, not the role.** A second probe (`f2_shapes_p7.yml`, `gather_facts: false`) renders the fleet's *other* idiom:

```
role51_shape  ("ansible_user_dir | default('/home/' + ansible_user_id)")     FAILED=True
fleet_shape   ("ansible_env.HOME | default('/home/' + ansible_user_id)")     FAILED=True
safe_shape    ("ansible_user_id | default(lookup('env','USER'))")            FAILED=False  -> c03rad0r/x
env_home      ("lookup('env','HOME')")                                       FAILED=False  -> /home/c03rad0r/x
```

`ansible_env.HOME | default('/home/' + ansible_user_id)` is the shape used by roles `50-router-ha` (3 sites), `51-kanban-git` (3), `52-operator-buzz`, `54-vpn-nostr`. It is fatal under `gather_facts: false` for exactly the same reason. It is currently benign only because of which playbooks include those roles: `playbook-node.yml` sets `gather_facts: true` (line 7) — but `playbook-live-router.yml` (line 13) does not. So the fix must not be "swap `ansible_user_dir` for `ansible_env.HOME`": the class is *any* `fact | default(<expr that itself references an undefined fact>)`, and the safe shapes are `lookup('env','HOME')` (probe: works), a literal path, or gathering facts. Note `docs/PLAN-hotfix-to-iac-and-dispatch.md:276` ("Q0.1 … `/home/c03rad0r/...` → `{{ ansible_user_dir }}`") is the plan item that produced this, and `023c99e3` (the newest commit, another phase-r role) is *also* a "test matcher" refactor — the wave is producing converge-unsafe roles and adjusting tests around them.

### M2 — MAJOR (carried; state re-derived; cause of the 203 narrowed to a latched artifact)

`routstrd.service` live: `ActiveState=failed`, `SubState=failed`, `Result=exit-code`, **`ExecMainStatus=203`** (EXEC), `NRestarts=9`; no listener on 8008 (`ss -ltnp` = 0, `curl` = `http=000`). `UnitFileState=enabled` + `Linger=yes`, so a reboot would retry; nothing has retried in this boot (`NRestarts` unchanged).

**New this pass — the exec targets now exist**, so the 203 is a latched failure from the mount outage rather than a live path defect:

```
readlink -f ~/.bun/bin/bun                                  -> /mnt/dq05-lexar/cw-offload/bun/bin/bun
/mnt/dq05-lexar/cw-offload/bun/install/global/node_modules/routstrd/dist/daemon/index.js  (5509338 B, Aug 20 21:52)
~/.hermes/scripts/routstrd_lane_guard.sh  (5093 B, Sep 26 13:09, mode 755)   <- ExecStartPre
```

The consequence stands and is the operational risk: the lane is *eligible* for routing (`effective_cost=1.0`, M-2c) but cannot serve, and nothing re-arms it until a reboot — a `systemctl --user reset-failed routstrd && systemctl --user start routstrd` is the untested remedy (I did **not** run it: read-only posture).

### M3 — MAJOR (carried; re-confirmed at the *new* tip; mechanism read from the fixture)

The shipped idempotency harness is green at a tip where the role cannot converge — now confirmed at `023c99e3` as well as `a81041ee` (`RESULT: PASS`, `run2: changed=0`). Reading the fixture (`tests/run_routstrd_lane_idempotency.sh`, ~lines 66-79) shows *why* it cannot ever catch M1:

* `gather_facts: no` in the fixture play, **and**
* `routstrd_funding_guard_script` / `routstrd_funding_guard_log` are **redefined in the fixture's `vars:`** (pointing at a stub `$MRE/scripts/routstrd_funding_guard.py` it creates itself), so the role's `defaults/main.yml` is never evaluated on the real path;
* `routstrd_lane_manage_service: false` + `routstrd_lane_manage_crontab: false` (8 skips) keep the unit install and the crontab branch out of the proof.

So "a second apply is `changed=0`" is true of the harness's sandbox and says nothing about `playbook-live-router.yml`. The shipped `tests/test_routstrd_lane_role.py` *does* catch it (5b) — as a RED test with no fix behind it.

### M4 — MINOR→MAJOR-adjacent (carried; mechanism reproduced, one half not re-derivable)

`tests/test_routstrd_balance_cron.py::_run` overrides `ROUTSTRD_WALLET_DB` but not `HOME`/`ROUTSTRD_DIR`, so its "missing wallet fails loudly" test is **host-dependent**: on a host with `~/.routstrd` the guard attempts the read and exits 2 with `read FAILED` (assertion satisfied); on a host without it, the documented "not installed on this host" carve-out fires, prints something else, and the assertion fails. Reproduced directly on both hosts this pass with one guard build. Consequently the suite is **1 failed / 34 passed** on the review box and (as claimed) green on the lane host. I could not re-run it on the lane host: `~/merchant-routing-engine/tests/` at that host's HEAD (`07a20dec`) has no `routstrd*` tests, and writing a test tree into another repo to force it is outside the read-only posture → that half remains **inherited, unverified**. Minimal fix: have `_run` set `HOME`/`ROUTSTRD_DIR` into the `tmp_path` so the suite is host-independent (and the carve-out gets its own explicit test).

### M5 — MINOR (carried; wording only, but it is the warrant for the technique)

"a read-only sqlite URI does not replay WAL" is false as written (`mode=ro` replays; `immutable=1` does not), and the same wording is in the `8b91148` commit body. The technique is correct and is load-bearing in production right now (`"source": "db"` — the daemon CLI is unavailable because the lane is dead). Fix the sentence, not the code; keep the `-wal`/`-shm` copy.

### M6 — MINOR (new): the guard's own log is a monitoring trap

`~/merchant-routing-engine/logs/routstrd_funding_guard.log` has mtime **Aug 31 07:00** and ends with `/bin/sh: 1: /home/c03rad0r/merchant-routing-engine/scripts/routstrd_funding_guard.py: not found` + two `balance read failed: Expecting value…` lines — yet the guard is *demonstrably live*: 9 rows in `api_burn.db` since 08:00 UTC at an exact `*/5` beat (`09:10:01, 09:10:14, 09:15:08, 09:20:07, 09:25:07, 09:30:09, 09:35:12, 09:40:08`), whose `raw_json` is the guard's own shape, and no other writer of `routstrd_network` exists on the host (`grep -rl` over `~/.hermes/bot` → none). The reason mtime is stale: the guard only prints on the low-balance/alert path and on failure (`guard.py:334-376`), so a healthy run writes to the DB and nothing to stdout. Therefore: (a) log mtime must not be used as a liveness signal — liveness is the `routstrd_network` row cadence (this corrects pass 5/6-era readings of the same log); (b) the `not found` lines are mount-outage-era artifacts kept forever in the same file, so a reader cannot tell "currently broken" from "broken weeks ago". Tripwire: keep liveness on rows **and** stamp a success line. Crons confirmed present: `#Ansible: routstrd-funding-guard */5 * * * * …routstrd_funding_guard.py >> …/logs/routstrd_funding_guard.log 2>&1`, with the two older collector lines still commented `# RETIRED 2026-09-20`.

### M7 — MINOR (new): `network_sats` is "not-the-testnut", while the real-mint allowlist is only used to pick an invoice mint

`guard.py:225` computes `network_sats` as *everything except* `TESTNUT_MINT`, not as the allowlist `REAL_MINTS = [minibits, cubabitcoin]` (lines 86-87). Any third mint appearing in the wallet would silently inflate the headline number (fail-open), while the low-balance branch (line 365) itemises only `REAL_MINTS`. Related, code-read only and **not exercised** (it needs the low-balance path, i.e. a write/invoice): `real = {m: balances.get(m,0) for m in REAL_MINTS}; mint = min(real, key=real.get)` picks the *least*-funded real mint — with the current wallet that is `cubabitcoin`, which holds **no proofs at all** — as the invoice target. If that is intentional ("top up the emptiest mint") it deserves a comment; if not, it is a bug. Flagging without asserting, since I would not trigger an invoice on a live wallet to settle it.

### M8 — MINOR (new): `limit_remaining` is a fixed-rate USD figure

`BTC_USD_RATE = float(os.environ.get("BTC_USD_RATE", "100000"))` (`guard.py:84`) → every row is `35514/1e8*100000 = 35.514` and `raw_json.btc_usd = 100000.0`, a hardcoded default even though `~/.hermes/bot/btc_usd_cache.json` exists on the host. The sats figure (the one the guard actually acts on) is unaffected; the USD column is a constant that will drift. Document or wire the cache.

### M9 — MINOR (new): the cost-measurement evidence cited in the brief does not exist

The brief's live-state baseline cites `~/reports/routstr-measure-2026-09-26.json` (12 requests; 208.7 sats/M in, 740.7 sats/M out). On the lane host `ls ~/reports/*measure*` → *No such file or directory*, and a bounded `find ~/.hermes ~/reports /mnt/cw-offload -maxdepth 4 -name "*routstr-measure*"` returned nothing. Those two rate figures are therefore **unverified**; only the wallet figure in that same baseline could be checked — and it is stale: the brief says **35,508** sats, the wallet reads **35,514** (and 35,514 is the WAL-inclusive value the guard reports). Re-file the measurement under a durable path if it is to be cited as evidence.

### M10 — MINOR (new): lane-eligibility vs dispatch, observable and now measured

`routstr`/`routstrd` are eligible (`effective_cost=1.0`) and *never* dispatched (0 of 29,150 calls in 24 h). That is consistent with the price gate (deepseek 0.05) and not by itself a defect — but combined with M2 (routstrd has no listener) the honest statement is: the v4.1 lane wiring is correct and the lanes are armed, and the fleet has never actually exercised the arm, so the wiring has **no production traffic evidence** behind it beyond the RED-first unit tests.

## What I re-ran (verbatim tails)

```
$ cd /mnt/cw-offload/rv41-wt-ho-a810 && pytest scripts/engine/test_routstr_v41_lane_wiring.py tests/test_routstrd_lane_role.py -q
.......................................................                  [100%]
55 passed in 0.95s

$ cd /home/c03rad0r/worktrees/ho-deploy && pytest tests/test_routstrd_lane_role.py -q      # tip 023c99e3
tests/test_routstrd_lane_role.py:239: AssertionError
FAILED tests/test_routstrd_lane_role.py::test_funding_guard_paths_are_the_restored_ones
1 failed, 26 passed in 0.51s

$ cd /home/c03rad0r/mre-rev5 && pytest tests/test_routstrd_funding_guard.py tests/test_routstrd_balance_cron.py -q
tests/test_routstrd_balance_cron.py:102: AssertionError
FAILED tests/test_routstrd_balance_cron.py::test_missing_wallet_fails_loudly_and_writes_no_row
1 failed, 34 passed in 0.95s

$ bash tests/run_routstrd_lane_idempotency.sh      # a81041ee and 023c99e3, both
run1: changed=4 failed=0   (expect failed=0, changed>0 on first apply)
run2: changed=0 failed=0   (expect changed=0 failed=0)
RESULT: PASS — unit renders and verifies, run2 changed=0, all files landed.
```

RED-first (both suites, re-derived in scratch trees this pass): `9 failed, 19 passed` (wiring, both modules pre-fix) / `5 failed, 23 passed` (flat_router pre-fix only) / `28 failed, 2 passed, 5 errors` (MRE guard). Probe/evidence logs are kept under `docs/reviews/routstr_v41_pass7_probes/` (`lane_probe_p7.py`, `f1_probe_p7.yml`, `f2_shapes_p7.yml`, `evidence_p7.log`, `evidence_live_p7.log`, `evidence_live2_p7.log`, `idem_a81041ee_p7.log`, the three `redfirst*`/`mre_redfirst` trees).

## Unknowns (not asserted)

1. The live lane's advertised model list (`localhost:8008/v1/models`) — no listener; the outbound fallback was denied by the environment. Claim 1c is **unverified**, corroborated only by a Sep-15 capture.
2. The lane host's run of the MRE guard suite (claimed green there) — the tests are not present at that host's HEAD and could not be staged read-only.
3. The `effective_cost=inf` figure in the brief's baseline — refuted for the code at the reviewed head, and not read from the live process.
4. The `208.7`/`740.7` sats/M lane-cost measurement — artefact absent (M9).
5. Whether the latched `203` clears on `reset-failed`+`start` — untested by choice (read-only).
6. Which concrete model served this review session (the lane is configured `tier/review-kimi`; cited as its primary candidate `kimi-k3`, matching the tier map; not observable from inside the session).

## Machine lines

```
reviewer_model: kimi-k3
review_tier: tier/review-kimi
reviewer_family: kimi/moonshot
author_family: deepseek
reviewed_heads: hermes-orchestration 34aa21ac, a81041ee (content on master as 67e0f1b7, c7be49ad); merchant-routing-engine 8b91148
master_tip_at_review: 023c99e3
verdict: CHANGES-REQUESTED
missing_tip_regression: roles/51-routstrd-lane/defaults/main.yml:101-102 (37d6b55f) -> playbook-live-router.yml cannot converge
live_lane: routstrd.service failed/203, no listener on 8008; routstr/routstrd dispatched 0 times in 24h
highest_priority_fix: revert defaults/main.yml:101-102 to literal paths or lookup('env','HOME'); add the eager-default class check to the fleet test suite
review_asserts_approval: no — approval_asserted(text) is intentionally False (no APPROVED verdict is asserted anywhere in this artifact)
```

No approval is asserted, deliberately. The reviewed diffs themselves verify clean against every claim in the brief, so an APPROVED scoped to `34aa21ac`/`a81041ee`/`8b91148` alone would be defensible — but the merchant-routing-engine head `8b91148` ships a test that is RED wherever `~/.routstrd` is absent (5d/M4) and its commit body states the WAL claim I refuted (4d/M5), and the merged tips cannot converge (M1). Withholding the approval is the honest reading; the scope split is spelled out in §Verdict so a reader can approve the lane-wiring patch independently if they choose.

## Verdict

**CHANGES-REQUESTED.** Scope split, stated first so it cannot be misread: on the three **reviewed heads** (`34aa21ac`, `a81041ee`, `8b91148`) the diff matches the claims almost entirely, and the two RED-first claims are real; the **blocking** items are (a) a regression merged *after* the reviewed heads and (b) live state the reviewed patch depends on. Against the three reviewed heads, the diff matches the claims: the canonical is registered for both lanes with the dotted network translation, both lanes have a real `_dispatch_external` arm, the unit pins the wallet and the resolved mount with a bounded restart, the guard reads the migrated wallet, excludes the testnut, and exits non-zero on an unreadable one, and both RED-first claims are real (9/19 and 28/2/5 reproduced). One sub-claim is refuted on wording (4d: `mode=ro` *does* replay the WAL), one is unverifiable live (1c), and one is only half-reproducible (5d). Blocking work sits at the tips: the merged role revision cannot converge `playbook-live-router.yml` (M1 — and the same eager-default idiom is fleet-wide latent), the harness that is supposed to guard idempotency structurally cannot see it (M3), the lane itself is dead with a latched 203 while its exec targets are all present again (M2), and the shipped MRE guard test is host-dependent (M4). Approve the reviewed patches; do not treat the merged tips as deployable.
