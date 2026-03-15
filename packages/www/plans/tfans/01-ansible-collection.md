# Phase 1: Ansible Collection — `rediacc.console`

## Collection Identity

| Field | Value |
|-------|-------|
| Namespace | `rediacc` |
| Name | `console` |
| FQCN | `rediacc.console` |
| Min Ansible | `2.15+` |
| Python | `3.10+` |
| License | MIT or proprietary (TBD) |
| Distribution | Ansible Galaxy + GitHub Releases |

## Directory Structure

```
packages/ansible/rediacc/console/
├── galaxy.yml                          # Collection metadata
├── meta/
│   └── runtime.yml                     # Ansible version requirements
├── plugins/
│   ├── modules/                        # Individual operation modules
│   │   ├── rediacc_repo.py             # Repository lifecycle
│   │   ├── rediacc_sync.py             # File sync (upload/download)
│   │   ├── rediacc_backup.py           # Backup push/pull
│   │   ├── rediacc_backup_info.py      # Backup listing (read-only)
│   │   ├── rediacc_backup_sync.py      # Bulk backup sync
│   │   ├── rediacc_backup_schedule.py  # Backup scheduling
│   │   ├── rediacc_snapshot.py         # BTRFS snapshots (create/delete)
│   │   ├── rediacc_snapshot_info.py    # Snapshot listing (read-only)
│   │   ├── rediacc_machine.py          # Machine registration + setup
│   │   ├── rediacc_machine_info.py     # Machine info (read-only)
│   │   ├── rediacc_autostart.py        # Autostart enable/disable
│   │   ├── rediacc_infra.py            # Traefik proxy setup
│   │   ├── rediacc_template.py         # Template application
│   │   ├── rediacc_datastore.py        # Datastore initialization and backend management
│   │   ├── rediacc_datastore_info.py   # Datastore status (read-only)
│   │   └── rediacc_datastore_fork.py   # Instant fork/unfork via Ceph
│   ├── inventory/
│   │   └── rediacc.py                  # Dynamic inventory from rdc config
│   ├── doc_fragments/
│   │   └── rdc_common.py               # Shared DOCUMENTATION for rdc_binary/config_name/debug
│   └── module_utils/
│       ├── rdc_runner.py               # Shared: rdc CLI execution wrapper
│       └── rdc_common.py               # Shared: argument specs, constants
├── roles/
│   ├── deploy_app/                     # Full deploy workflow
│   ├── migrate_repo/                   # Cross-machine migration
│   ├── setup_machine/                  # Machine provisioning
│   ├── backup_fleet/                   # Fleet-wide backup
│   └── disaster_recovery/             # DR runbook
├── playbooks/
│   ├── deploy.yml                      # Deploy app to fleet
│   ├── migrate.yml                     # Migrate repo between machines
│   ├── backup_all.yml                  # Backup all machines
│   └── health_check.yml                # Fleet health check
├── tests/
│   ├── unit/                           # Unit tests (pytest)
│   ├── integration/                    # Integration tests (rdc ops VMs)
│   └── molecule/                       # Molecule scenarios
└── README.md
```

## galaxy.yml

```yaml
namespace: rediacc
name: console
version: 1.0.0
readme: README.md
authors:
  - Rediacc <info@rediacc.com>
description: >-
  Ansible collection for managing Rediacc infrastructure.
  Deploy encrypted repositories, sync files, manage backups,
  and orchestrate across machine fleets.
license:
  - MIT
repository: https://github.com/rediacc/ansible-collection-console
documentation: https://rediacc.com/docs/ansible
homepage: https://rediacc.com
issues: https://github.com/rediacc/ansible-collection-console/issues
tags:
  - rediacc
  - docker
  - deployment
  - encryption
  - infrastructure
  - self-hosted
dependencies: {}
build_ignore:
  - tests/
  - .github/
  - molecule/
```

## meta/runtime.yml

```yaml
requires_ansible: ">=2.15.0"
plugin_routing:
  modules: {}
```

## Core Utility: `rdc_runner.py`

This is the shared CLI wrapper used by all modules. It handles:
- Finding the `rdc` binary
- Building command arguments
- Executing and parsing JSON output
- **Unwrapping the JSON envelope** (extracting `data` from `{success, command, data, errors, warnings, metrics}`)
- Mapping exit codes to Ansible failures
- Config file selection
- Distinguishing between **query commands** (return JSON) and **lifecycle commands** (return exit code only)

### JSON Envelope Format

Query commands (`config show`, `machine containers`, `config repositories`, etc.)
return a JSON envelope when `--output json` is used:

```json
{ "success": true, "command": "...", "data": {...}, "errors": null, "warnings": [], "metrics": {} }
```

The runner automatically extracts the `data` field so modules access it directly
via `result['json']` without knowing about the envelope.

### Lifecycle Commands (No JSON)

Lifecycle commands (`repo create`, `repo up`, `repo down`, `repo delete`, etc.)
do NOT return structured JSON even with `--output json`. They stream renet's
stdout/stderr directly. For these commands:
- **Exit code 0** = success, non-zero = failure
- **stdout** contains renet's raw output (docker pull progress, compose logs)
- **stderr** contains rdc's status messages (info, success, warn, error)

Use `run_lifecycle()` for these commands — it skips JSON parsing entirely.

```python
# plugins/module_utils/rdc_runner.py

import json

class RdcRunner:
    """Wrapper for executing rdc CLI commands from Ansible modules."""

    def __init__(self, module):
        self.module = module
        self.rdc_path = module.params.get('rdc_binary') or module.get_bin_path('rdc', required=True)
        self.config_name = module.params.get('config_name')
        self.debug = module.params.get('debug', False)

    def _build_cmd(self, args, json_output=True):
        """Build the rdc command array."""
        cmd = [self.rdc_path]
        if json_output:
            cmd.extend(['--output', 'json'])
        if self.config_name:
            cmd.extend(['--config', self.config_name])
        if self.debug:
            cmd.append('--debug')
        cmd.extend(args)
        return cmd

    def run(self, args, check_rc=True):
        """Execute a query command and return parsed JSON data.

        Automatically unwraps the JSON envelope: if stdout contains
        {success, command, data, ...}, result['json'] will be the 'data' field.
        The full envelope is available in result['envelope'].
        """
        cmd = self._build_cmd(args)
        rc, stdout, stderr = self.module.run_command(cmd, check_rc=False)

        result = {
            'rc': rc,
            'stdout': stdout,
            'stderr': stderr,
            'cmd': ' '.join(cmd),
            'json': None,
            'envelope': None,
        }

        # Parse JSON from stdout
        if stdout.strip():
            try:
                parsed = json.loads(stdout)
                # Check for JSON envelope format
                if isinstance(parsed, dict) and 'data' in parsed and 'success' in parsed:
                    result['envelope'] = parsed
                    result['json'] = parsed['data']
                    # Surface envelope errors as warnings
                    if parsed.get('errors'):
                        result['errors'] = parsed['errors']
                    if parsed.get('warnings'):
                        result['warnings'] = parsed['warnings']
                else:
                    # Plain JSON (no envelope) — use as-is
                    result['json'] = parsed
            except json.JSONDecodeError:
                result['json'] = None

        if check_rc and rc != 0:
            self.module.fail_json(
                msg=f"rdc command failed (rc={rc}): {stderr or stdout}",
                **result
            )

        return result

    def run_lifecycle(self, args, check_rc=True):
        """Execute a lifecycle command (create, up, down, delete).

        These commands do NOT return structured JSON — they stream renet's
        output directly. Only the exit code matters for success/failure.
        """
        cmd = self._build_cmd(args, json_output=False)
        rc, stdout, stderr = self.module.run_command(cmd, check_rc=False)

        result = {
            'rc': rc,
            'stdout': stdout,
            'stderr': stderr,
            'cmd': ' '.join(cmd),
        }

        if check_rc and rc != 0:
            self.module.fail_json(
                msg=f"rdc command failed (rc={rc}): {stderr or stdout}",
                **result
            )

        return result
```

## Common Argument Spec: `rdc_common.py`

Shared argument specs avoid duplication across modules. The `COMMON_ARGS`
dict is merged into every module's `argument_spec`.

```python
# plugins/module_utils/rdc_common.py

COMMON_ARGS = dict(
    rdc_binary=dict(type='str', required=False, default=None),
    config_name=dict(type='str', required=False, default=None),
    debug=dict(type='bool', required=False, default=False),
)

MACHINE_ARG = dict(
    machine=dict(type='str', required=True),
)

REPO_ARG = dict(
    name=dict(type='str', required=True),
)
```

## Documentation Fragment: `rdc_common`

All modules share the same `rdc_binary`, `config_name`, and `debug` parameters.
A doc_fragment avoids repeating documentation for these across all modules:

```python
# plugins/doc_fragments/rdc_common.py

class ModuleDocFragment:
    DOCUMENTATION = r'''
options:
    rdc_binary:
        description:
            - Path to the rdc binary.
            - If not set, the module will search for C(rdc) on PATH.
        type: str
    config_name:
        description:
            - Named rdc config to use (e.g., C(production), C(staging)).
            - Defaults to the default config file.
        type: str
    debug:
        description:
            - Enable verbose rdc output for troubleshooting.
        type: bool
        default: false
'''
```

Modules reference this fragment:
```python
DOCUMENTATION = r'''
module: rediacc_repo
extends_documentation_fragment:
    - rediacc.console.rdc_common
...
'''
```

## Dynamic Inventory Plugin

The inventory plugin reads the rdc config file and generates Ansible inventory
with all registered machines. This enables `hosts: all` in playbooks to target
all rdc machines.

### Caching

The plugin uses Ansible's `Cacheable` mixin for inventory caching. This avoids
running `rdc config show` on every `ansible-playbook` invocation — important
when the config is stable and rdc commands add SSH latency.

Users enable caching in `ansible.cfg`:
```ini
[inventory]
cache = true
cache_plugin = jsonfile
cache_timeout = 300
cache_connection = ~/.ansible/cache
```

The plugin checks the cache before calling rdc. If cached data exists and
hasn't expired, it skips the subprocess call entirely.

### Implementation

```python
# plugins/inventory/rediacc.py
# DOCUMENTATION, EXAMPLES, etc. omitted for brevity

class InventoryModule(BaseInventoryPlugin, Cacheable):
    NAME = 'rediacc.console.rediacc'

    def parse(self, inventory, loader, path, cache=True):
        super().parse(inventory, loader, path, cache)
        config = self._read_config_data(path)

        rdc_binary = config.get('rdc_binary', 'rdc')
        config_name = config.get('config_name', None)

        # Cache key: unique per config_name
        cache_key = f"rediacc_{config_name or 'default'}"
        rdc_config = None

        # Try cache first (Cacheable mixin)
        if cache:
            try:
                rdc_config = self._cache.get(cache_key, {})
            except KeyError:
                pass

        if not rdc_config:
            # Run: rdc config show --output json
            cmd = [rdc_binary, '--output', 'json']
            if config_name:
                cmd.extend(['--config', config_name])
            cmd.extend(['config', 'show'])

            result = subprocess.run(cmd, capture_output=True, text=True)
            parsed = json.loads(result.stdout)

            # Unwrap JSON envelope if present
            if isinstance(parsed, dict) and 'data' in parsed and 'success' in parsed:
                rdc_config = parsed['data']
            else:
                rdc_config = parsed

            # Store in cache
            if cache:
                self._cache[cache_key] = rdc_config

        # Add machines to inventory
        machines = rdc_config.get('machines', {})
        for name, machine_config in machines.items():
            self.inventory.add_host(name)
            self.inventory.set_variable(name, 'ansible_host', machine_config['ip'])
            self.inventory.set_variable(name, 'ansible_user', machine_config.get('user', 'root'))
            self.inventory.set_variable(name, 'ansible_port', machine_config.get('port', 22))
            # Pass rdc-specific vars
            self.inventory.set_variable(name, 'rediacc_datastore', machine_config.get('datastore', '/mnt/rediacc'))

            # Group by infra domain if set
            infra = machine_config.get('infra', {})
            if infra.get('domain'):
                self.inventory.add_group(f"domain_{infra['domain'].replace('.', '_')}")
                self.inventory.add_child(f"domain_{infra['domain'].replace('.', '_')}", name)

        # Add repos as host vars
        repos = rdc_config.get('repositories', {})
        for machine_name in machines:
            self.inventory.set_variable(machine_name, 'rediacc_repositories', repos)

        # SSH config from rdc
        ssh_config = rdc_config.get('ssh', {})
        if ssh_config.get('privateKeyPath'):
            for name in machines:
                self.inventory.set_variable(name, 'ansible_ssh_private_key_file', ssh_config['privateKeyPath'])
```

**Inventory source file** (`rediacc.yml`):
```yaml
plugin: rediacc.console.rediacc
rdc_binary: rdc
config_name: production  # optional, defaults to default config
```

**Usage**:
```bash
ansible-inventory -i rediacc.yml --list
ansible -i rediacc.yml all -m ping
```

## Build and Distribution

```bash
# Build collection tarball
cd packages/ansible/rediacc/console
ansible-galaxy collection build

# Install locally for testing
ansible-galaxy collection install rediacc-console-1.0.0.tar.gz --force

# Publish to Galaxy
ansible-galaxy collection publish rediacc-console-1.0.0.tar.gz --api-key $GALAXY_API_KEY
```

## CI Pipeline

```yaml
# .github/workflows/ansible-collection.yml
name: Ansible Collection CI
on:
  push:
    paths: ['packages/ansible/**']
  pull_request:
    paths: ['packages/ansible/**']

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install ansible-lint
      - run: ansible-lint packages/ansible/rediacc/console/

  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install pytest ansible
      - run: cd packages/ansible && pytest tests/unit/

  integration-tests:
    runs-on: ubuntu-latest  # or self-hosted with KVM
    needs: [lint, unit-tests]
    steps:
      - uses: actions/checkout@v4
      - run: npm install && cd packages/shared && npm run build
      - run: ./rdc.sh ops up --basic --parallel
      # ... register machines, run integration playbooks
      - run: ./rdc.sh ops down
```
