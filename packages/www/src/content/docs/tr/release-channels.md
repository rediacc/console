---
title: "Sürüm Kanalları"
description: "Edge ve Stable'ın farkları ve hangi kanalı çalıştırmalısınız."
category: "Concepts"
tags:
  - cli
  - operations
subcategory: platform
order: 2
language: tr
sourceHash: "29d62173c5cf044a"
sourceCommit: "abc292b1b7ca5096423e098c12a9b23bdabda16b"
---

Rediacc, CLI güncellemelerini iki kanal üzerinden yayınlar: **Stable** ve **Edge**. İkisi de aynı ürüne bağlanır, bu yüzden hesap, plan ve limitler her iki kanalda da aynıdır. Kanallar yalnızca bir sürümün size ne kadar çabuk ulaştığı konusunda ayrılır.

## Stable Kanal

Stable, tüm kullanıcılar için varsayılan kanaldır. Sürümler, bildirilen sorun olmaksızın 7 günlük bir bekleme süresinin ardından Edge'den terfi ettirilir.

- Muhafazakar bir yükseltme temposu tercih ediyorsanız önerilir
- Edge'de 7 günlük test sonrasında dağıtılır
- Kritik durumlarda düzeltmeler doğrudan iletilebilir

## Edge Kanal

Edge, her değişikliği main'e merge edildiği anda alır. Sürekli olarak dağıtılan yazılımın en güncel sürümüdür.

- Main'e her merge'de yayınlanır
- Stable ile aynı hesaplar, planlar ve limitler
- Yeni özellikleri erken denemek için en uygunu

## Tek Ürün, İki Kanal

Hesabınız, hangi kanalı kullanırsanız kullanın, veri bölgenizde `eu.rediacc.cloud`, `us.rediacc.cloud` veya `asia.rediacc.cloud` üzerinde durur. Kanal değiştirmek hesabınıza, verilerinize ve aboneliğinize dokunmaz. Bölgeler için [Veri Bölgeleri](/tr/docs/data-regions) sayfasına bakın.

## Karşılaştırma

| | Stable | Edge |
|---|---|---|
| **Dağıtım sıklığı** | 7 günlük bekleme sonrası | Main'e her merge'de |
| **Kararlılık** | 7 gün test edildi | En güncel kod, daha az bekleme süresi |
| **Planlar ve limitler** | Aynı | Aynı |
| **Hesap ve veriler** | Ortak | Ortak |
| **En uygun olduğu durum** | Üretim, ücretli iş yükleri | Erken erişim, değerlendirme |

## Terfiler Nasıl Çalışır

1. Main branch'e her merge, hemen Edge'e dağıtılır.
2. 7 gün sorunsuz geçtikten sonra Edge, otomatik olarak Stable'a terfi ettirilir.
3. Kritik düzeltmeler her iki kanala da aynı anda iletilebilir.

Bu, Stable'ın her zaman Edge'in en fazla 7 gün gerisinde olduğu anlamına gelir. Bekleme süresi, regresyonları Edge'den Stable'a yayılmadan önce yakalar.

## Hangi Kanalı Seçmeliyim?

**Stable'ı seçin:**
- 7 günlük bekleme penceresiyle muhafazakar bir yükseltme temposu tercih ediyorsanız
- En yeni özelliklerden çok maksimum güvenilirliği tercih ediyorsanız

**Edge'i seçin:**
- Yeni özellikleri erken denemek istiyorsanız
- Platformu değerlendiriyorsanız
- Daha yeni, daha az test edilmiş kodla rahat çalışabiliyorsanız

## Kurulum

Her iki kanaldan kurulum komutları, paket yöneticisi yapılandırması ve Docker etiketleri dahil olmak üzere [Kurulum](/tr/docs/installation) sayfasına bakın.

## CLI Kanal Yönetimi

CLI, kurulum sırasında yapılandırdığınız kanalı kullanır. Kanal değiştirmek için:

```bash
rdc update --channel edge      # Edge'e geç
rdc update --channel stable    # Stable'a geç
```
