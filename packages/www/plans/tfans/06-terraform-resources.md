# Phase 2b: Terraform Resource and Data Source Specifications

## Design Principles

1. **Query commands for state, lifecycle commands for mutations.** Never parse
   lifecycle command stdout — only check exit codes. Use separate query commands
   to verify state changes.

2. **Per-machine locking.** Every resource targets a machine. Acquire the machine
   mutex before any rdc operation. Config-modifying operations also acquire the
   config mutex. See `05-terraform-provider.md` concurrency design.

3. **Dry-run for plan.** `repo up/down/delete --dry-run` returns JSON — use this
   during `terraform plan` to show what would change without side effects.

4. **Machine CRUD commands have JSON support.** The `machine add/delete/rename`
   commands use `createResourceCommands()` factory which calls `outputService.print()`.
   This means machine Create/Delete can parse structured responses directly,
   unlike repo lifecycle commands which need execute-then-query.

5. **Design for `for_each`, not just `count`.** Resources use string identifiers
   so they work naturally with `for_each` maps. This prevents the index-shifting
   problem that plagues `count`-based resources when items are removed from the
   middle of a list.

6. **Import is day-one.** Every resource supports `ImportState` from v0.1.0.
   Users with existing rdc setups can adopt Terraform without recreating
   infrastructure. This is the #1 adoption barrier (see `00-overview.md`).

7. **Minimize required attributes.** Only require what's truly necessary for
   Create. Everything else is optional with sensible defaults. This keeps the
   minimum viable configuration small (3-line resource blocks).

8. **Avoid phantom diffs.** Never store computed values that change between
   reads (timestamps, dynamic IDs) as plan-visible attributes. Use `UseStateForUnknown`
   plan modifiers for computed attributes that are stable after creation.

9. **Attribute-path diagnostics.** Error messages should reference the specific
   attribute that caused the failure, not just "rdc command failed".

## Resources (Managed, CRUD Lifecycle)

### Resource 1: `rediacc_machine`

**Purpose**: Register a machine in the rdc config and optionally set it up.

**Wraps**: `rdc config add-machine`, `rdc config setup-machine`, `rdc config remove-machine`

```hcl
resource "rediacc_machine" "web" {
  name      = "web-1"
  ip        = "10.0.0.5"
  user      = "deploy"
  port      = 22
  datastore = "/mnt/rediacc"

  setup          = true          # Run setup-machine after registration
  datastore_size = "95%"         # For setup
}

# Using Terraform cloud provider outputs
resource "rediacc_machine" "from_hetzner" {
  name = "hetzner-1"
  ip   = hcloud_server.web.ipv4_address
  user = "root"

  setup = true
}
```

**Schema**:

| Attribute | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `name` | string | yes | - | Machine name (identifier) |
| `ip` | string | yes | - | IP address or hostname |
| `user` | string | yes | - | SSH username |
| `port` | number | no | 22 | SSH port |
| `datastore` | string | no | `/mnt/rediacc` | Datastore path |
| `setup` | bool | no | false | Run setup-machine after registration |
| `datastore_size` | string | no | `95%` | Size for BTRFS datastore |

**Computed Attributes**:

| Attribute | Type | Description |
|-----------|------|-------------|
| `id` | string | Machine name |
| `known_hosts` | string | SSH host key fingerprint |

**CRUD Implementation**:

```
Create:  (acquire config mutex + machine mutex)
  1. rdc machine add <name> --ip <ip> --user <user> [--port <port>] [--datastore <path>]
     → Returns JSON (factory command) — can parse response directly
  2. if setup: rdc config setup-machine <name> [--datastore-size <size>]
     → Lifecycle command (exit code only). Timeout: 20 minutes.

Read:
  1. rdc config show --output json → extract machines[name]
  2. Compare stored attributes (ip, user, port, datastore) with config values
  Note: setup status is not queryable — treat as write-only attribute

Update:
  - ip/user/port/datastore changed: remove + re-add (acquire config mutex)
  - setup changed false→true: run setup-machine (acquire machine mutex)
  - setup changed true→false: no-op (can't un-setup a machine)

Delete:  (acquire config mutex)
  1. rdc machine delete <name> → Returns JSON (factory command)

Import:
  terraform import rediacc_machine.web web-1
  → Read machine config from config show, populate ip/user/port/datastore
```

**Concurrency note:** Creating/deleting machines modifies the config file.
Must hold config mutex to prevent version conflicts with other machine or
repo operations that also write config.

---

### Resource 2: `rediacc_repository`

**Purpose**: Manage repository lifecycle (create, deploy, stop, delete).

**Wraps**: `rdc repo create`, `rdc repo up`, `rdc repo down`, `rdc repo delete`

```hcl
# Basic repository
resource "rediacc_repository" "app" {
  name    = "my-app"
  machine = rediacc_machine.web.name
  size    = "5G"
  deploy  = true

  lifecycle {
    prevent_destroy = true
  }
}

# Repository with sync source
resource "rediacc_repository" "app_with_sync" {
  name    = "my-app"
  machine = rediacc_machine.web.name
  size    = "10G"
  deploy  = true

  source_dir = "./my-app/"           # Local directory to sync
  sync_verify = true                  # Checksum-based change detection
  sync_mirror = false                 # Don't delete remote files

  autostart = true
}

# Repository with backup-before-destroy safety
resource "rediacc_repository" "important_data" {
  name    = "database"
  machine = rediacc_machine.web.name
  size    = "100G"
  deploy  = true
  mount   = true

  backup_before_destroy = true
  backup_storage        = "s3-backups"

  lifecycle {
    prevent_destroy = true
  }
}

# Fork from existing repo
resource "rediacc_repository" "test_copy" {
  name        = "my-app-test"
  machine     = rediacc_machine.web.name
  fork_from   = rediacc_repository.app.name
  deploy      = true
  mount       = true
  grand       = rediacc_repository.app.name
}
```

**Schema**:

| Attribute | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `name` | string | yes | - | Repository name |
| `machine` | string | yes | - | Target machine (must exist) |
| `size` | string | conditional | - | Required for new repos. E.g., `5G`, `1T` |
| `deploy` | bool | no | false | Run `repo up` after create |
| `mount` | bool | no | false | Mount volume before deploy |
| `checkpoint` | bool | no | false | CRIU checkpoint restore |
| `prep_only` | bool | no | false | Only run prep(), skip up() |
| `grand` | string | no | - | Parent repo for fork credentials |
| `fork_from` | string | no | - | Fork from this repo instead of creating fresh |
| `source_dir` | string | no | - | Local dir to sync before deploy |
| `sync_verify` | bool | no | false | Checksum-based sync |
| `sync_mirror` | bool | no | false | Mirror mode (delete remote extras) |
| `autostart` | bool | no | false | Enable autostart |
| `backup_before_destroy` | bool | no | false | Backup to storage before delete |
| `backup_storage` | string | no | - | Storage name for backup-before-destroy |

**Computed Attributes**:

| Attribute | Type | Description |
|-----------|------|-------------|
| `id` | string | `<name>:<machine>` |
| `guid` | string | Repository UUID |
| `network_id` | number | Docker network isolation ID |

**CRUD Implementation**:

All repo operations use the execute-then-query pattern because repo lifecycle
commands lack JSON output. Every operation acquires the machine mutex AND
config mutex (repo create/delete modify config).

```
Create:  (acquire config mutex + machine mutex, timeout: 30 min)
  1. Query: config repositories → does repo already exist?
  2. Execute: rdc repo create <name> -m <machine> --size <size>  (exit code)
  3. Verify: config repositories → confirm guid/networkId populated
  4. if source_dir: rdc sync upload (exit code)
  5. if deploy: rdc repo up (exit code, timeout: up to 30 min for Docker pulls)
  6. Verify: machine containers → confirm running state
  7. if autostart: rdc repo autostart enable (exit code)

  Fork variant:
  1. rdc repo fork <fork_from> -m <machine> --tag <name>  (exit code)
  2-7. Same verify + optional deploy steps

Read:
  1. config repositories → check repo exists, get guid/networkId
  2. machine containers → filter by repository name, check running state
  3. If repo gone from config: set ID to "" (Terraform marks for recreation)
  4. If repo exists but stopped when deploy=true: plan shows drift

  DO NOT use `rdc repo status` — it pipes renet's raw stdout (no JSON).

Update:  (acquire machine mutex, timeout: 30 min)
  - size increased + deployed: rdc repo expand (online, zero downtime)
  - size increased + stopped: rdc repo resize (offline)
  - size decreased: ForceNew — Terraform destroys and recreates
  - source_dir changed: sync upload → repo up (redeploy)
  - deploy false→true: repo up
  - deploy true→false: repo down
  - autostart changed: autostart enable/disable

Delete:  (acquire config mutex + machine mutex, timeout: 15 min)
  1. if backup_before_destroy: rdc backup push --to <storage>
  2. rdc repo down --unmount  (exit code)
  3. rdc repo delete  (exit code)
  4. Verify: config repositories → confirm removed

Import:
  terraform import rediacc_repository.app "my-app:server-1"
  → Parse name:machine from ID
  → Read config repositories for guid/networkId
  → Read machine containers for running state
  → Cannot import: size, source_dir, autostart (not queryable)
```

**Planning with dry-run:** During `terraform plan`, the provider can use
`rdc repo up --dry-run` / `rdc repo delete --dry-run` to get structured
JSON showing what would happen without executing. This improves plan output.

**Known drift detection gaps (v1.0):**
- Volume size is not queryable — can't detect external resize
- Autostart state is not queryable — can't detect external changes
- Sync content is not comparable — can't detect external file changes

These are accepted limitations. Future rdc CLI improvements (JSON for
`autostart list`, `repo status`) will close these gaps.

---

### Resource 3: `rediacc_backup_schedule`

**Purpose**: Configure and push backup schedule to a machine.

**Wraps**: `rdc backup schedule set`, `rdc backup schedule push`

```hcl
resource "rediacc_backup_schedule" "daily" {
  machine     = rediacc_machine.web.name
  storage     = "s3-backups"
  cron        = "0 2 * * *"    # Daily at 2 AM
  enabled     = true
}
```

**Schema**:

| Attribute | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `machine` | string | yes | - | Machine to push schedule to |
| `storage` | string | yes | - | Storage name for backups |
| `cron` | string | yes | - | Cron expression |
| `enabled` | bool | no | true | Enable/disable schedule |

**CRUD**:

```
Create:
  1. rdc backup schedule set --destination <storage> --cron <cron> --enable
  2. rdc backup schedule push <machine>

Read:
  1. rdc backup schedule show --output json

Update:
  1. rdc backup schedule set --destination/--cron/--enable/--disable
  2. rdc backup schedule push <machine>

Delete:
  1. rdc backup schedule set --disable
  2. rdc backup schedule push <machine>  (pushes disabled state)
```

---

### Resource 4: `rediacc_infra`

**Purpose**: Configure and push Traefik reverse proxy to a machine.

**Wraps**: `rdc config set-infra`, `rdc config push-infra`

```hcl
resource "rediacc_infra" "web" {
  machine = rediacc_machine.web.name
  domain  = "example.com"
  email   = "admin@example.com"
}
```

**Schema**:

| Attribute | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `machine` | string | yes | - | Target machine |
| `domain` | string | yes | - | Domain for HTTPS |
| `email` | string | yes | - | Email for Let's Encrypt |

---

## Data Sources (Read-Only)

### Data Source 1: `rediacc_machines`

```hcl
data "rediacc_machines" "all" {}

output "machine_ips" {
  value = { for name, m in data.rediacc_machines.all.machines : name => m.ip }
}
```

**Wraps**: `rdc config machines --output json`

**Schema**:

| Attribute | Type | Description |
|-----------|------|-------------|
| `machines` | map(object) | All registered machines: name → {ip, user, port, datastore} |

---

### Data Source 2: `rediacc_containers`

```hcl
data "rediacc_containers" "web" {
  machine = "server-1"
}

output "running_containers" {
  value = [for c in data.rediacc_containers.web.containers : c.name if c.state == "running"]
}
```

**Wraps**: `rdc machine containers <machine> --output json`

**Schema**:

| Attribute | Type | Description |
|-----------|------|-------------|
| `machine` | string (required) | Machine name |
| `containers` | list(object) | Containers: name, status, state, health, cpu, memory, repository |

---

### Data Source 3: `rediacc_repositories`

```hcl
data "rediacc_repositories" "all" {}

output "repos" {
  value = data.rediacc_repositories.all.repositories
}
```

**Wraps**: `rdc config repositories --output json`

**Schema**:

| Attribute | Type | Description |
|-----------|------|-------------|
| `repositories` | map(object) | All repos: name → {guid, networkId} |

---

### Data Source 4: `rediacc_health`

```hcl
data "rediacc_health" "web" {
  machine = rediacc_machine.web.name
}

output "is_healthy" {
  value = data.rediacc_health.web.status == "healthy"
}
```

**Wraps**: `rdc machine health <machine> --output json`

**Schema**:

| Attribute | Type | Description |
|-----------|------|-------------|
| `machine` | string (required) | Machine name |
| `status` | string | Overall health status |

---

## Complete Example (using `for_each`)

Using `for_each` instead of `count` prevents the index-shifting problem:
removing a machine from the middle of a list doesn't force-replace all
subsequent resources.

```hcl
terraform {
  required_providers {
    hcloud = {
      source  = "hetznercloud/hcloud"
      version = "~> 1.45"
    }
    rediacc = {
      source  = "rediacc/rediacc"
      version = "~> 0.1"
    }
  }
}

variable "workers" {
  default = {
    "worker-1" = { type = "cx31", location = "fsn1" }
    "worker-2" = { type = "cx31", location = "fsn1" }
    "worker-3" = { type = "cx31", location = "nbg1" }
  }
}

# 1. Provision VMs on Hetzner
resource "hcloud_server" "worker" {
  for_each    = var.workers
  name        = each.key
  server_type = each.value.type
  image       = "ubuntu-24.04"
  ssh_keys    = [hcloud_ssh_key.deploy.id]
  location    = each.value.location
}

# 2. Register machines in rdc
resource "rediacc_machine" "worker" {
  for_each = var.workers
  name     = each.key
  ip       = hcloud_server.worker[each.key].ipv4_address
  user     = "root"
  setup    = true
}

# 3. Deploy application to all machines
resource "rediacc_repository" "app" {
  for_each = var.workers
  name     = "my-app"
  machine  = rediacc_machine.worker[each.key].name
  size     = "10G"
  deploy   = true

  source_dir  = "./my-app/"
  sync_verify = true
  autostart   = true

  backup_before_destroy = true
  backup_storage        = "s3-backups"

  lifecycle {
    prevent_destroy = true
  }
}

# 4. Setup backup schedules
resource "rediacc_backup_schedule" "daily" {
  for_each = var.workers
  machine  = rediacc_machine.worker[each.key].name
  storage  = "s3-backups"
  cron     = "0 2 * * *"
}

# 5. Health check data source
data "rediacc_health" "workers" {
  for_each = var.workers
  machine  = rediacc_machine.worker[each.key].name

  depends_on = [rediacc_repository.app]
}

output "worker_health" {
  value = { for name, h in data.rediacc_health.workers : name => h.status }
}
```

## Import Workflow (Existing Infrastructure)

For users with existing rdc setups, import blocks (Terraform 1.5+) let them
adopt Terraform without recreating anything:

```hcl
# Import existing machines — no rdc commands run, just reads current state
import {
  to = rediacc_machine.web
  id = "web-1"
}

import {
  to = rediacc_machine.db
  id = "db-1"
}

# Import existing repos
import {
  to = rediacc_repository.app
  id = "my-app:web-1"
}

import {
  to = rediacc_repository.postgres
  id = "postgres:db-1"
}

# After import, define the matching resources
resource "rediacc_machine" "web" {
  name  = "web-1"
  ip    = "10.0.0.1"
  user  = "deploy"
  setup = true
}

resource "rediacc_repository" "app" {
  name    = "my-app"
  machine = rediacc_machine.web.name
  size    = "10G"
  deploy  = true

  lifecycle { prevent_destroy = true }
}
```

Run `terraform plan` after import to verify no drift. If plan shows changes,
adjust the resource config to match actual state before applying.

## Go Client: Envelope Handling

The Go client (`internal/client/rdc.go`) must handle the JSON envelope:

```go
// Envelope represents the rdc JSON output format for query commands.
type Envelope struct {
    Success  bool            `json:"success"`
    Command  string          `json:"command"`
    Data     json.RawMessage `json:"data"`
    Errors   json.RawMessage `json:"errors"`
    Warnings []string        `json:"warnings"`
    Metrics  json.RawMessage `json:"metrics"`
}

func (c *RdcClient) RunQuery(ctx context.Context, args ...string) (json.RawMessage, error) {
    raw, err := c.Run(ctx, args...)
    if err != nil {
        return nil, err
    }
    if raw == nil {
        return nil, nil
    }

    // Try to unwrap envelope
    var env Envelope
    if err := json.Unmarshal(raw, &env); err == nil && env.Data != nil {
        return env.Data, nil
    }

    // No envelope — return raw
    return raw, nil
}

func (c *RdcClient) RunLifecycle(ctx context.Context, args ...string) error {
    // Lifecycle commands: skip --output json, only check exit code
    cmdArgs := []string{}
    if c.ConfigName != "" {
        cmdArgs = append(cmdArgs, "--config", c.ConfigName)
    }
    cmdArgs = append(cmdArgs, args...)

    cmd := exec.CommandContext(ctx, c.BinaryPath, cmdArgs...)
    var stderr bytes.Buffer
    cmd.Stderr = &stderr

    if err := cmd.Run(); err != nil {
        return fmt.Errorf("rdc %v failed: %s\n%s", args, err, stderr.String())
    }
    return nil
}
```

## Implementation Priority

| Priority | Resource/Data Source | Effort | Notes |
|----------|---------------------|--------|-------|
| 1 | Provider + client | Medium | Foundation — must be first |
| 2 | `rediacc_machine` | Medium | Core — everything depends on it |
| 3 | `rediacc_repository` | High | Most complex — sync, deploy, fork, backup-before-destroy |
| 4 | `data.rediacc_machines` | Low | Simple JSON read |
| 5 | `data.rediacc_repositories` | Low | Simple JSON read |
| 6 | `data.rediacc_containers` | Low | Simple JSON read |
| 7 | `data.rediacc_health` | Low | Simple JSON read |
| 8 | `rediacc_backup_schedule` | Medium | Schedule set + push |
| 9 | `rediacc_infra` | Low | Set-infra + push-infra |
