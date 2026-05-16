#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT_DIR/infra/.env}"
CATEGORY_CODE="${CATEGORY_CODE:-sgcc_distribution}"

pass() {
  printf '✓ %s\n' "$1"
}

fail() {
  printf '✗ %s\n' "$1" >&2
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "缺少命令: $1"
}

require_cmd curl
require_cmd docker
require_cmd python3

env_value() {
  local key="$1"
  local fallback="$2"
  local value
  value="$(grep -E "^${key}=" "$ENV_FILE" | tail -n 1 | cut -d= -f2- || true)"
  if [ -n "$value" ]; then
    printf '%s' "$value"
  else
    printf '%s' "$fallback"
  fi
}

[ -f "$ENV_FILE" ] || fail "找不到环境文件: $ENV_FILE"

BACKEND_PORT="$(env_value BACKEND_PORT 8000)"
FRONTEND_PORT="$(env_value FRONTEND_PORT 3000)"
VITE_ENABLE_DEV_AUTH="$(env_value VITE_ENABLE_DEV_AUTH false)"
VITE_DEV_AUTH_TOKEN="$(env_value VITE_DEV_AUTH_TOKEN dev-token)"

BACKEND_URL="http://127.0.0.1:${BACKEND_PORT}"
FRONTEND_URL="http://127.0.0.1:${FRONTEND_PORT}"

cd "$ROOT_DIR"

docker compose --env-file "$ENV_FILE" -f infra/docker-compose.yml --profile app ps >/dev/null \
  || fail "Docker compose 状态不可读；请确认 Docker 正在运行"
pass "Docker compose 可访问"

if [ "$VITE_ENABLE_DEV_AUTH" != "true" ]; then
  fail "本地前端 dev auth 未开启；请在 infra/.env 设置 VITE_ENABLE_DEV_AUTH=true"
fi
pass "本地前端 dev auth 已开启"

curl -fsS "$FRONTEND_URL/" >/dev/null \
  || fail "前端不可访问: $FRONTEND_URL"
pass "前端可访问: $FRONTEND_URL"

curl -fsS "$BACKEND_URL/api/health" >/dev/null \
  || fail "后端健康检查失败: $BACKEND_URL/api/health"
pass "后端健康检查通过: $BACKEND_URL"

curl -fsS -H "Authorization: Bearer ${VITE_DEV_AUTH_TOKEN}" "$BACKEND_URL/api/auth/me" >/dev/null \
  || fail "dev-token 认证失败；请确认 VITE_DEV_AUTH_TOKEN 与后端开发 token 一致"
pass "dev-token 认证通过"

template_count="$(
  curl -fsS -H "Authorization: Bearer ${VITE_DEV_AUTH_TOKEN}" \
    "$BACKEND_URL/api/template-packages?category_code=${CATEGORY_CODE}" \
    | python3 -c 'import json,sys; data=json.load(sys.stdin); print(len(data) if isinstance(data, list) else 0)'
)"

if [ "$template_count" -le 0 ]; then
  fail "模板包为空: category_code=${CATEGORY_CODE}；请先导入或恢复模板包数据"
fi
pass "模板包可用: category_code=${CATEGORY_CODE}, count=${template_count}"

printf '\n本地 Tender 检查通过。\n'
