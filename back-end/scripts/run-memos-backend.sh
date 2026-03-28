#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"
# shellcheck source=./lib/load-env.sh
source "${SCRIPT_DIR}/lib/load-env.sh"

APP_ROOT="${DEVSTACK_APPS_ROOT}/memos"
ENV_FILE="${DEVSTACK_STATE_ROOT}/memos/config/.env"

require_dir "${APP_ROOT}"
require_file "${APP_ROOT}/go.mod"
load_env_file "${ENV_FILE}"

MEMOS_ADDR="${MEMOS_ADDR:-0.0.0.0}"
MEMOS_PORT="${MEMOS_PORT:-7921}"
MEMOS_DATA="${MEMOS_DATA:-/srv/devstack/state/memos/data}"
GO_BIN="go"

# Prefer snap Go for newer toolchain required by Memos.
if [[ -x "/snap/bin/go" ]]; then
  GO_BIN="/snap/bin/go"
fi

log_info "Starting Memos backend on ${MEMOS_ADDR}:${MEMOS_PORT}"
cd "${APP_ROOT}"
ARGS=(--addr "${MEMOS_ADDR}" --port "${MEMOS_PORT}" --data "${MEMOS_DATA}")
if [[ -n "${MEMOS_FRIENDSHIP_DSN:-}" ]]; then
  ARGS+=(--friendship-dsn "${MEMOS_FRIENDSHIP_DSN}")
fi
"${GO_BIN}" run ./cmd/memos "${ARGS[@]}"
