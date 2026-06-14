#!/bin/bash
# Tutorial 14: VS Code in the Browser + Sandbox Isolation
# `rdc vscode connect --browser` serves VS Code from inside the repo
# sandbox — no local install, works from any OS. The same kernel sandbox
# that guards `rdc term` guards the editor: the file tree and the
# integrated terminal end at the repo's walls.
#
# Prerequisites: shared tutorial config + provisioned worker VM.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/tutorial-helpers.sh"

# Silence pre-recording setup so its output doesn't bleed into the cast.
exec 3>&1 4>&2
exec >/dev/null 2>&1

M="$TUTORIAL_MACHINE_NAME"

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

rdc repo delete --name my-app --machine "$M" 2>/dev/null || true
rdc repo create --name my-app --machine "$M" --size 2G
rdc repo template apply --name app-postgres --machine "$M" --repository my-app
rdc repo up --name my-app --machine "$M"

# Pre-warm the browser VS Code server: the first connect downloads the
# server release onto the machine (~80 MB). The on-camera connect below
# then reuses the running server and is ready in seconds.
rdc vscode connect --machine "$M" --repository my-app --browser --url-only &
PREWARM_PID=$!
sleep 60
kill -INT "$PREWARM_PID" 2>/dev/null || true
wait "$PREWARM_PID" 2>/dev/null || true

# Restore stdout/stderr so asciinema captures only the demo from here on.
exec >&3 2>&4

clear_screen

section "VS Code from any browser — no install"
run_cmd_interrupt "rdc vscode connect --machine $M --repository my-app --browser --no-open" 8

pause 2

section "The editor lives INSIDE the repo sandbox"
run_cmd "rdc term connect --machine $M --repository my-app --command 'pwd && ls'"

pause 2

# The video's browser scene creates notes/todo.md inside the editor at render
# time. For the cast we seed the same file silently so the round-trip step
# below always has something to show, regardless of scene ordering.
rdc term connect --machine "$M" --repository my-app --command 'mkdir -p notes && printf "%s\n" "- ship the demo" "- write the report" > notes/todo.md' >/dev/null 2>&1

section "Files made in the browser are real repo files"
run_cmd "rdc term connect --machine $M --repository my-app --command 'cat notes/todo.md'"

pause 2

section "Try to leave the repo — the kernel says no"
run_cmd_expect_fail "rdc term connect --machine $M --repository my-app --command 'ls /'"

pause 2

run_cmd_expect_fail "rdc term connect --machine $M --repository my-app --command 'ls /home'"

pause 2

# End the on-camera portion; cleanup below is not recorded.
end_recording
# Cleanup — keep my-app deployed: the video render stage serves VS Code
# from it for the browser scenes.
rdc vscode serve stop --machine "$M" --repository my-app 2>/dev/null || true
