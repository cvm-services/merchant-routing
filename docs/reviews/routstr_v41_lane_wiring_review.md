# Cross-family cold review — routstr v4.1 lane wiring + routstrd service/guard IaC

reviewer_model: tier/review-kimi (provider: zai)  — kimi family
author_family: deepseek (workers deleg_17f47ac6 task0/1 + task2)
cross_family: SATISFIED (author deepseek, reviewer kimi)
date: 2026-09-27
worker_host: dq05 (100.90.22.201)   live_state_host: cobrador / CobradorWave (100.90.101.9)
review_mode: cold — every claim re-derived from code, diffs, live host state and re-run tests.
             Nothing in the author's summary was taken as given.
artifact: ~/reports/reviews/merchant-routing-routstr-v41-lane-wiring-kimi.md
repo_copy: docs/reviews/routstr_v41_lane_wiring_review.md (merchant-routing @ local commit)

## 0.1 tid / card

Could not be resolved from this worker. Searched all 115 board DBs under
~/.hermes/kanban/boards/*/kanban.db (read-only) for the branch names
`pr/routstr-v41-lane-wiring` / `pr/routstrd-lane-service`, `routstr-v41`,
`routstrd_lane_service`, `deleg_17f47ac6`, `routstrd_funding_guard` and for
any card created since 2026-09-25 mentioning routstr — zero hits. No kanban
toolset in this session, so no card attach is possible from here; the artifact
is referenced by path. Filename therefore carries a slug, not a tid.

## 0.2 SHA reconciliation (diff-vs-claim — done before evaluating anything)

| item | cited by the brief | what the repo actually shows |
|---|---|---|
| hermes-orchestration lane wiring | `34aa21ac` | NOT an ancestor of `origin/master` (`git merge-base --is-ancestor 34aa21ac origin/master` → NO). Code-equivalent PR tip = `67e0f1b7` (restricted-path diff `67e0f1b7^..34aa21ac` over scripts/roles/tests/docs/playbooks/state = empty). |
| hermes-orchestration routstrd service | `a81041ee` "= latest master" | NOT an ancestor of `origin/master` either. PR tip = `c7be49ad`. **Latest master = `bb587eb3`**, which *contains* `67e0f1b7` and `c7be49ad` but neither cited SHA. |
| merchant-routing-engine wallet fix | `8b91148` → main | CONFIRMED: `/mnt/cw-offload/merchant-routing-engine`, `main` tip = `8b91148`, `merge-base --is-ancestor 8b91148 main` → YES. |

Consequence, and the reason this matters: **`a81041ee` is not what is deployed.**
`origin/master` (=`bb587eb3`) carries later changes to the very files under
review, and the deployed router engine matches *that* head:

```
cobrador:~/.hermes/bot/flat_router.py  md5 1dc1091b…  == origin/master blob == a81041ee blob == 67e0f1b7 blob
cobrador:~/.hermes/bot/zai_proxy.py    md5 c2f13451…  == origin/master blob   (a81041ee blob = bcb2d9f0…, DIFFERENT)
git diff a81041ee origin/master -- roles/51-routstrd-lane/   → defaults/main.yml (funding-guard paths), 4 lines
git diff a81041ee origin/master -- scripts/engine/zai_proxy.py → 7 lines (later Phase-M friend-key removal)
```

I therefore evaluated **three** heads, not one: the cited `a81041ee`, the actual
merged master `bb587eb3` (deployed), and the engine `8b91148`.

---

## 1. Verdict table

| # | claim | verdict | one-line why |
|---|---|---|---|
| 1 | canonical `deepseek/deepseek-flash` in `PROVIDER_MODELS` for routstr **and** routstrd, `_PROVIDER_MODEL_NAMES` → `deepseek-v4.1-flash` (DOT), id checked against the live lane | **VERIFIED** (code: repo + deployed) / live-curl **NOT REPRODUCIBLE** (lane down) — corroborated independently | registry + translation present and byte-identical in repo and in the deployed `~/.hermes/bot/*.py`; `:8008/v1/models` unreachable today (http=000, no listener), but the daemon's own `routstr.db:usage_tracking` holds 39 rows of `model_id=deepseek-v4.1-flash` and the independent measure file records `advertised_in_catalog=true, catalog_size=21` |
| 2 | dispatch arm exists for both lanes (no `ollama_cloud_4`-class "registered but never dispatched" bug) | **VERIFIED** | in-process resolution returns `_dispatch_external` for both lanes, with `EXTERNAL_PROVIDERS` base_url, per_token tier, seed 1.0; live they are ranked candidates (last-resort, inf) — a lane with no arm could not be a candidate at all |
| 3 | role 51: `systemd --user` unit, bounded Restart, linger, wallet pinned to `~/.routstrd/wallet`, `RequiresMountsFor` resolved mount; 2nd apply changed=0; no path falls back to empty `~/.cocod/coco.db` | **VERIFIED** (IaC + idempotency, both heads) / **REFUTED LIVE** | every structural pin is present in the *deployed* unit and a second sandbox apply is `changed=0 failed=0`; but the service is `failed` (203/EXEC, NRestarts=9) and systemd has stopped retrying — the lane is DOWN |
| 4 | guard reads the migrated wallet, per-mint, excludes orangesync from `network_sats`, FAILS LOUD (non-zero) on unreadable/empty wallet, WAL-safe read technique | **VERIFIED** (code + live probes) / **PARTLY REFUTED** | wallet path + per-mint + testnut exclusion verified against the live DB; missing DB → rc 2 "read FAILED" **on a host that has ~/.routstrd/wallet**; the WAL technique is WAL-complete (measured). Two holes: (a) the "not present on this host" gate returns **rc 0** for a missing wallet when the dir is absent, (b) the *restored* */5 cron cannot execute on the router host |
| 5 | three named test files + engine guard test re-run; RED-first is real | **PARTLY REFUTED** | wiring test 28 passed + genuine RED-first (9 failed / 19 passed reverted); idempotency harness PASS both runs (run1 changed=4, run2 changed=0); **but** `tests/test_routstrd_lane_role.py` is **RED at merged master** (1 failed / 26 passed) and `tests/test_routstrd_balance_cron.py` is **RED at engine main** (1 failed / 34 passed); the "full engine suite 20F/570P" figure was not reproduced (17F/542P) |

Live-state premise from the brief, checked: deployed md5 == origin/master **VERIFIED**;
`routstrd.service active` **REFUTED** (failed); `enabled + linger` **VERIFIED**;
guard cron `*/5` **VERIFIED as a crontab line, REFUTED as a running job**;
wallet figure **VERIFIED but WAL-blind** (see §4); lane cost 208.7 / 740.7 sats/M
**VERIFIED** — from `/mnt/cw-offload/reports/routstr-measure-2026-09-26.json` (run[2]), not `~/reports/`.

---

## 2. Evidence, claim by claim

### Claim 1 — canonical id + DOT translation

Repo (`origin/master`), deployed (cobrador `~/.hermes/bot`), and `a81041ee` all agree:

```
== routed lanes in PROVIDER_MODELS:
   routstr : ['deepseek/deepseek-flash','deepseek/deepseek-v4-flash','deepseek/deepseek-v4-pro','glm-5.2','glm-5.3','kimi-k3']
   routstrd: [ same six ]
== _resolve_model_for_provider: {'routstr': 'deepseek-v4.1-flash', 'routstrd': 'deepseek-v4.1-flash'}
zai_proxy._PROVIDER_MODEL_NAMES['routstrd']['deepseek/deepseek-flash'] = 'deepseek-v4.1-flash'
```

Note the DOT (`deepseek-v4.1-flash`), which is the right id: the dash form
(`deepseek-v4-1-flash`) appears nowhere in the translation maps.

Live half of the claim, honestly: **cannot be re-run today.**
`curl http://localhost:8008/v1/models` → `http=000`; `ss -ltnp` on cobrador shows
**no listener on 8008 or 8009 at all**. So the "check the id against the live lane"
step is *not* satisfied by today's state. It is, however, corroborated twice from
the lane's own artefacts on disk:

```
routstr.db usage_tracking (the daemon's own request log):
   model_id 'deepseek-v4.1-flash'   39 rows      ← the dotted id really was served
   model_id 'tinfoil-deepseek-v4-1-flash'  (different lane)
reports/routstr-measure-2026-09-26.json run[0..2]:
   lane routstrd, base http://localhost:8008, canonical_model deepseek/deepseek-flash,
   network_model_id deepseek-v4.1-flash, advertised_in_catalog true, catalog_size 21,
   requests 12/12 ok / 0 failed
```

**Verdict: VERIFIED on the code (all three heads + deployed); live-endpoint check
UNVERIFIABLE TODAY, corroborated by the daemon's usage DB and the measure file.**

### Claim 2 — a dispatch arm for both lanes

The `ollama_cloud_4` failure mode is "provider in `PROVIDER_MODELS`, no dispatch
arm, chosen on price, never dispatched". Probed in-process against the deployed
engine and against the repo:

```
== tier/seed/external:
  routstr   dispatch=_dispatch_external tier='per_token' seed=1.0 ext_base='http://localhost:8009/v1' map={'deepseek/deepseek-flash': 'deepseek-v4.1-flash'}
  routstrd  dispatch=_dispatch_external tier='per_token' seed=1.0 ext_base='http://localhost:8008/v1' map={'deepseek/deepseek-flash': 'deepseek-v4.1-flash'}
== select_provider('deepseek/deepseek-flash')  [deployed engine, live state, cobrador]
  [0] ollama_cloud_4 0.001   [1] ollama_cloud 0.002   [2] deepseek 0.05
  [3] ollama_cloud_2 inf     [4] ollama_cloud_3 inf   [5] neuralwatt inf
  [6] deepinfra inf          [7] openrouter inf       [8] routstr inf     [9] routstrd inf
```

Both lanes resolve to a real arm (`_dispatch_external`), carry an
`EXTERNAL_PROVIDERS` entry, a `per_token` tier and a seed rate — the class bug is
**not** present. Two caveats stated as measured, not as conclusions:

* Live, both lanes sit at `effective_cost=inf`, i.e. **last-resort** (fleet
  convention: ∞ = last-resort, not delist). With `ollama_cloud_4`/`ollama_cloud`
  healthy they are never chosen — the lane wiring is correct but **carries no
  traffic while anything else is up**. In the repo run (no live price state) the
  same lanes came back at `1.0`, ranked 2nd/3rd, i.e. the ∞ is live health/pricing
  state, not a code property. The brief's "both at effective_cost=inf" premise is
  **confirmed live** and **not** a code property.
* `routstr`'s base is `http://localhost:8009/v1` — the VPS2 tunnel lane, which the
  in-repo comment itself records as down at change time and which is **still down
  today** (no listener, http=000). So one of the two newly-wired candidates points
  at a dead endpoint. That is a wiring-completeness observation, not a dispatch-arm bug.

**Verdict: VERIFIED.**

### Claim 3 — role `51-routstrd-lane`

Structurally complete. Deployed unit on cobrador, verbatim (comments stripped):

```
[Unit] Description=routstrd — Routstr daemon (buy lane 127.0.0.1:8008)
       After=network-online.target ; Wants=network-online.target
       RequiresMountsFor=/mnt/dq05-lexar /mnt/dq05-lexar/cw-offload/bun
       StartLimitIntervalSec=300 ; StartLimitBurst=5
[Service] Type=simple
       ExecStart=/mnt/dq05-lexar/cw-offload/bun/bin/bun /mnt/dq05-lexar/…/routstrd/dist/daemon/index.js --port 8008 --host 127.0.0.1
       ExecStartPre=/home/c03rad0r/.hermes/scripts/routstrd_lane_guard.sh --port 8008
       Environment=HOME=%h
       Environment=ROUTSTRD_DIR=%h/.routstrd
       Environment=ROUTSTRD_WALLET_DIR=%h/.routstrd/wallet   ← the wallet pin
       Environment=PATH=%h/.bun/bin:%h/.local/bin:/usr/local/bin:/usr/bin:/bin
       Restart=always ; RestartSec=5 ; TimeoutStopSec=30 ; WantedBy=default.target
```

* bounded Restart: `Restart=always` **plus** `StartLimitIntervalSec=300` /
  `StartLimitBurst=5` (the 2026-09-20 park recorded counter 27753) — VERIFIED.
* linger: `loginctl show-user c03rad0r -p Linger` → `Linger=yes`; the role has both
  a check task and an enable task — VERIFIED.
* wallet pinning / no `~/.cocod` fallback: `ROUTSTRD_DIR` + `ROUTSTRD_WALLET_DIR`
  both pinned; role test asserts no `.cocod/wallet` value and no
  `ROUTSTRD_WALLET_DIR=%h/.cocod` anywhere; the only `~/.cocod` mentions in the
  role tree are comments and the lane guard's `--status` **display** of the legacy
  DB size (it never reads it). The legacy `~/.cocod/coco.db` on cobrador was probed
  directly: **0 tables** — an accidental fallback would return an empty wallet, and
  no code path reads it. VERIFIED.
* idempotency: `bash tests/run_routstrd_lane_idempotency.sh` (sandbox, ssh shimmed,
  no host writes) at both `a81041ee` and `bb587eb3`: `run1 changed=4 failed=0`,
  `run2 changed=0 failed=0` — **second apply is a no-op** — VERIFIED.

Then the live half, which the brief asserts as `active`:

```
systemctl --user show routstrd.service:
  ActiveState=failed   Result=exit-code   NRestarts=9   UnitFileState=enabled
journalctl --user -u routstrd.service:
  Sep 26 23:25:43 routstrd.service: Main process exited, code=exited, status=203/EXEC
  Sep 26 23:25:48 routstrd.service: Scheduled restart job, restart counter is at 9.
  Sep 26 23:25:48 routstrd.service: Start request repeated too quickly.
  Sep 26 23:25:48 Failed to start routstrd.service - routstrd — Routstr daemon
findmnt -T /mnt/dq05-lexar  →  /  /dev/nvme0n1p2  ext4      (a plain, empty directory)
ls -ld /home/c03rad0r/merchant-routing-engine
  → lrwxrwxrwx … -> /mnt/dq05-lexar/cw-offload/merchant-routing-engine   (DANGLING)
```

**REFUTED LIVE**: the lane is not active, it is dead. `/v1/models` on 8008 is
unreachable (http=000). The mount the unit pins is not a mount unit at all on this
host, so `RequiresMountsFor` orders nothing; the exec target and the daemon
entrypoint both live on the absent drive; and because the start limit is exhausted,
systemd will **not** restart the unit when the drive returns (needs
`systemctl --user reset-failed routstrd.service` or a reboot). The bound that
protects against the 27753-style spin therefore also removes self-healing. See
MAJOR-1.

### Claim 4 — funding guard

Code (at `8b91148`), verified against the live wallet:

* wallet path: `~/.routstrd/wallet/coco.db` (honours `ROUTSTRD_WALLET_DB`); no
  `~/.cocod` read path anywhere in the reviewed guard.
* per-mint: balances are grouped by `mintUrl`, and `network_sats` sums only mints
  whose url is **not** `TESTNUT_MINT`; the live DB's two mints
  (`https://mint.minibits.cash/Bitcoin`, `https://mint.orangesync.tech`) match the
  exclusion string exactly → the +5,000 testnut is excluded from the gate figure. VERIFIED.
* fail loud: on cobrador (host that has `~/.routstrd/wallet`),
  `ROUTSTRD_WALLET_DB=/tmp/nope/coco.db ROUTSTRD_CLI= python3 guard --balance-json`
  → `⚠️ funding guard: routstrd wallet read FAILED — daemon: … | db: wallet db missing: /tmp/nope/coco.db`, **rc=2**,
  and the balance cron then exits **rc=1** writing **no row**:

```
AssertionError: assert 'read FAILED' in ('⚠️ routstrd balance payload unusable
(Expecting value: line 1 column 1 (char 0)): routstrd wallet not present on this host\n
⚠️ routstrd balance store failed\n')      tests/test_routstrd_balance_cron.py:102
```

* WAL / read-only technique — measured on the live wallet (db 630784 B, `-wal`
  168952 B, `-shm` 32768 B):

```
(A)  mode=ro on a COPY                     -> 98 proofs, minibits ready 35514
(A2) immutable=1 on the COPY               -> 96 proofs, minibits ready 35508   ← WAL-blind
(B)  rw COPY + wal_checkpoint(TRUNCATE)    -> 98 proofs, minibits ready 35514   ← what the guard does
(C)  mode=ro on the LIVE wallet            -> 98 proofs, minibits ready 35514
```

So the guard's copy-and-checkpoint is **WAL-complete** (it recovers the 2
WAL-resident proofs / 6 sats that `immutable=1` loses). MINOR-2: the guard's
docstring justification ("a read-only reader does not replay the WAL") is only true
for `immutable=1` — a plain `mode=ro` reader on the live file *did* replay it here.
The implementation choice is nevertheless the safe one (it also avoids depending on
a live writer's `-shm`).

Holes found, both real:

1. The `routstrd wallet not present on this host` gate returns **rc 0**. Same
   command on a host without `~/.routstrd`:
   `ROUTSTRD_WALLET_DB=/tmp/nope/coco.db … → "routstrd wallet not present on this host", rc=0`
   — a **silent zero** for a missing *configured* wallet DB. The cron then fails on
   JSON parse with a misleading "payload unusable", and no row is written. Fail-loud
   survives at the cron boundary (rc 1, no row) but the guard's own contract does not.
   This is precisely what makes the shipped test non-hermetic (MAJOR-3).
2. Operationally the guard **does not run on the router host at all**: the restored
   crontab line points at a path that is a dangling symlink into the unmounted drive,
   and the log directory under the same path does not exist, so the redirect fails
   too. Guard state file on cobrador is untouched since **Aug 22 12:30**, and no
   `routstrd`-matching journal/syslog entries were produced. "Restored" is true on
   paper and false in practice. See MEDIUM-1.

**Verdict: VERIFIED on the code/wallet logic; PARTLY REFUTED on fail-loud purity and
on the restored-cron being in force.**

### Claim 5 — tests re-run + RED-first

All runs re-executed by me, verbatim summaries:

| artefact | head | result |
|---|---|---|
| `scripts/engine/test_routstr_v41_lane_wiring.py` | `a81041ee` | **28 passed in 1.35s** |
| same | `bb587eb3` (origin/master, deployed) | **28 passed in 1.30s** |
| same, RED-first: only the wiring hunks reverted (`git diff 67e0f1b7^ 67e0f1b7 \| git apply -R`) | origin/master | **9 failed, 19 passed in 1.00s** ← genuine RED-first, and the 9 failures are exactly the 9 behavioural tests of this file |
| full engine suite (`scripts/engine`, minus the un-collectable file) | origin/master **wired** | **17 failed, 542 passed** |
| full engine suite | origin/master **wiring reverted** | **26 failed, 533 passed** — `diff` of the FAILED sets: *only* the 9 wiring tests differ, **no new failures** introduced elsewhere |
| `tests/test_routstrd_lane_role.py` | `a81041ee` / `c7be49ad` | **27 passed in 0.59s** |
| same | **`bb587eb3` (merged master)** | **1 failed, 26 passed** ← RED at head |
| same, RED-first (test present, `roles/` absent) | — | collection ERROR `FileNotFoundError: …/roles/51-routstrd-lane/defaults/main.yml` ← cannot pass without the role |
| `tests/run_routstrd_lane_idempotency.sh` | `a81041ee` and `bb587eb3` | PASS: `run1: changed=4 failed=0 (ok=15 skipped=10)`, `run2: changed=0 failed=0 (ok=15 skipped=8)`, `RESULT: PASS — unit renders and verifies, run2 changed=0, all files landed.` |
| engine `tests/test_routstrd_funding_guard.py` + `tests/test_routstrd_balance_cron.py` | `8b91148` (engine main tip) | **1 failed, 34 passed in 1.13s** |
| same, RED-first (`8b91148^` sources, current tests) | — | **28 failed, 2 passed, 5 errors in 0.69s** ← genuine RED-first |

The master failure, verbatim:

```
===== tests/test_routstrd_lane_role.py @ bb587eb3 =====
FAILED tests/test_routstrd_lane_role.py::test_funding_guard_paths_are_the_restored_ones
E       AssertionError: assert '{{ ansible_u...ding_guard.py' == '/home/c03rad...ding_guard.py'
E         - /home/c03rad0r/merchant-routing-engine/scripts/routstrd_funding_guard.py
E         + {{ ansible_user_dir | default('/home/' + ansible_user_id) }}/merchant-routing-engine/scripts/routstrd_funding_guard.py
1 failed, 26 passed in 0.48s
```

i.e. a **later** commit home-parameterised those paths and the contract test was not
updated. MAJOR-2.

The engine failure is the non-hermetic test: `test_missing_wallet_fails_loudly_and_writes_no_row`
expects `read FAILED` on stdout, which only happens where `~/.routstrd/wallet`
exists. PROVEN by running the *same* guard file against the *same* input on both
hosts (§Claim 4). MAJOR-3.

The brief's "full engine suite 20 failed / 570 passed" was **not reproduced**:
17 failed / 542 passed here, because `scripts/engine/test_lane_wiring_audit.py`
cannot even be collected in a repo checkout (it imports a *deployed* file,
`~/.hermes/bot/scripts/lane_wiring_audit.py`, that does not exist — `1 error during
collection`). The substantive part of that claim (pre-existing failures unrelated to
this change; the change adds 28 passing tests and no new failures) **is** verified by
the before/after FAILED-set diff above.

---

## 3. Findings

### MAJOR-1 — the routstrd buy lane is down on the router host, and cannot self-heal
`routstrd.service` = `failed` since 2026-09-26 23:25:43 (203/EXEC, NRestarts=9,
"Start request repeated too quickly"); nothing listens on 8008 (nor on routstr's
8009). Root: `ExecStart` pins the *resolved* bun path on an external drive that is
not mounted on cobrador (`/mnt/dq05-lexar` is a plain empty dir on ext4 `/`), so
`RequiresMountsFor=/mnt/dq05-lexar` — the role's explicit mount-ordering guarantee —
is a no-op. Because `StartLimitBurst=5` is exhausted, systemd will not bring the
lane back when the drive returns; recovery now needs `reset-failed` + start (or a
reboot). The claim "managed, bounded-restart, boot-enabled lane" is satisfied as
IaC but not as service. Impact: the newly wired lane is unreachable, so
`select_provider`'s routstrd candidate can only ever produce dispatch failures.
Recommend: order against the real mount unit (or an `x-systemd.automount`/autofs
unit) and/or ship a periodic `reset-failed && start` watchdog, and add a
lane-liveness probe that the manager sees.

### MAJOR-2 — merged master is RED: `tests/test_routstrd_lane_role.py` was not updated with the role
`test_funding_guard_paths_are_the_restored_ones` pins
`/home/c03rad0r/merchant-routing-engine/scripts/routstrd_funding_guard.py`, while
`origin/master`'s `roles/51-routstrd-lane/defaults/main.yml` now uses
`{{ ansible_user_dir | default('/home/' + ansible_user_id) }}/…`. 1 failed / 26
passed at `bb587eb3` (green at both PR tips). A head-of-record that fails its own
contract test is a claim-level falsification of "tests green".

### MAJOR-3 — engine main is RED: `test_routstrd_balance_cron.py` is not hermetic
`test_missing_wallet_fails_loudly_and_writes_no_row` passes only where the runner's
`HOME` has `~/.routstrd/wallet` (production host); it fails on any clean host, in CI,
and on this worker — 1 failed / 34 passed at engine `main` (`8b91148`). The test does
not isolate `HOME` even though the guard's own gate reads it. Fix: point the test at
a temp `HOME` and pre-create `~/.routstrd/wallet`, or make the guard distinguish
"not installed" from "configured wallet missing" (see MINOR-1).

### MEDIUM-1 — the "restored" funding-guard cron is dead on the router host
`crontab -l` (cobrador) contains `#Ansible: routstrd-funding-guard` `*/5 * * * *`
pointing at `/home/c03rad0r/merchant-routing-engine/scripts/routstrd_funding_guard.py`
— a **dangling symlink** into the unmounted drive. The log redirect target
(`…/merchant-routing-engine/logs/…`) does not exist either, so the job produces no
output and no log at all. Guard state file untouched since **Aug 22 12:30**.
So the funding guard — the control that keeps the wallet topped up — is not running
on the only host that hosts the lane, exactly while the lane it funds is dead.

### MINOR-1 — guard's skip gate conflates "not installed" with "wallet missing"
`ROUTSTRD_WALLET_DB=/tmp/nope/coco.db` on a host *without* `~/.routstrd` →
`routstrd wallet not present on this host`, **rc 0**. A misconfigured/missing wallet
DB is therefore a silent zero on such hosts (the cron then reports the confusing
"payload unusable"). Fail-loud at the cron boundary still holds (rc 1, no row).

### MINOR-2 — WAL docstring overstates
"The read-only URI does not replay the WAL" is true for `immutable=1` (96 proofs /
35,508) but **not** for `mode=ro`, which replayed the WAL fine on both a copy (98 /
35,514) and the live file (98 / 35,514). The chosen copy+`wal_checkpoint(TRUNCATE)`
technique is correct and WAL-complete; only the stated reason is wrong.

### MINOR-3 — citation drift
Cited SHAs `34aa21ac`/`a81041ee` are not in master; merged tips are `67e0f1b7` /
`c7be49ad`; latest master is `bb587eb3` (the brief says "latest master = a81041ee5").
The measure JSON is at `/mnt/cw-offload/reports/routstr-measure-2026-09-26.json`, not
`~/reports/`.

### MINOR-4 — the quoted wallet balance is the WAL-blind read
Brief: 35,508 sats minibits (+5,000 orangesync). Measured: **35,514** WAL-complete
ready at minibits (+5,000 testnut = 40,514 held; 35,514 counted as `network_sats`),
i.e. the brief's figure equals the `immutable=1` reader's 6-sat-low number.
Also note the network spend is well above the 5,000-sat guard floor.

### MINOR-5 — role's guard-script path is not repo-pinned (latent trap)
`routstrd_funding_guard_script` defaults to `<home>/merchant-routing-engine/…`. On
cobrador that path is a symlink into the offline drive; on dq05 it resolves to a
**stale 2026-09-04 copy** of the guard (md5 97c8ad46) that still targets the dead
`~/.cocod` socket (`COCOD_SOCK = HOME/".cocod"/"cocod.sock"`). No live impact today
(the role is gated on the lane being present — `routstrd_lane_active` requires the
daemon entry + bun + `config.json` — and dq05 has no routstr crontab), but any future
node that has the daemon and a stale engine tree would install a cron running an
unmigrated guard — the exact thing claim 3 says is impossible.

### MINOR-6 — reviewed engine checkout is not clean
`/mnt/cw-offload/merchant-routing-engine` carries index/worktree changes to
`scripts/routstr_balance_cron.sh`, `scripts/routstrd_balance_cron.sh` and
`scripts/routstrd_funding_guard.py` (3 files, +304 lines vs `HEAD`) plus modified
`AGENTS.md` / `config/providers.yaml`. All my test runs used a **clean detached
worktree at `8b91148`**, and the working-tree guard file is byte-identical to the
`8b91148` blob — so the verdicts stand — but the tree is not deploy-ready as-is.

### INFO
* `scripts/engine/test_lane_wiring_audit.py` cannot be collected in any repo
  checkout: it imports a deployed artefact (`~/.hermes/bot/scripts/lane_wiring_audit.py`)
  that does not exist → `1 error during collection`, which aborts a naive
  `pytest scripts/engine`.
* Lane economics: measured **208.70 sats/M in, 740.74 sats/M out** vs *published*
  23.77 / 47.54 — real spend is ~8.8× the advertised rate (12/12 requests,
  460 in / 301 out tokens, 0.323 sats charged). Worth an operator look when pricing
  the lane against PAYGO.
* `routstr` (VPS2 tunnel, port 8009) has no listener either: both newly wired lanes
  are down; only their registry/dispatch wiring is live.

---

## 4. Live-state deltas vs the brief (2026-09-26 premise)

| premise | measured 2026-09-27 | verdict |
|---|---|---|
| deployed `~/.hermes/bot/flat_router.py` md5 == origin/master blob | `1dc1091b…` both (cobrador) | VERIFIED |
| `select_provider('deepseek/deepseek-flash')` includes routstr + routstrd at `effective_cost=inf` | exactly that — ranked [8] and [9] of 10, after 8 finite/inf lanes | VERIFIED |
| `routstrd.service active+enabled+linger` | **failed** (203/EXEC, NRestarts=9) + enabled + `Linger=yes` | **REFUTED (active)** |
| guard cron `*/5` present | crontab line present, job cannot execute (dangling script + missing log dir) | **REFUTED (running)** |
| wallet 35,508 sats minibits (+5,000 orangesync) | 35,514 WAL-complete (+5,000 testnut) — the 35,508 is the WAL-blind read | VERIFIED-with-correction |
| lane cost 208.7 / 740.7 sats/M (12 requests) | `routstr-measure-2026-09-26.json` run[2]: 208.696 / 740.741, 12/12 ok | VERIFIED (path is `/mnt/cw-offload/reports/`) |

---

## 5. Unknowns / not re-runnable (marked, not guessed)

1. **Live `:8008/v1/models` id list** — lane down, endpoint refuses connections. The
   DOT id is corroborated from the daemon's usage DB + measure file instead.
2. **Root cause of the absent `/mnt/dq05-lexar` mount on cobrador** — I verified it
   is not mounted and that the unit therefore fails; I did not investigate why
   (laptop off-network vs. automount failure). Unknown, and it is the trigger for MAJOR-1.
3. **A real `ansible-playbook` second apply on cobrador** — not attempted (live-host
   write). Idempotency evidence is the repo's own sandbox harness (run1 changed=4 /
   run2 changed=0), which I re-ran at both heads.
4. **Deployed guard byte-identity on cobrador** — unreachable (dangling path); the
   reviewed guard is the `8b91148` blob (`md5 fec2e50a…`) and the dq05 checkout's
   working-tree copy matches it.
5. **The card tid** — not resolvable here (§0.1).

## 6. Method

All inspection read-only. Repo reads via `git show/diff/grep`, detached worktrees at
`a81041ee`, `bb587eb3` (hermes-orchestration) and `8b91148` (engine); live reads via
`ssh c03rad0r@100.90.101.9` (BatchMode) — `systemctl --user`, `journalctl --user`,
`ss`, `findmnt`, `crontab -l`, `md5sum`, and two scripts piped over ssh stdin
(`wal_probe.py`, in-process engine probe). Test runs: `python3 -m pytest` in the
worktrees + the shell idempotency harness. No repo writes by the reviewer; the only
writes are this artifact (and the copy committed locally to the merchant-routing
workspace). Author-written tests were re-run, mutated (RED-first by reverting the
change), and cross-checked against live host state.
