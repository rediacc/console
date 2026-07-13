#!/bin/bash
# Idempotently stage the my-app demo repo (app-postgres template, deployed)
# on the tutorial machine. Used as a storyboard setupCommand so browser
# scenes (VS Code workbench, file tours) have a live repo at render time.
#
# Env: TUTORIAL_MACHINE_NAME (default machine-11)

set -euo pipefail
export REDIACC_SKIP_FILE_WRITE_GUARD=1
export REDIACC_SKIP_MACHINE_ACTIVATION=1
M="${TUTORIAL_MACHINE_NAME:-machine-11}"

if rdc repo list --machine "$M" 2>/dev/null | grep -q "my-app"; then
    # Already present — make sure it is up (idempotent).
    rdc repo up my-app >/dev/null 2>&1 || true
    exit 0
fi

# The machine may have been re-provisioned since the config last saw this
# repo: a stale config row would make `repo create` refuse even though the
# datastore is empty. We only reach this point when the repo is NOT on the
# machine, so any existing config rows for it are stale by definition.
# `repo delete --archive-config` drops the row; the machine-side delete is
# idempotent, so an already-absent image is not an error.
rdc repo delete my-app --archive-config -y >/dev/null 2>&1 || true
rdc repo create my-app --machine "$M" --size 2G
rdc repo admin template apply my-app --template app-postgres
rdc repo up my-app
