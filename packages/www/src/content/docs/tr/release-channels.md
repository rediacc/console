---
title: "Sürüm Kanalları"
description: "Edge ve Stable sürüm kanallarını, farklılıklarını ve nasıl seçileceğini anlama."
category: "Concepts"
order: 2
language: tr
sourceHash: "33795f3fa77f4aa5"
sourceCommit: "a97009927c347f7090e4f4f60f3948997654ae4b"
---

Rediacc güncellemeleri iki sürüm kanalı üzerinden yayınlar: **Stable** ve **Edge**. Her kanal farklı bir kitleye hizmet eder ve farklı dengeler sunar.

## Stable Kanal

Stable, tüm kullanıcılar için varsayılan kanaldır. Sürümler, bildirilen sorun olmaksızın 7 günlük bir bekleme süresinin ardından Edge'den terfi ettirilir.

- Üretim iş yükleri ve ücretli planlar için önerilir
- Edge'de 7 günlük test sonrasında dağıtılır
- Kritik durumlarda düzeltmeler doğrudan iletilebilir
- Etki alanları: `eu.rediacc.com`, `us.rediacc.com`, `asia.rediacc.com`

## Edge Kanal

Edge, her değişikliği main'e merge edildiği anda alır. Sürekli olarak dağıtılan yazılımın en güncel sürümüdür.

- En yeni özellikler ve düzeltmeler, her merge'de dağıtılır
- 2X Community plan limitleri (aşağıdaki tabloya bakın)
- Sonsuza kadar ücretsiz. Edge'de ücretli plan mevcut değildir.
- Stable'dan ayrı hesaplar. Veriler kanallar arasında aktarılmaz.
- Etki alanları: `edge-eu.rediacc.com`, `edge-us.rediacc.com`, `edge-asia.rediacc.com`

## Karşılaştırma

| | Stable | Edge |
|---|---|---|
| **Dağıtım sıklığı** | 7 günlük bekleme sonrası | Main'e her merge'de |
| **Kararlılık** | 7 gün test edildi | En güncel kod, daha az bekleme süresi |
| **Community plan limitleri** | 10 GB depolar, 500 düzenleme/ay, 2 makine | 20 GB depolar, 1.000 düzenleme/ay, 4 makine |
| **Ücretli planlar** | Mevcut (Professional, Business, Enterprise) | Mevcut değil |
| **Hesaplar** | Bağımsız | Bağımsız (Stable'dan ayrı) |
| **En iyi kullanım** | Üretim, ücretli iş yükleri | Test, değerlendirme, yan projeler, erken erişim |

## Edge 2X Limitleri

Community planındaki Edge kullanıcıları ücretsiz olarak iki katına çıkmış kaynak limitleri alır:

| Kaynak | Stable Community | Edge Community |
|---|---|---|
| Depo boyutu | 10 GB | 20 GB |
| Ay başına lisans düzenlemesi | 500 | 1.000 |
| Makine aktivasyonları | 2 | 4 |

Daha yüksek limitlere veya ücretli plan özelliklerine ihtiyaç duyuyorsanız, Stable kanalında hesap oluşturun ve oradan yükseltin.

## Ayrı Hesaplar

Edge ve Stable, ayrı veritabanlarıyla ayrı altyapılar üzerinde çalışır. Edge'de oluşturulan bir hesap Stable'da mevcut değildir ve tam tersi de geçerlidir. Kanallar arasında geçiş yolu yoktur. Edge'de başlarsanız ve ileride ücretli bir plan istiyorsanız, Stable'da yeni bir hesap oluşturmanız gerekecektir.

## Terfiler Nasıl Çalışır

1. Main branch'e her merge, hemen Edge'e dağıtılır.
2. 7 gün sorunsuz geçtikten sonra Edge, otomatik olarak Stable'a terfi ettirilir.
3. Kritik düzeltmeler her iki kanala da aynı anda iletilebilir.

Bu, Stable'ın her zaman Edge'in en fazla 7 gün gerisinde olduğu anlamına gelir. Bekleme süresi, regresyonları üretim kullanıcılarına ulaşmadan önce yakalar.

## Hangi Kanalı Seçmeliyim?

**Stable'ı seçin:**
- Üretim iş yükleri çalıştırıyorsanız
- Ücretli planlara ihtiyaç duyuyorsanız (Professional, Business, Enterprise)
- En yeni özelliklerden çok maksimum güvenilirliği tercih ediyorsanız

**Edge'i seçin:**
- Yeni özellikleri erken denemek istiyorsanız
- Platformu değerlendiriyorsanız
- Yan projeler için cömert ücretsiz limitler istiyorsanız
- Daha yeni, daha az test edilmiş kodla rahat çalışabiliyorsanız

## Kurulum

Her iki kanaldan kurulum komutları, paket yöneticisi yapılandırması ve Docker etiketleri dahil olmak üzere [Kurulum](/tr/docs/installation) sayfasına bakın.

## CLI Kanal Yönetimi

CLI, kurulum veya giriş sırasında yapılandırılan kanalı otomatik olarak kullanır. Kanal değiştirmek için:

```bash
rdc update --channel edge      # Edge'e geç
rdc update --channel stable    # Stable'a geç
```

`rdc subscription login` komutunu çalıştırıp bir Edge bölgesi seçtiğinizde, CLI otomatik olarak Edge güncelleme kanalını yapılandırır. Manuel `--channel` bayrağına gerek yoktur.
