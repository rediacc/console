---
title: MCP Sunucu Kurulumu
description: Model Context Protocol (MCP) sunucusunu kullanarak yapay zeka ajanlarını Rediacc altyapısına bağlayın.
category: Guides
tags:
  - ai-agents
  - cli
subcategory: ai-agents
order: 33
language: tr
sourceHash: "5ffb60357e13aeab"
sourceCommit: "a2b1f5471f48c44fb704157f615369df9c354832"
---

## Genel Bakış

`rdc mcp serve` komutu, yapay zeka ajanlarının altyapınızı yönetmek için kullanabileceği yerel bir MCP (Model Context Protocol) sunucusu başlatır. Sunucu stdio taşıma yöntemini kullanır; yapay zeka ajanı sunucuyu bir alt süreç olarak başlatır ve JSON-RPC üzerinden iletişim kurar.

**Ön koşullar:** `rdc` kurulu ve en az bir makine ile yapılandırılmış olmalıdır.

## Claude Code

Projenizin `.mcp.json` dosyasına ekleyin:

```json
{
  "mcpServers": {
    "rdc": {
      "command": "rdc",
      "args": ["mcp", "serve"]
    }
  }
}
```

Veya adlandırılmış bir yapılandırma ile:

```json
{
  "mcpServers": {
    "rdc": {
      "command": "rdc",
      "args": ["mcp", "serve", "--config", "production"]
    }
  }
}
```

## Cursor

Ayarlar → MCP Sunucuları → Sunucu Ekle yolunu izleyin:

- **Ad**: `rdc`
- **Komut**: `rdc mcp serve`
- **Taşıma**: stdio

## Kullanılabilir Araçlar

<!-- >>> translated-table: mcp-tools -->

| Araç | Yıkıcı | Açıklama |
|---|---|---|
| `backup_browse` | hayır | Bir deponun içerdiği dosyaları listeler. |
| `backup_cancel` | hayır | Uzak bir makinede çalışan yedeklemeyi iptal eder. |
| `backup_check` | hayır | Saklanan bir anlık görüntünün parola ile açılabildiğini, bir dosyayı geri yükleyerek kanıtlar. |
| `backup_immutability_show` | hayır | Geçerli gecikmeli silme penceresini gösterir. |
| `backup_list` | hayır | Bir makinedeki yedekleme çıktılarını listeler. |
| `backup_manifests` | hayır | Sunucuda kayıtlı yedek anlık görüntü bildirimlerini listeler. |
| `backup_reconcile` | evet | Bir deponun saklanan bayt defterini depolamanın gerçekte tuttuğu değere sıfırlar (hiçbir parçayı silmez). |
| `backup_repair` | evet | Depolamanın kaybettiği veya hatalı tuttuğu parçaları, bu makinenin çapasından yeniden yükler. |
| `backup_restore` | evet | Bir yedekleme çıktısını canlı bir depoya dönüştürür. |
| `backup_retention` | hayır | Sunucunun uyguladığı anlık görüntü saklama ilkesini gösterir. |
| `backup_retention_preview` | hayır | Bir sonraki temizliğin hangi anlık görüntüleri sileceğini ve ne kadar alan açacağını gösterir. |
| `backup_run` | hayır | Yedeklemeyi hemen çalıştırır. |
| `backup_snapshot` | hayır | Parça deposunun anlık görüntüsünü yükler: önce tam envanter, ardından değişen hücreler. |
| `backup_status` | hayır | Uzak bir makinedeki yedekleme durumunu ve zamanlayıcı durumunu gösterir. |
| `backup_strategy_list` | hayır | Tüm yedekleme stratejilerini listeler. |
| `backup_strategy_show` | hayır | Bir yedekleme stratejisinin ayrıntılarını gösterir. |
| `backup_toc-key_sync` | hayır | Deponun listeleme anahtarını makinesine kurar veya farklı olanı değiştirir. |
| `backup_undelete` | hayır | Gecikmeli bir anlık görüntü silme işlemini yürürlüğe girmeden önce iptal eder. |
| `backup_usage` | hayır | Yedekleme depolama kotasını, saklanan baytları ve depo başına kullanımı gösterir. |
| `backup_verify` | hayır | Bir deponun yedekleme çapasını parça deposuna karşı doğrular. |
| `cluster_snapshot_list` | hayır | Kümenin grup anlık görüntülerini listeler. |
| `cluster_status` | hayır | Tüm kümeleri listeler veya bir küme adı verilirse o kümenin tam yapılandırmasını gösterir. |
| `config_access_list` | hayır | Yapılandırmanın erişim anahtarlarını listeler. |
| `config_prune` | hayır | Yerel yapılandırma dosyasındaki ~/.config/rediacc/<config>.json gereksiz yükü temizler. |
| `config_reconcile` | hayır | Yerel durum kovasını makinelerin gerçek durumundan yeniden oluşturur (renet list all). |
| `config_show` | hayır | Geçerli yapılandırmanın ayrıntılarını gösterir. |
| `credits` | hayır | Bu hesabın kalan kredi bakiyesini gösterir. |
| `datastore_list` | hayır | Adlandırılmış veri depolarını, nerelere bağlı olduklarını ve neler içerdiklerini listeler. |
| `datastore_snapshot_list` | hayır | Bir veri deposunun anlık görüntülerini listeler. |
| `datastore_status` | hayır | Bir veri deposunu gösterir: arka ucu, bağlantısı, kullanımı, depoları ve anlık görüntüleri. |
| `feedback_list` | hayır | Bu makinenin görebildiği geri bildirim raporlarını listeler: kimlik, kısa parmak izi, durum ve tarihler. |
| `feedback_report` | hayır | Son başarısız komuttan (--last), kayıtlı bir komuttan (--command <n>) veya yalnızca bir mesajdan rapor oluşturur, tam olarak nelerin gönderileceğini yazdırır ve onaydan sonra gönderir. |
| `feedback_show` | hayır | Bir geri bildirim raporunu kimliğiyle (veya benzersiz bir önekiyle) durumu, görülme sayısı ve tarihleriyle gösterir. |
| `job_cancel` | evet | Çalışan bir ayrık işi iptal eder. |
| `job_dismiss` | evet | İş biletlerinden yerelde vazgeçer: bekleyen adımları bırakılır ve bilet artık görünmez. |
| `job_gc` | evet | Biten işleri ve günlüklerini kaldırır. |
| `job_list` | hayır | Bir makinedeki ayrık işleri en yeniden başlayarak listeler. |
| `job_logs` | hayır | Bir ayrık işin olay günlüğünü yeniden oynatır veya canlı izler. |
| `job_status` | hayır | Bir ayrık işin durumunu gösterir. |
| `job_wait` | hayır | Bir işin bitmesi için en fazla 50 sn bekler. |
| `legal` | hayır | Yasal belgelerin bağlantılarını CLI dilinde, bağlayıcı İngilizce bağlantılarla birlikte yazdırır; ayrıca güncel Hizmet Şartları sürümünü sağlama toplamı ve arşiv URL'siyle, kayıtlı kabulü (oturum açıkken hesap sunucusundan, anonimken bu yapılandırmadan) ve sözleşme tarafını gösterir. |
| `machine_access_show` | hayır | Bir makineye bağlı erişim anahtarlarını ve her birinin orada çözümlediği aralıkları gösterir. |
| `machine_add` | hayır | SSH ile ulaşılabilen mevcut bir makineyi kaydeder. |
| `machine_containers` | hayır | Bir makinedeki Docker konteynerlerini listeler. |
| `machine_converge` | evet | Hâlâ eski bir çalışma zamanı düzeninde çalışan her depo arka plan hizmetini, güncel düzene geçmesi için tek tek yeniden başlatır. |
| `machine_deprovision` | evet | Bulutta sağlanmış bir makineyi yok eder ve yapılandırmadan kaldırır. |
| `machine_gpu_list` | hayır | Bir makinede algılanan GPU'ları, belirtimlerinin tanımladığı CDI aygıt adlarını ve her aygıtın verildiği depoları listeler. |
| `machine_health` | hayır | CI/CD işlem hatları için bir makinenin sağlığını denetler. |
| `machine_infra_show` | hayır | Bir makinenin altyapı yapılandırmasını (temel alan adı, genel IP'ler, portlar), paylaşılan TLS ayarlarını (sertifika e-postası, CF DNS belirteci) ve Cloudflare bölge kimliğini gösterir. |
| `machine_list` | hayır | Makineleri listeler. |
| `machine_provider_add` | hayır | Bir bulut sağlayıcısı ekler. |
| `machine_provider_list` | hayır | Makine sağlama için yapılandırılmış bulut sağlayıcılarını listeler. |
| `machine_provider_remove` | evet | Bir bulut sağlayıcı yapılandırmasını kaldırır. |
| `machine_provision` | evet | OpenTofu ile bir bulut sağlayıcıda yeni bir makine sağlar. |
| `machine_prune` | evet | Bir makineden sahipsiz veri deposu kaynaklarını ve eskimiş anlık görüntüleri kaldırır. |
| `machine_remove` | evet | Bir makineyi yapılandırmadan kaldırır. |
| `machine_repos` | hayır | Bir makineye dağıtılmış depoları listeler. |
| `machine_restart-services` | evet | Değiştirilmiş bir ikili dosyayı hâlâ çalıştıran renet arka plan hizmetlerini, her birinin yeni ikili dosyada etkin olduğunu doğrulayarak birer birim hâlinde kurulu olana geçirir. |
| `machine_scan-keys` | hayır | Makinenin SSH ana makine anahtarlarını yerel yapılandırmaya kaydeder. |
| `machine_services` | hayır | Bir makinedeki Rediacc tarafından yönetilen systemd hizmetlerini listeler (ad, durum, alt durum, yeniden başlatma sayısı, bellek, ada çözülmüş depo ve özgün değer repository_guid içinde). |
| `machine_setup` | hayır | Bir makinenin kurulumunu tamamlar: renet'i kurar ve makineyi depo barındırmaya hazırlar. |
| `machine_status` | hayır | Bir makinenin bağlantı ayrıntılarını (IP, kullanıcı, port, veri deposu), sistem bilgisini, konteynerlerini (ada çözülmüş depo, özgün değer repository_guid içinde, alan adı, autoRoute), hizmetlerini (ada çözülmüş depo), depolarını (GUID'den çözülmüş ad, özgün değer guid içinde) ve kaynak kullanımını getirir. |
| `repo_admin_fsck` | hayır | Yapılandırma başvurularını (dallar/HEAD) bir makinede bulunan nesnelere karşı doğrular; boşta kalan başvuruları ve sahipsiz commit'leri bildirir. |
| `repo_cat` | hayır | Bir depodaki dosyanın sınırlı bir bölümünü stdout'a okur (tanılar stderr'e gider). |
| `repo_checkout` | evet | Değişmez bir commit'i (veya dal ucunu) reflink ile yeni, yazılabilir bir çalışma çatalına kopyalar ve HEAD'i oraya yönlendirir. |
| `repo_commit` | evet | Bağlı bir çalışma çatalını yeni, değişmez bir commit'e dondurur (git benzeri). |
| `repo_create` | evet | Yeni bir depo oluşturur. |
| `repo_delete` | evet | Bir depoyu ve verilerini siler. |
| `repo_diff` | hayır | İki copy-on-write çatallanmış depo arasında git tarzı dosya düzeyinde fark. |
| `repo_down` | evet | Bir deponun Docker konteynerlerini durdurur (Rediaccfile down çalıştırır). |
| `repo_exec` | evet | Bir depo konteynerinin içinde komut çalıştırır. |
| `repo_fork` | evet | Bir deponun YENİ bir GUID ve networkId'ye sahip, neredeyse anlık bir CoW çatalını oluşturur (tamamen bağımsız kopya). |
| `repo_gc` | evet | Erişilebilirliğe dayalı çöp toplama: bir makinede hiçbir dal/HEAD'in erişmediği değişmez commit nesnelerini siler. |
| `repo_health` | hayır | Bir deponun Rediaccfile health() denetimlerini çalıştırır ve 0 (tamam), 1 (uyarı) veya 2 (hata) koduyla çıkar. |
| `repo_list` | hayır | Bir makinedeki depoları listeler. |
| `repo_log` | hayır | Bir çalışma çatalının geçerli commit'inden (veya bir commit başvurusundan) erişilebilen commit geçmişini, 'rdc repo commit' tarafından kaydedilen üst zincirini izleyerek yazdırır. |
| `repo_logs` | hayır | Bir deponun konteynerlerinden uygulama günlüklerini gösterir. |
| `repo_merge` | evet | Bir kaynak commit'i/çatalı, yaşam döngüsünü bozmadan hedef çalışma çatalına birleştirir. |
| `repo_migrate` | evet | Bir depoyu en az kesintiyle başka bir makineye taşır: iki aşamalı kopya (çalışırken toplu eşitleme, ardından kısa durdurma, fark eşitlemesi ve hedefte başlatma) ve DNS geçişi. |
| `repo_pull` | evet | Bir depoyu başka bir makineden çeker. |
| `repo_push` | evet | Bir deponun yedeğini depolamaya veya doğrudan başka bir makineye gönderir. |
| `repo_replicate` | hayır | Bir deponun salt okunur kopyalarını sağlar. |
| `repo_replicate_remove` | evet | Bir kopya kümesini kaldırır: oluşturulan k8s nesnelerini (etiketle sınırlı) siler, çatal veri depolarını atar, anlık görüntüsünü bırakır ve durumu unutur. |
| `repo_replicate_status` | hayır | Yönetilen kopya kümelerini gösterir: kopyalar, barındıran düğümler, çatal veri depoları, anlık görüntü ve yenileme zamanları. |
| `repo_secret_get` | hayır | Bir sırrın SHA-256 özetini gösterir. |
| `repo_secret_list` | hayır | Sır anahtarlarını ve kiplerini listeler (değerleri veya özetleri asla göstermez). |
| `repo_status` | hayır | Bir deponun durumunu getirir (bağlama durumu, Docker arka plan hizmetinin çalışıp çalışmadığı, konteyner sayısı, disk kullanımı). |
| `repo_trim` | hayır | Bağlı depolardan veri deposu havuzu alanını geri kazanır (çevrimiçi, kesintisiz). |
| `repo_up` | evet | Bir depoyu dağıtır veya günceller (renet compose üzerinden Rediaccfile up çalıştırır, konteynerleri başlatır). |

<!-- <<< translated-table -->

<!-- >>> translated-table: mcp-tools-local -->

| Araç | Yıkıcı | Açıklama |
|---|---|---|
| `cluster_kubeconfig` | hayır | Kümenin kontrol düğümünden kubeconfig dosyasını SSH ile alır ve kubectl için yerelde (0600) önbelleğe yazar. |
| `config_audit_log` | hayır | Bu yapılandırma üzerinden yapılan değişikliklerin denetim günlüğünü okur. |
| `config_audit_verify` | hayır | Denetim günlüğünün karma zincirinin kurcalanmadığını doğrular. |
| `config_current` | hayır | Etkin yapılandırmayı gösterir: ad, dosya, çözümlenen sunucu ve kanal, belirteç durumu. |
| `config_list` | hayır | Tüm yapılandırma dosyalarını listeler. |
| `machine_infra_cert_status` | hayır | Önbellekteki sertifika envanterini gösterir. |
| `server_status` | hayır | Kurulu bir sunucunun sağlığını, katmanını, sertifikasını ve imajını gösterir. |
| `version` | hayır | CLI sürümünü, platformu, güncelleme kanalını ve etkin lisansı yazdırır: oturum açıkken plan, oturumsuzken "anonymous (FREE per repository)", hesap sunucusuna ulaşılamıyorsa "unknown (server unreachable)". |

<!-- <<< translated-table -->

### Okuma Araçları (güvenli, yan etkisi yok)

| Araç | Açıklama |
|------|----------|
| `machine_query` | Bir makinenin sistem bilgisini, konteynerlerini, servislerini ve kaynak kullanımını gösterir |
| `machine_containers` | Docker konteynerlerini durum, sağlık, kaynak kullanımı, etiketler ve otomatik yönlendirme alan adıyla listeler |
| `machine_services` | Rediacc tarafından yönetilen systemd servislerini listeler (ad, durum, alt durum, yeniden başlatma sayısı, bellek, ait olduğu depo) |
| `machine_repos` | Dağıtılmış depoları listeler (ad, GUID, boyut, bağlama durumu, Docker durumu, konteyner sayısı, disk kullanımı, değiştirilme tarihi, Rediaccfile varlığı) |
| `machine_health` | Makine üzerinde sağlık kontrolü çalıştırır (sistem, konteynerler, servisler, depolama) |
| `machine_list` | Yapılandırılmış tüm makineleri listeler |
| `config_repositories` | Yapılandırılmış depoları ad-GUID eşlemeleriyle listeler |
| `config_show_infra` | Bir makine için altyapı yapılandırmasını gösterir (temel alan adı, genel IP'ler, TLS, Cloudflare bölgesi) |
| `config_providers` | Makine sağlama için yapılandırılmış bulut sağlayıcılarını listeler |
| `agent_capabilities` | Kullanılabilir tüm rdc CLI komutlarını argümanları ve seçenekleriyle listeler |
| `repo_secret_list` | Bir deponun gizli dizi adlarını ve teslim modlarını listeler (değerleri veya özetleri hiçbir zaman döndürmez). Okuma güvenlidir. |
| `repo_secret_get` | Bir gizli dizinin SHA-256 özetini ve teslim modunu döndürür. Düz metin değeri tasarım gereği hiçbir zaman döndürülmez. Bir gizli dizinin var olduğunu veya yenilendiğini doğrulamak için kullanın. |

### Yazma Araçları (yıkıcı)

| Araç | Açıklama |
|------|----------|
| `repo_create` | Bir makinede yeni şifreli depo oluşturur |
| `repo_up` | Depoyu dağıtır/günceller (Rediaccfile up çalıştırır, konteynerleri başlatır). İlk dağıtımda veya pull sonrasında `mount` kullanın |
| `repo_down` | Depo konteynerlerini durdurur. Varsayılan olarak bağlantıyı KESMEZ. LUKS konteynerini de kapatmak için `unmount` kullanın |
| `repo_delete` | Depoyu siler (konteynerleri, hacimleri, şifreli imajı yok eder). Kimlik bilgileri kurtarma için arşivlenir |
| `repo_fork` | Yeni GUID ve networkId ile CoW fork oluşturur (tam bağımsız kopya, çevrimiçi fork desteği var) |
| `backup_push` | Depo yedeğini depolama alanına veya başka bir makineye gönderir (aynı GUID -- yedek/göç, fork değil) |
| `backup_pull` | Depolama alanından veya makineden depo yedeği çeker. Çektikten sonra `repo_up` ile dağıtın (mount=true) |
| `machine_provision` | OpenTofu kullanarak bulut sağlayıcısında yeni makine sağlar |
| `machine_deprovision` | Buluttan sağlanan makineyi yok eder ve yapılandırmadan kaldırır |
| `config_add_provider` | Makine sağlama için bulut sağlayıcı yapılandırması ekler |
| `config_remove_provider` | Bulut sağlayıcı yapılandırmasını kaldırır |
| `term_exec` | SSH üzerinden uzak makinede komut çalıştırır |

## Örnek İş Akışları

**Makine durumunu kontrol etme:**
> "Üretim makinemin durumu nedir?"

Ajan `machine_query` aracını çağırır → sistem bilgisi, çalışan konteynerler, servisler ve kaynak kullanımını döndürür.

**Uygulama dağıtma:**
> "Gitlab'ı hazırlık makineme dağıt"

Ajan `repo_up` aracını `name: "gitlab"` ve `machine: "staging"` parametreleriyle çağırır → depoyu dağıtır, başarı/başarısızlık sonucunu döndürür.

**Başarısız bir servisi hata ayıklama:**
> "Nextcloud'um yavaş, sorunun ne olduğunu bul"

Ajan `machine_health` → `machine_containers` → günlükleri okumak için `term_exec` araçlarını çağırır → sorunu tespit eder ve çözüm önerir.

## Yapılandırma Seçenekleri

| Seçenek | Varsayılan | Açıklama |
|---------|------------|----------|
| `--config <name>` | (varsayılan yapılandırma) | Tüm komutlar için kullanılacak adlandırılmış yapılandırma |
| `--timeout <ms>` | `120000` | Varsayılan komut zaman aşımı (milisaniye) |

## Güvenlik

MCP sunucusu iki katmanlı koruma uygular:

### Yalnızca fork modu (varsayılan)

Varsayılan olarak, sunucu **yalnızca fork modunda** çalışır: yazma araçları (`repo_up`, `repo_down`, `repo_delete`, `backup_push`, `backup_pull`, `term_exec`) yalnızca fork depolar üzerinde işlem yapabilir. Ajanlar grand (orijinal) depolara dokunamaz. Tasarım gereği.

> **Depo başına gizli diziler tasarım gereği yalnızca CLI ile yönetilir.** `repo_secret_set` ve `repo_secret_unset` kasıtlı olarak MCP aracı olarak **sunulmamaktadır**. Yazma işlemleri bir `--current <önceki-değer>` ön koşulu (veya doğrulanmamış bir yenilemeyi kabul etmek için `--rotate-secret`) gerektirir; bu adım insan gözetimi gerektirir. Gizli dizi yenilenmesini önermesi gereken ajanlar, özeti doğrulamak için `repo_secret_get` çağırmalı, ardından operatöre yönelik CLI komutunu JSON hata zarfının `next.options[].run` alanı üzerinden kullanıcıya iletmelidir. Tam örüntü için [Yapay Zeka Ajanı Güvenliği](/en/docs/ai-agents-safety#structured-next-action-hints) sayfasına, kullanıcıya yönelik nasıl yapılır kılavuzu için [Depolar § Gizli Diziler](/en/docs/repositories#secrets) sayfasına bakın.

Grand depoları değiştirebilmesi için ajanı başlatmadan önce terminalinizde `REDIACC_ALLOW_GRAND_REPO` ortam değişkenini dışa aktarın:

```bash
export REDIACC_ALLOW_GRAND_REPO='gitlab'   # bir depo
# ya da 'repo1,repo2,repo3' (girişlerin etrafındaki boşluklar yoksayılır), ya da tüm depolar için '*'
claude   # ya da cursor, gemini, vb.
```

Geçersiz kılma, işlem soy ağacına karşı doğrulanır: ajanın kendisinin ortamında zaten bulunması gereken zamanında sayılır, yani ajanı (ve ajanın başlattığı MCP sunucusunu) başlatmadan önce dışa aktarıldığı anlamına gelir. Ajan oturum ortasında değişkeni ayarlayarak kendisine erişim veremez. Bu amaçla kasıtlı olarak sunucu bayrağı yoktur: MCP sunucusu argümanlarındaki bayrak, onu oraya koyanı kanıtlamaz, oysa soy ağacı kontrolü kanıtlar. Makine düzeyinde erişim (örneğin `term connect <machine>` depo belirtmeden) hâlâ `*` gerektirir; repo adlarından oluşan bir liste bu erişimi açmaz.

### Depo başına SSH anahtarları ve sunucu tarafı sandbox

Her deponun kendi SSH anahtar çifti vardır. Genel anahtar, tüm SSH oturumlarını `renet sandbox-gateway <repo-name>` üzerinden yönlendiren bir `command=` önekiyle `authorized_keys` dosyasına dağıtılır; bu sunucu tarafı ForceCommand, VS Code dahil hiçbir istemci tarafından atlatılamaz.

**Nasıl çalışır:**
1. `rdc repo create` veya `rdc repo fork`, depo başına benzersiz bir ed25519 anahtar çifti üretir
2. Genel anahtar uzak sunucuya `command="renet sandbox-gateway <name>"` ile dağıtılır
3. Bu anahtarı kullanan her SSH bağlantısı ağ geçidinden geçer ve şu kısıtlamalar uygulanır:
   - **Landlock LSM**, çekirdek düzeyinde dosya sistemi kısıtlamaları, deponun bağlama yoluyla sınırlı
   - **OverlayFS ev dizini katmanı**, `$HOME` yazmaları depo başına yakalanır, okumalar gerçek ev dizinine düşer
   - **Depo başına TMPDIR**, `<datastore>/.interim/sandbox/<name>/tmp/` konumunda
   - **Docker erişimi**, deponun izole Docker soketi üzerinden
   - **Ayrıcalık düşürme**, evrensel kullanıcıya (`rediacc`)
4. Deponun `.envrc` dosyası Docker ve ortam kurulumu için otomatik olarak yüklenir

**Okuma/Yazma izni**: depo bağlama yolu, depo başına sandbox çalışma alanı, ev dizini (katman üzerinden), Docker soketi
**Salt okunur izni**: sistem yolları (`/usr`, `/bin`, `/etc`, `/proc`, `/sys`)
**Engellenen**: diğer depoların bağlama yolları, izin listesi dışındaki sistem dosyaları

**VS Code entegrasyonu**: Her depo, `<datastore>/.interim/sandbox/<name>/.vscode-server/` konumunda kendi VS Code sunucusu kurulumuna sahiptir. Birden fazla depo, bağımsız sandbox ortamlarıyla aynı anda açık olabilir; depolar arasında sunucu paylaşımı yapılmaz.

Bu durum yanal hareketi engeller. Bir ajan fork'a shell erişimi kazansa bile, aynı makinedeki diğer depoları okuyamaz veya değiştiremez. Makine düzeyinde SSH (depo belirtmeksizin), takım anahtarını kullanır ve sandbox'lanmaz.

## Mimari

MCP sunucusu durumsuz (stateless) çalışır. Her araç çağrısı, `rdc`'yi `--output json --yes --quiet` bayraklarıyla izole bir alt süreç olarak başlatır. Bu şu anlama gelir:

- Araç çağrıları arasında durum sızıntısı olmaz
- Mevcut `rdc` yapılandırmanızı ve SSH anahtarlarınızı kullanır
- Bir komuttaki hatalar diğerlerini etkilemez
