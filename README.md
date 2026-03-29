# hackmit-eunoia

一个面向青少年心理健康支持场景的全栈项目，采用前后端分目录、统一仓库管理方式，便于协作开发、联调和部署。

English version: `README.en.md`

## 项目概览

- 目标：提供低压、私密、可持续的情绪支持体验。
- 主要能力：AI 对话、漂流瓶互动、情绪/日记记录等。
- 形态：单仓库（Monorepo）管理，前后端并列。

## 仓库结构

- `front-end/`：前端应用（React + TypeScript + Vite）
- `back-end/`：后端与中间层整合（mid-auth、Open WebUI、Memos、VoceChat 等）

建议从本 README 获取导航，从子目录 README 获取具体实现与运行细节：

- 前端说明：`front-end/README.md`
- 后端说明：`back-end/README.md`

## 架构关系（简版）

- 浏览器访问 `front-end`。
- 前端通过 mid-auth（位于 `back-end/services/mid-auth`）进行认证和 BFF 聚合。
- mid-auth 按能力转发或整合 Open WebUI / Memos / VoceChat。
- 业务数据与运行状态按后端文档约定存放。

## 环境准备

### 通用要求

- Linux/macOS 开发环境（Windows 建议使用 WSL2）。
- Git、Node.js、npm。
- 后端依赖（Python/数据库等）请以 `back-end/README.md` 为准。

### 克隆仓库

```bash
git clone https://github.com/untitled-usr/hackmit-eunoia.git
cd hackmit-eunoia
```

## 快速开始

### 前端开发启动

```bash
cd front-end
npm install
npm run dev
```

常用命令（前端）：

```bash
npm run build
npm run preview
```

### 后端开发启动

后端组件较多，推荐严格按后端文档顺序执行：

```bash
cd back-end
# 参考 back-end/README.md 的 Quick Start 与 Runbook
```

后端文档已包含：

- 依赖检查
- 环境文件模板同步
- 数据库初始化与迁移
- 多服务启动顺序
- 本地域名/反向代理建议

## 最小联调路径（推荐）

1. 先启动后端核心服务（以 `back-end/README.md` 为准）。
2. 再启动 `front-end` 开发服务器。
3. 前端配置指向 mid-auth 地址后，验证登录与核心页面链路。

## 配置与文档位置

- 前端环境示例：`front-end/.env.example`
- 后端环境模板：`back-end/env/templates/`
- 后端脚本入口：`back-end/scripts/`
- 关键后端服务文档：
  - `back-end/services/mid-auth/README.md`
  - `back-end/infra/nginx/README.md`

## 常见问题

- 前端能起但接口失败：
  - 先确认 mid-auth 已启动且可访问。
  - 再检查前端环境变量中的 API 基地址。
- 登录态异常（跨域/Cookie）：
  - 优先核对后端 README 中的 SameSite、Secure、反向代理配置说明。
- 后端服务依赖较多启动失败：
  - 按后端文档的顺序分步启动，不建议一次性并行全部服务。

## 开发协作建议

- 提交前先确保本地可启动、关键路径可用。
- 前后端变更尽量分开提交，便于回溯。
- 不要提交敏感信息（`.env`、token、私钥、数据库转储等）。

## 许可证与第三方声明

- 前端第三方声明：`front-end/THIRD_PARTY_LICENSES.md`
- 后端第三方声明：`back-end/THIRD_PARTY_LICENSES.md`

如需商用或二次分发，请先逐项核对第三方组件许可证约束。
