#!/bin/bash
# Tutorial 12: Monitoring
# Demonstrates rdc machine health, containers, repos, query, and rdc doctor.
# Brings up a small repo first so the queries return non-trivial data.
#
# Prerequisites: shared tutorial config + provisioned worker VM.

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

clear_screen

section "Health — system info"
run_cmd "rdc $C machine query --name $M --system"

pause 2

section "Containers"
run_cmd "rdc $C machine query --name $M --containers"

pause 2

section "Repos"
run_cmd "rdc $C machine query --name $M --repositories"

pause 2

section "Everything in one shot"
run_cmd "rdc $C machine query --name $M"

pause 2

section "Local sanity check"
# `rdc doctor` may exit non-zero in dev mode (subscription / SSH-key checks).
# Tolerate it; the cast captures the report.
run_cmd "rdc doctor || true"

pause 2

# Cleanup
rdc $C repo down --name my-app -m "$M" 2>/dev/null || true
rdc $C repo down --name my-app -m "$M" --unmount 2>/dev/null || true
rdc $C repo delete --name my-app -m "$M" 2>/dev/null || true

printf '\n\033[1;32m# Tutorial complete!\033[0m\n'
sleep 2
