---
title: Claude Code Kurulum Kılavuzu
description: Claude Code'u otonom Rediacc altyapı yönetimi için yapılandırmanın adım adım kılavuzu.
category: Guides
order: 31
language: tr
---

Claude Code, `rdc` CLI aracılığıyla Rediacc ile doğal olarak çalışır. Bu kılavuz kurulumu, izinleri ve yaygın iş akışlarını kapsar.

## Hızlı Kurulum

1. CLI'yi yükleyin: `curl -fsSL https://www.rediacc.com/install.sh | bash`
2. [AGENTS.md şablonunu](/tr/docs/agents-md-template) proje kök dizininize `CLAUDE.md` olarak kopyalayın
3. Claude Code'u proje dizininde başlatın

Claude Code başlangıçta `CLAUDE.md` dosyasını okur ve tüm etkileşimler için kalıcı bağlam olarak kullanır.

## CLAUDE.md Yapılandırması

Bunu proje kök dizininize yerleştirin. Tam sürüm için [AGENTS.md şablonuna](/tr/docs/agents-md-template) bakın. Temel bölümler:

```markdown
# Rediacc Infrastructure

## CLI Tool: rdc

### Common Operations
- Status: rdc machine info <machine> -o json
- Deploy: rdc repo up <repo> -m <machine> --yes
- Containers: rdc machine containers <machine> -o json
- Health: rdc machine health <machine> -o json
- SSH: rdc term <machine> [repo]

### Rules
- Always use --output json when parsing output
- Always use --yes for automated confirmations
- Use --dry-run before destructive operations
```

## Araç İzinleri

Claude Code, `rdc` komutlarını çalıştırmak için izin isteyecektir. Claude Code ayarlarınıza ekleyerek yaygın işlemleri önceden yetkilendirebilirsiniz:

- `rdc machine info *` izni verin — salt okunur durum kontrolleri
- `rdc machine containers *` izni verin — konteyner listeleme
- `rdc machine health *` izni verin — sağlık kontrolleri
- `rdc config repositories` izni verin — depo listeleme

Yıkıcı işlemler (`rdc repo up`, `rdc repo delete`) için, açıkça yetkilendirmediğiniz sürece Claude Code her zaman onay isteyecektir.

## Örnek İş Akışları

### Altyapı Durumunu Kontrol Etme

```
You: "What's the status of prod-1?"

Claude Code runs: rdc machine info prod-1 -o json
→ Shows machine status, repositories, containers, services
```

### Depo Dağıtımı

```
You: "Deploy the mail repo to prod-1"

Claude Code runs: rdc repo up mail -m prod-1 --dry-run -o json
→ Shows what would happen
Claude Code runs: rdc repo up mail -m prod-1 --yes
→ Deploys the repository
```

### Konteyner Sorunlarını Teşhis Etme

```
You: "Why is the nextcloud container unhealthy?"

Claude Code runs: rdc machine containers prod-1 -o json --fields name,status,repository
→ Lists container states
Claude Code runs: rdc term prod-1 -c "docker logs nextcloud-app --tail 50"
→ Checks recent logs
```

### Dosya Senkronizasyonu

```
You: "Upload the local config to the mail repo"

Claude Code runs: rdc sync upload -m prod-1 -r mail -l ./config --dry-run
→ Shows files that would be synced
Claude Code runs: rdc sync upload -m prod-1 -r mail -l ./config
→ Syncs the files
```

## İpuçları

- Claude Code TTY olmayan ortamı otomatik algılar ve JSON çıktısına geçer — çoğu durumda `-o json` belirtmenize gerek yoktur
- Claude Code'un tüm mevcut komutları keşfetmesi için `rdc agent capabilities` kullanın
- Ayrıntılı argüman/seçenek bilgisi için `rdc agent schema "komut adı"` kullanın
- `--fields` bayrağı, yalnızca belirli verilere ihtiyaç duyduğunuzda bağlam penceresi kullanımını düşük tutmaya yardımcı olur
