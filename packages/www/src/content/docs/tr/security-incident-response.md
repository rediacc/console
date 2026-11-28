---
title: "Güvenlik Olayı Müdahalesi"
description: "Rediacc'in kendi güvenlik olaylarını nasıl yönettiği: aşamalı müşteri bildirimleri, GDPR Art. 33(3) alanları, CRA raporlama yolu ve müşterilerin neler aldığı."
category: "Legal"
tags:
  - security
  - compliance
subcategory: foundations
order: 10
language: tr
sourceHash: "4b237976bd64e55e"
sourceCommit: "f9ac63ac37dff49f6c980f00fdacb7e41099ce81"
---

Bu sayfa, Rediacc'in kendisi bir güvenlik olayı yaşadığında, örneğin kendi sistemlerinin ele geçirilmesi veya ürünlerindeki aktif olarak istismar edilen bir açık durumunda neler olduğunu anlatır. Bir müşterinin kendi depoları içindeki olayları araştırmak ve bildirmek müşteriye aittir; Rediacc bunun için kanıt toplama araçlarını sağlar. Dışarıdan gelen açık bildirimleri [bildirim politikası](/tr/docs/security-disclosure-policy) kapsamındadır.

## Aşamalar

Her olayın saati, Rediacc olaydan haberdar olduğu anda başlar. Bilgiler aşamalar halinde verilir, çünkü tam tablo ilk günde nadiren bilinir ve GDPR Art. 33(4) bilgilerin kademeli olarak sağlanmasına izin verir.

| Aşama | Süre | İçerik |
|-------|------|--------|
| Erken uyarı | 24 saat içinde | şimdiye kadar bilinenler ve kötü niyetli eylemlerden şüphelenilip şüphelenilmediği |
| Bildirim | 72 saat içinde | olayın niteliği, ilk değerlendirme ve alınan önlemler |
| Nihai rapor | bildirimden sonra bir ay içinde; aktif olarak istismar edilen bir açık için, düzeltici veya hafifletici bir önlem hazır olduktan 14 gün sonra | ayrıntılı açıklama, kök neden ile uygulanan ve süren önlemler |

## Art. 33(3) alanları

Her aşama, GDPR Art. 33(3)'te sayılan dört öğeyi içerir:

1. ihlalin niteliği; ilgili veri sahiplerinin ve kişisel veri kayıtlarının kategorileri ve yaklaşık sayısı
2. daha fazla bilgi alınabilecek irtibat noktasının adı ve iletişim bilgileri
3. olası sonuçlar
4. ihlali gidermek için alınan veya önerilen önlemler; olası olumsuz etkilerini azaltmaya yönelik önlemler dahil

Bir değer henüz bilinmiyorsa aşama bunu belirtir ve bilineceği tarihi verir.

## Müşterilerin aldıkları

Bir olay bir kuruluşu etkilediğinde:

- her aşama, hesap portalında bir bildirim olarak ve e-posta ile kuruluşun sahiplerine, yöneticilerine ve güvenlik iletişim kişisine gönderilir
- bildirim ve e-posta, güvenlik iletişimi oldukları için bildirim tercihlerinden bağımsız olarak gönderilir
- portaldaki bir banner, yayımlanan tüm aşamaları gösteren olay sayfasına bağlanır
- her aşama, güvenlik araçlarının içe aktarabileceği makine tarafından okunabilir biçimde, ele geçirilme göstergelerini içeren bir STIX 2.1 paketi sunar

Etkilenmeyen bir kuruluş hiçbir şey almaz. Sahipler ve yöneticiler, postanın doğru kişiye ulaşması için kuruluşun güvenlik iletişim kişisini portaldan belirler.

## Düzenleyici raporlama

Rediacc, yasanın gerektirdiği durumlarda kendi olaylarını raporlar.

- **GDPR.** Rediacc veri işleyen olarak hareket ettiğinde, aşamalı bildirim veri sorumlusunu gereksiz gecikme olmaksızın bilgilendirir (Art. 33(2)) ve denetim makamına bildirim kararını veri sorumlusu verir. Rediacc veri sorumlusu olduğunda, mümkün olduğunda 72 saat içinde yetkili denetim makamına bildirimde bulunur (Art. 33(1)).
- **Cyber Resilience Act.** 11 Eylül 2026'dan itibaren Regulation (EU) 2024/2847'nin Art. 14 hükmü, bir üreticinin, dijital unsurlar içeren bir ürünün güvenliğini etkileyen aktif olarak istismar edilen bir açığı veya ciddi bir olayı, tek raporlama platformu üzerinden belirlenmiş CSIRT'e ve ENISA'ya bildirmesini gerektirir. Aynı 24 saatlik, 72 saatlik ve nihai adımlar geçerlidir; aynı olay kaydı hem müşteri bildirimini hem de başvuruyu besler.

## Şüpheli bir olayı bildirme

Rediacc'i etkileyen bir olaydan şüphelenen herkes, Rediacc bileşeninde beklenmedik bir davranış gören bir müşteri de dahil, [security@rediacc.com](mailto:security@rediacc.com) adresine yazar. Açık bildirimi [bildirim politikasına](/tr/docs/security-disclosure-policy) uyar.
