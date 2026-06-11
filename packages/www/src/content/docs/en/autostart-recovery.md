---
title: "Autostart & Recovery"
description: "How autostart works, the periodic reconciler that recovers repositories that go down after boot, and how to inspect recovery state."
category: "Guides"
order: 5
language: en
---

# Autostart & Recovery

Repositories with autostart enabled come up on their own at boot. If one goes down afterward, the periodic reconciler brings it back. No prompts. No manual restart.

For how to enable or disable autostart on a repository, see [Services: Autostart on Boot](/en/docs/services#autostart-on-boot).

## How Autostart Works

When you enable autostart for a repository, Rediacc generates a 256-byte random LUKS keyfile and adds it to LUKS slot 1 on the encrypted volume. The keyfile is stored at:

```
{datastore}/.credentials/keys/{guid}.key
```

This lets the machine mount the repository without prompting for the passphrase. LUKS slot 0 (your passphrase) is not changed.

The keyfile slot uses the fast PBKDF2 KDF: a 256-byte random keyfile is its own security margin, so a memory-hard KDF would add unlock latency without adding protection. Mounts open in well under a second. Repositories created before this optimization still pay a multi-second Argon2id derivation per mount; convert them in place (repository unmounted) with the operator command `renet repository kdf-migrate --name <guid>` on the machine. Slot 0 keeps Argon2id, the right choice for a human passphrase.

At boot, a one-shot systemd service named `rediacc-autostart.service` reads the list of autostart-enabled repositories, mounts each one using its keyfile, starts the per-repo Docker daemon, and runs the Rediaccfile `up()` hook. On shutdown, the service runs `down()`, stops Docker, and closes the LUKS volumes.

> **Security note:** The keyfile gives root-level access to the repository without the passphrase. Anyone with root access to the server can mount autostart-enabled repositories. Evaluate this against your threat model before enabling autostart on sensitive repos.

## The Recovery Gap

Boot autostart runs exactly once per boot. The router watchdog, which runs continuously after that, only restarts *containers inside an already-running repo with a running Docker daemon*. It cannot re-mount a LUKS volume or restart a per-network Docker daemon that has stopped.

This means that if a repository's LUKS volume is unmounted or its Docker daemon stops after the server has booted, neither the boot service nor the watchdog will recover it. Before the reconciler existed, a repo in this state stayed down until an operator intervened.

## Periodic Reconciler

The `rediacc-autostart-reconcile.timer` systemd timer fires about every 3 minutes and runs `renet repository reconcile`. For each autostart-enabled repository, the reconciler checks three things:

1. Is the LUKS volume mounted?
2. Is the per-network Docker daemon running?
3. Are the repository's services up?

If any check fails, the reconciler recovers the repository using its keyfile: it mounts the volume, starts the Docker daemon, and runs `up()`. No passphrase is required.

Repositories that are healthy, currently owned by a cold backup run, or within their back-off window are skipped.

### Back-off and Persistent Failure Markers

A repository that fails to recover does not immediately retry on every tick. The reconciler uses exponential back-off:

| Failure count | Wait before next attempt |
|---------------|--------------------------|
| 1 | 1 minute |
| 2 | 2 minutes |
| 3 | 5 minutes |
| 4 | 15 minutes |
| 5+ | 30 minutes, then 60 minutes |

After 5 consecutive failures, the reconciler writes a durable marker file at:

```
/var/lib/rediacc/reconcile/failed/{guid}
```

This file survives log rotation. Its presence means the repository requires operator attention. The reconciler logs the failure at error level and stops attempting automatic recovery for that repository until the marker is cleared.

Common causes of persistent recovery failure:

- **Untrusted or expired repo license**: the license check runs before `up()`.
- **Missing keyfile**: if the keyfile at `{datastore}/.credentials/keys/{guid}.key` was deleted, the reconciler cannot mount the volume without a passphrase.
- **Broken Rediaccfile**: a syntax error or an `up()` hook that always exits non-zero.

### Relationship to the Router Watchdog

The reconciler and the router watchdog handle different levels of failure and are designed to complement each other:

| Layer | What it handles |
|-------|-----------------|
| **Router watchdog** | Container-level restarts inside a running, mounted repo with a live Docker daemon |
| **Reconciler (`rediacc-autostart-reconcile.timer`)** | Repository-level recovery: re-mounting LUKS, restarting the Docker daemon, re-running `up()` |

If a single container crashes inside a healthy repo, the watchdog handles it. If the whole repo daemon stops, the reconciler handles it.

## Inspecting Recovery State

### Timer and service status

```bash
systemctl status rediacc-autostart-reconcile.timer
systemctl list-timers rediacc-autostart-reconcile.timer
```

### Reconciler logs

```bash
journalctl -u rediacc-autostart-reconcile.service
journalctl -u rediacc-autostart-reconcile.service --since "1 hour ago"
```

### Persistent failure markers

List repositories with durable failure markers:

```bash
ls /var/lib/rediacc/reconcile/failed/
```

Each filename is a repository GUID. Cross-reference with `rdc config repository list` to map GUIDs to repository names.

To clear a marker after you have resolved the underlying issue, delete the file:

```bash
rm /var/lib/rediacc/reconcile/failed/{guid}
```

The reconciler will attempt recovery again on the next timer tick.

## Related Pages

- [Services: Autostart on Boot](/en/docs/services#autostart-on-boot): enabling and disabling autostart, keyfile management
- [Backup & Restore](/en/docs/backup-restore): cold backup interaction with running services
