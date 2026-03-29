#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

# 本机 nvidia-smi：GPU 2 = RTX 4080 SUPER，ASR 固定使用该卡（优先于网页里的「ASR GPU序号」）。
export CUDA_DEVICE_ORDER=PCI_BUS_ID
export VIRTMATE_ASR_CUDA_DEVICE=2
export VIRTMATE_ASR_ISOLATE_GPU=1
export VIRTMATE_ASR_API_BASE_URL="${VIRTMATE_ASR_API_BASE_URL:-http://127.0.0.1:5264}"
export OPENWEBUI_BASE_URL="${OPENWEBUI_BASE_URL:-http://127.0.0.1:7920}"
export OPENWEBUI_USER_ID_HEADER="${OPENWEBUI_USER_ID_HEADER:-X-Acting-Uid}"
# 兼容某些环境下缺少系统级 CUDA 运行时库（如 libcublas.so.12），
# 优先从已安装的 Python nvidia 包补齐动态库搜索路径。
if [ -d "/opt/soulchat2/.venv/lib/python3.10/site-packages/nvidia" ]; then
  for d in /opt/soulchat2/.venv/lib/python3.10/site-packages/nvidia/*/lib; do
    [ -d "$d" ] || continue
    case ":${LD_LIBRARY_PATH-}:" in
      *":$d:"*) ;;
      *) LD_LIBRARY_PATH="$d${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" ;;
    esac
  done
  export LD_LIBRARY_PATH
fi

# 若需整进程只看见一张卡，可改用（序号按本机 nvidia-smi -L 调整）：
# export CUDA_VISIBLE_DEVICES=2

exec python3 run_server.py
