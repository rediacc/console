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

M="$TUTORIAL_MACHINE_NAME"
C="--config tutorial"

# Pre-recording setup
rm -f ~/.config/rediacc/tutorial.json 2>/dev/null || true
rdc config init --name tutorial --ssh-key "$TUTORIAL_SSH_KEY"
rdc --config tutorial config machine add --name "$M" --ip "$TUTORIAL_MACHINE_IP" --user "$TUTORIAL_MACHINE_USER"
for i in $(seq 1 30); do
    ssh -i "$TUTORIAL_SSH_KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=2 \
        "$TUTORIAL_MACHINE_USER@$TUTORIAL_MACHINE_IP" true 2>/dev/null && break
    sleep 2
done
rdc --config tutorial config machine setup --name "$M"
# Reap any orphaned repo state from previous tutorial runs.
rdc --config tutorial machine prune --name "$M" --orphaned-repos --force --grace-days 0 --force-delete-mounted 2>/dev/null || true

rdc $C repo delete --name my-app -m "$M" 2>/dev/null || true
rdc $C repo create --name my-app -m "$M" --size 2G
rdc $C repo template apply --name app-postgres -m "$M" -r my-app
rdc $C repo up --name my-app -m "$M"

mkdir -p /tmp/tutorial-src && echo "<h1>Hello</h1>" >/tmp/tutorial-src/index.html
mkdir -p /tmp/tutorial-backup

clear_screen

section "Tunnel — open the app in your browser"
# Tunnel is long-running. Show the command running for ~2s then stop it.
run_cmd "timeout 2s rdc $C repo tunnel -m $M -r my-app -c app || true"

pause 2

section "Term — run a command inside the repo"
run_cmd "rdc $C term connect -m $M -r my-app -c 'docker ps'"

pause 2

section "Sync — preview, then upload"
run_cmd "rdc $C repo sync upload -m $M -r my-app --local /tmp/tutorial-src --dry-run"

pause 1

run_cmd "rdc $C repo sync upload -m $M -r my-app --local /tmp/tutorial-src"

pause 2

# Clean up
rm -rf /tmp/tutorial-src /tmp/tutorial-backup
rdc $C repo down --name my-app -m "$M" 2>/dev/null || true
rdc $C repo down --name my-app -m "$M" --unmount 2>/dev/null || true
rdc $C repo delete --name my-app -m "$M" 2>/dev/null || true

printf '\n\033[1;32m# Tutorial complete!\033[0m\n'
sleep 2
