from __future__ import annotations

import os

# 在 uvicorn 加载 asr.api（进而 import ctranslate2）之前生效
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
os.environ.setdefault("CT2_CUDA_ALLOCATOR", "cub_caching")

import uvicorn


def main() -> None:
    port = int(os.getenv("VIRTMATE_ASR_API_PORT", "5264"))
    uvicorn.run("asr.api:app", host="0.0.0.0", port=port, reload=False)


if __name__ == "__main__":
    main()
