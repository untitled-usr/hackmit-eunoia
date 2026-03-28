# VirtMate Agent 子页面整合说明

## 入口与页面结构

- Agent 主页面：`/agent`
- VirtMate 子页面：`/agent/virtmate`
- 入口行为：点击 Agent 输入区麦克风按钮后，页内跳转到 `/agent/virtmate?tab=voice`

## 功能范围

本次整合保留以下能力：

- 聊天（含 WebSocket 增量事件）
- 语音录音与识别
- Live2D 模型加载
- 用户设置（会话提示词、识别灵敏度、用户命名、语音引擎等）

本次整合不包含以下前端能力：

- MMD 场景
- VRM 场景

说明：后端相关接口即便存在，也不在本次前端交付范围内。

## API/WS 模式

客户端支持两种模式：

- `midauth`（默认）
  - HTTP 前缀：`/me/virtmate/*`
  - WS：`/me/virtmate/ws/events`
  - `fetch` 自动带 `credentials: include`
  - `chat/send` 不发送 `user-id` 头，依赖会话映射
- `direct`
  - HTTP 前缀：`/api/*`
  - WS：`/ws/events`
  - `chat/send` 发送 `user-id` 头

可用参数与环境变量：

- URL 参数：
  - `api_mode=midauth|direct`
  - `api_prefix=/custom/prefix`
  - `tab=chat|voice|live2d|settings`
- 环境变量：
  - `VITE_VIRTMATE_API_MODE`
  - `VITE_VIRTMATE_API_PREFIX`
  - `VITE_VIRTMATE_API_ORIGIN`
  - `VITE_VIRTMATE_ASSET_ORIGIN`
  - `VITE_VIRTMATE_APP_URL`

## Live2D 资源约束

- 当前仅加载 `hiyori_free_t08` 模型：
  - `assets/live2d_model/hiyori_free_t08/hiyori_free_t08.model3.json`
- 口型联动通过轮询 `scene/mouth_y`（按模式映射）更新参数 `ParamMouthOpenY`。
