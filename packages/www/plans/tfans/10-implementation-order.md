# Implementation Order and Task Breakdown

## Phase 0: Foundations (do first, enables everything)

### 0.1 Fix BLOCKING CLI JSON Output Gaps

These must be fixed before Ansible/Terraform development begins.
See `00-overview.md` "Complete JSON Output Audit" for the full picture.

**Fix 1: `backup schedule show`** — BLOCKING for Terraform `rediacc_backup_schedule`
- File: `packages/cli/src/commands/backup.ts`
- Currently uses `outputService.info()` — nothing goes to stdout in JSON mode
- Change to `outputService.print(config, getOutputFormat())`
- Trivial change, high impact
- [ ] Implement
- [ ] Add test

**Fix 2: `backup list`** — BLOCKING for disaster recovery automation
- Currently uses `outputService.info()` for listing backups
- Ansible `disaster_recovery` role and Terraform import both need to
  enumerate available backups programmatically
- [ ] Evaluate: can this parse renet's response and format via outputService?
- [ ] Implement
- [ ] Add test

**Fix 3: `repo list`** — BLOCKING for complete state detection
- Currently pipes renet's raw stdout
- Workaround exists (`config repositories` + `machine containers`)
  but a native `repo list` with JSON would simplify idempotency checks
- [ ] Evaluate effort vs workaround adequacy
- [ ] Implement if justified

### 0.2 Fix IMPORTANT CLI Gaps (workarounds exist but fragile)

**Fix 4: `autostart list`** — needed for Terraform drift detection
- Without JSON output, Terraform can't detect if autostart was changed
  outside of Terraform
- [ ] Evaluate effort

**Fix 5: `repo status`** — needed for reliable running-state detection
- Currently pipes renet's raw stdout
- Workaround: use `machine containers` filtered by repository name
- Consider adding structured output that combines mount status + container state
- [ ] Evaluate: is the workaround sufficient for v1.0?

### 0.3 Verified JSON Commands (no changes needed)

These were audited and confirmed working:
- [x] `config show`, `config list` — full config / config listing
- [x] `machine info/containers/services/repos/health/vault-status/test-connection`
- [x] `machine add/list/rename/delete/status` (via createResourceCommands factory)
- [x] `queue list`, `queue trace`
- [x] `repo up/down/delete --dry-run` — returns structured JSON in dry-run mode

The dry-run capability is particularly valuable: it enables Ansible check mode
and Terraform plan to show what would change without executing.

### 0.4 Test Environment Setup
- [ ] Create setup/teardown scripts (see `09-test-environment.md`)
- [ ] Create minimal test app fixture (Rediaccfile + docker-compose)
- [ ] Verify `rdc ops up --basic --parallel` on CI runner
- [ ] Document CI requirements: KVM, 8GB+ RAM, 30GB+ disk, Node 18+

### 0.5 Validate Error Envelope Structure
- [ ] Verify error responses include `retryable`, `code`, `guidance` fields
  as seen in `packages/cli/src/utils/errors.ts`
- [ ] Document which error codes map to retryable vs permanent failures
- [ ] Test that non-TTY piping triggers auto-JSON detection

---

## Phase 1: Ansible Collection

### Milestone 1.1: Core Infrastructure (Week 1-2)
**Goal**: Working collection skeleton with the CLI wrapper utility.

- [ ] Create collection directory structure (`packages/ansible/rediacc/console/`)
- [ ] Write `galaxy.yml`
- [ ] Write `meta/runtime.yml`
- [ ] Implement `plugins/module_utils/rdc_runner.py` (CLI wrapper)
- [ ] Implement `plugins/module_utils/rdc_common.py` (shared arg specs)
- [ ] Write unit tests for `rdc_runner.py`
- [ ] Verify `ansible-galaxy collection build` succeeds

**Deliverable**: Installable collection tarball (no modules yet).

### Milestone 1.2: First Module — `rediacc_machine` (Week 2-3)
**Goal**: Register and setup machines via Ansible.

- [ ] Implement `plugins/modules/rediacc_machine.py`
  - [ ] `state: present` → `rdc config add-machine`
  - [ ] `state: setup` → `rdc config setup-machine`
  - [ ] `state: absent` → `rdc config remove-machine`
  - [ ] Idempotency: check `config machines` before acting
  - [ ] Check mode support
- [ ] Write unit tests (mock `run_command`)
- [ ] Write integration test (real VM)
- [ ] Add DOCUMENTATION/EXAMPLES/RETURN docstrings

**Deliverable**: Can register and setup ops VMs via Ansible.

### Milestone 1.3: Repository Lifecycle — `rediacc_repo` (Week 3-4)
**Goal**: Full repo CRUD through Ansible.

- [ ] Implement `plugins/modules/rediacc_repo.py`
  - [ ] `state: present` → create if not exists
  - [ ] `state: started` → create if needed + deploy
  - [ ] `state: stopped` → stop repo
  - [ ] `state: absent` → delete (requires force)
  - [ ] `state: forked` → fork from parent
  - [ ] `state: resized` → offline resize
  - [ ] `state: expanded` → online expand
  - [ ] Idempotency for each state
  - [ ] Check mode support
- [ ] Write unit tests (all state transitions)
- [ ] Write integration tests (create → deploy → stop → delete lifecycle)

**Deliverable**: Full repo management via Ansible.

### Milestone 1.4: Machine Info + Sync (Week 4-5)
**Goal**: Read-only inspection and file sync.

- [ ] Implement `plugins/modules/rediacc_machine_info.py`
  - [ ] query: info, containers, services, health, repos
- [ ] Implement `plugins/modules/rediacc_sync.py`
  - [ ] direction: upload, download
  - [ ] Options: mirror, verify, exclude, dry_run
- [ ] Write unit tests
- [ ] Write integration tests (sync test-app, verify containers)

**Deliverable**: Can deploy an app end-to-end: machine info → sync → deploy → verify.

### Milestone 1.5: Backup Operations (Week 5-6)
**Goal**: Cross-machine backup and bulk sync.

- [ ] Implement `plugins/modules/rediacc_backup.py`
  - [ ] direction: push to machine/storage
  - [ ] direction: pull from machine/storage
  - [ ] mutually_exclusive: to_machine/to_storage, from_machine/from_storage
- [ ] Implement `plugins/modules/rediacc_backup_info.py` (read-only, separate _info module)
  - [ ] List backups from machine or storage
- [ ] Implement `plugins/modules/rediacc_backup_sync.py`
  - [ ] direction: push/pull all repos to/from storage
- [ ] Implement `plugins/modules/rediacc_backup_schedule.py`
  - [ ] state: present (set + optional push)
  - [ ] state: absent (disable + optional push)
  - [ ] required_if: state=present requires destination, cron
- [ ] Write unit tests (argument validation, envelope mocking)
- [ ] Write integration tests (push from rediacc11 to rediacc12, verify)

**Deliverable**: Cross-machine backup and scheduling via Ansible.

### Milestone 1.6: Remaining Modules (Week 6-7)
**Goal**: Complete module coverage.

- [ ] Implement `plugins/modules/rediacc_snapshot.py`
- [ ] Implement `plugins/modules/rediacc_autostart.py`
- [ ] Implement `plugins/modules/rediacc_infra.py`
- [ ] Implement `plugins/modules/rediacc_template.py`
- [ ] Write unit tests for each
- [ ] Write integration tests for each

### Milestone 1.7: Dynamic Inventory Plugin (Week 7)
**Goal**: Auto-generate Ansible inventory from rdc config.

- [ ] Implement `plugins/inventory/rediacc.py`
  - [ ] Extend `BaseInventoryPlugin` + `Cacheable` mixin
  - [ ] Read rdc config, generate hosts
  - [ ] Set SSH connection vars from config
  - [ ] Group by domain if infra configured
  - [ ] Pass rediacc-specific host vars (datastore, repos)
  - [ ] Cache support (avoid repeated `rdc config show` calls)
- [ ] Write unit tests (mock config output, test cache hit/miss)
- [ ] Write integration test (`ansible-inventory -i rediacc.yml --list`)

### Milestone 1.8: Roles and Playbooks (Week 7-8)
**Goal**: Reusable high-level workflows.

- [ ] Implement `roles/setup_machine/`
- [ ] Implement `roles/deploy_app/`
- [ ] Implement `roles/migrate_repo/`
- [ ] Implement `roles/backup_fleet/`
- [ ] Implement `roles/disaster_recovery/`
- [ ] Write example playbooks (deploy, migrate, backup, health_check)
- [ ] Write Molecule tests for each role

### Milestone 1.9: Documentation and Release (Week 8-9)
**Goal**: Collection ready for public use.

- [ ] Write README.md with getting started guide
- [ ] Write role-specific README.md files
- [ ] Add ansible-lint configuration
- [ ] Set up CI pipeline (lint, unit, integration)
- [ ] Build and publish to Ansible Galaxy
- [ ] Add to rediacc documentation site

---

## Phase 2: Terraform Provider

### Milestone 2.1: Provider Skeleton (Week 9-10)
**Goal**: Compilable provider with config and client.

- [ ] Initialize Go module (`packages/terraform/terraform-provider-rediacc/`)
- [ ] Implement `main.go`
- [ ] Implement `internal/provider/provider.go`
  - [ ] Schema (config_name, config_path, rdc_path)
  - [ ] Environment variable fallback (REDIACC_CONFIG_NAME, REDIACC_RDC_PATH)
  - [ ] Configure (create RdcClient, verify connectivity)
  - [ ] Resource/DataSource registration
- [ ] Implement `internal/client/rdc.go`
  - [ ] RunQuery (execute + unwrap envelope)
  - [ ] RunLifecycle (execute, exit code only)
  - [ ] Verify (rdc config show)
  - [ ] Convenience methods for common operations
- [ ] Write unit tests for client
- [ ] Write GNUmakefile (build, test)
- [ ] Set up `dev_overrides` workflow (no `make install` needed)
- [ ] Verify `terraform plan` works with dev_overrides

**Deliverable**: Provider builds and initializes via dev_overrides.

### Milestone 2.2: Machine Resource + Import (Week 10-11)
**Goal**: Manage machines via Terraform. Import existing machines.

- [ ] Implement `internal/provider/resource_machine.go`
  - [ ] Schema (minimize required: name, ip, user only)
  - [ ] Create → `rdc config add-machine` + optional `setup-machine`
  - [ ] Read → `rdc config show` → check machines[name]
  - [ ] Update → remove + re-add (or setup if only setup changed)
  - [ ] Delete → `rdc config remove-machine`
  - [ ] **ImportState → parse machine name** (day-one requirement)
  - [ ] UseStateForUnknown plan modifier for computed attributes
- [ ] Write unit tests (schema, import parsing)
- [ ] Write acceptance test (create, update, import, destroy)
- [ ] Write example config (including import block example)

**Deliverable**: `terraform import rediacc_machine.web web-1` works.

### Milestone 2.3: Repository Resource + Import (Week 11-13)
**Goal**: Full repo lifecycle via Terraform. Import existing repos.

- [ ] Implement `internal/provider/resource_repository.go`
  - [ ] Schema (minimize required: name, machine only; size required_if new)
  - [ ] Create
    - [ ] Normal: create + optional sync + optional deploy
    - [ ] Fork: fork from parent
  - [ ] Read
    - [ ] Check config repositories + machine containers
    - [ ] Drift detection (running state vs deploy attribute)
    - [ ] UseStateForUnknown for guid, network_id
  - [ ] Update
    - [ ] Size increase → expand (ForceNew on decrease)
    - [ ] Source changed → re-sync + redeploy
    - [ ] Deploy toggled → up/down
    - [ ] Autostart changed → enable/disable
  - [ ] Delete
    - [ ] backup_before_destroy logic
    - [ ] Stop → unmount → delete
  - [ ] **ImportState → parse `name:machine`** (day-one requirement)
- [ ] Write unit tests (schema, import parsing, state transitions)
- [ ] Write acceptance tests
  - [ ] Basic lifecycle (create → deploy → expand → delete)
  - [ ] Idempotency (second apply = no diff)
  - [ ] Import then plan (imported resource shows no drift)
  - [ ] Fork workflow
  - [ ] Backup before destroy
  - [ ] for_each with multiple machines
- [ ] Write example configs (including for_each and import block examples)

### Milestone 2.4: Data Sources (Week 13-14)
**Goal**: Read-only queries for Terraform configs.

- [ ] Implement `data_source_machines.go`
- [ ] Implement `data_source_repositories.go`
- [ ] Implement `data_source_containers.go`
- [ ] Implement `data_source_health.go`
- [ ] Write tests for each
- [ ] Write example configs

### Milestone 2.5: Backup Schedule + Infra Resources (Week 14-15)
**Goal**: Complete resource coverage.

- [ ] Implement `resource_backup_schedule.go`
- [ ] Implement `resource_infra.go`
- [ ] Write tests
- [ ] Write examples

### Milestone 2.5b: Publish v0.1.0 (Week 14)
**Goal**: Early release for user feedback. Don't wait for perfection.

- [ ] Publish v0.1.0 with machine + repository + import
- [ ] Set up `.goreleaser.yml`
- [ ] Set up CI pipeline (build, lint, unit, acceptance)
- [ ] Publish to Terraform Registry
- [ ] Announce, gather feedback, iterate

**Rationale**: The Dokku provider stayed at 0.x for months and improved based
on real user feedback. Shipping early catches schema design issues before
they become breaking changes in 1.0.

### Milestone 2.6: Documentation and Release (Week 15-16)
**Goal**: Polish for 0.2.0+ and eventual 1.0.

- [ ] Set up `tfplugindocs` generation
- [ ] Write doc templates for each resource/data source
- [ ] Set up GPG signing for releases
- [ ] Write import workflow guide (biggest user need)
- [ ] Write `dev_overrides` guide for contributors
- [ ] Add to rediacc documentation site

---

## Phase 3: Integration

### Milestone 3.1: Terraform → Ansible Pipeline (Week 16-17)
**Goal**: Terraform outputs feed Ansible inventory.

- [ ] Test dynamic inventory plugin reads Terraform-populated config
- [ ] Write example: Terraform + Hetzner → Ansible deploy
- [ ] Write example: Terraform + DigitalOcean → Ansible deploy
- [ ] Write integration test (full pipeline against ops VMs)

### Milestone 3.2: Reference Architectures (Week 17-18)
**Goal**: Complete example configurations for common use cases.

- [ ] Single server (Terraform only)
- [ ] Multi-server fleet (Terraform + Ansible)
- [ ] Multi-region replication
- [ ] Disaster recovery runbook
- [ ] GitOps CI/CD pipeline
- [ ] Write documentation for each architecture

### Milestone 3.3: Integration Tests (Week 18-19)
**Goal**: End-to-end testing of the full stack.

- [ ] Write `tests/integration/test_full_stack.sh`
- [ ] Test: Terraform apply → Ansible deploy → verify → Terraform destroy
- [ ] Test: DR scenario (destroy source → restore from backup)
- [ ] Test: Migration scenario (move repo between machines)
- [ ] Add to CI pipeline

---

## Summary Timeline

```
Week  1-2:  [Phase 0] Foundations + collection skeleton
Week  2-3:  [Phase 1] rediacc_machine module
Week  3-4:  [Phase 1] rediacc_repo module
Week  4-5:  [Phase 1] rediacc_machine_info + rediacc_sync
Week  5-6:  [Phase 1] Backup modules (backup, backup_info, backup_sync)
Week  6-7:  [Phase 1] Remaining modules
Week  7-8:  [Phase 1] Inventory plugin (with caching) + roles + playbooks
Week  8-9:  [Phase 1] Docs + release ← ANSIBLE COLLECTION v1.0
Week  9-10: [Phase 2] Provider skeleton + client + env var fallback
Week 10-11: [Phase 2] Machine resource + import
Week 11-13: [Phase 2] Repository resource + import + for_each support
Week 13-14: [Phase 2] Data sources
    Week 14: ← PUBLISH v0.1.0 (early release for feedback)
Week 14-15: [Phase 2] Backup schedule + infra
Week 15-16: [Phase 2] Docs + polish ← TERRAFORM PROVIDER v0.2.0
Week 16-17: [Phase 3] Integration pipeline
Week 17-18: [Phase 3] Reference architectures + import workflow guide
Week 18-19: [Phase 3] Integration tests ← FULL STACK v0.3.0
    Future: Stabilize based on feedback → v1.0.0
```

## Risk Register

| Risk | Impact | Mitigation |
|------|--------|------------|
| **37 commands lack JSON output** | High | Phase 0 fixes blocking gaps; execute-then-query pattern covers the rest |
| **Terraform concurrency corrupts config** | High | mutexKV per machine + config mutex (see `05-terraform-provider.md`) |
| **Terraform destroy deletes user data** | Critical | `prevent_destroy` defaults, `backup_before_destroy`, `force: true` for Ansible |
| **No import support blocks adoption** | Critical | Import is day-one requirement for every resource — highest priority after CRUD |
| **Long operations timeout** | Medium | `terraform-plugin-framework-timeouts` with generous defaults; Ansible `async` |
| **Drift detection gaps** | Medium | Accept for v0.x: volume size, autostart, sync content not queryable |
| **rdc commands too slow for Terraform** | Medium | Parallel across machines (mutexKV allows it); cache config reads within a plan |
| **ops VMs not available in CI** | High | Self-hosted runner with KVM; Docker-in-Docker fallback for basic tests |
| **rdc CLI interface changes** | Medium | Centralized in `rdc_runner.py` / `rdc.go` — one file to update per language |
| **Error envelope format varies** | Medium | Phase 0.5 validates error structure; fallback: treat unparseable errors as non-retryable |
| **Config encryption blocks JSON parsing** | Low | rdc handles decryption transparently; provider never sees encrypted data |
| **Ansible Galaxy namespace conflict** | Low | Register `rediacc` namespace early |
| **Terraform Registry approval delay** | Low | Provider works locally without registry; `dev_overrides` for development |
| **Schema design mistakes in 1.0** | High | Start at 0.x, iterate with feedback. Breaking changes are free below 1.0. |
| **Phantom diffs in plan output** | Medium | UseStateForUnknown for stable computed values; never store timestamps as attributes |

## Definition of Done (per milestone)

- [ ] All new code has unit tests (80%+ coverage)
- [ ] Integration tests pass against ops VMs
- [ ] No regressions in existing tests
- [ ] Documentation updated
- [ ] Code reviewed
- [ ] CI pipeline passes
- [ ] Examples work end-to-end
