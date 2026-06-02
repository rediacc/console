---
title: Zaman Yolculuğu Kurtarma
description: "Haftalar önce silinen verileri btrfs anlık görüntüleriyle kurtarın; normal yedeklemeleriniz o noktayı geçmiş olsa bile."
category: Use Cases
order: 2
language: tr
sourceHash: "4c1fcb1667a89759"
sourceCommit: "4e60a12e0664cdee5ad9079a7b75e2d05980d0f5"
---

> **Başkaları Verilerini Sonsuza Kadar Kaybedince, Zamanda Geriye Yolculuk Yapabilirsiniz.**

**Not:** Bu, Rediacc'ın bu tür sorunları nasıl ele aldığını gösteren bir **kullanım örneğidir**. Bir startup'ız. Bunlar ürünün tasarlandığı gerçekçi senaryolardır; önceden tamamlanmış müşteri vaka çalışmaları değil.

**Kriz Senaryosu:** Yeni işe alınan bir çalışan, 3 hafta önce canlı veritabanınızdaki kritik satırları **yanlışlıkla sildi**. Yedekleme sisteminiz yalnızca 2 haftalık geçmişi saklıyor. Normal bir kurulumda bu veri kaybolmuş demektir.

## Sorun

Mehmet, büyük bir e-ticaret platformunun veritabanını yönetiyor. Bir sabah müşteriler geçmiş sipariş kayıtlarının **görünmediğinden** şikayet etmeye başlıyor. Araştırıyor. Yeni işe alınan bir mühendis, 3 hafta önce canlı veritabanından kritik satırları **yanlışlıkla silmiş**; **test ortamı yerine canlı veritabanına bağlanmış**. Her DBA'nın ya bizzat yaşadığı ya da bir aceminin yaptığını izlediği klasik hata.

**Mevcut Yedekleme Sistemi:** 
* Haftada bir kez tam yedekleme alınır 
* **Artımlı yedeklemeler** günlük olarak kaydedilir

**Sorun:** Silme işlemi **tam yedekleme tarihinden önce** gerçekleşti, dolayısıyla kayıp veriler hiçbir yedek dosyasında yer almıyor. Günlük yedeklemeler **yalnızca en son verileri kaydeder**, dolayısıyla **silinen öğeler kurtarılamaz**.

## Krizin Etkisi

Kayıp veriler nedeniyle: 
* Müşteriler **geri ödeme isteklerini işleme koyamaz** 
* Ödeme sisteminde tutarsızlıklar meydana gelir 
* Şikayetler sosyal medyada hızla yayıldı

**Sonuçlar:** 
* Müşteri destek ekibi **yoğun baskı** altındadır 
* Şirketin itibarı **hızla zarar görüyor** 
* Manuel veri kurtarma çabaları **yalnızca %15 başarı** sağlıyor

**Ek Zorluk:** 
* Depolama maliyetlerini azaltmak için şirket **yalnızca son 2 haftalık yedekleri** saklıyor 
* Silinen veriler **son yedeklemelerde** yer almıyor

## Rediacc Çözümü

Mehmet'in Rediacc ile kurduğu zaman makinesi çözümü şu şekilde:

![Time Travel Recovery](/img/time-travel-recovery.svg)

### 1. **Anlık görüntüler** 
* Rediacc her saat başı otomatik olarak sistemin anlık görüntüsünü alır 
* Bu anlık görüntüler aynı zamanda verilerin silinmesinden hemen önceki anları da kapsamaktadır

### 2. **Zamanda Geriye Dönmek** 
* Mehmet, Rediacc arayüzünde silme işleminin gerçekleştiği tarih ve saati seçer 
* Sistemin 3 hafta önceki anlık görüntüsünü 1 dakika içinde yeni bir örneğe geri yükler

### 3. **Tam Kurtarma** 
* Kayıp veriler tamamen ve tutarlı bir şekilde geri yüklenir

## Sonuç

* Şirketin itibarı **24 saat içinde** onarıldı 
*Mali kayıp **%95** oranında önlendi 
* Rediacc, **depolama maliyetlerini artırmadan** sık sık yedekleme yapılabileceğini kanıtladı
