# Spec 02 — The `RepoRuntime` Contract, Shared Contract-Test Suite, and Placement Dispatch

P0 implementation spec for design 02 §9 (runtime abstraction), 02 §4/§8 (the policy
invariants the contract enforces), 03 §2 (hygiene + convergence rules), 04 §4 (lifecycle
health gate), 09 §P1 (interface skeleton + contract tests land first). Everything marked
[P0-DECIDED] is a decision this spec makes; everything else restates a decision the design
suite already made, with the file/section reference.

All renet paths are relative to `private/renet/`; all CLI paths relative to
`packages/cli/`.

---

## 1. The `RepoRuntime` interface

### 1.1 Where it lives

[P0-DECIDED] New package **`pkg/reporuntime`** (import path
`github.com/rediacc/renet/pkg/reporuntime`).

- Not `pkg/runtime` (shadows the stdlib import in every file that touches goroutines or
  GC knobs).
- Not inside `pkg/repository` (that package is the docker/LUKS storage lifecycle, which
  the runtime explicitly must NOT touch) and not inside `pkg/kube` (one implementation
  cannot own the contract).
- Single package holding the interface plus both implementations
  (`reporuntime.go`, `env.go`, `leak.go`, `docker.go`, `kube.go`, `factory.go`),
  following the repo's established one-package-many-backends precedent:
  `pkg/datastore` (`backend_local.go` / `backend_ceph.go` under one `DatastoreBackend`
  interface, `backend.go:109`) and `pkg/kube/distro` (`k3s.go` / `external.go` under one
  `Distro` interface, `distro.go:119`).
- Dependency direction: `reporuntime` imports `pkg/orchestration`, `pkg/kube`,
  `pkg/kube/distro`, `pkg/list`. Nothing under those packages imports `reporuntime`
  (callers are `cmd/renet` and `pkg/functions/commands`). The existing
  `orchestration.Runtime` string type ("compose" | "kube", `pkg/orchestration/
  rediaccfile.go:497`) stays as the in-image `.rediacc.json` declaration; it is a
  different (demoted, lint-only) concept — see §3.4.

### 1.2 The interface, verbatim-ready

Names refine the 02 §9 list (`Deploy/Teardown/Fork/Status/InjectSecrets/Health/
ProvisionVolumes/ApplyIsolation` — all eight kept, signatures decided here).

```go
package reporuntime

import "context"

// Type identifies a repo runtime implementation.
type Type string

const (
	TypeDocker Type = "docker"
	TypeKube   Type = "kube"
)

// Role is the effect-isolation role a repo runs under (design 02 §4). It is
// injected as REDIACC_ROLE into every lifecycle hook and, for kube, published
// as the per-namespace role ConfigMap.
type Role string

const (
	RolePrimary   Role = "primary"
	RoleFork      Role = "fork"
	RoleRehearsal Role = "rehearsal"
	// RoleReplica is reserved for `repo replicate` read-only attaches
	// (05 §1, consumed in P3; gate C12). Defined now so the enum matches the
	// ROLE ConfigMap and kube_identity_rewrite role params from day one.
	RoleReplica Role = "replica"
)

// Writes is the fork-attach write disposition (design 03 §2), REDIACC_WRITES.
// Empty for a plain (non-fork) datastore.
type Writes string

const (
	WritesCeph  Writes = "ceph"
	WritesLocal Writes = "local"
)

// RepoHandle is everything the datastore layer hands a runtime. Every path in
// it is ALREADY mounted and writable. A RepoRuntime never mounts, unmounts,
// maps, unlocks, reflinks, or snapshots storage; it consumes paths. That rule
// is the load-bearing boundary of design 02 §9 (Ceph stays below, invisible)
// and is contract-tested (CT-10).
type RepoHandle struct {
	// Name is the composite repo name as the orchestration layer knows it
	// ("shop" for a grand repo, "shop:test" for a fork) — the value that
	// becomes REDIACC_REPO_NAME today (pkg/orchestration/up_down_workflows.go).
	Name string
	// GUID is the repository GUID (mount dir basename in the docker world).
	GUID string
	// NetworkID is the repo's network identity (per-repo dockerd socket /
	// loopback range in docker; per-networkID k3s unit at cluster scope).
	// Zero for kube repos, whose network identity is the namespace.
	NetworkID int
	// Datastore is the datastore NAME (REDIACC_DATASTORE). For a docker repo
	// on the implicit default datastore this is "default".
	Datastore string
	// DatastoreMount is the datastore's mount root (<ds-mount>).
	DatastoreMount string
	// RepoPath is the repo's own root: the LUKS mount path for docker
	// (/mnt/rediacc/mounts/<guid>), <ds-mount>/repos/<repo> for kube.
	// Rediaccfiles are discovered under it for BOTH runtimes.
	RepoPath string
	// Role and Writes feed the REDIACC_ROLE / REDIACC_WRITES contract.
	Role   Role
	Writes Writes
	// GrandGUID is the ancestry root for forks (empty for grand repos) —
	// generalizes the existing IsFork/GrandGuid state
	// (pkg/repository/state.go:38-39).
	GrandGUID string
	// Cluster and Namespace are set for kube repos only: the owning cluster
	// name and the repo namespace (a k8s repo IS its namespace).
	Cluster   string
	Namespace string
}

// VolumeSpec is one declared volume. Kube: one per declared PVC (parsed from
// the persisted manifests, today's kube.PVCInfo / pv.PVCSpec). Docker: always
// empty — the LUKS image IS the volume and the storage layer owns it.
type VolumeSpec struct {
	Name string // PVC name
	Size string // "10Gi" — capacity of the per-volume LUKS image (review F8)
}

// SecretSet is the config-sourced secret payload for one repo. Values arrive
// only through this parameter; a runtime never reads the CLI config itself.
type SecretSet struct {
	// Env: UPPER_SNAKE name -> value. Docker: exported as
	// REDIACC_SECRET_<NAME> into lifecycle env (existing behavior,
	// packages/cli/src/services/state.ts:215-219). Kube: one Opaque Secret
	// object per repo namespace (02 §4, new work).
	Env map[string]string
	// Files: name -> content. Docker: materialized under
	// /var/run/rediacc/secrets/<networkID>/ (pkg/orchestration/
	// secret_files.go). Kube: Secret object mounted per the declared mapping
	// (02 §11 item 5).
	Files map[string][]byte
}

// DeployOptions mirror today's up surface (UpOptions,
// pkg/orchestration/up_down_workflows.go:48).
type DeployOptions struct {
	Detach         bool
	SkipCheckpoint bool // docker CRIU restore skip; ignored by kube
}

// TeardownOptions mirror today's down surface (DownOptions, :76).
type TeardownOptions struct {
	Checkpoint bool // docker CRIU checkpoint before stop; ignored by kube
	Force      bool
}

// HealthState is one evaluation's verdict (04 §4, reconciled contract
// gate C5). Health is a SINGLE evaluation; the retry loop over Warming
// verdicts lives in the gate caller (cluster/migrate layer), not here.
type HealthState string

const (
	Healthy HealthState = "healthy"
	// Warming: health() exited 75 (EX_TEMPFAIL) or a per-attempt timeout
	// fired — the app is still starting. The gate caller retries within its
	// window (default 300 s, 30 s per attempt; flags owned by the CLI spec).
	Warming   HealthState = "warming"
	Unhealthy HealthState = "unhealthy"
	// HealthUnknown: no health() defined and no runtime-level readiness
	// signal available. The migrate/fork health gate treats Unknown per
	// policy (gate passes with a warning), never as Unhealthy.
	HealthUnknown HealthState = "unknown"
)

// HealthReport is the result of one health evaluation.
type HealthReport struct {
	State  HealthState `json:"state"`
	Detail string      `json:"detail,omitempty"`
}

// RepoStatus is the read-only status snapshot (docker: container/daemon
// summary from pkg/list; kube: namespace workload summary).
type RepoStatus struct {
	Running   bool              `json:"running"`
	Role      Role              `json:"role"`
	Workloads []WorkloadStatus  `json:"workloads,omitempty"`
	Extra     map[string]string `json:"extra,omitempty"`
}

// WorkloadStatus is one container (docker) or one Deployment/StatefulSet (kube).
type WorkloadStatus struct {
	Name  string `json:"name"`
	Ready bool   `json:"ready"`
	State string `json:"state"`
}

// RepoRuntime is how a repo runs: one contract, two implementations
// (design 02 §9). Method ORDER below is the canonical `up` sequence:
// ProvisionVolumes -> ApplyIsolation -> InjectSecrets -> Deploy.
// Policy invariants (fork => scrubbed secrets + regenerated credentials +
// Role != primary; migrate => secrets re-injected + identity preserved;
// ROLE/WRITES/DATASTORE env in every hook; leak-reporting teardown) live at
// THIS interface and are asserted once for both worlds by the contract suite
// (§2). A RepoRuntime never touches storage: it is handed mounted paths.
type RepoRuntime interface {
	// Type returns the implementation identity.
	Type() Type

	// ProvisionVolumes materializes the repo's declared volumes so Deploy
	// can bind them. Idempotent and adoptive: an existing volume image keeps
	// its data (today's pv.Provisioner.Provision semantic, cited at
	// pkg/kube/deploy.go:57 and pkg/kube/namespace.go:211). Docker: no-op.
	// Kube (layout per spec 05 §2, gate C1): per-volume LUKS image at
	// <RepoPath>/volumes/<pvc>.img, MOUNTED OUTSIDE the repo folder at
	// <ds-mount>/mounts/volumes/<repo>/<pvc>/ (no mountpoints inside
	// repos/<repo> — the reflink fork unit must stay mount-boundary-free),
	// plus a static `local`-type PV (nodeAffinity on rediacc.io/ds-<name>)
	// and the per-datastore no-provisioner StorageClass (02 §2, F5/F8).
	ProvisionVolumes(ctx context.Context, h RepoHandle, vols []VolumeSpec) error

	// ApplyIsolation converges the runtime's isolation primitives for the
	// repo (02 §8 parity table). Docker: per-repo dockerd + eBPF exec cgroup
	// + Landlock sandbox options (all existing; this method makes them an
	// asserted contract instead of scattered side effects). Kube: namespace +
	// default-deny ingress NetworkPolicy + hostPath/hostNetwork
	// ValidatingAdmissionPolicy + PSA label (templates: sibling P0 spec for
	// 02 §8). Idempotent.
	ApplyIsolation(ctx context.Context, h RepoHandle) error

	// InjectSecrets materializes s for the repo. Values never land inside
	// RepoPath (CT-12): docker writes host-side under /var/run/rediacc,
	// kube creates labeled Secret objects (label convention §1.5). Re-running
	// re-injects idempotently — that IS the rotation story (02 §11 item 5).
	InjectSecrets(ctx context.Context, h RepoHandle, s SecretSet) error

	// Deploy runs the repo's lifecycle up: Rediaccfile discovery +
	// validation + up() execution with the runtime-specific env (§1.4).
	// Deploy MAY internally re-run ProvisionVolumes as a convergence step
	// (both are idempotent); it MUST NOT inject secrets (the caller decides,
	// because fork/rehearsal deploys run secretless by policy, 04 §4).
	Deploy(ctx context.Context, h RepoHandle, opts DeployOptions) error

	// Teardown runs lifecycle down and releases runtime state. It is
	// leak-reporting (§1.6): a non-nil *TeardownLeak with a nil error means
	// the teardown succeeded but state survived that costs storage; the
	// caller surfaces it and a re-run converges (CT-6/CT-7). An error means
	// the teardown itself failed and nothing was lied about — lazy-success
	// (`umount -l` and friends) is forbidden by contract (03 §2 rule 2).
	Teardown(ctx context.Context, h RepoHandle, opts TeardownOptions) (*TeardownLeak, error)

	// Fork performs the RUNTIME half of a repo fork, after the storage layer
	// has already cloned bytes (reflink / RBD clone). It establishes the
	// child's runtime identity and enforces the new-principal policy:
	// credentials regenerated, secrets absent, Role rewritten (never
	// primary). See §1.7 for the per-runtime scope and the cluster-level
	// boundary. parent is read-only context (source paths for manifest
	// rewrite); child.Role MUST be RoleFork or RoleRehearsal (error
	// otherwise, CT-3).
	Fork(ctx context.Context, parent, child RepoHandle) error

	// Status returns a read-only snapshot. MUST NOT mutate anything (CT-15).
	Status(ctx context.Context, h RepoHandle) (*RepoStatus, error)

	// Health runs ONE evaluation of the repo health gate (04 §4, gate C5):
	// the Rediaccfile health() function layered on the runtime-level
	// readiness signal (§1.8). Never returns an error for "health() not
	// defined" — that is HealthUnknown. Warming verdicts are retried by the
	// gate CALLER, not by this method.
	Health(ctx context.Context, h RepoHandle) (*HealthReport, error)
}
```

Error contract (package-level sentinels, matched with `errors.Is`):

```go
var (
	// ErrNotDeployed: Deploy/Fork asked to act on a repo that was never
	// deployed (kube: no persisted manifests — today's "no persisted
	// manifest for namespace %s" error, pkg/kube/namespace.go:258).
	ErrNotDeployed = errors.New("reporuntime: repository was never deployed")
	// ErrWrongRuntime: the handle's placement-derived runtime contradicts
	// the repo's on-disk declaration (§3.4 conflict rule).
	ErrWrongRuntime = errors.New("reporuntime: repo declares a different runtime")
	// ErrHoldersPresent: teardown found live holders (kubelet volume mounts,
	// loop/dm devices) and refuses to proceed — the detach-before-unlink
	// rule surfacing at the runtime boundary (03 §2 rules 1-2).
	ErrHoldersPresent = errors.New("reporuntime: storage holders still present")
	// ErrRoleViolation: Fork called with child.Role == RolePrimary.
	ErrRoleViolation = errors.New("reporuntime: fork/rehearsal role must not be primary")
)
```

`orchestration.ErrFunctionNotDefined` (`pkg/orchestration/rediaccfile.go:23`, the exit-42
sentinel) stays where it is; `Health` consumes it internally and maps it to
`HealthUnknown`.

CLI exit-code mapping (gate G1): the authoritative four-row table lives in spec 03 §1;
this spec concurs with the review's proposal — `ErrRoleViolation` → 2,
`ErrNotDeployed` → 5, `ErrWrongRuntime` → the state-mismatch code,
`ErrHoldersPresent` → the busy code, with spec 03 fixing the exact numbers.

### 1.3 Rules restated as enforceable statements

1. **No storage access.** The runtime's constructors take `RepoHandle` +
   injected tool seams only; no `datastore.DatastoreBackend`, no `pkg/luks`, no
   `pkg/loop`, no `pkg/rbd` imports in `docker.go`/`kube.go`. Enforced by (a) the
   compile-time absence of those imports (checked by the dead-code/lint gate diff in
   `check:ci-renet`) and (b) CT-10's recording fixture.
2. **Policy at the interface.** The fork/migrate/env/teardown invariants are
   documented on the interface (above) and asserted once by the shared suite (§2), not
   re-derived per implementation.
3. **Idempotency.** `ProvisionVolumes`, `ApplyIsolation`, `InjectSecrets`, `Deploy`,
   `Teardown` are all safe to re-run against half-broken state and must converge
   (03 §2 rule 4, R2-F15 table). CT-8/CT-9.

### 1.4 Lifecycle env: the shared injection helper

[P0-DECIDED] One pure function in `pkg/reporuntime/env.go` builds the policy env for
every lifecycle hook (up/down/health), used by BOTH implementations so the contract test
asserts a single source:

```go
// LifecycleEnv returns the policy environment injected into every Rediaccfile
// lifecycle hook (up/down/health) for both runtimes (design 02 §4):
//   REDIACC_ROLE      primary|fork|rehearsal|replica
//   REDIACC_WRITES    ceph|local ("" omitted for a plain datastore)
//   REDIACC_DATASTORE <datastore name>
// plus the existing identity vars the docker world already injects
// (REDIACC_REPOSITORY, REDIACC_REPO_NAME, REDIACC_REPO_TAG,
// REDIACC_WORKING_DIR — pkg/orchestration/up_down_workflows.go:209-216).
func LifecycleEnv(h RepoHandle) map[string]string
```

Wiring with minimal churn:

- **Docker**: `UpOptions`/`DownOptions` gain one field, `ExtraEnv map[string]string`;
  `UpServices`/`DownServices` fold it into the existing `executor.SetEnv` block
  (`up_down_workflows.go:209` and `:345`). `DockerRuntime.Deploy` passes
  `LifecycleEnv(h)`. The docker-specific vars (`DOCKER_HOST`, `DOCKER_SOCKET`,
  service `*_IP` exports, `REDIACC_NETWORK_ID`) stay exactly where they are.
- **Kube**: the same map goes into the Rediaccfile executor env (kube repos already run
  their lifecycle through Rediaccfile `up()`, deploy comment at `pkg/kube/deploy.go:94`),
  with `KUBECONFIG` instead of `DOCKER_HOST`. Additionally `Deploy` converges a
  **per-namespace ConfigMap** pods can `envFrom` (02 §4):

  [P0-DECIDED] ConfigMap name **`rediacc-role`**, in the repo namespace, data =
  exactly the three policy keys (`REDIACC_ROLE`, `REDIACC_WRITES`,
  `REDIACC_DATASTORE`). `Fork` rewrites it (otherwise a fork boots claiming
  role=primary — F2). Applied via the same `kubectl apply` path as manifests
  (`Wrapper.applyBytes`, `pkg/kube/deploy.go:194`), so it needs no new plumbing.

- `EnsureEnvrc` (`up_down_workflows.go:455`) adds the same three keys to the managed
  `.envrc` block so interactive sessions see the role too.
- **Registry env (gate G3)**: a kube repo that opts into the per-repo image registry
  (spec 05 §5: one `rediacc-registry-<networkID>` zot unit, store at
  `repos/<repo>/registry/`) additionally receives `REDIACC_REGISTRY_HOST`
  (`registry.<repo>.rediacc.internal`) and `REDIACC_REGISTRY` (`<host>:<port>`, port
  allocated at repo create and recorded in v3 `state.repos` next to the networkId —
  spec 04 owns the field) in its lifecycle env. Not part of `LifecycleEnv`'s policy
  trio; injected by `KubeRuntime.Deploy` alongside `KUBECONFIG`. Unset for docker
  repos and for kube repos without the registry opt-in.

### 1.5 `DockerRuntime`: wrapping existing behavior (method-by-method map)

`DockerRuntime` is a thin adapter over code that already works; P1 explicitly builds it
first to prove the contract against reality (09 §P1). Struct holds an
`*orchestration.Orchestrator` factory plus the tool seams.

| Method | Wraps (existing code path) | Delta needed |
|---|---|---|
| `Deploy` | `Orchestrator.UpServices` (`pkg/orchestration/up_down_workflows.go:113`): SafeStartup, Rediaccfile discovery (`rediaccfile.go:67`), `ValidateRediaccfile`/`ValidateRuntime` (`rediaccfile.go:396`/`:569`), env block, `ExecuteUp` (`rediaccfile.go:269`). Bridge surface: `repository_up` (`pkg/functions/commands/repository.go:1037`). | `ExtraEnv` field (§1.4). Mount/unlock moves OUT: `UpServices` today auto-mounts via `SafeStartup(Mount: !mounted)`; under the contract the datastore layer mounts first and hands the path. Transitional: `DockerRuntime.Deploy` asserts mounted and errors (no auto-mount), the bridge keeps the mount step before constructing the handle. |
| `Teardown` | `Orchestrator.DownServices` (`up_down_workflows.go:302`) + `SafeShutdown` (`VerifyDeviceMapper: true`). | Convert the current `errors.Join(downErr, unmountErr)` (`:404`) into the leak contract: down() failures stay errors; post-down survivors (device-mapper still open, loop still attached, secrets dir not purged) become a `*TeardownLeak`. Reuse `FindLoopDevicesFor` + the `loopController` seam (`pkg/datastore/loop.go`, `backend_local.go`) — 03 §2 says do not reimplement. |
| `Fork` | Storage half: `renet repository fork` (bridge builder `RepositoryForkCommand`, `pkg/functions/commands/repository.go:582`). Runtime/identity half TODAY is split across renet state marking (`IsFork`/`GrandGuid`, `pkg/repository/state.go:38-39`, applied at up via `--grand-guid`) and the CLI: `registerFork` (`src/commands/repo-fork.ts:152-179`) mints a new GUID, allocates a new networkId, generates a **new SSH keypair** (`:167`, `generateSSHKeyPair`), and **omits the parent's `secrets` map** (the `addRepository` payload carries no secrets key), while sharing the parent's LUKS `credential` (the cloned image needs it). | `DockerRuntime.Fork` makes the renet-side half explicit: write fork state (Role, GrandGUID) into the repo state, verify no secret material exists for the child networkID (`/var/run/rediacc/secrets/<childNetID>` absent — `SecretsDir`, `pkg/orchestration/secret_files.go:40`). The CLI-side keypair/secret-omission behavior is already correct; it becomes CT-1/CT-2 assertions (docker leg partially vitest-side, see §2.5). |
| `Status` | `repository_status` bridge (`repository.go:1372`) / `pkg/list` (`list/repositories.go`). | Mapping into `RepoStatus`; `pkg/health` drift registry (`pkg/health/registry.go`, container healthcheck drift) feeds `WorkloadStatus.Ready`. |
| `InjectSecrets` | Env mode: CLI prefixes `REDIACC_SECRET_<NAME>` (`src/services/state.ts:215-219`) and threads them through `buildRenetEnvPrefix` (`src/services/executor/local-executor.ts:581`, `:1128`). File mode: `--secret-file NAME=<b64>` flags (`appendSecretFileFlags`, `repository.go:18`, used at `:1081`) materialized by `WriteSecretFiles` into `/var/run/rediacc/secrets/<networkID>/` (`secret_files.go`). | Consolidate the renet-side landing zone behind the method: `InjectSecrets` = write files via the existing `WriteSecretFiles` + stage env for the next `Deploy`. No transport change: values still arrive per-invocation from the CLI config (secrets never live on the machine at rest). |
| `Health` | Nothing (docker has no repo health gate today; container-level signal only: `pkg/health` registry + router watchdog). | NEW: execute `health()` via `RediaccfileExecutor.ExecuteFunction(info, "health")` (`rediaccfile.go:204`); exit-42 sentinel → try next Rediaccfile; all undefined → fall back to the `pkg/health` drift registry (any drifting container ⇒ Unhealthy; none ⇒ Healthy if containers running, Unknown if none expected). See §1.8. |
| `ProvisionVolumes` | n/a | Documented no-op returning nil (the LUKS image is the volume; the storage layer owns it). |
| `ApplyIsolation` | Per-repo dockerd + eBPF exec cgroup (`OpenExecCgroupFD`, `up_down_workflows.go:167`) + Landlock sandbox options (`buildSandboxOptions`, `:416`) + `.rediacc.json`/BPF preseed (`EnsureRediaccConfig`, `:520`). | Extraction, not new behavior: the method converges daemon+cgroup+sandbox config so `Deploy` can assume it. Contract value: the suite can now assert isolation exists rather than trusting SafeStartup's side effects. |

### 1.6 `TeardownLeak`: generalizing `NamespaceTeardownLeak`

Today's `kube.NamespaceTeardownLeak` (`pkg/kube/ceph_backend.go:46`) carries
Ceph-specific fields (`RadosNamespace`, `Pool`, `Images`) that the delete ledger removes
(02 §6). The generalized type keeps its two proven semantics — **non-fatal reporting**
("the k8s namespace is already gone by then, so failing would strand the caller",
`namespace.go:38-42`) and **keep-state-so-a-re-run-converges** (`cleanupNamespaceState`,
`namespace.go:58`) — and drops the Ceph vocabulary:

```go
// TeardownLeak names the state a teardown could not remove. nil = clean.
// A non-nil leak with a nil error means teardown succeeded but survivors
// cost real storage; the caller surfaces the leak (CLI: warning + -o json
// field; state bucket: recorded for storage-health's inventory sweep,
// 03 §2 rule 3) and a repeated Teardown converges.
type TeardownLeak struct {
	Runtime Type     `json:"runtime"`
	Repo    string   `json:"repo"`
	// Paths: surviving dirs/images (volume images, manifests dir, secrets dir).
	Paths []string `json:"paths,omitempty"`
	// Holders: loop/dm devices or kubelet mounts still attached — these also
	// make Teardown FAIL (ErrHoldersPresent) rather than merely leak, per
	// the detach-before-unlink rule; they appear here when Force reporting.
	Holders []string `json:"holders,omitempty"`
	// Objects: surviving cluster-scoped objects (kube: PV objects, the
	// StorageClass when the last repo of a datastore leaves).
	Objects []string `json:"objects,omitempty"`
	Reason  string   `json:"reason"`
}
```

`notef`-style accumulation (whitespace-collapsed multi-step reasons) is carried over
verbatim from `ceph_backend.go:62`.

### 1.7 `KubeRuntime` on the repo-as-folder model

`KubeRuntime` wraps `kube.Wrapper` (`pkg/kube/wrapper.go:28`) after the delete ledger has
run (02 §6: `CephPool`/`CephCluster` fields, `EnsureCephBackend`, `resolvePVBackend`,
`.rbd-backend.json` markers, `forkNamespaceRBD` all deleted; the wrapper keeps
`KubeconfigPath`/`Namespace`/`Cluster`/`Datastore`/sandbox/`applyBytes`).

| Method | Implementation on the new model |
|---|---|
| `ProvisionVolumes` | Successor of `materializeAndBindPVs` (`pkg/kube/deploy.go:58`), on the gate-ruled layout (C1, spec 05 §2 wins): for each declared PVC, create + open a per-volume LUKS image at `<RepoPath>/volumes/<pvc>.img` and mount it OUTSIDE the repo folder at `<ds-mount>/mounts/volumes/<repo>/<pvc>/` — the invariant is **no mountpoints inside `repos/<repo>/`**, so the fork unit stays a single mount-boundary-free reflink and never byte-copies decrypted plaintext. Then apply a `local`-type PV (whose `local.path` is the mounts-tree path, deterministic and identical across machines so PV objects in kine survive fork/migrate unrewritten) with `nodeAffinity` on `rediacc.io/ds-<name>` + `storageClassName: rediacc-ds-<name>` referencing the per-datastore no-provisioner/WFFC StorageClass (02 §2). Replaces `GenerateLocalPVManifest`'s hostPath PV (`deploy.go:33`). Adoptive-idempotent like today's `Provision`. LUKS keying for volume images: datastore-layer concern; the runtime receives mounted volume paths on redeploy (consistent with rule 1) — first-provision is the one place the runtime REQUESTS creation through an injected `VolumeProvisioner` seam handed in by the factory, so the LUKS/loop work still lives storage-side. |
| `ApplyIsolation` | `NamespaceCreate` (`pkg/kube/namespace.go:17`, keeps the reserved-token check) + apply the per-repo default-deny ingress NetworkPolicy + the hostPath/hostNetwork ValidatingAdmissionPolicy + PSA label (02 §8; templates and the F9 proxy-datapath resolution are the sibling P0 spec deliverable — this method is their apply-site). |
| `InjectSecrets` | NEW (02 §4: extend the docker model to k8s). Env map → one Opaque Secret **`rediacc-env`**; each file entry → key in one Opaque Secret **`rediacc-files`** [P0-DECIDED names], both in the repo namespace, applied via `applyBytes`. Labeled per §1.5a below. Re-apply = rotation. Nothing written under `{ds}/manifests` (CT-12: a fork must not inherit secret manifests via the persisted-manifest replay). |
| `Deploy` | Rediaccfile `up()` execution with kube env (KUBECONFIG + `LifecycleEnv`), exactly as k8s repos already deploy ("Apply is the deploy path a Rediaccfile up() calls", `deploy.go:94`); the Rediaccfile calls `renet kube -- apply ...` which lands in `Wrapper.Apply` (`deploy.go:100`): render (namespace stamp + router annotations + reserved-token check), persist under `{ds-mount}/manifests/...` (`ManifestsDir`, `deploy.go:15` — path moves INSIDE the repo folder, §note below), apply. Redeploy path = `Wrapper.Deploy` (`deploy.go:137`). Converges the `rediacc-role` ConfigMap (§1.4). |
| `Teardown` | Rediaccfile `down()` + `NamespaceDelete` (`namespace.go:33`) minus the Ceph legs; leak mapping: `PVImageDir`-style survivors → `TeardownLeak.Paths`, surviving PV objects/StorageClass → `.Objects`. NEW hygiene leg: unmount + close + detach every per-volume LUKS image (deepest-first, plain unmount, verify — kubelet still holding a volume mount ⇒ `ErrHoldersPresent`, 03 §2 rule 2). |
| `Fork` | Runtime half of a same-cluster namespace fork, after the datastore layer reflinked `<ds-mount>/repos/<repo>` → `<ds-mount>/repos/<repo>-<tag>` (the repo folder carries volumes AND manifests together, so `ForkNamespacePrepare`'s per-image clone loop, `namespace.go:100`, collapses to: read persisted manifests from the CHILD's own folder). Steps: rewrite manifests to the child namespace via `RenderManifest` (re-stamps router annotations, re-checks reserved tokens — `namespace.go:133-139` behavior kept), `ApplyIsolation(child)`, `ProvisionVolumes` in adopt mode (binds the reflinked images as PVs, `namespace.go:208-223` behavior kept), write the `rediacc-role` ConfigMap with the child Role, apply. Secrets: NOT injected; contract asserts zero `rediacc.io/injected=true` Secrets in the child namespace post-Fork (CT-1). |
| `Status` | Namespace workload summary via wrapper kubectl (`get deploy,sts,ds,pods -o json`), mapped to `WorkloadStatus`. |
| `Health` | Layered (04 §4): (1) Rediaccfile `health()` if defined; (2) else k8s readiness: all namespace workloads Available/Ready within a timeout ⇒ Healthy; (3) the control plane itself is NOT this method's job — that is `distro.Healthcheck` (`pkg/kube/distro/distro.go:150`, bridge `kube_health`, `pkg/functions/commands/kube.go:134`), called by the cluster layer before per-repo gates. |

Note on `ManifestsDir`: today manifests persist at `{datastore}/manifests/<cluster>/<ns>`
(`deploy.go:15`), OUTSIDE the repo's own tree — under repo-as-folder they move to
`<ds-mount>/repos/<repo>/manifests/` so a repo folder is self-contained and a reflink
fork carries its manifests by construction. [P0-DECIDED] (Without this move, `Fork`
would need the old cross-tree manifest copy and the "fork carries everything by
construction" claim of 04 §2.8 would be false at repo scope.)

**Cluster-level boundary.** `RepoRuntime.Fork` is repo-scope. The whole-cluster fork
(04 §2) is a CLUSTER-layer composition: group snap → clones → attach → **CP identity
rewrite with fork-mode PKI regeneration + kine secret scrub + ROLE rewrite** (the F1/F2
step, specced in the fork-scrub P0 spec; today's migrate-shaped seam is
`K3sDistro.RewriteIdentity`, `pkg/kube/distro/identity.go:63`, which preserves the CA —
correct for migrate only) → per-repo `runtime.Deploy` + `runtime.Health`. The
CONTRACT-level invariants (CT-1..CT-4) still name the cluster case: the kube legs of
CT-1/CT-2 are verified end-to-end at cluster-fork scope (§2.5), because that is where
kine rides the snapshot and where the parent's CA would otherwise survive.

#### 1.5a Secret label convention (gate C4: spec 05's convention rules)

The CONTRACT label is **`rediacc.io/injected: "true"`**, stamped on EVERY
renet-generated object (Secrets, the `rediacc-role` ConfigMap, NetworkPolicy, VAP, PV
objects) — this is what the fork scrub (spec 05 F4.1) and teardown enumerate.
`app.kubernetes.io/managed-by: renet` and `rediacc.io/repo: <repo>` may ride along as
informational labels; nothing keys on them. Unlabeled third-party Secrets are scrubbed
by default under fork/rehearsal (02 §4).

### 1.8 The health() contract (04 §4; reconciled at the gate, C5)

A dedicated optional **`health()`** Rediaccfile function, NOT an `info()` exit-code
convention — this half was decided independently and identically by spec 02 and spec 05
and is CONFIRMED. Rationale: `info()` is an existing informational hook with established
semantics in shipped Rediaccfiles; overloading its exit code would make today's
decorative failures suddenly gate migrations. Mechanics are the gate-ruled merge
(spec 05 base + this spec's sentinel carve-out):

- exit 0 ⇒ Healthy.
- **exit 75 (EX_TEMPFAIL) ⇒ Warming**: the app is still starting; the gate caller
  retries. The gate runs right after cutover/boot where warm-up is the common case; a
  single-shot probe would force every app to implement its own retry loop inside
  health().
- any other nonzero ⇒ Unhealthy immediately (stderr tail becomes `Detail`); the gate
  fails without waiting out the window.
- **exit 42 is reserved** (the executor's function-not-defined sentinel,
  `rediaccfile.go:220`) ⇒ treated as "health() undefined" ⇒ runtime-readiness fallback
  ⇒ Unknown when no signal. A user health() must not return 42.
- Per-attempt timeout **30 s**; a timeout counts as one Warming (75). The retry LOOP and
  the gate window (default **300 s**; flags per spec 03, gate G6) live in the gate
  caller (cluster/migrate layer) — `RepoRuntime.Health` is ONE evaluation returning
  the `Warming` disposition (§1.2 `HealthState`).
- Layering per spec 05 §6: distro `/readyz` (cluster layer, before per-repo gates) →
  runtime readiness / container-health default → health().
- Runs with the full lifecycle env (`LifecycleEnv` + runtime env), sandboxed exactly like
  up()/down() (same executor, CT-5 asserts the env).
- Multi-Rediaccfile repos: health() runs in discovery order; first Unhealthy wins;
  any Warming (with no Unhealthy) ⇒ Warming; all-undefined ⇒ fallback.

---

## 2. The shared contract-test suite

### 2.1 Shape: one suite, two fixtures, two levels

**Level A — pure-Go contract tests** (run in plain `go test ./...`, no VM, no root):
the suite is a set of numbered subtests driven through a fixture interface, executed
twice — once per implementation — from `pkg/reporuntime/contract_test.go`:

```go
func TestDockerRuntimeContract(t *testing.T) { runContract(t, newDockerFixture) }
func TestKubeRuntimeContract(t *testing.T)   { runContract(t, newKubeFixture) }

// runContract registers every CT-nn as t.Run("CT01_fork_secrets_scrubbed", ...)
// so both implementations produce IDENTICAL test names and a missing
// invariant is a visible hole, not a silent skip.
func runContract(t *testing.T, nf func(t *testing.T) contractFixture)
```

[P0-DECIDED] In-package private suite (`contract_test.go` + `contract_fixture_*.go`),
not an exported `contracttest` subpackage: both implementations live in
`pkg/reporuntime` (§1.1), so nothing outside the package needs to import the suite. If a
third runtime ever lands out-of-package (RKE2 is gated far away, 02 §10b), promote the
suite to `pkg/reporuntime/contracttest` then — mechanical move.

Fixture contract:

```go
// contractFixture adapts one implementation to the shared suite. Everything
// is faked at the tool boundary, not the logic boundary: the docker fixture
// runs REAL bash against temp-dir Rediaccfiles (the pattern of
// pkg/orchestration/rediaccfile_execute_test.go) with NetworkID=0 (no
// dockerd); the kube fixture records kubectl argv via toolexec.MockExecutor
// (pkg/toolexec/executor.go:157; the pattern of kube/deploy_test.go and
// namespace_test.go) and serves canned object lists.
type contractFixture interface {
	Runtime() RepoRuntime
	// NewRepo fabricates a deployed repo: temp-dir RepoPath with a
	// Rediaccfile whose up()/down()/health() dump their env to a capture
	// file, persisted manifests (kube), fake volume images (kube).
	NewRepo(t *testing.T, role Role) RepoHandle
	// CapturedEnv returns the env the last lifecycle hook actually saw
	// (parsed from the capture file) — proves injection END-TO-END through
	// real bash, not by inspecting SetEnv calls.
	CapturedEnv(t *testing.T, hook string) map[string]string
	// VisibleSecrets returns what a workload would see after InjectSecrets:
	// docker = files under the fixture's redirected SecretsBaseDir
	// (pkg/orchestration/secret_files.go:19 is a var — point it at t.TempDir())
	// + staged env; kube = Secret objects the mock executor recorded applied.
	VisibleSecrets(t *testing.T, h RepoHandle) map[string]string
	// BreakTeardown arms a failure so Teardown leaks (docker: unremovable
	// dir; kube: RemoveAll failure / recorded surviving PV object).
	BreakTeardown(t *testing.T, h RepoHandle)
	// StorageOps returns every storage-touching operation the runtime
	// attempted (mounts, loop/dm/cryptsetup/rbd argv) — must stay empty
	// outside the injected VolumeProvisioner seam (CT-10).
	StorageOps() []string
}
```

**Level B — e2e legs** (real VMs): the same numbered invariants asserted against real
machines, living in `packages/e2e-tests` (that is where `check:ci-e2e-coverage` greps
bridge-function usage, 09 §3). Suite files after the P1/P2 rewrite:

- `tests/04-repository-lifecycle.test.ts`, `tests/05-rediaccfiles-updown.test.ts` —
  docker Deploy/Teardown/env legs (extend with CT tags).
- `tests/13-postgres-fork-isolation.test.ts` — docker fork legs (CT-1/2/3 docker).
- `tests/kube/15-k8s-repo.test.ts` — kube Deploy/ProvisionVolumes/Teardown legs on the
  folder model (rewritten in P1).
- `tests/kube/16-k8s-ceph.test.ts` loses its subject (ceph-csi deleted); its replacement
  `16-datastore-cluster.test.ts` keeps the multinode fork/migrate proof shape (09 §P1)
  and carries the cluster-scope CT-1/2/4 kube legs.
- `tests/migrate/18-dual-group-migrate.test.ts` — CT-4 migrate legs.

Naming convention binding the levels: every e2e assertion that discharges a contract
invariant carries the CT id in its test title (`test('CT-02k fork cannot auth against
parent CA', ...)`), and Level A tests that cannot fully discharge an invariant say so:
`t.Log("e2e leg: CT-02k in 16-datastore-cluster.test.ts")`. A one-page matrix
(`pkg/reporuntime/CONTRACT.md`) lists CT id → Level A test name → e2e test title, and
the P1 gate reviews it for holes.

### 2.2 The numbered invariants

Legend: D = docker leg, K = kube leg; [A] pure-Go, [B] e2e, [A+B] both.

| # | Invariant | Level |
|---|---|---|
| **CT-01 fork ⇒ secrets absent/scrubbed.** | After `Fork`, `VisibleSecrets(child)` is empty. D: no `/var/run/rediacc/secrets/<childNetID>` entries, no `REDIACC_SECRET_*` staged; config-side: fork record carries no `secrets` map (vitest leg, §2.5). K: zero `rediacc.io/injected=true` Secrets in the child namespace (label per §1.5a, gate C4); cluster scope: kine-carried Secrets (rediacc AND third-party) scrubbed by the fork identity-rewrite (02 §4 F2). | [A] repo scope, [B] cluster scope (`16-datastore-cluster`) |
| **CT-02 fork ⇒ credentials regenerated.** | D: child repo record holds an SSH keypair ≠ parent's (`registerFork`, `repo-fork.ts:167` — vitest leg) and the parent's key does not authorize into the child sandbox [B]. K: the fork's CA must be **FINGERPRINT-DIFFERENT from the parent's** — "tls/ was recreated" is NOT a sufficient assertion: spike d (`reports/spikes/spike-d-pki-remint.md`) proved k3s restores the parent CA byte-identically from the kine `/bootstrap` entry unless the full 8-step scrub of spec 05 §7 runs (tls/ removal + `/bootstrap` row delete + token rotation + `extension-apiserver-authentication` ConfigMap rewrite + pod restarts + secret scrub + ROLE rewrite). Assertions: new-CA-vs-parent-CA fingerprint comparison; a parent-CA-minted client cert is REJECTED by the fork's API server; a parent join token cannot join the fork [B — the F1 blocker demo, cluster scope]. [A] leg: the fork step invokes the spec 05 §7 scrub seam — every step, in order (recorded calls). | [A+B] |
| **CT-03 fork/rehearsal ⇒ Role never primary.** | `Fork` with `child.Role == RolePrimary` fails `ErrRoleViolation`; after fork, `CapturedEnv("up")["REDIACC_ROLE"] ∈ {fork, rehearsal}`; K: `rediacc-role` ConfigMap rewritten in the same step. | [A] |
| **CT-04 migrate ⇒ secrets re-inject + identity preserved.** | Migrate is modeled as: same handle (GUID, Name, Role=primary preserved; K: CA preserved) on a new mount + `InjectSecrets` + `Deploy`. Asserts: secrets visible again after re-inject; D: GUID/networkID unchanged; K: CA fingerprint unchanged, serving leaf regenerated for the new IP (`RewriteIdentity` migrate mode, `identity.go:99-107`). | [A] policy, [B] identity (`18-dual-group-migrate`, cluster migrate suite) |
| **CT-05 lifecycle env injection.** | `REDIACC_ROLE`, `REDIACC_WRITES`, `REDIACC_DATASTORE` present and correct in `CapturedEnv` for up(), down(), AND health(), both runtimes (real-bash capture). K additionally: `rediacc-role` ConfigMap applied with identical values (recorded kubectl apply). | [A] |
| **CT-06 teardown is leak-reporting.** | Clean repo: `Teardown` ⇒ (nil, nil). `BreakTeardown`: ⇒ (leak != nil, nil error), leak names the surviving paths/objects with a non-empty Reason (generalizes `NamespaceDelete`'s semantic, `namespace.go:33`). | [A] |
| **CT-07 teardown re-run converges.** | After a leaked teardown, un-arm the failure; second `Teardown` ⇒ (nil, nil) and survivors gone (the keep-dirs-so-re-run-converges behavior, `namespace.go:58`). | [A] |
| **CT-08 deploy idempotency.** | `Deploy` twice ⇒ second succeeds, end state identical (docker: up() re-ran, no duplicate slots in `.rediacc.json`; kube: apply is convergent), per 03 §2 rule 4 / R2-F15. | [A+B] |
| **CT-09 volume provisioning is adoptive, on the ruled layout.** | K: `ProvisionVolumes` twice ⇒ existing image at `<RepoPath>/volumes/<pvc>.img` kept (content marker survives), mount converged at `<ds-mount>/mounts/volumes/<repo>/<pvc>/`, and NO mountpoint exists under `repos/<repo>/` (gate C1); after a fork, adopt mode binds the reflinked image rather than recreating (today's documented behavior, `namespace.go:208-212`). D: no-op returns nil. | [A] |
| **CT-10 runtime never touches storage.** | `StorageOps()` empty across the full verb set (except through the injected `VolumeProvisioner` seam); compile-level: no storage-package imports in `docker.go`/`kube.go`. | [A] |
| **CT-11 wrong-runtime refusal.** | Handle derived as kube but repo `.rediacc.json` declares compose (or vice versa) ⇒ `Deploy` fails `ErrWrongRuntime` before executing anything (extends `ValidateRuntime`, `rediaccfile.go:569`, into the dispatch conflict rule §3.4). | [A] |
| **CT-12 secrets never persist into repo data.** | After `InjectSecrets` + `Deploy`: no secret value below `RepoPath` (docker: the LUKS image content; kube: nothing under `<RepoPath>/manifests/`), so forks/branches/backups can never carry them. Asserted by grepping the fixture trees for sentinel values. | [A] |
| **CT-13 no lazy-success against holders.** | Armed holder (kube: fake kubelet mount recorded as held; docker: dm holder) ⇒ `Teardown` returns `ErrHoldersPresent`, does NOT unlink backing files (03 §2 rules 1-2). | [A] policy, [B] real-kubelet leg in `15-k8s-repo` |
| **CT-14 health dispositions (gate C5).** | health() exit 0 ⇒ Healthy; exit 75 ⇒ Warming; any other nonzero ⇒ Unhealthy with Detail; exit 42/undefined ⇒ runtime fallback ⇒ Unknown when no signal; 30 s per-attempt timeout ⇒ Warming (counts as one 75); `Health` never loops (one evaluation — the 300 s gate window is the caller's); env per CT-05. | [A] |
| **CT-15 status is read-only.** | `Status` leaves fixture trees byte-identical and records zero mutating tool calls. | [A] |

### 2.3 What is mockable vs what needs a VM (the explicit split)

Mockable (Level A): everything policy-shaped. Real bash + temp dirs give true env
propagation; `toolexec.MockExecutor` gives true argv assertions; redirecting the
`SecretsBaseDir` var gives true file materialization. No dockerd, no k3s, no LUKS, no
root.

VM-required (Level B), and WHY:
- CT-02 K cluster scope: only a real k3s can prove "parent CA rejected" AND the
  CA-fingerprint difference (spike d transcript
  `reports/spikes/spike-d-pki-remint.md` is the precursor — it caught the kine
  `/bootstrap` byte-identical CA restore that a mock could never surface; the e2e leg
  keeps both assertions true forever).
- CT-01 K cluster scope: kine actually riding a group snapshot needs real Ceph
  (`playwright.k8s-multinode.config.ts` fleet).
- CT-04 identity halves: real `RewriteIdentity` against a booted k3s.
- CT-08/CT-13 real-holder legs: real kubelet/loop/dm behavior (lazy-umount lies are
  precisely what mocks cannot reproduce).
- Anything touching per-volume LUKS mounts, fencing, or `--writes` dispositions.

Renet-side root-tagged Go tests (`//go:build root`, precedent
`pkg/repository/state_test.go`; vet gate runs `-tags "root ebpf_e2e"`) are NOT used for
the contract suite: the e2e legs live CLI-side in `packages/e2e-tests` where the
coverage gate and the fleet harness already are. Root-tagged Go tests stay for
storage-layer units only.

### 2.4 File locations and naming (summary)

```
private/renet/pkg/reporuntime/
  reporuntime.go        # interface, types, sentinels (§1.2)
  env.go                # LifecycleEnv (§1.4)
  leak.go               # TeardownLeak (§1.6)
  docker.go             # DockerRuntime (§1.5)
  kube.go               # KubeRuntime (§1.7)
  factory.go            # ForHandle + Detect (§3.3)
  contract_test.go      # runContract + CT-01..CT-15 (§2.1)
  contract_fixture_docker_test.go
  contract_fixture_kube_test.go
  CONTRACT.md           # CT ↔ test-name ↔ e2e-title matrix (§2.1)
packages/e2e-tests/tests/…            # Level B legs per the list in §2.1
packages/cli/src/commands/__tests__/repo-fork-contract.test.ts   # §2.5
```

### 2.5 The CLI-side sliver (vitest)

Two docker fork invariants are enforced in TypeScript, not Go — the keypair mint and the
secrets omission both happen in `registerFork` (`src/commands/repo-fork.ts:152-179`)
before renet is ever invoked. They get a dedicated vitest file
(`repo-fork-contract.test.ts`, named CT-01d-cli / CT-02d-cli) asserting: fork record has
fresh `sshPrivateKey`/`sshPublicKey` differing from the parent's, carries NO `secrets`
key, and preserves `credential` (deliberate: the cloned LUKS image needs the parent
passphrase — this is bytes-access the fork already has, not an effect credential).
The Go suite cannot see this layer; the matrix in `CONTRACT.md` records the delegation.

---

## 3. Dispatch: placement → runtime

### 3.1 Today's seam (what gets deleted)

- TS: repo verbs take `-m` XOR `--cluster`; `resolveRepoTarget`
  (`src/utils/repo-target.ts:27`) → `resolveExecutionTarget`
  (`src/services/cluster/cluster-target.ts`) maps a cluster to its control node +
  `kubeCluster` marker; local-executor injects KUBECONFIG when set. Docker-only verbs
  refuse via `assertDockerOnly` (`repo-target.ts:43`). The whole-cluster fork is a
  separate TS orchestration, `forkCluster`
  (`src/services/cluster/cluster-kube.ts:218`), still drain-and-stop shaped with the
  `dstAgents >= srcAgents` refusal (both die in P2 per 04).
- Go: the repo's in-image `.rediacc.json` `runtime` field ("compose" | "kube",
  `orchestration.Runtime`, `rediaccfile.go:497`) read by `repoRuntime()`
  (`up_down_workflows.go:105`) and enforced only as a LINT on Rediaccfile content
  (`ValidateRuntime`). Deploys reach kube through separate bridge functions
  (`kube_deploy`, `kube_namespace_*`, `kube_pv_*` — `pkg/functions/commands/kube.go`)
  rather than through `repository_up`.

This is exactly the "flag-routing seam with no enforced contract" 02 §9 names.

### 3.2 The new rule: placement decides, nothing else

Config schema v3 stores `placement: { datastore: <name> } | { machine: <name> }` per
repo (02 §11 R2-F1). Resolution:

```
placement.machine    ⇒ that machine's implicit default datastore ⇒ TypeDocker
placement.datastore  ⇒ datastore registry record:
                         record.cluster set   ⇒ TypeKube  (cluster, CP, node labels known)
                         record.cluster unset ⇒ TypeDocker (named tiering datastore)
```

[P0-DECIDED] **One-world datastores**: a named datastore is either cluster-attached
(hosts ONLY kube repos) or plain (hosts ONLY docker repos), fixed at
`datastore create` (`--cluster <name>` sets the backref) and immutable afterwards
(change = create new + `repo push`, consistent with "moving = a copy", 02 §7).
Rationale: without this rule the runtime cannot be derived from placement and would
need a per-repo runtime field that can drift — the exact disease 02 §9 diagnoses. It
also extends R2-F12 symmetrically: `repo create --machine M` refuses when M carries a
cluster membership backref (02 §7); `repo create --datastore D` onto a cluster
datastore IS the k8s repo form and needs no extra flag.

The repo record stores NO runtime field. Runtime is always derived at use, so it can
never disagree with placement.

### 3.3 Where resolution lives

**CLI side** [P0-DECIDED]: one resolver module
`packages/cli/src/services/config/placement.ts`:

```ts
export interface ResolvedPlacement {
  runtime: 'docker' | 'kube';
  datastore: string;            // name ("default" for the machine arm)
  machineName: string;          // current mounter, from the state bucket
  cluster?: string;             // set iff runtime === 'kube'
}
export async function resolvePlacement(repoName: string): Promise<ResolvedPlacement>;
```

It subsumes `resolveRepoTarget` (which dies with the `--cluster`/`-m` repo flags in P4,
06 §6) and performs the R2-F2 verification: the state bucket's attach record is a
ROUTING HINT — before returning, the resolver's caller path verifies the datastore is
mounted where state claims (piggybacked on the SSH session's first renet call) and
errors with the `config reconcile` suggestion on mismatch, never deploying to a wrong
host. `assertDockerOnly` generalizes into a per-verb capability table keyed on
`runtime` (06 owns the table; e.g. takeover/tunnel/autostart = docker-only in v1).

**renet side** [P0-DECIDED]: renet re-derives the runtime from ON-MACHINE truth rather
than trusting a CLI flag, following the established detect-from-disk pattern
(`datastore.DetectBackend`, `pkg/datastore/backend.go:30`; `distro.DetectDistro`,
`pkg/kube/distro/distro.go:242`):

- `datastore create`/`attach` write a descriptor **`<ds-mount>/.rediacc/datastore.json`**
  (path per gate C6 — `.rediacc/` is the established metadata-directory convention,
  matching the repo-scoped `.rediacc/` and the k3s data-dir at `<mount>/.rediacc/k3s`)
  recording `{ name, backend: local|ceph, cluster?: <name>, writes?: ceph|local,
  k3sVersion, k3sVersionWrittenAt }` (the one file carries the F14 skew metadata and
  the `--writes` disposition, so attach preflight and `LifecycleEnv` read one source).
- `reporuntime.Detect(dsMount, repoName) (RepoHandle, error)` reads the descriptor +
  repo state and `factory.go`'s `ForHandle(h, deps)` constructs the right
  implementation. `deps` carries the seams: orchestrator factory, kube wrapper builder,
  `VolumeProvisioner`, distro handle.
- The bridge functions become runtime-generic (this model WON gate C2):
  `repository_up/down/fork/status` dispatch through the factory, and
  **`repository_health` is ADDED as the new bridge surface** fronting
  `RepoRuntime.Health` (no health function exists on the bridge today; the gate's
  callers — `repo migrate`, `cluster migrate/rehearse`, `backup restore --up` — all
  consume it). `repo logs`/`repo exec` likewise need a runtime-generic surface (docker
  side maps to today's `container_logs`/`container_exec`). The `kube_deploy` /
  `kube_namespace_create` / `kube_namespace_fork` / `kube_namespace_delete` /
  `kube_pv_*` functions retire (their bodies become `KubeRuntime` internals). The
  exact rename/add/delete ledger is spec 01 §4's (reworked per C2); this spec fixes
  the direction. Per renamed function: regenerate types into `packages/shared`, update
  `packages/e2e-tests` references (`check:ci-e2e-coverage` greps per function name and
  WILL red otherwise, 09 §P1). Cluster-layer functions (`kube_identity_rewrite`,
  `kube_join`, `kube_node_remove`, `kube_prep_fork`, `kube_health` as the DISTRO
  healthcheck) stay separate, per the boundary below.

**Conflict rule (§3.4).** The in-image `.rediacc.json` `runtime` field is demoted to a
cross-check: if present and it contradicts the placement-derived runtime, every verb
refuses with `ErrWrongRuntime` and a teaching error naming both sources ("this repo's
image declares runtime=compose but datastore ds-alpha belongs to cluster main — a repo
cannot change worlds; repo push to a docker datastore instead"). Covered by CT-11.
Absent field = no check (docker legacy default, unchanged).

**Cluster verbs are not dispatched through RepoRuntime.** `cluster fork/migrate/
rehearse` are cluster-layer orchestrations (04) that compose: StorageBackend group
snap/clone/attach + `distro` identity rewrite (+ fork PKI/secret scrub) + per-repo
`RepoRuntime.Deploy`/`Health` for each repo the moved datastores contain. The runtime
interface deliberately has no cluster verbs; that keeps the third-runtime path (RKE2,
02 §10b) a pure `RepoRuntime`+`Distro` implementation exercise.

---

## 4. Reality deltas (cited-name verification)

Checked every identifier this spec and design 02 §9 cite; mismatches found:

1. **`StorageBackend` does not exist under that name.** 02 §9 says it "exists
   half-formed in `pkg/datastore`"; the actual interface is **`DatastoreBackend`**
   (`pkg/datastore/backend.go:109`, methods Initialize/Mount/Unmount/Expand/Resize/
   Cleanup/IsInitialized/GetInfo/Validate/Type). P1 may rename it to `StorageBackend`
   or keep the name; this spec refers to the real one.
2. **`pkg/kube/deploy.go:94`** — the cited comment line is the comment block's start;
   `func (w *Wrapper) Apply` is at `:100`. Same seam, off-by-six.
3. **The docker fork's "new SSH keypair" is CLI-side, not renet-side**: minted in
   `registerFork` (`packages/cli/src/commands/repo-fork.ts:167`), deployed at up time by
   `deployRepoKeyIfNeeded` (`src/services/repo/repo-key-deployment.ts`). Hence the
   vitest sliver (§2.5). Renet's own fork path never handles SSH keys.
4. **A `Runtime` name already exists**: `orchestration.Runtime` ("compose"/"kube",
   `rediaccfile.go:497`) — the in-image declaration this spec demotes to a lint
   (§3.4). The new package avoids the identifier (`reporuntime.Type`).
5. **`pkg/health` is taken**: it is the container-healthcheck drift registry
   (`pkg/health/registry.go`), unrelated to the `Health` verb; no new package named
   `health` may be introduced, and `DockerRuntime.Health`'s fallback READS this
   registry.
6. Verified as cited: `NamespaceTeardownLeak` (`pkg/kube/ceph_backend.go:46`) and its
   non-fatal + keep-dirs semantics (`pkg/kube/namespace.go:33`, `:58`);
   `forkCluster` at `packages/cli/src/services/cluster/cluster-kube.ts:218` including
   the drain-first shape and `dstAgents >= srcAgents` refusal 04 replaces;
   `kube_identity_rewrite` / `kube_prep_fork` bridge functions
   (`pkg/functions/commands/kube.go:61`, `:77`); `K3sDistro.RewriteIdentity`
   (CA-preserving, `pkg/kube/distro/identity.go:63`) and `PrepFork`
   (`distro/prepfork.go`); `materializeAndBindPVs` (`pkg/kube/deploy.go:58`),
   `resolvePVBackend` (`namespace.go:157`), `.rbd-backend.json` marker
   (`ceph_backend.go:71`) — all on the 02 §6 delete ledger; secrets plumbing
   (`state.ts:215`, `local-executor.ts:581/1128`, `appendSecretFileFlags`
   `repository.go:18`, `SecretsBaseDir` `secret_files.go:19`);
   `toolexec.MockExecutor` (`pkg/toolexec/executor.go:157`); e2e suites named in §2.1
   all exist under `packages/e2e-tests/tests/`.
7. **No k8s secret injection exists today** (no Secret-object creation anywhere in
   `pkg/kube`) — `KubeRuntime.InjectSecrets` is green-field, consistent with 02 §4
   calling it new work.

## 5. Cross-spec items (status after the gate review, 00-gate-review.md)

Resolved at the gate:
- Volume image/mount layout: spec 05 §2 WON (C1) — adopted throughout this file
  (§1.2 interface comment, §1.7 `ProvisionVolumes` row, CT-09).
- Secret label convention: `rediacc.io/injected=true` per spec 05 (C4) — §1.5a, CT-01.
- health() mechanics: reconciled contract (C5) — §1.8, `HealthState.Warming`, CT-14.
- Descriptor path: `<ds-mount>/.rediacc/datastore.json` per spec 05 (C6) — §3.3.
- Bridge dispatch: this spec's unified model WON (C2); the reworked ledger including
  `repository_health` and runtime-generic logs/exec is spec 01 §4's returning item.
- `datastore create --cluster <name>` flag (the one-world backref's CLI source) and
  the top-level `cluster` field: spec 03/04 fixes (C7); this spec's §3.2 unchanged.

Still open elsewhere (this spec only consumes them):
- NetworkPolicy + VAP template bodies and the F9 proxy-datapath verdict (spec 05,
  PENDING-SPIKE e; apply-site is `ApplyIsolation`, §1.7).
- The authoritative fork PKI scrub is spec 05 §7's 8-step sequence (spike d PASSED
  with correction: tls/ removal alone lets k3s restore the parent CA byte-identically
  from the kine `/bootstrap` entry — hence CT-02's fingerprint-difference assertion).
- Exit-code numbers for the sentinel mapping (spec 03 §1 table, G1 — §1.2 concurs).
- The `state.repos` registry-port field (spec 04, G3 — env note in §1.4).
- The per-verb docker-only/kube-only capability table (spec 03 / 06).
