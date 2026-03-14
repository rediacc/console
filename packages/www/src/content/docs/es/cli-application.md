---
title: "Aplicación CLI"
description: "Guía completa para usar la interfaz de línea de comandos de Rediacc para la gestión de la plataforma"
category: "Referencia"
order: 2
language: es
generated: true
generatedFrom: packages/cli/src/i18n/locales/es/cli.json
sourceHash: "a8d879752d531b2b"
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

<a id="cli-local-group-agent"></a>
## 1. {{t:cli.docs.sectionTitles.agent}}

{{t:cli.commands.agent.description}}

<a id="cli-local-agent-capabilities"></a>
### 1.1 capabilities

{{t:cli.commands.agent.capabilities.description}}

```bash
rdc agent capabilities
```

<a id="cli-local-agent-schema"></a>
### 1.2 schema

{{t:cli.commands.agent.schema.description}}

```bash
rdc agent schema <command>
```

<a id="cli-local-agent-exec"></a>
### 1.3 exec

{{t:cli.commands.agent.exec.description}}

```bash
rdc agent exec <command>
```

---

<a id="cli-local-group-config"></a>
## 2. {{t:cli.docs.sectionTitles.config}}

{{t:cli.commands.config.description}}

{{t:cli.docs.supplements.config.afterDescription}}

<a id="cli-local-config-init"></a>
### 2.1 init

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


<a id="cli-local-config-list"></a>
### 2.2 list

{{t:cli.commands.config.list.description}}

```bash
rdc config list
```

<a id="cli-local-config-show"></a>
### 2.3 show

{{t:cli.commands.config.show.description}}

```bash
rdc config show
```

<a id="cli-local-config-delete"></a>
### 2.4 delete

{{t:cli.commands.config.delete.description}}

```bash
rdc config delete <name>
```

<a id="cli-local-config-set"></a>
### 2.5 set

{{t:cli.commands.config.set.description}}

```bash
rdc config set <key> <value>
```

> **{{t:cli.docs.admonitions.tip}}**: {{t:cli.docs.supplements.config.set.tip}}

<a id="cli-local-config-clear"></a>
### 2.6 clear

{{t:cli.commands.config.clear.description}}

```bash
rdc config clear [key]
```

<a id="cli-local-config-recover"></a>
### 2.7 recover

{{t:cli.commands.config.recover.description}}

```bash
rdc config recover [name] [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-y, --yes` | {{t:cli.options.yes}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-config-add-machine"></a>
### 2.8 add-machine

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


<a id="cli-local-config-scan-keys"></a>
### 2.9 scan-keys

{{t:cli.commands.config.scanKeys.description}}

```bash
rdc config scan-keys [machine]
```

<a id="cli-local-config-remove-machine"></a>
### 2.10 remove-machine

{{t:cli.commands.config.removeMachine.description}}

```bash
rdc config remove-machine <name>
```

<a id="cli-local-config-machines"></a>
### 2.11 machines

{{t:cli.commands.config.machines.description}}

```bash
rdc config machines
```

<a id="cli-local-config-set-ssh"></a>
### 2.12 set-ssh

{{t:cli.commands.config.setSsh.description}}

```bash
rdc config set-ssh [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--private-key <path>` | {{t:cli.options.sshPrivateKey}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--public-key <path>` | {{t:cli.options.sshPublicKey}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-config-set-renet"></a>
### 2.13 set-renet

{{t:cli.commands.config.setRenet.description}}

```bash
rdc config set-renet <path>
```

<a id="cli-local-config-setup-machine"></a>
### 2.14 setup-machine

{{t:cli.commands.config.setupMachine.description}}

```bash
rdc config setup-machine <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--datastore <path>` | {{t:cli.commands.config.setupMachine.datastoreOption}} | {{t:cli.docs.optionLabels.no}} | `/mnt/rediacc` |
| `--datastore-size <size>` | {{t:cli.commands.config.setupMachine.datastoreSizeOption}} | {{t:cli.docs.optionLabels.no}} | `95%` |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-config-import-storage"></a>
### 2.15 import-storage

{{t:cli.commands.config.importStorage.description}}

```bash
rdc config import-storage <file> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--name <name>` | {{t:cli.commands.config.importStorage.optionName}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-config-remove-storage"></a>
### 2.16 remove-storage

{{t:cli.commands.config.removeStorage.description}}

```bash
rdc config remove-storage <name>
```

<a id="cli-local-config-storages"></a>
### 2.17 storages

{{t:cli.commands.config.storages.description}}

```bash
rdc config storages
```

<a id="cli-local-config-add-repository"></a>
### 2.18 add-repository

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


<a id="cli-local-config-remove-repository"></a>
### 2.19 remove-repository

{{t:cli.commands.config.removeRepository.description}}

```bash
rdc config remove-repository <name>
```

<a id="cli-local-config-repositories"></a>
### 2.20 repositories

{{t:cli.commands.config.repositories.description}}

```bash
rdc config repositories
```

<a id="cli-local-config-list-archived"></a>
### 2.21 list-archived

{{t:cli.commands.config.listArchived.description}}

```bash
rdc config list-archived
```

<a id="cli-local-config-restore-archived"></a>
### 2.22 restore-archived

{{t:cli.commands.config.restoreArchived.description}}

```bash
rdc config restore-archived <guid> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--name <name>` | {{t:cli.commands.config.restoreArchived.optionName}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-config-purge-archived"></a>
### 2.23 purge-archived

{{t:cli.commands.config.purgeArchived.description}}

```bash
rdc config purge-archived
```

<a id="cli-local-config-set-infra"></a>
### 2.24 set-infra

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


<a id="cli-local-config-set-ceph"></a>
### 2.25 set-ceph

{{t:cli.commands.config.setCeph.description}}

```bash
rdc config set-ceph [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-m, --machine <name>` | {{t:cli.options.machine}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--pool <name>` | {{t:cli.commands.config.setCeph.optionPool}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--image <name>` | {{t:cli.commands.config.setCeph.optionImage}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--cluster <name>` | {{t:cli.options.cluster}} | {{t:cli.docs.optionLabels.no}} | `ceph` |


<a id="cli-local-config-add-provider"></a>
### 2.26 add-provider

{{t:cli.commands.config.addProvider.description}}

```bash
rdc config add-provider <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--provider <source>` | {{t:cli.commands.config.addProvider.optionProvider}} | {{t:cli.docs.optionLabels.no}} | - |
| `--source <source>` | {{t:cli.commands.config.addProvider.optionSource}} | {{t:cli.docs.optionLabels.no}} | - |
| `--token <token>` | {{t:cli.commands.config.addProvider.optionToken}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--region <region>` | {{t:cli.commands.config.addProvider.optionRegion}} | {{t:cli.docs.optionLabels.no}} | - |
| `--type <type>` | {{t:cli.commands.config.addProvider.optionInstanceType}} | {{t:cli.docs.optionLabels.no}} | - |
| `--image <image>` | {{t:cli.commands.config.addProvider.optionImage}} | {{t:cli.docs.optionLabels.no}} | - |
| `--ssh-user <user>` | {{t:cli.commands.config.addProvider.optionSshUser}} | {{t:cli.docs.optionLabels.no}} | - |
| `--resource <type>` | {{t:cli.commands.config.addProvider.optionResource}} | {{t:cli.docs.optionLabels.no}} | - |
| `--label-attr <attr>` | {{t:cli.commands.config.addProvider.optionLabelAttr}} | {{t:cli.docs.optionLabels.no}} | - |
| `--region-attr <attr>` | {{t:cli.commands.config.addProvider.optionRegionAttr}} | {{t:cli.docs.optionLabels.no}} | - |
| `--size-attr <attr>` | {{t:cli.commands.config.addProvider.optionSizeAttr}} | {{t:cli.docs.optionLabels.no}} | - |
| `--image-attr <attr>` | {{t:cli.commands.config.addProvider.optionImageAttr}} | {{t:cli.docs.optionLabels.no}} | - |
| `--ipv4-output <attr>` | {{t:cli.commands.config.addProvider.optionIpv4Output}} | {{t:cli.docs.optionLabels.no}} | - |
| `--ipv6-output <attr>` | {{t:cli.commands.config.addProvider.optionIpv6Output}} | {{t:cli.docs.optionLabels.no}} | - |
| `--ssh-key-attr <attr>` | {{t:cli.commands.config.addProvider.optionSshKeyAttr}} | {{t:cli.docs.optionLabels.no}} | - |
| `--ssh-key-format <format>` | {{t:cli.commands.config.addProvider.optionSshKeyFormat}} | {{t:cli.docs.optionLabels.no}} | - |
| `--ssh-key-resource <type>` | {{t:cli.commands.config.addProvider.optionSshKeyResource}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-config-remove-provider"></a>
### 2.27 remove-provider

{{t:cli.commands.config.removeProvider.description}}

```bash
rdc config remove-provider <name>
```

<a id="cli-local-config-providers"></a>
### 2.28 providers

{{t:cli.commands.config.providers.description}}

```bash
rdc config providers
```

<a id="cli-local-config-show-infra"></a>
### 2.29 show-infra

{{t:cli.commands.config.showInfra.description}}

```bash
rdc config show-infra <machine>
```

<a id="cli-local-config-push-infra"></a>
### 2.30 push-infra

{{t:cli.commands.config.pushInfra.description}}

```bash
rdc config push-infra <machine> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-config-cert-cache"></a>
### 2.31 cert-cache

{{t:cli.commands.config.certCache.description}}

<a id="cli-local-config-cert-cache-pull"></a>
#### pull

{{t:cli.commands.config.certCache.pull.description}}

```bash
rdc config cert-cache pull <machine> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--no-prune` | {{t:cli.commands.config.certCache.pull.optionNoPrune}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-config-cert-cache-push"></a>
#### push

{{t:cli.commands.config.certCache.push.description}}

```bash
rdc config cert-cache push <machine> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-config-cert-cache-status"></a>
#### status

{{t:cli.commands.config.certCache.status.description}}

```bash
rdc config cert-cache status
```

<a id="cli-local-config-cert-cache-clear"></a>
#### clear

{{t:cli.commands.config.certCache.clear.description}}

```bash
rdc config cert-cache clear
```

<a id="cli-local-config-backup-strategy"></a>
### 2.32 backup-strategy

{{t:cli.commands.config.backupStrategy.description}}

<a id="cli-local-config-backup-strategy-set"></a>
#### set

{{t:cli.commands.config.backupStrategy.set.description}}

```bash
rdc config backup-strategy set [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--destination <storage>` | {{t:cli.commands.config.backupStrategy.set.optionDestination}} | {{t:cli.docs.optionLabels.no}} | - |
| `--cron <expression>` | {{t:cli.commands.config.backupStrategy.set.optionCron}} | {{t:cli.docs.optionLabels.no}} | - |
| `--enable` | {{t:cli.commands.config.backupStrategy.set.optionEnable}} | {{t:cli.docs.optionLabels.no}} | - |
| `--disable` | {{t:cli.commands.config.backupStrategy.set.optionDisable}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-config-backup-strategy-show"></a>
#### show

{{t:cli.commands.config.backupStrategy.show.description}}

```bash
rdc config backup-strategy show
```

---

<a id="cli-local-group-datastore"></a>
## 3. {{t:cli.docs.sectionTitles.datastore}}

{{t:cli.commands.datastore.description}}

<a id="cli-local-datastore-init"></a>
### 3.1 init

{{t:cli.commands.datastore.init.description}}

```bash
rdc datastore init [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-m, --machine <name>` | {{t:cli.commands.datastore.machineOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--size <size>` | {{t:cli.commands.datastore.init.sizeOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--backend <type>` | {{t:cli.commands.datastore.init.backendOption}} | {{t:cli.docs.optionLabels.no}} | `local` |
| `--pool <name>` | {{t:cli.commands.datastore.init.poolOption}} | {{t:cli.docs.optionLabels.no}} | `rbd` |
| `--image <name>` | {{t:cli.commands.datastore.init.imageOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--cluster <name>` | {{t:cli.commands.datastore.init.clusterOption}} | {{t:cli.docs.optionLabels.no}} | `ceph` |
| `--force` | {{t:cli.commands.datastore.init.forceOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-datastore-fork"></a>
### 3.2 fork

{{t:cli.commands.datastore.fork.description}}

```bash
rdc datastore fork [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-m, --machine <name>` | {{t:cli.commands.datastore.machineOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--to <name>` | {{t:cli.commands.datastore.fork.toOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--cow-size <size>` | {{t:cli.commands.datastore.fork.cowSizeOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-datastore-unfork"></a>
### 3.3 unfork

{{t:cli.commands.datastore.unfork.description}}

```bash
rdc datastore unfork [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-m, --machine <name>` | {{t:cli.commands.datastore.machineOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--source <image>` | {{t:cli.commands.datastore.unfork.sourceOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--snapshot <name>` | {{t:cli.commands.datastore.unfork.snapshotOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--dest <image>` | {{t:cli.commands.datastore.unfork.destOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--pool <name>` | {{t:cli.commands.datastore.unfork.poolOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--mount-point <path>` | {{t:cli.commands.datastore.unfork.mountPointOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--force` | {{t:cli.commands.datastore.unfork.forceOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-datastore-status"></a>
### 3.4 status

{{t:cli.commands.datastore.status.description}}

```bash
rdc datastore status [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-m, --machine <name>` | {{t:cli.commands.datastore.machineOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |


---

<a id="cli-local-group-store"></a>
## 4. {{t:cli.docs.sectionTitles.store}}

{{t:cli.commands.store.description}}

<a id="cli-local-store-add"></a>
### 4.1 add

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


<a id="cli-local-store-list"></a>
### 4.2 list

{{t:cli.commands.store.list.description}}

```bash
rdc store list
```

<a id="cli-local-store-remove"></a>
### 4.3 remove

{{t:cli.commands.store.remove.description}}

```bash
rdc store remove <name>
```

<a id="cli-local-store-push"></a>
### 4.4 push

{{t:cli.commands.store.push.description}}

```bash
rdc store push [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--store <name>` | {{t:cli.commands.store.push.optionStore}} | {{t:cli.docs.optionLabels.no}} | - |
| `--all` | {{t:cli.commands.store.push.optionAll}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-store-pull"></a>
### 4.5 pull

{{t:cli.commands.store.pull.description}}

```bash
rdc store pull [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--store <name>` | {{t:cli.commands.store.pull.optionStore}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--config <name>` | {{t:cli.commands.store.pull.optionConfig}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-store-sync"></a>
### 4.6 sync

{{t:cli.commands.store.sync.description}}

```bash
rdc store sync [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--store <name>` | {{t:cli.commands.store.sync.optionStore}} | {{t:cli.docs.optionLabels.no}} | - |
| `--all` | {{t:cli.commands.store.sync.optionAll}} | {{t:cli.docs.optionLabels.no}} | - |


---

<a id="cli-local-group-machine"></a>
## 5. {{t:cli.docs.sectionTitles.machine}}

{{t:cli.commands.machine.description}}

<a id="cli-local-machine-list"></a>
### 5.1 list

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


<a id="cli-local-machine-create"></a>
### 5.2 create

{{t:cli.commands.machine.create.description}}

```bash
rdc machine create <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-t, --team <name>` | {{t:cli.options.team}} | {{t:cli.docs.optionLabels.no}} | - |
| `-b, --bridge <name>` | {{t:cli.options.bridge}} | {{t:cli.docs.optionLabels.no}} | - |
| `--vault <json>` | {{t:cli.options.vaultJsonMachine}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-machine-delete"></a>
### 5.3 delete

{{t:cli.commands.machine.delete.description}}

```bash
rdc machine delete <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-t, --team <name>` | {{t:cli.options.team}} | {{t:cli.docs.optionLabels.no}} | - |
| `-f, --force` | {{t:cli.options.force}} | {{t:cli.docs.optionLabels.no}} | - |
| `--dry-run` | {{t:cli.options.dryRun}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-machine-update"></a>
### 5.4 update

{{t:cli.commands.machine.update.description}}

```bash
rdc machine update
```

<a id="cli-local-machine-health"></a>
### 5.5 health

{{t:cli.commands.machine.health.description}}

{{t:cli.docs.supplements.machine.health.afterDescription}}

```bash
rdc machine health <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-t, --team <name>` | {{t:cli.options.team}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-machine-containers"></a>
### 5.6 containers

{{t:cli.commands.machine.containers.description}}

```bash
rdc machine containers <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-t, --team <name>` | {{t:cli.options.team}} | {{t:cli.docs.optionLabels.no}} | - |
| `--health-check` | {{t:cli.commands.machine.containers.healthCheck}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-machine-services"></a>
### 5.7 services

{{t:cli.commands.machine.services.description}}

```bash
rdc machine services <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-t, --team <name>` | {{t:cli.options.team}} | {{t:cli.docs.optionLabels.no}} | - |
| `--stability-check` | {{t:cli.commands.machine.services.stabilityCheck}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-machine-status"></a>
### 5.8 status

{{t:cli.commands.machine.status.description}}

```bash
rdc machine status <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-t, --team <name>` | {{t:cli.options.team}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-machine-vault-status"></a>
### 5.9 vault-status

{{t:cli.commands.machine.vaultStatus.description}}

```bash
rdc machine vault-status <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-t, --team <name>` | {{t:cli.options.team}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-machine-repos"></a>
### 5.10 repos

{{t:cli.commands.machine.repos.description}}

```bash
rdc machine repos <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-t, --team <name>` | {{t:cli.options.team}} | {{t:cli.docs.optionLabels.no}} | - |
| `--search <text>` | {{t:cli.options.searchRepos}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-machine-test-connection"></a>
### 5.11 test-connection

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

<a id="cli-local-machine-info"></a>
### 5.12 info

{{t:cli.commands.machine.info.description}}

```bash
rdc machine info <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-machine-provision"></a>
### 5.13 provision

{{t:cli.commands.machine.provision.description}}

```bash
rdc machine provision <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--provider <name>` | {{t:cli.commands.machine.provision.optionProvider}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--region <region>` | {{t:cli.commands.machine.provision.optionRegion}} | {{t:cli.docs.optionLabels.no}} | - |
| `--type <type>` | {{t:cli.commands.machine.provision.optionType}} | {{t:cli.docs.optionLabels.no}} | - |
| `--image <image>` | {{t:cli.commands.machine.provision.optionImage}} | {{t:cli.docs.optionLabels.no}} | - |
| `--ssh-user <user>` | {{t:cli.commands.machine.provision.optionSshUser}} | {{t:cli.docs.optionLabels.no}} | - |
| `--base-domain <domain>` | {{t:cli.commands.machine.provision.optionBaseDomain}} | {{t:cli.docs.optionLabels.no}} | - |
| `--no-infra` | {{t:cli.commands.machine.provision.optionNoInfra}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-machine-deprovision"></a>
### 5.14 deprovision

{{t:cli.commands.machine.deprovision.description}}

```bash
rdc machine deprovision <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--force` | {{t:cli.options.yes}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-machine-deploy-backup"></a>
### 5.15 deploy-backup

{{t:cli.commands.machine.deployBackup.description}}

```bash
rdc machine deploy-backup <machine> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |


---

<a id="cli-local-group-mcp"></a>
## 6. {{t:cli.docs.sectionTitles.mcp}}

{{t:cli.commands.mcp.description}}

<a id="cli-local-mcp-serve"></a>
### 6.1 serve

{{t:cli.commands.mcp.serve.description}}

```bash
rdc mcp serve [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--config <name>` | {{t:cli.commands.mcp.serve.configOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--timeout <ms>` | {{t:cli.commands.mcp.serve.timeoutOption}} | {{t:cli.docs.optionLabels.no}} | `120000` |
| `--allow-grand` | {{t:cli.commands.mcp.serve.allowGrandOption}} | {{t:cli.docs.optionLabels.no}} | - |


---

<a id="cli-local-group-repo"></a>
## 7. {{t:cli.docs.sectionTitles.repo}}

{{t:cli.commands.repo.description}}

<a id="cli-local-repo-mount"></a>
### 7.1 mount

{{t:cli.commands.repo.mount.description}}

```bash
rdc repo mount [name] [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-m, --machine <name>` | {{t:cli.commands.repo.machineOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--checkpoint` | {{t:cli.commands.repo.mount.checkpointOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--parallel` | {{t:cli.commands.repo.upAll.parallelOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--concurrency <n>` | {{t:cli.commands.repo.upAll.concurrencyOption}} | {{t:cli.docs.optionLabels.no}} | `3` |
| `-y, --yes` | {{t:cli.commands.repo.yesOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |
| `--skip-router-restart` | {{t:cli.options.skipRouterRestart}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-repo-unmount"></a>
### 7.2 unmount

{{t:cli.commands.repo.unmount.description}}

```bash
rdc repo unmount [name] [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-m, --machine <name>` | {{t:cli.commands.repo.machineOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--checkpoint` | {{t:cli.commands.repo.unmount.checkpointOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--parallel` | {{t:cli.commands.repo.upAll.parallelOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--concurrency <n>` | {{t:cli.commands.repo.upAll.concurrencyOption}} | {{t:cli.docs.optionLabels.no}} | `3` |
| `-y, --yes` | {{t:cli.commands.repo.yesOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |
| `--skip-router-restart` | {{t:cli.options.skipRouterRestart}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-repo-up"></a>
### 7.3 up

{{t:cli.commands.repo.up.description}}

```bash
rdc repo up [name] [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-m, --machine <name>` | {{t:cli.commands.repo.machineOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--mount` | {{t:cli.commands.repo.up.mountOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--checkpoint` | {{t:cli.commands.repo.up.checkpointOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--grand <name>` | {{t:cli.commands.repo.up.grandOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--include-forks` | {{t:cli.commands.repo.upAll.includeForksOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--mount-only` | {{t:cli.commands.repo.upAll.mountOnlyOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--parallel` | {{t:cli.commands.repo.upAll.parallelOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--concurrency <n>` | {{t:cli.commands.repo.upAll.concurrencyOption}} | {{t:cli.docs.optionLabels.no}} | `3` |
| `-y, --yes` | {{t:cli.commands.repo.yesOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |
| `--skip-router-restart` | {{t:cli.options.skipRouterRestart}} | {{t:cli.docs.optionLabels.no}} | - |
| `--dry-run` | {{t:cli.options.dryRun}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-repo-up-all"></a>
### 7.4 up-all

{{t:cli.commands.repo.upAll.description}}

```bash
rdc repo up-all
```

<a id="cli-local-repo-down"></a>
### 7.5 down

{{t:cli.commands.repo.down.description}}

```bash
rdc repo down [name] [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-m, --machine <name>` | {{t:cli.commands.repo.machineOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--unmount` | {{t:cli.commands.repo.down.unmountOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--grand <name>` | {{t:cli.commands.repo.up.grandOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `-y, --yes` | {{t:cli.commands.repo.yesOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |
| `--skip-router-restart` | {{t:cli.options.skipRouterRestart}} | {{t:cli.docs.optionLabels.no}} | - |
| `--dry-run` | {{t:cli.options.dryRun}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-repo-status"></a>
### 7.6 status

{{t:cli.commands.repo.status.description}}

```bash
rdc repo status <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-m, --machine <name>` | {{t:cli.commands.repo.machineOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |
| `--skip-router-restart` | {{t:cli.options.skipRouterRestart}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-repo-list"></a>
### 7.7 list

{{t:cli.commands.repo.list.description}}

```bash
rdc repo list [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-m, --machine <name>` | {{t:cli.commands.repo.machineOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |
| `--skip-router-restart` | {{t:cli.options.skipRouterRestart}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-repo-create"></a>
### 7.8 create

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


<a id="cli-local-repo-delete"></a>
### 7.9 delete

{{t:cli.commands.repo.delete.description}}

```bash
rdc repo delete <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-m, --machine <name>` | {{t:cli.commands.repo.machineOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |
| `--skip-router-restart` | {{t:cli.options.skipRouterRestart}} | {{t:cli.docs.optionLabels.no}} | - |
| `--dry-run` | {{t:cli.options.dryRun}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-repo-fork"></a>
### 7.10 fork

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


<a id="cli-local-repo-resize"></a>
### 7.11 resize

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


<a id="cli-local-repo-expand"></a>
### 7.12 expand

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


<a id="cli-local-repo-validate"></a>
### 7.13 validate

{{t:cli.commands.repo.validate.description}}

```bash
rdc repo validate <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-m, --machine <name>` | {{t:cli.commands.repo.machineOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |
| `--skip-router-restart` | {{t:cli.options.skipRouterRestart}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-repo-autostart"></a>
### 7.14 autostart

{{t:cli.commands.repo.autostart.description}}

<a id="cli-local-repo-autostart-enable"></a>
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


<a id="cli-local-repo-autostart-disable"></a>
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


<a id="cli-local-repo-autostart-enable-all"></a>
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


<a id="cli-local-repo-autostart-disable-all"></a>
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


<a id="cli-local-repo-autostart-list"></a>
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


<a id="cli-local-repo-ownership"></a>
### 7.15 ownership

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


<a id="cli-local-repo-template"></a>
### 7.16 template

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


<a id="cli-local-repo-push"></a>
### 7.17 push

{{t:cli.commands.repo.push.description}}

```bash
rdc repo push [repo] [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--dest <filename>` | {{t:cli.commands.repo.push.optionDest}} | {{t:cli.docs.optionLabels.no}} | - |
| `--to <storage>` | {{t:cli.commands.repo.push.optionToStorage}} | {{t:cli.docs.optionLabels.no}} | - |
| `--to-machine <machine>` | {{t:cli.commands.repo.push.optionToMachine}} | {{t:cli.docs.optionLabels.no}} | - |
| `--provider <name>` | {{t:cli.commands.repo.push.optionProvider}} | {{t:cli.docs.optionLabels.no}} | - |
| `--checkpoint` | {{t:cli.commands.repo.push.optionCheckpoint}} | {{t:cli.docs.optionLabels.no}} | - |
| `--force` | {{t:cli.commands.repo.push.optionForce}} | {{t:cli.docs.optionLabels.no}} | - |
| `--tag <tag>` | {{t:cli.commands.repo.push.optionTag}} | {{t:cli.docs.optionLabels.no}} | - |
| `-m, --machine <name>` | {{t:cli.options.machine}} | {{t:cli.docs.optionLabels.no}} | - |
| `-w, --watch` | {{t:cli.options.watch}} | {{t:cli.docs.optionLabels.no}} | - |
| `--parallel` | {{t:cli.commands.repo.upAll.parallelOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--concurrency <n>` | {{t:cli.commands.repo.upAll.concurrencyOption}} | {{t:cli.docs.optionLabels.no}} | `3` |
| `-y, --yes` | {{t:cli.commands.repo.yesOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |
| `--skip-router-restart` | {{t:cli.options.skipRouterRestart}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-repo-pull"></a>
### 7.18 pull

{{t:cli.commands.repo.pull.description}}

```bash
rdc repo pull [repo] [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--from <storage>` | {{t:cli.commands.repo.pull.optionFromStorage}} | {{t:cli.docs.optionLabels.no}} | - |
| `--from-machine <machine>` | {{t:cli.commands.repo.pull.optionFromMachine}} | {{t:cli.docs.optionLabels.no}} | - |
| `--force` | {{t:cli.commands.repo.pull.optionForce}} | {{t:cli.docs.optionLabels.no}} | - |
| `-m, --machine <name>` | {{t:cli.options.machine}} | {{t:cli.docs.optionLabels.no}} | - |
| `-w, --watch` | {{t:cli.options.watch}} | {{t:cli.docs.optionLabels.no}} | - |
| `--parallel` | {{t:cli.commands.repo.upAll.parallelOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--concurrency <n>` | {{t:cli.commands.repo.upAll.concurrencyOption}} | {{t:cli.docs.optionLabels.no}} | `3` |
| `-y, --yes` | {{t:cli.commands.repo.yesOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |
| `--skip-router-restart` | {{t:cli.options.skipRouterRestart}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-repo-list-backups"></a>
### 7.19 list-backups

{{t:cli.commands.repo.listBackups.description}}

```bash
rdc repo list-backups [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--from <storage>` | {{t:cli.commands.repo.pull.optionFromStorage}} | {{t:cli.docs.optionLabels.no}} | - |
| `--from-machine <machine>` | {{t:cli.commands.repo.pull.optionFromMachine}} | {{t:cli.docs.optionLabels.no}} | - |
| `-m, --machine <name>` | {{t:cli.options.machine}} | {{t:cli.docs.optionLabels.no}} | - |
| `-w, --watch` | {{t:cli.options.watch}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |
| `--skip-router-restart` | {{t:cli.options.skipRouterRestart}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-repo-sync"></a>
### 7.20 sync

{{t:cli.commands.repo.sync.description}}

<a id="cli-local-repo-sync-push-all"></a>
#### push-all

{{t:cli.commands.repo.sync.pushAll.description}}

```bash
rdc repo sync push-all [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--to <storage>` | {{t:cli.commands.repo.push.optionToStorage}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--repo <name>` | {{t:cli.commands.repo.sync.pushAll.optionRepo}} | {{t:cli.docs.optionLabels.no}} | - |
| `-m, --machine <name>` | {{t:cli.options.machine}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-repo-sync-pull-all"></a>
#### pull-all

{{t:cli.commands.repo.sync.pullAll.description}}

```bash
rdc repo sync pull-all [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--from <storage>` | {{t:cli.commands.repo.pull.optionFromStorage}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--repo <name>` | {{t:cli.commands.repo.sync.pushAll.optionRepo}} | {{t:cli.docs.optionLabels.no}} | - |
| `--override` | {{t:cli.commands.repo.sync.pullAll.optionOverride}} | {{t:cli.docs.optionLabels.no}} | - |
| `-m, --machine <name>` | {{t:cli.options.machine}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-repo-sync-upload"></a>
#### upload

{{t:cli.commands.repo.sync.upload.description}}

```bash
rdc repo sync upload [options]
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


<a id="cli-local-repo-sync-download"></a>
#### download

{{t:cli.commands.repo.sync.download.description}}

```bash
rdc repo sync download [options]
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


<a id="cli-local-repo-sync-status"></a>
#### status

{{t:cli.commands.repo.sync.status.description}}

```bash
rdc repo sync status [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-t, --team <name>` | {{t:cli.options.team}} | {{t:cli.docs.optionLabels.no}} | - |
| `-m, --machine <name>` | {{t:cli.options.machine}} | {{t:cli.docs.optionLabels.no}} | - |
| `-r, --repository <name>` | {{t:cli.options.repository}} | {{t:cli.docs.optionLabels.no}} | - |
| `-l, --local <path>` | {{t:cli.options.localPath}} | {{t:cli.docs.optionLabels.no}} | - |
| `--remote <path>` | {{t:cli.options.remotePath}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-repo-snapshot"></a>
### 7.21 snapshot

{{t:cli.commands.repo.snapshot.description}}

<a id="cli-local-repo-snapshot-create"></a>
#### create

{{t:cli.commands.repo.snapshot.create.description}}

```bash
rdc repo snapshot create <repo> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-m, --machine <name>` | {{t:cli.options.machine}} | {{t:cli.docs.optionLabels.no}} | - |
| `--snapshot-name <name>` | {{t:cli.commands.repo.snapshot.create.optionSnapshotName}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-repo-snapshot-list"></a>
#### list

{{t:cli.commands.repo.snapshot.list.description}}

```bash
rdc repo snapshot list [repo] [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-m, --machine <name>` | {{t:cli.options.machine}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-repo-snapshot-delete"></a>
#### delete

{{t:cli.commands.repo.snapshot.delete.description}}

```bash
rdc repo snapshot delete <repo> <snapshot-name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-m, --machine <name>` | {{t:cli.options.machine}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |
| `--dry-run` | {{t:cli.options.dryRun}} | {{t:cli.docs.optionLabels.no}} | - |


---

<a id="cli-local-group-storage"></a>
## 8. {{t:cli.docs.sectionTitles.storage}}

{{t:cli.commands.storage.description}}

<a id="cli-local-storage-list"></a>
### 8.1 list

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


<a id="cli-local-storage-browse"></a>
### 8.2 browse

{{t:cli.commands.storage.browse.description}}

```bash
rdc storage browse <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--path <subpath>` | {{t:cli.commands.storage.browse.pathOption}} | {{t:cli.docs.optionLabels.no}} | `` |


<a id="cli-local-storage-pull"></a>
### 8.3 pull

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

<a id="cli-local-group-vscode"></a>
## 9. {{t:cli.docs.sectionTitles.vscode}}

{{t:cli.commands.vscode.description}}

<a id="cli-local-vscode-connect"></a>
### 9.1 connect

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


<a id="cli-local-vscode-list"></a>
### 9.2 list

{{t:cli.commands.vscode.list.description}}

```bash
rdc vscode list
```

<a id="cli-local-vscode-cleanup"></a>
### 9.3 cleanup

{{t:cli.commands.vscode.cleanup.description}}

```bash
rdc vscode cleanup [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--all` | {{t:cli.options.cleanupAll}} | {{t:cli.docs.optionLabels.no}} | - |
| `-c, --connection <name>` | {{t:cli.options.connectionName}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-vscode-check"></a>
### 9.4 check

{{t:cli.commands.vscode.check.description}}

```bash
rdc vscode check [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--insiders` | {{t:cli.options.insiders}} | {{t:cli.docs.optionLabels.no}} | - |


---

<a id="cli-local-group-term"></a>
## 10. {{t:cli.docs.sectionTitles.term}}

{{t:cli.commands.term.description}}

<a id="cli-local-term-connect"></a>
### 10.1 connect

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

<a id="cli-local-group-protocol"></a>
## 11. {{t:cli.docs.sectionTitles.protocol}}

{{t:cli.commands.protocol.description}}

<a id="cli-local-protocol-register"></a>
### 11.1 register

{{t:cli.commands.protocol.register.description}}

```bash
rdc protocol register [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--system` | {{t:cli.options.protocolSystem}} | {{t:cli.docs.optionLabels.no}} | - |
| `--force` | {{t:cli.options.protocolForce}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-protocol-unregister"></a>
### 11.2 unregister

{{t:cli.commands.protocol.unregister.description}}

```bash
rdc protocol unregister [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--system` | {{t:cli.options.protocolSystemUnregister}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-protocol-status"></a>
### 11.3 status

{{t:cli.commands.protocol.status.description}}

```bash
rdc protocol status
```

<a id="cli-local-protocol-open"></a>
### 11.4 open

{{t:cli.commands.protocol.open.description}}

```bash
rdc protocol open <url>
```

<a id="cli-local-protocol-build"></a>
### 11.5 build

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


<a id="cli-local-protocol-parse"></a>
### 11.6 parse

{{t:cli.commands.protocol.parse.description}}

```bash
rdc protocol parse <url>
```

---

<a id="cli-local-group-shortcuts"></a>
## 12. {{t:cli.docs.sectionTitles.shortcuts}}

<a id="cli-local-shortcuts-run"></a>
### 12.1 run

{{t:cli.commands.shortcuts.run.description}}

```bash
rdc run
```

<a id="cli-local-shortcuts-trace"></a>
### 12.2 trace

{{t:cli.commands.shortcuts.trace.description}}

```bash
rdc trace
```

<a id="cli-local-shortcuts-cancel"></a>
### 12.3 cancel

{{t:cli.commands.shortcuts.cancel.description}}

```bash
rdc cancel
```

<a id="cli-local-shortcuts-retry"></a>
### 12.4 retry

{{t:cli.commands.shortcuts.retry.description}}

```bash
rdc retry
```

---

<a id="cli-local-group-subscription"></a>
## 13. {{t:cli.docs.sectionTitles.subscription}}

{{t:cli.commands.subscription.description}}

<a id="cli-local-subscription-login"></a>
### 13.1 login

{{t:cli.commands.subscription.login.description}}

```bash
rdc subscription login [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-t, --token <token>` | {{t:cli.options.apiToken}} | {{t:cli.docs.optionLabels.no}} | - |
| `--server <url>` | {{t:cli.options.serverUrl}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-subscription-status"></a>
### 13.2 status

{{t:cli.commands.subscription.status.description}}

```bash
rdc subscription status
```

<a id="cli-local-subscription-activation-status"></a>
### 13.3 activation-status

{{t:cli.commands.subscription.activationStatus.description}}

```bash
rdc subscription activation-status [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-m, --machine <name>` | {{t:cli.options.machine}} | {{t:cli.docs.optionLabels.yes}} | - |


<a id="cli-local-subscription-refresh"></a>
### 13.4 refresh

{{t:cli.commands.subscription.refresh.description}}

```bash
rdc subscription refresh [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-m, --machine <name>` | {{t:cli.options.machine}} | {{t:cli.docs.optionLabels.yes}} | - |


<a id="cli-local-subscription-refresh-activation"></a>
### 13.5 refresh-activation

{{t:cli.commands.subscription.refreshActivation.description}}

```bash
rdc subscription refresh-activation [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-m, --machine <name>` | {{t:cli.options.machine}} | {{t:cli.docs.optionLabels.yes}} | - |


<a id="cli-local-subscription-refresh-repos"></a>
### 13.6 refresh-repos

{{t:cli.commands.subscription.refreshRepos.description}}

```bash
rdc subscription refresh-repos [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-m, --machine <name>` | {{t:cli.options.machine}} | {{t:cli.docs.optionLabels.yes}} | - |


<a id="cli-local-subscription-repo-status"></a>
### 13.7 repo-status

{{t:cli.commands.subscription.repoStatus.description}}

```bash
rdc subscription repo-status [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-m, --machine <name>` | {{t:cli.options.machine}} | {{t:cli.docs.optionLabels.yes}} | - |


<a id="cli-local-subscription-refresh-repo"></a>
### 13.8 refresh-repo

{{t:cli.commands.subscription.refreshRepo.description}}

```bash
rdc subscription refresh-repo <repo> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-m, --machine <name>` | {{t:cli.options.machine}} | {{t:cli.docs.optionLabels.yes}} | - |


---

<a id="cli-local-group-update"></a>
## 14. {{t:cli.docs.sectionTitles.update}}

{{t:cli.commands.update.description}}

<a id="cli-local-update"></a>
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

<a id="cli-local-group-doctor"></a>
## 15. {{t:cli.docs.sectionTitles.doctor}}

{{t:cli.commands.doctor.description}}

<a id="cli-local-doctor"></a>
```bash
rdc doctor
```

---

<a id="cli-local-group-ops"></a>
## 16. {{t:cli.docs.sectionTitles.ops}}

{{t:cli.commands.ops.description}}

<a id="cli-local-ops-up"></a>
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


<a id="cli-local-ops-down"></a>
### 16.2 down

{{t:cli.commands.ops.down.description}}

```bash
rdc ops down [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--backend <backend>` | {{t:cli.options.opsBackend}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-ops-status"></a>
### 16.3 status

{{t:cli.commands.ops.status.description}}

```bash
rdc ops status [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--backend <backend>` | {{t:cli.options.opsBackend}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-ops-ssh"></a>
### 16.4 ssh

{{t:cli.commands.ops.ssh.description}}

```bash
rdc ops ssh <vmId> [command...] [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--backend <backend>` | {{t:cli.options.opsBackend}} | {{t:cli.docs.optionLabels.no}} | - |
| `--user <user>` | {{t:cli.options.opsSSHUser}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-ops-setup"></a>
### 16.5 setup

{{t:cli.commands.ops.setup.description}}

```bash
rdc ops setup [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-ops-check"></a>
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
