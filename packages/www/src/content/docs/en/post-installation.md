---
title: "Post-Installation"
description: "Autostart configuration, context structure, and troubleshooting for Rediacc."
category: "Getting Started"
order: 3
language: en
---

# Post-Installation

After completing the [Step-by-Step Guide](/en/docs/guide), this page covers autostart configuration, understanding the context config file, and troubleshooting common issues.

## Autostart on Boot

By default, repositories must be manually mounted and started after a server reboot. **Autostart** configures repositories to automatically mount, start Docker, and run Rediaccfile `up()` when the server boots.

### How It Works

When you enable autostart for a repository:

1. A 256-byte random LUKS keyfile is generated and added to the repository's LUKS slot 1 (slot 0 remains the user passphrase).
2. The keyfile is stored at `{datastore}/.credentials/keys/{guid}.key` with `0600` permissions (root-only).
3. A systemd service (`rediacc-autostart`) is installed that runs at boot to mount all enabled repositories and start their services.

On system shutdown or reboot, the service gracefully stops all services (Rediaccfile `down()`), stops Docker daemons, and closes LUKS volumes.

> **Security note:** Enabling autostart stores a LUKS keyfile on the server's disk. Anyone with root access to the server can mount the repository without the passphrase. This is a trade-off between convenience (auto-boot) and security (requiring manual passphrase entry). Evaluate this based on your threat model.

### Enable Autostart

```bash
rdc repo autostart enable my-app -m server-1
```

You will be prompted for the repository passphrase. This is needed to authorize adding the keyfile to the LUKS volume.

### Enable Autostart for All Repositories

```bash
rdc repo autostart enable-all -m server-1
```

### Disable Autostart

```bash
rdc repo autostart disable my-app -m server-1
```

This removes the keyfile and kills LUKS slot 1. The repository will no longer mount automatically on boot.

### List Autostart Status

```bash
rdc repo autostart list -m server-1
```

Shows which repositories have autostart enabled and whether the systemd service is installed.

## Understanding the Context Config

All context configuration is stored in `~/.rediacc/config.json`. Here is an annotated example of what this file looks like after completing the guide:

```json
{
  "contexts": {
    "production": {
      "name": "production",
      "mode": "local",
      "apiUrl": "local://",
      "ssh": {
        "privateKeyPath": "/home/you/.ssh/id_ed25519"
      },
      "machines": {
        "prod-1": {
          "ip": "203.0.113.50",
          "user": "deploy",
          "port": 22,
          "datastore": "/mnt/rediacc",
          "knownHosts": "203.0.113.50 ssh-ed25519 AAAA..."
        }
      },
      "repositories": {
        "webapp": {
          "repositoryGuid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
          "credential": "base64-encoded-random-passphrase",
          "networkId": 2816
        }
      }
    }
  }
}
```

**Key fields:**

| Field | Description |
|-------|-------------|
| `mode` | `"local"` for local mode, `"s3"` for S3-backed contexts. |
| `apiUrl` | `"local://"` indicates local mode (no remote API). |
| `ssh.privateKeyPath` | Path to the SSH private key used for all machine connections. |
| `machines.<name>.knownHosts` | SSH host keys from `ssh-keyscan`, used to verify server identity. |
| `repositories.<name>.repositoryGuid` | UUID identifying the encrypted disk image on the server. |
| `repositories.<name>.credential` | LUKS encryption passphrase. **Not stored on the server.** |
| `repositories.<name>.networkId` | Network ID determining the IP subnet (2816 + n*64). Auto-assigned. |

> This file contains sensitive data (SSH key paths, LUKS credentials). It is stored with `0600` permissions (owner read/write only). Do not share it or commit it to version control.

## Troubleshooting

### SSH Connection Fails

- Verify you can connect manually: `ssh -i ~/.ssh/id_ed25519 deploy@203.0.113.50`
- Run `rdc context scan-keys server-1` to refresh host keys
- Check that the SSH port matches: `--port 22`

### Setup Machine Fails

- Ensure the user has sudo access without a password, or configure `NOPASSWD` for the required commands
- Check available disk space on the server
- Run with `--debug` for verbose output: `rdc context setup-machine server-1 --debug`

### Repository Create Fails

- Verify setup was completed: the datastore directory must exist
- Check disk space on the server
- Ensure the renet binary is installed (run setup again if needed)

### Services Fail to Start

- Check the Rediaccfile syntax: it must be valid Bash
- Ensure `docker compose` files use `network_mode: host`
- Verify Docker images are accessible (consider `docker compose pull` in `prep()`)
- Check container logs: SSH into the server and use `docker -H unix:///var/run/rediacc/docker-{networkId}.sock logs {container}`

### Permission Denied Errors

- Repository operations require root on the server (renet runs via `sudo`)
- Verify your user is in the `sudo` group
- Check that the datastore directory has correct permissions

### Run Diagnostics

Use the built-in doctor command to diagnose issues:

```bash
rdc doctor
```

This checks your environment, renet installation, context configuration, and authentication status.
