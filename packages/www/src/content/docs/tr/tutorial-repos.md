---
title: "Depo Yaşam Döngüsü"
description: "Şifreli bir depo oluştururken, konteynerleştirilmiş bir uygulama dağıtırken, konteynerleri incelerken ve temizlerken izleyin ve takip edin."
category: "Tutorials"
order: 3
language: tr
sourceHash: "b692ef9f49ac4aa0"
---

# Öğretici: Depo Yaşam Döngüsü

This tutorial walks through the full repository lifecycle: creating an encrypted repository, deploying a containerized application, inspecting running containers, stopping services, and cleaning up.

## Ön Koşullar

- The `rdc` CLI installed with a config initialized
- A provisioned machine (run `rdc config setup-machine` first — see [Machine Setup](/tr/docs/setup))
- A simple application with a `Rediaccfile` and `docker-compose.yml`

## Etkileşimli Kayıt

![Tutorial: Repository lifecycle](/assets/tutorials/repos-tutorial.cast)

## Neler Göreceksiniz

The recording above walks through each step below. Use the playback bar to navigate between commands.

### Adım 1: Şifreli bir depo oluşturun

```bash
rdc repo create test-app -m server-1 --size 2G
```

Creates a 2 GB LUKS-encrypted repository on the machine. The repository is automatically mounted and ready for file uploads.

### Adım 2: Depoları listeleyin

```bash
rdc repo list -m server-1
```

Shows all repositories on the machine with their size, mount status, and encryption state.

### Adım 3: Uygulama dosyalarını yükleyin

Upload your `Rediaccfile` and `docker-compose.yml` to the repository mount. The `rdc sync upload` command handles this via rsync:

```bash
rdc sync upload -m server-1 -r test-app --local ./my-app
```

### Adım 4: Servisleri başlatın

```bash
rdc repo up test-app -m server-1 --mount
```

This mounts the repository (if not already mounted), starts an isolated Docker daemon, pulls images via `prep()`, and starts services via `up()`.

### Adım 5: Çalışan konteynerleri görüntüleyin

```bash
rdc machine containers server-1
```

Makinedeki tüm depolardaki tüm çalışan konteynerleri, CPU ve bellek kullanımı dahil gösterir.

### Adım 6: Terminal üzerinden depoya erişin

```bash
rdc term server-1 test-app -c "docker ps"
```

Opens an SSH session with `DOCKER_HOST` set to the repository's isolated Docker daemon. Any Docker command runs against that repo's containers.

### Adım 7: Durdurun ve temizleyin

```bash
rdc repo down test-app -m server-1      # Stop services
rdc repo unmount test-app -m server-1   # Close encrypted volume
rdc repo delete test-app -m server-1    # Delete repository permanently
```

`down` stops containers and the Docker daemon. `unmount` closes the LUKS volume. `delete` permanently removes the repository and its encrypted storage.

## Sonraki Adımlar

- [Services](/tr/docs/services) — Rediaccfile reference, service networking, autostart, and multi-service layouts
- [Tutorial: Monitoring](/tr/docs/tutorial-monitoring) — health checks, container inspection, and diagnostics
- [Tools](/tr/docs/tools) — terminal, file sync, and VS Code integration
