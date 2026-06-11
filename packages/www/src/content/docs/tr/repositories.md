---
title: "Depolar"
description: "Uzak makinelerde LUKS ile şifrelenmiş depoları oluşturma, yönetme ve işletme."
category: "Guides"
order: 4
language: tr
sourceHash: "65fd6e7f9e6a83c1"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# Depolar

Bir **depo**, uzak bir sunucudaki LUKS ile şifrelenmiş bir disk görüntüsüdür. Bağlandığında şunları sağlar:
- Uygulama verileriniz için yalıtılmış bir dosya sistemi
- Özel bir Docker daemon (sunucunun Docker'ından ayrı)
- /26 alt ağındaki her hizmet için benzersiz geri döngü IP'leri

## Depo Oluşturma

```bash
rdc repo create --name my-app -m server-1 --size 10G
```

| Seçenek | Zorunlu | Açıklama |
|--------|----------|-------------|
| `-m, --machine <name>` | Evet | Deponun oluşturulacağı hedef makine |
| `--size <size>` | Evet | Şifrelenmiş disk görüntüsünün boyutu (örneğin `5G`, `10G`, `50G`) |
| `--skip-router-restart` | Hayır | İşlem sonrasında yönlendirici sunucusunu yeniden başlatmayı atla |

Çıktı, otomatik oluşturulan üç değeri gösterir:

- **Repository GUID** -- Sunucudaki şifrelenmiş disk görüntüsünü tanımlayan bir UUID.
- **Credential** -- LUKS birimini şifrelemek/çözmek için kullanılan rastgele bir parola.
- **Network ID** -- Bu deponun hizmetleri için IP alt ağını belirleyen bir tam sayı (2816'dan başlar, 64 artarak devam eder).

> **Kimlik bilgisini güvenli bir şekilde saklayın.** Bu, deponuzun şifreleme anahtarıdır. Kaybolursa, veriler kurtarılamaz. Kimlik bilgisi yerel `config.json` dosyanızda saklanır ancak sunucuda saklanmaz.

## Bağlama ve Çıkarma

Bağlama, depoyu şifreler ve dosya sistemine erişilebilir kılar. Çıkarma, şifrelenmiş birimi kapatır.

```bash
rdc repo mount --name my-app -m server-1  # Decrypt and mount
rdc repo unmount --name my-app -m server-1  # Unmount and re-encrypt
```

| Seçenek | Açıklama |
|--------|-------------|
| `--checkpoint` | Bağlama/çıkarma öncesinde bir CRIU kontrol noktası oluştur (`rediacc.checkpoint=true` etiketli kapsayıcılar için) |
| `--skip-router-restart` | İşlem sonrasında yönlendirici sunucusunu yeniden başlatmayı atla |

## Durumu Kontrol Etme

```bash
rdc repo status --name my-app -m server-1
```

## Depoları Listeleme

```bash
rdc repo list -m server-1
```

### Tür sütunu ve durum aynası

Çıktı tablosu üç değer içeren bir `Type` sütunu içerir:

- **`grand`**. Üst öğesi olmadan yerel CLI yapılandırmanıza kaydedilmiş üst düzey bir depo. Temel durum.
- **`fork`**. Başka bir deponun kopyala-üzerine-yaz (copy-on-write) çatalı. Yerel yapılandırmadaki `grandGuid` aracılığıyla **ya da** makinedeki renet `.interim/state` aynası aracılığıyla tanımlanır. Her iki kaynak da yetkilidir; ayna doldurulduktan sonra her ikisi de aynı değeri göstermelidir.
- **`unknown`**. Hiçbir sinyal depoyu sınıflandıramaz. Çoğunlukla ayna kodu gönderilmeden önce oluşturulmuş ve o tarihten bu yana hiç yeniden bağlanmamış eski bir fork veya yerel yapılandırma girdisi yanlışlıkla silinmiş eski bir `grand` depodur. CLI tahmin etmeyi reddeder; operatör [ayna geri doldurmayı](/en/docs/pruning#migration-state-mirror-backfill) çalıştırmalı ya da gerçekten sahipsizse dizini kaldırmalıdır.

`.interim/state/<guid>/.rediacc.json` aynası, yedek araçlarının ve `repo list` komutunun her görüntünün kilidini açmadan fork soyunu okuyabilmesi için LUKS ile şifrelenmiş birimin **dışına** yazılan küçük bir ek dosyadır. Birim içindeki `.rediacc.json` ile aynı yapıyı taşır (`is_fork`, `grand_guid`, `name` vb.) ve her `Repository.SaveState` işleminde yenilenir, yani her bağlama ve her durum değişikliğinde. Bu, zamanlanmış yedeklemelerde fork tespiti için gerçeği kaynaktan okur: `is_fork: true` diyen bir aynaya sahip, bağlı olmayan bir fork, `cold` ve `hot` yüklemelerinden doğru şekilde atlanır.

Bilinmeyen girdilerin rutin temizliği için bkz. [`rdc machine prune --prune-unknown`](/en/docs/pruning#phase-3---prune-unknown-surgical).

## Yeniden Boyutlandırma

Depoyu tam bir boyuta ayarlayın veya belirli bir miktarda genişletin:

```bash
rdc repo resize --name my-app -m server-1 --size 20G  # Set to exact size
rdc repo expand --name my-app -m server-1 --size 5G  # Add 5G to current size
```

> Yeniden boyutlandırmadan önce deponun çıkarılmış olması gerekir. `repo expand` çevrimiçi çalışır. Yeniden boyutlandırma deponun maksimum boyutunu değiştirir; maksimumu değiştirmeden serbest kalan blokları havuza geri vermek için bunun yerine [`repo trim`](#alan-kazanma-trim) kullanın.

## Alan Kazanma (trim)

Depo içindeki dosyaları silmek o depo için alan serbest bırakır; `repo trim` ise bu serbest kalan blokları paylaşılan datastore havuzuna geri döndürür. Sıfır kesinti süresiyle çevrimiçi çalışır:

```bash
rdc repo trim -m server-1                       # Trim every mounted repository plus the datastore
rdc repo trim -m server-1 --name my-app          # Trim one repository
rdc repo trim -m server-1 --report-only          # Show reclaimable space without trimming
rdc repo trim -m server-1 --docker               # Also clear stopped containers, dangling images, and build cache first
```

Nasıl çalışır: depo görüntüleri seyrek dosyalardır ve şifreli birim discard'ları iletir. Bir trim, depo içindeki dosya sistemine kullanılmayan her bloğu serbest bırakmasını bildirir; bu da taşıyıcı görüntüde delikler açar ve havuz kullanımını anında azaltır.

Notlar:

- Aktif bir yedekleme altındaki depolar atlanır ve raporlanır. Yedekleme sırasında trim yapmak alan serbest bırakmaz; çünkü yedekleme anlık görüntüsü blokları hâlâ referans alır.
- Trim'i arka arkaya iki kez çalıştırmak ikinci seferde 0 bayt raporlar. Dosya sistemi hangi blok gruplarının zaten trimlendiğini hatırlar; bu beklenen bir durumdur, hata değildir.
- `--docker`, yalnızca sarkan görüntüleri, durdurulmuş konteynerleri ve derleme önbelleğini kaldırır; etiketli görüntülere dokunmaz. Kullanılmayan birimleri de kaldırmak için `--docker-volumes` ekleyin (bu veri siler; yalnızca CLI).

## Otomatik Boyut Politikası

Boyutu elle değiştirmek yerine makine, depo boyutlarını kendisi yönetsin. Bir politika, çevrimiçi otomatik büyümeyi etkinleştirir (dolduğunda deponun maksimum boyutu artar) ve zamanlanmış trim'leri devreye sokar. Makine, `rediacc-storage-maintain` systemd zamanlayıcısı aracılığıyla politikaları her birkaç dakikada bir uygular.

```bash
# Machine-wide default: trim every repository daily
rdc repo policy set -m server-1 --auto-trim true

# Per-repository: grow my-app automatically, up to a hard ceiling
rdc repo policy set -m server-1 --name my-app --auto-grow true --max-quota 50G

# Inspect the stored and effective policy
rdc repo policy get -m server-1 --name my-app
```

Politika alanları:

| Alan | Anlam | Varsayılan |
|---|---|---|
| `--auto-grow` | Dosya sistemi eşiği aştığında depoyu çevrimiçi olarak büyüt | kapalı |
| `--max-quota` | Otomatik büyüme için sabit tavan. Zorunludur: ayarlamak, havuzu fazla sağlamanıza açık onayınızdır | yok |
| `--grow-threshold` | Büyümeyi tetikleyen dosya sistemi kullanım yüzdesi | 85 |
| `--grow-step` | Büyüme başına eklenecek miktar: mutlak (`10G`) veya mevcut boyutun yüzdesi (`20%`) | 20% |
| `--auto-trim` | Zamanlanmış trim'leri çalıştır | kapalı |
| `--trim-interval` | Otomatik trim'ler arasındaki minimum saat sayısı | 24 |

Güvenceler: otomatik büyüme, havuzun boş alanı bir rezervin (havuzun 10 GB veya %5'i, hangisi daha büyükse) altına düştüğünde reddeder; aynı deponun ardışık büyümeleri arasında en az 30 dakika bekler ve `--max-quota` değerini asla aşmaz. Otomatik küçültme yoktur: deponun maksimum boyutunu azaltmak her zaman elle, çevrimdışı bir [`repo resize`](#yeniden-boyutlandirma) işlemidir.

Depo başına ayarlar, makine genelindeki varsayılanı geçersiz kılar. Tekrarlanan `policy set` çağrıları yalnızca ilettiğiniz bayrakları değiştirir.

## Fork

Mevcut bir deponun mevcut durumunun bir kopyasını oluşturun:

```bash
rdc repo fork --parent my-app --tag staging -m server-1
```

Fork'lar isim:etiket modelini kullanır: elde edilen fork, `my-app:staging` olarak adlandırılır. Bu, kendi GUID ve ağ kimliğine sahip yeni bir şifrelenmiş kopya oluşturur ve üst öğenin adını paylaşır. Fork, üst öğeyle aynı LUKS kimlik bilgisini paylaşır.

> Fork'lar, diskte depolanan kimlik bilgileri de dahil olmak üzere üst öğenin verilerini BTRFS reflink aracılığıyla paylaşır. Bu kimlik bilgileri Stripe, AWS veya Railway gibi harici hizmetleri yetkilendirdiğinde bunun etkileri için bkz. [Rediacc'ın yalıtmadıkları](/en/docs/ai-agents-safety#what-rediacc-does-not-isolate). Dağıtım zamanı kimlik bilgilerini fork'un erişim alanı dışında tutmak için, değerleri depo içindeki `.env` dosyalarına gömmek yerine [depo başına gizli diziler](#secrets) kullanın.

Fork oluşturma sırasında `repo fork`, [durum aynası ek dosyasını](#type-column-and-the-state-mirror) `<datastore>/.interim/state/<fork-guid>/.rediacc.json` konumuna hemen yazar. Birimi açmadan. Böylece yeni fork, oluşturma anından itibaren `is_fork: true` olarak doğru şekilde tanımlanır. Bu, zamanlanmış yedeklemelerin fork'u atlamasına olanak tanır (fork'lar varsayılan olarak yükleme ardışık düzeninden dışlanır), hiç bağlı olmasa bile. Bir fork'u çatallayırken `grand_guid` doğru şekilde zincir oluşturur: yeni fork'un aynası, ara fork'un GUID'ini değil, orijinal büyük üst öğenin GUID'ini işaret eder.

### Tek adımda fork ve başlatma

`--up` seçeneği fork oluşturma, bağlama ve servisleri başlatma işlemlerini tek bir uzak operasyonda birleştirir. Konteynerler başlar başlamaz terminalinizi geri almak için `--detach` ekleyin; sağlık kontrolleri arka planda tamamlanır ve proxy her servis bağlanana kadar yeniden dener:

```bash
rdc repo fork --parent my-app --tag staging -m server-1 --up
rdc repo fork --parent my-app --tag scratch -m server-1 --up --detach
```

Testlerimizde 128 GB'lık bir depo fork'landı ve servisler yaklaşık 57 saniyede çalışır hale geldi; `--detach` ile bu süre yaklaşık 31 saniyeye indi. Ayrılmış çalıştırmalar, ilerlemeyi kontrol etmek için bir ipucu yazdırır: `rdc machine query --containers --name <machine>`.

### Süre nereye gidiyor

Birkaç saniyeden uzun süren çalıştırmalar, sonunda bir zamanlama özeti içerir: adım adım döküm, paralel çalışanları gösteren bir şelale ve Rediacc ardışık düzenini servislerinizin kendi başlatma süresinden ayıran bir atıf satırı:

```
  Rediacc pipeline 19.2s (61%) · service startup 12.3s (39%)
```

Servis başlatma, kapsayıcıların önyüklenmesidir; görüntüler, başlatma, sağlık kontrolleri; bunlar Rediaccfile tarafından tanımlandığından uygulamaya göre değişir. Grafikler etkileşimli terminallerde oluşturulur; borulu çıktıda zorlamak için `RDC_TIMING_CHART=1` değişkenini ayarlayın.

## Git Benzeri Sürüm Yönetimi

Fork'lar git commit'leri gibi davranabilir. `rdc repo commit` çalışan bir fork'u değiştirilemez, byte-kararlı bir commit'e dondurur; `rdc repo branch` bir geçmiş satırını adlandırır; `rdc repo checkout` bir commit'i reflink ile klonlayarak yazılabilir bir fork oluşturur; `rdc repo log` ebeveyn zincirini dolaşır; `rdc repo merge` ise canlı bir depoyu yerinde değiştirmeden iki satırı birleştirir. `rdc repo fork --immutable` tek adımda commit eşdeğeri bir taban üretir.

```bash
rdc repo commit --name my-app:work --message "schema migration applied" -m server-1
rdc repo branch --branch staging --name my-app:work
rdc repo checkout --ref staging --from my-app:work --tag staging-copy -m server-1
```

Tam komut kümesi, seçenekler ve çalışılmış örnekler için [Git benzeri dallanma referansına](/en/docs/repo-branching) bakın.

## Gizli Diziler

Depo başına gizli diziler, şifrelenmiş depo görüntüsüne yazılmadan kapsayıcılara enjekte edilen dağıtım zamanı kimlik bilgileridir. Deponun verilerinden ayrı bir düzlemde tutulurlar; bu nedenle `rdc repo fork` bunları yaymaz. Bir fork boş bir gizli dizi haritasıyla başlar ve kapsayıcıları, üst öğeden farklı bir harici asıl olarak tanımlanarak önyüklenir.

> Adım adım bir rehber ister misiniz? Tam set/list/deploy/verify/rotate döngüsü için [Gizli Dizileri Yönetme öğreticisine](/en/docs/tutorial-managing-secrets) bakın.

**Salt yazma modeli (GitHub tarzı):** `get` yalnızca SHA-256 özetini döndürür. Düz metin değeri hiçbir zaman, ne bir insana ne de bir ajana döndürülmez. Bir değerin ne olduğunu unutursanız, şifre yöneticinizde arayın ve döndürün; tasarım gereği Rediacc'dan geri okuyamazsınız. Bu, bir hata sınıfının tamamını ortadan kaldırır: terminal kayıtları, kabuk geçmişi, yanlışlıkla yeniden yönlendirme, omuz sörf.

İki teslimat modu:

- `env`. Gizli dizi, hedef makinedeki renet kabuğunda `REDIACC_SECRET_<KEY>` olarak dışa aktarılır. `docker-compose.yml` dosyanızdan `${REDIACC_SECRET_<KEY>}` enterpolasyonu aracılığıyla referans alın. Kapsayıcının ortamında görünür olduğundan, uygulamanın env'de zaten beklediği bağlantı dizesi şeklindeki değerler için bunu kullanın.
- `file`. Gizli dizi, ana makinede `/var/run/rediacc/secrets/<networkID>/<KEY>` konumuna yazılır (tmpfs, hiçbir zaman kalıcı değil). Compose dosyanızdan `file:` kaynağıyla üst düzey bir `secrets:` bildirimi ve hizmet başına bir `secrets:` listesi aracılığıyla referans alın. Kapsayıcılar `/run/secrets/<key>` konumundan okur. Hassas her şey için bu modu tercih edin. `docker inspect` veya `/proc/<pid>/environ` içinde hiçbir zaman görünmez.

```bash
# Set, list, get (digest only), unset
rdc repo secret set --name my-app --key STRIPE_LIVE_KEY --value sk_live_xxx --mode file --current ""
rdc repo secret set --name my-app --key DB_HOST         --value postgres.internal --mode env --current ""
rdc repo secret list --name my-app
rdc repo secret get  --name my-app --key DB_HOST    # → { key, mode, digest } — no value
rdc repo secret unset --name my-app --key STRIPE_LIVE_KEY --current sk_live_xxx
```

**Simetrik mutasyon kapısı.** Hem insanların hem de ajanların bir gizli diziyi üzerine yazmak veya kaldırmak için `--current <önceki-değer>` girmesi gerekir (passwd tarzı ön koşul). Yeni bir anahtarın ilk yazımı için `--current ""` (boş) girin. Önceki değeri doğrulamadan döndürmek için bunun yerine `--rotate-secret` kullanın. Bu, yüksek sesle bir döndürme olarak denetlenir. `--current` ve `--rotate-secret` birbirini dışlar.

Kabuk geçmişine maruziyetten kaçınmak için (tek seferlik yazımlar için), değeri argv yerine stdin'den okumak üzere `--value -` girin.

`docker-compose.yml` dosyanızda:

```yaml
services:
  api:
    image: myapp
    environment:
      DATABASE_HOST: ${REDIACC_SECRET_DB_HOST}
    secrets:
      - stripe_live_key

secrets:
  stripe_live_key:
    file: /var/run/rediacc/secrets/${REDIACC_NETWORK_ID}/STRIPE_LIVE_KEY
```

Küçük harfli hizmet tarafı referansı (`stripe_live_key`), kapsayıcı içindeki `/run/secrets/<name>` dosya adıdır; ana makine yolunun büyük harfli kuyruğu (`STRIPE_LIVE_KEY`), `--key` ile belirlediğinizle eşleşir. `${REDIACC_NETWORK_ID}`, `renet compose` tarafından otomatik olarak enterpolasyona tabi tutulur.

> **Depo arası yalıtım uygulanır**: renet'in compose doğrulayıcısı, başka bir deponun ağ kimliğine referans veren `secrets: file:` (ve `configs: file:`, ve `env_file:`) yollarını reddeder. `/var/run/rediacc/secrets/...` referansları için kabul edilen tek form, `${REDIACC_NETWORK_ID}` değişmez belirteci (veya kendi ağınızın tam sayısı) dir. `--unsafe` bu kontrolü geçersiz kılmaz. Rediaccfile bash alt işleminin etrafındaki Landlock korumalı alanı da dosya sistemi erişimini yalnızca kendi ağınızın gizli dizi diziniyle kapsar; bu nedenle bir Rediaccfile'dan kötü niyetli bir `cat /var/run/rediacc/secrets/<other>/X` çağrısı çekirdek katmanında EACCES ile başarısız olur.

> **Fork'lar**: `rdc repo fork` gizli dizileri **kopyalamaz**. Fork'ta gizli diziler kullanmak için fork üzerinde açıkça `rdc repo secret set --name <fork>` çalıştırın. Bu, yük taşıyan güvenlik özelliğidir. Fork'un kapsayıcıları, harici hizmetlere karşı üretim asıl olarak hareket edememeli.

> **Ajanlar** (Claude Code, Cursor vb.): `repo secret list` ve `repo secret get`, MCP araçları olarak sunulur (güvenli okuma. Yalnızca adlar ve özetler, hiçbir zaman değerler). `set` ve `unset` yalnızca CLI'dır çünkü `--current`/`--rotate-secret` seremonisi insan gözü gerektirir; bunları kabuk üzerinden çağıran ajanlar insanlarla aynı kapıya gelir. Ön koşul başarısız olduğunda JSON zarfı, yapılandırılmış bir `errors[].next.options[].run` alanı içerir. Ajanlar bu komutları kullanıcıya birebir iletmelidir. Tam model için bkz. [Yapay zeka ajanı güvenliği](/en/docs/ai-agents-safety).

## Doğrulama

Bir deponun dosya sistemi bütünlüğünü kontrol edin:

```bash
rdc repo validate --name my-app -m server-1
```

## Sahiplik

Depo içindeki dosya sahipliğini evrensel kullanıcıya (UID 7111) ayarlayın. Bu, genellikle çalışma istasyonunuzdan dosya yükledikten sonra gereklidir; dosyalar yerel UID'inizle gelir.

```bash
rdc repo ownership --name my-app -m server-1
```

Komut, Docker kapsayıcı veri dizinlerini (yazılabilir bağlama bağlantı noktaları) otomatik olarak algılar ve bunları dışlar. Bu, kendi UID'leri ile dosyaları yöneten kapsayıcıların bozulmasını önler (örneğin MariaDB=999, www-data=33).

| Seçenek | Açıklama |
|--------|-------------|
| `--uid <uid>` | 7111 yerine özel bir UID ayarla |
| `--skip-router-restart` | İşlem sonrasında yönlendirici sunucusunu yeniden başlatmayı atla |

Kapsayıcı verileri de dahil olmak üzere tüm dosyalarda sahipliği zorlamak için:

```bash
rdc repo ownership --name my-app -m server-1
```


Proje geçişi sırasında sahipliğin ne zaman ve nasıl kullanılacağına ilişkin tam bir rehber için bkz. [Geçiş Kılavuzu](/en/docs/migration).

## Şablon

Bir depoyu dosyalarla başlatmak için şablon uygulayın:

```bash
rdc repo template apply --name my-template -m server-1 -r my-app --file ./my-template.tar.gz
```

## Silme

Bir depoyu ve içindeki tüm verileri kalıcı olarak yok edin:

```bash
rdc repo delete --name my-app -m server-1
```

> Bu, şifrelenmiş disk görüntüsünü kalıcı olarak yok eder. Bu işlem geri alınamaz.

## Depo Geçişi

Bir depoyu bir makineden diğerine canlı olarak geçirin. Kesinti yalnızca son delta-senkronizasyon aşamasında oluşur: kesme noktasındaki yazma hızına bağlı olarak tipik olarak birkaç saniyeden az dakikaya kadar.

```bash
rdc repo migrate --name my-app --from server-1 --to server-2
```

| Seçenek | Açıklama |
|--------|-------------|
| `--provision` | Geçişten önce hedef makinede depoyu hazırlayın (LUKS görüntüsü oluşturur ve yapılandırmayı kaydeder) |
| `--checkpoint` | Geçiş öncesinde çalışan kapsayıcıların bir CRIU kontrol noktasını oluşturun |
| `--bwlimit <kbps>` | rsync bant genişliğini kilobayt/saniye cinsinden sınırlandırın |
| `--skip-dns` | Geçiş sonrasında DNS kayıtlarını güncellemeyi atlayın |

**Üç aşamalı akış:**

1. **Sıcak ön kopyalama** - Depo kaynakta çalışmaya devam ederken rsync verileri aktarır. Büyük dosyalar, herhangi bir kesinti olmadan önce aktarılır.
2. **Geçiş** - Depo kaynakta durdurulur, son bir rsync geçişi kalan değişiklikleri eşitler ve depo hedefte başlatılır.
3. **Hedefte başlatma** - renet, hedef makinede depoyu bağlar ve başlatır. `--skip-dns` geçilmediğinde DNS güncellenir.

![Repository Live Migration](/img/repo-migrate-flow.svg)

**Push ile migrate karşılaştırması:**

| | `repo push` | `repo migrate` |
|--|-------------|----------------|
| İşlem | Kopyala | Taşı |
| Sonrası kaynak | Değişmedi | Durduruldu |
| Kesinti süresi | Yok (yalnızca kopyalama) | Kısa geçiş penceresi |
| DNS güncelleme | Hayır | Evet (`--skip-dns` yoksa) |
| Kullanım durumu | Yedekleme, hazırlık klonu | Makine değiştirme, sunucu taşıma |

## Temizleme

Depoları sildikten veya başarısız işlemlerden kurtardıktan sonra, sahipsiz bağlama dizinleri, kilit dosyaları ve taşınamaz işaretçiler kalabilir. Temizleme bunları güvenli şekilde kaldırır:

```bash
# Preview what would be removed
rdc machine prune --name server-1 --dry-run

# Remove orphaned resources
rdc machine prune --name server-1
```

Yalnızca eşleşen depo görüntüsü olmayan kaynaklar etkilenir. Boş olmayan bağlama dizinleri hiçbir zaman kaldırılmaz.
