#!/bin/bash
# Tutorial 08: Managing Secrets
# Walks through env-mode + file-mode secrets, the write-only get, and the
# fork-empty proof.
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

rdc $C repo delete --name my-app:test -m "$M" 2>/dev/null || true
rdc $C repo delete --name my-app -m "$M" 2>/dev/null || true
rdc $C repo create --name my-app -m "$M" --size 2G

clear_screen

section "Set an env-mode secret"
run_cmd "rdc $C repo secret set --name my-app --key DB_HOST --value postgres.internal --mode env --current ''"

pause 2

section "Set a file-mode secret"
run_cmd "rdc $C repo secret set --name my-app --key STRIPE_KEY --value sk_test_xxx --mode file --current ''"

pause 2

section "List — names and modes only, never values"
run_cmd "rdc $C repo secret list --name my-app"

pause 2

section "Get — returns a digest, never the plaintext"
run_cmd "rdc $C repo secret get --name my-app --key STRIPE_KEY"

pause 2

section "Rotate when you forget the old value"
run_cmd "rdc $C repo secret set --name my-app --key STRIPE_KEY --value sk_test_new --mode file --rotate-secret"

pause 2

section "The fork punchline — no secrets follow"
run_cmd "rdc $C repo fork --parent my-app --tag test -m $M"

pause 1

run_cmd "rdc $C repo secret list --name my-app:test"

pause 2

# Cleanup
rdc $C repo delete --name my-app:test -m "$M" 2>/dev/null || true
rdc $C repo down --name my-app -m "$M" --unmount 2>/dev/null || true
rdc $C repo delete --name my-app -m "$M" 2>/dev/null || true

printf '\n\033[1;32m# Tutorial complete!\033[0m\n'
sleep 2
