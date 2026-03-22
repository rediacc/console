# Implementation Order and Task Breakdown

## Testing Philosophy: Gate Every Milestone

Every milestone ends with a **Gate** — a concrete, runnable verification that the
milestone is complete. Gates are not aspirational; they are pass/fail checkpoints.

### Rules

1. **No gate, no next milestone.** Don't start 1.3 until 1.2's gate passes.
2. **Gates include regression.** Every gate re-runs ALL previous unit tests,
   not just the new ones. A new module must not break `rdc_runner.py`.
3. **Smoke tests are cumulative.** A single smoke playbook/config grows with
   each milestone, exercising all implemented features together.
4. **Phase transitions require full suite.** Before starting Phase 2, ALL
   Phase 1 tests must pass (unit + integration + smoke).

### Smoke Test Files

| Phase | File | Grows with |
|-------|------|------------|
| 0 | `tests/smoke/verify-cli-fixes.sh` | Each CLI fix |
| 1 | `tests/smoke/ansible-smoke.yml` | Each Ansible milestone (tagged) |
| 2 | `tests/smoke/terraform-smoke/main.tf` | Each Terraform milestone |
| 3 | `tests/integration/test_full_stack.sh` | Integration patterns |

The Ansible smoke playbook uses tags so you can run subsets:
```bash
# Run smoke for milestones 1.2-1.4 only
ansible-playbook tests/smoke/ansible-smoke.yml --tags "machine,repo,sync"

# Full smoke (all implemented milestones)
ansible-playbook tests/smoke/ansible-smoke.yml --tags all
```

The Terraform smoke config uses `-target` for subsets:
```bash
# Run smoke for milestones 2.2-2.3 only
cd tests/smoke/terraform-smoke
terraform apply -auto-approve -target=rediacc_machine.test -target=rediacc_repository.test
terraform destroy -auto-approve
```

See `09-test-environment.md` for smoke test content definitions.

---

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
- [ ] Evaluate: is the workaround sufficient for v0.x?

**Fix 6: `datastore status`** — IMPORTANT, plain JSON (no envelope)
- Renet function outputs clean JSON to stdout, but CLI streams it via
  `outputService.info()` instead of routing through `outputService.print()`
- Workaround: runners parse stdout as plain JSON (no envelope unwrapping)
- Partially closes "volume size not queryable" drift detection gap
- [ ] Evaluate: route through `outputService.print()` for consistent envelope wrapping
- [ ] If not fixed, document plain JSON parsing in Ansible runner and Go client

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

**Gate:**
```bash
# Each fixed command returns JSON envelope
rdc --output json backup schedule show 2>/dev/null | jq -e '.success'
rdc --output json backup list -m rediacc11 2>/dev/null | jq -e '.success'

# Test environment healthy
rdc machine health rediacc11 --output json | jq -e '.data'
rdc machine health rediacc12 --output json | jq -e '.data'

# Smoke script passes
tests/smoke/verify-cli-fixes.sh   # exits 0
```

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

**Gate:**
```bash
cd packages/ansible
pytest tests/unit/module_utils/ -v                   # rdc_runner.py + rdc_common.py tests pass
ansible-galaxy collection build rediacc/console/     # Tarball builds cleanly
ansible-galaxy collection install rediacc-console-*.tar.gz --force  # Installs without error
```

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
- [ ] Add `machine` tag to smoke playbook

**Deliverable**: Can register and setup ops VMs via Ansible.

**Gate:**
```bash
cd packages/ansible
pytest tests/unit/ -v                                              # ALL unit tests (regression)
ansible-playbook tests/smoke/ansible-smoke.yml --tags machine      # Register rediacc11 → verify → remove → verify gone
```

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
- [ ] Add `repo` tag to smoke playbook

**Deliverable**: Full repo management via Ansible.

**Gate:**
```bash
cd packages/ansible
pytest tests/unit/ -v                                              # ALL unit tests (regression)
pytest tests/integration/test_02_repo_lifecycle.py -v              # Full lifecycle against VM
ansible-playbook tests/smoke/ansible-smoke.yml --tags machine,repo # Register → create repo → deploy → stop → delete → cleanup
```

### Milestone 1.4: Machine Info + Sync (Week 4-5)
**Goal**: Read-only inspection and file sync.

- [ ] Implement `plugins/modules/rediacc_machine_info.py`
  - [ ] query: info, containers, services, health, repos
- [ ] Implement `plugins/modules/rediacc_sync.py`
  - [ ] direction: upload, download
  - [ ] Options: mirror, verify, exclude, dry_run
- [ ] Write unit tests
- [ ] Write integration tests (sync test-app, verify containers)
- [ ] Add `sync` tag to smoke playbook

**Deliverable**: Can deploy an app end-to-end: machine info → sync → deploy → verify.

**Gate:**
```bash
cd packages/ansible
pytest tests/unit/ -v                                                  # ALL unit tests (regression)
pytest tests/integration/test_03_sync_module.py -v                     # Sync + verify
ansible-playbook tests/smoke/ansible-smoke.yml --tags machine,repo,sync
# Register → create repo → sync test-app → deploy → query containers → health check → cleanup
```

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
- [ ] Add `backup` tag to smoke playbook

**Deliverable**: Cross-machine backup and scheduling via Ansible.

**Gate:**
```bash
cd packages/ansible
pytest tests/unit/ -v                                                            # ALL unit tests (regression)
pytest tests/integration/test_04_backup_cross_machine.py -v                      # Push rediacc11→rediacc12
ansible-playbook tests/smoke/ansible-smoke.yml --tags machine,repo,sync,backup   # Previous + backup push/pull + schedule set
```

### Milestone 1.6: Remaining Modules (Week 6-7)
**Goal**: Complete module coverage.

- [ ] Implement `plugins/modules/rediacc_snapshot.py` (state: present/absent)
- [ ] Implement `plugins/modules/rediacc_snapshot_info.py` (read-only listing)
- [ ] Implement `plugins/modules/rediacc_autostart.py`
- [ ] Implement `plugins/modules/rediacc_infra.py`
- [ ] Implement `plugins/modules/rediacc_template.py`
- [ ] Write unit tests for each
- [ ] Write integration tests for each
- [ ] Add `snapshot`, `autostart` tags to smoke playbook

**Gate:**
```bash
cd packages/ansible
pytest tests/unit/ -v                                                                          # ALL unit tests (regression)
ansible-playbook tests/smoke/ansible-smoke.yml --tags machine,repo,sync,backup,snapshot,autostart
```

### Milestone 1.6b: Datastore Modules (Week 7)
**Goal**: Datastore management and Ceph instant fork.

- [ ] Implement `plugins/modules/rediacc_datastore.py`
  - [ ] `state: present` → `rdc datastore init --backend <backend>`
  - [ ] Parameters: `machine`, `backend` (local/ceph), `size`, `force`
  - [ ] Idempotency: check `datastore status` before acting
  - [ ] Check mode: report current backend and size
- [ ] Implement `plugins/modules/rediacc_datastore_info.py`
  - [ ] Read-only: returns `datastore status` output
  - [ ] Handle plain JSON (no envelope) — parse stdout directly
  - [ ] Returns: type, size, used, available, backend, mounted, cow_mode
- [ ] Implement `plugins/modules/rediacc_datastore_fork.py`
  - [ ] `state: present` → `rdc datastore fork -m <source> --to <target>`
  - [ ] `state: absent` → `rdc datastore unfork` (requires snapshot, clone, source_image)
  - [ ] `required_if`: present requires target_name, absent requires snapshot+clone+source_image
  - [ ] Returns fork metadata (snapshot, clone, source_image) for unfork
- [ ] Write unit tests (mock rdc runner, test plain JSON parsing for info)
- [ ] Write integration tests (requires TEST_TIER=full / Ceph cluster)
  - [ ] `test_05_datastore_fork.py`: init Ceph → fork → verify cow_mode → unfork → verify restored
- [ ] Add `datastore` tag to smoke playbook

**Deliverable**: Full datastore lifecycle including instant Ceph fork via Ansible.

**Gate (basic tier):**
```bash
cd packages/ansible
pytest tests/unit/ -v   # ALL unit tests — includes datastore unit tests (plain JSON parsing, mock fork output)
```

**Gate (full tier — requires TEST_TIER=full):**
```bash
cd packages/ansible
pytest tests/unit/ -v
pytest tests/integration/test_05_datastore_fork.py -v                            # Ceph fork lifecycle
ansible-playbook tests/smoke/ansible-smoke.yml --tags datastore                  # Init Ceph → fork → verify → unfork
```

### Milestone 1.7: Dynamic Inventory Plugin (Week 7-8)
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

**Gate:**
```bash
cd packages/ansible
pytest tests/unit/ -v                                                            # ALL unit tests (regression)
ansible-inventory -i tests/smoke/rediacc.yml --list | jq '.all.hosts | length > 0'  # Returns hosts from config
ansible -i tests/smoke/rediacc.yml all -m ping                                  # Can reach machines via dynamic inventory
```

### Milestone 1.8: Roles and Playbooks (Week 8-9)
**Goal**: Reusable high-level workflows.

- [ ] Implement `roles/setup_machine/`
- [ ] Implement `roles/deploy_app/`
- [ ] Implement `roles/migrate_repo/`
- [ ] Implement `roles/backup_fleet/`
- [ ] Implement `roles/disaster_recovery/`
- [ ] Implement `roles/fork_environment/`
  - [ ] Defaults: source_machine (required), target_name (required), repos_to_deploy ([])
  - [ ] Tasks: verify Ceph backend → fork → deploy repos → verify health → store metadata
  - [ ] Tags: fork, deploy, verify, cleanup
  - [ ] Requires Ceph-backed datastore on source machine
- [ ] Write example playbooks (deploy, migrate, backup, health_check, preview)
- [ ] Write Molecule tests for each role

**Gate:**
```bash
cd packages/ansible
pytest tests/unit/ -v                                                            # ALL unit tests (regression)
molecule test -s deploy_app                                                      # deploy_app role end-to-end
molecule test -s setup_machine                                                   # setup_machine role end-to-end
ansible-playbook tests/smoke/ansible-smoke.yml --tags all                        # FULL smoke: all features together
```

### Milestone 1.9: Documentation and Release (Week 9-10)
**Goal**: Collection ready for public use.

- [ ] Write README.md with getting started guide
- [ ] Write role-specific README.md files
- [ ] Add ansible-lint configuration
- [ ] Set up CI pipeline (lint, unit, integration)
- [ ] Build and publish to Ansible Galaxy
- [ ] Add to rediacc documentation site

**Gate:**
```bash
cd packages/ansible
ansible-lint rediacc/console/                                                    # No lint errors
ansible-galaxy collection build rediacc/console/                                 # Clean tarball
ansible-galaxy collection install rediacc-console-*.tar.gz --force
ansible-doc rediacc.console.rediacc_repo                                         # Docs render correctly
```

### Phase 1 → Phase 2 Transition Gate

Before starting any Terraform work, confirm Phase 1 is solid:

```bash
cd packages/ansible

# Full unit suite
pytest tests/unit/ -v

# Full integration suite (against running VMs)
pytest tests/integration/ -v

# Full smoke playbook (all tags)
ansible-playbook tests/smoke/ansible-smoke.yml --tags all

# Lint passes
ansible-lint rediacc/console/

# Collection builds and installs cleanly
ansible-galaxy collection build rediacc/console/
ansible-galaxy collection install rediacc-console-*.tar.gz --force
```

All must pass. If any fail, fix before proceeding to Phase 2.

---

## Phase 2: Terraform Provider

### Milestone 2.1: Provider Skeleton (Week 10-11)
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

**Gate:**
```bash
cd packages/terraform/terraform-provider-rediacc
go build ./...                                                                   # Compiles
go vet ./...                                                                     # No vet issues
go test ./internal/client/ -v                                                    # Client unit tests pass
go test ./internal/provider/ -v -run TestProvider                                # Provider config tests pass
terraform plan -no-color 2>&1 | grep -q "No changes"                            # Initializes with dev_overrides
```

### Milestone 2.2: Machine Resource + Import (Week 11-12)
**Goal**: Manage machines via Terraform. Import existing machines.

- [ ] Implement `internal/provider/resource_machine.go`
  - [ ] Schema (minimize required: name, ip, user only)
  - [ ] Create → `rdc config add-machine` + optional `setup-machine`
  - [ ] Optional `ceph {}` block → `rdc config set-ceph` + `rdc datastore init --backend ceph`
  - [ ] Read → `rdc config show` → check machines[name]
  - [ ] Read (Ceph) → `rdc datastore status` → check backend, size, mounted (plain JSON)
  - [ ] Update → remove + re-add (or setup if only setup changed)
  - [ ] Delete → `rdc config remove-machine`
  - [ ] **ImportState → parse machine name** (day-one requirement)
  - [ ] UseStateForUnknown plan modifier for computed attributes
- [ ] Write unit tests (schema, import parsing, ceph block validation)
- [ ] Write acceptance test (create, update, import, destroy)
- [ ] Write acceptance test (create with ceph — requires TEST_TIER=full)
- [ ] Write example config (including import block example)
- [ ] Add machine resource to smoke TF config

**Deliverable**: `terraform import rediacc_machine.web web-1` works.

**Gate:**
```bash
cd packages/terraform/terraform-provider-rediacc
go test ./... -v                                                                 # ALL unit tests (regression)
TF_ACC=1 go test ./... -v -run TestAccMachine -timeout 30m                       # Acceptance: create → import → plan no drift → destroy

# Smoke: apply creates machine, plan shows no drift, destroy removes it
cd tests/smoke/terraform-smoke
terraform apply -auto-approve -target=rediacc_machine.test
terraform plan -target=rediacc_machine.test | grep -q "No changes"
terraform destroy -auto-approve -target=rediacc_machine.test
```

### Milestone 2.3: Repository Resource + Import (Week 12-14)
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
- [ ] Add repository resource to smoke TF config

**Gate:**
```bash
cd packages/terraform/terraform-provider-rediacc
go test ./... -v                                                                 # ALL unit tests (regression)
TF_ACC=1 go test ./... -v -run 'TestAcc(Machine|Repository)' -timeout 30m       # All acceptance tests so far

# Smoke: machine + repo lifecycle
cd tests/smoke/terraform-smoke
terraform apply -auto-approve
terraform plan | grep -q "No changes"                                            # Idempotent
terraform destroy -auto-approve
```

### Milestone 2.4: Data Sources (Week 14-15)
**Goal**: Read-only queries for Terraform configs.

- [ ] Implement `data_source_machines.go`
- [ ] Implement `data_source_repositories.go`
- [ ] Implement `data_source_containers.go`
- [ ] Implement `data_source_health.go`
- [ ] Implement `data_source_datastore_status.go`
  - [ ] Wraps `rdc datastore status -m <machine>` (plain JSON, no envelope)
  - [ ] Returns: type, size, used, available, backend, mounted, initialized, rbd_image, cow_mode
  - [ ] Handle plain JSON parsing (no envelope unwrapping)
- [ ] Write tests for each
- [ ] Write example configs
- [ ] Add data sources to smoke TF config

**Gate:**
```bash
cd packages/terraform/terraform-provider-rediacc
go test ./... -v                                                                 # ALL unit tests (regression)
TF_ACC=1 go test ./... -v -run 'TestAcc(Machine|Repository|.*DataSource)' -timeout 30m

# Smoke: data sources return values after apply
cd tests/smoke/terraform-smoke
terraform apply -auto-approve
terraform output machine_health | grep -q "healthy"                              # Data source works
terraform destroy -auto-approve
```

### Milestone 2.5: Backup Schedule + Infra Resources (Week 15-16)
**Goal**: Complete basic resource coverage.

- [ ] Implement `resource_backup_schedule.go`
- [ ] Implement `resource_infra.go`
- [ ] Write tests
- [ ] Write examples
- [ ] Add to smoke TF config

**Gate:**
```bash
cd packages/terraform/terraform-provider-rediacc
go test ./... -v                                                                 # ALL unit tests (regression)
TF_ACC=1 go test ./... -v -timeout 30m                                           # ALL acceptance tests
```

### Milestone 2.5b: Publish v0.1.0 (Week 15)
**Goal**: Early release for user feedback. Don't wait for perfection.

- [ ] Publish v0.1.0 with machine + repository + import
- [ ] Set up `.goreleaser.yml`
- [ ] Set up CI pipeline (build, lint, unit, acceptance)
- [ ] Publish to Terraform Registry
- [ ] Announce, gather feedback, iterate

**Rationale**: The Dokku provider stayed at 0.x for months and improved based
on real user feedback. Shipping early catches schema design issues before
they become breaking changes in 1.0.

**Gate:**
```bash
goreleaser release --snapshot --clean                                            # Builds all platform binaries
# Install from local binary, verify basic workflow:
terraform init && terraform plan                                                 # Provider initializes from registry
```

### Milestone 2.5c: Datastore Fork Resource (Week 16-17)
**Goal**: Declarative Ceph fork lifecycle — the differentiator.

- [ ] Implement `internal/provider/resource_datastore_fork.go`
  - [ ] Create → verify Ceph backend → `rdc datastore fork -m <source> --to <target>`
  - [ ] Read → `rdc datastore status` → check `cow_mode` (plain JSON)
  - [ ] Delete → `rdc datastore unfork` with snapshot/clone/source_image from state
  - [ ] Computed: snapshot, clone, source_image, cow_mode
  - [ ] ForceNew on source_machine or target_name change
  - [ ] Parse fork stdout for snapshot/clone names
- [ ] Add `DatastoreFork()`, `DatastoreUnfork()`, `DatastoreStatus()` convenience methods to client
- [ ] Write unit tests (fork output parsing, plain JSON handling, Ceph requirement error)
- [ ] Write acceptance tests (requires TEST_TIER=full / Ceph cluster)
  - [ ] Fork lifecycle: create fork → verify cow_mode → destroy (unfork) → verify restored
  - [ ] Datastore status data source during active fork
  - [ ] Error on non-Ceph machine
- [ ] Write example config (preview environment per PR, canary release)

**Deliverable**: `rediacc_datastore_fork` resource — instant staging/preview/canary.

**Gate (basic tier):**
```bash
cd packages/terraform/terraform-provider-rediacc
go test ./... -v                                                                 # Unit tests pass (fork output parsing, plain JSON, Ceph requirement error)
```

**Gate (full tier — requires TEST_TIER=full):**
```bash
cd packages/terraform/terraform-provider-rediacc
go test ./... -v
TF_ACC=1 TEST_TIER=full go test ./... -v -run TestAccDatastoreFork -timeout 30m  # Fork lifecycle acceptance
```

### Milestone 2.6: Documentation and Release (Week 17-18)
**Goal**: Polish for 0.2.0+ and eventual 1.0.

- [ ] Set up `tfplugindocs` generation
- [ ] Write doc templates for each resource/data source
- [ ] Set up GPG signing for releases
- [ ] Write import workflow guide (biggest user need)
- [ ] Write `dev_overrides` guide for contributors
- [ ] Add to rediacc documentation site

**Gate:**
```bash
cd packages/terraform/terraform-provider-rediacc
tfplugindocs generate && git diff --exit-code docs/                              # Docs up to date
for dir in examples/resources/*/; do (cd "$dir" && terraform validate); done     # All examples valid
```

### Phase 2 → Phase 3 Transition Gate

Before starting integration work, confirm both Phase 1 and Phase 2 are solid:

```bash
# Ansible full suite
cd packages/ansible
pytest tests/unit/ -v
pytest tests/integration/ -v
ansible-playbook tests/smoke/ansible-smoke.yml --tags all
ansible-lint rediacc/console/

# Terraform full suite
cd packages/terraform/terraform-provider-rediacc
go test ./... -v
TF_ACC=1 go test ./... -v -timeout 30m

# Both tools install cleanly
ansible-galaxy collection build packages/ansible/rediacc/console/
goreleaser release --snapshot --clean
```

All must pass. If any fail, fix before proceeding to Phase 3.

---

## Phase 3: Integration

### Milestone 3.1: Terraform → Ansible Pipeline (Week 18-19)
**Goal**: Terraform outputs feed Ansible inventory.

- [ ] Test dynamic inventory plugin reads Terraform-populated config
- [ ] Write example: Terraform + Hetzner → Ansible deploy
- [ ] Write example: Terraform + DigitalOcean → Ansible deploy
- [ ] Write integration test (full pipeline against ops VMs)

**Gate:**
```bash
# Terraform apply populates config, Ansible reads it
cd tests/integration/terraform && terraform apply -auto-approve
ansible-inventory -i ../ansible/rediacc.yml --list | jq '.all.hosts | length == 2'
ansible-playbook -i ../ansible/rediacc.yml ../ansible/deploy.yml
cd ../terraform && terraform destroy -auto-approve
```

### Milestone 3.2: Reference Architectures (Week 19-20)
**Goal**: Complete example configurations for common use cases.

- [ ] Single server (Terraform only)
- [ ] Multi-server fleet (Terraform + Ansible)
- [ ] Multi-region replication
- [ ] Disaster recovery runbook
- [ ] GitOps CI/CD pipeline
- [ ] Preview environments via Ceph fork (TF manages fork, Ansible deploys PR changes)
- [ ] Canary release with real data (Ansible: fork → deploy → validate → unfork)
- [ ] Nightly DR validation (Ansible: fork → simulate failure → restore → verify → unfork)
- [ ] Write documentation for each architecture

**Gate:**
```bash
# All reference architecture TF configs are valid
for dir in examples/architectures/*/; do
    (cd "$dir" && terraform init -backend=false && terraform validate)
done

# All reference playbooks have valid syntax
ansible-playbook --syntax-check examples/playbooks/*.yml
```

### Milestone 3.3: Integration Tests (Week 20-21)
**Goal**: End-to-end testing of the full stack.

- [ ] Write `tests/integration/test_full_stack.sh`
- [ ] Test: Terraform apply → Ansible deploy → verify → Terraform destroy
- [ ] Test: DR scenario (destroy source → restore from backup)
- [ ] Test: Migration scenario (move repo between machines)
- [ ] Test: Ceph fork preview environment (TF fork → Ansible deploy → verify → TF destroy)
  - Requires TEST_TIER=full
- [ ] Test: Canary release flow (fork → deploy new version → validate → unfork)
  - Requires TEST_TIER=full
- [ ] Add to CI pipeline (basic tier default, full tier on self-hosted runners)

**Gate:**
```bash
# Full stack integration (basic tier)
tests/integration/test_full_stack.sh

# Full stack integration (full tier — Ceph)
TEST_TIER=full tests/integration/test_full_stack.sh
```

---

## Summary Timeline

```
Week  1-2:  [Phase 0] Foundations + collection skeleton
Week  2-3:  [Phase 1] rediacc_machine module
Week  3-4:  [Phase 1] rediacc_repo module
Week  4-5:  [Phase 1] rediacc_machine_info + rediacc_sync
Week  5-6:  [Phase 1] Backup modules (backup, backup_info, backup_sync)
Week  6-7:  [Phase 1] Remaining modules (snapshot, autostart, infra, template)
      7:    [Phase 1] Datastore modules (datastore, datastore_info, datastore_fork)
Week  7-8:  [Phase 1] Inventory plugin (with caching)
Week  8-9:  [Phase 1] Roles + playbooks (incl. fork_environment)
Week  9-10: [Phase 1] Docs + release ← ANSIBLE COLLECTION v1.0
                       ⛔ Phase 1 → Phase 2 Transition Gate
Week 10-11: [Phase 2] Provider skeleton + client + env var fallback
Week 11-12: [Phase 2] Machine resource + import (+ optional ceph block)
Week 12-14: [Phase 2] Repository resource + import + for_each support
Week 14-15: [Phase 2] Data sources (incl. datastore_status)
    Week 15: ← PUBLISH v0.1.0 (early release for feedback)
Week 15-16: [Phase 2] Backup schedule + infra
Week 16-17: [Phase 2] Datastore fork resource ← DIFFERENTIATOR
Week 17-18: [Phase 2] Docs + polish ← TERRAFORM PROVIDER v0.2.0
                       ⛔ Phase 2 → Phase 3 Transition Gate
Week 18-19: [Phase 3] Integration pipeline
Week 19-20: [Phase 3] Reference architectures (incl. fork-based patterns)
Week 20-21: [Phase 3] Integration tests ← FULL STACK v0.3.0
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
| **Ceph cluster unavailable in CI** | Medium | Two-tier testing: basic (no Ceph) default, full (Ceph) on self-hosted runners with 12GB+ RAM |
| **Fork mounts on source machine** | Medium | Document clearly; design patterns around staging/test machines as fork sources, not production |
| **`datastore status` plain JSON (no envelope)** | Low | Handle in both Ansible runner and Go client as special case; fix in rdc CLI long-term |
| **Ceph fork metadata lost on state corruption** | Medium | Store snapshot/clone/source_image as computed attributes; manual `rdc datastore unfork` as escape hatch |
| **Gate regression catches real issues late** | Medium | Run `pytest tests/unit/ -v` (or `go test ./...`) after every code change, not just at gates |

## Definition of Done (per milestone)

- [ ] All new code has unit tests (80%+ coverage)
- [ ] ALL previous unit tests still pass (regression)
- [ ] Integration tests pass against ops VMs
- [ ] Smoke test updated with new features (tagged)
- [ ] **Gate commands pass** (specific to each milestone)
- [ ] Documentation updated
- [ ] Code reviewed
- [ ] CI pipeline passes
- [ ] Examples work end-to-end
