#!/usr/bin/env bash
# Role-51 convergence probe at master: run the SHIPPED role through the SHIPPED
# deploy shape (gather_facts: no, like playbook-live-router.yml) but WITHOUT the
# idempotency harness's override of routstrd_funding_guard_script/_log, so the
# defaults/main.yml expression is templated for real.
#
# Side-effect-free: throwaway HOME, routstrd_lane_manage_service=false,
# routstrd_lane_manage_crontab=false (the role's own sandbox gates).
set -euo pipefail

HO=/mnt/cw-offload/rv41-wt-ho
ROLE_SRC="$HO/roles/51-routstrd-lane"
SSTEST="$(mktemp -d -t rv41rolepath.XXXXXX)"
trap '[ -n "${KEEP:-}" ] || rm -rf "$SSTEST"' EXIT

FIX="$SSTEST/repo"
export HOME="$SSTEST/home"
mkdir -p "$HOME" "$FIX/roles" "$FIX/scripts/fleet"
cp -r "$ROLE_SRC" "$FIX/roles/51-routstrd-lane"
cp "$HO/scripts/fleet/routstrd_lane_guard.sh" "$FIX/scripts/fleet/"

# synthetic toolchain + the wallet/config the role gates on
mkdir -p "$HOME/.bun/bin" "$HOME/.bun/install/global/node_modules/routstrd/dist/daemon"
printf '#!/bin/sh\nexit 0\n' > "$HOME/.bun/bin/bun"; chmod +x "$HOME/.bun/bin/bun"
: > "$HOME/.bun/install/global/node_modules/routstrd/dist/index.js"
: > "$HOME/.bun/install/global/node_modules/routstrd/dist/daemon/index.js"
ln -s ../install/global/node_modules/routstrd/dist/index.js "$HOME/.bun/bin/routstrd"
mkdir -p "$HOME/.routstrd/wallet" "$HOME/.hermes/scripts" "$HOME/.config/systemd/user"
printf '{"port":8008,"host":"127.0.0.1"}\n' > "$HOME/.routstrd/config.json"
mkdir -p "$HOME/merchant-routing-engine/scripts" "$HOME/merchant-routing-engine/logs"
printf '#!/usr/bin/env python3\nprint("stub")\n' > "$HOME/merchant-routing-engine/scripts/routstrd_funding_guard.py"

# NOTE: no routstrd_funding_guard_script / _log overrides here (unlike the
# shipped tests/run_routstrd_lane_idempotency.sh) — the role's own defaults are
# what we are probing.
cat > "$FIX/playbook.yml" <<'YAML'
---
- name: 51-routstrd-lane path-resolution probe (shipped deploy shape)
  hosts: localhost
  connection: local
  gather_facts: no
  vars:
    repo_dir: "{{ playbook_dir }}"
    hermes_home: "{{ lookup('env','HOME') }}/.hermes"
    routstrd_lane_home: "{{ lookup('env','HOME') }}"
    routstrd_lane_manage_service: false
    routstrd_lane_manage_crontab: false
  tasks:
    - import_role: { name: 51-routstrd-lane }
YAML

set +e
ansible-playbook "$FIX/playbook.yml" -i localhost, 2>&1 | tail -30
rc=${PIPESTATUS[0]}
set -e
echo "PLAYBOOK rc=$rc"
