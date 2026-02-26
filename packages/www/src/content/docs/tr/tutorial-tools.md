---
title: "Araçlar"
description: "Terminal, dosya senkronizasyonu, VS Code entegrasyonu ve CLI güncelleme komutlarını kullanırken izleyin ve takip edin."
category: "Tutorials"
order: 5
language: tr
sourceHash: "6cf8e14712148f7f"
---

# Öğretici: Araçlar

This tutorial demonstrates the productivity tools built into `rdc`: SSH terminal access, file synchronization, VS Code integration, and CLI updates.

## Ön Koşullar

- The `rdc` CLI installed with a config initialized
- A provisioned machine with a running repository (see [Tutorial: Repository Lifecycle](/tr/docs/tutorial-repos))

## Etkileşimli Kayıt

![Tutorial: Tools](/assets/tutorials/tools-tutorial.cast)

## Neler Göreceksiniz

The recording above walks through each step below. Use the playback bar to navigate between commands.

### Adım 1: Makineye bağlanın

```bash
rdc term server-1 -c "hostname"
rdc term server-1 -c "uptime"
```

Run inline commands on a remote machine via SSH. The `-c` flag executes a single command and returns the output without opening an interactive session.

### Adım 2: Depoya bağlanın

```bash
rdc term server-1 my-app -c "docker ps"
```

When connecting to a repository, `DOCKER_HOST` is automatically set to the repository's isolated Docker socket. Any Docker command runs against that repository's containers only.

### Adım 3: Dosya senkronizasyonunu önizleyin (deneme)

```bash
rdc sync upload -m server-1 -r my-app --local ./src --dry-run
```

The `--dry-run` flag previews what would be transferred without actually uploading files. Shows new files, changed files, and total transfer size.

### Adım 4: Dosyaları yükleyin

```bash
rdc sync upload -m server-1 -r my-app --local ./src
```

Transfers files from your local machine to the remote repository mount via rsync over SSH.

### Adım 5: Yüklenen dosyaları doğrulayın

```bash
rdc term server-1 my-app -c "ls -la"
```

Confirm the files arrived by listing the repository's mount directory.

### Adım 6: VS Code entegrasyon kontrolü

```bash
rdc vscode check
```

Verifies your VS Code installation, Remote SSH extension, and SSH configuration for remote development. Shows which settings need to be configured.

### Adım 7: CLI güncellemelerini kontrol edin

```bash
rdc update --check-only
```

Checks if a newer version of the `rdc` CLI is available without applying it. Use `rdc update` (without `--check-only`) to install the update.

## Sonraki Adımlar

- [Tools](/tr/docs/tools) — full reference for terminal, sync, VS Code, and update commands
- [Tutorial: Backup & Restore](/tr/docs/tutorial-backup) — backup, restore, and scheduled sync
- [Services](/tr/docs/services) — Rediaccfile reference and service networking
