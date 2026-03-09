# rdc config — Machine Registration & SSH

Manage config files, machine inventory, SSH keys, and machine setup.

## Machine management

### Add a machine
```
rdc config add-machine <name> --ip <address> --user <username> [--port <port>] [--datastore <path>]
```
Registers a machine and auto-scans SSH host keys. Defaults: port 22, datastore `/mnt/rediacc`.

### List machines
```
rdc config machines
```

### Remove a machine
```
rdc config remove-machine <name>
```

### Set default machine
```
rdc config set machine <name>
```
Sets the default machine so `-m` flag can be omitted in other commands.

## SSH configuration

### Set SSH keys
```
rdc config set-ssh --private-key <path> [--public-key <path>]
```
Updates the SSH key used by the CLI for all remote operations (SFTP, rsync, provisioning).

**For ops VMs**: VMs created with `rdc ops up` trust a staging key. Set it with:
```
rdc config set-ssh --private-key ~/.renet/staging/.ssh/id_rsa --public-key ~/.renet/staging/.ssh/id_rsa.pub
```

### Scan host keys
```
rdc config scan-keys [machine]
```
Re-scans SSH host keys. Run after VM re-provisioning if host key changes.

## Machine setup

### Setup a machine
```
rdc config setup-machine <name> [--datastore <path>] [--datastore-size <size>]
```
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
```
rdc config show
```

### Create named config
```
rdc config init <name> [--ssh-key <path>]
```
Default config at `~/.config/rediacc/rediacc.json` is auto-created on first use. Use `init` only for additional named configs.

### List configs
```
rdc config list
```

### Use a specific config
```
rdc --config <name> <command>
```

## Infrastructure (Traefik proxy)

### Configure infra
```
rdc config set-infra <machine> [--base-domain <domain>] [--public-ipv4 <ip>] [--public-ipv6 <ip>] [--cert-email <email>] [--cf-dns-token <token>] [--tcp-ports <ports>] [--udp-ports <ports>]
```

- `--base-domain`, `--public-ipv4`, `--public-ipv6`, `--tcp-ports`, `--udp-ports` are per-machine.
- `--cert-email`, `--cf-dns-token` are shared across all machines in the config.
- Machine name is automatically sent to renet as `machine_name` for subdomain routing (e.g., `*.server-1.example.com`).
- Proxy entrypoints are only generated for configured address families (IPv4-only machines get no IPv6 entrypoints, and vice versa).

### View infra
```
rdc config show-infra <machine>
```
Shows base domain, public IPs, TLS email, and port forwarding config. Also visible in `rdc machine info <machine>`.

### Push infra to machine
```
rdc config push-infra <machine>
```
Installs Traefik reverse proxy and rediacc-router with `--machine-name`. Also creates Cloudflare DNS records (`{machineName}.{baseDomain}` and `*.{machineName}.{baseDomain}`) if `--cf-dns-token` is set. Required for HTTPS routing. Auto-routes use machine subdomains: `{service}-{id}.{machineName}.{baseDomain}`.

## Cloud provisioning (OpenTofu)

### Add a cloud provider
```
rdc config add-provider <name> --provider <source> --token <token> [--region <r>] [--type <t>] [--image <i>]
```
Registers a cloud provider for automated VM provisioning. Known providers: `linode/linode`, `hetznercloud/hcloud`. Use `--source` instead of `--provider` for custom providers with manual attribute mapping.

### List cloud providers
```
rdc config providers
```

### Remove a cloud provider
```
rdc config remove-provider <name>
```

### Provision a machine
```
rdc machine provision <name> --provider <provider-name> [--region <r>] [--type <t>] [--image <i>] [--base-domain <domain>] [--no-infra] [--debug]
```
Creates a VM via OpenTofu, waits for SSH, registers the machine, installs renet, and runs setup. Auto-detects `baseDomain` from sibling machines in the config; use `--base-domain` to override or `--no-infra` to skip infrastructure setup entirely. Requires `tofu` binary on PATH.

### Deprovision a machine
```
rdc machine deprovision <name> [--force] [--debug]
```
Destroys a cloud-provisioned VM via OpenTofu and removes from config. Only works for machines created with `machine provision`.

### Workflow: Cloud-provisioned machine
```bash
rdc config set-ssh --private-key ~/.ssh/id_ed25519 --public-key ~/.ssh/id_ed25519.pub
rdc config add-provider my-linode --provider linode/linode --token $TOKEN --region us-east
rdc machine provision prod-1 --provider my-linode
# baseDomain auto-detected from sibling machines (or pass --base-domain example.com)
# Now ready for: rdc repo create <name> -m prod-1 --size 5G
```

## Backup strategy

### Configure backup strategy
```
rdc config backup-strategy set [--destination <name>] [--cron <expr>] [--enable] [--retention <count>]
```
Configures automated backup schedule. Multiple destinations supported.

### Show backup strategy
```
rdc config backup-strategy show
```

## Repository GUID mappings

### List repositories
```
rdc config repositories
```

### Add repository mapping
```
rdc config add-repository <name> [--guid <guid>] [--network-id <id>]
```

### Remove repository mapping
```
rdc config remove-repository <name>
```

## Workflow: New machine from scratch

```bash
rdc config add-machine myserver --ip 10.0.0.1 --user deploy
rdc config set-ssh --private-key ~/.ssh/id_ed25519
rdc config setup-machine myserver
# Now ready for: rdc repo create <name> -m myserver --size 5G
```

## Workflow: Ops VM

```bash
rdc ops up --basic --parallel
rdc config add-machine rediacc11 --ip 192.168.111.11 --user muhammed
rdc config set-ssh --private-key ~/.renet/staging/.ssh/id_rsa --public-key ~/.renet/staging/.ssh/id_rsa.pub
rdc config setup-machine rediacc11
```
