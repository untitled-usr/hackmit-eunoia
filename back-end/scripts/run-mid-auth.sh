#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"
# shellcheck source=./lib/load-env.sh
source "${SCRIPT_DIR}/lib/load-env.sh"

APP_ROOT="${DEVSTACK_WORKSPACE_ROOT}/services/mid-auth"
ENV_FILE="${DEVSTACK_STATE_ROOT}/mid-auth/config/.env"

require_dir "${APP_ROOT}"
require_file "${APP_ROOT}/requirements.txt"
load_env_file "${ENV_FILE}"

MID_AUTH_HOST="${MID_AUTH_HOST:-0.0.0.0}"
MID_AUTH_PORT="${MID_AUTH_PORT:-19000}"
MID_AUTH_LOG_LEVEL="${MID_AUTH_LOG_LEVEL:-info}"
MID_AUTH_ENABLE_HTTPS="${MID_AUTH_ENABLE_HTTPS:-false}"
MID_AUTH_TLS_CERTFILE="${MID_AUTH_TLS_CERTFILE:-}"
MID_AUTH_TLS_KEYFILE="${MID_AUTH_TLS_KEYFILE:-}"

# 使用 venv 的 python -m uvicorn，避免直接调用 .venv/bin/uvicorn --reload 时
# multiprocessing spawn 子进程落到系统 Python（缺依赖、加载系统 site-packages）。
PYTHON_BIN="${APP_ROOT}/.venv/bin/python"
if [[ ! -x "${PYTHON_BIN}" ]]; then
	log_warn "No project venv at ${PYTHON_BIN}; falling back to python3 on PATH"
	PYTHON_BIN="python3"
fi

UVICORN_ARGS=(
	-m uvicorn app.main:app
	--host "${MID_AUTH_HOST}"
	--port "${MID_AUTH_PORT}"
	--reload
	--log-level "${MID_AUTH_LOG_LEVEL}"
)

if [[ "${MID_AUTH_ENABLE_HTTPS,,}" == "true" ]]; then
	if [[ -z "${MID_AUTH_TLS_CERTFILE}" || -z "${MID_AUTH_TLS_KEYFILE}" ]]; then
		log_error "MID_AUTH_ENABLE_HTTPS=true requires MID_AUTH_TLS_CERTFILE and MID_AUTH_TLS_KEYFILE"
		exit 1
	fi
	require_file "${MID_AUTH_TLS_CERTFILE}"
	require_file "${MID_AUTH_TLS_KEYFILE}"
	UVICORN_ARGS+=(--ssl-certfile "${MID_AUTH_TLS_CERTFILE}" --ssl-keyfile "${MID_AUTH_TLS_KEYFILE}")
	log_info "Starting Mid Auth FastAPI with HTTPS on ${MID_AUTH_HOST}:${MID_AUTH_PORT}"
else
	log_info "Starting Mid Auth FastAPI on ${MID_AUTH_HOST}:${MID_AUTH_PORT}"
fi

cd "${APP_ROOT}"
exec "${PYTHON_BIN}" "${UVICORN_ARGS[@]}"
