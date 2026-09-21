# PLAN: retire rclone, payload and feature
Status: compacted
First-Seen: 2026-09-17
Full-Text: f7a5351a9 agent/PLAN-rclone-decommission.md
Full-Text-Blob: 09c51ce36a58383f4f12ac17ed21fe99cdbcab29
Record-Sig: 859faadb

## Why
The operator asked to stop embedding rclone in the rdc binaries for a smaller artifact, then chose the wider scope and the sequencing: "Full removal, after cutover." The risk this plan existed to manage was a `grep -rl rclone | xargs` sweep, which would have destroyed two things that must live: `rdc storage browse` / `storage import`, which spawn the operator's OWN rclone from PATH
and are the only in-product read path to a ~500 GiB OneDrive archive, and `ops rustfs configure-workers`, which installs rclone on a worker VM and never touches the embedded asset.

## Outcome
SHIPPED. Measured 2026-09-06 against the renet submodule at its current pointer and against this tree. The embedded asset is gone: `pkg/embed/embed.go` and `Dockerfile` contain zero occurrences of rclone, the three `backup_sync*.go` command files are deleted, the embed lockfile and the third-party credits carry none, and `build.sh` gained `_embed_prune_orphans` plus an extra-file
arm on the receipt check so a stale asset cannot pass as current. Console side, the config schema keeps its `storage` kind and refuses at the call site, `--hosted-service` closed the destination-kind gap, and every deliberate survivor above is alive. TWO DEVIATIONS THE PLAN DOES NOT RECORD: `rdc storage prune` was listed under "Dies" but survives, rewired onto the PATH-rclone
browser service; and the standing `strings -a ... | grep -c rclone-linux` assertion the plan demanded was never wired into any gate, so the removal is proven by today's tree and is not pinned against re-embedding.

## Lessons
- The renet landing is a SUBMODULE commit and is deliberately not cited as a hex
token here: a submodule sha does not resolve from this repository and `check:ci-plan-citations` reds on it. Find it by subject, "cold path for the chunk store, and rclone leaves the binary".
- A removal needs a gate as much as a feature does. Nothing in the tree today
would report rclone re-entering the payload.

## Boxes
(this plan carried no checkbox tasks)

## Record
Record-Kind: compacted
Prior-Status: done
Compacted-By: 8f55d4f0
Compacted-At: 2026-09-06T17:08:53Z
Boxes: 0 attested, 0 open, 0 abandoned
Epics: none
Touched: scripts/dev/lib/cf-auth.sh, docs/backup-storage/05-docs-and-decommission.md, packages/shared/src/config-schema/schemas.ts, .ci/scripts/test/gates/test-embed-credits.sh, .ci/scripts/test/gates/test-embed-asset-freshness.sh, scripts/lib/embed-asset-sources.ts, packages/cli/src/data/third-party-credits.json, .gitmodules
Gates: none
Why-Source: author
Read-History: `git show 09c51ce36a58383f4f12ac17ed21fe99cdbcab29` recovers the text; `git log --find-object=09c51ce36a58383f4f12ac17ed21fe99cdbcab29 --all` names the commit

## History
- 2026-09-06T17:08:53Z compacted by 8f55d4f0 from `done` (record-sig 859faadb)
