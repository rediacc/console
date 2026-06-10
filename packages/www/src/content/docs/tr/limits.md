---
title: Limitler ve Kotalar
description: >-
  Rediacc depoları, hizmetleri, ağ yapılandırması ve depolamaya uygulanan
  limitler, maksimum değerler ve kotalar için başvuru kaynağı.
category: Reference
order: 99
language: tr
sourceHash: "8bd2b499c6b8eff6"
sourceCommit: "ff9c470edf8760f63f12baf681c04db51a0c202f"
---

# Limitler ve Kotalar

Rediacc dağıtım limitleri. Üçü katıdır ve donanım eklenerek değiştirilemez: depo başına 61 hizmet sınırlaması (ağ adres alanı tahsisi), çekirdek 6.1 minimumu (CRIU gereksinimleri) ve Let's Encrypt'in kayıtlı alan adı başına haftalık 50 joker sertifika yayınlama sınırlaması. Diğer her şey esnek: donanım eklediğinizde hareket eder. Bir topolojiye geçmeden önce farkı bilin.

---

## Depo Başına Hizmetler

Her depo aynı anda çalışan en fazla **61 hizmeti** destekler.

Bu, her depoya ayrılan ağ adres alanı tarafından belirlenen katı bir limittir. Her hizmet kendi özel IP adresini alır ve her deponun adres bloğu tam olarak 61 hizmet yuvası barındırır.

Bakınız: bir depoda 61 hizmete ulaşmak genellikle Rediacc kısıtlaması değil, bir mimari sorunun göstergesidir. Çözüm, yardımcı konteynerları ve izleme ajanlarını kendi izolasyon sınırına sahip başka bir depoya taşımak veya uygulamanın kendisindeki bağımsız çalışan süreç sayısını azaltmaktır.

---

## Makine Başına Depolar

Rediacc tarafından uygulanan katı bir üst sınır yoktur. Pratik limit, makinenizin kaynaklarına bağlıdır:

| Kaynak | Etki |
|--------|------|
| Disk alanı | Her depo şifrelenmiş bir disk görüntüsüdür. 1 TB kullanılabilir depolamaya sahip bir makine birçok depo barındırabilir, ancak tüm görüntülerin toplam boyutu veri deposu havuzuna sığmalıdır. |
| RAM | Çalışan her depo kendi Docker daemon ve konteynerlerini başlatır. Bellek kullanımı iş yüklerinize bağlıdır. |
| CPU | Paralel depo işlemleri (başlatma, yedekleme, çatallama) geçici CPU yükü ekler. |

**Tipik dağıtımlar** makine başına 10 ila 50 depo arasında sorunsuz çalıştırır. 32 GB ve üzeri RAM ve 500 GB ve üzeri depolamaya sahip makineler düzenli olarak 100'den fazla depo çalıştırır.

### Sistem genelinde ağ kimliği limiti

Her depoya, özel IP adres aralığını hesaplamak için kullanılan benzersiz bir **ağ kimliği** (numara) atanır. Bu havuz, aynı Rediacc yapılandırması tarafından yönetilen tüm makineler ve depolar arasında paylaşılır.

| Limit | Değer |
|-------|-------|
| Toplam kullanılabilir ağ kimlikleri | ~261,944 |
| Kapsam | Yapılandırma başına (yapılandırmadaki tüm makineler arasında paylaşılır) |

Bir depo silindiğinde, ağ kimliği serbest bırakılır ve yeniden kullanılabilir hale gelir. Rediacc kimlikleri sıralı olarak atar ve yalnızca ileri sayaç tavana yaklaştığında serbest bırakılmış boşlukları tarar. Pratikte bu limite asla ulaşılmaz. Tek bir yapılandırmanın ömrü boyunca yüz binlerce depo oluşturmayı ve izlemeyi gerektirir.

---

## Çatallar

Bir deponun aktif çatal sayısında limit yoktur. Her çatal, kendi şifrelenmiş depolaması, ağ adresleri ve Docker daemon ile tam bir yazma üzerine kopyalama klonudur. Çatallar, oluşturulduktan sonra kendilerine yazılan verilerle orantılı disk alanı tüketir (ana deponun tam boyutuyla değil).

---

## Harici Portlar

### Her zaman aktif portlar

Portlar yalnızca `rdc config infra set --public-ipv4` ile genel bir IP yapılandırdığınızda açılır. O zamana kadar makinede açık port yoktur. Yapılandırıldıktan sonra:

| Port | Protokol | Amaç |
|------|----------|------|
| 80 | TCP | HTTP: Traefik tarafından yönetilir; yapılandırılmamış alan adları için 404 döndürür, hiçbir hizmete iletilmez |
| 443 | TCP | HTTPS: yukarıdakiyle aynı; eşleşen rotası olmayan istekler proxy katmanında reddedilir |
| 10000–10010 | TCP | Rediacc tarafından yönetilen TCP yönlendirmesi için dinamik aralık |

HTTP/HTTPS, ham TCP portlarından farklıdır: 80 ve 443 portları açık olmasına rağmen, her istek ters proxy tarafından açık bir yönlendirme tablosuna göre doğrulanır. Yapılandırılmış bir hizmet ve eşleşen alan adı olmadan hiçbir uygulama koduna erişilmez ve hiçbir veri ifşa edilmez.

### İsteğe bağlı TCP/UDP yönlendirme

Diğer tüm portlar (veritabanları, önbellekler, mesaj aracıları, DNS, e-posta) **varsayılan olarak kapalıdır** ve açıkça açılmalıdır. Bu, makinenin saldırı yüzeyini minimum düzeyde tutar.

Belirli bir hizmetten port açmak için:

```yaml
labels:
  - "rediacc.tcp_ports=5432"   # expose PostgreSQL from this container
  - "rediacc.udp_ports=53"     # expose DNS from this container
```

Makine düzeyinde port açmak için (tüm hizmetlere açık):

```bash
rdc config infra set -m server-1 --tcp-ports 25,587,993   # mail server
rdc config infra push -m server-1
```

> Belirli bir gereksiniminiz olmadıkça veritabanı veya önbellek portlarını asla dışarıya açmayın. Web hizmetleri için HTTPS otomatik rotalarını kullanın ve depolama hizmetlerini dahili tutun.

---

## Veri Deposu

Veri deposu, makine ilk kurulduğunda oluşturulan sabit boyutlu bir havuzdur. Boyutu otomatik olarak büyümez.

- **Minimum önerilen boyut**: 50 GB
- **Maksimum boyut**: Diskinizle sınırlıdır. Tek bir havuz tam bir diski kaplayabilir.
- **Yeniden boyutlandırma**: Mevcut bir havuzu genişletmek için `rdc datastore resize` kullanın. Küçültme desteklenmez.
- **Dosya sistemi**: Rediacc, yazma üzerine kopyalama anlık görüntüleri ve verimli çatallama için dahili olarak BTRFS kullanır. Tam üretim kararlılığı için **Linux 6.1 veya üzeri** çekirdek çalıştıran bir makine gerektirir.

Her depo görüntüsünün oluşturma sırasında belirlenen sabit bir maksimum boyutu vardır (varsayılan: 10 GB). Tek bir depoyu genişletmek için `rdc repo resize` kullanın. Tüm depo maksimum boyutlarının toplamı, veri deposu havuz boyutunu aşamaz.

---

## HTTP Rotaları

`rediacc.service_port` etiketine sahip her hizmet otomatik olarak bir HTTPS rotası alır. Rotalı hizmet sayısında limit yoktur (depo başına 61 hizmet maksimumuna tabidir).

Joker TLS sertifikaları, ilk dağıtımda Let's Encrypt (Cloudflare DNS-01 doğrulaması) aracılığıyla depo başına verilir. Let's Encrypt, **kayıtlı alan adı başına haftada 50 sertifika** ile sınırlar. Rediacc, depo başına (hizmet başına değil) tek bir joker sertifika kullandığından, tek bir haftada 50'den fazla yeni depo oluşturan bir dağıtım bu tavana ulaşır.

Çatallar, ana deponun mevcut joker sertifikasını yeniden kullanır ve herhangi bir sertifika kotası tüketmez.

---

## Kontrol Noktası / Geri Yükleme (CRIU)

CRIU aracılığıyla canlı geçiş aşağıdaki kısıtlamalara sahiptir:

- **İsteğe bağlı**: Yalnızca `rediacc.checkpoint=true` etiketine sahip konteynerler kontrol noktasına alınır. Veritabanları ve durumsuz hizmetler varsayılan olarak hariç tutulur ve geri yüklemede sıfırdan başlar.
- **Çekirdek gereksinimi**: Hem kaynak hem de hedef makinede Linux 6.1 veya üzeri.
- **Ağ modu**: CRIU, ana bilgisayar ağ modunu gerektirir. Özel ağ yapılandırmaları kullanan konteynerlerin kontrol noktası alınamaz.
- **Bellek**: Kontrol noktası veri boyutu, kontrol noktasına alınan sürecin yerleşik belleğine eşittir. Bellekteki büyük veri kümeleri (örneğin, 4 GB veri önbelleğe alan bir Node.js uygulaması) 4 GB kontrol noktası dosyaları üretir.
- **TCP bağlantıları**: Uygulamalar, geri yükleme sırasında bağlantı kaybını tolere etmelidir. Aktif TCP bağlantıları **korunmaz**, geri yüklenen süreç soketleri kapalı olarak görür ve yeniden bağlanmalıdır. Bu, hem aynı makine hem de makineler arası geri yükleme yollarına uygulanır.
- **Aynı makinede canlı fork, ebeveyn adreslerini yönlendirir**: Ebeveyn çalışmaya devam ederken `rdc repo fork --parent X --tag Y --checkpoint` ve ardından `rdc repo up` çalışır. Geri yüklenen süreçler, checkpoint anındaki ebeveynin loopback adreslerini taşır; sistem bunları şeffaf biçimde fork'un kendi adreslerine yönlendirir (aynı servis, verinin fork kopyası). Geri yüklenen bir TCP bağlantısının ilk kullanımı yine başarısız olur ve uygulamanın yeniden bağlanması gerekir; yukarıdaki TCP maddesine bakın.

---

## Yedekleme

| Limit | Değer |
|-------|-------|
| Depo başına yedekleme hedefleri | Sınırsız |
| Eş zamanlı yedekleme görevleri | Depo başına 1 (eş zamanlı tetiklenirse görevler kuyruğa alınır) |
| Yedekleme sıklığı | Zorunlu minimum aralık yok; depolama bant genişliğinizle sınırlıdır. Yükleme hızını sınırlamak için `rdc config backup-strategy set --name <name> --bwlimit "6M"` kullanın (rclone `--bwlimit` sözdizimi: basit `6M`, yönlü `6M:off` veya zaman çizelgesi `08:00,3M;22:00,10M`) |
| Saklama | Depolama sağlayıcınız (S3, Cloudflare R2 vb.) tarafından kontrol edilir. Rediacc saklama politikaları uygulamaz. |
| Makineler arası yedekleme | Desteklenir; hedef makinede yeterli veri deposu alanı olmalıdır |

---

## CLI ve API

| Limit | Değer |
|-------|-------|
| Aynı makineye eş zamanlı `rdc` komutları | Sınırsız (her komut kendi SSH bağlantısını açar) |
| Varsayılan paralel depo başlatma eş zamanlılığı | 3 (`--concurrency` ile ayarlanabilir) |
| SSH bağlantı zaman aşımı | İlk bağlantı için 30 saniye |
| `rdc` oturum süresi | Zaman aşımı yok; uzun süren işlemler bağlantıyı aktif tutar |

---

## Desteklenen İşletim Sistemi Sürümleri

Uzak makinelerin, Rediacc'ın çekirdek, dosya sistemi ve ağ izolasyonu gereksinimlerini karşılamak için aşağıdakilerden birini çalıştırması gerekir. Bu liste, CI'da test edilen yetkili kümedir (Bridge Workers matrisi) ve [Gereksinimler](/en/docs/requirements) ile senkronize tutulmalıdır:

| İşletim Sistemi | Minimum Sürüm | Varsayılan Çekirdek | Notlar |
|-----------------|----------------|---------------------|--------|
| Ubuntu | 24.04 LTS *(önerilen)* | 6.8 | AppArmor varsayılan. |
| Debian | 13 (Trixie); 12 Bookworm da çalışır | 6.12 (Debian 12'de 6.1) | |
| Fedora | 43 | 6.12 | SELinux enforcing varsayılan. |
| openSUSE Leap | 16.0 | 6.4+ | AppArmor varsayılan. |
| Oracle Linux | 10 (UEK) | UEK 7+ | UEK btrfs'i korur; SELinux enforcing varsayılan. |

**Minimum gerekli çekirdek: 6.1.** Daha eski çekirdek çalıştıran makineler, kurulum sırasında açık bir hata mesajıyla reddedilir.

> **Neden çekirdek 6.1?** Rediacc, şifrelenmiş depo depolaması ve yazma üzerine kopyalama çatallaması için BTRFS kullanır. Linux 6.1, büyük veri depoları için bağlama sürelerini önemli ölçüde azaltan, anlık görüntü silme performansını artıran ve önceki çekirdeklerde bulunan veri bütünlüğü sorunlarını düzelten kritik BTRFS iyileştirmelerini getirmiştir. Çekirdek 6.1, depolar arasındaki ağ izolasyonunu zorunlu kılan, `bind()` çağrılarını şeffaf bir şekilde yeniden yazan ve depolar arasındaki bağlantıları engelleyen çekirdek düzeyindeki ağ izolasyonu kancaları için de gereklidir.

> **Neden Rocky Linux 10 / RHEL 10 standart çekirdeği değil?** RHEL 10'un standart çekirdeği `btrfs` modülü olmadan gönderilir (`modprobe btrfs` "Module btrfs not found" hatasıyla başarısız olur). Rediacc'ın şifreli depolama arka ucu btrfs olmadan çalışamaz. **Oracle Linux 10, desteklenen listede tek RHEL uyumlu hedeftir** çünkü btrfs'i koruyan Unbreakable Enterprise Kernel'i (UEK) varsayılan olarak kullanır. Tam açıklama için [Gereksinimler: Neden UEK?](/en/docs/requirements) sayfasına bakın.

### Çekirdek özellik matrisi

Matrisi, CI'da test edilen her işletim sisteminin kutudan çıktığında neler sağladığına tek bakışta görmek için okuyun. Beşinin tümü her gereksinimi karşılar; bu nedenle matris operatör odaklı bir referanstır, bir seçim kriteri değildir.

| İşletim Sistemi | btrfs modülü | cgroups v2 | Landlock (ABI >= 1) | eBPF cgroup kancaları |
|-----------------|-------------|------------|---------------------|----------------------|
| Ubuntu 24.04 | yerleşik | unified hierarchy | evet (5.13+) | evet |
| Debian 13 | yerleşik | unified hierarchy | evet | evet |
| Fedora 43 | yerleşik | unified hierarchy | evet | evet |
| openSUSE Leap 16.0 | yerleşik | unified hierarchy | evet | evet |
| Oracle Linux 10 (UEK) | yerleşik (UEK aracılığıyla) | unified hierarchy | evet | evet |
