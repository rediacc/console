---
title: Çapraz Yedekleme Stratejisi
description: "Yedeklemeleriniz makinesi çöktüğü anda çöker. Rediacc anlık görüntüleri ayrı bir makineye çoğaltarak, tek bir disk arızasının tüm verileri ele geçirmesini engeller."
category: Use Cases
order: 5
language: tr
sourceHash: "39dbeac1faec121c"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

> **Felaket Geldiğinde Verileriniz Hayatta Kalacak mı? Rediacc ile Her Zaman İşe Yarar.**

**Not:** Bu, Rediacc'ın bu sorunu nasıl çözebileceğini gösteren bir **kullanım örneğidir**. Bu senaryolar tamamlanmış vaka çalışmalarından ziyade potansiyel uygulamalardır.

**Kriz Senaryosu:** Müşteri çağrısı sorunu açığa çıkarır: **disk arızası**. Uzak yedekleme sunucusunun en son yedeği **3 hafta öncesinden**. Yani, haftalarca veri kaybedilmiş.

## Sorun

Şirket, verileri **yalnızca aynı makineye** yedeklemenin risklerinin farkına vardı: 
* Donanım arızaları 
* Siber saldırılar 
* Savaş, deprem, yangın, sel gibi fiziki afetler 
* Veri kaybına karşı yetersiz koruma

**Çözüm Arayın:** 
* 20 TB verinin **uzak bir sunucuya** yedeklenmesine karar verilmiştir. 
* Bununla birlikte, geleneksel yöntemlerle bu yedekleme **2 hafta** sürer ve bant genişliğinin **%99,99'unu (anlık görüntüler arasındaki toplam verinin güncelleme oranına bağlı olarak)** kaplar

## Krizin Etkisi

Bir müşteri aramasından sonra: 
* **Hizmetlerin çalışmadığı** fark edildi 
* Bir **disk hatası** algılandı 
* Uzak yedekleme sunucusu kontrol edildiğinde **son yedeğin 3 hafta önce alındığı** anlaşılmaktadır.

**Sonuçlar:** 
* Manuel disk kurtarma girişimleri **başarısız** 
* 3 haftalık veri kaybı nedeniyle **müşteri sözleşmeleri iptal edilmiştir** 
* Şirketin **itibarı ciddi şekilde zedelendi**

## Rediacc Çözümü

![Cross Backup Strategy](/img/cross-backup.svg)

### 1. **İlk Yedekleme** 
* İlk defa 20 TB verinin uzaktaki bir sunucuya aktarılması 2 hafta sürer

### 2. **Saatlik Çapraz Yedeklemeler** 
* Her saat başı tam yedekleme algısı oluşturulup **yalnızca değişen veriler** aktarılır

### 3. **Afet Senaryolarına Hazırlık** 
* Veriler **kıtalararası** sunuculara bile yedeklenebilir 
* Ana makine çökse bile, 1 saat kadar önceki veriler **dakikalar içinde etkinleştirilir**

## Sonuç

**Zaman Tasarrufu:** 
* Yedekleme süresi **2 haftadan ortalama 4 dakikaya** düşürüldü 
* Veri kaybı riski **1 saate** düşürüldü

**Maliyet Optimizasyonu:** 
* Bant genişliği tüketimi **%98** azaldı

**Kesintisiz İş Sürekliliği:** 
* Ana sunucu çöktüğünde uzaktan yedekleme **7 dakika** içinde etkinleştirildi
