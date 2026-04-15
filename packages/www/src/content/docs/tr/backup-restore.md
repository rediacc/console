---
title: Yedekleme ve Geri Yükleme
description: >-
  Şifrelenmiş depoları harici depolamaya yedekleyin, yedeklerden geri yükleyin
  ve otomatik yedeklemeler planlayın.
category: Guides
order: 7
language: tr
sourceHash: "0c7ebc3efb8877c5"
sourceCommit: "8b0f83c57ebaaa0a2bee93143db34ab677b4e68b"
---

# Yedekleme ve Geri Yükleme

Rediacc, şifrelenmiş depoları harici depolama sağlayıcılarına yedekleyebilir ve aynı veya farklı makinelerde geri yükleyebilir. Yedekler şifrelenmiştir; geri yükleme için deponun LUKS kimlik bilgisi gereklidir.

## Depolamayı Yapılandırma

Yedekleri göndermeden önce bir depolama sağlayıcısı kaydedin. Rediacc, rclone uyumlu tüm depolamaları destekler: S3, B2, Google Drive ve daha fazlası.

### rclone'dan İçe Aktarma

Zaten yapılandırılmış bir rclone uzak bağlantınız varsa:

```bash
rdc config storage import --file rclone.conf
```

Bu, bir rclone yapılandırma dosyasındaki depolama yapılandırmalarını mevcut yapılandırmaya aktarır. Desteklenen türler: S3, B2, Google Drive, OneDrive, Mega, Dropbox, Box, Azure Blob ve Swift.

### Depolamaları Görüntüleme

```bash
rdc config storage list
```

## Yedek Gönderme

Bir depo yedeğini harici depolamaya gönderin:

```bash
rdc repo push --name my-app -m server-1 --to my-storage
```

Push, yazmadan önce her zaman hedef deponun bağlı olup olmadığını kontrol eder. Bağlı değilse işlem iptal edilir.

| Seçenek | Açıklama |
|---------|----------|
| `--to <storage>` | Hedef depolama konumu |
| `--to-machine <machine>` | Makineden makineye yedekleme için hedef makine |
| `--dest <filename>` | Özel hedef dosya adı |
| `--checkpoint` | Göndermeden önce CRIU checkpoint oluştur (`rediacc.checkpoint=true` etiketli konteynerler için). Hedef `repo up` ile otomatik geri yüklenir |
| `--force` | Mevcut bir yedeği geçersiz kıl |
| `--bwlimit <limit>` | rsync transferi için bant genişliği sınırı (örn. `10M`, `500K`) |
| `--tag <tag>` | Yedeği etiketle |
| `-w, --watch` | İşlem ilerlemesini izle |
| `--debug` | Ayrıntılı çıktıyı etkinleştir |
| `--skip-router-restart` | İşlem sonrası yönlendirici sunucusunun yeniden başlatılmasını atla |

## Yedek Çekme / Geri Yükleme

Harici depolamadan bir depo yedeğini çekin:

```bash
rdc repo pull --name my-app -m server-1 --from my-storage
```

Pull, yazmadan önce her zaman hedef deponun bağlı olup olmadığını kontrol eder. Bağlı değilse işlem iptal edilir.

| Seçenek | Açıklama |
|---------|----------|
| `--from <storage>` | Kaynak depolama konumu |
| `--from-machine <machine>` | Makineden makineye geri yükleme için kaynak makine |
| `--force` | Mevcut yerel yedeği geçersiz kıl |
| `--bwlimit <limit>` | rsync transferi için bant genişliği sınırı (örn. `10M`, `500K`) |
| `-w, --watch` | İşlem ilerlemesini izle |
| `--debug` | Ayrıntılı çıktıyı etkinleştir |
| `--skip-router-restart` | İşlem sonrası yönlendirici sunucusunun yeniden başlatılmasını atla |

## Yedekleri Listeleme

Bir depolama konumundaki mevcut yedekleri görüntüleyin:

```bash
rdc repo backup list --from my-storage -m server-1
```

## Toplu Senkronizasyon

Tüm depoları aynı anda gönderin veya çekin:

### Tümünü Depolamaya Gönder

```bash
rdc repo push --to my-storage -m server-1
```

### Tümünü Depolamadan Çek

```bash
rdc repo pull --from my-storage -m server-1
```

| Seçenek | Açıklama |
|---------|----------|
| `--to <storage>` | Hedef depolama (gönderme yönü) |
| `--from <storage>` | Kaynak depolama (çekme yönü) |
| `--repo <name>` | Belirli depoları senkronize et (tekrarlanabilir) |
| `--override` | Mevcut yedekleri geçersiz kıl |
| `--debug` | Ayrıntılı çıktıyı etkinleştir |
| `--skip-router-restart` | İşlem sonrası yönlendirici sunucusunun yeniden başlatılmasını atla |

## Zamanlanmış Yedeklemeler

Rediacc, adlandırılmış yedekleme stratejileri kullanır. Her strateji bir zamanlama, yedekleme modu, isteğe bağlı bant genişliği sınırı ve dosya filtreleri tanımlar. Makineler, hangi yedeklemelerin çalıştırılacağını belirlemek için stratejileri adlarıyla referans alır.

### Yedekleme Modları

| Mod | Davranış | Kesinti Süresi |
|-----|----------|----------------|
| `hot` | Servisler çalışırken BTRFS anlık görüntüsü alınır (kilitlenme tutarlı) | Yok |
| `cold` | Servisler durdurulur, anlık görüntü alınır, servisler yeniden başlatılır, anlık görüntü yüklenir (uygulama tutarlı) | Kısa |

Kilitlenme tutarlı anlık görüntülere izin veren servisler için `hot` kullanın. Garantili tutarlılığa ihtiyaç duyduğunuzda ve kısa yeniden başlatmayı kabul edebildiğinizde `cold` kullanın.

### Soğuk Yedekleme Semantiği

Soğuk yedekleme, dahil edilen her depo için üç aşamada çalışır: **durdur -- anlık görüntü -- başlat**. Garantilerin sınırlarını anlamak, operatörlerin kısmi arızaları erken tespit etmesine yardımcı olur.

**Soğuk yedeklemenin garantiledikleri:**

- Anlık görüntüden önce, dahil edilen her depodaki çalışan konteynerler Rediaccfile `down()` kancası aracılığıyla düzgün biçimde durdurulur ve depo başına Docker daemon sessiz hale getirilir. Anlık görüntü bu nedenle yalnızca kilitlenme tutarlı değil, uygulama tutarlıdır.
- Anlık görüntüden önce çalışan konteyner ID'lerinin kümesi `/var/run/rediacc/cold-backup-<guid>.running.json` adresinde bir sidecar dosyasına kaydedilir. Bu, "işimiz bittiğinde nelerin tekrar çalışıyor olması gerektiği" için gerçeğin kaynağıdır.
- Anlık görüntüden sonra, tam compose yığınını geri yüklemek için deponun Rediaccfile `up()` kancası çağrılır.
- `/var/run/rediacc/cold-backup-<guid>.status.json` adresindeki çalıştırma başına durum sidecar'ı her denemenin aşamasını, sonucunu ve hatalarını kaydeder.

**Soğuk yedeklemenin garanti ETMEDİKLERİ:**

- `up()` en iyi efors ile calısır. Soğuk yedeklemenin kontrolü dışındaki nedenlerle başarısız olabilir (`depends_on: service_healthy` koşulunun hala beklenmesi, compose dosyası sözdizimi hatası, görüntü çekerken geçici bir ağ arızası). Başarısız olduğunda, soğuk yedekleme hatayı hata seviyesinde günlüğe kaydeder, durum sidecar'ını yazar ve bir sonraki depoya geçer.
- `up()` başarısız olduğunda, **doğrudan yedek yeniden başlatma** devreye girer: çalışma sidecar'ı okunur ve kaydedilen her konteyner ID'si doğrudan Docker API aracılığıyla yeniden başlatılır (compose olmadan). Bu, Rediaccfile kancalarını yeniden çalıştırmadan compose akışında bir sorun olsa bile servisleri geri getirir.
- Bazı konteyner ID'leri için yedek de başarısız olursa (örneğin, Docker daemon'un kendisi çalışmıyorsa), sidecar **yerinde bırakılır**, böylece yönlendirici watchdog her tıkta yeniden denemeye devam edebilir.

**Watchdog kurtarma:** her tıkta watchdog, çalışma sidecar'ının varlığını kontrol eder. Orada listelenen ve şu anda durdurulmuş olan herhangi bir konteyner ID'si, *konteynerin kaydedilmiş `restart_policy`'sinden bağımsız olarak* yeniden başlatılır. Bu, `restart: on-failure` ile yapılandırılmış servislerin (Docker'ın temiz bir durdurmanın ardından yeniden başlatmayacağı) soğuk yedeklemeden sonra geri dönmesi anlamına gelir. Listelenen tüm konteynerler çalışır duruma geldiğinde sidecar silinir.

**Operatörlerin arızaları nasıl tespit edeceği:**

- `rdc machine query --name <machine> --containers` çalışma durumunu gösterir. Beklenen kümeyle karşılaştırın.
- Makinedeki `/var/run/rediacc/cold-backup-<guid>.status.json` dosyasını kontrol edin. `rdc term connect -m <machine> -r <repo> -c "cat /var/run/rediacc/cold-backup-$GUID.status.json"` ile inceleyebilirsiniz. Eski bir `startedAt` ile birlikte `success: false`, son yedeklemenin temiz tamamlanmadığı anlamına gelir.
- renet yedekleme çalıştırmasından gelen günlükler (`journalctl -u renet-*` veya doğrudan `rdc machine deploy-backup` çağrısı) `Cold backup: post-snapshot restart summary total=N compose_ok=N fallback_ok=N failed=N failed_repos=[...]` biçiminde bir son özet satırı yayar. Boş olmayan `failed_repos` grep hedefidir.

### Strateji Tanımlama

```bash
rdc config backup-strategy set \
  --name hourly-hot \
  --destination my-storage \
  --cron "0 * * * *" \
  --mode hot \
  --bwlimit 20M \
  --enable
```

```bash
rdc config backup-strategy set \
  --name nightly-cold \
  --destination my-storage \
  --cron "0 2 * * *" \
  --mode cold \
  --include "*.db" \
  --exclude "tmp/**" \
  --enable
```

| Seçenek | Açıklama |
|---------|----------|
| `--name <name>` | Strateji adı (makine bağlama için kullanılır) |
| `--destination <storage>` | Yüklenecek depolama sağlayıcısı |
| `--cron <expression>` | Cron ifadesi (örn. `"0 2 * * *"` günlük saat 02:00 için) |
| `--mode <hot\|cold>` | Yedekleme modu |
| `--bwlimit <limit>` | Yüklemeler için bant genişliği sınırı (örn. `10M`) |
| `--include <pattern>` | Dahil etme filtresi (tekrarlanabilir) |
| `--exclude <pattern>` | Hariç tutma filtresi (tekrarlanabilir) |
| `--enable` / `--disable` | Stratejiyi etkinleştir veya devre dışı bırak |

### Stratejileri Görüntüleme

```bash
rdc config backup-strategy list
rdc config backup-strategy show --name nightly-cold
```

### Strateji Kaldırma

```bash
rdc config backup-strategy remove --name nightly-cold
```

### Stratejileri Makineye Bağlama

Yapılandırmanızda bir veya daha fazla strateji adını bir makineye bağlayın:

```json
{
  "machines": {
    "hostinger": {
      "backupStrategies": ["hourly-hot", "nightly-cold"]
    }
  }
}
```

## Yedekleme İşlemleri

### Zamanlamayı Makineye Dağıtma

Bağlı stratejileri bir makineye systemd zamanlayıcıları olarak gönderin:

```bash
rdc machine backup schedule -m server-1
rdc machine backup schedule -m server-1 --dry-run
```

`--dry-run` oluşturulan systemd birim dosyalarını dağıtmadan yazdırır. rclone token'ları dry-run çıktısında maskelenir.

### Şimdi Yedekleme Çalıştırma

Zamanlayıcıyı beklemeden hemen yedekleme başlatın. `systemd-run` kullanarak geçici yürütme ile zamanlayıcı dağıtılmamış olsa bile çalışır:

```bash
rdc machine backup now -m server-1
rdc machine backup now -m server-1 --strategy nightly-cold
```

### Yedekleme Durumunu Görüntüleme

Yedekleme zamanlayıcılarının mevcut durumunu ve son iş sonuçlarını gösterir:

```bash
rdc machine backup status -m server-1
rdc machine backup status -m server-1 --strategy hourly-hot
```

### Çalışan Yedeklemeyi İptal Etme

```bash
rdc machine backup cancel -m server-1
rdc machine backup cancel -m server-1 --strategy nightly-cold
```

## Depo Migrasyonu

Bir depoyu bir makineden diğerine taşıyın:

```bash
rdc repo migrate --name my-app --from server-1 --to server-2
```

| Seçenek | Açıklama |
|---------|----------|
| `--name <repo>` | Migrasyon yapılacak depo |
| `--from <machine>` | Kaynak makine |
| `--to <machine>` | Hedef makine |
| `--provision` | Aktarımdan önce hedefte depoyu hazırla |
| `--checkpoint` | Migrasyondan önce CRIU checkpoint oluştur |
| `--skip-dns` | Migrasyondan sonra DNS kaydı güncellemeyi atla |
| `--bwlimit <limit>` | Transfer için bant genişliği sınırı (örn. `50M`) |

Migrasyon, şifrelenmiş depo verilerini rsync aracılığıyla aktarır. Kaynak depo, siz açıkça kaldırana kadar bozulmadan kalır.

## Depolamayı Tarama

Bir depolama konumunun içeriğini tarayın:

```bash
rdc storage browse --name my-storage
```

## En İyi Uygulamalar

- Kritik veriler için uygulama tutarlı anlık görüntüler almak amacıyla günlük soğuk yedeklemeler zamanlayın
- Sıfır kesinti gerektiren yüksek frekanslı anlık görüntüler için sıcak yedeklemeleri kullanın
- Yedek bütünlüğünü doğrulamak için geri yüklemeleri periyodik olarak test edin
- Kritik veriler için birden fazla depolama sağlayıcısı kullanın (örn. S3 + B2)
- Kimlik bilgilerini güvende tutun; yedekler şifrelenmiştir ancak geri yükleme için LUKS kimlik bilgisi gereklidir
