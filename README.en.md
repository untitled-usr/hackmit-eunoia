# hackmit-eunoia

A full-stack project focused on mental health support for teenagers, organized as a single repository with separate `front-end` and `back-end` directories for easier development, integration, and deployment.

Chinese version: `README.md`

## Project Overview

- Goal: provide a low-pressure, private, and sustainable emotional support experience.
- Core features: AI chat, drifting-bottle interaction, mood/diary journaling.
- Repository style: monorepo with frontend and backend side by side.

## Repository Structure

- `front-end/`: frontend app (React + TypeScript + Vite)
- `back-end/`: backend and middleware integration (mid-auth, Open WebUI, Memos, VoceChat, etc.)

Use this root README for navigation and the subdirectory READMEs for implementation details:

- Frontend docs: `front-end/README.md`
- Backend docs: `back-end/README.md`

## Architecture (Quick View)

- Browser accesses the `front-end`.
- Frontend talks to mid-auth (`back-end/services/mid-auth`) for authentication and BFF aggregation.
- mid-auth proxies/integrates Open WebUI, Memos, and VoceChat APIs.
- Runtime state and infra details follow backend documentation.

## Prerequisites

### General

- Linux/macOS development environment (Windows users are recommended to use WSL2).
- Git, Node.js, npm.
- Backend dependencies (Python/database/etc.) are documented in `back-end/README.md`.

### Clone

```bash
git clone <your-repo-url>
cd hackmit-eunoia
```

## Quick Start

### Start Frontend

```bash
cd front-end
npm install
npm run dev
```

Common frontend commands:

```bash
npm run build
npm run preview
```

### Start Backend

Backend includes multiple services. Follow backend docs step by step:

```bash
cd back-end
# follow Quick Start and Runbook in back-end/README.md
```

Backend docs include:

- dependency checks
- env template sync
- database bootstrap and migrations
- startup order for multiple services
- local domain and reverse proxy guidance

## Minimal Integration Flow (Recommended)

1. Start backend core services (follow `back-end/README.md`).
2. Start frontend dev server.
3. Point frontend API base URL to mid-auth, then verify login and core pages.

## Config and Docs Index

- Frontend env example: `front-end/.env.example`
- Backend env templates: `back-end/env/templates/`
- Backend scripts entry: `back-end/scripts/`
- Key backend docs:
  - `back-end/services/mid-auth/README.md`
  - `back-end/infra/nginx/README.md`

## FAQ

- Frontend runs but API fails:
  - Make sure mid-auth is running and reachable.
  - Check frontend API base URL env config.
- Session/cookie issues:
  - Check SameSite, Secure, and reverse proxy notes in backend README.
- Backend startup failures:
  - Start services in documented order instead of launching all at once.

## Collaboration Notes

- Before committing, ensure local startup and key flows work.
- Prefer separate commits for frontend and backend changes.
- Never commit secrets (`.env`, tokens, private keys, DB dumps, etc.).

## Licenses and Third-Party Notices

- Frontend notices: `front-end/THIRD_PARTY_LICENSES.md`
- Backend notices: `back-end/THIRD_PARTY_LICENSES.md`

If you plan commercial use or redistribution, review third-party license constraints carefully.
