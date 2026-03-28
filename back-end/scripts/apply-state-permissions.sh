#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"

require_dir "${DEVSTACK_STATE_ROOT}"

chmod 750 /srv/devstack /srv/devstack/state

for app in open-webui memos vocechat mid-auth; do
  require_dir "${DEVSTACK_STATE_ROOT}/${app}"
  chmod 750 "${DEVSTACK_STATE_ROOT}/${app}"
  chmod 750 "${DEVSTACK_STATE_ROOT}/${app}/data" "${DEVSTACK_STATE_ROOT}/${app}/logs" "${DEVSTACK_STATE_ROOT}/${app}/run"
  chmod 700 "${DEVSTACK_STATE_ROOT}/${app}/config"
done

chmod 750 "${DEVSTACK_STATE_ROOT}/shared" "${DEVSTACK_STATE_ROOT}/shared/certs" "${DEVSTACK_STATE_ROOT}/shared/backups"

for env_file in \
  "${DEVSTACK_STATE_ROOT}/open-webui/config/.env" \
  "${DEVSTACK_STATE_ROOT}/memos/config/.env" \
  "${DEVSTACK_STATE_ROOT}/vocechat/config/.env" \
  "${DEVSTACK_STATE_ROOT}/mid-auth/config/.env"; do
  if [[ -f "${env_file}" ]]; then
    chmod 600 "${env_file}"
  fi
done

log_info "State permissions applied successfully."
