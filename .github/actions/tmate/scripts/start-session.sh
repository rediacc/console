#!/bin/bash
set -e

# Input parameters
TIMEOUT="${1:-30}"
SERVER_HOST="${2:-}"
SERVER_PORT="${3:-}"

echo "🖥️  Starting tmate session..."
echo "   Timeout: ${TIMEOUT}s"

# Configure custom server if provided
if [ -n "$SERVER_HOST" ]; then
    echo "   Server: $SERVER_HOST:${SERVER_PORT:-22}"
    export TMATE_SERVER_HOST="$SERVER_HOST"
    if [ -n "$SERVER_PORT" ]; then
        export TMATE_SERVER_PORT="$SERVER_PORT"
    fi
fi

# Create temp directory for session data
TMATE_LOG="/tmp/tmate-$$.log"
TMATE_SOCK="/tmp/tmate-$$.sock"

# Start tmate in detached mode
echo "⏳ Starting tmate session (max ${TIMEOUT}s)..."
tmate -S "$TMATE_SOCK" new-session -d > "$TMATE_LOG" 2>&1

# Wait for socket to be created and find tmate PID
TMATE_PID=""
for i in $(seq 1 "$TIMEOUT"); do
    if [ -S "$TMATE_SOCK" ]; then
        # Find the actual tmate process PID
        TMATE_PID=$(pgrep -f "tmate -S $TMATE_SOCK" | head -1)
        if [ -n "$TMATE_PID" ]; then
            break
        fi
    fi
    sleep 1
done

if [ ! -S "$TMATE_SOCK" ] || [ -z "$TMATE_PID" ]; then
    echo "❌ Error: tmate socket not created or process not found within ${TIMEOUT}s"
    echo "📋 tmate log output:"
    cat "$TMATE_LOG" 2>/dev/null || echo "No log output"
    echo ""
    echo "Process list:"
    ps aux | grep tmate || echo "No tmate processes found"
    exit 1
fi

# Wait for tmate to be ready and connected
echo "⏳ Waiting for tmate connection..."
for i in $(seq 1 "$TIMEOUT"); do
    if tmate -S "$TMATE_SOCK" display -p '#{tmate_ssh}' 2>/dev/null | grep -q "ssh"; then
        break
    fi
    sleep 1
done

# Extract connection information
SSH_CONNECTION=$(tmate -S "$TMATE_SOCK" display -p '#{tmate_ssh}' 2>/dev/null || echo "")
WEB_URL=$(tmate -S "$TMATE_SOCK" display -p '#{tmate_web}' 2>/dev/null || echo "")
SSH_RO_CONNECTION=$(tmate -S "$TMATE_SOCK" display -p '#{tmate_ssh_ro}' 2>/dev/null || echo "")
WEB_RO_URL=$(tmate -S "$TMATE_SOCK" display -p '#{tmate_web_ro}' 2>/dev/null || echo "")

# Validate that we got connection info
if [ -z "$SSH_CONNECTION" ] && [ -z "$WEB_URL" ]; then
    echo "❌ Error: Could not extract connection info within ${TIMEOUT}s"
    echo "📋 tmate log output:"
    cat "$TMATE_LOG" 2>/dev/null || echo "No log output"
    echo ""
    echo "Socket status:"
    ls -la "$TMATE_SOCK" 2>/dev/null || echo "Socket not found"
    exit 1
fi

# Display connection information (unless silent mode)
if [ "$SILENT_MODE" != "true" ]; then
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "🌍 TMATE SESSION ACTIVE"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""

    if [ -n "$SSH_CONNECTION" ]; then
        echo "   📡 SSH Access (Read/Write):"
        echo "      $SSH_CONNECTION"
        echo ""
    fi

    if [ -n "$WEB_URL" ]; then
        echo "   🌐 Web Access (Read/Write):"
        echo "      $WEB_URL"
        echo ""
    fi

    if [ -n "$SSH_RO_CONNECTION" ]; then
        echo "   👁️  SSH Access (Read-Only):"
        echo "      $SSH_RO_CONNECTION"
        echo ""
    fi

    if [ -n "$WEB_RO_URL" ]; then
        echo "   👁️  Web Access (Read-Only):"
        echo "      $WEB_RO_URL"
        echo ""
    fi

    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
else
    echo "🔐 tmate session started in silent mode (connection details in outputs only)"
    echo ""
fi

# Mask sensitive connection strings so GitHub Actions redacts them from logs
if [ -n "$SSH_CONNECTION" ]; then echo "::add-mask::$SSH_CONNECTION"; fi
if [ -n "$WEB_URL" ]; then echo "::add-mask::$WEB_URL"; fi
if [ -n "$SSH_RO_CONNECTION" ]; then echo "::add-mask::$SSH_RO_CONNECTION"; fi
if [ -n "$WEB_RO_URL" ]; then echo "::add-mask::$WEB_RO_URL"; fi

# Set outputs for GitHub Actions
{
    echo "ssh-connection=$SSH_CONNECTION"
    echo "web-url=$WEB_URL"
    echo "session-pid=$TMATE_PID"
    echo "ssh-ro-connection=$SSH_RO_CONNECTION"
    echo "web-ro-url=$WEB_RO_URL"
} >> "$GITHUB_OUTPUT"

# Save session info for cleanup
{
    echo "SSH_CONNECTION=$SSH_CONNECTION"
    echo "WEB_URL=$WEB_URL"
    echo "TMATE_PID=$TMATE_PID"
    echo "TMATE_SOCK=$TMATE_SOCK"
} > /tmp/tmate-session-info.txt

echo "✅ tmate session started successfully"
echo ""
echo "💡 Tips:"
echo "   - Session runs in background, workflow continues"
echo "   - Connect any time using the URLs above"
echo "   - Session stays active until job ends or manual cleanup"
echo "   - Use 'kill $TMATE_PID' to stop the session"
echo ""
