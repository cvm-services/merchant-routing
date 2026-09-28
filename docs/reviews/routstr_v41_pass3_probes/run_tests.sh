#!/usr/bin/env bash
set -u
OUT=/mnt/cw-offload/review-rv41/ev
mkdir -p "$OUT"
HO=/mnt/cw-offload/rv41-wt-ho
MRE=/mnt/cw-offload/rv41-wt-mre

{
echo "### host=$(hostname) date=$(date -Is)"
echo "### repo heads:"
echo "  HO worktree: $(git -C "$HO" rev-parse HEAD) $(git -C "$HO" log -1 --format=%s)"
echo "  MRE worktree: $(git -C "$MRE" rev-parse HEAD) $(git -C "$MRE" log -1 --format=%s)"
echo "### test file inventory:"
ls -la "$HO/scripts/engine/test_routstr_v41_lane_wiring.py" "$HO/tests/test_routstrd_lane_role.py" "$HO/tests/run_routstrd_lane_idempotency.sh" "$MRE/tests/test_routstrd_funding_guard.py" "$MRE/tests/test_routstrd_balance_cron.py" 2>&1
} > "$OUT/t_meta.txt" 2>&1

cd "$HO"
echo "===== T1 wiring (in-repo pytest) =====" > "$OUT/t1_wiring.txt" 2>&1
python3 -m pytest scripts/engine/test_routstr_v41_lane_wiring.py -q -p no:cacheprovider >> "$OUT/t1_wiring.txt" 2>&1
echo "rc=$?" >> "$OUT/t1_wiring.txt"

echo "===== T2 role (in-repo pytest) =====" > "$OUT/t2_role.txt" 2>&1
python3 -m pytest tests/test_routstrd_lane_role.py -q -p no:cacheprovider >> "$OUT/t2_role.txt" 2>&1
echo "rc=$?" >> "$OUT/t2_role.txt"

echo "===== T3 idempotency harness =====" > "$OUT/t3_idem.txt" 2>&1
bash tests/run_routstrd_lane_idempotency.sh >> "$OUT/t3_idem.txt" 2>&1
echo "rc=$?" >> "$OUT/t3_idem.txt"

cd "$MRE"
echo "===== T4 guard tests (engine @8b91148) =====" > "$OUT/t4_guard.txt" 2>&1
python3 -m pytest tests/test_routstrd_funding_guard.py -q -p no:cacheprovider >> "$OUT/t4_guard.txt" 2>&1
echo "rc=$?" >> "$OUT/t4_guard.txt"

echo "===== T5 balance-cron tests (engine @8b91148) =====" > "$OUT/t5_balance.txt" 2>&1
python3 -m pytest tests/test_routstrd_balance_cron.py -q -p no:cacheprovider >> "$OUT/t5_balance.txt" 2>&1
echo "rc=$?" >> "$OUT/t5_balance.txt"

tail -n 6 "$OUT"/t1_wiring.txt "$OUT"/t2_role.txt "$OUT"/t3_idem.txt "$OUT"/t4_guard.txt "$OUT"/t5_balance.txt
