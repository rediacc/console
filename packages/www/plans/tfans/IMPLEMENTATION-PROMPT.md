# Ansible Collection + Terraform Provider Implementation Prompt

Paste this into a new Claude Code session. The AI will implement the full plan autonomously.

---

## Mission

You are implementing two new packages for the Rediacc console monorepo:

1. **`packages/ansible/rediacc/console/`** — An Ansible collection (`rediacc.console`) with 16 Python modules, 6 roles, a dynamic inventory plugin, and example playbooks. It wraps the `rdc` CLI to manage machines, repositories, backups, datastores, and Ceph instant fork.

2. **`packages/terraform/terraform-provider-rediacc/`** — A Terraform provider (Go, `terraform-plugin-framework`) with 5 managed resources, 5 data sources, CLI wrapper client, and concurrency control. It enables declarative infrastructure management with `rdc`.

There are 11 plan files that specify everything in detail. Your job is to read them, implement milestone by milestone, and **test each milestone against real VMs** before proceeding to the next.

## Environment

### Project Root

```
/home/muhammed/monorepo/console/.worktrees/0227-1/
```

**CRITICAL: This is a git worktree.** This path is the ONLY correct project root. Never use `/home/muhammed/monorepo/console/` — that's a different checkout.

### Running `rdc` Commands

In development, ALL `rdc` commands run through:
```bash
./run.sh rdc <command>
```

This script:
1. Checks Node.js version (>=22)
2. Installs npm dependencies (if needed)
3. Builds `packages/shared/` (if needed)
4. Builds the `renet` Go binary (if needed)
5. Runs CLI via `npx tsx packages/cli/src/index.ts <args>`

**Each invocation has ~5 seconds bootstrap overhead.** Minimize invocations by chaining independent commands:
```bash
# BAD: 3 invocations = 15s overhead
./run.sh rdc config add-machine rediacc11 --ip 192.168.111.11 --user muhammed
./run.sh rdc config add-machine rediacc12 --ip 192.168.111.12 --user muhammed
./run.sh rdc config set-ssh --private-key ~/.renet/staging/.ssh/id_rsa --public-key ~/.renet/staging/.ssh/id_rsa.pub

# GOOD: 1 invocation chained = 5s overhead
./run.sh rdc config add-machine rediacc11 --ip 192.168.111.11 --user muhammed && \
./run.sh rdc config add-machine rediacc12 --ip 192.168.111.12 --user muhammed && \
./run.sh rdc config set-ssh --private-key ~/.renet/staging/.ssh/id_rsa --public-key ~/.renet/staging/.ssh/id_rsa.pub
```

Actually no — `./run.sh rdc` must be called separately per command (it's the entrypoint). You can't chain rdc subcommands inside one `./run.sh rdc` call. But you CAN chain multiple `./run.sh rdc` calls with `&&`:
```bash
./run.sh rdc config add-machine rediacc11 --ip 192.168.111.11 --user muhammed && \
./run.sh rdc config add-machine rediacc12 --ip 192.168.111.12 --user muhammed
```

### Build Commands

```bash
# Install dependencies (run once, or after pulling changes)
npm install

# Build shared package (REQUIRED before CLI or any other package)
cd packages/shared && npm run build && cd ../..

# Type check CLI
npx tsc --noEmit --project packages/cli/tsconfig.json

# Run CLI unit tests (vitest)
cd packages/cli && npm run test:unit

# Run CLI E2E tests (playwright, requires VMs)
cd packages/cli && npm test
```

This monorepo uses **npm**, not pnpm.

### Language/Framework Details

| Package | Language | Test Framework | Build |
|---------|----------|---------------|-------|
| `packages/ansible/` | Python 3.10+ | pytest + Molecule | `ansible-galaxy collection build` |
| `packages/terraform/` | Go 1.22+ | `go test` + terraform-plugin-testing | `go build ./...` |
| `packages/cli/` | TypeScript | vitest (unit) + playwright (E2E) | `tsc` or `tsx` (dev) |
| `packages/shared/` | TypeScript | vitest | `tsc` |

## Plan Files

Read ALL of these before implementing. They contain complete specifications:

```
packages/www/plans/tfans/
├── 00-overview.md              # Architecture vision, JSON audit, design decisions
├── 01-ansible-collection.md    # Collection structure, galaxy.yml, rdc_runner.py, inventory plugin
├── 02-ansible-modules.md       # 16 module specifications with parameters, returns, idempotency
├── 03-ansible-roles.md         # 6 role definitions with tasks, defaults, tags
├── 04-ansible-testing.md       # Testing strategy: unit (pytest), integration, Molecule
├── 05-terraform-provider.md    # Provider architecture, Go client, concurrency, types
├── 06-terraform-resources.md   # 5 resources + 5 data sources with full CRUD specs
├── 07-terraform-testing.md     # Unit tests, acceptance tests, CI pipeline
├── 08-integration.md           # TF+Ansible patterns, preview environments, canary, DR
├── 09-test-environment.md      # VM setup, smoke tests, teardown, CI requirements
└── 10-implementation-order.md  # Milestone breakdown with ✅ Gates — YOUR PRIMARY GUIDE
```

**Read them in order (00 → 10).** Then follow `10-implementation-order.md` milestone by milestone.

## Testing Infrastructure: Real VMs via `rdc ops`

### The Core Principle

**Test against real VMs, not mocks, as much as possible.** Unit tests can mock `rdc` CLI output, but integration tests and smoke tests must run against actual ops VMs.

### VM Provisioning

```bash
# Check prerequisites (KVM, virsh, qemu-img, etc.)
./run.sh rdc ops check

# Install prerequisites if missing
./run.sh rdc ops setup

# Provision VMs (basic: 1 bridge + 2 workers, ~5 min)
./run.sh rdc ops up --basic --parallel

# Check they're running
./run.sh rdc ops status
```

### VM Topology

| VM | Name | IP | Role |
|----|------|----|------|
| 1 | rediacc1 | 192.168.111.1 | Bridge (registry, not directly tested) |
| 11 | rediacc11 | 192.168.111.11 | Primary test machine |
| 12 | rediacc12 | 192.168.111.12 | Secondary (cross-machine tests) |
| 21-23 | rediacc21-23 | 192.168.111.21-23 | Ceph nodes (skipped with --basic) |

### Post-Provisioning Setup

After `ops up`, register machines and set SSH keys:

```bash
./run.sh rdc config add-machine rediacc11 --ip 192.168.111.11 --user muhammed
./run.sh rdc config add-machine rediacc12 --ip 192.168.111.12 --user muhammed
./run.sh rdc config set-ssh \
    --private-key ~/.renet/staging/.ssh/id_rsa \
    --public-key ~/.renet/staging/.ssh/id_rsa.pub
./run.sh rdc config setup-machine rediacc11
./run.sh rdc config setup-machine rediacc12
```

**IMPORTANT:** `setup-machine` takes 5-15 minutes per machine (installs Docker, creates BTRFS datastore, provisions renet). Be patient and use a long timeout.

### Full Tier (Ceph — for datastore fork tests)

```bash
# Provision with Ceph nodes (takes ~15 min)
./run.sh rdc ops up --parallel

# Configure Ceph on workers
./run.sh rdc config set-ceph -m rediacc11 --pool rediacc_rbd_pool --image test-ds-11
./run.sh rdc config set-ceph -m rediacc12 --pool rediacc_rbd_pool --image test-ds-12
./run.sh rdc datastore init -m rediacc11 --backend ceph --size 10G --force
./run.sh rdc datastore init -m rediacc12 --backend ceph --size 10G --force
```

### Teardown

```bash
./run.sh rdc ops down
```

### VM Lifecycle During Development

VMs persist across test runs. You only need `ops up` once per session. If tests leave dirty state (orphan repos, etc.), clean up with:
```bash
./run.sh rdc repo delete <repo-name> -m rediacc11
./run.sh rdc config remove-repository <repo-name>
```

If VMs are corrupted, destroy and recreate:
```bash
./run.sh rdc ops down && ./run.sh rdc ops up --basic --parallel
```

## Implementation Approach

### The Rule: Gate Every Milestone

`10-implementation-order.md` defines **Gates** for each milestone — specific commands that must pass before proceeding. Follow them strictly:

1. **Read the milestone** in `10-implementation-order.md`
2. **Implement** the code listed
3. **Run the gate** commands
4. **If gate fails**: fix, don't proceed
5. **If gate passes**: move to next milestone

### Phase 0: Foundations

Before writing any Ansible or Terraform code:
1. Provision VMs: `./run.sh rdc ops up --basic --parallel`
2. Register + setup machines (see "Post-Provisioning Setup" above)
3. Fix the BLOCKING CLI JSON output gaps listed in Phase 0
4. Create the smoke test files defined in `09-test-environment.md`
5. Run the Phase 0 gate

### Phase 1: Ansible Collection

Create `packages/ansible/rediacc/console/` with the directory structure from `01-ansible-collection.md`.

For each module:
1. Read its spec in `02-ansible-modules.md`
2. Implement the module in `plugins/modules/`
3. Write unit tests in `tests/unit/` (pytest, mock `run_command`)
4. Write integration tests in `tests/integration/` (real VMs — `./run.sh rdc` must work)
5. Add the module's section to the smoke playbook
6. Run the milestone's gate

**Integration test pattern:**
```python
import subprocess
import json

def run_rdc(*args):
    """Run rdc CLI and return parsed JSON."""
    result = subprocess.run(
        ['./run.sh', 'rdc', '--output', 'json'] + list(args),
        capture_output=True, text=True, timeout=300,
        cwd='/home/muhammed/monorepo/console/.worktrees/0227-1'
    )
    if result.returncode != 0:
        raise RuntimeError(f"rdc failed: {result.stderr}")
    parsed = json.loads(result.stdout)
    # Unwrap envelope
    if isinstance(parsed, dict) and 'data' in parsed and 'success' in parsed:
        return parsed['data']
    return parsed
```

### Phase 2: Terraform Provider

Create `packages/terraform/terraform-provider-rediacc/` with the directory structure from `05-terraform-provider.md`.

Initialize the Go module:
```bash
cd packages/terraform/terraform-provider-rediacc
go mod init github.com/rediacc/terraform-provider-rediacc
go get github.com/hashicorp/terraform-plugin-framework
go get github.com/hashicorp/terraform-plugin-testing
```

The Go client (`internal/client/rdc.go`) wraps `rdc` via `exec.Command`. The binary path comes from the provider config — use `./run.sh rdc` path during development.

For acceptance tests:
```bash
cd packages/terraform/terraform-provider-rediacc
TF_ACC=1 RDC_BINARY="/home/muhammed/monorepo/console/.worktrees/0227-1/run.sh rdc" \
    go test ./... -v -timeout 30m
```

### Phase 3: Integration

The integration patterns from `08-integration.md` combine Terraform and Ansible. Test against the same ops VMs.

## Critical Rules

1. **Never call `renet` directly.** Only use `rdc` CLI. If `rdc` is missing a command, the fix goes into `rdc`.

2. **JSON envelope format.** Query commands (`config show`, `machine containers`, etc.) return:
   ```json
   {"success": true, "command": "...", "data": {...}, "errors": null, "warnings": [], "metrics": {}}
   ```
   Always unwrap `data` field. Exception: `datastore status` returns **plain JSON** (no envelope).

3. **Lifecycle commands have no JSON.** `repo create`, `repo up`, `repo down`, `repo delete`, `datastore fork`, `datastore unfork`, etc. — only check exit code, then query state separately.

4. **Config version conflicts.** `rdc`'s config file has a `version` field. Concurrent writes cause conflicts. The Terraform provider needs `mutexKV` per-machine locking (see `05-terraform-provider.md`).

5. **`backup schedule` flags.** Use `--destination`, `--cron`, `--enable`/`--disable`. NOT `--interval` or `--storage`.

6. **Terraform versioning.** Start at `0.x`. Ansible collection at `1.0`. Never refer to the Terraform provider as "v1.0".

7. **`datastore status` is special.** It outputs plain JSON from renet's stdout without the CLI's envelope wrapping. Parse as plain JSON.

8. **Fork mounts on source machine.** `datastore fork` replaces the source machine's `/mnt/rediacc` with a COW overlay. Design patterns around staging/test machines as fork sources.

9. **Don't break existing CLI code.** Your Phase 0 CLI fixes must not regress existing functionality. Run `cd packages/cli && npm run test:unit` after any CLI changes.

10. **Timeouts.** `setup-machine` = 5-15 min. `repo up` = 2-30 min (Docker pulls). `backup push` = minutes-hours. Set generous timeouts.

## File Reference Cheat Sheet

| Need | File |
|------|------|
| Module parameter specs | `02-ansible-modules.md` |
| Role task definitions | `03-ansible-roles.md` |
| `rdc_runner.py` implementation | `01-ansible-collection.md` (lines 140-235) |
| `galaxy.yml` | `01-ansible-collection.md` (lines 67-96) |
| Inventory plugin | `01-ansible-collection.md` (lines 299-410) |
| Go client (`rdc.go`) | `05-terraform-provider.md` |
| TF resource CRUD specs | `06-terraform-resources.md` |
| TF acceptance test examples | `07-terraform-testing.md` |
| Smoke playbook content | `09-test-environment.md` (Smoke Tests section) |
| Smoke TF config content | `09-test-environment.md` (Smoke Tests section) |
| Test fixture (Rediaccfile) | `09-test-environment.md` (Test Data section) |
| Gate commands per milestone | `10-implementation-order.md` (each milestone's Gate block) |

## Execution Order

```
1. Read all 11 plan files (00-10)
2. Provision VMs: ./run.sh rdc ops up --basic --parallel
3. Register + setup machines
4. Phase 0: Fix CLI gaps, create test infra, run Phase 0 gate
5. Phase 1 milestones 1.1 → 1.9: Ansible collection, gate each
6. Phase 1 → 2 transition gate (full Ansible suite)
7. Phase 2 milestones 2.1 → 2.6: Terraform provider, gate each
8. Phase 2 → 3 transition gate (full Ansible + Terraform suite)
9. Phase 3 milestones 3.1 → 3.3: Integration patterns, gate each
```

**Remember: no gate, no next milestone.** If a gate fails, fix the issue first.

Start by reading the plan files, then proceed with Phase 0.
