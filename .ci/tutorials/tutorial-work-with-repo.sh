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
exec >/dev/null 2>&1

M="$TUTORIAL_MACHINE_NAME"

# Pre-recording setup
rm -f ~/.config/rediacc/rediacc.json 2>/dev/null || true
rdc config init --ssh-key "$TUTORIAL_SSH_KEY"
rdc config machine add --name "$M" --ip "$TUTORIAL_MACHINE_IP" --user "$TUTORIAL_MACHINE_USER"
for i in $(seq 1 30); do
    ssh -i "$TUTORIAL_SSH_KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=2 \
        "$TUTORIAL_MACHINE_USER@$TUTORIAL_MACHINE_IP" true 2>/dev/null && break
    sleep 2
done
rdc config machine setup --name "$M"
# Reap any orphaned repo state from previous tutorial runs.
rdc machine prune --name "$M" --orphaned-repos --force --grace-days 0 --force-delete-mounted 2>/dev/null || true

rdc repo delete --name my-app --machine "$M" 2>/dev/null || true
rdc repo create --name my-app --machine "$M" --size 2G
rdc repo template apply --name app-postgres --machine "$M" --repository my-app
rdc repo up --name my-app --machine "$M"

mkdir -p /tmp/tutorial-src && echo "<h1>Hello</h1>" >/tmp/tutorial-src/index.html
mkdir -p /tmp/tutorial-backup

# Restore stdout/stderr so asciinema captures only the demo from here on.
exec >&3 2>&4

clear_screen

section "Tunnel — open the app in your browser"
# Tunnel is long-running. Show the command running for ~2s then stop it.
run_cmd "timeout 2s rdc repo tunnel --machine $M --repository my-app --container app || true"

pause 2

section "Term — run a command inside the repo"
run_cmd "rdc term connect --machine $M --repository my-app --command 'docker ps' 2>/dev/null"

pause 2

section "Sync — preview, then upload"
run_cmd "rdc repo sync upload --machine $M --repository my-app --local /tmp/tutorial-src --dry-run"

pause 1

run_cmd "rdc repo sync upload --machine $M --repository my-app --local /tmp/tutorial-src"

pause 2

# Clean up
rm -rf /tmp/tutorial-src /tmp/tutorial-backup
rdc repo down --name my-app --machine "$M" 2>/dev/null || true
rdc repo down --name my-app --machine "$M" --unmount 2>/dev/null || true
rdc repo delete --name my-app --machine "$M" 2>/dev/null || true

printf '\n\033[1;32m# Tutorial complete!\033[0m\n'
sleep 2
