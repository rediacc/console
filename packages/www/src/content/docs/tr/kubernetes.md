---
title: "Kubernetes"
description: "Kubernetes'i Rediacc'ın depo zihniyetiyle çalıştırın: çalışan bir kümeyi, verileri dahil, kısa bir kesinti süresiyle başka bir makineye veya veri merkezine fork'layın ya da taşıyın."
category: "Guides"
order: 6
language: tr
sourceHash: "56e1f177e8f4ef41"
---

# Kubernetes

Rediacc, platformun geri kalanının üzerine inşa edildiği depo zihniyetinden ödün vermeden Kubernetes'i ürüne getirir. Ayırt edici iddia nettir: **çalışan bir kümeyi, verileri dahil, kısa bir kesinti süresiyle başka bir makineye veya veri merkezine fork'layabilir ya da taşıyabilirsiniz**. Bu, durdur-ve-geri-yükle taşıma değildir ve sıfır kesinti sihri de değildir. İş yükleri hedefte yeniden başlar, kesinti süresi saniyeler içinde ölçülür ve veriler birlikte taşınır.

Kubernetes, diğer sunucu tarafı ikili dosyalarla aynı şekilde renet içine gömülü, sertifikalı bir Kubernetes dağıtımı olan [k3s](https://k3s.io/) tarafından çalıştırılır.

## Nesne Modeli

Rediacc, depo zihniyetinin hâlâ geçerli olması için olağan "küme her şeyi sarar" resmini tersine çevirir:

- **Küme konteynerdir.** Bir makine, Docker depolarını (değişmeden) ve/veya kümeleri barındırır. Bir makinedeki tek düğümlü bir küme, "tek dosya tüm sistemi taşır" hikâyesini küme düzeyinde korur. Küme durumu (k3s veri dizini: gömülü veri deposu ve containerd'i) düğüm başına bir tane olmak üzere veri deposu destekli copy-on-write imaj dosyalarında yaşar; k3s'in `--data-dir`'i imaj bağlama noktasının içine bağlanır.
- **Bir Kubernetes deposu bir ad alanıdır.** `rdc repo create --cluster <name>`, çalışma zamanı evi o küme içindeki `<repo>` Kubernetes ad alanı olan bir depo oluşturur.
- **Kalıcı birimler ayrı copy-on-write birimleridir.** PV'ler, Ceph üzerinde RBD imajları veya yerel arka uçta bir renet yerel PV sağlayıcısı aracılığıyla küçük veri deposu imaj dosyalarıdır. Asla tek bir opak küme imajı içindeki dizinler değildir: iç dosya sisteminin reflink'i yoktur, bu nedenle bağımsız depo başına forklar bağımsız PV imajları gerektirir.

Bu ayrım, her iki vaadi de aynı anda fiziksel olarak mümkün kılan şeydir: **her zaman copy-on-write ad alanı forkları** (her deponun verisi bağımsız olarak klonlanır) ve **kümenin tamamının taşınabilirliği** (küme imajları artı her PV imajı birlikte taşınır).

| Kavram | Docker deposu | Kubernetes deposu |
|---|---|---|
| Çalışma zamanı evi | Yalıtılmış Docker daemon'u | Bir kümedeki ad alanı |
| Enjekte edilen ortam değişkeni | `DOCKER_HOST` | `KUBECONFIG` |
| Dağıtım sarmalayıcısı | `renet compose` | `renet kube` |
| Veri birimi | Bir LUKS imajı | Küme imajları artı PV başına imajlar |
| Fork birimi | Depo imajı | Ad alanı artı PV klonları |
| Tüm yerin klonlanması | (depo zaten yerdir) | `rdc cluster fork` / `rdc cluster migrate` |

## Bir Küme Tanımlama ve Oluşturma

Bir küme, özel bir ağ üzerindeki adlandırılmış bir düğüm havuzları kümesidir. Önce yapılandırmada tanımlayın, sonra hazırlayın.

```bash
# Havuzlarla bir küme tanımlayın (henüz hiçbir şey hazırlanmadı)
rdc config cluster add --name prod \
  --provider my-linode \
  --pool ceph:ceph:3 \
  --pool k8s:k8s-server:3

# Havuz üyelerini hazırlayın, her birinde renet'i başlatın, bileşenleri kurun (önce Ceph)
rdc cluster create --name prod
```

Havuz rolleri `ceph`, `k8s-server`, `k8s-agent` ve `hyperconverged`'dir (açık katılım gerektirir, çünkü Ceph bellek hedefleri ile kubelet tahliye eşikleri aynı RAM için yarışır). Her havuz, donanım asimetrisini havuz başına boyut ve disk parametreleri olarak taşır: disk ağırlıklı Ceph düğümleri, cpu/ram ağırlıklı Kubernetes düğümleri.

Havuz üyeleri, geri referansla birlikte `<cluster>-<pool>-<n>` olarak `resources.machines` içinde somutlaşır, bu nedenle **mevcut her `-m` komutu bunlar üzerinde çalışır**: `rdc machine query`, `rdc term connect`, depo komutları ve yedekleme stratejileri, küme düğümlerini sıradan makineler olarak görür.

Bulut sağlayıcılar, `rdc machine provision`'ın kullandığı aynı `ProviderMapping` kayıt defterini izleyerek [OpenTofu](https://opentofu.org/) üzerinden hazırlanır; bu, özel ağ bloğu (VLAN veya VPC, damgalanacak MTU, özel NIC adlandırması) ile genişletilmiştir. Yerel KVM, `rdc ops` aracılığıyla her zaman kullanılabilir test yoludur.

```bash
# Kümeleri inceleyin
rdc cluster status                 # tüm kümeleri listele
rdc cluster status --name prod     # bir kümenin tam yapılandırması

# Bir havuzu büyütün veya küçültün (makine ekler/kaldırır, düğümleri katılır/boşaltır)
rdc cluster scale --name prod --pool k8s --count 5

# Zaten hazırlanmış üyelere bileşenler kurun
rdc cluster install --name prod

# Hazırlanmış üyeleri kaldırın ve kümeyi yapılandırmadan çıkarın
rdc cluster destroy --name prod
```

### Kubeconfig Alma

Kubeconfig, büyük olduğu ve döndüğü için yapılandırma dosyanızda asla saklanmaz. OpenTofu çalışma dizinleri ve sertifika önbelleğiyle aynı yan durum desenini izleyerek talep üzerine SSH üzerinden alınır ve `0600` izinleriyle yerel olarak önbelleğe alınır.

```bash
rdc cluster kubeconfig --name prod
# Yazdırır: export KUBECONFIG=~/.config/rediacc/kube/prod.yaml
```

## Kubernetes Depoları

Hedef bayrağı çalışma zamanına karar verir. Bir tür bayrağı yoktur.

```bash
# Docker deposu (değişmeden): bir makinede yalıtılmış bir Docker daemon'u
rdc repo create --name shop -m server-1 --size 10G

# Kubernetes deposu: bir küme içinde "shop" ad alanı artı depolaması
rdc repo create --name shop --cluster prod --size 10G
```

Depo fiilleri, depo kapsamlı çalışma için tek yüzeydir. Hedef çözümleme hunisi sayesinde, depo komut kümesinin neredeyse tamamı `--cluster` kabul eder ve küme uyumlu hale gelir: `fork`, `migrate`, `push`, `pull`, `up`, `down`, `resize`, `diff`, `commit`, `branch`, `checkout`, `merge`, `trim`, `cat`, `mount`, `sync`, `list`, `status` ve `log`. Bir küme hedefi, kendi kontrol düğümü artı deponun ad alanına sabitlenmiş KUBECONFIG bağlamına çözümlenir; bu, bir makineyi `DOCKER_HOST` artı bir çalışma dizinine çözümlemenin analoğudur.

```bash
rdc repo sync upload --cluster prod -r shop --local ./config
rdc cluster kubeconfig --name prod           # KUBECONFIG'i dışa aktarın, ardından kubectl'i doğrudan kullanın
```

Küme düğümleri de `resources.machines` içinde somutlaşır, bu nedenle sıradan `rdc term connect -m <cluster>-<pool>-<n>` komutuyla belirli bir düğüme SSH ile bağlanabilirsiniz.

### Çift Çalışma Zamanlı Rediaccfile

Docker ile Kubernetes arasındaki taşınabilirlik, otomatik manifest dönüşümüne değil bir kurala dayanır. Aynı `up()` ve `down()` fonksiyonları altında hem bir `renet compose` yolu hem de bir `renet kube` yolu sunan bir depo, her iki yönde de serbestçe taşınır, çünkü veri dizini kuralları özdeştir. renet, bir makine hedefinde `DOCKER_HOST`'u ve bir küme hedefinde `KUBECONFIG`'i enjekte eder; `up()` hangisinin ayarlandığını okur ve buna göre yönlendirir.

```bash
up() {
  if [ -n "$KUBECONFIG" ]; then
    renet kube apply -f manifests/     # Kubernetes çalışma zamanı
  else
    renet compose -- up -d             # Docker çalışma zamanı
  fi
}
```

Hedef çalışma zamanından yoksun bir depo, veri aktarım aşamasından **sonra** net bir ret alır: imajlar taşınır ve dağıtım adımı, durumu bozmak yerine, deponun bir Kubernetes (veya Docker) yolu bildirmediğini söyler.

## Bir Deponun Fork'lanması

Bir Kubernetes deposunda `rdc repo fork`, her zaman veriyi kopyalar, her zaman anında. `--full` bayrağı ve varyantları yoktur.

```bash
rdc repo fork --parent shop --tag joseph --cluster prod
```

Bu, aynı kümede `shop-joseph` ad alanını oluşturur, her birimi copy-on-write olarak klonlar (Ceph'te bir RBD klonu, yerel arka uçta PV imaj dosyalarının bir reflink'i) ve iş yüklerini orada dağıtır. Fork URL'si, ebeveynin joker karakter sertifikası altında anında canlıdır, bu nedenle yeni bir sertifika veya DNS kaydı verilmez.

Hedef yükseltmesi:

- `--to-cluster <name>`, başka bir mevcut kümeye fork'lar. Aynı Ceph arka ucu: RBD klonu copy-on-write kalır. Farklı arka uç: push mekanizması imajları taşır.
- `--provider <p>`, önce kaynak kümenin şeklini varsayılan olarak yansıtan havuz özellikleriyle yeni bir küme hazırlar (bayraklar geçersiz kılar).

KVM test laboratuvarında ölçüldüğünde, bir ad alanı forku, ebeveyn iş yükü dokunulmadan ve iki ad alanı bağımsız olarak birbirinden ayrılarak yaklaşık bir ila beş saniyede tamamlanır.

## Kümenin Tamamının Fork'lanması veya Taşınması

Kümenin tamamına ait işlemler `rdc cluster` grubunda yaşar, çünkü farklı bir nesne üzerinde (tüm depolarıyla birlikte tüm yer) hareket ederler ve tek bir depo adı alan bir komutla ifade edilemezler. Bu, amiral gemisi hikâyedir.

```bash
# Tüm bir kümeyi, depolarının verileri dahil, yeni bir kümeye klonlayın
rdc cluster fork --name prod --tag staging

# Tüm bir kümeyi, depolarının verileri dahil, başka bir makineye veya veri merkezine taşıyın
rdc cluster migrate --name prod --to server-2
```

Her ikisi de küme imajları artı her depo PV imajının copy-on-write'ını koordine eder, ardından klonun veya taşınan kümenin yeni adreslerinde sağlıklı bir şekilde ayağa kalkması için düğüm kimliğini yeniden yazar. k3s, kontrol düzlemi durumunu gömülü veri deposunda tuttuğundan, kümenin imajının kendisi anlık görüntüdür: tutarlılık sırası önce kontrol düzlemi, sonra PV'ler, sonra ajanlardır.

KVM test laboratuvarında uçtan uca ölçülen dürüst rakamlar:

| İşlem | Ne yapar | Ölçülen |
|---|---|---|
| Ad alanı forku | Bir deponun ad alanını artı PV'lerini yerinde klonlar | ~1-5 sn |
| Tek RBD imaj forku | Bir Ceph destekli PV klonunun copy-on-write'ı | ~5 sn |
| Tüm 2 düğümlü küme forku | Boşaltır, kontrol düzlemini ve ajanı reflink'ler, yeni IP'lere kimliği yeniden yazar, ebeveyn dokunulmadan kalır | ~46 sn |
| Makineler arası küme taşıma | Sıcak ön kopya artı durdur-ve-yeniden-başlat kesintisi | ~16 sn kesinti |

Varsayılan tutarlılık **çökme-tutarlı ve referans olarak bütündür**: bu, iş yüklerinin gördüğü şey olan bir güç döngüsüyle aynı semantiktir. İş yükünün dosya sistemleri kopyalama sırasında donduğunda uygulama-tutarlı anlık görüntüler kullanılabilir. Bu, kasıtlı olarak sıfır kesinti süresi olarak sunulmaz. Başka hiç kimse "verileri dahil çalışan bir kümeyi fork'lamayı" sunmuyor; dürüst çerçeveleme, bir pazarlama mutlağı yerine kısa, ölçülen bir kesinti süresidir.

## Depolama: ceph-csi ve Kalıcı Birimler

Ceph, herhangi bir Kubernetes kümesinin **dışında**, `ceph` havuzunda renet'in cephadm akışı tarafından hazırlanır ve kümeler onu renet şablonlu ceph-csi manifestleri aracılığıyla tüketir. Her küme örneği (ve her fork), kiracı başına yalıtım ilkeli olan kendi RBD/RADOS ad alanını alır. Depolama tüm kümelerin altında yer alır, bu nedenle düz Docker depolarını ve veri deposu arka ucunu da destekler ve bir küme forku, kendi depolama arka ucunu fork'lamak yerine Kubernetes'in altındaki RBD imajlarını klonlar.

Yerel arka uçta (Ceph olmadan), bir renet yerel PV sağlayıcısı her PV'yi veri deposundaki küçük bir copy-on-write imaj dosyasıyla destekler ve fork'ta reflink ile klonlanır. Disk üzerindeki düzen ve renet komutları için [Sunucu Referansı](/en/docs/server-reference) sayfasına bakın.

## Bir Dağıtım Seçme

Dağıtım, küçük, gerçek bir arayüze sahip bir soyutlamadır (kurulum, katılma, kubeconfig, sağlık kontrolü, yükseltme ve benzerleri):

- **k3s** varsayılandır ve tek gömülü dağıtımdır. Apache-2.0 lisanslıdır, CNCF sertifikalıdır, tek bir taşınabilir ikili dosyadır ve hem gömülü Traefik'i hem de ServiceLB'si Rediacc proxy'si lehine devre dışı bırakılmıştır. `--data-dir`'i başlangıçta bağlanır; bu tam olarak imaj bağlama yolu değiştiğinde küme forkunun ve taşımasının ihtiyaç duyduğu şeydir. k3s, `repoEmbeddable` olarak işaretlenmiştir.
- **external**, kendi kubeconfig'inizi getirin demektir. Yalnızca `getKubeconfig` ve `healthcheck` gerçek iş yapar; yaşam döngüsü fiilleri, hatalar yerine birinci sınıf "uygulanamaz" sonuçları döndürür.
- **RKE2**, FIPS/CIS müşterileri için planlanan üçüncü arka uçtur, bu sürümün parçası değildir.

Küme forku ve taşıması, `repoEmbeddable` olmayan bir dağıtımda çalışmayı, durumu bozmak yerine net bir hatayla reddeder, çünkü küme durumunu veri deposu imajlarına gömmek, başlangıçta bağlanan bir data-dir gerektirir.

## Kayıt Defteri (Registry)

İki farklı imaj sorunu, iki araç:

- **Üst akış sıkıntısı** (Docker Hub oran sınırları, reddedilen pull'lar, çevrimdışı): gömülü bir [zot](https://zotregistry.dev/) pull-through önbelleği, kontrol havuzunda birden fazla üst akışa (docker.io, ghcr.io, quay.io) karşı `sync.onDemand` ile çalışır. Diğer ikili dosyalarla aynı şekilde renet'e gömülüdür ve ops test kayıt defterinin yerini alır, böylece her çalıştırma onu kullanır.
- **Küme içi dağıtım**: k3s'in gömülü kayıt defteri aynası, düğümlerin zaten çekilmiş imajları eşler arası paylaşmasını sağlar.

Bağlantı, containerd'in `certs.d/hosts.toml` ve k3s'in `registries.yaml` dosyaları aracılığıyla şeffaf ve yeniden başlatma gerektirmeden yapılır. Küme imajı içindeki depo başına containerd deposu, fork'ların ve taşımaların kullandığı gerçeğin kaynağı olmaya devam eder; kayıt defteri internetin önünde bir önbellektir, asla durum değildir.

## Ağ ve URL'ler

Kubernetes depo URL'leri düz şemayı izler; ad alanı kimliği en soldaki etikete katlanır ve küme ikinci kararlı etiket olur:

```
{service}--{repo}.{cluster}.{machine}.{base}          Kubernetes deposu (ad alanı = repo)
{service}--{repo}-{tag}.{cluster}.{machine}.{base}    fork (ad alanı = repo-tag)
```

Her ad alanı ve her fork, ebeveynin joker karakter sertifikasını ve DNS kaydını devralır, bu nedenle fork URL'leri anında canlıdır ve yeni sertifikalar yalnızca yeni bir küme veya depo oluşturulduğunda verilir. Yönlendirici, `rediacc.*` ile açıklama eklenmiş Service'ler için kümeyi yoklayarak Kubernetes servislerini keşfeder; bu, Docker etiketlerini okumanın Kubernetes analoğudur. Yönlendirme modeli için [Ağ](/en/docs/networking) sayfasına, depolama arka uçları için [Mimari](/en/docs/architecture) sayfasına bakın.

## Atıf

Rediacc, birkaç üçüncü taraf ikili dosyası (k3s, zot ve renet'in gömdüğü diğerleri) taşır. Sürümlerini, SPDX lisans tanımlayıcılarını ve kaynak kodu arşivi URL'lerini istediğiniz zaman yazdırın:

```bash
rdc credits
rdc credits --licenses    # sürümlerle birlikte paketlenen tam THIRD_PARTY_LICENSES metni
```
