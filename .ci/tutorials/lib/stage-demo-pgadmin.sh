#!/bin/bash
# Idempotently stage the demo-pgadmin repo (postgres + pgAdmin demo app,
# deployed) AND its demo-pgadmin:experiment fork on the tutorial machine.
# Used by the fork-isolation storyboard setupCommand so the pgAdmin browser
# scenes have a live grand and fork at render time.
#
# `repo up` / `repo fork --up` block until the compose healthchecks pass
# (pgAdmin's first boot rebuilds its config DB, ~100s), so when this script
# returns both pgAdmin instances are actually serving — a detached fork
# would race the browser scenes and record a dead page.
#
# Env: TUTORIAL_MACHINE_NAME (default machine-11)

set -euo pipefail
export REDIACC_SKIP_FILE_WRITE_GUARD=1
export REDIACC_SKIP_MACHINE_ACTIVATION=1
M="${TUTORIAL_MACHINE_NAME:-machine-11}"
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../apps/demo-pgadmin" && pwd)"

repos="$(rdc repo list --machine "$M" 2>/dev/null || true)"

if echo "$repos" | grep -q '"demo-pgadmin"'; then
    rdc repo up --name demo-pgadmin --machine "$M" >/dev/null
else
    # The machine may have been re-provisioned since the config last saw this
    # repo: a stale config row would make `repo create` refuse even though the
    # datastore is empty. We only reach this point when the repo is NOT on the
    # machine, so any existing config rows for it are stale by definition.
    rdc config repository remove --name demo-pgadmin >/dev/null 2>&1 || true
    rdc config repository remove --name demo-pgadmin:experiment >/dev/null 2>&1 || true
    rdc repo create --name demo-pgadmin --machine "$M" --size 2G
    rdc repo sync upload --machine "$M" --repository demo-pgadmin --local "$APP_DIR/"
    rdc repo up --name demo-pgadmin --machine "$M"
fi

if echo "$repos" | grep -q '"demo-pgadmin:experiment"'; then
    rdc repo up --name demo-pgadmin:experiment --machine "$M" >/dev/null
else
    if ! rdc repo fork --parent demo-pgadmin --tag experiment --machine "$M" --up; then
        # A live fork of a running parent can copy half-written docker
        # state: stale db/pgadmin container records then block compose
        # create with a name conflict. Clear them and finish with a plain
        # up. If the fork is unusable beyond that, recreate it from
        # scratch (the failed fork leaves repo + config entry behind, so
        # both must be removed before re-forking).
        sleep 5
        rdc term connect -m "$M" -r demo-pgadmin:experiment -c "docker rm -f db pgadmin" || true
        if ! rdc repo up --name demo-pgadmin:experiment --machine "$M"; then
            rdc repo delete --name demo-pgadmin:experiment --machine "$M" || true
            rdc config repository remove --name demo-pgadmin:experiment || true
            rdc repo fork --parent demo-pgadmin --tag experiment --machine "$M" --up
        fi
    fi
fi
