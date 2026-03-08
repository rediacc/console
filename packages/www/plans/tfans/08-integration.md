# Phase 3: Terraform + Ansible + rdc Integration

## The Full Stack

Phase 3 connects Terraform (infra) → Ansible (orchestration) → rdc (app deployment)
into cohesive, reusable workflows.

### Architectural Rule: Always Use `rdc`, Never `renet`

All integration patterns call the `rdc` CLI only. Renet is a low-level internal
component managed by rdc. The Terraform provider and Ansible modules MUST never
call renet directly (no `ssh user@machine sudo renet ...` patterns). If rdc is
missing a command or JSON output, the fix goes into rdc — not a renet bypass.

### JSON Output Behavior

- **Query commands** (`config show`, `machine containers`, etc.) return a JSON
  envelope: `{success, command, data, errors, warnings, metrics}`
- **Lifecycle commands** (`repo create`, `repo up`, etc.) stream renet's output
  directly — only the exit code matters (0 = success)
- Both Ansible modules and the Terraform provider handle this via separate
  methods: `run()`/`RunQuery()` for queries, `run_lifecycle()`/`RunLifecycle()`
  for mutations

## When to Use Which Tool

| Scenario | Recommended Tool | Why |
|----------|-----------------|-----|
| Provision cloud VMs + DNS | Terraform only | Declarative, cloud providers have mature TF support |
| Single machine, few repos | Terraform only | Simple, one `terraform apply` does everything |
| Fleet of 5+ machines | Terraform + Ansible | TF provisions, Ansible orchestrates rolling deploys |
| Rolling updates with health gates | Ansible only | `serial` + `until` + health checks |
| Disaster recovery runbook | Ansible only | Procedural, needs conditional logic and error recovery |
| Multi-region replication | Terraform + Ansible | TF manages infra per region, Ansible handles data flow |
| GitOps CI/CD pipeline | Both | TF in infra step, Ansible in deploy step |
| Instant staging/preview environment | Terraform + Ansible | TF manages `rediacc_datastore_fork`, Ansible deploys to forked env |
| Canary release with real data | Ansible only | Fork → deploy new version → validate → promote or discard |
| Nightly DR validation | Ansible only | Fork production → run DR playbook → verify → unfork |

**Rule of thumb:** Terraform for "what should exist", Ansible for "what should happen".
Terraform is poor at procedural workflows (backup → migrate → verify → cleanup).
Ansible is poor at declarative state management (drift detection, dependency graph).

## Pattern 1: Terraform Provisions, Ansible Deploys

The most common pattern. Terraform creates infrastructure, outputs feed
Ansible's dynamic inventory, Ansible orchestrates rdc across the fleet.

### Flow

```
1. terraform apply
   └── Creates VMs (Hetzner/DO/AWS)
   └── Registers machines (rediacc_machine)
   └── Sets up machines (setup = true)

2. ansible-playbook -i rediacc.yml deploy.yml
   └── Inventory plugin reads rdc config (populated by Terraform)
   └── Deploys apps across all machines
   └── Rolling updates with health gates
```

### Terraform (infra.tf)

```hcl
terraform {
  required_providers {
    hcloud = {
      source  = "hetznercloud/hcloud"
      version = "~> 1.45"
    }
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.0"
    }
    rediacc = {
      source  = "rediacc/rediacc"
      version = "~> 0.1"
    }
  }
}

variable "workers" {
  default = {
    "worker-1" = { location = "fsn1" }
    "worker-2" = { location = "fsn1" }
    "worker-3" = { location = "nbg1" }
  }
}

variable "domain" {
  default = "mycompany.com"
}

# Hetzner VMs
resource "hcloud_ssh_key" "deploy" {
  name       = "rediacc-deploy"
  public_key = file("~/.ssh/id_ed25519.pub")
}

resource "hcloud_server" "worker" {
  for_each    = var.workers
  name        = each.key
  server_type = "cx31"
  image       = "ubuntu-24.04"
  ssh_keys    = [hcloud_ssh_key.deploy.id]
  location    = each.value.location
}

# DNS records
resource "cloudflare_record" "worker" {
  for_each = var.workers
  zone_id  = var.cloudflare_zone_id
  name     = each.key
  content  = hcloud_server.worker[each.key].ipv4_address
  type     = "A"
  proxied  = false
}

# Register machines in rdc
resource "rediacc_machine" "worker" {
  for_each = var.workers
  name     = each.key
  ip       = hcloud_server.worker[each.key].ipv4_address
  user     = "root"
  setup    = true
}

# Infra (Traefik)
resource "rediacc_infra" "worker" {
  for_each = var.workers
  machine  = rediacc_machine.worker[each.key].name
  domain   = var.domain
  email    = "ops@${var.domain}"
}

# Outputs for visibility
output "machines" {
  value = { for name, m in rediacc_machine.worker : name => hcloud_server.worker[name].ipv4_address }
}
```

### Ansible Dynamic Inventory (rediacc.yml)

```yaml
plugin: rediacc.console.rediacc
# No config needed — reads from default rdc config
# which Terraform already populated
```

### Ansible Playbook (deploy.yml)

```yaml
---
# Deploy application to fleet provisioned by Terraform
# Usage: terraform apply && ansible-playbook -i rediacc.yml deploy.yml

- name: Deploy my-app to all workers
  hosts: all
  serial: 1                          # One at a time for zero-downtime
  max_fail_percentage: 0             # Stop on first failure

  vars:
    app_name: my-app
    app_source: ./my-app/
    app_size: 10G

  tasks:
    - name: Snapshot before deploy
      rediacc.console.rediacc_snapshot:
        repository: "{{ app_name }}"
        machine: "{{ inventory_hostname }}"
        state: present
      ignore_errors: true            # OK if repo doesn't exist yet

    - name: Deploy app
      ansible.builtin.include_role:
        name: rediacc.console.deploy_app
      vars:
        rediacc_app_name: "{{ app_name }}"
        rediacc_app_source: "{{ app_source }}"
        rediacc_app_size: "{{ app_size }}"
        rediacc_snapshot_before_deploy: false  # Already done above

    - name: Wait for containers
      rediacc.console.rediacc_machine_info:
        machine: "{{ inventory_hostname }}"
        query: containers
      register: containers
      until: >-
        containers.json | default([])
        | selectattr('repository', 'equalto', app_name)
        | selectattr('state', 'equalto', 'running')
        | list | length > 0
      retries: 12
      delay: 10

    - name: Health gate before next machine
      rediacc.console.rediacc_machine_info:
        machine: "{{ inventory_hostname }}"
        query: health
      register: health
      failed_when: health.json.status | default('unknown') != 'healthy'
```

---

## Pattern 2: Terraform-Only (Simple Deployments)

For simpler setups where fleet orchestration isn't needed, Terraform
manages everything declaratively:

```hcl
# Everything in one terraform apply
resource "rediacc_machine" "server" {
  name  = "prod-1"
  ip    = "10.0.0.1"
  user  = "deploy"
  setup = true
}

resource "rediacc_repository" "postgres" {
  name       = "postgres"
  machine    = rediacc_machine.server.name
  size       = "50G"
  deploy     = true
  source_dir = "./templates/postgresql/"
  autostart  = true

  backup_before_destroy = true
  backup_storage        = "s3-backups"

  lifecycle { prevent_destroy = true }
}

resource "rediacc_repository" "app" {
  name       = "my-app"
  machine    = rediacc_machine.server.name
  size       = "10G"
  deploy     = true
  source_dir = "./my-app/"
  autostart  = true

  depends_on = [rediacc_repository.postgres]

  lifecycle { prevent_destroy = true }
}

resource "rediacc_backup_schedule" "daily" {
  machine = rediacc_machine.server.name
  storage = "s3-backups"
  cron    = "0 2 * * *"
}
```

---

## Pattern 3: DR Automation (Ansible + Terraform)

Disaster recovery: provision new infrastructure and restore from backups.

### Terraform (dr-infra.tf)

```hcl
# Provision emergency replacement server
resource "hcloud_server" "dr" {
  name        = "dr-replacement"
  server_type = "cx41"           # Bigger for emergency
  image       = "ubuntu-24.04"
  ssh_keys    = [hcloud_ssh_key.deploy.id]
}

resource "rediacc_machine" "dr" {
  name  = "dr-replacement"
  ip    = hcloud_server.dr.ipv4_address
  user  = "root"
  setup = true
}
```

### Ansible (dr-restore.yml)

```yaml
---
# Restore all services to DR machine
# Usage: terraform apply -target=rediacc_machine.dr && ansible-playbook dr-restore.yml
- name: Disaster Recovery
  hosts: localhost
  tasks:
    - name: Restore from backup
      ansible.builtin.include_role:
        name: rediacc.console.disaster_recovery
      vars:
        rediacc_dr_storage: s3-backups
        rediacc_dr_target_machine: dr-replacement
        rediacc_dr_autostart_after: true
```

---

## Pattern 4: Multi-Region Replication

Deploy repos to machines in multiple regions with periodic backup sync:

### Terraform

```hcl
variable "regions" {
  default = {
    fsn1 = { name = "eu-1",  type = "cx31" }
    ash  = { name = "us-1",  type = "cx31" }
    sin  = { name = "ap-1",  type = "cx31" }
  }
}

resource "hcloud_server" "regional" {
  for_each    = var.regions
  name        = each.value.name
  server_type = each.value.type
  image       = "ubuntu-24.04"
  location    = each.key
  ssh_keys    = [hcloud_ssh_key.deploy.id]
}

resource "rediacc_machine" "regional" {
  for_each = var.regions
  name     = each.value.name
  ip       = hcloud_server.regional[each.key].ipv4_address
  user     = "root"
  setup    = true
}
```

### Ansible (replicate.yml)

```yaml
---
# Replicate primary repos to all regional machines
- name: Replicate to regions
  hosts: localhost
  vars:
    primary_machine: eu-1
    target_machines:
      - us-1
      - ap-1
    repos:
      - my-app
      - database

  tasks:
    - name: Push backup to each target
      rediacc.console.rediacc_backup:
        repository: "{{ item.0 }}"
        machine: "{{ primary_machine }}"
        direction: push
        to_machine: "{{ item.1 }}"
      loop: "{{ repos | product(target_machines) | list }}"

    - name: Deploy on targets
      rediacc.console.rediacc_repo:
        name: "{{ item.0 }}"
        machine: "{{ item.1 }}"
        state: started
        mount: true
      loop: "{{ repos | product(target_machines) | list }}"
```

---

## Pattern 5: GitOps Workflow

Store Terraform configs and Ansible playbooks in Git, use CI/CD for deployment:

```
repo/
├── infra/
│   ├── main.tf              # Infrastructure definition
│   ├── variables.tf
│   └── terraform.tfvars     # Non-secret values
├── deploy/
│   ├── rediacc.yml           # Dynamic inventory
│   ├── deploy.yml           # Deploy playbook
│   └── group_vars/
│       └── all.yml          # App configuration
├── apps/
│   ├── my-app/              # App files (Rediaccfile + compose)
│   └── database/            # DB files
└── .github/workflows/
    └── deploy.yml           # CI/CD pipeline
```

### CI/CD Pipeline

```yaml
name: Deploy

on:
  push:
    branches: [main]

jobs:
  infra:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: hashicorp/setup-terraform@v3
      - run: cd infra && terraform init && terraform apply -auto-approve

  deploy:
    needs: infra
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install ansible
      - run: ansible-galaxy collection install rediacc.console
      - run: cd deploy && ansible-playbook -i rediacc.yml deploy.yml
```

---

## Testing the Integration

### Integration Test Scenario

Test the complete Terraform → Ansible → rdc flow using ops VMs:

```bash
#!/bin/bash
# tests/integration/test_full_stack.sh

set -e

echo "=== Phase 1: Provision VMs ==="
./run.sh rdc ops up --basic --parallel

echo "=== Phase 2: Terraform apply ==="
cd tests/integration/terraform
terraform init
terraform apply -auto-approve \
  -var "machine1_ip=192.168.111.11" \
  -var "machine2_ip=192.168.111.12" \
  -var "rdc_binary=$(pwd)/../../../run.sh rdc"

echo "=== Phase 3: Ansible deploy ==="
cd ../ansible
ansible-playbook -i rediacc.yml deploy.yml \
  -e "rdc_binary=$(pwd)/../../../run.sh rdc"

echo "=== Phase 4: Verify ==="
ansible-playbook -i rediacc.yml verify.yml

echo "=== Phase 5: Terraform destroy ==="
cd ../terraform
terraform destroy -auto-approve

echo "=== Phase 6: Teardown VMs ==="
cd ../../..
./run.sh rdc ops down

echo "=== All integration tests passed ==="
```

### Test Terraform Config (tests/integration/terraform/main.tf)

```hcl
variable "machine1_ip" {}
variable "machine2_ip" {}
variable "rdc_binary" { default = "rdc" }

provider "rediacc" {
  rdc_path = var.rdc_binary
}

resource "rediacc_machine" "test1" {
  name  = "test-machine-1"
  ip    = var.machine1_ip
  user  = "muhammed"
  setup = true
}

resource "rediacc_machine" "test2" {
  name  = "test-machine-2"
  ip    = var.machine2_ip
  user  = "muhammed"
  setup = true
}

resource "rediacc_repository" "test_app" {
  name    = "integration-test-app"
  machine = rediacc_machine.test1.name
  size    = "1G"
  deploy  = true
}

data "rediacc_health" "test1" {
  machine = rediacc_machine.test1.name
  depends_on = [rediacc_repository.test_app]
}

output "health" {
  value = data.rediacc_health.test1.status
}
```

### Test Ansible Playbook (tests/integration/ansible/verify.yml)

```yaml
---
- name: Verify deployment
  hosts: all
  gather_facts: false
  tasks:
    - name: Check containers
      rediacc.console.rediacc_machine_info:
        machine: "{{ inventory_hostname }}"
        query: containers
      register: containers

    - name: Assert app is running
      ansible.builtin.assert:
        that:
          - containers.json | selectattr('repository', 'equalto', 'integration-test-app') | list | length > 0
        fail_msg: "integration-test-app not found on {{ inventory_hostname }}"
```

---

## Gradual Adoption Patterns

### Pattern 6: "I Already Have Stuff Running" (Import Workflow)

The most common real-world scenario. Users have existing rdc machines and
repos running in production. They want to adopt Terraform/Ansible without
downtime or recreation.

**Step 1: Import machines into Terraform**
```hcl
# Import existing machines (no changes, just reads state)
import {
  to = rediacc_machine.prod
  id = "prod-1"
}

resource "rediacc_machine" "prod" {
  name  = "prod-1"
  ip    = "10.0.0.1"     # Match existing config
  user  = "deploy"
  setup = true            # Already set up, won't re-run
}
```

**Step 2: Verify with plan**
```bash
terraform plan
# Should show: No changes. Your infrastructure matches the configuration.
```

**Step 3: Gradually import repos**
```hcl
import {
  to = rediacc_repository.app
  id = "my-app:prod-1"
}

resource "rediacc_repository" "app" {
  name    = "my-app"
  machine = rediacc_machine.prod.name
  size    = "10G"
  deploy  = true
  lifecycle { prevent_destroy = true }
}
```

**Step 4: New resources via Terraform, existing via rdc**

Keep managing existing repos with `rdc` directly. Only add new repos to
Terraform as needed. No all-or-nothing migration required.

### The Kamal Model: TF for Machines, CLI for Apps

Inspired by 37signals' Kamal: use Terraform for infrastructure provisioning
(VMs, DNS, firewalls, machine registration) and `rdc` CLI directly for
application management. This is the natural starting point for most users:

```
Terraform manages:          rdc manages (directly):
├── Cloud VMs               ├── repo create/up/down
├── DNS records             ├── sync upload/download
├── Firewall rules          ├── backup push/pull
├── rediacc_machine         └── day-to-day operations
└── (optional) rediacc_infra

Ansible adds value at:
├── Rolling deploys across 5+ machines
├── Health-gated batch updates
└── DR runbooks
```

This works because Terraform's value is declarative infrastructure management
(what should exist), while `rdc`'s value is the actual deployment workflow
(encrypted repos, Docker isolation, backup). They complement without overlapping.

### Coexistence with Manual Operations

The tools must coexist with manual `rdc` usage. Users will always run
`rdc machine info`, `rdc repo up`, `rdc term` directly. The IaC tools
should not break when out-of-band changes happen:

- **Terraform Read()** detects drift and shows it in `plan` output
- **Ansible check mode** queries current state before acting
- **Neither tool** locks out manual `rdc` usage
- **Config version conflicts** are retried (not fatal)

## Pattern 6: Preview Environments via Ceph Fork

The infrastructure equivalent of Vercel preview deployments — every PR gets a
complete copy of the production stack with real data, created in < 2 seconds.

### Ansible Playbook (preview.yml)

```yaml
---
# Create preview environment from production
# Usage: ansible-playbook preview.yml -e pr_number=42 -e source_machine=staging-1
- name: Preview Environment
  hosts: localhost
  vars:
    source_machine: staging-1
    pr_number: ""
    app_source: "./my-app/"

  tasks:
    - name: Fork datastore (< 2 seconds)
      rediacc.console.rediacc_datastore_fork:
        source_machine: "{{ source_machine }}"
        target_name: "pr-{{ pr_number }}"
        state: present
      register: fork

    - name: Upload PR changes
      rediacc.console.rediacc_sync:
        machine: "{{ source_machine }}"
        repository: my-app
        direction: upload
        local_path: "{{ app_source }}"
        verify: true

    - name: Redeploy with changes
      rediacc.console.rediacc_repo:
        name: my-app
        machine: "{{ source_machine }}"
        state: started

    - name: Wait for healthy
      rediacc.console.rediacc_machine_info:
        machine: "{{ source_machine }}"
        query: health
      register: health
      until: health.json.status | default('unknown') == 'healthy'
      retries: 12
      delay: 10

    - name: Store fork metadata for cleanup
      ansible.builtin.set_fact:
        fork_metadata: "{{ fork.json }}"
```

### Terraform (preview environments as resources)

```hcl
# CI/CD creates preview per PR, destroys on merge
variable "pr_number" {}

resource "rediacc_datastore_fork" "preview" {
  source_machine = rediacc_machine.staging.name
  target_name    = "pr-${var.pr_number}"
}

# After fork, deploy PR changes via Ansible
resource "null_resource" "deploy_pr" {
  depends_on = [rediacc_datastore_fork.preview]
  provisioner "local-exec" {
    command = "ansible-playbook deploy-pr.yml -e source_machine=${rediacc_machine.staging.name}"
  }
}
```

---

## Pattern 7: Canary Release with Real Data

Fork production data → deploy new version → validate → promote or discard.
Unlike traditional canary deploys that use empty environments, this tests
against an exact copy of production data.

### Ansible Playbook (canary.yml)

```yaml
---
# Canary release: fork → deploy → validate → decide
- name: Canary Release
  hosts: localhost
  vars:
    production_machine: prod-1
    app_name: my-app
    app_source: ./my-app-v2/
    validation_script: ./scripts/validate-canary.sh

  tasks:
    - name: Fork production (< 2 seconds)
      rediacc.console.rediacc_datastore_fork:
        source_machine: "{{ production_machine }}"
        target_name: canary
        state: present
      register: fork

    - name: Deploy new version to canary
      rediacc.console.rediacc_sync:
        machine: "{{ production_machine }}"
        repository: "{{ app_name }}"
        direction: upload
        local_path: "{{ app_source }}"
        verify: true

    - name: Restart with new code
      rediacc.console.rediacc_repo:
        name: "{{ app_name }}"
        machine: "{{ production_machine }}"
        state: started

    - name: Run validation suite
      ansible.builtin.script: "{{ validation_script }}"
      register: validation
      ignore_errors: true

    - name: Cleanup canary (unfork restores original)
      rediacc.console.rediacc_datastore_fork:
        source_machine: "{{ production_machine }}"
        state: absent
        snapshot: "{{ fork.json.snapshot }}"
        clone: "{{ fork.json.clone }}"
        source_image: "{{ fork.json.source_image }}"
        force: true

    - name: Report result
      ansible.builtin.debug:
        msg: "Canary {{ 'PASSED' if validation.rc == 0 else 'FAILED' }}. Production restored to original state."
```

---

## Pattern 8: Nightly DR Validation

Fork production every night → run full DR playbook against the fork →
verify all services recover → unfork. Actual disaster recovery testing
with real data, automated. This is what Netflix's Chaos Engineering aims
for but is typically too expensive to do with full data copies.

### Ansible Playbook (dr-validate.yml)

```yaml
---
# Nightly DR validation against production fork
# Usage: Run via cron or CI schedule
- name: DR Validation
  hosts: localhost
  vars:
    production_machine: prod-1
    dr_storage: s3-backups
    expected_repos:
      - my-app
      - database
      - mail

  tasks:
    - name: Fork production for DR test
      rediacc.console.rediacc_datastore_fork:
        source_machine: "{{ production_machine }}"
        target_name: dr-test
        state: present
      register: fork

    - name: Simulate failure — stop all repos
      rediacc.console.rediacc_repo:
        name: "{{ item }}"
        machine: "{{ production_machine }}"
        state: stopped
      loop: "{{ expected_repos }}"

    - name: Restore from backup (DR procedure)
      ansible.builtin.include_role:
        name: rediacc.console.disaster_recovery
      vars:
        rediacc_dr_storage: "{{ dr_storage }}"
        rediacc_dr_target_machine: "{{ production_machine }}"

    - name: Verify all repos recovered
      rediacc.console.rediacc_machine_info:
        machine: "{{ production_machine }}"
        query: containers
      register: containers
      until: >-
        expected_repos | difference(
          containers.json | default([])
          | selectattr('state', 'equalto', 'running')
          | map(attribute='repository') | list
        ) | length == 0
      retries: 20
      delay: 15

    - name: Cleanup — unfork restores real production
      rediacc.console.rediacc_datastore_fork:
        source_machine: "{{ production_machine }}"
        state: absent
        snapshot: "{{ fork.json.snapshot }}"
        clone: "{{ fork.json.clone }}"
        source_image: "{{ fork.json.source_image }}"
        force: true
      tags: [always]

    - name: Report
      ansible.builtin.debug:
        msg: "DR validation PASSED — all {{ expected_repos | length }} repos recovered successfully"
```

---

## Anti-Patterns to Avoid

### Don't duplicate rdc's responsibilities

Ansible/Terraform should NEVER:
- SSH into machines and run renet commands directly
- Parse Docker container state via `docker ps` — use `rdc machine containers`
- Manage LUKS volumes, loopback IPs, or Docker daemon sockets
- Build QueueVaultV2 payloads — only rdc knows how
- Allocate networkIds — rdc manages `nextNetworkId` in config

### Don't manage the same resource in both tools

If Terraform manages `rediacc_repository.app`, Ansible should NOT also create
or delete that repo. Use one tool for lifecycle, the other for orchestration.
Good: TF creates repos, Ansible does rolling redeploys.
Bad: TF creates repos, Ansible also creates repos on different machines.

### Don't run Terraform and Ansible concurrently against the same config

rdc's config file has a `version` field for conflict detection. Running
`terraform apply` and `ansible-playbook` simultaneously against the same
config will cause version conflicts. Sequence them: TF first, then Ansible.

### Don't bypass data safety guardrails

Never use `terraform destroy -auto-approve` in production without
`backup_before_destroy = true` on all repository resources. Never use
Ansible `state: absent` without `force: true` and a preceding backup task.

## Lessons from Similar Projects

**From the Dokku Terraform provider:** Keep the transport layer (SSH/exec)
separate from domain logic. The Dokku provider has `ssh.go` → `dokku.go` →
`resource_*.go`, which makes it easy to test each layer independently.

**From community.docker Ansible collection:** Idempotency detection by comparing
desired vs actual state is fragile when the underlying tool changes output format.
Pin to structured JSON output and version-gate parsing logic.

**From Google's Terraform provider:** Per-resource mutex locking prevents
concurrent modification of the same cloud resource. Essential for CLI-wrapper
providers where the underlying tool doesn't handle concurrency.

**From the Shell Terraform provider:** A `read` script that re-queries actual
state is the key to drift detection. Compare output to previously stored state
to detect out-of-band changes.
