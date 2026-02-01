---
title: "CLI Application"
description: "Complete guide to using the Rediacc command-line interface for platform management"
category: "Core Concepts"
order: 2
language: en
generated: true
generatedFrom: packages/cli/src/i18n/locales/en/cli.json
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
| `--context` | {{t:cli.options.context}} |
| `--lang` | {{t:cli.options.lang}} |
| `--force` | {{t:cli.options.force}} |

---

## 1. {{t:cli.docs.sectionTitles.auth}}

{{t:cli.commands.auth.description}}

### 1.1 login

{{t:cli.commands.auth.login.description}}

```bash
rdc auth login [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-e, --email <email>` | {{t:cli.options.email}} | {{t:cli.docs.optionLabels.no}} | - |
| `-p, --password <password>` | {{t:cli.options.password}} | {{t:cli.docs.optionLabels.no}} | - |
| `-m, --master-password <password>` | {{t:cli.options.masterPassword}} | {{t:cli.docs.optionLabels.no}} | - |
| `-n, --name <name>` | {{t:cli.options.sessionName}} | {{t:cli.docs.optionLabels.no}} | - |
| `--endpoint <url>` | {{t:cli.options.endpoint}} | {{t:cli.docs.optionLabels.no}} | - |
| `--save-as <context>` | {{t:cli.options.saveAs}} | {{t:cli.docs.optionLabels.no}} | - |


### 1.2 logout

{{t:cli.commands.auth.logout.description}}

```bash
rdc auth logout
```

### 1.3 status

{{t:cli.commands.auth.status.description}}

```bash
rdc auth status
```

### 1.4 register

{{t:cli.commands.auth.register.description}}

{{t:cli.docs.supplements.auth.register.afterDescription}}

```bash
rdc auth register [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--organization <name>` | {{t:cli.options.organization}} | {{t:cli.docs.optionLabels.yes}} | - |
| `-e, --email <email>` | {{t:cli.options.email}} | {{t:cli.docs.optionLabels.yes}} | - |
| `-p, --password <password>` | {{t:cli.options.password}} | {{t:cli.docs.optionLabels.yes}} | - |
| `-m, --master-password <password>` | {{t:cli.options.masterPassword}} | {{t:cli.docs.optionLabels.no}} | - |
| `--endpoint <url>` | {{t:cli.options.endpoint}} | {{t:cli.docs.optionLabels.no}} | - |
| `--plan <plan>` | {{t:cli.options.subscriptionPlan}} | {{t:cli.docs.optionLabels.no}} | `COMMUNITY` |


### 1.5 activate

{{t:cli.commands.auth.activate.description}}

```bash
rdc auth activate [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-e, --email <email>` | {{t:cli.options.email}} | {{t:cli.docs.optionLabels.yes}} | - |
| `-p, --password <password>` | {{t:cli.options.password}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--code <code>` | {{t:cli.options.activationCode}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--endpoint <url>` | {{t:cli.options.endpoint}} | {{t:cli.docs.optionLabels.no}} | - |


### 1.6 tfa

{{t:cli.commands.auth.tfa.description}}

#### disable

{{t:cli.commands.auth.tfa.disable.description}}

```bash
rdc auth tfa disable [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--code <code>` | {{t:cli.options.tfaCode}} | {{t:cli.docs.optionLabels.no}} | - |
| `-y, --yes` | {{t:cli.options.yes}} | {{t:cli.docs.optionLabels.no}} | - |


#### enable

{{t:cli.commands.auth.tfa.enable.description}}

```bash
rdc auth tfa enable
```

#### status

{{t:cli.commands.auth.tfa.status.description}}

```bash
rdc auth tfa status
```

### 1.7 token

{{t:cli.commands.auth.token.description}}

#### fork

{{t:cli.commands.auth.token.fork.description}}

```bash
rdc auth token fork [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-n, --name <name>` | {{t:cli.options.tokenName}} | {{t:cli.docs.optionLabels.no}} | `CLI Fork` |
| `-e, --expires <hours>` | {{t:cli.options.expires}} | {{t:cli.docs.optionLabels.no}} | `24` |


#### list

{{t:cli.commands.auth.token.list.description}}

```bash
rdc auth token list
```

#### revoke

{{t:cli.commands.auth.token.revoke.description}}

```bash
rdc auth token revoke <requestId>
```

> **{{t:cli.docs.admonitions.tip}}**: {{t:cli.docs.supplements.auth.tip}}

---

## 2. {{t:cli.docs.sectionTitles.context}}

{{t:cli.commands.context.description}}

{{t:cli.docs.supplements.context.afterDescription}}

### 2.1 list

{{t:cli.commands.context.list.description}}

```bash
rdc context list
```

### 2.2 show

{{t:cli.commands.context.show.description}}

```bash
rdc context show
```

### 2.3 use

{{t:cli.commands.context.use.description}}

```bash
rdc context use
```

### 2.4 create

{{t:cli.commands.context.create.description}}

```bash
rdc context create <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-u, --api-url <url>` | {{t:cli.options.apiUrl}} | {{t:cli.docs.optionLabels.no}} | - |


### 2.5 delete

{{t:cli.commands.context.delete.description}}

```bash
rdc context delete <name>
```

### 2.6 rename

{{t:cli.commands.context.rename.description}}

```bash
rdc context rename <oldName> <newName>
```

### 2.7 current

{{t:cli.commands.context.current.description}}

```bash
rdc context current
```

### 2.8 set

{{t:cli.commands.context.set.description}}

```bash
rdc context set <key> <value>
```

> **{{t:cli.docs.admonitions.tip}}**: {{t:cli.docs.supplements.context.set.tip}}

### 2.9 unset

{{t:cli.commands.context.unset.description}}

```bash
rdc context unset
```

### 2.10 clear

{{t:cli.commands.context.clear.description}}

```bash
rdc context clear [key]
```

### 2.11 set-language

{{t:cli.commands.context.setLanguage.description}}

```bash
rdc context set-language
```

### 2.12 create-local

{{t:cli.commands.context.createLocal.description}}

{{t:cli.docs.supplements.context.createLocal.afterDescription}}

```bash
rdc context create-local <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--ssh-key <path>` | {{t:cli.options.sshKey}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--renet-path <path>` | {{t:cli.options.renetPath}} | {{t:cli.docs.optionLabels.no}} | - |


### 2.13 add-machine

{{t:cli.commands.context.addMachine.description}}

```bash
rdc context add-machine <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--ip <address>` | {{t:cli.options.machineIp}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--user <username>` | {{t:cli.options.sshUser}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--port <port>` | {{t:cli.options.sshPort}} | {{t:cli.docs.optionLabels.no}} | `22` |
| `--datastore <path>` | {{t:cli.options.datastore}} | {{t:cli.docs.optionLabels.no}} | `/mnt/rediacc` |


### 2.14 remove-machine

{{t:cli.commands.context.removeMachine.description}}

```bash
rdc context remove-machine <name>
```

### 2.15 machines

{{t:cli.commands.context.machines.description}}

```bash
rdc context machines
```

### 2.16 set-ssh

{{t:cli.commands.context.setSsh.description}}

```bash
rdc context set-ssh [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--private-key <path>` | {{t:cli.options.sshPrivateKey}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--public-key <path>` | {{t:cli.options.sshPublicKey}} | {{t:cli.docs.optionLabels.no}} | - |


### 2.17 create-s3

{{t:cli.commands.context.createS3.description}}

```bash
rdc context create-s3 <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--endpoint <url>` | {{t:cli.commands.context.createS3.optionEndpoint}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--bucket <name>` | {{t:cli.commands.context.createS3.optionBucket}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--access-key-id <key>` | {{t:cli.commands.context.createS3.optionAccessKeyId}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--ssh-key <path>` | {{t:cli.options.sshPrivateKey}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--secret-access-key <key>` | {{t:cli.commands.context.createS3.optionSecretAccessKey}} | {{t:cli.docs.optionLabels.no}} | - |
| `--region <region>` | {{t:cli.commands.context.createS3.optionRegion}} | {{t:cli.docs.optionLabels.no}} | `auto` |
| `--prefix <prefix>` | {{t:cli.commands.context.createS3.optionPrefix}} | {{t:cli.docs.optionLabels.no}} | - |
| `--renet-path <path>` | {{t:cli.commands.context.createS3.optionRenetPath}} | {{t:cli.docs.optionLabels.no}} | - |
| `--master-password <password>` | {{t:cli.commands.context.createS3.optionMasterPassword}} | {{t:cli.docs.optionLabels.no}} | - |


### 2.18 set-renet

{{t:cli.commands.context.setRenet.description}}

```bash
rdc context set-renet <path>
```

---

## 3. {{t:cli.docs.sectionTitles.organization}}

{{t:cli.commands.organization.description}}

### 3.1 list

{{t:cli.commands.organization.list.description}}

```bash
rdc organization list
```

### 3.2 info

{{t:cli.commands.organization.info.description}}

```bash
rdc organization info
```

### 3.3 dashboard

{{t:cli.commands.organization.dashboard.description}}

```bash
rdc organization dashboard
```

### 3.4 vault

{{t:cli.commands.organization.vault.description}}

#### get

{{t:cli.commands.organization.vault.get.description}}

```bash
rdc organization vault get
```

#### list

{{t:cli.commands.organization.vault.list.description}}

```bash
rdc organization vault list
```

#### update

{{t:cli.commands.organization.vault.update.description}}

```bash
rdc organization vault update [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--vault <json>` | {{t:cli.options.vaultContent}} | {{t:cli.docs.optionLabels.no}} | - |
| `--vault-version <n>` | {{t:cli.options.vaultVersion}} | {{t:cli.docs.optionLabels.no}} | - |


### 3.5 export

{{t:cli.commands.organization.export.description}}

```bash
rdc organization export [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--path <path>` | {{t:cli.options.outputPath}} | {{t:cli.docs.optionLabels.no}} | - |


### 3.6 import

{{t:cli.commands.organization.import.description}}

```bash
rdc organization import <path> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--mode <mode>` | {{t:cli.options.importMode}} | {{t:cli.docs.optionLabels.no}} | `merge` |


### 3.7 maintenance

{{t:cli.commands.organization.maintenance.description}}

```bash
rdc organization maintenance <action>
```

> **{{t:cli.docs.admonitions.warning}}**: {{t:cli.docs.supplements.organization.maintenance.warning}}

---

## 4. {{t:cli.docs.sectionTitles.user}}

{{t:cli.commands.user.description}}

### 4.1 list

{{t:cli.commands.user.list.description}}

```bash
rdc user list
```

### 4.2 create

{{t:cli.commands.user.create.description}}

```bash
rdc user create <email> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-p, --password <password>` | {{t:cli.options.userPassword}} | {{t:cli.docs.optionLabels.no}} | - |


### 4.3 activate

{{t:cli.commands.user.activate.description}}

```bash
rdc user activate <email> <activationCode>
```

### 4.4 deactivate

{{t:cli.commands.user.deactivate.description}}

```bash
rdc user deactivate <email> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-f, --force` | {{t:cli.options.force}} | {{t:cli.docs.optionLabels.no}} | - |


### 4.5 reactivate

{{t:cli.commands.user.reactivate.description}}

```bash
rdc user reactivate <email>
```

### 4.6 update-email

{{t:cli.commands.user.updateEmail.description}}

```bash
rdc user update-email <currentEmail> <newEmail>
```

### 4.7 update-password

{{t:cli.commands.user.updatePassword.description}}

```bash
rdc user update-password [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--password <password>` | {{t:cli.options.newPasswordNonInteractive}} | {{t:cli.docs.optionLabels.no}} | - |
| `--confirm <confirm>` | {{t:cli.options.confirmPasswordNonInteractive}} | {{t:cli.docs.optionLabels.no}} | - |


### 4.8 update-language

{{t:cli.commands.user.updateLanguage.description}}

```bash
rdc user update-language <language>
```

### 4.9 exists

{{t:cli.commands.user.exists.description}}

```bash
rdc user exists <email>
```

### 4.10 vault

{{t:cli.commands.user.vault.description}}

#### get

{{t:cli.commands.user.vault.get.description}}

```bash
rdc user vault get
```

#### update

{{t:cli.commands.user.vault.update.description}}

```bash
rdc user vault update [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--vault <json>` | {{t:cli.options.vaultContent}} | {{t:cli.docs.optionLabels.no}} | - |
| `--vault-version <n>` | {{t:cli.options.vaultVersion}} | {{t:cli.docs.optionLabels.no}} | - |


### 4.11 permission

{{t:cli.commands.user.permission.description}}

#### assign

{{t:cli.commands.user.permission.assign.description}}

```bash
rdc user permission assign <userEmail> <groupName>
```

---

## 5. {{t:cli.docs.sectionTitles.team}}

{{t:cli.commands.team.description}}

### 5.1 list

{{t:cli.commands.team.list.description}}

```bash
rdc team list [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--search <text>` | {{t:cli.options.searchInField}} | {{t:cli.docs.optionLabels.no}} | - |
| `--sort <field>` | {{t:cli.options.sortByField}} | {{t:cli.docs.optionLabels.no}} | - |
| `--desc` | {{t:cli.options.sortDescending}} | {{t:cli.docs.optionLabels.no}} | - |


### 5.2 create

{{t:cli.commands.team.create.description}}

```bash
rdc team create <name>
```

### 5.3 member

{{t:cli.commands.team.member.description}}

#### list

{{t:cli.commands.team.member.list.description}}

```bash
rdc team member list <teamName>
```

#### add

{{t:cli.commands.team.member.add.description}}

```bash
rdc team member add <teamName> <userEmail>
```

#### remove

{{t:cli.commands.team.member.remove.description}}

```bash
rdc team member remove <teamName> <userEmail>
```

---

## 6. {{t:cli.docs.sectionTitles.permission}}

{{t:cli.commands.permission.description}}

### 6.1 list

{{t:cli.commands.permission.list.description}}

```bash
rdc permission list
```

### 6.2 group

{{t:cli.commands.permission.group.description}}

#### list

{{t:cli.commands.permission.group.list.description}}

```bash
rdc permission group list
```

#### create

{{t:cli.commands.permission.group.create.description}}

```bash
rdc permission group create <name>
```

#### delete

{{t:cli.commands.permission.group.delete.description}}

```bash
rdc permission group delete <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-f, --force` | {{t:cli.options.force}} | {{t:cli.docs.optionLabels.no}} | - |


#### show

{{t:cli.commands.permission.group.show.description}}

```bash
rdc permission group show <name>
```

### 6.3 add

{{t:cli.commands.permission.add.description}}

```bash
rdc permission add <groupName> <permission>
```

### 6.4 remove

{{t:cli.commands.permission.remove.description}}

```bash
rdc permission remove <groupName> <permission>
```

---

## 7. {{t:cli.docs.sectionTitles.region}}

{{t:cli.commands.region.description}}

### 7.1 list

{{t:cli.commands.region.list.description}}

```bash
rdc region list [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--search <text>` | {{t:cli.options.searchInField}} | {{t:cli.docs.optionLabels.no}} | - |
| `--sort <field>` | {{t:cli.options.sortByField}} | {{t:cli.docs.optionLabels.no}} | - |
| `--desc` | {{t:cli.options.sortDescending}} | {{t:cli.docs.optionLabels.no}} | - |


---

## 8. {{t:cli.docs.sectionTitles.bridge}}

{{t:cli.commands.bridge.description}}

### 8.1 list

{{t:cli.commands.bridge.list.description}}

```bash
rdc bridge list [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-r, --region <name>` | {{t:cli.options.region}} | {{t:cli.docs.optionLabels.no}} | - |
| `--search <text>` | {{t:cli.options.searchInField}} | {{t:cli.docs.optionLabels.no}} | - |
| `--sort <field>` | {{t:cli.options.sortByField}} | {{t:cli.docs.optionLabels.no}} | - |
| `--desc` | {{t:cli.options.sortDescending}} | {{t:cli.docs.optionLabels.no}} | - |


### 8.2 reset-auth

{{t:cli.commands.bridge.resetAuth.description}}

```bash
rdc bridge reset-auth <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-r, --region <name>` | {{t:cli.options.region}} | {{t:cli.docs.optionLabels.no}} | - |


---

## 9. {{t:cli.docs.sectionTitles.machine}}

{{t:cli.commands.machine.description}}

### 9.1 list

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


### 9.2 create

{{t:cli.commands.machine.create.description}}

```bash
rdc machine create <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-t, --team <name>` | {{t:cli.options.team}} | {{t:cli.docs.optionLabels.no}} | - |
| `-b, --bridge <name>` | {{t:cli.options.bridge}} | {{t:cli.docs.optionLabels.no}} | - |
| `--vault <json>` | {{t:cli.options.vaultJsonMachine}} | {{t:cli.docs.optionLabels.no}} | - |


### 9.3 delete

{{t:cli.commands.machine.delete.description}}

```bash
rdc machine delete <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-t, --team <name>` | {{t:cli.options.team}} | {{t:cli.docs.optionLabels.no}} | - |
| `-f, --force` | {{t:cli.options.force}} | {{t:cli.docs.optionLabels.no}} | - |


### 9.4 update

{{t:cli.commands.machine.update.description}}

```bash
rdc machine update
```

### 9.5 health

{{t:cli.commands.machine.health.description}}

{{t:cli.docs.supplements.machine.health.afterDescription}}

```bash
rdc machine health <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-t, --team <name>` | {{t:cli.options.team}} | {{t:cli.docs.optionLabels.no}} | - |


### 9.6 containers

{{t:cli.commands.machine.containers.description}}

```bash
rdc machine containers <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-t, --team <name>` | {{t:cli.options.team}} | {{t:cli.docs.optionLabels.no}} | - |
| `--health-check` | {{t:cli.commands.machine.containers.healthCheck}} | {{t:cli.docs.optionLabels.no}} | - |


### 9.7 services

{{t:cli.commands.machine.services.description}}

```bash
rdc machine services <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-t, --team <name>` | {{t:cli.options.team}} | {{t:cli.docs.optionLabels.no}} | - |
| `--stability-check` | {{t:cli.commands.machine.services.stabilityCheck}} | {{t:cli.docs.optionLabels.no}} | - |


### 9.8 vault-status

{{t:cli.commands.machine.vaultStatus.description}}

```bash
rdc machine vault-status <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-t, --team <name>` | {{t:cli.options.team}} | {{t:cli.docs.optionLabels.no}} | - |


### 9.9 repos

{{t:cli.commands.machine.repos.description}}

```bash
rdc machine repos <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-t, --team <name>` | {{t:cli.options.team}} | {{t:cli.docs.optionLabels.no}} | - |
| `--search <text>` | {{t:cli.options.searchRepos}} | {{t:cli.docs.optionLabels.no}} | - |


### 9.10 test-connection

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

## 10. {{t:cli.docs.sectionTitles.repository}}

{{t:cli.commands.repository.description}}

### 10.1 list

{{t:cli.commands.repository.list.description}}

```bash
rdc repository list [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-t, --team <name>` | {{t:cli.options.team}} | {{t:cli.docs.optionLabels.no}} | - |


### 10.2 create

{{t:cli.commands.repository.create.description}}

```bash
rdc repository create <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-t, --team <name>` | {{t:cli.options.team}} | {{t:cli.docs.optionLabels.no}} | - |
| `--tag <tag>` | {{t:cli.options.repositoryTag}} | {{t:cli.docs.optionLabels.no}} | `latest` |
| `--parent <name>` | {{t:cli.options.parentRepository}} | {{t:cli.docs.optionLabels.no}} | - |
| `--parent-tag <tag>` | {{t:cli.options.parentRepositoryTag}} | {{t:cli.docs.optionLabels.no}} | - |


### 10.3 rename

{{t:cli.commands.repository.rename.description}}

```bash
rdc repository rename <oldName> <newName> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-t, --team <name>` | {{t:cli.options.team}} | {{t:cli.docs.optionLabels.no}} | - |
| `--tag <tag>` | {{t:cli.options.repositoryTag}} | {{t:cli.docs.optionLabels.no}} | `latest` |


### 10.4 delete

{{t:cli.commands.repository.delete.description}}

```bash
rdc repository delete <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-t, --team <name>` | {{t:cli.options.team}} | {{t:cli.docs.optionLabels.no}} | - |
| `--tag <tag>` | {{t:cli.options.repositoryTag}} | {{t:cli.docs.optionLabels.no}} | `latest` |
| `-f, --force` | {{t:cli.options.force}} | {{t:cli.docs.optionLabels.no}} | - |


### 10.5 promote

{{t:cli.commands.repository.promote.description}}

```bash
rdc repository promote <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-t, --team <name>` | {{t:cli.options.team}} | {{t:cli.docs.optionLabels.no}} | - |
| `--tag <tag>` | {{t:cli.options.repositoryTag}} | {{t:cli.docs.optionLabels.no}} | `latest` |
| `-f, --force` | {{t:cli.options.force}} | {{t:cli.docs.optionLabels.no}} | - |


> **{{t:cli.docs.admonitions.note}}**: {{t:cli.docs.supplements.repository.promote.note}}

### 10.6 vault

{{t:cli.commands.repository.vault.description}}

#### get

{{t:cli.commands.repository.vault.get.description}}

```bash
rdc repository vault get <repositoryName> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-t, --team <name>` | {{t:cli.options.team}} | {{t:cli.docs.optionLabels.no}} | - |
| `--tag <tag>` | {{t:cli.options.repositoryTag}} | {{t:cli.docs.optionLabels.no}} | `latest` |


#### update

{{t:cli.commands.repository.vault.update.description}}

```bash
rdc repository vault update <repositoryName> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-t, --team <name>` | {{t:cli.options.team}} | {{t:cli.docs.optionLabels.no}} | - |
| `--tag <tag>` | {{t:cli.options.repositoryTag}} | {{t:cli.docs.optionLabels.no}} | `latest` |
| `--vault <json>` | {{t:cli.options.vaultContent}} | {{t:cli.docs.optionLabels.no}} | - |
| `--vault-version <n>` | {{t:cli.options.vaultVersion}} | {{t:cli.docs.optionLabels.no}} | - |


---

## 11. {{t:cli.docs.sectionTitles.storage}}

{{t:cli.commands.storage.description}}

### 11.1 list

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


---

## 12. {{t:cli.docs.sectionTitles.queue}}

{{t:cli.commands.queue.description}}

{{t:cli.docs.supplements.queue.afterDescription}}

### 12.1 list

{{t:cli.commands.queue.list.description}}

```bash
rdc queue list [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-t, --team <name>` | {{t:cli.options.team}} | {{t:cli.docs.optionLabels.no}} | - |
| `--status <status>` | {{t:cli.options.filterStatus}} | {{t:cli.docs.optionLabels.no}} | - |
| `--priority-min <n>` | {{t:cli.options.priorityMin}} | {{t:cli.docs.optionLabels.no}} | - |
| `--priority-max <n>` | {{t:cli.options.priorityMax}} | {{t:cli.docs.optionLabels.no}} | - |
| `--search <text>` | {{t:cli.options.searchQueue}} | {{t:cli.docs.optionLabels.no}} | - |
| `--sort <field>` | {{t:cli.options.sortByField}} | {{t:cli.docs.optionLabels.no}} | - |
| `--desc` | {{t:cli.options.sortDescending}} | {{t:cli.docs.optionLabels.no}} | - |
| `--limit <n>` | {{t:cli.options.limit}} | {{t:cli.docs.optionLabels.no}} | `50` |


### 12.2 create

{{t:cli.commands.queue.create.description}}

```bash
rdc queue create [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-f, --function <name>` | {{t:cli.options.functionName}} | {{t:cli.docs.optionLabels.yes}} | - |
| `-t, --team <name>` | {{t:cli.options.team}} | {{t:cli.docs.optionLabels.no}} | - |
| `-m, --machine <name>` | {{t:cli.options.machine}} | {{t:cli.docs.optionLabels.no}} | - |
| `-b, --bridge <name>` | {{t:cli.options.bridge}} | {{t:cli.docs.optionLabels.no}} | - |
| `-p, --priority <1-5>` | {{t:cli.options.priority}} | {{t:cli.docs.optionLabels.no}} | `3` |
| `--param <key=value>` | {{t:cli.options.param}} | {{t:cli.docs.optionLabels.no}} | - |
| `--vault <json>` | {{t:cli.options.rawVault}} | {{t:cli.docs.optionLabels.no}} | - |


### 12.3 cancel

{{t:cli.commands.queue.cancel.description}}

```bash
rdc queue cancel <taskId>
```

### 12.4 retry

{{t:cli.commands.queue.retry.description}}

```bash
rdc queue retry <taskId>
```

### 12.5 trace

{{t:cli.commands.queue.trace.description}}

```bash
rdc queue trace <taskId> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-w, --watch` | {{t:cli.options.watchUpdates}} | {{t:cli.docs.optionLabels.no}} | - |
| `--interval <ms>` | {{t:cli.options.pollInterval}} | {{t:cli.docs.optionLabels.no}} | `2000` |


> **{{t:cli.docs.admonitions.tip}}**: {{t:cli.docs.supplements.queue.trace.tip}}

### 12.6 delete

{{t:cli.commands.queue.delete.description}}

```bash
rdc queue delete <taskId> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-f, --force` | {{t:cli.options.force}} | {{t:cli.docs.optionLabels.no}} | - |


---

## 13. {{t:cli.docs.sectionTitles.sync}}

{{t:cli.commands.sync.description}}

### 13.1 upload

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


### 13.2 download

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


### 13.3 status

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

## 14. {{t:cli.docs.sectionTitles.vscode}}

{{t:cli.commands.vscode.description}}

### 14.1 connect

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


### 14.2 list

{{t:cli.commands.vscode.list.description}}

```bash
rdc vscode list
```

### 14.3 cleanup

{{t:cli.commands.vscode.cleanup.description}}

```bash
rdc vscode cleanup [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--all` | {{t:cli.options.cleanupAll}} | {{t:cli.docs.optionLabels.no}} | - |
| `-c, --connection <name>` | {{t:cli.options.connectionName}} | {{t:cli.docs.optionLabels.no}} | - |


### 14.4 check

{{t:cli.commands.vscode.check.description}}

```bash
rdc vscode check [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--insiders` | {{t:cli.options.insiders}} | {{t:cli.docs.optionLabels.no}} | - |


---

## 15. {{t:cli.docs.sectionTitles.term}}

{{t:cli.commands.term.description}}

### 15.1 connect

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

## 16. {{t:cli.docs.sectionTitles.ceph}}

{{t:cli.commands.ceph.description}}

### 16.1 cluster

{{t:cli.commands.ceph.cluster.description}}

#### list

{{t:cli.commands.ceph.cluster.list.description}}

```bash
rdc ceph cluster list
```

#### create

{{t:cli.commands.ceph.cluster.create.description}}

```bash
rdc ceph cluster create <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--vault <content>` | {{t:cli.options.vaultContent}} | {{t:cli.docs.optionLabels.no}} | - |


#### delete

{{t:cli.commands.ceph.cluster.delete.description}}

```bash
rdc ceph cluster delete <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-f, --force` | {{t:cli.options.force}} | {{t:cli.docs.optionLabels.no}} | - |


#### machines

{{t:cli.commands.ceph.cluster.machines.description}}

```bash
rdc ceph cluster machines <name>
```

#### vault

{{t:cli.commands.ceph.cluster.vault.description}}

**get:**

{{t:cli.commands.ceph.cluster.vault.get.description}}

```bash
rdc ceph cluster vault get <name>
```

**update:**

{{t:cli.commands.ceph.cluster.vault.update.description}}

```bash
rdc ceph cluster vault update <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--vault <content>` | {{t:cli.options.vaultContent}} | {{t:cli.docs.optionLabels.yes}} | - |


### 16.2 pool

{{t:cli.commands.ceph.pool.description}}

#### list

{{t:cli.commands.ceph.pool.list.description}}

```bash
rdc ceph pool list [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--team <name>` | {{t:cli.options.team}} | {{t:cli.docs.optionLabels.no}} | - |
| `--cluster <name>` | {{t:cli.options.cluster}} | {{t:cli.docs.optionLabels.no}} | - |


#### create

{{t:cli.commands.ceph.pool.create.description}}

```bash
rdc ceph pool create <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--cluster <name>` | {{t:cli.options.cluster}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--team <name>` | {{t:cli.options.team}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--vault <content>` | {{t:cli.options.vaultContent}} | {{t:cli.docs.optionLabels.no}} | - |


#### delete

{{t:cli.commands.ceph.pool.delete.description}}

```bash
rdc ceph pool delete <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--team <name>` | {{t:cli.options.team}} | {{t:cli.docs.optionLabels.yes}} | - |
| `-f, --force` | {{t:cli.options.force}} | {{t:cli.docs.optionLabels.no}} | - |


#### vault

{{t:cli.commands.ceph.pool.vault.description}}

**get:**

{{t:cli.commands.ceph.pool.vault.get.description}}

```bash
rdc ceph pool vault get <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--team <name>` | {{t:cli.options.team}} | {{t:cli.docs.optionLabels.yes}} | - |


**update:**

{{t:cli.commands.ceph.pool.vault.update.description}}

```bash
rdc ceph pool vault update <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--team <name>` | {{t:cli.options.team}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--vault <content>` | {{t:cli.options.vaultContent}} | {{t:cli.docs.optionLabels.yes}} | - |


### 16.3 image

{{t:cli.commands.ceph.image.description}}

#### list

{{t:cli.commands.ceph.image.list.description}}

```bash
rdc ceph image list [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--pool <name>` | {{t:cli.options.pool}} | {{t:cli.docs.optionLabels.no}} | - |
| `--team <name>` | {{t:cli.options.team}} | {{t:cli.docs.optionLabels.no}} | - |


#### create

{{t:cli.commands.ceph.image.create.description}}

```bash
rdc ceph image create <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--pool <name>` | {{t:cli.options.pool}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--team <name>` | {{t:cli.options.team}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--machine <name>` | {{t:cli.options.machine}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--vault <content>` | {{t:cli.options.vaultContent}} | {{t:cli.docs.optionLabels.no}} | - |


#### delete

{{t:cli.commands.ceph.image.delete.description}}

```bash
rdc ceph image delete <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--pool <name>` | {{t:cli.options.pool}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--team <name>` | {{t:cli.options.team}} | {{t:cli.docs.optionLabels.yes}} | - |
| `-f, --force` | {{t:cli.options.force}} | {{t:cli.docs.optionLabels.no}} | - |


### 16.4 snapshot

{{t:cli.commands.ceph.snapshot.description}}

#### list

{{t:cli.commands.ceph.snapshot.list.description}}

```bash
rdc ceph snapshot list [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--image <name>` | {{t:cli.options.image}} | {{t:cli.docs.optionLabels.no}} | - |
| `--pool <name>` | {{t:cli.options.pool}} | {{t:cli.docs.optionLabels.no}} | - |
| `--team <name>` | {{t:cli.options.team}} | {{t:cli.docs.optionLabels.no}} | - |


#### create

{{t:cli.commands.ceph.snapshot.create.description}}

```bash
rdc ceph snapshot create <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--image <name>` | {{t:cli.options.image}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--pool <name>` | {{t:cli.options.pool}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--team <name>` | {{t:cli.options.team}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--vault <content>` | {{t:cli.options.vaultContent}} | {{t:cli.docs.optionLabels.no}} | - |


#### delete

{{t:cli.commands.ceph.snapshot.delete.description}}

```bash
rdc ceph snapshot delete <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--image <name>` | {{t:cli.options.image}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--pool <name>` | {{t:cli.options.pool}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--team <name>` | {{t:cli.options.team}} | {{t:cli.docs.optionLabels.yes}} | - |
| `-f, --force` | {{t:cli.options.force}} | {{t:cli.docs.optionLabels.no}} | - |


### 16.5 clone

{{t:cli.commands.ceph.clone.description}}

#### list

{{t:cli.commands.ceph.clone.list.description}}

```bash
rdc ceph clone list [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--snapshot <name>` | {{t:cli.options.snapshot}} | {{t:cli.docs.optionLabels.no}} | - |
| `--image <name>` | {{t:cli.options.image}} | {{t:cli.docs.optionLabels.no}} | - |
| `--pool <name>` | {{t:cli.options.pool}} | {{t:cli.docs.optionLabels.no}} | - |
| `--team <name>` | {{t:cli.options.team}} | {{t:cli.docs.optionLabels.no}} | - |


#### create

{{t:cli.commands.ceph.clone.create.description}}

```bash
rdc ceph clone create <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--snapshot <name>` | {{t:cli.options.snapshot}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--image <name>` | {{t:cli.options.image}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--pool <name>` | {{t:cli.options.pool}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--team <name>` | {{t:cli.options.team}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--vault <content>` | {{t:cli.options.vaultContent}} | {{t:cli.docs.optionLabels.no}} | - |


#### delete

{{t:cli.commands.ceph.clone.delete.description}}

```bash
rdc ceph clone delete <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--snapshot <name>` | {{t:cli.options.snapshot}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--image <name>` | {{t:cli.options.image}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--pool <name>` | {{t:cli.options.pool}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--team <name>` | {{t:cli.options.team}} | {{t:cli.docs.optionLabels.yes}} | - |
| `-f, --force` | {{t:cli.options.force}} | {{t:cli.docs.optionLabels.no}} | - |


#### machines

{{t:cli.commands.ceph.clone.machines.description}}

```bash
rdc ceph clone machines <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--snapshot <name>` | {{t:cli.options.snapshot}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--image <name>` | {{t:cli.options.image}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--pool <name>` | {{t:cli.options.pool}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--team <name>` | {{t:cli.options.team}} | {{t:cli.docs.optionLabels.yes}} | - |


#### assign

{{t:cli.commands.ceph.clone.assign.description}}

```bash
rdc ceph clone assign <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--snapshot <name>` | {{t:cli.options.snapshot}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--image <name>` | {{t:cli.options.image}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--pool <name>` | {{t:cli.options.pool}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--team <name>` | {{t:cli.options.team}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--machines <names>` | {{t:cli.options.machineNames}} | {{t:cli.docs.optionLabels.yes}} | - |


#### unassign

{{t:cli.commands.ceph.clone.unassign.description}}

```bash
rdc ceph clone unassign <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--snapshot <name>` | {{t:cli.options.snapshot}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--image <name>` | {{t:cli.options.image}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--pool <name>` | {{t:cli.options.pool}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--team <name>` | {{t:cli.options.team}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--machines <names>` | {{t:cli.options.machineNames}} | {{t:cli.docs.optionLabels.yes}} | - |


---

## 17. {{t:cli.docs.sectionTitles.audit}}

{{t:cli.commands.audit.description}}

### 17.1 list

{{t:cli.commands.audit.list.description}}

```bash
rdc audit list
```

### 17.2 log

{{t:cli.commands.audit.log.description}}

```bash
rdc audit log [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--limit <n>` | {{t:cli.options.limit}} | {{t:cli.docs.optionLabels.no}} | `100` |


### 17.3 trace

{{t:cli.commands.audit.trace.description}}

```bash
rdc audit trace <entityType> <entityId>
```

### 17.4 history

{{t:cli.commands.audit.history.description}}

```bash
rdc audit history <entityType> <entityId>
```

---

## 18. {{t:cli.docs.sectionTitles.protocol}}

{{t:cli.commands.protocol.description}}

### 18.1 register

{{t:cli.commands.protocol.register.description}}

```bash
rdc protocol register [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--system` | {{t:cli.options.protocolSystem}} | {{t:cli.docs.optionLabels.no}} | - |
| `--force` | {{t:cli.options.protocolForce}} | {{t:cli.docs.optionLabels.no}} | - |


### 18.2 unregister

{{t:cli.commands.protocol.unregister.description}}

```bash
rdc protocol unregister [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--system` | {{t:cli.options.protocolSystemUnregister}} | {{t:cli.docs.optionLabels.no}} | - |


### 18.3 status

{{t:cli.commands.protocol.status.description}}

```bash
rdc protocol status
```

### 18.4 open

{{t:cli.commands.protocol.open.description}}

```bash
rdc protocol open <url>
```

### 18.5 build

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


### 18.6 parse

{{t:cli.commands.protocol.parse.description}}

```bash
rdc protocol parse <url>
```

---

## 19. {{t:cli.docs.sectionTitles.shortcuts}}

### 19.1 run

{{t:cli.commands.shortcuts.run.description}}

```bash
rdc run
```

### 19.2 trace

{{t:cli.commands.shortcuts.trace.description}}

```bash
rdc trace
```

### 19.3 cancel

{{t:cli.commands.shortcuts.cancel.description}}

```bash
rdc cancel
```

### 19.4 retry

{{t:cli.commands.shortcuts.retry.description}}

```bash
rdc retry
```

---

## 20. {{t:cli.docs.sectionTitles.update}}

{{t:cli.commands.update.description}}

```bash
rdc update [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--force` | {{t:cli.commands.update.force}} | {{t:cli.docs.optionLabels.no}} | - |
| `--check-only` | {{t:cli.commands.update.checkOnly}} | {{t:cli.docs.optionLabels.no}} | - |


---

## 21. {{t:cli.docs.sectionTitles.doctor}}

{{t:cli.commands.doctor.description}}

```bash
rdc doctor
```

---

## {{t:cli.docs.errors.heading}}

{{t:cli.docs.errors.intro}}

| {{t:cli.docs.tableHeaders.error}} | {{t:cli.docs.tableHeaders.meaning}} |
|-------|---------|
| {{t:cli.errors.authRequired}} | {{t:cli.docs.errors.meanings.authRequired}} |
| {{t:cli.errors.noActiveContext}} | {{t:cli.docs.errors.meanings.noActiveContext}} |
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
