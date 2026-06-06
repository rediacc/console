---
title: AI Ajan Entegrasyonuna Genel Bakış
description: "Claude Code, Cursor ve Cline'ın rdc aracılığıyla Rediacc altyapısını nasıl yönettiği: JSON çıktısı, ajan iç gözlemi ve güvenlik koruyucuları."
category: Guides
order: 30
language: tr
sourceHash: "0aa0c975030d4856"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

Açıkçası, `rdc` tasarım gereği ajan bilinçlidir. Claude Code, Cursor, Cline: bir alt kabukta `rdc` çağıran herhangi bir AI asistanı yapılandırılmış JSON çıktısı, makine tarafından okunabilir hatalar ve otonom Rediacc altyapı yönetimi için isteyeceğiniz güvenlik koruyucularını elde eder. Entegrasyonun nasıl çalıştığına bakalım.

## Neden Self-Hosted + AI Ajanları

Rediacc'ın mimarisi ajanlar için oldukça uygun çalışır:

- **CLI öncelikli**: Her işlem bir `rdc` komutudur, GUI gerekmez
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

Dosyayı yerleştirin; ajan tahmin etmek zorunda kalmadan çalışabilmek için ihtiyaç duyduğu tam komut referansına, mimari bağlama ve kurallara sahip olur.

### 2. JSON Çıktı Hattı

Ajanlar `rdc`'yi bir alt kabukta çağırdığında, çıktı otomatik olarak JSON'a geçer (TTY olmayan algılama). Her JSON yanıtı tutarlı bir zarf kullanır:

```json
{
  "success": true,
  "command": "machine query",
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
    "guidance": "Verify the resource name with \"rdc machine query\" or \"rdc config repository list\""
  }]
}
```

### 3. Ajan Yetenekleri Keşfi

`rdc agent` alt komutu yapılandırılmış iç gözlem sağlar:

```bash
# List all commands with arguments and options
rdc agent capabilities

# Show detailed schema for a specific command
rdc agent schema --command "machine query"

# Execute a command with JSON stdin
echo '{"name": "prod-1"}' | rdc agent exec "machine query"
```

## Ajanlar İçin Temel Bayraklar

| Bayrak | Amaç |
|------|---------|
| `--output json` / `-o json` | Makine tarafından okunabilir JSON çıktısı |
| `--yes` / `-y` | Etkileşimli onayları atla |
| `--quiet` / `-q` | Bilgilendirici stderr çıktısını bastır |
| `--fields name,status` | Çıktıyı belirli alanlarla sınırla |
| `--dry-run` | Yıkıcı işlemleri çalıştırmadan önizle |

## Güvenlik ve Koruyucular

CLI, ajanları terminaldeki bir kullanıcıyla aynı şekilde ele almaz. Hassas işlemlerin gerçekleştirilebilmesi için mevcut durumu önceden bildiğinizin kanıtlanması gerekir (`--current` bayrağı), etkileşimli editör akışları varsayılan olarak reddedilir ve her red işlemi denetim günlüğüne kaydedilir. [AI Ajan Güvenliği ve Koruyucular](/tr/docs/ai-agents-safety) referansı tam güvenlik duvarı tablosunu, bilgi geçidi modelini, `REDIACC_ALLOW_CONFIG_EDIT` kapsam geçersiz kılma özelliğini ve karma zincirli denetim günlüğünü kapsar.

## Sonraki Adımlar

- [AI Ajan Güvenliği ve Koruyucular](/tr/docs/ai-agents-safety), Ajanların yapabilecekleri ve yapamayacakları, bilgi geçidi, denetim günlüğü
- [Claude Code Kurulum Kılavuzu](/tr/docs/ai-agents-claude-code), Adım adım Claude Code yapılandırması
- [Cursor Kurulum Kılavuzu](/tr/docs/ai-agents-cursor), Cursor IDE entegrasyonu
- [JSON Çıktı Referansı](/tr/docs/ai-agents-json-output), Eksiksiz JSON çıktı belgeleri
- [AGENTS.md Şablonu](/tr/docs/agents-md-template), Kopyala-yapıştır ajan yapılandırma şablonu
