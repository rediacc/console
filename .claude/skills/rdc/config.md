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
Provisions everything needed to run repositories. Idempotent — safe to re-run. Defaults: datastore `/mnt/rediacc`, size `95%`.

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
rdc config set-infra <machine> [--domain <domain>] [--email <email>]
```

### Push infra to machine
```
rdc config push-infra <machine>
```
Installs Traefik reverse proxy and rediacc-router. Required for HTTPS routing.

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
