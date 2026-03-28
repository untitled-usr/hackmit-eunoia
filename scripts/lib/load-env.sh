#!/usr/bin/env bash
set -euo pipefail

load_env_file() {
  local env_file="$1"
  if [[ ! -f "$env_file" ]]; then
    printf '[ERROR] Missing env file: %s\n' "$env_file" >&2
    return 1
  fi

  # shellcheck disable=SC1090
  set -a
  source "$env_file"
  set +a
}
