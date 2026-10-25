# PLAN: F20, share repo network IDs across devices: state sync carries them, the machine is the fallback and renet guards each ID

Status: approved -- the operator approved this rewrite 2026-10-23 (/ask, ruling #0c1cbd0d): D1(b) shipped, D3(a) and D6(a) ruled, the done parts of T2 dropped
Owner: d778be9d
First-Seen: 2026-09-25
Depends-On: PLAN-config-sync-hardening.md -- the synced `state` carries the IDs through its compare-and-swap push (T5 there, landed), and the two-device harness in `private/account/tests/integration/config-sync/` is its T1/T2. Both plans edit `packages/cli/src/i18n/locales/*/cli.json`, so Box T6 here lands after the hardening plan's i18n commits.
Priority: P1 -- a device with no recorded ID allocates one that collides with another repo's on the same machine (section 1.3), and renet then force-removes the holder's containers. Data volumes survive, so this is not P0, but it is a silent outage of a repo nobody touched.
Concurrency: parallel -- the renet box and the CLI boxes edit disjoint trees; the account-harness box waits until `private/account` is free; Owns: decides overlaps
Owns: private/renet/cmd/renet/repository_create.go, private/renet/cmd/renet/repository_fork.go, private/renet/cmd/renet/netid_guard_test.go, packages/cli/src/services/config/config-network-id.ts, packages/cli/src/services/config/network-id-discovery.ts, packages/cli/src/services/config/config-resources.ts, packages/cli/src/services/repo/repo-mount-check.ts, packages/cli/src/utils/repo-executor.ts, packages/cli/src/services/state.ts, packages/cli/src/services/config/config-reconcile.ts, packages/cli/src/commands/repo-create-delete.ts, packages/cli/src/commands/repo-fork.ts, packages/cli/src/commands/backup.ts, packages/cli/src/services/cluster/cluster-kube.ts, packages/cli/src/services/config/__tests__/config-reconcile.test.ts, packages/cli/src/services/config/__tests__/network-id-discovery.test.ts, packages/cli/src/services/config/__tests__/config-network-id.test.ts, private/account/tests/integration/config-sync/network-id.test.ts, private/account/tests/integration/config-sync/harness/machine.ts, docs/design/spec/04-config-schema-v3.md
Worklist: (the lead adds this with worklist.py --add)

## Rulings

- **D1(b), recorded as SHIPPED** (operator 2026-09-25, "striping the networkid is a disaster ... it's key info per repo and we aim to have shared machines per team"): a repo's `networkId` and the `networkIds.next` counter sync through the store with the rest of `state`; commits e2d1b04e55, d47018557e and 64438d30b8 landed it. Machine discovery is only the FALLBACK for a repo whose record still has no ID, so no device allocates blind.
- **D2**: renet refuses a held ID (`network_id_in_use`) and a silent renumber (`network_id_mismatch`). Shipped, see "Already done".
- **D3(a)**: the allocation floor comes from the TARGET machine only (its used set), not every machine in the config.
- **D4(a)**: when state and the machine disagree on an existing repo, the machine wins; state is rewritten and one info line is printed.
- **D5(a)**: the sibling runtime keys (`registryPort`, `pushState`, `head`, `headCommit`, `branches`, `reflog`) are out of scope.
- **D6(a)**: when the machine is unreachable and the repo has no local ID, fail closed.

## Already done (verified against the tree 2026-10-23; not boxes)

- renet pins `network_id` in `renet list repositories --json` from the unmounted mirror: `TestGetRepositories_NetworkIDFromMirrorWhileUnmounted` in `private/renet/pkg/list/repositories_test.go:349`.
- The guard exists: `guardNetworkID` and the holder scan in `private/renet/cmd/renet/netid_guard.go`, covered by `private/renet/cmd/renet/netid_guard_test.go`.
- `renet network used --json`, the `network_used` function and its contract are in (`private/renet/cmd/renet/network_commands.go`, `private/renet/pkg/functions/commands/network_used_test.go`), and so are the renet i18n keys.
- `repository up` calls the guard at `private/renet/cmd/renet/repository_up.go:149`, and returns the error rather than exiting.
- State sync carries `state.repos[*][*].networkId` and `state.networkIds.next` (D1(b) above).
- `repository create` and fork start reach the guard through `newGuardedOrchestrator` (`private/renet/cmd/renet/repository_create.go:156`, `private/renet/cmd/renet/repository_fork.go:476`). Only the `repository up` path has a test; Box R1 pins the other two.

## Boxes

Writers: **R** renet (`private/renet/**`), **B** the CLI and shared packages, **C** the harness files in Owns, **lead** closure. The renet submodule PR (R) merges first, then the account submodule PR (C), then the console PR (B and the pointer bumps).

- [x] R1 [R] Pin the guard wiring for `repository create` and fork start. In `private/renet/cmd/renet/netid_guard_test.go`, add cases mirroring `TestRepositoryUp_HeldNetworkIDRefusedBeforeOrchestrator`: `repository create` and `startForkServices` (`private/renet/cmd/renet/repository_fork.go`) with a held ID return `network_id_in_use` as a returned error before the orchestrator exists, never `log.Fatal`, and a seam counts calls to `RemoveForeignProjectContainers` as 0. If a case shows a path that does not reach `guardNetworkID`, fix it in `private/renet/cmd/renet/repository_create.go` or `private/renet/cmd/renet/repository_fork.go`, mirroring `private/renet/cmd/renet/repository_up.go:149`. Acceptance: from `private/renet`, `go test -tags nolicense ./cmd/renet/ -run 'NetworkID|Guard'` exits 0, and deleting the guard call from `newGuardedOrchestrator` turns the new cases red.
    (ticked) 2026-10-25T11:06:28Z by d778be9d: commit:1498835931713e (renet 82cb5dba): four held/free cases on create and fork start; go test -tags nolicense ./cmd/renet/ rc=0 in a scratch clone; the guard removed turns both held cases red
- [ ] T1 [C] WAITING until `private/account` is free. Add the fake machine (`private/account/tests/integration/config-sync/harness/machine.ts`) and scenarios N1-N7 (section 4.2) in `private/account/tests/integration/config-sync/network-id.test.ts`. Scenarios that reproduce F20 start as `it.fails('F20 N<k> ...')` with the `arrange`/`isSymptom` guards from `harness/guard.ts`. The `device.process()` hook injecting the fake executor is a small edit to `harness/device.ts`, reviewed by the hardening plan's C.
- [x] T3 [B] Discovery as the fallback, then allocation with a floor:
  - (a) `probeRepoPresent` (`packages/cli/src/services/repo/repo-mount-check.ts:99`) returns `{present, networkId}` from the `repository_list` output it already fetches, so discovery costs no extra SSH round trip.
  - (b) Add the module `packages/cli/src/services/config/network-id-discovery.ts` with `discoverNetworkId({repoGuid, machine, datastore})` and `machineUsedNetworkIds(machine)` (the latter over `network_used`).
  - (c) `ensureRepositoryNetworkId(repoRef, target)` (`packages/cli/src/services/config/config-resources.ts`) takes the resolved machine and datastore. A synced local ID wins. When the record has none it asks the machine first and records the answer with `updateState`; it allocates only when the machine positively reports it does not have the repo. An unreachable machine fails closed (D6(a)).
  - (d) `allocateNetworkIdInStore(configName, {floor})` (`packages/cli/src/services/config/config-network-id.ts`): `next = max(local next, max(target machine used) + 64)`, forward-only. `registerNewRepo`, `registerFork`, backup restore and the cluster-kube allocators pass the TARGET machine's used set (D3(a)).
  - (e) On `network_id_in_use` from create, fork or restore, advance past the holder and retry once. On `up` or `mount` of an existing repo never re-allocate: surface the error, which names the holder and points to `rdc config reconcile`.
    (ticked) 2026-10-25T11:06:42Z by d778be9d: commit:1498835931713e: T3 per the networkid writer; CLI vitest src 3369 passed, cli tsc rc=0, check:ci-i18n-cli-key-usage rc=0 (lead reruns)
- [x] T4 [B] Remove the `docker-undefined.sock` path in `packages/cli/src/services/state.ts` (the `machineVault.dockerHost` and `dockerSocket` lines that interpolate `repoConfig.networkId`). A record with no ID resolves through `ensureRepositoryNetworkId` or throws a typed error; it never interpolates `undefined`.
    (ticked) 2026-10-25T11:06:46Z by d778be9d: commit:b3b74547b: state.ts sets the socket only when repoConfig.networkId is defined and ssh-connection.ts throws errors.ssh.noNetworkId otherwise; no edit needed
- [x] T5 [B] `config reconcile` rebuilds `state.repos[*][*].networkId` from `renet list all --json` by GUID match (spec 04 §4.2) and handles divergence per D4(a) (`packages/cli/src/services/config/config-reconcile.ts`). Delete the stale comment above the `state.machines` rebuild there ("requires the renet `network_id` field ... until it lands"), because the field has landed (`private/renet/pkg/list/types.go:212-216`). Correct the claim in `packages/cli/src/services/cluster/cluster-kube.ts` ("so no id is ever handed out twice"), which is false across devices before the floor lands. Update `docs/design/spec/04-config-schema-v3.md` §1.3 and §4.2 to the synced-with-machine-fallback rule.
    (ticked) 2026-10-25T11:06:43Z by d778be9d: commit:1498835931713e: T5 per the networkid writer; CLI vitest src 3369 passed, cli tsc rc=0, check:ci-i18n-cli-key-usage rc=0 (lead reruns)
- [x] T6 [B] i18n: add `networkIdInUse`, `networkIdUndiscoverable` and `networkIdDiverged` to every `packages/cli/src/i18n/locales/*/cli.json`, after the hardening plan's i18n commits.
    (ticked) 2026-10-25T11:06:44Z by d778be9d: commit:1498835931713e: T6 per the networkid writer; CLI vitest src 3369 passed, cli tsc rc=0, check:ci-i18n-cli-key-usage rc=0 (lead reruns)
- [ ] T7 [lead] Closure: run the mutation controls in section 4.4 by hand, each must turn its test red; confirm the account integration lane lists `config-sync/network-id.test.ts` and the renet unit lane runs the new guard cases; flip N1-N6 from `it.fails` to `it` (T3, T4 and T5 flip their own) and delete their guards; record the outcome in the hardening plan's F20 entry.

## 1. What happened before state sync, and what the fallback still covers

### 1.1 How IDs are allocated and used

- **Allocation.** `allocateNetworkIdInStore` (`packages/cli/src/services/config/config-network-id.ts:28`) reads and advances `state.networkIds.next` through `configFileStorage.updateState`, which is a per-file lock on this host only.
  - When the counter is missing, `pickInitialNetworkId` (`:46-53`) seeds it from the IDs in the local `state.repos`, or from `MIN_NETWORK_ID` (2816, `packages/shared/src/renet-contract/utils/validation.ts:236`) when there are none.
  - The step is 64 (`:239`).
- **Callers:**
  - `registerNewRepo` (`packages/cli/src/commands/repo-create-delete.ts:124`)
  - `registerFork` (`packages/cli/src/commands/repo-fork.ts:191`)
  - backup restore (`packages/cli/src/commands/backup.ts:161`)
  - cluster fork (`packages/cli/src/services/cluster/cluster-fork.ts:227`)
  - the k3s server and agents (`packages/cli/src/services/cluster/cluster-kube.ts:278`, `:314`)
  - the lazy path `ensureRepositoryNetworkId` (`packages/cli/src/services/config/network-id-discovery.ts:278-293`), which allocates whenever the local record has no ID.
- **Where the ID lives.** It is a runtime key (`packages/cli/src/services/config/resource-state.ts:54-55`) in `state.repos[name][tag]`, and `state.networkIds.next` holds the forward counter. Both are classed `public` (`packages/shared/src/config-schema/sensitivity.ts:255`, `:271`) and are no longer stripped: state sync carries them to every device (commits e2d1b04e55, d47018557e, 64438d30b8). The account-side compare-and-swap push settles two devices writing at once. **Historical note:** until those commits a second device received the repo's birth record but never its network ID, which is the failure chain in 1.3. That chain still describes what a device with a record lacking an ID (data pushed before the change, or a diverged device) does when it allocates blind, and is the reason the discovery fallback exists.
- **Uses on the machine.** The ID reaches renet as `network_id` in the vault (`packages/cli/src/services/renet/renet-execution.ts:413-415`, `:433-434`), and then as `--network-id` (`private/renet/pkg/functions/commands/repository.go`, the `AddNetworkID` calls). The ID names:
  - the per-repo dockerd socket, `/var/run/rediacc/docker-<id>.sock` (`private/renet/pkg/repository/repository.go:103-104`);
  - the loopback block `127.x.y.z/26` (`private/renet/pkg/config/iputil.go:23-44`);
  - the tmpfs secrets directory `/var/run/rediacc/secrets/<id>/`;
  - the registry unit, `rediacc-registry-<id>.service`;
  - the k3s unit and node interface for cluster members (`packages/cli/src/services/cluster/cluster-kube.ts:271-278`).

### 1.2 Can the machine recover the ID? Yes, for docker repos

- **Where renet records it.** `Repository.SaveState` writes the in-volume `.rediacc.json` and mirrors it, `network_id` included, to `<datastore>/.interim/state/<guid>/` (`private/renet/pkg/repository/state.go:231-237`). Every mount saves state.
- **Readable while unmounted.** `renet list repositories --json` and `renet list all --json` fill `RepositoryInfo.NetworkID` from that mirror (`private/renet/pkg/list/repositories.go:295`, field at `private/renet/pkg/list/types.go:212-216`). The mirror can be read without unlocking the volume.
- **The CLI can already see it.** The TypeScript contract carries the field (`packages/shared/src/renet-contract/data/list-types.generated.ts`, `network_id?: number` on `RepositoryInfo`).
- **The CLI already asks for it.** The default verifier (`packages/cli/src/utils/repo-target.ts:35-49`) already runs `repository_list` against the placement machine for every mutating repo verb (`packages/cli/src/services/repo/repo-mount-check.ts:99-124`), then throws `network_id` away.
- **Not recoverable this way:**
  - Kube-arm repos: `repository_list` cannot see `<ds>/repos/<guid>` (`packages/cli/src/utils/repo-target.ts:40`, #92).
  - k3s member IDs: these are not repos. The machine still knows them through their units and loopback aliases, which `network used` in T2 covers.
  - Repos whose mirror was never written, meaning never mounted since renet #67. The in-volume `.rediacc.json` has the ID once they are mounted.
- **Nothing uses it yet.** Spec 04 §1.3 already classes `repos.*.networkId` as rebuildable from the machine and asked for this renet field, which has now landed. The CLI half, reconcile rebuilding the ID, was never built (`packages/cli/src/services/config/config-reconcile.ts:241`).

### 1.3 What breaks when device B runs a command on a repo A created (proof chain)

Setup: device A creates repos `x` (2816) and `y` (2880) on machine `m`. Device B pulls; it has both records and no `state.repos`.

1. **B gets x's ID for y.** B runs `rdc repo up y`. `packages/cli/src/commands/repo.ts:100` calls `executeRepoFunction`, then `packages/cli/src/utils/repo-executor.ts:84` calls `ensureRepositoryNetworkId('y')`. There, `packages/cli/src/services/config/network-id-discovery.ts:286` finds no ID, and `packages/cli/src/services/config/network-id-discovery.ts:287` allocates. B's `usedIds` is empty, so `packages/cli/src/services/config/config-network-id.ts:50` returns `MIN_NETWORK_ID` = **2816, which is x's ID**. `packages/cli/src/services/config/network-id-discovery.ts:292` records it in B's state.
2. **renet renumbers y.** `packages/cli/src/services/renet/renet-execution.ts:413` sends `network_id: 2816`. `private/renet/cmd/renet/repository_up.go:104` accepts it and `:117` builds the orchestrator for y on 2816. Mounting y sees the persisted 2880 and rewrites the repo to 2816, keeping 2880 as an alias (`private/renet/pkg/repository/state.go:474-487`, `private/renet/pkg/config/config.go:102-112`). This is the fork mechanism from #440, applied here by accident.
3. **x's containers are removed.** In `SafeStartup`, x's daemon on `docker-2816.sock` is responding, so `RemoveForeignProjectContainers(2816, <y project>)` (`private/renet/pkg/orchestration/workflows.go:133`, body at `private/renet/pkg/daemon/discovery.go:146-186`) runs `docker rm -f` on **every x container**.
4. **x's daemon now serves y.** `setupAndStartDocker` (`private/renet/pkg/orchestration/workflows.go:156`, `:864-884`) rewrites the `docker-2816` unit to y's data root and restarts it. x is down. y now owns x's socket, loopback /26 and secrets directory.
5. **The damage repeats.** A's next `rdc repo up y` sends 2880, and renet renumbers y back. If x is running again by then, the same removal hits whichever repo holds the ID.
6. **B's shells get a bad socket.** On B, `rdc term y` / `vscode` builds `DOCKER_HOST=unix:///var/run/rediacc/docker-undefined.sock` (`packages/cli/src/services/state.ts:207-208`), because the vault path reads `repoConfig.networkId` without calling ensure.
7. **B's own new repos collide.** A new repo created on B (`packages/cli/src/commands/repo-create-delete.ts:124`) gets 2816 (or the next ID in B's sequence). On a machine that hosts repos from both devices, this collides on the first pair. renet's create path validates only the ID's format (`private/renet/pkg/repository/lifecycle.go:395-407`), never whether another repo holds it.

### 1.4 Collision risk

- **Certain, not random.** Every device starts at 2816 and steps by 64. B's k-th allocation equals A's k-th allocation. The size of the ID space (about 261,944 slots) does not help.
- **Where it applies:**
  - on any machine that hosts repos from two devices;
  - when a repo created on one device is moved by the other (`repo push`/`migrate` carry the ID, `packages/cli/src/services/renet/renet-execution.ts:433`);
  - for k3s agents, which draw from the same per-device counter.
- **Not only within one config.** Two different configs (a local and a remote config, or two teams' configs) that point at one machine collide the same way. Only the machine sees every claimant.


## 2. Design

### 2.1 renet

Shipped except the pin in Box R1. `guardNetworkID` refuses a held ID (`network_id_in_use`, naming the holder) and a renumber of a repo's own persisted ID (`network_id_mismatch`, carrying the persisted ID) before any orchestrator exists, so `SafeStartup` never reaches `RemoveForeignProjectContainers` for a foreign ID (`private/renet/pkg/orchestration/workflows.go:133`). A fork mirror carrying only `AliasNetworkID` is not a claimant, and a first fork mount is exempt from the mismatch check.

### 2.2 CLI

**One resolution order** in `ensureRepositoryNetworkId`, with the target from `resolveRepoRef` (`packages/cli/src/utils/repo-target.ts:99`):
1. The local ID, which state sync delivers to every device.
2. The probe's `networkId`, if the machine has the repo; written to state.
3. A fresh allocation, if the machine reports it definitely does not have the repo.
4. Otherwise a fail-closed error (D6(a)).

Callers that run before a target is resolved (`packages/cli/src/commands/repo-cat.ts:89`, `packages/cli/src/commands/repo-diff.ts:260`, `packages/cli/src/commands/repo-migrate.ts:108,132`, `packages/cli/src/commands/repo-fork.ts:607`, `packages/cli/src/commands/repo-create-delete.ts:436`) get the target passed in.

**Floor.** `machineUsedNetworkIds(machine)` rides `network_used` on the target machine alone (D3(a)). A single device on a fresh machine produces today's sequence (N7).

**Retry.** Create, fork and restore retry once on `network_id_in_use` with `floor = holder + 64`. On `network_id_mismatch` the CLI adopts the persisted ID and does not retry.

**Reconcile.** Rebuild the ID by GUID; on divergence the machine wins (D4(a)).

## 3. Tests

### 3.1 The fake machine (`private/account/tests/integration/config-sync/harness/machine.ts`)

An in-memory table of repos (`guid -> {networkId, containers, datastore}`) and daemons (`id -> ownerGuid`). `execute({functionName})` serves `repository_list` (name plus `network_id`), `network_used` (every claimant) and `repository_create`/`repository_up` (docker arm). With `guard: 'renet-today'` a passed ID overwrites the persisted one and a held ID's containers are removed, as `private/renet/pkg/repository/state.go:487` and `private/renet/pkg/orchestration/workflows.go:133` did before the guard; with `guard: 'renet-guarded'` it refuses as the shipped guard does. `device.process({machine})` mocks `packages/cli/src/services/executor/executor-factory.js` with `vi.doMock` before the fresh module graph loads, so two devices share one machine.

### 4.2 Two-device scenarios (`network-id.test.ts`), reworked for the synced model

The synced model changes the setup: device B, after a pull, already HOLDS A's IDs. The F20 symptom now needs a record WITHOUT an ID, which is a repo pushed before sync carried IDs, or a device whose state diverged. Each scenario therefore starts from a B whose pulled record has the ID stripped (`arrange`), except N1b.

| ID | Scenario | Asserts | Starts as |
|---|---|---|---|
| N1a | A creates x, y on m; B pulls (synced) | B's state already holds 2816 and 2880; `ensureRepositoryNetworkId('y')` makes no machine call | green (control for D1(b)) |
| N1b | Same, but B's pulled record for y has no ID; B runs `ensureRepositoryNetworkId('y', {machine: m})` | Returns 2880 from the probe; B's state records it | `it.fails` (F20) |
| N2 | N1b setup; B runs `repo up y` against the fake | x's containers intact; x's daemon owner unchanged; y's persisted ID still 2880 | `it.fails` (F20) |
| N3 | Both devices synced; B creates z on m | z's ID not in {2816, 2880}; equals 2944 (the counter synced) and, with a stale counter, the floor lifts it past m's used set | `it.fails` for the stale-counter case |
| N4 | A and B create on m at once (`Promise.all`, guarded fake) | Every repo on m has a distinct ID; the loser retried once | `it.fails` (F20) |
| N5 | B's connection vault for a record with no ID (`getConnectionVaults`) | `dockerSocket === /var/run/rediacc/docker-2880.sock` after discovery; never contains `undefined` | `it.fails` (F20) |
| N6 | Machine unreachable; B runs `repo up y` with no ID | Fails closed with `networkIdUndiscoverable`; `state.networkIds` unchanged | `it.fails` (F20) |
| N7 | Single device A, fresh machine, three creates | 2816, 2880, 2944, byte-identical to today | green (control) |

N1b, N2, N3, N5 and N6 flip in T3/T4; N4 needs the guarded fake and T3.

### 3.3 Unit tests

- **renet:** the Box R1 cases (create and fork start refuse a held ID before the orchestrator, removal count 0).
- **CLI:**
  - `packages/cli/src/services/config/__tests__/config-network-id.test.ts`: the floor raises `next`, never lowers it, keeps multiples of 64, and comes from the target machine's used set only.
  - `packages/cli/src/services/config/__tests__/network-id-discovery.test.ts`: a synced ID beats discovery; a discovered ID beats allocation; a definite absence allocates; an unreachable machine throws; a mismatch adopts the persisted ID.
  - the `repo-mount-check` probe returns `networkId`.
  - `packages/cli/src/services/config/__tests__/config-reconcile.test.ts`: the ID is rebuilt by GUID, and divergence lets the machine win.
  - a `packages/cli/src/services/state.ts` vault test: no `undefined` in the socket path.

### 4.4 Mutation controls (T7; each must turn its test red)

| Revert | Red test |
|---|---|
| `ensureRepositoryNetworkId` allocates without asking the probe | N1b, N2 |
| Drop the `{floor}` argument in `registerNewRepo` | N3 (stale counter) |
| Remove the create retry on `network_id_in_use` | N4 |
| `state.ts` interpolates `repoConfig.networkId` directly | N5 |
| Discovery falls back to allocation on an unreachable machine | N6 |
| The floor reads every machine in the config instead of the target | the floor unit test |
| `pickInitialNetworkId` seeds from the floor when the counter is set | N7 |
| Remove the guard call from `newGuardedOrchestrator` | the Box R1 cases |
| Reconcile skips the `network_id` rebuild | `config-reconcile.test.ts` |

## 4. Sequencing and risks

- **Order.** R1 and T3-T5 in parallel (disjoint trees), T1 when `private/account` is free, then T6 and T7.
- **Rollout skew.** A new CLI against an old renet has no `network_used`: the floor falls back to `max(local next, max(probe network_ids) + 64)`, since the probe already returns every repo's ID in that datastore. Without the guard only discovery protects, which fixes every case except concurrent creates.
- **Old CLI on a new renet** gets the guard's refusal instead of a destroyed repo; the message must say what to run, which is why T6 exists.
- **Kube-arm repos** are invisible to the probe (`packages/cli/src/utils/repo-target.ts:40`, #92); for them discovery falls back to reconcile, and spec 13 records the gap.
- **Two devices that already diverged.** On a machine where step 2 of section 1.3 already happened, the persisted ID is B's, and D4(a) adopts it on both devices; the stale alias is harmless.
