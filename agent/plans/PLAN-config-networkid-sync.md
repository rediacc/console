# PLAN: F20, share repo network IDs across devices by treating the machine as the authority and guarding each ID in renet

Status: draft
Owner: d778be9d
First-Seen: 2026-09-25
Depends-On: PLAN-config-sync-hardening.md -- this plan builds on two parts of it. T3 (HOST_LOCAL_POINTERS plus the single `overlayHostLocal`) keeps a device's discovered `state.repos[*][*].networkId` alive across pulls. Without T3, every pull would wipe the IDs this plan discovers. T1/T2 (the config-sync harness in `private/account/tests/integration/config-sync/`) hosts the two-device scenarios. If the operator picks D1(b) instead of the recommendation, the plan also waits on that plan's T4 (rebase on the server copy) and T5 (compare-and-swap push). Both plans edit `packages/cli/src/i18n/locales/*/cli.json`, so T6 here lands after the hardening plan's i18n commits.
Priority: P1 -- proposed by AI. The finding is worse than "device B does not know A's IDs". The two devices' ID sequences are identical, so collisions are certain, not a matter of chance. When B brings up a repo A created, B's CLI allocates a fresh ID for it, and that ID is already held by another repo on the same machine. renet then force-removes the holder's containers and rewrites that repo's dockerd unit. Data volumes survive (so this is not P0), but it is a silent outage of a repo the operator never touched.
Concurrency: parallel. There are four writers: R (renet, `private/renet/**`), B (CLI and shared), C (the harness files listed in Owns, reviewed by the hardening plan's C because they share `harness/device.ts`), and the lead. R and B meet at one contract, the `network_id_in_use` error and the `network_used` function. T0 freezes that contract before R or B start.
Owns: private/renet/pkg/repository/netid_guard.go (new), private/renet/pkg/repository/netid_guard_test.go (new), private/renet/cmd/renet/repository_up.go, private/renet/cmd/renet/repository_create.go, private/renet/cmd/renet/repository_fork.go (startForkServices only), private/renet/cmd/renet/network_commands.go, private/renet/cmd/renet/network_commands_test.go, private/renet/pkg/functions/commands/network_used.go (new), private/renet/pkg/list/repositories_test.go, private/renet/pkg/i18n/locales/*.go (new keys only), packages/shared/src/renet-contract/data/functions.generated.ts (regenerated), packages/cli/src/services/config/config-network-id.ts, packages/cli/src/services/config/network-id-discovery.ts (new), packages/cli/src/services/config/config-resources.ts (the network ID section, lines ~641-665 only), packages/cli/src/services/repo/repo-mount-check.ts, packages/cli/src/utils/repo-executor.ts, packages/cli/src/services/state.ts (repository vault block only), packages/cli/src/services/config/config-reconcile.ts, packages/cli/src/commands/repo-create-delete.ts (registerNewRepo only), packages/cli/src/commands/repo-fork.ts (registerFork only), packages/cli/src/commands/backup.ts (restore allocation only), packages/cli/src/services/cluster/cluster-kube.ts (allocation comment and call only), packages/cli/src/services/__tests__/config-network-id.test.ts, packages/cli/src/services/config/__tests__/network-id-discovery.test.ts (new), packages/cli/src/services/__tests__/config-reconcile.test.ts, private/account/tests/integration/config-sync/network-id.test.ts (new), private/account/tests/integration/config-sync/harness/machine.ts (new), docs/design/spec/04-config-schema-v3.md (sections 1.3 and 4.2 only)
Worklist: (the lead adds this with worklist.py --add)

## Tasks

Writers:
- **R**: renet (`private/renet/**`)
- **B**: the CLI and shared packages
- **C**: the harness files in Owns
- **lead**: decisions, contract and closure

The renet submodule PR (R) merges first. The account submodule PR (C) comes next. The console PR (B, the regenerated contract, and the pointer bumps) follows both.

- [ ] T0 [lead] Get the operator's answers to D1-D6 (section 5). Freeze the contract that T2 and T3 share:
  - the renet error code `network_id_in_use`, with the JSON body `{network_id, holder: {kind, name, datastore}}`;
  - the function name `network_used` and its JSON shape: `[{network_id, kind: "repo"|"daemon"|"loopback"|"k3s", name?, datastore?}]`;
  - the CLI error class names.
- [ ] T1 [C] Add the fake machine (`harness/machine.ts`) and the scenarios N1-N7 (section 4.2) in `network-id.test.ts`. Every scenario that reproduces F20 starts as `it.fails('F20 N<k> ...')` and uses the `arrange`/`isSymptom` guards from `harness/guard.ts`. The `device.process()` hook that injects the fake executor is a small edit to `harness/device.ts`, reviewed by the hardening plan's C.
- [ ] T2 [R] renet side:
  - (a) Pin the existing `network_id` field of `renet list repositories --json` with a test in `pkg/list/repositories_test.go`.
  - (b) Add `repository.NetworkIDHolder(ctx, networkID, selfName)` in `pkg/repository/netid_guard.go`. It scans every registered datastore's `.interim/state/*` mirror, the running per-network daemons (`/var/run/rediacc/docker-<id>.sock` and the unit's data root), the configured loopback /26 aliases, and the k3s units.
  - (c) Call it in `repository create`, `repository up` and fork start. The call goes after the ID is resolved and before `CreateOrchestrator`, so `SafeStartup` never reaches `RemoveForeignProjectContainers` for a foreign ID. A hit returns `network_id_in_use`, which is a returned error, not `log.Fatal`, because the repo lock is held.
  - (d) Add `renet network used --json` and the `network_used` function, then regenerate `functions.generated.ts`.
  - (e) Add i18n keys.
- [ ] T3 [B] Discovery before allocation:
  - (a) `probeRepoPresent` (`repo-mount-check.ts:99`) returns `{present, networkId}` from the `repository_list` output it already fetches, so discovery costs no extra SSH round trip.
  - (b) Add the new module `network-id-discovery.ts` with `discoverNetworkId({repoGuid, machine, datastore})` and `machineUsedNetworkIds(machine)`.
  - (c) `ensureRepositoryNetworkId(repoRef, target)` takes the resolved machine and datastore. When the local ID is missing it asks the machine first, records the answer with `updateState`, and allocates only when the machine positively reports that it does not have the repo. If the machine is unreachable, it fails closed per D6.
  - (d) `allocateNetworkIdInStore(configName, {floor})`: `next = max(local next, max(machine used) + 64)`, keeping the forward-only counter. `registerNewRepo`, `registerFork`, backup restore and the cluster-kube allocators pass the target machine's used set.
  - (e) On `network_id_in_use` from create, fork or restore, advance past the holder and retry once. On `up`/`mount` of an existing repo, never re-allocate: surface the error, which names the holder and points to `rdc config reconcile`.
- [ ] T4 [B] Remove the `docker-undefined.sock` path in `state.ts:206-207`. When the local ID is missing, the connection vault resolves the ID through `ensureRepositoryNetworkId` (discovery) or throws a typed error. It never interpolates `undefined`.
- [ ] T5 [B] `config reconcile` rebuilds `state.repos[*][*].networkId` from `renet list all --json` by GUID match (spec 04 §4.2), and handles divergence per D4. Delete the stale comment at `config-reconcile.ts:241`, because the renet field has landed (`private/renet/pkg/list/types.go:212-216`). Correct the claim at `cluster-kube.ts:274` ("no id is ever handed out twice"), which is false across devices. Update spec 04 §1.3 and §4.2 to describe the machine-authoritative rule.
- [ ] T6 [B] i18n: add the new CLI errors (`networkIdInUse`, `networkIdUndiscoverable`, `networkIdDiverged`) to all `packages/cli/src/i18n/locales/*/cli.json`, after the hardening plan's i18n commits.
- [ ] T7 [lead] Closure:
  - Run the mutation controls in section 4.4 by hand; each must turn its test red.
  - Confirm that the account integration lane log lists `config-sync/network-id.test.ts`, and that the renet unit lane runs `netid_guard_test.go`.
  - Flip N1-N6 from `it.fails` to `it` (T3, T4 and T5 each flip their own), and delete their guards.
  - Record the outcome of D1-D6 in the hardening plan's F20 entry.

## 1. What happens today

### 1.1 How IDs are allocated and used

- **Allocation.** `allocateNetworkIdInStore` (`packages/cli/src/services/config/config-network-id.ts:25-43`) reads and advances `state.networkIds.next` through `configFileStorage.updateState`, which is a per-file lock on this host only.
  - When the counter is missing, `pickInitialNetworkId` (`:46-53`) seeds it from the IDs in the local `state.repos`, or from `MIN_NETWORK_ID` (2816, `packages/shared/src/renet-contract/utils/validation.ts:236`) when there are none.
  - The step is 64 (`:239`).
- **Callers:**
  - `registerNewRepo` (`commands/repo-create-delete.ts:121`)
  - `registerFork` (`commands/repo-fork.ts:175`)
  - backup restore (`commands/backup.ts:147`)
  - cluster fork (`services/cluster/cluster-fork.ts:227`)
  - the k3s server and agents (`services/cluster/cluster-kube.ts:277`, `:314`)
  - the lazy path `ensureRepositoryNetworkId` (`services/config/config-resources.ts:649-664`), which allocates whenever the local record has no ID.
- **Where the ID lives.** It is a runtime key (`services/config/resource-state.ts:54-55`), so it sits in `state.repos[name][tag]`. `stripStateForPush` (`adapters/config-field-crypto.ts:156-167`) removes the whole `state` before every push, and `HOST_LOCAL_POINTERS` (`packages/shared/src/config-schema/sensitivity.ts:369-377`) keeps the local `state` over every pull. A second device therefore receives the repo's birth record (GUID, credential, placement) but never its network ID.
- **Uses on the machine.** The ID reaches renet as `network_id` in the vault (`services/renet/renet-execution.ts:413-415`, `:433-434`), and then as `--network-id` (`private/renet/pkg/functions/commands/repository.go`, the `AddNetworkID` calls). The ID names:
  - the per-repo dockerd socket, `/var/run/rediacc/docker-<id>.sock` (`private/renet/pkg/repository/repository.go:103-104`);
  - the loopback block `127.x.y.z/26` (`private/renet/pkg/config/iputil.go:23-44`);
  - the tmpfs secrets directory `/var/run/rediacc/secrets/<id>/`;
  - the registry unit, `rediacc-registry-<id>.service`;
  - the k3s unit and node interface for cluster members (`cluster-kube.ts:270-277`).

### 1.2 Can the machine recover the ID? Yes, for docker repos

- **Where renet records it.** `Repository.SaveState` writes the in-volume `.rediacc.json` and mirrors it, `network_id` included, to `<datastore>/.interim/state/<guid>/` (`private/renet/pkg/repository/state.go:231-237`). Every mount saves state.
- **Readable while unmounted.** `renet list repositories --json` and `renet list all --json` fill `RepositoryInfo.NetworkID` from that mirror (`private/renet/pkg/list/repositories.go:295`, field at `pkg/list/types.go:212-216`). The mirror can be read without unlocking the volume.
- **The CLI can already see it.** The TypeScript contract carries the field (`packages/shared/src/renet-contract/data/list-types.generated.ts`, `network_id?: number` on `RepositoryInfo`).
- **The CLI already asks for it.** The default verifier (`utils/repo-target.ts:35-49`) already runs `repository_list` against the placement machine for every mutating repo verb (`services/repo/repo-mount-check.ts:99-124`), then throws `network_id` away.
- **Not recoverable this way:**
  - Kube-arm repos: `repository_list` cannot see `<ds>/repos/<guid>` (`repo-target.ts:40`, #92).
  - k3s member IDs: these are not repos. The machine still knows them through their units and loopback aliases, which `network used` in T2 covers.
  - Repos whose mirror was never written, meaning never mounted since renet #67. The in-volume `.rediacc.json` has the ID once they are mounted.
- **Nothing uses it yet.** Spec 04 §1.3 already classes `repos.*.networkId` as rebuildable from the machine and asked for this renet field, which has now landed. The CLI half, reconcile rebuilding the ID, was never built (`services/config/config-reconcile.ts:241`).

### 1.3 What breaks when device B runs a command on a repo A created (proof chain)

Setup: device A creates repos `x` (2816) and `y` (2880) on machine `m`. Device B pulls; it has both records and no `state.repos`.

1. **B gets x's ID for y.** B runs `rdc repo up y`. `repo.ts:99` calls `executeRepoFunction`, then `repo-executor.ts:84` calls `ensureRepositoryNetworkId('y')`. There, `config-resources.ts:658` finds no ID, and `:660` allocates. B's `usedIds` is empty, so `config-network-id.ts:30` returns `MIN_NETWORK_ID` = **2816, which is x's ID**. `:661-662` records it in B's state.
2. **renet renumbers y.** `renet-execution.ts:413` sends `network_id: 2816`. `repository_up.go:104` accepts it and `:117` builds the orchestrator for y on 2816. Mounting y sees the persisted 2880 and rewrites the repo to 2816, keeping 2880 as an alias (`pkg/repository/state.go:474-487`, `pkg/config/config.go:102-112`). This is the fork mechanism from #440, applied here by accident.
3. **x's containers are removed.** In `SafeStartup`, x's daemon on `docker-2816.sock` is responding, so `RemoveForeignProjectContainers(2816, <y project>)` (`pkg/orchestration/workflows.go:133`, body at `pkg/daemon/discovery.go:146-186`) runs `docker rm -f` on **every x container**.
4. **x's daemon now serves y.** `setupAndStartDocker` (`workflows.go:156`, `:864-884`) rewrites the `docker-2816` unit to y's data root and restarts it. x is down. y now owns x's socket, loopback /26 and secrets directory.
5. **The damage repeats.** A's next `rdc repo up y` sends 2880, and renet renumbers y back. If x is running again by then, the same removal hits whichever repo holds the ID.
6. **B's shells get a bad socket.** On B, `rdc term y` / `vscode` builds `DOCKER_HOST=unix:///var/run/rediacc/docker-undefined.sock` (`services/state.ts:206-207`), because the vault path reads `repoConfig.networkId` without calling ensure.
7. **B's own new repos collide.** A new repo created on B (`repo-create-delete.ts:121`) gets 2816 (or the next ID in B's sequence). On a machine that hosts repos from both devices, this collides on the first pair. renet's create path validates only the ID's format (`pkg/repository/lifecycle.go:395-407`), never whether another repo holds it.

### 1.4 Collision risk

- **Certain, not random.** Every device starts at 2816 and steps by 64. B's k-th allocation equals A's k-th allocation. The size of the ID space (about 261,944 slots) does not help.
- **Where it applies:**
  - on any machine that hosts repos from two devices;
  - when a repo created on one device is moved by the other (`repo push`/`migrate` carry the ID, `renet-execution.ts:433`);
  - for k3s agents, which draw from the same per-device counter.
- **Not only within one config.** Two different configs (a local and a remote config, or two teams' configs) that point at one machine collide the same way. Only the machine sees every claimant.

## 2. Options

| | (a) The machine is authoritative, the CLI discovers, renet guards | (b) Sync IDs through the config store | (c) renet allocates from a per-machine counter |
|---|---|---|---|
| Existing repo, missing ID on B | Read from the machine in the probe that already runs (no extra SSH) | Arrives with the pull | Read from the machine, as in (a) |
| New ID on B | Local counter, with a floor at the target machine's used set; renet refuses a held ID | Config-wide counter; the compare-and-swap push decides between concurrent creators | renet picks under the machine's own lock and returns it |
| Concurrent creates on one machine | The second create gets `network_id_in_use` and retries once | One push wins; the loser must re-allocate on rebase (T4 re-applies the bucket with a stale ID unless allocation reruns) | Serialized by the machine lock; no conflict |
| Two different configs on one machine | Caught by the renet guard | **Not caught** (each config is its own universe) | Caught |
| Cross-machine move (push, migrate, restore) | Can hit a held ID on the destination; the guard refuses instead of destroying; D3(b) narrows the risk | Unique config-wide | Needs renumber-on-arrival (the alias remap exists only for a CoW fork's first up); the largest renet change |
| Depends on the hardening plan | T3 and the harness only | T3, T4, T5 and a registry change: `/state` is host-local as a whole, and HOST_LOCAL_POINTERS allows no carve-out beneath it, so `networkId` must move to the spec half (`RepoRecord`) with a migration | T3 and the harness only |
| Version churn | None (state writes) | An allocation bumps the version; acceptable, since a repo's birth already does | None |
| Repairs devices that have already diverged | Yes: the machine wins (D4) | No: the first push publishes whichever device's wrong ID it holds | Yes |
| Offline | Mutating verbs on an existing repo need the machine anyway | Remote writes already fail closed | Create needs the machine anyway |

**Recommendation: (a), with the renet guard.**
- It matches the design already written down: spec 04 §1.3 classes the ID as rebuildable state, and renet already publishes it.
- It needs no protocol change and adds no SSH round trip to the common path.
- It repairs devices that have already diverged.
- Only the machine-side guard protects against every source of a bad ID: another device, another config, a hand edit, a restored backup.

(b) remains a possible follow-up once the hardening plan's T5 ships, if cross-machine moves prove collision-prone. The guard in (a) is still needed under (b), because (b) cannot see other configs.

## 3. Design (option a)

### 3.1 renet (T2)

**Guard.** `NetworkIDHolder(ctx, id, self)` returns the first claimant of `id` that is not `self`:
- a mirror whose `NetworkID == id` in any registered datastore (`datastore.LoadRegistry`, plus the implicit default);
- a daemon unit for `docker-<id>` whose data root belongs to another repo;
- a loopback alias block owned by a non-repo holder (k3s).

What is not a claimant:
- A fork mirror carrying only `AliasNetworkID` (`cmd/renet/repository_fork.go:416-433` writes `NetworkID` as 0).
- The repo itself, including its own persisted ID when it differs from the requested one. Those are handled below as an explicit renumber decision.

**Enforcement.**
- `repository_create.go` after line 129, `repository_up.go` after line 104 (before `CreateOrchestrator` at 117), and fork start all call the guard.
- On a hit, the verb returns `network_id_in_use`. It must never reach `workflows.go:133`.
- An `up` whose requested ID differs from the repo's own persisted ID, outside a first fork mount, is refused with `network_id_mismatch`, which carries the persisted ID. This stops the silent renumber in step 2 of section 1.3. The CLI (T3) treats the persisted ID as the answer.

**`network used --json`.** Lists every claimant with its kind, for the allocation floor.

### 3.2 CLI (T3, T4, T5)

**One discovery path.** `ensureRepositoryNetworkId` gets the target from `resolveRepoRef` (`utils/repo-target.ts:99`). It then decides in this order:
1. The local ID, if present.
2. The probe's `networkId`, if the machine has the repo. The value is written to state.
3. A fresh allocation, if the machine reports that it definitely does not have the repo.
4. Otherwise, a fail-closed error (D6).

Every caller that runs before a target is resolved (`repo-cat.ts:89`, `repo-diff.ts:260`, `repo-migrate.ts:108,132`, `repo-fork.ts:584`, `repo-create-delete.ts:388`) gets the target passed in.

**Allocation floor.**
- `machineUsedNetworkIds(machine)` rides `network_used`. `allocateNetworkIdInStore` takes `{floor}` and keeps the forward-only semantics.
- A single device with a fresh machine produces the same sequence as today (N7).

**Retry.**
- Create, fork and restore retry once on `network_id_in_use`, using `floor = holder + 64`.
- On `network_id_mismatch`, the CLI adopts the persisted ID and does not retry.

**Reconcile.** Rebuild the ID by GUID. On divergence, follow D4.

## 4. Tests

### 4.1 The fake machine (`harness/machine.ts`)

The fake models renet's behavior today, with a switch for the guard:
- **Contents.** An in-memory table of repos (`guid -> {networkId, containers, datastore}`) and of daemons (`id -> ownerGuid`).
- **`execute({functionName})` handling:**
  - `repository_list`: returns `name` plus `network_id` from the mirror.
  - `network_used`: returns every claimant.
  - `repository_create` / `repository_up`: a docker-arm model. The passed ID overwrites the persisted one, as `state.go:487` does. If another repo's daemon owns the ID, that repo's containers are removed and the daemon is reassigned, as `workflows.go:133` and `:156` do.
- **Guard switch.** `guard: 'renet-today' | 'renet-guarded'` selects the pre-T2 or post-T2 model.
- **How it is injected.** `device.process({machine})` mocks `packages/cli/src/services/executor/executor-factory.js` with `vi.doMock` before the fresh module graph is imported, so two devices share one machine.
- **Link to real renet.** The fake stays honest through the Go tests in 4.3, which pin the real behavior it models. T7 checks by hand that the fake's `renet-today` model matches `workflows.go:124-158`.

### 4.2 Two-device scenarios (`network-id.test.ts`)

| ID | Scenario | Asserts | Starts as |
|---|---|---|---|
| N1 | A creates x, y on m; B pulls; B runs `ensureRepositoryNetworkId('y', {machine: m})` | Returns 2880 (A's); B's state records 2880 | `it.fails` (F20; the symptom is 2816) |
| N2 | Same setup; B runs `repo up y` against the fake | x's containers intact; x's daemon owner unchanged; y's persisted ID still 2880 | `it.fails` (F20) |
| N3 | Same setup; B creates z on m | z's ID not in {2816, 2880}; equals 2944 under D3(a) | `it.fails` (F20) |
| N4 | A and B create repos on m at once (`Promise.all`, guarded fake) | Every repo on m has a distinct ID; the loser retried once | `it.fails` (F20) |
| N5 | B's connection vault for y (`getConnectionVaults`) | `dockerSocket === /var/run/rediacc/docker-2880.sock`; never contains `undefined` | `it.fails` (F20) |
| N6 | Machine unreachable; B runs `repo up y` with no local ID | Fails closed with `networkIdUndiscoverable`; B's `state.networkIds` unchanged | `it.fails` (F20) |
| N7 | Single device A, fresh machine, three creates | 2816, 2880, 2944, byte-identical to today | green (control) |

- **Test lane.** The file has a `describe`-count assertion and runs in the account integration lane like its siblings.
- **Flips.** N1, N2, N3, N5 and N6 flip in T3/T4. N4 needs both T2 (the guard model and contract) and T3.

### 4.3 Unit tests

- **renet:**
  - `pkg/list/repositories_test.go`: `network_id` comes from the mirror while unmounted.
  - `pkg/repository/netid_guard_test.go`:
    - a holder found across two datastores;
    - the repo's own ID is not a holder;
    - an alias-only fork mirror is not a holder;
    - a daemon unit rooted in another repo is a holder.
  - `cmd/renet`: `repository up` with a held ID returns `network_id_in_use` before the orchestrator is built. A seam counts calls to `RemoveForeignProjectContainers`; the count must be 0.
  - `repository up` with an ID that differs from the persisted one returns `network_id_mismatch`, and a first fork mount is exempt.
  - `network used --json` shape.
- **CLI:**
  - `config-network-id.test.ts`: the floor raises `next`, never lowers it, and keeps multiples of 64.
  - `network-id-discovery.test.ts`: a discovered ID beats allocation; a definite absence allocates; an unreachable machine throws; a mismatch adopts the persisted ID.
  - `repo-mount-check` test: the probe returns `networkId`.
  - `config-reconcile.test.ts`: the ID is rebuilt by GUID, and divergence follows D4.
  - A `state.ts` vault test: no `undefined` in the socket path.

### 4.4 Mutation controls (T7; each must turn its test red)

| Revert | Red test |
|---|---|
| `ensureRepositoryNetworkId` allocates without asking the probe | N1, N2 |
| Drop the `{floor}` argument in `registerNewRepo` | N3 |
| Remove the create retry on `network_id_in_use` | N4 |
| `state.ts` interpolates `repoConfig.networkId` directly | N5 |
| Discovery falls back to allocation on an unreachable machine | N6 |
| Seed `pickInitialNetworkId` from the floor even when the machine is empty and the counter is set | N7 |
| Remove the `NetworkIDHolder` call from `repository_up.go` | the Go `cmd/renet` guard test |
| Treat alias-only fork mirrors as holders | the `netid_guard_test.go` fork case |
| Reconcile skips the `network_id` rebuild | `config-reconcile.test.ts` |

## 5. Operator decisions (recommended option first)

- **D1, approach:**
  - (a) the machine is authoritative, the CLI discovers, and renet guards (section 3), **recommended**;
  - (b) sync the IDs through the config store: move `networkId` into `RepoRecord` and sync the counter; needs the hardening plan's T4 and T5 plus a migration;
  - (c) renet allocates from a per-machine counter and renumbers on arrival for cross-machine moves.
- **D2, renet's response to a held ID:**
  - (a) refuse with `network_id_in_use`, naming the holder, and refuse a silent renumber with `network_id_mismatch`, **recommended**;
  - (b) warn and proceed;
  - (c) no guard.
- **D3, allocation floor for a new ID:**
  - (a) the local counter and the target machine's used set, **recommended**;
  - (b) every reachable machine in the config (config-wide uniqueness, one SSH round trip per machine; unreachable machines are skipped with a warning);
  - (c) the local counter only (today).
- **D4, local state and the machine disagree on an existing repo:**
  - (a) the machine wins; state is rewritten and one info line is printed, **recommended**;
  - (b) a hard error pointing to `rdc config reconcile`.
- **D5, sibling runtime keys** (`registryPort`, `pushState`, `head`, `headCommit`, `branches`, `reflog`), which are equally unsynced:
  - (a) out of scope; spec 04 §1.3 classes them as rebuildable or advisory, and each gets a follow-up entry, **recommended**;
  - (b) fold them into this plan.
- **D6, discovery when the machine is unreachable:**
  - (a) fail closed for a repo with no local ID, **recommended**;
  - (b) allocate with a warning (today's behavior, which is the cause of section 1.3).

## 6. Sequencing and risks

- **Order.** T0, then T1 (red scenarios), then T2 and T3 in parallel against the frozen contract, then T4 and T5, then T6 and T7.
- **Rollout skew.** A new CLI talking to an old renet:
  - `network_used` is missing, so the CLI treats the floor as unknown. Under D3(a) it falls back to `max(local next, max(probe network_ids) + 64)`, since the probe already returns the IDs of every repo in that datastore.
  - Without the guard, only the discovery half protects. That still fixes every case except concurrent creates.
- **Old CLI on a new renet.** Old CLIs get the guard's refusal instead of destroying a repo's containers. The error message must say what to run, which is the reason T6 exists.
- **Multi-datastore machines.** The probe covers one datastore, and the floor comes from `network_used`, which covers all of them. Kube-arm repos remain invisible to the probe (#92), so for them discovery falls back to reconcile. Spec 13 records that gap.
- **Two devices that already diverged.** On a machine where step 2 of section 1.3 has already happened, the persisted ID is B's. D4(a) adopts it on both devices, and the stale alias stays harmless.

### Critical Files for Implementation
- /home/developer/console/packages/cli/src/services/config/config-network-id.ts
- /home/developer/console/packages/cli/src/services/config/config-resources.ts
- /home/developer/console/packages/cli/src/services/repo/repo-mount-check.ts
- /home/developer/console/private/renet/cmd/renet/repository_up.go (with pkg/orchestration/workflows.go and pkg/repository/state.go)
- /home/developer/console/private/account/tests/integration/config-sync/harness/device.ts
