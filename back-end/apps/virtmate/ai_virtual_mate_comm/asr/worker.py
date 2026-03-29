from __future__ import annotations

import ctypes
import glob
import json
import os
import site
import sys
import tempfile
import wave
from pathlib import Path

ROOT_PARENT = Path(__file__).resolve().parents[1]
if str(ROOT_PARENT) not in sys.path:
    sys.path.insert(0, str(ROOT_PARENT))

from server.config import RuntimeConfig


def _parse_gpu_index(runtime: RuntimeConfig) -> int:
    env_idx = (os.environ.get("VIRTMATE_ASR_CUDA_DEVICE") or "").strip()
    if env_idx.isdigit():
        return max(0, int(env_idx))
    cfg_idx = str(runtime.config.get("ASR_GPU序号", "0")).strip()
    if cfg_idx.isdigit():
        return max(0, int(cfg_idx))
    return 0


def _can_load_shared_lib(name: str) -> bool:
    try:
        ctypes.CDLL(name)
        return True
    except Exception:
        return False


def _discover_nvidia_lib_dirs() -> list[str]:
    # 常见位置：当前 Python site-packages + 已存在的业务 venv。
    candidate_roots: list[Path] = []
    try:
        for p in site.getsitepackages():
            candidate_roots.append(Path(p) / "nvidia")
    except Exception:
        pass
    try:
        candidate_roots.append(Path(site.getusersitepackages()) / "nvidia")
    except Exception:
        pass
    candidate_roots.extend(
        [
            Path("/opt/soulchat2/.venv/lib/python3.10/site-packages/nvidia"),
            Path("/usr/local/lib/python3.10/dist-packages/nvidia"),
        ]
    )

    found: list[str] = []
    seen: set[str] = set()
    needed = {"libcublas.so.12", "libcudart.so.12", "libcudnn.so.9"}
    for root in candidate_roots:
        if not root.is_dir():
            continue
        for libdir in glob.glob(str(root / "*" / "lib")):
            try:
                names = {p.name for p in Path(libdir).glob("*.so*")}
            except Exception:
                continue
            if not (names & needed):
                continue
            if libdir in seen:
                continue
            seen.add(libdir)
            found.append(libdir)
    return found


def _ensure_cuda_ld_library_path() -> None:
    # 针对 "Library libcublas.so.12 is not found or cannot be loaded"
    # 在 worker 进程内补齐运行时搜索路径，避免依赖系统全局 ldconfig。
    if _can_load_shared_lib("libcublas.so.12"):
        return
    lib_dirs = _discover_nvidia_lib_dirs()
    if not lib_dirs:
        return
    current = [p for p in (os.environ.get("LD_LIBRARY_PATH") or "").split(":") if p]
    merged: list[str] = []
    seen: set[str] = set()
    for p in [*lib_dirs, *current]:
        if p and p not in seen:
            seen.add(p)
            merged.append(p)
    os.environ["LD_LIBRARY_PATH"] = ":".join(merged)


def _setup_cuda_env_for_asr(runtime: RuntimeConfig) -> None:
    engine = str(runtime.config.get("ASR引擎", "")).strip()
    device = str(runtime.config.get("ASR设备", "")).strip()
    if engine != "faster_whisper_cuda" or device != "cuda":
        return
    # 统一为 nvidia-smi 的物理序号语义，避免 CUDA 默认“按性能排序”导致选错卡。
    os.environ["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"
    # 默认隔离到单卡，避免 ASR 误占其他 GPU 业务（例如 vLLM）所在显卡。
    isolate = (os.environ.get("VIRTMATE_ASR_ISOLATE_GPU") or "1").strip() != "0"
    gpu_idx = _parse_gpu_index(runtime)
    if isolate:
        os.environ["CUDA_VISIBLE_DEVICES"] = str(gpu_idx)
        os.environ["VIRTMATE_ASR_CUDA_DEVICE"] = "0"
        os.environ["VIRTMATE_ASR_CUDA_DEVICE_PHYSICAL"] = str(gpu_idx)
    _ensure_cuda_ld_library_path()


def _warmup_once(asr: "AsrService") -> None:
    enabled = (os.environ.get("VIRTMATE_ASR_WARMUP") or "1").strip() != "0"
    if not enabled:
        return
    warmup_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(prefix="asr_warmup_", suffix=".wav", delete=False) as f:
            warmup_path = Path(f.name)
        with wave.open(str(warmup_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            # 0.4s 的静音 PCM：足够触发模型初始化，不影响业务语义。
            wf.writeframes(b"\x00\x00" * int(16000 * 0.4))
        _ = asr.recognize_file(warmup_path)
    except Exception:
        pass
    finally:
        try:
            if warmup_path is not None:
                warmup_path.unlink(missing_ok=True)
        except Exception:
            pass


def _run_single(root_dir: Path, audio_path: Path) -> int:
    try:
        runtime = RuntimeConfig.load(root_dir)
        _setup_cuda_env_for_asr(runtime)
        from asr.service import AsrService

        asr = AsrService(runtime)
        text = asr.recognize_file(audio_path)
        print(json.dumps({"ok": True, "text": text}, ensure_ascii=False))
        return 0
    except Exception as e:  # pragma: no cover
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
        return 1


def _run_server(root_dir: Path) -> int:
    runtime = RuntimeConfig.load(root_dir)
    _setup_cuda_env_for_asr(runtime)
    from asr.service import AsrService

    asr = AsrService(runtime)
    _warmup_once(asr)

    for raw in sys.stdin:
        line = (raw or "").strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception:
            print(json.dumps({"ok": False, "error": "invalid json"}, ensure_ascii=False), flush=True)
            continue
        action = str(req.get("action") or "recognize")
        if action == "shutdown":
            print(json.dumps({"ok": True, "bye": True}, ensure_ascii=False), flush=True)
            return 0
        try:
            runtime.refresh()
            if action == "status":
                print(json.dumps({"ok": True, "status": asr.get_runtime_status()}, ensure_ascii=False), flush=True)
                continue
            if action != "recognize":
                print(json.dumps({"ok": False, "error": f"unsupported action: {action}"}, ensure_ascii=False), flush=True)
                continue
            audio_path = Path(str(req.get("audio_path") or "")).resolve()
            if not audio_path.exists():
                print(json.dumps({"ok": False, "error": "audio file not found"}, ensure_ascii=False), flush=True)
                continue
            text = asr.recognize_file(audio_path)
            print(json.dumps({"ok": True, "text": text}, ensure_ascii=False), flush=True)
        except Exception as e:
            print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False), flush=True)
    return 0


def main() -> int:
    if len(sys.argv) >= 3 and sys.argv[1] == "--serve":
        root_dir = Path(sys.argv[2]).resolve()
        return _run_server(root_dir)
    if len(sys.argv) < 3:
        print(json.dumps({"ok": False, "error": "usage: worker.py <root_dir> <audio_path>"}))
        print(json.dumps({"ok": False, "error": "or: worker.py --serve <root_dir>"}))
        return 2
    root_dir = Path(sys.argv[1]).resolve()
    audio_path = Path(sys.argv[2]).resolve()
    return _run_single(root_dir, audio_path)


if __name__ == "__main__":
    raise SystemExit(main())
