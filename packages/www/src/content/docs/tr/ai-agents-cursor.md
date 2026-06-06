---
title: Cursor Kurulum Kılavuzu
description: Cursor IDE'yi .cursorrules ve terminal entegrasyonu kullanarak Rediacc altyapısıyla çalışacak şekilde yapılandırın.
category: Guides
order: 32
language: tr
sourceHash: "b5e835461de00400"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

Kısaca: `.cursorrules` dosyası Rediacc bağlamını Cursor'ın yapay zekasına yükler; terminal ise gerçek makinelerinize karşı `rdc` komutları çalıştırmasını sağlar.

## Hızlı Kurulum

1. CLI'yi yükleyin: `curl -fsSL https://www.rediacc.com/install.sh | bash`
2. [AGENTS.md şablonunu](/tr/docs/agents-md-template) proje kök dizininize `.cursorrules` olarak kopyalayın
3. Projeyi Cursor'da açın

Cursor başlangıçta `.cursorrules` dosyasını okur. Şunu göz önünde bulundurun: bağlam penceresi sınırları geçerlidir, bu nedenle dosyayı genel şablonlarla doldurmak yerine gerçek makinelerinize ve repolarınıza odaklanmış tutun.

## .cursorrules Yapılandırması

Proje kök dizininizde Rediacc altyapı bağlamıyla `.cursorrules` dosyasını oluşturun. Tam sürüm için [AGENTS.md şablonuna](/tr/docs/agents-md-template) bakın.

Dahil edilmesi gereken temel bölümler:

- CLI aracı adı (`rdc`) ve kurulumu
- `--output json` bayrağıyla yaygın komutlar
- Mimari genel bakış (depo izolasyonu, Docker daemon'ları)
- Terminoloji kuralları (adaptörler, modlar değil)

## Terminal Entegrasyonu

Cursor, entegre terminali aracılığıyla `rdc` komutlarını çalıştırabilir. Yaygın kalıplar:

### Durum Kontrolü

Cursor'a sorun: *"Üretim sunucumun durumunu kontrol et"*

Cursor terminalde çalıştırır:
```bash
rdc machine query --name prod-1 -o json
```

### Değişiklikleri Dağıtma

Cursor'a sorun: *"Güncellenmiş nextcloud yapılandırmasını dağıt"*

Cursor terminalde çalıştırır:
```bash
rdc repo up --name nextcloud -m prod-1 --yes
```

### Günlükleri Görüntüleme

Cursor'a sorun: *"Bana son mail konteyner günlüklerini göster"*

Cursor terminalde çalıştırır:
```bash
rdc term connect -m prod-1 -r mail -c "docker logs mail-postfix --tail 100"
```

## Çalışma Alanı Ayarları

Takım projeleri için, Rediacc'a özel Cursor ayarlarını `.cursor/settings.json` dosyasına ekleyin:

```json
{
  "terminal.defaultProfile": "bash",
  "ai.customInstructions": "Use rdc CLI for all infrastructure operations. Always use --output json when parsing results."
}
```

## İpuçları

- Cursor'ın Composer modu, çok adımlı altyapı görevleri için iyi çalışır
- Terminal çıktısına referans vermek için Cursor sohbetinde `@terminal` kullanın
- `rdc agent capabilities` komutu, Cursor'a eksiksiz bir komut referansı sunar
- AI araçları arasında maksimum uyumluluk için `.cursorrules` dosyasını `CLAUDE.md` dosyasıyla birleştirin
