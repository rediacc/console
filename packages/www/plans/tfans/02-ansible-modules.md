# Phase 1b: Ansible Module Specifications

Each module follows the CLI-wrapper pattern: build args → call `rdc` → parse
JSON output → report changed state. All modules use the shared `rdc_runner.py`
utility (see `01-ansible-collection.md`).

## Design Conventions (Ansible Best Practices)

### 1. Use `state` for Desired State, Not `action`

All modules that manage resource state use a `state` parameter with standard
values: `present`, `absent`, `started`, `stopped`. This is the universal
Ansible convention (see `community.docker.docker_container`, `ansible.builtin.service`).

**Exception:** Pure action modules (sync, backup push/pull) where there is no
idempotent target state. These use `direction` (upload/download, push/pull).

### 2. Separate `_info` Modules for Read-Only Operations

Read-only queries belong in dedicated `_info` modules, not mixed into
mutation modules. This follows the `community.docker` pattern:
- `docker_container` → manages state
- `docker_container_info` → reads state

Our split:
- `rediacc_machine` → manages registration/setup
- `rediacc_machine_info` → reads info/health/containers
- `rediacc_backup_info` → lists available backups (not mixed into `rediacc_backup`)

### 3. Argument Validation via `argument_spec`

Use `mutually_exclusive`, `required_if`, and `required_together` in
`argument_spec` — don't validate in module code. Ansible validates
before the module runs and produces standard error messages.

```python
module = AnsibleModule(
    argument_spec=dict(
        state=dict(choices=['present', 'started', 'stopped', 'absent', 'forked', 'resized', 'expanded']),
        size=dict(type='str'),
        fork_tag=dict(type='str'),
        force=dict(type='bool', default=False),
    ),
    required_if=[
        ('state', 'present', ['size']),
        ('state', 'resized', ['size']),
        ('state', 'expanded', ['size']),
        ('state', 'forked', ['fork_tag']),
        ('state', 'absent', ['force'], True),  # True = must be truthy
    ],
    mutually_exclusive=[
        ('fork_tag', 'size'),  # Fork doesn't need size
    ],
    supports_check_mode=True,
)
```

### 4. Check Mode Mapped to `--dry-run`

`repo up`, `repo down`, and `repo delete` support `--dry-run` which returns
structured JSON. Modules map Ansible check mode to this:
- **Check mode:** run with `--dry-run`, parse response, report `changed: true/false`
- **Normal mode:** run without `--dry-run`, verify via post-query

Modules that lack dry-run support simulate check mode by querying current
state and comparing to desired state without executing.

### 5. Diff Mode Support

When `_diff=True`, modules return `before` and `after` dicts showing what
changed. This makes `ansible-playbook --diff` useful:

```python
if module._diff:
    result['diff'] = {
        'before': {'state': 'stopped', 'name': repo_name},
        'after': {'state': 'started', 'name': repo_name},
    }
```

### 6. DOCUMENTATION/EXAMPLES/RETURN Strings

Every module MUST include `DOCUMENTATION`, `EXAMPLES`, and `RETURN` module-level
docstrings. These are required by `ansible-doc`, Ansible Galaxy, and `ansible-lint`.
They are the module's public API documentation.

### 7. Execute-Then-Query Pattern

Of 63 rdc commands, only 26 return structured JSON. All repo lifecycle commands
(`create`, `up`, `down`, `delete`, `fork`, `resize`, `expand`) return human-only
messages. Modules must:

1. **Query** current state via JSON-capable command (`config repositories`, `machine containers`)
2. **Execute** lifecycle command — only check exit code (0=success)
3. **Query again** to confirm state changed

The runner provides `run()` for queries and `run_lifecycle()` for mutations.

### 8. Error Handling

The rdc error envelope includes `retryable`, `code`, and `guidance` fields.
Modules should surface `guidance` in failure messages. For retryable errors,
modules set `result['retryable'] = True` so playbooks can use `retries` + `until`.

### 9. Return Values

All modules return structured data (not raw stdout). Minimum return values:

| Key | Type | Description |
|-----|------|-------------|
| `changed` | bool | Whether state was modified |
| `<resource>` | dict | Resource state after operation |
| `diff` | dict | Before/after (when `_diff=True`) |
| `retryable` | bool | Whether failure is transient (on error only) |

## Module 1: `rediacc_repo`

**Purpose**: Full repository lifecycle (create, deploy, stop, delete, fork, resize, expand).

**Wraps**: `rdc repo create|up|down|delete|fork|resize|expand`

```yaml
# Create + deploy a repository
- name: Deploy my-app
  rediacc.console.rediacc_repo:
    name: my-app
    machine: server-1
    state: started
    size: 5G

# Stop a repository
- name: Stop my-app
  rediacc.console.rediacc_repo:
    name: my-app
    machine: server-1
    state: stopped
    unmount: true

# Delete a repository (requires force)
- name: Remove my-app
  rediacc.console.rediacc_repo:
    name: my-app
    machine: server-1
    state: absent
    force: true

# Fork a repository
- name: Fork my-app for testing
  rediacc.console.rediacc_repo:
    name: my-app
    machine: server-1
    state: forked
    fork_tag: my-app-test

# Resize (offline)
- name: Resize my-app
  rediacc.console.rediacc_repo:
    name: my-app
    machine: server-1
    state: resized
    size: 20G

# Expand (online, zero downtime)
- name: Expand my-app
  rediacc.console.rediacc_repo:
    name: my-app
    machine: server-1
    state: expanded
    size: 20G
```

**Parameters**:

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `name` | str | yes | - | Repository name |
| `machine` | str | yes | - | Target machine name |
| `state` | str | yes | - | `present`, `started`, `stopped`, `absent`, `forked`, `resized`, `expanded` |
| `size` | str | conditional | - | Required for `present`, `resized`, `expanded`. E.g., `5G`, `100G`, `1T` |
| `mount` | bool | no | false | Mount volume before deploy |
| `checkpoint` | bool | no | false | Restore CRIU checkpoint |
| `grand` | str | no | - | Parent repo name for fork credential inheritance |
| `unmount` | bool | no | false | Unmount volume on stop |
| `fork_tag` | str | conditional | - | Required for `state: forked`. Name for the fork |
| `force` | bool | no | false | Required for `state: absent` |
| `rdc_binary` | str | no | auto | Path to rdc binary |
| `config_name` | str | no | default | Named config to use |
| `debug` | bool | no | false | Verbose output |

**Return Values**:

| Key | Type | Description |
|-----|------|-------------|
| `changed` | bool | Whether state was modified |
| `repository` | dict | Repository config (guid, networkId, etc.) |
| `stdout` | str | Raw rdc output |
| `cmd` | str | Command that was executed |

**Idempotency Logic**:

```
state: present
  → Check: `rdc config repositories --output json` → exists?
  → If yes: changed=false
  → If no: `rdc repo create` → changed=true

state: started
  → Check: `rdc machine containers --output json` → filter by repo name → running?
  → If yes: changed=false
  → If no:
    → If repo doesn't exist: create first, then up → changed=true
    → If repo exists but stopped: `rdc repo up` → changed=true
  Note: DO NOT use `rdc repo status` — it pipes renet's raw stdout (no JSON).
  Use `machine containers` filtered by repository name instead.

state: stopped
  → Check: `rdc machine containers --output json` → filter by repo name → running?
  → If not running: changed=false
  → If running: `rdc repo down` → changed=true

state: absent
  → Check: `rdc config repositories --output json` → exists?
  → If no: changed=false
  → If yes: `rdc repo delete` → changed=true
```

**Check Mode**: For `started`/`stopped`/`absent`, uses `--dry-run` which returns
structured JSON showing what would change. For `present`, queries state only.
Reports `changed: true/false` without executing.

**Diff Mode**: When `_diff=True`, returns `before` and `after` state dicts.

---

## Module 2: `rediacc_sync`

**Purpose**: File sync between local filesystem and remote repository.

**Wraps**: `rdc sync upload|download|status`

```yaml
# Upload app files
- name: Upload application code
  rediacc.console.rediacc_sync:
    machine: server-1
    repository: my-app
    direction: upload
    local_path: ./my-app/
    verify: true

# Download database dumps
- name: Download backups
  rediacc.console.rediacc_sync:
    machine: server-1
    repository: my-app
    direction: download
    local_path: ./backups/
    remote_path: data/dumps

# Mirror mode (delete remote files not in local)
- name: Mirror deploy directory
  rediacc.console.rediacc_sync:
    machine: server-1
    repository: my-app
    direction: upload
    local_path: ./deploy/
    mirror: true
    verify: true
```

**Parameters**:

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `machine` | str | yes | - | Target machine |
| `repository` | str | yes | - | Repository name |
| `direction` | str | yes | - | `upload` or `download` |
| `local_path` | str | no | `.` | Local directory path |
| `remote_path` | str | no | - | Subdirectory within repo |
| `mirror` | bool | no | false | Delete files not in source |
| `verify` | bool | no | false | Checksum-based change detection |
| `exclude` | list | no | [] | Glob patterns to exclude |
| `dry_run` | bool | no | false | Preview without transfer |

**Idempotency**: Always reports `changed=true` on upload/download (rsync determines actual changes). Use `dry_run: true` + register to check first.

---

## Module 3: `rediacc_backup`

**Purpose**: Backup push/pull between machines or to/from storage.

**Wraps**: `rdc repo backup push|pull`

**Design note:** The `list` functionality is in `rediacc_backup_info` (separate
read-only module, following Ansible `_info` convention).

```yaml
# Push to another machine
- name: Backup my-app to standby
  rediacc.console.rediacc_backup:
    repository: my-app
    machine: server-1
    direction: push
    to_machine: standby-1
    checkpoint: true

# Push to S3 storage
- name: Backup to S3
  rediacc.console.rediacc_backup:
    repository: my-app
    machine: server-1
    direction: push
    to_storage: s3-backups

# Pull from another machine
- name: Pull backup from source
  rediacc.console.rediacc_backup:
    repository: my-app
    machine: standby-1
    direction: pull
    from_machine: server-1
```

**Parameters**:

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `repository` | str | yes | - | Repository name |
| `machine` | str | yes | - | Primary machine |
| `direction` | str | yes | - | `push` or `pull` |
| `to_machine` | str | no | - | Target machine for push |
| `to_storage` | str | no | - | Storage name for push |
| `from_machine` | str | no | - | Source machine for pull |
| `from_storage` | str | no | - | Storage name for pull |
| `checkpoint` | bool | no | false | CRIU checkpoint (live migration) |
| `force` | bool | no | false | Overwrite existing backup |
| `tag` | str | no | - | Backup tag identifier |

**Argument validation:**
```python
required_if=[
    ('direction', 'push', ['to_machine', 'to_storage'], True),  # One of these required
    ('direction', 'pull', ['from_machine', 'from_storage'], True),
],
mutually_exclusive=[
    ('to_machine', 'to_storage'),
    ('from_machine', 'from_storage'),
],
```

---

## Module 3b: `rediacc_backup_info`

**Purpose**: List available backups (read-only, no changes).

**Wraps**: `rdc repo backup list`

```yaml
# List backups from a machine
- name: List available backups
  rediacc.console.rediacc_backup_info:
    machine: server-1
  register: backup_list

# List backups from storage
- name: List backups in S3
  rediacc.console.rediacc_backup_info:
    storage: s3-backups
  register: storage_backups
```

**Parameters**:

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `machine` | str | no | - | List backups on this machine |
| `storage` | str | no | - | List backups in this storage |

**Returns**: `backup_list.json` — list of backup entries (unwrapped from JSON envelope).

---

## Module 4: `rediacc_backup_sync`

**Purpose**: Bulk backup sync of all repos on a machine to/from storage.

**Wraps**: `rdc repo backup sync push|pull`

```yaml
# Push all repos to S3
- name: Sync all repos to backup storage
  rediacc.console.rediacc_backup_sync:
    machine: server-1
    direction: push
    storage: s3-backups

# Push specific repos only
- name: Sync critical repos to backup storage
  rediacc.console.rediacc_backup_sync:
    machine: server-1
    direction: push
    storage: s3-backups
    repos:
      - my-app
      - database

# Pull from storage (disaster recovery)
- name: Pull all backups from S3
  rediacc.console.rediacc_backup_sync:
    machine: server-1
    direction: pull
    storage: s3-backups
    override: true
```

**Parameters**:

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `machine` | str | yes | - | Target machine |
| `direction` | str | yes | - | `push` or `pull` |
| `storage` | str | yes | - | Storage name |
| `repos` | list | no | all | Filter to specific repos |
| `override` | bool | no | false | Overwrite on pull |

**Design note:** Uses `direction` (not `state`) because this is a one-shot
sync action with no idempotent target state.

---

## Module 5: `rediacc_backup_schedule`

**Purpose**: Configure and push backup schedules to machines.

**Wraps**: `rdc repo backup schedule set|show|push`

```yaml
# Configure and push schedule (desired state: present + pushed)
- name: Set daily backup schedule
  rediacc.console.rediacc_backup_schedule:
    state: present
    destination: s3-backups
    cron: "0 2 * * *"
    enabled: true
    machine: server-1    # Also push to machine

# Just configure without pushing
- name: Configure schedule only
  rediacc.console.rediacc_backup_schedule:
    state: present
    destination: s3-backups
    cron: "0 2 * * *"

# Disable schedule
- name: Disable backup schedule
  rediacc.console.rediacc_backup_schedule:
    state: absent
    machine: server-1    # Push disabled state to machine
```

**Parameters**:

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `state` | str | yes | - | `present` or `absent` |
| `destination` | str | conditional | - | Required for `present`. Storage name. |
| `cron` | str | conditional | - | Required for `present`. Cron expression. |
| `enabled` | bool | no | true | Enable/disable schedule |
| `machine` | str | no | - | Push schedule to this machine after set |

**Argument validation:**
```python
required_if=[
    ('state', 'present', ['destination', 'cron']),
],
```

---

## Module 6: `rediacc_snapshot`

**Purpose**: BTRFS point-in-time snapshots.

**Wraps**: `rdc snapshot create|list|delete`

```yaml
# Create snapshot before update
- name: Snapshot before deploy
  rediacc.console.rediacc_snapshot:
    repository: my-app
    machine: server-1
    state: present
  register: snapshot

# Delete old snapshot
- name: Delete old snapshot
  rediacc.console.rediacc_snapshot:
    repository: my-app
    machine: server-1
    state: absent
    snapshot_name: "{{ snapshot.name }}"

# List snapshots (read-only — separate _info module)
- name: List snapshots
  rediacc.console.rediacc_snapshot_info:
    repository: my-app
    machine: server-1
  register: snapshots
```

---

## Module 7: `rediacc_machine`

**Purpose**: Machine registration and setup.

**Wraps**: `rdc config add-machine|setup-machine|remove-machine|set-ssh|scan-keys`

```yaml
# Register a new machine
- name: Register server
  rediacc.console.rediacc_machine:
    name: server-1
    state: present
    ip: 10.0.0.5
    user: deploy
    port: 22
    datastore: /mnt/rediacc

# Setup machine (install Docker, create BTRFS datastore)
- name: Setup server
  rediacc.console.rediacc_machine:
    name: server-1
    state: setup

# Remove machine
- name: Decommission server
  rediacc.console.rediacc_machine:
    name: server-1
    state: absent
```

**Parameters**:

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `name` | str | yes | - | Machine name |
| `state` | str | yes | - | `present`, `setup`, `absent` |
| `ip` | str | conditional | - | Required for `present` |
| `user` | str | conditional | - | Required for `present` |
| `port` | int | no | 22 | SSH port |
| `datastore` | str | no | `/mnt/rediacc` | Datastore path |
| `datastore_size` | str | no | `95%` | Datastore size for setup |

**Idempotency**: `state: present` checks `rdc config machines --output json` first. `state: setup` is idempotent by design (rdc setup-machine is safe to re-run).

---

## Module 8: `rediacc_machine_info`

**Purpose**: Read-only machine inspection.

**Wraps**: `rdc machine info|containers|services|health|repos`

```yaml
# Get full machine info
- name: Get machine status
  rediacc.console.rediacc_machine_info:
    machine: server-1
    query: info
  register: machine_info

# Health check with failure on unhealthy
- name: Health check
  rediacc.console.rediacc_machine_info:
    machine: server-1
    query: health
  register: health
  failed_when: health.json.status != 'healthy'

# List containers
- name: Get containers
  rediacc.console.rediacc_machine_info:
    machine: server-1
    query: containers
  register: containers
```

**Parameters**:

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `machine` | str | yes | - | Machine name |
| `query` | str | yes | - | `info`, `containers`, `services`, `health`, `repos` |

---

## Module 9: `rediacc_autostart`

**Purpose**: Enable/disable repository autostart.

**Wraps**: `rdc repo autostart enable|disable|enable-all|disable-all|list`

```yaml
- name: Enable autostart for my-app
  rediacc.console.rediacc_autostart:
    name: my-app
    machine: server-1
    state: enabled
```

---

## Module 10: `rediacc_infra`

**Purpose**: Configure and push Traefik reverse proxy infrastructure.

**Wraps**: `rdc config set-infra|push-infra`

```yaml
- name: Configure infra
  rediacc.console.rediacc_infra:
    machine: server-1
    domain: example.com
    email: admin@example.com
    state: configured

- name: Push infra to machine
  rediacc.console.rediacc_infra:
    machine: server-1
    state: pushed
```

---

## Module 11: `rediacc_template`

**Purpose**: Apply a template to a repository.

**Wraps**: `rdc repo template`

```yaml
- name: Apply PostgreSQL template
  rediacc.console.rediacc_template:
    name: my-db
    machine: server-1
    template_file: ./templates/postgresql.json
    grand: my-db-parent  # optional, for fork credential
```

---

## Module 12: `rediacc_datastore`

**Purpose**: Initialize and manage machine datastore backend.

**Wraps**: `rdc config set-ceph`, `rdc datastore init`

```yaml
# Initialize Ceph-backed datastore
- name: Setup Ceph datastore
  rediacc.console.rediacc_datastore:
    machine: server-1
    state: present
    backend: ceph
    size: 100G
    pool: rediacc_rbd_pool
    image: ds-prod
    force: true

# Local backend (default from setup-machine)
- name: Verify local datastore
  rediacc.console.rediacc_datastore:
    machine: server-1
    state: present
    backend: local
    size: 50G
```

**Parameters**:

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `machine` | str | yes | - | Target machine |
| `state` | str | yes | - | `present` (init datastore) |
| `backend` | str | no | local | `local` or `ceph` |
| `size` | str | yes | - | Datastore size (e.g., `100G`) |
| `pool` | str | conditional | - | Required for `ceph`. Ceph pool name |
| `image` | str | conditional | - | Required for `ceph`. RBD image name |
| `cluster` | str | no | ceph | Ceph cluster name |
| `force` | bool | no | false | Replace existing datastore |

**Idempotency**: Check `datastore status` — if backend matches and initialized=true, changed=false. If backend mismatch, requires force=true.

---

## Module 13: `rediacc_datastore_info`

**Purpose**: Query datastore status (read-only).

**Wraps**: `rdc datastore status`

```yaml
- name: Check datastore status
  rediacc.console.rediacc_datastore_info:
    machine: server-1
  register: ds_status

- name: Assert Ceph backend
  ansible.builtin.assert:
    that: ds_status.json.backend == 'ceph'
```

**Parameters**:

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `machine` | str | yes | - | Target machine |

**Returns**: `ds_status.json` — dict with `type`, `size`, `used`, `available`, `path`, `mounted`, `initialized`, `backend`, `rbd_image`. During fork: `cow_mode: true`.

**Note**: `datastore status` outputs plain JSON (no envelope wrapping). The runner parses it as plain JSON.

---

## Module 14: `rediacc_datastore_fork`

**Purpose**: Instant Ceph datastore fork and cleanup. This is the infrastructure equivalent of PlanetScale database branching — fork an entire encrypted application stack in < 2 seconds.

**Wraps**: `rdc datastore fork`, `rdc datastore unfork`

**Design note:** Uses `state` (not `direction`) because fork has a clear lifecycle — the fork either exists or doesn't. `state: present` creates the fork, `state: absent` destroys it.

```yaml
# Fork production datastore for testing (< 2 seconds)
- name: Fork datastore
  rediacc.console.rediacc_datastore_fork:
    source_machine: prod-1
    target_name: staging
    state: present
  register: fork_result

# fork_result.json contains: {snapshot, clone, source_image}
# All repos are instantly available on the COW overlay

# Clean up fork (restores original datastore)
- name: Unfork datastore
  rediacc.console.rediacc_datastore_fork:
    source_machine: prod-1
    state: absent
    snapshot: "{{ fork_result.json.snapshot }}"
    clone: "{{ fork_result.json.clone }}"
    source_image: "{{ fork_result.json.source_image }}"
    force: true
```

**Parameters**:

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `source_machine` | str | yes | - | Machine with Ceph datastore to fork |
| `target_name` | str | conditional | - | Required for `present`. Name for the fork (used in clone naming) |
| `state` | str | yes | - | `present` (fork) or `absent` (unfork) |
| `snapshot` | str | conditional | - | Required for `absent`. Snapshot name from fork output |
| `clone` | str | conditional | - | Required for `absent`. Clone name from fork output |
| `source_image` | str | conditional | - | Required for `absent`. Original RBD image name |
| `cow_size` | str | no | - | COW overlay size |
| `force` | bool | no | false | Continue cleanup on errors |

**Argument validation:**
```python
required_if=[
    ('state', 'present', ['target_name']),
    ('state', 'absent', ['snapshot', 'clone', 'source_image']),
],
```

**Important**: Fork mounts on the source machine, replacing `/mnt/rediacc` with a COW overlay. The original datastore is restored on unfork. Use separate machines for source and fork targets in production.

---

## Implementation Priority

| Priority | Module | Effort | Value |
|----------|--------|--------|-------|
| 1 | `rediacc_repo` | High | Critical — core lifecycle |
| 2 | `rediacc_machine` | Medium | Critical — fleet setup |
| 3 | `rediacc_machine_info` | Low | High — health checks, conditionals |
| 4 | `rediacc_sync` | Medium | High — deployment workflow |
| 5 | `rediacc_backup` | Medium | High — cross-machine ops |
| 6 | `rediacc_backup_info` | Low | High — DR automation needs list |
| 7 | `rediacc_backup_sync` | Low | Medium — fleet backup |
| 8 | `rediacc_backup_schedule` | Low | Medium — automation |
| 9 | `rediacc_autostart` | Low | Medium — production readiness |
| 10 | `rediacc_snapshot` | Low | Medium — safety net |
| 11 | `rediacc_snapshot_info` | Low | Low — list snapshots |
| 12 | `rediacc_infra` | Low | Low — one-time setup |
| 13 | `rediacc_template` | Low | Low — convenience |
| 14 | `rediacc_datastore` | Low | Medium — Ceph setup |
| 15 | `rediacc_datastore_info` | Low | Medium — status queries |
| 16 | `rediacc_datastore_fork` | Medium | High — instant fork differentiator |

Start with modules 1-6. They cover the full deploy + backup workflow. Add datastore modules (14-16) after core modules are stable.
