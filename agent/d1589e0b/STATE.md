## SESSION d1589e0b 2026-09-04T22:45:16Z

# d1589e0b — babysit 0903-1, then merge, then main, then the prod release

## Next action
Read the tail of the `ci-trace.py --wait --until-final` already running on Console
CI run **33925722555** (head 3fe226463). Red: pull the FULL failed-step log via
`gh api repos/rediacc/console/actions/jobs/<id>/logs --allow-escape-sequences`,
fix, `GH_TOKEN=$(gh auth token) npm run ci:quick`, push. Green: `/pr-merge`
(#e9ad31ad). Also uncommitted here: the two hook fixes below, needing their own
ci:quick and push.

## Where the branch is
HEAD == origin/0903-1 == **3fe226463**. Earlier head c5538ac5c was red on parity,
now resolved.

## The parity red, and the trap behind it
Run 33924398787 failed "Validate parity between the local gate set and the CI
quality surface": test-vacuity-floors.sh was tracked with no manifest entry tagged
qualityGateTest. The file was NOT mine — 3049f36cb swept in peer 74de73ca's gate
test, already staged when I committed, while its manifest entry stayed in that
session's uncommitted work.

**Why it looked clean locally: CI checks out TRACKED files only; every local gate
reads the WORKING TREE.** A split between a committed file and an uncommitted one
is invisible to ci:quick by construction.

Repaired forward (never checkout/restore): aea608dd9 `git rm --cached` on that one
path, leaving the file on disk untracked, byte for byte. I did NOT commit their
manifest hunk; I messaged them (#6b21eb94) and they landed both halves in
3fe226463.

## Two bugs found while blocked, both mine, both fixed, both UNCOMMITTED
1. **The harness wrote into the operator's REAL worklist.** `_harness.sh` exported
   WORKLIST_STORE_DIR process-wide but passed TMPDIR per-invocation; the store has
   two halves (writer files from the first, legacy log + markdown + `.lastevent-*`
   from the second). A bare call straddled them and compact() rewrote the real
   legacy file from the union, so three fixture items showed as the operator's open
   work every stop. Fixed `_harness.sh:90`; control case 203 at `26-migrate.sh:430`
   asserts `--path` from a bare call, plus an inverted control.
2. **`--reassign` is blind on any compacted store.** compact() re-emits the fold
   with `by="compact"`, erasing every writer, keeping the owner. The phantom
   backstop and the age gate scanned `by` while the selection matches `owner`, so
   the polluted items were unreachable through EVERY verb: --tick refused them as
   another session's, --reassign as "has written no events at all". One shared
   derivation now: `wl_store.identity_activity` at `wl_store.py:802`. Control: case
   190b ending `18-identity.sh`, compacting FIRST and asserting the erasure before
   testing the verb. All three items ticked; open list clean.

## The three orders, in sequence
1. **#e9ad31ad** green+reviewed+threads resolved, then `/pr-merge`, never by hand.
2. **#dfe46a93** then follow main, fixing DIRECTLY ON MAIN (explicit operator
   override). Pre-diagnosed: main is red from qs/fast-uri advisories already fixed
   here (dad3748d3, 9c4a029d0), so the merge should clear it. Verify, don't assume.
3. **#624e1863** then `gh workflow run "Release to Production" -f force=true`, soak
   skipped. Failure expected; fix the release process. Pre-diagnosed: 6 failures at
   "Assert the edge version is actually released" because on main that step passes
   no env and the R2 probe dies on NoCredentials. This branch already fixes it
   (promote-stable.yml:74-76, assert-edge-tag-exists.sh:90-91), so the NEXT failure
   is the real work.

## Constraints
Peer **74de73ca** is live in this worktree and branch with uncommitted files. Stage
HUNKS not files, especially `scripts/ci-runner/manifest.ts`. **Check `git diff
--cached --stat` before every commit** — skipping it cost this CI round.
`ci-trace.py --wait --until-final` is the only sanctioned CI watch. No
Co-Authored-By/Generated-with trailers; every commit needs `PR-TASK: 24c98380`.
