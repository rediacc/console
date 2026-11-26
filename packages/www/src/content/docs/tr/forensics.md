---
title: "Adli Analiz: Ele Geçirilmiş Bir Depodan Kanıt"
description: "Müşterinin seçtiği ayrıntı düzeyinde, depo başına ağ akışı ve hassas dosya açma kayıtları; her 30 saniyede imzalı, zincirli gruplar halinde gönderilir. Üç yakalama düzeyini, ani artış tetikleyicisini, plan kotalarını, çevrimdışı ve sunucu tarafı tespiti ve sunucunun neleri okuyabildiğini kapsar."
category: "Guides"
tags:
  - security
  - compliance
subcategory: data-protection
order: 9
language: tr
sourceHash: "c349f479d246dee4"
sourceCommit: "0531ce955ea0d1658b8fceefd6aa44e3c270521c"
---

# Adli Analiz

Adli analiz, bir depo içinde çalışan yazılım ele geçirildikten sonra iki soruyu yanıtlar: veriler ne zaman alındı ve hangi veriler alındı. Rediacc üçüncü taraf yazılımdaki bir açığı kapatamaz; bu yüzden özellik, ele geçirilmeye dayanan kanıtlar kaydeder. Kayıtları, makinede depo sandbox'ının dışında çalışan, root yetkili bir toplayıcı yazar ve müşterinin yöneticilerinin erişemediği bir bucket'a gönderir.

Kayıtlar hacmi, hedefi ve zamanlamayı gösterir. Akış kayıtları hacmi ve hedefi kanıtlar, içeriği değil. [Olay iş akışı](/tr/docs/incident-response) bu kayıtları okur, [olay raporları](/tr/docs/incident-reports) ise onları bir düzenleyici kuruma sunulacak imzalı belgelere dönüştürür.

## Neler kaydedilir

Yakalama depo başınadır. Depolar ana makinenin ağını kullanır; bu nedenle trafik IP adresine göre değil, cgroup'a (deponun kendi slice'ı) göre atfedilir.

| Kayıt | İçerik |
|---|---|
| Ağ akışı | Zaman, süreç, hedef adres ve port, protokol, giden ve gelen bayt, biliniyorsa DNS adı, biliniyorsa hedefin ASN ve ülkesi |
| Dosya açma | Hassas listedeki bir yolla eşleşen yol için zaman, süreç ve yol |
| Kalp atışı | Her grupta imzalı bir işaret; böylece durmuş bir toplayıcı sessizlik olarak değil, boşluk olarak görünür |

Varsayılan hassas liste `.env` dosyalarını, anahtar ve sertifika dosyalarını (`*.pem`, `*.key`, `id_rsa*`, `id_ed25519*`), parola veritabanlarını (`*.kdbx`), veritabanı dökümlerini ve dosyalarını (`*.sql`, `*.dump`, `*.bak`, `*.sqlite*`) ve `pgdata` gibi veritabanı veri dizinlerini kapsar. Bir depo listeyi genişletebilir veya kendi desenleriyle değiştirebilir.

Paket yükleri ve dosya içerikleri hiçbir zaman kaydedilmez.

## Yakalama düzeyleri

Her deponun tek bir düzeyi vardır ve varsayılan en küçüğüdür. Daha yüksek bir düzey, alttakinin kaydettiği her şeyi de kaydeder.

| Düzey | Kaydedilen |
|---|---|
| `basic` | Hedef, port ve protokol başına her 5 dakikada bir özet; gelen ve giden baytlarla |
| `standard` | Her dakika bir akış kaydı; süreç ve DNS adıyla |
| `full` | Standard, ayrıca hassas yollardaki dosya açmalar |

Düzey depo başına ayarlanır:

```bash
rdc forensics level mail basic
rdc forensics level mail standard
rdc forensics level mail full
```

Toplayıcı düzeyi planın içerdiği sınırla kısıtlar. Planda adli analiz kotası yoksa depo hiçbir şey kaydetmez.

### Ani artış tetikleyicisi

Her düzey bir tetikleyiciyi kurar. Depo 24 saattir gözlemlendikten sonra, bir dakikadaki giden bayt kendi hareketli ortalamasının on katını (ve dakikada 50 MiB'ı) aşarsa depo 24 saatliğine Full düzeyine geçer. Tetikleyen dakika ortalamaya katılmaz; böylece tek bir veri sızdırma, bir sonrakini yakalaması gereken taban çizgisini yükseltemez.

## Planlar ve kotalar

Adli analiz ücretli planlar içindir ve yalnızca plan ücretliyken kayıt yapar. Yükseltme geçmişsiz başlar.

| Plan | Adli analiz kotası |
|---|---|
| Free, Community | 0 (hiçbir şey kaydedilmez) |
| Professional | 25 GB |
| Business | 125 GB |
| Enterprise | 512 GB veya Rediacc yöneticilerinin belirlediği özel bir kota |

Kota, planın yedekleme kotasının dörtte biridir ve yedekleme hesabından ayrıdır. Daha fazla kota yalnızca plan yükseltmesiyle gelir.

Kota dolduğunda önce en eski kayıtlar çıkarılır (FIFO). Son 7 gün kilitlidir ve asla çıkarılmaz, çünkü bucket onları 7 gün kilitler. Yalnızca kilitli baytlar kotayı aşacaksa yeni gruplar reddedilir. Öngörülen 7 günlük alım sığmayacaksa düzey Basic ile sınırlanır. Sahipler ve yöneticiler kotanın yüzde 80'inde, sınır Basic'e düştüğünde ve bir grup reddedildiğinde bildirim alır.

Bildirilmiş bir olayın içine düşen kayıtlar, olay kapandıktan 30 gün sonrasına kadar çıkarma dışında tutulur. Bkz. [olay müdahalesi](/tr/docs/incident-response).

## Gönderim ve bütünlük

Toplayıcı her 30 saniyede bir grup keser. Her grup makinenin spool anahtarıyla imzalanır ve bir önceki grubun özetini taşır; böylece silinen veya değiştirilen bir grup zinciri bozar. Gruplar, makinenin lisans blob'undan üretilen yalnızca oluşturmaya izin veren önceden imzalı URL'lerle yüklenir; makine kayıt ekleyebilir ama üzerine yazamaz veya silemez. Bağlantı koptuğunda gruplar yerel imzalı bir spool'da bekler ve bağlantı dönünce gönderilir.

Gece sıkıştırması, grupları depo başına bir gün dosyasında ve makine başına bir başlık dosyasında birleştirir; bu dosyada her imzalı başlık listelenir ve her boşluk işaretlenir. Hesabın denetim gün dosyaları da organizasyon ve gün başına aynı şekilde zincirlenir.

`rdc forensics verify` ve soruşturma sayfasındaki Verify evidence düğmesi bu zincirleri yeniden hesaplar. Bkz. [olay müdahalesi](/tr/docs/incident-response).

## Tespit

Anomali tespiti iki kez çalışır. Makinedeki istatistiksel bir dedektör hemen tepki verir ve depoyu Full'a geçirir. Sunucu, alım sırasında kendi dedektörlerini çalıştırır; böylece ele geçirilmiş bir ana makinede bile tespit sürer. Kayıt başına yapay zeka çalışmaz.

Dedektörler katmanlıdır ve her depo kendi trafiğinden öğrenir:

| Dedektör | Aradığı |
|---|---|
| Haftanın saatine göre taban çizgileri | Deponun o saat için olağan ritminin dışındaki bayt, bağlantı, farklı hedef, yeni DNS adı ve yeni süreçler |
| Half-Space Trees | Daha önce görülen akışlara benzemeyen bir akış |
| ECOD ve HBOS | Aykırı olarak puanlanan akış grupları ve puanı belirleyen özellikler |
| İlk görülme | Daha önce açmadığı hassas bir dosyayı açan bir süreç |

Her bulgu, onu üreten özellik başına gerekçeleri taşır ve açıklama bu gerekçelerden kurulan bir şablondur. Çevrimdışıyken dil modeli yoktur. Bir bulgu, hesap bildirimine ve sahiplere, yöneticilere ve güvenlik kişisine giden bir e-postaya dönüşür. Makine çevrimdışıyken yerelde hemen harekete geçer (Full yakalama ve imzalı spool'una bir kayıt) ve bağlantı dönünce uyarıyı, özgün tespit zamanını koruyarak iletir.

### Model paketleri

Dedektör parametreleri `data.rediacc.com/models/` adresinde imzalı paketler olarak yayımlanır: içerik adresli dosyalar, renet'e gömülü çevrimdışı bir Ed25519 model anahtarıyla imzalanmış bir manifest, asgari bir renet sürümü ve yalnızca artan bir sürüm; böylece sürüm düşürme reddedilir. Paket kurulmadan önce doğrulanır ve bir öncekine dönülebilir.

```bash
renet models status
renet models update
renet models rollback
```

İnternete kapalı kurulumlar aynı imzalı paketi `rdc server bundle` içinde alır; `--no-models` verilmedikçe.

## Sunucunun okuyabildikleri

Hesap sunucusu kayıtları okur, çünkü zaman çizelgesi, doğrulama ve sunucu dedektörleri bunlara ihtiyaç duyar: hedefler, portlar, süreç adları, DNS adları, bayt sayaçları ve hassas dosya yolları. Paket yüklerini veya dosya içeriklerini almaz.

Gelen bir istemci adresi kayıtlarda kısaltılmış olarak saklanır (IPv4 için /24, IPv6 için /48); adresin tamamı ise 30 gün sonra silinen ayrı bir bölümde durur. Silinen bölümün özeti imzalı başlıkta kalır; böylece zincir hâlâ doğrulanır ve doğrulayıcı adresi karartılmış olarak bildirir. Giden hedefler tam kalır, çünkü kanıt onlardır.

Müşteriler kayıtları bir soruşturma üzerinden açar; bunun için ücretli plan, sahip veya yönetici rolü ve yakın zamanda yeniden kimlik doğrulama gerekir, ve her görüntüleme denetlenir. Rediacc desteği adli verileri yalnızca müşterinin verdiği süreli bir izinle görür. İşleme koşulları [veri işleme sözleşmesinde](/tr/data-processing-agreement) yer alır.
