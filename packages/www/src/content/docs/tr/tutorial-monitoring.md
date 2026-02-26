---
title: "İzleme ve Tanılama"
description: "Makine sağlığını kontrol ederken, konteynerleri incelerken, servisleri gözden geçirirken ve tanılama çalıştırırken izleyin ve takip edin."
category: "Tutorials"
order: 4
language: tr
sourceHash: "e121e29d9a6359bc"
---

# Öğretici: İzleme ve Tanılama

This tutorial demonstrates the monitoring and diagnostic commands available in `rdc`: health checks, container inspection, service status, vault overview, and environment diagnostics.

## Ön Koşullar

- The `rdc` CLI installed with a config initialized
- A provisioned machine with at least one running repository (see [Tutorial: Repository Lifecycle](/tr/docs/tutorial-repos))

## Etkileşimli Kayıt

![Tutorial: Monitoring & Diagnostics](/assets/tutorials/monitoring-tutorial.cast)

## Neler Göreceksiniz

The recording above walks through each step below. Use the playback bar to navigate between commands.

### Adım 1: Tanılama çalıştırın

```bash
rdc doctor
```

Checks your local environment: Node.js, CLI version, renet binary, configuration, and virtualization support. Each check reports **OK**, **Warning**, or **Error**.

### Adım 2: Makine sağlık kontrolü

```bash
rdc machine health server-1
```

Sistem çalışma süresi, disk kullanımı, veri deposu kullanımı, konteyner sayıları, depolama SMART durumu ve tespit edilen sorunları içeren kapsamlı bir sağlık raporu alır.

### Adım 3: Çalışan konteynerleri görüntüleyin

```bash
rdc machine containers server-1
```

Lists all running containers across all repositories on the machine, showing name, status, state, health, CPU usage, memory usage, and which repository owns each container.

### Adım 4: systemd servislerini kontrol edin

```bash
rdc machine services server-1
```

Lists Rediacc-related systemd services (Docker daemons, loopback aliases) with their state, sub-state, restart count, and memory usage.

### Adım 5: Kasa durum özeti

```bash
rdc machine vault-status server-1
```

Provides a high-level overview of the machine: hostname, uptime, memory, disk, datastore, and total repository counts.

### Adım 6: Ana bilgisayar anahtarlarını tarayın

```bash
rdc config scan-keys server-1
```

Refreshes the SSH host key stored in your config for the machine. Useful after a machine rebuild or IP change.

### Adım 7: Bağlantıyı doğrulayın

```bash
rdc term server-1 -c "hostname"
rdc term server-1 -c "uptime"
```

Quick SSH connectivity check by running inline commands on the remote machine.

## Sonraki Adımlar

- [Monitoring](/tr/docs/monitoring) — full reference for all monitoring commands
- [Troubleshooting](/tr/docs/troubleshooting) — common issues and solutions
- [Tutorial: Tools](/tr/docs/tutorial-tools) — terminal, file sync, and VS Code integration
