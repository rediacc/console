---
title: "Repositories"
description: "Create, manage, and operate LUKS-encrypted repositories on remote machines."
category: "Guides"
order: 4
language: en
sourceHash: "06b8912e9b65b720"
---

# Repositories

A **repository** is a LUKS-encrypted disk image on a remote server. When mounted, it provides:
- An isolated filesystem for your application data
- A dedicated Docker daemon (separate from the host's Docker)
- Unique loopback IPs for each service within a /26 subnet

## Create a Repository

```bash
rdc repo create --name my-app -m server-1 --size 10G
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
rdc repo mount --name my-app -m server-1  # Decrypt and mount
rdc repo unmount --name my-app -m server-1  # Unmount and re-encrypt
```

| Option | Description |
|--------|-------------|
| `--checkpoint` | Create a CRIU checkpoint before mount/unmount (for containers with `rediacc.checkpoint=true` label) |
| `--skip-router-restart` | Skip restarting the route server after the operation |

## Check Status

```bash
rdc repo status --name my-app -m server-1
```

## List Repositories

```bash
rdc repo list -m server-1
```

## Resize

Set the repository to an exact size or expand by a given amount:

```bash
rdc repo resize --name my-app -m server-1 --size 20G  # Set to exact size
rdc repo expand --name my-app -m server-1 --size 5G  # Add 5G to current size
```

> The repository must be unmounted before resizing.

## Fork

Create a copy of an existing repository at its current state:

```bash
rdc repo fork --parent my-app --tag staging -m server-1
```

Forks use the name:tag model: the resulting fork is named `my-app:staging`. This creates a new encrypted copy with its own GUID and network ID, while sharing the parent's name. The fork shares the same LUKS credential as the parent.

> Forks share the parent's data via BTRFS reflink, including any credentials stored on disk. See [What Rediacc does not isolate](/en/docs/ai-agents-safety#what-rediacc-does-not-isolate) for the implications when those credentials authorize external services like Stripe, AWS, or Railway.

## Validate

Check the filesystem integrity of a repository:

```bash
rdc repo validate --name my-app -m server-1
```

## Ownership

Set file ownership within a repository to the universal user (UID 7111). This is typically needed after uploading files from your workstation, which arrive with your local UID.

```bash
rdc repo ownership --name my-app -m server-1
```

The command automatically detects Docker container data directories (writable bind mounts) and excludes them. This prevents breaking containers that manage files with their own UIDs (e.g., MariaDB=999, www-data=33).

| Option | Description |
|--------|-------------|
| `--uid <uid>` | Set a custom UID instead of 7111 |
| `--skip-router-restart` | Skip restarting the route server after the operation |

To force ownership on all files, including container data:

```bash
rdc repo ownership --name my-app -m server-1
```


See the [Migration Guide](/en/docs/migration) for a complete walkthrough of when and how to use ownership during project migration.

## Template

Apply a template to initialize a repository with files:

```bash
rdc repo template apply --name my-template -m server-1 -r my-app --file ./my-template.tar.gz
```

## Delete

Permanently destroy a repository and all data inside it:

```bash
rdc repo delete --name my-app -m server-1
```

> This permanently destroys the encrypted disk image. This action cannot be undone.

## Migrate Repository

Live-migrate a repository from one machine to another with minimal downtime.

```bash
rdc repo migrate --name my-app --from server-1 --to server-2
```

| Option | Description |
|--------|-------------|
| `--provision` | Provision the repository on the target machine before migrating (creates LUKS image and registers config) |
| `--checkpoint` | Create a CRIU checkpoint of running containers before cutover |
| `--bwlimit <kbps>` | Limit rsync bandwidth in kilobytes per second |
| `--skip-dns` | Skip updating DNS records after cutover |

**Three-phase flow:**

1. **Hot pre-copy** - rsync transfers data while the repository stays running on the source. Large files are transferred before any downtime.
2. **Cutover** - the repository is stopped on the source, a final rsync pass syncs remaining changes, and the repository starts on the target.
3. **Start on target** - renet mounts and starts the repository on the target machine. DNS is updated unless `--skip-dns` is passed.

![Repository Live Migration](/img/repo-migrate-flow.svg)

**Push vs migrate:**

| | `repo push` | `repo migrate` |
|--|-------------|----------------|
| Operation | Copy | Move |
| Source after | Unchanged | Stopped |
| Downtime | None (copy only) | Brief cutover window |
| DNS update | No | Yes (unless `--skip-dns`) |
| Use case | Backup, staging clone | Machine replacement, server move |

## Prune

After deleting repositories or recovering from failed operations, orphaned mount directories, lock files, and immovable markers may remain. Prune removes these safely:

```bash
# Preview what would be removed
rdc machine prune --name server-1 --dry-run

# Remove orphaned resources
rdc machine prune --name server-1
```

Only resources with no matching repository image are affected. Non-empty mount directories are never removed.
