---
title: "تطبيق سطر الأوامر"
description: "دليل شامل لاستخدام واجهة سطر أوامر Rediacc لإدارة المنصة"
category: "مرجع"
order: 2
language: ar
generated: true
generatedFrom: packages/cli/src/i18n/locales/ar/cli.json
sourceHash: "15b88c4c24232a54"
---

<!-- THIS FILE IS AUTO-GENERATED. Do not edit manually. -->
<!-- To regenerate: npm run generate:cli-docs -w @rediacc/www -->

# {{t:cli.docs.pageTitle}}

## {{t:cli.docs.overview.heading}}

{{t:cli.docs.overview.text}}

### {{t:cli.docs.installation.heading}}

{{t:cli.docs.installation.text}}

```bash
# macOS / Linux
curl -fsSL https://get.rediacc.com | sh

# Or use the packaged binary directly
./rdc --help
```

### {{t:cli.docs.globalOptions.heading}}

{{t:cli.docs.globalOptions.intro}}

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} |
|------|-------------|
| `--output` | {{t:cli.options.output}} |
| `--config` | {{t:cli.options.config}} |
| `--lang` | {{t:cli.options.lang}} |
| `--force` | {{t:cli.options.force}} |

---

## 1. {{t:cli.docs.sectionTitles.config}}

{{t:cli.commands.config.description}}

{{t:cli.docs.supplements.config.afterDescription}}

### 1.1 init

{{t:cli.commands.config.init.description}}

{{t:cli.docs.supplements.config.init.afterDescription}}

```bash
rdc config init [name] [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--ssh-key <path>` | {{t:cli.options.sshKey}} | {{t:cli.docs.optionLabels.no}} | - |
| `--renet-path <path>` | {{t:cli.options.renetPath}} | {{t:cli.docs.optionLabels.no}} | - |
| `--master-password <password>` | {{t:cli.commands.config.init.optionMasterPassword}} | {{t:cli.docs.optionLabels.no}} | - |
| `--s3-endpoint <url>` | {{t:cli.commands.config.init.optionS3Endpoint}} | {{t:cli.docs.optionLabels.no}} | - |
| `--s3-bucket <name>` | {{t:cli.commands.config.init.optionS3Bucket}} | {{t:cli.docs.optionLabels.no}} | - |
| `--s3-access-key-id <key>` | {{t:cli.commands.config.init.optionS3AccessKeyId}} | {{t:cli.docs.optionLabels.no}} | - |
| `--s3-secret-access-key <key>` | {{t:cli.commands.config.init.optionS3SecretAccessKey}} | {{t:cli.docs.optionLabels.no}} | - |
| `--s3-region <region>` | {{t:cli.commands.config.init.optionS3Region}} | {{t:cli.docs.optionLabels.no}} | `auto` |
| `--s3-prefix <prefix>` | {{t:cli.commands.config.init.optionS3Prefix}} | {{t:cli.docs.optionLabels.no}} | - |
| `-u, --api-url <url>` | {{t:cli.options.apiUrl}} | {{t:cli.docs.optionLabels.no}} | - |


### 1.2 list

{{t:cli.commands.config.list.description}}

```bash
rdc config list
```

### 1.3 show

{{t:cli.commands.config.show.description}}

```bash
rdc config show
```

### 1.4 delete

{{t:cli.commands.config.delete.description}}

```bash
rdc config delete <name>
```

### 1.5 set

{{t:cli.commands.config.set.description}}

```bash
rdc config set <key> <value>
```

> **{{t:cli.docs.admonitions.tip}}**: {{t:cli.docs.supplements.config.set.tip}}

### 1.6 clear

{{t:cli.commands.config.clear.description}}

```bash
rdc config clear [key]
```

### 1.7 recover

{{t:cli.commands.config.recover.description}}

```bash
rdc config recover [name] [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-y, --yes` | {{t:cli.options.yes}} | {{t:cli.docs.optionLabels.no}} | - |


### 1.8 add-machine

{{t:cli.commands.config.addMachine.description}}

```bash
rdc config add-machine <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--ip <address>` | {{t:cli.options.machineIp}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--user <username>` | {{t:cli.options.sshUser}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--port <port>` | {{t:cli.options.sshPort}} | {{t:cli.docs.optionLabels.no}} | `22` |
| `--datastore <path>` | {{t:cli.options.datastore}} | {{t:cli.docs.optionLabels.no}} | `/mnt/rediacc` |


### 1.9 scan-keys

{{t:cli.commands.config.scanKeys.description}}

```bash
rdc config scan-keys [machine]
```

### 1.10 remove-machine

{{t:cli.commands.config.removeMachine.description}}

```bash
rdc config remove-machine <name>
```

### 1.11 machines

{{t:cli.commands.config.machines.description}}

```bash
rdc config machines
```

### 1.12 set-ssh

{{t:cli.commands.config.setSsh.description}}

```bash
rdc config set-ssh [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--private-key <path>` | {{t:cli.options.sshPrivateKey}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--public-key <path>` | {{t:cli.options.sshPublicKey}} | {{t:cli.docs.optionLabels.no}} | - |


### 1.13 set-renet

{{t:cli.commands.config.setRenet.description}}

```bash
rdc config set-renet <path>
```

### 1.14 setup-machine

{{t:cli.commands.config.setupMachine.description}}

```bash
rdc config setup-machine <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--datastore <path>` | {{t:cli.commands.config.setupMachine.datastoreOption}} | {{t:cli.docs.optionLabels.no}} | `/mnt/rediacc` |
| `--datastore-size <size>` | {{t:cli.commands.config.setupMachine.datastoreSizeOption}} | {{t:cli.docs.optionLabels.no}} | `95%` |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |


### 1.15 import-storage

{{t:cli.commands.config.importStorage.description}}

```bash
rdc config import-storage <file> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--name <name>` | {{t:cli.commands.config.importStorage.optionName}} | {{t:cli.docs.optionLabels.no}} | - |


### 1.16 remove-storage

{{t:cli.commands.config.removeStorage.description}}

```bash
rdc config remove-storage <name>
```

### 1.17 storages

{{t:cli.commands.config.storages.description}}

```bash
rdc config storages
```

### 1.18 add-repository

{{t:cli.commands.config.addRepository.description}}

```bash
rdc config add-repository <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--guid <guid>` | {{t:cli.commands.config.addRepository.optionGuid}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--tag <tag>` | {{t:cli.options.repositoryTag}} | {{t:cli.docs.optionLabels.no}} | `latest` |
| `--credential <credential>` | {{t:cli.commands.config.addRepository.optionCredential}} | {{t:cli.docs.optionLabels.no}} | - |
| `--network-id <id>` | {{t:cli.commands.config.addRepository.optionNetworkId}} | {{t:cli.docs.optionLabels.no}} | - |


### 1.19 remove-repository

{{t:cli.commands.config.removeRepository.description}}

```bash
rdc config remove-repository <name>
```

### 1.20 repositories

{{t:cli.commands.config.repositories.description}}

```bash
rdc config repositories
```

### 1.21 set-infra

{{t:cli.commands.config.setInfra.description}}

```bash
rdc config set-infra <machine> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--public-ipv4 <ip>` | {{t:cli.commands.config.setInfra.optionPublicIPv4}} | {{t:cli.docs.optionLabels.no}} | - |
| `--public-ipv6 <ip>` | {{t:cli.commands.config.setInfra.optionPublicIPv6}} | {{t:cli.docs.optionLabels.no}} | - |
| `--base-domain <domain>` | {{t:cli.commands.config.setInfra.optionBaseDomain}} | {{t:cli.docs.optionLabels.no}} | - |
| `--cert-email <email>` | {{t:cli.commands.config.setInfra.optionCertEmail}} | {{t:cli.docs.optionLabels.no}} | - |
| `--cf-dns-token <token>` | {{t:cli.commands.config.setInfra.optionCfDnsToken}} | {{t:cli.docs.optionLabels.no}} | - |
| `--tcp-ports <ports>` | {{t:cli.commands.config.setInfra.optionTcpPorts}} | {{t:cli.docs.optionLabels.no}} | - |
| `--udp-ports <ports>` | {{t:cli.commands.config.setInfra.optionUdpPorts}} | {{t:cli.docs.optionLabels.no}} | - |


### 1.22 show-infra

{{t:cli.commands.config.showInfra.description}}

```bash
rdc config show-infra <machine>
```

### 1.23 push-infra

{{t:cli.commands.config.pushInfra.description}}

```bash
rdc config push-infra <machine> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |


---

## 2. {{t:cli.docs.sectionTitles.store}}

{{t:cli.commands.store.description}}

### 2.1 add

{{t:cli.commands.store.add.description}}

```bash
rdc store add <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--type <type>` | {{t:cli.commands.store.add.optionType}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--encryption-key <key>` | {{t:cli.commands.store.add.optionEncryptionKey}} | {{t:cli.docs.optionLabels.no}} | - |
| `--s3-endpoint <url>` | {{t:cli.commands.config.init.optionS3Endpoint}} | {{t:cli.docs.optionLabels.no}} | - |
| `--s3-bucket <name>` | {{t:cli.commands.config.init.optionS3Bucket}} | {{t:cli.docs.optionLabels.no}} | - |
| `--s3-region <region>` | {{t:cli.commands.config.init.optionS3Region}} | {{t:cli.docs.optionLabels.no}} | `auto` |
| `--s3-access-key-id <key>` | {{t:cli.commands.config.init.optionS3AccessKeyId}} | {{t:cli.docs.optionLabels.no}} | - |
| `--s3-secret-access-key <key>` | {{t:cli.commands.config.init.optionS3SecretAccessKey}} | {{t:cli.docs.optionLabels.no}} | - |
| `--s3-prefix <prefix>` | {{t:cli.commands.store.add.optionS3Prefix}} | {{t:cli.docs.optionLabels.no}} | - |
| `--local-path <path>` | {{t:cli.commands.store.add.optionLocalPath}} | {{t:cli.docs.optionLabels.no}} | - |
| `--bw-folder-id <id>` | {{t:cli.commands.store.add.optionBwFolderId}} | {{t:cli.docs.optionLabels.no}} | - |
| `--git-url <url>` | {{t:cli.commands.store.add.optionGitUrl}} | {{t:cli.docs.optionLabels.no}} | - |
| `--git-branch <branch>` | {{t:cli.commands.store.add.optionGitBranch}} | {{t:cli.docs.optionLabels.no}} | - |
| `--git-path <path>` | {{t:cli.commands.store.add.optionGitPath}} | {{t:cli.docs.optionLabels.no}} | - |
| `--vault-addr <url>` | {{t:cli.commands.store.add.optionVaultAddr}} | {{t:cli.docs.optionLabels.no}} | - |
| `--vault-token <token>` | {{t:cli.commands.store.add.optionVaultToken}} | {{t:cli.docs.optionLabels.no}} | - |
| `--vault-mount <path>` | {{t:cli.commands.store.add.optionVaultMount}} | {{t:cli.docs.optionLabels.no}} | - |
| `--vault-prefix <path>` | {{t:cli.commands.store.add.optionVaultPrefix}} | {{t:cli.docs.optionLabels.no}} | - |
| `--vault-namespace <ns>` | {{t:cli.commands.store.add.optionVaultNamespace}} | {{t:cli.docs.optionLabels.no}} | - |


### 2.2 list

{{t:cli.commands.store.list.description}}

```bash
rdc store list
```

### 2.3 remove

{{t:cli.commands.store.remove.description}}

```bash
rdc store remove <name>
```

### 2.4 push

{{t:cli.commands.store.push.description}}

```bash
rdc store push [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--store <name>` | {{t:cli.commands.store.push.optionStore}} | {{t:cli.docs.optionLabels.no}} | - |
| `--all` | {{t:cli.commands.store.push.optionAll}} | {{t:cli.docs.optionLabels.no}} | - |


### 2.5 pull

{{t:cli.commands.store.pull.description}}

```bash
rdc store pull [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--store <name>` | {{t:cli.commands.store.pull.optionStore}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--config <name>` | {{t:cli.commands.store.pull.optionConfig}} | {{t:cli.docs.optionLabels.no}} | - |


### 2.6 sync

{{t:cli.commands.store.sync.description}}

```bash
rdc store sync [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--store <name>` | {{t:cli.commands.store.sync.optionStore}} | {{t:cli.docs.optionLabels.no}} | - |
| `--all` | {{t:cli.commands.store.sync.optionAll}} | {{t:cli.docs.optionLabels.no}} | - |


---

## 3. {{t:cli.docs.sectionTitles.machine}}

{{t:cli.commands.machine.description}}

### 3.1 list

{{t:cli.commands.machine.list.description}}

```bash
rdc machine list [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-t, --team <name>` | {{t:cli.options.team}} | {{t:cli.docs.optionLabels.no}} | - |
| `--search <text>` | {{t:cli.options.searchInField}} | {{t:cli.docs.optionLabels.no}} | - |
| `--sort <field>` | {{t:cli.options.sortByField}} | {{t:cli.docs.optionLabels.no}} | - |
| `--desc` | {{t:cli.options.sortDescending}} | {{t:cli.docs.optionLabels.no}} | - |


### 3.2 create

{{t:cli.commands.machine.create.description}}

```bash
rdc machine create <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-t, --team <name>` | {{t:cli.options.team}} | {{t:cli.docs.optionLabels.no}} | - |
| `-b, --bridge <name>` | {{t:cli.options.bridge}} | {{t:cli.docs.optionLabels.no}} | - |
| `--vault <json>` | {{t:cli.options.vaultJsonMachine}} | {{t:cli.docs.optionLabels.no}} | - |


### 3.3 delete

{{t:cli.commands.machine.delete.description}}

```bash
rdc machine delete <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-t, --team <name>` | {{t:cli.options.team}} | {{t:cli.docs.optionLabels.no}} | - |
| `-f, --force` | {{t:cli.options.force}} | {{t:cli.docs.optionLabels.no}} | - |


### 3.4 update

{{t:cli.commands.machine.update.description}}

```bash
rdc machine update
```

### 3.5 health

{{t:cli.commands.machine.health.description}}

{{t:cli.docs.supplements.machine.health.afterDescription}}

```bash
rdc machine health <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-t, --team <name>` | {{t:cli.options.team}} | {{t:cli.docs.optionLabels.no}} | - |


### 3.6 containers

{{t:cli.commands.machine.containers.description}}

```bash
rdc machine containers <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-t, --team <name>` | {{t:cli.options.team}} | {{t:cli.docs.optionLabels.no}} | - |
| `--health-check` | {{t:cli.commands.machine.containers.healthCheck}} | {{t:cli.docs.optionLabels.no}} | - |


### 3.7 services

{{t:cli.commands.machine.services.description}}

```bash
rdc machine services <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-t, --team <name>` | {{t:cli.options.team}} | {{t:cli.docs.optionLabels.no}} | - |
| `--stability-check` | {{t:cli.commands.machine.services.stabilityCheck}} | {{t:cli.docs.optionLabels.no}} | - |


### 3.8 status

{{t:cli.commands.machine.status.description}}

```bash
rdc machine status <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-t, --team <name>` | {{t:cli.options.team}} | {{t:cli.docs.optionLabels.no}} | - |


### 3.9 vault-status

{{t:cli.commands.machine.vaultStatus.description}}

```bash
rdc machine vault-status <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-t, --team <name>` | {{t:cli.options.team}} | {{t:cli.docs.optionLabels.no}} | - |


### 3.10 repos

{{t:cli.commands.machine.repos.description}}

```bash
rdc machine repos <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-t, --team <name>` | {{t:cli.options.team}} | {{t:cli.docs.optionLabels.no}} | - |
| `--search <text>` | {{t:cli.options.searchRepos}} | {{t:cli.docs.optionLabels.no}} | - |


### 3.11 test-connection

{{t:cli.commands.machine.testConnection.description}}

```bash
rdc machine test-connection [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--ip <address>` | {{t:cli.options.machineIp}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--user <name>` | {{t:cli.options.sshUser}} | {{t:cli.docs.optionLabels.yes}} | - |
| `-t, --team <name>` | {{t:cli.options.team}} | {{t:cli.docs.optionLabels.no}} | - |
| `-b, --bridge <name>` | {{t:cli.options.bridge}} | {{t:cli.docs.optionLabels.no}} | - |
| `--port <number>` | {{t:cli.options.sshPort}} | {{t:cli.docs.optionLabels.no}} | `22` |
| `--password <pwd>` | {{t:cli.options.sshPassword}} | {{t:cli.docs.optionLabels.no}} | - |
| `--datastore <path>` | {{t:cli.options.datastore}} | {{t:cli.docs.optionLabels.no}} | `/mnt/rediacc` |
| `-m, --machine <name>` | {{t:cli.options.machineForVault}} | {{t:cli.docs.optionLabels.no}} | - |
| `--save` | {{t:cli.options.saveKnownHosts}} | {{t:cli.docs.optionLabels.no}} | - |


> **{{t:cli.docs.admonitions.tip}}**: {{t:cli.docs.supplements.machine.testConnection.tip}}

---

## 4. {{t:cli.docs.sectionTitles.repo}}

{{t:cli.commands.repo.description}}

### 4.1 mount

{{t:cli.commands.repo.mount.description}}

```bash
rdc repo mount <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-m, --machine <name>` | {{t:cli.commands.repo.machineOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--checkpoint` | {{t:cli.commands.repo.mount.checkpointOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |
| `--skip-router-restart` | {{t:cli.options.skipRouterRestart}} | {{t:cli.docs.optionLabels.no}} | - |


### 4.2 unmount

{{t:cli.commands.repo.unmount.description}}

```bash
rdc repo unmount <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-m, --machine <name>` | {{t:cli.commands.repo.machineOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--checkpoint` | {{t:cli.commands.repo.unmount.checkpointOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |
| `--skip-router-restart` | {{t:cli.options.skipRouterRestart}} | {{t:cli.docs.optionLabels.no}} | - |


### 4.3 up

{{t:cli.commands.repo.up.description}}

```bash
rdc repo up <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-m, --machine <name>` | {{t:cli.commands.repo.machineOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--mount` | {{t:cli.commands.repo.up.mountOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--prep-only` | {{t:cli.commands.repo.up.prepOnlyOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--grand <name>` | {{t:cli.commands.repo.up.grandOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |
| `--skip-router-restart` | {{t:cli.options.skipRouterRestart}} | {{t:cli.docs.optionLabels.no}} | - |


### 4.4 up-all

{{t:cli.commands.repo.upAll.description}}

```bash
rdc repo up-all [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-m, --machine <name>` | {{t:cli.commands.repo.machineOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--include-forks` | {{t:cli.commands.repo.upAll.includeForksOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--mount-only` | {{t:cli.commands.repo.upAll.mountOnlyOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--dry-run` | {{t:cli.commands.repo.upAll.dryRunOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--parallel` | {{t:cli.commands.repo.upAll.parallelOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--concurrency <n>` | {{t:cli.commands.repo.upAll.concurrencyOption}} | {{t:cli.docs.optionLabels.no}} | `3` |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |
| `--skip-router-restart` | {{t:cli.options.skipRouterRestart}} | {{t:cli.docs.optionLabels.no}} | - |


### 4.5 down

{{t:cli.commands.repo.down.description}}

```bash
rdc repo down <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-m, --machine <name>` | {{t:cli.commands.repo.machineOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--unmount` | {{t:cli.commands.repo.down.unmountOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--grand <name>` | {{t:cli.commands.repo.up.grandOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |
| `--skip-router-restart` | {{t:cli.options.skipRouterRestart}} | {{t:cli.docs.optionLabels.no}} | - |


### 4.6 status

{{t:cli.commands.repo.status.description}}

```bash
rdc repo status <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-m, --machine <name>` | {{t:cli.commands.repo.machineOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |
| `--skip-router-restart` | {{t:cli.options.skipRouterRestart}} | {{t:cli.docs.optionLabels.no}} | - |


### 4.7 list

{{t:cli.commands.repo.list.description}}

```bash
rdc repo list [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-m, --machine <name>` | {{t:cli.commands.repo.machineOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |
| `--skip-router-restart` | {{t:cli.options.skipRouterRestart}} | {{t:cli.docs.optionLabels.no}} | - |


### 4.8 create

{{t:cli.commands.repo.create.description}}

```bash
rdc repo create <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-m, --machine <name>` | {{t:cli.commands.repo.machineOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--size <size>` | {{t:cli.commands.repo.create.sizeOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |
| `--skip-router-restart` | {{t:cli.options.skipRouterRestart}} | {{t:cli.docs.optionLabels.no}} | - |


### 4.9 delete

{{t:cli.commands.repo.delete.description}}

```bash
rdc repo delete <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-m, --machine <name>` | {{t:cli.commands.repo.machineOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |
| `--skip-router-restart` | {{t:cli.options.skipRouterRestart}} | {{t:cli.docs.optionLabels.no}} | - |


### 4.10 fork

{{t:cli.commands.repo.fork.description}}

```bash
rdc repo fork <parent> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-m, --machine <name>` | {{t:cli.commands.repo.machineOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--tag <name>` | {{t:cli.commands.repo.fork.tagOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |
| `--skip-router-restart` | {{t:cli.options.skipRouterRestart}} | {{t:cli.docs.optionLabels.no}} | - |


### 4.11 resize

{{t:cli.commands.repo.resize.description}}

```bash
rdc repo resize <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-m, --machine <name>` | {{t:cli.commands.repo.machineOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--size <size>` | {{t:cli.commands.repo.resize.sizeOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |
| `--skip-router-restart` | {{t:cli.options.skipRouterRestart}} | {{t:cli.docs.optionLabels.no}} | - |


### 4.12 expand

{{t:cli.commands.repo.expand.description}}

```bash
rdc repo expand <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-m, --machine <name>` | {{t:cli.commands.repo.machineOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--size <size>` | {{t:cli.commands.repo.resize.sizeOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |
| `--skip-router-restart` | {{t:cli.options.skipRouterRestart}} | {{t:cli.docs.optionLabels.no}} | - |


### 4.13 validate

{{t:cli.commands.repo.validate.description}}

```bash
rdc repo validate <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-m, --machine <name>` | {{t:cli.commands.repo.machineOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |
| `--skip-router-restart` | {{t:cli.options.skipRouterRestart}} | {{t:cli.docs.optionLabels.no}} | - |


### 4.14 autostart

{{t:cli.commands.repo.autostart.description}}

#### enable

{{t:cli.commands.repo.autostart.enable.description}}

```bash
rdc repo autostart enable <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-m, --machine <name>` | {{t:cli.commands.repo.machineOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |
| `--skip-router-restart` | {{t:cli.options.skipRouterRestart}} | {{t:cli.docs.optionLabels.no}} | - |


#### disable

{{t:cli.commands.repo.autostart.disable.description}}

```bash
rdc repo autostart disable <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-m, --machine <name>` | {{t:cli.commands.repo.machineOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |
| `--skip-router-restart` | {{t:cli.options.skipRouterRestart}} | {{t:cli.docs.optionLabels.no}} | - |


#### enable-all

{{t:cli.commands.repo.autostart.enableAll.description}}

```bash
rdc repo autostart enable-all [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-m, --machine <name>` | {{t:cli.commands.repo.machineOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |
| `--skip-router-restart` | {{t:cli.options.skipRouterRestart}} | {{t:cli.docs.optionLabels.no}} | - |


#### disable-all

{{t:cli.commands.repo.autostart.disableAll.description}}

```bash
rdc repo autostart disable-all [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-m, --machine <name>` | {{t:cli.commands.repo.machineOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |
| `--skip-router-restart` | {{t:cli.options.skipRouterRestart}} | {{t:cli.docs.optionLabels.no}} | - |


#### list

{{t:cli.commands.repo.autostart.list.description}}

```bash
rdc repo autostart list [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-m, --machine <name>` | {{t:cli.commands.repo.machineOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |
| `--skip-router-restart` | {{t:cli.options.skipRouterRestart}} | {{t:cli.docs.optionLabels.no}} | - |


### 4.15 ownership

{{t:cli.commands.repo.ownership.description}}

```bash
rdc repo ownership <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-m, --machine <name>` | {{t:cli.commands.repo.machineOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--uid <uid>` | {{t:cli.commands.repo.ownership.uidOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |
| `--skip-router-restart` | {{t:cli.options.skipRouterRestart}} | {{t:cli.docs.optionLabels.no}} | - |


### 4.16 template

{{t:cli.commands.repo.template.description}}

```bash
rdc repo template <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-m, --machine <name>` | {{t:cli.commands.repo.machineOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--file <path>` | {{t:cli.commands.repo.template.fileOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--grand <name>` | {{t:cli.commands.repo.up.grandOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |
| `--skip-router-restart` | {{t:cli.options.skipRouterRestart}} | {{t:cli.docs.optionLabels.no}} | - |


---

## 5. {{t:cli.docs.sectionTitles.storage}}

{{t:cli.commands.storage.description}}

### 5.1 list

{{t:cli.commands.storage.list.description}}

```bash
rdc storage list [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-t, --team <name>` | {{t:cli.options.team}} | {{t:cli.docs.optionLabels.no}} | - |
| `--search <text>` | {{t:cli.options.searchInField}} | {{t:cli.docs.optionLabels.no}} | - |
| `--sort <field>` | {{t:cli.options.sortByField}} | {{t:cli.docs.optionLabels.no}} | - |
| `--desc` | {{t:cli.options.sortDescending}} | {{t:cli.docs.optionLabels.no}} | - |


### 5.2 browse

{{t:cli.commands.storage.browse.description}}

```bash
rdc storage browse <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--path <subpath>` | {{t:cli.commands.storage.browse.pathOption}} | {{t:cli.docs.optionLabels.no}} | `` |


### 5.3 pull

{{t:cli.commands.storage.pull.description}}

```bash
rdc storage pull <storageName> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-r, --repository <name>` | {{t:cli.commands.storage.pull.repositoryOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `-m, --machine <name>` | {{t:cli.commands.repo.machineOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |
| `--skip-router-restart` | {{t:cli.options.skipRouterRestart}} | {{t:cli.docs.optionLabels.no}} | - |


---

## 6. {{t:cli.docs.sectionTitles.sync}}

{{t:cli.commands.sync.description}}

### 6.1 upload

{{t:cli.commands.sync.upload.description}}

```bash
rdc sync upload [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-t, --team <name>` | {{t:cli.options.team}} | {{t:cli.docs.optionLabels.no}} | - |
| `-m, --machine <name>` | {{t:cli.options.machine}} | {{t:cli.docs.optionLabels.no}} | - |
| `-r, --repository <name>` | {{t:cli.options.repository}} | {{t:cli.docs.optionLabels.no}} | - |
| `-l, --local <path>` | {{t:cli.options.localPath}} | {{t:cli.docs.optionLabels.no}} | - |
| `--remote <path>` | {{t:cli.options.remotePath}} | {{t:cli.docs.optionLabels.no}} | - |
| `--mirror` | {{t:cli.options.mirrorUpload}} | {{t:cli.docs.optionLabels.no}} | - |
| `--verify` | {{t:cli.options.verifyChecksum}} | {{t:cli.docs.optionLabels.no}} | - |
| `--confirm` | {{t:cli.options.confirmSync}} | {{t:cli.docs.optionLabels.no}} | - |
| `--exclude <patterns...>` | {{t:cli.options.excludePatterns}} | {{t:cli.docs.optionLabels.no}} | - |
| `--dry-run` | {{t:cli.options.dryRun}} | {{t:cli.docs.optionLabels.no}} | - |


### 6.2 download

{{t:cli.commands.sync.download.description}}

```bash
rdc sync download [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-t, --team <name>` | {{t:cli.options.team}} | {{t:cli.docs.optionLabels.no}} | - |
| `-m, --machine <name>` | {{t:cli.options.machine}} | {{t:cli.docs.optionLabels.no}} | - |
| `-r, --repository <name>` | {{t:cli.options.repository}} | {{t:cli.docs.optionLabels.no}} | - |
| `-l, --local <path>` | {{t:cli.options.localPath}} | {{t:cli.docs.optionLabels.no}} | - |
| `--remote <path>` | {{t:cli.options.remotePath}} | {{t:cli.docs.optionLabels.no}} | - |
| `--mirror` | {{t:cli.options.mirrorDownload}} | {{t:cli.docs.optionLabels.no}} | - |
| `--verify` | {{t:cli.options.verifyChecksum}} | {{t:cli.docs.optionLabels.no}} | - |
| `--confirm` | {{t:cli.options.confirmSync}} | {{t:cli.docs.optionLabels.no}} | - |
| `--exclude <patterns...>` | {{t:cli.options.excludePatterns}} | {{t:cli.docs.optionLabels.no}} | - |
| `--dry-run` | {{t:cli.options.dryRun}} | {{t:cli.docs.optionLabels.no}} | - |


### 6.3 status

{{t:cli.commands.sync.status.description}}

```bash
rdc sync status [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-t, --team <name>` | {{t:cli.options.team}} | {{t:cli.docs.optionLabels.no}} | - |
| `-m, --machine <name>` | {{t:cli.options.machine}} | {{t:cli.docs.optionLabels.no}} | - |
| `-r, --repository <name>` | {{t:cli.options.repository}} | {{t:cli.docs.optionLabels.no}} | - |
| `-l, --local <path>` | {{t:cli.options.localPath}} | {{t:cli.docs.optionLabels.no}} | - |
| `--remote <path>` | {{t:cli.options.remotePath}} | {{t:cli.docs.optionLabels.no}} | - |


---

## 7. {{t:cli.docs.sectionTitles.vscode}}

{{t:cli.commands.vscode.description}}

### 7.1 connect

{{t:cli.commands.vscode.connect.description}}

```bash
rdc vscode connect [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-t, --team <name>` | {{t:cli.options.team}} | {{t:cli.docs.optionLabels.no}} | - |
| `-m, --machine <name>` | {{t:cli.options.machine}} | {{t:cli.docs.optionLabels.no}} | - |
| `-r, --repository <name>` | {{t:cli.options.repository}} | {{t:cli.docs.optionLabels.no}} | - |
| `-f, --folder <path>` | {{t:cli.options.folder}} | {{t:cli.docs.optionLabels.no}} | - |
| `--url-only` | {{t:cli.options.urlOnly}} | {{t:cli.docs.optionLabels.no}} | - |
| `-n, --new-window` | {{t:cli.options.newWindow}} | {{t:cli.docs.optionLabels.no}} | - |
| `--skip-env-setup` | {{t:cli.options.skipEnvSetup}} | {{t:cli.docs.optionLabels.no}} | - |
| `--insiders` | {{t:cli.options.insiders}} | {{t:cli.docs.optionLabels.no}} | - |


### 7.2 list

{{t:cli.commands.vscode.list.description}}

```bash
rdc vscode list
```

### 7.3 cleanup

{{t:cli.commands.vscode.cleanup.description}}

```bash
rdc vscode cleanup [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--all` | {{t:cli.options.cleanupAll}} | {{t:cli.docs.optionLabels.no}} | - |
| `-c, --connection <name>` | {{t:cli.options.connectionName}} | {{t:cli.docs.optionLabels.no}} | - |


### 7.4 check

{{t:cli.commands.vscode.check.description}}

```bash
rdc vscode check [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--insiders` | {{t:cli.options.insiders}} | {{t:cli.docs.optionLabels.no}} | - |


---

## 8. {{t:cli.docs.sectionTitles.term}}

{{t:cli.commands.term.description}}

### 8.1 connect

{{t:cli.commands.term.connect.description}}

```bash
rdc term connect [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-t, --team <name>` | {{t:cli.options.team}} | {{t:cli.docs.optionLabels.no}} | - |
| `-m, --machine <name>` | {{t:cli.options.machine}} | {{t:cli.docs.optionLabels.no}} | - |
| `-r, --repository <name>` | {{t:cli.options.repository}} | {{t:cli.docs.optionLabels.no}} | - |
| `-c, --command <cmd>` | {{t:cli.options.command}} | {{t:cli.docs.optionLabels.no}} | - |
| `--container <id>` | {{t:cli.options.container}} | {{t:cli.docs.optionLabels.no}} | - |
| `--container-action <action>` | {{t:cli.options.containerAction}} | {{t:cli.docs.optionLabels.no}} | - |
| `--log-lines <lines>` | {{t:cli.options.logLines}} | {{t:cli.docs.optionLabels.no}} | - |
| `--follow` | {{t:cli.options.follow}} | {{t:cli.docs.optionLabels.no}} | - |
| `--external` | {{t:cli.options.external}} | {{t:cli.docs.optionLabels.no}} | - |


---

## 9. {{t:cli.docs.sectionTitles.protocol}}

{{t:cli.commands.protocol.description}}

### 9.1 register

{{t:cli.commands.protocol.register.description}}

```bash
rdc protocol register [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--system` | {{t:cli.options.protocolSystem}} | {{t:cli.docs.optionLabels.no}} | - |
| `--force` | {{t:cli.options.protocolForce}} | {{t:cli.docs.optionLabels.no}} | - |


### 9.2 unregister

{{t:cli.commands.protocol.unregister.description}}

```bash
rdc protocol unregister [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--system` | {{t:cli.options.protocolSystemUnregister}} | {{t:cli.docs.optionLabels.no}} | - |


### 9.3 status

{{t:cli.commands.protocol.status.description}}

```bash
rdc protocol status
```

### 9.4 open

{{t:cli.commands.protocol.open.description}}

```bash
rdc protocol open <url>
```

### 9.5 build

{{t:cli.commands.protocol.build.description}}

```bash
rdc protocol build [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--token <token>` | {{t:cli.options.protocolToken}} | {{t:cli.docs.optionLabels.yes}} | - |
| `-t, --team <name>` | {{t:cli.options.team}} | {{t:cli.docs.optionLabels.yes}} | - |
| `-m, --machine <name>` | {{t:cli.options.machine}} | {{t:cli.docs.optionLabels.yes}} | - |
| `-r, --repository <name>` | {{t:cli.options.repository}} | {{t:cli.docs.optionLabels.no}} | - |
| `-a, --action <action>` | {{t:cli.options.protocolAction}} | {{t:cli.docs.optionLabels.no}} | `desktop` |
| `-p, --params <key=value...>` | {{t:cli.options.protocolParams}} | {{t:cli.docs.optionLabels.no}} | - |


### 9.6 parse

{{t:cli.commands.protocol.parse.description}}

```bash
rdc protocol parse <url>
```

---

## 10. {{t:cli.docs.sectionTitles.snapshot}}

{{t:cli.commands.snapshot.description}}

### 10.1 create

{{t:cli.commands.snapshot.create.description}}

```bash
rdc snapshot create <repo> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-m, --machine <name>` | {{t:cli.options.machine}} | {{t:cli.docs.optionLabels.no}} | - |
| `--snapshot-name <name>` | {{t:cli.commands.snapshot.create.optionSnapshotName}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |


### 10.2 list

{{t:cli.commands.snapshot.list.description}}

```bash
rdc snapshot list [repo] [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-m, --machine <name>` | {{t:cli.options.machine}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |


### 10.3 delete

{{t:cli.commands.snapshot.delete.description}}

```bash
rdc snapshot delete <repo> <snapshot-name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-m, --machine <name>` | {{t:cli.options.machine}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |


---

## 11. {{t:cli.docs.sectionTitles.backup}}

{{t:cli.commands.backup.description}}

### 11.1 push

{{t:cli.commands.backup.push.description}}

```bash
rdc backup push <repo> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--dest <filename>` | {{t:cli.commands.backup.push.optionDest}} | {{t:cli.docs.optionLabels.no}} | - |
| `--to <storage>` | {{t:cli.commands.backup.push.optionToStorage}} | {{t:cli.docs.optionLabels.no}} | - |
| `--to-machine <machine>` | {{t:cli.commands.backup.push.optionToMachine}} | {{t:cli.docs.optionLabels.no}} | - |
| `--checkpoint` | {{t:cli.commands.backup.push.optionCheckpoint}} | {{t:cli.docs.optionLabels.no}} | - |
| `--force` | {{t:cli.commands.backup.push.optionForce}} | {{t:cli.docs.optionLabels.no}} | - |
| `--tag <tag>` | {{t:cli.commands.backup.push.optionTag}} | {{t:cli.docs.optionLabels.no}} | - |
| `-m, --machine <name>` | {{t:cli.options.machine}} | {{t:cli.docs.optionLabels.no}} | - |
| `-w, --watch` | {{t:cli.options.watch}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |
| `--skip-router-restart` | {{t:cli.options.skipRouterRestart}} | {{t:cli.docs.optionLabels.no}} | - |


### 11.2 pull

{{t:cli.commands.backup.pull.description}}

```bash
rdc backup pull <repo> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--from <storage>` | {{t:cli.commands.backup.pull.optionFromStorage}} | {{t:cli.docs.optionLabels.no}} | - |
| `--from-machine <machine>` | {{t:cli.commands.backup.pull.optionFromMachine}} | {{t:cli.docs.optionLabels.no}} | - |
| `--force` | {{t:cli.commands.backup.pull.optionForce}} | {{t:cli.docs.optionLabels.no}} | - |
| `-m, --machine <name>` | {{t:cli.options.machine}} | {{t:cli.docs.optionLabels.no}} | - |
| `-w, --watch` | {{t:cli.options.watch}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |
| `--skip-router-restart` | {{t:cli.options.skipRouterRestart}} | {{t:cli.docs.optionLabels.no}} | - |


### 11.3 list

{{t:cli.commands.backup.list.description}}

```bash
rdc backup list [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--from <storage>` | {{t:cli.commands.backup.pull.optionFromStorage}} | {{t:cli.docs.optionLabels.no}} | - |
| `--from-machine <machine>` | {{t:cli.commands.backup.pull.optionFromMachine}} | {{t:cli.docs.optionLabels.no}} | - |
| `-m, --machine <name>` | {{t:cli.options.machine}} | {{t:cli.docs.optionLabels.no}} | - |
| `-w, --watch` | {{t:cli.options.watch}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |
| `--skip-router-restart` | {{t:cli.options.skipRouterRestart}} | {{t:cli.docs.optionLabels.no}} | - |


### 11.4 sync

{{t:cli.commands.backup.sync.description}}

```bash
rdc backup sync [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--to <storage>` | {{t:cli.commands.backup.sync.optionTo}} | {{t:cli.docs.optionLabels.no}} | - |
| `--from <storage>` | {{t:cli.commands.backup.sync.optionFrom}} | {{t:cli.docs.optionLabels.no}} | - |
| `--repo <name>` | {{t:cli.commands.backup.sync.optionRepo}} | {{t:cli.docs.optionLabels.no}} | - |
| `--override` | {{t:cli.commands.backup.sync.optionOverride}} | {{t:cli.docs.optionLabels.no}} | - |
| `-m, --machine <name>` | {{t:cli.options.machine}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |


### 11.5 schedule

{{t:cli.commands.backup.schedule.description}}

#### set

{{t:cli.commands.backup.schedule.set.description}}

```bash
rdc backup schedule set [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--destination <storage>` | {{t:cli.commands.backup.schedule.set.optionDestination}} | {{t:cli.docs.optionLabels.no}} | - |
| `--cron <expression>` | {{t:cli.commands.backup.schedule.set.optionCron}} | {{t:cli.docs.optionLabels.no}} | - |
| `--enable` | {{t:cli.commands.backup.schedule.set.optionEnable}} | {{t:cli.docs.optionLabels.no}} | - |
| `--disable` | {{t:cli.commands.backup.schedule.set.optionDisable}} | {{t:cli.docs.optionLabels.no}} | - |


#### show

{{t:cli.commands.backup.schedule.show.description}}

```bash
rdc backup schedule show
```

#### push

{{t:cli.commands.backup.schedule.push.description}}

```bash
rdc backup schedule push <machine> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |


---

## 12. {{t:cli.docs.sectionTitles.shortcuts}}

### 12.1 run

{{t:cli.commands.shortcuts.run.description}}

```bash
rdc run
```

### 12.2 trace

{{t:cli.commands.shortcuts.trace.description}}

```bash
rdc trace
```

### 12.3 cancel

{{t:cli.commands.shortcuts.cancel.description}}

```bash
rdc cancel
```

### 12.4 retry

{{t:cli.commands.shortcuts.retry.description}}

```bash
rdc retry
```

---

## 13. {{t:cli.docs.sectionTitles.subscription}}

{{t:cli.commands.subscription.description}}

### 13.1 login

{{t:cli.commands.subscription.login.description}}

```bash
rdc subscription login [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-t, --token <token>` | {{t:cli.options.apiToken}} | {{t:cli.docs.optionLabels.no}} | - |
| `--server <url>` | {{t:cli.options.serverUrl}} | {{t:cli.docs.optionLabels.no}} | - |


### 13.2 status

{{t:cli.commands.subscription.status.description}}

```bash
rdc subscription status [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-m, --machine <name>` | {{t:cli.options.machine}} | {{t:cli.docs.optionLabels.no}} | - |


### 13.3 refresh

{{t:cli.commands.subscription.refresh.description}}

```bash
rdc subscription refresh [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-m, --machine <name>` | {{t:cli.options.machine}} | {{t:cli.docs.optionLabels.yes}} | - |


---

## 14. {{t:cli.docs.sectionTitles.update}}

{{t:cli.commands.update.description}}

```bash
rdc update [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--force` | {{t:cli.commands.update.force}} | {{t:cli.docs.optionLabels.no}} | - |
| `--check-only` | {{t:cli.commands.update.checkOnly}} | {{t:cli.docs.optionLabels.no}} | - |
| `--rollback` | {{t:cli.commands.update.rollback}} | {{t:cli.docs.optionLabels.no}} | - |
| `--status` | {{t:cli.commands.update.statusDescription}} | {{t:cli.docs.optionLabels.no}} | - |


---

## 15. {{t:cli.docs.sectionTitles.doctor}}

{{t:cli.commands.doctor.description}}

```bash
rdc doctor
```

---

## 16. {{t:cli.docs.sectionTitles.ops}}

{{t:cli.commands.ops.description}}

### 16.1 up

{{t:cli.commands.ops.up.description}}

```bash
rdc ops up [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--force` | {{t:cli.options.opsForce}} | {{t:cli.docs.optionLabels.no}} | - |
| `--parallel` | {{t:cli.options.opsParallel}} | {{t:cli.docs.optionLabels.no}} | - |
| `--basic` | {{t:cli.options.opsBasic}} | {{t:cli.docs.optionLabels.no}} | - |
| `--lite` | {{t:cli.options.opsLite}} | {{t:cli.docs.optionLabels.no}} | - |
| `--skip-orchestration` | {{t:cli.options.opsSkipOrchestration}} | {{t:cli.docs.optionLabels.no}} | - |
| `--backend <backend>` | {{t:cli.options.opsBackend}} | {{t:cli.docs.optionLabels.no}} | - |
| `--os <name>` | {{t:cli.options.opsOS}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |


### 16.2 down

{{t:cli.commands.ops.down.description}}

```bash
rdc ops down [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--backend <backend>` | {{t:cli.options.opsBackend}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |


### 16.3 status

{{t:cli.commands.ops.status.description}}

```bash
rdc ops status [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--backend <backend>` | {{t:cli.options.opsBackend}} | {{t:cli.docs.optionLabels.no}} | - |


### 16.4 ssh

{{t:cli.commands.ops.ssh.description}}

```bash
rdc ops ssh <vmId> [command...] [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--backend <backend>` | {{t:cli.options.opsBackend}} | {{t:cli.docs.optionLabels.no}} | - |
| `--user <user>` | {{t:cli.options.opsSSHUser}} | {{t:cli.docs.optionLabels.no}} | - |


### 16.5 setup

{{t:cli.commands.ops.setup.description}}

```bash
rdc ops setup [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |


### 16.6 check

{{t:cli.commands.ops.check.description}}

```bash
rdc ops check
```

---

## {{t:cli.docs.errors.heading}}

{{t:cli.docs.errors.intro}}

| {{t:cli.docs.tableHeaders.error}} | {{t:cli.docs.tableHeaders.meaning}} |
|-------|---------|
| {{t:cli.errors.authRequired}} | {{t:cli.docs.errors.meanings.authRequired}} |
| {{t:cli.errors.noActiveConfig}} | {{t:cli.docs.errors.meanings.noActiveConfig}} |
| {{t:cli.errors.permissionDenied}} | {{t:cli.docs.errors.meanings.permissionDenied}} |
| {{t:cli.errors.machineRequired}} | {{t:cli.docs.errors.meanings.machineRequired}} |
| {{t:cli.errors.teamRequired}} | {{t:cli.docs.errors.meanings.teamRequired}} |
| {{t:cli.errors.regionRequired}} | {{t:cli.docs.errors.meanings.regionRequired}} |

---

## {{t:cli.docs.outputFormats.heading}}

{{t:cli.docs.outputFormats.text}}

```bash
rdc machine list --output json
rdc machine list --output yaml
rdc machine list --output csv
rdc machine list --output table   # default
```

{{t:cli.docs.outputFormats.closing}}
