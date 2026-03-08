---
title: "Приложение CLI (Облако / Экспериментальный)"
description: "Облачные команды для Rediacc CLI — аутентификация, команды, организации и мультитенантное управление"
category: "Справочник"
order: 3
language: ru
generated: true
generatedFrom: packages/cli/src/i18n/locales/ru/cli.json
sourceHash: "4444ea8dff323936"
---

<!-- THIS FILE IS AUTO-GENERATED. Do not edit manually. -->
<!-- To regenerate: npm run generate:cli-docs -w @rediacc/www -->

# {{t:cli.docs.cloudPageTitle}}

## {{t:cli.docs.cloudOverview.heading}}

{{t:cli.docs.cloudOverview.text}}

<a id="cli-cloud-group-auth"></a>
## 1. {{t:cli.docs.sectionTitles.auth}}

{{t:cli.commands.auth.description}}

<a id="cli-cloud-auth-login"></a>
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


<a id="cli-cloud-auth-logout"></a>
### 1.2 logout

{{t:cli.commands.auth.logout.description}}

```bash
rdc auth logout
```

<a id="cli-cloud-auth-status"></a>
### 1.3 status

{{t:cli.commands.auth.status.description}}

```bash
rdc auth status
```

<a id="cli-cloud-auth-register"></a>
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


<a id="cli-cloud-auth-activate"></a>
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


<a id="cli-cloud-auth-tfa"></a>
### 1.6 tfa

{{t:cli.commands.auth.tfa.description}}

<a id="cli-cloud-auth-tfa-disable"></a>
#### disable

{{t:cli.commands.auth.tfa.disable.description}}

```bash
rdc auth tfa disable [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--code <code>` | {{t:cli.options.tfaCode}} | {{t:cli.docs.optionLabels.no}} | - |
| `-y, --yes` | {{t:cli.options.yes}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-cloud-auth-tfa-enable"></a>
#### enable

{{t:cli.commands.auth.tfa.enable.description}}

```bash
rdc auth tfa enable
```

<a id="cli-cloud-auth-tfa-status"></a>
#### status

{{t:cli.commands.auth.tfa.status.description}}

```bash
rdc auth tfa status
```

<a id="cli-cloud-auth-token"></a>
### 1.7 token

{{t:cli.commands.auth.token.description}}

<a id="cli-cloud-auth-token-fork"></a>
#### fork

{{t:cli.commands.auth.token.fork.description}}

```bash
rdc auth token fork [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-n, --name <name>` | {{t:cli.options.tokenName}} | {{t:cli.docs.optionLabels.no}} | `CLI Fork` |
| `-e, --expires <hours>` | {{t:cli.options.expires}} | {{t:cli.docs.optionLabels.no}} | `24` |


<a id="cli-cloud-auth-token-list"></a>
#### list

{{t:cli.commands.auth.token.list.description}}

```bash
rdc auth token list
```

<a id="cli-cloud-auth-token-revoke"></a>
#### revoke

{{t:cli.commands.auth.token.revoke.description}}

```bash
rdc auth token revoke <requestId>
```

> **{{t:cli.docs.admonitions.tip}}**: {{t:cli.docs.supplements.auth.tip}}

---

<a id="cli-cloud-group-organization"></a>
## 2. {{t:cli.docs.sectionTitles.organization}}

{{t:cli.commands.organization.description}}

<a id="cli-cloud-organization-list"></a>
### 2.1 list

{{t:cli.commands.organization.list.description}}

```bash
rdc organization list
```

<a id="cli-cloud-organization-info"></a>
### 2.2 info

{{t:cli.commands.organization.info.description}}

```bash
rdc organization info
```

<a id="cli-cloud-organization-dashboard"></a>
### 2.3 dashboard

{{t:cli.commands.organization.dashboard.description}}

```bash
rdc organization dashboard
```

<a id="cli-cloud-organization-vault"></a>
### 2.4 vault

{{t:cli.commands.organization.vault.description}}

<a id="cli-cloud-organization-vault-get"></a>
#### get

{{t:cli.commands.organization.vault.get.description}}

```bash
rdc organization vault get
```

<a id="cli-cloud-organization-vault-list"></a>
#### list

{{t:cli.commands.organization.vault.list.description}}

```bash
rdc organization vault list
```

<a id="cli-cloud-organization-vault-update"></a>
#### update

{{t:cli.commands.organization.vault.update.description}}

```bash
rdc organization vault update [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--vault <json>` | {{t:cli.options.vaultContent}} | {{t:cli.docs.optionLabels.no}} | - |
| `--vault-version <n>` | {{t:cli.options.vaultVersion}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-cloud-organization-export"></a>
### 2.5 export

{{t:cli.commands.organization.export.description}}

```bash
rdc organization export [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--path <path>` | {{t:cli.options.outputPath}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-cloud-organization-import"></a>
### 2.6 import

{{t:cli.commands.organization.import.description}}

```bash
rdc organization import <path> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--mode <mode>` | {{t:cli.options.importMode}} | {{t:cli.docs.optionLabels.no}} | `merge` |


<a id="cli-cloud-organization-maintenance"></a>
### 2.7 maintenance

{{t:cli.commands.organization.maintenance.description}}

```bash
rdc organization maintenance <action>
```

> **{{t:cli.docs.admonitions.warning}}**: {{t:cli.docs.supplements.organization.maintenance.warning}}

---

<a id="cli-cloud-group-user"></a>
## 3. {{t:cli.docs.sectionTitles.user}}

{{t:cli.commands.user.description}}

<a id="cli-cloud-user-list"></a>
### 3.1 list

{{t:cli.commands.user.list.description}}

```bash
rdc user list
```

<a id="cli-cloud-user-create"></a>
### 3.2 create

{{t:cli.commands.user.create.description}}

```bash
rdc user create <email> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-p, --password <password>` | {{t:cli.options.userPassword}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-cloud-user-activate"></a>
### 3.3 activate

{{t:cli.commands.user.activate.description}}

```bash
rdc user activate <email> <activationCode>
```

<a id="cli-cloud-user-deactivate"></a>
### 3.4 deactivate

{{t:cli.commands.user.deactivate.description}}

```bash
rdc user deactivate <email> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-f, --force` | {{t:cli.options.force}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-cloud-user-reactivate"></a>
### 3.5 reactivate

{{t:cli.commands.user.reactivate.description}}

```bash
rdc user reactivate <email>
```

<a id="cli-cloud-user-update-email"></a>
### 3.6 update-email

{{t:cli.commands.user.updateEmail.description}}

```bash
rdc user update-email <currentEmail> <newEmail>
```

<a id="cli-cloud-user-update-password"></a>
### 3.7 update-password

{{t:cli.commands.user.updatePassword.description}}

```bash
rdc user update-password [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--password <password>` | {{t:cli.options.newPasswordNonInteractive}} | {{t:cli.docs.optionLabels.no}} | - |
| `--confirm <confirm>` | {{t:cli.options.confirmPasswordNonInteractive}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-cloud-user-update-language"></a>
### 3.8 update-language

{{t:cli.commands.user.updateLanguage.description}}

```bash
rdc user update-language <language>
```

<a id="cli-cloud-user-exists"></a>
### 3.9 exists

{{t:cli.commands.user.exists.description}}

```bash
rdc user exists <email>
```

<a id="cli-cloud-user-vault"></a>
### 3.10 vault

{{t:cli.commands.user.vault.description}}

<a id="cli-cloud-user-vault-get"></a>
#### get

{{t:cli.commands.user.vault.get.description}}

```bash
rdc user vault get
```

<a id="cli-cloud-user-vault-update"></a>
#### update

{{t:cli.commands.user.vault.update.description}}

```bash
rdc user vault update [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--vault <json>` | {{t:cli.options.vaultContent}} | {{t:cli.docs.optionLabels.no}} | - |
| `--vault-version <n>` | {{t:cli.options.vaultVersion}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-cloud-user-permission"></a>
### 3.11 permission

{{t:cli.commands.user.permission.description}}

<a id="cli-cloud-user-permission-assign"></a>
#### assign

{{t:cli.commands.user.permission.assign.description}}

```bash
rdc user permission assign <userEmail> <groupName>
```

---

<a id="cli-cloud-group-team"></a>
## 4. {{t:cli.docs.sectionTitles.team}}

{{t:cli.commands.team.description}}

<a id="cli-cloud-team-list"></a>
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


<a id="cli-cloud-team-create"></a>
### 4.2 create

{{t:cli.commands.team.create.description}}

```bash
rdc team create <name>
```

<a id="cli-cloud-team-member"></a>
### 4.3 member

{{t:cli.commands.team.member.description}}

<a id="cli-cloud-team-member-list"></a>
#### list

{{t:cli.commands.team.member.list.description}}

```bash
rdc team member list <teamName>
```

<a id="cli-cloud-team-member-add"></a>
#### add

{{t:cli.commands.team.member.add.description}}

```bash
rdc team member add <teamName> <userEmail>
```

<a id="cli-cloud-team-member-remove"></a>
#### remove

{{t:cli.commands.team.member.remove.description}}

```bash
rdc team member remove <teamName> <userEmail>
```

---

<a id="cli-cloud-group-permission"></a>
## 5. {{t:cli.docs.sectionTitles.permission}}

{{t:cli.commands.permission.description}}

<a id="cli-cloud-permission-list"></a>
### 5.1 list

{{t:cli.commands.permission.list.description}}

```bash
rdc permission list
```

<a id="cli-cloud-permission-group"></a>
### 5.2 group

{{t:cli.commands.permission.group.description}}

<a id="cli-cloud-permission-group-list"></a>
#### list

{{t:cli.commands.permission.group.list.description}}

```bash
rdc permission group list
```

<a id="cli-cloud-permission-group-create"></a>
#### create

{{t:cli.commands.permission.group.create.description}}

```bash
rdc permission group create <name>
```

<a id="cli-cloud-permission-group-delete"></a>
#### delete

{{t:cli.commands.permission.group.delete.description}}

```bash
rdc permission group delete <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-f, --force` | {{t:cli.options.force}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-cloud-permission-group-show"></a>
#### show

{{t:cli.commands.permission.group.show.description}}

```bash
rdc permission group show <name>
```

<a id="cli-cloud-permission-add"></a>
### 5.3 add

{{t:cli.commands.permission.add.description}}

```bash
rdc permission add <groupName> <permission>
```

<a id="cli-cloud-permission-remove"></a>
### 5.4 remove

{{t:cli.commands.permission.remove.description}}

```bash
rdc permission remove <groupName> <permission>
```

---

<a id="cli-cloud-group-region"></a>
## 6. {{t:cli.docs.sectionTitles.region}}

{{t:cli.commands.region.description}}

<a id="cli-cloud-region-list"></a>
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

<a id="cli-cloud-group-bridge"></a>
## 7. {{t:cli.docs.sectionTitles.bridge}}

{{t:cli.commands.bridge.description}}

<a id="cli-cloud-bridge-list"></a>
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


<a id="cli-cloud-bridge-reset-auth"></a>
### 7.2 reset-auth

{{t:cli.commands.bridge.resetAuth.description}}

```bash
rdc bridge reset-auth <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-r, --region <name>` | {{t:cli.options.region}} | {{t:cli.docs.optionLabels.no}} | - |


---

<a id="cli-cloud-group-repository"></a>
## 8. {{t:cli.docs.sectionTitles.repository}}

{{t:cli.commands.repository.description}}

<a id="cli-cloud-repository-list"></a>
### 8.1 list

{{t:cli.commands.repository.list.description}}

```bash
rdc repository list [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-t, --team <name>` | {{t:cli.options.team}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-cloud-repository-create"></a>
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


<a id="cli-cloud-repository-rename"></a>
### 8.3 rename

{{t:cli.commands.repository.rename.description}}

```bash
rdc repository rename <oldName> <newName> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-t, --team <name>` | {{t:cli.options.team}} | {{t:cli.docs.optionLabels.no}} | - |
| `--tag <tag>` | {{t:cli.options.repositoryTag}} | {{t:cli.docs.optionLabels.no}} | `latest` |


<a id="cli-cloud-repository-delete"></a>
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


<a id="cli-cloud-repository-promote"></a>
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

<a id="cli-cloud-repository-vault"></a>
### 8.6 vault

{{t:cli.commands.repository.vault.description}}

<a id="cli-cloud-repository-vault-get"></a>
#### get

{{t:cli.commands.repository.vault.get.description}}

```bash
rdc repository vault get <repositoryName> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-t, --team <name>` | {{t:cli.options.team}} | {{t:cli.docs.optionLabels.no}} | - |
| `--tag <tag>` | {{t:cli.options.repositoryTag}} | {{t:cli.docs.optionLabels.no}} | `latest` |


<a id="cli-cloud-repository-vault-update"></a>
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

<a id="cli-cloud-group-queue"></a>
## 9. {{t:cli.docs.sectionTitles.queue}}

{{t:cli.commands.queue.description}}

{{t:cli.docs.supplements.queue.afterDescription}}

<a id="cli-cloud-queue-list"></a>
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


<a id="cli-cloud-queue-create"></a>
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


<a id="cli-cloud-queue-cancel"></a>
### 9.3 cancel

{{t:cli.commands.queue.cancel.description}}

```bash
rdc queue cancel <taskId>
```

<a id="cli-cloud-queue-retry"></a>
### 9.4 retry

{{t:cli.commands.queue.retry.description}}

```bash
rdc queue retry <taskId>
```

<a id="cli-cloud-queue-trace"></a>
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

<a id="cli-cloud-queue-delete"></a>
### 9.6 delete

{{t:cli.commands.queue.delete.description}}

```bash
rdc queue delete <taskId> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-f, --force` | {{t:cli.options.force}} | {{t:cli.docs.optionLabels.no}} | - |


---

<a id="cli-cloud-group-ceph"></a>
## 10. {{t:cli.docs.sectionTitles.ceph}}

{{t:cli.commands.ceph.description}}

<a id="cli-cloud-ceph-cluster"></a>
### 10.1 cluster

{{t:cli.commands.ceph.cluster.description}}

<a id="cli-cloud-ceph-cluster-list"></a>
#### list

{{t:cli.commands.ceph.cluster.list.description}}

```bash
rdc ceph cluster list
```

<a id="cli-cloud-ceph-cluster-create"></a>
#### create

{{t:cli.commands.ceph.cluster.create.description}}

```bash
rdc ceph cluster create <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--vault <content>` | {{t:cli.options.vaultContent}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-cloud-ceph-cluster-delete"></a>
#### delete

{{t:cli.commands.ceph.cluster.delete.description}}

```bash
rdc ceph cluster delete <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `-f, --force` | {{t:cli.options.force}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-cloud-ceph-cluster-machines"></a>
#### machines

{{t:cli.commands.ceph.cluster.machines.description}}

```bash
rdc ceph cluster machines <name>
```

#### vault

{{t:cli.commands.ceph.cluster.vault.description}}

<a id="cli-cloud-ceph-cluster-vault-get"></a>
**get:**

{{t:cli.commands.ceph.cluster.vault.get.description}}

```bash
rdc ceph cluster vault get <name>
```

<a id="cli-cloud-ceph-cluster-vault-update"></a>
**update:**

{{t:cli.commands.ceph.cluster.vault.update.description}}

```bash
rdc ceph cluster vault update <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--vault <content>` | {{t:cli.options.vaultContent}} | {{t:cli.docs.optionLabels.yes}} | - |


<a id="cli-cloud-ceph-pool"></a>
### 10.2 pool

{{t:cli.commands.ceph.pool.description}}

<a id="cli-cloud-ceph-pool-list"></a>
#### list

{{t:cli.commands.ceph.pool.list.description}}

```bash
rdc ceph pool list [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--team <name>` | {{t:cli.options.team}} | {{t:cli.docs.optionLabels.no}} | - |
| `--cluster <name>` | {{t:cli.options.cluster}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-cloud-ceph-pool-create"></a>
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


<a id="cli-cloud-ceph-pool-delete"></a>
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

<a id="cli-cloud-ceph-pool-vault-get"></a>
**get:**

{{t:cli.commands.ceph.pool.vault.get.description}}

```bash
rdc ceph pool vault get <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--team <name>` | {{t:cli.options.team}} | {{t:cli.docs.optionLabels.yes}} | - |


<a id="cli-cloud-ceph-pool-vault-update"></a>
**update:**

{{t:cli.commands.ceph.pool.vault.update.description}}

```bash
rdc ceph pool vault update <name> [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--team <name>` | {{t:cli.options.team}} | {{t:cli.docs.optionLabels.yes}} | - |
| `--vault <content>` | {{t:cli.options.vaultContent}} | {{t:cli.docs.optionLabels.yes}} | - |


<a id="cli-cloud-ceph-image"></a>
### 10.3 image

{{t:cli.commands.ceph.image.description}}

<a id="cli-cloud-ceph-image-list"></a>
#### list

{{t:cli.commands.ceph.image.list.description}}

```bash
rdc ceph image list [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--pool <name>` | {{t:cli.options.pool}} | {{t:cli.docs.optionLabels.no}} | - |
| `--team <name>` | {{t:cli.options.team}} | {{t:cli.docs.optionLabels.no}} | - |


<a id="cli-cloud-ceph-image-create"></a>
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


<a id="cli-cloud-ceph-image-delete"></a>
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


<a id="cli-cloud-ceph-snapshot"></a>
### 10.4 snapshot

{{t:cli.commands.ceph.snapshot.description}}

<a id="cli-cloud-ceph-snapshot-list"></a>
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


<a id="cli-cloud-ceph-snapshot-create"></a>
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


<a id="cli-cloud-ceph-snapshot-delete"></a>
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


<a id="cli-cloud-ceph-clone"></a>
### 10.5 clone

{{t:cli.commands.ceph.clone.description}}

<a id="cli-cloud-ceph-clone-list"></a>
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


<a id="cli-cloud-ceph-clone-create"></a>
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


<a id="cli-cloud-ceph-clone-delete"></a>
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


<a id="cli-cloud-ceph-clone-machines"></a>
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


<a id="cli-cloud-ceph-clone-assign"></a>
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


<a id="cli-cloud-ceph-clone-unassign"></a>
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

<a id="cli-cloud-group-audit"></a>
## 11. {{t:cli.docs.sectionTitles.audit}}

{{t:cli.commands.audit.description}}

<a id="cli-cloud-audit-list"></a>
### 11.1 list

{{t:cli.commands.audit.list.description}}

```bash
rdc audit list
```

<a id="cli-cloud-audit-log"></a>
### 11.2 log

{{t:cli.commands.audit.log.description}}

```bash
rdc audit log [options]
```

| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |
|------|-------------|----------|---------|
| `--limit <n>` | {{t:cli.options.limit}} | {{t:cli.docs.optionLabels.no}} | `100` |


<a id="cli-cloud-audit-trace"></a>
### 11.3 trace

{{t:cli.commands.audit.trace.description}}

```bash
rdc audit trace <entityType> <entityId>
```

<a id="cli-cloud-audit-history"></a>
### 11.4 history

{{t:cli.commands.audit.history.description}}

```bash
rdc audit history <entityType> <entityId>
```

---
