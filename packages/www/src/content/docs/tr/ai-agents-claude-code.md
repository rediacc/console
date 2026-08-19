---
title: Claude Code Kurulum Kılavuzu
description: >-
  Claude Code'u otonom Rediacc altyapı yönetimi için yapılandırmanın adım adım
  kılavuzu.
category: Guides
tags:
  - ai-agents
  - cli
order: 31
language: tr
sourceHash: "2c925f7e46d63e9a"
sourceCommit: "23543669cd22bce3f14d69a0886bac8a12061412"
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
- Status: rdc machine status <machine> -o json
- Deploy: rdc repo up <repo>@<machine> --yes
- Containers: rdc machine status <machine> --containers -o json
- Health: rdc machine health <machine> -o json
- SSH: rdc term connect <machine> [repo]

### Rules
- Always use --output json when parsing output
- Always use --yes for automated confirmations
- Use --dry-run before destructive operations
```

## Araç İzinleri

Claude Code, `rdc` komutlarını çalıştırmak için izin isteyecektir. Claude Code ayarlarınıza ekleyerek yaygın işlemleri önceden yetkilendirebilirsiniz:

- `rdc machine status *` izni verin, salt okunur durum kontrolleri
- `rdc machine status * --containers` izni verin, konteyner listeleme
- `rdc machine health *` izni verin, sağlık kontrolleri
- `rdc repo list` izni verin, depo listeleme

Yıkıcı işlemler (`rdc repo up`, `rdc repo delete`) için, açıkça yetkilendirmediğiniz sürece Claude Code her zaman onay isteyecektir.

## Örnek İş Akışları

### Altyapı Durumunu Kontrol Etme

```
You: "What's the status of prod-1?"

Claude Code runs: rdc machine status prod-1 -o json
→ Shows machine status, repositories, containers, services
```

### Depo Dağıtımı

```
You: "Deploy the mail repo to prod-1"

Claude Code runs: rdc repo up mail@prod-1 --dry-run -o json
→ Shows what would happen
Claude Code runs: rdc repo up mail@prod-1 --yes
→ Deploys the repository
```

### Konteyner Sorunlarını Teşhis Etme

```
You: "Why is the nextcloud container unhealthy?"

Claude Code runs: rdc machine status prod-1 --containers -o json --fields name,status,repository
→ Lists container states
Claude Code runs: rdc term prod-1 -c "docker logs nextcloud-app --tail 50"
→ Checks recent logs
```

### Dosya Senkronizasyonu

```
You: "Upload the local config to the mail repo"

Claude Code runs: rdc repo sync upload mail@prod-1 --local ./config --dry-run
→ Shows files that would be synced
Claude Code runs: rdc repo sync upload mail@prod-1 --local ./config
→ Syncs the files
```

## İpuçları

- Claude Code TTY olmayan ortamı otomatik algılar ve JSON çıktısına geçer, çoğu durumda `-o json` belirtmenize gerek yoktur
- Claude Code'un tüm mevcut komutları keşfetmesi için `rdc --help-all` kullanın
- `--fields` bayrağı, yalnızca belirli verilere ihtiyaç duyduğunuzda bağlam penceresi kullanımını düşük tutmaya yardımcı olur
