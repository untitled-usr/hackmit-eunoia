#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"
# shellcheck source=./lib/load-env.sh
source "${SCRIPT_DIR}/lib/load-env.sh"

APP_ROOT="${DEVSTACK_APPS_ROOT}/open-webui"
BACKEND_DIR="${APP_ROOT}/backend"
ENV_FILE="${DEVSTACK_STATE_ROOT}/open-webui/config/.env"

require_dir "${APP_ROOT}"
require_dir "${BACKEND_DIR}"
require_file "${BACKEND_DIR}/dev.sh"
load_env_file "${ENV_FILE}"

export PORT="${PORT:-7920}"
# 默认值含分号，不能写在 ${VAR:-...} 里（否则分号会被当成命令分隔符）
if [[ -z "${CORS_ALLOW_ORIGIN:-}" ]]; then
  export CORS_ALLOW_ORIGIN='http://localhost:7923;http://127.0.0.1:7923;http://owui.dev.local'
fi

append_origin() {
  local origin="$1"
  [[ -n "${origin}" ]] || return 0
  case ";${CORS_ALLOW_ORIGIN};" in
    *";${origin};"*) ;;
    *) CORS_ALLOW_ORIGIN="${CORS_ALLOW_ORIGIN};${origin}" ;;
  esac
}

# Allow LAN-origin frontend access in dev (common when visiting via host IP).
for ip in $(hostname -I 2>/dev/null || true); do
  [[ "${ip}" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]] || continue
  append_origin "http://${ip}"
  append_origin "http://${ip}:7920"
  append_origin "http://${ip}:7923"
done
export CORS_ALLOW_ORIGIN

export FORWARDED_ALLOW_IPS="${FORWARDED_ALLOW_IPS:-127.0.0.1}"

log_info "Starting Open WebUI backend on port ${PORT}"
cd "${BACKEND_DIR}"
bash dev.sh
