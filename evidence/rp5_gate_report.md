# RP-5 Shadow Validation Evidence Report

**Report path:** `evidence/rp5_gate_report.md`
**Raw evidence (JSONL):** `evidence/rp5_shadow_evidence.jsonl`
**Summarizer:** `src/rp5_shadow_validator.py`
**Gate:** RP-5 (Proactive GLM-5.2 Throttling / Real Price Tracking)
**Date:** 2026-09-14
**Verdict:** **FAIL**

---

## Executive Summary

The 48-hour shadow validation window was executed against the live
`zai_proxy` instrumentation in `~/.hermes/bot/zai_usage.db`. The proxy is
active (api_calls within 2 minutes of evaluation). Three of the six RP-5
gate criteria **FAIL** due to pre-existing infrastructure gaps — not due to
the RP-5 logic itself. The gate cannot pass in its current state because
the shadow-mode instrumentation is not fully wired on this host (DQ05).

## Per-Criterion Evaluation

### (a) All 6 providers measured within 30 min of startup — **FAIL**

- **Expected:** `ours, friend, ollama_cloud, ppq, deepinfra, openrouter`
- **Seen in 30-min window:** `ollama_cloud` only
- **Missing:** `ours, friend, ppq, deepinfra, openrouter`
- **Root cause:** The proxy on DQ05 routes to a reduced provider set
  (`ollama_cloud, opencode_go, telnyx, oxalpha`). The full 6-provider set
  (`ours, friend, ppq, deepinfra, openrouter`) has not been active in the
  last 48h — `ours` last seen 80h ago, `friend` 775h ago, `ppq` 90h ago.
  The proxy's traffic pattern is low-volume health checks, not production
  routing through all providers.

### (b) Ollama rate converges to $0.0155/M +/-10% — **PASS**

- **Target:** $0.0155/M, tolerance +/-10% → range $0.01395–$0.01705
- **Actual:** $0.0155/M (source: `seed`)
- **Note:** The rate matches the target exactly, but this is the cold-start
  seed value, not a measured convergence. `real_price_tracker` reports
  `source=seed` for `ollama_cloud` — no `cost_usd` data in `api_calls`
  (the column does not exist in this DB). The gate passes because the seed
  is within tolerance, but this is not a true convergence.

### (c) Extra-usage detected when session.usage >= 1.0 — **FAIL**

- **API available:** No
- **Session usage:** None (cannot fetch)
- **Root cause:** `OLLAMA_CLOUD_API_KEY` environment variable is not set on
  this host. `fetch_ollama_usage()` returns `None` because it cannot
  authenticate to `https://ollama.com/api/usage`. Without the API, the
  `session_usage` fraction is unavailable, and the extra-usage regime
  cannot be detected. The `routing_shadow_decisions` table (P6 pressure
  routing) has **0 rows** — no quota_regime data has ever been logged.
  `pressure_decisions` shows only `GREEN` state.

### (d) Extra rate $0.46/M +/-30% for glm-5.2 when active — **PASS**

- **Target:** $0.46/M, tolerance +/-30% → range $0.322–$0.598
- **Actual:** $0.46/M (source: `realtime_pricing_seed`)
- **Note:** The rate matches the `DEFAULT_COLD_START_RATES` seed in
  `src/realtime_pricing.py`. This is the documented measured value from
  `docs/extra-usage-real-data-analysis.md`. No live measured extra-usage
  data is available (API unreachable), so the seed is used. Passes by
  definition (seed == target), but the "when active" condition was never
  triggered (criterion (c) failed).

### (e) No NaN/crash/stale > 30 min — **FAIL**

- **NaN/inf count:** 0 (clean)
- **Stale tables (> 30 min):**
  - `flat_router_shadow_decisions`: 47.9h stale (last entry 2026-09-12 19:50)
  - `routing_shadow_decisions`: never (0 rows — table empty)
- **Fresh tables:**
  - `api_calls`: 1.8m (proxy alive)
  - `key_decisions`: 55s
  - `routing_profit`: 55s
  - `pressure_decisions`: 1.8m
- **Root cause:** The P6 pressure-routing shadow table
  (`routing_shadow_decisions`) has 0 rows — the shadow optimizer's
  `log_decision_with_pressure` path is not being invoked. The proxy's
  shadow hook (`_shadow_hook`) may have failed to initialize, or the
  `log_decision_with_pressure` method is not being called because the
  shadow optimizer's `route()` call returns no decision. The
  `flat_router_shadow_decisions` table stopped receiving data 47.9h ago,
  suggesting the flat-router shadow comparison path also stopped.

### (f) Kill switch OFF = identical routing to current behavior — **PASS**

- **Env var:** `OLLAMA_THROTTLE_ENABLED=false` (not set → defaults to false)
- **Systemd conf:** `env-features.conf` does NOT contain
  `OLLAMA_THROTTLE_ENABLED` — confirmed absent.
- **Kill switch:** OFF
- **Note:** With the kill switch OFF, the RP-5 proactive throttle logic
  (`_THROTTLE_ENABLED = False`) is completely bypassed. The throttle state
  is always `"normal"`, no tier/price adjustments are applied, and routing
  behaves identically to the pre-RP-5 baseline. This is the correct shadow
  configuration.

---

## Anomalies and Root Causes

| # | Criterion | Anomaly | Root Cause |
|---|-----------|---------|------------|
| 1 | (a) | 5 of 6 providers not seen | DQ05 proxy routes to a reduced set (ollama_cloud, opencode_go, telnyx, oxalpha). ours/friend/ppq/deepinfra/openrouter are not active on this host. |
| 2 | (c) | Ollama API unreachable | `OLLAMA_CLOUD_API_KEY` not set. `fetch_ollama_usage()` returns None. No extra-usage detection possible. |
| 3 | (c) | `routing_shadow_decisions` empty (0 rows) | The P6 pressure-routing shadow log path is not being invoked. The shadow optimizer either failed to init or the `log_decision_with_pressure` call is never reached. |
| 4 | (e) | `flat_router_shadow_decisions` stale 47.9h | The flat-router shadow comparison stopped 47.9h ago. Likely the proxy was restarted or the flat router shadow path broke. |
| 5 | (e) | Rate refresh cron not active | No systemd timer or crontab entry exists for `real_price_tracker.collect_rates()` (RP-5b). The `rate_export.json` file does not exist. |

---

## Instrumentation Health

### Proxy state
- The `zai-proxy.service` systemd unit shows `inactive (dead)` but
  `api_calls` and `key_decisions` are being updated within 2 minutes,
  indicating the proxy IS running — likely via a different mechanism
  (embedded in another process, or started manually outside systemd).

### Feature flags (from systemd drop-in `env-features.conf`)
- `ZAI_QUOTA_PRESSURE_ENABLED=true`
- `OLLAMA_QUOTA_PRESSURE_ENABLED=true`
- `LIVE_ROUTER_DYNAMIC_RATES_ENABLED=true`
- `PER_MODEL_PRICING_ENABLED=true`
- `OLLAMA_THROTTLE_ENABLED` — **NOT SET** (kill switch OFF, correct for shadow)

### Rate refresh (RP-5b cron)
- **Not wired.** No crontab entry or systemd timer for
  `real_price_tracker.collect_rates()`. The `rate_export.json` output file
  does not exist. `collect_rates()` runs only when manually invoked.
  All providers report `source=seed` — none have measured data.

---

## Gate Verdict

**FAIL** — 3 of 6 criteria pass (b, d, f), 3 fail (a, c, e).

The failures are infrastructure gaps on this host (DQ05), not RP-5 logic
errors:
- (a) The proxy doesn't route to all 6 providers in the startup window
- (c) The Ollama billing API key is not configured
- (e) The P6 shadow table and rate-refresh cron are not wired

**Recommendation:** The gate cannot pass on DQ05 in its current
configuration. To pass, the following would need to be addressed:
1. Set `OLLAMA_CLOUD_API_KEY` so `fetch_ollama_usage()` can reach the API
2. Wire the RP-5b rate-refresh cron (systemd timer calling
   `collect_rates()` hourly)
3. Investigate why `routing_shadow_decisions` receives 0 rows (the shadow
   hook's `log_decision_with_pressure` path is not being invoked)
4. Ensure all 6 providers are exercised within the startup window (either
   via real traffic or synthetic health probes)

The kill switch (criterion f) is correctly OFF — routing is identical to
the baseline, and the RP-5 throttle logic is not affecting any routing
decisions. No live routing or billing was modified during this validation.

---

## Raw Evidence

Health-check evidence is appended to `evidence/rp5_shadow_evidence.jsonl`
(JSONL format, one line per health-check run). The full gate evaluation
JSON is at `evidence/rp5_gate_report.json`.

A periodic health-check cron job (`rp5-shadow-health-check`, every 3h)
will continue appending evidence lines to the JSONL file for ongoing
monitoring.

### Evidence file paths (stable)
- `evidence/rp5_gate_report.md` — this written report
- `evidence/rp5_gate_report.json` — machine-readable gate evaluation
- `evidence/rp5_shadow_evidence.jsonl` — health-check evidence log (JSONL)
- `src/rp5_shadow_validator.py` — the summarizer script