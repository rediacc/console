# Test Environment Setup Using `rdc ops`

## Overview

All integration and acceptance tests for both the Ansible collection and the
Terraform provider run against local VMs provisioned by `rdc ops`. This
ensures reproducible, isolated test environments without cloud costs.

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

## Quick Reference

```bash
# Full setup
./scripts/test-env-setup.sh

# Run Ansible unit tests
cd packages/ansible && pytest tests/unit/ -v

# Run Ansible integration tests
cd packages/ansible && RDC_BINARY="../../run.sh rdc" pytest tests/integration/ -v

# Run Terraform unit tests
cd packages/terraform/terraform-provider-rediacc && go test ./... -v

# Run Terraform acceptance tests
cd packages/terraform/terraform-provider-rediacc
TF_ACC=1 RDC_BINARY="../../../run.sh rdc" go test ./... -v -timeout 30m

# Full teardown
./scripts/test-env-teardown.sh
```
