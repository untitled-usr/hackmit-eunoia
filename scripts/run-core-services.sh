#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"

MID_AUTH_SCRIPT="${SCRIPT_DIR}/run-mid-auth.sh"
OPEN_WEBUI_SCRIPT="${SCRIPT_DIR}/run-open-webui.sh"
VOCECHAT_BACKEND_SCRIPT="${SCRIPT_DIR}/run-vocechat-backend.sh"
VOCECHAT_FRONTEND_SCRIPT="${SCRIPT_DIR}/run-vocechat-frontend.sh"
MEMOS_SCRIPT="${SCRIPT_DIR}/run-memos.sh"
ASR_SCRIPT="${DEVSTACK_APPS_ROOT}/virtmate/ai_virtual_mate_comm/start_asr_api.sh"

require_file "${MID_AUTH_SCRIPT}"
require_file "${OPEN_WEBUI_SCRIPT}"
require_file "${VOCECHAT_BACKEND_SCRIPT}"
require_file "${VOCECHAT_FRONTEND_SCRIPT}"
require_file "${MEMOS_SCRIPT}"
require_file "${ASR_SCRIPT}"

pids=()
names=()

start_service() {
  local name="$1"
  local script="$2"

  log_info "Starting ${name}..."
  bash "${script}" &
  local pid="$!"
  pids+=("${pid}")
  names+=("${name}")
  log_info "${name} started (pid=${pid})"
}

cleanup() {
  local exit_code="${1:-0}"
  trap - INT TERM

  for pid in "${pids[@]}"; do
    if kill -0 "${pid}" 2>/dev/null; then
      kill "${pid}" 2>/dev/null || true
    fi
  done

  for pid in "${pids[@]}"; do
    wait "${pid}" 2>/dev/null || true
  done

  exit "${exit_code}"
}

on_signal() {
  log_info "Received stop signal, shutting down all core services..."
  cleanup 0
}

service_name_for_pid() {
  local target_pid="$1"
  local i
  for i in "${!pids[@]}"; do
    if [[ "${pids[$i]}" == "${target_pid}" ]]; then
      printf '%s\n' "${names[$i]}"
      return 0
    fi
  done
  printf 'unknown-service\n'
}

remove_pid() {
  local target_pid="$1"
  local new_pids=()
  local new_names=()
  local i
  for i in "${!pids[@]}"; do
    if [[ "${pids[$i]}" != "${target_pid}" ]]; then
      new_pids+=("${pids[$i]}")
      new_names+=("${names[$i]}")
    fi
  done
  pids=("${new_pids[@]}")
  names=("${new_names[@]}")
}

trap on_signal INT TERM

log_info "Starting core services: Mid Auth + Open WebUI + VoceChat + Memos + ASR"

start_service "mid-auth" "${MID_AUTH_SCRIPT}"
start_service "open-webui" "${OPEN_WEBUI_SCRIPT}"
start_service "vocechat-backend" "${VOCECHAT_BACKEND_SCRIPT}"
start_service "vocechat-frontend" "${VOCECHAT_FRONTEND_SCRIPT}"
start_service "memos" "${MEMOS_SCRIPT}"
start_service "asr" "${ASR_SCRIPT}"

log_info "All launch commands sent."
log_info "Press Ctrl+C to stop all services."

overall_status=0
while [[ "${#pids[@]}" -gt 0 ]]; do
  exited_pid=""
  status=0
  if ! wait -n -p exited_pid "${pids[@]}"; then
    status="$?"
  fi

  exited_service="$(service_name_for_pid "${exited_pid}")"
  if [[ "${status}" -eq 0 ]]; then
    log_info "Service exited: ${exited_service} (pid=${exited_pid}, status=0)"
  else
    log_warn "Service exited with error: ${exited_service} (pid=${exited_pid}, status=${status})"
    overall_status="${status}"
  fi

  remove_pid "${exited_pid}"
done

log_info "All managed services have exited."
exit "${overall_status}"
