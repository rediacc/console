---
title: "Kurulum"
description: "rdc CLI'ı dizüstü bilgisayarınıza tek komutla yükleyin ve rdc doctor ile doğrulayın."
category: "Tutorials"
subcategory: essentials
order: 1
language: tr
sourceHash: "99d4ca1a4f89278e"
---

# Kurulum

`rdc`'yi kurmak üç adımdan oluşur: kurulum sayfasını açın, işletim sisteminizi seçin, komutu terminalinize yapıştırın. Tüm süreç genellikle bir-iki dakika içinde tamamlanır.

## Öğreticiyi izleyin

![Tutorial: Installation](/assets/tutorials/tutorial-installation.cast)

## Üç adım

![Three steps overview](/img/tutorials/tutorial-installation/slide-1.svg)

1. [Kurulum sayfasını](/en/install) açın.
2. İşletim sisteminizi seçin.
3. Kurulum komutunu kopyalayıp terminalinize yapıştırın.

## Platformunuza göre kurun

Kurulum sayfası sizin için doğru komutu oluşturur; ancak standart tek satırlık komutlar şunlardır.

**Linux / macOS:**

```bash
time curl -fsSL https://www.rediacc.com/install.sh | bash
```

**Windows (PowerShell):**

```powershell
iwr -useb https://www.rediacc.com/install.ps1 | iex
```

> `time` öneki, bir komutun ne kadar sürdüğünü yazdıran bir kabuk numarasıdır. Bu seriyi boyunca her adımın gerçek hızını görebilmeniz için kullanıyoruz. İsteğe bağlıdır; istemiyorsanız kaldırabilirsiniz.

## Kurulumu doğrulayın

Betik tamamlandıktan sonra `rdc`'nin ihtiyaç duyduğu her şeyin yerinde olduğunu kontrol edin:

```bash
time rdc doctor
```

`rdc doctor`, Node, SSH ve `rdc`'nin diğer bağımlılıklarını tek tek kontrol eder; eksik bir şey varsa bildirir.

## `rdc` neden dizüstü bilgisayarınızda yaşar?

![rdc on your laptop, renet on the server](/img/tutorials/tutorial-installation/slide-2.svg)

`rdc`, dizüstü bilgisayarınızdaki CLI aracıdır. Sunucu ise `renet` adlı ayrı bir bileşen çalıştırır. `rdc`, SSH üzerinden `renet`'i yapılandırır ve yönetir. Sunucularınıza manuel olarak SSH yapmanıza hiç gerek kalmaz. `rdc` bunu sizin için halleder.

Bu kurulumu önümüzdeki iki öğreticide düzgün biçimde yapılandıracağız.

---

Sonraki: [SSH Anahtar Yapılandırması](/en/docs/tutorial-ssh-keys).
