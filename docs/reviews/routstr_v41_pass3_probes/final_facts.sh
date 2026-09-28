#!/usr/bin/env bash
# consolidated, re-run-able fact capture for the pass-3 report
set -u
HO=/home/c03rad0r/hermes-orchestration
MRE=/mnt/cw-offload/merchant-routing-engine
echo "### captured $(date -Is) on $(hostname)"
echo
echo "=== A. hermes-orchestration lineage ==="
git -C "$HO" rev-parse --short origin/master
git -C "$HO" log --oneline -1 origin/master
for sha in 34aa21ac a81041ee 67e0f1b7 c7be49ad 37d6b55f; do
  printf '%s subject=%s\n' "$sha" "$(git -C "$HO" log --oneline -1 --format='%s' $sha 2>/dev/null || echo MISSING)"
  git -C "$HO" merge-base --is-ancestor "$sha" origin/master 2>/dev/null \
    && echo "   ancestor-of-origin/master: YES" || echo "   ancestor-of-origin/master: NO/unknown"
done
echo "-- github refs at the PR tips --"
git -C "$HO" log --oneline -1 refs/remotes/github/pr/routstr-v41-lane-wiring 2>/dev/null
git -C "$HO" log --oneline -1 refs/remotes/github/pr/routstrd-lane-service 2>/dev/null
echo "-- github/master --"
git -C "$HO" log --oneline -1 refs/remotes/github/master 2>/dev/null
echo
echo "=== B. blob identity (repo vs deployed) ==="
for ref in 34aa21ac a81041ee origin/master; do
  printf '%-14s flat_router=%s zai_proxy=%s\n' "$ref" \
    "$(git -C "$HO" rev-parse $ref:scripts/engine/flat_router.py 2>/dev/null)" \
    "$(git -C "$HO" rev-parse $ref:scripts/engine/zai_proxy.py 2>/dev/null)"
done
echo "deployed cobrador (md5): $(md5sum /mnt/cw-offload/rv41-deployed/flat_router.py | cut -d' ' -f1) / $(md5sum /mnt/cw-offload/rv41-deployed/zai_proxy.py | cut -d' ' -f1)"
echo "deployed dq05     (md5): $(md5sum /home/c03rad0r/.hermes/bot/flat_router.py | cut -d' ' -f1) / $(md5sum /home/c03rad0r/.hermes/bot/zai_proxy.py | cut -d' ' -f1)"
echo "origin/master     (md5): $(git -C "$HO" cat-file blob origin/master:scripts/engine/flat_router.py | md5sum | cut -d' ' -f1) / $(git -C "$HO" cat-file blob origin/master:scripts/engine/zai_proxy.py | md5sum | cut -d' ' -f1)"
echo
echo "=== C. role 51 / master delta vs the reviewed head ==="
git -C "$HO" diff --stat a81041ee origin/master -- roles/51-routstrd-lane/
echo "-- the 4-line defaults delta --"
git -C "$HO" diff a81041ee origin/master -- roles/51-routstrd-lane/defaults/main.yml | sed -n '1,30p'
echo
echo "=== D. merchant-routing-engine lineage ==="
git -C "$MRE" log --oneline -1 refs/heads/main
git -C "$MRE" log --oneline -1 refs/remotes/github/main 2>/dev/null
git -C "$MRE" merge-base --is-ancestor 8b91148 refs/heads/main && echo "8b91148 ancestor of main: YES"
echo "guard blobs: 8b91148=$(git -C "$MRE" rev-parse 8b91148:scripts/routstrd_funding_guard.py) worktree-md5=$(md5sum "$MRE/scripts/routstrd_funding_guard.py" | cut -d' ' -f1)"
echo "            HEADfile-md5=$(git -C "$MRE" show 8b91148:scripts/routstrd_funding_guard.py | md5sum | cut -d' ' -f1)"
