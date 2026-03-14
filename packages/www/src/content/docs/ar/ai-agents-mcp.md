---
title: إعداد خادم MCP
description: ربط وكلاء الذكاء الاصطناعي بالبنية التحتية لـ Rediacc باستخدام خادم Model Context Protocol (MCP).
category: Guides
order: 33
language: ar
sourceHash: "51c5a7f855ead072"
sourceCommit: "ecb32701b07b8536282aea0d26f58ef06296288b"
---

## نظرة عامة

يقوم أمر `rdc mcp serve` بتشغيل خادم MCP (Model Context Protocol) محلي يمكن لوكلاء الذكاء الاصطناعي استخدامه لإدارة البنية التحتية الخاصة بك. يستخدم الخادم نقل stdio — يقوم وكيل الذكاء الاصطناعي بتشغيله كعملية فرعية ويتواصل عبر JSON-RPC.

**المتطلبات الأساسية:** تثبيت `rdc` وتكوينه مع جهاز واحد على الأقل.

## Claude Code

أضف إلى ملف `.mcp.json` الخاص بمشروعك:

```json
{
  "mcpServers": {
    "rdc": {
      "command": "rdc",
      "args": ["mcp", "serve"]
    }
  }
}
```

أو مع تكوين مُسمّى:

```json
{
  "mcpServers": {
    "rdc": {
      "command": "rdc",
      "args": ["mcp", "serve", "--config", "production"]
    }
  }
}
```

## Cursor

افتح الإعدادات → خوادم MCP → إضافة خادم:

- **الاسم**: `rdc`
- **الأمر**: `rdc mcp serve`
- **النقل**: stdio

## الأدوات المتاحة

### أدوات القراءة (آمنة، بدون آثار جانبية)

| الأداة | الوصف |
|------|-------------|
| `machine_info` | Get system info, containers, services, and resource usage for a machine |
| `machine_containers` | List Docker containers with status, health, resource usage, labels, and auto-route domain |
| `machine_services` | List rediacc-managed systemd services (name, state, sub-state, restart count, memory, owning repository) |
| `machine_repos` | List deployed repositories (name, GUID, size, mount status, Docker state, container count, disk usage, modified date, Rediaccfile present) |
| `machine_health` | Run health check on a machine (system, containers, services, storage) |
| `machine_list` | List all configured machines |
| `config_repositories` | List configured repositories with name-to-GUID mappings |
| `config_show_infra` | Show infrastructure configuration for a machine (base domain, public IPs, TLS, Cloudflare zone) |
| `config_providers` | List configured cloud providers for machine provisioning |
| `agent_capabilities` | List all available rdc CLI commands with their arguments and options |

### أدوات الكتابة (تدميرية)

| الأداة | الوصف |
|------|-------------|
| `repo_create` | Create a new encrypted repository on a machine |
| `repo_up` | Deploy/update a repository (runs Rediaccfile up, starts containers). Use `mount` for first deploy or after pull |
| `repo_down` | Stop repository containers. Does NOT unmount by default. Use `unmount` to also close the LUKS container |
| `repo_delete` | Delete a repository (destroys containers, volumes, encrypted image). Credential archived for recovery |
| `repo_fork` | Create a CoW fork with new GUID and networkId (fully independent copy, online forking supported) |
| `backup_push` | Push repository backup to storage or another machine (same GUID -- backup/migration, not fork) |
| `backup_pull` | Pull repository backup from storage or machine. After pull, deploy with `repo_up` (mount=true) |
| `machine_provision` | Provision a new machine on a cloud provider using OpenTofu |
| `machine_deprovision` | Destroy a cloud-provisioned machine and remove from config |
| `config_add_provider` | Add a cloud provider configuration for machine provisioning |
| `config_remove_provider` | Remove a cloud provider configuration |
| `term_exec` | Execute a command on a remote machine via SSH |

## أمثلة على سير العمل

**التحقق من حالة الجهاز:**
> "ما حالة جهاز الإنتاج الخاص بي؟"

يستدعي الوكيل `machine_info` ← يُرجع معلومات النظام والحاويات العاملة والخدمات واستخدام الموارد.

**نشر تطبيق:**
> "انشر gitlab على جهاز الاختبار الخاص بي"

يستدعي الوكيل `repo_up` مع `name: "gitlab"` و `machine: "staging"` ← ينشر المستودع ويُرجع النجاح/الفشل.

**تصحيح خدمة معطلة:**
> "خدمة nextcloud بطيئة، اكتشف ما المشكلة"

يستدعي الوكيل `machine_health` ← `machine_containers` ← `term_exec` لقراءة السجلات ← يحدد المشكلة ويقترح حلاً.

## خيارات التكوين

| الخيار | الافتراضي | الوصف |
|--------|---------|-------------|
| `--config <name>` | (التكوين الافتراضي) | التكوين المُسمّى لاستخدامه في جميع الأوامر |
| `--timeout <ms>` | `120000` | مهلة الأمر الافتراضية بالمللي ثانية |
| `--allow-grand` | off | Allow destructive operations on grand (non-fork) repositories |

## الأمان

The MCP server enforces two layers of protection:

### Fork-only mode (default)

By default, the server runs in **fork-only mode** — write tools (`repo_up`, `repo_down`, `repo_delete`, `backup_push`, `backup_pull`, `term_exec`) can only operate on fork repositories. Grand (original) repositories are protected from agent modifications.

To allow an agent to modify grand repos, start with `--allow-grand`:

```json
{
  "mcpServers": {
    "rdc": {
      "command": "rdc",
      "args": ["mcp", "serve", "--allow-grand"]
    }
  }
}
```

يمكنك أيضا ضبط متغير البيئة `REDIACC_ALLOW_GRAND_REPO` على اسم مستودع محدد أو على `*` لجميع المستودعات.

### Kernel-level filesystem sandbox (Landlock)

When `term_exec` runs a command on a repository, the command is wrapped with `renet sandbox-exec` on the remote machine. This applies Linux Landlock LSM restrictions at the kernel level:

- **Allowed**: the repository's own mount path, `/tmp`, system binaries (`/usr`, `/bin`, `/etc`), the repo's Docker socket
- **Blocked**: other repositories' mount paths, home directory writes, arbitrary filesystem access

This prevents lateral movement — even if an agent gains shell access to a fork, it cannot read or modify other repositories on the same machine. Machine-level SSH (without a repository) is not sandboxed.

## البنية المعمارية

خادم MCP عديم الحالة. كل استدعاء أداة يُشغّل `rdc` كعملية فرعية معزولة مع علامات `--output json --yes --quiet`. هذا يعني:

- لا تسرب للحالة بين استدعاءات الأدوات
- يستخدم تكوين `rdc` الحالي ومفاتيح SSH الخاصة بك
- يعمل مع كل من المحول المحلي والسحابي
- الأخطاء في أمر واحد لا تؤثر على الأوامر الأخرى
