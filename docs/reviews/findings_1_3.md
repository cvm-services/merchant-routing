# Review findings 1–3: safety, confirmation, fail-safe

Artifacts reviewed:
- `~/.hermes/bot/docs/routstr_delist_contract.md` — **MISSING**
- `~/.hermes/bot/docs/routstr-delist.md` — read as fallback
- `~/.hermes/bot/scripts/routstr_delist.py`
- `~/.hermes/bot/tests/test_routstr_delist.py`

No artifacts were modified.

---

## Finding 1 — BLOCKER: required contract file is missing

**Severity:** BLOCKER

The task explicitly named `~/.hermes/bot/docs/routstr_delist_contract.md` as a review artifact. That file does not exist on disk. The review therefore cannot be anchored to the prescribed contract document. The implementation and tests appear to have been written against `~/.hermes/bot/docs/routstr-delist.md` instead.

Evidence:
- `read_file ~/.hermes/bot/docs/routstr_delist_contract.md` returned `File not found: /home/c03rad0r/.hermes/bot/docs/routstr_delist_contract.md` with a similar-file hint of `/home/c03rad0r/.hermes/bot/docs/routstr-delist.md`.

Until the requested contract file exists or the task references are updated, this finding is blocking.

---

## Finding 2 — HIGH: confirmation-by-re-fetch is implemented but the test suite does not regression-test the production SSH/shell-quoting path

**Severity:** HIGH

The script correctly gates a fired delist on a second, read-only listings fetch (`_SshBackend.verify`) rather than on the pull's own self-report. However, every test in the contract suite mocks the backend at the `FakeSellNode` level and executes payloads directly via `exec()`, bypassing `_SshBackend._run`, `build_ssh_docker_cmd`, and the actual `subprocess.run` SSH path. No test round-trips the shell-quoted remote command through `shlex.split` or exercises an adversarial container/payload to prove shell injection is impossible.

Evidence:
- `~/.hermes/bot/scripts/routstr_delist.py:414-425` `build_ssh_docker_cmd` shell-quotes `container` and `payload` before building the remote command string.
- `~/.hermes/bot/scripts/routstr_delist.py:790-793` `verify` runs the independent `SELECT COUNT(*) FROM models WHERE enabled=1` payload.
- `~/.hermes/bot/scripts/routstr_delist.py:682-688` success is gated on `vres.get("ok") is True and vres.get("count") == 0`.
- `~/.hermes/bot/scripts/routstr_delist.py:719-739` unconfirmed pulls exit non-zero, do not consume the baseline, and do not set `delisted=true`.
- `~/.hermes/bot/tests/test_routstr_delist.py` `FakeSellNode.execute` calls `exec(payload, g)` with a patched `sqlite3`; it never calls `build_ssh_docker_cmd` or `_SshBackend._run`.
- Content search for `shlex`, `shell`, `quote`, or `build_ssh` in `~/.hermes/bot/tests/test_routstr_delist.py` returned zero hits.

The design is sound, but the transport-safety and subprocess confirmation paths are not empirically covered by the prescribed test artifact.

---

## Finding 3 — HIGH: fail-safe stale/corrupt feed handling is implemented but the corrupt-feed baseline-preservation path lacks an explicit regression test

**Severity:** HIGH

The script correctly fail-closes on stale or unreadable prediction feeds: unparseable `--preds` is treated as a feed error, stale feeds are treated as dead data, and the acceleration baseline is never overwritten with an empty prediction list. The CLI exits non-zero when only a stale/failed feed exists and no trigger fired.

Evidence:
- `~/.hermes/bot/scripts/routstr_delist.py:485-496` `feed_is_stale` returns `True` when the file age cannot be determined.
- `~/.hermes/bot/scripts/routstr_delist.py:582-585` `preds_error = bool(args.preds) and not raw_preds` marks explicitly requested-but-unusable feeds as an error.
- `~/.hermes/bot/scripts/routstr_delist.py:589-593` a stale feed zeroes out `raw_preds` before baseline updating.
- `~/.hermes/bot/scripts/routstr_delist.py:651-660` the quiet/no-fire path exits `1` when `preds_error or preds_stale`.
- `~/.hermes/bot/scripts/routstr_delist.py:248-268` `update_state` only overwrites `snapshot` when `preds` is truthy, preserving the previous baseline on empty/unusable feeds.

What is missing is an explicit test that a corrupt, non-empty `--preds` file (for example, valid JSON that is not a list of dicts) does not wipe the stored baseline. The test file asserts stale and missing-feed behavior, but not corrupt-feed baseline preservation.

---
