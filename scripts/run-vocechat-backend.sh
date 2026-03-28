#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"
# shellcheck source=./lib/load-env.sh
source "${SCRIPT_DIR}/lib/load-env.sh"

APP_ROOT="${DEVSTACK_APPS_ROOT}/vocechat-server"
ENV_FILE="${DEVSTACK_STATE_ROOT}/vocechat/config/.env"

require_dir "${APP_ROOT}"
require_file "${APP_ROOT}/Cargo.toml"
load_env_file "${ENV_FILE}"

VOCECHAT_CONFIG_FILE="${VOCECHAT_CONFIG_FILE:-/srv/devstack/state/vocechat/config/config.toml}"
require_file "${VOCECHAT_CONFIG_FILE}"

log_info "Starting VoceChat server with config ${VOCECHAT_CONFIG_FILE}"
cd "${APP_ROOT}"
cargo run -- "${VOCECHAT_CONFIG_FILE}"
