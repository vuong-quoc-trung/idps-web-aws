#!/usr/bin/env bash
# Reversible deactivation only: preserve configs, spool, logs and DB.
set -euo pipefail
sudo systemctl disable --now pbl4-audit-sender-rotate.timer pbl4-audit-sender.service
sudo systemctl stop pbl4-audit-sender-rotate.service
printf '%s\n' 'Preserved configuration, checkpoints, queue and logs for rollback/recovery.'
