---
title: "Backup & Restore"
description: "Push your repository to external storage and restore it on a new server when you need it."
category: "Tutorials"
subcategory: advanced
order: 11
language: en
---

# Backup & Restore

Your app is live in production. Now make sure you never lose it. `rdc` can push your entire repository (app, database, files, configs) to external storage and pull it back any time. Survive ransomware, hardware failure, anything.

## Watch the tutorial

![Tutorial: Backup and restore](/assets/tutorials/tutorial-backup-restore.cast)

## Three steps

![Configure, push, restore](/img/tutorials/tutorial-backup-restore/slide-1.svg)

1. **Configure** a storage provider.
2. **Push** a backup.
3. **Restore** when you need it.

## Step 1: Configure storage

You need an `rclone` config file. If you already use rclone, import it directly:

```bash
time rdc config storage import --file rclone.conf
```

This supports S3, B2, Google Drive, Dropbox, and many more. Verify what's wired up:

```bash
time rdc config storage list
```

## Step 2: Push a backup

```bash
time rdc repo push --name my-app -m my-server --to my-storage
```

Your entire repository (app, database, files, everything) is now backed up. Because the repository itself is encrypted, the backup is encrypted too. No extra key management.

List your backups any time:

```bash
time rdc repo backup list --from my-storage -m my-server
```

## Why no downtime?

The app keeps running while the backup uploads. How is that consistent?

Same logic as a [fork](/en/docs/tutorial-forking). `rdc` forks first, then uploads the fork. The fork captures the moment; your live app keeps going. No downtime, no inconsistency.

## Step 3: Restore on a new server

Let's say your server dies. Set up a new server, add it to `rdc`, and pull:

```bash
time rdc repo pull --name my-app -m new-server --from my-storage
```

Then start it:

```bash
time rdc repo up --name my-app -m new-server
```

Your app is back. Same data, same containers, different machine.

## Faster backups: machine to machine

You can also push directly between machines, no cloud storage in between:

```bash
time rdc repo push --name my-app -m my-server --to-machine backup-server
```

> **Pro tip.** Storage uploads always send everything. Machine-to-machine sends only the difference. The first machine-to-machine push takes the usual time, but every push after that is much faster. Great for frequent backups.

---

Next: [Monitoring](/en/docs/tutorial-monitoring).
