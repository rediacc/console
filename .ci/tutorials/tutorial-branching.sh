#!/bin/bash
# Tutorial 15: Branching — Commit & Rollback
# Git-like version history on CoW forks: freeze a working fork into an
# immutable commit, name it with a branch, keep working, then survive a
# real disaster — a dropped database table — by checking the branch out
# into a fresh writable fork. The rollback restores the file AND the
# PostgreSQL data.
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

rdc repo delete --name app:rollback --machine "$M" 2>/dev/null || true
rdc repo delete --name app:work --machine "$M" 2>/dev/null || true
rdc repo delete --name app --machine "$M" 2>/dev/null || true
rdc repo create --name app --machine "$M" --size 2G
rdc repo template apply --name app-postgres --machine "$M" --repository app
# Commits are made from working FORKS; the grand stays pristine.
rdc repo fork --parent app --tag work --machine "$M" --up --detach

# Seed real data: wait for postgres, then create a customers table with
# three rows. The on-camera arc drops this table and the rollback
# restores it.
for i in $(seq 1 60); do
    rdc term connect --machine "$M" --repository app:work \
        --command 'docker exec db pg_isready -q -U app -d app' 2>/dev/null && break
    sleep 2
done
rdc term connect --machine "$M" --repository app:work \
    --command "docker exec db psql -U app -d app -c \"CREATE TABLE customers(id serial PRIMARY KEY, name text); INSERT INTO customers(name) VALUES ('ada'),('grace'),('linus')\""

# Restore stdout/stderr so asciinema captures only the demo from here on.
exec >&3 2>&4

clear_screen

section "Version one of your app state"
# Exec variant adds `sync`: repo commit reflink-clones the LUKS image at
# the btrfs level, and a just-written file can still sit in the inner
# ext4 page cache — the clone would miss it (see lib/stage-branching.sh).
run_cmd "rdc term connect --machine $M --repository app:work --command 'echo v1 > version.txt && cat version.txt'" \
    "rdc term connect --machine $M --repository app:work --command 'echo v1 > version.txt && sync && sync && cat version.txt'"

pause 2

section "Real data lives here too"
run_cmd "rdc term connect --machine $M --repository app:work --command 'docker exec db psql -U app -d app -c \"SELECT count(*) FROM customers\"'"

pause 2

section "Freeze it — an immutable commit"
run_cmd "rdc repo commit --name app:work --message 'v1 baseline' --machine $M"

pause 2

section "Name the commit with a branch"
run_cmd "rdc repo branch --branch stable --name app:work"

pause 2

section "Keep working — version two"
run_cmd "rdc term connect --machine $M --repository app:work --command 'echo v2 > version.txt && cat version.txt'" \
    "rdc term connect --machine $M --repository app:work --command 'echo v2 > version.txt && sync && sync && cat version.txt'"

pause 2

section "Disaster — the risky change drops the table"
run_cmd "rdc term connect --machine $M --repository app:work --command 'docker exec db psql -U app -d app -c \"DROP TABLE customers\"'" \
    "rdc term connect --machine $M --repository app:work --command 'docker exec db psql -U app -d app -c \"DROP TABLE customers\" && sync && sync'"

pause 1

run_cmd_expect_fail "rdc term connect --machine $M --repository app:work --command 'docker exec db psql -U app -d app -c \"SELECT count(*) FROM customers\"'"

pause 2

run_cmd "rdc repo commit --name app:work --message 'v2 risky change' --machine $M"

pause 2

section "The history, like git log"
run_cmd "rdc repo log --name app:work --machine $M"

pause 2

section "Roll back: check the stable branch out"
run_cmd "rdc repo checkout --ref stable --from app:work --tag rollback --machine $M"

pause 1

run_cmd "rdc repo up --name app:rollback --machine $M"

pause 2

section "Proof — the rollback is version one"
run_cmd "rdc term connect --machine $M --repository app:rollback --command 'cat version.txt'"

pause 2

section "And the dropped table is back — all three rows"
# Exec variant waits for postgres to finish crash recovery after the
# fresh fork's first boot before running the same SELECT.
run_cmd "rdc term connect --machine $M --repository app:rollback --command 'docker exec db psql -U app -d app -c \"SELECT count(*) FROM customers\"'" \
    "rdc term connect --machine $M --repository app:rollback --command 'for i in \$(seq 1 30); do docker exec db pg_isready -q -U app -d app && break; sleep 2; done; docker exec db psql -U app -d app -c \"SELECT count(*) FROM customers\"'"

pause 2

# End the on-camera portion; cleanup below is not recorded.
end_recording
# Keep the branching state deployed: the video render stage opens both
# forks in VS Code for the side-by-side beat.
true
