# Phase 1c: Ansible Role Definitions

Roles combine modules into reusable workflows. Each role is a directory under
`roles/` in the collection with standard Ansible structure.

## Role Design Conventions

### Variable Namespacing

All role variables use the `rediacc_` prefix followed by the role context.
This prevents collisions when multiple roles are used in the same play
(Ansible best practice — see `geerlingguy` roles for examples):

| Role | Variable prefix | Example |
|------|----------------|---------|
| `setup_machine` | `rediacc_` | `rediacc_datastore`, `rediacc_infra_domain` |
| `deploy_app` | `rediacc_app_` | `rediacc_app_name`, `rediacc_app_size` |
| `migrate_repo` | `rediacc_migrate_` | `rediacc_migrate_source`, `rediacc_migrate_target` |
| `backup_fleet` | `rediacc_backup_` | `rediacc_backup_storage`, `rediacc_backup_cron` |
| `disaster_recovery` | `rediacc_dr_` | `rediacc_dr_storage`, `rediacc_dr_target_machine` |

### Tags for Selective Execution

Every role task has a tag so users can run subsets of a role:

```bash
# Only sync files, skip deploy
ansible-playbook deploy.yml --tags rediacc_sync

# Only health check
ansible-playbook deploy.yml --tags rediacc_health

# Skip snapshot
ansible-playbook deploy.yml --skip-tags rediacc_snapshot
```

Tags follow the pattern `rediacc_<action>` (e.g., `rediacc_deploy`,
`rediacc_sync`, `rediacc_health`, `rediacc_snapshot`, `rediacc_autostart`).

### Handler Patterns

Roles use handlers with `listen` for event-driven actions. This allows
multiple tasks to trigger the same handler without coupling:

```yaml
# handlers/main.yml
- name: Verify machine health
  rediacc.console.rediacc_machine_info:
    machine: "{{ inventory_hostname }}"
    query: health
  register: rediacc_health_result
  listen: rediacc_state_changed

- name: Report deployment status
  ansible.builtin.debug:
    msg: "{{ inventory_hostname }}: health={{ rediacc_health_result.json.status | default('unknown') }}"
  listen: rediacc_state_changed
```

Tasks notify the handler after state changes:
```yaml
- name: Deploy repository
  rediacc.console.rediacc_repo:
    name: "{{ rediacc_app_name }}"
    machine: "{{ inventory_hostname }}"
    state: started
  notify: rediacc_state_changed
```

## JSON Output Convention

All modules use `rdc_runner.py` which automatically unwraps the JSON envelope
(`{success, command, data, ...}`). When a module registers output, `result.json`
contains the `data` field directly — not the full envelope. For example:

- `rdc machine health` → `result.json` = `{status: "healthy", ...}`
- `rdc machine containers` → `result.json` = `[{name: ..., state: ..., repository: ...}, ...]`
- `rdc config repositories` → `result.json` = `{repo-name: {repositoryGuid: ..., networkId: ...}, ...}`

Lifecycle commands (`repo create`, `repo up`, etc.) don't return JSON.
Modules use `run_lifecycle()` for those and report `changed` based on exit code.

## Role 1: `setup_machine`

**Purpose**: Register, configure, and set up a machine from scratch.

```
roles/setup_machine/
├── tasks/main.yml
├── defaults/main.yml
├── meta/main.yml
└── README.md
```

### defaults/main.yml
```yaml
rediacc_ssh_private_key: ~/.ssh/id_ed25519
rediacc_ssh_public_key: ""
rediacc_datastore: /mnt/rediacc
rediacc_datastore_size: "95%"
rediacc_infra_domain: ""
rediacc_infra_email: ""
rediacc_setup_infra: false
```

### tasks/main.yml
```yaml
- name: Register machine in rdc config
  rediacc.console.rediacc_machine:
    name: "{{ inventory_hostname }}"
    state: present
    ip: "{{ ansible_host }}"
    user: "{{ ansible_user | default('root') }}"
    port: "{{ ansible_port | default(22) }}"
    datastore: "{{ rediacc_datastore }}"

- name: Setup machine (Docker, BTRFS, tools)
  rediacc.console.rediacc_machine:
    name: "{{ inventory_hostname }}"
    state: setup
    datastore_size: "{{ rediacc_datastore_size }}"

- name: Configure infra (Traefik proxy)
  rediacc.console.rediacc_infra:
    machine: "{{ inventory_hostname }}"
    domain: "{{ rediacc_infra_domain }}"
    email: "{{ rediacc_infra_email }}"
    state: configured
  when: rediacc_setup_infra | bool

- name: Push infra to machine
  rediacc.console.rediacc_infra:
    machine: "{{ inventory_hostname }}"
    state: pushed
  when: rediacc_setup_infra | bool

- name: Verify machine health
  rediacc.console.rediacc_machine_info:
    machine: "{{ inventory_hostname }}"
    query: health
  register: health_result
  failed_when: false

- name: Report machine status
  ansible.builtin.debug:
    msg: "Machine {{ inventory_hostname }} setup complete. Health: {{ health_result.json.status | default('unknown') }}"
```

### Usage
```yaml
- hosts: new_machines
  roles:
    - role: rediacc.console.setup_machine
      vars:
        rediacc_setup_infra: true
        rediacc_infra_domain: mycompany.com
        rediacc_infra_email: ops@mycompany.com
```

---

## Role 2: `deploy_app`

**Purpose**: Full application deployment — create repo, sync files, deploy, verify.

```
roles/deploy_app/
├── tasks/main.yml
├── defaults/main.yml
├── handlers/main.yml
├── meta/main.yml
└── README.md
```

### defaults/main.yml
```yaml
rediacc_app_name: ""           # Required
rediacc_app_size: "5G"
rediacc_app_source: ""         # Local path to app files
rediacc_app_template: ""       # Template file path (alternative to source)
rediacc_app_autostart: true
rediacc_app_verify_health: true
rediacc_app_health_retries: 10
rediacc_app_health_delay: 5
rediacc_sync_verify: true
rediacc_sync_mirror: false
rediacc_snapshot_before_deploy: false
```

### tasks/main.yml
```yaml
- name: Validate required variables
  ansible.builtin.assert:
    that:
      - rediacc_app_name | length > 0
      - rediacc_app_source | length > 0 or rediacc_app_template | length > 0
    fail_msg: "Either rediacc_app_source or rediacc_app_template must be set"
  tags: [always]

- name: Check if repository exists
  rediacc.console.rediacc_machine_info:
    machine: "{{ inventory_hostname }}"
    query: repos
  register: existing_repos
  changed_when: false
  tags: [rediacc_deploy]

- name: Create repository
  rediacc.console.rediacc_repo:
    name: "{{ rediacc_app_name }}"
    machine: "{{ inventory_hostname }}"
    state: present
    size: "{{ rediacc_app_size }}"
  when: rediacc_app_name not in (existing_repos.json | default([]) | map(attribute='name', default='') | list)
  tags: [rediacc_deploy]

- name: Snapshot before deploy
  rediacc.console.rediacc_snapshot:
    repository: "{{ rediacc_app_name }}"
    machine: "{{ inventory_hostname }}"
    state: present
  when: rediacc_snapshot_before_deploy | bool
  tags: [rediacc_snapshot]

- name: Apply template
  rediacc.console.rediacc_template:
    name: "{{ rediacc_app_name }}"
    machine: "{{ inventory_hostname }}"
    template_file: "{{ rediacc_app_template }}"
  when: rediacc_app_template | length > 0
  tags: [rediacc_deploy]

- name: Upload application files
  rediacc.console.rediacc_sync:
    machine: "{{ inventory_hostname }}"
    repository: "{{ rediacc_app_name }}"
    direction: upload
    local_path: "{{ rediacc_app_source }}"
    verify: "{{ rediacc_sync_verify }}"
    mirror: "{{ rediacc_sync_mirror }}"
  when: rediacc_app_source | length > 0
  tags: [rediacc_sync]

- name: Deploy repository
  rediacc.console.rediacc_repo:
    name: "{{ rediacc_app_name }}"
    machine: "{{ inventory_hostname }}"
    state: started
  notify: rediacc_state_changed
  tags: [rediacc_deploy]

- name: Enable autostart
  rediacc.console.rediacc_autostart:
    name: "{{ rediacc_app_name }}"
    machine: "{{ inventory_hostname }}"
    state: enabled
  when: rediacc_app_autostart | bool
  tags: [rediacc_autostart]

- name: Wait for containers to be healthy
  rediacc.console.rediacc_machine_info:
    machine: "{{ inventory_hostname }}"
    query: containers
  register: containers
  until: >-
    containers.json | default([])
    | selectattr('repository', 'equalto', rediacc_app_name)
    | selectattr('state', 'equalto', 'running')
    | list | length > 0
  retries: "{{ rediacc_app_health_retries }}"
  delay: "{{ rediacc_app_health_delay }}"
  when: rediacc_app_verify_health | bool
  tags: [rediacc_health]
```

### Usage
```yaml
# Deploy to all machines in parallel
- hosts: workers
  strategy: free
  roles:
    - role: rediacc.console.deploy_app
      vars:
        rediacc_app_name: my-app
        rediacc_app_source: ./my-app/
        rediacc_app_size: 10G

# Rolling deploy (2 at a time, with health checks)
- hosts: workers
  serial: 2
  roles:
    - role: rediacc.console.deploy_app
      vars:
        rediacc_app_name: my-app
        rediacc_app_source: ./my-app/
        rediacc_snapshot_before_deploy: true
```

---

## Role 3: `migrate_repo`

**Purpose**: Migrate a repository from one machine to another (with optional live migration).

```
roles/migrate_repo/
├── tasks/main.yml
├── defaults/main.yml
└── README.md
```

### defaults/main.yml
```yaml
rediacc_migrate_repo: ""         # Required
rediacc_migrate_source: ""       # Required
rediacc_migrate_target: ""       # Required
rediacc_migrate_checkpoint: false  # CRIU live migration
rediacc_migrate_stop_source: false # Stop on source after migration
rediacc_migrate_verify: true
```

### tasks/main.yml
```yaml
- name: Validate migration parameters
  ansible.builtin.assert:
    that:
      - rediacc_migrate_repo | length > 0
      - rediacc_migrate_source | length > 0
      - rediacc_migrate_target | length > 0
      - rediacc_migrate_source != rediacc_migrate_target
    fail_msg: "Migration requires repo, source, and target (source != target)"
  run_once: true
  delegate_to: localhost

- name: Check source repo status
  rediacc.console.rediacc_machine_info:
    machine: "{{ rediacc_migrate_source }}"
    query: containers
  register: source_containers
  delegate_to: localhost

- name: Backup push to target
  rediacc.console.rediacc_backup:
    repository: "{{ rediacc_migrate_repo }}"
    machine: "{{ rediacc_migrate_source }}"
    direction: push
    to_machine: "{{ rediacc_migrate_target }}"
    checkpoint: "{{ rediacc_migrate_checkpoint }}"
  delegate_to: localhost

- name: Deploy on target
  rediacc.console.rediacc_repo:
    name: "{{ rediacc_migrate_repo }}"
    machine: "{{ rediacc_migrate_target }}"
    state: started
    mount: true
    checkpoint: "{{ rediacc_migrate_checkpoint }}"
  delegate_to: localhost

- name: Verify target containers
  rediacc.console.rediacc_machine_info:
    machine: "{{ rediacc_migrate_target }}"
    query: containers
  register: target_containers
  until: >-
    target_containers.json | default([])
    | selectattr('repository', 'equalto', rediacc_migrate_repo)
    | selectattr('state', 'equalto', 'running')
    | list | length > 0
  retries: 10
  delay: 5
  delegate_to: localhost
  when: rediacc_migrate_verify | bool

- name: Stop source after successful migration
  rediacc.console.rediacc_repo:
    name: "{{ rediacc_migrate_repo }}"
    machine: "{{ rediacc_migrate_source }}"
    state: stopped
    unmount: true
  delegate_to: localhost
  when: rediacc_migrate_stop_source | bool
```

### Usage
```yaml
- hosts: localhost
  tasks:
    - name: Migrate gitlab to new server
      ansible.builtin.include_role:
        name: rediacc.console.migrate_repo
      vars:
        rediacc_migrate_repo: gitlab
        rediacc_migrate_source: old-server
        rediacc_migrate_target: new-server
        rediacc_migrate_checkpoint: true
        rediacc_migrate_stop_source: true
```

---

## Role 4: `backup_fleet`

**Purpose**: Run backup across all machines in the fleet.

### tasks/main.yml
```yaml
- name: Configure and push backup schedule
  rediacc.console.rediacc_backup_schedule:
    state: present
    destination: "{{ rediacc_backup_storage }}"
    cron: "{{ rediacc_backup_cron }}"
    enabled: true
    machine: "{{ inventory_hostname }}"
  tags: [rediacc_backup_schedule]

- name: Run immediate backup sync
  rediacc.console.rediacc_backup_sync:
    machine: "{{ inventory_hostname }}"
    direction: push
    storage: "{{ rediacc_backup_storage }}"
  when: rediacc_backup_immediate | default(false) | bool
  tags: [rediacc_backup_sync]
```

### Usage
```yaml
- hosts: all_machines
  serial: 3  # 3 machines backing up at once
  roles:
    - role: rediacc.console.backup_fleet
      vars:
        rediacc_backup_storage: s3-backups
        rediacc_backup_cron: "0 2 * * *"
        rediacc_backup_immediate: true
```

---

## Role 5: `disaster_recovery`

**Purpose**: Restore all repos on a machine from backup storage.

### defaults/main.yml
```yaml
rediacc_dr_storage: ""           # Required: storage name
rediacc_dr_target_machine: ""    # Required: machine to restore to
rediacc_dr_repos: []             # Optional: specific repos (default: all)
rediacc_dr_autostart_after: true
```

### tasks/main.yml
```yaml
- name: Ensure target machine is set up
  rediacc.console.rediacc_machine:
    name: "{{ rediacc_dr_target_machine }}"
    state: setup
  delegate_to: localhost

- name: List available backups
  rediacc.console.rediacc_backup_info:
    storage: "{{ rediacc_dr_storage }}"
  register: available_backups
  delegate_to: localhost

- name: Pull backups from storage
  rediacc.console.rediacc_backup_sync:
    machine: "{{ rediacc_dr_target_machine }}"
    direction: pull
    storage: "{{ rediacc_dr_storage }}"
    repos: "{{ rediacc_dr_repos if rediacc_dr_repos | length > 0 else omit }}"
    override: true
  delegate_to: localhost

- name: Deploy all repos
  rediacc.console.rediacc_repo:
    name: "{{ item }}"
    machine: "{{ rediacc_dr_target_machine }}"
    state: started
    mount: true
  loop: "{{ rediacc_dr_repos if rediacc_dr_repos | length > 0 else available_backups.json | default([]) | map(attribute='name') | list }}"
  delegate_to: localhost

- name: Enable autostart for all restored repos
  rediacc.console.rediacc_autostart:
    name: "{{ item }}"
    machine: "{{ rediacc_dr_target_machine }}"
    state: enabled
  loop: "{{ rediacc_dr_repos if rediacc_dr_repos | length > 0 else available_backups.json | default([]) | map(attribute='name') | list }}"
  delegate_to: localhost
  when: rediacc_dr_autostart_after | bool

- name: Verify health
  rediacc.console.rediacc_machine_info:
    machine: "{{ rediacc_dr_target_machine }}"
    query: health
  register: dr_health
  delegate_to: localhost

- name: Report DR status
  ansible.builtin.debug:
    msg: >-
      Disaster recovery complete for {{ rediacc_dr_target_machine }}.
      Health: {{ dr_health.json.status | default('unknown') }}.
      Repos restored: {{ rediacc_dr_repos | length if rediacc_dr_repos | length > 0 else 'all' }}.
```

### Usage
```yaml
# Restore everything to a fresh machine
- hosts: localhost
  tasks:
    - ansible.builtin.include_role:
        name: rediacc.console.disaster_recovery
      vars:
        rediacc_dr_storage: s3-backups
        rediacc_dr_target_machine: new-server-1
```

---

## Example Playbooks

### playbooks/deploy.yml
```yaml
---
# Deploy an application across a fleet of machines
# Usage: ansible-playbook -i rediacc.yml deploy.yml -e app_name=my-app -e app_source=./my-app/
- hosts: workers
  serial: "{{ deploy_batch_size | default(2) }}"
  max_fail_percentage: 0

  roles:
    - role: rediacc.console.deploy_app
      vars:
        rediacc_app_name: "{{ app_name }}"
        rediacc_app_source: "{{ app_source }}"
        rediacc_app_size: "{{ app_size | default('5G') }}"
        rediacc_snapshot_before_deploy: "{{ snapshot | default(true) }}"
```

### playbooks/health_check.yml
```yaml
---
# Fleet-wide health check
# Usage: ansible-playbook -i rediacc.yml health_check.yml
- hosts: all
  gather_facts: false

  tasks:
    - name: Check machine health
      rediacc.console.rediacc_machine_info:
        machine: "{{ inventory_hostname }}"
        query: health
      register: health

    - name: Check containers
      rediacc.console.rediacc_machine_info:
        machine: "{{ inventory_hostname }}"
        query: containers
      register: containers

    - name: Report unhealthy machines
      ansible.builtin.debug:
        msg: "UNHEALTHY: {{ inventory_hostname }} - {{ health.json | default({}) }}"
      when: health.json.status | default('unknown') != 'healthy'

    - name: Report unhealthy containers
      ansible.builtin.debug:
        msg: "Container {{ item.name }} on {{ inventory_hostname }}: {{ item.health }}"
      loop: "{{ containers.json | default([]) }}"
      when: item.health | default('none') == 'unhealthy'
```
