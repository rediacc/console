#!/bin/bash
# Tutorial 11: Backup & Restore
#
# The honest story, machine to machine: a repository is copied to a second
# machine, the primary goes offline, and the copy is restored into a live
# repository whose data is then read back on camera. `repo push` produces a
# BACKUP ARTIFACT on the destination, not a second live repo (docs/design/
# 06-cli-reshape.md §5); `backup restore` is what turns that artifact into a
# repository under a name.
#
# WHAT REPLACED THE OLD SCRIPT. This used to teach `rdc storage import`,
# `rdc repo push my-app --to my-storage`, `rdc backup list --storage` and
# `rdc repo pull --from my-storage`. The rclone cloud arm was retired, so all
# four now refuse (packages/cli/src/commands/repo-backup.ts:183
# refuseRetiredStorage, and renet's errStorageRetired). None of them is used
# here any more.
#
# WHY THE CHUNK STORE IS NOT DEMONSTRATED END TO END. Point-in-time backup is
# `rdc backup snapshot` (upload) and `rdc backup restore --at` (download), both
# over the content-addressed chunk store. The upload leg mints a storage
# session through the account server and needs an installed repository licence,
# neither of which this harness has -- measured, not assumed:
#
#   rdc backup snapshot my-app --dry-run
#     -> exit 1, {"status":"failed","reason":"no installed repository license"}
#   rdc backup manifests my-app / rdc backup usage
#     -> exit 2, "Subscription token required"
#
# So the chunk store is NAMED on camera with type_only_cmd (typed, never run)
# and its credential-free read side, `rdc backup verify`, is EXERCISED in the
# silenced setup below so the sequence still proves the verb works. Verify is
# not on camera because it prints the CLI JSON envelope by design
# (packages/cli/src/commands/backup-storage.ts:262), which
# validate-tutorial-cast-output.js rejects as raw JSON where a table belongs.
#
# Prerequisites: shared tutorial config + TWO provisioned worker VMs
# (TUTORIAL_MACHINE_IP and TUTORIAL_BACKUP_HOST).

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/tutorial-helpers.sh"

# Silence pre-recording setup so its output doesn't bleed into the cast.
exec 3>&1 4>&2
exec >/dev/null 2>&1

M="$TUTORIAL_MACHINE_NAME"
M2="${TUTORIAL_MACHINE2_NAME:-machine-12}"
M2_IP="${TUTORIAL_BACKUP_HOST:-192.168.111.12}"
M2_USER="${TUTORIAL_BACKUP_USER:-$TUTORIAL_MACHINE_USER}"

# Pre-recording setup
rm -f ~/.config/rediacc/rediacc.json 2>/dev/null || true
rdc config init --ssh-key "$TUTORIAL_SSH_KEY"
rdc machine add "$M" --ip "$TUTORIAL_MACHINE_IP" --user "$TUTORIAL_MACHINE_USER"
rdc machine add "$M2" --ip "$M2_IP" --user "$M2_USER"
for ip in "$TUTORIAL_MACHINE_IP" "$M2_IP"; do
    for i in $(seq 1 30); do
        ssh -i "$TUTORIAL_SSH_KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=2 \
            "$TUTORIAL_MACHINE_USER@$ip" true 2>/dev/null && break
        sleep 2
    done
done
rdc machine setup "$M"
rdc machine setup "$M2"
# Reap any orphaned repo state from previous tutorial runs, on both machines:
# the restored repo lives on $M2 and carries the SOURCE repo's GUID, so a
# half-finished earlier run leaves an image there that no config row addresses.
rdc machine prune "$M" --orphaned-repos --force --grace-days 0 --force-delete-mounted 2>/dev/null || true
rdc machine prune "$M2" --orphaned-repos --force --grace-days 0 --force-delete-mounted 2>/dev/null || true

# Restored repo first: it and my-app share one GUID, and deleting the source
# row first would leave nothing addressing the copy on $M2.
rdc repo delete my-app-restored --yes 2>/dev/null || true
rdc repo delete my-app --yes --archive-config -y 2>/dev/null || true
rdc repo create my-app --machine "$M" --size 2G
rdc repo admin template apply my-app --template app-postgres
rdc repo up my-app --no-start
# The payload the whole tutorial is about. A file, not a database, so the
# survival check on camera is one readable line rather than a psql session.
#
# `sync` is LOAD-BEARING, not hygiene. Without it this tutorial passes most of
# the time and fails silently the rest: `repo push` reflink-snapshots the
# encrypted image, so a write still sitting in the guest page cache travels as
# allocated-but-zero. Measured on run 4 of this rewrite -- step 1 printed the
# line (page cache), and after the restore `cat orders.txt` returned 27 NUL
# bytes, one per character, at exit code 0. Same reason tutorial-delta-transfer
# syncs after its dd.
rdc term connect my-app -c "echo 'order-1042 paid 2026-08-16' > orders.txt && sync"

# The chunk store's credential-free read side, run here rather than on camera
# (see the header). It answers `no-backup` on a repo that has never been
# uploaded, and exits 0 doing so -- a non-zero here means the verb broke.
rdc backup verify my-app

# Restore stdout/stderr so asciinema captures only the demo from here on.
exec >&3 2>&4

clear_screen

section "The data that has to survive"
run_cmd "rdc term connect my-app --command 'cat orders.txt'"

pause 2

section "Step 1: Copy the repository to a second machine"
run_cmd "rdc repo push my-app --to $M2"

pause 2

section "Step 2: The backup machine now holds it"
run_cmd "rdc repo list --machine $M2"

pause 2

section "Step 3: Disaster, the primary goes offline"
run_cmd "rdc repo down my-app --unmount"

pause 2

section "Step 4: Restore the copy into a live repository"
run_cmd "rdc backup restore my-app@$M2 --as my-app-restored --machine $M2 --yes"

pause 2

section "Step 5: Mount it"
run_cmd "rdc repo up my-app-restored --no-start"

pause 2

section "Step 6: The data survived"
run_cmd "rdc term connect my-app-restored --command 'cat orders.txt'"

pause 2

# Point-in-time backup over the chunk store. Typed, never run: the upload leg
# mints a session through the account server, which this recording has no
# credentials for. See the header for the measured refusals.
section "Point-in-time backups go to the chunk store"
type_only_cmd "rdc backup snapshot my-app"

pause 2

# End the on-camera portion; cleanup below is not recorded.
end_recording
# Cleanup. Restored repo first (it owns the copy on $M2 under the shared GUID),
# then the source. Archiving my-app's config row drops it from the config, which
# makes any leftover image on $M2 orphaned for the GUID sweep below.
rdc repo down my-app-restored --unmount 2>/dev/null || true
rdc repo delete my-app-restored --yes 2>/dev/null || true
# my-app is already down and unmounted (step 3 did it on camera); this is only
# the guard for a run that aborted before reaching that step. Observed on a live
# run: this teardown leaves an empty /mnt/rediacc/mounts/<guid>/ holding .envrc
# and .rediacc.json after the delete. 8 KB of metadata, harmless to a re-run
# (the setup prune above sweeps the images), reported as a product defect rather
# than papered over with an rm here.
rdc repo down my-app --unmount 2>/dev/null || true
rdc repo delete my-app --yes --archive-config -y 2>/dev/null || true
rdc machine prune "$M2" --orphaned-repos --force --grace-days 0 --force-delete-mounted 2>/dev/null || true
