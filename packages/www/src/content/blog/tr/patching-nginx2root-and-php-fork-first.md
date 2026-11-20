---
title: "nginx2root ve PHP RCE'leri: Canlı Sunucuyu Tek Akşamda Yamalamak, Önce Fork"
description: "İki günde iki kritik güvenlik sürümü geldi. 43 konteyneri kontrol ettik, gerçekten açıkta olan 6 tanesini bulduk, riskli güncellemeyi önce bir fork üzerinde denedik ve canlı ortamı veri kaybı olmadan yamaladık."
author: Rediacc
publishedDate: 2026-11-20
category: case-study
tags:
  - security
  - cve
  - nginx
  - php
  - case-study
featured: true
language: tr
sourceHash: "94c45a97bd6b1c4e"
sourceCommit: "c3bae279da16e5441ac808ac85b812debb514694"
---

> **Özet.** nginx, 18 Kasım'da nginx2root (CVE-2026-123007 ve dört kardeş RCE) için düzeltmeleri yayımladı. PHP ise 19 Kasım'da, yedisi kritik olmak üzere 17 CVE için düzeltme çıkardı. 20'sinin akşamı kendi canlı sunucumuzu yamaladık.
>
> - **43 konteyner**, her birine hangi nginx ve PHP sürümünü çalıştırdığı sorularak dakikalar içinde kontrol edildi.
> - **13** tanesi eski sürümdeydi. Yalnızca **6** tanesi açıktaydı: üç herkese açık web uygulamasının PHP konteynerleri.
> - Her düzeltme **resmi bir imajdan** geldi ve indirmeden önce registry üzerinden doğrulandı.
> - En riskli güncelleme (8 sürümlük ERPNext atlaması) önce **gerçek veriyle bir fork üzerinde** denendi. Fork, sürüm notlarının cevaplayamadığı tek soruyu cevapladı.
> - İndirme sırasında bir disk doldu. Volume'u canlıyken büyütmek **3,9 saniye** sürdü, kesinti olmadı.

## Neler açıklandı

**nginx2root**, açık kaynak nginx'te bulunan beş uzaktan kod çalıştırma (RCE) açığından oluşan bir set. Manşetteki açık olan CVE-2026-123007, HTTP/2 akış kontrolündeki bir integer underflow hatası ve CVSS 4.0'da 9,2 puan aldı. HTTP/2'si açık olan, 1.9.5 (2015) ile 1.31.8 arasındaki her nginx sürümünü etkiliyor. Diğer dört açık için arkada bir proxy ile HTTP/3, `auth_http` kullanan mail proxy ya da DNS resolver'ın `mirror` ile birlikte kullanımı gerekiyor. Düzeltilmiş sürümler: **1.31.9** (mainline) ve **1.30.7** (stable). Aynı gün herkese açık bir proof of concept yayımlandı.

**PHP sürümü** bir gün sonra geldi: 8.5.13, 8.4.28, 8.3.37 ve 8.2.36. En ciddi açıklar oturum (session) yönetiminde ve timezone cache'inde, ikisi de kod çalıştırmaya kadar gidebiliyor. İkinci bir grup yalnızca PHP-FPM'i etkiliyor: request smuggling, durum sayfasında bir XSS ve yerel yetki yükseltme.

Bu yazıdaki sunucu `hostinger`. [PocketOS testimizde](/tr/blog/i-tested-rediacc-against-the-pocketos-incident) kullandığımız canlı makinenin aynısı. Üzerinde webmail'li bir mail sunucusu, Nextcloud, bir pazarlama stack'i, ERPNext, bir GitLab, bir gözlemlenebilirlik stack'i ve birkaç demo çalışıyor. Her uygulama kendi Rediacc deposunda duruyor: kendi Docker daemon'ı ve kendi özel IP aralığı olan şifreli bir volume.

## 1. Adım: Neyin savunmasız olduğunu, sonra neyin açıkta olduğunu bul

İmaj tag'leri eksik bilgi verir. `nextcloud:35-apache` içindeki PHP hakkında hiçbir şey söylemez, bir Debian paketi de güvenlik düzeltmesinden önce ve sonra aynı şekilde `nginx/1.26.3` raporlamaya devam eder. Biz de tag'lere bakmak yerine çalışan her konteynere doğrudan sorduk.

```bash
for repo in nextcloud mail mautic erpnext gitlab marketing observability demo-stackoverflow; do
  rdc term connect "$repo@hostinger" -c 'for c in $(docker ps --format "{{.Names}}"); do
    echo "$c: $(docker exec "$c" sh -c "nginx -v 2>&1; php -v 2>/dev/null | head -1")"
  done'
done
```

`rdc term connect <repo>` komutu, deponun kendi ortamında bir shell açar ve `DOCKER_HOST` zaten o deponun Docker daemon'ını gösterir. Tek bir döngü bütün makineyi taradı.

![Triyaj hunisi: 43 konteyner, 13'ünde nginx veya PHP var, 13'ü eski sürümde, 6'sı açıkta](/img/blog-cve-triage-funnel.svg)

Sonuç: 13 konteynerde nginx ya da PHP vardı ve 13'ü de düzeltmeden eskiydi. Kulağa 13 acil durum gibi geliyor. Değildi.

Savunmasız olmak, kodda açığın bulunması demek. Açıkta olmak ise bir saldırganın bu açığa gerçekten ulaşabilmesi demek. Aradaki fark ağ yolu, bu sunucuda da her herkese açık istek aynı yoldan geçiyor.

![Trafik yolu: ziyaretçiler HTTPS ve HTTP/2 ile Traefik'e bağlanır, Traefik her uygulamaya düz HTTP/1.1 iletir](/img/blog-cve-traffic-path.svg)

Her deponun önündeki reverse proxy olan Traefik, TLS ve HTTP/2'yi orada sonlandırır. Uygulamalarla özel bir loopback adresi üzerinden düz HTTP/1.1 konuşur. nginx'i kendi içinde barındıran iki uygulamanın nginx config'lerini kontrol ettik: `http2` yok, HTTP/3 yok, `mirror` yok, mail proxy yok. Yani nginx2root'un içeri girecek yolu yoktu.

PHP açıkları farklı. Sıradan web istekleriyle birlikte geliyorlar. Nextcloud, Roundcube (webmail) ve Mautic'in üçü de Apache arkasında PHP çalıştırıyordu, üçü de internete açıktı ve üçü de bir yama sürümü geride kalmıştı. Bu altı konteyner sıranın başına geçti.

Bir ayrıntı PHP tarafını biraz rahatlattı: üç uygulama da PHP'yi PHP-FPM olarak değil Apache modülü olarak çalıştırıyor, dolayısıyla yalnızca FPM'i etkileyen açıklar geçerli değildi. Oturum ve timezone açıkları ise geçerliydi.

## 2. Adım: Resmi düzeltmeyi bul, blog yazılarına değil registry'ye güven

İlk web aramalarımız kendinden emin ama birbiriyle çelişen cevaplar verdi. Bir makale resmi Nextcloud imajının hâlâ eski bir PHP ile geldiğini söylüyordu. Bir diğeri üçüncü taraf bir imajda düzeltme olduğunu yazıyordu. Hiçbiri imajın kendisinden alıntı yapmıyordu.

İçinde ne olduğunu görmek için imajı indirmeye gerek yok. Registry her imajın config'ini sunuyor ve PHP tabanlı resmi imajlar `PHP_VERSION` bilgisini bu config'e yazıyor.

```bash
curl -s "https://registry-1.docker.io/v2/library/nextcloud/blobs/<config-digest>" \
  -H "Authorization: Bearer $TOKEN" | jq -r '.config.Env[]' | grep PHP_VERSION
# PHP_VERSION=8.5.13
```

Bu, her uygulama için dakikalar içinde net bir cevap verdi:

| Uygulama | Çalışan | Resmi düzeltme | Düzeltmedeki PHP |
|---|---|---|---|
| Nextcloud | 35.0.2 | `nextcloud:35.0.3-apache` | 8.5.13 |
| Roundcube | 1.7.5 | `roundcube/roundcubemail:1.7.6-apache` | 8.4.28 |
| Mautic | 7.2.1 | `mautic/mautic:7.2.2-20261119-apache` | 8.3.37 |
| ERPNext | v16.52.1 | `frappe/erpnext:v16.60.0` | (nginx: bilinmiyor) |

ERPNext diğerlerinden farklıydı. nginx'i Debian'ın paketinden geliyor, bu yüzden sürüm metni her iki durumda da 1.26.3 kalıyor. Debian'ın düzeltilmiş build'i `1.26.3-3+deb13u11` ve 19 Kasım'da yayımlandı. Yeni ERPNext imajı o akşam build edildi. Düzeltme içinde miydi? İmaj config'i bunu söyleyemez. Sadece imajı çalıştırmak söyler.

## 3. Adım: Riskli olanı önce fork üzerinde dene

Roundcube 1.7.5'ten 1.7.6'ya gibi yama sürümlerinin riski düşük. ERPNext v16.52'den v16.60'a ise gerçek muhasebe verisi üzerinde sekiz sürümlük veritabanı migration'ı demek. Prova bu uygulamaya yapıldı.

![Önce fork ile devreye alma: dondurulmuş fork, test fork'u, güncelle ve kontrol et, sonra canlı ortam](/img/blog-cve-fork-first-rollout.svg)

Rediacc fork'u, bir depoyu verisiyle birlikte copy-on-write klonla çıkarılmış tam bir kopyasıdır. Boyutu ne olursa olsun saniyeler sürer ve kopya kendi Docker daemon'ını, IP aralığını ve URL'sini alır. İçindeki hiçbir şey canlı ortama dokunamaz.

```bash
rdc repo fork erpnext@hostinger --tag cve-test
rdc repo up erpnext:cve-test@hostinger --no-start   # mount only, start nothing yet
```

Fork'u başlatmadan önce compose dosyasını düzenledik: yeni imaj tag'i girildi, scheduler ve iki job kuyruğu devre dışı bir profile altına park edildi. Gerçek ERPNext verisinin kopyası üzerinde çalışan bir scheduler, gerçek müşterilere gerçek e-postalar gönderirdi. Bunlar kapalıyken fork sayfaları sunabiliyor ve migration çalıştırabiliyordu, başka bir şey yapamıyordu.

```bash
docker run --rm --entrypoint dpkg-query frappe/erpnext:v16.60.0 -W nginx
# nginx  1.26.3-3+deb13u11
```

Cevap buydu: yeni imaj Debian'ın yamalı nginx'ini taşıyordu. Ardından fork tam güncellemeyi çalıştırdı: `bench --site all migrate` canlı veritabanının bir kopyası üzerinde sorunsuz bitti, uygulama sağlık endpoint'inde `pong` döndü ve giriş sayfası fork'un kendi URL'sinde açıldı.

İmaj hâlâ eski paketi taşısaydı plan basitti: dur, fork'u sil, bir sonraki build'i bekle. Canlı ortam hiçbir şeyi düzeltmeyen bir güncelleme için yeniden başlamak yerine olduğu gibi kalacaktı.

## 4. Adım: Canlı ortam, her seferinde bir uygulama

Her uygulama aynı kısa rutini izledi:

1. **Snapshot.** `rdc repo fork <app> --tag pre-cve-20261120 --immutable` komutu dondurulmuş, salt okunur bir kopya oluşturur. Mount edilemez ve başlatılamaz, yani hiçbir şey onu değiştiremez.
2. **Tag'i sabitle.** Compose dosyasını düzeltilmiş tam tag'e göre düzenle.
3. **Çek, sonra deploy et.** `docker pull`, ardından `rdc repo up <app> -y`.
4. **Uygulamanın kendi güncelleme adımını çalıştır** (varsa).
5. **Doğrula**: içeriden (sürüm, migration'lar) ve dışarıdan (herkese açık URL).

| Uygulama | Ne oldu | Konteynerler tekrar ayakta |
|---|---|---|
| Nextcloud | İmajın entrypoint'i `occ upgrade` ile 35.0.2'den 35.0.3'e geçti, yaklaşık bir dakika bakım modunda kaldı | 66 sn |
| Roundcube | Düz imaj değişimi, şema kontrolünde yapılacak bir şey çıkmadı | 24 sn |
| Mautic | İlk pull'da disk doldu (aşağıda), ardından `doctrine:migrations:migrate` | 6 sn |
| ERPNext | Provadaki adımların aynısı, scheduler açık bırakıldı, `bench migrate` çıkış kodu 0 | 17 sn |

Son kontrol, her PHP konteynerinde PHP 8.5.13, 8.4.28 ve 8.3.37'yi, ERPNext'te nginx `deb13u11`'i ve sağlık kontrolü başarısız olmayan 43 konteynerin tamamının çalıştığını gösterdi.

## Neler ters gitti

**Değişken bir tag eski imajı gizledi.** Nextcloud `nextcloud:35-apache` üzerindeydi. Bu tag zaten düzeltilmiş imajı gösteriyordu, ama `docker compose up -d` elinde olan bir imajı yeniden çekmez, bu yüzden sunucu eski PHP ile sonsuza kadar kalabilirdi. `35.0.3-apache` tag'ini sabitlemek, çalışan sürümü compose dosyasında görünür kılıyor ve her güncellemede gerçek bir değişikliği zorluyor.

**İndirme sırasında bir disk doldu.** Mautic imajı 2,1 GB, deposunda ise 1,4 GB boş yer vardı. Pull, çalışan konteynerlere dokunmadan önce `no space left on device` hatasıyla düştü. Çözüm tek komuttu ve Mautic trafik sunmaya devam ederken yapıldı:

```bash
rdc repo expand mautic@hostinger --size 12G
# Repository expanded (3.9s)
```

Volume canlıyken 8 GB'dan 12 GB'a büyüdü ve pull tamamlandı. Makinenin boyut politikası artık bir depoyu dolmadan önce otomatik büyütebiliyor.

**Dondurulmuş snapshot'lar hiç kullanılmadı.** Her güncelleme çalıştığı için dört `pre-cve` kopyası öylece durdu. Güvenlik ağının amacı da bu, ama iki dürüst not var. Uygulamalar çalışırken alındılar, dolayısıyla içlerindeki veritabanı dosyaları crash-consistent: elektrik kesildikten sonraki durumla aynı, temiz bir kapatma değil. Ayrıca hiç denenmemiş bir geri dönüş, garanti değil bir plandır. Bir dahaki sefere snapshot tazeyken bir restore denenecek.

**Bir uygulamanın henüz düzeltilmiş sürümü yok.** İkinci bir uygulama kendi nginx'ini vendor imajının içinde barındırıyor ve o vendor henüz nginx 1.31.9'u yayımlamadı. Yukarıdaki trafik yolu HTTP/2'yi bu uygulamadan uzak tutuyor, bu yüzden elle build edilmiş bir imaj yerine vendor'ın sürümünü bekliyor.

## Seçimler ve nedenleri

| Elimizdeki seçenek | Seçtiğimiz | Neden |
|---|---|---|
| Hızlı önlem olarak HTTP/2'yi kapatmak | Yeni imajlarla yamalamak | HTTP/2 zaten Traefik'te bitiyordu, yani önlem hiçbir şey katmazdı. Yama, açığı saklamak yerine ortadan kaldırır. |
| Sürüm metnine güvenmek | İmajın içindeki paketi kontrol etmek | Debian, `nginx -v` çıktısını değiştirmeden düzeltmeleri geri taşır (backport). Gerçek build'i yalnızca `dpkg-query` gösterir. |
| Hangi imajın düzeltilmiş olduğu konusunda makalelere güvenmek | Registry'deki imaj config'ini okumak | Makaleler birbiriyle çelişti. Kaynak registry. |
| `35-apache` gibi değişken tag'ler | `35.0.3-apache` gibi tam tag'ler | Değişken bir tag düzeltmeyi gösterirken sunucu eski imajı çalıştırmaya devam edebilir. |
| Yerinde güncelleyip bozulursa geri dönmek | Büyük atlamalar için önce fork, küçükler için önce snapshot | Fork provası saniyeler tutar ve sorunu kullanıcılardan önce bulur. Tek adımlık bir yama sürümü için tam prova gereksiz. |
| Trafiği canary ile bölmek (`rdc repo canary`) | Fork üzerinde prova yapmak | Canary yeni sürümü canlı veri üzerinde çalıştırır, bu da şeması geriye dönük uyumlu uygulamalara uyar. 8 sürümlük bir migration böyle değil. |
| Dolan diski elle temizlemek | Volume'u canlıyken büyütmek | Docker'ın veri klasörü altındaki dosyaları silmek risklidir. Büyütmek tek komut ve yeniden başlatma gerektirmiyor. |

## Tuttuğumuz kontrol listesi

1. Her konteynere ne çalıştırdığını sor. Tag'lere bakma.
2. Gerçek ağ yolunu takip ederek savunmasız olanı açıkta olandan ayır.
3. Açıkta olanları bugün, gerisini bu hafta yamala.
4. Düzeltmeyi makalelerden değil registry'den oku.
5. Paket tabanlı bir düzeltmede imajın içindeki paket build'ini kontrol et.
6. Her değişiklikten önce snapshot al. Güncelleme veriyi migrate ediyorsa fork üzerinde prova yap.
7. Tam tag'leri sabitle.
8. İçeriden ve dışarıdan doğrula, sonra fork'ları temizle.

Advisory'leri okumaktan son doğrulamaya kadar bütün işi, operatör oturum başlamadan önce canlı ortam erişimi vermiş şekilde, `rdc` üzerinden çalışan bir yapay zeka ajanı (Claude Code) yürüttü. Bunu rahat kılan fork-first rutini oldu: ajan deneylerini kopyalar üzerinde yaptı, canlı ortam ise yalnızca daha önce işe yaradığı görülmüş adımları gördü.
