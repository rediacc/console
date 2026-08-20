#!/bin/bash
# Tutorial 06: Working with Your Repo
# Demonstrates the daily three: tunnel, term, sync. The tunnel command is
# long-running, so we start it in the background, capture a brief snapshot,
# then kill it. Sync and term run normally.
#
# Prerequisites: shared tutorial config + provisioned worker VM + a deployed
# my-app repo (we deploy it inline to keep this script self-contained).

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/tutorial-helpers.sh"

# Silence pre-recording setup so its output doesn't bleed into the cast.
exec 3>&1 4>&2
exec >"$TUTORIAL_SETUP_LOG" 2>&1

M="$TUTORIAL_MACHINE_NAME"

# Pre-recording setup
rm -f ~/.config/rediacc/rediacc.json 2>/dev/null || true
rdc config init --ssh-key "$TUTORIAL_SSH_KEY"
rdc machine add "$M" --ip "$TUTORIAL_MACHINE_IP" --user "$TUTORIAL_MACHINE_USER"
for i in $(seq 1 30); do
    ssh -i "$TUTORIAL_SSH_KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=2 \
        "$TUTORIAL_MACHINE_USER@$TUTORIAL_MACHINE_IP" true 2>/dev/null && break
    sleep 2
done
rdc machine setup "$M"
# Reap any orphaned repo state from previous tutorial runs.
rdc machine prune "$M" --orphaned-repos --force --grace-days 0 --force-delete-mounted 2>/dev/null || true

rdc repo delete my-app --yes 2>/dev/null || true
rdc repo create my-app --machine "$M" --size 2G
rdc repo admin template apply my-app --template app-postgres
rdc repo up my-app

mkdir -p /tmp/tutorial-src && echo "<h1>Hello</h1>" >/tmp/tutorial-src/index.html
mkdir -p /tmp/tutorial-backup

# Restore stdout/stderr so asciinema captures only the demo from here on.
exec >&3 2>&4

clear_screen

section "Tunnel — open the app in your browser"
# Tunnel is long-running: let it serve for a few seconds, then Ctrl+C it
# exactly like a user would.
run_cmd_interrupt "rdc repo tunnel my-app --container app" 4

pause 2

section "Term — run a command inside the repo"
# Narrow --format, not bare `docker ps`: the default table is 122 columns and
# the recorded terminal is 107, so it wrapped into the row below and shredded
# the layout. Name/Status/Ports is what the demo is actually showing.
run_cmd "rdc term connect my-app --command 'docker ps --format \"table {{.Names}}\t{{.Status}}\t{{.Ports}}\"'"

pause 2

section "Sync — preview, then upload"
run_cmd "rdc repo sync upload my-app --local /tmp/tutorial-src --dry-run"

pause 1

run_cmd "rdc repo sync upload my-app --local /tmp/tutorial-src"

pause 2

# End the on-camera portion; cleanup below is not recorded.
end_recording
# Clean up
rm -rf /tmp/tutorial-src /tmp/tutorial-backup
rdc repo down my-app 2>/dev/null || true
rdc repo down my-app --unmount 2>/dev/null || true
rdc repo delete my-app --yes 2>/dev/null || true
