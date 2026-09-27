# Cross-family cold review — routstr v4.1 lane wiring + routstrd service/guard IaC
## PASS 2 — independent re-derivation (nothing carried over unverified)

reviewer_model: tier/review-kimi (provider: zai)  — kimi family
author_family: deepseek (workers deleg_17f47ac6 task0/1 + task2)  — deepseek family
cross_family: SATISFIED (author deepseek != reviewer kimi); this reviewer did not author any
              reviewed commit and read no author narrative beyond the brief's claims.
date: 2026-09-27
worker_host: dq05 (100.90.22.201)   live_state_host: cobrador / CobradorWave (100.90.101.9)
review_mode: cold. Every claim re-derived this session from code, git objects, live host state
             and re-run tests. Verdicts below were reached from the artifacts, then compared to
             the brief; where the brief and my measurement disagree, both are quoted.
predecessor: pass 1 of the same card —
             ~/reports/reviews/merchant-routing-routstr-v41-lane-wiring-kimi.md
             (== repo docs/reviews/routstr_v41_lane_wiring_review.md, md5 5651673c, committed
             as 2301524). Pass 1 is preserved; this file supersedes its numbers where they differ.
artifact: ~/reports/reviews/merchant-routing-routstr-v41-lane-wiring-kimi-pass2.md

## 0.1 tid / card
Not resolvable from this worker (same result as pass 1). The two llm-routing cards that mention
"lane wiring" (t_5ee2197a, t_ef53ad89) are a different deliverable (JSON-verdict review of a
health-state fix, assignee worker-base, model_override glm-5.3) and neither references
pr/routstr-v41-lane-wiring, pr/routstrd-lane-service or deleg_17f47ac6. No kanban toolset is
present in this session, so no card attach is possible from here: the artifact is referenced by
path. The filename therefore carries a slug, not a tid.

## 0.2 SHA reconciliation — done before evaluating anything (diff-vs-claim)
Re-derived this session in /home/c03rad0r/hermes-orchestration:

| item | cited by the brief | what git actually shows |
|---|---|---|
| lane wiring | `34aa21ac` | exists, right subject, but **NOT an ancestor of origin/master**. Merged tip with the same subject = `67e0f1b7` (IS an ancestor). |
| routstrd service | `a81041ee` "both merged to master, latest master = a81041ee5" | `a81041ee` **NOT an ancestor of origin/master**. Merged tip with the same subject = `c7be49ad` (IS an ancestor). **origin/master = `bb587eb3`** (a "Merge pull request #172" commit), not `a81041ee5`. |
| engine wallet fix | `8b91148` merged to main | CONFIRMED: `main` tip == `8b91148`, `github/main` == `8b91148`, and it is the tip of branch `pr/routstrd-wallet-path`. |

Consequence that matters: **the cited SHAs are the PR-side commits, not what shipped**, and the
deployed engine matches `origin/master` (`bb587eb3`), which carries later changes to two of the
reviewed paths:

```
bb587eb3:scripts/engine/flat_router.py  1dc1091bd4d264edbfe2c0e9cae89454
bb587eb3:scripts/engine/zai_proxy.py    c2f13451b527acdba70861224a966287
67e0f1b7:scripts/engine/flat_router.py  1dc1091b…  (same as master)
67e0f1b7:scripts/engine/zai_proxy.py    bcb2d9f0f9c7aee76becc3346b14c381  (differs)
a81041ee:scripts/engine/zai_proxy.py    bcb2d9f0…  (differs from master)
cobrador:~/.hermes/bot/flat_router.py   1dc1091bd4d264edbfe2c0e9cae89454  == bb587eb3 blob
cobrador:~/.hermes/bot/zai_proxy.py     c2f13451b527acdba70861224a966287  == bb587eb3 blob
git diff a81041ee origin/master -- roles/51-routstrd-lane/  → defaults/main.yml, 4 lines
git diff a81041ee origin/master -- scripts/engine/zai_proxy.py → 7 lines (later Phase-M change)
```

I therefore evaluated **three** heads, not one: cited `a81041ee`, real merged master `bb587eb3`
(= deployed), engine `8b91148`. Line citations below are `bb587eb3` unless stated.

---

## 1. Verdict table

| # | claim | verdict | why |
|---|---|---|---|
| 1 | canonical `deepseek/deepseek-flash` in `PROVIDER_MODELS` for routstr **and** routstrd, `_PROVIDER_MODEL_NAMES` → network id `deepseek-v4.1-flash` (DOT), id checked against the live lane | **VERIFIED (code)** / **live curl NOT REPRODUCIBLE at head** | both registries + both translation entries present and identical in repo and deployed copies (md5s above); `curl :8008/v1/models` returns an empty body and `:8009` returns http=000 *today* because the lane is down (finding MAJOR-1), so the live id check cannot be re-run. Corroborated independently: the daemon's own `~/.routstrd/routstr.db` `usage_tracking` holds `model_id=deepseek-v4.1-flash` ×38 and a sibling `tinfoil-deepseek-v4-1-flash` ×1, **zero** `deepseek-v4-flash` rows; the measure file records `advertised_in_catalog=true, catalog_size=21` on all 3 runs. |
| 2 | a dispatch arm exists for both lanes (no `ollama_cloud_4`-class "in the registry, no arm, chosen on price, never dispatched") | **VERIFIED** | `_make_dispatch_fn('routstr'|'routstrd')` → `<locals>._dispatch_external` → `handler._try_external_single(name,…)` (`flat_router.py:1406-1408`), reachable from the real dispatch path `_dispatch_to_provider` (`:1426`) and `:1607`; `zai_proxy.EXTERNAL_PROVIDERS` has base_url for both (routstr `http://localhost:8009/v1`, routstrd `http://localhost:8008/v1`); `PROVIDER_TIER[...]='per_token'`; `_SEED_RATES[...]=1.00`. The trap's precondition (no arm + no EXTERNAL_PROVIDERS entry ⇒ falsy handler) does not hold for these two lanes. |
| 3 | role 51: systemd --user unit, bounded Restart, linger, wallet pinned to `~/.routstrd/wallet`, `RequiresMountsFor` resolved mount; a **second** apply `changed=0`; no path falls back to the empty `~/.cocod/coco.db` | **VERIFIED (IaC + idempotency)** / **REFUTED LIVE** | sandbox harness PASS: run1 `changed=4 failed=0`, run2 `changed=0 failed=0`, rendered unit accepted by `systemd-analyze --user verify` (rc=0), every structural pin asserted OK; the **live** unit carries the same pins (`ROUTSTRD_DIR=%h/.routstrd`, `ROUTSTRD_WALLET_DIR=%h/.routstrd/wallet`, `StartLimitBurst=5`, `Restart=always`, `RequiresMountsFor=/mnt/dq05-lexar /mnt/dq05-lexar/cw-offload/bun`, `ExecStartPre=…routstrd_lane_guard.sh --port 8008`), `Linger=yes`, `is-enabled=enabled`. But the service is **`failed`**, `ExecMainStatus=203` (EXEC), `NRestarts=9`, last ActiveEnter 2026-09-26 23:25:43 → the lane is DOWN and will not self-heal. |
| 4 | guard reads the migrated wallet (per-mint, orangesync testnut excluded from `network_sats`) and FAILS LOUD (non-zero) on an unreadable/empty wallet; read-only sqlite URI does not replay WAL — check the technique | **VERIFIED with two holes** | path, per-mint, testnut exclusion and rc=2 fail-loud all reproduced (below, incl. on the production host); WAL technique is correct and necessary — measured. Hole (a): when `~/.routstrd` is **absent** the guard takes the "not installed on this host" gate and returns **rc 0**. Hole (b): the *restored* */5 cron entry cannot execute on the router host at all (finding MEDIUM-1). |
| 5 | the named test files re-run; RED-first is real | **PARTLY REFUTED** | wiring test 28 passed and RED-first is genuine (9 failed/19 passed with only the wiring hunks reverted); idempotency harness PASS; engine red-to-green is genuine (28 failed/2 passed/5 errors against the pre-fix guard). **But two shipped tests are RED at their own merged heads**: `tests/test_routstrd_lane_role.py` 1 failed/26 passed at `bb587eb3`, and the engine `tests/test_routstrd_balance_cron.py` 1 failed/34 passed at `8b91148`. |

Live-state premise from the brief, checked item by item:

| brief's live state | result |
|---|---|
| deployed `~/.hermes/bot/flat_router.py` md5 == origin/master blob | **VERIFIED** (1dc1091b…, and `zai_proxy.py` c2f13451… == master) |
| live `select_provider('deepseek/deepseek-flash')` candidates include routstr + routstrd, both at `effective_cost=inf` | names **VERIFIED**; `inf` **NOT REPRODUCED** — in a scratch env both lanes price at **1.0** while `deepseek`=0.05 and `ollama_cloud*`/`neuralwatt`/`deepinfra`/`openrouter`=inf. `inf` on the production host reflects live quota/exhaust state, which is not visible from this worker (marked unknown, not refuted). |
| `routstrd.service` **active**+enabled+linger | **REFUTED**: `failed` (203/EXEC since 2026-09-26 23:25, start limit exhausted); enabled **VERIFIED**; `Linger=yes` **VERIFIED** |
| guard cron `*/5` present | **VERIFIED as a crontab line / REFUTED as a working job** (`#Ansible: routstrd-funding-guard` + `*/5 * * * * …/merchant-routing-engine/scripts/routstrd_funding_guard.py`; that path is a dangling symlink on the host — see MEDIUM-1) |
| wallet 35,508 sats minibits (+5,000 orangesync) | **VERIFIED but WAL-blind**: 35,508 is exactly what an `immutable=1` reader returns (96 proofs); the WAL-correct value is **35,514** (98 proofs), which is what the guard itself reports |
| measured lane cost 208.7 / 740.7 sats/M (12 requests) | **VERIFIED**, but the file is `/mnt/cw-offload/reports/routstr-measure-2026-09-26.json` (run[2]), not `~/reports/` — see MINOR-3 |

---

## 2. Evidence, claim by claim

### Claim 1 — registry entries + DOT translation
In-process load of the reviewed head (`bb587eb3` worktree), repo copies only:

```
PROVIDER_MODELS['routstr']  = {'kimi-k3','glm-5.3','glm-5.2','deepseek/deepseek-v4-pro',
                               'deepseek/deepseek-v4-flash','deepseek/deepseek-flash'}
PROVIDER_MODELS['routstrd'] = same set
_PROVIDER_MODEL_NAMES['routstr']  = {'deepseek/deepseek-flash': 'deepseek-v4.1-flash'}
_PROVIDER_MODEL_NAMES['routstrd'] = {'deepseek/deepseek-flash': 'deepseek-v4.1-flash'}
```

Legacy ids are **kept** (`flat_router.py:311-325`) and no legacy canonical is re-pointed at a
`v4.1` native id (`test_no_silent_substitution_of_legacy_id`), i.e. FR-2 is respected.
The DOT form is the lane's actual id — corroborated while the lane is down:

```
cobrador$ sqlite3 ~/.routstrd/routstr.db "select model_id,count(*) from usage_tracking group by 1 order by 2 desc;"
deepseek-v4.1-flash|38      glm-5.2|14      glm-5.3|2
glm-4.5-flash|1             gpt-5.6-luna|1  tinfoil-deepseek-v4-1-flash|1
```
(no `deepseek-v4-flash*` rows at all). This is *indirect*: `curl -s http://localhost:8008/v1/models`
today returns an empty body and `:8009` returns `000`, so **the brief's live probe cannot be
reproduced at head** — the only reason the id is still verifiable is the daemon's own ledger.

### Claim 2 — dispatch arm
```
_make_dispatch_fn('routstr')  = <function _make_dispatch_fn.<locals>._dispatch_external>
_make_dispatch_fn('routstrd') = <function _make_dispatch_fn.<locals>._dispatch_external>
flat_router.py:1406  def _dispatch_external(handler, body, model, buffer, t0):
flat_router.py:1407      return handler._try_external_single(name, body, model, buffer, t0)
flat_router.py:1426  dispatch_fn = _make_dispatch_fn(name)     # _dispatch_to_provider
flat_router.py:1607  dispatch_fn = _make_dispatch_fn(name)     # second call site
EXTERNAL_PROVIDERS['routstr']['base_url']  = http://localhost:8009/v1
EXTERNAL_PROVIDERS['routstrd']['base_url'] = http://localhost:8008/v1
PROVIDER_TIER   = {'routstr':'per_token','routstrd':'per_token'}
_SEED_RATES     = {'routstr':1.0,'routstrd':1.0}
```
The `ollama_cloud_4` lesson is about a lane that reaches *the* fall-through arm but has **no**
`EXTERNAL_PROVIDERS` entry, so the arm returns a falsy handler. Both routstr lanes have a
`base_url`, so the arm is live. VERIFIED.

### Claim 3 — service IaC: structure vs deployed reality
Sandbox harness (`tests/run_routstrd_lane_idempotency.sh`, real ansible 2.19, throwaway HOME,
`routstrd_lane_manage_service=false`, `routstrd_lane_manage_crontab=false`, TMPDIR=/tmp):

```
run1: changed=4 failed=0   (expect failed=0, changed>0 on first apply)
run2: changed=0 failed=0   (expect changed=0 failed=0)
OK   mount ordering pinned / wallet pinned to the NEW path / config dir pinned
OK   Restart=always / restart is bounded / second-instance guard wired / boot-enabled
OK   no legacy ~/.cocod path in the unit's settings
systemd-analyze --user verify rc=0
RESULT: PASS — unit renders and verifies, run2 changed=0, all files landed.
```

Deployed unit (cobrador, non-comment lines) — structurally identical, with the mount pin resolved
to the real (but in this case unmounted) location:

```
RequiresMountsFor=/mnt/dq05-lexar /mnt/dq05-lexar/cw-offload/bun
ExecStart=/mnt/dq05-lexar/cw-offload/bun/bin/bun …/routstrd/dist/daemon/index.js --port 8008 --host 127.0.0.1
ExecStartPre=/home/c03rad0r/.hermes/scripts/routstrd_lane_guard.sh --port 8008
Environment=ROUTSTRD_DIR=%h/.routstrd
Environment=ROUTSTRD_WALLET_DIR=%h/.routstrd/wallet
Restart=always   StartLimitIntervalSec=300   StartLimitBurst=5   WantedBy=default.target
```

Live reality (the part the brief's "active+enabled+linger" premise misses):

```
systemctl --user is-active routstrd.service   → failed
systemctl --user is-enabled routstrd.service  → enabled
show -p NRestarts -p Result -p ExecMainStatus → NRestarts=9  Result=exit-code  ExecMainStatus=203
journalctl --user -u routstrd.service:
  routstrd.service: Unable to locate executable '/mnt/dq05-lexar/cw-offload/bun/bin/bun': No such file or directory
  routstrd.service: Failed at step EXEC spawning /mnt/dq05-lexar/cw-offload/bun/bin/bun: No such file or directory
  routstrd.service: Main process exited, code=exited, status=203/EXEC
  routstrd.service: Scheduled restart job, restart counter is at 9.
  routstrd.service: Start request repeated too quickly.        ← StartLimitBurst=5 exhausted → no self-heal
~/.bun -> /mnt/dq05-lexar/cw-offload/bun          (dangling: the mount dir is an empty ext4 dir)
curl -s http://localhost:8008/v1/models           (empty body; :8009 → http=000)
Linger=yes
```
The `ExecStartPre` guard itself is healthy, which isolates the fault to the missing mount/binary:
`routstrd_lane_guard.sh --check` → `guard: port 8008 free — ok to start routstrd.service` (rc=0);
`--status` → `holder: none`, `wallet ~/.routstrd/wallet/coco.db: 630784 bytes`,
`wallet ~/.cocod/coco.db: 0 bytes`.

Note the IaC is *structurally* the thing the brief describes (bounded restart, linger, both wallet
env vars pinned, mount ordering resolved at converge time) — the failure is that the unit was
converged onto a path that is not a mount on this host, and `Restart=always` + an exhausted start
limit turns that into a permanently dead lane rather than a flapping one. "No path falls back to
the empty `~/.cocod/coco.db`" holds for the unit and for the guard (see claim 4).

### Claim 4 — wallet reader, testnut, fail-loud, WAL technique
Wallet path: the fixed guard defines only `WALLET_DIR = ~/.routstrd/wallet` /
`WALLET_DB = WALLET_DIR/coco.db` (env-overridable via `ROUTSTRD_WALLET_DB`); the whole 393-line
file was read end-to-end — every `~/.cocod` mention is narrative in comments/docstrings, there is
no `COCOD_SOCK` reader left (the pre-fix version's live reader was the `cocod` unix socket). The
collector cron defaults to `$HOME/.routstrd/wallet/coco.db` (`routstrd_balance_cron.sh:28`).

Exit-code matrix, reproduced twice — locally against a fake HOME (subprocess, so `Path.home()`
is correct at import) and, for the two decisive rows, **on the production host itself**:

```
guard --balance-json          local (fake HOME)                cobrador (real HOME)
 ~/.routstrd EXISTS, db missing   rc=2 "…wallet read FAILED — db: wallet db missing: …"   rc=2 "…read FAILED — db: wallet db missing: /tmp/rev41-nope/coco.db"
 ~/.routstrd EXISTS, db 0-byte    rc=2 "…no coco_cashu_proofs table (0 tables)…"
 ~/.routstrd EXISTS, zero proofs  rc=2 "…holds zero proofs…"
 ~/.routstrd EXISTS, healthy      rc=0 {"balances":{minibits:35508,orangesync:5000},"network_sats":35508,"source":"db",…}
 ~/.routstrd ABSENT               rc=0 "routstrd wallet not present on this host"      ← hole (a)

routstrd_balance_cron.sh      rc / rows written
 db missing (dir present)     rc=1 rows=0  "⚠️ routstrd balance read FAILED (wallet: …)"
 db 0-byte                    rc=1 rows=0  "…read FAILED…"
 dir absent                   rc=1 rows=0  "…payload unusable (Expecting value…): routstrd wallet not present on this host"
 healthy                      rc=0 rows=1  (limit_remaining = 35508/1e8*100000)
```
Live wallet read on the router host with the reviewed guard, this session:

```
$ python3 /tmp/rev41_guard.py --balance-json     # reviewer's copy of 8b91148:scripts/routstrd_funding_guard.py
{"balances": {"https://mint.minibits.cash/Bitcoin": 35514, "https://mint.orangesync.tech": 5000},
 "network_sats": 35514, "source": "db", "wallet_db": "/home/c03rad0r/.routstrd/wallet/coco.db",
 "testnut_mint": "https://mint.orangesync.tech"}      rc=0
```
→ per-mint ✓, testnut excluded from `network_sats` but reported per mint ✓, source=db (the daemon
CLI is unavailable because the lane is down) ✓.

**WAL technique — measured, and the reason it matters** (fixture wallet, rows written with
`journal_mode=WAL` and left resident in the `-wal`, exactly the daemon-held state):

```
-wal size = 20632 B
guard (copy db+-wal+-shm, open COPY rw, PRAGMA wal_checkpoint(TRUNCATE)) → {minibits:35008,
      orangesync:500}  total=35508        ← correct
immutable=1 reader on the live file      → OperationalError: no such table: coco_cashu_proofs
mode=ro reader on the live file          → total=35508   ← replay happens
source wallet sha unchanged after read   → True
```
And on the **live** wallet (cobrador, this session), the same differential explains the brief's
figure exactly:

```
coco.db 630784 B ; coco.db-wal 168952 B (mtime Sep 26 15:05) ; coco.db-shm 32768 B
sqlite3 "file:…?immutable=1" → minibits 35508 | orangesync 5000 | 96 proofs   ← the brief's 35,508
sqlite3 "file:…?mode=ro"     → minibits 35514 | orangesync 5000
guard (copy+checkpoint)      → 35514
```
So: the brief's "35,508 sats" is a **WAL-blind** reading; the true spendable balance is 35,514
(2 proofs, 6 sats, still only in the `-wal`). The guard's chosen technique is the correct one, and
it never opens the live file. Two caveats recorded as findings: the guard's "missing/0-proofs
wallet is an ERROR" property holds only when `~/.routstrd` exists (MINOR-1), and the docstring's
claim that "a read-only/**immutable=1** reader does NOT replay the WAL" is true for `immutable=1`
but **not** for `mode=ro`, which does replay (MINOR-2).

### Claim 5 — tests re-run (verbatim)
Reviewed head worktree `bb587eb3` (hermes-orchestration), engine worktree `8b91148`:

```
$ python3 -m pytest scripts/engine/test_routstr_v41_lane_wiring.py -q
28 passed in 1.66s                                        ← GREEN

$ bash tests/run_routstrd_lane_idempotency.sh             ← see claim 3: RESULT: PASS,
run1 changed=4 failed=0 / run2 changed=0 failed=0          systemd-analyze --user verify rc=0

$ python3 -m pytest tests/test_routstrd_lane_role.py -q
.................F.........                               [100%]
FAILED tests/test_routstrd_lane_role.py::test_funding_guard_paths_are_the_restored_ones   ← RED at merged master
1 failed, 26 passed in 0.49s
  assert '{{ ansible_user_dir | default(…\+ ansible_user_id) }}/merchant-routing-engine/scripts/routstrd_funding_guard.py'
      == '/home/c03rad0r/merchant-routing-engine/scripts/routstrd_funding_guard.py'
  (a later commit home-parameterised defaults/main.yml; the pin was not updated)

$ python3 -m pytest tests/test_routstrd_funding_guard.py tests/test_routstrd_balance_cron.py -q   (engine @ 8b91148)
.................................F.                       [100%]
FAILED tests/test_routstrd_balance_cron.py::test_missing_wallet_fails_loudly_and_writes_no_row   ← RED at main
1 failed, 34 passed in 1.93s
  AssertionError: assert 'read FAILED' in ('⚠️ routstrd balance payload unusable (Expecting value:
  line 1 column 1 (char 0)): routstrd wallet not present on this host | ⚠️ routstrd balance store failed')
```
The failing engine test is **non-hermetic**: it asserts the literal `read FAILED`, which only
appears when `~/.routstrd` exists (so the guard enters its read path instead of the
"not present on this host" gate). Proven by running the same guard, same inputs, on both hosts:

```
cobrador$ HOME=/home/c03rad0r ROUTSTRD_WALLET_DB=/tmp/rev41-nope/coco.db ROUTSTRD_CLI= \
          python3 /tmp/rev41_guard.py --balance-json
⚠️ funding guard: routstrd wallet read FAILED — daemon: …not found | db: wallet db missing: /tmp/rev41-nope/coco.db
rc=2                                    ← test would PASS here
dq05 (no ~/.routstrd): same invocation → rc=0 "routstrd wallet not present on this host"  ← test FAILS
```

**RED-first — genuine, both repos, re-derived by reverting only the fix:**

```
hermes-orchestration (wiring): git diff 67e0f1b7^ 67e0f1b7 -- scripts/engine/{flat_router,zai_proxy}.py | git apply -R
  → 9 failed, 19 passed      (exactly the 9 wiring tests: lane_advertises_v41_canonical ×2,
     select_provider_includes_lane ×2, includes_both_lanes, has_translation_entry ×2,
     resolution_helper_returns_network_id ×2)
  → restored: 28 passed
merchant-routing-engine (wallet): git checkout 8b91148^ -- scripts/routstrd_funding_guard.py scripts/routstrd_balance_cron.sh
  → 28 failed, 2 passed, 5 errors   (the 35 new tests against the pre-fix cocod-socket reader)
  → at 8b91148: 1 failed, 34 passed
```
The RED-first claim is real in both repos; the only RED at head is the two defects above.

---

## 3. Findings

**MAJOR-1 — the routstrd buy lane is DOWN on the production host and cannot self-heal.**
`routstrd.service` is `failed`: 203/EXEC because `ExecStart` (and `~/.bun`) resolve into
`/mnt/dq05-lexar/cw-offload/…`, which on cobrador is an empty ext4 directory (not the drive), and
`StartLimitBurst=5` was exhausted at restart counter 9 ("Start request repeated too quickly"), so
`Restart=always` no longer retries. No listener on 8008 or 8009. `RequiresMountsFor=` only orders
*if* a unit with a matching mount exists; a plain directory satisfies it, so the pin is
satisfied-but-wrong and nothing repairs or alerts. Effect on the reviewed change: the V4.1 wiring
is inert on this host — every `deepseek/deepseek-flash` request stays on the 0.05-cost direct lane
and the routstr lanes are unreachable overflow. Fix direction: make the pin fail closed (e.g.
`ConditionPathIsMountPoint=`, or assert the mount unit is active) so the unit refuses instead of
203-looping, and add the lane to a health check that surfaces "down > N minutes".

**MAJOR-2 — `tests/test_routstrd_lane_role.py` is RED at merged master** (1 failed / 26 passed,
`test_funding_guard_paths_are_the_restored_ones`). The role's `defaults/main.yml` was later
home-parameterised (`{{ ansible_user_dir | default('/home/' + ansible_user_id) }}`) and the pin was
not updated. Either the pin must drop the absolute prefix or the default must go back to a literal;
whichever way, the suite is red on the head that shipped. (Note the same template also produces the
crontab line that MEDIUM-1 shows to be unrunnable.)

**MAJOR-3 — the engine suite is RED at `main`** (1 failed / 34 passed,
`tests/test_routstrd_balance_cron.py::test_missing_wallet_fails_loudly_and_writes_no_row`), and the
assertion is host-dependent rather than a code defect: it pins the guard's message text for a state
that is only reached when `~/.routstrd` exists. Fix: assert on `returncode != 0` + `rows == []`
(the observable contract, already asserted) and point `HOME` at a fixture, or assert the guard's own
rc/JSON instead of a substring. As written, the test's verdict flips based on which host runs it.

**MEDIUM-1 — the "restored" `*/5` funding-guard cron cannot execute on the router host.**
`crontab -l` shows `#Ansible: routstrd-funding-guard` + `*/5 * * * * /home/c03rad0r/merchant-routing-engine/scripts/routstrd_funding_guard.py >> …/logs/routstrd_funding_guard.log 2>&1`,
but `~/merchant-routing-engine` is a symlink to `/mnt/dq05-lexar/cw-offload/merchant-routing-engine`
on the unmounted drive:
```
$ python3 /home/c03rad0r/merchant-routing-engine/scripts/routstrd_funding_guard.py --balance-json
/usr/bin/python3: can't open file '…': [Errno 2] No such file or directory     rc=2
$ ls ~/merchant-routing-engine/logs/   → No such file or directory
```
So the funding guard is dead in both directions: the wallet it would read is live and correct, but
nothing runs, and the log path cannot even be created. (The companion collector cron at line 47 is
explicitly RETIRED.) Calling the cron "restored" is true only at the crontab-line level.

**MINOR-1 — guard fail-open for a missing configured wallet.** With `ROUTSTRD_WALLET_DB` pointing
at a genuinely missing DB, the guard still exits **0** ("routstrd wallet not present on this host")
whenever `~/.routstrd` itself is absent, because the "not installed on this host" gate
(`routstrd_funding_guard.py:331-335`) tests `WALLET_DIR.exists()` and the *un-overridden* default
path, not the overridden one, and ignores the env override in the directory test. The collector
still fails non-zero (rc 1, no row), so no false 0-sat row is written — the hole is at the guard
level, and only for the "whole directory missing" shape.

**MINOR-2 — WAL docstring overstates the hazard.** The comment says "a read-only/`immutable=1`
reader would silently miss WAL-resident proofs". Measured: `immutable=1` can fail outright (in my
fixture even the *schema* was still in the `-wal`, giving `no such table`), whereas `mode=ro`
**does** replay the WAL and returns the correct total. The chosen copy+checkpoint technique is
right (and never touches the live file); the doc just needs to name `immutable=1` precisely.

**MINOR-3 — citation drift in the brief** (does not change any verdict): `34aa21ac`/`a81041ee` are
not in `origin/master` (the merged tips are `67e0f1b7`/`c7be49ad`; latest master is `bb587eb3`,
not `a81041ee5`); the measure file lives at `/mnt/cw-offload/reports/`, not `~/reports/`; and
`35,508` is the WAL-blind reading of a 35,514-sat wallet.

**MINOR-4 — the engine checkout used for the review is not pristine.** On dq05,
`/mnt/cw-offload/merchant-routing-engine` has HEAD on branch `t_d0e69a24/routstr-delist` (07a20de)
with staged modifications (`scripts/routstrd_funding_guard.py`, `scripts/routstrd_balance_cron.sh`,
2 other scripts + 4 src files = the "+304 staged lines"). All review runs above were done in a
clean `git worktree` at `8b91148`, never in that dirty tree — but anyone re-running "the suite"
in place is testing a different artifact.

**MINOR-5 — no card/tid attach.** As in pass 1, the card for this offload task is not identifiable
from this worker and no kanban toolset is available; the artifact is referenced by path.

---

## 4. What I could NOT verify (unknowns, stated as unknown)
1. **The live lane's model catalog.** `curl :8008/v1/models` is unusable today (lane down). The DOT
   id is corroborated only by the daemon's `usage_tracking` ledger and the 2026-09-26 measure file.
2. **`effective_cost=inf` for the two lanes on the production host.** Reproduced only as `1.0` in a
   scratch env; the `inf` values depend on live quota/exhaust state not reachable from this worker.
3. **Whether the cited PR-side SHAs were ever pushed to the remote as-is** — the local clone shows
   them as loose objects only; I verified ancestry against `origin/master` and nothing more.
4. **Anything about the author's own runs** (their claimed "full engine suite 20F/570P", their RED
   captures): not re-derived here; pass 1 could not reproduce that figure either.
5. Nothing else: every other number in this document is a command output from this session.

## 5. Reproduction (all commands used)
```
# heads
git -C ~/hermes-orchestration rev-parse origin/master            # bb587eb3
for s in 34aa21ac a81041ee 67e0f1b7 c7be49ad; do git -C ~/hermes-orchestration merge-base --is-ancestor $s origin/master; done
git -C /mnt/cw-offload/merchant-routing-engine rev-parse main github/main   # 8b91148 both
# clean trees (never the dirty checkout)
git -C ~/hermes-orchestration worktree add --detach /tmp/rv41-ho-wt bb587eb3
git -C /mnt/cw-offload/merchant-routing-engine worktree add --detach /tmp/rv41-eng-wt 8b91148
# suites
cd /tmp/rv41-ho-wt && python3 -m pytest scripts/engine/test_routstr_v41_lane_wiring.py -q   # 28 passed
cd /tmp/rv41-ho-wt && python3 -m pytest tests/test_routstrd_lane_role.py -q                 # 1F/26P
cd /tmp/rv41-ho-wt && bash tests/run_routstrd_lane_idempotency.sh                           # PASS
cd /tmp/rv41-eng-wt && python3 -m pytest tests/test_routstrd_funding_guard.py tests/test_routstrd_balance_cron.py -q  # 1F/34P
# RED-first
cd /tmp/rv41-ho-wt && git diff 67e0f1b7^ 67e0f1b7 -- scripts/engine/flat_router.py scripts/engine/zai_proxy.py | git apply -R
cd /tmp/rv41-eng-wt && git checkout 8b91148^ -- scripts/routstrd_funding_guard.py scripts/routstrd_balance_cron.sh
# live (cobrador)
ssh -i ~/.ssh/laptop_sync c03rad0r@cobradorwave.local 'systemctl --user is-active routstrd.service; journalctl --user -u routstrd.service -n 12; crontab -l | grep -i routstrd'
ssh … 'python3 /tmp/rev41_guard.py --balance-json'
ssh … 'sqlite3 "file:~/.routstrd/wallet/coco.db?immutable=1" "select mintUrl,sum(amount) from coco_cashu_proofs where state=\"ready\" group by 1"'
ssh … 'sqlite3 ~/.routstrd/routstr.db "select model_id,count(*) from usage_tracking group by 1 order by 2 desc"'
ssh … 'md5sum ~/.hermes/bot/flat_router.py ~/.hermes/bot/zai_proxy.py'
```
Local probe scripts used (reviewer-authored, kept for audit): `/tmp/rv41-probe2.py` (claim 2),
`/tmp/rv41-probe4.py` + `/tmp/rv41-probe4b.py` (claim 4 exit-code/wallet matrix).
No production artifact was modified by this review: the wallet was only ever read (and copied to a
private temp dir by the guard itself), no unit was started/stopped, no crontab was edited.
