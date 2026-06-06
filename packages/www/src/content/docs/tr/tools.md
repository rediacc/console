---
title: Araçlar
description: >-
  Dosya senkronizasyonu, terminal erişimi, VS Code entegrasyonu ve CLI
  güncellemeleri.
category: Guides
order: 9
language: tr
sourceHash: "4b3aebff5e82416f"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# Araçlar

Rediacc, makinelerinizde ve depolarınızda günlük çalışma için dört araç sunar: SSH üzerinden dosya senkronizasyonu, bir SSH terminali, VS Code entegrasyonu ve CLI otomatik güncellemeleri. Dördü de SSH üzerinde çalışır. Uzak taraf için hiçbir ajan veya daemon gerekli değildir. Bunların herhangi biri için bir GUI arıyorsanız, yanlış sayfaya bakmaktasınız.

## Dosya Senkronizasyonu (sync)

SSH üzerinden rsync kullanarak iş istasyonunuz ile uzak depo arasında dosya aktarımı yapın.

### Dosya Yükleme

`--local` bir veya daha fazla yolu kabul eder. Her yol bir dosya veya dizin olabilir. Dosyalar `<remote>/<basename>` konumuna indirilir; dizin içeriği `<remote>/` konumuna birleştirilir. Tek bir dosya için dosyaya açıkça hedef yolunu vermek üzere `--remote-file` tercih edin.

```bash
# Dizin (içeriği uzak konuma birleştirilir)
rdc repo sync upload -m server-1 -r my-app --local ./src --remote /app/src

# Tek dosya, uzak dizine bırakılır (temel ad korunur)
rdc repo sync upload -m server-1 -r my-app --local ./config.yml --remote /app/conf

# Tek dosya, açık hedef yolu
rdc repo sync upload -m server-1 -r my-app --local ./config.yml --remote-file /app/conf/config.yml

# Bir çağrıda birden fazla kaynak
rdc repo sync upload -m server-1 -r my-app --local a.yml b.yml ./assets --remote /app
```

`--remote` ve `--remote-file` karşılıklı olarak dışlayıcıdır. `--remote-file` tamamen bir dosyaya işaret eden bir `--local` yolu gerektirir.

`--mirror` bir dosya kaynağıyla birleştirilemez; uzak dizindeki eşdüzey dosyaları silecektir.

### Dosya İndirme

Bir dizin için `--remote` (varsayılan) veya tek bir dosya için `--remote-file` kullanın. İki bayrak karşılıklı olarak dışlayıcıdır.

```bash
# Dizin
rdc repo sync download -m server-1 -r my-app --remote /app/data --local ./data

# Tek dosya — `--local` mevcut bir dizin olmalıdır
rdc repo sync download -m server-1 -r my-app --remote-file /app/conf/config.yml --local ./local-conf
```

### Senkronizasyon Durumunu Kontrol Etme

```bash
rdc repo sync status -m server-1 -r my-app
```

### Seçenekler

| Seçenek | Açıklama |
|---------|----------|
| `-m, --machine <name>` | Hedef makine |
| `-r, --repository <name>` | Hedef depo |
| `--local <paths...>` | Bir veya daha fazla yerel dosya/dizin yolu (yükleme) ya da yerel hedef dizin (indirme) |
| `--remote <path>` | Uzak dizin (depo bağlama noktasına göre) |
| `--remote-file <path>` | Tek dosya yüklemeleri veya indirmeleri için uzak dosya yolu (`--remote` yerine) |
| `--dry-run` | Aktarım yapmadan değişiklikleri önizle |
| `--mirror` | Kaynağı hedefe yansıt, fazla dosyaları sil (yalnızca dizin kaynakları) |
| `--verify` | Aktarım sonrası sağlama toplamlarını doğrula |
| `--confirm` | Ayrıntılı görünümle etkileşimli onay |
| `--exclude <patterns...>` | Dosya desenlerini hariç tut |
| `--skip-router-restart` | İşlem sonrası yönlendirme sunucusunu yeniden başlatmayı atla |

## SSH Terminali (term)

Bir makineye veya depo ortamına etkileşimli SSH oturumu açın.

### Kısa Sözdizimi

Bağlanmanın en hızlı yolu:

```bash
rdc term connect -m server-1                    # Bir makineye bağlan
rdc term connect -m server-1 -r my-app             # Bir depoya bağlan
```

### Komut Çalıştırma

Etkileşimli oturum açmadan bir komut çalıştırın:

```bash
rdc term connect -m server-1 -c "uptime"
rdc term connect -m server-1 -r my-app -c "docker ps"
```

Bir depoya bağlanırken, `DOCKER_HOST` otomatik olarak deponun izole Docker soketine ayarlanır, böylece `docker ps` yalnızca o deponun konteynerlerini gösterir.

### Connect Alt Komutu

Veya aynı sonuç için açık bayraklarla `connect` alt komutunu kullanın:

```bash
rdc term connect -m server-1
rdc term connect -m server-1 -r my-app
```

### Konteyner İşlemleri

Çalışan bir konteynerle doğrudan etkileşim kurun:

```bash
# Konteyner içinde kabuk aç
rdc term connect -m server-1 -r my-app --container <container-id>

# Konteyner günlüklerini görüntüle
rdc term connect -m server-1 -r my-app --container <container-id> --container-action logs

# Günlükleri gerçek zamanlı takip et
rdc term connect -m server-1 -r my-app --container <container-id> --container-action logs --follow

# Konteyner istatistiklerini görüntüle
rdc term connect -m server-1 -r my-app --container <container-id> --container-action stats

# Konteynerde komut çalıştır
rdc term connect -m server-1 -r my-app --container <container-id> --container-action exec -c "ls -la"
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
rdc vscode connect -r my-app -m server-1
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
rdc vscode cleanup
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
rdc update --rollback
```

Önceden yüklenmiş sürüme geri döner. Yalnızca bir güncelleme uygulandıktan sonra kullanılabilir.

### Güncelleme Durumu

```bash
rdc update --status
```

Mevcut sürümü, güncelleme kanalını ve otomatik güncelleme yapılandırmasını gösterir.

#### Yayın Kanalları

```bash
rdc update --channel edge      # Sürekli dağıtılan üretim güncellemeleri
rdc update --channel stable    # Edge'den 7 gün sonra tercih edilen (varsayılan)
rdc update --status            # Mevcut kanal ve sürüm bilgisini göster
```
