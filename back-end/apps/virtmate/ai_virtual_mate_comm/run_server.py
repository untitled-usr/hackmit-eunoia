from __future__ import annotations

import os

# 在 uvicorn 加载 server.app（进而 import ctranslate2）之前生效
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
os.environ.setdefault("CT2_CUDA_ALLOCATOR", "cub_caching")

from pathlib import Path

import uvicorn

from server.config import RuntimeConfig


def main() -> None:
    root = os.path.dirname(os.path.abspath(__file__))
    runtime = RuntimeConfig.load(Path(root))
    default_port = runtime.get_server_ports()["chatweb_port"]
    port = int(os.getenv("VIRTMATE_SERVER_PORT", default_port))
    uvicorn.run("server.app:app", host="0.0.0.0", port=port, reload=False)


if __name__ == "__main__":
    main()

