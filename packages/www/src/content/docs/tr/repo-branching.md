---
title: "Git benzeri dallanma"
description: "Kopyala-yaz fork'larını git commit'leri olarak ele alın: bir fork'u değişmez bir commit'e dondurun, dalları adlandırın, commit'leri yazılabilir fork'lara geri aktarın, geçmişi dolaşın ve canlı bir depoyu yerinde hiç değiştirmeden birleştirin."
category: Reference
subcategory: advanced
order: 41
language: tr
sourceHash: "2448559f0fcfc0e0"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# Git benzeri dallanma

İşte zihinsel model: Rediacc, kopyala-yaz fork'larını git benzeri bir sürüm geçmişine dönüştürür. Her değişmez fork bir **commit**'tir: bayt kararlı, dondurulmuş ve bağlanmayı reddeden bir görüntü. Dallar, bir commit'i işaret eden adlandırılmış referanslardır. `rdc repo checkout`, bir commit'i reflink-klonlar ve yeni bir yazılabilir çalışma fork'una geri aktarır; `rdc repo merge` ise canlı bir depoyu yerinde hiç değiştirmeden iki geçmiş çizgisini birleştirir.

Model iki depoya eşlenir. **Makine nesne deposudur**: commit'ler, veri deposunda yaşayan değişmez fork görüntüleridir. **CLI yapılandırması ref deposudur**: dal adları, geçerli `HEAD` ve reflog, makinede değil yerel yapılandırmanızda yaşar. Bu, git'in `.git/objects` ile `.git/refs` arasında kullandığı ayrımın aynısıdır.

## Ne zaman kullanılır

Bir fork bir adı hak ettiğinde dallanmaya başvurun. Bir yapay zeka ajanı üretim fork'unda serbest kaldı, sonuç iyi görünüyor ve daha sonra geri dönebileceğiniz ya da tanıtabileceğiniz donmuş, adlandırılmış bir kontrol noktası istiyorsunuz: `rdc repo commit` onu dondurur, `rdc repo branch` onu adlandırır. Riskli bir geçişten önce, garantili olarak hiçbir zaman değişmeyecek kesin bir geri alma noktasına sahip olmak için çalışma fork'unu commit edin (değişmez bir commit bağlanmayı reddeder, bu nedenle hiçbir şey içine yazamaz). İki kontrol noktasını karşılaştırmak için `rdc repo diff`, ortak bir kopyala-yaz atası paylaştıkları için herhangi iki commit arasında çalışır. Gözden geçirilmiş bir çalışma çizgisini hedef fork'a geri getirmek için `rdc repo merge`, sonucu bir reflink klonunda oluşturur ve atomik olarak değiştirir; böylece çalışan bir hedef birleştirme ortasında hiçbir zaman bozulmaz.

Yalnızca tek kullanımlık bir kopyaya ihtiyaç duyduğunuzda `rdc repo fork` yerine kullanmayın. Sade bir fork, geçici, test başına yalıtım için doğru birimdir. Commit'ler, bir durum saklamaya, adlandırmaya veya taşımaya değer olduğunda değer katar.

## Commit'ler ve fork'lar nasıl ilişkilidir

Bir depo, btrfs havuzundaki tek bir LUKS görüntü dosyasıdır. Bir fork bu görüntünün sabit zamanlı reflink'idir; bu nedenle 1 GB'lık bir depoyu ve 100 GB'lık bir depoyu fork'lamak aynı sürer. Bir **commit**, değişmez olarak işaretlenmiş bir fork'tur: renet onu bağlamayı reddeder, bu da görüntüsünü sonsuza kadar bayt kararlı tutar. Bu bayt kararlılığı, bir commit'i güvenilir bir geri alma noktası ve makineler arası delta aktarımı için belirleyici bir taban yapan şeydir.

`rdc repo commit`, commit mesajını, yazarını, zaman damgasını ve üst commit'i **birimin içine** kaydeder (böylece meta veri push sırasında görüntüyle birlikte seyahat eder) ve ayrıca birimin dışına yansıtır (böylece `rdc repo log`, hiçbir şeyi kilidi açmadan geçmişi dolaşabilir). Commit ettiğiniz çalışma fork'u, git çalışma ağacınızı commit'ten sonra olduğu gibi değiştirmeden devam eder.

## Komutlar

### rdc repo commit

Bağlı bir çalışma fork'unu yeni bir değişmez commit'e dondurun.

```bash
rdc repo commit --name <fork> --message "<message>" -m <machine>
```

| Seçenek | Açıklama | Varsayılan |
|---------|----------|------------|
| `--name <name>` | Commit edilecek çalışma fork'u. Bağlı olmalıdır. Zorunlu. | zorunlu |
| `--message <msg>` | Commit mesajı. Zorunlu. | zorunlu |
| `--author <author>` | Commit meta verisine kaydedilen commit yazarı. | ayarlanmamış |
| `-m, --machine <name>` | Hedef makine. Zorunlu. | zorunlu |
| `--debug` | Stderr'de ayrıntılı tanılamalar. | kapalı |

Yeni commit, `immutable: true` ile yerel yapılandırmaya kaydedilir ve çalışma fork'unun `headCommit`'i onu işaret edecek şekilde ilerler. Değişmez bir depoyu commit etmek reddedilir: önce yazılabilir bir fork'a aktarın.

### rdc repo branch

Bir çalışma fork'unun geçerli commit'ini işaret eden adlandırılmış bir dal ref'i oluşturun.

```bash
rdc repo branch --branch <name> --name <fork>
```

| Seçenek | Açıklama | Varsayılan |
|---------|----------|------------|
| `--branch <branch>` | Yeni dalın adı. Zorunlu. | zorunlu |
| `--name <name>` | Dalın işaret ettiği geçerli commit'e sahip çalışma fork'u. Zorunlu. | zorunlu |

Bu yalnızca yapılandırma işlemidir. Makinede hiçbir iş olmaz. Dal ref'i bir adı çalışma fork'unun `headCommit`'ine eşler; bu nedenle fork'un önce en az bir commit'i olmalıdır.

### rdc repo checkout

Değişmez bir commit'i (veya dal ucunu) yeni bir yazılabilir çalışma fork'una reflink olarak klonlayın.

```bash
rdc repo checkout --ref <commit> --tag <newFork> -m <machine>
rdc repo checkout --ref <branchName> --from <fork> --tag <newFork> -m <machine>
```

| Seçenek | Açıklama | Varsayılan |
|---------|----------|------------|
| `--ref <commit\|branch>` | Aktarılacak commit GUID'si veya `--from` verildiğinde dal adı. Zorunlu. | zorunlu |
| `--tag <name>` | Yeni yazılabilir çalışma fork'unun adı. Zorunlu. | zorunlu |
| `-m, --machine <name>` | Hedef makine. Zorunlu. | zorunlu |
| `--from <workingFork>` | Bu çalışma fork'unun dal kümesinde `--ref`'i dal adı olarak çözümler. | doğrudan commit |
| `--debug` | Stderr'de ayrıntılı tanılamalar. | kapalı |
| `--skip-router-restart` | Router yeniden başlatma adımını atlar. | kapalı |

Checkout, fork reflink yolunu yeniden kullanır; bu nedenle depo boyutundan bağımsız olarak neredeyse anlık ve sabit zaman alır. Yeni çalışma fork'unun `headCommit`'i aktarılan commit'e ayarlanır.

### rdc repo log

Bir çalışma fork'undan veya commit'ten erişilebilen commit geçmişini dolaşın.

```bash
rdc repo log --name <fork> -m <machine>
```

| Seçenek | Açıklama | Varsayılan |
|---------|----------|------------|
| `--name <name>` | Geçmiş yürüyüşüne başlanacak çalışma fork'u veya commit. Zorunlu. | zorunlu |
| `-m, --machine <name>` | Hedef makine. Zorunlu. | zorunlu |
| `--json` | Commit geçmişini JSON olarak çıktılar. | kapalı |
| `--debug` | Stderr'de ayrıntılı tanılamalar. | kapalı |

`log`, `rdc repo commit` tarafından kaydedilen üst zinciri dolaşır; hiçbir commit kilitlenmeden veya bağlanmadan birim dışı durum yansımasını okur. Salt okunur.

### rdc repo merge

Canlı hedefi yerinde değiştirmeden bir kaynak commit veya fork'u hedef çalışma fork'una birleştirin.

```bash
rdc repo merge --name <target> --from <source> -m <machine>
rdc repo merge --name <target> --from <source> --resolve theirs -m <machine>
```

| Seçenek | Açıklama | Varsayılan |
|---------|----------|------------|
| `--name <name>` | Birleştirilecek hedef çalışma fork'u. Zorunlu. | zorunlu |
| `--from <source>` | Birleştirilecek kaynak commit veya fork. Zorunlu. | zorunlu |
| `-m, --machine <name>` | Hedef makine. Zorunlu. | zorunlu |
| `--force` | Önce bağlı veya çalışan bir hedefi susturun, sonra birleştirin. Canlı bağlamayı hiçbir zaman değiştirmez. | kapalı |
| `--resolve <ours\|theirs>` | Dosya başına üç yollu birleştirme: kaynağın dosya başına değişikliklerini hedefe katlayın; her iki tarafta değişen dosyalar için kaynağın sürümünü tutun (`ours`) veya alın (`theirs`). Tüm görüntü alma-onların için atlayın. | kapalı |
| `--base <guid>` | Üç yollu birleştirme için ortak ata commit'i (`--resolve` ile kullanılır). Kaynak commit'in üst öğesini veya hedefin geçerli commit'ini varsayılan olarak kullanır. | otomatik |
| `--debug` | Stderr'de ayrıntılı tanılamalar. | kapalı |

Sonuç, bir reflink klonunda oluşturulur ve çökme korumalı bir işaret arkasında atomik olarak değiştirilir; böylece kesintiye uğrayan bir birleştirme orijinal hedefi bozulmadan bırakır. Bağlı veya çalışan hedef, hedefi değiştirmeden önce temizce kapatan `--force` olmadıkça reddedilir.

`--resolve` olmadan birleştirme, tüm görüntü alma-onlarındır (hedef kaynak olur). `--resolve` ile, kaynak commit'in kaydedilen üst öğesine karşı dosya başına üç yollu birleştirmedir: yalnızca bir tarafta değişen dosyalar o taraftan alınır ve her iki tarafta değişen dosyalar bayrakla çözülür. Çatışan yollar raporlanır.

### rdc repo gc

Hiçbir dalın veya HEAD'in ulaşmadığı bir makinedeki değişmez commit nesnelerini çöp toplama.

```bash
rdc repo gc -m <machine>            # kuru çalıştırma önizlemesi (varsayılan)
rdc repo gc --apply -m <machine>    # erişilemeyen commit'leri sil
```

| Seçenek | Açıklama | Varsayılan |
|---------|----------|------------|
| `-m, --machine <name>` | Toplama yapılacak makine. Zorunlu. | zorunlu |
| `--apply` | Erişilemeyen commit'leri gerçekten sil (aksi halde kuru çalıştırma önizlemesi). | kapalı |
| `--debug` | Stderr'de ayrıntılı tanılamalar. | kapalı |

Erişilebilirlik yerel yapılandırmadan hesaplanır (ref deposu): her dal ucunu ve HEAD'i üst zincirden takip ederek erişilebilen commit'ler kümesi. Bu kümenin dışındaki makinedeki değişmez commit'ler erişilemez. Bağlı nesne veya çalışma fork'u hiçbir zaman toplanmaz.

### rdc repo fsck

Yapılandırma ref'lerini bir makinede bulunan nesnelere karşı doğrulayın.

```bash
rdc repo fsck -m <machine>
```

| Seçenek | Açıklama | Varsayılan |
|---------|----------|------------|
| `-m, --machine <name>` | Kontrol edilecek makine. Zorunlu. | zorunlu |

Sarkan ref'leri (makinede nesnesi olmayan bir GUID'i işaret eden dal ucu veya HEAD) ve yetim commit'leri (makinede herhangi bir ref'in ulaşmadığı değişmez commit) raporlar. Salt okunur; yetim commit'leri `rdc repo gc --apply` ile geri kazanın.

### Değişmez fork'lar

`rdc repo fork --immutable`, yeni fork'u oluşturmada salt okunur olarak işaretler; ayrı bir `commit` adımı olmadan commit eşdeğeri bir taban üretir.

```bash
rdc repo fork --parent <name> --tag <tag> --immutable -m <machine>
```

Değişmez fork bağlanmayı reddeder; bu da görüntüsünü sonsuza kadar bayt kararlı tutar. Bu, tabanın her iki uçta özdeş olması gereken makineler arası delta push için dondurulmuş taban olarak kullanışlıdır. Değişiklik yapmak için yazılabilir bir kopyaya aktarın (veya yeniden fork'layın).

## Örnekler

### Çalışma fork'unu commit et

```bash
$ rdc repo commit --name myapp:work --message "schema migration applied" -m server-1
Committed 4f3c2a1b9d8e: schema migration applied
```

### Açık yazar ile commit et

```bash
$ rdc repo commit --name myapp:work --message "nightly snapshot" --author ci-bot -m server-1
Committed 7a1b2c3d4e5f: nightly snapshot
```

### Geçerli commit'te dal adlandır

```bash
$ rdc repo branch --branch staging --name myapp:work
Branch "staging" -> 4f3c2a1b9d8e
```

### Commit'i yeni yazılabilir fork'a aktar

```bash
$ rdc repo checkout --ref 4f3c2a1b9d8e --tag rollback-test -m server-1
```

### Dal ucunu adıyla aktar

`--from` ile `--ref` değeri verilen çalışma fork'undaki dal adı olarak çözümlenir:

```bash
$ rdc repo checkout --ref staging --from myapp:work --tag staging-copy -m server-1
```

### Geçmişi dolaş

```bash
$ rdc repo log --name myapp:work -m server-1
commit 4f3c2a1b9d8e
  Author: ci-bot  Date: 2026-05-29T10:14:02Z
  schema migration applied
commit 9d8e7a1b2c3d
  Author: ci-bot  Date: 2026-05-28T22:01:55Z
  initial import
```

### JSON olarak geçmiş

`--json`, yapılandırılmış yürüyüşü en yeniden başlayarak çıktılar:

```bash
$ rdc repo log --name myapp:work --json -m server-1
{
  "success": true,
  "start": "4f3c2a1b9d8e",
  "entries": [
    {
      "guid": "4f3c2a1b9d8e",
      "message": "schema migration applied",
      "author": "ci-bot",
      "parent": "9d8e7a1b2c3d",
      "committed_at": "2026-05-29T10:14:02Z",
      "immutable": true
    }
  ]
}
```

### İki commit'i farklılaştır

`rdc repo diff`, ortak bir kopyala-yaz atası paylaştıkları için herhangi iki commit arasında çalışır. Bir commit'i aktar, sonra diğerine göre farklılaştır:

```bash
$ rdc repo checkout --ref 4f3c2a1b9d8e --tag review -m server-1
$ rdc repo diff --name review --base myapp:work -m server-1
M  db/schema.sql

1 file changed: 0 added, 1 modified, 0 deleted, 0 renamed
```

Tam diff referansı için [rdc repo diff](/tr/docs/repo-diff) sayfasına bakın.

### Gözden geçirilmiş çizgiyi geri birleştir

```bash
$ rdc repo merge --name myapp:main --from myapp:work -m server-1
Merged myapp:work into myapp:main
```

### Çalışan hedefe birleştir

Bağlı veya çalışan hedef, önce onu susturan `--force` olmadıkça reddedilir:

```bash
$ rdc repo merge --name myapp:main --from myapp:work --force -m server-1
Merged myapp:work into myapp:main
```

### Dosya başına üç yollu birleştirme

Aynı commit'ten aktarılan iki fork (`feature` ve `hotfix`) bazı dosyaları değiştirdi. `--resolve theirs`, kaynağı (`hotfix`) hedefe (`feature`) katar: yalnızca bir tarafın değiştirdiği dosyalar o taraftan alınır ve her iki tarafın değiştirdiği dosyalar kaynağa çözülür. Taban paylaşılan atadan otomatik algılanır (veya `--base` ile sabitleyin):

```bash
$ rdc repo merge --name myapp:feature --from myapp:hotfix --resolve theirs -m server-1
Merged myapp:hotfix into myapp:feature (three-way); 1 conflict(s) resolved --theirs: [config/app.yaml]
```

`config/app.yaml` her iki tarafta değişti ve kaynağa çözüldü; yalnızca `hotfix`'in eklediği dosya uygulandı ve yalnızca `feature`'ın değiştirdiği dosya tutuldu. Çatışma yolları inceleyebilmeniz için raporlanır.

### Doğrudan değişmez taban oluştur

```bash
$ rdc repo fork --parent myapp --tag baseline-v1 --immutable -m server-1
```

## Delta push ve pull

Değişmez, bayt kararlı bir görüntü aynı zamanda **blok düzeyinde delta aktarımının** temelidir. Aynı değişmez taban iki makinede mevcutsa, bir push veya pull tüm şifreli görüntüyü taramak yerine o tabana göre değişen blokları hesaplayabilir ve yalnızca onları taşıyabilir. Birkaç değişen bloklu 1 GB'lık bir depo o zaman megabaytlarda aktarılır.

Normalde elle taban vermezsiniz. Tam push'tan sonra CLI, push edilmiş görüntüyü her iki makinede değişmez taban olarak tutar ve kaydeder; böylece o deponun **sonraki** push'u, hedefte zaten mevcut olan fork için bile bayrak olmaksızın otomatik olarak yalnızca deltayı gönderir. (Mevcut bir fork'un *tam* yeniden push'u hâlâ `--force` gerektirir; çünkü doğrulanmış delta uygulamak yerine tüm görüntüyü değiştirir.) Belirli bir tabanı sabitlemek için `--delta-base <guid>`, değişen blokların nasıl algılandığını kontrol etmek için `--strategy <auto|physical|shared>` kullanın (`auto` neredeyse tüm durumlarda doğrudur).

```bash
# İlk push tam aktarımdır; ayrıca her iki uçta yeniden kullanılabilir taban tutar.
$ rdc repo push --name myapp:work --to-machine backup-1 -m server-1

# Yerel değişikliklerden sonra sonraki push yalnızca değişen blokları gönderir, bayrak gerekmez.
$ rdc repo push --name myapp:work --to-machine backup-1 -m server-1

# Açık taban belirt (her iki makinede mevcut değişmez commit).
$ rdc repo push --name myapp:work --to-machine backup-1 --delta-base 4f3c2a1b9d8e -m server-1

# Delta ayrıca ters yönde çalışır; bir makine kaynağından yalnızca değişen blokları çeker.
$ rdc repo pull --name myapp:work --from-machine backup-1 --delta-base 4f3c2a1b9d8e -m server-1

# Mevcut yerel depoyu (üzerine yaz) --force ile yeniden çek.
$ rdc repo pull --name myapp:work --from-machine backup-1 --force -m server-1
```

Delta aktarımı yalnızca makineler arasında geçerlidir (FIEMAP tabanı olan uzak). Bulut nesne depolamasına push her zaman tam görüntüyü aktarır. Tabanın her iki uçta bayt bayta özdeş olması gerekir; bu da tam olarak değişmez bir commit'in veya `--immutable` fork'un garanti ettiği şeydir.

## JSON şeması

`rdc repo log --json`, renet sonucunu standart zarfla sarar. Yürütülen geçmiş, en yeniden başlayarak `entries`'te yaşar:

| Alan | Tür | Açıklama |
|------|-----|----------|
| `success` | boolean | Yürüyüşün tamamlanıp tamamlanmadığı. |
| `start` | string | Yürüyüşün başladığı GUID. |
| `entries` | array | Commit başına bir nesne, en yeniden başlayarak. |
| `entries[].guid` | string | Commit GUID'si. |
| `entries[].message` | string | Commit mesajı. Boş olduğunda atlanır. |
| `entries[].author` | string | Commit yazarı. Boş olduğunda atlanır. |
| `entries[].parent` | string | Üst commit GUID'si. Kökde atlanır. |
| `entries[].committed_at` | string | RFC 3339 commit zaman damgası. Ayarlanmadığında atlanır. |
| `entries[].immutable` | boolean | Commit'in salt okunur olarak işaretlenip işaretlenmediği (gerçek commit için her zaman true). |

Zarf alanları ve TTY dışı ortamlarda JSON çıktısı veren otomatik algılama kuralları için [JSON Çıktı Referansı](/tr/docs/ai-agents-json-output) sayfasına bakın.

## Sınırlamalar

- **Ref'ler yereldir.** Dal adları, `HEAD` ve reflog, makinede değil CLI yapılandırmanızda yaşar. Başka bir makineye commit push etmek commit nesnesini ve birim içi meta verilerini gönderir; ancak dal ref'i yapılandırma taraflı bir kavramdır.
- **Commit bağlanmayı reddeder.** Amacı budur: değişmezlik, commit'i bayt kararlı yapan şeydir. Commit'i çalıştırmak veya düzenlemek için önce yazılabilir bir çalışma fork'una aktarın.
- **Birleştirme çözümü dosya düzeyindedir, satır düzeyinde değil.** Hem tüm görüntü alma-onları (`--resolve` yok) hem de dosya başına üç yollu (`--resolve ours|theirs`) desteklenir. Üç yollu birleştirme, çatışmaları bir dosya başına bayrak başına çözer; dosya içinde satır düzeyinde çerçeve veya birleştirme işaretçileri üretmez.
- **Geçmiş bir üst zincirdir.** `rdc repo log`, commit zamanında kaydedilen tek `parent` bağlantısını dolaşır. Meta verisi sorgulanan makinede mevcut olmayan bir commit'e ulaştığında durur.

## Ayrıca bakın

- [rdc repo diff](/tr/docs/repo-diff). İlgili herhangi iki commit veya fork arasında dosya düzeyinde diff.
- [Depolar](/tr/docs/repositories). Depolar oluşturma, fork'lama, bağlama ve işletme.
