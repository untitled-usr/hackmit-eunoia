#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

# 本机 nvidia-smi：GPU 2 = RTX 4080 SUPER，ASR 固定使用该卡（优先于网页里的「ASR GPU序号」）。
export CUDA_DEVICE_ORDER=PCI_BUS_ID
export VIRTMATE_ASR_CUDA_DEVICE=2
export VIRTMATE_ASR_ISOLATE_GPU=1

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

exec python3 run_asr_server.py
