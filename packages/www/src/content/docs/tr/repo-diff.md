---
title: "rdc repo diff"
description: "İki copy-on-write forked depo arasında git benzeri, dosya düzeyinde fark göster - şifrelenmiş görüntülerini blok düzeyinde karşılaştırarak, şifre çözmeksizin."
category: Reference
subcategory: advanced
order: 40
language: tr
sourceHash: "c72fbcc13e7e77ed"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# rdc repo diff

`rdc repo diff`, iki ilgili depo arasında hangi dosyaların değiştiğini rapor eder: bir fork ve onun ana deposu, ya da copy-on-write atasını paylaşan herhangi iki depo. `--name <fork>` ile fork'u yerel konfigürasyonun kaydettiği ana depoya karşı karşılaştır, veya `--base <repo>` ekleyerek herhangi bir ilgili depoya karşı karşılaştır; burada `--base` temel (eski) taraf ve `--name` hedef (yeni) taraftır. Bu komut salt okunurdur ve görüntüleri hiçbir zaman şifre çözmez. Bunları uzak makinede blok düzeyinde karşılaştırır, bu nedenle maliyet depo boyutunun değil, değişen blok sayısının takip edilir: aynı düzenlemeleri yapan 1 GB depo ve 100 GB depo aynı sürede işlenir. Deponun tamamı değişmişse, blok sayısı boyutla ölçeklendirilir ve maliyet de öyledir.

## Ne zaman kullanılır

Yani: bir fork'u yükseltmeden önce `repo diff` kullanın. Bir AI ajanı prodüksiyonun fork'lanmış bir kopyasında dolaşıyordu ve değişikliği geri birleştirmeden önce tam olarak hangi dosyalara dokunduğunu görmek istiyorsunuz: `repo diff --name <fork> -m <machine>` size bu dosya listesini saniyeler içinde verir. Saniyeler. Olağanüstü durumda kurtarma geri yüklemesinden sonra, geri yüklenen fork'u, onu yeniden üretmesi gereken anlık görüntüye karşı karşılaştırın; beklenen dosya setinin geri geldiğini ve başka bir şeyin sürüklenmediğini doğrulayın. Haftalarca ana depo ile yan yana çalışan uzun ömürlü bir fork için, diff birikmiş uyumsuzluğu (konfigürasyon düzenlemeleri, log artışı, şema göçleri) gösterir; her iki ağacı da elle bağlamaya ve yürümeye gerek olmadan.

İlişkisiz depolar arasında kullanmayın. Her iki taraf da copy-on-write atası paylaşmalıdır, çünkü karşılaştırma paylaşılan blok tarihinde çalışır. Ayrıca bir ikili diff aracı değildir: `--content` yalnızca metin dosyaları için satır düzeyinde çıktı üretir ve ikili dosyalar `Binary files differ` bildirirler.

## Komut referansı

### Özet

```bash
rdc repo diff --name <fork> -m <machine>            # fork'u ana deposuna karşı karşılaştır
rdc repo diff --name <fork> --base <repo> -m <machine>   # herhangi bir ilgili depoya karşı karşılaştır
```

### Seçenekler

| Seçenek | Açıklama | Varsayılan |
|--------|----------|-----------|
| `--name <name>` | İncelenecek depo (hedef, yeni taraf). Gerekli. | gerekli |
| `--base <name>` | Karşılaştırılacak depo (temel, eski taraf). `--name` adresinin ana deposu olarak yerel konfigürasyondan çözülür. | `--name` adresinin ana deposu |
| (format bayrağı yok) | Ad-durum çıktısı: değişen her dosya için renkli `A`/`M`/`D`/`R` harfi ve bir satırlık özet. | açık |
| `--name-only` | Satır başına bir değişen yol, durum harfi yok. Pipe dostu. | kapalı |
| `--stat` | Dosya başına değişiklik büyüklüğü (bayt ve blok deltaları) ve toplamlar alt bilgisi. | kapalı |
| `--content <path>` | Tek bir dosyanın birleştirilmiş metin farkı. Yalnızca metin; ikili dosyalar `Binary files differ` bildirirler. | kapalı |
| `--json` | Ajanlar ve komut dosyaları için yapılandırılmış çıktı. | kapalı |
| `--fast` | İçerik-hash doğrulaması adımını atlayın ve blok filtresine güvenin. Daha hızlı, ancak Değiştirilmiş dosyaları aşırı rapor edebilir. | kapalı |
| `-m, --machine <name>` | Hedef makine. Gerekli. | gerekli |
| `--debug` | stderr'de ayrıntılı tanılama. | kapalı |
| `--skip-router-restart` | Yönlendirici yeniden başlatma adımını atlayın. | kapalı |

## Örnekler

### Ana depoya karşı varsayılan ad-durum

Yalnızca `--name` ile, fork yerel konfigürasyonda kaydedilen ana deposuna karşı karşılaştırılır. Burada `test-1gb:fork1` fork'u bir değiştirilmiş dosyaya sahiptir:

```bash
$ rdc repo diff --name test-1gb:fork1 -m hostinger
M  hello.txt

1 file changed: 0 added, 1 modified, 0 deleted, 0 renamed
```

### Açık bir tabana karşı karşılaştırma

`--base` ile herhangi bir ilgili depoya karşı karşılaştırın. `--base` temel (eski) taraf, `--name` hedef (yeni) taraftır:

```bash
$ rdc repo diff --name test-1gb:fork1 --base test-1gb:latest -m hostinger
M  hello.txt

1 file changed: 0 added, 1 modified, 0 deleted, 0 renamed
```

### `--stat` ile değişiklik büyüklüğü

`--stat` dosya başına bayt ve blok deltası ile toplamlar alt bilgisini ekler:

```bash
$ rdc repo diff --name test-1gb:fork1 --stat -m hostinger
 hello.txt | +8 bytes, 1 block

1 file changed, 4096 bytes touched
```

### Yalnızca yollar, bir araca pipe edilmiş

`--name-only` durum harfi olmadan satır başına bir yol yazdırır, başka bir komuta beslemek için hazır:

```bash
$ rdc repo diff --name test-1gb:fork1 --name-only -m hostinger | xargs -I{} echo "review: {}"
review: hello.txt
```

### Bir dosyanın satır düzeyinde farkı

`--content` tek bir metin dosyasının birleştirilmiş farkını üretir:

```bash
$ rdc repo diff --name test-1gb:fork1 --content hello.txt -m hostinger
--- a/hello.txt
+++ b/hello.txt
@@ -1 +1 @@
-the original line of text in the parent
+the original line of text in the parent, now edited
```

### jq ile JSON filtreleme

`--json` yapılandırılmış zarf çıktısını stdout'a gönderir, bu nedenle `jq` içine temiz bir şekilde pipe edilir:

```bash
$ rdc repo diff --name test-1gb:fork1 --json -m hostinger | jq '.data.entries[] | select(.status=="M")'
{
  "status": "M",
  "path": "/hello.txt",
  "type": "file",
  "old_size": 53,
  "size": 61,
  "bytes_changed": 4096,
  "blocks_changed": 1,
  "inode": 13,
  "content_changed": true,
  "mode_changed": false,
  "uid_changed": false,
  "gid_changed": false
}
```

## Çıktı biçimleri

### Ad-durum (varsayılan)

Her değiştirilmiş dosya bir durum harfi ve yolunu alır. `A` eklenen, `M` değiştirilmiş, `D` silinmiş, `R` yeniden adlandırılmış (eski yol gösterilir). Kategori başına sayı ile bir özet satırı takip eder.

### `--name-only`

Satır başına bir yol, durum harfi yok, özet yok. Aşağı akış komutu temiz bir dosya listesi istediğinde kullanın.

### `--stat`

Her satır dosyanın bayt deltası ve blok deltasını taşır. Bir alt bilgi toplam dosya sayısını ve toplam dokunulan baytları rapor eder. Bu, değişikliğin ağırlığının hangi yerlerde oturduğunu gösterir, yalnızca hangi dosyaların hareket ettiğini değil.

### `--content <path>`

Tek bir metin dosyası için standart birleştirilmiş diff (`---`/`+++` başlıkları, `@@` parçaları). İkili dosyalar `Binary files differ` bildirirler ve hiçbir parça üretmezler.

### `--json`

Tam yapılandırılmış sonuç. Veri stdout'a gider; ilerleme ve tanılama stderr'e gider, bu nedenle JSON, ilerleme yazdırılırken bile `jq` veya başka bir ayrıştırıcıya temiz bir şekilde pipe edilir.

## JSON şeması

CLI, renet sonucunu standart zarfa sarar (`success`, `command`, `data`, `errors`, `warnings`, `metrics`). Diff sonucu `data` içinde snake_case alanları ile bulunur:

```json
{
  "success": true,
  "command": "repo diff",
  "data": {
    "base": "<base-guid>",
    "target": "<target-guid>",
    "added": 0,
    "modified": 1,
    "deleted": 0,
    "renamed": 0,
    "strategy": "shared",
    "fast": false,
    "degraded": false,
    "block_size": 4096,
    "total_bytes_changed": 4096,
    "entries": [
      {
        "status": "M",
        "path": "/hello.txt",
        "type": "file",
        "old_size": 53,
        "size": 61,
        "bytes_changed": 4096,
        "blocks_changed": 1,
        "inode": 13,
        "content_changed": true,
        "mode_changed": false,
        "uid_changed": false,
        "gid_changed": false
      }
    ]
  }
}
```

`entries[]` içindeki her nesne bir değiştirilmiş yolu açıklar:

| Alan | Tür | Açıklama |
|------|-----|----------|
| `status` | `A` \| `M` \| `D` \| `R` | Eklenen, Değiştirilmiş, Silinmiş veya Yeniden Adlandırılmış. |
| `path` | string | Hedef taraftaki yol (veya silme için temel taraftaki yol). |
| `old_path` | string | Önceki yol. Yalnızca yeniden adlandırmalarda mevcut. |
| `type` | `file` \| `dir` \| `symlink` \| `other` | Giriş türü. |
| `old_size` | number | Temel taraftaki bayt cinsinden boyut. |
| `size` | number | Hedef taraftaki bayt cinsinden boyut. |
| `bytes_changed` | number | Farklı baytlar, tam blok olarak yuvarlanmış. |
| `blocks_changed` | number | Değiştirilmiş blok sayısı. |
| `inode` | number | İnode numarası, yeniden adlandırma algılaması için kullanılır. |
| `content_changed` | boolean | Dosya içeriğinin (sadece meta veriler değil) değişip değişmediği. |
| `mode_changed` | boolean | Dosya modunun değişip değişmediği. Doğru olduğunda `old_mode`/`new_mode` mevcuttur. |
| `uid_changed` | boolean | Sahibinin değişip değişmediği. Doğru olduğunda `old_uid`/`new_uid` mevcuttur. |
| `gid_changed` | boolean | Grubun değişip değişmediği. Doğru olduğunda `old_gid`/`new_gid` mevcuttur. |
| `old_target` / `new_target` | string | Sembolik bağlantı hedefleri. Değiştirilmiş sembolik bağlantılar için mevcut. |

Zarfa alanları ve TTY olmayan ortamlarda JSON yayan otomatik algılama kuralları için [JSON Çıktı Referansı](/tr/docs/ai-agents-json-output) bölümüne bakın.

## Nasıl çalışır

Bir depo, btrfs havuzunda bir LUKS2 görüntü dosyasıdır ve bir fork, o görüntünün sabit zamanlı reflink'idir. `repo diff` iki şifrelenmiş görüntüyü FIEMAP aracılığıyla blok düzeyinde karşılaştırır, yalnızca dosya sistemi meta verilerini okur ve hiçbir zaman şifre çözmez. Değişen şifrelenmiş metin uzaklıklarını LUKS veri uzaklığı ile kaydırarak ext4 cihaz uzaklıklarını alır, ardından bu uzaklıkları her dosyanın ext4 extent haritası aracılığıyla dosya adlarıyla geri eşler. Her iki bağlantının inode-kimlik yürüyüşü, sonucu Eklenen, Değiştirilmiş, Silinmiş ve Yeniden Adlandırılmış girdilere uzlaştırır. İş değişen blok sayısı ile sınırlandırıldığından, diff depo boyutundan bağımsızdır ve canlı bir bağlantıyı yerinde yeniden kullandığından, çalışan bir depoyu asla rahatsız etmez. Tam mekanizm [Git diff for encrypted disk images](/tr/blog/git-diff-for-encrypted-disk-images) bölümünde açıklanmıştır.

## Sınırlamalar

- **Yalnızca ilgili fork'lar.** Her iki taraf da copy-on-write atası paylaşmalıdır. İlişkisiz depolar arasında anlamlı bir blok düzeyinde karşılaştırma yoktur.
- **Yeniden adlandırma algılaması inode tabanlıdır.** Bir dosya aynı inode yeni bir yolda görüntülendiğinde yeniden adlandırılmış olarak rapor edilir. Sil-sonra-yeniden oluştur (yeni bir inode) yeniden adlandırma değil, Silinmiş artı Eklenen giriş olarak gösterilir.
- **`--content` yalnızca metindir.** Metin dosyaları için satır düzeyinde parçalar üretir. İkili dosyalar `Binary files differ` bildirirler.
- **`--fast` Değiştirilmiş aşırı raporlayabilir.** Blok filtresine güvenip içerik-hash doğrulamasını atlar, bu nedenle blokları içerik değiştirilmeksizin hareket eden bir dosya Değiştirilmiş olarak görünebilir.
- **Extent-yürüyüş süresi boyutla değil, parçalanma ile ölçeklendirilir.** Yoğun şekilde parçalanmış bir dosya sistemi eşlenecek daha fazla extent'e sahiptir, bu da değişikliklerin bayt hacmi küçük olsa bile yürüyüşü uzatır.

## Ayrıca bakın

- [rdc repo fork](/tr/docs/repositories). Bu komutun karşılaştırdığı copy-on-write fork'u oluştur.
- [rdc repo status](/tr/docs/repositories). Tek bir deponun geçerli durumu.
- [rdc repo cat](/tr/docs/repositories). Bir depodan tek bir dosya oku.
