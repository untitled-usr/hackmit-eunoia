# DevStack Workspace (No Docker)

This workspace runs `Open WebUI`, `Memos`, and `VoceChat` from source code without Docker.

## Layout

- `apps/open-webui`: Open WebUI source
- `apps/memos`: Memos source
- `apps/vocechat-server`: VoceChat server source
- `apps/vocechat-web`: VoceChat web source
- `services/mid-auth`: reserved FastAPI middle layer
- `infra/nginx`: reverse proxy config
- `infra/systemd-user`: user-level service units
- `env/templates`: versioned env templates (`*.example`)
- `scripts`: start scripts and bootstrap helpers

Runtime state lives outside this workspace:

- `/srv/devstack/state/open-webui/{data,config,logs,run}`
- `/srv/devstack/state/memos/{data,config,logs,run}`
- `/srv/devstack/state/vocechat/{data,config,logs,run}`
- `/srv/devstack/state/mid-auth/{data,config,logs,run}`
- `/srv/devstack/state/shared/{certs,backups}`

## License Notice

This workspace integrates multiple upstream components (VoceChat, Memos, Open WebUI, and
AI Virtual Mate Community Edition). See `THIRD_PARTY_LICENSES.md` for a consolidated
third-party license notice and upstream references.

## Quick Start

1. Check host prerequisites:
   - `scripts/check-prereqs.sh`
2. Copy and adjust env files:
   - `scripts/sync-env-templates.sh`
3. Apply strict state permissions:
   - `scripts/apply-state-permissions.sh`
4. Install dependencies inside each app repo.
5. Initialize the mid-auth database (PostgreSQL + Alembic), after `sync-env-templates.sh` and editing `mid-auth` env:
   - `scripts/bootstrap-mid-auth-db.sh`
6. Start services independently:
   - `scripts/run-open-webui-backend.sh`
   - `scripts/run-open-webui-frontend.sh`
   - `scripts/run-memos-backend.sh`
   - `scripts/run-memos-frontend.sh`
   - `scripts/run-vocechat-backend.sh`
   - `scripts/run-vocechat-frontend.sh`
   - `scripts/run-mid-auth.sh`

## Port Plan

固定占用 **7920–7925**：**先三个后端，再三个前端**（产品顺序均为 Open WebUI → Memos → VoceChat）。

- 后端：Open WebUI `7920`，Memos `7921`，VoceChat `7922`
- 前端：Open WebUI `7923`，Memos `7924`，VoceChat `7925`

Mid Auth（FastAPI）仍为 `19000`（未纳入上述连续段）。

## Nginx Local Domains

See `infra/nginx/devstack.conf`:

- `owui.dev.local`
- `memos.dev.local`
- `chat.dev.local`
- `api.dev.local` → reverse proxy to mid-auth on `127.0.0.1:19000`

Add host entries (example): `127.0.0.1 owui.dev.local memos.dev.local chat.dev.local api.dev.local`, then point your local Nginx at `infra/nginx/devstack.conf` (or include its `server` blocks) and reload Nginx.

## Mid-Auth full-stack runbook

### Database and migrations

- Ensure `scripts/sync-env-templates.sh` has created `/srv/devstack/state/mid-auth/config/.env` and that `MID_AUTH_DATABASE_URL` matches your PostgreSQL instance.
- Run `scripts/bootstrap-mid-auth-db.sh`: on PostgreSQL it creates the application database if missing, installs the service venv when needed, runs `alembic upgrade head`, and probes `SELECT 1`. For SQLite URLs it skips `CREATE DATABASE` and only runs Alembic.
- Template reference: `env/templates/mid-auth.env.example`. Deeper API notes: `services/mid-auth/README.md`.

### Environment essentials

- Set `MID_AUTH_PROVISION_USE_STUB=false` (or omit; default is false) so registration provisions real shadow users in Open WebUI, VoceChat, and Memos.
- Point `MID_AUTH_OPEN_WEBUI_BASE_URL`, `MID_AUTH_MEMOS_BASE_URL`, and `MID_AUTH_VOCECHAT_BASE_URL` at the backends in the [Port Plan](#port-plan) (VoceChat uses the `/api` suffix as in the template).
- Admin BFF routes need `MID_AUTH_OPEN_WEBUI_ADMIN_ACTING_UID`, `MID_AUTH_VOCECHAT_ADMIN_ACTING_UID`, and `MID_AUTH_MEMOS_ADMIN_ACTING_UID` aligned with each downstream’s acting/admin identity; without them the corresponding `/admin/...` handlers respond with **503**.

### Recommended startup order

1. PostgreSQL reachable.
2. `scripts/bootstrap-mid-auth-db.sh`
3. Backends: Open WebUI → Memos → VoceChat (may be started in parallel once healthy; registration rolls back partial downstream work on failure).
4. `scripts/run-mid-auth.sh` on port `19000`.
5. Optional HTTP smoke (register → login → sample BFF): `BASE_URL=http://127.0.0.1:19000 scripts/e2e-mid-auth-curl.sh` (see `services/mid-auth/README.md` **Curl E2E**).

### `api.dev.local` and session cookies

- With Nginx, callers can use `http://api.dev.local` as the mid-auth base URL instead of `http://127.0.0.1:19000`.
- If the browser UI runs on another **site** (e.g. `http://localhost:7923` while the API is `http://api.dev.local`), cookies with `SameSite=Lax` (the template default) are **not** sent on cross-site `fetch`/XHR. For that layout you typically need `MID_AUTH_SESSION_COOKIE_SAMESITE=none`, **HTTPS in front of Nginx**, and `MID_AUTH_SESSION_COOKIE_SECURE=true` (browsers require `Secure` when `SameSite=None`).
- For local same-origin or same-site setups, keeping `lax` and `MID_AUTH_SESSION_COOKIE_SECURE=false` is usually enough.

### Quick verification checklist

| Check | Expected |
| --- | --- |
| Migrations | `alembic current` reports head |
| Register | `POST /auth/register` → **201**; `user_app_mappings` has `openwebui`, `vocechat`, `memos` rows |
| Login | `POST /auth/login` sets session cookie; `GET /auth/me` → **200** |
| User BFF | With session, Open WebUI proxy routes (e.g. `GET /me/ai/workbench/models`) succeed when mapped; **404** if the user has no Open WebUI mapping |
