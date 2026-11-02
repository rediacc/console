# PLAN: the U1 and U2 upgrade drills bring old-layout daemons up without the job-only CLI

Status: executing
Depends-On: no-dep -- the drills and the job-only CLI are both already on this branch
Owner: d778be9d
Updated: 2026-10-30
Priority: P1 -- vm:check cannot reach VERIFIED while U1 and U2 fail, and every live-proof tick waits on a VERIFIED receipt
Concurrency: parallel
Owns: .ci/rediacc_ci/drills/upgrade_converge.py, .ci/rediacc_ci/drills/converge_preflight.py, .ci/rediacc_ci/tests/drills/**, .ci/rediacc_ci/tests/test_drills_upgrade_converge.py, .ci/rediacc_ci/tests/test_drills_converge_preflight.py, agent/plans/PLAN-fix-upgrade-drills-flat-daemon-bringup.md
First-Seen: 2026-10-30
Worklist: #96386e54, PR-TASK 9f92c43e

## Finding

U1 (`.ci/rediacc_ci/drills/upgrade_converge.py:320-330`) and U2 (`.ci/rediacc_ci/drills/converge_preflight.py:369-374`) drive the current CLI against a renet built from `0c3a88a^` to get daemons on the pre-isolation layout. Since console a5f022b2b every machine command runs as a renet job with no synchronous fallback (`packages/cli/src/services/executor/detached-execution.ts:304`), and the old renet predates the job flags, so "create grand under old renet" fails in every vm:check run since 2026-10-29.

## Design

Chosen: candidate (b), the old renet's own `repository up` invoked over ssh, with the CLI kept for what only it can do. `upgrade_converge.OldLayoutBringUp` is shared by U1 and U2:

1. With `renetPath` on the current build, the CLI creates the grand and forks it WITHOUT `--up` (both are renet jobs, which the current renet runs). The CLI alone allocates the guid, network id and credential and records them in the throwaway config.
2. The old binary replaces the slot `/usr/lib/rediacc/renet/current/renet` resolves to, under the provisioner's lock (`install_current_renet_script`). The CLI's own provision used to overwrite that same slot when `renetPath` named the old build, since the dev VERSION is constant. The symlink then points at the old build with the provision cache cleared, so a later CLI provision (U2's `repo sync upload`) verifies the old binary instead of replacing it, and `renet` on the worker is the gate-less old binary for U2's `renet compose -- up -d`.
3. Each fork is started by `sudo renet repository up --name <guid> --datastore <ds> --network-id <N> --repo-name <grand>:<tag> --grand-guid <grand guid> --password-stdin`, the command the old renet's `repository_up` builder composed (renet 7070d28 `pkg/functions/commands/repository.go` RepositoryUpCommand.Build). The credential travels on stdin from a 0600 file, never on argv. The daemons that come up are the old binary's, on the flat layout, as under the old `fork --up`.

Three things the first live runs corrected (2026-10-30): the fork ids come from the config (`resources.repositories.<parent>.tags.<tag>` and `state.repos.<parent>.<tag>.networkId`, `fork_record`), because `repo list` names no network id for a fork that was never started; the install takes the provisioner lock as the ssh user and runs only `install`/`mv` under sudo, because with `fs.protected_regular=2` root cannot open the user-owned `/tmp/.rdc-renet-provision.lock` (rc 66); and each teardown points the symlink back at the current build first, since the deletes are renet jobs. Live proof: `npm run vm:check -- --only U1,U2`, run vmc-10300306-0daa49, 54 assertions, 0 failed, teardown clean (NOT_VERIFIED by design for an `--only` run).

Why not (a): a second CLI from `a5f022b2b^` needs its own bundle build through `prepare-cli` and node_modules, and drifts from the config schema the current CLI writes. Why not (c): (b) works without either. The one difference from the pre-a5f022b2b flow is the grand, whose daemon now starts under the current renet; U1 and U2 assert only on the forks.

Found on the way and fixed: both teardowns left the CLI's `<cfg>.json.bak` copy in ~/.config/rediacc (36 u1-/u2- copies on 2026-10-30, each carrying the gateway E2E key, repo credentials and ssh keys); `config_files` now names it. U2 wrote its config with write-then-chmod; it is now created 0600 from the first byte, as U1's is. The unit tests live at `.ci/rediacc_ci/tests/test_drills_upgrade_converge.py` (the `tests/drills/**` glob in Owns names no existing path).

## Boxes

- [ ] F1: The drills bring the old-layout daemons up through a path the old renet supports (design chosen by the writer with evidence and recorded here). Accept: U1 and U2 pass live on the KVM fleet.
- [ ] F2: `npm run vm:check -- --changed` reaches VERIFIED. Accept: the receipt at .ci/cache/vm-check/receipt.json reads VERIFIED for the head tree.
