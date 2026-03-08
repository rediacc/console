# Phase 1d: Ansible Testing Strategy

## Testing Layers

```
Layer 1: Unit Tests (pytest)           ← Fast, no infrastructure
  └── Test module argument validation, idempotency logic, output parsing

Layer 2: Integration Tests (rdc ops)   ← Real VMs, real rdc commands
  └── Test modules against live infrastructure

Layer 3: Role Tests (Molecule)         ← Full playbook runs
  └── Test role workflows end-to-end

Layer 4: Inventory Tests               ← Dynamic inventory plugin
  └── Test config parsing and host generation
```

## Key Testing Principles

1. **Unit tests must mock the JSON envelope format.** Query commands return
   `{success, command, data, ...}` — the runner unwraps this. Test mocks
   must produce envelope-wrapped responses, not raw data.

2. **Unit tests for lifecycle commands must use `run_lifecycle()`.** These
   commands don't return JSON. Mock only the exit code and stderr.

3. **Check mode tests should use `--dry-run`.** `repo up/down/delete` support
   `--dry-run` which returns structured JSON. Check mode should invoke this
   and report what would change without executing.

4. **Integration tests need resource cleanup.** Use test name prefixes
   (`test-ansible-*`) and a cleanup fixture that deletes matching repos
   even if tests fail mid-run.

5. **Error handling tests must cover `retryable` flag.** The error envelope
   includes `retryable: true/false` — test that modules surface this
   correctly for playbook retry logic.

6. **Test argument validation declaratively.** Verify `mutually_exclusive`,
   `required_if`, and `required_together` constraints produce proper errors
   before the module code runs (Ansible validates these at module init).

7. **Test diff mode output.** When `_diff=True`, verify modules return
   `before` and `after` dicts that accurately show state transitions.

8. **Test `state` parameter naming.** Verify backup modules use `direction`
   (not `action`), schedule modules use `state` (not `action`), and all
   state-based modules accept standard values (`present`, `absent`, etc.).

## Layer 1: Unit Tests

Unit tests verify module internals without calling `rdc`. They mock
`module.run_command()` and test argument validation, command building,
and output parsing.

**Framework**: pytest + ansible's `ModuleTestCase` or plain mocking

**Location**: `tests/unit/plugins/modules/`

### Test Structure

```
tests/
├── unit/
│   ├── conftest.py                      # Shared fixtures
│   ├── plugins/
│   │   ├── modules/
│   │   │   ├── test_rediacc_repo.py
│   │   │   ├── test_rediacc_sync.py
│   │   │   ├── test_rediacc_backup.py
│   │   │   ├── test_rediacc_machine.py
│   │   │   └── test_rediacc_machine_info.py
│   │   ├── module_utils/
│   │   │   ├── test_rdc_runner.py
│   │   │   └── test_rdc_common.py
│   │   └── inventory/
│   │       └── test_rediacc_inventory.py
│   └── pytest.ini
```

### Example: test_rdc_runner.py

```python
import json
import pytest
from unittest.mock import MagicMock, patch
from plugins.module_utils.rdc_runner import RdcRunner


@pytest.fixture
def mock_module():
    module = MagicMock()
    module.params = {'rdc_binary': '/usr/bin/rdc', 'config_name': None, 'debug': False}
    module.get_bin_path.return_value = '/usr/bin/rdc'
    return module


class TestRdcRunner:
    def test_builds_command_with_json_output(self, mock_module):
        """rdc commands always include --output json"""
        runner = RdcRunner(mock_module)
        mock_module.run_command.return_value = (0, '{}', '')
        runner.run(['machine', 'info', 'server-1'])
        cmd = mock_module.run_command.call_args[0][0]
        assert '--output' in cmd
        assert 'json' in cmd

    def test_includes_config_flag(self, mock_module):
        """--config flag is added when config_name is set"""
        mock_module.params['config_name'] = 'production'
        runner = RdcRunner(mock_module)
        mock_module.run_command.return_value = (0, '{}', '')
        runner.run(['config', 'show'])
        cmd = mock_module.run_command.call_args[0][0]
        assert '--config' in cmd
        assert 'production' in cmd

    def test_includes_debug_flag(self, mock_module):
        """--debug flag is added when debug=True"""
        mock_module.params['debug'] = True
        runner = RdcRunner(mock_module)
        mock_module.run_command.return_value = (0, '{}', '')
        runner.run(['repo', 'list', '-m', 'server-1'])
        cmd = mock_module.run_command.call_args[0][0]
        assert '--debug' in cmd

    def test_parses_json_envelope(self, mock_module):
        """JSON envelope is unwrapped — result['json'] is the data field"""
        runner = RdcRunner(mock_module)
        envelope = json.dumps({
            'success': True,
            'command': 'machine health',
            'data': {'status': 'healthy'},
            'errors': None,
            'warnings': [],
            'metrics': {}
        })
        mock_module.run_command.return_value = (0, envelope, '')
        result = runner.run(['machine', 'health', 'server-1'])
        assert result['json'] == {'status': 'healthy'}
        assert result['envelope']['success'] is True

    def test_parses_plain_json(self, mock_module):
        """Plain JSON (no envelope) is returned as-is"""
        runner = RdcRunner(mock_module)
        mock_module.run_command.return_value = (0, '{"custom": "data"}', '')
        result = runner.run(['some', 'command'])
        assert result['json'] == {'custom': 'data'}
        assert result['envelope'] is None

    def test_fails_on_nonzero_rc(self, mock_module):
        """Non-zero exit code calls fail_json"""
        runner = RdcRunner(mock_module)
        mock_module.run_command.return_value = (1, '', 'Error: not found')
        runner.run(['repo', 'status', 'missing', '-m', 'server-1'])
        mock_module.fail_json.assert_called_once()

    def test_skips_rc_check_when_disabled(self, mock_module):
        """check_rc=False allows non-zero exit without failure"""
        runner = RdcRunner(mock_module)
        mock_module.run_command.return_value = (1, '', 'Error: not found')
        result = runner.run(['repo', 'status', 'missing', '-m', 'x'], check_rc=False)
        assert result['rc'] == 1
        mock_module.fail_json.assert_not_called()

    def test_handles_empty_stdout(self, mock_module):
        """Empty stdout results in json=None"""
        runner = RdcRunner(mock_module)
        mock_module.run_command.return_value = (0, '', '')
        result = runner.run(['config', 'show'])
        assert result['json'] is None

    def test_handles_non_json_stdout(self, mock_module):
        """Non-JSON stdout results in json=None"""
        runner = RdcRunner(mock_module)
        mock_module.run_command.return_value = (0, 'Success!', '')
        result = runner.run(['config', 'show'])
        assert result['json'] is None

    def test_lifecycle_skips_json_parsing(self, mock_module):
        """run_lifecycle() does not parse JSON or add --output json"""
        runner = RdcRunner(mock_module)
        mock_module.run_command.return_value = (0, 'Starting...', 'info: created')
        result = runner.run_lifecycle(['repo', 'create', 'x', '-m', 'y', '--size', '1G'])
        assert 'json' not in result
        cmd = mock_module.run_command.call_args[0][0]
        assert '--output' not in cmd
```

### Example: test_rediacc_repo.py

```python
import json
import pytest
from unittest.mock import MagicMock, patch


class TestRediaccRepoCreate:
    """Test state: present (create)"""

    def test_creates_repo_when_not_exists(self, mock_module):
        """Should call rdc repo create when repo doesn't exist"""
        mock_module.params.update({
            'name': 'my-app',
            'machine': 'server-1',
            'state': 'present',
            'size': '5G',
        })
        # First call: config repositories query (envelope, repo not found)
        # Second call: repo create lifecycle (exit code only)
        # Third call: config repositories query (envelope, verify created)
        empty_envelope = json.dumps({
            'success': True, 'command': 'config repositories',
            'data': {}, 'errors': None, 'warnings': [], 'metrics': {}
        })
        created_envelope = json.dumps({
            'success': True, 'command': 'config repositories',
            'data': {'my-app': {'repositoryGuid': 'abc', 'networkId': 1}},
            'errors': None, 'warnings': [], 'metrics': {}
        })
        mock_module.run_command.side_effect = [
            (0, empty_envelope, ''),    # query: no repos
            (0, 'Created', ''),          # lifecycle: create success
            (0, created_envelope, ''),   # query: verify created
        ]
        # ... run module, assert changed=True

    def test_skips_create_when_exists(self, mock_module):
        """Should not call rdc repo create when repo already exists"""
        mock_module.params.update({
            'name': 'my-app',
            'machine': 'server-1',
            'state': 'present',
            'size': '5G',
        })
        envelope = json.dumps({
            'success': True, 'command': 'config repositories',
            'data': {'my-app': {'repositoryGuid': 'abc', 'networkId': 1}},
            'errors': None, 'warnings': [], 'metrics': {}
        })
        mock_module.run_command.side_effect = [
            (0, envelope, ''),  # query: repo exists
        ]
        # ... run module, assert changed=False

    def test_check_mode_does_not_create(self, mock_module):
        """Check mode should report would-change without executing"""
        mock_module.params.update({
            'name': 'my-app',
            'machine': 'server-1',
            'state': 'present',
            'size': '5G',
        })
        mock_module.check_mode = True
        mock_module.run_command.side_effect = [
            (0, json.dumps({}), ''),  # repo doesn't exist
        ]
        # ... run module, assert changed=True, only 1 run_command call


class TestRediaccRepoDelete:
    """Test state: absent"""

    def test_requires_force_for_delete(self, mock_module):
        """Should fail when force=false for deletion"""
        mock_module.params.update({
            'name': 'my-app',
            'machine': 'server-1',
            'state': 'absent',
            'force': False,
        })
        # ... run module, assert fail_json called

    def test_skips_delete_when_not_exists(self, mock_module):
        """Should not attempt delete when repo doesn't exist"""
        mock_module.params.update({
            'name': 'my-app',
            'machine': 'server-1',
            'state': 'absent',
            'force': True,
        })
        mock_module.run_command.side_effect = [
            (0, json.dumps({}), ''),  # no repos
        ]
        # ... run module, assert changed=False


class TestRediaccRepoStarted:
    """Test state: started"""

    def test_creates_and_starts_when_new(self, mock_module):
        """Should create then deploy when repo doesn't exist"""
        # ... test both create + up sequence

    def test_starts_existing_stopped_repo(self, mock_module):
        """Should only run up when repo exists but is stopped"""
        # ... test up-only path
```

### Running Unit Tests

```bash
cd packages/ansible
pip install pytest ansible
pytest tests/unit/ -v
```

---

## Layer 2: Integration Tests

Integration tests run against real infrastructure provisioned by `rdc ops`.
They execute actual `rdc` commands through the Ansible modules.

**Framework**: pytest (calling ansible-playbook) or Ansible's built-in test framework

**Location**: `tests/integration/`

### Setup: Provision Test Environment

See `09-test-environment.md` for full details. Summary:

```bash
# Provision 2 VMs for testing
./run.sh rdc ops up --basic --parallel

# Register machines
./run.sh rdc config add-machine rediacc11 --ip 192.168.111.11 --user muhammed
./run.sh rdc config add-machine rediacc12 --ip 192.168.111.12 --user muhammed
./run.sh rdc config set-ssh \
  --private-key ~/.renet/staging/.ssh/id_rsa \
  --public-key ~/.renet/staging/.ssh/id_rsa.pub

# Setup machines
./run.sh rdc config setup-machine rediacc11
./run.sh rdc config setup-machine rediacc12
```

### Integration Test Structure

```
tests/integration/
├── conftest.py                        # pytest fixtures for VM setup
├── inventory.yml                      # Static inventory for test VMs
├── test_01_machine_module.py
├── test_02_repo_lifecycle.py
├── test_03_sync_module.py
├── test_04_backup_cross_machine.py
├── test_05_roles.py
├── playbooks/                         # Test playbooks
│   ├── test_deploy.yml
│   ├── test_migrate.yml
│   └── test_backup_fleet.yml
└── cleanup.yml                        # Teardown playbook
```

### Test Inventory (for ops VMs)

```yaml
# tests/integration/inventory.yml
all:
  hosts:
    rediacc11:
      ansible_host: 192.168.111.11
      ansible_user: muhammed
      ansible_ssh_private_key_file: ~/.renet/staging/.ssh/id_rsa
    rediacc12:
      ansible_host: 192.168.111.12
      ansible_user: muhammed
      ansible_ssh_private_key_file: ~/.renet/staging/.ssh/id_rsa
  vars:
    rdc_binary: "{{ lookup('env', 'RDC_BINARY') | default('./run.sh rdc', true) }}"
```

### Example: test_02_repo_lifecycle.py

```python
"""Integration tests for rediacc_repo module lifecycle."""
import subprocess
import json
import pytest

MACHINE = 'rediacc11'
REPO_NAME = 'test-ansible-repo'

def run_playbook(playbook_content, extra_vars=None):
    """Write temp playbook and run it."""
    # ... helper to run ansible-playbook with inventory

class TestRepoLifecycle:
    """Tests run in order — create, deploy, check, stop, delete."""

    def test_01_create_repo(self):
        """Create a new repository via ansible module."""
        result = run_playbook(f"""
        - hosts: localhost
          tasks:
            - rediacc.console.rediacc_repo:
                name: {REPO_NAME}
                machine: {MACHINE}
                state: present
                size: 1G
                rdc_binary: ./run.sh rdc
        """)
        assert result.returncode == 0
        # Verify: check rdc config repositories
        check = subprocess.run(
            ['./run.sh', 'rdc', '--output', 'json', 'config', 'repositories'],
            capture_output=True, text=True
        )
        repos = json.loads(check.stdout)
        assert REPO_NAME in repos

    def test_02_create_idempotent(self):
        """Creating same repo again should be idempotent (changed=false)."""
        result = run_playbook(f"""
        - hosts: localhost
          tasks:
            - rediacc.console.rediacc_repo:
                name: {REPO_NAME}
                machine: {MACHINE}
                state: present
                size: 1G
                rdc_binary: ./run.sh rdc
              register: result
            - ansible.builtin.assert:
                that: not result.changed
        """)
        assert result.returncode == 0

    def test_03_deploy_repo(self):
        """Deploy the repository (state: started)."""
        # First sync a simple Rediaccfile + compose
        # Then run repo up
        pass

    def test_04_check_containers(self):
        """Verify containers are running after deploy."""
        pass

    def test_05_stop_repo(self):
        """Stop the repository."""
        pass

    def test_06_delete_repo(self):
        """Delete the repository."""
        pass

    def test_07_delete_idempotent(self):
        """Deleting non-existent repo should be idempotent."""
        pass
```

### Example: test_04_backup_cross_machine.py

```python
"""Integration tests for cross-machine backup operations."""

class TestCrossMachineBackup:
    """Tests backup push from rediacc11 to rediacc12."""

    def test_01_create_repo_on_source(self):
        """Create repo on rediacc11."""
        pass

    def test_02_deploy_app_on_source(self):
        """Deploy a simple app with data."""
        pass

    def test_03_backup_push_to_target(self):
        """Push backup from rediacc11 to rediacc12."""
        result = run_playbook(f"""
        - hosts: localhost
          tasks:
            - rediacc.console.rediacc_backup:
                repository: test-backup-repo
                machine: rediacc11
                direction: push
                to_machine: rediacc12
                rdc_binary: ./run.sh rdc
        """)
        assert result.returncode == 0

    def test_04_deploy_on_target(self):
        """Deploy the backed-up repo on rediacc12."""
        pass

    def test_05_verify_data_integrity(self):
        """Verify data matches between source and target."""
        pass

    def test_06_cleanup(self):
        """Delete repos on both machines."""
        pass
```

---

## Layer 3: Role Tests (Molecule)

Molecule tests verify complete role workflows.

**Framework**: Molecule with delegated driver (uses rdc ops VMs)

### Molecule Structure

```
roles/deploy_app/
└── molecule/
    └── default/
        ├── molecule.yml
        ├── converge.yml
        ├── verify.yml
        └── cleanup.yml
```

### molecule.yml

```yaml
dependency:
  name: galaxy
driver:
  name: delegated
  options:
    managed: false
platforms:
  - name: rediacc11
    groups:
      - workers
provisioner:
  name: ansible
  inventory:
    hosts:
      all:
        hosts:
          rediacc11:
            ansible_host: 192.168.111.11
            ansible_user: muhammed
            ansible_ssh_private_key_file: ~/.renet/staging/.ssh/id_rsa
verifier:
  name: ansible
```

### converge.yml

```yaml
- name: Converge
  hosts: workers
  roles:
    - role: rediacc.console.deploy_app
      vars:
        rediacc_app_name: molecule-test-app
        rediacc_app_source: "{{ playbook_dir }}/files/test-app/"
        rediacc_app_size: 1G
```

### verify.yml

```yaml
- name: Verify
  hosts: workers
  tasks:
    - name: Check containers are running
      rediacc.console.rediacc_machine_info:
        machine: "{{ inventory_hostname }}"
        query: containers
      register: containers

    - name: Assert app container exists
      ansible.builtin.assert:
        that:
          - containers.json | selectattr('repository', 'equalto', 'molecule-test-app') | list | length > 0
```

### Running Molecule Tests

```bash
cd packages/ansible/rediacc/console/roles/deploy_app
molecule test
```

---

## Layer 4: Inventory Plugin Tests

```python
# tests/unit/plugins/inventory/test_rediacc_inventory.py

class TestRediaccInventory:
    def test_parses_machines_from_config(self):
        """Should create host entries from rdc config machines."""
        config_output = json.dumps({
            'machines': {
                'server-1': {'ip': '10.0.0.1', 'user': 'deploy', 'port': 22},
                'server-2': {'ip': '10.0.0.2', 'user': 'deploy', 'port': 2222},
            },
            'repositories': {
                'my-app': {'repositoryGuid': 'abc-123'},
            }
        })
        # Mock subprocess, run inventory plugin, verify hosts

    def test_sets_ssh_key_from_config(self):
        """Should set ansible_ssh_private_key_file from rdc ssh config."""
        pass

    def test_groups_by_domain(self):
        """Should create groups based on infra domain."""
        pass

    def test_handles_empty_config(self):
        """Should return empty inventory for config with no machines."""
        pass
```

---

## CI/CD Test Pipeline

```yaml
# .github/workflows/ansible-tests.yml
name: Ansible Collection Tests

on:
  push:
    paths: ['packages/ansible/**']
  pull_request:
    paths: ['packages/ansible/**']

jobs:
  unit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install pytest ansible
      - run: cd packages/ansible && pytest tests/unit/ -v --tb=short

  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install ansible-lint yamllint
      - run: ansible-lint packages/ansible/rediacc/console/
      - run: yamllint packages/ansible/rediacc/console/

  # Integration tests require self-hosted runner with KVM support
  integration:
    runs-on: [self-hosted, kvm]
    needs: [unit, lint]
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@v4
      - run: npm install && cd packages/shared && npm run build
      - name: Provision test VMs
        run: ./run.sh rdc ops up --basic --parallel
      - name: Register machines
        run: |
          ./run.sh rdc config add-machine rediacc11 --ip 192.168.111.11 --user muhammed
          ./run.sh rdc config add-machine rediacc12 --ip 192.168.111.12 --user muhammed
          ./run.sh rdc config set-ssh \
            --private-key ~/.renet/staging/.ssh/id_rsa \
            --public-key ~/.renet/staging/.ssh/id_rsa.pub
          ./run.sh rdc config setup-machine rediacc11
          ./run.sh rdc config setup-machine rediacc12
      - name: Install collection
        run: |
          cd packages/ansible/rediacc/console
          ansible-galaxy collection build
          ansible-galaxy collection install rediacc-console-*.tar.gz --force
      - name: Run integration tests
        run: |
          cd packages/ansible
          RDC_BINARY="$(pwd)/../../run.sh rdc" pytest tests/integration/ -v --tb=short
        env:
          ANSIBLE_COLLECTIONS_PATH: ~/.ansible/collections
      - name: Teardown VMs
        if: always()
        run: ./run.sh rdc ops down
```

---

## Test Coverage Goals

| Layer | Coverage Target | What it validates |
|-------|----------------|-------------------|
| Unit | 90%+ per module | Argument validation, command building, output parsing, idempotency logic, check mode |
| Integration | All modules | Actual rdc commands work, state changes are real, error handling |
| Role | All roles | End-to-end workflows, multi-step operations, failure recovery |
| Inventory | 100% | Config parsing, host generation, SSH key handling |
