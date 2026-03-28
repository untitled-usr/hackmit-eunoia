#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"
# shellcheck source=./lib/load-env.sh
source "${SCRIPT_DIR}/lib/load-env.sh"

APP_ROOT="${DEVSTACK_APPS_ROOT}/memos/web"
ENV_FILE="${DEVSTACK_STATE_ROOT}/memos/config/.env"

require_dir "${APP_ROOT}"
require_file "${APP_ROOT}/package.json"
load_env_file "${ENV_FILE}"

# Memos web requires Node >=24.
if [[ -s "${HOME}/.nvm/nvm.sh" ]]; then
  # shellcheck disable=SC1090
  source "${HOME}/.nvm/nvm.sh"
  nvm use 24 >/dev/null
fi

MEMOS_FE_PORT="${MEMOS_FE_PORT:-7924}"
export HOST="${HOST:-0.0.0.0}"
export DEV_PROXY_SERVER="${DEV_PROXY_SERVER:-http://127.0.0.1:${MEMOS_PORT:-7921}}"

log_info "Starting Memos frontend on port ${MEMOS_FE_PORT}"
cd "${APP_ROOT}"
pnpm dev --host "${HOST}" --port "${MEMOS_FE_PORT}"
