#!/usr/bin/env python3
"""pass-7 probe: lane wiring at the reviewed head (a81041ee).

Loads the repo copies of zai_proxy/flat_router by explicit path (same loader
technique as scripts/engine/test_routstr_v41_lane_wiring.py) so that the
DEPLOYED ~/.hermes/bot copies cannot mask the reviewed change.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ENGINE = Path(sys.argv[1] if len(sys.argv) > 1
              else "/mnt/cw-offload/rv41-wt-ho-a810/scripts/engine")
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
import zai_proxy as zp  # noqa: E402

out = {"engine": str(ENGINE)}
out["canonical"] = CANONICAL
out["reg_routstr"] = sorted(fr.PROVIDER_MODELS.get("routstr", []))
out["reg_routstrd"] = sorted(fr.PROVIDER_MODELS.get("routstrd", []))
out["has_canonical_routstr"] = CANONICAL in fr.PROVIDER_MODELS.get("routstr", [])
out["has_canonical_routstrd"] = CANONICAL in fr.PROVIDER_MODELS.get("routstrd", [])

trans = {}
for lane in ("routstr", "routstrd"):
    try:
        trans[lane] = zp._PROVIDER_MODEL_NAMES[lane].get(CANONICAL)
    except Exception as e:  # noqa: BLE001
        trans[lane] = f"ERR {e!r}"
out["translate"] = trans

cands = fr.select_provider(CANONICAL)
rows = []
for c in cands:
    rows.append({
        "name": getattr(c, "name", None),
        "effective_cost": repr(getattr(c, "effective_cost", "n/a")),
        "base_url": getattr(c, "base_url", None),
    })
out["candidates"] = rows
names = [getattr(c, "name", None) for c in cands]
out["lane_in_candidates"] = {lane: (lane in names) for lane in ("routstr", "routstrd")}

disp = {}
for lane in ("routstr", "routstrd"):
    try:
        fn = fr._make_dispatch_fn(lane)
        disp[lane] = getattr(fn, "__name__", None)
    except Exception as e:  # noqa: BLE001
        disp[lane] = f"ERR {e!r}"
out["dispatch_fn"] = disp

print(json.dumps(out, indent=2))
