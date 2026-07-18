# P0 Spec 04 — Config Schema v3

Status: P0 spec deliverable (R2-F1, R2-F2, R2-F3, R2-F5, R2-F6, R2-F7, R2-F9).
Implements: 02 §11 (all seven items), 02 §7 (placement tagged union), 06 §6 (addressing
state needs), 03 §2 (attach state + holder inventory), 09 §P1 (config v3 lands with the
renet storage core).
Verified against the working tree on 2026-07-10; every cited identifier was grepped.
Where the suite left detail thin, decisions here are marked **[P0-DECIDED]**.
Gate review applied (`00-gate-review.md`, 2026-07-10): C4 (secret label contract key),
C7 (cluster backref lifted out of the backend union), C11 (merged secret caps),
C14 (holders gain `volumes`), C15 (set-placement ghost verb removed), G3 (registryPort).

Code studied:
- `packages/shared/src/config-schema/schemas.ts` (v2 Zod schema, `CONFIG_KEY_ORDER_V2`, `stringifyConfig`)
- `packages/shared/src/config-schema/sensitivity.ts` (pointer-template registry) + `schema/walker.ts`
- `packages/shared/src/config-schema/migrations/{index.ts,v1-to-v2.ts} + packages/cli/src/schema/__tests__/migrations.test.ts`
- `packages/cli/src/services/config/resource-state.ts` (THE bug), `config-resources.ts`,
  `config-cluster-logic.ts`, `config-network-id.ts`, `config-resources-resolve.ts`
- `packages/cli/src/adapters/config-file-storage.ts` (atomic save, unconditional version bump)
- `packages/cli/src/services/account/cert-cache.ts`, `services/repo/repo-secrets-store.ts`
- `private/renet/pkg/list/types.go` (`ListResult`, the `renet list all --json` contract)
- `.ci/scripts/quality/check-config-migrations.sh` (the gate)

---

## 1. The v3 schema

### 1.1 Top level

```ts
export const RdcConfigSchema = z.object({
  schemaVersion: z.literal(3),
  id: uuid,
  version: z.number().int().min(1),   // bumps ONLY on spec-half changes (see 1.5)
  account: AccountSchema.optional(),        // team/region keys DELETED (R2-F9)
  defaults: DefaultsSchema.optional(),      // machine key DELETED (R2-F9)
  credentials: CredentialsSchema.optional(),
  resources: ResourcesSchema.optional(),    // the spec half
  infra: InfraTopSchema.optional(),         // acmeCertCache MOVED to state
  encryption: EncryptionSchema.optional(),  // per-field only; '/resources' blob retired
  remote: RemoteConfigSchema.optional(),
  renetPath: z.string().optional(),
  state: StateSchema.optional(),            // NEW: the status half (1.3)
}).loose();                                  // unknown top-level keys still round-trip
```

`CONFIG_KEY_ORDER_V3` = `CONFIG_KEY_ORDER_V2` with `state` appended last, so the
spec half stays at the top of the file and diffs read spec-first (the R2-F8
git-diffability bonus).

### 1.2 The spec half (`resources` + siblings)

#### 1.2.1 Placement tagged union (R2-F1)

```ts
const PlacementSchema = z.union([
  z.object({ datastore: resourceName }),  // a NAMED datastore (registry entry)
  z.object({ machine: resourceName }),    // that machine's IMPLICIT default datastore
]);
export type Placement = z.infer<typeof PlacementSchema>;
```

Exactly the two `repo create` flags, one-to-one (02 §7). Implicit default datastores
never enter the registry, so NAMED datastore names stay unique per config and
`--datastore` alone determines cluster/node/tier. The resolver has two arms and zero
string special-casing:

```
resolvePlacementMachine(p: Placement):
  machine arm    -> that machine (verify it exists; verify it carries NO cluster
                    membership backref, else the R2-F12 teaching refusal)
  datastore arm  -> registry[p.datastore] ->
      backend local -> backend.machine
      backend rbd   -> state.datastores[name].attachedTo   (ROUTING HINT, 1.3;
                       verified at use, errors with a reconcile suggestion)
```

#### 1.2.2 Named datastore registry (NEW)

```ts
const DatastoreBackendSchema = z.union([
  z.object({                       // second/tiering pool on one machine
    kind: z.literal('local'),
    machine: resourceName,         // the anchor; local datastores do not move
    path: absolutePath,            // e.g. /mnt/rediacc-fast
  }),
  z.object({                       // RBD image; mobile among the machines that reach its Ceph
    kind: z.literal('rbd'),
    pool: z.string().min(1),
    image: z.string().min(1),
  }),
]);

const DatastoreConfigSchema = z.object({
  backend: DatastoreBackendSchema,
  // Cluster backref (gate C7: top-level, ORTHOGONAL to the backend union).
  // Set at `datastore create --cluster <name>`, validated against
  // resources.clusters, IMMUTABLE thereafter (one-world datastores, spec 02 §3.2).
  // set   => kubernetes-world datastore (repos placed here are kube repos);
  //          legal on BOTH backends (local-NVMe tier inside a cluster is real,
  //          suite 02 §1 / 03 §3 — it just sits outside the group-snap instant).
  // unset => docker-world datastore; legal on BOTH backends (an rbd datastore
  //          without a cluster is the `machine set-ceph` replacement, 06 §2).
  cluster: resourceName.optional(),
  size: z.string().optional(),          // provision size, e.g. "200G"
  parent: z.object({                    // fork lineage (datastore fork, 03)
    datastore: resourceName,
    snapshot: z.string().optional(),    // rbd snap / group-snap member it was cloned from
  }).optional(),
});

// in ResourcesSchema:
datastores: z.record(resourceName, DatastoreConfigSchema).optional(),
```

Notes:
- The `default` datastore of every machine is implicit (02 §7): auto-created by
  `machine setup` at `machines[*].datastore ?? /mnt/rediacc`, never registered here.
  `machines[*].datastore` (the existing optional path override) is KEPT as the implicit
  default's mount path.
- **This registry is the single source for runtime dispatch** (spec 02 §3.2 consumes
  it, spec 03 §2.3 resolves through it): placement machine arm ⇒ docker; placement
  datastore arm ⇒ `registry[name].cluster` set ⇒ kube, unset ⇒ docker. No other
  signal participates.
- An rbd datastore's Ceph endpoint (mon addresses, keyring) is renet-side derivation
  (machine registry + on-datastore descriptor), never config data.
- Datastores are unencrypted (02 §5), so the record carries no key material.
- Attach state (`attachedTo`, `writes`, holders) is STATUS, not spec: 1.3.
- `machines[*].ceph` (v2's `CephConfigSchema`) is retired; Ceph becomes a datastore
  backend property (02 §6). Migration handling: 3.2 transform 7.

#### 1.2.3 Repositories: structural tags (R2-F5)

v2 keys repositories by flat string, bare (`"erpnext"`) or composite (`"demo:latest"`),
with a `RESERVED_GRAND_TAG = 'latest'` resolver special-case pile
(`resolveExactOrLatest`, `assertRestoredForkKeyIsExplicit`, `parseRepoRef` in
`utils/config-schema.ts`, issue #495 lineage). v3 makes the grammar data:

```ts
const TagName = z.string().min(1).max(63)
  .regex(/^[a-z0-9]([a-z0-9-]*[a-z0-9])?$/)
  // ':' and '@' are structurally impossible in a record key that matches this
  // regex, which is the 06 §6.4 create-time validation for the tag position.

const RepoRecordSchema = z.object({
  repositoryGuid: uuid,
  credential: z.string().optional(),
  grandGuid: z.string().optional(),
  parentGuid: z.string().optional(),
  immutable: z.boolean().optional(),
  sshPrivateKey: z.string().optional(),
  sshPublicKey: z.string().optional(),
  secrets: z.record(SecretKeySchema, SecretEntrySchema).optional(),
  // REMOVED from the record (v2 leftovers):
  //   tag           -> redundant with the record key
  //   networkId     -> state.repos (1.3)
  //   pushState     -> state.repos
  //   headCommit, commitMessage, commitAuthor, commitParent,
  //   branches, head, reflog -> state.repos (ref store is status, 1.3)
});

const RepoFamilySchema = z.object({
  placement: PlacementSchema.optional(),   // optional ONLY for migrated configs; every
                                           // derived-machine op REQUIRES it (see 3.2/4)
  grand: TagName,                          // WHICH tag key is the production line
  tags: z.record(TagName, RepoRecordSchema),
});

// in ResourcesSchema:
repositories: z.record(resourceName, RepoFamilySchema).optional(),
```

**`latest` retirement [P0-DECIDED, shape]**: what dies is the RESOLVER magic, not the
string. `grand` is an explicit data pointer at the tag key holding the production
record; bare `shop` resolves to `tags[family.grand]`, `shop:test` to `tags['test']`.
`latest` becomes an ordinary, legal tag name with zero special behavior. Consequences:
- `RESERVED_GRAND_TAG`, `resolveExactOrLatest`, and the fork-restore tag ban
  (`assertRestoredForkKeyIsExplicit`) are all deleted; the #495 bare-name ambiguity
  class is structurally impossible (record keys are unique; bare names always follow
  the `grand` pointer; `AmbiguousRepoTargetError` machinery in
  `config-resources-resolve.ts` dies with it).
- New `repo create` stamps the grand under tag `main` **[P0-DECIDED]**; migrated
  grands keep the literal tag `latest` (3.2 transform 2) so migrated and fresh configs
  differ in data, not behavior.
- Placement is per FAMILY, not per record: `repo fork` is a reflink inside the parent's
  datastore, so grand and forks are co-located by construction, and 06 §6.5 already
  fixes "names unique per config, placement single-valued, pushed copies are backup
  artifacts". Repos inside a FORKED DATASTORE are addressed through the fork datastore's
  own name (04 anchor+rejoin spec owns that identity question, not this schema).

#### 1.2.4 Clusters, providers, backup strategies, storages, secrets

- `clusters`: v2 `ClusterConfigSchema` kept (provider, network, pools, kubernetes,
  registry, ceph ref, controlNode, kvm) MINUS `kvm.memberIds`, which moves to
  `state.clusters[*].memberIds` (it is a booted-VM allocation ledger, exactly the
  "status churn bumps the version counter" problem R2-F2 names).
- `cloudProviders`: kept as-is; `apiToken` finally encrypted at rest (2.3).
- `backupStrategies`: kept as-is.
- `storages` (rclone backup targets, `vaultContent`): kept as-is. The noun survives the
  06 reshape (`rdc storage list/create/delete/browse/prune/import`); it is disjoint from
  the new `datastores` registry and the two must never be merged.
- Per-repo `secrets`: kept on the RepoRecord (spec: the operator declared them), shape
  unchanged (`UPPER_SNAKE` key regex, `env|file` mode), size cap changes in §5.
  Fork isolation invariant carried forward: fork registration never copies `secrets`.
- `deletedRepositories`: kept as an array; `ArchivedRepository.name` splits into
  `{ name, tag }` (3.2 transform 9) since composite strings die everywhere.

### 1.3 The `state` bucket (R2-F2)

Everything mutable-at-runtime that today pollutes the spec (grep-verified writers listed
per field):

```ts
const StateSchema = z.object({
  // Datastore attach/mount status. Writers: datastore attach/detach/fork (P1),
  // node lifecycle units (P2), config reconcile.
  datastores: z.record(resourceName, z.object({
    attachedTo: resourceName.optional(),      // current mounter machine (ROUTING HINT)
    writes: z.enum(['ceph', 'local']).optional(), // fork-attach disposition (03 §2)
    mounted: z.boolean().optional(),
    mountPath: absolutePath.optional(),
    attachedAt: z.string().optional(),
    // Expected-holder inventory for the 03 hygiene sweep (rule 3): what losetup -a
    // and dmsetup ls SHOULD show for this datastore. Diffed by storage-health.
    // Shape mirrors spec 01's on-machine registry {loops, dm, volumes} (gate C14):
    // `volumes` = per-volume LUKS image mounts expected under the ds mounts tree.
    holders: z.object({
      loops: z.array(z.string()).optional(),
      dm: z.array(z.string()).optional(),
      volumes: z.array(z.string()).optional(),
    }).optional(),
  })).optional(),

  // Per-machine observations. Writers: config reconcile, machine query.
  machines: z.record(resourceName, z.object({
    lastSeenAt: z.string().optional(),
    renetVersion: z.string().optional(),
  })).optional(),

  // Per-cluster observations. memberIds moved from clusters[*].kvm.memberIds
  // (writer today: services/cluster/kvm-provisioner.ts). k3s versions are the
  // F14 skew metadata consumed by the attach preflight.
  clusters: z.record(resourceName, z.object({
    memberIds: z.record(z.string(), z.array(z.number().int().min(1))).optional(),
    k3sVersion: z.string().optional(),               // observed control plane
    nodes: z.record(resourceName, z.object({
      k3sVersion: z.string().optional(),
      lastSeenAt: z.string().optional(),
    })).optional(),
  })).optional(),

  // Per-repo-record runtime state, addressed name -> tag (mirrors resources
  // .repositories structurally; a state entry with no matching spec record is
  // pruned by reconcile).
  repos: z.record(resourceName, z.record(TagName, z.object({
    networkId: z.number().int().optional(),   // writer: config-network-id.ts
    // Per-repo zot registry port (gate G3; spec 05 §5): allocated at `repo create`
    // for registry-opted repos from the 21000-28999 range, recorded next to
    // networkId. Rebuildable: the machine's rediacc-registry-<networkID>.service
    // unit carries the port.
    registryPort: z.number().int().min(21000).max(28999).optional(),
    pushState: z.record(z.string(), z.object({ // writer: repo-delta.ts, repo push
      verifiedBase: z.string().optional(),
      lastPushAt: z.string(),
      method: z.enum(['rsync', 'delta']),
    })).optional(),
    // Branching ref store (writer: commands/repo-branching.ts). Machine = object
    // store, state bucket = ref store.
    headCommit: z.string().optional(),
    commitMessage: z.string().optional(),
    commitAuthor: z.string().optional(),
    commitParent: z.string().optional(),
    head: z.string().optional(),
    branches: z.record(z.string(), z.string()).optional(),
    reflog: z.array(ReflogEntrySchema).optional(),
  }))).optional(),

  // NetworkId forward counter, moved from defaults.nextNetworkId
  // (writer: allocateNetworkIdInStore, config-network-id.ts).
  networkIds: z.object({ next: z.number().int().optional() }).optional(),

  // ACME cert cache, moved from infra.acmeCertCache
  // (writer: services/account/cert-cache.ts:584-587).
  certCache: z.record(z.string(), AcmeCertCacheSchema).optional(),

  reconciledAt: z.string().optional(),
}).optional();
```

**The three documented properties (02 §11.1), made precise:**

1. **Excluded from the version counter and from remote push.** State writes go through
   a new `configFileStorage.updateState()` that does NOT bump `version`; remote push
   serializes the config with `state` (and any `encryption.encryptedFields` entry whose
   pointer starts with `/state/`) stripped. This kills the optimistic-version conflicts
   and audit noise that status churn causes today (every `pushState` stamp and cert
   refresh currently bumps the counter via `config-file-storage.ts:213`).
2. **Rebuildable via `config reconcile`** (§4), with an honest per-field ledger. Not
   all state is machine-observable, so v3 defines three classes; ALL are losable
   without a correctness failure:
   - **Rebuildable** (reconcile restores from `renet list all --json` + the P1
     datastore verbs): `datastores.*` attach/mounted/holders, `machines.*`,
     `clusters.*.k3sVersion/nodes`, `repos.*.networkId` (requires the P1 renet
     addition below), `repos.*.registryPort` (from the per-repo registry unit),
     `certCache` (re-fetchable from the source machine).
   - **Partially rebuildable**: `clusters.*.memberIds` (from `renet ops` libvirt
     inventory on the KVM host; unrecoverable if the host is gone, in which case the
     VMs are too).
   - **Advisory history, self-healing on next use** (reconcile prunes but cannot
     reconstruct): `repos.*.pushState` (loss degrades the next push to full rsync,
     never to corruption; `verifiedBase` is re-proven per push), `repos.*` branching
     refs and `reflog` (commits are immutable on-machine objects; losing refs loses
     naming/history, never data; reconcile re-lists commit objects from the machine's
     `.interim` mirrors so `branches` can be re-seeded, `reflog` restarts empty).
3. **Routing HINT, verified at use.** Every derived-machine operation (06 §6: `-m` is
   gone) that resolves through `state.datastores[*].attachedTo` MUST verify before
   acting: one cheap remote check that the datastore is actually mounted on that
   machine (renet reports it; `ListResult.repositories[].mount_path` and the P1
   datastore-status verb). Mismatch is a hard error naming both sides plus the fix:
   `state says ds-alpha is attached to prod-2, but prod-2 does not have it mounted.
   Run 'rdc config reconcile' to refresh, or 'rdc datastore attach ds-alpha --to <m>'.`
   Never fall back to trying other machines: a guess is a wrong-host deploy.

**Required renet-side addition (P1)**: `RepositoryInfo` in `private/renet/pkg/list/types.go`
does not expose the repo's networkId today (only `HealthDriftEntry.NetworkID` has it, and
only for drifting containers). Reconcile needs it to rebuild `repos.*.networkId` without
re-allocating (a re-allocation would silently break the repo's baked loopback /26 and
socket path). Add `network_id` to `RepositoryInfo`, sourced from the `.interim` state
mirror like `is_fork`/`grand_guid`/`repo_name` already are.

### 1.4 Sensitivity registry: v3 pointer delta

`schema/sensitivity.ts` templates are rewritten for the new shapes (the walker in
`schema/walker.ts` needs zero changes; `*` already matches record keys at any depth):

| v2 template | v3 template |
|---|---|
| `/resources/repositories/*/credential` (and sshPrivateKey, sshPublicKey, secrets/*/value, secrets/*/mode, repositoryGuid, grandGuid, parentGuid) | `/resources/repositories/*/tags/*/<same>` |
| `/resources/machines/*/ceph/...` (3 entries) | deleted with the field |
| (none) | `/resources/datastores/*/backend/...`, `/resources/datastores/*/cluster`, `/resources/datastores/*/parent/...` all `public` |
| `/infra/acmeCertCache/*/data` (`credential`) | `/state/certCache/*/data` (`credential`, `commit: false` since state never pushes) |
| `/resources/repositories/*/pushState/...` | `/state/repos/*/*/pushState/...` (`public`) |
| `/account/team`, `/account/region` | deleted (R2-F9; never registered anyway) |

New invariant entries for the `check:ci-schema-coverage` gate: every new leaf in
`DatastoreConfigSchema` and `StateSchema` gets a registry entry (mostly `public`;
`certCache/*/data` is the one credential living under `/state`).

### 1.5 Version counter and ordering semantics

- `version` bumps only in `configFileStorage.update()` (spec writes). The new
  `updateState()` path writes the same file atomically (same lock, same
  `stringifyConfig`) without a bump. There is no diff heuristic: the WRITER declares
  which half it is touching, and the two entry points are the enforcement (a spec
  writer that sneaks a state field in is a code-review error, and `check:ci-schema-coverage`
  plus the regression tests in 2.5 keep the split honest).
- `stringifyConfig` ordering extends `CONFIG_KEY_ORDER_V2` with `state`; all nested
  records keep the existing sorted-key behavior, so the file stays deterministic and
  git-diffable (R2-F8).

---

## 2. Unified persist + per-field encryption (R2-F3, the data-loss fix)

### 2.1 The confirmed bug, precisely

Two writers disagree about who owns `cfg.resources`:

- `LocalResourceState.persist()` master-password branch,
  `services/config/resource-state.ts:203-214`: writes the compound AES-GCM blob to
  `encryption.encryptedFields['/resources']` and sets **`resources: undefined`**
  (line 212). Its `LocalState` only contains machines/storages/repositories/
  deletedRepositories/sshContent.
- The second path writes clusters/cloudProviders/backupStrategies PLAINTEXT into
  `cfg.resources` via direct `configFileStorage.update()` calls:
  `config-resources.ts:505/518/542/560` (backupStrategies), `:575/:587`
  (cloudProviders), `config-cluster-logic.ts:103` (clusters). The comment at
  `config-resources.ts:600-602` even codifies the split ("cluster records are
  non-secret so they live in the plain config").

So in master-password mode: `cluster add` writes `resources.clusters`; the next repo or
machine mutation runs `persist()`, which nukes the entire `resources` subtree. Clusters,
providers, and strategies are DESTROYED. Additionally the blob is all-or-nothing and
leaves `cloudProviders[*].apiToken` and `credentials.cfDnsApiToken` in plaintext forever.

**Sibling bug (same class, found during this spec)**: `RemoteResourceState.persist()`
(`resource-state.ts:345-372`) reconstructs a `fullConfig` containing ONLY
machines/storages/repositories/deletedRepositories + ssh, hardcodes
`schemaVersion: 2` and `encryption: {mode:'plaintext'}`, and pushes it whole, so every
remote push also drops clusters/providers/strategies/infra/defaults. The unified
persist below fixes both by construction.

### 2.2 The v3 persist architecture: one chokepoint

**Principle: encryption is a storage-layer transform, not a caller behavior.** Callers
never see or produce blobs; they read and write plaintext config objects. The transform
lives in `ConfigFileStorage` (the single component every writer already goes through):

```
save/update/updateState(name, updater):
  1. loadRaw(file) -> decryptFields(raw, password?)      // plaintext in memory
  2. updated = updater(plainConfig)
  3. bump version IFF spec entry point (1.5)
  4. encryptFields(updated, password) when encryption.mode === 'master-password':
       for each { pointer, value, meta } of walkSensitive(updated):
         if meta.encryptAtRest and value !== undefined:
           encryption.encryptedFields[pointer] = aesGcmEncrypt(canonicalJson? no —
             JSON.stringify(value)) as { nonce, tag, ciphertext }
           setByPointer(updated, pointer, undefined)      // leaf removed from plaintext
  5. stringifyConfig -> atomic write (existing temp+rename, existing file lock)

load(name):
  parse -> runMigrations -> RdcConfigSchema.parse
        -> decryptFields when a password is available (lazy: reads that touch no
           sensitive field never prompt; getResourceState() prompts exactly where
           config-base.ts:63-67 already does)
```

Consequences:
- `LocalResourceState.persist()`'s two branches (`resource-state.ts:185-241`) are
  DELETED; its setters become plain `configFileStorage.update()` calls on
  `resources.*`. The class shrinks to a typed view over the config file.
- The cluster/provider/strategy CRUD in `config-resources.ts` keeps its existing
  `configFileStorage.update()` calls UNCHANGED and becomes automatically
  encryption-correct: same path as everything else. The dual-path world is gone,
  which is why datastore records (P1) are born safe.
- `RemoteResourceState` stops reconstructing configs: push serializes the real
  on-disk config (minus `/state/*`, per 1.3), so nothing can be dropped.
- Per-field granularity is driven ENTIRELY by `schema/sensitivity.ts` via
  `walkSensitive` + `metaForPointer` (both exist and are tested in
  `schema/__tests__/walker.test.ts`); `encryptAtRest` already defaults to true for
  `secret`/`credential` kinds (`sensitivity.ts:47`). No parallel field list.
- The encrypted-fields container keeps the v2 shape
  (`encryption.encryptedFields: Record<pointer, EncryptedBlob>`) but pointers are now
  always CONCRETE leaf pointers, never the compound `'/resources'`.

### 2.3 Which fields encrypt at rest (v3 inventory)

Everything with kind `secret` or `credential` in the v3 registry (1.4):

| Pointer (v3) | Kind | v2 blob coverage |
|---|---|---|
| `/account/token` | secret | NO (escaped) |
| `/credentials/ssh/privateKey` | credential | yes (via sshContent) |
| `/credentials/cfDnsApiToken` | secret | **NO (escaped — named in R2-F3)** |
| `/resources/storages/*/vaultContent` | secret | yes |
| `/resources/repositories/*/tags/*/credential` | credential | yes |
| `/resources/repositories/*/tags/*/sshPrivateKey` | credential | yes |
| `/resources/repositories/*/tags/*/secrets/*/value` | secret | yes |
| `/resources/cloudProviders/*/apiToken` | secret | **NO (escaped — named in R2-F3)** |
| `/state/certCache/*/data` | credential | NO (lived at /infra, escaped) |

**The verifier exception [P0-DECIDED]**: `/credentials/masterPasswordVerifier` is kind
`secret` in the registry but MUST carry `encryptAtRest: false` (explicit override): it
is the value the CLI uses to CHECK the master password before any decryption can
happen; encrypting it under the password it verifies is a bootstrapping deadlock. It is
a verifier (not a recoverable secret), safe to store as designed. This override plus a
test asserting it survives the registry (2.5, test T4) prevents a future registry edit
from bricking every encrypted config.

Compound blob retirement: after the v2→v3 migration (§3, transform 5) no code reads or
writes `'/resources'`; the constant `RESOURCES_BLOB_POINTER` and both
`encryptSection`/`decryptSection` helpers in `resource-state.ts` are deleted.

### 2.4 Failure and prompt semantics

- Master-password prompt locations do not change: `getResourceState()`
  (`config-base.ts:63-67`) and any command reading a sensitive leaf. Commands that
  touch only public/spec fields (list machines, show placement) read the plaintext
  skeleton without prompting; encrypted leaves surface as
  `<encrypted:pointer>` stubs in `-o json` when no password was supplied, mirroring
  the existing `redactClone` stub convention.
- A wrong password fails at the verifier check before any write; a decrypt failure of
  an individual field (corrupt blob) is a hard error naming the pointer, never a
  silent drop.

### 2.5 Regression test spec (reproduces today's data loss)

`packages/cli/src/services/__tests__/persist-unification.test.ts` (vitest, temp config
dir via the existing config-file-storage test seams, master password injected by
stubbing `services/core/master-password.ts#requireMasterPassword`):

- **T1 (THE R2-F3 scenario, must fail on v2 code, pass on v3)**:
  1. Create config; enable master-password mode (set verifier + `mode: 'master-password'`).
  2. `configService.addCluster('c1', <minimal valid ClusterConfig>)`.
  3. `configService.addCloudProvider('hetzner', { apiToken: 'tok' })`; add one
     backup strategy.
  4. Mutate a repo through the resource state (`setRepositories`), then a machine
     (`setMachines`) — the v2 persist path that wipes `resources`.
  5. Reload from disk cold (new storage instance). Assert: cluster `c1`, provider
     `hetzner`, and the strategy all still exist. (On v2 this assertion fails: they
     are destroyed by `resource-state.ts:212`.)
- **T2 (per-field at-rest)**: with master-password mode on, after T1's writes read the
  RAW file bytes. Assert none of: the provider apiToken plaintext, `cfDnsApiToken`
  plaintext, any `sshPrivateKey` PEM header, any repo secret value. Assert
  `encryption.encryptedFields` keys are concrete pointers and `'/resources'` is absent.
- **T3 (round-trip)**: decrypt-on-load returns byte-identical values for every
  encrypted pointer; toggling mode master-password -> plaintext -> master-password
  round-trips all fields (the mode-downgrade branch at `resource-state.ts:237-238`
  is replaced by an explicit `config encryption disable` transform).
- **T4 (verifier bootstrap)**: `masterPasswordVerifier` is present in plaintext in the
  raw file while mode is master-password (the 2.3 exception), and login/verify works
  on a cold load.
- **T5 (state does not bump version)**: record `version`; write `pushState` and a cert
  cache entry via `updateState()`; assert `version` unchanged; write a machine via
  `update()`; assert `version` incremented by exactly 1.
- **T6 (remote push completeness)**: with a mock `RemoteConfigAdapter`, push after T1;
  assert the pushed document contains clusters/providers/strategies and does NOT
  contain `state`.

---

## 3. The v2→v3 migration (R2-F6)

Exactly ONE migration, no v2 tolerance afterward. Built on the real machinery:
`packages/shared/src/config-schema/migrations/` (registered in `index.ts` `MIGRATIONS`, pattern =
`v1-to-v2.ts` + `__tests__/migrations.test.ts`), fixtures at
`packages/cli/src/__tests__/fixtures/config/v*-sample.json`, gate =
`.ci/scripts/quality/check-config-migrations.sh` (round-trips every fixture through
`runMigrations` + `RdcConfigSchema.safeParse`).

### 3.1 Machinery changes

1. `CURRENT_SCHEMA_VERSION = 3`; `schemaVersion: z.literal(3)`; add
   `migrations/v2-to-v3.ts`; register; fixture `v3-sample.json`.
2. **The runner goes async with a context**:
   `migrate(raw, ctx: MigrationContext) => Promise<Record<string, unknown>>` where
   `ctx.getMasterPassword(): Promise<string>` lazily prompts (wired to the existing
   `requireMasterPassword`). Reason: unpacking the v2 compound blob (transform 5)
   requires the password at migration time; deferring it would keep the dual-path
   reader alive, which the redesign forbids. `runMigrations` and its single caller
   (`ConfigFileStorage.load()`, already async) absorb the `await`. v1-to-v2 ignores ctx.
   The gate script's inline tsx runner adds one `await` and passes a ctx whose
   `getMasterPassword` throws (fixtures are plaintext; an encrypted fixture cannot be
   gate-checked without a password and is covered in vitest instead).
3. Migration prints a one-line summary of every lossy/warned transform (7 below) to
   stderr; the migrated file is persisted immediately by `load()` (existing behavior).

### 3.2 Transform ledger (the complete list, 10 transforms)

1. **Stamp** `schemaVersion: 3`.
2. **Composite repo keys → families.** For each key in `resources.repositories`:
   `parseRepoRef(key)` semantics (split on first `:`); group records by base name.
   Bare key or `:latest` key → that family's grand: `grand: 'latest'`,
   `tags: { latest: record }`. Other keys → `tags[tag] = record`. Drop the redundant
   per-record `tag` field. If BOTH `shop` and `shop:latest` exist (already ambiguous
   in v2), REFUSE: migration error listing both keys and instructing a pre-migration
   `config repository remove` of one. A family with only fork records (grand deleted
   in v2) gets `grand` pointing at the lexicographically-first tag plus a stderr
   warning naming the family.
3. **Placement synthesis: none.** v2 stores no repo→machine mapping (the root cause 06
   §6 names), so the migration CANNOT invent placement; guessing would be a wrong-host
   deploy factory. `placement` is written ABSENT; every derived-machine operation on a
   placement-less family errors:
   `repository "shop" has no placement recorded (config migrated from v2). Run
   'rdc config reconcile' to discover it; if the machine is unreachable, set it
   manually with 'rdc config edit' (schema-validated).`
   (Gate C15: no `repo set-placement` leaf exists or will be added for a one-time
   migration path; reconcile + `config edit` are the two sanctioned routes.)
   `config reconcile` (§4) fills placement by matching `repositoryGuid` against each
   machine's `renet list all --json` repository inventory. **[P0-DECIDED]**
4. **Status extraction → state bucket**: move per repo record `networkId`, `pushState`,
   `headCommit`, `commitMessage`, `commitAuthor`, `commitParent`, `head`, `branches`,
   `reflog` into `state.repos[name][tag]`; move `defaults.nextNetworkId` →
   `state.networkIds.next`; move `infra.acmeCertCache` → `state.certCache`; move each
   `clusters[*].kvm.memberIds` → `state.clusters[<name>].memberIds`.
5. **Compound blob → per-field.** If `encryption.mode === 'master-password'` and
   `encryptedFields['/resources']` exists: prompt via ctx, decrypt the blob
   (`nonce:tag:ciphertext` format, `aes.ts` helpers), lay the contents into
   `resources.*` / `credentials.ssh`, delete the `'/resources'` entry, then re-encrypt
   per-field (the storage layer's `encryptFields` from 2.2 runs on save, so the
   migration only needs to materialize plaintext in memory; the save path does the
   rest). Wrong password = migration aborts cleanly, file untouched, re-runnable.
6. **Residue sweep (R2-F9)**: delete `defaults.machine`; delete `account.team` and
   `account.region`. (The `config set/clear` command vocabulary at
   `commands/config.ts:349-373` dies in P4; the schema keys die here so v3 never
   carries them.)
7. **`machines[*].ceph` retirement [P0-DECIDED: drop with warning]**: the field is
   deleted and a stderr warning names each machine and the equivalent
   `rdc datastore create <name> --cluster <c> --pool <pool>` to re-declare it. No
   auto-synthesis: v2's per-machine ceph pointer lacks the cluster anchor a v3
   datastore record requires, and the ops-fleet Ceph configs are being rebuilt in this
   redesign anyway (sole-operator, clean-break policy).
8. **Repo secret cap re-validation**: values over the new caps (§5) fail migration
   with the key named (the operator moves the payload out of config; a silent
   truncation of a secret is never acceptable).
9. **`deletedRepositories[*].name` composite split** → `{ name, tag }` with the same
   parse as transform 2 (`tag: 'latest'` when bare).
10. **Everything else passes through untouched**: machines (minus ceph), storages,
    clusters (minus kvm.memberIds), cloudProviders, backupStrategies, account,
    defaults, credentials, infra (minus acmeCertCache), remote, renetPath, and — via
    `.loose()` — unknown top-level keys.

### 3.3 Unknown and corrupt fields

- Unknown TOP-LEVEL keys: preserved verbatim (`.loose()` round-trip, existing v2
  behavior, kept).
- Unknown keys INSIDE known buckets: v2 sub-schemas are strict (Zod default strips),
  and migration operates pre-parse on raw JSON; the migration moves only known keys
  and leaves unrecognized siblings in place, then the post-migration
  `RdcConfigSchema.parse` surfaces them as validation errors if they collide with v3
  strictness. Net policy: migration never deletes data it does not understand;
  validation refuses rather than trims.
- Corrupt values (bad GUID, invalid cron, malformed encrypted blob): migration does
  NOT repair; the existing `load()` behavior (throw `ValidationError` with pointer
  paths, file left untouched on disk) is the contract. A config that cannot migrate
  is reported, never half-written: the migration runs on an in-memory copy and only
  `load()`'s single persist writes the result (existing atomicity via temp+rename).
- Downgrade refusal (`schemaVersion > 3`) kept as-is (`migrations/index.ts:51-55`).

### 3.4 Migration test + fixture plan

- Enrich `v1-sample.json`/keep `v2-sample.json` minimal; grow `v2-sample.json` into a
  representative plaintext config: bare repo key + `:latest` key + two fork keys with
  networkId/pushState/branches/reflog, a cluster with `kvm.memberIds`, a cloudProvider
  with apiToken, a backupStrategy, `defaults.machine`, `defaults.nextNetworkId`,
  `account.team/region`, `machines[*].ceph`, `infra.acmeCertCache`, an unknown
  top-level key. Add `v3-sample.json` (post-shape). The gate script round-trips all
  three unchanged in mechanism (its fixture regex `^v\d+-sample\.json$` and version
  loop already generalize).
- `migrations/__tests__/migrations.test.ts` additions, mirroring the existing
  patterns (idempotence, downgrade refusal, schema-pass):
  - every transform 1-10 asserted individually on targeted inputs;
  - **encrypted-blob unpack**: build a v2 config whose `'/resources'` blob was
    encrypted with a known test password (use `nodeCryptoProvider` directly), run
    migration with a ctx returning that password, assert per-field pointers exist,
    plaintext absent from the raw result, and values round-trip;
  - wrong-password abort leaves input untouched and is re-runnable;
  - `shop` + `shop:latest` collision refusal with both keys named;
  - idempotence: migrating a v3 doc is a no-op (`migrated: false` path);
  - output of the enriched `v2-sample.json` passes `RdcConfigSchema` and contains NO
    `defaults.machine`, `account.team/region`, `machines[*].ceph`,
    `infra.acmeCertCache`, composite repo keys, or `'/resources'` blob pointer.

---

## 4. `config reconcile` (and `config recover` interaction)

### 4.1 Inputs

- The spec half: `resources.machines` (SSH targets), `resources.datastores`,
  `resources.repositories`, `resources.clusters`.
- Per machine, over the existing SSH + renet execution path
  (`services/machine/machine-status.ts` already consumes it):
  `sudo renet list all --json` → `ListResult` (`private/renet/pkg/list/types.go:9`):
  `repositories[]` gives `name` (GUID directory), `repo_name` (friendly `name:tag`
  from the `.interim` mirror), `is_fork`, `grand_guid`, `mounted`, `mount_path`,
  `image_path`, plus (P1 addition, 1.3) `network_id`. `system.machine_id`,
  `system.hostname`, and `storage_health` feed machine/datastore state.
- P1 datastore verbs: `renet datastore status --json` per datastore (attach point,
  writes mode, loop/dm holders via `FindLoopDevicesFor` + `dmsetup ls`).
- For clusters: k3s version probe per node (P2 wires it; reconcile consumes),
  `renet ops list` on the KVM host for `memberIds`.

### 4.2 What it rebuilds (and what it only prunes)

Per the 1.3 ledger: rebuilds `state.datastores` (attachedTo/mounted/mountPath/holders),
`state.machines`, `state.clusters` (k3sVersion, nodes, memberIds where the KVM host
answers), `state.repos[*][*].networkId`, and re-seeds `branches` from on-machine commit
objects. Prunes state entries whose spec record is gone. Fills MISSING `placement`
(3.2 transform 3) by GUID match; it never OVERWRITES an existing placement (see 4.3).
Stamps `state.reconciledAt`. Writes via `updateState()` (no version bump); prints a
spec-vs-observed diff table; `-o json` supported (R2-F15).

### 4.3 Mismatch behavior

Reconcile separates OBSERVATION (state, safe to auto-heal) from DECLARATION (spec,
never auto-edited):

- state-vs-machine drift → rewritten silently (that is the verb's job).
- spec-vs-machine CONFLICT (a repo GUID observed on machine B while placement says
  machine A; a datastore image found on an unexpected host; the same GUID observed on
  two machines): NOT auto-fixed. Reported with both sides and the legitimate verbs:
  `repo migrate` for a move, `backup restore` for a pushed copy (06 §6.4b conflict
  vocabulary), `--accept-observed` **[P0-DECIDED]** as the explicit flag that rewrites
  placement to match observation (the R2-F18 rule: `-y` skips confirmation, only an
  explicit data-loss/authority flag changes meaning).
- Derived-routing verification at USE (1.3 property 3) is the runtime twin: any
  mismatch between the routing hint and reality is a hard error suggesting
  `config reconcile`, never a retry-elsewhere.

### 4.4 `config recover` interaction

`config recover` (restore a config file from backup) restores a possibly-stale `state`
bucket. Contract: stale state must degrade to a CLEAR ERROR, never a wrong-host deploy
(02 §11.1). Mechanics that guarantee it:
- Every derived-machine op verifies the hint at use (1.3 property 3); a stale
  `attachedTo` fails the verification and names `config reconcile` as the fix.
- Recover prints a standing warning:
  `restored config includes runtime state from <mtime>. Run 'rdc config reconcile'
  before deploy operations.` and stamps `state.reconciledAt` to the restored value so
  the staleness is visible in `config show`.
- Recover never triggers reconcile implicitly (it may run with the fleet unreachable;
  the errors-at-use contract already fails closed). **[P0-DECIDED]**

---

## 5. Secrets honesty (R2-F7)

1. **Size caps (gate C11, merged with spec 05)**: env-mode **32 KiB per value**,
   file-mode **256 KiB per value**, and **512 KiB aggregate per repo per mode**
   (replacing the single 10 MB cap at `schemas.ts:155` and its duplicate at
   `utils/config-schema.ts:69`, which must be deduplicated to one source). Rationale:
   the config file is atomically rewritten and remote-pushed WHOLE on every mutation,
   so multi-MB values tax every write; the k8s apiserver caps a Secret OBJECT at
   ~1 MiB, and each mode materializes as one Secret per repo namespace (§5.2), hence
   the per-mode aggregate; env blocks have single-string practical limits well under
   128 KiB. Anything larger is a file the data plane should carry, not the config
   plane. Enforcement: `SecretEntrySchema` superRefine (per-value, mode-dependent) +
   a family-level refine over `RepoRecordSchema.secrets` (per-mode aggregate);
   migration transform 8 re-validates all three numbers.
2. **`UPPER_SNAKE → env|file` k8s mapping [P0-DECIDED]**: per repo NAMESPACE (the k8s
   repo isolation unit, 02 §8), renet materializes at `up()`:
   - Secret `rediacc-env` (type Opaque): all env-mode keys. Injected into workloads via
     `envFrom: [{ secretRef: { name: rediacc-env }, prefix: REDIACC_SECRET_ }]`, so the
     in-container names are byte-identical to the docker world's
     `REDIACC_SECRET_<KEY>` contract.
   - Secret `rediacc-files` (type Opaque): all file-mode keys. Mounted as a volume at
     `/var/run/rediacc/secrets/` (one file per KEY, mode 0400), matching the docker
     world's tmpfs path shape (no `<networkId>` segment: the namespace is the scope).
     k8s Secret volumes are tmpfs-backed on the node, preserving the never-on-disk
     property at the node level.
   - Both objects carry the CONTRACT label **`rediacc.io/injected=true`** (gate C4:
     the key the fork secret-scrub and teardown enumerate on every renet-generated
     object; spec 05 owns the convention). `app.kubernetes.io/managed-by: renet` and
     `rediacc.io/repo: <guid>` ride along as informational labels only.
3. **Honesty statement (docs obligation)**: the write-only ceremony (TTY/agent reveal
   gating) protects the CONFIG-FILE surface only. Once materialized as k8s Secret
   objects, values are readable to anything with namespace access
   (`kubectl get secret -o yaml`), and to kine at rest unless k3s
   `--secrets-encryption` is enabled. The docs page for `repo secret` must say this in
   those words; parity note: the docker world's tmpfs/env materialization has the same
   property for anyone with repo-socket access.
4. **Idempotent re-inject IS the rotation story (stated, not implied)**:
   `repo secret set KEY --mode env` + `rdc repo up <name>` re-applies both Secret
   objects (apply semantics, deterministic names). File-mode values propagate to
   running pods via kubelet sync (~1 min) without restart; env-mode values require the
   pod restart that `up()`'s rollout already causes. No versioned-secret machinery, no
   dual-write windows: re-run `up()`, that is the contract, and the help text says so.

---

## 6. Reality deltas (spec-suite / code mismatches found while writing this)

1. **02 §11 cites `services/config/migrations/`**; the machinery actually lives at
   `packages/shared/src/config-schema/migrations/`. This spec uses the real path.
2. **`migrations/index.ts:14` comment says fixtures live at
   `packages/cli/tests/fixtures/config/`**; the gate script and the actual files use
   `packages/cli/src/__tests__/fixtures/config/`. Fix the comment in P1.
3. **`resource-state.ts:6-8` header claims "Encryption-at-rest is per-field (see Step
   13)"** while the implementation is the compound `'/resources'` blob (line 74
   admits it: "per-individual-field encryption is a future evolution"). The header
   describes v3, not the code it sits on.
4. **`sensitivity.ts:9-12` consumer list** cites `services/mutation-gate.ts` and
   `services/resource-state.ts`; post-reorg paths are `services/core/mutation-gate.ts`
   and `services/config/resource-state.ts`.
5. **`RemoteResourceState.persist` drops clusters/providers/strategies/infra on every
   push and hardcodes `schemaVersion: 2`** (`resource-state.ts:345-372`): the R2-F3
   bug has a remote twin the review did not name. Fixed by the same unification (2.2).
6. **Encryption-mode default reads `DEFAULTS.CONTEXT.CONFIG_KIND`**
   (`resource-state.ts:94`, value `'plaintext'` at
   `packages/shared/src/config/defaults.ts:336`): a misleadingly-named constant doing
   double duty; give v3 its own `ENCRYPTION_MODE_DEFAULT`.
7. **`renet list all --json` has no per-repo `network_id`** (`RepositoryInfo`,
   `pkg/list/types.go:143`; only `HealthDriftEntry` carries one). Reconcile needs it;
   named as a P1 renet addition in 1.3.
8. **Secret cap constant is duplicated** (`schemas.ts:155` and
   `utils/config-schema.ts:69`); §5's cap change must land in exactly one place.
9. **`clusters[*].kvm.memberIds` is written by the KVM provisioner into the spec half
   today** (`services/cluster/kvm-provisioner.ts`), bumping the version counter per
   boot: a live example of the R2-F2 churn problem, resolved by transform 4.
