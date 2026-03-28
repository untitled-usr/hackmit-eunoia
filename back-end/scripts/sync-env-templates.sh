#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"

declare -A TARGETS=(
  ["open-webui.env.example"]="${DEVSTACK_STATE_ROOT}/open-webui/config/.env"
  ["memos.env.example"]="${DEVSTACK_STATE_ROOT}/memos/config/.env"
  ["vocechat.env.example"]="${DEVSTACK_STATE_ROOT}/vocechat/config/.env"
  ["mid-auth.env.example"]="${DEVSTACK_STATE_ROOT}/mid-auth/config/.env"
)

for tpl in "${!TARGETS[@]}"; do
  src="${DEVSTACK_TEMPLATES_ROOT}/${tpl}"
  dst="${TARGETS[$tpl]}"
  require_file "$src"
  require_dir "$(dirname "$dst")"

  if [[ -f "$dst" ]]; then
    log_warn "Keep existing env file: $dst"
    continue
  fi

  cp "$src" "$dst"
  chmod 600 "$dst"
  log_info "Created env file from template: $dst"
done

log_info "Env template sync completed."
