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
- Run `rdc context scan-keys server-1` to refresh host keys
- Check that the SSH port matches: `--port 22`
- Test connectivity: `rdc machine test-connection --ip 203.0.113.50 --user deploy`

## Host Key Mismatch

If a server was reinstalled or its SSH keys changed, you'll see "host key verification failed":

```bash
rdc context scan-keys server-1
```

This fetches fresh host keys and updates your config.

## Setup Machine Fails

- Ensure the SSH user has sudo access without a password, or configure `NOPASSWD` for the required commands
- Check available disk space on the server
- Run with `--debug` for verbose output: `rdc context setup-machine server-1 --debug`

## Repository Create Fails

- Verify setup was completed: the datastore directory must exist
- Check disk space on the server
- Ensure the renet binary is installed (run setup again if needed)

## Services Fail to Start

- Check the Rediaccfile syntax: it must be valid Bash
- Ensure `docker compose` files use `network_mode: host`
- Verify Docker images are accessible (consider `docker compose pull` in `prep()`)
- Check container logs using the repository's Docker socket:

```bash
rdc term server-1 my-app -c "docker logs <container-name>"
```

Or view all containers:

```bash
rdc machine containers server-1
```

## Permission Denied Errors

- Repository operations require root on the server (renet runs via `sudo`)
- Verify your SSH user is in the `sudo` group
- Check that the datastore directory has correct permissions

## Docker Socket Issues

Each repository has its own Docker daemon. When running Docker commands manually, you must specify the correct socket:

```bash
# Using rdc term (auto-configured):
rdc term server-1 my-app -c "docker ps"

# Or manually with the socket:
docker -H unix:///var/run/rediacc/docker-2816.sock ps
```

Replace `2816` with your repository's network ID (found in `config.json` or `rdc repo status`).

## Containers Created on Wrong Docker Daemon

If your containers appear on the host system's Docker daemon instead of the repository's isolated daemon, the most common cause is using `sudo docker` inside a Rediaccfile.

`sudo` resets environment variables, so `DOCKER_HOST` is lost and Docker defaults to the system socket (`/var/run/docker.sock`). Rediacc blocks this automatically, but if you encounter it:

- **Use `docker` directly** — Rediaccfile functions already run with sufficient privileges
- If you must use sudo, use `sudo -E docker` to preserve environment variables
- Check your Rediaccfile for any `sudo docker` commands and remove the `sudo`

## Terminal Not Working

If `rdc term` fails to open a terminal window:

- Use inline mode with `-c` to run commands directly:
  ```bash
  rdc term server-1 -c "ls -la"
  ```
- Force external terminal with `--external` if inline mode has issues
- On Linux, ensure you have `gnome-terminal`, `xterm`, or another terminal emulator installed

## Run Diagnostics

```bash
rdc doctor
```

This checks your environment, renet installation, context configuration, and authentication status. Each check reports OK, Warning, or Error with a brief explanation.
