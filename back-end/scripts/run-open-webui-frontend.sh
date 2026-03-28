#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"

APP_ROOT="${DEVSTACK_APPS_ROOT}/open-webui"
require_dir "${APP_ROOT}"
require_file "${APP_ROOT}/package.json"

# Open WebUI currently targets Node <=22.
if [[ -s "${HOME}/.nvm/nvm.sh" ]]; then
  # shellcheck disable=SC1090
  source "${HOME}/.nvm/nvm.sh"
  nvm use 22 >/dev/null
fi

OWUI_FE_PORT="${OWUI_FE_PORT:-7923}"
export HOST="${HOST:-0.0.0.0}"

log_info "Starting Open WebUI frontend on port ${OWUI_FE_PORT}"
cd "${APP_ROOT}"
npm run dev -- --host "${HOST}" --port "${OWUI_FE_PORT}"
