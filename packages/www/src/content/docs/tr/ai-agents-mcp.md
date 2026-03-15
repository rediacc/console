---
title: MCP Sunucu Kurulumu
description: Model Context Protocol (MCP) sunucusunu kullanarak yapay zeka ajanlarını Rediacc altyapısına bağlayın.
category: Guides
order: 33
language: tr
sourceHash: "ac1ed364eb890583"
sourceCommit: "ecb32701b07b8536282aea0d26f58ef06296288b"
---

## Genel Bakış

`rdc mcp serve` komutu, yapay zeka ajanlarının altyapınızı yönetmek için kullanabileceği yerel bir MCP (Model Context Protocol) sunucusu başlatır. Sunucu stdio taşıma yöntemini kullanır — yapay zeka ajanı sunucuyu bir alt süreç olarak başlatır ve JSON-RPC üzerinden iletişim kurar.

**Ön koşullar:** `rdc` kurulu ve en az bir makine ile yapılandırılmış olmalıdır.

## Claude Code

Projenizin `.mcp.json` dosyasına ekleyin:

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

Veya adlandırılmış bir yapılandırma ile:

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

Ayarlar → MCP Sunucuları → Sunucu Ekle yolunu izleyin:

- **Ad**: `rdc`
- **Komut**: `rdc mcp serve`
- **Taşıma**: stdio

## Kullanılabilir Araçlar

### Okuma Araçları (güvenli, yan etkisi yok)

| Araç | Açıklama |
|------|----------|
| `machine_query` | Get system info, containers, services, and resource usage for a machine |
| `machine_containers` | List Docker containers with status, health, resource usage, labels, and auto-route domain |
| `machine_services` | List rediacc-managed systemd services (name, state, sub-state, restart count, memory, owning repository) |
| `machine_repos` | List deployed repositories (name, GUID, size, mount status, Docker state, container count, disk usage, modified date, Rediaccfile present) |
| `machine_health` | Run health check on a machine (system, containers, services, storage) |
| `machine_list` | List all configured machines |
| `config_repositories` | List configured repositories with name-to-GUID mappings |
| `config_show_infra` | Show infrastructure configuration for a machine (base domain, public IPs, TLS, Cloudflare zone) |
| `config_providers` | List configured cloud providers for machine provisioning |
| `agent_capabilities` | List all available rdc CLI commands with their arguments and options |

### Yazma Araçları (yıkıcı)

| Araç | Açıklama |
|------|----------|
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

## Örnek İş Akışları

**Makine durumunu kontrol etme:**
> "Üretim makinemin durumu nedir?"

Ajan `machine_query` aracını çağırır → sistem bilgisi, çalışan konteynerler, servisler ve kaynak kullanımını döndürür.

**Uygulama dağıtma:**
> "Gitlab'ı hazırlık makineme dağıt"

Ajan `repo_up` aracını `name: "gitlab"` ve `machine: "staging"` parametreleriyle çağırır → depoyu dağıtır, başarı/başarısızlık sonucunu döndürür.

**Başarısız bir servisi hata ayıklama:**
> "Nextcloud'um yavaş, sorunun ne olduğunu bul"

Ajan `machine_health` → `machine_containers` → günlükleri okumak için `term_exec` araçlarını çağırır → sorunu tespit eder ve çözüm önerir.

## Yapılandırma Seçenekleri

| Seçenek | Varsayılan | Açıklama |
|---------|------------|----------|
| `--config <name>` | (varsayılan yapılandırma) | Tüm komutlar için kullanılacak adlandırılmış yapılandırma |
| `--timeout <ms>` | `120000` | Varsayılan komut zaman aşımı (milisaniye) |
| `--allow-grand` | off | Allow destructive operations on grand (non-fork) repositories |

## Güvenlik

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

`REDIACC_ALLOW_GRAND_REPO` ortam değişkenini belirli bir repo adına ya da tüm repolar için `*` değerine de ayarlayabilirsiniz.

### Kernel-level filesystem sandbox (Landlock)

When `term_exec` runs a command on a repository, the command is wrapped with `renet sandbox-exec` on the remote machine. This applies Linux Landlock LSM restrictions at the kernel level:

- **Allowed**: the repository's own mount path, `/tmp`, system binaries (`/usr`, `/bin`, `/etc`), the repo's Docker socket
- **Blocked**: other repositories' mount paths, home directory writes, arbitrary filesystem access

This prevents lateral movement — even if an agent gains shell access to a fork, it cannot read or modify other repositories on the same machine. Machine-level SSH (without a repository) is not sandboxed.

## Mimari

MCP sunucusu durumsuz (stateless) çalışır. Her araç çağrısı, `rdc`'yi `--output json --yes --quiet` bayraklarıyla izole bir alt süreç olarak başlatır. Bu şu anlama gelir:

- Araç çağrıları arasında durum sızıntısı olmaz
- Mevcut `rdc` yapılandırmanızı ve SSH anahtarlarınızı kullanır
- Hem yerel hem de bulut adaptörleriyle çalışır
- Bir komuttaki hatalar diğerlerini etkilemez
