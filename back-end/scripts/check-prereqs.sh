#!/usr/bin/env bash
set -euo pipefail

missing=0

check_cmd() {
  local cmd="$1"
  local hint="$2"
  if command -v "$cmd" >/dev/null 2>&1; then
    printf '[OK]   %s\n' "$cmd"
  else
    printf '[MISS] %s (%s)\n' "$cmd" "$hint"
    missing=1
  fi
}

check_cmd "git" "required for source sync"
check_cmd "python3" "required for Open WebUI and mid-auth"
check_cmd "python3.11" "recommended for Open WebUI backend"
check_cmd "node" "required for Open WebUI/Memos/VoceChat frontends"
check_cmd "npm" "required for Open WebUI frontend"
check_cmd "pnpm" "required for Memos and VoceChat web"
check_cmd "go" "required for Memos backend"
check_cmd "cargo" "required for VoceChat backend"
check_cmd "nginx" "required for reverse proxy"

if command -v /snap/bin/go >/dev/null 2>&1; then
  printf '[OK]   /snap/bin/go\n'
else
  printf '[WARN] /snap/bin/go not found (Memos may need newer Go than apt)\n'
fi

if [[ -s "${HOME}/.nvm/nvm.sh" ]]; then
  # shellcheck disable=SC1090
  source "${HOME}/.nvm/nvm.sh"
  if nvm ls 24 >/dev/null 2>&1; then
    printf '[OK]   nvm node 24 installed\n'
  else
    printf '[WARN] nvm node 24 missing (Memos web recommends >=24)\n'
  fi
  if nvm ls 22 >/dev/null 2>&1; then
    printf '[OK]   nvm node 22 installed\n'
  else
    printf '[WARN] nvm node 22 missing (Open WebUI targets <=22)\n'
  fi
else
  printf '[WARN] nvm not found (mixed Node requirements may conflict)\n'
fi

if [[ "$missing" -ne 0 ]]; then
  printf '\nOne or more prerequisites are missing.\n'
  exit 1
fi

printf '\nAll prerequisites are installed.\n'
