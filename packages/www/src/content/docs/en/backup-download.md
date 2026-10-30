---
title: "Backup Download"
description: "Copy a repository's encrypted image to a local directory or an external drive, update it in place on later runs, or rebuild it straight from the backup store with no machine."
category: "Guides"
tags:
  - backup
  - storage
subcategory: data-protection
order: 8
language: en
---

# Backup Download

`rdc backup download` keeps a copy of a repository's encrypted image on a local directory or an external drive. The copy is the same ciphertext that sits on the machine, so nothing is decrypted on the way. The credential that opens it stays in the config, which makes [config storage](/en/docs/config-storage) enrollment the way to keep it safe. Without the credential the image cannot be opened.

There are two sources. A running machine is the default. The backup store is the other, selected with `--store`.

## Download from a machine

```bash
rdc backup download mail@prod --to /mnt/usb
```

`--to` names an existing, writable directory. It is never created, so mount the drive first. The image lands at `<machine>/<name>.<tag>.img`, with a `.state.json` file beside it.

Each run takes a fresh snapshot of the repository that is held only while the transfer lives, sends the differences with rsync, and compares a sha256 of the result with the machine's snapshot.

| Flag | Effect |
|------|--------|
| `--all -m <machine>` | Copy every grand repository placed on the machine |
| `--include-forks` | With `--all`, copy forks too |
| `--bwlimit <rate>` | Cap network bandwidth, such as `100Mbps` or `12.5M` |
| `--checkpoint` | Checkpoint and freeze the repository before the snapshot (hot backup) |
| `--retries <n>` | In-run retries after a network failure (default 3) |
| `--skip-verify` | Skip the sha256 comparison; rsync's own checksum still runs |
| `--skip-space-check` | Warn instead of refusing when the target may lack free space |

### Updating the copy

A second run updates the existing image in place by rsync delta. A weekly run sends only what changed, and the target needs room for one copy of the image, not two. Before a run starts, the free space is checked against the image size, and `--skip-space-check` turns a refusal into a warning.

### Interrupted runs and resume

The state file records `status`. It is `incomplete` from before the first byte is written until a run is verified, and an `incomplete` image is not usable. Ctrl-C, a lost connection or a killed process leaves it that way. Running the same command again resumes, and only the differences are sent. The command exits 0 once the status is `complete`.

### Requirements

The transfer needs rsync 3.1.3 or newer on this computer and has no SFTP fallback. Linux distributions ship it. On macOS, `brew install rsync` replaces the bundled openrsync, which cannot run the transfer. On Windows, install MSYS2 with the rsync package, or use the desktop app.

### External drives

The target filesystem decides what fits.

- **FAT32** cannot hold a file over 4 GiB, and the command refuses the run.
- **exFAT** without sparse-file support stores the image at its full apparent size, so the free-space check counts that size.
- A **copy-on-write snapshot** taken locally of the target (btrfs, ZFS, APFS) keeps earlier versions of the image. Each in-place update then costs the changed blocks in addition to the old ones.

## Download from the backup store

```bash
export REDIACC_TOKEN=<api-token>
rdc backup download mail --store --to /mnt/usb
```

`--store` rebuilds the image directly from the chunk store, with no machine involved. The token in `REDIACC_TOKEN` needs the `backup:read` and `backup:restore` scopes. A CLI login never carries `backup:restore`, so create the token on the portal's API Tokens page. It must belong to a team and be created by a current organization owner or admin.

`--store` takes exactly one repository name. It takes no `-m`, `--checkpoint`, `--all`, `--include-forks`, `--bwlimit`, `--retries`, `--skip-verify` or `--skip-space-check`: the store fetch has its own resume and verifies every chunk.

The image is written to `<dir>/<name>.<tag>.img`. An interrupted fetch keeps the partial copy, and the same command resumes from it.

### Choosing a snapshot with `--at`

By default the newest snapshot is fetched. `--at <time|snapshot>` selects another, either a time in ISO 8601 or a snapshot id. It applies only with `--store`.

```bash
rdc backup download mail --store --to /mnt/usb --at 2026-10-01T00:00:00Z
```

On a platform other than Linux, the fetched image is encrypted and cannot be opened locally. Send it to a Linux machine with `rdc backup upload`.

## Upload a copy back

```bash
rdc backup upload /mnt/usb/prod/mail.latest.img --to prod --as mail-copy --up
```

`rdc backup upload` sends a downloaded image to a machine and registers it as a new repository. The transfer resumes after an interruption, and the machine checks the sha256 and the LUKS header before it places the image. The state file beside the image supplies the credential. When that file is lost, `--from-repo <name>` names the repository that supplies it.

| Flag | Effect |
|------|--------|
| `--as <name>` | Name for the new repository (default: the image's name) |
| `--datastore <name>` | Place the image on a named datastore |
| `--from-repo <name>` | Supply the credential and lineage when the state file is unusable |
| `--bwlimit <rate>`, `--retries <n>` | The same as for download |
| `--up` | Start the repository once it is registered |
| `--skip-verify` | Skip comparing with the sha256 recorded at download |

## Stale transfer snapshots

A transfer killed hard can leave its snapshot on the machine. `rdc machine status` counts stale transfer snapshots in the pool summary, and `rdc machine prune <machine> --dry-run` lists them. Running `rdc machine prune <machine>` removes them.

See [Backup & Restore](/en/docs/backup-restore) for snapshots to chunk storage.
