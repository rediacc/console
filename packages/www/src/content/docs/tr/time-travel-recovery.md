---
title: Zaman Yolculuğu Kurtarma
description: Anlık görüntü tabanlı zaman yolculuğu ile haftalar öncesinden yanlışlıkla silinen verileri kurtarın.
category: Use Cases
order: 2
language: tr
---

> **Başkaları Verilerini Sonsuza Kadar Kaybedince, Zamanda Geriye Yolculuk Yapabilirsiniz.**

**Not:** Bu, Rediacc'ın bu sorunu nasıl çözebileceğini gösteren bir **kullanım örneğidir**. Bir startup olarak bu senaryolar, tamamlanmış vaka çalışmalarından ziyade potansiyel uygulamaları temsil ediyor.

**Kriz Senaryosu:** Yeni işe alınan bir çalışan, 3 hafta önce canlı veritabanındaki kritik verileri **yanlışlıkla sildi**. Şirketin yedekleme sistemi, yedeklemeleri yalnızca 2 hafta boyunca sakladı ve geleneksel yöntemlerle veri kurtarmayı neredeyse imkansız hale getirdi.

## Sorun

Mehmet, büyük bir online alışveriş şirketinin veri tabanından sorumlu bir sistem uzmanıdır. Bir sabah müşteri şikayeti üzerine geçmiş sipariş kayıtlarından bazılarının sistemde **görünmediğini** fark eder. Araştırma, yeni işe alınan bir çalışanın 3 hafta önce canlı veri tabanından bazı kritik verileri **yanlışlıkla sildiğini** ve **test ortamı yerine canlı veri tabanına bağlandığını** ortaya koyuyor.

**Mevcut Yedekleme Sistemi:** 
* Haftada bir kez tam yedekleme alınır 
* **Artımlı yedeklemeler** günlük olarak kaydedilir

**İkilem:** Silme işlemi **tam yedekleme tarihinden önce** gerçekleşti, dolayısıyla kayıp veriler yedeklemelerde yer almıyor. Günlük yedeklemeler **yalnızca en son verileri kaydeder**, dolayısıyla **silinen öğeler kurtarılamaz**.

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

Mehmet, Rediacc ile "zaman makinesi" benzeri bir çözüm sunuyor:

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