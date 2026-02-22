---
title: "Repositories"
description: "Create, manage, and operate LUKS-encrypted repositories on remote machines."
category: "Guides"
order: 4
language: en
---

# Repositories

A **repository** is a LUKS-encrypted disk image on a remote server. When mounted, it provides:
- An isolated filesystem for your application data
- A dedicated Docker daemon (separate from the host's Docker)
- Unique loopback IPs for each service within a /26 subnet

## Create a Repository

```bash
rdc repo create my-app -m server-1 --size 10G
```

| Option | Required | Description |
|--------|----------|-------------|
| `-m, --machine <name>` | Yes | Target machine where the repository will be created |
| `--size <size>` | Yes | Size of the encrypted disk image (e.g., `5G`, `10G`, `50G`) |
| `--skip-router-restart` | No | Skip restarting the route server after the operation |

The output will show three auto-generated values:

- **Repository GUID** -- A UUID that identifies the encrypted disk image on the server.
- **Credential** -- A random passphrase used to encrypt/decrypt the LUKS volume.
- **Network ID** -- An integer (starting at 2816, incrementing by 64) that determines the IP subnet for this repository's services.

> **Store the credential securely.** It is the encryption key for your repository. If lost, data cannot be recovered. The credential is stored in your local `config.json` but is not stored on the server.

## Mount and Unmount

Mount decrypts and makes the repository filesystem accessible. Unmount closes the encrypted volume.

```bash
rdc repo mount my-app -m server-1       # Decrypt and mount
rdc repo unmount my-app -m server-1     # Unmount and re-encrypt
```

| Option | Description |
|--------|-------------|
| `--checkpoint` | Create a checkpoint before mount/unmount |
| `--skip-router-restart` | Skip restarting the route server after the operation |

## Check Status

```bash
rdc repo status my-app -m server-1
```

## List Repositories

```bash
rdc repo list -m server-1
```

## Resize

Set the repository to an exact size or expand by a given amount:

```bash
rdc repo resize my-app -m server-1 --size 20G    # Set to exact size
rdc repo expand my-app -m server-1 --size 5G      # Add 5G to current size
```

> The repository must be unmounted before resizing.

## Fork

Create a copy of an existing repository at its current state:

```bash
rdc repo fork my-app -m server-1 --tag my-app-staging
```

This creates a new encrypted copy with its own GUID and network ID. The fork shares the same LUKS credential as the parent.

## Validate

Check the filesystem integrity of a repository:

```bash
rdc repo validate my-app -m server-1
```

## Ownership

Set file ownership within a repository to the universal user (UID 7111). This is typically needed after uploading files from your workstation, which arrive with your local UID.

```bash
rdc repo ownership my-app -m server-1
```

The command automatically detects Docker container data directories (writable bind mounts) and excludes them. This prevents breaking containers that manage files with their own UIDs (e.g., MariaDB=999, www-data=33).

| Option | Description |
|--------|-------------|
| `--uid <uid>` | Set a custom UID instead of 7111 |
| `--force` | Skip Docker volume detection and chown everything |
| `--skip-router-restart` | Skip restarting the route server after the operation |

To force ownership on all files, including container data:

```bash
rdc repo ownership my-app -m server-1 --force
```

> **Warning:** Using `--force` on running containers may break them. Stop services first with `rdc repo down` if needed.

See the [Migration Guide](/en/docs/migration) for a complete walkthrough of when and how to use ownership during project migration.

## Template

Apply a template to initialize a repository with files:

```bash
rdc repo template my-app -m server-1 --file ./my-template.tar.gz
```

## Delete

Permanently destroy a repository and all data inside it:

```bash
rdc repo delete my-app -m server-1
```

> This permanently destroys the encrypted disk image. This action cannot be undone.
