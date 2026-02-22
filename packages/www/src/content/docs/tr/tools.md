---
title: Araçlar
description: >-
  Dosya senkronizasyonu, terminal erişimi, VS Code entegrasyonu, güncellemeler
  ve tanılamalar.
category: Guides
order: 8
language: tr
sourceHash: 80ca3cd3e1a55d4b
---

# Araçlar

Rediacc, uzak depolarla çalışmak için üretkenlik araçları içerir: dosya senkronizasyonu, SSH terminali, VS Code entegrasyonu ve CLI güncellemeleri.

## Dosya Senkronizasyonu (sync)

SSH üzerinden rsync kullanarak iş istasyonunuz ile uzak depo arasında dosya aktarımı yapın.

### Dosya Yükleme

```bash
rdc sync upload -m server-1 -r my-app --local ./src --remote /app/src
```

### Dosya İndirme

```bash
rdc sync download -m server-1 -r my-app --remote /app/data --local ./data
```

### Senkronizasyon Durumunu Kontrol Etme

```bash
rdc sync status -m server-1 -r my-app
```

### Seçenekler

| Seçenek | Açıklama |
|---------|----------|
| `-m, --machine <name>` | Hedef makine |
| `-r, --repository <name>` | Hedef depo |
| `--local <path>` | Yerel dizin yolu |
| `--remote <path>` | Uzak yol (depo bağlama noktasına göre) |
| `--dry-run` | Aktarım yapmadan değişiklikleri önizle |
| `--mirror` | Kaynağı hedefe yansıt (fazla dosyaları sil) |
| `--verify` | Aktarım sonrası sağlama toplamlarını doğrula |
| `--confirm` | Ayrıntılı görünümle etkileşimli onay |
| `--exclude <patterns...>` | Dosya desenlerini hariç tut |
| `--skip-router-restart` | İşlem sonrası yönlendirme sunucusunu yeniden başlatmayı atla |

## SSH Terminali (term)

Bir makineye veya depo ortamına etkileşimli SSH oturumu açın.

### Kısa Sözdizimi

Bağlanmanın en hızlı yolu:

```bash
rdc term server-1                    # Bir makineye bağlan
rdc term server-1 my-app             # Bir depoya bağlan
```

### Komut Çalıştırma

Etkileşimli oturum açmadan bir komut çalıştırın:

```bash
rdc term server-1 -c "uptime"
rdc term server-1 my-app -c "docker ps"
```

Bir depoya bağlanırken, `DOCKER_HOST` otomatik olarak deponun izole Docker soketine ayarlanır, böylece `docker ps` yalnızca o deponun konteynerlerini gösterir.

### Connect Alt Komutu

`connect` alt komutu, açık bayraklarla aynı işlevselliği sağlar:

```bash
rdc term connect -m server-1
rdc term connect -m server-1 -r my-app
```

### Konteyner İşlemleri

Çalışan bir konteynerle doğrudan etkileşim kurun:

```bash
# Konteyner içinde kabuk aç
rdc term server-1 my-app --container <container-id>

# Konteyner günlüklerini görüntüle
rdc term server-1 my-app --container <container-id> --container-action logs

# Günlükleri gerçek zamanlı takip et
rdc term server-1 my-app --container <container-id> --container-action logs --follow

# Konteyner istatistiklerini görüntüle
rdc term server-1 my-app --container <container-id> --container-action stats

# Konteynerde komut çalıştır
rdc term server-1 my-app --container <container-id> --container-action exec -c "ls -la"
```

| Seçenek | Açıklama |
|---------|----------|
| `--container <id>` | Hedef Docker konteyner kimliği |
| `--container-action <action>` | İşlem: `terminal` (varsayılan), `logs`, `stats`, `exec` |
| `--log-lines <n>` | Gösterilecek günlük satır sayısı (varsayılan: 50) |
| `--follow` | Günlükleri sürekli takip et |
| `--external` | Satır içi SSH yerine harici terminal kullan |

## VS Code Entegrasyonu (vscode)

Doğru SSH ayarlarıyla önceden yapılandırılmış bir uzak SSH oturumunu VS Code'da açın.

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

### Bağlantıları Temizleme

```bash
rdc vscode clean
```

Artık gerekli olmayan VS Code SSH yapılandırmalarını kaldırır.

### Yapılandırmayı Kontrol Etme

```bash
rdc vscode check
```

VS Code kurulumunu, Remote SSH eklentisini ve etkin bağlantıları doğrular.

> **Ön koşul:** VS Code'da [Remote - SSH](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-ssh) eklentisini kurun.

## CLI Güncellemeleri (update)

`rdc` CLI'ını güncel tutun.

### Güncellemeleri Kontrol Etme

```bash
rdc update --check-only
```

### Güncellemeyi Uygulama

```bash
rdc update
```

Güncellemeler indirilir ve yerinde uygulanır. CLI, platformunuz (Linux, macOS veya Windows) için doğru ikili dosyayı otomatik olarak seçer. Yeni sürüm bir sonraki çalıştırmada etkin olur.

### Geri Alma

```bash
rdc update rollback
```

Önceden yüklenmiş sürüme geri döner. Yalnızca bir güncelleme uygulandıktan sonra kullanılabilir.

### Güncelleme Durumu

```bash
rdc update status
```

Mevcut sürümü, güncelleme kanalını ve otomatik güncelleme yapılandırmasını gösterir.
