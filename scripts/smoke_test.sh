#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${H3_API_URL:-http://127.0.0.1:6006}"
APP_DIR="${H3_APP_DIR:-/root/h3-app}"
python "${APP_DIR}/scripts/validate_comfy.py"
curl --fail --silent --show-error "${BASE_URL}/health"
curl --fail --silent --show-error \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"古装少女回头，镜头缓慢推近","duration":5,"aspect_ratio":"9:16","preset":"draft","accepted_terms":true}' \
  "${BASE_URL}/v1/videos"
