# rdc config — Machine Registration & SSH

For full command syntax and options, see [reference.md](reference.md).

Manage config files, machine inventory, SSH keys, and machine setup.

## Machine management

### Add a machine
Registers a machine and auto-scans SSH host keys. Defaults: port 22, datastore `/mnt/rediacc`.

### List machines

### Remove a machine

## SSH configuration

### Set SSH keys
Updates the SSH key used by the CLI for all remote operations (SFTP, rsync, provisioning).

**For ops VMs**: VMs created with `rdc ops up` trust a staging key. Set it with:
```
rdc config set-ssh --private-key ~/.renet/staging/.ssh/id_rsa --public-key ~/.renet/staging/.ssh/id_rsa.pub
```

### Scan host keys
Re-scans SSH host keys. Run after VM re-provisioning if host key changes.

## Machine setup

### Setup a machine
Provisions everything needed to run repositories. Idempotent — safe to re-run. Defaults: datastore `/mnt/rediacc`, size `95%`. After successful setup, automatically runs `push-infra` if the machine has infrastructure configured.

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

### Configure infra
- `--base-domain`, `--public-ipv4`, `--public-ipv6`, `--tcp-ports`, `--udp-ports` are per-machine.
- `--cert-email`, `--cf-dns-token` are shared across all machines in the config.
- Machine name is automatically sent to renet as `machine_name` for subdomain routing (e.g., `*.server-1.example.com`).
- Proxy entrypoints are only generated for configured address families (IPv4-only machines get no IPv6 entrypoints, and vice versa).

### View infra
Shows base domain, public IPs, TLS email, and port forwarding config. Also visible in `rdc machine query <machine>`.

### Push infra to machine
Installs Traefik reverse proxy and rediacc-router with `--machine-name`. Also creates Cloudflare DNS records (`{machineName}.{baseDomain}` and `*.{machineName}.{baseDomain}`) if `--cf-dns-token` is set. Required for HTTPS routing. Auto-routes use machine subdomains: `{service}-{id}.{machineName}.{baseDomain}`.

## Cloud provisioning (OpenTofu)

### Add a cloud provider
Registers a cloud provider for automated VM provisioning. Known providers: `linode/linode`, `hetznercloud/hcloud`. Use `--source` instead of `--provider` for custom providers with manual attribute mapping.

### List cloud providers

### Remove a cloud provider

### Provision a machine
Creates a VM via OpenTofu, waits for SSH, registers the machine, installs renet, and runs setup. Auto-detects `baseDomain` from sibling machines in the config; use `--base-domain` to override or `--no-infra` to skip infrastructure setup entirely. Requires `tofu` binary on PATH.

### Deprovision a machine
Destroys a cloud-provisioned VM via OpenTofu and removes from config. Only works for machines created with `machine provision`.

### Workflow: Cloud-provisioned machine
```bash
rdc config set-ssh --private-key ~/.ssh/id_ed25519 --public-key ~/.ssh/id_ed25519.pub
rdc config provider add my-linode --provider linode/linode --token $TOKEN --region us-east
rdc machine provision prod-1 --provider my-linode
# baseDomain auto-detected from sibling machines (or pass --base-domain example.com)
# Now ready for: rdc repo create <name> -m prod-1 --size 5G
```

## Backup strategy

### Configure backup strategy
Configures automated backup schedule. Multiple destinations supported.

### Show backup strategy

## Repository GUID mappings

### List repositories

### Add repository mapping

### Remove repository mapping

## Workflow: New machine from scratch

```bash
rdc config machine add myserver --ip 10.0.0.1 --user deploy
rdc config set-ssh --private-key ~/.ssh/id_ed25519
rdc config machine setup myserver
# Now ready for: rdc repo create <name> -m myserver --size 5G
```

## Workflow: Ops VM

```bash
rdc ops up --basic --parallel
rdc config machine add rediacc11 --ip 192.168.111.11 --user muhammed
rdc config set-ssh --private-key ~/.renet/staging/.ssh/id_rsa --public-key ~/.renet/staging/.ssh/id_rsa.pub
rdc config machine setup rediacc11
```
