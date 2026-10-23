#!/usr/bin/env bash
set -euo pipefail

BACKEND_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd -- "$BACKEND_DIR"

if [[ ! -f .env ]]; then
  printf 'Không tìm thấy file cấu hình: %s/.env\n' "$BACKEND_DIR" >&2
  exit 1
fi

set -a
source .env
set +a

LOCAL_JDK="$BACKEND_DIR/../../.local-jdk/25"
if [[ -z "${JAVA_HOME:-}" && -x "$LOCAL_JDK/bin/java" ]]; then
  export JAVA_HOME="$LOCAL_JDK"
fi
if [[ -n "${JAVA_HOME:-}" ]]; then
  export PATH="$JAVA_HOME/bin:$PATH"
fi

JAVA_MAJOR="$(java -XshowSettings:properties -version 2>&1 | awk '/java.specification.version =/ {print $3}')"
if [[ "$JAVA_MAJOR" != "25" ]]; then
  printf 'Backend yêu cầu JDK 25; Java hiện tại: %s. Đặt JAVA_HOME tới JDK 25 rồi chạy lại.\n' "$JAVA_MAJOR" >&2
  exit 1
fi

exec ./mvnw spring-boot:run "$@"
