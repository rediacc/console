---
title: AI Ajan Güvenliği ve Koruma Önlemleri
description: 'Rediacc CLI''ı, AI kodlama asistanlarının sırları sızdırmasını, kimlik bilgilerinin üzerine yazmasını veya ayrıcalıkları yükseltmesini nasıl önler. Bilgi kapıları, gizleme, soy ağacı doğrulamalı geçersiz kılmalar ve karma zincirli denetim kaydı.'
category: Concepts
order: 35
language: tr
sourceHash: "ae23c9bc851ecfcd"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

Altyapınızı yönetmek için bir AI kodlama asistanını kullanıyorsanız. Claude Code, Cursor, Gemini CLI, Copilot CLI veya benzer herhangi bir araç `rdc` komutunu çalıştırdığında, CLI onu klavye başındaki bir insandan farklı ele alır ve farklı bir kural seti uygular. Bu sayfa ajanın yapabileceğini, yapamayacağını ve ajan bu koruma önlemlerini atlatmaya çalışsa bile bunların nasıl geçerli kaldığını açıklar.

## Hızlı başvuru: ajanların yapabileceği ve yapamayacağı işlemler

| İşlem | Ajan varsayılanı | Belirli bir kullanım durumu için nasıl açılır |
|---|---|---|
| `rdc config show` (gizlenmiş) | ✅ allowed |  |
| `rdc config field get --pointer <pointer>` (gizlenmiş taslak veya özet) | ✅ allowed |  |
| `rdc config field get --pointer <pointer> --digest` | ✅ allowed |  |
| `rdc config field set --pointer <pointer>` (genel alan) | ✅ allowed |  |
| `rdc config field set --pointer <pointer>` (hassas alan, **doğru `--current` ile**) | ✅ allowed |  |
| `rdc config edit --dump` (gizlenmiş JSONC) | ✅ allowed |  |
| `rdc config audit {log, tail, verify}` | ✅ allowed |  |
| `rdc config field set --pointer <pointer>` (hassas alan, `--current` olmadan) | 🔴 refused | `--current "<eski değer>"` sağlayın |
| `rdc config field get --pointer <pointer> --reveal` | 🔴 refused | Bunun yerine `--digest` kullanın |
| `rdc config show --reveal` | 🔴 refused | Düz `rdc config show` kullanın |
| `rdc config edit` (etkileşimli düzenleyici) | 🔴 refused | İnsan, ajanı başlatmadan önce `REDIACC_ALLOW_CONFIG_EDIT=*` ayarlar |
| `rdc config edit --apply <file>` | 🔴 refused | Aynı geçersiz kılma |
| `rdc config field rotate --pointer <pointer>` | 🔴 refused | Aynı geçersiz kılma; etkileşimli onay kullanır |
| `rdc term connect -m <machine>` (doğrudan makine SSH) | 🔴 refused | Önce bir repo forkla ve fork'a bağlan |

Bir ajana reddedilen her şey `outcome: refused` ve bir gerekçeyle denetim kaydına yazılır.

## Ajanlar nasıl tespit edilir

CLI bir işlemi ajan olarak değerlendirirken şu koşullardan herhangi birinin doğru olması yeterlidir:

- `REDIACC_AGENT`, `CLAUDECODE`, `GEMINI_CLI`, `COPILOT_CLI` değişkenlerinden biri `"1"` olarak ayarlanmış ya da `CURSOR_TRACE_ID` herhangi bir değerle ayarlanmış.
- Linux'ta: soy ağacındaki herhangi bir üst işlem bu değişkenlerden birini kendi ortamında barındırıyorsa (`/proc/<pid>/environ` üzerinden). Ajan `env -i` veya sarmalayıcı bir betikle kendi değişkenlerini kaldırsa bile üst zincir CLI'a kimin başlattığını söyler.

Tespit işlem başına bir kez çalışır ve önbelleğe alınır. Devre dışı bırakılamaz.

## Bilgi kapısı modeli

Hassas değişiklikler `passwd(1)` kuralına uyar: bir sırrı değiştirmek için onu önceden bildiğinizi kanıtlayın. **İnsanlar ve ajanlar için simetriktir**. Her ikisi de aynı kapıdan geçer. "Klavye başındayım" adında bir geçiş yolu yoktur.

- `/credentials/cfDnsApiToken` adresinde saklanan bir API token'ını döndürmek istiyorsunuz?
- CLI sorar: "mevcut değer nedir?"
- Ajan (veya insan) düz metni `--current "$OLD"` aracılığıyla sağlar. CLI `$OLD` değerini SHA-256 ile hashler ve şu anda saklanan değerin özeti ile karşılaştırır. Eşleşme geçti respon yazma işlemi gerçekleşir. Uyumsuzluk reddedilir, denetlenir.
- Önceki değeri doğrulamadan döndürmek için `--rotate-secret` adımını geçin (mutually exclusive with `--current`). Bu yüksek sesle denetim kaydı olarak yazılır.

Model üç saldırı yüzeyini kapatır:

1. **Sessiz rotasyon**: önceden `$OLD` değerine erişimi olmayan bir ajan (veya insan) onu kendi seçtiği bir değerle değiştiremez.
2. **Araştırma yoluyla sızdırma**: özet yanıtı asla düz metin içermez; ele geçirilmiş bir denetim kaydı bile `expected abc12345…, got deadbeef…` gösterir, altta yatan değerleri değil.
3. **Üretim yapılandırmasının yanlışlıkla üzerine yazılması**: her seferinde kasıtlı `--current` gerektirir, TTY'de bile. "STRIPE_TEST ayarlamak istemiştim ama üretim kabuğundayım" hatasını yakalar.

### Yapılandırılmış sonraki adım ipuçları

Ön koşul başarısız olduğunda, JSON zarfı (`--output json`) ajanların insandan tam olarak ne yapmasını isteyeceğini söyleyen yapılandırılmış bir `errors[].next` alanı taşır:

```json
{
  "errors": [{
    "code": "PRECONDITION_MISMATCH",
    "message": "...",
    "next": {
      "summary": "Provide the current value or acknowledge rotation.",
      "options": [
        { "description": "Re-read current digest, then retry with --current",
          "run": "rdc repo secret get --name mail --key STRIPE_KEY" },
        { "description": "Skip the precondition (rotation, audited)",
          "run": "rdc repo secret set --name mail --key STRIPE_KEY --value <new> --mode file --rotate-secret" }
      ]
    }
  }]
}
```

**Ajanlar `next.options[].run` komutunu insan yerine sözlü olarak iletmelidir; kendi komutlarını oluşturmamalıdır.** Bu "ajan olmayan komut oluşturur" başarısız modundan kaçınır ve operatörü gerçek işlemin kontrolünde tutar.

### Uygulamalı örnek

```bash
# Gizleme taslağının kısa özetini alma (ajanlar için güvenli).
$ rdc config field get --pointer /credentials/cfDnsApiToken
{"pointer": "/credentials/cfDnsApiToken", "value": "<redacted:secret>:abc12345"}

# Kanıt olmadan üzerine yazmayı deneme: reddedildi.
$ rdc config field set --pointer /credentials/cfDnsApiToken --new '"agent-picked-value"'
✗ Precondition failed: sensitive path requires --current (or --rotate-secret)

# Mevcut düz metni sağlama: izin verildi.
$ rdc config field set --pointer /credentials/cfDnsApiToken \
    --current "$OLD_CF_TOKEN" \
    --new   "$NEW_CF_TOKEN"
Set /credentials/cfDnsApiToken
```

Ajan hiç `$OLD_CF_TOKEN` değerine sahip olmadıysa ön koşulu karşılayamaz ve rotasyon reddedilir. *Sahip olan* kullanıcı bunu yine de düzenleyici aracılığıyla veya kabuğundan `--current` geçirerek yapabilir.

## Varsayılan olarak gizleme

Hassas durumu okuyan her `rdc` komutu: `config show`, `config field get`, `config machine list`, `config edit --dump`: gizli alanlar için düz metin yerine **gizleme taslakları** döndürür:

```
"sshKey":       "<redacted:credential>:9f3a2c1b"
"cfDnsApiToken":"<redacted:secret>:abc12345"
"storages.s3-prod.vaultContent": "<redacted:secret>:1f2e3d4c"
```

Taslağın 8 karakterli onaltılık soneki `sha256(canonicalize(value))` değerinin ilk 8 karakteridir: bir bakışta iki farklı değeri ayırt etmeye yeterli, tersine çevirmeye yeterli değil. Ajan bir taslak kullanarak değeri hiç görmeden değişip değişmediğini takip edebilir.

`--reveal` etkileşimli bir TTY'deki insanlar için gizlemeyi kaldırır. Ajanlar TTY durumundan bağımsız olarak reddedilir. Her verilen izin `reveal_granted` denetim kaydı yazar; her red, aktörün ajan sinyalleri eklenmiş `refused` kaydı yazar.

## `REDIACC_ALLOW_CONFIG_EDIT` geçersiz kılma

Etkileşimli düzenleyici, `--apply`, `field rotate` gibi bazı işlemler insanlar için vardır ve ajan için güvenli bir yol sunmaz. Bir ajanın bunlardan birini yapmasını etkin olarak istiyorsanız şunu ayarlarsınız:

```bash
export REDIACC_ALLOW_CONFIG_EDIT='*'          # tam atlama
# veya
export REDIACC_ALLOW_CONFIG_EDIT='/credentials/ssh/privateKey,/infra/cfDnsZoneId'
# (virgülle ayrılmış kapsam globları: segment başına * joker karakterlere izin verilir)
```

...ve ajan bunu devralır.

**Kritik ayrıntı**: geçersiz kılma, soy zincirinde ajanın **üstündeki** bir işlemde görünmelidir. Ajan bunu kendi ortamına (ya da oluşturduğu bir alt kabukta) ayarlarsa CLI reddeder ve size bunu bildirir:

> `Interactive editor is blocked in agent environments (REDIACC_ALLOW_CONFIG_EDIT was set but ancestry verification failed: the override must be set by your shell, not by an agent).`

Efekt: bir ajan oturum ortasında `export REDIACC_ALLOW_CONFIG_EDIT='*'` çalıştırarak bir koruma önlemini aşamaz. Yalnızca bir üst işlem (ajanı başlatmadan önce terminalinizdeki siz) o kapıyı açabilir.

## Platform desteği: geçersiz kılmalar yalnızca Linux

`REDIACC_ALLOW_CONFIG_EDIT` ve `REDIACC_ALLOW_GRAND_REPO`, geçersiz kılmanın ajan tarafından enjekte edilmediğini, sizin tarafınızdan ayarlandığını kanıtlamak için soy ağacı doğrulamasına dayanır. Doğrulama, zincir boyunca her işlem için `/proc/<pid>/environ` dosyasını okur. Bu dosya çekirdek tarafından exec sırasında ayarlanır ve işlemin kendisi tarafından değiştirilemez; bu nedenle üst kabuğun ortamı kurcalanamaz bir tanıktır.

Bu dosya macOS veya Windows'ta yoktur. Meşruiyeti doğrulamanın bir yolu olmadığında CLI kapalı şekilde başarısız olur. Ajanı başlatmadan önce kabuğunuzda geçersiz kılmayı doğru bir şekilde ayarlamış olsanız bile, geçersiz kılma reddedilir. Hata mesajı tam olarak ne yapmanız gerektiğini söyler:

> The REDIACC_ALLOW_GRAND_REPO override is not supported on darwin. This override only works on Linux. On Windows and macOS, agents must use the fork-first workflow. … To use the override, run your agent on Linux (directly, WSL, Docker, or a VM).

Linux dışı kullanıcıların ön-fork iş akışından kaçış yolu yoktur. Bu kasıtlıdır. Ajanlar, nasıl yönlendirilmiş olurlarsa olsunlar, arkasından geçip geçemeyen bir sandbox üzerinde çalıştırılır. Geçersiz kılmaya ihtiyacınız varsa ajanınızı WSL, bir Linux konteyneri veya bir Linux VM içinde çalıştırın; aksi takdirde bir fork üzerinde çalışın.

## Denetim kaydı

Her değişiklik, her red, her `--reveal` izni `~/.config/rediacc/audit.log.jsonl` dosyasına (mod `0600`, 10 MB'ta döndürülür) bir JSONL satırı yazar. Her satır karma ile zincirlenmiştir: `prevHash` alanı `sha256("<önceki satır>")` değeridir. Herhangi bir satırı değiştirmek, sonraki tüm satırlarda zinciri bozar.

```jsonl
{"ts":"2026-04-21T10:02:47.831Z","actor":{"kind":"agent","agentSignals":["CLAUDECODE"]},"command":"config field set","paths":["/credentials/cfDnsApiToken"],"outcome":"ok","configId":"...","configVersion":48,"prevHash":"sha256:9f3a..."}
{"ts":"2026-04-21T10:02:51.114Z","actor":{"kind":"agent","agentSignals":["CLAUDECODE"]},"command":"config edit","paths":[],"outcome":"refused","reason":"agent without REDIACC_ALLOW_CONFIG_EDIT=*","prevHash":"sha256:abc1..."}
{"ts":"2026-04-21T10:03:05.220Z","actor":{"kind":"human"},"command":"config show --reveal","paths":[],"outcome":"reveal_granted","configId":"...","configVersion":48,"prevHash":"sha256:deac..."}
```

### İnceleme

```bash
# Son kayıtları listele
rdc config audit log --since 24h

# İşaretçi globuna göre filtrele
rdc config audit log --path '/credentials/*'

# Yalnızca ajandan kaynaklanan kayıtlar
rdc config audit log --actor agent

# Yeni kayıtları canlı akış (durdurmak için Ctrl+C)
rdc config audit tail

# Karma zincirinin bozulmadığını doğrula
rdc config audit verify
# → "Chain integrity verified across 247 entries."
#   VEYA
# → "Chain broken at line 103: file has been tampered with or corrupted."
```

### Denetim kaydında asla görünmeyenler

- Düz metin sır değerleri
- Parolalar, tokenlar, SSH anahtarları
- `--current` ön koşul uyumsuzluğunda eski/yeni değerler (yalnızca 8 karakterlik özet öneki)

Kayıt, bir güvenlik denetçisiyle paylaşmak veya bir hata raporuna eklemek için güvenlidir.

## Davranış modelinin sınırları

Ajan koruma önlemleri **davranışsaldır, kriptografik değil**. Yapılandırma dosyasıyla aynı UID altında çalışan kararlı veya yönlendirilmiş bir ajan her zaman `cat ~/.config/rediacc/rediacc.json` yaparak düz metni okuyabilir, çünkü dosya işlem tarafından okunabilir.

Gerçek kriptografik zorunluluk için [şifreli yapılandırma deposunu](/tr/docs/config-storage) kullanın: sırlar sunucu tarafında yaşar, her hassas alan alan başına bir HMAC taahhüdü taşır ve hesap çalışanı depolananla karma eşleşmesi yapmayan `--current` ön koşullu yazmaları reddeder. Sunucu hiçbir zaman düz metni görmez (sıfır bilgi), ancak kapıyı zorlar.

Yerel dosya yolu: kolay yol güvenlidir. Uzak depo yolu: zor yol da zordur.

## Rediacc'in izole etmediği şeyler

Bu sayfadaki ajan koruma önlemleri Rediacc'in kendi altyapısını korur: yapılandırma dosyası, depo başına Docker daemon'u, LUKS ile şifrelenmiş depo verileri, kapsamlanmış SSH sandbox'ı. Bunlar, deponuzun kimlik bilgilerini tuttuğu harici servisleri korumaz.

Bir depo çatalı, üst birimin BTRFS reflink'idir. Üst birimde diskte yaşayan her şey, çatalda bayt bayt aynıdır: kod, veri ve `.env` dosyaları. Deponuz bir `STRIPE_LIVE_KEY`, bir `AWS_ACCESS_KEY_ID`, bir Railway API token'ı veya üçüncü taraf bir servis için herhangi bir uzun ömürlü kimlik bilgisi içeriyorsa, çatal bunu devralır. Çatalın sandbox'ında çalışan bir ajan o dosyayı okuyabilir, değeri sızdırabilir veya üçüncü taraf API'sini çağırmak için kullanabilir. Üçüncü taraf servisin, çağrının üretim yerine bir çataldan geldiğini bilmesinin bir yolu yoktur.

Bu, paylaşılan sorumluluk çizgisidir:

| Sınır | Sahibi |
|---|---|
| Depo verileri, mount ad alanı, Docker kapsamı, ajan korumaları, denetim kaydı, deploy-time gizli enjeksiyonu | Rediacc |
| Bu gizli bilgileri kullanan uygulama kodu ve yapı zamanında görüntüye dahil edilen kimlik bilgileri | Depo geliştirici |

Birincil azaltma yerleştirilmiş olarak gelir: **[depo başına sırlar](/tr/docs/repositories#secrets)** şifreli depo görüntüsünden ayrı bir düzlemde saklanır ve çatal sınırı arasında kopyalanmaz. Bir çatalın konteynerleri boş bir sırlar haritasıyla önyüklenir ve kendilerini üst konteynere göre farklı bir harici asıl olarak tanımlarlar. `rdc repo secret set` ile ayarlayın (compose interpolasyonu için env-modu, tmpfs `secrets:` blokları için file-modu). Mutasyon kapısı simetrik olarak uzanan ve insanlar ve ajanlar varolan bir değerin üzerine yazmak veya silmek için `--current` (passwd-stili ön koşulu) veya `--rotate-secret` (denetlenen rotasyon) sağlamak zorundadır.

**Depo arasında izolasyon zorlanır.** Depo B'deki kötü niyetli veya dikkatsiz bir compose dosyası depo A'nın sırlar dizinine referans veremez. Renet'in compose doğrulayıcısı, geçerli depo dışındaki `${REDIACC_NETWORK_ID}` dizinine işaret eden herhangi bir `secrets: file:`, `configs: file:` veya `env_file:` yolunu zor şekilde reddeder ve red `--unsafe` tarafından geçersiz kılınamaz. Savunma derinliği: Rediaccfile bash alt işlemi etrafındaki Landlock sandbox'ı dosya sistem okumasını yalnızca geçerli ağın sırlar dizinine kapsam alır; bu nedenle kötü niyetli bir Rediaccfile'dan `cat /var/run/rediacc/secrets/<other>/X` çekirdek katmanında EACCES ile başarısız olur.

İki ek desen kenar durumlarını kapatır:

1. **Üretim kimlik bilgilerini depo dosya sisteminin kendisine takmayın.** Görüntüye işlenmiş bir `.env` dosyası veya `up()` sırasında hacim içinde kalıcı bir kimlik bilgisi çatalın içine reflink'lenmiştir. Depo başına sırlar özelliği yalnızca sırlar düzleminde tuttuğunuz değerleri korur. Zaten LUKS görüntüsünde yaşayan bayt'ları geriye doğru koruyamaz. Baked-in `.env` dosyalarıyla mevcut depo'lar için bunları depo başına sırların içine el ile kaldırın.
2. **Çatalın giden ağını eBPF egress filtreleme ile kısıtlayın** böylece çatal yalnızca localhost ve açık sandbox uç noktalarına ulaşabilir. Rediacc'in depo başına ağ izolasyonu temeldir; depo başına egress allowlist'leri bugün inşa edilmemiştir, ancak yol açıktır.

Rediacc, deploy-time enjeksiyonunu, çatal arasında izolasyonu ve depo arasında izolasyonu yönetir. "Görüntüye bakma" yarısı sizin üzerinizdir.

## Hızlı tarifler

### Bir ajana tek bir bulut tokenını döndürme izni verme

```bash
# Siz olarak, ajanı başlatmadan önce:
export REDIACC_ALLOW_CONFIG_EDIT='/credentials/cfDnsApiToken'
claude-code              # ya da cursor, gemini vb.
```

Artık ajan `config field rotate /credentials/cfDnsApiToken --new …` çalıştırabilir ama `/credentials/ssh/privateKey` alanını düzenleyemez veya etkileşimli düzenleyiciyi açamaz.

### Bir ajana geniş kapsamlı bir yapılandırma düzenleme oturumuna izin verme

```bash
export REDIACC_ALLOW_CONFIG_EDIT='*'
claude-code
```

Ajan `rdc config edit` açabilir, `--reveal` kullanabilir ve `field rotate` çalıştırabilir. Her işlem yine de `actor.kind: agent` ve `CLAUDECODE` sinyaliyle denetim kaydına yazılır.

### Bir ajanın hangi alanları değiştirebileceğini keşfetme

```bash
rdc config field list --sensitive --output json
```

Her işaretçi şablonunu, türünü (`secret` / `credential` / `pii` / `identifier`) ve sunucu tarafındaki HMAC zarfına dahil edilip edilmediğini döndürür.

## Ayrıca bakınız

- [AI Ajan Entegrasyonuna Genel Bakış](/tr/docs/ai-agents-overview): üst düzey tur
- [Claude Code kurulumu](/tr/docs/ai-agents-claude-code): entegrasyon şablonu
- [JSON çıktı zarfı](/tr/docs/ai-agents-json-output): makine tarafından okunabilir yanıtlar
- [Şifreli yapılandırma deposu](/tr/docs/config-storage): sunucu tarafı kriptografik zorunluluk
- [Hesap güvenliği](/tr/docs/account-security): operatör odaklı güvenlik duruşu
