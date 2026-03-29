from __future__ import annotations

import asyncio
import json
import os
import requests
import subprocess
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, Header, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from server.context import AppContext
from server.models import (
    ChatSendRequest,
    GlobalConfigUpdateRequest,
    SessionSettingsUpdateRequest,
    TtsPlaybackStateRequest,
    TtsSynthesizeRequest,
)

try:
    import pynvml as nv
except Exception:  # pragma: no cover
    nv = None

try:
    import torch
except Exception:  # pragma: no cover
    torch = None

ROOT_DIR = Path(__file__).resolve().parents[1]
WEBAPP_DIR = ROOT_DIR / "webapp"
ASSETS_DIR = ROOT_DIR / "dist" / "assets"
DATA_IMAGE_DIR = ROOT_DIR / "data" / "image"
ASR_API_BASE_URL = (
    os.environ.get("VIRTMATE_ASR_API_BASE_URL", "http://127.0.0.1:5264").strip().rstrip("/")
)
ASR_API_TIMEOUT_SECONDS = float(os.environ.get("VIRTMATE_ASR_API_TIMEOUT_SECONDS", "120"))

ctx = AppContext(ROOT_DIR)
app = FastAPI(title="VirtMate C/S Server", version="1.0.0")


def _fetch_asr_status() -> dict[str, Any]:
    try:
        res = requests.get(
            f"{ASR_API_BASE_URL}/api/asr/status",
            timeout=ASR_API_TIMEOUT_SECONDS,
        )
        payload = res.json() if getattr(res, "content", b"") else {}
        status_code = int(getattr(res, "status_code", 0) or 0)
        ok = 200 <= status_code < 300
        if ok and isinstance(payload, dict) and isinstance(payload.get("asr"), dict):
            return payload["asr"]
        return {"last_error": f"ASR API HTTP {status_code}: {payload}"}
    except Exception as e:
        return {"last_error": f"ASR API unavailable: {e}"}

# allow_origins=["*"] 与 allow_credentials=True 不能同时用，否则浏览器会拦截跨域（界面常显示「访问被拒绝」）。
# 本服务鉴权不依赖 Cookie，跨域 API 用 session_id 等即可。
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_private_network=True,
)

app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")
# 兼容旧前端/脚本在 /scene/* 页面里的相对资源路径（会请求到 /scene/assets/*）
app.mount("/scene/assets", StaticFiles(directory=str(ASSETS_DIR)), name="scene-assets")
app.mount("/data/image", StaticFiles(directory=str(DATA_IMAGE_DIR)), name="data-image")
app.mount("/app", StaticFiles(directory=str(WEBAPP_DIR), html=True), name="spa")


@app.get("/")
async def index() -> RedirectResponse:
    return RedirectResponse(url="/app/")


@app.get("/api/health")
async def health() -> dict[str, Any]:
    return {"ok": True}


@app.get("/api/config/global")
async def config_global(mask_secrets: bool = False) -> dict[str, Any]:
    return ctx.runtime.get_global_view(mask_secrets=mask_secrets)


@app.post("/api/config/global")
async def update_config_global(req: GlobalConfigUpdateRequest) -> dict[str, Any]:
    body = req.model_dump(exclude_none=True)
    config_updates = {
        "ASR引擎": body.get("asr_engine"),
        "ASR模型": body.get("asr_model"),
        "ASR设备": body.get("asr_device"),
        "ASR计算精度": body.get("asr_compute_type"),
        "ASR_GPU序号": body.get("asr_cuda_device_index"),
        "ASR禁用自动回退": body.get("asr_disable_auto_fallback"),
        "语音识别灵敏度": body.get("asr_sensitivity"),
        "声纹识别": body.get("asr_voiceprint_switch"),
    }
    more_set_updates = {
        "声纹识别阈值": body.get("asr_voiceprint_threshold"),
        "本地TTS服务器IP": body.get("tts_local_host"),
        "GPT-SoVITS端口": body.get("tts_gpt_sovits_port"),
        "CosyVoice端口": body.get("tts_cosyvoice_port"),
        "Index-TTS端口": body.get("tts_indextts_port"),
        "VoxCPM端口": body.get("tts_voxcpm_port"),
        "本地TTS超时时间秒": body.get("tts_local_timeout_sec"),
        "本地TTS失败回退引擎": body.get("tts_fallback_engine"),
    }
    preference_updates = {
        "语音合成引擎": body.get("tts_default_engine"),
    }
    config_updates = {k: v for k, v in config_updates.items() if v is not None}
    more_set_updates = {k: v for k, v in more_set_updates.items() if v is not None}
    preference_updates = {k: v for k, v in preference_updates.items() if v is not None}
    res = ctx.runtime.update_global(
        config_updates=config_updates,
        more_set_updates=more_set_updates,
        preference_updates=preference_updates,
    )
    return {"ok": True, "global": res}


@app.get("/api/runtime/hardware")
async def runtime_hardware() -> dict[str, Any]:
    gpu: dict[str, Any] = {"cuda_available": False, "name": "", "vram_total_mb": 0}
    if torch is not None:
        try:
            if torch.cuda.is_available():
                gpu["cuda_available"] = True
                gpu["name"] = torch.cuda.get_device_name(0)
        except Exception:
            pass
    if nv is not None:
        try:
            nv.nvmlInit()
            handle = nv.nvmlDeviceGetHandleByIndex(0)
            mem = nv.nvmlDeviceGetMemoryInfo(handle)
            name = nv.nvmlDeviceGetName(handle)
            if isinstance(name, bytes):
                name = name.decode("utf-8", errors="ignore")
            gpu["name"] = gpu["name"] or str(name)
            gpu["vram_total_mb"] = int(mem.total // (1024 * 1024))
            gpu["cuda_available"] = True
        except Exception:
            pass
    if not gpu["cuda_available"]:
        try:
            out = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=3,
            ).strip()
            if out:
                first = out.splitlines()[0]
                parts = [x.strip() for x in first.split(",")]
                gpu["name"] = parts[0] if parts else ""
                if len(parts) > 1 and parts[1].isdigit():
                    gpu["vram_total_mb"] = int(parts[1])
                gpu["cuda_available"] = True
        except Exception:
            pass
    return {
        "gpu": gpu,
        "asr": await asyncio.to_thread(_fetch_asr_status),
        "tts": ctx.tts.get_runtime_status(),
        "global": ctx.runtime.get_global_view(mask_secrets=True),
    }


@app.get("/api/session/settings")
async def session_settings(session_id: str = "default") -> dict[str, Any]:
    return ctx.chat.get_session_settings(session_id)


@app.post("/api/session/settings")
async def update_session_settings(req: SessionSettingsUpdateRequest) -> dict[str, Any]:
    updates = req.model_dump(exclude={"session_id"}, exclude_none=True)
    settings = ctx.chat.update_session_settings(req.session_id, updates)
    await ctx.events.publish(
        req.session_id,
        {"type": "session.settings", "session_id": req.session_id, "data": {"settings": settings}},
    )
    return settings


@app.post("/api/chat/send")
async def chat_send(
    req: ChatSendRequest,
    user_id: str | None = Header(default=None, alias="user-id"),
) -> dict[str, Any]:
    uid = (user_id or "").strip()
    if not uid:
        return JSONResponse(
            status_code=400,
            content={"ok": False, "error": "missing user-id header"},
        )
    model = (req.model or "").strip()
    if not model:
        return JSONResponse(
            status_code=400,
            content={
                "ok": False,
                "error": "model is required (set body.model)",
            },
        )

    user_record = ctx.store.append_message(req.session_id, "user", req.text)
    await ctx.events.publish(
        req.session_id,
        {"type": "chat.message", "session_id": req.session_id, "data": {"message": user_record}},
    )
    await ctx.events.publish(
        req.session_id,
        {"type": "chat.status", "session_id": req.session_id, "data": {"status": "thinking"}},
    )

    settings = ctx.chat.get_session_settings(req.session_id)
    loop = asyncio.get_running_loop()

    def on_delta(_chunk: str, full_text: str) -> None:
        loop.call_soon_threadsafe(
            asyncio.create_task,
            ctx.events.publish(
                req.session_id,
                {
                    "type": "chat.delta",
                    "session_id": req.session_id,
                    "data": {"delta": _chunk, "content": full_text},
                },
            ),
        )

    try:
        answer, conv_id = await ctx.chat.chat_via_openwebui(
            user_id=uid,
            session_id=req.session_id,
            user_text=req.text,
            model=model,
            conversation_id=(req.conversation_id or "").strip() or None,
            settings=settings,
            stream=bool(req.stream),
            on_delta=on_delta if req.stream else None,
        )
    except Exception as e:
        await ctx.events.publish(
            req.session_id,
            {"type": "chat.error", "session_id": req.session_id, "data": {"error": str(e)}},
        )
        await ctx.events.publish(
            req.session_id,
            {"type": "chat.status", "session_id": req.session_id, "data": {"status": "error"}},
        )
        return JSONResponse(status_code=502, content={"ok": False, "error": str(e)})

    bot_record = ctx.store.append_message(req.session_id, "assistant", answer)
    await ctx.events.publish(
        req.session_id,
        {"type": "chat.message", "session_id": req.session_id, "data": {"message": bot_record}},
    )
    if req.with_tts and settings.get("tts_engine") != "关闭语音合成":
        tts_res = await ctx.tts.synthesize(answer, tts_engine=settings.get("tts_engine"))
        await ctx.events.publish(
            req.session_id,
            {"type": "tts.ready", "session_id": req.session_id, "data": tts_res},
        )
    await ctx.events.publish(
        req.session_id,
        {"type": "chat.status", "session_id": req.session_id, "data": {"status": "done"}},
    )

    return {
        "ok": True,
        "conversation_id": conv_id,
        "message": user_record,
        "assistant": bot_record,
    }


@app.websocket("/ws/events")
async def ws_events(ws: WebSocket, session_id: str = "default") -> None:
    await ctx.events.connect(session_id, ws)
    try:
        await ws.send_json({"type": "session.connected", "session_id": session_id, "data": {"ok": True}})
        while True:
            # 保持连接存活，也允许客户端主动上报事件
            _ = await ws.receive_text()
    except WebSocketDisconnect:
        await ctx.events.disconnect(session_id, ws)
    except Exception:
        await ctx.events.disconnect(session_id, ws)


@app.post("/api/asr/recognize")
async def asr_recognize(
    audio: UploadFile = File(...),
    session_id: str = Form("default"),
) -> dict[str, Any]:
    try:
        raw = await audio.read()
        filename = audio.filename or "voice.wav"
        ctype = audio.content_type or "application/octet-stream"

        def _call_asr_api() -> dict[str, Any]:
            res = requests.post(
                f"{ASR_API_BASE_URL}/api/asr/recognize",
                files={"audio": (filename, raw, ctype)},
                timeout=ASR_API_TIMEOUT_SECONDS,
            )
            payload = res.json() if getattr(res, "content", b"") else {}
            status_code = int(getattr(res, "status_code", 0) or 0)
            ok = 200 <= status_code < 300
            if not isinstance(payload, dict):
                return {"ok": False, "error": f"invalid ASR API response: {payload}"}
            if not ok:
                return {"ok": False, "error": f"ASR API HTTP {status_code}: {payload}"}
            return payload

        payload = await asyncio.to_thread(_call_asr_api)
        if payload.get("ok") is True:
            text = str(payload.get("text") or "")
        else:
            text = f"ASR识别失败（{payload.get('error') or 'ASR API返回异常'}）"
    except Exception as e:
        text = f"ASR识别失败（{e}）"
    await ctx.events.publish(
        session_id,
        {"type": "asr.result", "session_id": session_id, "data": {"text": text}},
    )
    return {"text": text}


@app.post("/api/tts/synthesize")
async def tts_synthesize(req: TtsSynthesizeRequest) -> dict[str, Any]:
    res = await ctx.tts.synthesize(req.text, req.tts_engine)
    await ctx.events.publish(req.session_id, {"type": "tts.ready", "session_id": req.session_id, "data": res})
    return res


@app.post("/api/tts/playback")
async def tts_playback(req: TtsPlaybackStateRequest) -> dict[str, Any]:
    state = ctx.store.get_state(req.session_id)
    state["is_playing"] = req.is_playing
    if req.mouth_y is not None:
        try:
            y = float(req.mouth_y)
        except Exception:
            y = 0.0
        state["mouth_y"] = max(0.0, min(1.0, y))
        state["mouth_updated_ts"] = time.time()
    elif not req.is_playing:
        state["mouth_y"] = 0.0
        state["mouth_updated_ts"] = time.time()
    ctx.store.upsert_state(req.session_id, state)
    await ctx.events.publish(
        req.session_id,
        {
            "type": "tts.playback",
            "session_id": req.session_id,
            "data": {"is_playing": req.is_playing, "mouth_y": state.get("mouth_y")},
        },
    )
    return {"ok": True}


@app.get("/api/audio/{filename}")
async def get_audio(filename: str) -> FileResponse:
    path = ctx.tts.audio_dir / filename
    return FileResponse(path)


def _resolve_mouth_y_for_scene(session_id: str | None) -> float:
    now = time.time()
    freshness_sec = 1.2

    def _pick_y(state: dict[str, Any]) -> float:
        if not bool(state.get("is_playing", False)):
            return 0.0
        ts = state.get("mouth_updated_ts")
        try:
            tsf = float(ts)
        except Exception:
            return 0.0
        if now - tsf > freshness_sec:
            return 0.0
        y = state.get("mouth_y")
        try:
            yf = float(y)
        except Exception:
            return 0.0
        return max(0.0, min(1.0, yf))

    sid = (session_id or "").strip()
    if sid:
        state = ctx.store.get_state(sid)
        y = _pick_y(state)
        if y > 0:
            return y
    # 兼容旧版 live2d 脚本未携带 session_id 的情况：回退到所有会话中的最大口型值。
    return max((_pick_y(s) for s in ctx.store.list_states()), default=0.0)


@app.get("/api/scene/mouth_y")
async def scene_mouth_y(session_id: str | None = None) -> dict[str, float]:
    return {"y": _resolve_mouth_y_for_scene(session_id)}


@app.get("/api/get_mouth_y")
async def get_mouth_y_legacy(session_id: str | None = None) -> dict[str, float]:
    # 兼容旧版前端静态资源仍请求 /api/get_mouth_y
    return await scene_mouth_y(session_id=session_id)


@app.get("/scene/live2d", response_class=HTMLResponse)
async def scene_live2d() -> str:
    return """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <link rel="icon" type="image/png" href="/assets/image/logo.png" />
  <title>Live2D角色 - VirtMate C/S</title>
  <style>
    body { margin:0; background-image:url('/assets/image/bg.jpg'); background-size:cover; overflow:hidden; }
    #canvas2 { width:60%; height:auto; margin:50px auto; display:block; }
  </style>
  <script src="/assets/live2d_core/live2dcubismcore.min.js"></script>
  <script src="/assets/live2d_core/live2d.min.js"></script>
  <script src="/assets/live2d_core/pixi.min.js"></script>
  <script type="module" crossorigin src="/assets/live2d.js"></script>
</head>
<body>
  <div id="app"></div>
  <canvas id="canvas2"></canvas>
</body>
</html>
"""


@app.get("/scene/mmd", response_class=HTMLResponse)
async def scene_mmd() -> str:
    return """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <link rel="icon" type="image/png" href="/assets/image/logo.png"/>
  <title>MMD 3D角色 - VirtMate C/S</title>
  <style>
    body { margin:0; background-image:url('/assets/image/bg.jpg'); background-size:cover; }
    canvas { display:block; }
  </style>
</head>
<body>
  <script src="/assets/mmd_core/ammo.js"></script>
  <script src="/assets/mmd_core/mmdparser.min.js"></script>
  <script src="/assets/mmd_core/three.min.js"></script>
  <script src="/assets/mmd_core/CCDIKSolver.js"></script>
  <script src="/assets/mmd_core/MMDPhysics.js"></script>
  <script src="/assets/mmd_core/TGALoader.js"></script>
  <script src="/assets/mmd_core/MMDLoader.js"></script>
  <script src="/assets/mmd_core/OrbitControls.js"></script>
  <script src="/assets/mmd_core/MMDAnimationHelper.js"></script>
  <script src="/assets/mmd.js"></script>
</body>
</html>
"""


@app.get("/scene/mmd/vmd", response_class=HTMLResponse)
async def scene_mmd_vmd() -> str:
    return """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <link rel="icon" type="image/png" href="/assets/image/logo.png"/>
  <title>MMD 3D动作 - VirtMate C/S</title>
  <style>
    body { margin:0; background-image:url('/assets/image/bg.jpg'); background-size:cover; }
    canvas { display:block; }
  </style>
</head>
<body>
  <script src="/assets/mmd_core/ammo.js"></script>
  <script src="/assets/mmd_core/mmdparser.min.js"></script>
  <script src="/assets/mmd_core/three.min.js"></script>
  <script src="/assets/mmd_core/CCDIKSolver.js"></script>
  <script src="/assets/mmd_core/MMDPhysics.js"></script>
  <script src="/assets/mmd_core/TGALoader.js"></script>
  <script src="/assets/mmd_core/MMDLoader.js"></script>
  <script src="/assets/mmd_core/OrbitControls.js"></script>
  <script src="/assets/mmd_core/MMDAnimationHelper.js"></script>
  <script src="/assets/mmd_vmd.js"></script>
</body>
</html>
"""


@app.get("/scene/vrm", response_class=HTMLResponse)
async def scene_vrm(session_id: str = "default") -> str:
    model_name_path = ROOT_DIR / "data" / "db" / "vrm_model_name.db"
    model_name = model_name_path.read_text(encoding="utf-8").strip() if model_name_path.exists() else "小月.vrm"
    return f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1.0">
  <link rel="icon" type="image/png" href="/assets/image/logo.png"/>
  <title>VRM 3D角色 - VirtMate C/S</title>
  <style>
    body {{ margin:0; overflow:hidden; background-image:url('/assets/image/bg.jpg'); background-size:cover; }}
    canvas {{ display:block; }}
  </style>
</head>
<body>
  <script type="importmap">
  {{
    "imports": {{
      "three": "/assets/vrm_core/three.module.js",
      "three/addons/": "/assets/vrm_core/jsm/",
      "@pixiv/three-vrm": "/assets/vrm_core/three-vrm.module.min.js"
    }}
  }}
  </script>
  <script type="module">
    import * as THREE from 'three';
    import {{ GLTFLoader }} from 'three/addons/loaders/GLTFLoader.js';
    import {{ OrbitControls }} from 'three/addons/controls/OrbitControls.js';
    import {{ VRMLoaderPlugin, VRMUtils }} from '@pixiv/three-vrm';

    const renderer = new THREE.WebGLRenderer({{ antialias:true, alpha:true }});
    renderer.setSize(window.innerWidth, window.innerHeight);
    document.body.appendChild(renderer.domElement);
    const camera = new THREE.PerspectiveCamera(30.0, window.innerWidth / window.innerHeight, 0.1, 20.0);
    camera.position.set(0.0, 1.0, 5.0);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.target.set(0.0, 1.0, 0.0);
    controls.update();
    const scene = new THREE.Scene();
    scene.background = null;
    const light = new THREE.DirectionalLight(0xffffff, Math.PI);
    light.position.set(1.0, 1.0, 1.0).normalize();
    scene.add(light);

    let currentVrm = null;
    const loader = new GLTFLoader();
    loader.register((parser) => new VRMLoaderPlugin(parser));
    loader.load('/assets/vrm_model/{model_name}', (gltf) => {{
      const vrm = gltf.userData.vrm;
      VRMUtils.removeUnnecessaryVertices(gltf.scene);
      VRMUtils.combineSkeletons(gltf.scene);
      scene.add(vrm.scene);
      currentVrm = vrm;
    }});

    async function checkSpeaking() {{
      if (!currentVrm || !currentVrm.expressionManager) return;
      try {{
        const res = await fetch('/api/scene/mouth_y?session_id={session_id}');
        const data = await res.json();
        const y = data.y || 0;
        currentVrm.expressionManager.setValue('aa', y * 0.6);
      }} catch (_e) {{}}
    }}
    setInterval(checkSpeaking, 200);

    const clock = new THREE.Clock();
    function animate() {{
      requestAnimationFrame(animate);
      const dt = clock.getDelta();
      if (currentVrm) currentVrm.update(dt);
      controls.update();
      renderer.render(scene, camera);
    }}
    animate();
    window.addEventListener('resize', () => {{
      camera.aspect = window.innerWidth / window.innerHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(window.innerWidth, window.innerHeight);
    }});
  </script>
</body>
</html>
"""

