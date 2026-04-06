---
title: "CLIアプリケーション"
description: "プラットフォーム管理のためのRediaccコマンドラインインターフェースの完全ガイド"
category: "リファレンス"
order: 2
language: ja
generated: true
generatedFrom: packages/cli/src/i18n/locales/ja/cli.json
sourceHash: "998c7fff6f303d02"
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
curl -fsSL https://www.rediacc.com | sh

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
rdc agent schema [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--command <path>` | {{t:cli.options.command}} | {{t:cli.docs.optionLabels.yes}} | - |


<a id="cli-local-agent-exec"></a>
### 1.3 exec

{{t:cli.commands.agent.exec.description}}

```bash
rdc agent exec [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--command <path>` | {{t:cli.options.command}} | {{t:cli.docs.optionLabels.yes}} | - |


<a id="cli-local-agent-generate-reference"></a>
### 1.4 generate-reference

{{t:cli.commands.agent.generateReference.description}}

```bash
rdc agent generate-reference
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
rdc config init [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--name <name>` | {{t:cli.options.name}} | {{t:cli.docs.optionLabels.no}} | - |
| `--ssh-key <path>` | {{t:cli.options.sshKey}} | {{t:cli.docs.optionLabels.no}} | - |
| `--renet-path <path>` | {{t:cli.options.renetPath}} | {{t:cli.docs.optionLabels.no}} | - |
| `--master-password <password>` | {{t:cli.commands.config.init.optionMasterPassword}} | {{t:cli.docs.optionLabels.no}} | - |
| `-u, --api-url <url>` | {{t:cli.options.apiUrl}} | {{t:cli.docs.optionLabels.no}} | - |
| `--server <url>` | {{t:cli.options.serverUrl}} | {{t:cli.docs.optionLabels.no}} | - |


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
rdc config delete [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--name <name>` | {{t:cli.options.name}} | {{t:cli.docs.optionLabels.yes}} | - |


<a id="cli-local-config-set"></a>
### 2.5 set

{{t:cli.commands.config.set.description}}

```bash
rdc config set [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--key <key>` | {{t:cli.options.configKey}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--value <value>` | {{t:cli.options.configValue}} | {{t:cli.docs.optionLabels.yes}} | - |


> **{{t:cli.docs.admonitions.tip}}**: {{t:cli.docs.supplements.config.set.tip}}

<a id="cli-local-config-clear"></a>
### 2.6 clear

{{t:cli.commands.config.clear.description}}

```bash
rdc config clear [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--key <key>` | {{t:cli.options.configKey}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-config-recover"></a>
### 2.7 recover

{{t:cli.commands.config.recover.description}}

```bash
rdc config recover [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--name <name>` | {{t:cli.options.name}} | {{t:cli.docs.optionLabels.no}} | - |
| `-y, --yes` | {{t:cli.options.yes}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-config-set-ssh"></a>
### 2.8 set-ssh

{{t:cli.commands.config.setSsh.description}}

```bash
rdc config set-ssh
```

<a id="cli-local-config-set-renet"></a>
### 2.9 set-renet

{{t:cli.commands.config.setRenet.description}}

```bash
rdc config set-renet
```

<a id="cli-local-config-ssh"></a>
### 2.10 ssh

{{t:cli.commands.config.ssh.description}}

<a id="cli-local-config-ssh-set"></a>
#### set

{{t:cli.commands.config.ssh.set.description}}

```bash
rdc config ssh set [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--key <path>` | {{t:cli.commands.config.ssh.set.optionKey}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--embed` | {{t:cli.commands.config.ssh.set.optionEmbed}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-config-ssh-show"></a>
#### show

{{t:cli.commands.config.ssh.show.description}}

```bash
rdc config ssh show
```

<a id="cli-local-config-ssh-remove"></a>
#### remove

{{t:cli.commands.config.ssh.remove.description}}

```bash
rdc config ssh remove
```

<a id="cli-local-config-remote"></a>
### 2.11 remote

{{t:cli.commands.config.remote.description}}

<a id="cli-local-config-remote-enable"></a>
#### enable

{{t:cli.commands.config.remote.enable.description}}

```bash
rdc config remote enable [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--headless` | {{t:cli.commands.config.remote.enable.optionHeadless}} | {{t:cli.docs.optionLabels.no}} | - |
| `--api-url <url>` | {{t:cli.options.serverUrl}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-config-remote-disable"></a>
#### disable

{{t:cli.commands.config.remote.disable.description}}

```bash
rdc config remote disable
```

<a id="cli-local-config-remote-status"></a>
#### status

{{t:cli.commands.config.remote.status.description}}

```bash
rdc config remote status
```

<a id="cli-local-config-remote-refresh"></a>
#### refresh

{{t:cli.commands.config.remote.refresh.description}}

```bash
rdc config remote refresh
```

<a id="cli-local-config-machine"></a>
### 2.12 machine

{{t:cli.commands.config.machine.description}}

<a id="cli-local-config-machine-add"></a>
#### add

{{t:cli.commands.config.machine.add.description}}

```bash
rdc config machine add [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--name <name>` | {{t:cli.options.name}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--ip <address>` | {{t:cli.options.machineIp}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--user <username>` | {{t:cli.options.sshUser}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--port <port>` | {{t:cli.options.sshPort}} | {{t:cli.docs.optionLabels.no}} | `22` |
| `--datastore <path>` | {{t:cli.options.datastore}} | {{t:cli.docs.optionLabels.no}} | `/mnt/rediacc` |


<a id="cli-local-config-machine-remove"></a>
#### remove

{{t:cli.commands.config.machine.remove.description}}

```bash
rdc config machine remove [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--name <name>` | {{t:cli.options.name}} | {{t:cli.docs.optionLabels.yes}} | - |


<a id="cli-local-config-machine-list"></a>
#### list

{{t:cli.commands.config.machine.list.description}}

```bash
rdc config machine list
```

<a id="cli-local-config-machine-scan-keys"></a>
#### scan-keys

{{t:cli.commands.config.machine.scanKeys.description}}

```bash
rdc config machine scan-keys [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-m, --machine <name>` | {{t:cli.options.machine}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-config-machine-setup"></a>
#### setup

{{t:cli.commands.config.machine.setup.description}}

```bash
rdc config machine setup [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--name <name>` | {{t:cli.options.name}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--datastore <path>` | {{t:cli.commands.config.machine.setup.datastoreOption}} | {{t:cli.docs.optionLabels.no}} | `/mnt/rediacc` |
| `--datastore-size <size>` | {{t:cli.commands.config.machine.setup.datastoreSizeOption}} | {{t:cli.docs.optionLabels.no}} | `95%` |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-config-machine-set-ceph"></a>
#### set-ceph

{{t:cli.commands.config.machine.setCeph.description}}

```bash
rdc config machine set-ceph [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-m, --machine <name>` | {{t:cli.options.machine}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--pool <name>` | {{t:cli.commands.config.machine.setCeph.optionPool}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--image <name>` | {{t:cli.commands.config.machine.setCeph.optionImage}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--cluster <name>` | {{t:cli.options.cluster}} | {{t:cli.docs.optionLabels.no}} | `ceph` |


<a id="cli-local-config-repository"></a>
### 2.13 repository

{{t:cli.commands.config.repository.description}}

<a id="cli-local-config-repository-add"></a>
#### add

{{t:cli.commands.config.repository.add.description}}

```bash
rdc config repository add [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--name <name>` | {{t:cli.options.name}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--guid <guid>` | {{t:cli.commands.config.repository.add.optionGuid}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--tag <tag>` | {{t:cli.options.repositoryTag}} | {{t:cli.docs.optionLabels.no}} | `latest` |
| `--credential <credential>` | {{t:cli.commands.config.repository.add.optionCredential}} | {{t:cli.docs.optionLabels.no}} | - |
| `--network-id <id>` | {{t:cli.commands.config.repository.add.optionNetworkId}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-config-repository-remove"></a>
#### remove

{{t:cli.commands.config.repository.remove.description}}

```bash
rdc config repository remove [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--name <name>` | {{t:cli.options.name}} | {{t:cli.docs.optionLabels.yes}} | - |


<a id="cli-local-config-repository-list"></a>
#### list

{{t:cli.commands.config.repository.list.description}}

```bash
rdc config repository list
```

<a id="cli-local-config-repository-list-archived"></a>
#### list-archived

{{t:cli.commands.config.repository.listArchived.description}}

```bash
rdc config repository list-archived
```

<a id="cli-local-config-repository-restore-archived"></a>
#### restore-archived

{{t:cli.commands.config.repository.restoreArchived.description}}

```bash
rdc config repository restore-archived [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--name <name>` | {{t:cli.options.name}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--new-name <name>` | {{t:cli.options.newName}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-config-repository-purge-archived"></a>
#### purge-archived

{{t:cli.commands.config.repository.purgeArchived.description}}

```bash
rdc config repository purge-archived
```

<a id="cli-local-config-provider"></a>
### 2.14 provider

{{t:cli.commands.config.provider.description}}

<a id="cli-local-config-provider-add"></a>
#### add

{{t:cli.commands.config.provider.add.description}}

```bash
rdc config provider add [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--name <name>` | {{t:cli.options.name}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--provider <source>` | {{t:cli.commands.config.provider.add.optionProvider}} | {{t:cli.docs.optionLabels.no}} | - |
| `--source <source>` | {{t:cli.commands.config.provider.add.optionSource}} | {{t:cli.docs.optionLabels.no}} | - |
| `--token <token>` | {{t:cli.commands.config.provider.add.optionToken}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--region <region>` | {{t:cli.commands.config.provider.add.optionRegion}} | {{t:cli.docs.optionLabels.no}} | - |
| `--type <type>` | {{t:cli.commands.config.provider.add.optionInstanceType}} | {{t:cli.docs.optionLabels.no}} | - |
| `--image <image>` | {{t:cli.commands.config.provider.add.optionImage}} | {{t:cli.docs.optionLabels.no}} | - |
| `--ssh-user <user>` | {{t:cli.commands.config.provider.add.optionSshUser}} | {{t:cli.docs.optionLabels.no}} | - |
| `--resource <type>` | {{t:cli.commands.config.provider.add.optionResource}} | {{t:cli.docs.optionLabels.no}} | - |
| `--label-attr <attr>` | {{t:cli.commands.config.provider.add.optionLabelAttr}} | {{t:cli.docs.optionLabels.no}} | - |
| `--region-attr <attr>` | {{t:cli.commands.config.provider.add.optionRegionAttr}} | {{t:cli.docs.optionLabels.no}} | - |
| `--size-attr <attr>` | {{t:cli.commands.config.provider.add.optionSizeAttr}} | {{t:cli.docs.optionLabels.no}} | - |
| `--image-attr <attr>` | {{t:cli.commands.config.provider.add.optionImageAttr}} | {{t:cli.docs.optionLabels.no}} | - |
| `--ipv4-output <attr>` | {{t:cli.commands.config.provider.add.optionIpv4Output}} | {{t:cli.docs.optionLabels.no}} | - |
| `--ipv6-output <attr>` | {{t:cli.commands.config.provider.add.optionIpv6Output}} | {{t:cli.docs.optionLabels.no}} | - |
| `--ssh-key-attr <attr>` | {{t:cli.commands.config.provider.add.optionSshKeyAttr}} | {{t:cli.docs.optionLabels.no}} | - |
| `--ssh-key-format <format>` | {{t:cli.commands.config.provider.add.optionSshKeyFormat}} | {{t:cli.docs.optionLabels.no}} | - |
| `--ssh-key-resource <type>` | {{t:cli.commands.config.provider.add.optionSshKeyResource}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-config-provider-remove"></a>
#### remove

{{t:cli.commands.config.provider.remove.description}}

```bash
rdc config provider remove [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--name <name>` | {{t:cli.options.name}} | {{t:cli.docs.optionLabels.yes}} | - |


<a id="cli-local-config-provider-list"></a>
#### list

{{t:cli.commands.config.provider.list.description}}

```bash
rdc config provider list
```

<a id="cli-local-config-storage"></a>
### 2.15 storage

{{t:cli.commands.config.storage.description}}

<a id="cli-local-config-storage-import"></a>
#### import

{{t:cli.commands.config.storage.import.description}}

```bash
rdc config storage import [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--file <path>` | {{t:cli.options.file}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--name <name>` | {{t:cli.commands.config.storage.import.optionName}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-config-storage-remove"></a>
#### remove

{{t:cli.commands.config.storage.remove.description}}

```bash
rdc config storage remove [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--name <name>` | {{t:cli.options.name}} | {{t:cli.docs.optionLabels.yes}} | - |


<a id="cli-local-config-storage-list"></a>
#### list

{{t:cli.commands.config.storage.list.description}}

```bash
rdc config storage list
```

<a id="cli-local-config-infra"></a>
### 2.16 infra

{{t:cli.commands.config.infra.description}}

<a id="cli-local-config-infra-set"></a>
#### set

{{t:cli.commands.config.infra.set.description}}

```bash
rdc config infra set [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-m, --machine <name>` | {{t:cli.options.machine}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--public-ipv4 <ip>` | {{t:cli.commands.config.infra.set.optionPublicIPv4}} | {{t:cli.docs.optionLabels.no}} | - |
| `--public-ipv6 <ip>` | {{t:cli.commands.config.infra.set.optionPublicIPv6}} | {{t:cli.docs.optionLabels.no}} | - |
| `--base-domain <domain>` | {{t:cli.commands.config.infra.set.optionBaseDomain}} | {{t:cli.docs.optionLabels.no}} | - |
| `--cert-email <email>` | {{t:cli.commands.config.infra.set.optionCertEmail}} | {{t:cli.docs.optionLabels.no}} | - |
| `--cf-dns-token <token>` | {{t:cli.commands.config.infra.set.optionCfDnsToken}} | {{t:cli.docs.optionLabels.no}} | - |
| `--tcp-ports <ports>` | {{t:cli.commands.config.infra.set.optionTcpPorts}} | {{t:cli.docs.optionLabels.no}} | - |
| `--udp-ports <ports>` | {{t:cli.commands.config.infra.set.optionUdpPorts}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-config-infra-show"></a>
#### show

{{t:cli.commands.config.infra.show.description}}

```bash
rdc config infra show [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-m, --machine <name>` | {{t:cli.options.machine}} | {{t:cli.docs.optionLabels.yes}} | - |


<a id="cli-local-config-infra-push"></a>
#### push

{{t:cli.commands.config.infra.push.description}}

```bash
rdc config infra push [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-m, --machine <name>` | {{t:cli.options.machine}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-config-cert-cache"></a>
### 2.17 cert-cache

{{t:cli.commands.config.certCache.description}}

<a id="cli-local-config-cert-cache-pull"></a>
#### pull

{{t:cli.commands.config.certCache.pull.description}}

```bash
rdc config cert-cache pull [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-m, --machine <name>` | {{t:cli.options.machine}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--no-prune` | {{t:cli.commands.config.certCache.pull.optionNoPrune}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-config-cert-cache-push"></a>
#### push

{{t:cli.commands.config.certCache.push.description}}

```bash
rdc config cert-cache push [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-m, --machine <name>` | {{t:cli.options.machine}} | {{t:cli.docs.optionLabels.yes}} | - |
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
### 2.18 backup-strategy

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

<a id="cli-local-group-machine"></a>
## 4. {{t:cli.docs.sectionTitles.machine}}

{{t:cli.commands.machine.description}}

<a id="cli-local-machine-list"></a>
### 4.1 list

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
### 4.2 create

{{t:cli.commands.machine.create.description}}

```bash
rdc machine create [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--name <name>` | {{t:cli.options.name}} | {{t:cli.docs.optionLabels.yes}} | - |
| `-t, --team <name>` | {{t:cli.options.team}} | {{t:cli.docs.optionLabels.no}} | - |
| `-b, --bridge <name>` | {{t:cli.options.bridge}} | {{t:cli.docs.optionLabels.no}} | - |
| `--vault <json>` | {{t:cli.options.vaultJsonMachine}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-machine-rename"></a>
### 4.3 rename

{{t:cli.commands.machine.rename.description}}

```bash
rdc machine rename [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--current-name <name>` | {{t:cli.options.currentName}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--new-name <name>` | {{t:cli.options.newName}} | {{t:cli.docs.optionLabels.yes}} | - |
| `-t, --team <name>` | {{t:cli.options.team}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-machine-delete"></a>
### 4.4 delete

{{t:cli.commands.machine.delete.description}}

```bash
rdc machine delete [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--name <name>` | {{t:cli.options.name}} | {{t:cli.docs.optionLabels.yes}} | - |
| `-t, --team <name>` | {{t:cli.options.team}} | {{t:cli.docs.optionLabels.no}} | - |
| `-f, --force` | {{t:cli.options.force}} | {{t:cli.docs.optionLabels.no}} | - |
| `--dry-run` | {{t:cli.options.dryRun}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-machine-vault"></a>
### 4.5 vault

{{t:cli.commands.machine.vault.description}}

```bash
rdc machine vault
```

<a id="cli-local-machine-vault-status"></a>
### 4.6 vault-status

{{t:cli.commands.machine.vault-status.description}}

```bash
rdc machine vault-status [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--name <name>` | {{t:cli.options.name}} | {{t:cli.docs.optionLabels.yes}} | - |
| `-t, --team <name>` | {{t:cli.options.team}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-machine-update"></a>
### 4.7 update

{{t:cli.commands.machine.update.description}}

```bash
rdc machine update
```

<a id="cli-local-machine-health"></a>
### 4.8 health

{{t:cli.commands.machine.health.description}}

{{t:cli.docs.supplements.machine.health.afterDescription}}

```bash
rdc machine health <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-t, --team <name>` | {{t:cli.options.team}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-machine-containers"></a>
### 4.9 containers

{{t:cli.commands.machine.containers.description}}

```bash
rdc machine containers <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-t, --team <name>` | {{t:cli.options.team}} | {{t:cli.docs.optionLabels.no}} | - |
| `--health-check` | {{t:cli.commands.machine.containers.healthCheck}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-machine-services"></a>
### 4.10 services

{{t:cli.commands.machine.services.description}}

```bash
rdc machine services <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-t, --team <name>` | {{t:cli.options.team}} | {{t:cli.docs.optionLabels.no}} | - |
| `--stability-check` | {{t:cli.commands.machine.services.stabilityCheck}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-machine-query"></a>
### 4.11 query

{{t:cli.commands.machine.query.description}}

```bash
rdc machine query [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--name <name>` | {{t:cli.options.name}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |
| `--system` | {{t:cli.options.querySystem}} | {{t:cli.docs.optionLabels.no}} | - |
| `--repositories` | {{t:cli.options.queryRepositories}} | {{t:cli.docs.optionLabels.no}} | - |
| `--containers` | {{t:cli.options.queryContainers}} | {{t:cli.docs.optionLabels.no}} | - |
| `--services` | {{t:cli.options.queryServices}} | {{t:cli.docs.optionLabels.no}} | - |
| `--network` | {{t:cli.options.queryNetwork}} | {{t:cli.docs.optionLabels.no}} | - |
| `--block-devices` | {{t:cli.options.queryBlockDevices}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-machine-vault-status"></a>
### 4.12 vault-status

{{t:cli.commands.machine.vaultStatus.description}}

```bash
rdc machine vault-status [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--name <name>` | {{t:cli.options.name}} | {{t:cli.docs.optionLabels.yes}} | - |
| `-t, --team <name>` | {{t:cli.options.team}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-machine-repos"></a>
### 4.13 repos

{{t:cli.commands.machine.repos.description}}

```bash
rdc machine repos <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-t, --team <name>` | {{t:cli.options.team}} | {{t:cli.docs.optionLabels.no}} | - |
| `--search <text>` | {{t:cli.options.searchRepos}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-machine-test-connection"></a>
### 4.14 test-connection

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

<a id="cli-local-machine-provision"></a>
### 4.15 provision

{{t:cli.commands.machine.provision.description}}

```bash
rdc machine provision [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--name <name>` | {{t:cli.options.name}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--provider <name>` | {{t:cli.commands.machine.provision.optionProvider}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--region <region>` | {{t:cli.commands.machine.provision.optionRegion}} | {{t:cli.docs.optionLabels.no}} | - |
| `--type <type>` | {{t:cli.commands.machine.provision.optionType}} | {{t:cli.docs.optionLabels.no}} | - |
| `--image <image>` | {{t:cli.commands.machine.provision.optionImage}} | {{t:cli.docs.optionLabels.no}} | - |
| `--ssh-user <user>` | {{t:cli.commands.machine.provision.optionSshUser}} | {{t:cli.docs.optionLabels.no}} | - |
| `--base-domain <domain>` | {{t:cli.commands.machine.provision.optionBaseDomain}} | {{t:cli.docs.optionLabels.no}} | - |
| `--no-infra` | {{t:cli.commands.machine.provision.optionNoInfra}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-machine-deprovision"></a>
### 4.16 deprovision

{{t:cli.commands.machine.deprovision.description}}

```bash
rdc machine deprovision [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--name <name>` | {{t:cli.options.name}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--force` | {{t:cli.options.yes}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-machine-backup"></a>
### 4.17 backup

{{t:cli.commands.machine.backup.description}}

<a id="cli-local-machine-backup-schedule"></a>
#### schedule

{{t:cli.commands.machine.backup.schedule.description}}

```bash
rdc machine backup schedule [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-m, --machine <name>` | {{t:cli.options.machine}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-machine-prune"></a>
### 4.18 prune

{{t:cli.commands.machine.prune.description}}

```bash
rdc machine prune [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--name <name>` | {{t:cli.options.name}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--dry-run` | {{t:cli.commands.machine.prune.dryRunOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--orphaned-repos` | {{t:cli.commands.machine.prune.orphanedReposOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--force` | {{t:cli.options.force}} | {{t:cli.docs.optionLabels.no}} | - |
| `--grace-days <days>` | {{t:cli.options.graceDays}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |


---

<a id="cli-local-group-mcp"></a>
## 5. {{t:cli.docs.sectionTitles.mcp}}

{{t:cli.commands.mcp.description}}

<a id="cli-local-mcp-serve"></a>
### 5.1 serve

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
## 6. {{t:cli.docs.sectionTitles.repo}}

{{t:cli.commands.repo.description}}

<a id="cli-local-repo-mount"></a>
### 6.1 mount

{{t:cli.commands.repo.mount.description}}

```bash
rdc repo mount [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--name <name>` | {{t:cli.options.name}} | {{t:cli.docs.optionLabels.no}} | - |
| `-m, --machine <name>` | {{t:cli.commands.repo.machineOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--checkpoint` | {{t:cli.commands.repo.mount.checkpointOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--no-docker` | {{t:cli.commands.repo.mount.noDockerOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--parallel` | {{t:cli.commands.repo.upAll.parallelOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--concurrency <n>` | {{t:cli.commands.repo.upAll.concurrencyOption}} | {{t:cli.docs.optionLabels.no}} | `3` |
| `-y, --yes` | {{t:cli.commands.repo.yesOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |
| `--skip-router-restart` | {{t:cli.options.skipRouterRestart}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-repo-unmount"></a>
### 6.2 unmount

{{t:cli.commands.repo.unmount.description}}

```bash
rdc repo unmount [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--name <name>` | {{t:cli.options.name}} | {{t:cli.docs.optionLabels.no}} | - |
| `-m, --machine <name>` | {{t:cli.commands.repo.machineOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--checkpoint` | {{t:cli.commands.repo.unmount.checkpointOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--parallel` | {{t:cli.commands.repo.upAll.parallelOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--concurrency <n>` | {{t:cli.commands.repo.upAll.concurrencyOption}} | {{t:cli.docs.optionLabels.no}} | `3` |
| `-y, --yes` | {{t:cli.commands.repo.yesOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |
| `--skip-router-restart` | {{t:cli.options.skipRouterRestart}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-repo-up"></a>
### 6.3 up

{{t:cli.commands.repo.up.description}}

```bash
rdc repo up [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--name <name>` | {{t:cli.options.name}} | {{t:cli.docs.optionLabels.no}} | - |
| `-m, --machine <name>` | {{t:cli.commands.repo.machineOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--mount` | {{t:cli.commands.repo.up.mountOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--skip-checkpoint` | {{t:cli.commands.repo.up.skipCheckpointOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--tls` | {{t:cli.commands.repo.up.tlsOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--include-forks` | {{t:cli.commands.repo.upAll.includeForksOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--mount-only` | {{t:cli.commands.repo.upAll.mountOnlyOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--parallel` | {{t:cli.commands.repo.upAll.parallelOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--concurrency <n>` | {{t:cli.commands.repo.upAll.concurrencyOption}} | {{t:cli.docs.optionLabels.no}} | `3` |
| `-y, --yes` | {{t:cli.commands.repo.yesOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |
| `--skip-router-restart` | {{t:cli.options.skipRouterRestart}} | {{t:cli.docs.optionLabels.no}} | - |
| `--dry-run` | {{t:cli.options.dryRun}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-repo-up-all"></a>
### 6.4 up-all

{{t:cli.commands.repo.upAll.description}}

```bash
rdc repo up-all
```

<a id="cli-local-repo-down"></a>
### 6.5 down

{{t:cli.commands.repo.down.description}}

```bash
rdc repo down [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--name <name>` | {{t:cli.options.name}} | {{t:cli.docs.optionLabels.no}} | - |
| `-m, --machine <name>` | {{t:cli.commands.repo.machineOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--unmount` | {{t:cli.commands.repo.down.unmountOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--checkpoint` | {{t:cli.commands.repo.down.checkpointOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `-y, --yes` | {{t:cli.commands.repo.yesOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |
| `--skip-router-restart` | {{t:cli.options.skipRouterRestart}} | {{t:cli.docs.optionLabels.no}} | - |
| `--dry-run` | {{t:cli.options.dryRun}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-repo-status"></a>
### 6.6 status

{{t:cli.commands.repo.status.description}}

```bash
rdc repo status [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--name <name>` | {{t:cli.options.name}} | {{t:cli.docs.optionLabels.yes}} | - |
| `-m, --machine <name>` | {{t:cli.commands.repo.machineOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |
| `--skip-router-restart` | {{t:cli.options.skipRouterRestart}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-repo-list"></a>
### 6.7 list

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
### 6.8 create

{{t:cli.commands.repo.create.description}}

```bash
rdc repo create [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--name <name>` | {{t:cli.options.name}} | {{t:cli.docs.optionLabels.yes}} | - |
| `-m, --machine <name>` | {{t:cli.commands.repo.machineOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--size <size>` | {{t:cli.commands.repo.create.sizeOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--no-docker` | {{t:cli.commands.repo.create.noDockerOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |
| `--skip-router-restart` | {{t:cli.options.skipRouterRestart}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-repo-delete"></a>
### 6.9 delete

{{t:cli.commands.repo.delete.description}}

```bash
rdc repo delete [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--name <name>` | {{t:cli.options.name}} | {{t:cli.docs.optionLabels.yes}} | - |
| `-m, --machine <name>` | {{t:cli.commands.repo.machineOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--archive-config` | {{t:cli.commands.repo.delete.archiveOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |
| `--skip-router-restart` | {{t:cli.options.skipRouterRestart}} | {{t:cli.docs.optionLabels.no}} | - |
| `--dry-run` | {{t:cli.options.dryRun}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-repo-fork"></a>
### 6.10 fork

{{t:cli.commands.repo.fork.description}}

```bash
rdc repo fork [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--parent <name>` | {{t:cli.options.name}} | {{t:cli.docs.optionLabels.yes}} | - |
| `-m, --machine <name>` | {{t:cli.commands.repo.machineOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--tag <name>` | {{t:cli.commands.repo.fork.tagOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--checkpoint` | {{t:cli.commands.repo.fork.checkpointOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--up` | {{t:cli.commands.repo.fork.upOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |
| `--skip-router-restart` | {{t:cli.options.skipRouterRestart}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-repo-takeover"></a>
### 6.11 takeover

{{t:cli.commands.repo.takeover.description}}

```bash
rdc repo takeover [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--name <name>` | {{t:cli.options.name}} | {{t:cli.docs.optionLabels.yes}} | - |
| `-m, --machine <name>` | {{t:cli.commands.repo.machineOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--force` | {{t:cli.commands.repo.takeover.forceOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |
| `--skip-router-restart` | {{t:cli.options.skipRouterRestart}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-repo-resize"></a>
### 6.12 resize

{{t:cli.commands.repo.resize.description}}

```bash
rdc repo resize [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--name <name>` | {{t:cli.options.name}} | {{t:cli.docs.optionLabels.yes}} | - |
| `-m, --machine <name>` | {{t:cli.commands.repo.machineOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--size <size>` | {{t:cli.commands.repo.resize.sizeOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |
| `--skip-router-restart` | {{t:cli.options.skipRouterRestart}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-repo-expand"></a>
### 6.13 expand

{{t:cli.commands.repo.expand.description}}

```bash
rdc repo expand [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--name <name>` | {{t:cli.options.name}} | {{t:cli.docs.optionLabels.yes}} | - |
| `-m, --machine <name>` | {{t:cli.commands.repo.machineOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--size <size>` | {{t:cli.commands.repo.resize.sizeOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |
| `--skip-router-restart` | {{t:cli.options.skipRouterRestart}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-repo-validate"></a>
### 6.14 validate

{{t:cli.commands.repo.validate.description}}

```bash
rdc repo validate [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--name <name>` | {{t:cli.options.name}} | {{t:cli.docs.optionLabels.yes}} | - |
| `-m, --machine <name>` | {{t:cli.commands.repo.machineOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |
| `--skip-router-restart` | {{t:cli.options.skipRouterRestart}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-repo-autostart"></a>
### 6.15 autostart

{{t:cli.commands.repo.autostart.description}}

<a id="cli-local-repo-autostart-enable"></a>
#### enable

{{t:cli.commands.repo.autostart.enable.description}}

```bash
rdc repo autostart enable [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--name <name>` | {{t:cli.options.name}} | {{t:cli.docs.optionLabels.no}} | - |
| `-m, --machine <name>` | {{t:cli.commands.repo.machineOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |
| `--skip-router-restart` | {{t:cli.options.skipRouterRestart}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-repo-autostart-disable"></a>
#### disable

{{t:cli.commands.repo.autostart.disable.description}}

```bash
rdc repo autostart disable [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--name <name>` | {{t:cli.options.name}} | {{t:cli.docs.optionLabels.no}} | - |
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
### 6.16 ownership

{{t:cli.commands.repo.ownership.description}}

```bash
rdc repo ownership [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--name <name>` | {{t:cli.options.name}} | {{t:cli.docs.optionLabels.yes}} | - |
| `-m, --machine <name>` | {{t:cli.commands.repo.machineOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--uid <uid>` | {{t:cli.commands.repo.ownership.uidOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |
| `--skip-router-restart` | {{t:cli.options.skipRouterRestart}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-repo-template"></a>
### 6.17 template

{{t:cli.commands.repo.template.description}}

<a id="cli-local-repo-template-list"></a>
#### list

{{t:cli.commands.repo.template.list.description}}

```bash
rdc repo template list
```

<a id="cli-local-repo-template-apply"></a>
#### apply

{{t:cli.commands.repo.template.apply.description}}

```bash
rdc repo template apply [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--name <name>` | {{t:cli.options.name}} | {{t:cli.docs.optionLabels.yes}} | - |
| `-m, --machine <name>` | {{t:cli.commands.repo.machineOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `-r, --repository <name>` | {{t:cli.options.repository}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--file <path>` | {{t:cli.commands.repo.template.fileOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--grand <name>` | {{t:cli.commands.repo.up.grandOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |
| `--skip-router-restart` | {{t:cli.options.skipRouterRestart}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-repo-push"></a>
### 6.18 push

{{t:cli.commands.repo.push.description}}

```bash
rdc repo push [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--name <name>` | {{t:cli.options.name}} | {{t:cli.docs.optionLabels.no}} | - |
| `--to <remote>` | {{t:cli.commands.repo.push.optionTo}} | {{t:cli.docs.optionLabels.no}} | - |
| `--to-machine <machine>` | — | {{t:cli.docs.optionLabels.no}} | - |
| `--provision <provider>` | {{t:cli.commands.repo.push.optionProvision}} | {{t:cli.docs.optionLabels.no}} | - |
| `--checkpoint` | {{t:cli.commands.repo.push.optionCheckpoint}} | {{t:cli.docs.optionLabels.no}} | - |
| `--force` | {{t:cli.commands.repo.push.optionForce}} | {{t:cli.docs.optionLabels.no}} | - |
| `--up` | {{t:cli.commands.repo.push.optionUp}} | {{t:cli.docs.optionLabels.no}} | - |
| `--tag <tag>` | {{t:cli.commands.repo.push.optionTag}} | {{t:cli.docs.optionLabels.no}} | - |
| `-m, --machine <name>` | {{t:cli.options.machine}} | {{t:cli.docs.optionLabels.yes}} | - |
| `-w, --watch` | {{t:cli.options.watch}} | {{t:cli.docs.optionLabels.no}} | - |
| `--parallel` | {{t:cli.commands.repo.upAll.parallelOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--concurrency <n>` | {{t:cli.commands.repo.upAll.concurrencyOption}} | {{t:cli.docs.optionLabels.no}} | `3` |
| `-y, --yes` | {{t:cli.commands.repo.yesOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |
| `--skip-router-restart` | {{t:cli.options.skipRouterRestart}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-repo-pull"></a>
### 6.19 pull

{{t:cli.commands.repo.pull.description}}

```bash
rdc repo pull [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--name <name>` | {{t:cli.options.name}} | {{t:cli.docs.optionLabels.no}} | - |
| `--from <remote>` | {{t:cli.commands.repo.pull.optionFrom}} | {{t:cli.docs.optionLabels.no}} | - |
| `--from-machine <machine>` | — | {{t:cli.docs.optionLabels.no}} | - |
| `--force` | {{t:cli.commands.repo.pull.optionForce}} | {{t:cli.docs.optionLabels.no}} | - |
| `--up` | {{t:cli.commands.repo.pull.optionUp}} | {{t:cli.docs.optionLabels.no}} | - |
| `-m, --machine <name>` | {{t:cli.options.machine}} | {{t:cli.docs.optionLabels.yes}} | - |
| `-w, --watch` | {{t:cli.options.watch}} | {{t:cli.docs.optionLabels.no}} | - |
| `--parallel` | {{t:cli.commands.repo.upAll.parallelOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--concurrency <n>` | {{t:cli.commands.repo.upAll.concurrencyOption}} | {{t:cli.docs.optionLabels.no}} | `3` |
| `-y, --yes` | {{t:cli.commands.repo.yesOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |
| `--skip-router-restart` | {{t:cli.options.skipRouterRestart}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-repo-backup"></a>
### 6.20 backup

{{t:cli.commands.repo.backup.description}}

<a id="cli-local-repo-backup-list"></a>
#### list

{{t:cli.commands.repo.backup.list.description}}

```bash
rdc repo backup list [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--from <remote>` | {{t:cli.commands.repo.pull.optionFrom}} | {{t:cli.docs.optionLabels.no}} | - |
| `--from-machine <machine>` | — | {{t:cli.docs.optionLabels.no}} | - |
| `-m, --machine <name>` | {{t:cli.options.machine}} | {{t:cli.docs.optionLabels.yes}} | - |
| `-w, --watch` | {{t:cli.options.watch}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |
| `--skip-router-restart` | {{t:cli.options.skipRouterRestart}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-repo-sync"></a>
### 6.21 sync

{{t:cli.commands.repo.sync.description}}

<a id="cli-local-repo-sync-push"></a>
#### push

{{t:cli.commands.repo.sync.push.description}}

```bash
rdc repo sync push
```

<a id="cli-local-repo-sync-pull"></a>
#### pull

{{t:cli.commands.repo.sync.pull.description}}

```bash
rdc repo sync pull
```

<a id="cli-local-repo-sync-upload"></a>
#### upload

{{t:cli.commands.repo.sync.upload.description}}

```bash
rdc repo sync upload [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-t, --team <name>` | {{t:cli.options.team}} | {{t:cli.docs.optionLabels.no}} | - |
| `-m, --machine <name>` | {{t:cli.options.machine}} | {{t:cli.docs.optionLabels.yes}} | - |
| `-r, --repository <name>` | {{t:cli.options.repository}} | {{t:cli.docs.optionLabels.no}} | - |
| `--local <path>` | {{t:cli.options.localPath}} | {{t:cli.docs.optionLabels.no}} | - |
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
| `-m, --machine <name>` | {{t:cli.options.machine}} | {{t:cli.docs.optionLabels.yes}} | - |
| `-r, --repository <name>` | {{t:cli.options.repository}} | {{t:cli.docs.optionLabels.no}} | - |
| `--local <path>` | {{t:cli.options.localPath}} | {{t:cli.docs.optionLabels.no}} | - |
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
| `-m, --machine <name>` | {{t:cli.options.machine}} | {{t:cli.docs.optionLabels.yes}} | - |
| `-r, --repository <name>` | {{t:cli.options.repository}} | {{t:cli.docs.optionLabels.no}} | - |
| `--local <path>` | {{t:cli.options.localPath}} | {{t:cli.docs.optionLabels.no}} | - |
| `--remote <path>` | {{t:cli.options.remotePath}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-repo-snapshot"></a>
### 6.22 snapshot

{{t:cli.commands.repo.snapshot.description}}

<a id="cli-local-repo-snapshot-create"></a>
#### create

{{t:cli.commands.repo.snapshot.create.description}}

```bash
rdc repo snapshot create
```

<a id="cli-local-repo-snapshot-list"></a>
#### list

{{t:cli.commands.repo.snapshot.list.description}}

```bash
rdc repo snapshot list
```

<a id="cli-local-repo-snapshot-delete"></a>
#### delete

{{t:cli.commands.repo.snapshot.delete.description}}

```bash
rdc repo snapshot delete
```

<a id="cli-local-repo-tunnel"></a>
### 6.23 tunnel

{{t:cli.commands.repo.tunnel.description}}

```bash
rdc repo tunnel [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-m, --machine <name>` | {{t:cli.options.machine}} | {{t:cli.docs.optionLabels.no}} | - |
| `-r, --repository <name>` | {{t:cli.options.repository}} | {{t:cli.docs.optionLabels.no}} | - |
| `-c, --container <name>` | {{t:cli.commands.repo.tunnel.containerOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--port <port>` | {{t:cli.commands.repo.tunnel.portOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--local <port>` | {{t:cli.commands.repo.tunnel.localOption}} | {{t:cli.docs.optionLabels.no}} | - |


---

<a id="cli-local-group-storage"></a>
## 7. {{t:cli.docs.sectionTitles.storage}}

{{t:cli.commands.storage.description}}

<a id="cli-local-storage-list"></a>
### 7.1 list

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


<a id="cli-local-storage-create"></a>
### 7.2 create

{{t:cli.commands.storage.create.description}}

```bash
rdc storage create [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--name <name>` | {{t:cli.options.name}} | {{t:cli.docs.optionLabels.yes}} | - |
| `-t, --team <name>` | {{t:cli.options.team}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-storage-rename"></a>
### 7.3 rename

{{t:cli.commands.storage.rename.description}}

```bash
rdc storage rename [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--current-name <name>` | {{t:cli.options.currentName}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--new-name <name>` | {{t:cli.options.newName}} | {{t:cli.docs.optionLabels.yes}} | - |
| `-t, --team <name>` | {{t:cli.options.team}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-storage-delete"></a>
### 7.4 delete

{{t:cli.commands.storage.delete.description}}

```bash
rdc storage delete [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--name <name>` | {{t:cli.options.name}} | {{t:cli.docs.optionLabels.yes}} | - |
| `-t, --team <name>` | {{t:cli.options.team}} | {{t:cli.docs.optionLabels.no}} | - |
| `-f, --force` | {{t:cli.options.force}} | {{t:cli.docs.optionLabels.no}} | - |
| `--dry-run` | {{t:cli.options.dryRun}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-storage-vault"></a>
### 7.5 vault

{{t:cli.commands.storage.vault.description}}

```bash
rdc storage vault
```

<a id="cli-local-storage-browse"></a>
### 7.6 browse

{{t:cli.commands.storage.browse.description}}

```bash
rdc storage browse [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--name <name>` | {{t:cli.options.name}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--path <subpath>` | {{t:cli.commands.storage.browse.pathOption}} | {{t:cli.docs.optionLabels.no}} | `` |


<a id="cli-local-storage-prune"></a>
### 7.7 prune

{{t:cli.commands.storage.prune.description}}

```bash
rdc storage prune [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--name <name>` | {{t:cli.options.name}} | {{t:cli.docs.optionLabels.yes}} | - |
| `-m, --machine <name>` | {{t:cli.options.machine}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--dry-run` | {{t:cli.options.dryRun}} | {{t:cli.docs.optionLabels.no}} | - |
| `--force` | {{t:cli.options.force}} | {{t:cli.docs.optionLabels.no}} | - |
| `--grace-days <days>` | {{t:cli.options.graceDays}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |
| `--skip-router-restart` | {{t:cli.options.skipRouterRestart}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-storage-pull"></a>
### 7.8 pull

{{t:cli.commands.storage.pull.description}}

```bash
rdc storage pull
```

---

<a id="cli-local-group-vscode"></a>
## 8. {{t:cli.docs.sectionTitles.vscode}}

{{t:cli.commands.vscode.description}}

<a id="cli-local-vscode-connect"></a>
### 8.1 connect

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
### 8.2 list

{{t:cli.commands.vscode.list.description}}

```bash
rdc vscode list
```

<a id="cli-local-vscode-cleanup"></a>
### 8.3 cleanup

{{t:cli.commands.vscode.cleanup.description}}

```bash
rdc vscode cleanup [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--all` | {{t:cli.options.cleanupAll}} | {{t:cli.docs.optionLabels.no}} | - |
| `-c, --connection <name>` | {{t:cli.options.connectionName}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-vscode-check"></a>
### 8.4 check

{{t:cli.commands.vscode.check.description}}

```bash
rdc vscode check [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--insiders` | {{t:cli.options.insiders}} | {{t:cli.docs.optionLabels.no}} | - |


---

<a id="cli-local-group-term"></a>
## 9. {{t:cli.docs.sectionTitles.term}}

{{t:cli.commands.term.description}}

<a id="cli-local-term-connect"></a>
### 9.1 connect

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
| `--reset-home` | {{t:cli.options.resetHome}} | {{t:cli.docs.optionLabels.no}} | - |


---

<a id="cli-local-group-protocol"></a>
## 10. {{t:cli.docs.sectionTitles.protocol}}

{{t:cli.commands.protocol.description}}

<a id="cli-local-protocol-register"></a>
### 10.1 register

{{t:cli.commands.protocol.register.description}}

```bash
rdc protocol register [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--system` | {{t:cli.options.protocolSystem}} | {{t:cli.docs.optionLabels.no}} | - |
| `--force` | {{t:cli.options.protocolForce}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-protocol-unregister"></a>
### 10.2 unregister

{{t:cli.commands.protocol.unregister.description}}

```bash
rdc protocol unregister [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--system` | {{t:cli.options.protocolSystemUnregister}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-protocol-status"></a>
### 10.3 status

{{t:cli.commands.protocol.status.description}}

```bash
rdc protocol status
```

<a id="cli-local-protocol-open"></a>
### 10.4 open

{{t:cli.commands.protocol.open.description}}

```bash
rdc protocol open <url>
```

<a id="cli-local-protocol-build"></a>
### 10.5 build

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
### 10.6 parse

{{t:cli.commands.protocol.parse.description}}

```bash
rdc protocol parse <url>
```

---

<a id="cli-local-group-shortcuts"></a>
## 11. {{t:cli.docs.sectionTitles.shortcuts}}

<a id="cli-local-shortcuts-run"></a>
### 11.1 run

{{t:cli.commands.shortcuts.run.description}}

```bash
rdc run
```

<a id="cli-local-shortcuts-trace"></a>
### 11.2 trace

{{t:cli.commands.shortcuts.trace.description}}

```bash
rdc trace
```

<a id="cli-local-shortcuts-cancel"></a>
### 11.3 cancel

{{t:cli.commands.shortcuts.cancel.description}}

```bash
rdc cancel
```

<a id="cli-local-shortcuts-retry"></a>
### 11.4 retry

{{t:cli.commands.shortcuts.retry.description}}

```bash
rdc retry
```

---

<a id="cli-local-group-subscription"></a>
## 12. {{t:cli.docs.sectionTitles.subscription}}

{{t:cli.commands.subscription.description}}

<a id="cli-local-subscription-login"></a>
### 12.1 login

{{t:cli.commands.subscription.login.description}}

```bash
rdc subscription login [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-t, --token <token>` | {{t:cli.options.apiToken}} | {{t:cli.docs.optionLabels.no}} | - |
| `--server <url>` | {{t:cli.options.serverUrl}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-subscription-logout"></a>
### 12.2 logout

{{t:cli.commands.subscription.logout.description}}

```bash
rdc subscription logout
```

<a id="cli-local-subscription-status"></a>
### 12.3 status

{{t:cli.commands.subscription.status.description}}

```bash
rdc subscription status
```

<a id="cli-local-subscription-activation"></a>
### 12.4 activation

{{t:cli.commands.subscription.activation.description}}

<a id="cli-local-subscription-activation-status"></a>
#### status

{{t:cli.commands.subscription.activation.status.description}}

```bash
rdc subscription activation status [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-m, --machine <name>` | {{t:cli.options.machine}} | {{t:cli.docs.optionLabels.yes}} | - |


<a id="cli-local-subscription-repo"></a>
### 12.5 repo

{{t:cli.commands.subscription.repo.description}}

<a id="cli-local-subscription-repo-status"></a>
#### status

{{t:cli.commands.subscription.repo.status.description}}

```bash
rdc subscription repo status [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-m, --machine <name>` | {{t:cli.options.machine}} | {{t:cli.docs.optionLabels.yes}} | - |


<a id="cli-local-subscription-refresh"></a>
### 12.6 refresh

{{t:cli.commands.subscription.refresh.description}}

<a id="cli-local-subscription-refresh-activation"></a>
#### activation

{{t:cli.commands.subscription.refresh.activation.description}}

```bash
rdc subscription refresh activation [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-m, --machine <name>` | {{t:cli.options.machine}} | {{t:cli.docs.optionLabels.yes}} | - |


<a id="cli-local-subscription-refresh-repos"></a>
#### repos

{{t:cli.commands.subscription.refresh.repos.description}}

```bash
rdc subscription refresh repos [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-m, --machine <name>` | {{t:cli.options.machine}} | {{t:cli.docs.optionLabels.yes}} | - |


<a id="cli-local-subscription-refresh-repo"></a>
#### repo

{{t:cli.commands.subscription.refresh.repo.description}}

```bash
rdc subscription refresh repo [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--name <name>` | {{t:cli.options.name}} | {{t:cli.docs.optionLabels.yes}} | - |
| `-m, --machine <name>` | {{t:cli.options.machine}} | {{t:cli.docs.optionLabels.yes}} | - |


---

<a id="cli-local-group-update"></a>
## 13. {{t:cli.docs.sectionTitles.update}}

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
| `--channel <channel>` | {{t:cli.commands.update.channelDescription}} | {{t:cli.docs.optionLabels.no}} | - |


---

<a id="cli-local-group-doctor"></a>
## 14. {{t:cli.docs.sectionTitles.doctor}}

{{t:cli.commands.doctor.description}}

<a id="cli-local-doctor"></a>
```bash
rdc doctor
```

---

<a id="cli-local-group-ops"></a>
## 15. {{t:cli.docs.sectionTitles.ops}}

{{t:cli.commands.ops.description}}

<a id="cli-local-ops-up"></a>
### 15.1 up

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
### 15.2 down

{{t:cli.commands.ops.down.description}}

```bash
rdc ops down [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--backend <backend>` | {{t:cli.options.opsBackend}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-ops-status"></a>
### 15.3 status

{{t:cli.commands.ops.status.description}}

```bash
rdc ops status [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--backend <backend>` | {{t:cli.options.opsBackend}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-ops-ssh"></a>
### 15.4 ssh

{{t:cli.commands.ops.ssh.description}}

```bash
rdc ops ssh [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--vm-id <id>` | {{t:cli.options.vmId}} | {{t:cli.docs.optionLabels.yes}} | - |
| `-c, --command <cmd>` | {{t:cli.options.command}} | {{t:cli.docs.optionLabels.no}} | - |
| `--backend <backend>` | {{t:cli.options.opsBackend}} | {{t:cli.docs.optionLabels.no}} | - |
| `--user <user>` | {{t:cli.options.opsSSHUser}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-ops-setup"></a>
### 15.5 setup

{{t:cli.commands.ops.setup.description}}

```bash
rdc ops setup [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-ops-check"></a>
### 15.6 check

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
