---
title: "تطبيق CLI (سحابي / تجريبي)"
description: "أوامر سحابية حصرية لـ Rediacc CLI — المصادقة والفرق والمنظمات وإدارة المستأجرين المتعددين"
category: "مرجع"
order: 3
language: ar
generated: true
generatedFrom: packages/cli/src/i18n/locales/ar/cli.json
sourceHash: "4dccd517c95c8c6a"
---

<!-- THIS FILE IS AUTO-GENERATED. Do not edit manually. -->
<!-- To regenerate: npm run generate:cli-docs -w @rediacc/www -->

# {{t:cli.docs.cloudPageTitle}}

## {{t:cli.docs.cloudOverview.heading}}

{{t:cli.docs.cloudOverview.text}}

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
| `--save-as <name>` | {{t:cli.options.saveAs}} | {{t:cli.docs.optionLabels.no}} | - |


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

## 2. {{t:cli.docs.sectionTitles.organization}}

{{t:cli.commands.organization.description}}

### 2.1 list

{{t:cli.commands.organization.list.description}}

```bash
rdc organization list
```

### 2.2 info

{{t:cli.commands.organization.info.description}}

```bash
rdc organization info
```

### 2.3 dashboard

{{t:cli.commands.organization.dashboard.description}}

```bash
rdc organization dashboard
```

### 2.4 vault

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


### 2.5 export

{{t:cli.commands.organization.export.description}}

```bash
rdc organization export [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--path <path>` | {{t:cli.options.outputPath}} | {{t:cli.docs.optionLabels.no}} | - |


### 2.6 import

{{t:cli.commands.organization.import.description}}

```bash
rdc organization import <path> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--mode <mode>` | {{t:cli.options.importMode}} | {{t:cli.docs.optionLabels.no}} | `merge` |


### 2.7 maintenance

{{t:cli.commands.organization.maintenance.description}}

```bash
rdc organization maintenance <action>
```

> **{{t:cli.docs.admonitions.warning}}**: {{t:cli.docs.supplements.organization.maintenance.warning}}

---

## 3. {{t:cli.docs.sectionTitles.user}}

{{t:cli.commands.user.description}}

### 3.1 list

{{t:cli.commands.user.list.description}}

```bash
rdc user list
```

### 3.2 create

{{t:cli.commands.user.create.description}}

```bash
rdc user create <email> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-p, --password <password>` | {{t:cli.options.userPassword}} | {{t:cli.docs.optionLabels.no}} | - |


### 3.3 activate

{{t:cli.commands.user.activate.description}}

```bash
rdc user activate <email> <activationCode>
```

### 3.4 deactivate

{{t:cli.commands.user.deactivate.description}}

```bash
rdc user deactivate <email> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-f, --force` | {{t:cli.options.force}} | {{t:cli.docs.optionLabels.no}} | - |


### 3.5 reactivate

{{t:cli.commands.user.reactivate.description}}

```bash
rdc user reactivate <email>
```

### 3.6 update-email

{{t:cli.commands.user.updateEmail.description}}

```bash
rdc user update-email <currentEmail> <newEmail>
```

### 3.7 update-password

{{t:cli.commands.user.updatePassword.description}}

```bash
rdc user update-password [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--password <password>` | {{t:cli.options.newPasswordNonInteractive}} | {{t:cli.docs.optionLabels.no}} | - |
| `--confirm <confirm>` | {{t:cli.options.confirmPasswordNonInteractive}} | {{t:cli.docs.optionLabels.no}} | - |


### 3.8 update-language

{{t:cli.commands.user.updateLanguage.description}}

```bash
rdc user update-language <language>
```

### 3.9 exists

{{t:cli.commands.user.exists.description}}

```bash
rdc user exists <email>
```

### 3.10 vault

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


### 3.11 permission

{{t:cli.commands.user.permission.description}}

#### assign

{{t:cli.commands.user.permission.assign.description}}

```bash
rdc user permission assign <userEmail> <groupName>
```

---

## 4. {{t:cli.docs.sectionTitles.team}}

{{t:cli.commands.team.description}}

### 4.1 list

{{t:cli.commands.team.list.description}}

```bash
rdc team list [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--search <text>` | {{t:cli.options.searchInField}} | {{t:cli.docs.optionLabels.no}} | - |
| `--sort <field>` | {{t:cli.options.sortByField}} | {{t:cli.docs.optionLabels.no}} | - |
| `--desc` | {{t:cli.options.sortDescending}} | {{t:cli.docs.optionLabels.no}} | - |


### 4.2 create

{{t:cli.commands.team.create.description}}

```bash
rdc team create <name>
```

### 4.3 member

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

## 5. {{t:cli.docs.sectionTitles.permission}}

{{t:cli.commands.permission.description}}

### 5.1 list

{{t:cli.commands.permission.list.description}}

```bash
rdc permission list
```

### 5.2 group

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

### 5.3 add

{{t:cli.commands.permission.add.description}}

```bash
rdc permission add <groupName> <permission>
```

### 5.4 remove

{{t:cli.commands.permission.remove.description}}

```bash
rdc permission remove <groupName> <permission>
```

---

## 6. {{t:cli.docs.sectionTitles.region}}

{{t:cli.commands.region.description}}

### 6.1 list

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

## 7. {{t:cli.docs.sectionTitles.bridge}}

{{t:cli.commands.bridge.description}}

### 7.1 list

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


### 7.2 reset-auth

{{t:cli.commands.bridge.resetAuth.description}}

```bash
rdc bridge reset-auth <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-r, --region <name>` | {{t:cli.options.region}} | {{t:cli.docs.optionLabels.no}} | - |


---

## 8. {{t:cli.docs.sectionTitles.repository}}

{{t:cli.commands.repository.description}}

### 8.1 list

{{t:cli.commands.repository.list.description}}

```bash
rdc repository list [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-t, --team <name>` | {{t:cli.options.team}} | {{t:cli.docs.optionLabels.no}} | - |


### 8.2 create

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


### 8.3 rename

{{t:cli.commands.repository.rename.description}}

```bash
rdc repository rename <oldName> <newName> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-t, --team <name>` | {{t:cli.options.team}} | {{t:cli.docs.optionLabels.no}} | - |
| `--tag <tag>` | {{t:cli.options.repositoryTag}} | {{t:cli.docs.optionLabels.no}} | `latest` |


### 8.4 delete

{{t:cli.commands.repository.delete.description}}

```bash
rdc repository delete <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-t, --team <name>` | {{t:cli.options.team}} | {{t:cli.docs.optionLabels.no}} | - |
| `--tag <tag>` | {{t:cli.options.repositoryTag}} | {{t:cli.docs.optionLabels.no}} | `latest` |
| `-f, --force` | {{t:cli.options.force}} | {{t:cli.docs.optionLabels.no}} | - |


### 8.5 promote

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

### 8.6 vault

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

## 9. {{t:cli.docs.sectionTitles.queue}}

{{t:cli.commands.queue.description}}

{{t:cli.docs.supplements.queue.afterDescription}}

### 9.1 list

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


### 9.2 create

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


### 9.3 cancel

{{t:cli.commands.queue.cancel.description}}

```bash
rdc queue cancel <taskId>
```

### 9.4 retry

{{t:cli.commands.queue.retry.description}}

```bash
rdc queue retry <taskId>
```

### 9.5 trace

{{t:cli.commands.queue.trace.description}}

```bash
rdc queue trace <taskId> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-w, --watch` | {{t:cli.options.watchUpdates}} | {{t:cli.docs.optionLabels.no}} | - |
| `--interval <ms>` | {{t:cli.options.pollInterval}} | {{t:cli.docs.optionLabels.no}} | `2000` |


> **{{t:cli.docs.admonitions.tip}}**: {{t:cli.docs.supplements.queue.trace.tip}}

### 9.6 delete

{{t:cli.commands.queue.delete.description}}

```bash
rdc queue delete <taskId> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-f, --force` | {{t:cli.options.force}} | {{t:cli.docs.optionLabels.no}} | - |


---

## 10. {{t:cli.docs.sectionTitles.ceph}}

{{t:cli.commands.ceph.description}}

### 10.1 cluster

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


### 10.2 pool

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


### 10.3 image

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


### 10.4 snapshot

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


### 10.5 clone

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

## 11. {{t:cli.docs.sectionTitles.audit}}

{{t:cli.commands.audit.description}}

### 11.1 list

{{t:cli.commands.audit.list.description}}

```bash
rdc audit list
```

### 11.2 log

{{t:cli.commands.audit.log.description}}

```bash
rdc audit log [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--limit <n>` | {{t:cli.options.limit}} | {{t:cli.docs.optionLabels.no}} | `100` |


### 11.3 trace

{{t:cli.commands.audit.trace.description}}

```bash
rdc audit trace <entityType> <entityId>
```

### 11.4 history

{{t:cli.commands.audit.history.description}}

```bash
rdc audit history <entityType> <entityId>
```

---
