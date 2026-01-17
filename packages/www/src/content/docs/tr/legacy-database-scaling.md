---
title: Eski Veritabanı Ölçeklendirme
description: Gerçek zamanlı veri çoğaltma ve sorgu dağıtımından yararlanarak eski veritabanlarını geçiş yapmadan ölçeklendirin.
category: Use Cases
order: 3
language: tr
---

> **Eski Veritabanınız Sizi Geride Tutuyor. Kırmadan Özgürleşin.**

**Not:** Bu, Rediacc'ın bu sorunu nasıl çözebileceğini gösteren bir **kullanım örneğidir**. Bir startup olarak bu senaryolar, tamamlanmış vaka çalışmalarından ziyade potansiyel uygulamaları temsil ediyor.

**Kriz Senaryosu:** Kubernetes ile sunucuların 10 kez ölçeklendirilmesine rağmen performans yalnızca 2 kat arttı. Müşteriler yavaş sorgulama sürelerinden, tatmin edici sonuçlar alınamadan maliyetlerin artmasından ve itibarın risk altında olmasından şikayetçiydi.

## Sorun

Şirketin bulut ortamındaki hizmetleri **yanıt vermekte zorlanıyordu**. Çözüm olarak yazılım ekibi: 
* **Kubernetes ile yatay ölçeklendirme** yapıldı ve **sunucu sayısı 10 kat artırıldı** 
* Ancak performans **yalnızca 2 kat** arttı

**Darboğaz Tespiti:** 
* Sorunun kaynağının **ölçeklendirilemeyen eski bir veritabanı** olduğu anlaşıldı 
* Veritabanı modern mimarilerdeki gibi dağınık bir şekilde çalışamıyordu

**İkilem:** 
* Modern bir veritabanına geçiş **yıllar sürebilir** → Kodun yeniden yazılması, veri geçişi ve test süreçleri gerekiyordu 
* Maliyet ve zaman kaybı kabul edilemezdi

## Krizin Etkisi

* Müşteriler **yavaş sorgu süreleri** nedeniyle şikayetçi 
* Sunucu maliyetleri artıyor ancak **performans tatmin edici değil** 
* Rekabetçi bir piyasada **itibar kaybı** riskinin artması

## Rediacc Çözümü

Rediacc'ın çapraz yedekleme özelliğini kullanan sistem mühendisi Yüksel:

![Eski Veritabanı Ölçeklendirmesi](/img/legacy-scaling.svg)

### 1. **Gerçek Zamanlı Veri Çoğaltma** 
* Eski veritabanındaki değişiklikler **10-15 dakika aralıklarla** diğer sunuculara aktarıldı** 
* **Yalnızca değiştirilen veriler** senkronize edildi → **Bant genişliği tüketimi %95 oranında azaltıldı**

### 2. **Sorgu Dağıtımı** 
* Okuma sorguları **birden fazla makineye dağıtıldı** 
* Tutarlılığı sağlamak için yazma işlemleri **ana veritabanında** tutuldu

### 3. **Ücretsiz Ölçeklendirme** 
* Eski sistem **değiştirilmeden** ek sunucularla desteklendi 
* Yeni donanım alımına gerek yok → Maliyet optimizasyonu için **Bulut sunucular saatlik olarak kiralandı**

## Sonuç

**Performans Artışı:** 
* Sorgu süreleri **55 saniyeden 7 saniyeye** düşürüldü 
* Sistem kapasitesi **8 kat** artırıldı

**Maliyet Kontrolü:** 
* Eski sistemin yeniden yazılmasıyla elde edilen tasarruf → **Finansal kaynaklar korundu**

**Zaman Kazanımı:** 
* Çözüm **3 hafta içinde** uygulandı 
* Müşteri şikayetleri **%99,99 (anlık görüntüler arasındaki toplam verinin güncelleme oranına bağlı olarak)** çözüldü