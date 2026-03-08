---
title: MCP Sunucu Kurulumu
description: Model Context Protocol (MCP) sunucusunu kullanarak yapay zeka ajanlarını Rediacc altyapısına bağlayın.
category: Guides
order: 33
language: tr
sourceHash: "1b6cd5ba5d8d0ffe"
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
| `machine_info` | Sistem bilgisi, konteynerler, servisler ve kaynak kullanımını gösterir |
| `machine_containers` | Bir makinede çalışan Docker konteynerlerini listeler |
| `machine_services` | Bir makinedeki systemd servislerini listeler |
| `machine_repos` | Bir makinedeki dağıtılmış depoları listeler |
| `machine_health` | Sağlık kontrolü çalıştırır (sistem, konteynerler, servisler, depolama) |
| `config_repositories` | Yapılandırılmış depoları ad-GUID eşlemeleriyle listeler |
| `agent_capabilities` | Kullanılabilir tüm rdc CLI komutlarını listeler |

### Yazma Araçları (yıkıcı)

| Araç | Açıklama |
|------|----------|
| `repo_up` | Bir makineye depo dağıtır/günceller |
| `repo_down` | Bir makinedeki depoyu durdurur |
| `term_exec` | SSH üzerinden uzak makinede komut çalıştırır |

## Örnek İş Akışları

**Makine durumunu kontrol etme:**
> "Üretim makinemin durumu nedir?"

Ajan `machine_info` aracını çağırır → sistem bilgisi, çalışan konteynerler, servisler ve kaynak kullanımını döndürür.

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

## Mimari

MCP sunucusu durumsuz (stateless) çalışır. Her araç çağrısı, `rdc`'yi `--output json --yes --quiet` bayraklarıyla izole bir alt süreç olarak başlatır. Bu şu anlama gelir:

- Araç çağrıları arasında durum sızıntısı olmaz
- Mevcut `rdc` yapılandırmanızı ve SSH anahtarlarınızı kullanır
- Hem yerel hem de bulut adaptörleriyle çalışır
- Bir komuttaki hatalar diğerlerini etkilemez
