from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import threading
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, UploadFile

ROOT_DIR = Path(__file__).resolve().parents[1]
ASR_WORKER_SCRIPT = ROOT_DIR / "asr" / "worker.py"
CACHE_MEDIA_DIR = ROOT_DIR / "data" / "cache" / "asr_api_media"
CACHE_MEDIA_DIR.mkdir(parents=True, exist_ok=True)


class AsrWorkerClient:
    def __init__(self, root_dir: Path, worker_script: Path) -> None:
        self.root_dir = root_dir
        self.worker_script = worker_script
        self._lock = threading.Lock()
        self._proc: subprocess.Popen[str] | None = None

    def _start_locked(self) -> None:
        if self._proc is not None and self._proc.poll() is None:
            return
        self._proc = subprocess.Popen(
            [sys.executable, str(self.worker_script), "--serve", str(self.root_dir)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=dict(os.environ),
        )

    def _ask_locked(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._start_locked()
        if self._proc is None or self._proc.stdin is None or self._proc.stdout is None:
            return {"ok": False, "error": "asr worker unavailable"}
        try:
            self._proc.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
            self._proc.stdin.flush()
            line = self._proc.stdout.readline()
            if not line:
                stderr = ""
                if self._proc.stderr is not None:
                    try:
                        stderr = (self._proc.stderr.read() or "").strip()[:500]
                    except Exception:
                        stderr = ""
                return {"ok": False, "error": f"asr worker exited unexpectedly: {stderr}"}
            try:
                return json.loads(line.strip())
            except Exception:
                return {"ok": False, "error": f"asr worker invalid response: {line[:300]}"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def recognize(self, audio_path: Path) -> dict[str, Any]:
        req = {"action": "recognize", "audio_path": str(audio_path)}
        with self._lock:
            res = self._ask_locked(req)
            if res.get("ok") is True:
                return res
            self._proc = None
            return self._ask_locked(req)

    def status(self) -> dict[str, Any]:
        with self._lock:
            res = self._ask_locked({"action": "status"})
        if res.get("ok") is True and isinstance(res.get("status"), dict):
            return res["status"]
        return {"last_error": str(res.get("error") or "asr worker status unavailable")}

    def shutdown(self) -> None:
        with self._lock:
            if self._proc is None:
                return
            try:
                _ = self._ask_locked({"action": "shutdown"})
            except Exception:
                pass
            try:
                if self._proc.poll() is None:
                    self._proc.terminate()
                    self._proc.wait(timeout=2)
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass
            self._proc = None


asr_worker_client = AsrWorkerClient(ROOT_DIR, ASR_WORKER_SCRIPT)
app = FastAPI(title="VirtMate ASR API", version="1.0.0")


@app.on_event("startup")
async def startup_warmup_asr_worker() -> None:
    _ = await asyncio.to_thread(asr_worker_client.status)


@app.on_event("shutdown")
async def shutdown_asr_worker() -> None:
    await asyncio.to_thread(asr_worker_client.shutdown)


@app.get("/api/health")
async def health() -> dict[str, Any]:
    return {"ok": True}


@app.get("/api/asr/status")
async def asr_status() -> dict[str, Any]:
    return {"ok": True, "asr": await asyncio.to_thread(asr_worker_client.status)}


@app.post("/api/asr/recognize")
async def asr_recognize(audio: UploadFile = File(...)) -> dict[str, Any]:
    suffix = Path(audio.filename or "voice.wav").suffix or ".wav"
    filename = f"{uuid.uuid4().hex}{suffix}"
    path = CACHE_MEDIA_DIR / filename
    path.write_bytes(await audio.read())
    try:
        payload = await asyncio.to_thread(asr_worker_client.recognize, path)
        if payload.get("ok") is True:
            return {"ok": True, "text": str(payload.get("text") or "")}
        return {"ok": False, "error": str(payload.get("error") or "worker返回异常"), "text": ""}
    except Exception as e:
        return {"ok": False, "error": str(e), "text": ""}
    finally:
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass
