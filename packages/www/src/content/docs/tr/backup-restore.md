---
title: Yedekleme ve Geri Yükleme
description: >-
  Şifrelenmiş depoları harici depolamaya yedekleyin, yedeklerden geri yükleyin
  ve otomatik yedeklemeler planlayın.
category: Guides
order: 7
language: tr
sourceHash: "bd53047cef737088"
---

# Yedekleme ve Geri Yükleme

Rediacc, şifrelenmiş depoları harici depolama sağlayıcılarına yedekleyebilir ve aynı veya farklı makinelerde geri yükleyebilir. Yedekler şifrelenmiştir -- geri yükleme için deponun LUKS kimlik bilgisi gereklidir.

## Depolamayı Yapılandırma

Yedekleri göndermeden önce bir depolama sağlayıcısı kaydedin. Rediacc, rclone uyumlu tüm depolamaları destekler: S3, B2, Google Drive ve daha fazlası.

### rclone'dan İçe Aktarma

Zaten yapılandırılmış bir rclone uzak bağlantınız varsa:

```bash
rdc config storage import rclone.conf
```

Bu, bir rclone yapılandırma dosyasındaki depolama yapılandırmalarını mevcut yapılandırmaya aktarır. Desteklenen türler: S3, B2, Google Drive, OneDrive, Mega, Dropbox, Box, Azure Blob ve Swift.

### Depolamaları Görüntüleme

```bash
rdc config storage list
```

## Yedek Gönderme

Bir depo yedeğini harici depolamaya gönderin:

```bash
rdc repo push my-app -m server-1 --to my-storage
```

| Seçenek | Açıklama |
|---------|----------|
| `--to <storage>` | Hedef depolama konumu |
| `--to-machine <machine>` | Makineden makineye yedekleme için hedef makine |
| `--dest <filename>` | Özel hedef dosya adı |
| `--checkpoint` | Göndermeden önce CRIU checkpoint oluştur (`rediacc.checkpoint=true` etiketli konteynerler için). Hedef `repo up` ile otomatik geri yüklenir |
| `--force` | Mevcut bir yedeği geçersiz kıl |
| `--tag <tag>` | Yedeği etiketle |
| `-w, --watch` | İşlem ilerlemesini izle |
| `--debug` | Ayrıntılı çıktıyı etkinleştir |
| `--skip-router-restart` | Skip restarting the route server after the operation |

## Yedek Çekme / Geri Yükleme

Harici depolamadan bir depo yedeğini çekin:

```bash
rdc repo pull my-app -m server-1 --from my-storage
```

| Seçenek | Açıklama |
|---------|----------|
| `--from <storage>` | Kaynak depolama konumu |
| `--from-machine <machine>` | Makineden makineye geri yükleme için kaynak makine |
| `--force` | Mevcut yerel yedeği geçersiz kıl |
| `-w, --watch` | İşlem ilerlemesini izle |
| `--debug` | Ayrıntılı çıktıyı etkinleştir |
| `--skip-router-restart` | Skip restarting the route server after the operation |

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
| `--skip-router-restart` | Skip restarting the route server after the operation |

## Zamanlanmış Yedeklemeler

Uzak makinede systemd zamanlayıcısı olarak çalışan bir cron zamanlamasıyla yedeklemeleri otomatikleştirin.

### Zamanlama Ayarlama

```bash
rdc config backup-strategy set --destination my-storage --cron "0 2 * * *" --enable
```

Farklı zamanlamalarla birden fazla hedef yapılandırabilirsiniz:

```bash
rdc config backup-strategy set --destination my-s3 --cron "0 2 * * *" --enable
rdc config backup-strategy set --destination azure-backup --cron "0 6 * * *" --enable
```

| Seçenek | Açıklama |
|---------|----------|
| `--destination <storage>` | Yedekleme hedefi (hedef başına ayarlanabilir) |
| `--cron <expression>` | Cron ifadesi (ör. `"0 2 * * *"` günlük saat 02:00 için) |
| `--enable` | Zamanlamayı etkinleştir |
| `--disable` | Zamanlamayı devre dışı bırak |

### Zamanlamayı Makineye Gönderme

Zamanlama yapılandırmasını systemd zamanlayıcısı olarak bir makineye dağıtın:

```bash
rdc machine deploy-backup server-1
```

### Zamanlamayı Görüntüleme

```bash
rdc config backup-strategy show
```

## Depolamayı Tarama

Bir depolama konumunun içeriğini tarayın:

```bash
rdc storage browse my-storage
```

## En İyi Uygulamalar

- **Günlük yedeklemeler planlayın** en az bir depolama sağlayıcısına
- **Geri yüklemeleri düzenli olarak test edin** yedek bütünlüğünü doğrulamak için
- **Kritik veriler için birden fazla depolama sağlayıcısı kullanın** (ör. S3 + B2)
- **Kimlik bilgilerini güvende tutun** -- yedekler şifrelenmiştir ancak geri yükleme için LUKS kimlik bilgisi gereklidir
