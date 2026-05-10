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

M="$TUTORIAL_MACHINE_NAME"
C="--config tutorial"
BASE_DOMAIN="${TUTORIAL_BASE_DOMAIN:-test.local}"
CERT_EMAIL="${TUTORIAL_CERT_EMAIL:-admin@test.local}"
CF_TOKEN="${TUTORIAL_CF_DNS_TOKEN:-dummy-token-for-recording}"

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

rdc $C repo delete --name infra -m "$M" 2>/dev/null || true

clear_screen

section "Step 2: Configure infrastructure on rdc"
run_cmd "rdc $C config infra set -m $M --public-ipv4 $TUTORIAL_MACHINE_IP --base-domain $BASE_DOMAIN --cert-email $CERT_EMAIL --cf-dns-token $CF_TOKEN"

pause 2

run_cmd "rdc $C config infra show -m $M"

pause 2

section "Step 3: Push it to the server"
# Push will fail against dummy DNS token; allow that in the recording.
run_cmd "rdc $C config infra push -m $M || true"

pause 2

section "Step 4: Deploy the proxy"
run_cmd "rdc $C repo create --name infra -m $M --size 1G"

pause 1

# `single-service` is the closest in-tree template to what users would author
# as their own `proxy` template (Traefik + secrets). The recording stands in
# for the user-supplied proxy template described in the docs.
run_cmd "rdc $C repo template apply --name single-service -m $M -r infra || true"

pause 1

run_cmd "rdc $C repo up --name infra -m $M || true"

pause 2

# Cleanup
rdc $C repo down --name infra -m "$M" 2>/dev/null || true
rdc $C repo down --name infra -m "$M" --unmount 2>/dev/null || true
rdc $C repo delete --name infra -m "$M" 2>/dev/null || true

printf '\n\033[1;32m# Tutorial complete!\033[0m\n'
sleep 2
