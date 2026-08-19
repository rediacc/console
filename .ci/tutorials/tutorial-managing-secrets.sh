#!/bin/bash
# Tutorial 08: Managing Secrets
# Walks through env-mode + file-mode secrets, the write-only get, the
# deploy-time proof that both secrets really reach the container, and the
# fork punchline: a fork inherits no secrets and cannot even start the
# same compose.
#
# Prerequisites: shared tutorial config + provisioned worker VM. The demo
# app ships in .ci/tutorials/apps/secrets-demo/.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/tutorial-helpers.sh"

# Silence pre-recording setup so its output doesn't bleed into the cast.
exec 3>&1 4>&2
exec >"$TUTORIAL_SETUP_LOG" 2>&1

M="$TUTORIAL_MACHINE_NAME"
APP_DIR="$SCRIPT_DIR/apps/secrets-demo"

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

rdc repo delete my-app:test --yes 2>/dev/null || true
rdc repo delete my-app --yes 2>/dev/null || true
rdc repo create my-app --machine "$M" --size 2G
# Stage the compose that consumes BOTH secret modes (env interpolation +
# /run/secrets file mount) so the on-camera `repo up` has something real
# to feed.
rdc repo sync upload my-app --local "$APP_DIR/"

# Restore stdout/stderr so asciinema captures only the demo from here on.
exec >&3 2>&4

clear_screen

section "Set an env-mode secret"
run_cmd "rdc repo secret set my-app --key DB_HOST --value postgres.internal --mode env"

pause 2

section "Set a file-mode secret"
run_cmd "rdc repo secret set my-app --key STRIPE_KEY --value sk_test_xxx --mode file"

pause 2

section "List — names and modes only, never values"
run_cmd "rdc repo secret list my-app"

pause 2

section "Get — returns a digest, never the plaintext"
run_cmd "rdc repo secret get my-app --key STRIPE_KEY"

pause 2

section "Rotate when you forget the old value"
run_cmd "rdc repo secret set my-app --key STRIPE_KEY --value sk_test_new --mode file --rotate-secret"

pause 2

section "Deploy — the app consumes both secrets"
run_cmd "rdc repo up my-app"

pause 2

section "Proof — the env secret reaches the container"
run_cmd "rdc term connect my-app --command 'docker exec app printenv DB_HOST'"

pause 2

section "Proof — the file secret is mounted at /run/secrets"
run_cmd "rdc term connect my-app --command 'docker exec app cat /run/secrets/stripe_key'"

pause 2

section "The fork punchline — no secrets follow"
run_cmd "rdc repo fork my-app --tag test"

pause 1

run_cmd "rdc repo secret list my-app:test"

pause 2

section "The fork cannot even start the parent's compose"
# The file secret does not exist under the fork's network ID, so Docker
# refuses the mount. The failure IS the demo: production credentials
# never follow a fork.
run_cmd_expect_fail "rdc repo up my-app:test"

pause 2

# End the on-camera portion; cleanup below is not recorded.
end_recording
# Cleanup
rdc repo delete my-app:test --yes --archive-config -y 2>/dev/null || true
rdc repo down my-app --unmount 2>/dev/null || true
rdc repo delete my-app --yes 2>/dev/null || true
