#!/usr/bin/env python3
"""pass-5 probe: what does the flat router's candidate list actually look like
for the canonical deepseek/deepseek-flash id, at origin/master?

Loads the repo copies of zai_proxy/flat_router by explicit path (same technique
as scripts/engine/test_routstr_v41_lane_wiring.py's loader) so the DEPLOYED
~/.hermes/bot copies cannot mask the repo change.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ENGINE = Path("/home/c03rad0r/worktrees/ho-deploy/scripts/engine")
CANONICAL = "deepseek/deepseek-flash"

for p in (str(ENGINE), str(ENGINE / "src")):
    if p not in sys.path:
        sys.path.insert(0, p)

for name in ("zai_proxy", "flat_router"):
    spec = importlib.util.spec_from_file_location(name, ENGINE / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    for p in (str(ENGINE), str(ENGINE / "src")):
        if p in sys.path:
            sys.path.remove(p)
        sys.path.insert(0, p)

import flat_router as fr  # noqa: E402

print("canonical:", CANONICAL)
print("PROVIDER_MODELS[routstr]  has canonical:", CANONICAL in fr.PROVIDER_MODELS["routstr"])
print("PROVIDER_MODELS[routstrd] has canonical:", CANONICAL in fr.PROVIDER_MODELS["routstrd"])

cands = fr.select_provider(CANONICAL)
print(f"\nselect_provider({CANONICAL!r}) -> {len(cands)} candidates")
for c in cands:
    name = getattr(c, "name", None)
    cost = getattr(c, "effective_cost", "n/a")
    print(f"  {name:<16} effective_cost={cost!r}  attrs={[a for a in dir(c) if not a.startswith('_')][:8]}")
names = [getattr(c, "name", None) for c in cands]
for lane in ("routstr", "routstrd"):
    print(f"lane {lane!r} in candidates: {lane in names}")

fn = fr._make_dispatch_fn("routstrd")
print(f"\n_make_dispatch_fn('routstrd') -> {fn.__name__ if fn else None}")
fn2 = fr._make_dispatch_fn("routstr")
print(f"_make_dispatch_fn('routstr')  -> {fn2.__name__ if fn2 else None}")
