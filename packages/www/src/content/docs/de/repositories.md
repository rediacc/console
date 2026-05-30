---
title: Repositories
description: >-
  LUKS-verschlüsselte Repositories auf entfernten Maschinen erstellen, verwalten
  und betreiben.
category: Guides
order: 4
language: de
sourceHash: "531ee9648611844e"
sourceCommit: "4e60a12e0664cdee5ad9079a7b75e2d05980d0f5"
untranslated: true
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

### Type column and the state mirror

The output table includes a `Type` column with three values:

- **`grand`**. A top-level repository registered in your local CLI config without a parent. The base case.
- **`fork`**. A copy-on-write fork of another repo. Identified either via `grandGuid` in the local config **or** via the renet `.interim/state` mirror on the machine. Either source is authoritative; both should agree once the mirror is populated.
- **`unknown`**. Neither signal can classify the repo. Most often a pre-mirror legacy fork (created before the mirror code shipped and never re-mounted since), or a stale `grand` whose local-config entry was deleted by mistake. The CLI refuses to guess; the operator should run [the mirror backfill](/en/docs/pruning#migration-state-mirror-backfill) or remove the directory if it's genuinely orphaned.

The `.interim/state/<guid>/.rediacc.json` mirror is a small sidecar file written **outside** the LUKS-encrypted volume so backup tooling and `repo list` can read fork lineage without unlocking each image. It carries the same shape as the in-volume `.rediacc.json` (`is_fork`, `grand_guid`, `name`, etc.) and is refreshed on every `Repository.SaveState`. I.e. every mount and every state mutation. It's the source of truth for fork detection in scheduled backups: an unmounted fork with a mirror that says `is_fork: true` is correctly skipped from `cold` and `hot` uploads.

For routine cleanup of unknown entries, see [`rdc machine prune --prune-unknown`](/en/docs/pruning#phase-3---prune-unknown-surgical).

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

> Forks share the parent's data via BTRFS reflink, including any credentials stored on disk. See [What Rediacc does not isolate](/en/docs/ai-agents-safety#what-rediacc-does-not-isolate) for the implications when those credentials authorize external services like Stripe, AWS, or Railway. To keep deploy-time credentials out of the fork's reach, use [per-repo secrets](#secrets) instead of baking values into `.env` files inside the repo.

At fork creation, `repo fork` writes the [state mirror sidecar](#type-column-and-the-state-mirror) at `<datastore>/.interim/state/<fork-guid>/.rediacc.json` immediately. Without unlocking the volume. So the new fork is correctly identified as `is_fork: true` from the moment of creation. This lets scheduled backups skip it (forks are excluded from the upload pipeline by default) even if it's never mounted. When forking a fork, `grand_guid` chains correctly: the new fork's mirror points at the original grand parent's GUID, not at the intermediate fork.

## Git-ähnliche Versionierung

Forks können als Git-Commits eingesetzt werden. `rdc repo commit` friert einen arbeitenden Fork zu einem unveränderlichen, byte-stabilen Commit ein; `rdc repo branch` benennt eine Historienfolge; `rdc repo checkout` klont einen Commit per Reflink zurück in einen beschreibbaren Fork; `rdc repo log` geht die Elternkette durch; und `rdc repo merge` kombiniert zwei Entwicklungslinien, ohne ein laufendes Repository direkt zu ändern. `rdc repo fork --immutable` erzeugt eine commit-äquivalente Basis in einem einzigen Schritt.

```bash
rdc repo commit --name my-app:work --message "schema migration applied" -m server-1
rdc repo branch --branch staging --name my-app:work
rdc repo checkout --ref staging --from my-app:work --tag staging-copy -m server-1
```

Siehe die [Referenz für git-ähnliches Branching](/de/docs/repo-branching) für den vollständigen Befehlssatz, Optionen und Beispiele.

## Secrets

Per-repo secrets are deploy-time credentials injected into containers without being written to the encrypted repository image. They are kept on a separate plane from the repository's data, so `rdc repo fork` does not propagate them. A fork starts with an empty secrets map and its containers boot identifying themselves as a different external principal than the parent.

> Want a step-by-step walkthrough? See the [Managing Secrets tutorial](/en/docs/tutorial-managing-secrets) for the full set/list/deploy/verify/rotate cycle.

**Write-only model (GitHub-style):** `get` returns the SHA-256 digest only. The plaintext value is never returned to anyone, human or agent. If you forget what a value is, look it up in your password manager and rotate; you cannot read it back from Rediacc by design. This eliminates an entire class of leak: terminal recordings, shell history, accidental redirection, shoulder-surfing.

Two delivery modes:

- `env`. The secret is exported as `REDIACC_SECRET_<KEY>` in the renet shell on the target machine. Reference it from your `docker-compose.yml` via `${REDIACC_SECRET_<KEY>}` interpolation. Visible inside the container's environment, so use this for connection-string-shaped values that the application already expects in env.
- `file`. The secret is written to `/var/run/rediacc/secrets/<networkID>/<KEY>` on the host (tmpfs, never persisted). Reference it from your compose file via a top-level `secrets:` declaration with `file:` source, plus a per-service `secrets:` list. Containers read from `/run/secrets/<key>`. Prefer this mode for anything sensitive. It never appears in `docker inspect` or `/proc/<pid>/environ`.

```bash
# Set, list, get (digest only), unset
rdc repo secret set --name my-app --key STRIPE_LIVE_KEY --value sk_live_xxx --mode file --current ""
rdc repo secret set --name my-app --key DB_HOST         --value postgres.internal --mode env --current ""
rdc repo secret list --name my-app
rdc repo secret get  --name my-app --key DB_HOST    # → { key, mode, digest } — no value
rdc repo secret unset --name my-app --key STRIPE_LIVE_KEY --current sk_live_xxx
```

**Symmetric mutation gate.** Both humans and agents need `--current <previous-value>` to overwrite or unset a secret (passwd-style precondition). For first-write of a new key, pass `--current ""` (empty). To rotate without verifying the prior value, pass `--rotate-secret` instead. This is loudly audited as a rotation. `--current` and `--rotate-secret` are mutually exclusive.

Pass `--value -` to read from stdin instead of argv (avoids shell-history exposure for one-shot writes).

In your `docker-compose.yml`:

```yaml
services:
  api:
    image: myapp
    environment:
      DATABASE_HOST: ${REDIACC_SECRET_DB_HOST}
    secrets:
      - stripe_live_key

secrets:
  stripe_live_key:
    file: /var/run/rediacc/secrets/${REDIACC_NETWORK_ID}/STRIPE_LIVE_KEY
```

The lowercase service-side reference (`stripe_live_key`) is the in-container `/run/secrets/<name>` filename; the uppercase tail of the host path (`STRIPE_LIVE_KEY`) matches what you set with `--key`. `${REDIACC_NETWORK_ID}` is interpolated by `renet compose` automatically.

> **Cross-repo isolation enforced**: renet's compose validator rejects `secrets: file:` (and `configs: file:`, and `env_file:`) paths that reference any other repo's network ID. The literal `${REDIACC_NETWORK_ID}` token (or your own network's int) is the only accepted form for `/var/run/rediacc/secrets/...` references. And `--unsafe` does NOT override this check. The Landlock sandbox around the Rediaccfile bash subprocess also scopes filesystem access to your own network's secrets directory only, so a malicious `cat /var/run/rediacc/secrets/<other>/X` from a Rediaccfile fails with EACCES at the kernel layer.

> **Forks**: `rdc repo fork` does **not** copy secrets. To use secrets in a fork, run `rdc repo secret set --name <fork>` on the fork explicitly. This is the load-bearing safety property. The fork's containers should not be able to act as the production principal against external services.

> **Agents** (Claude Code, Cursor, etc.): `repo secret list` and `repo secret get` are exposed as MCP tools (read-safe. Names + digests only, never values). `set` and `unset` are CLI-only because the `--current`/`--rotate-secret` ceremony requires human eyes-on; agents calling them via shell get the same gate as humans. When precondition fails, the JSON envelope contains a structured `errors[].next.options[].run` field. Agents should relay those commands verbatim to the user. See [AI agent safety](/en/docs/ai-agents-safety) for the full model.

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
