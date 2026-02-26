---
title: "Makine Kurulumu"
description: "Bir yapılandırma oluştururken, makine eklerken, bağlantıyı test ederken, tanılama çalıştırırken ve altyapıyı yapılandırırken izleyin ve takip edin."
category: "Tutorials"
order: 2
language: tr
sourceHash: "743a5b6abe79a1af"
---

# Öğretici: Makine Kurulumu

This tutorial walks through the complete setup workflow: creating a config, registering a remote machine, verifying SSH connectivity, running diagnostics, and configuring infrastructure settings.

## Ön Koşullar

- The `rdc` CLI installed
- A remote server (or local VM) reachable via SSH
- An SSH private key that can authenticate to the server

## Etkileşimli Kayıt

![Tutorial: Machine setup and configuration](/assets/tutorials/setup-tutorial.cast)

## Neler Göreceksiniz

The recording above walks through each step below. Use the playback bar to navigate between commands.

### Adım 1: Yeni yapılandırma oluşturun

```bash
rdc config init tutorial-demo --ssh-key ~/.ssh/id_ed25519
```

Creates a named config file at `~/.config/rediacc/tutorial-demo.json`. Each config stores machine definitions, SSH credentials, and infrastructure settings.

### Adım 2: Yapılandırmaları görüntüleyin

```bash
rdc config list
```

Lists all available configs with their adapter type (local or cloud) and machine count.

### Adım 3: Makine ekleyin

```bash
rdc config add-machine bridge-vm --ip 192.168.111.1 --user muhammed --config tutorial-demo
```

Registers a machine in the config. The CLI automatically runs `ssh-keyscan` to fetch and store the server's host keys.

### Adım 4: Makineleri görüntüleyin

```bash
rdc config machines --config tutorial-demo
```

Shows all machines in the current config with their connection details.

### Adım 5: Varsayılan makineyi ayarlayın

```bash
rdc config set machine bridge-vm --config tutorial-demo
```

Varsayılan bir makine ayarlar, böylece sonraki komutlarda `-m bridge-vm` parametresini atlayabilirsiniz.

### Adım 6: Bağlantıyı test edin

```bash
rdc term bridge-vm -c "hostname"
rdc term bridge-vm -c "uptime"
```

Runs commands on the machine over SSH to verify connectivity is working.

### Adım 7: Tanılama çalıştırın

```bash
rdc doctor
```

Checks your environment: CLI version, Docker, renet binary, config status, SSH key, and virtualization prerequisites.

### Adım 8: Altyapıyı yapılandırın

```bash
rdc config set-infra bridge-vm \
  --public-ipv4 192.168.111.1 \
  --base-domain test.local \
  --cert-email admin@test.local
```

Sets the infrastructure configuration for public-facing services. After setting infra, view the configuration:

```bash
rdc config show-infra bridge-vm
```

Deploy the generated Traefik proxy config to the server with `rdc config push-infra bridge-vm`.

## Sonraki Adımlar

- [Machine Setup](/tr/docs/setup) — full reference for all config and setup commands
- [Quick Start](/tr/docs/quick-start) — deploy a containerized application end-to-end
- [Tutorial: Repository Lifecycle](/tr/docs/tutorial-repos) — create, deploy, and manage repositories
