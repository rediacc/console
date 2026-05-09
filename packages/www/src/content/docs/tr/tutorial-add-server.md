---
title: "İlk Sunucunuzu Ekleyin"
description: "İlk sunucunuzu rdc'ye kaydedin, yapılandırın ve rdc + renet mimarisini anlayın."
category: "Tutorials"
subcategory: essentials
order: 3
language: tr
sourceHash: "2b5de59f61cfb88c"
---

# İlk Sunucunuzu Ekleyin

Sunucu eklemeden önce `rdc`'nin nasıl çalıştığını anlamak işinizi kolaylaştırır. Rediacc iki araçlı bir mimariye sahiptir: dizüstü bilgisayarınızda `rdc`, sunucuda `renet`.

## Öğreticiyi izleyin

![Tutorial: Adding your first server](/assets/tutorials/tutorial-add-server.cast)

## Neden iki araç?

![rdc on laptop, renet on server, SSH between](/img/tutorials/tutorial-add-server/slide-1.svg)

- **`rdc`**, dizüstü bilgisayarınızdaki CLI aracıdır. Komutları buraya yazarsınız.
- **`renet`**, sunucudaki orkestratördür. Şifreleme, Docker ve izolasyonu yönetir.

Yerel olarak bir komut çalıştırdığınızda `rdc`, SSH üzerinden bağlanır ve sunucuda `renet`'i çalıştırır. Sunucularınıza hiçbir zaman manuel olarak SSH yapmanız gerekmez. `rdc` bunu sizin için halleder.

## Adım 1: Sunucuyu kaydedin

`rdc`'ye sunucu hakkında bilgi verin. Ad, IP ve kullanıcı bilgilerini kendinizinkiyle değiştirin.

```bash
time rdc config machine add --name my-server --ip 192.168.1.100 --user deploy
```

## Adım 2: Yapılandırın

Kurulum, sunucuya `renet` yükler ve şifreli veri deposunu oluşturur.

```bash
time rdc config machine setup --name my-server
```

Tamamlandığında sunucunuz depo barındırmaya hazır olur.

## Yapılandırma dosyası nerede?

`rdc`'nin kurulumunuz hakkında bildiklerini doğrulayın:

```bash
time rdc config show
```

Ya da ham JSON dosyasını doğrudan açın:

```bash
vim ~/.config/rediacc/rediacc.json
```

Bu tek dosya her şeyi içerir: makineler, depolar, SSH anahtarı, şifreleme kimlik bilgileri. Başka bir dizüstü bilgisayara kopyalarsanız o makineden de hazır olursunuz.

---

Sonraki: [İlk Deponuzu Oluşturun](/en/docs/tutorial-create-repo).
