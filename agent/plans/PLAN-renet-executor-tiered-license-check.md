# PLAN: every tiered renet function is licence-checked, with or without a repository

Status: executing
Depends-On: no-dep -- renet 23c0c03b (test mode enforces licensing) is already on this branch
Owner: d778be9d
Updated: 2026-10-30
Priority: P1 -- a tiered function called without a repository skips the executor licence check on every path
Concurrency: parallel
Owns: agent/plans/PLAN-renet-executor-tiered-license-check.md, private/renet/pkg/functions/executor_local.go, private/renet/pkg/license/**, private/renet/cmd/renet/ops_selftest.go, private/renet/pkg/functions/*_test.go, private/renet/cmd/renet/ops_selftest_test.go
Live-Proof: hostinger -- hostinger is the renet surface's live target: the released renet refuses a repo-less tiered call there exactly as the unit tests show
First-Seen: 2026-10-30
Worklist: #618c0002, PR-TASK 9f92c43e

## Finding

`validateRepoLicenseForCreate` and `validateRepositoryOperationLicense` in `private/renet/pkg/functions/executor_local.go` return nil when the call carries no repository, so a function the tier map marks create, operate or full but that runs without one (setup, ceph_pool_create, datastore_create, kube_install are the candidates) is never licence-checked at the executor. `renet ops test comprehensive` (`private/renet/cmd/renet/ops_selftest.go`) runs repository_create and mount through `functions once --test-mode` without installing a licence, which fails on every enforcing build since renet 23c0c03b.

## Design

Survey (registry probe, 2026-10-30): 74 functions are tiered; each was driven through `validateRepositoryOperationByTier` with no repository. Before the fix every one returned nil (`executor_local.go` `validateRepoLicenseForCreate`/`validateRepositoryOperationLicense`, `if repoName == "" { return nil }`). Renet has NO machine-scoped or datastore-scoped licence: every licence is a repo licence (`pkg/license/store.go` keys by repository GUID), so option (b) "check at another scope" exists only where a renet command already checks each repository itself.

Mechanism. `tierEntry` (`pkg/license/tiermap.go`) gains `repoParam` (the parameter that carries the repository, read instead of the vault field) and `repoless RepolessRule`. The executor resolves the repository (`licensedRepositoryName`), and when none is named it consults the rule; the zero value `RepolessRefuse` refuses with `LICENSE_REQUIRED` wrapping `license.ErrRepositoryUnnamed` (reason `invalid`, so the CLI fails fast rather than reissuing). A tiered function that gains a repo-less caller therefore fails closed until a rule is written. `TestRepolessTieredCallsAreDecided` (`pkg/functions/executor_repoless_test.go`) drives every tiered function repo-less and fails on any that passes without being listed in its pinned `repolessPassAllowed`; both plants (default answer nil; default nil for all but the control) fired and were removed.

Decisions per function:

- TierNone, machine-scoped, touches no repository data: `setup` (machine bootstrap, never carries a repository, `pkg/functions/commands/system.go:281`); `daemon_setup`, `daemon_start`, `daemon_restart`, `daemon_wait_docker` (keyed by network id, the builders never read a repository, `commands/daemon.go:144,172,274,339`; repository data is reached only through repository_up/mount, which are checked); `network_ensure_ips` (loopback IPs by network id, `commands/daemon.go:367`); `repository_autostart_disable_all` (teardown: withdraws autostart keyslots and starts nothing, `cmd/renet/repository_autostart.go:731`, under the map's teardown-is-None principle).
- Checked at the repository a parameter names: `repository_fork` (tag, unchanged behaviour), `repository_promote` (parent, the grand that keeps its identity; `commands/repository.go:1790`), `repository_policy_set` (name).
- Machine scope when no repository is named: `repository_policy_set` with no name writes the machine-wide policy (`cmd/renet/repository_policy.go:55`).
- Checked per repository by the command itself (`RepolessEachRepoChecked`): `repository_up_all` (`cmd/renet/repository_up_all.go:348` validates each repo before starting it), `repository_autostart_enable_all` (the start path `recoverRepository`, `cmd/renet/repository_autostart.go:170`, validates each repo before mounting).
- Refused when repo-less (default): every other tiered function outside Q1. All of them require a repository in their builder (`RequireRepository`), so only a malformed call is affected; it now fails as LICENSE_REQUIRED instead of "Repository name is required".
- Unchanged pending Q1 (`RepolessPendingOperator`, runs unchecked repo-less exactly as before, enumerated in the map and pinned by the test): ceph_bootstrap_cluster, ceph_client_config_install, ceph_client_mount, ceph_clone_create, ceph_clone_flatten, ceph_clone_image, ceph_clone_mount, ceph_cluster_create, ceph_image_create, ceph_image_format, ceph_image_map, ceph_image_resize, ceph_install_prerequisites, ceph_pool_create, ceph_snapshot_create, ceph_snapshot_protect, ceph_snapshot_rollback, ceph_snapshot_unprotect, datastore_adopt, datastore_attach, datastore_create, datastore_expand, datastore_fork, datastore_resize, datastore_snapshot_create, datastore_volumes_open, kube_apply, kube_fork_dest_prep, kube_identity_rewrite, kube_install, kube_join, kube_node_label, kube_prep_fork, kube_registry_up, kube_registry_wire, kube_upgrade.

Operator questions:

- Q1 (paid-feature infrastructure without a repository). Recommended first: (A) TierNone for the cluster and datastore build-out verbs (ceph cluster/pool/install/bootstrap, kube install/join/upgrade/registry, datastore create/attach/adopt/expand/resize), because the licence is per repository and every repository placed on that infrastructure is gated at create and on every operate/full verb; datastore_fork is already metered through `missing` (the fork re-mints datastoreId, its repos find no blob and the CLI reissues, claiming slots). Under (A) the ceph image/snapshot/clone verbs, which default their image to the vault repository (`commands/ceph.go:751` and siblings), would keep their tier and move to `RepolessRefuse`, so a repo-less call to them is refused. (B) Keep them tiered and refuse repo-less calls now: ceph, kube and datastore flows from the CLI break until a machine- or datastore-scoped licence exists. (C) Design a new machine/datastore licence scope in the account server and renet (no such notion exists today).
- Q2 (`datastore_volumes_open`, param `repo`). It opens a kube repo's per-volume LUKS images and names the repository in a parameter, so `repoParam: "repo"` would check it, but the operate validator's size pre-flight assumes the docker layout (`executor_local.go`, the kube skip keyed on the `runtime` export, issue #80). Recommended: answer with Q1's kube decision and, if gated, set `repoParam: "repo"` plus the `runtime=kube` export at the caller.

T2. `renet ops test comprehensive` generated `test-repo-<unix>`, a name the account server can never license (it signs UUIDs only), and renet has no command that obtains a fresh licence (`license renew` only refreshes an installed one). The command now takes `--repository <guid>` and refuses before any VM starts without a GUID (`comprehensiveSelfTestPrecheck`), naming `/licenses/activate-repo`, `packages/e2e-tests/src/utils/licence.ts` installRepoLicence and `renet repository license-status`; on the worker the script checks `repository license-status --repo` reports the licence installed after datastore init and before repository_create, exiting 10 with the same hint.

Follow-ups for the lead: the seven TierNone flips change `packages/shared/src/renet-contract/data/license-tiers.generated.ts` (regen per the contract-freshness recipe; the CLI reads only the `create` tier, so no CLI behaviour moves); the new `ErrRepositoryUnnamed` surfaces as reason `invalid`.

## Boxes

- [ ] T1: Each tiered function that can run without a repository is either TierNone in the tier map or checked at another scope, decided per function with file:line evidence. Accept: cd private/renet && go test ./pkg/functions/... ./pkg/license/... rc 0, with a test that fires on a planted unchecked repo-less tiered call.
- [ ] T2: renet ops test comprehensive installs a licence or refuses with a message naming how to provide one before repository_create. Accept: cd private/renet && go test ./cmd/renet/... rc 0.
- [ ] L1: hostinger's released renet refuses a repo-less tiered call without a licence. Accept: the live call's exit 10 LICENSE_REQUIRED, recorded through the live_proof recorder.
