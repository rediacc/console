---
title: "Güvenlik Açığı Bildirim Politikası"
description: "Rediacc'te bir güvenlik açığının nasıl bildirileceği: kapsam, güvenli liman, bildirim yöntemi ve beklenen yanıt süreleri."
category: "Legal"
tags:
  - security
  - compliance
subcategory: foundations
order: 9
language: tr
sourceHash: "612e816f7a8be282"
sourceCommit: "f9ac63ac37dff49f6c980f00fdacb7e41099ce81"
---

Rediacc, ürün ve hizmetlerindeki güvenlik açıklarına ilişkin bildirimleri memnuniyetle karşılar. Bu politika, nelerin kapsamda olduğunu, bildirimin nasıl yapılacağını ve bildirimde bulunan kişinin karşılığında neler bekleyebileceğini anlatır. Makine tarafından okunabilir iletişim dosyası `/.well-known/security.txt` adresindedir (RFC 9116).

## Kapsam

Kapsam dahilinde olanlar:

- `rdc` CLI'ı ve `renet` makine orkestratörü
- hesap sunucusu, web portalı ve API'si
- `rediacc.com` ve `rediacc.cloud` altındaki Rediacc web siteleri
- sürüm çıktıları: ikili dosyalar, konteyner imajları ve yükleyiciler

Kapsam dışında olanlar:

- bir makineye fiziksel erişim gerektiren bulgular veya bildirimde bulunan kişinin zaten kontrol ettiği ele geçirilmiş bir uç nokta
- istek hacmiyle hizmet reddi, spam veya çalışanlara yönelik sosyal mühendislik
- etkisi gösterilmemiş, otomatik tarayıcılardan gelen raporlar
- Rediacc'in yalnızca değiştirmeden yeniden dağıttığı üçüncü taraf yazılımlardaki açıklar; bunlar ilgili yukarı akış projesine bildirilir, buraya da bir kopya gönderilmesi memnuniyetle karşılanır

## Nasıl bildirilir

Bildirimi [security@rediacc.com](mailto:security@rediacc.com) adresine gönderin. Şunları ekleyin:

- etkilenen ürün ve sürüm ya da URL
- yeniden üretme adımları veya bir proof of concept
- bildirimde bulunan kişinin öngördüğü etki
- sorunun zaten herkese açık olup olmadığı veya istismar edilip edilmediği
- takip için bir iletişim adresi ve adının anılmasının istenip istenmediği

İngilizce bildirimler tercih edilir. Gerçek müşteri verileri rapora eklenmez: erişimin asgari düzeyde bir kanıtı yeterlidir.

## Güvenli liman

Rediacc, bu politika kapsamında iyi niyetle hareket eden bir bildirimci hakkında hukuki yola başvurmaz ve bunu desteklemez. İyi niyetli hareket etmek, bildirimcinin şunları yapması anlamına gelir:

- yalnızca kendi hesaplarında, makinelerinde ve verilerinde ya da Rediacc'in sahip olduğu varlıklarda test yapar
- sorunu kanıtladığı noktada durur, başkalarına ait verileri okumaz, değiştirmez, kopyalamaz veya silmez
- hizmeti diğer kullanıcılar için aksatmaz
- gecikmeden bildirir ve aşağıda belirtilen koordineli ifşa tarihine kadar ayrıntıları gizli tutar

Bu sınırlar içinde kalan çalışmalar yetkili sayılır ve Rediacc, soran üçüncü bir tarafa bunu belirtir.

## Yanıt süreleri

| Adım | Hedef |
|------|-------|
| Bildirimin alındığının teyidi | 2 iş günü |
| Önem derecesini içeren ilk değerlendirme | 5 iş günü |
| Açık olduğu sürece durum güncellemeleri | en az 14 günde bir |
| Kritik bir sorun için düzeltme veya hafifletme | değerlendirmeden itibaren 14 gün |
| Doğrulanmış diğer sorunlar için düzeltme veya hafifletme | değerlendirmeden itibaren 90 gün |

Bu süreler hedeftir; daha fazla zaman gerektiren bir bildirime gerekçe ve yeni bir tarih verilir.

## Koordineli ifşa

Ayrıntılar düzeltmeyle birlikte, normalde ilk değerlendirmeden sonraki 90 gün içinde yayımlanır. Daha erken ya da daha geç yayımlanmasını isteyen bildirimci, tarihi raporda belirtir ve iki taraf bir tarih üzerinde anlaşır. Doğada zaten istismar edilen bir açık, [olay müdahale sayfasında](/tr/docs/security-incident-response) açıklandığı gibi bir olay olarak ele alınır.

## Teşekkür

Doğrulanan bir bildirim, sürüm notlarında veya güvenlik bülteninde bildirimcinin seçtiği ad ya da takma adla anılır. Rediacc ücretli bir ödül programı yürütmez.

## İlgili sayfalar

- [Olay müdahalesi](/tr/docs/security-incident-response)
- [Hesap güvenliği ve API](/tr/docs/account-security)
