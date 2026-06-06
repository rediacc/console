---
title: Risksiz Yükseltmeler
description: >-
  Anında klonlama ve saatlik anlık görüntüleri kullanarak veritabanı
  yükseltmelerini risk olmadan test edin.
category: Use Cases
order: 4
language: tr
sourceHash: "242617b8bede9535"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

> **Her Şeyi Test Edin. Risk Yok. Güvenle Yükseltin.**

Kısa not: Rediacc henüz hiçbir üretim müşteriye sahip değil. Bu, mimarinin bu senaryoyu pratikte nasıl işlediğini gösteren bir kullanım örneğidir ve gerçek bir dağıtımdan bir vaka çalışması değildir.

**Kriz Senaryosu:** Veritabanı yükseltmesi sırasında, eski sürüme dönmeyi veya yeni sürüme geçmeyi engelleyen **beklenmeyen bir hata** oluştu. Müşteriler sistemlere erişemedi ve 5000'den fazla çalışan çalışamadı. Tek çözüm tam bir sistem geri yükleme yapılmaktan geçiyordu ve bu işletme çevrimdışıyken mühendis saatlerine mal oldu.

## Sorun

Mehmet, ekibi çevrimdışı alamayan üretim veritabanlarını yönetiyor. Bugün bir **100 TB PostgreSQL veritabanını sürüm 13'ten 14'e yükseltme** yapıyor. Planı:

1. **Yedek alın** → Ancak veri boyutu nedeniyle yedekleme **birkaç gün** sürer 
2. **Yükseltmeyi hafta sonu yapın** → Departmanlara **Cumartesi 01:00-05:00** arasında kesinti bildirilir.

## Krizin Etkisi

* Yükseltme sırasında **beklenmeyen bir hata** oluştu 
* Veritabanı **eski sürüme geri dönemez veya yeni sürüme geçemez** 
* Dış destek ekipleri bile sorunu çözemiyor

**Etkiler:** 
* Müşteriler **ödeme ve sipariş sistemlerine erişemez** 
* Şirket çalışanları (**5000+ kişi**) çalışamaz 
* **İtibar kaybı** ve şikayetlerin artması başlıyor

**Geçici Çözüm:** 
* Son yedekleme **yeni bir sunucuya** yüklenir → **Donanım maliyeti iki katına çıkar** 
* Perşembe ve Cuma verileri **yalnızca canlı ortamda** olduğundan veri kaybı meydana gelir 
* **Farklı versiyonlara sahip iki veri tabanı oluşturuldu** → Tutarsızlıklar artıyor

## Rediacc Çözümü

İşte Rediacc ile neler değişiyor:

![Risk-Free Upgrades](/img/risk-free-upgrades.svg)

### 1. **Anında Klonlama** 
* **100 TB'lik veritabanının bir kopyası saniyeler içinde oluşturulur** 
* Yükseltme testleri **canlı sistemi etkilemeden** gerçekleştirilir

### 2. **Saatlik Anlık Görüntüler** 
* Yükseltme işlemi sırasında **hangi adımın ne zamandan beri başarısız olduğu** belirlenir 
* Sorunlu işlemler **önceden tespit edilir** ve düzeltilir

### 3. **Sorunsuz Yükseltme** 
* Yükseltme başarısız olursa **canlı ortam etkilenmez** 
* Yükseltme başarılı olursa yeni canlı ortam en son klon haline gelir

## Sonuç

**Zaman ve Maliyet Tasarrufu:** 
* Yedekleme süresi **7 günden 10 saniyeye** düşürüldü

**Risksiz Yükseltme:** 
* Test ortamında hatalar önceden tespit edildi → **Canlı sistemde sorun yaşanmadı**

**Sıfır Kesinti Süresi:** 
* Müşteriler ve çalışanlar **hiçbir aksaklık hissetmediler**
