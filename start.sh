#!/usr/bin/env bash
# Delegate to scripts/linux/start.sh
exec "$(dirname "$0")/scripts/linux/start.sh" "$@"
