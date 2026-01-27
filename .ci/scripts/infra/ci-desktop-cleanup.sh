#!/bin/bash
# CI Desktop Cleanup Script
# Stops desktop processes started by ci-desktop.sh
#
# Usage:
#   ./ci-desktop-cleanup.sh

set -e

echo "Cleaning up desktop processes..."

if [ -f /tmp/desktop-pids.txt ]; then
    # Kill processes in reverse order of startup
    while IFS='=' read -r name pid; do
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            echo "  Stopping $name (PID: $pid)..."
            kill "$pid" 2>/dev/null || true
        fi
    done < <(tac /tmp/desktop-pids.txt)
    rm -f /tmp/desktop-pids.txt
    echo "Desktop cleanup complete"
else
    echo "No desktop processes found (/tmp/desktop-pids.txt missing)"
fi
