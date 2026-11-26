---
title: "Olay Raporları: Aşamalı, İmzalı ve Doğrulanabilir"
description: "Bir müşteri deposundaki olay için erken uyarıyı, bildirimi ve nihai raporu JSON, STIX 2.1 veya PDF olarak üretin. Her rapor Ed25519 ile imzalanır, QR doğrulama bağlantısı taşır ve alanlarını NIS2, 2025/302 biçimi ve GDPR md. 33(3) ile eşler."
category: "Guides"
tags:
  - security
  - compliance
subcategory: data-protection
order: 11
language: tr
sourceHash: "777d8ae1dde17294"
sourceCommit: "0531ce955ea0d1658b8fceefd6aa44e3c270521c"
---

# Olay Raporları

Bildirilmiş bir olay ([olay müdahalesi](/tr/docs/incident-response)), müşterinin bir düzenleyici kuruma sunacağı üç aşamalı rapor üretir. Rediacc belgeleri kanıttan üretir. Bir olayın önemli veya bildirilebilir olup olmadığı müşterinin takdirinde kalır ve her rapor bunu belirtir.

## Aşamalar

Her aşama yalnızca gerektirdiği bölümleri listeler; aşamanın istemediği bir bölüm boş bırakılmaz, çıkarılır.

| Aşama | Vade | Ekler |
|---|---|---|
| Erken uyarı | Haberdar olunduktan 24 saat sonra | Başlık, zaman çizelgesi, uzlaşma göstergeleri, şüphelenilen kötü niyetli ve sınır ötesi etki |
| Bildirim | Haberdar olunduktan 72 saat sonra | İlk değerlendirme, veri etkisi (kategoriler, yaklaşık sayılar, Üye Devletler) ve ATT&CK teknikleri |
| Nihai | Bildirimden bir takvim ayı sonra | Kök neden ve azaltma adımları |

Nihai rapor bir bildirimin ardından gelir; bu yüzden önce bildirim üretilir. Her aşama bir önceki aşamanın bölümlerini içerir.

Bir rapordaki her olgu nasıl bilindiğini söyler: kanıtta gözlemlendi, müşteri tarafından girildi veya çıkarıldı. Çıkarılan bir olgu bir güven düzeyi ve dedektörün gerekçesini taşır. Değerlendirme, veri kategorileri, Üye Devletler, şüphelenilen neden, alınan önlemler, irtibat noktası ve teknikler, müşterinin üretmeden önce olay sayfasında girdiği girdilerdir.

## Biçimler

| Biçim | Kullanım |
|---|---|
| JSON | Kanonik, doğrulanabilir biçim |
| STIX 2.1 | Tehdit istihbaratı araçları için gösterge paketi |
| PDF | Latin olmayan yazıları da işleyen okunabilir belge; her sayfa altbilgisinde sorumluluk reddi, QR kodu ve rapor özeti bulunur |

Olay sayfasında her aşamanın biçim başına bir indirme düğmesi vardır. Komut satırından:

```bash
rdc incident export <id> --stage early-warning
rdc incident export <id> --stage notification --format stix
rdc incident export <id> --stage final --format pdf --out ./reports
```

Biçim varsayılan olarak JSON'dur. `--format` yalnızca `--stage` ile geçerlidir. Dosya rapor kimliği altında yazılır.

## İmza ve doğrulama

Her rapor bir Ed25519 rapor anahtarıyla imzalanır; rapor kimliği, aşama ve özet herkese açık bir kayıtta yer alır. İmza raporun kanonik içeriğini kapsar; bu yüzden imzadan sonraki her değişiklik fark edilir.

Bir rapor üç yerde denetlenir:

- PDF üzerindeki QR kodunun açtığı `/account/verify/report/<id>` doğrulama sayfası. Denetim tarayıcıda, yayımlanmış rapor anahtarına karşı çalışır ve hiçbir şey yüklenmez. JSON dosyası tamamen denetlenir. PDF tarayıcıda yeniden özetlenemez; bu yüzden sayfa PDF'nin raporun özetini taşıdığını doğrular ve tam denetim için JSON dosyasına yönlendirir.
- Bir JSON raporu için komut satırı:

```bash
rdc forensics verify --report ./reports/<report-id>.json
```

İçerik veya imza eşleşmezse komut 1 koduyla çıkar. PDF, üretildiği JSON raporu üzerinden doğrulanır.

- Raporun içindeki kanıt damgası; pencere için Verify evidence sonucunu kaydeder: kimin, hangi sürümle ve ne zaman doğruladığı.

## Alan eşlemesi

Her rapor alanı, müşterinin bildirim yaptığı rejimlerle eşlenir; böylece içerik yeniden yazılmadan taşınabilir. Eşleme üç rejimi kapsar: NIS2 md. 23(4), (AB) 2025/302 Uygulama Tüzüğü olay bildirimi biçimi ve GDPR md. 33(3). Örnekler:

| Rapor alanı | NIS2 | GDPR |
|---|---|---|
| Haberdar olma zamanı | Md. 23(4)(a) | Md. 33(1) |
| Kronoloji | Md. 23(4)(d) | Md. 33(3)(a) |
| İrtibat noktası | Md. 23(4) | Md. 33(3)(b) |

Bir rejimde karşılığı olmayan alan, dışarıda bırakılmak yerine nedenini söyler. Örneğin GDPR md. 33(3) bildiriminde referans numarası veya kapanış zamanı yoktur.

## Bir raporun iddia etmedikleri

Her aşamada iki ifade basılır:

- Akış kayıtları hacmi ve hedefi kanıtlar, içeriği değil.
- Olayın önemli veya bildirilebilir olup olmadığı müşterinin takdirindedir.

Rediacc, müşteri adına bir düzenleyici kuruma hiçbir şey sunmaz.
