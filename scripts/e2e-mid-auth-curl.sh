#!/usr/bin/env bash
# End-to-end smoke tests for mid-auth from a browser-like client (curl + cookie jar).
# Prerequisites: migrated DB, mid-auth running (see services/mid-auth/README.md "Curl E2E").
#
# Environment:
#   BASE_URL                     default http://127.0.0.1:19000
#   (Admin HTTP BFF routes have been removed from mid-auth.)
#   MID_AUTH_E2E_SOFT_DOWNSTREAM   if 1 (default), BFF routes may return 502/503/504 without failing the script (warn only)
#   MID_AUTH_E2E_STRICT_DOWNSTREAM if 1, BFF routes must return 200
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:19000}"
MID_AUTH_E2E_SOFT_DOWNSTREAM="${MID_AUTH_E2E_SOFT_DOWNSTREAM:-1}"
MID_AUTH_E2E_STRICT_DOWNSTREAM="${MID_AUTH_E2E_STRICT_DOWNSTREAM:-0}"
if [[ "${MID_AUTH_E2E_STRICT_DOWNSTREAM}" == "1" ]]; then
  MID_AUTH_E2E_SOFT_DOWNSTREAM=0
fi

COOKIE_JAR=""
HDR_FILE=""
BODY_FILE=""
cleanup() {
  [[ -n "${COOKIE_JAR}" && -f "${COOKIE_JAR}" ]] && rm -f "${COOKIE_JAR}"
  [[ -n "${HDR_FILE}" && -f "${HDR_FILE}" ]] && rm -f "${HDR_FILE}"
  [[ -n "${BODY_FILE}" && -f "${BODY_FILE}" ]] && rm -f "${BODY_FILE}"
}
trap cleanup EXIT

COOKIE_JAR="$(mktemp)"
HDR_FILE="$(mktemp)"
BODY_FILE="$(mktemp)"
touch "${COOKIE_JAR}"

have_jq=false
if command -v jq >/dev/null 2>&1; then
  have_jq=true
fi

die() {
  printf '[e2e] FAIL: %s\n' "$*" >&2
  exit 1
}

warn() {
  printf '[e2e] WARN: %s\n' "$*" >&2
}

step() {
  printf '[e2e] -- %s\n' "$*" >&2
}

# Usage: _curl_exec method path extra_curl_args...
# Sets global _last_code, writes body to BODY_FILE, headers to HDR_FILE
_last_code=""
_curl_exec() {
  local method="$1"
  local path="$2"
  shift 2
  : >"${HDR_FILE}"
  : >"${BODY_FILE}"
  _last_code="$(
    curl -sS -X "${method}" "${BASE_URL}${path}" \
      -D "${HDR_FILE}" \
      -o "${BODY_FILE}" \
      -w '%{http_code}' \
      "$@"
  )"
}

expect_eq() {
  local name="$1"
  local got="$2"
  local want="$3"
  if [[ "${got}" != "${want}" ]]; then
    local snippet
    snippet="$(head -c 400 "${BODY_FILE}" 2>/dev/null | tr '\n' ' ')"
    die "${name}: expected HTTP ${want}, got ${got} body=${snippet}"
  fi
}

expect_json_ok() {
  local name="$1"
  if [[ "${have_jq}" == true ]]; then
    jq -e . "${BODY_FILE}" >/dev/null 2>&1 || die "${name}: response is not valid JSON"
  fi
}

# Downstream BFF: 200 required, or soft-allow 502/503/504
expect_bff() {
  local name="$1"
  local code="$2"
  if [[ "${code}" == "200" ]]; then
    expect_json_ok "${name}"
    return 0
  fi
  if [[ "${MID_AUTH_E2E_SOFT_DOWNSTREAM}" == "1" ]] && [[ "${code}" =~ ^(502|503|504)$ ]]; then
    warn "${name}: HTTP ${code} (downstream unavailable?); continuing because MID_AUTH_E2E_SOFT_DOWNSTREAM=1"
    return 0
  fi
  expect_eq "${name}" "${code}" "200"
}

E2E_ID="$(date +%s)_${RANDOM}"
USERNAME="e2e_${E2E_ID}"
EMAIL="${USERNAME}@example.test"
PASSWORD="ValidPass123!"
NEW_PASSWORD="NewValidPass99!"

step "GET /healthz"
_curl_exec GET "/healthz"
expect_eq "healthz" "${_last_code}" "200"

step "GET /v1/capabilities"
_curl_exec GET "/v1/capabilities"
expect_eq "capabilities" "${_last_code}" "200"
expect_json_ok "capabilities"

step "GET /auth/me without cookie (expect 401)"
_curl_exec GET "/auth/me"
expect_eq "me_unauthenticated" "${_last_code}" "401"

step "POST /auth/register password too short (expect 422)"
_curl_exec POST "/auth/register" \
  -H 'Content-Type: application/json' \
  -d '{"username":"x","email":"a@b.co","password":"short"}'
expect_eq "register_short_password" "${_last_code}" "422"

step "POST /auth/register missing email (expect 422)"
_curl_exec POST "/auth/register" \
  -H 'Content-Type: application/json' \
  -d "{\"username\":\"${USERNAME}_bad\",\"password\":\"${PASSWORD}\"}"
expect_eq "register_missing_email" "${_last_code}" "422"

step "POST /auth/register invalid JSON body (expect 422)"
_curl_exec POST "/auth/register" \
  -H 'Content-Type: application/json' \
  -d 'not-json'
expect_eq "register_invalid_json" "${_last_code}" "422"

step "POST /auth/register valid (expect 201)"
_curl_exec POST "/auth/register" \
  -H 'Content-Type: application/json' \
  -d "{\"username\":\"${USERNAME}\",\"email\":\"${EMAIL}\",\"password\":\"${PASSWORD}\",\"display_name\":\"E2E User\"}"
if [[ "${_last_code}" != "201" ]]; then
  snippet="$(head -c 500 "${BODY_FILE}" | tr '\n' ' ')"
  die "register_valid: expected HTTP 201, got ${_last_code} body=${snippet} — start downstream apps or set MID_AUTH_PROVISION_USE_STUB=true in mid-auth .env"
fi
expect_json_ok "register_valid"
if [[ "${have_jq}" == true ]]; then
  u="$(jq -r '.user.username' "${BODY_FILE}")"
  [[ "${u}" == "${USERNAME}" ]] || die "register response username mismatch: ${u}"
fi

step "POST /auth/register duplicate (expect 409)"
_curl_exec POST "/auth/register" \
  -H 'Content-Type: application/json' \
  -d "{\"username\":\"${USERNAME}\",\"email\":\"${EMAIL}\",\"password\":\"${PASSWORD}\"}"
expect_eq "register_duplicate" "${_last_code}" "409"

step "POST /auth/login wrong password (expect 401)"
_curl_exec POST "/auth/login" \
  -H 'Content-Type: application/json' \
  -d "{\"identifier\":\"${EMAIL}\",\"password\":\"WrongPassword123!\"}"
expect_eq "login_wrong_password" "${_last_code}" "401"

step "POST /auth/login unknown user (expect 401)"
_curl_exec POST "/auth/login" \
  -H 'Content-Type: application/json' \
  -d '{"identifier":"no_such_user_e2e@example.test","password":"x"}'
expect_eq "login_unknown_user" "${_last_code}" "401"

step "POST /auth/login success (expect 200 + Set-Cookie)"
: >"${COOKIE_JAR}"
_curl_exec POST "/auth/login" \
  -H 'Content-Type: application/json' \
  -c "${COOKIE_JAR}" -b "${COOKIE_JAR}" \
  -d "{\"identifier\":\"${EMAIL}\",\"password\":\"${PASSWORD}\"}"
expect_eq "login_success" "${_last_code}" "200"
if ! grep -qi '^set-cookie:' "${HDR_FILE}"; then
  die "login_success: missing Set-Cookie header"
fi
expect_json_ok "login_success"

step "GET /auth/me with session (expect 200)"
_curl_exec GET "/auth/me" -b "${COOKIE_JAR}"
expect_eq "me_authenticated" "${_last_code}" "200"
if [[ "${have_jq}" == true ]]; then
  u="$(jq -r '.username' "${BODY_FILE}")"
  e="$(jq -r '.email' "${BODY_FILE}")"
  [[ "${u}" == "${USERNAME}" ]] || die "/auth/me username mismatch"
  [[ "${e}" == "${EMAIL}" ]] || die "/auth/me email mismatch"
fi

step "GET /me/profile (expect 200)"
_curl_exec GET "/me/profile" -b "${COOKIE_JAR}"
expect_eq "get_profile" "${_last_code}" "200"

step "PATCH /me/profile valid (expect 200)"
_curl_exec PATCH "/me/profile" \
  -H 'Content-Type: application/json' \
  -b "${COOKIE_JAR}" \
  -d '{"display_name":"E2E Patched"}'
expect_eq "patch_profile_ok" "${_last_code}" "200"

step "PATCH /me/profile empty display_name (expect 422)"
_curl_exec PATCH "/me/profile" \
  -H 'Content-Type: application/json' \
  -b "${COOKIE_JAR}" \
  -d '{"display_name":""}'
expect_eq "patch_profile_invalid" "${_last_code}" "422"

step "GET /me/posts (expect 200 or soft downstream 5xx)"
_curl_exec GET "/me/posts" -b "${COOKIE_JAR}"
expect_bff "get_me_posts" "${_last_code}"

step "GET /me/library/stats (expect 200 or soft downstream 5xx)"
_curl_exec GET "/me/library/stats" -b "${COOKIE_JAR}"
expect_bff "get_library_stats" "${_last_code}"

step "GET /me/conversations (expect 200 or soft downstream 5xx)"
_curl_exec GET "/me/conversations" -b "${COOKIE_JAR}"
expect_bff "get_conversations" "${_last_code}"

step "GET /me/ai/chats (expect 200 or soft downstream 5xx)"
_curl_exec GET "/me/ai/chats" -b "${COOKIE_JAR}"
expect_bff "get_ai_chats" "${_last_code}"

step "GET /me/ai/workbench/models?page=1 without cookie (expect 401 or 503 if OW URL unset)"
_curl_exec GET "/me/ai/workbench/models?page=1"
if [[ "${_last_code}" != "401" ]] && [[ "${_last_code}" != "503" ]]; then
  die "workbench_models_no_cookie: expected HTTP 401 or 503, got ${_last_code}"
fi

step "GET /me/ai/workbench/models?page=1 with session (expect 200 or soft 5xx)"
_curl_exec GET "/me/ai/workbench/models?page=1" -b "${COOKIE_JAR}"
expect_bff "get_workbench_models" "${_last_code}"

step "GET /admin/openwebui/system/config (removed; expect 404)"
_curl_exec GET "/admin/openwebui/system/config" -b "${COOKIE_JAR}"
expect_eq "admin_route_removed" "${_last_code}" "404"

step "POST /auth/change-password wrong old password (expect 400)"
_curl_exec POST "/auth/change-password" \
  -H 'Content-Type: application/json' \
  -b "${COOKIE_JAR}" \
  -d "{\"old_password\":\"not-the-password\",\"new_password\":\"${NEW_PASSWORD}\"}"
expect_eq "change_password_wrong_old" "${_last_code}" "400"

step "POST /auth/change-password success (expect 200, sessions cleared)"
_curl_exec POST "/auth/change-password" \
  -H 'Content-Type: application/json' \
  -c "${COOKIE_JAR}" -b "${COOKIE_JAR}" \
  -d "{\"old_password\":\"${PASSWORD}\",\"new_password\":\"${NEW_PASSWORD}\"}"
expect_eq "change_password_ok" "${_last_code}" "200"

step "GET /auth/me after password change (expect 401)"
_curl_exec GET "/auth/me" -b "${COOKIE_JAR}"
expect_eq "me_after_password_change" "${_last_code}" "401"

step "POST /auth/login old password (expect 401)"
_curl_exec POST "/auth/login" \
  -H 'Content-Type: application/json' \
  -d "{\"identifier\":\"${EMAIL}\",\"password\":\"${PASSWORD}\"}"
expect_eq "login_old_password_after_change" "${_last_code}" "401"

step "POST /auth/login new password (expect 200)"
: >"${COOKIE_JAR}"
_curl_exec POST "/auth/login" \
  -H 'Content-Type: application/json' \
  -c "${COOKIE_JAR}" -b "${COOKIE_JAR}" \
  -d "{\"identifier\":\"${EMAIL}\",\"password\":\"${NEW_PASSWORD}\"}"
expect_eq "login_new_password" "${_last_code}" "200"

step "POST /auth/logout (expect 200)"
_curl_exec POST "/auth/logout" -b "${COOKIE_JAR}" -c "${COOKIE_JAR}"
expect_eq "logout" "${_last_code}" "200"

step "GET /auth/me after logout (expect 401)"
_curl_exec GET "/auth/me" -b "${COOKIE_JAR}"
expect_eq "me_after_logout" "${_last_code}" "401"

printf '[e2e] OK — all steps passed (BASE_URL=%s)\n' "${BASE_URL}" >&2
