#!/usr/bin/env bash
# Create the mid-auth application database (PostgreSQL) if missing, then run Alembic migrations.
# Loads MID_AUTH_DATABASE_URL from ${DEVSTACK_STATE_ROOT}/mid-auth/config/.env (sync via sync-env-templates.sh).
# For SQLite URLs, skips CREATE DATABASE and only runs alembic upgrade head.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"
# shellcheck source=./lib/load-env.sh
source "${SCRIPT_DIR}/lib/load-env.sh"

ENV_FILE="${DEVSTACK_STATE_ROOT}/mid-auth/config/.env"
MID_AUTH_ROOT="${DEVSTACK_WORKSPACE_ROOT}/services/mid-auth"

require_file "${ENV_FILE}"
require_dir "${MID_AUTH_ROOT}"
load_env_file "${ENV_FILE}"

if [[ -z "${MID_AUTH_DATABASE_URL:-}" ]]; then
  log_error "MID_AUTH_DATABASE_URL is not set in ${ENV_FILE}"
  exit 1
fi

ensure_postgres_database() {
  local raw="$1"
  local out py_status
  set +e
  out="$(MID_AUTH_DATABASE_URL="$raw" python3 - <<'PY'
import os
import urllib.parse

raw = os.environ["MID_AUTH_DATABASE_URL"]
low = raw.lower()
if low.startswith("sqlite") or "+sqlite" in low:
    print("sqlite")
    raise SystemExit(0)

u0 = raw.replace("postgresql+psycopg://", "postgresql://").replace(
    "postgresql+asyncpg://", "postgresql://"
)
u = urllib.parse.urlparse(u0)
if u.scheme not in ("postgresql", "postgres"):
    print(f"unsupported scheme {u.scheme!r}", file=__import__("sys").stderr)
    raise SystemExit(2)
path = (u.path or "").lstrip("/")
if not path:
    print("MID_AUTH_DATABASE_URL must include a database name", file=__import__("sys").stderr)
    raise SystemExit(2)
dbname = path.split("?")[0]
admin = u._replace(path="/postgres")
admin_url = urllib.parse.urlunparse(admin)
print(admin_url)
print(dbname)
PY
)"
  py_status=$?
  set -e
  if [[ "$py_status" -ne 0 ]]; then
    exit "$py_status"
  fi
  if [[ "$(echo "$out" | head -1)" == "sqlite" ]]; then
    log_info "SQLite detected; skipping PostgreSQL CREATE DATABASE."
    return 0
  fi
  local admin_url dbname
  admin_url="$(echo "$out" | sed -n '1p')"
  dbname="$(echo "$out" | sed -n '2p')"

  if ! command -v psql >/dev/null 2>&1; then
    log_error "psql not found; install PostgreSQL client tools or create the database manually."
    exit 1
  fi

  local exists
  exists="$(psql "$admin_url" -v ON_ERROR_STOP=1 -Atc "SELECT 1 FROM pg_database WHERE datname = '${dbname//\'/\'\'}'")" || {
    log_error "Cannot connect with maintenance URL (postgres db). Check MID_AUTH_DATABASE_URL credentials and host."
    exit 1
  }

  if [[ "$exists" == "1" ]]; then
    log_info "Database already exists: ${dbname}"
  else
    log_info "Creating database: ${dbname}"
    psql "$admin_url" -v ON_ERROR_STOP=1 -c "CREATE DATABASE \"${dbname//\"/\"\"}\""
  fi
}

ensure_postgres_database "${MID_AUTH_DATABASE_URL}"

VENV="${MID_AUTH_ROOT}/.venv"
if [[ ! -x "${VENV}/bin/python" ]]; then
  log_info "Creating Python venv at ${VENV}"
  python3 -m venv "${VENV}"
fi
# shellcheck disable=SC1091
source "${VENV}/bin/activate"
pip install -q -r "${MID_AUTH_ROOT}/requirements.txt"

log_info "Running alembic upgrade head in ${MID_AUTH_ROOT}"
(
  cd "${MID_AUTH_ROOT}"
  alembic upgrade head
)

log_info "Probing application database connection..."
MID_AUTH_DATABASE_URL="${MID_AUTH_DATABASE_URL}" python3 - <<'PY'
import os
from sqlalchemy import create_engine, text

url = os.environ["MID_AUTH_DATABASE_URL"]
engine = create_engine(url)
with engine.connect() as conn:
    conn.execute(text("SELECT 1"))
print("ok")
PY

log_info "Mid-auth database bootstrap finished."
