#!/usr/bin/env python3
"""Claim-2 probe: dispatch arm + candidate list for the routstr/routstrd lanes.

Loads the repo copies at the reviewed head (bb587eb3 worktree) — same loader
pattern as scripts/engine/test_routstr_v41_lane_wiring.py.
"""
import importlib.util
import sys
import types
from pathlib import Path

ENGINE = Path("/tmp/rv41-ho-wt/scripts/engine")
for p in (str(ENGINE), str(ENGINE / "src")):
    if p not in sys.path:
        sys.path.insert(0, p)

mods = {}
for name in ("zai_proxy", "flat_router"):
    spec = importlib.util.spec_from_file_location(name, ENGINE / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    mods[name] = m
    for p in (str(ENGINE), str(ENGINE / "src")):
        if p in sys.path:
            sys.path.remove(p)
        sys.path.insert(0, p)
zp, fr = mods["zai_proxy"], mods["flat_router"]

CANON = "deepseek/deepseek-flash"
print("PROVIDER_MODELS['routstr']  =", fr.PROVIDER_MODELS["routstr"])
print("PROVIDER_MODELS['routstrd'] =", fr.PROVIDER_MODELS["routstrd"])
print("_PROVIDER_MODEL_NAMES routstr  =", zp._PROVIDER_MODEL_NAMES.get("routstr"))
print("_PROVIDER_MODEL_NAMES routstrd =", zp._PROVIDER_MODEL_NAMES.get("routstrd"))
print()
print("PROVIDER_TIER   :", {l: fr.PROVIDER_TIER.get(l) for l in ("routstr", "routstrd")})
print("_SEED_RATES     :", {l: fr._SEED_RATES.get(l) for l in ("routstr", "routstrd")})
for lane in ("routstr", "routstrd"):
    ext = zp.EXTERNAL_PROVIDERS.get(lane)
    print(f"EXTERNAL_PROVIDERS[{lane}] base_url =", (ext or {}).get("base_url"))
print()
print("--- select_provider(%r) -> candidates ---" % CANON)
for c in fr.select_provider(CANON):
    print("   name=%-16s tier=%-10s effective_cost=%-10s model=%s" % (
        c.name, getattr(c, "tier", None), getattr(c, "effective_cost", None),
        getattr(c, "model", None)))
print()
print("--- dispatch arm ---")
for lane in ("routstr", "routstrd"):
    fn = fr._make_dispatch_fn(lane)
    print(f"  _make_dispatch_fn({lane!r}) = {fn!r} name={getattr(fn, '__name__', None)}")
print()
print("--- how dispatch fns are registered/looked up (source grep) ---")
import re
src = (ENGINE / "flat_router.py").read_text()
for i, line in enumerate(src.splitlines(), 1):
    if "_make_dispatch_fn" in line or "DISPATCH_FNS" in line or "routstr" in line.lower():
        print(f"  flat_router.py:{i}: {line.strip()[:130]}")
