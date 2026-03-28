#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"

BACKEND_SCRIPT="${SCRIPT_DIR}/run-open-webui-backend.sh"
FRONTEND_SCRIPT="${SCRIPT_DIR}/run-open-webui-frontend.sh"

require_file "${BACKEND_SCRIPT}"
require_file "${FRONTEND_SCRIPT}"

backend_pid=""
frontend_pid=""

cleanup() {
  local exit_code="${1:-0}"

  if [[ -n "${backend_pid}" ]] && kill -0 "${backend_pid}" 2>/dev/null; then
    kill "${backend_pid}" 2>/dev/null || true
  fi

  if [[ -n "${frontend_pid}" ]] && kill -0 "${frontend_pid}" 2>/dev/null; then
    kill "${frontend_pid}" 2>/dev/null || true
  fi

  wait "${backend_pid}" 2>/dev/null || true
  wait "${frontend_pid}" 2>/dev/null || true
  exit "${exit_code}"
}

on_signal() {
  log_info "Received stop signal, shutting down Open WebUI services..."
  cleanup 0
}

trap on_signal INT TERM

log_info "Starting Open WebUI backend + frontend (non-Docker)..."

bash "${BACKEND_SCRIPT}" &
backend_pid="$!"
log_info "Backend started (pid=${backend_pid})"

bash "${FRONTEND_SCRIPT}" &
frontend_pid="$!"
log_info "Frontend started (pid=${frontend_pid})"

log_info "Open WebUI should be available at http://localhost:7923 (frontend) and http://localhost:7920 (backend)"
log_info "Press Ctrl+C to stop both services"

wait -n "${backend_pid}" "${frontend_pid}"
status="$?"
log_warn "One of the Open WebUI processes exited (status=${status}), stopping the other one..."
cleanup "${status}"
