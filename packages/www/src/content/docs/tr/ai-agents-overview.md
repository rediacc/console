---
title: AI Ajan Entegrasyonuna Genel Bakış
description: Claude Code, Cursor ve Cline gibi AI kodlama asistanlarının otonom dağıtım ve yönetim için Rediacc altyapısıyla nasıl entegre olduğu.
category: Guides
order: 30
language: tr
sourceHash: "3374e0f154375ffb"
---

AI kodlama asistanları, `rdc` CLI aracılığıyla Rediacc altyapısını otonom olarak yönetebilir. Bu kılavuz entegrasyon yaklaşımlarını ve nasıl başlayacağınızı kapsar.

## Neden Self-Hosted + AI Ajanları

Rediacc'ın mimarisi doğal olarak ajan dostudur:

- **CLI öncelikli**: Her işlem bir `rdc` komutudur — GUI gerekmez
- **SSH tabanlı**: Ajanların eğitim verilerinden en iyi bildiği protokol
- **JSON çıktı**: Tüm komutlar tutarlı bir zarfla `--output json` destekler
- **Docker izolasyonu**: Her depo kendi daemon'ına ve ağ ad alanına sahiptir
- **Betiklenebilir**: `--yes` onayları atlar, `--dry-run` yıkıcı işlemleri önizler

## Entegrasyon Yaklaşımları

### 1. AGENTS.md / CLAUDE.md Şablonu

Başlamanın en hızlı yolu. [AGENTS.md şablonumuzu](/tr/docs/agents-md-template) proje kök dizininize kopyalayın:

- Claude Code için `CLAUDE.md`
- Cursor için `.cursorrules`
- Windsurf için `.windsurfrules`

Bu, ajana mevcut komutlar, mimari ve kurallar hakkında tam bağlam sağlar.

### 2. JSON Çıktı Hattı

Ajanlar `rdc`'yi bir alt kabukta çağırdığında, çıktı otomatik olarak JSON'a geçer (TTY olmayan algılama). Her JSON yanıtı tutarlı bir zarf kullanır:

```json
{
  "success": true,
  "command": "machine info",
  "data": { ... },
  "errors": null,
  "warnings": [],
  "metrics": { "duration_ms": 42 }
}
```

Hata yanıtları `retryable` ve `guidance` alanlarını içerir:

```json
{
  "success": false,
  "errors": [{
    "code": "NOT_FOUND",
    "message": "Machine \"prod-2\" not found",
    "retryable": false,
    "guidance": "Verify the resource name with \"rdc machine info\" or \"rdc config repositories\""
  }]
}
```

### 3. Ajan Yetenekleri Keşfi

`rdc agent` alt komutu yapılandırılmış iç gözlem sağlar:

```bash
# List all commands with arguments and options
rdc agent capabilities

# Show detailed schema for a specific command
rdc agent schema "machine info"

# Execute a command with JSON stdin
echo '{"name": "prod-1"}' | rdc agent exec "machine info"
```

## Ajanlar İçin Temel Bayraklar

| Bayrak | Amaç |
|------|---------|
| `--output json` / `-o json` | Makine tarafından okunabilir JSON çıktısı |
| `--yes` / `-y` | Etkileşimli onayları atla |
| `--quiet` / `-q` | Bilgilendirici stderr çıktısını bastır |
| `--fields name,status` | Çıktıyı belirli alanlarla sınırla |
| `--dry-run` | Yıkıcı işlemleri çalıştırmadan önizle |

## Sonraki Adımlar

- [Claude Code Kurulum Kılavuzu](/tr/docs/ai-agents-claude-code) — Adım adım Claude Code yapılandırması
- [Cursor Kurulum Kılavuzu](/tr/docs/ai-agents-cursor) — Cursor IDE entegrasyonu
- [JSON Çıktı Referansı](/tr/docs/ai-agents-json-output) — Eksiksiz JSON çıktı belgeleri
- [AGENTS.md Şablonu](/tr/docs/agents-md-template) — Kopyala-yapıştır ajan yapılandırma şablonu
