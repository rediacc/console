---
title: MCP Sunucu Kurulumu
description: Model Context Protocol (MCP) sunucusunu kullanarak yapay zeka ajanlarını Rediacc altyapısına bağlayın.
category: Guides
order: 33
language: tr
sourceHash: "ce5f1392ebaa380b"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
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
| `--allow-grand` | off | Grand (fork olmayan) depolarda yıkıcı işlemlere izin ver |

## Güvenlik

MCP sunucusu iki katmanlı koruma uygular:

### Yalnızca fork modu (varsayılan)

Varsayılan olarak, sunucu **yalnızca fork modunda** çalışır: yazma araçları (`repo_up`, `repo_down`, `repo_delete`, `backup_push`, `backup_pull`, `term_exec`) yalnızca fork depolar üzerinde işlem yapabilir. Ajanlar grand (orijinal) depolara dokunamaz. Tasarım gereği.

> **Depo başına gizli diziler tasarım gereği yalnızca CLI ile yönetilir.** `repo_secret_set` ve `repo_secret_unset` kasıtlı olarak MCP aracı olarak **sunulmamaktadır**. Yazma işlemleri bir `--current <önceki-değer>` ön koşulu (veya doğrulanmamış bir yenilemeyi kabul etmek için `--rotate-secret`) gerektirir; bu adım insan gözetimi gerektirir. Gizli dizi yenilenmesini önermesi gereken ajanlar, özeti doğrulamak için `repo_secret_get` çağırmalı, ardından operatöre yönelik CLI komutunu JSON hata zarfının `next.options[].run` alanı üzerinden kullanıcıya iletmelidir. Tam örüntü için [Yapay Zeka Ajanı Güvenliği](/en/docs/ai-agents-safety#structured-next-action-hints) sayfasına, kullanıcıya yönelik nasıl yapılır kılavuzu için [Depolar § Gizli Diziler](/en/docs/repositories#secrets) sayfasına bakın.

Grand depoları değiştirebilmesi için ajanı `--allow-grand` ile başlatın:

```json
{
  "mcpServers": {
    "rdc": {
      "command": "rdc",
      "args": ["mcp", "serve", "--allow-grand"]
    }
  }
}
```

`REDIACC_ALLOW_GRAND_REPO` ortam değişkenini tek bir repo adına, virgülle ayrılmış bir repo adı listesine (örneğin `repo1,repo2,repo3`) ya da tüm repolar için `*` değerine de ayarlayabilirsiniz. Girişlerin etrafındaki boşluklar yoksayıldığı için `repo1, repo2` de çalışır. Makine düzeyinde erişim (örneğin repo belirtmeden `term connect -m <machine>`) hâlâ `*` gerektirir; repo adlarından oluşan bir liste bu erişimi açmaz.

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
- Hem yerel hem de bulut adaptörleriyle çalışır
- Bir komuttaki hatalar diğerlerini etkilemez
