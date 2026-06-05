---
title: "Otomatik Başlatma ve Kurtarma"
description: "Otomatik başlatmanın nasıl çalıştığı, önyükleme sonrası duran depoları kurtaran periyodik uzlaştırıcı ve kurtarma durumunun nasıl inceleneceği."
category: "Guides"
order: 5
language: tr
sourceHash: "00a1796a0b0d20da"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# Otomatik Başlatma ve Kurtarma

Otomatik başlatma etkin olan depolar önyükleme sırasında kendiliğinden başlar. Bunlardan biri daha sonra kapanırsa, periyodik uzlaştırıcı onu geri getirir. Hiçbir bildirim. El ile yeniden başlatma yok.

Bir depo için otomatik başlatmayı etkinleştirme veya devre dışı bırakma hakkında bilgi için bkz. [Servisler: Önyükleme Sırasında Otomatik Başlatma](/tr/docs/services#önyükleme-sırasında-otomatik-başlatma).

## Otomatik Başlatma Nasıl Çalışır

Bir depo için otomatik başlatmayı etkinleştirdiğinizde, Rediacc 256 baytlık rastgele bir LUKS anahtar dosyası oluşturur ve bunu şifreli birimdeki LUKS slot 1'e ekler. Anahtar dosyası şu konumda saklanır:

```
{datastore}/.credentials/keys/{guid}.key
```

Bu, makinenin parola sorulmadan depoyu bağlamasına olanak tanır. LUKS slot 0 (parolanız) değiştirilmez.

Önyükleme sırasında, `rediacc-autostart.service` adlı tek seferlik bir systemd servisi otomatik başlatmanın etkin olduğu depoların listesini okur, her birini anahtar dosyasını kullanarak bağlar, depo başına Docker daemon'ını başlatır ve Rediaccfile `up()` kancasını çalıştırır. Kapatma sırasında servis `down()` kancasını çalıştırır, Docker'ı durdurur ve LUKS birimlerini kapatır.

> **Güvenlik notu:** Anahtar dosyası, parola olmadan depoya root düzeyinde erişim sağlar. Sunucuya root erişimi olan herhangi biri otomatik başlatmanın etkin olduğu depoları bağlayabilir. Hassas depolarda otomatik başlatmayı etkinleştirmeden önce bunu kendi tehdit modelinize göre değerlendirin.

## Kurtarma Açığı

Önyükleme otomatik başlatması her önyükleme için tam olarak bir kez çalışır. Sonrasında sürekli çalışan yönlendirici watchdog yalnızca *çalışan bir Docker daemon'una sahip, zaten çalışan bir depodaki konteynerleri* yeniden başlatır. Bir LUKS birimini yeniden bağlayamaz veya durmuş bir ağ başına Docker daemon'unu yeniden başlatamaz.

Bu, bir deponun LUKS birimi sunucu önyüklendikten sonra ayrılırsa veya Docker daemon'u durursa, ne önyükleme servisinin ne de watchdog'un onu kurtaramayacağı anlamına gelir. Uzlaştırıcı var olmadan önce, bu durumdaki bir depo bir operatör müdahale edene kadar kapalı kalırdı.

## Periyodik Uzlaştırıcı

`rediacc-autostart-reconcile.timer` systemd zamanlayıcısı yaklaşık her 3 dakikada bir tetiklenir ve `renet repository reconcile` komutunu çalıştırır. Otomatik başlatmanın etkin olduğu her depo için uzlaştırıcı üç şeyi kontrol eder:

1. LUKS birimi bağlı mı?
2. Ağ başına Docker daemon'u çalışıyor mu?
3. Deponun servisleri ayakta mı?

Herhangi bir kontrol başarısız olursa, uzlaştırıcı depoyu anahtar dosyasını kullanarak kurtarır: birimi bağlar, Docker daemon'unu başlatır ve `up()` kancasını çalıştırır. Parola gerekmez.

Sağlıklı olan, şu anda soğuk yedekleme tarafından kullanılan veya geri çekilme penceresinde olan depolar atlanır.

### Geri Çekilme ve Kalıcı Başarısızlık İşaretçileri

Kurtarılmayı başaramayan bir depo, her döngüde hemen yeniden denemez. Uzlaştırıcı üstel geri çekilme kullanır:

| Başarısızlık sayısı | Sonraki denemeden önceki bekleme |
|---------------------|----------------------------------|
| 1 | 1 dakika |
| 2 | 2 dakika |
| 3 | 5 dakika |
| 4 | 15 dakika |
| 5+ | 30 dakika, ardından 60 dakika |

5 ardışık başarısızlıktan sonra, uzlaştırıcı şu konumda kalıcı bir işaretçi dosyası yazar:

```
/var/lib/rediacc/reconcile/failed/{guid}
```

Bu dosya, günlük rotasyonundan sağ çıkar. Varlığı, deponun operatör müdahalesi gerektirdiği anlamına gelir. Uzlaştırıcı başarısızlığı error seviyesinde kaydeder ve işaretçi silinene kadar o depo için otomatik kurtarma girişimlerini durdurur.

Kalıcı kurtarma başarısızlığının yaygın nedenleri:

- **Güvenilmez veya süresi dolmuş depo lisansı**: lisans kontrolü `up()` işlevinden önce çalışır.
- **Eksik anahtar dosyası**: `{datastore}/.credentials/keys/{guid}.key` konumundaki anahtar dosyası silinmişse, uzlaştırıcı parola olmadan birimi bağlayamaz.
- **Bozuk Rediaccfile**: sözdizimi hatası veya her zaman sıfır dışı kodla çıkan bir `up()` kancası.

### Yönlendirici Watchdog ile İlişki

Uzlaştırıcı ve yönlendirici watchdog farklı başarısızlık düzeylerini ele alır ve birbirini tamamlamak üzere tasarlanmıştır:

| Katman | Ne ile ilgilenir |
|--------|-----------------|
| **Yönlendirici watchdog** | Çalışan, bağlı ve aktif Docker daemon'una sahip bir depodaki konteyner düzeyinde yeniden başlatmalar |
| **Uzlaştırıcı (`rediacc-autostart-reconcile.timer`)** | Depo düzeyinde kurtarma: LUKS'u yeniden bağlama, Docker daemon'unu yeniden başlatma, `up()` kancasını yeniden çalıştırma |

Sağlıklı bir depodaki tek bir konteyner çökerse, watchdog bununla ilgilenir. Tüm depo daemon'u durursa, uzlaştırıcı bununla ilgilenir.

## Kurtarma Durumunu İnceleme

### Zamanlayıcı ve servis durumu

```bash
systemctl status rediacc-autostart-reconcile.timer
systemctl list-timers rediacc-autostart-reconcile.timer
```

### Uzlaştırıcı günlükleri

```bash
journalctl -u rediacc-autostart-reconcile.service
journalctl -u rediacc-autostart-reconcile.service --since "1 hour ago"
```

### Kalıcı başarısızlık işaretçileri

Kalıcı başarısızlık işaretçisi olan depoları listeleyin:

```bash
ls /var/lib/rediacc/reconcile/failed/
```

Her dosya adı bir depo GUID'idir. GUID'leri depo adlarıyla eşleştirmek için `rdc config repository list` komutunu kullanın.

Temel sorunu çözdükten sonra işaretçiyi temizlemek için dosyayı silin:

```bash
rm /var/lib/rediacc/reconcile/failed/{guid}
```

Uzlaştırıcı, bir sonraki zamanlayıcı döngüsünde kurtarmayı yeniden deneyecektir.

## İlgili Sayfalar

- [Servisler: Önyükleme Sırasında Otomatik Başlatma](/tr/docs/services#önyükleme-sırasında-otomatik-başlatma): otomatik başlatmayı etkinleştirme ve devre dışı bırakma, anahtar dosyası yönetimi
- [Yedekleme ve Geri Yükleme](/tr/docs/backup-restore): çalışan servislerle soğuk yedekleme etkileşimi
