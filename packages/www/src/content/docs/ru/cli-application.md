---
title: "CLI-приложение"
description: "Полное руководство по использованию интерфейса командной строки Rediacc для управления платформой"
category: "Справочник"
order: 2
language: ru
generated: true
generatedFrom: packages/cli/src/i18n/locales/ru/cli.json
sourceHash: "16f7e9d8dad6e5ec"
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

<a id="cli-local-group-config"></a>
## 1. {{t:cli.docs.sectionTitles.config}}

{{t:cli.commands.config.description}}

{{t:cli.docs.supplements.config.afterDescription}}

<a id="cli-local-config-prune"></a>
### 1.1 prune

{{t:cli.commands.config.prune.description}}

```bash
rdc config prune [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--dry-run` | {{t:cli.commands.config.prune.dryRunOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--certs-only` | {{t:cli.commands.config.prune.certsOnlyOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--archives-only` | {{t:cli.commands.config.prune.archivesOnlyOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--refs-only` | {{t:cli.commands.config.prune.refsOnlyOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--purge-archived` | {{t:cli.commands.config.prune.purgeArchivedOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--orphan-repos` | {{t:cli.commands.config.prune.orphanReposOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--grace-days <days>` | {{t:cli.commands.config.prune.graceDaysOption}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-config-init"></a>
### 1.2 init

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
| `--server <url>` | {{t:cli.options.serverUrl}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-config-list"></a>
### 1.3 list

{{t:cli.commands.config.list.description}}

```bash
rdc config list
```

<a id="cli-local-config-show"></a>
### 1.4 show

{{t:cli.commands.config.show.description}}

```bash
rdc config show [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--reveal` | {{t:cli.commands.config.show.optionReveal}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-config-delete"></a>
### 1.5 delete

{{t:cli.commands.config.delete.description}}

```bash
rdc config delete <name>
```

<a id="cli-local-config-set"></a>
### 1.6 set

{{t:cli.commands.config.set.description}}

```bash
rdc config set <key> <value>
```

<a id="cli-local-config-clear"></a>
### 1.7 clear

{{t:cli.commands.config.clear.description}}

```bash
rdc config clear [key]
```

<a id="cli-local-config-recover"></a>
### 1.8 recover

{{t:cli.commands.config.recover.description}}

```bash
rdc config recover [name] [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-y, --yes` | {{t:cli.options.yes}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-config-ssh"></a>
### 1.9 ssh

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
### 1.10 remote

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
| `--password` | {{t:cli.commands.config.remote.enable.optionPassword}} | {{t:cli.docs.optionLabels.no}} | - |
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

<a id="cli-local-config-field"></a>
### 1.11 field

{{t:cli.commands.config.field.description}}

<a id="cli-local-config-field-get"></a>
#### get

{{t:cli.commands.config.field.get.description}}

```bash
rdc config field get [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--pointer <pointer>` | {{t:cli.commands.config.field.get.optionPointer}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--reveal` | {{t:cli.commands.config.field.get.optionReveal}} | {{t:cli.docs.optionLabels.no}} | - |
| `--digest` | {{t:cli.commands.config.field.get.optionDigest}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-config-field-set"></a>
#### set

{{t:cli.commands.config.field.set.description}}

```bash
rdc config field set [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--pointer <pointer>` | {{t:cli.commands.config.field.get.optionPointer}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--new <value>` | {{t:cli.commands.config.field.set.optionNew}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--current <value>` | {{t:cli.commands.config.field.set.optionCurrent}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-config-field-unset"></a>
#### unset

{{t:cli.commands.config.field.unset.description}}

```bash
rdc config field unset [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--pointer <pointer>` | {{t:cli.commands.config.field.get.optionPointer}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--current <value>` | {{t:cli.commands.config.field.unset.optionCurrent}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-config-field-rotate"></a>
#### rotate

{{t:cli.commands.config.field.rotate.description}}

```bash
rdc config field rotate [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--pointer <pointer>` | {{t:cli.commands.config.field.rotate.optionPointer}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--new <value>` | {{t:cli.commands.config.field.rotate.optionNew}} | {{t:cli.docs.optionLabels.yes}} | - |


<a id="cli-local-config-field-list"></a>
#### list

{{t:cli.commands.config.field.list.description}}

```bash
rdc config field list [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--sensitive` | {{t:cli.commands.config.field.list.optionSensitive}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-config-edit"></a>
### 1.12 edit

{{t:cli.commands.config.edit.description}}

```bash
rdc config edit [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--reveal` | {{t:cli.commands.config.field.get.optionReveal}} | {{t:cli.docs.optionLabels.no}} | - |
| `--dump` | {{t:cli.commands.config.edit.optionDump}} | {{t:cli.docs.optionLabels.no}} | - |
| `--apply <file>` | {{t:cli.commands.config.edit.optionApply}} | {{t:cli.docs.optionLabels.no}} | - |
| `--current-secrets <file>` | {{t:cli.commands.config.edit.optionCurrentSecrets}} | {{t:cli.docs.optionLabels.no}} | - |
| `--editor <cmd>` | {{t:cli.commands.config.edit.optionEditor}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-config-audit"></a>
### 1.13 audit

{{t:cli.commands.config.audit.description}}

<a id="cli-local-config-audit-log"></a>
#### log

{{t:cli.commands.config.audit.log.description}}

```bash
rdc config audit log [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--since <spec>` | {{t:cli.commands.config.audit.log.optionSince}} | {{t:cli.docs.optionLabels.no}} | - |
| `--path <glob>` | {{t:cli.commands.config.audit.log.optionPath}} | {{t:cli.docs.optionLabels.no}} | - |
| `--actor <kind>` | {{t:cli.commands.config.audit.log.optionActor}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-config-audit-tail"></a>
#### tail

{{t:cli.commands.config.audit.tail.description}}

```bash
rdc config audit tail
```

<a id="cli-local-config-audit-verify"></a>
#### verify

{{t:cli.commands.config.audit.verify.description}}

```bash
rdc config audit verify
```

<a id="cli-local-config-reconcile"></a>
### 1.14 reconcile

{{t:cli.commands.config.reconcile.description}}

```bash
rdc config reconcile [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--machine <m...>` | {{t:cli.commands.config.reconcile.optionMachine}} | {{t:cli.docs.optionLabels.no}} | - |
| `--dry-run` | {{t:cli.options.dryRun}} | {{t:cli.docs.optionLabels.no}} | - |
| `--accept-observed` | {{t:cli.commands.config.reconcile.optionAcceptObserved}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-config-rotate-cek"></a>
### 1.15 rotate-cek

{{t:cli.commands.config.rotateCek.description}}

```bash
rdc config rotate-cek [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--api-url <url>` | {{t:cli.options.serverUrl}} | {{t:cli.docs.optionLabels.no}} | - |


---

<a id="cli-local-group-datastore"></a>
## 2. {{t:cli.docs.sectionTitles.datastore}}

{{t:cli.commands.datastore.description}}

<a id="cli-local-datastore-resize"></a>
### 2.1 resize

{{t:cli.commands.datastore.resize.description}}

```bash
rdc datastore resize <datastore> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--size <size>` | {{t:cli.commands.datastore.resize.sizeOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-datastore-fork"></a>
### 2.2 fork

{{t:cli.commands.datastore.fork.description}}

```bash
rdc datastore fork <datastore> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--tag <tag>` | {{t:cli.commands.datastore.fork.tagOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--attach-to <machine>` | {{t:cli.commands.datastore.fork.attachToOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--writes <disposition>` | {{t:cli.commands.datastore.fork.writesOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--cow-size <size>` | {{t:cli.commands.datastore.fork.cowSizeOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-datastore-status"></a>
### 2.3 status

{{t:cli.commands.datastore.status.description}}

```bash
rdc datastore status <datastore> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-datastore-create"></a>
### 2.4 create

{{t:cli.commands.datastore.create.description}}

```bash
rdc datastore create <datastore> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-m, --machine <name>` | {{t:cli.commands.datastore.create.machineOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--size <size>` | {{t:cli.commands.datastore.create.sizeOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--backend <type>` | {{t:cli.commands.datastore.create.backendOption}} | {{t:cli.docs.optionLabels.no}} | `local` |
| `--pool <name>` | {{t:cli.commands.datastore.create.poolOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--image <name>` | {{t:cli.commands.datastore.create.imageOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--cluster <name>` | {{t:cli.commands.datastore.create.clusterOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-datastore-list"></a>
### 2.5 list

{{t:cli.commands.datastore.list.description}}

```bash
rdc datastore list [place]
```

<a id="cli-local-datastore-attach"></a>
### 2.6 attach

{{t:cli.commands.datastore.attach.description}}

```bash
rdc datastore attach <datastore> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--to <machine>` | {{t:cli.commands.datastore.attach.toOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--writes <disposition>` | {{t:cli.commands.datastore.attach.writesOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--cow-size <size>` | {{t:cli.commands.datastore.fork.cowSizeOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--no-auto` | {{t:cli.commands.datastore.attach.noAutoOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--force` | {{t:cli.commands.datastore.attach.forceOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-datastore-detach"></a>
### 2.7 detach

{{t:cli.commands.datastore.detach.description}}

```bash
rdc datastore detach <datastore> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--discard` | {{t:cli.commands.datastore.detach.discardOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `-y, --yes` | {{t:cli.options.yes}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-datastore-snapshot"></a>
### 2.8 snapshot

{{t:cli.commands.datastore.snapshot.description}}

<a id="cli-local-datastore-snapshot-create"></a>
#### create

{{t:cli.commands.datastore.snapshot.create.description}}

```bash
rdc datastore snapshot create <datastore> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--snapshot <label>` | {{t:cli.commands.cluster.snapshot.create.labelOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-datastore-snapshot-list"></a>
#### list

{{t:cli.commands.datastore.snapshot.list.description}}

```bash
rdc datastore snapshot list <datastore> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-datastore-delete"></a>
### 2.9 delete

{{t:cli.commands.datastore.delete.description}}

```bash
rdc datastore delete <datastore> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-y, --yes` | {{t:cli.options.yes}} | {{t:cli.docs.optionLabels.no}} | - |
| `--force` | {{t:cli.commands.datastore.delete.forceOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |


---

<a id="cli-local-group-machine"></a>
## 3. {{t:cli.docs.sectionTitles.machine}}

{{t:cli.commands.machine.description}}

<a id="cli-local-machine-list"></a>
### 3.1 list

{{t:cli.commands.machine.list.description}}

```bash
rdc machine list [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--search <text>` | {{t:cli.options.searchInField}} | {{t:cli.docs.optionLabels.no}} | - |
| `--sort <field>` | {{t:cli.options.sortByField}} | {{t:cli.docs.optionLabels.no}} | - |
| `--desc` | {{t:cli.options.sortDesc}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-machine-health"></a>
### 3.2 health

{{t:cli.commands.machine.health.description}}

{{t:cli.docs.supplements.machine.health.afterDescription}}

```bash
rdc machine health <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-t, --team <name>` | {{t:cli.options.team}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-machine-provision"></a>
### 3.3 provision

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
### 3.4 deprovision

{{t:cli.commands.machine.deprovision.description}}

```bash
rdc machine deprovision <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--force` | {{t:cli.options.yes}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-machine-prune"></a>
### 3.5 prune

{{t:cli.commands.machine.prune.description}}

```bash
rdc machine prune <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--dry-run` | {{t:cli.commands.machine.prune.dryRunOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--orphaned-repos` | {{t:cli.commands.machine.prune.orphanedReposOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--prune-unknown` | {{t:cli.commands.machine.prune.pruneUnknownOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--force-delete-mounted` | {{t:cli.commands.machine.prune.forceDeleteMountedOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--force` | {{t:cli.options.force}} | {{t:cli.docs.optionLabels.no}} | - |
| `--grace-days <days>` | {{t:cli.options.graceDays}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-machine-add"></a>
### 3.6 add

{{t:cli.commands.machine.add.description}}

```bash
rdc machine add <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--ip <address>` | {{t:cli.options.machineIp}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--user <username>` | {{t:cli.options.sshUser}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--port <port>` | {{t:cli.options.sshPort}} | {{t:cli.docs.optionLabels.no}} | `22` |


<a id="cli-local-machine-infra"></a>
### 3.7 infra

{{t:cli.commands.machine.infra.description}}

#### cert

{{t:cli.commands.machine.infra.cert.description}}

<a id="cli-local-machine-infra-cert-clear"></a>
**clear:**

{{t:cli.commands.machine.infra.cert.clear.description}}

```bash
rdc machine infra cert clear
```

<a id="cli-local-machine-infra-cert-pull"></a>
**pull:**

{{t:cli.commands.machine.infra.cert.pull.description}}

```bash
rdc machine infra cert pull <machine> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--no-prune` | {{t:cli.commands.machine.infra.cert.pull.optionNoPrune}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-machine-infra-cert-push"></a>
**push:**

{{t:cli.commands.machine.infra.cert.push.description}}

```bash
rdc machine infra cert push <machine> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-machine-infra-cert-status"></a>
**status:**

{{t:cli.commands.machine.infra.cert.status.description}}

```bash
rdc machine infra cert status
```

<a id="cli-local-machine-infra-push"></a>
#### push

{{t:cli.commands.machine.infra.push.description}}

```bash
rdc machine infra push <machine> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-machine-infra-set"></a>
#### set

{{t:cli.commands.machine.infra.set.description}}

```bash
rdc machine infra set <machine> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--public-ipv4 <ip>` | {{t:cli.commands.machine.infra.set.optionPublicIPv4}} | {{t:cli.docs.optionLabels.no}} | - |
| `--public-ipv6 <ip>` | {{t:cli.commands.machine.infra.set.optionPublicIPv6}} | {{t:cli.docs.optionLabels.no}} | - |
| `--base-domain <domain>` | {{t:cli.commands.machine.infra.set.optionBaseDomain}} | {{t:cli.docs.optionLabels.no}} | - |
| `--cert-email <email>` | {{t:cli.commands.machine.infra.set.optionCertEmail}} | {{t:cli.docs.optionLabels.no}} | - |
| `--cf-dns-token <token>` | {{t:cli.commands.machine.infra.set.optionCfDnsToken}} | {{t:cli.docs.optionLabels.no}} | - |
| `--tcp-ports <ports>` | {{t:cli.commands.machine.infra.set.optionTcpPorts}} | {{t:cli.docs.optionLabels.no}} | - |
| `--udp-ports <ports>` | {{t:cli.commands.machine.infra.set.optionUdpPorts}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-machine-infra-show"></a>
#### show

{{t:cli.commands.machine.infra.show.description}}

```bash
rdc machine infra show <machine>
```

<a id="cli-local-machine-provider"></a>
### 3.8 provider

{{t:cli.commands.machine.provider.description}}

<a id="cli-local-machine-provider-add"></a>
#### add

{{t:cli.commands.machine.provider.add.description}}

```bash
rdc machine provider add <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--provider <source>` | {{t:cli.commands.machine.provider.add.optionProvider}} | {{t:cli.docs.optionLabels.no}} | - |
| `--source <source>` | {{t:cli.commands.machine.provider.add.optionSource}} | {{t:cli.docs.optionLabels.no}} | - |
| `--token <token>` | {{t:cli.commands.machine.provider.add.optionToken}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--region <region>` | {{t:cli.commands.machine.provider.add.optionRegion}} | {{t:cli.docs.optionLabels.no}} | - |
| `--type <type>` | {{t:cli.commands.machine.provider.add.optionInstanceType}} | {{t:cli.docs.optionLabels.no}} | - |
| `--image <image>` | {{t:cli.commands.machine.provider.add.optionImage}} | {{t:cli.docs.optionLabels.no}} | - |
| `--ssh-user <user>` | {{t:cli.commands.machine.provider.add.optionSshUser}} | {{t:cli.docs.optionLabels.no}} | - |
| `--resource <type>` | {{t:cli.commands.machine.provider.add.optionResource}} | {{t:cli.docs.optionLabels.no}} | - |
| `--label-attr <attr>` | {{t:cli.commands.machine.provider.add.optionLabelAttr}} | {{t:cli.docs.optionLabels.no}} | - |
| `--region-attr <attr>` | {{t:cli.commands.machine.provider.add.optionRegionAttr}} | {{t:cli.docs.optionLabels.no}} | - |
| `--size-attr <attr>` | {{t:cli.commands.machine.provider.add.optionSizeAttr}} | {{t:cli.docs.optionLabels.no}} | - |
| `--image-attr <attr>` | {{t:cli.commands.machine.provider.add.optionImageAttr}} | {{t:cli.docs.optionLabels.no}} | - |
| `--ipv4-output <attr>` | {{t:cli.commands.machine.provider.add.optionIpv4Output}} | {{t:cli.docs.optionLabels.no}} | - |
| `--ipv6-output <attr>` | {{t:cli.commands.machine.provider.add.optionIpv6Output}} | {{t:cli.docs.optionLabels.no}} | - |
| `--ssh-key-attr <attr>` | {{t:cli.commands.machine.provider.add.optionSshKeyAttr}} | {{t:cli.docs.optionLabels.no}} | - |
| `--ssh-key-format <format>` | {{t:cli.commands.machine.provider.add.optionSshKeyFormat}} | {{t:cli.docs.optionLabels.no}} | - |
| `--ssh-key-resource <type>` | {{t:cli.commands.machine.provider.add.optionSshKeyResource}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-machine-provider-list"></a>
#### list

{{t:cli.commands.machine.provider.list.description}}

```bash
rdc machine provider list
```

<a id="cli-local-machine-provider-remove"></a>
#### remove

{{t:cli.commands.machine.provider.remove.description}}

```bash
rdc machine provider remove <name>
```

<a id="cli-local-machine-remove"></a>
### 3.9 remove

{{t:cli.commands.machine.remove.description}}

```bash
rdc machine remove <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-y, --yes` | {{t:cli.options.yes}} | {{t:cli.docs.optionLabels.no}} | - |
| `--force` | {{t:cli.commands.machine.remove.forceOption}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-machine-scan-keys"></a>
### 3.10 scan-keys

{{t:cli.commands.machine.scanKeys.description}}

```bash
rdc machine scan-keys [name]
```

<a id="cli-local-machine-setup"></a>
### 3.11 setup

{{t:cli.commands.machine.setup.description}}

```bash
rdc machine setup <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--datastore-path <path>` | {{t:cli.commands.machine.setup.datastoreOption}} | {{t:cli.docs.optionLabels.no}} | `/mnt/rediacc` |
| `--datastore-size <size>` | {{t:cli.commands.machine.setup.datastoreSizeOption}} | {{t:cli.docs.optionLabels.no}} | `95%` |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-machine-status"></a>
### 3.12 status

{{t:cli.commands.machine.status.description}}

```bash
rdc machine status [name] [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |
| `--system` | {{t:cli.options.querySystem}} | {{t:cli.docs.optionLabels.no}} | - |
| `--repositories` | {{t:cli.options.queryRepositories}} | {{t:cli.docs.optionLabels.no}} | - |
| `--containers` | {{t:cli.options.queryContainers}} | {{t:cli.docs.optionLabels.no}} | - |
| `--services` | {{t:cli.options.queryServices}} | {{t:cli.docs.optionLabels.no}} | - |
| `--network` | {{t:cli.options.queryNetwork}} | {{t:cli.docs.optionLabels.no}} | - |
| `--block-devices` | {{t:cli.options.queryBlockDevices}} | {{t:cli.docs.optionLabels.no}} | - |
| `--licenses` | {{t:cli.options.queryLicenses}} | {{t:cli.docs.optionLabels.no}} | - |
| `--storage-health` | {{t:cli.options.queryStorageHealth}} | {{t:cli.docs.optionLabels.no}} | - |
| `--datastores` | {{t:cli.options.queryDatastores}} | {{t:cli.docs.optionLabels.no}} | - |
| `--health-check` | {{t:cli.commands.machine.status.healthCheck}} | {{t:cli.docs.optionLabels.no}} | - |
| `--stability-check` | {{t:cli.commands.machine.status.stabilityCheck}} | {{t:cli.docs.optionLabels.no}} | - |
| `--search <text>` | {{t:cli.options.searchRepos}} | {{t:cli.docs.optionLabels.no}} | - |
| `--sync-certs` | {{t:cli.options.querySyncCerts}} | {{t:cli.docs.optionLabels.no}} | - |
| `--strict` | {{t:cli.options.queryStrict}} | {{t:cli.docs.optionLabels.no}} | - |


---

<a id="cli-local-group-cluster"></a>
## 4. {{t:cli.docs.sectionTitles.cluster}}

{{t:cli.commands.cluster.description}}

<a id="cli-local-cluster-create"></a>
### 4.1 create

{{t:cli.commands.cluster.create.description}}

```bash
rdc cluster create <cluster> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--provider <provider>` | {{t:cli.commands.cluster.create.providerOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--pool <spec...>` | {{t:cli.commands.cluster.create.poolOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--declare-only` | {{t:cli.commands.cluster.create.declareOnlyOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--network-cidr <cidr>` | {{t:cli.commands.cluster.create.cidrOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--network-primitive <primitive>` | {{t:cli.commands.cluster.create.primitiveOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--control-node <machine>` | {{t:cli.commands.cluster.create.controlNodeOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--net-name <name>` | {{t:cli.commands.cluster.create.netNameOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--net-base <prefix>` | {{t:cli.commands.cluster.create.netBaseOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--net-offset <n>` | {{t:cli.commands.cluster.create.netOffsetOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--control-id <n>` | {{t:cli.commands.cluster.create.controlIdOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--docker-registry <endpoint>` | {{t:cli.commands.cluster.create.dockerRegistryOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--ssh-user <user>` | {{t:cli.commands.cluster.create.sshUserOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--base-domain <domain>` | {{t:cli.commands.cluster.create.baseDomainOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--control-ds-size <size>` | {{t:cli.commands.cluster.create.controlDsSizeOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--control-ds-backend <backend>` | {{t:cli.commands.cluster.create.controlDsBackendOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--control-ds-pool <pool>` | {{t:cli.commands.cluster.create.controlDsPoolOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-cluster-status"></a>
### 4.2 status

{{t:cli.commands.cluster.status.description}}

```bash
rdc cluster status [cluster]
```

<a id="cli-local-cluster-scale"></a>
### 4.3 scale

{{t:cli.commands.cluster.scale.description}}

```bash
rdc cluster scale <cluster> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--pool <pool>` | {{t:cli.commands.cluster.scale.poolOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--count <n>` | {{t:cli.commands.cluster.scale.countOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-cluster-destroy"></a>
### 4.4 destroy

{{t:cli.commands.cluster.destroy.description}}

```bash
rdc cluster destroy <cluster> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--force` | {{t:cli.commands.cluster.destroy.forceOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-cluster-kubeconfig"></a>
### 4.5 kubeconfig

{{t:cli.commands.cluster.kubeconfig.description}}

```bash
rdc cluster kubeconfig <cluster>
```

<a id="cli-local-cluster-fork"></a>
### 4.6 fork

{{t:cli.commands.cluster.fork.description}}

```bash
rdc cluster fork <cluster> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--tag <tag>` | {{t:cli.commands.cluster.fork.tagOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--to <dest-cluster>` | {{t:cli.commands.cluster.fork.toOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--writes <disposition>` | {{t:cli.commands.cluster.fork.writesOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--up` | {{t:cli.commands.cluster.fork.upOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-cluster-migrate"></a>
### 4.7 migrate

{{t:cli.commands.cluster.migrate.description}}

```bash
rdc cluster migrate <cluster> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--to <dest-cluster>` | {{t:cli.commands.cluster.migrate.toOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-cluster-join"></a>
### 4.8 join

{{t:cli.commands.cluster.join.description}}

```bash
rdc cluster join <machine> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--cluster <name>` | {{t:cli.commands.cluster.join.clusterOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-cluster-evict"></a>
### 4.9 evict

{{t:cli.commands.cluster.evict.description}}

```bash
rdc cluster evict <machine> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--force` | {{t:cli.commands.cluster.evict.forceOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-cluster-rehearse"></a>
### 4.10 rehearse

{{t:cli.commands.cluster.rehearse.description}}

```bash
rdc cluster rehearse <cluster> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--on <dest-cluster>` | {{t:cli.commands.cluster.rehearse.onOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--tag <tag>` | {{t:cli.commands.cluster.rehearse.tagOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-cluster-snapshot"></a>
### 4.11 snapshot

{{t:cli.commands.cluster.snapshot.description}}

<a id="cli-local-cluster-snapshot-create"></a>
#### create

{{t:cli.commands.cluster.snapshot.create.description}}

```bash
rdc cluster snapshot create <cluster> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--snapshot <label>` | {{t:cli.commands.cluster.snapshot.create.labelOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-cluster-snapshot-list"></a>
#### list

{{t:cli.commands.cluster.snapshot.list.description}}

```bash
rdc cluster snapshot list <cluster> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
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


---

<a id="cli-local-group-repo"></a>
## 6. {{t:cli.docs.sectionTitles.repo}}

{{t:cli.commands.repo.description}}

<a id="cli-local-repo-up"></a>
### 6.1 up

{{t:cli.commands.repo.up.description}}

```bash
rdc repo up [ref] [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--no-start` | {{t:cli.commands.repo.up.noStartOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--skip-checkpoint` | {{t:cli.commands.repo.up.skipCheckpointOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--tls` | {{t:cli.commands.repo.up.tlsOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--no-wait` | {{t:cli.commands.repo.up.noWaitOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--all` | {{t:cli.commands.repo.up.allOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `-m, --machine <name>` | {{t:cli.commands.repo.batchMachineOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--include-forks` | {{t:cli.commands.repo.upAll.includeForksOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--parallel` | {{t:cli.commands.repo.upAll.parallelOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--concurrency <n>` | {{t:cli.commands.repo.upAll.concurrencyOption}} | {{t:cli.docs.optionLabels.no}} | `3` |
| `-y, --yes` | {{t:cli.commands.repo.yesOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |
| `--skip-router-restart` | {{t:cli.options.skipRouterRestart}} | {{t:cli.docs.optionLabels.no}} | - |
| `--dry-run` | {{t:cli.options.dryRun}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-repo-down"></a>
### 6.2 down

{{t:cli.commands.repo.down.description}}

```bash
rdc repo down [ref] [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--unmount` | {{t:cli.commands.repo.down.unmountOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--checkpoint` | {{t:cli.commands.repo.down.checkpointOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--all` | {{t:cli.commands.repo.down.allOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `-m, --machine <name>` | {{t:cli.commands.repo.batchMachineOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--parallel` | {{t:cli.commands.repo.upAll.parallelOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--concurrency <n>` | {{t:cli.commands.repo.upAll.concurrencyOption}} | {{t:cli.docs.optionLabels.no}} | `3` |
| `-y, --yes` | {{t:cli.commands.repo.yesOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |
| `--skip-router-restart` | {{t:cli.options.skipRouterRestart}} | {{t:cli.docs.optionLabels.no}} | - |
| `--dry-run` | {{t:cli.options.dryRun}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-repo-status"></a>
### 6.3 status

{{t:cli.commands.repo.status.description}}

```bash
rdc repo status <ref> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |
| `--skip-router-restart` | {{t:cli.options.skipRouterRestart}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-repo-cat"></a>
### 6.4 cat

{{t:cli.commands.repo.cat.description}}

```bash
rdc repo cat <ref> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--remote-file <path>` | {{t:cli.commands.repo.cat.remoteFileOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--max-bytes <n>` | {{t:cli.commands.repo.cat.maxBytesOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--offset <n>` | {{t:cli.commands.repo.cat.offsetOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--head <lines>` | {{t:cli.commands.repo.cat.headOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--tail <lines>` | {{t:cli.commands.repo.cat.tailOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--stat` | {{t:cli.commands.repo.cat.statOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--force-binary` | {{t:cli.commands.repo.cat.forceBinaryOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |
| `--skip-router-restart` | {{t:cli.options.skipRouterRestart}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-repo-diff"></a>
### 6.5 diff

{{t:cli.commands.repo.diff.description}}

```bash
rdc repo diff <ref> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--base <ref>` | {{t:cli.commands.repo.diff.baseOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--name-only` | {{t:cli.commands.repo.diff.nameOnlyOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--stat` | {{t:cli.commands.repo.diff.statOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--content [path]` | {{t:cli.commands.repo.diff.contentOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--fast` | {{t:cli.commands.repo.diff.fastOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |
| `--skip-router-restart` | {{t:cli.options.skipRouterRestart}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-repo-list"></a>
### 6.6 list

{{t:cli.commands.repo.list.description}}

```bash
rdc repo list [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-m, --machine <name>` | {{t:cli.commands.repo.machineOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--datastore <name>` | {{t:cli.commands.repo.list.datastoreOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |
| `--skip-router-restart` | {{t:cli.options.skipRouterRestart}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-repo-create"></a>
### 6.7 create

{{t:cli.commands.repo.create.description}}

```bash
rdc repo create <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-m, --machine <name>` | {{t:cli.commands.repo.machineOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--datastore <name>` | {{t:cli.commands.repo.create.datastoreOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--size <size>` | {{t:cli.commands.repo.create.sizeOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--no-docker` | {{t:cli.commands.repo.create.noDockerOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |
| `--skip-router-restart` | {{t:cli.options.skipRouterRestart}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-repo-delete"></a>
### 6.8 delete

{{t:cli.commands.repo.delete.description}}

```bash
rdc repo delete <ref> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--archive-config` | {{t:cli.commands.repo.delete.archiveOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `-y, --yes` | {{t:cli.options.yes}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |
| `--skip-router-restart` | {{t:cli.options.skipRouterRestart}} | {{t:cli.docs.optionLabels.no}} | - |
| `--dry-run` | {{t:cli.options.dryRun}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-repo-commit"></a>
### 6.9 commit

{{t:cli.commands.repo.commit.description}}

```bash
rdc repo commit <ref> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--message <msg>` | {{t:cli.commands.repo.commit.messageOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--author <author>` | {{t:cli.commands.repo.commit.authorOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-repo-branch"></a>
### 6.10 branch

{{t:cli.commands.repo.branch.description}}

```bash
rdc repo branch <ref> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--branch <branch>` | {{t:cli.commands.repo.branch.branchOption}} | {{t:cli.docs.optionLabels.yes}} | - |


<a id="cli-local-repo-checkout"></a>
### 6.11 checkout

{{t:cli.commands.repo.checkout.description}}

```bash
rdc repo checkout <commit-or-branch-ref> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--tag <name>` | {{t:cli.commands.repo.checkout.tagOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--from <workingFork>` | {{t:cli.commands.repo.checkout.fromOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |
| `--skip-router-restart` | {{t:cli.options.skipRouterRestart}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-repo-log"></a>
### 6.12 log

{{t:cli.commands.repo.log.description}}

```bash
rdc repo log <ref> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-repo-merge"></a>
### 6.13 merge

{{t:cli.commands.repo.merge.description}}

```bash
rdc repo merge <ref> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--from <source>` | {{t:cli.commands.repo.merge.fromOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--force` | {{t:cli.commands.repo.merge.forceOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--resolve <ours|theirs>` | {{t:cli.commands.repo.merge.resolveOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--base <guid>` | {{t:cli.commands.repo.merge.baseOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-repo-gc"></a>
### 6.14 gc

{{t:cli.commands.repo.gc.description}}

```bash
rdc repo gc [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-m, --machine <name>` | {{t:cli.commands.repo.machineOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--apply` | {{t:cli.commands.repo.gc.applyOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-repo-fork"></a>
### 6.15 fork

{{t:cli.commands.repo.fork.description}}

```bash
rdc repo fork <ref> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--tag <name>` | {{t:cli.commands.repo.fork.tagOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--checkpoint` | {{t:cli.commands.repo.fork.checkpointOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--immutable` | {{t:cli.commands.repo.fork.immutableOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--up` | {{t:cli.commands.repo.fork.upOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--no-wait` | {{t:cli.commands.repo.fork.detachOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |
| `--skip-router-restart` | {{t:cli.options.skipRouterRestart}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-repo-replicate"></a>
### 6.16 replicate

{{t:cli.commands.repo.replicate.description}}

<a id="cli-local-repo-replicate-status"></a>
#### status

{{t:cli.commands.repo.replicate.status.description}}

```bash
rdc repo replicate status <ref>
```

<a id="cli-local-repo-replicate-remove"></a>
#### remove

{{t:cli.commands.repo.replicate.remove.description}}

```bash
rdc repo replicate remove <ref> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-repo-replicate-refresh"></a>
#### refresh

{{t:cli.commands.repo.replicate.refresh.description}}

```bash
rdc repo replicate refresh <ref> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-repo-canary"></a>
### 6.17 canary

{{t:cli.commands.repo.canary.description}}

<a id="cli-local-repo-canary-status"></a>
#### status

{{t:cli.commands.repo.canary.status.description}}

```bash
rdc repo canary status <ref>
```

<a id="cli-local-repo-canary-weight"></a>
#### weight

{{t:cli.commands.repo.canary.weight.description}}

```bash
rdc repo canary weight <ref> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--weight <percent>` | {{t:cli.commands.repo.canary.weightOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-repo-canary-remove"></a>
#### remove

{{t:cli.commands.repo.canary.remove.description}}

```bash
rdc repo canary remove <ref> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-repo-canary-create"></a>
#### create

{{t:cli.commands.repo.canary.create.description}}

```bash
rdc repo canary create <ref> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--image <image>` | {{t:cli.commands.repo.canary.imageOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--port <port>` | {{t:cli.commands.repo.canary.portOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--weight <percent>` | {{t:cli.commands.repo.canary.weightOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--service <name>` | {{t:cli.commands.repo.canary.serviceOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--replicas <n>` | {{t:cli.commands.repo.canary.replicasOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-repo-resize"></a>
### 6.18 resize

{{t:cli.commands.repo.resize.description}}

```bash
rdc repo resize <ref> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--size <size>` | {{t:cli.commands.repo.resize.sizeOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |
| `--skip-router-restart` | {{t:cli.options.skipRouterRestart}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-repo-expand"></a>
### 6.19 expand

{{t:cli.commands.repo.expand.description}}

```bash
rdc repo expand <ref> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--size <size>` | {{t:cli.commands.repo.resize.sizeOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |
| `--skip-router-restart` | {{t:cli.options.skipRouterRestart}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-repo-trim"></a>
### 6.20 trim

{{t:cli.commands.repo.trim.description}}

```bash
rdc repo trim [ref] [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--docker` | {{t:cli.commands.repo.trim.dockerOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--docker-volumes` | {{t:cli.commands.repo.trim.dockerVolumesOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--report-only` | {{t:cli.commands.repo.trim.reportOnlyOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `-m, --machine <name>` | {{t:cli.commands.repo.machineOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-repo-policy"></a>
### 6.21 policy

{{t:cli.commands.repo.policy.description}}

<a id="cli-local-repo-policy-set"></a>
#### set

{{t:cli.commands.repo.policy.set.description}}

```bash
rdc repo policy set [ref] [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--auto-grow <bool>` | {{t:cli.commands.repo.policy.set.autoGrowOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--max-quota <size>` | {{t:cli.commands.repo.policy.set.maxQuotaOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--grow-threshold <percent>` | {{t:cli.commands.repo.policy.set.growThresholdOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--grow-step <step>` | {{t:cli.commands.repo.policy.set.growStepOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--auto-trim <bool>` | {{t:cli.commands.repo.policy.set.autoTrimOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--trim-interval <hours>` | {{t:cli.commands.repo.policy.set.trimIntervalOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `-m, --machine <name>` | {{t:cli.commands.repo.machineOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-repo-policy-get"></a>
#### get

{{t:cli.commands.repo.policy.get.description}}

```bash
rdc repo policy get [ref] [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-m, --machine <name>` | {{t:cli.commands.repo.machineOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-repo-push"></a>
### 6.22 push

{{t:cli.commands.repo.push.description}}

```bash
rdc repo push <ref> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--to <remote>` | {{t:cli.commands.repo.push.optionTo}} | {{t:cli.docs.optionLabels.no}} | - |
| `--to-machine <machine>` | — | {{t:cli.docs.optionLabels.no}} | - |
| `--provision <provider>` | {{t:cli.commands.repo.push.optionProvision}} | {{t:cli.docs.optionLabels.no}} | - |
| `--checkpoint` | {{t:cli.commands.repo.push.optionCheckpoint}} | {{t:cli.docs.optionLabels.no}} | - |
| `--force` | {{t:cli.commands.repo.push.optionForce}} | {{t:cli.docs.optionLabels.no}} | - |
| `-w, --watch` | {{t:cli.options.watch}} | {{t:cli.docs.optionLabels.no}} | - |
| `--bwlimit <limit>` | {{t:cli.commands.repo.push.optionBwlimit}} | {{t:cli.docs.optionLabels.no}} | - |
| `--delta-base <guid>` | {{t:cli.commands.repo.push.optionDeltaBase}} | {{t:cli.docs.optionLabels.no}} | - |
| `--strategy <strategy>` | {{t:cli.commands.repo.push.optionStrategy}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |
| `--skip-router-restart` | {{t:cli.options.skipRouterRestart}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-repo-pull"></a>
### 6.23 pull

{{t:cli.commands.repo.pull.description}}

```bash
rdc repo pull <ref> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--from <remote>` | {{t:cli.commands.repo.pull.optionFrom}} | {{t:cli.docs.optionLabels.no}} | - |
| `--from-machine <machine>` | — | {{t:cli.docs.optionLabels.no}} | - |
| `--force` | {{t:cli.commands.repo.pull.optionForce}} | {{t:cli.docs.optionLabels.no}} | - |
| `--up` | {{t:cli.commands.repo.pull.optionUp}} | {{t:cli.docs.optionLabels.no}} | - |
| `-w, --watch` | {{t:cli.options.watch}} | {{t:cli.docs.optionLabels.no}} | - |
| `--bwlimit <limit>` | {{t:cli.commands.repo.push.optionBwlimit}} | {{t:cli.docs.optionLabels.no}} | - |
| `--delta-base <guid>` | {{t:cli.commands.repo.pull.optionDeltaBase}} | {{t:cli.docs.optionLabels.no}} | - |
| `--strategy <strategy>` | {{t:cli.commands.repo.push.optionStrategy}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |
| `--skip-router-restart` | {{t:cli.options.skipRouterRestart}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-repo-migrate"></a>
### 6.24 migrate

{{t:cli.commands.repo.migrate.description}}

```bash
rdc repo migrate <ref> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--to <place>` | {{t:cli.commands.repo.migrate.optionTo}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--provision <provider>` | {{t:cli.commands.repo.migrate.optionProvision}} | {{t:cli.docs.optionLabels.no}} | - |
| `--bwlimit <limit>` | {{t:cli.commands.repo.migrate.optionBwlimit}} | {{t:cli.docs.optionLabels.no}} | - |
| `--checkpoint` | {{t:cli.commands.repo.migrate.optionCheckpoint}} | {{t:cli.docs.optionLabels.no}} | - |
| `--delta-base <guid>` | {{t:cli.commands.repo.migrate.optionDeltaBase}} | {{t:cli.docs.optionLabels.no}} | - |
| `--strategy <strategy>` | {{t:cli.commands.repo.migrate.optionStrategy}} | {{t:cli.docs.optionLabels.no}} | - |
| `--skip-dns` | {{t:cli.commands.repo.migrate.optionSkipDns}} | {{t:cli.docs.optionLabels.no}} | - |
| `--keep-source` | {{t:cli.commands.repo.migrate.optionKeepSource}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-repo-sync"></a>
### 6.25 sync

{{t:cli.commands.repo.sync.description}}

<a id="cli-local-repo-sync-upload"></a>
#### upload

{{t:cli.commands.repo.sync.upload.description}}

```bash
rdc repo sync upload <ref> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--local <paths...>` | {{t:cli.options.localPaths}} | {{t:cli.docs.optionLabels.no}} | - |
| `--remote <path>` | {{t:cli.options.remotePath}} | {{t:cli.docs.optionLabels.no}} | - |
| `--remote-file <path>` | {{t:cli.options.remoteFileUpload}} | {{t:cli.docs.optionLabels.no}} | - |
| `--mirror` | {{t:cli.options.mirrorUpload}} | {{t:cli.docs.optionLabels.no}} | - |
| `--verify` | {{t:cli.options.verifyChecksum}} | {{t:cli.docs.optionLabels.no}} | - |
| `--confirm` | {{t:cli.options.confirmSync}} | {{t:cli.docs.optionLabels.no}} | - |
| `--exclude <patterns...>` | {{t:cli.options.excludePatterns}} | {{t:cli.docs.optionLabels.no}} | - |
| `--dry-run` | {{t:cli.options.dryRun}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-repo-sync-download"></a>
#### download

{{t:cli.commands.repo.sync.download.description}}

```bash
rdc repo sync download <ref> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--local <path>` | {{t:cli.options.localPath}} | {{t:cli.docs.optionLabels.no}} | - |
| `--remote <path>` | {{t:cli.options.remotePath}} | {{t:cli.docs.optionLabels.no}} | - |
| `--remote-file <path>` | {{t:cli.options.remoteFile}} | {{t:cli.docs.optionLabels.no}} | - |
| `--mirror` | {{t:cli.options.mirrorDownload}} | {{t:cli.docs.optionLabels.no}} | - |
| `--verify` | {{t:cli.options.verifyChecksum}} | {{t:cli.docs.optionLabels.no}} | - |
| `--confirm` | {{t:cli.options.confirmSync}} | {{t:cli.docs.optionLabels.no}} | - |
| `--exclude <patterns...>` | {{t:cli.options.excludePatterns}} | {{t:cli.docs.optionLabels.no}} | - |
| `--dry-run` | {{t:cli.options.dryRun}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-repo-sync-status"></a>
#### status

{{t:cli.commands.repo.sync.status.description}}

```bash
rdc repo sync status <ref> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--local <path>` | {{t:cli.options.localPath}} | {{t:cli.docs.optionLabels.no}} | - |
| `--remote <path>` | {{t:cli.options.remotePath}} | {{t:cli.docs.optionLabels.no}} | - |
| `--remote-file <path>` | {{t:cli.options.remoteFile}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-repo-tunnel"></a>
### 6.26 tunnel

{{t:cli.commands.repo.tunnel.description}}

```bash
rdc repo tunnel <ref> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-c, --container <name>` | {{t:cli.commands.repo.tunnel.containerOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--port <port>` | {{t:cli.commands.repo.tunnel.portOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--local <port>` | {{t:cli.commands.repo.tunnel.localOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--url-only` | {{t:cli.commands.repo.tunnel.urlOnlyOption}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-repo-secret"></a>
### 6.27 secret

{{t:cli.commands.repo.secret.description}}

<a id="cli-local-repo-secret-get"></a>
#### get

{{t:cli.commands.repo.secret.get.description}}

```bash
rdc repo secret get <ref> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--key <KEY>` | {{t:cli.commands.repo.secret.keyOption}} | {{t:cli.docs.optionLabels.yes}} | - |


<a id="cli-local-repo-secret-list"></a>
#### list

{{t:cli.commands.repo.secret.list.description}}

```bash
rdc repo secret list <ref>
```

<a id="cli-local-repo-secret-set"></a>
#### set

{{t:cli.commands.repo.secret.set.description}}

```bash
rdc repo secret set <ref> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--key <KEY>` | {{t:cli.commands.repo.secret.keyOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--value <value>` | {{t:cli.commands.repo.secret.valueOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--mode <mode>` | {{t:cli.commands.repo.secret.modeOption}} | {{t:cli.docs.optionLabels.no}} | `file` |
| `--current <value>` | {{t:cli.commands.repo.secret.currentOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--rotate-secret` | {{t:cli.commands.repo.secret.rotateOption}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-repo-secret-unset"></a>
#### unset

{{t:cli.commands.repo.secret.unset.description}}

```bash
rdc repo secret unset <ref> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--key <KEY>` | {{t:cli.commands.repo.secret.keyOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--current <value>` | {{t:cli.commands.repo.secret.currentOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--rotate-secret` | {{t:cli.commands.repo.secret.rotateOption}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-repo-admin"></a>
### 6.28 admin

{{t:cli.commands.repo.admin.description}}

#### archive

{{t:cli.commands.repo.admin.archive.description}}

<a id="cli-local-repo-admin-archive-list"></a>
**list:**

{{t:cli.commands.repo.admin.archive.list.description}}

```bash
rdc repo admin archive list
```

<a id="cli-local-repo-admin-archive-purge"></a>
**purge:**

{{t:cli.commands.repo.admin.archive.purge.description}}

```bash
rdc repo admin archive purge [name] [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-y, --yes` | {{t:cli.options.yes}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-repo-admin-archive-restore"></a>
**restore:**

{{t:cli.commands.repo.admin.archive.restore.description}}

```bash
rdc repo admin archive restore <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--new-name <name>` | {{t:cli.options.newName}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-repo-admin-validate"></a>
#### validate

{{t:cli.commands.repo.admin.validate.description}}

```bash
rdc repo admin validate <ref> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |
| `--skip-router-restart` | {{t:cli.options.skipRouterRestart}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-repo-admin-fsck"></a>
#### fsck

{{t:cli.commands.repo.admin.fsck.description}}

```bash
rdc repo admin fsck [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-m, --machine <name>` | {{t:cli.commands.repo.machineOption}} | {{t:cli.docs.optionLabels.yes}} | - |


<a id="cli-local-repo-admin-ownership"></a>
#### ownership

{{t:cli.commands.repo.admin.ownership.description}}

```bash
rdc repo admin ownership <ref> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--uid <uid>` | {{t:cli.commands.repo.admin.ownership.uidOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |
| `--skip-router-restart` | {{t:cli.options.skipRouterRestart}} | {{t:cli.docs.optionLabels.no}} | - |


#### autostart

{{t:cli.commands.repo.admin.autostart.description}}

<a id="cli-local-repo-admin-autostart-enable"></a>
**enable:**

{{t:cli.commands.repo.admin.autostart.enable.description}}

```bash
rdc repo admin autostart enable [ref] [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |
| `--skip-router-restart` | {{t:cli.options.skipRouterRestart}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-repo-admin-autostart-disable"></a>
**disable:**

{{t:cli.commands.repo.admin.autostart.disable.description}}

```bash
rdc repo admin autostart disable [ref] [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |
| `--skip-router-restart` | {{t:cli.options.skipRouterRestart}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-repo-admin-autostart-list"></a>
**list:**

{{t:cli.commands.repo.admin.autostart.list.description}}

```bash
rdc repo admin autostart list [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-m, --machine <name>` | {{t:cli.commands.repo.machineOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |
| `--skip-router-restart` | {{t:cli.options.skipRouterRestart}} | {{t:cli.docs.optionLabels.no}} | - |


#### template

{{t:cli.commands.repo.admin.template.description}}

<a id="cli-local-repo-admin-template-list"></a>
**list:**

{{t:cli.commands.repo.admin.template.list.description}}

```bash
rdc repo admin template list
```

<a id="cli-local-repo-admin-template-apply"></a>
**apply:**

{{t:cli.commands.repo.admin.template.apply.description}}

```bash
rdc repo admin template apply <ref> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--template <name>` | {{t:cli.commands.repo.admin.template.apply.templateOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--file <path>` | {{t:cli.commands.repo.admin.template.fileOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--grand <name>` | {{t:cli.commands.repo.up.grandOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |
| `--skip-router-restart` | {{t:cli.options.skipRouterRestart}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-repo-promote"></a>
### 6.29 promote

{{t:cli.commands.repo.promote.description}}

```bash
rdc repo promote <fork-ref> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-y, --yes` | {{t:cli.options.yes}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |
| `--skip-router-restart` | {{t:cli.options.skipRouterRestart}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-repo-logs"></a>
### 6.30 logs

{{t:cli.commands.repo.logs.description}}

```bash
rdc repo logs <ref> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-c, --container <name>` | {{t:cli.commands.repo.logs.containerOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `-f, --follow` | {{t:cli.commands.repo.logs.followOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--lines <n>` | {{t:cli.commands.repo.logs.linesOption}} | {{t:cli.docs.optionLabels.no}} | `100` |
| `--timestamps` | {{t:cli.commands.repo.logs.timestampsOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-repo-exec"></a>
### 6.31 exec

{{t:cli.commands.repo.exec.description}}

```bash
rdc repo exec <ref> <cmd...> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-c, --container <name>` | {{t:cli.commands.repo.exec.containerOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `-i, --interactive` | {{t:cli.commands.repo.exec.interactiveOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `-u, --user <user>` | {{t:cli.commands.repo.exec.userOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |


---

<a id="cli-local-group-job"></a>
## 7. {{t:cli.docs.sectionTitles.job}}

{{t:cli.commands.job.description}}

<a id="cli-local-job-list"></a>
### 7.1 list

{{t:cli.commands.job.list.description}}

```bash
rdc job list [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-m, --machine <name>` | {{t:cli.commands.repo.machineOption}} | {{t:cli.docs.optionLabels.yes}} | - |


<a id="cli-local-job-status"></a>
### 7.2 status

{{t:cli.commands.job.status.description}}

```bash
rdc job status <job-id> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-m, --machine <name>` | {{t:cli.commands.repo.machineOption}} | {{t:cli.docs.optionLabels.yes}} | - |


<a id="cli-local-job-logs"></a>
### 7.3 logs

{{t:cli.commands.job.logs.description}}

```bash
rdc job logs <job-id> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-m, --machine <name>` | {{t:cli.commands.repo.machineOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `-f, --follow` | {{t:cli.commands.job.logs.followOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--since-line <n>` | {{t:cli.commands.job.logs.sinceLineOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-job-cancel"></a>
### 7.4 cancel

{{t:cli.commands.job.cancel.description}}

```bash
rdc job cancel <job-id> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-m, --machine <name>` | {{t:cli.commands.repo.machineOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `-y, --yes` | {{t:cli.options.yes}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-job-gc"></a>
### 7.5 gc

{{t:cli.commands.job.gc.description}}

```bash
rdc job gc [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-m, --machine <name>` | {{t:cli.commands.repo.machineOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--older-than <duration>` | {{t:cli.commands.job.gc.olderThanOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `-y, --yes` | {{t:cli.options.yes}} | {{t:cli.docs.optionLabels.no}} | - |


---

<a id="cli-local-group-backup"></a>
## 8. {{t:cli.docs.sectionTitles.backup}}

{{t:cli.commands.backup.description}}

<a id="cli-local-backup-schedule"></a>
### 8.1 schedule

{{t:cli.commands.backup.schedule.description}}

```bash
rdc backup schedule [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-m, --machine <name>` | {{t:cli.options.machine}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--dry-run` | {{t:cli.commands.backup.schedule.optionDryRun}} | {{t:cli.docs.optionLabels.no}} | - |
| `--force` | {{t:cli.commands.backup.schedule.optionForce}} | {{t:cli.docs.optionLabels.no}} | - |
| `--reset-failed` | {{t:cli.commands.backup.schedule.optionResetFailed}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-backup-cancel"></a>
### 8.2 cancel

{{t:cli.commands.backup.cancel.description}}

```bash
rdc backup cancel [strategy] [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-m, --machine <name>` | {{t:cli.options.machine}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-backup-list"></a>
### 8.3 list

{{t:cli.commands.backup.list.description}}

```bash
rdc backup list [artifact-ref] [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-m, --machine <name>` | {{t:cli.options.machine}} | {{t:cli.docs.optionLabels.no}} | - |
| `--storage <name>` | {{t:cli.commands.backup.list.optionStorage}} | {{t:cli.docs.optionLabels.no}} | - |
| `--path <subdir>` | {{t:cli.commands.backup.list.optionPath}} | {{t:cli.docs.optionLabels.no}} | - |
| `-w, --watch` | {{t:cli.options.watch}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-backup-restore"></a>
### 8.4 restore

{{t:cli.commands.backup.restore.description}}

```bash
rdc backup restore <artifact-ref> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--as <name>` | {{t:cli.commands.backup.restore.optionAs}} | {{t:cli.docs.optionLabels.no}} | - |
| `-m, --machine <name>` | {{t:cli.options.machine}} | {{t:cli.docs.optionLabels.no}} | - |
| `--datastore <name>` | {{t:cli.commands.backup.restore.optionDatastore}} | {{t:cli.docs.optionLabels.no}} | - |
| `--up` | {{t:cli.commands.backup.restore.optionUp}} | {{t:cli.docs.optionLabels.no}} | - |
| `--health-window <seconds>` | {{t:cli.options.healthWindow}} | {{t:cli.docs.optionLabels.no}} | - |
| `--health-timeout <seconds>` | {{t:cli.options.healthTimeout}} | {{t:cli.docs.optionLabels.no}} | - |
| `-y, --yes` | {{t:cli.options.yes}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-backup-run"></a>
### 8.5 run

{{t:cli.commands.backup.run.description}}

```bash
rdc backup run [strategy] [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-m, --machine <name>` | {{t:cli.options.machine}} | {{t:cli.docs.optionLabels.yes}} | - |
| `-w, --watch` | {{t:cli.options.watch}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-backup-status"></a>
### 8.6 status

{{t:cli.commands.backup.status.description}}

```bash
rdc backup status [strategy] [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-m, --machine <name>` | {{t:cli.options.machine}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-backup-strategy"></a>
### 8.7 strategy

{{t:cli.commands.backup.strategy.description}}

<a id="cli-local-backup-strategy-set"></a>
#### set

{{t:cli.commands.backup.strategy.set.description}}

```bash
rdc backup strategy set <strategy> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--destination <name>` | {{t:cli.commands.backup.strategy.set.optionDestination}} | {{t:cli.docs.optionLabels.no}} | - |
| `--storage <name>` | {{t:cli.commands.backup.strategy.set.optionStorage}} | {{t:cli.docs.optionLabels.no}} | - |
| `--cron <expression>` | {{t:cli.commands.backup.strategy.set.optionCron}} | {{t:cli.docs.optionLabels.no}} | - |
| `--mode <mode>` | {{t:cli.commands.backup.strategy.set.optionMode}} | {{t:cli.docs.optionLabels.no}} | - |
| `--bwlimit <limit>` | {{t:cli.commands.backup.strategy.set.optionBwlimit}} | {{t:cli.docs.optionLabels.no}} | - |
| `--include <repos>` | {{t:cli.commands.backup.strategy.set.optionInclude}} | {{t:cli.docs.optionLabels.no}} | - |
| `--exclude <repos>` | {{t:cli.commands.backup.strategy.set.optionExclude}} | {{t:cli.docs.optionLabels.no}} | - |
| `--folder <path>` | {{t:cli.commands.backup.strategy.set.optionFolder}} | {{t:cli.docs.optionLabels.no}} | - |
| `--enable` | {{t:cli.commands.backup.strategy.set.optionEnable}} | {{t:cli.docs.optionLabels.no}} | - |
| `--disable` | {{t:cli.commands.backup.strategy.set.optionDisable}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-backup-strategy-bind"></a>
#### bind

{{t:cli.commands.backup.strategy.bind.description}}

```bash
rdc backup strategy bind <strategy> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-m, --machine <name>` | {{t:cli.commands.repo.machineOption}} | {{t:cli.docs.optionLabels.yes}} | - |


<a id="cli-local-backup-strategy-unbind"></a>
#### unbind

{{t:cli.commands.backup.strategy.unbind.description}}

```bash
rdc backup strategy unbind <strategy> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-m, --machine <name>` | {{t:cli.commands.repo.machineOption}} | {{t:cli.docs.optionLabels.yes}} | - |


<a id="cli-local-backup-strategy-remove"></a>
#### remove

{{t:cli.commands.backup.strategy.remove.description}}

```bash
rdc backup strategy remove <strategy> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--destination <name>` | {{t:cli.commands.backup.strategy.remove.optionDestination}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-backup-strategy-list"></a>
#### list

{{t:cli.commands.backup.strategy.list.description}}

```bash
rdc backup strategy list
```

<a id="cli-local-backup-strategy-show"></a>
#### show

{{t:cli.commands.backup.strategy.show.description}}

```bash
rdc backup strategy show [strategy]
```

---

<a id="cli-local-group-storage"></a>
## 9. {{t:cli.docs.sectionTitles.storage}}

{{t:cli.commands.storage.description}}

<a id="cli-local-storage-list"></a>
### 9.1 list

{{t:cli.commands.storage.list.description}}

```bash
rdc storage list [name] [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--reveal` | {{t:cli.commands.storage.list.optionReveal}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-storage-browse"></a>
### 9.2 browse

{{t:cli.commands.storage.browse.description}}

```bash
rdc storage browse <storage> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--path <subpath>` | {{t:cli.commands.storage.browse.pathOption}} | {{t:cli.docs.optionLabels.no}} | `` |


<a id="cli-local-storage-prune"></a>
### 9.3 prune

{{t:cli.commands.storage.prune.description}}

```bash
rdc storage prune <storage> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-m, --machine <name>` | {{t:cli.commands.storage.prune.machineOption}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--dry-run` | {{t:cli.options.dryRun}} | {{t:cli.docs.optionLabels.no}} | - |
| `--force` | {{t:cli.options.force}} | {{t:cli.docs.optionLabels.no}} | - |
| `--force-delete-mounted` | {{t:cli.commands.storage.prune.forceDeleteMountedOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--grace-days <days>` | {{t:cli.options.graceDays}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |
| `--skip-router-restart` | {{t:cli.options.skipRouterRestart}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-storage-add"></a>
### 9.4 add

{{t:cli.commands.storage.add.description}}

```bash
rdc storage add <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--vault <json>` | {{t:cli.options.vaultContent}} | {{t:cli.docs.optionLabels.yes}} | - |


<a id="cli-local-storage-import"></a>
### 9.5 import

{{t:cli.commands.storage.import.description}}

```bash
rdc storage import <file> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--name <name>` | {{t:cli.commands.storage.import.optionName}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-storage-remove"></a>
### 9.6 remove

{{t:cli.commands.storage.remove.description}}

```bash
rdc storage remove <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-y, --yes` | {{t:cli.options.yes}} | {{t:cli.docs.optionLabels.no}} | - |
| `--dry-run` | {{t:cli.options.dryRun}} | {{t:cli.docs.optionLabels.no}} | - |


---

<a id="cli-local-group-vscode"></a>
## 10. {{t:cli.docs.sectionTitles.vscode}}

{{t:cli.commands.vscode.description}}

<a id="cli-local-vscode-connect"></a>
### 10.1 connect

{{t:cli.commands.vscode.connect.description}}

```bash
rdc vscode connect <target> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-f, --folder <path>` | {{t:cli.options.folder}} | {{t:cli.docs.optionLabels.no}} | - |
| `--url-only` | {{t:cli.options.urlOnly}} | {{t:cli.docs.optionLabels.no}} | - |
| `-n, --new-window` | {{t:cli.options.newWindow}} | {{t:cli.docs.optionLabels.no}} | - |
| `--skip-env-setup` | {{t:cli.options.skipEnvSetup}} | {{t:cli.docs.optionLabels.no}} | - |
| `--insiders` | {{t:cli.options.insiders}} | {{t:cli.docs.optionLabels.no}} | - |
| `--browser` | {{t:cli.options.vscodeBrowser}} | {{t:cli.docs.optionLabels.no}} | - |
| `--no-open` | {{t:cli.options.vscodeNoOpen}} | {{t:cli.docs.optionLabels.no}} | - |
| `--local <port>` | {{t:cli.commands.repo.tunnel.localOption}} | {{t:cli.docs.optionLabels.no}} | - |
| `--server-provider <id>` | {{t:cli.options.vscodeServerProvider}} | {{t:cli.docs.optionLabels.no}} | - |
| `--server-archive <file>` | {{t:cli.options.vscodeServerArchive}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-vscode-list"></a>
### 10.2 list

{{t:cli.commands.vscode.list.description}}

```bash
rdc vscode list
```

<a id="cli-local-vscode-cleanup"></a>
### 10.3 cleanup

{{t:cli.commands.vscode.cleanup.description}}

```bash
rdc vscode cleanup [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--all` | {{t:cli.options.cleanupAll}} | {{t:cli.docs.optionLabels.no}} | - |
| `-c, --connection <name>` | {{t:cli.options.connectionName}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-vscode-check"></a>
### 10.4 check

{{t:cli.commands.vscode.check.description}}

```bash
rdc vscode check [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--insiders` | {{t:cli.options.insiders}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-vscode-serve"></a>
### 10.5 serve

{{t:cli.commands.vscode.serve.description}}

<a id="cli-local-vscode-serve-status"></a>
#### status

{{t:cli.commands.vscode.serve.status.description}}

```bash
rdc vscode serve status <target> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--server-provider <id>` | {{t:cli.options.vscodeServerProvider}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-vscode-serve-stop"></a>
#### stop

{{t:cli.commands.vscode.serve.stop.description}}

```bash
rdc vscode serve stop <target> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--server-provider <id>` | {{t:cli.options.vscodeServerProvider}} | {{t:cli.docs.optionLabels.no}} | - |


---

<a id="cli-local-group-term"></a>
## 11. {{t:cli.docs.sectionTitles.term}}

{{t:cli.commands.term.description}}

<a id="cli-local-term-connect"></a>
### 11.1 connect

{{t:cli.commands.term.connect.description}}

```bash
rdc term connect <target> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-c, --command <cmd>` | {{t:cli.options.command}} | {{t:cli.docs.optionLabels.no}} | - |
| `--external` | {{t:cli.options.external}} | {{t:cli.docs.optionLabels.no}} | - |
| `--reset-home` | {{t:cli.options.resetHome}} | {{t:cli.docs.optionLabels.no}} | - |


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


<a id="cli-local-subscription-logout"></a>
### 13.2 logout

{{t:cli.commands.subscription.logout.description}}

```bash
rdc subscription logout
```

<a id="cli-local-subscription-status"></a>
### 13.3 status

{{t:cli.commands.subscription.status.description}}

```bash
rdc subscription status [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-m, --machine <name>` | {{t:cli.options.machine}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-subscription-refresh"></a>
### 13.4 refresh

{{t:cli.commands.subscription.refresh.description}}

```bash
rdc subscription refresh [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-m, --machine <name>` | {{t:cli.options.machine}} | {{t:cli.docs.optionLabels.no}} | - |
| `--repo <ref>` | {{t:cli.options.repoRef}} | {{t:cli.docs.optionLabels.no}} | - |


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
| `--channel <channel>` | {{t:cli.commands.update.channelDescription}} | {{t:cli.docs.optionLabels.no}} | - |


---

<a id="cli-local-group-credits"></a>
## 15. {{t:cli.docs.sectionTitles.credits}}

{{t:cli.commands.credits.description}}

<a id="cli-local-credits"></a>
```bash
rdc credits [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--licenses` | {{t:cli.options.licenses}} | {{t:cli.docs.optionLabels.no}} | - |


---

<a id="cli-local-group-doctor"></a>
## 16. {{t:cli.docs.sectionTitles.doctor}}

{{t:cli.commands.doctor.description}}

<a id="cli-local-doctor"></a>
```bash
rdc doctor
```

---

<a id="cli-local-group-ops"></a>
## 17. {{t:cli.docs.sectionTitles.ops}}

{{t:cli.commands.ops.description}}

<a id="cli-local-ops-up"></a>
### 17.1 up

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
### 17.2 down

{{t:cli.commands.ops.down.description}}

```bash
rdc ops down [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--backend <backend>` | {{t:cli.options.opsBackend}} | {{t:cli.docs.optionLabels.no}} | - |
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-ops-status"></a>
### 17.3 status

{{t:cli.commands.ops.status.description}}

```bash
rdc ops status [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--backend <backend>` | {{t:cli.options.opsBackend}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-ops-ssh"></a>
### 17.4 ssh

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
### 17.5 setup

{{t:cli.commands.ops.setup.description}}

```bash
rdc ops setup [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--debug` | {{t:cli.options.debug}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-local-ops-check"></a>
### 17.6 check

{{t:cli.commands.ops.check.description}}

```bash
rdc ops check
```

---

<a id="cli-local-group-serve"></a>
## 18. {{t:cli.docs.sectionTitles.serve}}

{{t:cli.commands.serve.description}}

<a id="cli-local-serve"></a>
```bash
rdc serve [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-p, --port <port>` | {{t:cli.commands.serve.optionPort}} | {{t:cli.docs.optionLabels.no}} | `8080` |
| `--host <host>` | {{t:cli.commands.serve.optionHost}} | {{t:cli.docs.optionLabels.no}} | `0.0.0.0` |
| `--mode <mode>` | {{t:cli.commands.serve.optionMode}} | {{t:cli.docs.optionLabels.no}} | `daemon` |


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
