# PLAN: the U1 and U2 upgrade drills bring old-layout daemons up without the job-only CLI

Status: executing
Depends-On: no-dep -- the drills and the job-only CLI are both already on this branch
Owner: d778be9d
Updated: 2026-10-30
Priority: P1 -- vm:check cannot reach VERIFIED while U1 and U2 fail, and every live-proof tick waits on a VERIFIED receipt
Concurrency: parallel
Owns: .ci/rediacc_ci/drills/upgrade_converge.py, .ci/rediacc_ci/drills/converge_preflight.py, .ci/rediacc_ci/tests/drills/**, agent/plans/PLAN-fix-upgrade-drills-flat-daemon-bringup.md
First-Seen: 2026-10-30
Worklist: #96386e54, PR-TASK 9f92c43e

## Finding

U1 (`.ci/rediacc_ci/drills/upgrade_converge.py:320-330`) and U2 (`.ci/rediacc_ci/drills/converge_preflight.py:369-374`) drive the current CLI against a renet built from `0c3a88a^` to get daemons on the pre-isolation layout. Since console 87455a94f every machine command runs as a renet job with no synchronous fallback (`packages/cli/src/services/executor/detached-execution.ts:304`), and the old renet predates the job flags, so "create grand under old renet" fails in every vm:check run since 2026-10-29.

## Boxes

- [ ] F1: The drills bring the old-layout daemons up through a path the old renet supports (design chosen by the writer with evidence and recorded here). Accept: U1 and U2 pass live on the KVM fleet.
- [ ] F2: `npm run vm:check -- --changed` reaches VERIFIED. Accept: the receipt at .ci/cache/vm-check/receipt.json reads VERIFIED for the head tree.
