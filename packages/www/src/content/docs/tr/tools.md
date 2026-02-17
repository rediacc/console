---
title: "Araçlar"
description: "Dosya senkronizasyonu, terminal erisimi, VS Code entegrasyonu, guncellemeler ve tanilamalar."
category: "Getting Started"
order: 4
language: tr
---

# Araçlar

Rediacc, uzak depolarla çalışmak için çeşitli üretkenlik araçları içerir. Bu araçlar, bağlam yapılandırmanız tarafından kurulan SSH bağlantısı üzerine inşa edilmiştir.

## Dosya Senkronizasyonu (sync)

rsync over SSH kullanarak iş istasyonunuz ile uzak depo arasında dosya aktarımı yapın.

### Dosya Yükleme

```bash
rdc sync upload my-app -m server-1 --local ./src --remote /app/src
```

### Dosya İndirme

```bash
rdc sync download my-app -m server-1 --remote /app/data --local ./data
```

### Seçenekler

| Seçenek | Açıklama |
|---------|----------|
| `-m, --machine <name>` | Hedef makine |
| `--local <path>` | Yerel dizin yolu |
| `--remote <path>` | Uzak yol (depo bağlama noktasına göre) |
| `--dry-run` | Aktarım yapmadan değişiklikleri önizle |
| `--delete` | Kaynakta bulunmayan dosyaları hedefte sil |

`--dry-run` bayrağı, senkronizasyona başlamadan önce nelerin aktarılacağını önizlemek için kullanışlıdır.

## SSH Terminali (term)

Bir makineye veya doğrudan bir deponun bağlama yoluna etkileşimli SSH oturumu açın.

### Makineye Bağlanma

```bash
rdc term connect server-1
```

### Depoya Bağlanma

```bash
rdc term connect my-app -m server-1
```

Bir depoya bağlanırken, terminal oturumu deponun bağlama dizininde ve deponun Docker soketi yapılandırılmış olarak başlar.

## VS Code Entegrasyonu (vscode)

Doğru SSH ayarları ve Remote SSH uzantısı ile önceden yapılandırılmış olarak VS Code'da uzak SSH oturumu açın.

### Depoya Bağlanma

```bash
rdc vscode connect my-app -m server-1
```

Bu komut:
1. VS Code kurulumunuzu algılar
2. SSH bağlantısını `~/.ssh/config` dosyasında yapılandırır
3. Oturum için SSH anahtarını kalıcı hale getirir
4. VS Code'u depo yoluna Remote SSH bağlantısıyla açar

### Yapılandırılmış Bağlantıları Listeleme

```bash
rdc vscode list
```

VS Code için yapılandırılmış tüm SSH bağlantılarını gösterir.

### Bağlantıları Temizleme

```bash
rdc vscode clean
```

Artık gerekli olmayan VS Code SSH yapılandırmalarını kaldırır.

> **Ön koşul:** VS Code'da [Remote - SSH](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-ssh) uzantısını kurun.

## CLI Güncellemeleri (update)

`rdc` CLI'ı en son özellikler ve hata düzeltmeleriyle güncel tutun.

### Güncellemeleri Kontrol Etme

```bash
rdc update --check-only
```

### Güncelleme Uygulama

```bash
rdc update
```

Güncellemeler indirilir ve yerinde uygulanır. Yeni sürüm bir sonraki çalıştırmada etkinleşir.

### Geri Alma

```bash
rdc update rollback
```

Önceden kurulu olan sürüme geri döner. Yalnızca bir güncelleme uygulandıktan sonra kullanılabilir.

### Otomatik Güncelleme Durumu

```bash
rdc update status
```

Mevcut sürümü, güncelleme kanalını ve otomatik güncelleme yapılandırmasını gösterir.

## Sistem Tanılamaları (doctor)

Rediacc ortamınızın kapsamlı bir tanılama kontrolünü çalıştırın.

```bash
rdc doctor
```

doctor komutu şunları kontrol eder:

| Kategori | Kontroller |
|----------|------------|
| **Ortam** | Node.js sürümü, CLI sürümü, SEA modu |
| **Renet** | İkili dosya varlığı, sürüm, gömülü CRIU ve rsync |
| **Yapılandırma** | Aktif bağlam, mod, makineler, SSH anahtarı |
| **Kimlik Doğrulama** | Oturum durumu |

Her kontrol, kısa bir açıklamayla birlikte **Tamam**, **Uyarı** veya **Hata** durumu bildirir. Herhangi bir sorunu giderirken ilk adım olarak bunu kullanın.
