---
title: "Yedek İndirme"
description: "Bir deponun şifreli imajını yerel bir dizine veya harici bir sürücüye kopyalar, sonraki çalıştırmalarda yerinde günceller ya da hiçbir makine olmadan doğrudan yedek deposundan yeniden oluşturur."
category: "Guides"
tags:
  - backup
  - storage
subcategory: data-protection
order: 8
language: tr
sourceHash: "c52e6a0471befc30"
---

# Yedek İndirme

`rdc backup download`, bir deponun şifreli imajının kopyasını yerel bir dizinde veya harici bir sürücüde tutar. Kopya, makinede duran şifreli metnin aynısıdır; bu yüzden yolda hiçbir şey çözülmez. İmajı açan kimlik bilgisi yapılandırmada kalır, bu nedenle onu güvende tutmanın yolu [config storage](/tr/docs/config-storage) kaydıdır. Kimlik bilgisi olmadan imaj açılamaz.

İki kaynak vardır. Çalışan bir makine varsayılandır. Diğeri, `--store` ile seçilen yedek deposudur.

## Bir makineden indirme

```bash
rdc backup download mail@prod --to /mnt/usb
```

`--to`, var olan ve yazılabilir bir dizini belirtir. Dizin hiçbir zaman oluşturulmaz, bu yüzden sürücü önceden bağlanmalıdır. İmaj `<machine>/<name>.<tag>.img` konumuna yazılır ve yanında bir `.state.json` dosyası bulunur.

Her çalıştırma, deponun yalnızca aktarım süresince tutulan yeni bir anlık görüntüsünü alır, farkları rsync ile gönderir ve sonucun sha256 değerini makinenin anlık görüntüsüyle karşılaştırır.

| Bayrak | Etki |
|------|--------|
| `--all -m <machine>` | Makineye yerleştirilmiş her grand depoyu kopyalar |
| `--include-forks` | `--all` ile birlikte fork'ları da kopyalar |
| `--bwlimit <rate>` | Ağ bant genişliğini sınırlar, örneğin `100Mbps` veya `12.5M` |
| `--checkpoint` | Anlık görüntüden önce depoya checkpoint uygular ve dondurur (sıcak yedek) |
| `--retries <n>` | Ağ hatasından sonra çalıştırma içindeki yeniden denemeler (varsayılan 3) |
| `--skip-verify` | sha256 karşılaştırmasını atlar; rsync'in kendi sağlama toplamı yine çalışır |
| `--skip-space-check` | Hedefte boş alan yetmeyebilirse reddetmek yerine uyarır |

### Kopyayı güncelleme

İkinci çalıştırma, var olan imajı rsync deltasıyla yerinde günceller. Haftalık bir çalıştırma yalnızca değişeni gönderir ve hedefin iki değil, imajın bir kopyası kadar yere ihtiyacı vardır. Bir çalıştırma başlamadan önce boş alan imaj boyutuyla karşılaştırılır ve `--skip-space-check` bir reddi uyarıya çevirir.

### Yarıda kalan çalıştırmalar ve devam

Durum dosyası `status` değerini kaydeder. İlk bayt yazılmadan önceden bir çalıştırma doğrulanana kadar değer `incomplete` olur ve `incomplete` bir imaj kullanılamaz. Ctrl-C, kopan bağlantı veya sonlandırılan bir işlem imajı bu durumda bırakır. Aynı komutu yeniden çalıştırmak kaldığı yerden devam ettirir ve yalnızca farklar gönderilir. Durum `complete` olunca komut 0 koduyla çıkar.

### Gereksinimler

Aktarım için bu bilgisayarda rsync 3.1.3 veya daha yenisi gerekir ve SFTP yedeği yoktur. Linux dağıtımları rsync'i hazır getirir. macOS'ta `brew install rsync`, aktarımı çalıştıramayan yerleşik openrsync'in yerine geçer. Windows'ta rsync paketiyle MSYS2 kurulur veya masaüstü uygulaması kullanılır.

### Harici sürücüler

Nelerin sığacağına hedefin dosya sistemi karar verir.

- **FAT32**, 4 GiB'den büyük bir dosyayı tutamaz ve komut çalıştırmayı reddeder.
- Seyrek dosya desteği olmayan **exFAT**, imajı görünen tam boyutuyla saklar; boş alan denetimi de bu boyutu sayar.
- Hedefin yerelde alınmış bir **copy-on-write anlık görüntüsü** (btrfs, ZFS, APFS) imajın önceki sürümlerini korur. Bu durumda her yerinde güncelleme, eski bloklara ek olarak değişen blokların da maliyetini taşır.

## Yedek deposundan indirme

```bash
export REDIACC_TOKEN=<api-token>
rdc backup download mail --store --to /mnt/usb
```

`--store`, imajı hiçbir makine olmadan doğrudan chunk deposundan yeniden oluşturur. `REDIACC_TOKEN` içindeki belirteç `backup:read` ve `backup:restore` kapsamlarına ihtiyaç duyar. Bir CLI oturumu `backup:restore` kapsamını hiçbir zaman taşımaz; bu yüzden belirteç portalın API Tokens sayfasında oluşturulur. Bir ekibe ait olmalı ve kuruluşun mevcut bir sahibi veya yöneticisi tarafından oluşturulmuş olmalıdır.

`--store` tam olarak bir depo adı alır. `-m`, `--checkpoint`, `--all`, `--include-forks`, `--bwlimit`, `--retries`, `--skip-verify` ve `--skip-space-check` bayraklarını kabul etmez: depodan alma işleminin kendi devam mekanizması vardır ve her chunk'ı doğrular.

İmaj `<dir>/<name>.<tag>.img` konumuna yazılır. Yarıda kalan bir alma işlemi kısmi kopyayı korur ve aynı komut oradan devam eder.

### `--at` ile anlık görüntü seçme

Varsayılan olarak en yeni anlık görüntü alınır. `--at <time|snapshot>` başka birini seçer; ISO 8601 biçiminde bir zaman ya da bir anlık görüntü kimliği verilebilir. Yalnızca `--store` ile geçerlidir.

```bash
rdc backup download mail --store --to /mnt/usb --at 2026-10-01T00:00:00Z
```

Linux dışındaki bir platformda alınan imaj şifrelidir ve yerelde açılamaz. `rdc backup upload` ile bir Linux makinesine gönderilir.

## Kopyayı geri yükleme

```bash
rdc backup upload /mnt/usb/prod/mail.latest.img --to prod --as mail-copy --up
```

`rdc backup upload`, indirilmiş bir imajı bir makineye gönderir ve yeni bir depo olarak kaydeder. Aktarım kesintiden sonra devam eder; makine imajı yerleştirmeden önce sha256 değerini ve LUKS başlığını denetler. Kimlik bilgisini imajın yanındaki durum dosyası sağlar. Bu dosya kaybolduğunda `--from-repo <name>`, kimlik bilgisini sağlayan depoyu belirtir.

| Bayrak | Etki |
|------|--------|
| `--as <name>` | Yeni depo için ad (varsayılan: imajın adı) |
| `--datastore <name>` | İmajı adlandırılmış bir datastore'a yerleştirir |
| `--from-repo <name>` | Durum dosyası kullanılamadığında kimlik bilgisini ve soy bilgisini sağlar |
| `--bwlimit <rate>`, `--retries <n>` | İndirmedeki ile aynı |
| `--up` | Depoyu kaydedildikten sonra başlatır |
| `--skip-verify` | İndirme sırasında kaydedilen sha256 ile karşılaştırmayı atlar |

## Eskimiş aktarım anlık görüntüleri

Aniden sonlandırılan bir aktarım, anlık görüntüsünü makinede bırakabilir. `rdc machine status`, eskimiş aktarım anlık görüntülerini havuz özetinde sayar ve `rdc machine prune <machine> --dry-run` bunları listeler. `rdc machine prune <machine>` komutu çalıştırıldığında bunlar kaldırılır.

Chunk depolamaya alınan anlık görüntüler için [Yedekleme ve Geri Yükleme](/tr/docs/backup-restore) sayfasına bakılabilir.
