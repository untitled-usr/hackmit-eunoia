# hackmit-eunoia

该仓库采用前后端同级目录结构，便于统一管理与独立部署。

## 目录结构

- `front-end/`：Eunoia 前端（React + TypeScript + Vite）
- `back-end/`：后端与中间层（包含 mid-auth、Open WebUI、Memos、VoceChat 等整合内容）

## 快速开始

### 1) 前端

```bash
cd front-end
npm install
npm run dev
```

更多说明见：`front-end/README.md`

### 2) 后端

```bash
cd back-end
# 按 back-end/README.md 的步骤准备环境并启动
```

更多说明见：`back-end/README.md`

## 说明

- 仓库根目录仅做总体导航；详细运行、端口、环境变量与组件说明请分别查看子目录 README。
- 第三方许可证信息分别位于：
  - `front-end/THIRD_PARTY_LICENSES.md`
  - `back-end/THIRD_PARTY_LICENSES.md`
