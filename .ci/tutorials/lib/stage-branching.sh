#!/bin/bash
# Idempotently stage the branching demo state (app grand + app:work at v2 +
# stable branch at v1 + app:rollback checked out) on the tutorial machine.
# Used as the tutorial-branching storyboard setupCommand so the VS Code
# side-by-side scene has both forks live at render time.
#
# Env: TUTORIAL_MACHINE_NAME (default machine-11)

set -euo pipefail
export REDIACC_SKIP_FILE_WRITE_GUARD=1
export REDIACC_SKIP_MACHINE_ACTIVATION=1
M="${TUTORIAL_MACHINE_NAME:-machine-11}"

# Pre-start the in-sandbox openvscode server for a repo so the browser scene's
# own `vscode connect --url-only` reuses a warm server (cold start costs ~10s+
# of recorded footage). The tunnel process is killed once the URL prints; the
# server itself keeps running until the storyboard teardown stops it.
prewarm_vscode() {
    local repo="$1" out pid i
    out="$(mktemp)"
    rdc vscode connect --machine "$M" --repository "$repo" --browser --url-only >"$out" 2>/dev/null &
    pid=$!
    for i in $(seq 1 120); do
        grep -q '^http' "$out" 2>/dev/null && break
        kill -0 "$pid" 2>/dev/null || break
        sleep 1
    done
    kill "$pid" 2>/dev/null || true
    wait "$pid" 2>/dev/null || true
    rm -f "$out"
}

list="$(rdc repo list --machine "$M" 2>/dev/null || true)"

if echo "$list" | grep -q "rollback" && echo "$list" | grep -q "work"; then
    rdc repo up --name app:work --machine "$M" >/dev/null 2>&1 || true
    rdc repo up --name app:rollback --machine "$M" >/dev/null 2>&1 || true
    prewarm_vscode app:rollback
    prewarm_vscode app:work
    exit 0
fi

# Reaching here means the staged chain is absent or PARTIAL (interrupted
# run, re-provisioned machine, stale config rows). Tear down whatever
# half-exists on the machine and in the config, then rebuild from scratch.
for r in app:rollback app:work app; do
    rdc repo delete --name "$r" --machine "$M" >/dev/null 2>&1 || true
    rdc config repository remove --name "$r" >/dev/null 2>&1 || true
done
rdc config repository remove --name app:latest >/dev/null 2>&1 || true
rdc repo create --name app --machine "$M" --size 2G
rdc repo template apply --name app-postgres --machine "$M" --repository app

# Rebind the staged stack to its allocated loopback IPs on conflict-free
# ports (5433/3100) so it coexists with whatever else runs on the machine
# (my-app's template binds wildcard 5432/3000). The patch is applied to the
# GRAND right after template apply — `repo create` leaves it mounted, so
# term connect works — and every fork inherits the fixed files, so forks can
# `--up` directly. ${DB_IP}/${SERVICE_IP} resolve per-repo at compose time.
PATCH_B64="$(
    base64 -w0 <<'PATCH'
set -e
sed -i \
    -e 's/listen_addresses=\*/listen_addresses=${DB_IP} -c port=5433/' \
    -e 's#@${DB_IP}:5432/#@${DB_IP}:5433/#' \
    -e 's/-h localhost/-h ${DB_IP} -p 5433/' \
    -e 's/rediacc.service_port=3000/rediacc.service_port=3100/' \
    docker-compose.yml
sed -i \
    -e 's/const PORT = 3000;/const PORT = 3100;/' \
    -e "s/const HOST = '0.0.0.0';/const HOST = process.env.SERVICE_IP || '0.0.0.0';/" \
    app/server.mjs
sync && sync
PATCH
)"
rdc term connect --machine "$M" --repository app --command "echo $PATCH_B64 | base64 -d | bash"
rdc repo fork --parent app --tag work --machine "$M" --up
rdc repo up --name app:work --machine "$M"

# `sync` after each write: repo commit reflink-clones the LUKS image at the
# btrfs level, and a just-written file can still sit in the inner ext4 page
# cache — the clone would then miss it (commit's own syncfs only covers the
# outer filesystem). Double sync settles ext4 -> loop -> btrfs propagation.
rdc term connect --machine "$M" --repository app:work --command 'echo v1 > version.txt && sync && sync'
rdc repo commit --name app:work --message 'v1 baseline' --machine "$M"
rdc repo branch --branch stable --name app:work
rdc term connect --machine "$M" --repository app:work --command 'echo v2 > version.txt && sync && sync'
rdc repo commit --name app:work --message 'v2 risky change' --machine "$M"
rdc repo checkout --ref stable --from app:work --tag rollback --machine "$M"
rdc repo up --name app:rollback --machine "$M"
prewarm_vscode app:rollback
prewarm_vscode app:work
