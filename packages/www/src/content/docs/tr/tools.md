---
title: Araçlar
description: >-
  Dosya senkronizasyonu, terminal erişimi, VS Code entegrasyonu ve CLI
  güncellemeleri.
category: Guides
order: 9
language: tr
sourceHash: "2b8afb656455d6ec"
sourceCommit: "3fb35b9a33c7e8ec6753ecd56231f2018e8f4803"
---

# Araçlar

Rediacc, makinelerinizde ve depolarınızda günlük çalışma için dört araç sunar: SSH üzerinden dosya senkronizasyonu, bir SSH terminali, VS Code entegrasyonu ve CLI otomatik güncellemeleri. Dördü de SSH üzerinde çalışır. Uzak taraf için hiçbir ajan veya daemon gerekli değildir. Bunların herhangi biri için bir GUI arıyorsanız, yanlış sayfaya bakmaktasınız.

## Dosya Senkronizasyonu (sync)

SSH üzerinden rsync kullanarak iş istasyonunuz ile uzak depo arasında dosya aktarımı yapın.

### Dosya Yükleme

`--local` bir veya daha fazla yolu kabul eder. Her yol bir dosya veya dizin olabilir. Dosyalar `<remote>/<basename>` konumuna indirilir; dizin içeriği `<remote>/` konumuna birleştirilir. Tek bir dosya için dosyaya açıkça hedef yolunu vermek üzere `--remote-file` tercih edin.

```bash
# Dizin (içeriği uzak konuma birleştirilir)
rdc repo sync upload my-app --local ./src --remote /app/src

# Tek dosya, uzak dizine bırakılır (temel ad korunur)
rdc repo sync upload my-app --local ./config.yml --remote /app/conf

# Tek dosya, açık hedef yolu
rdc repo sync upload my-app --local ./config.yml --remote-file /app/conf/config.yml

# Bir çağrıda birden fazla kaynak
rdc repo sync upload my-app --local a.yml b.yml ./assets --remote /app
```

`--remote` ve `--remote-file` karşılıklı olarak dışlayıcıdır. `--remote-file` tamamen bir dosyaya işaret eden bir `--local` yolu gerektirir.

`--mirror` bir dosya kaynağıyla birleştirilemez; uzak dizindeki eşdüzey dosyaları silecektir.

### Dosya İndirme

Bir dizin için `--remote` (varsayılan) veya tek bir dosya için `--remote-file` kullanın. İki bayrak karşılıklı olarak dışlayıcıdır.

```bash
# Dizin
rdc repo sync download my-app --remote /app/data --local ./data

# Tek dosya: `--local` mevcut bir dizin olmalıdır
rdc repo sync download my-app --remote-file /app/conf/config.yml --local ./local-conf
```

### Senkronizasyon Durumunu Kontrol Etme

```bash
rdc repo sync status my-app
```

### Seçenekler

| Seçenek | Açıklama |
|---------|----------|
| `-m, --machine <name>` | Hedef makine |
| `<ref>` (konumsal) | Hedef depo referansı: `name`, `name:tag`, isteğe bağlı olarak `@machine` |
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
rdc term connect server-1                    # Bir makineye bağlan
rdc term connect my-app             # Bir depoya bağlan
```

### Komut Çalıştırma

Etkileşimli oturum açmadan bir komut çalıştırın:

```bash
rdc term connect server-1 -c "uptime"
rdc term connect my-app -c "docker ps"
```

Bir depoya bağlanırken, `DOCKER_HOST` otomatik olarak deponun izole Docker soketine ayarlanır, böylece `docker ps` yalnızca o deponun konteynerlerini gösterir.

### Connect Alt Komutu

Veya aynı sonuç için açık bayraklarla `connect` alt komutunu kullanın:

```bash
rdc term connect server-1
rdc term connect my-app
```

### Konteyner İşlemleri

Çalışan bir konteynerle doğrudan etkileşim kurun:

```bash
# Konteyner içinde kabuk aç
rdc repo exec my-app -c <container> -i -- bash

# Konteyner günlüklerini görüntüle
rdc repo logs my-app -c <container>

# Günlükleri gerçek zamanlı takip et
rdc repo logs my-app -c <container> --follow

# Konteyner istatistiklerini görüntüle
rdc repo exec my-app -c <container> -i -- bash --container-action stats

# Konteynerde komut çalıştır
rdc repo exec my-app -c <container> -- ls -la
```

| Seçenek | Komut | Açıklama |
|---------|-------|----------|
| `-c, --container <name>` | ikisi de | Depo içindeki hedef konteyner |
| `--lines <n>` | `repo logs` | Gösterilecek günlük satırı sayısı |
| `-f, --follow` | `repo logs` | Günlükleri sürekli takip et |
| `--timestamps` | `repo logs` | Her satırın başına zaman damgası ekle |
| `-i, --interactive` | `repo exec` | stdin'i açık tut (kabuk için gerekli) |
| `-u, --user <user>` | `repo exec` | Belirli bir kullanıcı olarak çalıştır |

## VS Code Entegrasyonu (vscode)

Doğru SSH ayarlarıyla önceden yapılandırılmış bir uzak SSH oturumunu VS Code'da açın.

### Depoya Bağlanma

```bash
rdc vscode connect my-app
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

### Tarayıcıda VS Code

Yerel VS Code yok mu? Editörü depo sandbox'ının içinden sunun ve herhangi bir tarayıcıda açın:

```bash
rdc vscode connect my-app --browser
```

Bu komut:
1. Makineye açık kaynak editör sunucusunu bir kez kurar (salt okunur paylaşımlı yol, sağlama toplamı doğrulanmış)
2. Depo sandbox'ının içinde başlatır; dosya ağacı, entegre terminal ve tüm alt süreçler tam olarak deponun gördüğünü görür
3. Yerel bir porta SSH tüneli açar ve oturum başına token URL'si ile tarayıcınızı başlatır

Siz tüneli kapattıktan sonra sunucu çalışmaya devam eder; yeniden bağlanırken mevcut sunucu kullanılır. Yönetmek için:

```bash
rdc vscode serve status my-app
rdc vscode serve stop my-app
```

| Seçenek | Açıklama |
|---------|----------|
| `--no-open` | Tarayıcıyı açmak yerine URL'yi yazdır |
| `--url-only` | stdout'a tam olarak bir URL satırı yaz (scripting için) ve tüneli tut |
| `--local <port>` | Yerel tünel portunu seçin |
| `--server-provider <id>` | Editör sunucu uygulaması: `openvscode` (varsayılan) veya `code-server` |
| `--server-archive <file>` | Makinede önceden hazırlanmış bir tarball'dan kur (internet bağlantısı gerekmez) |

Linux, macOS, Windows veya tabletten çalışır. Yerel tek gereksinim bir tarayıcıdır.

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
