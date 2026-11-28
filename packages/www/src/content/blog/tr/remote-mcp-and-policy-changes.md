---
title: "Uzak MCP: Yalnızca sahibinin okuyabildiğini okuyan bir ajan"
description: "Uzak MCP üç bölgesel Worker üzerinde çalışır. Bir grant, bir config'in anahtarını ve sahibinin politika anahtarlarını taşır, ana anahtarı asla, ve hiçbir token grant'ten uzun yaşamaz."
author: Rediacc
publishedDate: 2026-11-25
category: announcement
tags:
  - mcp
  - ai-agents
  - security
  - policy
featured: false
language: tr
sourceHash: "ce8dbe4241a2d7ab"
sourceCommit: "dda643f43f9dadc19e08a84858e87f115d428f85"
---

> **Özet.** Uzak MCP, bir yapay zekâ ajanına terminal yerine bir URL verir. Tasarımın sorusu ajanın nasıl bağlanacağı değil, bağlandıktan sonra neyi görebileceğiydi. Cevap: grant'i oluşturan kişinin gördüğünün tam olarak kendisi, fazlası değil.
>
> - Bir grant **tek bir config**'e ulaşır ve **tek bir bölgede** yaşar.
> - Token'lar en fazla **1 saat** (erişim) ve **30 gün** (yenileme) sürer, grant'in kendisinden uzun asla.
> - Grant, bir config'in içerik anahtarını ve iki **politika okuma anahtarını** taşır, config deposunun ana anahtarını asla.
> - Politika kayıtlarının biçimi değişti. Eskileri reddedilir, geçiş yolu yoktur.

## Oturum kabuğu değil, bir URL

Yerel MCP sunucusu (`rdc mcp serve`) ajanın yanında çalışır ve üzerinde çalıştığı makinenin erişimini devralır. Uzak sunucu farklıdır. Her bölgede `mcp.<region>.rediacc.cloud` adresinde bir MCP Worker çalışır ve her ajan tek bir grant'in URL'sine bağlanır: `https://mcp.<region>.rediacc.cloud/g/<grantId>`. Araç çağrıları bir geliştiricinin dizüstü bilgisayarında değil, kuruluşun yürütücüsünde (executor) çalışır.

claude.ai gibi etkileşimli istemciler PKCE'li OAuth 2.1 ile giriş yapar. Arayüzsüz ajanlar `rmcp_<grantId>.<secret>` biçiminde bir bearer gönderir. İki biçim de grant'i tanımlar, URL'deki kimlik ise yalnızca onu adlandırır.

## Sınır grant'in kendisidir

Grant küçük ve belirli bir nesnedir. Bir config'i, bir son kullanma tarihini ve bir kapsamı belirtir: salt okunur bayrağı, araç izin listesi, makine ve depo adı desenleri.

Bu yapıdan üç kural çıkar:

- **Tek config.** Başka bir config'i adlandıran bir `tools/call`, hiçbir şey çalışmadan önce `REDIACC_GRANT_SCOPE` ile reddedilir. Üç config'i olan kullanıcı üç grant yetkilendirir.
- **Tek bölge.** Grant kimlikleri bölgeleriyle başlar. Yanlış Worker'a ulaşan istek, doğru URL ile birlikte HTTP 421 yanıtı alır ve asla iletilmez.
- **Tek ömür.** Erişim token'ı, 1 saat ile grant'te kalan sürenin kısası kadar yaşar. Yenileme token'ı, 30 gün ile grant'te kalan sürenin kısası kadar yaşar. Her yenileme grant'i yeniden sorgular, bu yüzden iptal edilmiş bir grant bir sonraki değişimde çalışmayı bırakır. Bir yenileme token'ını iki kez sunmak grant'i iptal eder.

Bir grant URL'si varsayılan olarak 7 gün, en fazla 30 gün geçerlidir.

## Sahibi gibi değerlendirilir

İlginç kısım anahtar malzemesidir. Grant bölünmüş bir sırdır. Tarayıcı rastgele bir değer üretir ve yalnızca bir kez gösterir. Hesap sunucusu bundan türetilen etiketin yalnızca özetini saklar, yürütücü ise slot anahtarını ancak iki yarıya da sahipken türetir. Bu slot anahtarının açtığı şey config'in kendi içerik anahtarıdır, kuruluşun ana anahtarı asla.

Aynı slot anahtarı iki **politika anahtarı** da açar. Politika, yani bir config girdisinin yetkilendirme kuralları, artık kendi kaydında durur ve depo anahtarından ile kaydın işaretçisinden türetilen bir anahtarla mühürlenir: depo, config, ekip ve anahtar nesli. Grant, kendi ekip config'inin anahtarını ve kuruluş düzeyindeki config'in anahtarını taşır. Bunlar sahibinin okuduğu iki politika kaydıdır, dolayısıyla yürütücü de aynılarını okur.

Sonuç olarak ajan, sahibi gibi değerlendirilir. Tavan, ekip politikasıyla daraltılmış kuruluş politikasıdır. Ajan yalnızca bir insan onayının ve bu tavanın ikisinin de izin verdiği yerde işlem yapar. Politikayı düzenleyemez, secret değerlerini okuyamaz, kendi grant'ini genişletemez. Kuruluşun kilitlediği bir anahtar ekip politikasında yok sayılır ve ajan bu sonuçla kişiyle aynı şekilde karşılaşır.

Her anahtarı bir işaretçiye bağlamanın belirtmeye değer bir yan etkisi vardır. Bir politika anahtarına sahip olan, o işaretçinin kayıtlarını yalnızca o anahtar neslinde açar. Başka bir depo, config veya ekip için sunulan ya da başka bir sürüm altında yeniden oynatılan bir blob, bütünlük etiketinden geçemez.

## Mevcut kurulumlar için değişenler

- **Politika kayıtları sürüm 2'dir.** Doğrudan depo anahtarıyla mühürlenmiş sürüm 1 kaydı açılmaz. Bu, bilerek yapılmış temiz bir kopuştur.
- **Barındırılan yazmalar aynı politikaya tabidir.** Barındırılan yürütücü üzerinden yapılan config yazmaları, kaydedilmeden önce politika tavanına karşı denetlenir.
- **Yerel ajanlar aynı tavanı korur.** `REDIACC_ALLOW_CONFIG_EDIT`, bir ajanı adlandırdığı işaretçiler için config düzenlemeye hâlâ açar, ancak yalnızca politikanın izin verdiği sınırlar içinde.
- **Süresi dolmuş ve döndürülmüş grant'ler açıkça hata verir.** `initialize` ve `tools/list` yanıt vermeye devam eder, her çağrı ise bir `reauthUrl` ile `REDIACC_GRANT_EXPIRED`, `REDIACC_GRANT_REVOKED` veya `REDIACC_KEY_ROTATED` döndürür.

Her grant dakikada 60 çağrıya ve aynı anda 5 çağrıya izin verir.

## Sızan bir URL ne sağlar

Sızan bir URL, süresi dolana veya iptal edilene kadar o kullanıcı gibi, yalnızca tek config'i üzerinde işlem yapar. Kuruluşun başka hiçbir config'ini ve bölgesinin barındırılan yürütücüsü dışındaki hiçbir şeyi açmaz. Araç çıktısı ise kullanıcının bağladığı model sağlayıcısına ulaşır. Bu sağlayıcıyı Rediacc seçmez.

Kurulum rehberi [MCP Server Setup](/tr/docs/ai-agents-mcp) sayfasındadır, anahtar düzeni ise [güvenlik modelinde](/tr/docs/security-model) anlatılır.
