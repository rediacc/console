---
title: "İzleme ve Tanılama"
description: "Makine sağlığını kontrol edin, konteynerleri inceleyin, systemd servislerini gözden geçirin, host anahtarlarını tarayın ve ortam tanılamalarını çalıştırın."
category: "Tutorials"
order: 4
language: tr
sourceHash: "af9f17a05dfb13b9"
---

# Rediacc ile Altyapıyı İzleme ve Tanılama

Altyapıyı sağlıklı tutmak, makine durumu, konteyner durumu ve servis sağlığı hakkında görünürlük gerektirir. Bu öğreticide, ortam tanılamalarını çalıştırır, makine sağlığını kontrol eder, konteynerleri ve servisleri inceler, kasa durumunu gözden geçirir ve bağlantıyı doğrularsınız. Bitirdiğinizde, altyapınızdaki sorunları nasıl belirleyip araştıracağınızı bileceksiniz.

## Ön Koşullar

- Yapılandırması başlatılmış olarak `rdc` CLI kurulu
- En az bir çalışan deposu olan hazırlanmış bir makine (bkz. [Öğretici: Depo Yaşam Döngüsü](/tr/docs/tutorial-repos))

## Etkileşimli Kayıt

![Öğretici: İzleme ve Tanılama](/assets/tutorials/monitoring-tutorial.cast)

### Adım 1: Tanılama çalıştırın

Yerel ortamınızı yapılandırma sorunları açısından kontrol ederek başlayın.

```bash
rdc doctor
```

Node.js, CLI sürümü, renet ikili dosyası, yapılandırma ve sanallaştırma desteğini kontrol eder. Her kontrol **OK**, **Warning** veya **Error** olarak raporlar.

### Adım 2: Makine sağlık kontrolü

```bash
rdc machine health server-1
```

Uzak makineden kapsamlı bir sağlık raporu alır: sistem çalışma süresi, disk kullanımı, veri deposu kullanımı, konteyner sayıları, depolama SMART durumu ve tespit edilen sorunlar.

### Adım 3: Çalışan konteynerleri görüntüleyin

```bash
rdc machine containers server-1
```

Makinedeki tüm depolardaki tüm çalışan konteynerleri listeler; ad, durum, hal, sağlık, CPU kullanımı, bellek kullanımı ve her konteynerin hangi depoya ait olduğunu gösterir.

### Adım 4: systemd servislerini kontrol edin

Her deponun Docker daemon ve ağını çalıştıran temel servisleri görmek için:

```bash
rdc machine services server-1
```

Rediacc ile ilgili systemd servislerini (Docker daemon'ları, loopback takma adları) durumları, alt durumları, yeniden başlatma sayıları ve bellek kullanımları ile listeler.

### Adım 5: Kasa durum özeti

```bash
rdc machine vault-status server-1
```

Makinenin üst düzey bir genel görünümünü sağlar: ana bilgisayar adı, çalışma süresi, bellek, disk, veri deposu ve toplam depo sayıları.

### Adım 6: Host anahtarlarını tarayın

Bir makine yeniden oluşturulduysa veya IP'si değiştiyse, saklanan SSH host anahtarını yenileyin.

```bash
rdc config machine scan-keys server-1
```

Sunucunun mevcut host anahtarlarını alır ve yapılandırmanızı günceller. Bu, "host key verification failed" hatalarını önler.

### Adım 7: Bağlantıyı doğrulayın

Makinenin erişilebilir olduğunu ve yanıt verdiğini doğrulamak için hızlı bir SSH bağlantı kontrolü.

```bash
rdc term server-1 -c "hostname"
rdc term server-1 -c "uptime"
```

Ana bilgisayar adı doğru sunucuya bağlandığınızı onaylar. Çalışma süresi sistemin normal çalıştığını onaylar.

## Sorun Giderme

**Sağlık kontrolü zaman aşımına uğruyor veya "SSH connection failed" gösteriyor**
Makinenin çevrimiçi ve erişilebilir olduğunu doğrulayın: `ping <ip>`. SSH anahtarınızın doğru yapılandırıldığını `rdc term <machine> -c "echo ok"` ile kontrol edin.

**Servis listesinde "Service not found"**
Rediacc servisleri yalnızca en az bir depo dağıtıldıktan sonra görünür. Depo yoksa servis listesi boştur.

**Konteyner listesi eski veya durmuş konteynerleri gösteriyor**
Önceki dağıtımlardan kalan konteynerler, `repo down` temiz çalıştırılmadıysa kalabilir. Bunları `rdc repo down <repo> -m <machine>` ile durdurun veya `rdc term <machine> <repo> -c "docker ps -a"` ile doğrudan inceleyin.

## Sonraki Adımlar

Tanılama çalıştırdınız, makine sağlığını kontrol ettiniz, konteynerleri ve servisleri inceleydiniz ve bağlantıyı doğruladınız. Dağıtımlarınızla çalışmak için:

- [İzleme](/tr/docs/monitoring) — tüm izleme komutları için tam referans
- [Sorun Giderme](/tr/docs/troubleshooting) — yaygın sorunlar ve çözümler
- [Öğretici: Araçlar](/tr/docs/tutorial-tools) — terminal, dosya senkronizasyonu ve VS Code entegrasyonu
