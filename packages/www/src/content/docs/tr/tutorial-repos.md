---
title: "Depo Yaşam Döngüsü"
description: "Şifreli bir depo oluşturun, konteynerleştirilmiş bir uygulama dağıtın, konteynerleri inceleyin ve temizleyin."
category: "Tutorials"
order: 3
language: tr
sourceHash: "0c4edddefa30df1c"
---

# Rediacc ile Depoları Dağıtma ve Yönetme

Depolar, Rediacc'ın temel dağıtım birimidir — her biri kendi Docker daemon'ı ve özel depolaması olan izole, şifreli bir ortamdır. Bu öğreticide şifreli bir depo oluşturur, konteynerleştirilmiş bir uygulama dağıtır, çalışan konteynerleri inceler ve temizlersiniz. Bitirdiğinizde tam bir dağıtım yaşam döngüsünü tamamlamış olursunuz.

## Ön Koşullar

- Yapılandırması başlatılmış `rdc` CLI'nin kurulu olması
- Hazırlanmış bir makine (bkz. [Öğretici: Makine Kurulumu](/tr/docs/tutorial-setup))
- `Rediaccfile` ve `docker-compose.yml` içeren basit bir uygulama

## Etkileşimli Kayıt

![Öğretici: Depo yaşam döngüsü](/assets/tutorials/repos-tutorial.cast)

### Adım 1: Şifreli bir depo oluşturun

Her depo kendi LUKS şifreli depolama birimine sahip olur. Makineyi ve depolama boyutunu belirtin.

```bash
rdc repo create test-app -m server-1 --size 2G
```

Rediacc 2 GB'lık şifreli bir birim oluşturur, biçimlendirir ve otomatik olarak bağlar. Depo, dosya yüklemeye hazırdır.

### Adım 2: Depoları listeleyin

Yeni deponun kullanılabilir olduğunu doğrulayın.

```bash
rdc repo list -m server-1
```

Makinedeki tüm depoları boyutları, bağlama durumları ve şifreleme durumlarıyla birlikte gösterir.

### Adım 3: Bağlama yolunu inceleyin

Dağıtımdan önce, deponun depolamasının bağlı ve erişilebilir olduğunu doğrulayın.

```bash
rdc term server-1 -c "ls -la /mnt/rediacc/mounts/test-app/"
```

Bağlama dizini, uygulama dosyalarının bulunduğu yerdir — `Rediaccfile`, `docker-compose.yml` ve veri birimleri.

### Adım 4: Servisleri başlatın

Depoyu bağlayarak ve Docker servislerini başlatarak uygulamayı dağıtın.

```bash
rdc repo up test-app -m server-1 --mount
```

Bu, depoyu bağlar (zaten bağlı değilse), izole bir Docker daemon başlatır ve `up()` ile servisleri başlatır.

> **Not:** İlk dağıtım, Docker imajları indirildiği için daha uzun sürer. Sonraki başlatmalar önbelleğe alınmış imajları yeniden kullanır.

### Adım 5: Çalışan konteynerleri görüntüleyin

```bash
rdc machine containers server-1
```

Makinedeki tüm depolardaki tüm çalışan konteynerleri, CPU ve bellek kullanımı dahil gösterir.

### Adım 6: Depo terminaline erişin

Deponun izole Docker ortamında komut çalıştırmak için:

```bash
rdc term server-1 test-app -c "docker ps"
```

Terminal oturumu, `DOCKER_HOST`'u deponun izole Docker soketine ayarlar. Tüm Docker komutları yalnızca o deponun konteynerlerine karşı çalışır.

### Adım 7: Durdurun ve temizleyin

İşiniz bittiğinde, servisleri durdurun, şifreli birimi kapatın ve isteğe bağlı olarak depoyu silin.

```bash
rdc repo down test-app -m server-1      # Servisleri durdur
rdc repo unmount test-app -m server-1   # Şifreli birimi kapat
rdc repo delete test-app -m server-1    # Depoyu kalıcı olarak sil
```

`down` konteynerleri ve Docker daemon'ı durdurur. `unmount` LUKS birimini kapatır. `delete` depoyu ve şifreli depolamasını kalıcı olarak kaldırır.

> **Uyarı:** `repo delete` geri alınamaz. Depodaki tüm veriler yok edilir. Gerekiyorsa önce bir yedek oluşturun.

## Sorun Giderme

**Depo oluşturma sırasında "Yetersiz disk alanı"**
Şifreli birim, ana makinede bitişik boş alan gerektirir. Sunucuda `df -h` ile kullanılabilir alanı kontrol edin. Daha küçük bir `--size` değeri kullanmayı veya disk alanı boşaltmayı düşünün.

**`repo up` sırasında Docker imaj çekme zaman aşımı**
Büyük imajlar yavaş bağlantılarda zaman aşımına uğrayabilir. `rdc repo up` ile yeniden deneyin — kaldığı yerden devam eder. Ağdan izole ortamlar için, imajları deponun Docker daemon'ına önceden yükleyin.

**"Bağlama başarısız" veya "LUKS açma başarısız"**
LUKS parolası yapılandırmadan türetilir. Depoyu oluşturan aynı yapılandırmayı kullandığınızı doğrulayın. Birim başka bir işlem tarafından zaten bağlıysa, önce bağlantısını kesin.

## Sonraki Adımlar

Şifreli bir depo oluşturdunuz, bir uygulama dağıttınız, konteynerleri inceleydiniz ve temizlediniz. Dağıtımlarınızı izlemek için:

- [Servisler](/tr/docs/services) — Rediaccfile referansı, servis ağları, otomatik başlatma ve çoklu servis düzenleri
- [Öğretici: İzleme ve Tanılama](/tr/docs/tutorial-monitoring) — sağlık kontrolleri, konteyner inceleme ve tanılama
- [Araçlar](/tr/docs/tools) — terminal, dosya senkronizasyonu ve VS Code entegrasyonu
