---
title: "Yedekleme ve Ağ"
description: "Otomatik yedekleme zamanlamalarını yapılandırın, depolama sağlayıcılarını yönetin, altyapı ağını kurun ve hizmet portlarını kaydedin."
category: "Tutorials"
order: 6
language: tr
sourceHash: "e756fef6749b54c5"
---

# Rediacc ile Yedekleme ve Ağ Nasıl Yapılandırılır

Otomatik yedeklemeler depolarınızı korur ve altyapı ağı hizmetleri dış dünyaya açar. Bu öğreticide, depolama sağlayıcıları ile yedekleme zamanlamalarını yapılandırır, TLS sertifikalarıyla genel ağ kurarsınız, hizmet portlarını kaydeder ve yapılandırmayı doğrularsınız. Tamamladığınızda makineniz üretim trafiğine hazır olacaktır.

## Ön Koşullar

- Yapılandırması başlatılmış şekilde kurulmuş `rdc` CLI
- Hazırlanmış bir makine (bkz. [Öğretici: Makine Kurulumu](/tr/docs/tutorial-setup))

## Etkileşimli Kayıt

![Tutorial: Backup & Networking](/assets/tutorials/backup-tutorial.cast)

### Adım 1: Mevcut depolamaları görüntüleyin

Depolama sağlayıcıları (S3, B2, Google Drive, vb.) yedekleme hedefleri olarak hizmet eder. Hangi sağlayıcıların yapılandırıldığını kontrol edin.

```bash
rdc config storages
```

rclone yapılandırmalarından içe aktarılmış tüm yapılandırılmış depolama sağlayıcılarını listeler. Boşsa, önce bir depolama sağlayıcı ekleyin — bkz. [Yedekleme ve Geri Yükleme](/tr/docs/backup-restore).

### Adım 2: Yedekleme zamanlamasını yapılandırın

Bir cron zamanlamasına göre çalışan otomatik yedeklemeler kurun.

```bash
rdc backup schedule set --destination my-s3 --cron "0 2 * * *" --enable
```

Bu, sabah 2'de günlük yedeklemeler zamanlar ve tüm depoları `my-s3` depolamasına gönderir. Zamanlama yapılandırmanızda saklanır ve makinelere systemd zamanlayıcı olarak dağıtılabilir.

### Adım 3: Yedekleme zamanlamasını görüntüleyin

Zamanlamanın uygulandığını doğrulayın.

```bash
rdc backup schedule show
```

Mevcut yedekleme yapılandırmasını gösterir: hedef, cron ifadesi ve etkinleştirme durumu.

### Adım 4: Altyapıyı yapılandırın

Herkese açık hizmetler için makinenin harici IP'si, temel alan adı ve Let's Encrypt TLS için bir sertifika e-postası gereklidir.

```bash
rdc config set-infra server-1 \
  --public-ipv4 203.0.113.50 \
  --base-domain example.com \
  --cert-email admin@example.com
```

Rediacc bu ayarlardan bir Traefik ters proxy yapılandırması oluşturur.

### Adım 5: TCP/UDP portları ekleyin

Hizmetleriniz HTTP dışı portlara ihtiyaç duyuyorsa (örn. SMTP, DNS), bunları Traefik giriş noktaları olarak kaydedin.

```bash
rdc config set-infra server-1 \
  --tcp-ports 25,143,465,587,993 \
  --udp-ports 53
```

Bu, Docker hizmetlerinin etiketler aracılığıyla referans verebileceği Traefik giriş noktaları (`tcp-25`, `udp-53`, vb.) oluşturur.

### Adım 6: Altyapı yapılandırmasını görüntüleyin

Tam altyapı yapılandırmasını doğrulayın.

```bash
rdc config show-infra server-1
```

Genel IP'leri, alan adını, sertifika e-postasını ve tüm kayıtlı portları görüntüler.

### Adım 7: Yedekleme zamanlamasını devre dışı bırakın

Yapılandırmayı silmeden otomatik yedeklemeleri durdurmak için:

```bash
rdc backup schedule set --disable
rdc backup schedule show
```

Yapılandırma korunur ve daha sonra `--enable` ile yeniden etkinleştirilebilir.

## Sorun Giderme

**"Invalid cron expression"**
Cron formatı `minute hour day month weekday` şeklindedir. Yaygın zamanlamalar: `0 2 * * *` (günlük saat 2), `0 */6 * * *` (her 6 saatte), `0 0 * * 0` (haftalık Pazar gece yarısı).

**"Storage destination not found"**
Hedef adı yapılandırılmış bir depolama sağlayıcısıyla eşleşmelidir. Mevcut adları görmek için `rdc config storages` çalıştırın. Yeni sağlayıcıları rclone yapılandırması aracılığıyla ekleyin.

**Dağıtım sırasında "Infrastructure config incomplete"**
Üç alanın tümü gereklidir: `--public-ipv4`, `--base-domain` ve `--cert-email`. Eksik alanları kontrol etmek için `rdc config show-infra <machine>` çalıştırın.

## Sonraki Adımlar

Otomatik yedeklemeleri yapılandırdınız, altyapı ağını kurdunuz, hizmet portlarını kaydettiniz ve yapılandırmayı doğruladınız. Yedeklemeleri yönetmek için:

- [Yedekleme ve Geri Yükleme](/tr/docs/backup-restore) — push, pull, list ve sync komutları için tam referans
- [Ağ](/tr/docs/networking) — Docker etiketleri, TLS sertifikaları, DNS ve TCP/UDP yönlendirme
- [Öğretici: Makine Kurulumu](/tr/docs/tutorial-setup) — ilk yapılandırma ve hazırlama
