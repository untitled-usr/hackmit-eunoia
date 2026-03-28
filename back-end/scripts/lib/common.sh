#!/usr/bin/env bash
set -euo pipefail

readonly DEVSTACK_WORKSPACE_ROOT="/root/devstack/workspace"
readonly DEVSTACK_APPS_ROOT="${DEVSTACK_WORKSPACE_ROOT}/apps"
readonly DEVSTACK_STATE_ROOT="/srv/devstack/state"
readonly DEVSTACK_TEMPLATES_ROOT="${DEVSTACK_WORKSPACE_ROOT}/env/templates"

log_info() {
  printf '[INFO] %s\n' "$*"
}

log_warn() {
  printf '[WARN] %s\n' "$*" >&2
}

log_error() {
  printf '[ERROR] %s\n' "$*" >&2
}

require_dir() {
  local path="$1"
  if [[ ! -d "$path" ]]; then
    log_error "Directory not found: $path"
    exit 1
  fi
}

require_file() {
  local path="$1"
  if [[ ! -f "$path" ]]; then
    log_error "File not found: $path"
    exit 1
  fi
}
