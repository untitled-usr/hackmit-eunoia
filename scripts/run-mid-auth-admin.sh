#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"
# shellcheck source=./lib/load-env.sh
source "${SCRIPT_DIR}/lib/load-env.sh"

APP_ROOT="${DEVSTACK_WORKSPACE_ROOT}/services/mid-auth-admin"
ENV_FILE="${DEVSTACK_STATE_ROOT}/mid-auth/config/.env"

require_dir "${APP_ROOT}"
require_file "${APP_ROOT}/requirements.txt"
load_env_file "${ENV_FILE}"

MID_AUTH_ADMIN_HOST="${MID_AUTH_ADMIN_HOST:-127.0.0.1}"
MID_AUTH_ADMIN_PORT="${MID_AUTH_ADMIN_PORT:-18080}"
MID_AUTH_ADMIN_LOG_LEVEL="${MID_AUTH_ADMIN_LOG_LEVEL:-info}"

PYTHON_BIN="${APP_ROOT}/.venv/bin/python"
if [[ ! -x "${PYTHON_BIN}" ]]; then
	log_warn "No project venv at ${PYTHON_BIN}; falling back to python3 on PATH"
	PYTHON_BIN="python3"
fi

log_info "Starting Mid Auth Admin FastAPI on ${MID_AUTH_ADMIN_HOST}:${MID_AUTH_ADMIN_PORT}"
cd "${APP_ROOT}"
exec "${PYTHON_BIN}" -m uvicorn mid_auth_admin.main:app \
  --host "${MID_AUTH_ADMIN_HOST}" \
  --port "${MID_AUTH_ADMIN_PORT}" \
  --reload \
  --log-level "${MID_AUTH_ADMIN_LOG_LEVEL}"

