# Findings 1–3 Review: routstr dynamic delist

Artifacts reviewed end-to-end:
- `~/.hermes/bot/docs/routstr-delist.md`
- `~/.hermes/bot/scripts/routstr_delist.py`
- `~/.hermes/bot/tests/test_routstr_delist.py`

Note: `~/.hermes/bot/docs/routstr_delist_contract.md` was **missing**. The actual contract document is `~/.hermes/bot/docs/routstr-delist.md`, which was used instead. This path mismatch is a documentation/HIGH inconsistency for downstream tooling, but the contract itself is readable and complete.

---

## Finding 1 — Safety: remote-command shell-safety in `build_ssh_docker_cmd`

**Severity: LOW**

`~/.hermes/bot/scripts/routstr_delist.py:414-425` builds the `ssh` remote command as a single argv element and `shlex.quote`s the container name and the Python payload:

```python
remote = " ".join(["docker", "exec", shlex.quote(container),
                   "python3", "-c", shlex.quote(payload)])
return ["ssh", ssh_target, remote]
```

The local side runs `subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)` at `~/.hermes/bot/scripts/routstr_delist.py:808` **without** `shell=True`, so no local shell expansion occurs and the only shell parse is remote. Quoting the payload and container is correct and prevents remote shell injection from those values. The regression concept is present in tests via the `FakeSellNode` executing the real payload, although there is no explicit `shlex.split`-roundtrip assertion in `test_routstr_delist.py` against the exact string (the contract doc claims one exists).

The `ssh_target` is passed unquoted to `ssh` as a positional argument (`~/.hermes/bot/scripts/routstr_delist.py:425`). Because `ssh` itself parses the target as `[user@]host[:port]` (or accepts alias/config names), a malicious `--ssh-target` could redirect the connection. The target defaults to a fixed operator value and is only set via an explicit CLI override, so this is a configuration-level residual risk rather than an active command-injection vector in the constructed remote pipeline.

Evidence:
- `~/.hermes/bot/scripts/routstr_delist.py:414-425` — `build_ssh_docker_cmd` quotes `container` and `payload`.
- `~/.hermes/bot/scripts/routstr_delist.py:808` — local `subprocess.run` is not shell-invoked.
- `~/.hermes/bot/docs/routstr-delist.md:134-139` — contract documents the same shell-safety design and says a regression test reparses with `shlex.split`, which is not visibly present in `test_routstr_delist.py`.

Verdict: remote shell injection via the payload/container is mitigated correctly. Severity LOW for the unquoted `ssh_target` positional and the missing explicit `shlex.split` regression test.

---

## Finding 2 — Confirmation: independent re-fetch verifies a delist

**Severity: OK**

A fired delist performs a pull followed by an independent read-only verification round-trip. `~/.hermes/bot/scripts/routstr_delist.py:662-697` calls:

```python
vres = backend.verify(deadline=deadline)
if vres.get("ok") is True and vres.get("count") == 0:
    res["confirmed"] = True
    res["verified_count"] = vres.get("count")
    confirmed = True
    break
```

The verify payload at `~/.hermes/bot/scripts/routstr_delist.py:400-411` is read-only:

```python
return (
    "import sqlite3,json;"
    "db=sqlite3.connect('/app/data/keys.db');"
    "n=db.execute('SELECT COUNT(*) FROM models WHERE enabled=1')"
    ".fetchone()[0];"
    "print(json.dumps({'ok':True,'count':n}))"
)
```

If the verify reports a non-zero count or fails, `res["ok"]` is forced to `False`, `confirmed` stays `False`, and one bounded in-run retry is attempted while `time.monotonic() < deadline` (`~/.hermes/bot/scripts/routstr_delist.py:671-697`). Failure path at `~/.hermes/bot/scripts/routstr_delist.py:719-739` exits non-zero, does not set `delisted=true`, does not consume the acceleration baseline, and increments/trips the circuit breaker.

Tests cover this behavior:
- `~/.hermes/bot/tests/test_routstr_delist.py:318-345` confirms `delist` + verified count of zero.
- `~/.hermes/bot/tests/test_routstr_delist.py:346-360` confirms a lying pull is refuted by verification and fails with exit 1.

Evidence:
- `~/.hermes/bot/scripts/routstr_delist.py:400-411` — read-only verify payload.
- `~/.hermes/bot/scripts/routstr_delist.py:662-697` — verify gates `confirmed`.
- `~/.hermes/bot/scripts/routstr_delist.py:719-739` — failure semantics preserve baseline and flag.
- `~/.hermes/bot/tests/test_routstr_delist.py:318-360` — regression coverage for verified success and refuted pull.
- `~/.hermes/bot/docs/routstr-delist.md:64-75` — contract confirms the same semantics.

Verdict: independent verification is correctly implemented and tested. Severity OK.

---

## Finding 3 — Fail-safe: stale/corrupt `--preds` feed must not trigger or blind baseline

**Severity: OK**

Feed handling at `~/.hermes/bot/scripts/routstr_delist.py:580-597` is fail-closed:

```python
override = args.manual or manual_override(args.override)
raw_preds = _read_preds(args.preds)
preds_error = bool(args.preds) and not raw_preds
preds_stale = bool(args.preds) and bool(raw_preds) and \
    feed_is_stale(args.preds)
if preds_stale:
    raw_preds = []
```

`feed_is_stale` at `~/.hermes/bot/scripts/routstr_delist.py:485-496` treats any age-determination failure as stale:

```python
try:
    age = (now if now is not None else time.time()) - \
        os.path.getmtime(pred_input)
    return not (0 <= age <= max_age_s)
except OSError:
    return True
```

The stored baseline snapshot is only updated when `preds` is truthy (`~/.hermes/bot/scripts/routstr_delist.py:261-262`), so a missing/corrupt feed (`raw_preds == []`) cannot wipe the previous baseline (`~/.hermes/bot/scripts/routstr_delist.py:255-257`). A stale feed is zeroed before the snapshot update path, so it also does not refresh the baseline. When nothing fires, `preds_error` or `preds_stale` forces exit 1 (`~/.hermes/bot/scripts/routstr_delist.py:660`). Manual override is intentionally not gated by freshness (`~/.hermes/bot/scripts/routstr_delist.py:580` uses `args.manual` and `manual_override(args.override)` before the freshness guard).

Tests cover this:
- `~/.hermes/bot/tests/test_routstr_delist.py:427-433` confirms `--manual` still delists despite stale feed.
- `~/.hermes/bot/tests/test_routstr_delist.py:308-315` confirms first run without baseline is quiet.

Evidence:
- `~/.hermes/bot/scripts/routstr_delist.py:485-496` — `feed_is_stale` returns `True` on any error.
- `~/.hermes/bot/scripts/routstr_delist.py:580-597` — stale feeds are zeroed; errors are flagged.
- `~/.hermes/bot/scripts/routstr_delist.py:255-262` — baseline only refreshes on non-empty predictions.
- `~/.hermes/bot/scripts/routstr_delist.py:660` — non-zero exit when feed error or stale.
- `~/.hermes/bot/tests/test_routstr_delist.py:427-433` — manual override bypasses stale guard.
- `~/.hermes/bot/docs/routstr-delist.md:55-60` — contract describes the freshness guard.

Verdict: stale and unreadable feeds are handled fail-closed, preserve baseline, and surface failure. Severity OK.
