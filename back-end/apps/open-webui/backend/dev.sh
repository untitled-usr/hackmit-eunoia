# 后端 DEV：开启 /docs、/openapi.json 等（与 open_webui.env.ENV 一致）
export ENV="${ENV:-dev}"

if [[ -z "${CORS_ALLOW_ORIGIN:-}" ]]; then
  export CORS_ALLOW_ORIGIN='http://localhost:7923;http://127.0.0.1:7923;http://owui.dev.local'
fi

append_origin() {
  local origin="$1"
  [[ -n "${origin}" ]] || return 0
  case ";${CORS_ALLOW_ORIGIN};" in
    *";${origin};"*) ;;
    *) CORS_ALLOW_ORIGIN="${CORS_ALLOW_ORIGIN};${origin}" ;;
  esac
}

# Allow LAN access during development (e.g. http://<server-ip>:7923 -> backend :7920).
for ip in $(hostname -I 2>/dev/null || true); do
  [[ "${ip}" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]] || continue
  append_origin "http://${ip}"
  append_origin "http://${ip}:7920"
  append_origin "http://${ip}:7923"
done
export CORS_ALLOW_ORIGIN
PORT="${PORT:-7920}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_UVICORN="${SCRIPT_DIR}/.venv/bin/uvicorn"
if [[ -x "${VENV_UVICORN}" ]]; then
  exec "${VENV_UVICORN}" open_webui.main:app --port "${PORT}" --host 0.0.0.0 --forwarded-allow-ips '*' --reload
fi
exec uvicorn open_webui.main:app --port "${PORT}" --host 0.0.0.0 --forwarded-allow-ips '*' --reload
