# PLAN: read-only rdc verbs never provision renet
Status: executing
Owner: d778be9d
Updated: 2026-09-24

Lead's rulings: every recommendation accepted; sessions (rows 2, 4, 5, 7) are `'read-only'`; `REDIACC_ALLOW_DIRTY_RENET` is yes; box 23 (commit) belongs to the babysitter.

## Finding

`provisionRenetToRemote` (`/home/developer/console/packages/cli/src/services/renet/renet-execution.ts:80-120`) has no read-only mode. Every caller runs `renetProvisioner.provision()` (`packages/cli/src/services/renet/renet-provisioner.ts:219`), which does the following:

- **Upload.** It hashes the local binary and uploads it whenever the remote hash differs (`packages/cli/src/services/renet/renet-provisioner.ts:310-315`, `stageRenetBinary`). In dev mode the local binary is `private/renet/bin/renet`, rebuilt by `ensure_renet_built` (`.ci/lib/local-common.sh:759`) from whatever is in the working tree, dirty or not.
- **Swap.** It always runs the locked install (`installWithRemoteLock`, `:608`). That moves the binary into `/usr/lib/rediacc/renet/<VERSION>/renet`, repoints `current` (`:677`) and repoints `/usr/bin/renet` (`:684`).
- **Restart.** It restarts `rediacc-router` whenever `currentUpdated` (`:329`). That is true after an upload, and also when only the `current` pointer moved.
- **Weak opt-out.** `REDIACC_SKIP_ROUTER_RESTART=1` only affects the restart flag (`packages/cli/src/services/renet/renet-execution.ts:94-95`). The upload and both symlink swaps still happen. Everything that runs `/usr/bin/renet` or `current` then runs the new binary, including `sandbox-gateway`, the autostart timers and the backup units. So the env var does not make production safe.
- **Live path.** `machine status` goes through `gatherStatus` (`packages/cli/src/commands/machine/status.ts:627-655`). That calls both `fetchMachineStatus` (`packages/cli/src/services/machine/machine-status.ts:79`) and `fetchRepoLicenseDetail` (`packages/cli/src/services/machine/machine-status.ts:155`), and each of those provisions.

The grep for `provisionRenetToRemote(` returns 17 lines: the definition (`packages/cli/src/services/renet/renet-execution.ts:80`) plus **16 call sites**. Four of them are shared wrappers that serve both read-only and mutating verbs: `connectForJobs`, `resolveMachineContext`, `prepareSyncConnection` → `ensureRenetProvisioned`, and the executor's `provisionAndVerify`.

Read paths already tolerate a different renet version:
- `isListResult` only needs one known top-level key (`packages/shared/src/renet-contract/data/list-types.generated.ts:349-363`).
- `fetchRepoLicenseDetail` is documented as best-effort against older renet and returns `[]` on any error (`packages/cli/src/services/machine/machine-status.ts:145-147, 170-172`).
- `backup status` only runs `systemctl is-active` (`packages/cli/src/commands/backup-ops.ts:256`). It never uses the renet path it provisions (`packages/cli/src/commands/backup-ops.ts:316`).
- The executor already warns on version skew and carries on (`packages/cli/src/services/executor/local-executor.ts:2007-2009`, `versionSkewWarning`).

## Design

### Recommendation

1. **One entry point with a required access argument.** Replace `provisionRenetToRemote` with `acquireRemoteRenet(access: RenetAccess, config, machine, sshPrivateKey, options, sftp?)`, where `type RenetAccess = 'read-only' | 'provision'`.
   - `access` is the first positional parameter, not a field in the options bag. An options bag invites `{}`, and `{}` is exactly how today's 16 sites got the default.
   - The old name is deleted, not aliased (clean break). tsc then flags every site and every test mock until each one declares its access.
   - The return type becomes `{ remotePath: string; uploaded: boolean; drift: RenetDrift | null }`.

2. **`'read-only'` uses a new method, `renetProvisioner.inspect()`.** It shares only the pure helpers with `provision()`: `resolveArch`, `computeLocalHash`, `getRemoteHashAndVersion`, and the cache lookups. It never reaches `stageRenetBinary`, `installWithRemoteLock`, `restartRunningServices` or the local provision lock.
   - It runs one SSH exec that reads hash and version for the versioned slot (`REMOTE_INSTALL_PATH`) and for `current`.
   - `remotePath` is the versioned slot if it exists, otherwise `current`.
   - A fresh in-memory or persisted provision-state entry still short-circuits with zero SSH. Recording a proven match in provision-state is allowed, because that is a local write only.

3. **Drift policy for read-only verbs: warn and run the remote binary as-is. Fail only when there is nothing to run.**
   - Missing binary: throw `renet is not installed on <machine>; run 'rdc machine setup <machine>' to provision it`.
   - Different hash or version: `outputService.warn(...)`, which goes to stderr and into the JSON `warnings` array (`packages/cli/src/services/core/output.ts:349-353, 174-180`). The message names the machine, the remote version and short hash, the local version and short hash, and "run `rdc machine setup <machine>` or any mutating command to update". Print it once per host per process.
   - Why warn rather than fail:
     - None of the status-style readers depend on a version match (see Finding).
     - Operators run `machine status` precisely to decide whether to deploy. Failing on drift would blind it on every machine after each CLI update.
     - A really incompatible remote still fails loudly on its own (for example "renet list all failed"), now with the drift line printed just before it.

4. **The executor decides per function, from one exhaustive table.** Add `RENET_FUNCTION_ACCESS: Record<RenetFunctionName, RenetAccess>` (new file `services/executor/renet-function-access.ts`).
   - Because it is a `Record` over the generated union, a new renet function breaks tsc until someone classifies it.
   - `provisionAndVerify` (`packages/cli/src/services/executor/local-executor.ts:2031`) calls `acquireRemoteRenet(renetAccessFor(options.functionName), ...)`.
   - Names outside the contract map to `'read-only'`. The safe default is to never swap the binary for something unclassified.
   - No new field on `ExecuteOptions`, so the daemon wire protocol (`packages/cli/src/services/executor/daemon/protocol.ts:30`) is untouched.
   - Read-only functions: `backup_browse, backup_list, backup_verify, ceph_clone_list, ceph_image_info, ceph_image_list, ceph_snapshot_list, container_inspect, container_list, container_logs, container_stats, kube_health, kube_kubeconfig, machine_ping, machine_ssh_test, machine_version, repository_autostart_list, repository_cat, repository_diff, repository_health, repository_info, repository_list, repository_log, repository_logs, repository_policy_get, repository_status, repository_validate`.
   - Everything else is `'provision'`. That includes `container_exec` and `repository_exec`, because they run arbitrary commands.

5. **Uploading a binary built from a dirty tree needs an explicit opt-in: yes.** Use `REDIACC_ALLOW_DIRTY_RENET=1`.
   - Reason: that is exactly what reached production here. With one operator, committing is cheap and makes every deployed hash traceable to a commit. It also matches what `private/renet/CLAUDE.md:138` already promises ("once a renet source change is committed locally...").
   - Where the check runs: `provision()` gets an `uploadGuard` callback, invoked only when `remote.hash !== localHash`, just before `stageRenetBinary` (`packages/cli/src/services/renet/renet-provisioner.ts:310`). A no-op provision on a dirty tree therefore never pays for or trips the check.
   - What `acquireRemoteRenet` passes as the guard (dev mode, when `localBinaryPath` is set):
     1. Run `git -C <dirname(bin)> rev-parse --show-toplevel`, then `git -C <top> status --porcelain`.
     2. Include untracked files, because Go compiles untracked `.go` files. `bin/` is already gitignored.
     3. If the tree is dirty, throw and list up to 10 paths plus the opt-in.
     4. If the binary is not in a git work tree (SEA, or a release binary on PATH), allow the upload.
   - SEA builds skip the check entirely.
   - This is an env var, not a flag. A flag costs 13 locales and a contract regeneration, per the precedent at `packages/cli/src/services/renet/renet-provisioner.ts:79-83`.
   - Known limit: a stale binary built dirty and then stashed away is not caught here. `ensure_renet_built` rebuilds on the next `./rdc.sh`, so the gap only exists when calling the bundle directly.

6. **Delete the `backup status` call (`packages/cli/src/commands/backup-ops.ts:314-318`) rather than switching it to read-only.** Its result is discarded, and its comment "needed for SSH connection" is wrong: `machineConnections.acquireFor` at `:320` does the SSH.

7. **Guarantees.**
   - Type level: `access` is required, and the function table is exhaustive.
   - Test level: a ledger test uses the TypeScript compiler API to parse `src/**` and pin every access-bearing call site to its declared access. It also asserts that `renetProvisioner.provision(` appears only in `renet-execution.ts`, so nobody can bypass the entry point.

### Rejected alternatives

- **Optional `mode` defaulting to `'provision'`.** It keeps the silent default that caused this. Rejected.
- **Two exported functions (`provisionRenet` / `inspectRemoteRenet`).** Equally safe for literal sites. But four wrappers choose access at runtime, so each would need an `if` that duplicates the call. A typed union forwards cleanly. (Internally the two paths are still separate methods.)
- **Opt-out env var or flag (`REDIACC_SKIP_RENET_PROVISION`).** It is a convention, the default stays dangerous, and it has the same shape as the `SKIP_ROUTER_RESTART` that already failed.
- **Upload but skip the restart.** That is the current behaviour. The symlink swaps at `packages/cli/src/services/renet/renet-provisioner.ts line 677-684 (blob cec6a875d9fa)` change what production runs even without a restart.
- **Fail on any drift for read-only verbs.** Rejected; see point 3. Only a missing binary fails.
- **A process-global "read-only command" flag set from commander metadata (the MCP `isDestructive` classification).** The executor daemon runs many commands in one process, and mutating verbs contain internal read steps, so a global flag is the wrong granularity.

## Call-site table

Line numbers are verified against the current tree. "Fwd" means the wrapper forwards an `access` parameter that its callers must supply.

| # | Site (file:line) | Enclosing fn | Verb(s) | Class | Access after fix |
|---|---|---|---|---|---|
| 1 | `packages/cli/src/commands/repo-sync.ts:52` | `ensureRenetProvisioned` (via `prepareSyncConnection` :184/:189) | `repo sync upload` (:332) / `download` (:440) / `status` (:586, dry-run download) | MIXED → Fwd | upload `'provision'`; download and status `'read-only'` |
| 2 | `packages/cli/src/commands/repo-tunnel.ts:217` | `tunnelConnect` (:150) | `repo tunnel` | READ-ONLY (session) | `'read-only'` |
| 3 | `packages/cli/src/commands/subscription-actions.ts:79` | `resolveMachineContext` (:74) | `subscription status -m` (:328), `subscription refresh -m` (:365 via `resolveSubscriptionCommandContext` :89-98) | MIXED → Fwd | status `'read-only'`; refresh `'provision'` (hard-code inside `resolveSubscriptionCommandContext`) |
| 4 | `packages/cli/src/commands/vscode-browser.ts:86` | `prepareBrowserConnection` (:66) | `vscode browser` | READ-ONLY (session) | `'read-only'` |
| 5 | `packages/cli/src/commands/vscode.ts:183` | `provisionAndPrepare` (:171) | `vscode connect` | READ-ONLY (session) | `'read-only'` (rename fn to `prepareRemote`) |
| 6 | `packages/cli/src/services/provision/infra-provision.ts:368` | `pushInfraConfig` (:348) | `machine infra push`, machine add, tofu/cluster provision | MUTATING | `'provision'` |
| 7 | `packages/cli/src/commands/term.ts:289` | `connectTerminal` (:262) | `term connect` | READ-ONLY (session) | `'read-only'` |
| 8 | `packages/cli/src/services/executor/job-remote.ts:105` | `connectForJobs` (:99) | `job list` (packages/cli/src/commands/job.ts:119), `status` (:140), `logs` (:205), serve job-logs (packages/cli/src/services/serve/server.ts:310); `job cancel` (:254), `gc` (:288) | MIXED → Fwd (also `withJobConnection` packages/cli/src/commands/job.ts:55) | list/status/logs/serve `'read-only'`; cancel/gc `'provision'` |
| 9 | `packages/cli/src/services/renet/machine-bootstrap.ts:48` | `bootstrapMachine` (:39) | provision/bootstrap | MUTATING | `'provision'` |
| 10 | `packages/cli/src/services/machine/machine-status.ts:79` | `fetchMachineStatus` (:54) | `machine status`, `machine health` (packages/cli/src/services/state.ts:114), repo tunnel (:174), URL print (packages/cli/src/commands/repo-batch-utils.ts:227), prune listing (packages/cli/src/commands/machine/prune.ts:236, :304), config (packages/cli/src/commands/config.ts line 296 (blob 597383d13bca)), reconcile (packages/cli/src/services/config/config-reconcile.ts:303) | READ-ONLY (always a read step) | `'read-only'` |
| 11 | `packages/cli/src/services/machine/machine-status.ts:155` | `fetchRepoLicenseDetail` (:149) | `machine status` licenses | READ-ONLY | `'read-only'` |
| 12 | `packages/cli/src/commands/machine/register.ts:280` | `registerSetup` action (:262) | `machine setup` | MUTATING | `'provision'` |
| 13 | `packages/cli/src/commands/backup-ops.ts:146` | `runBackupNow` (:109) | `backup run` | MUTATING | `'provision'` |
| 14 | `packages/cli/src/commands/backup-ops.ts:316` | `showBackupStatus` (:300) | `backup status` | READ-ONLY | **delete the call** (result unused) |
| 15 | `packages/cli/src/services/backup/backup-schedule.ts:115` | `preDeployProvisioning` (:102; dry-run already returns early :108-113) | `backup schedule` push | MUTATING | `'provision'` |
| 16 | `packages/cli/src/services/executor/local-executor.ts:2031` | `provisionAndVerify` (:2021) | every bridge-function dispatch (`repo up/down/...`, `repo list`, `storage` :42/:102, `repo logs`, etc.) | MIXED (dispatcher) | `renetAccessFor(options.functionName)` from `RENET_FUNCTION_ACCESS` |

Decision point for the operator: rows 2, 4, 5 and 7 are access sessions. They deploy a per-repo key but by intent change nothing else, and they are classed read-only (the lead confirmed it). Flipping any of them is a one-token change, and the ledger test will demand that the change be deliberate.

## Boxes

- [x] 1. `renet-provisioner.ts`: add a public `inspect(config, { localBinaryPath }, sftp?)`. It returns `{ arch, remotePath | null, remoteHash, remoteVersion, localHash, drift: 'none' | 'hash' | 'version' | 'missing' }`. Its single SSH exec probes `REMOTE_INSTALL_PATH` (:56) and `REMOTE_CURRENT_PATH` (:46). It reuses `resolveArch`, `computeLocalHash` and `getRemoteHashAndVersion` (:530), plus the cache fast path from `provision()` (:228-250). It takes no local lock and makes no `stageRenetBinary`, `installWithRemoteLock` or `restartRunningServices` call.
    (ticked) 2026-09-24T07:55:16Z by d778be9d: inspect() added, read-only; 4 inspect tests green; mutation 5 (inspect->doProvision) red then restored (packages/cli/src/services/renet/renet-provisioner.ts:197)
- [x] 2. `renet-provisioner.ts`: add an optional `uploadGuard?: () => void | Promise<void>` to the `provision` and `doProvision` options. Invoke it inside `if (remote.hash !== context.localHash)` (:310) before `stageRenetBinary`.
    (ticked) 2026-09-24T07:55:17Z by d778be9d: uploadGuard wired before staging; 3 guard tests green; mutation 7a red then restored (packages/cli/src/services/renet/renet-provisioner.ts:297)
- [x] 3. `renet-execution.ts`: export `type RenetAccess` and `acquireRemoteRenet(access, ...)`. Delete `provisionRenetToRemote` (:80-120) with no alias. The read-only branch calls `inspect`: it throws on `missing` with the `rdc machine setup <name>` message, and warns once per host (module-level `Set`) on drift. The provision branch keeps today's restart logic (:94-95) and passes `uploadGuard: () => assertRenetSourceClean(localBinaryPath, machine)` when `localBinaryPath` is set.
    (ticked) 2026-09-24T07:55:17Z by d778be9d: RenetAccess + acquireRemoteRenet exported, old name gone (grep empty); renet-access.test 7/7; mutation 4 red (packages/cli/src/services/renet/renet-execution.ts:177)
- [x] 4. `renet-execution.ts`: implement `assertRenetSourceClean` using `execFileSync('git', ...)`, as described in Design point 5 and honouring `REDIACC_ALLOW_DIRTY_RENET`. The error lists up to 10 porcelain paths and the target machine IP.
    (ticked) 2026-09-24T07:55:17Z by d778be9d: dirty-tree guard lists up to 10 paths plus machine IP; dirty and clean tests green; mutation 7b red (packages/cli/src/services/renet/renet-execution.ts:107)
- [x] 5. New `services/executor/renet-function-access.ts`: `RENET_FUNCTION_ACCESS` (`Record<RenetFunctionName, RenetAccess>`) and `renetAccessFor(name: string): RenetAccess` (unknown names → `'read-only'`). Wire it into `packages/cli/src/services/executor/local-executor.ts:2031`. Rename the `options` argument there so that `skipRouterRestart`/`debug` still pass through.
    (ticked) 2026-09-24T07:55:17Z by d778be9d: 27 read-only functions, rest provision; renet-function-access.test 4/4; mutation 3 red then restored (packages/cli/src/services/executor/renet-function-access.ts:17)
- [x] 6. Sites 6, 9, 12, 13, 15: pass `'provision'`.
    (ticked) 2026-09-24T07:55:18Z by d778be9d: all 5 mutating sites pass 'provision', pinned in renet-access-ledger.test (packages/cli/src/services/provision/infra-provision.ts:369)
- [x] 7. Sites 2, 4, 5, 7, 10, 11: pass `'read-only'`. Update the flow comment at `packages/cli/src/services/machine/machine-status.ts:45-53`, step 2 ("Resolve remote renet (read-only, never uploads)"), and the debug message at :69-71.
    (ticked) 2026-09-24T07:55:18Z by d778be9d: 6 session/status sites read-only, flow comment and debug text updated; mutation 1 red then restored (packages/cli/src/services/machine/machine-status.ts:80)
- [x] 8. Site 14: delete `packages/cli/src/commands/backup-ops.ts:314-318`. Keep the `Connecting to` info line.
    (ticked) 2026-09-24T07:55:18Z by d778be9d: backup status call deleted with its unused debug param; ledger asserts none; mutation 6 red (packages/cli/src/commands/backup-ops.ts:311)
- [x] 9. Site 8: change `connectForJobs(machineName, access: RenetAccess)` and `withJobConnection(machineName, access, fn)` in `packages/cli/src/commands/job.ts:55`. Pass `'read-only'` at packages/cli/src/commands/job.ts:119, :140, :205 and packages/cli/src/services/serve/server.ts:310, and `'provision'` at :254 and :288. Rewrite the doc comment at `packages/cli/src/services/executor/job-remote.ts:92-98`: an untouched machine now fails `job list` with the setup hint.
    (ticked) 2026-09-24T07:55:18Z by d778be9d: job paths declare access, doc comment rewritten; ledger pins them; mutation 2 red then restored (packages/cli/src/services/executor/job-remote.ts:104)
- [x] 10. Site 3: `resolveMachineContext(machineName, access)`. `executeMachineStatus` (:328) passes `'read-only'`, and `resolveSubscriptionCommandContext` (:98) passes `'provision'`.
    (ticked) 2026-09-24T07:55:18Z by d778be9d: subscription access split; subscription.test asserts both, 19/19 green (packages/cli/src/commands/subscription-actions.ts:337)
- [x] 11. Site 1: `ensureRenetProvisioned(machineName, access)` and `prepareSyncConnection(validated, remoteSubPath, opts & { access })`. `syncUpload` (:332) passes `'provision'`. `syncDownload` (:440) passes `'read-only'`, which also covers `sync status` (:586). Keep the non-fatal `catch` for both.
    (ticked) 2026-09-24T07:55:19Z by d778be9d: sync access split, non-fatal catch kept; pinned in the ledger (packages/cli/src/commands/repo-sync.ts:448)
- [x] 12. Rename the mocks in 6 existing test files: `packages/cli/src/services/executor/__tests__/detached-jobs.test.ts:113`, `packages/cli/src/commands/__tests__/subscription.test.ts:117`, `packages/cli/src/services/__tests__/local-executor.test.ts:100`, `packages/cli/src/services/__tests__/local-executor-license-size.test.ts:96`, `packages/cli/src/services/__tests__/local-executor-restore-license.test.ts:111`, `packages/cli/src/services/__tests__/backup-schedule.test.ts:48`. Also `packages/cli/src/services/__tests__/machine-status.test.ts:35`.
    (ticked) 2026-09-24T07:55:19Z by d778be9d: mocks renamed in 7 test files; all green in the full CLI suite (packages/cli/src/services/__tests__/local-executor.test.ts:100)
- [x] 13. Test `renet-provisioner.test.ts`, new `describe('inspect (read-only)')`:
    (ticked) 2026-09-24T07:55:19Z by d778be9d: renet-provisioner.test 45/45; mutations 5 and 7a red then restored (packages/cli/src/services/__tests__/renet-provisioner.test.ts:758)
  - With a hash mismatch: assert that no `sftp.exec` argument matches `/mv -f|ln -s|systemctl|flock|mkdir/`, and that a mocked `renet-binary-transfer.js` `stageRenetBinary` has zero calls.
  - Missing → `drift: 'missing', remotePath: null`.
  - Versioned slot absent but `current` present → `remotePath` ends `current/renet`.
  - `uploadGuard` is called on a mismatch and not on a match; a throwing guard means no staging.
  - Fires if `inspect` delegates to `doProvision`, or if the guard moves outside the mismatch branch.
- [x] 14. Test new `src/services/__tests__/renet-access.test.ts` (mock the `renetProvisioner` singleton, `outputService`, and `node:child_process`):
    (ticked) 2026-09-24T07:55:19Z by d778be9d: renet-access.test 7/7; mutations 4 and 7b red then restored (packages/cli/src/services/__tests__/renet-access.test.ts:61)
  - `'read-only'` calls `inspect` and never `provision`.
  - Drift warns once, and the text contains the machine, both versions and `rdc machine setup`.
  - Missing rejects with `rdc machine setup`.
  - `'provision'` calls `provision` with `restartServices: true`.
  - A dirty porcelain makes the guard throw and name `REDIACC_ALLOW_DIRTY_RENET`; with the env set it passes.
  - The read-only path never spawns git.
- [x] 15. Test `machine-status.test.ts`: assert `mockAcquire.mock.calls[0][0] === 'read-only'` for both `fetchMachineStatus` and `fetchRepoLicenseDetail`.
    (ticked) 2026-09-24T07:55:20Z by d778be9d: machine-status.test green; mutation 1 turns it red (packages/cli/src/services/__tests__/machine-status.test.ts:112)
- [x] 16. Test new `src/services/executor/__tests__/renet-function-access.test.ts`: assert the set of read-only keys equals the explicit expected list in both directions, and `renetAccessFor('nope') === 'read-only'`. In `local-executor.test.ts`, assert that `repository_list` reaches the mock with `'read-only'` and `repository_up` with `'provision'`.
    (ticked) 2026-09-24T07:55:20Z by d778be9d: 4 table tests plus 2 executor tests green; mutation 3 red (packages/cli/src/services/executor/__tests__/renet-function-access.test.ts:10)
- [x] 17. Test `subscription.test.ts`: `status -m` → `'read-only'`; `refresh -m` → `'provision'`.
    (ticked) 2026-09-24T07:55:20Z by d778be9d: subscription.test 19/19 green (packages/cli/src/commands/__tests__/subscription.test.ts:501)
- [x] 18. Static ledger `src/__tests__/renet-access-ledger.test.ts`, following the tree walk in `env-tombstones.test.ts`:
    (ticked) 2026-09-24T07:55:20Z by d778be9d: ledger 4/4; mutations 1, 2 and 6 red then restored (packages/cli/src/__tests__/renet-access-ledger.test.ts:32)
  1. Parse each `src/**/*.ts` (excluding `__tests__`) with `typescript.createSourceFile`.
  2. Collect every `CallExpression` whose callee is `acquireRemoteRenet`, `connectForJobs`, `withJobConnection`, `resolveMachineContext`, `ensureRenetProvisioned` or `prepareSyncConnection`.
  3. Key each by `file::enclosingFunction::callee` and read the access argument text (a literal, or a forwarded identifier recorded as `<forwarded>`).
  4. Compare against an inline `LEDGER` taken from the table above. Fail on a mismatch, on an unlisted call, and on a listed call that has gone missing.
  5. Also assert that `renetProvisioner.provision(` appears only in `services/renet/renet-execution.ts`, and that `showBackupStatus` contains no `acquireRemoteRenet`.
- [x] 19. Env registration: add `REDIACC_ALLOW_DIRTY_RENET` to `.ci/config/env-manifest.json` (alphabetical, next to `REDIACC_ALLOW_DOWNGRADE` :688) and to `docs/environment-variables.md` (after :57). In the :58 row, note that `REDIACC_SKIP_ROUTER_RESTART` affects mutating verbs only. Grep `.ci/` and `scripts/` for rdc runs aimed only at local VMs, and export the opt-in there if they build from dirty trees.
    (ticked) 2026-09-24T07:55:20Z by d778be9d: env registration done; the .ci and scripts callers are other writers' files, reported to the lead (docs/environment-variables.md:58)
- [x] 20. Docs, `private/renet/CLAUDE.md:127-138` (submodule; edited, left uncommitted per the lead's ruling): step 5 becomes "Mutating verbs sync the freshly-built renet...". Add that read-only verbs (status/list/logs/term/vscode/job list...) never upload or restart and instead warn on drift, and that uploads from a dirty renet tree are refused unless `REDIACC_ALLOW_DIRTY_RENET=1`.
    (ticked) 2026-09-24T07:55:21Z by d778be9d: private/renet/CLAUDE.md edited, left uncommitted per the lead's ruling (private/renet/CLAUDE.md:138)
- [x] 21. Docs, `packages/www/src/content/docs/*/installation.md` "Remote Binary Updates" (en :214-226, 13 locales): "commands that change a machine provision renet; read-only commands never replace it and warn when it differs". Scope the `--skip-router-restart` sentence to those commands.
    (ticked) 2026-09-24T07:55:21Z by d778be9d: 13 installation.md files; translation-freshness and docs-structure-parity exit 0 (packages/www/src/content/docs/en/installation.md:216)
- [x] 22. Help text: append "Read-only: never updates renet on the machine; warns when its version differs." to `commands.machine.status.description` in all 13 `packages/cli/src/i18n/locales/*/cli.json`, then `cd packages/cli && npm run generate:cli-contract && npm run generate:skill-reference`. The claim at `packages/cli/src/i18n/locales/en/cli.json:468` ("Read-only queries") and `packages/www/src/content/docs/en/ai-agents-claude-code.md:51` ("read-only status checks") become true and need no edit.
    (ticked) 2026-09-24T07:55:21Z by d778be9d: 13 locales, EN hash manifest updated, generate:cli-contract and skill reference regenerated; check:ci-cli-contract exit 0 (packages/cli/src/i18n/locales/en/cli.json:687)
- [ ] 23. Commit with the `PR-TASK` trailer for worklist item `#f8ff8ede` (`agent/pr/0923-1.md line 74 (blob e31f5018a9c4)`).

**Order:** 1-2 (provisioner), then 3-5 (entry point and table). tsc then lists every broken site, which drives 6-12. After that the tests (13-18), then env and docs (19-22).

## Critical files

- `/home/developer/console/packages/cli/src/services/renet/renet-execution.ts`
- `/home/developer/console/packages/cli/src/services/renet/renet-provisioner.ts`
- `/home/developer/console/packages/cli/src/services/executor/local-executor.ts` (and new `renet-function-access.ts` beside it)
- `/home/developer/console/packages/cli/src/services/machine/machine-status.ts`
- `/home/developer/console/packages/cli/src/services/executor/job-remote.ts` (with `/home/developer/console/packages/cli/src/commands/job.ts`)

Also touched:
- `/home/developer/console/packages/cli/src/commands/subscription-actions.ts`
- `/home/developer/console/packages/cli/src/commands/repo-sync.ts`
- `/home/developer/console/packages/cli/src/commands/backup-ops.ts`
- `/home/developer/console/packages/cli/src/services/__tests__/renet-provisioner.test.ts`
- `/home/developer/console/packages/cli/src/services/__tests__/machine-status.test.ts`
- `/home/developer/console/private/renet/CLAUDE.md`
- `/home/developer/console/packages/www/src/content/docs/en/installation.md`
- `/home/developer/console/docs/environment-variables.md`
- `/home/developer/console/.ci/config/env-manifest.json`

## Verification

```bash
cd /home/developer/console && npx tsc --noEmit -p packages/cli/tsconfig.json
cd /home/developer/console/packages/cli && npm test -- renet-provisioner renet-access renet-function-access machine-status
cd /home/developer/console/packages/cli && npm test -- renet-access-ledger local-executor subscription detached-jobs backup-schedule
cd /home/developer/console/packages/cli && npm test          # full suite
cd /home/developer/console/packages/cli && npm run lint
grep -rn "provisionRenetToRemote" /home/developer/console/packages/cli/src   # expect no output
```

**Mutation checks.** Apply each defect by hand, confirm the named test goes red, then revert. The tests must stay green on clean code.
1. `machine-status.ts` fetchMachineStatus `'read-only'` → `'provision'`: fails machine-status.test (box 15) and the ledger.
2. `job.ts` list `'read-only'` → `'provision'`: fails the ledger.
3. `RENET_FUNCTION_ACCESS.container_list = 'provision'`: fails renet-function-access.test.
4. The read-only branch of `acquireRemoteRenet` calls `provision`: fails renet-access.test.
5. `inspect` calls `doProvision`: fails the renet-provisioner inspect tests.
6. Re-add the call in `showBackupStatus`, or add a new `acquireRemoteRenet('provision', ...)` in any command file: fails the ledger ("unlisted call").
7. Remove the `uploadGuard` call: fails the renet-provisioner guard test and the renet-access dirty test.

**Live check** (optional; do it only after `git stash` of a renet change is committed or reverted): `./rdc.sh machine status <dev-vm>` after a local renet rebuild should print the drift warning and no "Renet updated" or "Restarted rediacc-router" lines. `REDIACC_ALLOW_DIRTY_RENET= ./rdc.sh repo up <repo>` on a dirty renet tree against a dev VM should refuse and list the dirty paths.

## Execution notes (2026-09-24)

- `renet-provisioner.ts` sat at 509 of the 512 counted lines `max-lines` allows, so the read-only probe did not fit inside it. Probe, parse and drift classification live in `packages/cli/src/services/renet/renet-inspect.ts`, and the local provisioning lock helpers moved unchanged into `renet-provision-lock.ts`. `provision()` and `inspect()` share one `lookupVerified` fast path and one `rememberVerified` write.
- Drift compares the numeric core of `VERSION`: a dev build carries a suffix (`0.0.0-dev`) while the remote probe extracts `x.y.z`.
- `commands.vscode.connect.provisioningRenet` was still claiming to provision on the read-only vscode paths. Its value now reads "Checking renet on remote..." in all 13 locales; the key name is unchanged.
- The CLI EN hash manifest was updated for the two changed keys only (`scripts/lib/crc32.ts`), because `i18n:generate-hashes` also rewrites the `private/account` manifests.
- Mutation checks 1-7 (7 split into 7a, provisioner call, and 7b, entry-point wiring) all went red and were restored byte-identical (sha256).

