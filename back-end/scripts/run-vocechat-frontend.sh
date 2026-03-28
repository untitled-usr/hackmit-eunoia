#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"
# shellcheck source=./lib/load-env.sh
source "${SCRIPT_DIR}/lib/load-env.sh"

APP_ROOT="${DEVSTACK_APPS_ROOT}/vocechat-web"
ENV_FILE="${DEVSTACK_STATE_ROOT}/vocechat/config/.env"

require_dir "${APP_ROOT}"
require_file "${APP_ROOT}/package.json"
load_env_file "${ENV_FILE}"

# Run VoceChat web with modern Node runtime.
if [[ -s "${HOME}/.nvm/nvm.sh" ]]; then
  # shellcheck disable=SC1090
  source "${HOME}/.nvm/nvm.sh"
  nvm use 24 >/dev/null
fi

export HOST="${HOST:-0.0.0.0}"
export PORT="${VOCECHAT_FE_PORT:-7925}"
export VOCECHAT_API_TARGET="${VOCECHAT_API_TARGET:-http://127.0.0.1:${VOCECHAT_SERVER_PORT:-7922}}"
export VOCECHAT_WEB_ROOT="${APP_ROOT}"

log_info "Building VoceChat web release bundle"
cd "${APP_ROOT}"
pnpm build:release

log_info "Starting VoceChat web on ${HOST}:${PORT} (proxy -> ${VOCECHAT_API_TARGET})"
node "${SCRIPT_DIR}/serve-vocechat-frontend.js"
