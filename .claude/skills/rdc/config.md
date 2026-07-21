# rdc config / rdc machine — Machine Registration & SSH

For full command syntax and options, see [reference.md](reference.md).

Manage config files, machine inventory, SSH keys, and machine setup.

**Where things live now**: machine inventory and setup are under the `machine` noun
(`rdc machine add|remove|list|scan-keys|setup|provider|infra`), not under `config`.
`rdc config` keeps config-file concerns: `init`, `list`, `show`, `set`, `edit`, `ssh`,
`remote`, `field`, `audit`, `prune`, `reconcile`.

## Machine management

### Add a machine
`rdc machine add <name> --ip <ip> --user <username>` registers a machine and auto-scans SSH host keys. Defaults: port 22.

### List machines
`rdc machine list`

### Remove a machine
`rdc machine remove <name>`

## SSH configuration

### Set SSH keys
Updates the SSH key used by the CLI for all remote operations (SFTP, rsync, provisioning).

**For ops VMs**: VMs created with `rdc ops up` trust a staging key. Set it with:
```
rdc config ssh set --key ~/.renet/staging/.ssh/id_rsa
```

### Scan host keys
`rdc machine scan-keys <name>` re-scans SSH host keys. Run after VM re-provisioning if the host key changes.

## Machine setup

### Setup a machine
`rdc machine setup <name>` provisions everything needed to run repositories. Idempotent, so it is safe to re-run. Defaults: datastore `/mnt/rediacc`, size `95%` (override with `--datastore-path` / `--datastore-size`). After successful setup, automatically pushes infra if the machine has infrastructure configured.

What it does:
- Installs Docker and configures system-level Docker experimental mode
- Creates BTRFS datastore for encrypted volumes
- Installs CRIU from system packages (Ubuntu 24.04 uses OBS repository)
- Writes `/etc/criu/runc.conf` with `tcp-established` for TCP connection preservation during checkpoint
- Installs rsync and rclone for backup/sync operations
- Per-repo Docker daemons automatically get `"experimental": true` in their daemon.json (handled by renet, not setup-machine)

Required before creating repositories on a machine.

## Config management

### Show current config

### Create named config
Default config at `~/.config/rediacc/rediacc.json` is auto-created on first use. Use `init` only for additional named configs.

### List configs

### Use a specific config
Pass `--config <name>` to any `rdc` command.

## Infrastructure (Traefik proxy)

Infra lives under `rdc machine infra` (`set`, `show`, `push`, and `cert {pull,push,status,clear}`).
Each takes the machine positionally.

### Configure infra
`rdc machine infra set <machine> ...`
- `--base-domain`, `--public-ipv4`, `--public-ipv6`, `--tcp-ports`, `--udp-ports` are per-machine.
- `--cert-email`, `--cf-dns-token` are shared across all machines in the config.
- Machine name is automatically sent to renet as `machine_name` for subdomain routing (e.g., `*.server-1.example.com`).
- Proxy entrypoints are only generated for configured address families (IPv4-only machines get no IPv6 entrypoints, and vice versa).

### View infra
`rdc machine infra show <machine>` shows base domain, public IPs, TLS email, and port forwarding config. Also visible in `rdc machine status <machine>`.

### Push infra to machine
`rdc machine infra push <machine>` installs the Traefik reverse proxy and rediacc-router. Also creates Cloudflare DNS records (`{machineName}.{baseDomain}` and `*.{machineName}.{baseDomain}`) if `--cf-dns-token` is set. Required for HTTPS routing. Auto-routes use machine subdomains: `{service}-{id}.{machineName}.{baseDomain}`.

### Certificate cache
`rdc machine infra cert {pull,push,status,clear}` manages the local TLS certificate cache (`pull` and `push` take the machine positionally).

## Cloud provisioning (OpenTofu)

### Add a cloud provider
`rdc machine provider add <name> --provider <source> --token <token>` registers a cloud provider for automated VM provisioning. Known providers: `linode/linode`, `hetznercloud/hcloud`. Use `--source` instead of `--provider` for custom providers with manual attribute mapping.

### List cloud providers
`rdc machine provider list`

### Remove a cloud provider
`rdc machine provider remove <name>`

### Provision a machine
`rdc machine provision <name> --provider <provider>` creates a VM via OpenTofu, waits for SSH, registers the machine, installs renet, and runs setup. Auto-detects `baseDomain` from sibling machines in the config; use `--base-domain` to override or `--no-infra` to skip infrastructure setup entirely. Requires `tofu` binary on PATH.

### Deprovision a machine
`rdc machine deprovision <name>` destroys a cloud-provisioned VM via OpenTofu and removes it from the config. Only works for machines created with `machine provision`.

### Workflow: Cloud-provisioned machine
```bash
rdc config ssh set --key ~/.ssh/id_ed25519
rdc machine provider add my-linode --provider linode/linode --token $TOKEN --region us-east
rdc machine provision prod-1 --provider my-linode
# baseDomain auto-detected from sibling machines (or pass --base-domain example.com)
# Now ready for: rdc repo create <name> -m prod-1 --size 5G
```

## Backup strategy

Backup strategies moved to the `backup` noun: `rdc backup strategy {set,remove,list,show}`.
See [backup.md](backup.md).

## Repository records

Repository records live in the config and are managed by the repo lifecycle commands
(`rdc repo create` / `rdc repo delete`). List them with `rdc repo list`. Archived records
(from `repo delete --archive-config`) are handled by `rdc repo admin archive {list,restore,purge}`.

## Workflow: New machine from scratch

```bash
rdc machine add myserver --ip 10.0.0.1 --user deploy
rdc config ssh set --key ~/.ssh/id_ed25519
rdc machine setup myserver
# Now ready for: rdc repo create <name> -m myserver --size 5G
```

## Workflow: Ops VM

```bash
rdc ops up --basic --parallel
rdc machine add rediacc11 --ip 192.168.111.11 --user muhammed
rdc config ssh set --key ~/.renet/staging/.ssh/id_rsa
rdc machine setup rediacc11
```
