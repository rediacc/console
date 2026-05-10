---
title: "Yedekleme ve Geri Yükleme"
description: "Deponuzu harici depolama alanına gönderin ve ihtiyaç duyduğunuzda yeni bir sunucuda geri yükleyin."
category: "Tutorials"
subcategory: advanced
order: 11
language: tr
sourceHash: "8b48f3b19352aebe"
---

# Yedekleme ve Geri Yükleme

Uygulamanız üretimde canlı. Şimdi onu hiç kaybetmeyeceğinizden emin olun. `rdc`, tüm deponuzu (uygulama, veritabanı, dosyalar, yapılandırmalar) harici depolamaya gönderebilir ve istediğiniz zaman geri çekebilir. Fidye yazılımına, donanım arızasına, her şeye karşı dayanıklılık sağlar.

## Öğreticiyi izleyin

![Tutorial: Backup and restore](/assets/tutorials/tutorial-backup-restore.cast)

## Üç adım

![Configure, push, restore](/img/tutorials/tutorial-backup-restore/slide-1.svg)

1. Bir depolama sağlayıcısı **yapılandırın**.
2. Yedek **gönderin**.
3. İhtiyaç duyduğunuzda **geri yükleyin**.

## Adım 1: Depolamayı yapılandırın

Bir `rclone` yapılandırma dosyasına ihtiyacınız var. Halihazırda rclone kullanıyorsanız doğrudan içe aktarın:

```bash
time rdc config storage import --file rclone.conf
```

S3, B2, Google Drive, Dropbox ve çok daha fazlası desteklenir. Nelerin bağlı olduğunu doğrulayın:

```bash
time rdc config storage list
```

## Adım 2: Yedek gönderin

```bash
time rdc repo push --name my-app -m my-server --to my-storage
```

Tüm deponuz (uygulama, veritabanı, dosyalar, her şey) artık yedeklendi. Deponun kendisi şifreli olduğu için yedek de şifreli olur. Ek anahtar yönetimi gerekmez.

Yedeklerinizi istediğiniz zaman listeleyin:

```bash
time rdc repo backup list --from my-storage -m my-server
```

## Neden kesinti yok?

Yedek yüklenirken uygulama çalışmaya devam eder. Bu nasıl tutarlı olur?

[Fork](/en/docs/tutorial-forking) mantığının aynısı. `rdc` önce fork alır, sonra fork'u yükler. Fork o anı yakalar; canlı uygulamanız devam eder. Kesinti yok, tutarsızlık yok.

## Adım 3: Yeni sunucuda geri yükleyin

Diyelim ki sunucunuz çöktü. Yeni bir sunucu kurun, `rdc`'ye ekleyin ve çekin:

```bash
time rdc repo pull --name my-app -m new-server --from my-storage
```

Ardından başlatın:

```bash
time rdc repo up --name my-app -m new-server
```

Uygulamanız geri döndü. Aynı veri, aynı container'lar, farklı makine.

## Daha hızlı yedekler: makineden makineye

Ayrıca doğrudan makineler arasında da gönderebilirsiniz; arada bulut depolama olmadan:

```bash
time rdc repo push --name my-app -m my-server --to-machine backup-server
```

> **İpucu.** Depolama yüklemeleri her zaman her şeyi gönderir. Makineden makineye yalnızca farkı gönderir. İlk makineden makineye gönderim olağan süreyi alır, ancak sonraki her gönderim çok daha hızlıdır. Sık yedeklemeler için idealdir.

---

Sonraki: [İzleme](/en/docs/tutorial-monitoring).
