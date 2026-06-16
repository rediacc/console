#!/bin/bash
# Tutorial 13: Fork Isolation
# A live PostgreSQL + pgAdmin app is forked in seconds; the fork is a fully
# independent copy. The terminal cast shows the fork lifecycle; the video
# adds browser scenes (pgAdmin on grand vs fork, side-by-side) driven by the
# storyboard's setupCommand/urlFromCommand hooks at render time.
#
# Prerequisites: shared tutorial config + provisioned worker VM. The demo
# app ships in .ci/tutorials/apps/demo-pgadmin/.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/tutorial-helpers.sh"

# Silence pre-recording setup so its output doesn't bleed into the cast.
exec 3>&1 4>&2
exec >/dev/null 2>&1

M="$TUTORIAL_MACHINE_NAME"
APP_DIR="$SCRIPT_DIR/apps/demo-pgadmin"

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

rdc repo delete --name demo-pgadmin:experiment --machine "$M" 2>/dev/null || true
rdc repo delete --name demo-pgadmin --machine "$M" 2>/dev/null || true
rdc repo create --name demo-pgadmin --machine "$M" --size 2G
rdc repo sync upload --machine "$M" --repository demo-pgadmin --local "$APP_DIR/"
rdc repo up --name demo-pgadmin --machine "$M"

# Restore stdout/stderr so asciinema captures only the demo from here on.
exec >&3 2>&4

clear_screen

section "A live database app"
run_cmd "rdc repo list --machine $M"

pause 2

section "Fork it — a full copy, in seconds"
# --detach: the CoW copy + container start take seconds; pgAdmin's first-boot
# health warmup continues in the background and is not worth 2 minutes of cast.
run_cmd "rdc repo fork --parent demo-pgadmin --tag experiment --machine $M --up --detach"

pause 2

section "Two independent copies, side by side"
run_cmd "rdc repo list --machine $M"

pause 2

section "Done experimenting? Throw the fork away"
run_cmd "rdc repo delete --name demo-pgadmin:experiment --machine $M"

pause 2

# End the on-camera portion; cleanup below is not recorded.
end_recording
# Cleanup — keep the grand deployed: the video render stage forks it again
# for the browser scenes.
rdc config repository remove --name demo-pgadmin:experiment 2>/dev/null || true
