---
title: "Java4Shell: CPU Uygundu, Sunucuda Java Yoktu, Şablonlarımız Bize Pin'lemeyi Öğretti"
description: "CVE-2026-114938 için AVX-512 VBMI destekli bir CPU ve etkilenen bir JDK gerekiyor. Sunucumuzda CPU vardı ama hiç JVM yoktu. Asıl iş, yayımladığımız uygulama şablonlarında çıktı: pin'lenmiş tek bir tag, 2023'ten kalma bir JDK'yı dondurmuştu."
author: Rediacc
publishedDate: 2026-11-20
category: case-study
tags:
  - security
  - cve
  - java
  - docker
  - case-study
featured: true
language: tr
sourceHash: "df1e880f9d6ac549"
sourceCommit: "fca7bdc04b65c873118e8b35ce56fdd0c7c46e1b"
---

> **Özet.** Java4Shell (CVE-2026-114938), OpenJDK'nın JIT ile derlenen Base64 decoder'ında bir heap out-of-bounds write açığı. Yalnızca AVX-512 VBMI destekli x86-64 CPU'larda tetikleniyor.
>
> - Canlı sunucumuzun CPU'sunda **gereken dört flag'in hepsi var**. Sadece CPU kontrolüne bakılırsa açıkta görünüyordu.
> - **43 konteyner**, host ve çalışmayan depolar üzerinde yaptığımız taramada **hiç Java runtime'ı çıkmadı**. Aynı taramanın `python3` arayan kontrol çalıştırması, olması gereken her yerde onu buldu. Sunucuda yamalanacak bir şey yok.
> - Yayımladığımız uygulama şablonlarında durum farklıydı. **Dördü** bir JVM başlatıyor. **Üçü** değişken tag kullanıyor ve 20 Kasım'da yamalı JDK'larla upstream'de zaten yeniden build edildi.
> - **Biri**, Elasticsearch, `8.11.0` sürümüne pin'lenmişti: Kasım 2023'ten kalma, içinde `21.0.1` JDK'sı olan bir imaj. Elastic'in henüz düzeltilmiş bir sürümü yok. Bu yüzden şablon artık Elasticsearch'ü Elastic'in kendi önlem flag'i ile başlatıyor ve bu çalışan bir node üzerinde doğrulandı.

## Neler açıklandı

17 Kasım'da Calif araştırmacıları **Java4Shell**'i yayımladı, Oracle ve OpenJDK aynı gün düzeltmeleri çıkardı. Hata, HotSpot'un donanım hızlandırmalı Base64 decoder'ında: AVX-512 VBMI yolu son birkaç karakteri yanlış işliyor ve bir heap buffer'ının sonunun ötesine yazabiliyor. Hesabı olmayan uzaktan bir saldırgan bunu bellek bozulmasına, uygun bir uygulamada ise kod çalıştırmaya çevirebiliyor. Yazıda, tanınmış birkaç Java sunucu ürünü için kimlik doğrulamasız zincirler gösteriliyor.

Triyaj için önemli ayrıntılar:

- **Etkilenenler:** Düzeltme build'lerinden önceki OpenJDK 17.0.6 ve sonrası, 21, 25 ve 27. Standart Java 8 ve Java 11 etkilenmiyor.
- **Düzeltilmiş sürümler:** 17.0.21.1, 21.0.13.1, 25.0.5.1 ve 27.0.1.1 (Temurin build'lerinde `+2`, 27 için `+4` bulunur). `17.0.21` raporlayan ama sonunda `.1` olmayan bir runtime hâlâ savunmasız.
- **Ön koşullar:** AVX-512 VBMI destekli bir x86-64 CPU, decoder'ı zaten derlemiş bir JIT ve güvenilmeyen girdiden Base64 çözen bir uygulama yolu. ARM etkilenmiyor.
- **Puan:** CVSS 4.0'da 9,2, CVSS 3.1'de 8,1. Bağımsız bir proof of concept herkese açık. Yazı yazılırken canlı ortamda bir istismar bildirilmemişti.
- **Önlem:** JVM'i `-XX:-UseBASE64Intrinsics` ile başlatmak. Yayımlanan diğer seçenek olan `-XX:UseAVX=2` de x86-64'te işe yarıyor ama ARM'daki bir JVM'in başlamayı reddetmesine yol açıyor.

[Önceki yama turumuz](/tr/blog/patching-nginx2root-and-php-fork-first) dört uygulamayı önce fork ile devreye almakla bitmişti. Bu tur çok daha erken bitti ve ilginç olan kısım da nedeni.

## 1. Adım: CPU uygun mu?

CVE'lerin çoğunun yazılım tarafında bir ön koşulu olur. Bunun bir de donanım ön koşulu var ve kontrol etmesi ucuz:

```bash
rdc term connect hostinger -c "grep -m1 '^flags' /proc/cpuinfo | tr ' ' '\n' | grep -E '^(avx512f|avx512bw|avx512vbmi|bmi2)$'"
# avx512bw avx512f avx512vbmi bmi2
```

Dördü de var. Makine, tam AVX-512 desteği olan yeni nesil bir sunucu CPU'su olan AMD EPYC 9354P ile çalışıyor. Triyaj burada bitseydi cevap "açıkta, bu gece Java'lı her şeyi yamala" olurdu.

![Üç ön koşul: CPU uygun, JDK kontrolü başarısız, dolayısıyla girdi yoluna hiç ulaşılmıyor](/img/blog-java4shell-preconditions.svg)

## 2. Adım: Yamalanacak bir Java var mı?

CPU zincirin yalnızca bir halkası. İkinci halka etkilenen bir JDK, bu yüzden bir sonraki soru basitti: hangi konteynerler Java çalıştırıyor?

```bash
for c in $(docker ps --format '{{.Names}}'); do
  docker exec "$c" sh -c 'command -v java && java -version 2>&1 | head -1
    find / -xdev -name libjvm.so 2>/dev/null | head -2'
done
```

Bunu, makinedeki her depo için `rdc term connect <repo>@hostinger` üzerinden çalıştırdık. `libjvm.so` için yapılan `find`, bir uygulama klasörünün içine gömülü olan ve `PATH` üzerinde bulunmayan JVM'leri yakalıyor. Örneğin Elasticsearch JDK'sını böyle taşıyor.

Sonuç boştu. Çalışan 43 konteynerin hiçbirinde `java` ya da `libjvm.so` yoktu.

Bir tarama bir şey bulabildiğini göstermeden, boş sonucu hiçbir şey kanıtlamaz. Bu yüzden aynı döngüyü bu kez ERPNext konteynerlerinde olduğunu bildiğimiz `python3` için tekrar çalıştırdık. Hepsinde Python 3.14 çıktı. Tarama çalışıyor, sunucuda gerçekten Java yok.

Soruyu kapatmadan önce iki yer daha kontrol edildi. Host'ta Java ve `/usr/lib/jvm` yoktu. Üzerinde hiçbir şey çalışmayan depoların Docker daemon'larında Java imajı yoktu. Bunlardan birinde kendi monorepo'muzun bir checkout'u vardı ve compose dosyalarında `cassandra:5.0` ile `elasticsearch:8.11.0` geçiyordu. Bu bizi bir sonraki adıma götürdü.

## 3. Adım: Yayımladığımız şablonlar

Rediacc, hazır uygulama şablonları sunuyor: her uygulama için bir `docker-compose.yaml` ve bir Rediaccfile. Bunları bizim işletmediğimiz bir sunucu da devreye alabilir. Yani bir şablondaki Java imajı, bizim sunucumuz temiz olsa bile, doğru CPU'ya sahip her müşteri için bir risk.

```bash
git grep -nE "image:\s*(cassandra|neo4j|solr|elasticsearch|keycloak|kafka|jenkins|tomcat|openjdk|eclipse-temurin)"
```

Dört şablon bir JVM başlatıyor. İkisinde registry'deki imaj config'i JDK'yı zaten belirtiyor. Diğer ikisinde belirtmiyor, bu yüzden her imajı bir kez çalıştırıp sorduk:

```bash
docker run --rm --entrypoint sh cassandra:5.0 -c 'java -version 2>&1 | head -1'
# openjdk version "17.0.21.1" 2026-11-17
```

| Şablon | Şablondaki tag | Bugün içindeki JDK | Durum |
|---|---|---|---|
| Cassandra | `cassandra:5.0` | 17.0.21.1+2 | upstream'de düzeltildi, 20 Kasım'da yeniden build edildi |
| Neo4j | `neo4j:5-community` | 21.0.13.1+2 | upstream'de düzeltildi, 20 Kasım'da yeniden build edildi |
| Solr | `solr:9-slim` | 17.0.21.1+2 | upstream'de düzeltildi, 20 Kasım'da yeniden build edildi |
| Elasticsearch | `elasticsearch:8.11.0` | 21.0.1 (gömülü) | **savunmasız**, Elastic'in henüz düzeltilmiş sürümü yok |

![Pin'li ve değişken tag: pin'lenmiş Elasticsearch imajı 2023'ten kalma bir JDK taşıdı, değişken tag'ler düzeltmeyle yeniden build edildi](/img/blog-java4shell-pinned-vs-floating.svg)

## Pin'leme dersi, gözden geçirilmiş hâli

Önceki yazı "tam tag'leri pin'le" ile bitmişti. Bu tur o kurala bir dipnot ekliyor.

Pin'lemek, bilerek çalıştırıp güncellediğimiz uygulamalar için doğru. Pin, çalışan sürümü görünür kılıyor. Değişken bir tag ise bir düzeltmeyi gösterirken sunucu eski imajı çalıştırmaya devam edebilir, çünkü `docker compose up -d` elinde olan bir imajı yeniden çekmez.

Insanların sıfırdan devreye aldığı şablonlarda tablo tersine dönüyor. Üç değişken major tag (`5.0`, `5-community`, `9-slim`), düzeltmeden üç gün sonra bizim tarafta hiçbir değişiklik olmadan yamalı JDK'yı aldı. Tek tam pin olan `8.11.0` ise Elasticsearch'ü Kasım 2023'te build edilmiş bir imajda dondurdu. O tag'in hiçbir yeniden build'i bu JDK'yı düzeltmeyecek.

Bu yüzden tuttuğumuz kuralın iki yarısı var. Canlı ortamdaki uygulamalar tam tag ve bilinçli bir güncelleme alıyor. Şablonlar da pin'leniyor, çünkü Elasticsearch ve Kibana aynı sürümde çalışmak zorunda. Ama artık her şablon pin'i pin registry'mizde listeleniyor. Orada freshness gate'leri geride kalan bir pin'i üç yıl boyunca öylece bırakmak yerine işaretliyor.

## 4. Adım: Önlem, gerçek bir node üzerinde kanıtlandı

Elastic, düzeltmenin gömülü JDK güncellemesi olarak yakında çıkacak 8.19.26, 9.4.10, 9.5.7 ve 9.6.0 sürümleriyle geleceğini duyurdu. Bunlardan biri çıkana kadar resmi yönlendirme JVM flag'i. Şablonda bu, `ES_JAVA_OPTS` içine bir kelime daha eklemek demek:

```yaml
environment:
  - "ES_JAVA_OPTS=-Xms${ES_HEAP_SIZE} -Xmx${ES_HEAP_SIZE} -XX:-UseBASE64Intrinsics"
```

![Flag neyi değiştiriyor: JIT, AVX-512 intrinsic'i yerine düz Java decoder'ını kullanmaya devam ediyor](/img/blog-java4shell-intrinsic-flag.svg)

Compose dosyasındaki bir flag, JVM onaylayana kadar yalnızca bir iddia. İki kez kontrol ettik. Önce gömülü JDK'nın kendisini, flag'li ve flag'siz:

```bash
J=/usr/share/elasticsearch/jdk/bin/java
docker run --rm --entrypoint $J elasticsearch:8.11.0 -XX:+PrintFlagsFinal -version | grep ' UseBASE64Intrinsics '
#  bool UseBASE64Intrinsics = true   {product} {default}
docker run --rm --entrypoint $J elasticsearch:8.11.0 -XX:-UseBASE64Intrinsics -XX:+PrintFlagsFinal -version | grep ' UseBASE64Intrinsics '
#  bool UseBASE64Intrinsics = false  {product} {command line}
```

Sonra şablonun seçenekleriyle gerçek bir tek node'lu cluster başlattık. Yeşil olarak ayağa kalktı ve kendi API'si flag'i JVM argümanları arasında listeledi:

```bash
curl -s localhost:19200/_nodes/jvm | jq '.nodes[].jvm.input_arguments | map(select(test("BASE64")))'
# ["-XX:-UseBASE64Intrinsics"]
```

## Neler ters gitti

**CPU kontrolü cevabı neredeyse belirleyecekti.** En görünür ön koşul bu, tek komutla kontrol ediliyor ve "açıkta" dedi. Gerçek bir JVM arayan ikinci kontrol, gece yarısı acil durumunu bir şablon değişikliğine çevirdi.

**Bir test paketi çalışmaması gereken yerde çalıştı.** Şablon düzenlemesini doğrulamak için şablon paketinin lifecycle test paketini bir iş istasyonunda çalıştırdık. Bu paket, çıplak bir Docker host için değil lisanslı bir Rediacc deposu için yazılmış ve başka şablonları başlatarak on dakikadan fazla sürdü. Ayrıca ilgisiz bir şablonun ürettiği secret'ı kendi kaynak klasörüne yazdığını gösterdi: kimsenin commit'e girmesini istemeyeceği bir dosya. O şablon artık secret'ı kaynak ağacının dışına yazıyor ve test paketi, ihtiyaç duyduğu depo olmadan başlamayı reddediyor.

**Fork'lanacak bir şey yoktu.** Her değişiklikten önce canlı deponun fork'unu almak olağan güvenlik adımımız, ama bu sefer hedef yoktu. Değişiklik git'teki bir şablon dosyasındaydı, bu yüzden güvenlik ağı bir snapshot değil, incelenebilir bir commit ve canlı bir boot testiydi.

## Seçimler ve nedenleri

| Elimizdeki seçenek | Seçtiğimiz | Neden |
|---|---|---|
| CPU kontrolünü cevap saymak | Gerçek bir JVM aramak | CPU açıkta dedi, JVM yoksa istismar edilecek bir şey de yok. |
| Boş sonuca güvenmek | Mutlaka bir şey bulması gereken bir kontrol çalıştırmak | Bozuk bir taramanın boş sonucu, temiz bir sunucuyla aynı görünür. |
| JDK sürümünü registry'den okumak | Her imajı bir kez çalıştırmak | Dört imajdan ikisi JDK sürümünü config'ine yazmıyor. |
| `-XX:UseAVX=2` | `-XX:-UseBASE64Intrinsics` | Daha dar: tüm AVX-512 hızlanmalarını değil tek bir rutini kapatıyor ve ARM'daki JVM yine başlıyor. |
| Elasticsearch'ü şimdi en yeni 8.19'a çıkarmak | 8.11.0'da kalmak, flag'i eklemek, düzeltilmiş sürüm çıkınca yükseltmek | Bugün çıkmış en yeni sürümler hâlâ etkilenen bir JDK taşıyor ve Kibana'nın da aynı adımda geçmesi gerekiyor. |
| Her yerde tam pin | Tam pin ve her şablon pin'i için bir freshness gate | Alarmsız bir pin 2023'ten kalma bir JDK'yı dondurdu. Gate pin'i koruyor ve alarmı ekliyor. |

## Tuttuğumuz kontrol listesi

1. Yalnızca eşleşen ilk ön koşulu değil, tüm ön koşulları kontrol et.
2. Sadece ürün adını değil, runtime'ın kendisini ara (`java`, `libjvm.so`).
3. Her boş sonucu bir kontrol taramasıyla kanıtla.
4. Yalnızca çalıştırdığımızı değil, yayımladığımızı da tara.
5. Sürümü imajın içinden oku. Config sessizse imajı çalıştır.
6. En dar önlemi tercih et ve çalışan süreçte doğrula.
7. Vendor'ın düzeltilmiş sürümünü takip et ve çıkınca önlemi kaldır.

Önceki turda olduğu gibi işi `rdc` üzerinden bir yapay zeka ajanı (Claude Code) yürüttü, canlı ortam erişimini operatör oturum başlamadan önce verdi. Bu sefer canlı ortam hiç değişmedi: sunucudaki her adım bir okumaydı, tek düzeltme git üzerinden bir şablona girdi ve arkasında canlı bir test vardı.
