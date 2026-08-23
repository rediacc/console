---
title: Kesinti Sırasında Bankacılık Sürekliliği
description: >-
  Kıtalararası veri yansıtma ile elektrik kesintileri sırasında bankacılık
  operasyonlarınızı sürdürün.
category: Use Cases
tags:
  - backup
  - migration
subcategory: resilience
order: 6
language: tr
sourceHash: "8817b7a0a9304cd0"
sourceCommit: "b8e332b73573133a282b5c508bc049af1fbeb581"
---

> **Işıklar Söndüğünde İşletmeniz Açık Kalır.**

**Not:** Bu, Rediacc'ın bu sorunu nasıl çözebileceğini gösteren bir **kullanım örneğidir**. Bir startup olarak bu senaryolar, tamamlanmış vaka çalışmalarından ziyade potansiyel uygulamaları temsil ediyor.

**Kriz Senaryosu:** 28 Nisan 2025'te İspanya ve Portekiz'i etkileyen, Fransa'daki hasarlı bir iletim hattının tetiklediği büyük bir elektrik kesintisi. Elektrik kesintisi kritik BT altyapısını çökerterek büyük bankaların ve teknoloji şirketlerinin sistemlerine erişimlerini kaybetmelerine neden oldu.

## Sorun

İberya elektrik şebekesi feci bir arıza kademesiyle karşı karşıya kaldı:

* **Fransa'nın güneybatısındaki bir yangın** kritik bir iletim hattına zarar verdi 
* Sınır ötesi ara bağlantıların **aniden kopmasından** kaynaklanan hasar 
* İspanya ve Portekiz Avrupa şebekesinden **elektriksel olarak izole edildi**

**İşletmeler Üzerindeki Etkisi:** 
* İspanya genelindeki veri merkezlerinde **anında güç kaybı** yaşandı 
* Kontrol sistemi arızaları nedeniyle birçok lokasyonda yedek jeneratörler devreye giremedi 
* Bankacılık sistemleri çevrimdışı oldu ve ülke genelinde işlemler engellendi

**BT Altyapısı Zorlukları:** 
* **Yerel yedekleme sistemleri** aynı etkilenen bölgede bulundukları için etkisizdi 
* **Acil durum kurtarma prosedürleri** fiziksel sunuculara yerel erişime dayanıyordu 
* **İş sürekliliği planları** ülke çapında 4 saatten uzun süren elektrik kesintilerini hesaba katmıyordu

## Krizin Etkisi

BT hizmetindeki kesinti şunlara yol açtı: 
* **Finansal sistemin çökmesi** ve tahmini 4,5 milyar Euro işlem gecikmesi 
* Kritik iş verilerine 14 saatten fazla erişilemez hale geliyor 
* Büyük e-ticaret platformları tamamen kapanıyor 
* Müşteri hizmetleri sistemleri birden fazla sektörde başarısız oluyor

## Rediacc Çözümü

Rediacc'ın kıtalar arası kopyalama çözümünü uygulayan büyük bir İspanyol bankacılık grubu, kriz boyunca faaliyetlerini sürdürdü:

![Banking Continuity During Blackout](/img/blackout-continuity.svg)

### 1. **Kıtalararası Veri Yansıtma** 
* Temel bankacılık veritabanları ve işlem sistemleri Amerika Birleşik Devletleri'ndeki veri merkezlerine **sürekli olarak kopyalanıyor olurdu** 
* Müşteri verileri ve işlem kayıtları, bağlantınızın ve veri hacminizin izin verdiği çoğaltma gecikmesi içinde senkronize kalırdı

### 2. **Sorunsuz Operasyonel Geçiş** 
* İspanyol sunucular güç kaybettiğinde trafik **otomatik olarak ABD merkezli sistemlere yönlendirilirdi** 
* Müşteriler, şebeke arızası kadar uzun süren bir kesinti yerine, yönlendirme tamamlanana kadar yalnızca kısa bir kesinti fark ederdi

### 3. **Uzaktan Hizmete Devam Etme** 
* Etkilenmeyen ülkelerdeki çağrı merkezleri, kopyalanan sistemlere erişip müşteri desteğini sürdürebilirdi 
* Mobil bankacılık uygulamaları alternatif veri merkezlerine bağlanarak işlevselliğini korurdu

## Potansiyel Sonuç

**İş Sürekliliği:** 
* Rakipler 14 saatten fazla çevrimdışı kaldı. Bu mimariyi kullanan bir banka ise aynı süre boyunca hizmet vermeye devam ederdi

**Hizmet Sürekliliği:** 
* İkinci bir bölgesi olmayan kurumlar bunu yapamazken, o işlemleri işlemeye devam edebilirdi

**Finansal Koruma:** 
* Bir ödeme sisteminin devre dışı kaldığı her saat için biriken işlem başarısızlığı kayıplarından kaçınılırdı 
* Hiçbir veri kaybolmaz veya bozulmazdı, dolayısıyla herhangi bir kurtarma işlemine gerek kalmazdı
