#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

# 先启动独立 ASR API（后台），再启动 VirtMate 主服务（前台）。
bash ./start_asr_api.sh >/tmp/virtmate_asr_api.log 2>&1 &
exec bash ./start_cs.sh
