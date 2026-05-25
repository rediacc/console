---
title: "Troubleshooting"
description: "Solutions for common issues with SSH, setup, repositories, services, and Docker."
category: "Guides"
order: 10
language: en
---

# Troubleshooting

Common issues and their solutions. When in doubt, start with `rdc doctor` to run a comprehensive diagnostic check.

## SSH Connection Fails

- Verify you can connect manually: `ssh -i ~/.ssh/id_ed25519 deploy@203.0.113.50`
- Run `rdc config machine scan-keys -m server-1` to refresh host keys
- Check that the SSH port matches: `--port 22`
- Test with a simple command: `rdc term connect -m server-1 -c "hostname"`

## Host Key Mismatch

If a server was reinstalled or its SSH keys changed, you'll see "host key verification failed":

```bash
rdc config machine scan-keys -m server-1
```

This fetches fresh host keys and updates your config.

## Setup Machine Fails

- Ensure the SSH user has sudo access without a password, or configure `NOPASSWD` for the required commands
- Check available disk space on the server
- Run with `--debug` for verbose output: `rdc config machine setup --name server-1 --debug`

## Distribution-Specific Setup Issues

The five officially supported server OSes (Ubuntu 24.04, Debian 13, Fedora 43, openSUSE Leap 16.0, Oracle Linux 10) ship with different security policies and package managers. Most setups "just work"; the cases below cover the ones that don't.

### SELinux denials (Fedora 43, Oracle Linux 10)

Both run SELinux in enforcing mode. rdc setup does not install a custom SELinux policy; the per-repo docker daemon runs under the standard `container_t` context. If setup fails with AVC denials, check the audit log and identify the domain:

```bash
sudo ausearch -m AVC -ts recent | head -40
# Or:
sudo tail -f /var/log/audit/audit.log | grep AVC
```

If a denial points at the renet binary or a specific file path, the fix is almost always to relabel (`restorecon -v /path`) rather than to disable SELinux. As a temporary workaround while you investigate, `sudo setenforce 0` moves the system to permissive. Re-enable with `sudo setenforce 1` once you confirm the relabel sticks.

### AppArmor denials (Ubuntu 24.04, openSUSE Leap 16.0)

Both run AppArmor by default; the per-repo docker daemon uses the default container profile. If a container inside a repo is being blocked:

```bash
dmesg | grep -i apparmor
sudo aa-status
```

CRIU is the known case that hits AppArmor. Renet auto-sets `security_opt: apparmor=unconfined` on containers labeled `rediacc.checkpoint=true`. You should not need to configure AppArmor profiles yourself for anything else. See the CRIU notes in [Rules of Rediacc](/en/docs/rules-of-rediacc).

### Package manager error signatures

| OS | Package manager | Typical error | Resolution |
|----|-----------------|---------------|------------|
| Ubuntu / Debian | apt-get | `File has unexpected size (N != M). Mirror sync in progress?` | Cloudflare edge cache behind origin. Retry `apt-get update` after ~15s; the integrity check passes on the next poll. |
| Fedora / Oracle | dnf | `Problem: nothing provides rediacc-cli` | The RPM repo metadata cached on disk is stale. Run `sudo dnf clean all && sudo dnf makecache`. |
| openSUSE | zypper | `Repository 'rediacc' needs to be refreshed.` | Run `sudo zypper refresh rediacc` once; subsequent installs should succeed. |

### btrfs module missing (RHEL 10 / Rocky Linux 10 / AlmaLinux 10)

If `rdc config machine setup` or `renet system check-btrfs` fails with:

```
Module btrfs not found
```

...the server is running RHEL 10's stock kernel, which ships without the in-tree btrfs module. This is not a Rediacc bug; RHEL 10 dropped btrfs intentionally. The resolution is to run **Oracle Linux 10 instead**. Oracle 10 defaults to the Unbreakable Enterprise Kernel (UEK), which retains btrfs. See [Requirements → Why UEK?](/en/docs/requirements) for the full story.

## Repository Create Fails

- Verify setup was completed: the datastore directory must exist
- Check disk space on the server
- Ensure the renet binary is installed (run setup again if needed)

## Services Fail to Start

- Check the Rediaccfile syntax: it must be valid Bash
- Ensure your Rediaccfile uses `renet compose --` (not `docker compose`)
- Verify Docker images are accessible (consider `renet compose -- pull` in `up()`)
- Check container logs using the repository's Docker socket:

```bash
rdc term connect -m server-1 -r my-app -c "docker logs <container-name>"
```

Or view all containers:

```bash
rdc machine containers --name server-1
```

## Permission Denied Errors

- Repository operations require root on the server (renet runs via `sudo`)
- Verify your SSH user is in the `sudo` group
- Check that the datastore directory has correct permissions

## Docker Socket Issues

Each repository has its own Docker daemon. When running Docker commands manually, you must specify the correct socket:

```bash
# Using rdc term (auto-configured):
rdc term connect -m server-1 -r my-app -c "docker ps"

# Or manually with the socket:
docker -H unix:///var/run/rediacc/docker-2816.sock ps
```

Replace `2816` with your repository's network ID (found in `rediacc.json` or `rdc repo status`).

## `docker run` has no network, `apt update` fails, `curl` hangs

Inside a repository shell, running a container without `--network host` gives you an isolated container with only a loopback interface, no DNS, and no outbound connectivity. Commands like `apt update`, `pip install`, `curl https://...`, or any network fetch will fail immediately with DNS errors.

This is intentional. Rediacc's networking model is **host networking for every service**, enforced by `renet compose`. A default Docker bridge with NAT would bypass the kernel-level loopback isolation that prevents one repo from reaching another repo's services, so the per-repo Docker daemon (`FlavorRediacc`) is configured with `"bridge": "none"` and `"iptables": false`. There is no routable bridge for a plain `docker run` container to attach to. (Per-user Hub daemons (`FlavorHub`) used by development environments are the exception: they enable bridge + iptables so user-run containers have outbound networking.)

**To get network access in an ad-hoc container, use host networking:**

```bash
# Inside a repository shell (rdc term connect -m <machine> -r <repo>)
docker run --rm --network host -it ubuntu bash
# Now apt update, curl, pip install all work.
```

**For production services, use a Rediaccfile with `renet compose`** instead of raw `docker run`. `renet compose` injects `network_mode: host`, service IP labels, and Traefik routing labels automatically. See [Services](/en/docs/services) for details.

## VS Code Permission Denied on sandbox files

When connecting with `rdc vscode connect -m <machine> -r <repo>`, you may have seen errors like `scp: .../.vscode-server/vscode-cli-*.tar.gz: Permission denied` after a previous VS Code session. This was caused by mixed file ownership inside the sandbox directory, which held files written by both your SSH user and the internal `rediacc` user.

Modern versions of renet fix this by:

- Creating the per-repo sandbox workspace (`/mnt/rediacc/.interim/sandbox/<repo>/`) with group `rediacc` and the set-group-ID bit (mode `2775`), so every file written underneath inherits the correct group.
- Applying umask `002` inside the sandbox runtime so new files are created group-writable (`0664`/`0775`).
- Normalizing an existing `.vscode-server/` subtree on startup so stale files from before the fix get repaired automatically.

If you still see permission errors, restart the repo's Docker daemon once with `sudo systemctl restart rediacc-docker-<network-id>` from a shell on the machine so the normalization pass runs, then retry `rdc vscode connect`.

## Daemon fails to start after a renet upgrade

Before each start, `renet daemon start-foreground` rewrites `daemon.json` and `containerd.toml` in the repository's config directory from the current templates, so a repository whose config was generated by an older renet version automatically picks up the new format. You do not need to run any migration command, and you do not need to manually regenerate the systemd unit. Just restart the service:

```bash
sudo systemctl restart rediacc-docker-<network-id>
```

If the unit is still failing, check the journal for a specific error:

```bash
sudo journalctl -u rediacc-docker-<network-id> --no-pager -n 50
```

## Containers Created on Wrong Docker Daemon

If your containers appear on the host system's Docker daemon instead of the repository's isolated daemon, the most common cause is using `sudo docker` inside a Rediaccfile.

`sudo` resets environment variables, so `DOCKER_HOST` is lost and Docker defaults to the system socket (`/var/run/docker.sock`). Rediacc blocks this automatically, but if you encounter it:

- **Use `docker` directly**, Rediaccfile functions already run with sufficient privileges
- If you must use sudo, use `sudo -E docker` to preserve environment variables
- Check your Rediaccfile for any `sudo docker` commands and remove the `sudo`

## Terminal Not Working

If `rdc term` fails to open a terminal window:

- Use inline mode with `-c` to run commands directly:
  ```bash
  rdc term connect -m server-1 -c "ls -la"
  ```
- Force external terminal with `--external` if inline mode has issues
- On Linux, ensure you have `gnome-terminal`, `xterm`, or another terminal emulator installed

## Run Diagnostics

```bash
rdc doctor
```

This checks your environment, renet installation, config configuration, and authentication status. Each check reports OK, Warning, or Error with a brief explanation.
