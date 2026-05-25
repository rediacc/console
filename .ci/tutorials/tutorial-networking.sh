#!/bin/bash
# Tutorial 09: Networking & Domains
# Demonstrates rdc config infra set / push and the proxy template apply. The
# tutorial uses a `.local` domain + dummy Cloudflare token so it runs without
# touching real DNS — operators recording for production should pass real
# values via TUTORIAL_BASE_DOMAIN / TUTORIAL_CF_DNS_TOKEN.
#
# Prerequisites: shared tutorial config + provisioned worker VM.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/tutorial-helpers.sh"

# Silence pre-recording setup so its output doesn't bleed into the cast.
exec 3>&1 4>&2
exec >/dev/null 2>&1

M="$TUTORIAL_MACHINE_NAME"
BASE_DOMAIN="${TUTORIAL_BASE_DOMAIN:-test.local}"
CERT_EMAIL="${TUTORIAL_CERT_EMAIL:-admin@test.local}"
CF_TOKEN="${TUTORIAL_CF_DNS_TOKEN:-dummy-token-for-recording}"

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

rdc repo delete --name infra --machine "$M" 2>/dev/null || true

# Restore stdout/stderr so asciinema captures only the demo from here on.
exec >&3 2>&4

clear_screen

section "Step 2: Configure infrastructure on rdc"
run_cmd "rdc config infra set --machine $M --public-ipv4 $TUTORIAL_MACHINE_IP --base-domain $BASE_DOMAIN --cert-email $CERT_EMAIL --cf-dns-token $CF_TOKEN"

pause 2

run_cmd "rdc config infra show --machine $M"

pause 2

section "Step 3: Push it to the server"
# Push will fail against dummy DNS token; allow that in the recording.
run_cmd "rdc config infra push --machine $M || true"

pause 2

section "Step 4: Deploy the proxy"
run_cmd "rdc repo create --name infra --machine $M --size 1G"

pause 1

# `single-service` is the closest in-tree template to what users would author
# as their own `proxy` template (Traefik + secrets). The recording stands in
# for the user-supplied proxy template described in the docs.
run_cmd "rdc repo template apply --name single-service --machine $M --repository infra || true"

pause 1

run_cmd "rdc repo up --name infra --machine $M || true"

pause 2

# Cleanup
rdc repo down --name infra --machine "$M" 2>/dev/null || true
rdc repo down --name infra --machine "$M" --unmount 2>/dev/null || true
rdc repo delete --name infra --machine "$M" 2>/dev/null || true

printf '\n\033[1;32m# Tutorial complete!\033[0m\n'
sleep 2
