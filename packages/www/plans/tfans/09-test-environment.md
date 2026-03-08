# Test Environment Setup Using `rdc ops`

## Overview

All integration and acceptance tests for both the Ansible collection and the
Terraform provider run against local VMs provisioned by `rdc ops`. This
ensures reproducible, isolated test environments without cloud costs.

## Test Environment Tiers

| Tier | Provisioning | Capabilities | When to use |
|------|-------------|--------------|-------------|
| **Basic** | `rdc ops up --basic --parallel` | Local datastores, rsync backup, all module tests | Default for CI, sufficient for most testing |
| **Full (Ceph)** | `rdc ops up --parallel` | Basic + Ceph datastores, instant fork, fork tests | Required for datastore fork tests, preview environment patterns |

The basic tier provisions 1 bridge + 2 workers (~6GB RAM, ~5 min).
The full tier adds 3 Ceph nodes (~12GB RAM, ~15 min including Ceph bootstrap).

### Full tier: Additional setup after VM provisioning

```bash
# After 'rdc ops up --parallel' (includes Ceph nodes 21-23):

# Configure Ceph on worker machines
$RDC config set-ceph -m rediacc11 --pool rediacc_rbd_pool --image test-ds-11
$RDC config set-ceph -m rediacc12 --pool rediacc_rbd_pool --image test-ds-12

# Initialize Ceph-backed datastores (replaces local from setup-machine)
$RDC datastore init -m rediacc11 --backend ceph --size 10G --force
$RDC datastore init -m rediacc12 --backend ceph --size 10G --force

# Verify
$RDC datastore status -m rediacc11
$RDC datastore status -m rediacc12
```

## Prerequisites

The host machine needs:
- KVM/QEMU (Linux), QEMU (macOS), or Hyper-V (Windows)
- Sufficient RAM for 2-3 VMs (~2GB each)
- `rdc` accessible (via `./run.sh rdc` in development)

Verify prerequisites:
```bash
./run.sh rdc ops check
```

If checks fail, install prerequisites:
```bash
./run.sh rdc ops setup
```

## VM Topology

For testing, use the `--basic` flag (1 bridge + 1-2 workers):

| VM | Name | IP | Role in Tests |
|----|------|----|---------------|
| 1 | rediacc1 | 192.168.111.1 | Bridge (registry, not directly tested) |
| 11 | rediacc11 | 192.168.111.11 | Primary test machine |
| 12 | rediacc12 | 192.168.111.12 | Secondary (for cross-machine tests) |
| 21 | rediacc21 | 192.168.111.21 | Ceph OSD node 1 (skipped with --basic) |
| 22 | rediacc22 | 192.168.111.22 | Ceph OSD node 2 (skipped with --basic) |
| 23 | rediacc23 | 192.168.111.23 | Ceph OSD node 3 (skipped with --basic) |

## Setup Script

```bash
#!/bin/bash
# scripts/test-env-setup.sh
# Sets up the complete test environment for Ansible/Terraform testing.

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RDC="$PROJECT_ROOT/run.sh rdc"
SSH_KEY_DIR="$HOME/.renet/staging/.ssh"

echo "=== Step 1: Build dependencies ==="
cd "$PROJECT_ROOT"
npm install
cd packages/shared && npm run build && cd ../..

echo "=== Step 2: Provision VMs ==="
$RDC ops up --basic --parallel

echo "=== Step 3: Wait for VMs to be ready ==="
# ops up may return before SSH is fully ready
for ip in 192.168.111.11 192.168.111.12; do
    echo "Waiting for $ip..."
    for i in $(seq 1 30); do
        if ssh -o StrictHostKeyChecking=no -o ConnectTimeout=2 \
            -i "$SSH_KEY_DIR/id_rsa" muhammed@"$ip" "echo ready" 2>/dev/null; then
            echo "$ip is ready"
            break
        fi
        sleep 2
    done
done

echo "=== Step 4: Register machines ==="
$RDC config add-machine rediacc11 --ip 192.168.111.11 --user muhammed 2>/dev/null || true
$RDC config add-machine rediacc12 --ip 192.168.111.12 --user muhammed 2>/dev/null || true

echo "=== Step 5: Set SSH keys ==="
$RDC config set-ssh \
    --private-key "$SSH_KEY_DIR/id_rsa" \
    --public-key "$SSH_KEY_DIR/id_rsa.pub"

echo "=== Step 6: Setup machines ==="
$RDC config setup-machine rediacc11
$RDC config setup-machine rediacc12

echo "=== Step 6b: Setup Ceph datastores (full tier only) ==="
if [[ "${TEST_TIER:-basic}" == "full" ]]; then
    $RDC config set-ceph -m rediacc11 --pool rediacc_rbd_pool --image test-ds-11
    $RDC config set-ceph -m rediacc12 --pool rediacc_rbd_pool --image test-ds-12
    $RDC datastore init -m rediacc11 --backend ceph --size 10G --force
    $RDC datastore init -m rediacc12 --backend ceph --size 10G --force
    echo "Ceph datastores initialized"
fi

echo "=== Step 7: Verify health ==="
$RDC machine health rediacc11
$RDC machine health rediacc12

echo "=== Step 8: Verify JSON envelope output ==="
# Validate that query commands return the expected JSON envelope format.
# This is critical: Ansible modules and Terraform provider depend on it.
REPOS_JSON=$($RDC --output json config repositories 2>/dev/null)
if echo "$REPOS_JSON" | jq -e '.success' >/dev/null 2>&1; then
    echo "JSON envelope format: OK"
else
    echo "WARNING: config repositories did not return JSON envelope format"
    echo "Output: $REPOS_JSON"
fi

echo "=== Test environment ready ==="
echo "Machines: rediacc11 (192.168.111.11), rediacc12 (192.168.111.12)"
echo "RDC binary: $RDC"
```

## Teardown Script

```bash
#!/bin/bash
# scripts/test-env-teardown.sh

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RDC="$PROJECT_ROOT/run.sh rdc"

echo "=== Cleaning up test repos ==="
# Delete any test repos that weren't cleaned up
# Note: JSON envelope format — extract 'data' field first, then get keys
for repo in $($RDC --output json config repositories 2>/dev/null | jq -r '.data // . | keys[]' 2>/dev/null || true); do
    case "$repo" in
        test-*|acc-test-*|molecule-*|integration-*)
            echo "Deleting test repo: $repo"
            $RDC repo delete "$repo" -m rediacc11 2>/dev/null || true
            $RDC repo delete "$repo" -m rediacc12 2>/dev/null || true
            $RDC config remove-repository "$repo" 2>/dev/null || true
            ;;
    esac
done

echo "=== Removing test machines from config ==="
$RDC config remove-machine rediacc11 2>/dev/null || true
$RDC config remove-machine rediacc12 2>/dev/null || true

echo "=== Destroying VMs ==="
$RDC ops down

echo "=== Teardown complete ==="
```

## Test Data: Minimal App for Testing

A minimal application for integration tests. Contains a Rediaccfile and
docker-compose.yaml that can be created, deployed, and verified.

```bash
# tests/fixtures/test-app/
mkdir -p tests/fixtures/test-app
```

### tests/fixtures/test-app/Rediaccfile

```bash
#!/bin/bash
# Minimal test application for integration testing

_use_renet() { [[ -n "$REPOSITORY_NETWORK_ID" ]] && command -v renet &>/dev/null; }
_compose() { _use_renet && renet compose --network-id "$REPOSITORY_NETWORK_ID" -- "$@" || docker compose "$@"; }

prep() {
    _compose pull
}

up() {
    _compose up -d
}

down() {
    _compose down -v
}

info() {
    echo "test-app: integration test fixture"
}
```

### tests/fixtures/test-app/docker-compose.yaml

```yaml
services:
  web:
    image: nginx:alpine
    healthcheck:
      test: ["CMD", "wget", "-q", "--spider", "http://localhost:80/"]
      interval: 5s
      timeout: 3s
      retries: 3
    volumes:
      - ./html:/usr/share/nginx/html:ro
```

### tests/fixtures/test-app/html/index.html

```html
<h1>Test App</h1>
<p>Integration test fixture for Ansible/Terraform testing.</p>
```

## Environment Variables for Tests

| Variable | Default | Used By | Description |
|----------|---------|---------|-------------|
| `RDC_BINARY` | `rdc` | Both | Path to rdc binary |
| `TEST_MACHINE_1` | `rediacc11` | Both | Primary test machine |
| `TEST_MACHINE_2` | `rediacc12` | Both | Secondary test machine |
| `TF_ACC` | (unset) | Terraform | Set to `1` to run acceptance tests |
| `ANSIBLE_COLLECTIONS_PATH` | (default) | Ansible | Where collection is installed |
| `TEST_TIER` | `basic` | Both | `basic` or `full` (Ceph). Controls whether Ceph setup runs. |

## Naming Conventions for Test Resources

To safely identify and clean up test resources:

| Type | Prefix | Example |
|------|--------|---------|
| Ansible unit test repos | `test-` | `test-repo-create` |
| Ansible integration test repos | `test-ansible-` | `test-ansible-deploy` |
| Terraform acceptance test repos | `acc-test-` | `acc-test-repo` |
| Molecule test repos | `molecule-` | `molecule-test-app` |
| Integration test repos | `integration-` | `integration-test-app` |

The teardown script uses these prefixes to clean up.

## CI Runner Requirements

For CI/CD (GitHub Actions, GitLab CI, etc.):

### Self-Hosted Runner Setup

```yaml
# Required runner labels: [self-hosted, kvm]
# Runner must have:
#   - KVM support (nested virt or bare metal)
#   - 8GB+ RAM
#   - 30GB+ disk
#   - Node.js 18+
#   - Go 1.22+
#   - Python 3.10+
#   - Ansible 2.15+
# For full tier (Ceph):
#   - 12GB+ RAM (3 additional Ceph VMs)
#   - 50GB+ disk (Ceph OSD storage)
```

### Docker-Based CI (Alternative)

If KVM is not available, tests can run against a Docker-in-Docker setup,
but this is limited (no full VM isolation, no CRIU, no BTRFS snapshots).

```yaml
# .github/workflows/ci.yml (Docker-based fallback)
services:
  dind:
    image: docker:dind
    options: --privileged
```

This is NOT recommended for full integration testing but can work
for basic module validation.

## Smoke Tests (Cumulative)

Smoke tests grow with each milestone. They exercise all implemented features
together in a single run — a quick "is everything still working?" check.
See `10-implementation-order.md` for when each section gets added.

### Ansible Smoke Playbook (`tests/smoke/ansible-smoke.yml`)

Each milestone adds a tagged section. Run subsets with `--tags` or
`--tags all` for the full smoke.

```yaml
---
# tests/smoke/ansible-smoke.yml
# Cumulative smoke test for the rediacc.console Ansible collection.
# Each section is tagged so milestones can run their subset.
# Usage:
#   ansible-playbook tests/smoke/ansible-smoke.yml --tags machine,repo
#   ansible-playbook tests/smoke/ansible-smoke.yml --tags all

- name: Ansible Collection Smoke Test
  hosts: localhost
  gather_facts: false
  vars:
    test_machine: "{{ lookup('env', 'TEST_MACHINE_1') | default('rediacc11', true) }}"
    test_machine_2: "{{ lookup('env', 'TEST_MACHINE_2') | default('rediacc12', true) }}"
    test_repo: smoke-test-app
    test_app_source: "{{ playbook_dir }}/../../fixtures/test-app/"

  tasks:
    # === Milestone 1.2: Machine ===
    - name: "[machine] Register test machine"
      rediacc.console.rediacc_machine:
        name: "{{ test_machine }}"
        state: present
        ip: 192.168.111.11
        user: muhammed
      tags: [machine]

    - name: "[machine] Verify machine exists"
      rediacc.console.rediacc_machine_info:
        machine: "{{ test_machine }}"
        query: info
      register: machine_info
      tags: [machine]

    - name: "[machine] Assert machine registered"
      ansible.builtin.assert:
        that: machine_info.json is defined
      tags: [machine]

    # === Milestone 1.3: Repository ===
    - name: "[repo] Create and deploy test repo"
      rediacc.console.rediacc_repo:
        name: "{{ test_repo }}"
        machine: "{{ test_machine }}"
        state: started
        size: 1G
      tags: [repo]

    - name: "[repo] Stop test repo"
      rediacc.console.rediacc_repo:
        name: "{{ test_repo }}"
        machine: "{{ test_machine }}"
        state: stopped
      tags: [repo]

    # === Milestone 1.4: Sync ===
    - name: "[sync] Upload test-app files"
      rediacc.console.rediacc_sync:
        machine: "{{ test_machine }}"
        repository: "{{ test_repo }}"
        direction: upload
        local_path: "{{ test_app_source }}"
        verify: true
      tags: [sync]

    - name: "[sync] Deploy after sync"
      rediacc.console.rediacc_repo:
        name: "{{ test_repo }}"
        machine: "{{ test_machine }}"
        state: started
      tags: [sync]

    - name: "[sync] Verify containers running"
      rediacc.console.rediacc_machine_info:
        machine: "{{ test_machine }}"
        query: containers
      register: containers
      until: >-
        containers.json | default([])
        | selectattr('repository', 'equalto', test_repo)
        | selectattr('state', 'equalto', 'running')
        | list | length > 0
      retries: 12
      delay: 10
      tags: [sync]

    - name: "[sync] Health check"
      rediacc.console.rediacc_machine_info:
        machine: "{{ test_machine }}"
        query: health
      register: health
      failed_when: health.json.status | default('unknown') != 'healthy'
      tags: [sync]

    # === Milestone 1.5: Backup ===
    - name: "[backup] Push backup to second machine"
      rediacc.console.rediacc_backup:
        repository: "{{ test_repo }}"
        machine: "{{ test_machine }}"
        direction: push
        to_machine: "{{ test_machine_2 }}"
      tags: [backup]

    - name: "[backup] Set backup schedule"
      rediacc.console.rediacc_backup_schedule:
        machine: "{{ test_machine }}"
        destination: "{{ test_machine_2 }}"
        cron: "0 3 * * *"
        state: present
      tags: [backup]

    # === Milestone 1.6: Snapshot + Autostart ===
    - name: "[snapshot] Create snapshot"
      rediacc.console.rediacc_snapshot:
        repository: "{{ test_repo }}"
        machine: "{{ test_machine }}"
        state: present
      tags: [snapshot]

    - name: "[autostart] Enable autostart"
      rediacc.console.rediacc_autostart:
        repository: "{{ test_repo }}"
        machine: "{{ test_machine }}"
        state: enabled
      tags: [autostart]

    # === Milestone 1.6b: Datastore (Ceph only) ===
    - name: "[datastore] Check datastore status"
      rediacc.console.rediacc_datastore_info:
        machine: "{{ test_machine }}"
      register: ds_status
      tags: [datastore]

    - name: "[datastore] Fork datastore (Ceph only)"
      rediacc.console.rediacc_datastore_fork:
        source_machine: "{{ test_machine }}"
        target_name: smoke-fork
        state: present
      register: fork_result
      when: ds_status.json.backend | default('local') == 'ceph'
      tags: [datastore]

    - name: "[datastore] Verify cow_mode"
      rediacc.console.rediacc_datastore_info:
        machine: "{{ test_machine }}"
      register: ds_forked
      failed_when: not ds_forked.json.cow_mode | default(false)
      when: fork_result is not skipped
      tags: [datastore]

    - name: "[datastore] Unfork"
      rediacc.console.rediacc_datastore_fork:
        source_machine: "{{ test_machine }}"
        state: absent
        snapshot: "{{ fork_result.json.snapshot }}"
        clone: "{{ fork_result.json.clone }}"
        source_image: "{{ fork_result.json.source_image }}"
        force: true
      when: fork_result is not skipped
      tags: [datastore]

    # === Cleanup (always runs) ===
    - name: "[cleanup] Delete test repo"
      rediacc.console.rediacc_repo:
        name: "{{ test_repo }}"
        machine: "{{ test_machine }}"
        state: absent
        force: true
      tags: [always]
      ignore_errors: true

    - name: "[cleanup] Remove backup schedule"
      rediacc.console.rediacc_backup_schedule:
        machine: "{{ test_machine }}"
        state: absent
      tags: [always]
      ignore_errors: true
```

### Ansible Smoke Inventory (`tests/smoke/rediacc.yml`)

```yaml
plugin: rediacc.console.rediacc
# Reads from default rdc config (populated by test-env-setup.sh)
```

### Terraform Smoke Config (`tests/smoke/terraform-smoke/main.tf`)

Each milestone adds resources. Use `-target` to test subsets.

```hcl
# tests/smoke/terraform-smoke/main.tf
# Cumulative smoke test for the rediacc Terraform provider.
# Usage:
#   terraform apply -auto-approve                     # Full smoke
#   terraform apply -auto-approve -target=rediacc_machine.test  # Machine only
#   terraform plan | grep "No changes"                # Idempotency check
#   terraform destroy -auto-approve                   # Cleanup

variable "rdc_binary" {
  default = "rdc"
}

variable "enable_fork" {
  default = false
  description = "Enable datastore fork test (requires TEST_TIER=full)"
}

provider "rediacc" {
  rdc_path = var.rdc_binary
}

# === Milestone 2.2: Machine ===
resource "rediacc_machine" "test" {
  name  = "smoke-test-machine"
  ip    = "192.168.111.11"
  user  = "muhammed"
  setup = true
}

# === Milestone 2.3: Repository ===
resource "rediacc_repository" "test" {
  name    = "smoke-test-repo"
  machine = rediacc_machine.test.name
  size    = "1G"
  deploy  = true

  source_dir  = "../../../fixtures/test-app/"
  sync_verify = true
}

# === Milestone 2.4: Data Sources ===
data "rediacc_machines" "all" {
  depends_on = [rediacc_machine.test]
}

data "rediacc_health" "test" {
  machine    = rediacc_machine.test.name
  depends_on = [rediacc_repository.test]
}

data "rediacc_containers" "test" {
  machine    = rediacc_machine.test.name
  depends_on = [rediacc_repository.test]
}

# === Milestone 2.5: Backup Schedule ===
resource "rediacc_backup_schedule" "test" {
  machine = rediacc_machine.test.name
  storage = "smoke-storage"
  cron    = "0 4 * * *"
}

# === Milestone 2.5c: Datastore Fork (Ceph only) ===
resource "rediacc_datastore_fork" "test" {
  count          = var.enable_fork ? 1 : 0
  source_machine = rediacc_machine.test.name
  target_name    = "smoke-fork"
}

# === Outputs (verify data sources work) ===
output "machine_health" {
  value = data.rediacc_health.test.status
}

output "machine_count" {
  value = length(data.rediacc_machines.all.machines)
}

output "container_count" {
  value = length(data.rediacc_containers.test.containers)
}

output "fork_active" {
  value = var.enable_fork ? rediacc_datastore_fork.test[0].cow_mode : false
}
```

### Phase 0: CLI Fix Verification (`tests/smoke/verify-cli-fixes.sh`)

```bash
#!/bin/bash
# tests/smoke/verify-cli-fixes.sh
# Verify all Phase 0 CLI fixes produce valid JSON output.
# Exits 0 if all pass, non-zero if any fail.

set -euo pipefail

RDC="${RDC_BINARY:-rdc}"
MACHINE="${TEST_MACHINE_1:-rediacc11}"
PASS=0
FAIL=0

check() {
    local desc="$1"; shift
    if "$@" >/dev/null 2>&1; then
        echo "  PASS: $desc"
        ((PASS++))
    else
        echo "  FAIL: $desc"
        ((FAIL++))
    fi
}

echo "=== Verifying CLI JSON output fixes ==="

# Fix 1: backup schedule show
check "backup schedule show returns JSON envelope" \
    bash -c "$RDC --output json backup schedule show 2>/dev/null | jq -e '.success'"

# Fix 2: backup list
check "backup list returns JSON envelope" \
    bash -c "$RDC --output json backup list -m $MACHINE 2>/dev/null | jq -e '.success'"

# Existing: config show (should always work)
check "config show returns JSON envelope" \
    bash -c "$RDC --output json config show 2>/dev/null | jq -e '.success'"

# Existing: machine health
check "machine health returns JSON envelope" \
    bash -c "$RDC --output json machine health $MACHINE 2>/dev/null | jq -e '.data'"

# Existing: machine containers
check "machine containers returns JSON envelope" \
    bash -c "$RDC --output json machine containers $MACHINE 2>/dev/null | jq -e '.success'"

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
[[ $FAIL -eq 0 ]]
```

## Quick Reference

```bash
# Full setup
./scripts/test-env-setup.sh

# Run Ansible unit tests
cd packages/ansible && pytest tests/unit/ -v

# Run Ansible integration tests
cd packages/ansible && RDC_BINARY="../../run.sh rdc" pytest tests/integration/ -v

# Run Ansible smoke test (all tags)
cd packages/ansible && ansible-playbook tests/smoke/ansible-smoke.yml --tags all

# Run Ansible smoke test (specific milestone)
cd packages/ansible && ansible-playbook tests/smoke/ansible-smoke.yml --tags machine,repo

# Run Terraform unit tests
cd packages/terraform/terraform-provider-rediacc && go test ./... -v

# Run Terraform acceptance tests
cd packages/terraform/terraform-provider-rediacc
TF_ACC=1 RDC_BINARY="../../../run.sh rdc" go test ./... -v -timeout 30m

# Run Terraform smoke test
cd tests/smoke/terraform-smoke && terraform apply -auto-approve && terraform destroy -auto-approve

# Full setup with Ceph (for fork tests)
TEST_TIER=full ./scripts/test-env-setup.sh

# Run datastore fork tests (requires full tier)
cd packages/ansible && RDC_BINARY="../../run.sh rdc" pytest tests/integration/test_05_datastore_fork.py -v

# Run Terraform fork smoke (requires full tier)
cd tests/smoke/terraform-smoke && terraform apply -auto-approve -var="enable_fork=true"
terraform destroy -auto-approve

# Verify Phase 0 CLI fixes
tests/smoke/verify-cli-fixes.sh

# Full teardown
./scripts/test-env-teardown.sh
```
