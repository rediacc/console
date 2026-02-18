---
title: "Yedekleme ve Geri Yükleme"
description: "Şifrelenmiş depoları harici depolamaya yedekleyin, yedeklerden geri yükleyin ve otomatik yedeklemeler planlayın."
category: "Guides"
order: 7
language: tr
---

# Yedekleme ve Geri Yükleme

Rediacc, şifrelenmiş depoları harici depolama sağlayıcılarına yedekleyebilir ve aynı veya farklı makinelerde geri yükleyebilir. Yedekler şifrelenmiştir -- geri yükleme için deponun LUKS kimlik bilgisi gereklidir.

## Depolamayı Yapılandırma

Yedekleri göndermeden önce bir depolama sağlayıcısı kaydedin. Rediacc, rclone uyumlu tüm depolamaları destekler: S3, B2, Google Drive ve daha fazlası.

### rclone'dan İçe Aktarma

Zaten yapılandırılmış bir rclone uzak bağlantınız varsa:

```bash
rdc context import-storage my-storage
```

Bu, rclone yapılandırmanızdaki depolama ayarını mevcut bağlama aktarır.

### Depolamaları Görüntüleme

```bash
rdc context storages
```

## Yedek Gönderme

Bir depo yedeğini harici depolamaya gönderin:

```bash
rdc backup push my-app -m server-1 --to my-storage
```

| Seçenek | Açıklama |
|---------|----------|
| `--to <storage>` | Hedef depolama konumu |
| `--to-machine <machine>` | Makineden makineye yedekleme için hedef makine |
| `--dest <filename>` | Özel hedef dosya adı |
| `--checkpoint` | Göndermeden önce bir kontrol noktası oluştur |
| `--force` | Mevcut bir yedeği geçersiz kıl |
| `--tag <tag>` | Yedeği etiketle |
| `-w, --watch` | İşlem ilerlemesini izle |
| `--debug` | Ayrıntılı çıktıyı etkinleştir |

## Yedek Çekme / Geri Yükleme

Harici depolamadan bir depo yedeğini çekin:

```bash
rdc backup pull my-app -m server-1 --from my-storage
```

| Seçenek | Açıklama |
|---------|----------|
| `--from <storage>` | Kaynak depolama konumu |
| `--from-machine <machine>` | Makineden makineye geri yükleme için kaynak makine |
| `--force` | Mevcut yerel yedeği geçersiz kıl |
| `-w, --watch` | İşlem ilerlemesini izle |
| `--debug` | Ayrıntılı çıktıyı etkinleştir |

## Yedekleri Listeleme

Bir depolama konumundaki mevcut yedekleri görüntüleyin:

```bash
rdc backup list --from my-storage -m server-1
```

## Toplu Senkronizasyon

Tüm depoları aynı anda gönderin veya çekin:

### Tümünü Depolamaya Gönder

```bash
rdc backup sync --to my-storage -m server-1
```

### Tümünü Depolamadan Çek

```bash
rdc backup sync --from my-storage -m server-1
```

| Seçenek | Açıklama |
|---------|----------|
| `--to <storage>` | Hedef depolama (gönderme yönü) |
| `--from <storage>` | Kaynak depolama (çekme yönü) |
| `--repo <name>` | Belirli depoları senkronize et (tekrarlanabilir) |
| `--override` | Mevcut yedekleri geçersiz kıl |
| `--debug` | Ayrıntılı çıktıyı etkinleştir |

## Zamanlanmış Yedeklemeler

Uzak makinede systemd zamanlayıcısı olarak çalışan bir cron zamanlamasıyla yedeklemeleri otomatikleştirin.

### Zamanlama Ayarlama

```bash
rdc backup schedule set --destination my-storage --cron "0 2 * * *" --enable
```

| Seçenek | Açıklama |
|---------|----------|
| `--destination <storage>` | Varsayılan yedekleme hedefi |
| `--cron <expression>` | Cron ifadesi (ör. `"0 2 * * *"` günlük saat 02:00 için) |
| `--enable` | Zamanlamayı etkinleştir |
| `--disable` | Zamanlamayı devre dışı bırak |

### Zamanlamayı Makineye Gönderme

Zamanlama yapılandırmasını systemd zamanlayıcısı olarak bir makineye dağıtın:

```bash
rdc backup schedule push server-1
```

### Zamanlamayı Görüntüleme

```bash
rdc backup schedule show
```

## Depolamayı Tarama

Bir depolama konumunun içeriğini tarayın:

```bash
rdc storage browse my-storage -m server-1
```

## En İyi Uygulamalar

- **Günlük yedeklemeler planlayın** en az bir depolama sağlayıcısına
- **Geri yüklemeleri düzenli olarak test edin** yedek bütünlüğünü doğrulamak için
- **Kritik veriler için birden fazla depolama sağlayıcısı kullanın** (ör. S3 + B2)
- **Kimlik bilgilerini güvende tutun** -- yedekler şifrelenmiştir ancak geri yükleme için LUKS kimlik bilgisi gereklidir
