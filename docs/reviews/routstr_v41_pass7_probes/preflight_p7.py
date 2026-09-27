#!/usr/bin/env python3
"""Pre-flight the pass-7 review artifact with the gate engine's own functions."""
import importlib.util
import os
import sys

ENG = os.path.expanduser("~/.hermes/bot/governance/gate_engine.py")
spec = importlib.util.spec_from_file_location("gate_engine", ENG)
ge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ge)

path = sys.argv[1]
text = open(path, "r", encoding="utf-8").read()

print("artifact:", path, len(text), "chars")
print("approval_asserted:", ge.approval_asserted(text))
print("RE_MODEL.findall:", sorted(set(ge.RE_MODEL.findall(text))))
print("review_benchmark_floor_ok('kimi-k3','tier/review-kimi'):",
      ge.review_benchmark_floor_ok("kimi-k3", "tier/review-kimi"))
print("scan_secrets:", ge.scan_secrets(text))
print("pr_branch_asserted:", ge.pr_branch_asserted(text))
for fn in ("RE_REJECT", "RE_APPROVE"):
    rx = getattr(ge, fn, None)
    if rx is not None:
        print(f"{fn}:", sorted(set(rx.findall(text)))[:6])
