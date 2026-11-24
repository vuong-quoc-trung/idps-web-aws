#!/bin/bash
set -euo pipefail
cd "$HOME/idps-web-aws/student-web/backend"
if [[ -n $(ss -H -ltn 'sport = :8080') ]]; then
    echo "Backend on port 8080 still serving. Stop it in its original VM terminal before starting the replacement." >&2
    exit 1
fi
read -rp "Numeric ID of the approved STUDENT/STAFF lab account: " lab
[[ $lab =~ ^[1-9][0-9]*$ ]]
export APP_NATIVE_LABUSERIDS="$lab"
export APP_NATIVE_SESSIONLEASEDIR=/var/lib/ws-student-leases/leases
export APP_NATIVE_SESSIONKEY
APP_NATIVE_SESSIONKEY=$(cat "$HOME/.config/websentinel/native-session.key")
[[ -n $APP_NATIVE_SESSIONKEY ]]
if [[ -x /usr/lib/jvm/java-25-openjdk-amd64/bin/javac ]]; then
    export JAVA_HOME=/usr/lib/jvm/java-25-openjdk-amd64
fi
exec bash ./run.sh
