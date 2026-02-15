#!/usr/bin/env bash
set -e

if [[ -z "${PROJECT_DIR:-}" ]]; then
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
    PROJECT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
fi

PLUGIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"

echo "[INFO] Patching core files for plugin blueprint support..."

python3 -c "
import sys
import os
sys.path.insert(0, '$PLUGIN_DIR')
from patch_core import patch_core_files

success, error = patch_core_files()
if not success:
    print(f'[ERROR] Patch failed: {error}')
    sys.exit(1)
print('[INFO] Core files patched successfully')
"

echo "[INFO] Done"

SERVICE_NAME="${APPNAME:-inkypi}"

if systemctl list-unit-files --type=service 2>/dev/null | grep -q "^${SERVICE_NAME}.service"; then
    echo "[INFO] Restarting ${SERVICE_NAME} service."
    sudo systemctl restart "${SERVICE_NAME}.service" 2>&1 || echo "[WARN] Service restart failed"
else
    echo "[INFO] Service ${SERVICE_NAME}.service not found, skipping restart (e.g. development mode)"
fi
