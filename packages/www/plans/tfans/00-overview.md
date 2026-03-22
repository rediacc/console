# Terraform + Ansible Integration Plan for Rediacc

## Reading Order

| # | File | Phase | Summary |
|---|------|-------|---------|
| 0 | `00-overview.md` | - | This file. Architecture vision and rationale |
| 1 | `01-ansible-collection.md` | 1 | Collection structure, packaging, distribution |
| 2 | `02-ansible-modules.md` | 1 | Individual module specifications |
| 3 | `03-ansible-roles.md` | 1 | Reusable role definitions |
| 4 | `04-ansible-testing.md` | 1 | Ansible testing strategy |
| 5 | `05-terraform-provider.md` | 2 | Provider architecture and design |
| 6 | `06-terraform-resources.md` | 2 | Resource and data source specifications |
| 7 | `07-terraform-testing.md` | 2 | Terraform testing strategy |
| 8 | `08-integration.md` | 3 | Terraform + Ansible + rdc combined workflows |
| 9 | `09-test-environment.md` | - | Test infrastructure using `rdc ops` |
| 10 | `10-implementation-order.md` | - | Prioritized task breakdown with estimates |

## Architecture Vision

```
                        USER'S INFRASTRUCTURE
                        =====================

  ┌──────────────────────────────────────────────────────┐
  │ Terraform (HCL)                                      │
  │                                                      │
  │ Cloud VMs ──► DNS ──► Firewall ──► rediacc_machine   │
  │ (Hetzner,    (CF)    (rules)      (register +        │
  │  DO, AWS)                          setup via SSH)     │
  └───────────────────────┬──────────────────────────────┘
                          │ terraform output → inventory
  ┌───────────────────────▼──────────────────────────────┐
  │ Ansible (YAML playbooks)                             │
  │                                                      │
  │ Fleet orchestration:                                 │
  │  - Rolling deploys across N machines                 │
  │  - Conditional logic (disk space, OS version)        │
  │  - Health-check gates between batches                │
  │  - Backup scheduling across fleet                    │
  │  - Disaster recovery runbooks                        │
  └───────────────────────┬──────────────────────────────┘
                          │ calls rdc CLI
  ┌───────────────────────▼──────────────────────────────┐
  │ rdc / renet (existing)                               │
  │                                                      │
  │ Per-machine operations:                              │
  │  - Encrypted repo lifecycle (create/up/down/delete)  │
  │  - File sync (rsync delta)                           │
  │  - Cross-machine backup push/pull                    │
  │  - Live migration (CRIU checkpoint)                  │
  │  - BTRFS snapshots                                   │
  │  - Template-based deployment                         │
  └──────────────────────────────────────────────────────┘
```

## Why This Order

### Phase 1: Ansible Collection (implement first)

**Rationale**: Ansible wraps the existing `rdc` CLI. No changes to rdc needed.
The CLI-wrapper pattern is proven (see `community.general.terraform` module).
Immediate value: fleet-level parallelism and orchestration rdc currently lacks.

- Python modules (~100-200 lines each) wrapping `rdc` commands
- `rdc --output json` already provides structured output for parsing
- Low risk: if a module fails, the user can still run `rdc` directly
- Ansible Galaxy distribution reaches existing DevOps audiences

### Phase 2: Terraform Provider (implement second)

**Rationale**: Requires Go, more complex, but adds declarative state management.
Phase 1 experience informs which resources matter most. The provider calls
`rdc` CLI via `exec.Command()` — same wrapper pattern as Phase 1, different language.

- Go provider using `terraform-plugin-framework` (not legacy SDKv2)
- CLI-wrapper pattern, same as the Dokku Terraform provider
- Adds plan/apply, drift detection, dependency graph
- Needs careful design around data safety (repos contain user data)
- Must solve concurrency: Terraform runs operations in parallel but rdc
  cannot handle concurrent ops on the same machine

### Phase 3: Integration Layer (implement last)

**Rationale**: Combines both tools into cohesive workflows.
Requires both Phase 1 and Phase 2 to be stable.

- Terraform provisions infra + registers machines
- Terraform outputs flow to Ansible dynamic inventory
- Ansible orchestrates rdc across the fleet
- Example playbooks and Terraform configs for common scenarios

## What Rdc Already Handles (Do Not Duplicate)

These operations are rdc's domain. Ansible/Terraform should **call** rdc, not reimplement:

| Operation | rdc command | Multi-machine? |
|-----------|-------------|----------------|
| Create encrypted repo | `repo create` | Single machine |
| Deploy repo | `repo up` | Single machine |
| Stop repo | `repo down` | Single machine |
| Cross-machine backup | `backup push --to-machine` | Source + target |
| Cross-machine pull | `backup pull --from-machine` | Source + target |
| Storage backup | `backup push --to <storage>` | Single machine |
| Bulk sync to storage | `backup sync push` | All repos on 1 machine |
| Live migration | `backup push --checkpoint` | Source + target |
| File sync | `sync upload/download` | Single machine |
| Fork repo | `repo fork --tag` | Single machine |
| Machine setup | `config setup-machine` | Single machine |
| Backup scheduling | `backup schedule push` | Single machine |
| Deploy all repos | `repo up-all --parallel` | Single machine |
| Ceph datastore init | `datastore init --backend ceph` | Single machine |
| Instant fork (Ceph) | `datastore fork --to <machine>` | Source machine (Ceph cluster) |
| Fork cleanup | `datastore unfork` | Single machine |
| Datastore status | `datastore status` | Single machine |
| Ceph config | `config set-ceph` | Config write |

## Three Transfer Mechanisms

Rdc provides three ways to move data between machines. Each serves a different
purpose — they complement each other, not compete:

| | Backup Push | CRIU Migration | Ceph Fork |
|---|---|---|---|
| **Scope** | Single repository | Single repo + process state | Entire datastore (all repos) |
| **Speed** | Minutes-hours (rsync delta) | Seconds + transfer time | < 2 seconds (any size) |
| **Data transferred** | Changed blocks only (after first full) | Changed blocks + CRIU image (~130MB) | Zero (Ceph COW clone) |
| **Requires** | Both machines registered | CRIU installed on both | Ceph cluster |
| **Use case** | Backup, migration, DR | Live migration (preserve memory) | Staging, preview, testing, canary |
| **Granularity** | Per-repo | Per-repo | All repos at once |
| **Isolation** | Full (separate identity) | Full (same identity, new machine) | COW (reads shared, writes local) |
| **rdc command** | `backup push --to-machine` | `backup push --checkpoint` | `datastore fork --to` |
| **Ansible module** | `rediacc_backup` | `rediacc_backup` | `rediacc_datastore_fork` |
| **Terraform resource** | N/A (procedural) | N/A (procedural) | `rediacc_datastore_fork` |

**Why Ceph fork is a differentiator:** PlanetScale branches databases. Neon
branches Postgres. Vercel clones frontend builds. Rediacc forks **entire
encrypted application stacks** — Docker services, data volumes, LUKS encryption,
compose configs, all repos on a machine — in under 2 seconds regardless of size.
No other self-hosted infrastructure tool offers this.

**How fork works:** RBD snapshot → COW clone → device-mapper overlay.
Reads come from the shared Ceph clone (no transfer needed). Writes go to a
local sparse file that starts at 0 bytes and grows only with actual changes.
After unfork, the original datastore is restored automatically.

**Current limitation:** Fork mounts on the source machine, replacing its
`/mnt/rediacc` with the COW overlay. For production → staging cloning,
the staging machine needs Ceph client access to mount the clone independently.
The ops provisioner (`rdc ops up`) configures Ceph client access on all workers
automatically.

## What Ansible/Terraform Add (The Gaps)

| Gap | Tool | How |
|-----|------|-----|
| Parallel ops across N machines | Ansible | `hosts: all`, `serial: 2`, `strategy: free` |
| Conditional deployment | Ansible | `when: disk_free > 100GB` |
| Rolling updates with health gates | Ansible | `serial` + `until` + health check |
| Declarative desired state | Terraform | `resource "rediacc_repository"` in HCL |
| Drift detection | Terraform | `terraform plan` detects manual changes |
| Infrastructure + app in one flow | Terraform | Hetzner VM + rediacc repo in same apply |
| Dependency ordering across machines | Terraform | Implicit deps from resource references |
| Fleet inventory from infra | Both | Terraform outputs → Ansible dynamic inventory |
| Runbook codification | Ansible | Playbooks for DR, migration, scaling |

## Discovered Obstacles (from CLI source investigation)

### Architectural Rule: Always `rdc`, Never `renet`

Renet is a low-level orchestrator managed by rdc. External tools MUST call
`rdc` CLI only — never SSH into machines and run renet directly. Reasons:
rdc manages renet's lifecycle (provisioning/upgrades), builds the QueueVaultV2
payload (SSH keys, credentials, storage configs), manages config (machines,
repos, network IDs, SSH keys), and handles SSH transport. If rdc is missing
a command or JSON output, fix rdc — don't bypass it.

### Complete JSON Output Audit

The CLI has two output methods:
- `outputService.print(data, format)` → respects `--output json`, wraps in envelope
- `outputService.info/success/error()` → human-only, goes to stderr, no JSON

**Commands WITH JSON support (26 commands):**

| Category | Commands |
|----------|----------|
| Config queries | `config list`, `config show`, `config recover` (backup info) |
| Machine CRUD | `machine add`, `machine list`, `machine rename`, `machine delete`, `machine status` (via factory) |
| Machine queries | `machine info`, `machine containers`, `machine services`, `machine repos`, `machine health`, `machine vault-status`, `machine test-connection` |
| Queue | `queue list`, `queue trace` |
| Repo (dry-run only) | `repo up --dry-run`, `repo down --dry-run`, `repo delete --dry-run` |

**Commands with PARTIAL JSON support (streamed, no envelope):**

| Category | Commands | Notes |
|----------|----------|-------|
| Datastore | `datastore status` | Renet function outputs clean JSON to stdout, but CLI streams it without envelope wrapping. Parseable by runners as plain JSON. |

**Commands WITHOUT JSON support (42 commands) — the gaps:**

| Category | Commands | Impact |
|----------|----------|--------|
| Repo lifecycle | `create`, `mount`, `unmount`, `up`, `down`, `status`, `list` | HIGH — core operations for both tools |
| Repo extended | `fork`, `resize`, `expand`, `validate`, `template`, `ownership` | MEDIUM — needed for Terraform Update |
| Autostart | `enable`, `disable`, `enable-all`, `disable-all`, `list` | MEDIUM — Terraform needs read-back |
| Sync | `upload`, `download`, `status` | LOW — exit-code-only is acceptable |
| Backup | `push`, `pull`, `list`, `sync` | MEDIUM — `list` needed for DR |
| Backup schedule | `set`, `show`, `push` | HIGH — `show` blocks Terraform Read() |
| Datastore lifecycle | `init`, `fork`, `unfork` | LOW — lifecycle commands, exit-code-only is acceptable |
| Config mutations | `set-ceph` | LOW — config write, uses `outputService.info()` |
| Queue mutations | `create`, `cancel`, `retry`, `delete` | LOW — not used by IaC tools |

### Obstacle Severity and Fixes Required

**BLOCKING (must fix before implementation):**

1. **`backup schedule show`** — uses `outputService.info()` instead of `print()`.
   Without this, Terraform cannot implement Read() for `rediacc_backup_schedule`.
   Fix: change to `outputService.print(config, getOutputFormat())`.

2. **`repo list`** — pipes renet's raw stdout, no JSON formatting at all.
   Workaround exists (`config repositories` gives repo config, `machine containers`
   gives running state), but a direct `repo list` with JSON would simplify modules.

3. **`backup list`** — no JSON output. The disaster_recovery role and Terraform
   import both need to enumerate available backups programmatically.

**IMPORTANT (should fix, workarounds exist):**

4. **`repo status`** — pipes renet's raw stdout. Workaround: use `machine containers`
   filtered by repository name. Document this pattern.

5. **`autostart list`** — no JSON. Workaround: Terraform can track autostart state
   internally without read-back, but drift detection won't work.

6. **All repo lifecycle commands** — return human messages, not structured data.
   Workaround: execute-then-query pattern (run command → query state separately).
   Acceptable but adds latency (2 SSH calls per operation).

7. **`datastore status`** — renet function outputs clean JSON to stdout, but the
   CLI streams it via `outputService.info()` (stderr) + `executeFunction()` (stdout
   pass-through) instead of routing through `outputService.print()`. Workaround:
   runners parse stdout as plain JSON (no envelope). Fix: route through
   `outputService.print()` for consistent envelope wrapping. This partially closes
   the "volume size not queryable" drift detection gap — `datastore status` returns
   `size`, `used`, `available`, `backend`, `mounted` at the datastore level.

**NICE-TO-HAVE (workarounds are adequate):**

8. **`repo up/down/delete --dry-run`** DO return JSON — this is useful for
   Ansible check mode. The plans should leverage this.

9. **Sync commands** — exit-code-only is fine for Ansible (`changed: true` always).

10. **Datastore lifecycle commands** (`init`, `fork`, `unfork`) — exit-code-only
    is acceptable. Use `datastore status` to verify state after execution.

### JSON Envelope Format

All JSON output uses this envelope structure:

```
{success: bool, command: string, data: any, errors: null|[{code, message, details, retryable, guidance}], warnings: string[], metrics: {duration_ms: number}}
```

Key detail: the **error envelope includes `retryable` and `guidance` fields**.
This is valuable for Ansible/Terraform error handling — they can distinguish
transient failures from permanent ones without pattern-matching error messages.

### Config File Structure (relevant fields)

The rdc config (`~/.config/rediacc/rediacc.json`) contains:

- `machines` — map of machine name → {ip, user, port, datastore, knownHosts, infra}
- `repositories` — map of repo name → {repositoryGuid, tag, credential, networkId}
- `storages` — map of storage name → {provider, vaultContent}
- `ssh` / `sshContent` — SSH key paths and inline key content
- `backup` — {defaultDestination, schedule, enabled}
- `nextNetworkId` — auto-incrementing network allocation counter
- `encrypted` / `encryptedResources` — AES-256-GCM encryption for at-rest config
- `s3` — optional S3 resource state backend (still local adapter, not a separate mode)
- `id` / `version` — config identity and conflict detection

**Important for Terraform:** The `version` field increments on every config write.
If two Terraform operations modify config concurrently, the second will see a
version conflict. This is part of why per-machine locking matters.

### stdout/stderr Behavior

- **Query commands**: data → stdout (JSON envelope), status messages → stderr
- **Lifecycle commands**: renet's raw output → stdout, rdc's status → stderr
- **Auto-TTY detection**: when stdout is piped (non-TTY), CLI defaults to JSON
  even without `--output json`. This means Ansible/Terraform will get JSON
  from query commands automatically, but should still pass `--output json`
  explicitly for clarity.

## Key Design Decisions

### 1. CLI Wrapper Architecture

Modules call `rdc` via subprocess (`exec.Command` in Go, `run_command` in Python).
rdc is the only public interface — renet is internal.

**Precedent:** The Dokku Terraform provider follows the same pattern (wraps CLI
over SSH). The `community.general.terraform` Ansible module wraps the `terraform`
binary. This is a battle-tested approach.

**Three-layer design** (learned from Dokku provider):
1. **Transport layer** — executes rdc binary, captures output, handles timeouts
2. **Command builder** — constructs rdc arguments, parses JSON envelope
3. **Resource lifecycle** — maps Terraform CRUD / Ansible states to rdc commands

### 2. Concurrency and Locking (Terraform-specific)

**Problem:** Terraform runs resource operations in parallel (default parallelism=10).
rdc cannot handle concurrent operations on the same machine — two simultaneous
`repo up` commands on the same machine will conflict. Additionally, rdc's config
file has a `version` field that increments on writes, causing conflicts.

**Solution:** Implement a `mutexKV` pattern (used by Google's Terraform provider).
Serialize all operations per machine hostname. Operations on *different* machines
can safely run in parallel.

Lock granularity: `rediacc/machine/<machine-name>`. Any resource operation that
targets a specific machine acquires that machine's lock before executing.

Config-modifying operations (`machine add/delete`, `repo create/delete`) need
a separate config-level lock: `rediacc/config`. This prevents version conflicts.

**Ansible:** Not a problem — Ansible serializes tasks per host by default.
`strategy: free` parallelizes across hosts, which is safe.

### 3. Timeout Handling

**Problem:** rdc operations can take a long time:
- `config setup-machine`: 5-15 minutes (installs Docker, creates BTRFS datastore)
- `repo up`: 2-30 minutes (Docker image pulls, compose up, health checks)
- `backup push`: minutes to hours (depends on data size and network)
- `sync upload`: variable (depends on file count and size)

**Terraform solution:** Use `terraform-plugin-framework-timeouts` to let users
configure per-resource timeouts. Sensible defaults:
- `rediacc_machine` create: 20 minutes
- `rediacc_repository` create: 30 minutes
- `rediacc_backup_schedule` create: 5 minutes
- All deletes: 10 minutes

**Ansible solution:** Ansible's `async` + `poll` pattern for long-running tasks.
Modules should accept a `timeout` parameter with generous defaults.

### 4. Error Classification

The rdc error envelope includes `retryable` and `code` fields. Use these
to distinguish error types:

**Retryable** (retry with backoff):
- SSH connection refused / timeout (host briefly unreachable)
- renet not ready (Docker daemon still starting after setup)
- Temporary network issues during backup/sync

**Non-retryable** (fail immediately):
- Authentication failures (wrong SSH key, unknown host)
- Validation errors (invalid repo name, missing parameters)
- Resource conflicts (repo already exists, port in use)
- Permission denied

**Terraform:** Use `tfresource.Retry()` with the `retryable` flag from the
error envelope. Non-retryable errors propagate immediately.

**Ansible:** Report retry status in module return values. Let playbooks
decide retry behavior via `retries` + `until`.

### 5. State Detection and Drift

**The execute-then-query pattern**: Since 37 of 63 commands lack JSON output,
modules must always:
1. Query current state via JSON-capable commands
2. Execute lifecycle command (exit code only)
3. Query again to confirm the change

**Available query commands for state detection:**

| What to detect | Query command | Returns |
|----------------|--------------|---------|
| Does repo exist? | `config repositories` | Map of name → {guid, networkId} |
| Is repo running? | `machine containers` | List of containers with repository field |
| Is machine healthy? | `machine health` | Status + details |
| Machine system info | `machine info` | System, repos, containers, services |
| What services run? | `machine services` | List of systemd services |

**Drift detection (Terraform Read):** The Read function queries actual state
and compares to stored state. If a repo was deleted outside Terraform,
Read returns empty state (removes from Terraform state), and next `plan`
shows it needs recreation. If a repo was stopped manually, Read detects
the mismatch and `plan` shows it needs to be restarted.

**Key limitation:** Cannot detect all per-repo drift. If someone resizes a
repo outside Terraform, there's no per-repo size query. Accept this as a
known limitation. Note: `datastore status` returns datastore-level size/usage,
which partially closes this gap for the `rediacc_machine` resource.

### 6. Data Safety

Repositories contain user data (encrypted LUKS volumes). Destruction is
irreversible and potentially catastrophic.

- Terraform: all examples use `prevent_destroy = true`
- Terraform: `backup_before_destroy` attribute triggers backup before delete
- Ansible: `state: absent` requires explicit `force: true`
- Both: backup-before-destroy as a configurable safety net

### 7. Dry-Run Mode for Check/Plan

A useful discovery: `repo up`, `repo down`, and `repo delete` support
`--dry-run` which DOES return structured JSON. This enables:
- **Terraform plan**: can show what would change without executing
- **Ansible check mode**: can report `changed: true/false` without acting

Modules should use `--dry-run` during check/plan phases where available.

### 8. Config System Integration

Both tools reference rdc's existing config file rather than duplicating
credentials. The config has everything needed: machine IPs, SSH keys,
repo metadata, storage backends, backup schedules.

- Terraform: `config_name` provider attribute (defaults to default config)
- Ansible: `config_name` module parameter
- Ansible inventory: reads config via `rdc config show --output json`

**Encrypted configs:** When `encrypted: true`, rdc handles decryption
transparently. Ansible/Terraform don't need to know about encryption.

**Environment variable fallback** (Terraform best practice):

| HCL attribute | Env var fallback | Description |
|---------------|-----------------|-------------|
| `config_name` | `REDIACC_CONFIG_NAME` | Named config to use |
| `config_path` | `REDIACC_CONFIG_PATH` | Explicit config file path |
| `rdc_path` | `REDIACC_RDC_PATH` | Path to rdc binary |

Evaluation order: HCL attribute → environment variable → default.
This follows the pattern used by AWS (`AWS_PROFILE`), Hetzner
(`HCLOUD_TOKEN`), and Cloudflare (`CLOUDFLARE_API_TOKEN`) providers.
Keeps `.tf` files credential-free and portable across environments.

### 9. Ceph Fork as Core Differentiator

The `datastore fork` command enables instant copy-on-write cloning of entire
datastores (all repos, all data) in under 2 seconds via Ceph RBD snapshots.
This is the infrastructure equivalent of what PlanetScale/Neon do for databases
and what Vercel/Render do for preview deployments — but for entire encrypted
application stacks.

**Patterns this enables:**

| Pattern | Description | Industry equivalent |
|---------|-------------|-------------------|
| Preview environments | Fork production → deploy PR branch → test → unfork | Vercel preview deploys |
| Canary release | Fork → deploy new version → validate → promote or discard | Netflix canary |
| Nightly DR validation | Fork → run DR playbook → verify recovery → unfork | Chaos engineering |
| Time-travel debugging | Fork at incident → attach debuggers → investigate → unfork | Neon branching |
| Ephemeral test environments | Fork → integration tests with real data → unfork | PlanetScale branches |

**Design implications:**

- **Ansible** owns fork workflows — fork/unfork is procedural (do X, then Y, then cleanup).
  New module: `rediacc_datastore_fork`. New roles: `fork_environment`, preview/canary patterns.
- **Terraform** manages fork *lifecycle* — `rediacc_datastore_fork` as a managed resource
  where Create=fork, Read=`datastore status` (check `cow_mode`), Delete=unfork.
  Fork metadata (snapshot name, clone name) stored as computed attributes in state.
- **Ceph is optional** — all existing functionality works with local backend.
  Ceph adds the instant fork capability for users who need it.
- **Machine resource extended** — `rediacc_machine` gains an optional `ceph {}` block
  for Ceph RBD configuration. When present, `config set-ceph` + `datastore init --backend ceph`
  run during machine setup.

**Two datastore backends:**

| Backend | Storage | Fork speed | Use case |
|---------|---------|------------|----------|
| `local` (default) | Loop-backed file | Slow (rsync) | Single machines, no Ceph |
| `ceph` | RBD image on Ceph cluster | Instant (< 2s) | Multi-machine, testing, staging |

The `datastore status` command returns JSON (plain, no envelope) with: `type`,
`size`, `used`, `available`, `path`, `mounted`, `initialized`, `backend`,
`rbd_image`. During an active fork, `cow_mode: true` is added.

## Progressive Adoption Strategy

### The Natural Path: Manual → CLI → Terraform/Ansible

Most users already run `rdc` manually. The tools should meet them where
they are, not require a greenfield setup. The adoption path:

1. **Already using rdc manually** — import existing machines and repos
   into Terraform state without recreating them. This is the #1 adoption
   barrier for IaC tools (learned from Dokku/Coolify/Proxmox providers).

2. **Start with Terraform for new machines** — provision cloud VMs and
   register them with `rediacc_machine`. Keep managing repos via `rdc`
   directly. This is the "Kamal model" (TF for infrastructure, CLI for apps).

3. **Add repos to Terraform as needed** — import existing repos one at a
   time with `terraform import`. Don't require all-or-nothing migration.

4. **Add Ansible for fleet operations** — when managing 5+ machines,
   Ansible adds value for rolling deploys and health gates. Terraform
   handles what exists; Ansible handles what happens.

5. **Add Ceph for instant operations** — when fork speed matters
   (staging environments, preview deployments, DR testing, canary releases),
   provision a Ceph cluster and switch machines to Ceph-backed datastores.
   Forks go from minutes (rsync) to seconds (Ceph COW). This unlocks the
   preview environment and canary release patterns that no other self-hosted
   tool can offer.

### Import as a Day-One Feature

Import is NOT a nice-to-have — it's the #1 barrier to adoption. Every
resource must support `terraform import` from v0.1.0. Without it, users
with existing infrastructure can't adopt the provider without destroying
and recreating everything (unacceptable for production repos with data).

Import formats:
- `terraform import rediacc_machine.web web-1`
- `terraform import rediacc_repository.app "my-app:server-1"`
- `terraform import rediacc_backup_schedule.daily "server-1"`

Terraform 1.5+ import blocks (no CLI required):
```hcl
import {
  to = rediacc_machine.web
  id = "web-1"
}

import {
  to = rediacc_repository.app
  id = "my-app:server-1"
}
```

### Minimum Viable Configuration

First-time users should be able to start with 3 lines:

```hcl
provider "rediacc" {}  # Uses default config, rdc on PATH

resource "rediacc_machine" "web" {
  name = "web-1"
  ip   = "10.0.0.1"
  user = "root"
}
```

No API keys, no endpoints, no complex setup. The provider reads the
existing rdc config file that users already have.

### Versioning: Start at 0.x

Publish 0.1.0 early, iterate with user feedback. Semantic versioning
below 1.0 allows breaking changes. The Dokku provider stayed at 0.x
for months and iterated based on real user issues. Don't wait for
perfection — ship a working provider with import + machine + repository
and gather feedback.

## Repository Structure (New Packages)

```
packages/
├── ansible/                          # NEW: Ansible collection
│   └── rediacc/console/              # namespace.collection
│       ├── galaxy.yml
│       ├── meta/runtime.yml
│       ├── plugins/modules/          # Python modules
│       ├── plugins/inventory/        # Dynamic inventory plugin
│       ├── plugins/doc_fragments/    # Shared DOCUMENTATION strings
│       ├── plugins/module_utils/     # Shared utilities
│       ├── roles/                    # Reusable roles
│       ├── playbooks/               # Example playbooks
│       └── tests/                   # Molecule + integration tests
│
├── terraform/                        # NEW: Terraform provider
│   └── terraform-provider-rediacc/   # Go module
│       ├── main.go
│       ├── go.mod
│       ├── internal/
│       │   ├── provider/             # Provider + resources + data sources
│       │   └── client/               # rdc CLI wrapper in Go
│       ├── examples/                 # Example .tf files
│       └── tests/                    # Acceptance tests
```
