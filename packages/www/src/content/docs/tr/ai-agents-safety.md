---
title: AI Ajan Güvenliği ve Koruma Önlemleri
description: >-
  Rediacc'in yapay zekâ kodlama asistanlarının sırları sızdırmasını, kimlik
  bilgilerinin üzerine yazmasını veya yetki yükseltmesini nasıl engellediği.
  Her yüzey için tek karar, açık onay VE ilke tavanı, bilgi kapıları, gizleme
  ve sunucuda kuruluş ve gün bazında, CLI'da ise yerel bir dosyada hash zincirli bir denetim günlüğü.
category: Concepts
tags:
  - ai-agents
  - security
subcategory: ai-agents
order: 35
language: tr
sourceHash: "43350a2e682cebcc"
sourceCommit: "cc655e698ed2c42faef5311e268425c04997f243"
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
| `rdc config edit --dump --redacted` (gizlenmiş JSONC) | ✅ allowed |  |
| `rdc config audit {log, tail, verify}` | ✅ allowed |  |
| `rdc config field set --pointer <pointer>` (hassas alan, `--current` olmadan) | 🔴 refused | `--current "<eski değer>"` sağlayın |
| `rdc repo secret set <repo> --rotate-secret` (`--current` olmadan rotasyon) | 🔴 refused | `--current` verin veya rotasyonu bir insan terminalde yapsın |
| `rdc config field get --pointer <pointer> --reveal` | 🔴 refused | Bunun yerine `--digest` kullanın |
| `rdc config show --reveal` | 🔴 refused | Düz `rdc config show` kullanın |
| `rdc config edit` (etkileşimli düzenleyici) | 🔴 refused, geçersiz kılma yok | `--dump --redacted` ile inceleyin, tek bir alanı `config field set --current` ile değiştirin |
| `rdc config edit --apply <file>` | 🔴 refused, geçersiz kılma yok | Aynısı; tüm belgedeki düzenlemeleri terminaldeki bir insan uygular |
| `rdc config edit --reveal` | 🔴 refused, geçersiz kılma yok | Aynısı |
| `rdc config field rotate --pointer <pointer>` | 🔴 refused | Bir insan etkileşimli bir terminalde çalıştırır |
| Bir grand (üretim) deposunu değiştirmek | 🔴 refused | O depo için bir insanın açık onayı, grand depo değişikliklerine izin veren bir ilke içinde ([aşağıda](#one-decision-opt-in-and-policy-ceiling)) |
| Küme veya veri deposu yaşam döngüsü işlemleri | 🔴 refused | O küme için bir insanın açık onayı, küme işlemlerine izin veren bir ilke içinde |
| `rdc term connect <machine>` (doğrudan makine SSH) | 🔴 refused | Önce bir repo forkla ve fork'a bağlan |

Bir ajana yönelik her ret, `outcome: refused` ve bir gerekçeyle denetim günlüğüne yazılır. Yapılandırma belgesinin tamamını düzenlemenin ajan için hiçbir yolu yoktur: yapılandırma her deponun LUKS kimlik bilgisini taşır ve onu yeniden yazabilen bir ajan, şifreli birimin onsuz açılamayacağı bir kimlik bilgisini de silebilirdi.

## Ajanlar nasıl tespit edilir

CLI bir işlemi ajan olarak değerlendirirken şu koşullardan herhangi birinin doğru olması yeterlidir:

- `REDIACC_AGENT`, `CLAUDECODE`, `GEMINI_CLI`, `COPILOT_CLI` değişkenlerinden biri `"1"` olarak ayarlanmış ya da `CURSOR_TRACE_ID` herhangi bir değerle ayarlanmış.
- Linux'ta: soy ağacındaki herhangi bir üst işlem bu değişkenlerden birini kendi ortamında barındırıyorsa (`/proc/<pid>/environ` üzerinden). Ajan `env -i` veya sarmalayıcı bir betikle kendi değişkenlerini kaldırsa bile üst zincir CLI'a kimin başlattığını söyler.

Tespit işlem başına bir kez çalışır ve önbelleğe alınır. Devre dışı bırakılamaz. Uzak MCP izni, çağrılarını yürütücüde ajan çağrısı olarak işaretler; tespit gerekmez.

## Tek karar: açık onay VE ilke tavanı

Bir `rdc` komutu çalıştıran her yüzey (CLI, yerel MCP sunucusu, uzak MCP sunucusu, `rdc --proxy` ve web konsolu) aynı karar işlevine sorar, bu yüzden hepsi aynı şeyleri reddeder ve aynı şeylere izin verir. İşlev iki koşul uygular ve bir ajan yalnızca ikisinin de sağlandığı yerde eylem yapar:

1. **İlke tavanı.** Ekip ilkesiyle daraltılmış kuruluş ilkesi, çağıranın hangi komutları, makineleri ve depoları kullanabileceğini ve grand depo değişikliklerine (`allowGrandRepos`) ile küme işlemlerine (`allowClusterOps`) hiç izin verilip verilmediğini belirler. İlke kaydı olmayan bir yapılandırma role göre bir varsayılana döner: sahipler ve yöneticiler eylem yapabilir, üyeler yapamaz. İlke, yalnızca sahiplerin ve yöneticilerin yazdığı ayrı, mühürlü bir kayıttır ([Güvenlik Modeli](/tr/docs/security-model#policy)); hiçbir ajan ve hiçbir CLI komutu onu düzenleyemez.
2. **İnsanın açık onayı.** Tavanın içinde bile bir ajanın, değiştirebileceği grand depoyu veya kümeyi adıyla belirtecek bir insana ihtiyacı vardır:
   - **Yerel ajanlar** (CLI ve yerel MCP): İnsan, ajanı başlatmadan önce terminalde `REDIACC_ALLOW_GRAND_REPO` (depo adları veya `*`) ya da `REDIACC_ALLOW_CLUSTER_OPS` (küme adları veya `*`) değişkenini dışa aktarır. CLI süreç soy ağacını denetler, bu yüzden ajanın oturum ortasında ayarladığı bir değişken sayılmaz ([her işletim sisteminde nasıl doğrulandığı](#how-a-local-opt-in-is-verified-on-each-os)).
   - **Uzak ajanlar** (uzak MCP): Açık onaylar, insanın hesap arayüzünde oluşturduğu iznin parçasıdır ([Uzak sunucu](/tr/docs/ai-agents-mcp#remote-server)).

Açık onay tavanı hiçbir zaman genişletmez: ilkenin kapattığı bir depo, ortam veya izin ne derse desin kapalı kalır. Fork'lar için açık onay gerekmez. CLI'nin tanımlayamadığı bir depo grand sayılır.

**Yıkıcı değişiklikler önce onay ister.** Bir ajan bir grand depoda yıkıcı bir değişiklik için yetkilendirildiğinde (örneğin `repo delete`), yanıt `needs_confirmation` olur. Bir MCP istemcisi kullanıcıya bir onay istemi gösterir; onay istemi olmayan bir istemci, kullanıcıya sorduktan sonra geri göndermesi için bir `confirm` argümanı alır. CLI'de insan komutu `--confirm-grand <repo>` ile yeniden çalıştırır.

Her yanıt kararlı bir kod taşır (`POLICY_DENIED`, `GRAND_REPO_DENIED`, `CLUSTER_OPS_DENIED`, `AGENT_OPT_IN_MISSING`, `FORK_BLOCKED`, `AGENT_BLOCKED`, `CONFIRMATION_REQUIRED`); böylece bir betik veya ajan, iletiye değil koda göre dallanır ([JSON çıktısı](/tr/docs/ai-agents-json-output)).

## Bilgi kapısı modeli

Hassas değişiklikler `passwd(1)` kuralına uyar: bir sırrı değiştirmek için onu önceden bildiğinizi kanıtlayın. **İnsanlar ve ajanlar için simetriktir**. Her ikisi de aynı kapıdan geçer. "Klavye başındayım" adında bir geçiş yolu yoktur.

- `/credentials/cfDnsApiToken` adresinde saklanan bir API token'ını döndürmek istiyorsunuz?
- CLI sorar: "mevcut değer nedir?"
- Ajan (veya insan) düz metni `--current "$OLD"` aracılığıyla sağlar. CLI `$OLD` değerini SHA-256 ile hashler ve şu anda saklanan değerin özeti ile karşılaştırır. Eşleşme geçti respon yazma işlemi gerçekleşir. Uyumsuzluk reddedilir, denetlenir.
- Önceki değeri doğrulamadan rotasyon yapmak için `--rotate-secret` verin (`--current` ile birlikte kullanılamaz). Bu, açıkça rotasyon olarak denetlenir ve yalnızca etkileşimli bir terminaldeki insan için geçerlidir: bir ajan veya stdin'de terminali olmayan bir betik yine de `--current` gerektirir.

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
          "run": "rdc repo secret get mail --key STRIPE_KEY" },
        { "description": "Skip the precondition (rotation, audited)",
          "run": "rdc repo secret set mail --key STRIPE_KEY --value <new> --mode file --rotate-secret" }
      ]
    }
  }]
}
```

**Ajanlar, kendi komutlarını uydurmak yerine `next.options[].run` değerini insana olduğu gibi iletmelidir.** Bu, ajanın var olmayan bir komut uydurması hatasını önler ve gerçek eylemin kontrolünü operatörde tutar. Rotasyon seçeneği, insanın terminalde çalıştırması içindir; ajanın kendisine reddedilir.

### Uygulamalı örnek

```bash
# Gizleme taslağının kısa özetini alma (ajanlar için güvenli).
$ rdc config field get --pointer /credentials/cfDnsApiToken
{"pointer": "/credentials/cfDnsApiToken", "value": "<redacted:secret>:abc12345"}

# Kanıt olmadan üzerine yazmayı deneme: reddedildi.
$ rdc config field set --pointer /credentials/cfDnsApiToken --new '"agent-picked-value"'
✗ Precondition failed: sensitive path requires --current

# Mevcut düz metni sağlama: izin verildi.
$ rdc config field set --pointer /credentials/cfDnsApiToken \
    --current "$OLD_CF_TOKEN" \
    --new   "$NEW_CF_TOKEN"
Set /credentials/cfDnsApiToken
```

Ajan `$OLD_CF_TOKEN` değerine hiç sahip olmadıysa ön koşulu karşılayamaz ve rotasyon reddedilir. Değeri bilen kişi yine de yapabilir: kendi kabuğundan `--current` vererek veya etkileşimli bir terminalde `rdc config field rotate` ile.

## Varsayılan olarak gizleme

Hassas durumu okuyan her `rdc` komutu: `config show`, `config field get`, `config machine list`, `config edit --dump --redacted`: gizli alanlar için düz metin yerine **gizleme taslakları** döndürür:

```
"sshKey":       "<redacted:credential>:9f3a2c1b"
"cfDnsApiToken":"<redacted:secret>:abc12345"
"storages.s3-prod.vaultContent": "<redacted:secret>:1f2e3d4c"
```

Taslağın 8 karakterli onaltılık soneki `sha256(canonicalize(value))` değerinin ilk 8 karakteridir: bir bakışta iki farklı değeri ayırt etmeye yeterli, tersine çevirmeye yeterli değil. Ajan bir taslak kullanarak değeri hiç görmeden değişip değişmediğini takip edebilir.

`--reveal` etkileşimli bir TTY'deki insanlar için gizlemeyi kaldırır. Ajanlar TTY durumundan bağımsız olarak reddedilir. Her verilen izin `reveal_granted` denetim kaydı yazar; her red, aktörün ajan sinyalleri eklenmiş `refused` kaydı yazar.

## Yerel bir açık onay her işletim sisteminde nasıl doğrulanır

`REDIACC_ALLOW_GRAND_REPO` ve `REDIACC_ALLOW_CLUSTER_OPS` her ikisi de, açık onayın ajan tarafından enjekte edilmediğini, insan tarafından ayarlandığını kanıtlamak için soy ağacı doğrulamasına dayanır. Doğrulama Linux, macOS ve Windows'ta çalışır, ancak okuduğu tanık platforma göre farklıdır ve garantinin gücü de öyle:

| Platform | Tanık | Güç |
|---|---|---|
| Linux | Zincir boyunca her işlem için `/proc/<pid>/environ` | Exec-time anlık görüntüsü, çekirdek tarafından sunulan. Bir işlem başlatıldığı şeyi geriye doğru düzenleyemez. |
| macOS | `kern.procargs2` sysctl, `rdc` içine gömülü bir küçük yardımcı tarafından okunur | Linux'ta olduğu gibi aynı exec-time anlık görüntü özelliği. Kök olmadan kendi işlemleriniz için okunabilir. |
| Windows | Her üst işlemin canlı ortam bloğu (PEB), aynı yardımcı tarafından okunur, PID-yeniden kullanım korumasıyla | Daha zayıf: Windows exec-time anlık görüntüsü tutmadığından, kontrol mevcut belleği okur. Üst süreçler yine de bir ajanın normalde çalıştırabileceği herhangi bir şey tarafından yeniden yazılamaz, ancak tanık Linux ve macOS'ta çekirdek tarafından dondurulmuş şekilde değildir. |

macOS ve Windows'ta CLI, okumayı yapmak için paketlenmiş `renet` ikilisini başlatır; yardımcı, izlenen değişkenlerden hangilerini her atanın taşıdığını bildirir ve tüm karar mantığı CLI'de kalır. Yardımcı eksikse, eskiyse veya herhangi bir nedenle başarısız olursa CLI açık onayı doğrulayamaz ve **güvenli biçimde kapalı kalır**: açık onay reddedilir ve hata, bir şeyin yanlış yapıldığını değil, doğrulamanın kullanılamadığını söyler. Çalışan bir kurulum bu iletiyi hiç göstermez; `rdc` yeniden kurulduğunda yardımcı geri gelir.

Her platformda geçerli olan: açık onay, ajan süreci başladığında ortamında zaten bulunmalıdır. Terminalde dışa aktarılır, ardından ajan başlatılır. Değişkeni oturum ortasında ayarlayan bir ajan reddedilir.

## Denetim kaydı

Her değişiklik, her red, her `--reveal` izni `~/.config/rediacc/audit.log.jsonl` dosyasına (mod `0600`, 10 MB'ta döndürülür) bir JSONL satırı yazar. Her satır karma ile zincirlenmiştir: `prevHash` alanı `sha256("<önceki satır>")` değeridir. Herhangi bir satırı değiştirmek, sonraki tüm satırlarda zinciri bozar.

```jsonl
{"ts":"2026-04-21T10:02:47.831Z","actor":{"kind":"agent","agentSignals":["CLAUDECODE"]},"command":"config field set","paths":["/credentials/cfDnsApiToken"],"outcome":"ok","configId":"...","configVersion":48,"prevHash":"sha256:9f3a..."}
{"ts":"2026-04-21T10:02:51.114Z","actor":{"kind":"agent","agentSignals":["CLAUDECODE"]},"command":"config edit","paths":[],"outcome":"refused","reason":"agent environment","prevHash":"sha256:abc1..."}
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

Birincil azaltma yerleştirilmiş olarak gelir: **[depo başına sırlar](/tr/docs/repositories#secrets)** şifreli depo görüntüsünden ayrı bir düzlemde saklanır ve çatal sınırı arasında kopyalanmaz. Bir çatalın konteynerleri boş bir sırlar haritasıyla önyüklenir ve kendilerini üst konteynere göre farklı bir harici asıl olarak tanımlarlar. `rdc repo secret set` ile ayarlayın (compose interpolasyonu için env-modu, tmpfs `secrets:` blokları için file-modu). Mutasyon kapısı simetrik olarak uzanan ve insanlar ve ajanlar varolan bir değerin üzerine yazmak veya silmek için `--current` (passwd-stili ön koşulu) sağlamak zorundadır; `--rotate-secret` (denetlenen rotasyon) terminaldeki insan için alternatiftir.

**Depo arasında izolasyon zorlanır.** Depo B'deki kötü niyetli veya dikkatsiz bir compose dosyası depo A'nın sırlar dizinine referans veremez. Renet'in compose doğrulayıcısı, geçerli depo dışındaki `${REDIACC_NETWORK_ID}` dizinine işaret eden herhangi bir `secrets: file:`, `configs: file:` veya `env_file:` yolunu zor şekilde reddeder ve red `--unsafe` tarafından geçersiz kılınamaz. Savunma derinliği: Rediaccfile bash alt işlemi etrafındaki Landlock sandbox'ı dosya sistem okumasını yalnızca geçerli ağın sırlar dizinine kapsam alır; bu nedenle kötü niyetli bir Rediaccfile'dan `cat /var/run/rediacc/net-<other>/secrets/X` çekirdek katmanında EACCES ile başarısız olur. Aynısı Docker API'si için de geçerlidir: her deponun Docker soketine bir renet politika proxy'si hizmet verir ve bu proxy `--privileged`, host `pid`, `ipc` ve `uts` değerlerini, aygıt isteklerini ve başka bir deponun çalışma zamanına ya da verisine ulaşan bind'ları `403` ile reddeder. Böylece `${DOCKER_SOCKET}` tutan bir konteyner API'yi kullanarak başka bir depoya ulaşamaz; denetlenen yalnızca bir compose dosyası da değildir. Bind kuralını yalnızca operatör, adı verilmiş host dizinleri için, hiçbir konteynerin yazamayacağı root sahipli bir izinle genişletebilir.

İki ek desen kenar durumlarını kapatır:

1. **Üretim kimlik bilgilerini depo dosya sisteminin kendisine takmayın.** Görüntüye işlenmiş bir `.env` dosyası veya `up()` sırasında hacim içinde kalıcı bir kimlik bilgisi çatalın içine reflink'lenmiştir. Depo başına sırlar özelliği yalnızca sırlar düzleminde tuttuğunuz değerleri korur. Zaten LUKS görüntüsünde yaşayan bayt'ları geriye doğru koruyamaz. Baked-in `.env` dosyalarıyla mevcut depo'lar için bunları depo başına sırların içine el ile kaldırın.
2. **Çatalın giden ağını eBPF egress filtreleme ile kısıtlayın** böylece çatal yalnızca localhost ve açık sandbox uç noktalarına ulaşabilir. Rediacc'in depo başına ağ izolasyonu temeldir; depo başına egress allowlist'leri bugün inşa edilmemiştir, ancak yol açıktır.

Rediacc, deploy-time enjeksiyonunu, çatal arasında izolasyonu ve depo arasında izolasyonu yönetir. "Görüntüye bakma" yarısı sizin üzerinizdir.

## Hızlı tarifler

### Bir ajanın tek bir grand depoda çalışmasına izin vermek

```bash
# İnsan olarak, ajanı başlatmadan önce:
export REDIACC_ALLOW_GRAND_REPO='gitlab'
claude              # veya cursor, gemini vb.
```

Ajan artık ilkenin grand depo değişikliklerine izin verdiği yerde `gitlab` deposunu değiştirebilir, başka hiçbir grand depoyu değiştiremez. `repo delete gitlab` gibi yıkıcı bir değişiklik yine onay ister.

### Eski değeri bilmeden bir bulut belirtecini döndürmek

```bash
# İnsan olarak, etkileşimli bir terminalde:
rdc config field rotate --pointer /credentials/cfDnsApiToken --new "$NEW_CF_TOKEN"
```

`--current` olmadan rotasyon insanda kalır. Mevcut değeri bilen bir ajan bunun yerine `rdc config field set --current` kullanır.

### Bir ajanın hangi alanları değiştirebileceğini keşfetme

```bash
rdc config field list --sensitive --output json
```

Her işaretçi şablonunu, türünü (`secret` / `credential` / `pii` / `identifier`) ve sunucu tarafındaki HMAC zarfına dahil edilip edilmediğini döndürür.

## Ayrıca bakınız

- [AI Ajan Entegrasyonuna Genel Bakış](/tr/docs/ai-agents-overview): üst düzey tur
- [MCP sunucusu](/tr/docs/ai-agents-mcp): yerel ve uzak MCP, izinler ve açık onayları
- [Güvenlik Modeli](/tr/docs/security-model): ilke kaydı ve onu kimin yazabileceği
- [Claude Code kurulumu](/tr/docs/ai-agents-claude-code): entegrasyon şablonu
- [JSON çıktı zarfı](/tr/docs/ai-agents-json-output): makine tarafından okunabilir yanıtlar
- [Şifreli yapılandırma deposu](/tr/docs/config-storage): sunucu tarafı kriptografik zorunluluk
- [Hesap güvenliği](/tr/docs/account-security): operatör odaklı güvenlik duruşu
