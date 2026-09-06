#!/bin/sh
set -e

# Ensure app directories exist and are owned by appuser
mkdir -p /app/data /app/logs /app/backups
chown -R appuser:appuser /app/data /app/logs /app/backups 2>/dev/null || true
chmod -R 775 /app/data /app/logs /app/backups 2>/dev/null || true

# Step down from root and execute command as unprivileged appuser
exec gosu appuser "$@"
