---
title: "Aplicación CLI"
description: "Guía completa para usar la interfaz de línea de comandos de Rediacc para la gestión de la plataforma"
category: "Conceptos Básicos"
order: 2
language: es
generated: true
generatedFrom: packages/cli/src/i18n/locales/es/cli.json
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
rdc auth login
```

```
? Email: admin@example.com
? Password: ********
✓ Login successful! Saved to context "default"
```

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
rdc auth register
```

### 1.5 activate

{{t:cli.commands.auth.activate.description}}

```bash
rdc auth activate
```

```bash
rdc auth activate -e user@example.com -p yourpassword --code ABC123
```

### 1.6 tfa

{{t:cli.commands.auth.tfa.description}}

#### disable

{{t:cli.commands.auth.tfa.disable.description}}

```bash
rdc auth tfa disable
```

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
rdc auth token fork
```

#### list

{{t:cli.commands.auth.token.list.description}}

```bash
rdc auth token list
```

#### revoke

{{t:cli.commands.auth.token.revoke.description}}

```bash
rdc auth token revoke
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
rdc context create
```

### 2.5 delete

{{t:cli.commands.context.delete.description}}

```bash
rdc context delete
```

### 2.6 rename

{{t:cli.commands.context.rename.description}}

```bash
rdc context rename
```

### 2.7 current

{{t:cli.commands.context.current.description}}

```bash
rdc context current
```

### 2.8 set

{{t:cli.commands.context.set.description}}

```bash
rdc context set
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
rdc context clear
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
rdc context create-local
```

### 2.13 add-machine

{{t:cli.commands.context.addMachine.description}}

```bash
rdc context add-machine
```

### 2.14 remove-machine

{{t:cli.commands.context.removeMachine.description}}

```bash
rdc context remove-machine
```

### 2.15 machines

{{t:cli.commands.context.machines.description}}

```bash
rdc context machines
```

### 2.16 set-ssh

{{t:cli.commands.context.setSsh.description}}

```bash
rdc context set-ssh
```

### 2.17 set-renet

{{t:cli.commands.context.setRenet.description}}

```bash
rdc context set-renet
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
rdc organization vault update
```

### 3.5 export

{{t:cli.commands.organization.export.description}}

```bash
rdc organization export
```

### 3.6 import

{{t:cli.commands.organization.import.description}}

```bash
rdc organization import
```

### 3.7 maintenance

{{t:cli.commands.organization.maintenance.description}}

```bash
rdc organization maintenance
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
rdc user create
```

### 4.3 activate

{{t:cli.commands.user.activate.description}}

```bash
rdc user activate
```

### 4.4 deactivate

{{t:cli.commands.user.deactivate.description}}

```bash
rdc user deactivate
```

### 4.5 reactivate

{{t:cli.commands.user.reactivate.description}}

```bash
rdc user reactivate
```

### 4.6 update-email

{{t:cli.commands.user.updateEmail.description}}

```bash
rdc user update-email
```

### 4.7 update-password

{{t:cli.commands.user.updatePassword.description}}

```bash
rdc user update-password
```

### 4.8 update-language

{{t:cli.commands.user.updateLanguage.description}}

```bash
rdc user update-language
```

### 4.9 exists

{{t:cli.commands.user.exists.description}}

```bash
rdc user exists
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
rdc user vault update
```

### 4.11 permission

{{t:cli.commands.user.permission.description}}

#### assign

{{t:cli.commands.user.permission.assign.description}}

```bash
rdc user permission assign
```

---

## 5. {{t:cli.docs.sectionTitles.team}}

{{t:cli.commands.team.description}}

### 5.1 list

{{t:cli.commands.team.list.description}}

```bash
rdc team list
```

### 5.2 create

{{t:cli.commands.team.create.description}}

```bash
rdc team create
```

### 5.3 member

{{t:cli.commands.team.member.description}}

#### list

{{t:cli.commands.team.member.list.description}}

```bash
rdc team member list
```

#### add

{{t:cli.commands.team.member.add.description}}

```bash
rdc team member add
```

#### remove

{{t:cli.commands.team.member.remove.description}}

```bash
rdc team member remove
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
rdc permission group create
```

#### delete

{{t:cli.commands.permission.group.delete.description}}

```bash
rdc permission group delete
```

#### show

{{t:cli.commands.permission.group.show.description}}

```bash
rdc permission group show
```

### 6.3 add

{{t:cli.commands.permission.add.description}}

```bash
rdc permission add
```

### 6.4 remove

{{t:cli.commands.permission.remove.description}}

```bash
rdc permission remove
```

---

## 7. {{t:cli.docs.sectionTitles.region}}

{{t:cli.commands.region.description}}

### 7.1 list

{{t:cli.commands.region.list.description}}

```bash
rdc region list
```

---

## 8. {{t:cli.docs.sectionTitles.bridge}}

{{t:cli.commands.bridge.description}}

### 8.1 list

{{t:cli.commands.bridge.list.description}}

```bash
rdc bridge list
```

### 8.2 reset-auth

{{t:cli.commands.bridge.resetAuth.description}}

```bash
rdc bridge reset-auth
```

---

## 9. {{t:cli.docs.sectionTitles.machine}}

{{t:cli.commands.machine.description}}

### 9.1 list

{{t:cli.commands.machine.list.description}}

```bash
rdc machine list
```

### 9.2 create

{{t:cli.commands.machine.create.description}}

```bash
rdc machine create
```

### 9.3 delete

{{t:cli.commands.machine.delete.description}}

```bash
rdc machine delete
```

### 9.4 update

{{t:cli.commands.machine.update.description}}

```bash
rdc machine update
```

### 9.5 health

{{t:cli.commands.machine.health.description}}

{{t:cli.docs.supplements.machine.health.afterDescription}}

```bash
rdc machine health
```

### 9.6 containers

{{t:cli.commands.machine.containers.description}}

```bash
rdc machine containers
```

### 9.7 services

{{t:cli.commands.machine.services.description}}

```bash
rdc machine services
```

### 9.8 vault-status

{{t:cli.commands.machine.vaultStatus.description}}

```bash
rdc machine vault-status
```

### 9.9 repos

{{t:cli.commands.machine.repos.description}}

```bash
rdc machine repos
```

### 9.10 test-connection

{{t:cli.commands.machine.testConnection.description}}

```bash
rdc machine test-connection
```

> **{{t:cli.docs.admonitions.tip}}**: {{t:cli.docs.supplements.machine.testConnection.tip}}

---

## 10. {{t:cli.docs.sectionTitles.repository}}

{{t:cli.commands.repository.description}}

### 10.1 list

{{t:cli.commands.repository.list.description}}

```bash
rdc repository list
```

### 10.2 create

{{t:cli.commands.repository.create.description}}

```bash
rdc repository create
```

### 10.3 rename

{{t:cli.commands.repository.rename.description}}

```bash
rdc repository rename
```

### 10.4 delete

{{t:cli.commands.repository.delete.description}}

```bash
rdc repository delete
```

### 10.5 promote

{{t:cli.commands.repository.promote.description}}

```bash
rdc repository promote
```

> **{{t:cli.docs.admonitions.note}}**: {{t:cli.docs.supplements.repository.promote.note}}

### 10.6 vault

{{t:cli.commands.repository.vault.description}}

#### get

{{t:cli.commands.repository.vault.get.description}}

```bash
rdc repository vault get
```

#### update

{{t:cli.commands.repository.vault.update.description}}

```bash
rdc repository vault update
```

---

## 11. {{t:cli.docs.sectionTitles.storage}}

{{t:cli.commands.storage.description}}

### 11.1 list

{{t:cli.commands.storage.list.description}}

```bash
rdc storage list
```

---

## 12. {{t:cli.docs.sectionTitles.queue}}

{{t:cli.commands.queue.description}}

{{t:cli.docs.supplements.queue.afterDescription}}

### 12.1 list

{{t:cli.commands.queue.list.description}}

```bash
rdc queue list
```

### 12.2 create

{{t:cli.commands.queue.create.description}}

```bash
rdc queue create
```

### 12.3 cancel

{{t:cli.commands.queue.cancel.description}}

```bash
rdc queue cancel
```

### 12.4 retry

{{t:cli.commands.queue.retry.description}}

```bash
rdc queue retry
```

### 12.5 trace

{{t:cli.commands.queue.trace.description}}

```bash
rdc queue trace
```

> **{{t:cli.docs.admonitions.tip}}**: {{t:cli.docs.supplements.queue.trace.tip}}

### 12.6 delete

{{t:cli.commands.queue.delete.description}}

```bash
rdc queue delete
```

---

## 13. {{t:cli.docs.sectionTitles.sync}}

{{t:cli.commands.sync.description}}

### 13.1 upload

{{t:cli.commands.sync.upload.description}}

```bash
rdc sync upload
```

### 13.2 download

{{t:cli.commands.sync.download.description}}

```bash
rdc sync download
```

### 13.3 status

{{t:cli.commands.sync.status.description}}

```bash
rdc sync status
```

---

## 14. {{t:cli.docs.sectionTitles.vscode}}

{{t:cli.commands.vscode.description}}

### 14.1 connect

{{t:cli.commands.vscode.connect.description}}

```bash
rdc vscode connect
```

### 14.2 list

{{t:cli.commands.vscode.list.description}}

```bash
rdc vscode list
```

### 14.3 cleanup

{{t:cli.commands.vscode.cleanup.description}}

```bash
rdc vscode cleanup
```

### 14.4 check

{{t:cli.commands.vscode.check.description}}

```bash
rdc vscode check
```

---

## 15. {{t:cli.docs.sectionTitles.term}}

{{t:cli.commands.term.description}}

### 15.1 connect

{{t:cli.commands.term.connect.description}}

```bash
rdc term connect
```

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
rdc ceph cluster create
```

#### delete

{{t:cli.commands.ceph.cluster.delete.description}}

```bash
rdc ceph cluster delete
```

#### machines

{{t:cli.commands.ceph.cluster.machines.description}}

```bash
rdc ceph cluster machines
```

#### vault

{{t:cli.commands.ceph.cluster.vault.description}}

**get:**

{{t:cli.commands.ceph.cluster.vault.get.description}}

```bash
rdc ceph cluster vault get
```

**update:**

{{t:cli.commands.ceph.cluster.vault.update.description}}

```bash
rdc ceph cluster vault update
```

### 16.2 pool

{{t:cli.commands.ceph.pool.description}}

#### list

{{t:cli.commands.ceph.pool.list.description}}

```bash
rdc ceph pool list
```

#### create

{{t:cli.commands.ceph.pool.create.description}}

```bash
rdc ceph pool create
```

#### delete

{{t:cli.commands.ceph.pool.delete.description}}

```bash
rdc ceph pool delete
```

#### vault

{{t:cli.commands.ceph.pool.vault.description}}

**get:**

{{t:cli.commands.ceph.pool.vault.get.description}}

```bash
rdc ceph pool vault get
```

**update:**

{{t:cli.commands.ceph.pool.vault.update.description}}

```bash
rdc ceph pool vault update
```

### 16.3 image

{{t:cli.commands.ceph.image.description}}

#### list

{{t:cli.commands.ceph.image.list.description}}

```bash
rdc ceph image list
```

#### create

{{t:cli.commands.ceph.image.create.description}}

```bash
rdc ceph image create
```

#### delete

{{t:cli.commands.ceph.image.delete.description}}

```bash
rdc ceph image delete
```

### 16.4 snapshot

{{t:cli.commands.ceph.snapshot.description}}

#### list

{{t:cli.commands.ceph.snapshot.list.description}}

```bash
rdc ceph snapshot list
```

#### create

{{t:cli.commands.ceph.snapshot.create.description}}

```bash
rdc ceph snapshot create
```

#### delete

{{t:cli.commands.ceph.snapshot.delete.description}}

```bash
rdc ceph snapshot delete
```

### 16.5 clone

{{t:cli.commands.ceph.clone.description}}

#### list

{{t:cli.commands.ceph.clone.list.description}}

```bash
rdc ceph clone list
```

#### create

{{t:cli.commands.ceph.clone.create.description}}

```bash
rdc ceph clone create
```

#### delete

{{t:cli.commands.ceph.clone.delete.description}}

```bash
rdc ceph clone delete
```

#### machines

{{t:cli.commands.ceph.clone.machines.description}}

```bash
rdc ceph clone machines
```

#### assign

{{t:cli.commands.ceph.clone.assign.description}}

```bash
rdc ceph clone assign
```

#### unassign

{{t:cli.commands.ceph.clone.unassign.description}}

```bash
rdc ceph clone unassign
```

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
rdc audit log
```

### 17.3 trace

{{t:cli.commands.audit.trace.description}}

```bash
rdc audit trace
```

### 17.4 history

{{t:cli.commands.audit.history.description}}

```bash
rdc audit history
```

---

## 18. {{t:cli.docs.sectionTitles.protocol}}

{{t:cli.commands.protocol.description}}

### 18.1 register

{{t:cli.commands.protocol.register.description}}

```bash
rdc protocol register
```

### 18.2 unregister

{{t:cli.commands.protocol.unregister.description}}

```bash
rdc protocol unregister
```

### 18.3 status

{{t:cli.commands.protocol.status.description}}

```bash
rdc protocol status
```

### 18.4 open

{{t:cli.commands.protocol.open.description}}

```bash
rdc protocol open
```

### 18.5 build

{{t:cli.commands.protocol.build.description}}

```bash
rdc protocol build
```

### 18.6 parse

{{t:cli.commands.protocol.parse.description}}

```bash
rdc protocol parse
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
