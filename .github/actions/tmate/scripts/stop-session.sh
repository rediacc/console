#!/bin/bash
set -e

# Input parameter
SESSION_PID="${1:-}"

echo "🛑 Stopping tmate session..."

# If PID provided as argument, use it
if [ -n "$SESSION_PID" ]; then
    echo "   Using provided PID: $SESSION_PID"
    if kill "$SESSION_PID" 2>/dev/null; then
        echo "✅ tmate session stopped (PID: $SESSION_PID)"
    else
        echo "⚠️  Process $SESSION_PID not found or already stopped"
    fi
    exit 0
fi

# Otherwise, try to read from session info file
if [ -f /tmp/tmate-session-info.txt ]; then
    source /tmp/tmate-session-info.txt

    if [ -n "$TMATE_PID" ]; then
        echo "   Found PID: $TMATE_PID"
        if kill "$TMATE_PID" 2>/dev/null; then
            echo "✅ tmate session stopped (PID: $TMATE_PID)"
        else
            echo "⚠️  Process $TMATE_PID not found or already stopped"
        fi
    fi

    # Cleanup socket if exists
    if [ -n "$TMATE_SOCK" ] && [ -S "$TMATE_SOCK" ]; then
        rm -f "$TMATE_SOCK"
        echo "   Cleaned up socket: $TMATE_SOCK"
    fi

    # Cleanup session info
    rm -f /tmp/tmate-session-info.txt
else
    # Fallback: try to find and kill all tmate processes
    echo "   Session info not found, searching for tmate processes..."
    if pgrep -f "tmate.*new-session" > /dev/null; then
        pkill -f "tmate.*new-session" && echo "✅ Stopped all tmate sessions"
    else
        echo "⚠️  No active tmate sessions found"
    fi
fi

# Cleanup any remaining temp files
rm -f /tmp/tmate-*.log /tmp/tmate-*.sock /tmp/tmate-session-info.txt 2>/dev/null || true

echo "✅ Cleanup complete"
