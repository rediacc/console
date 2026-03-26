---
title: Hesap Yönetimi
description: Rediacc'ta organizasyonlar, ekipler, üyeler ve abonelikler.
category: Guides
order: 12
language: tr
---

### Organizasyonlar

Kayıt olduğunuzda, Rediacc sizin için otomatik olarak bir organizasyon oluşturur. Organizasyonunuz tüm kaynaklar için üst düzey kapsayıcıdır -- makineler, depolar, abonelikler ve ekip üyeleri.

![Registration Flow](/img/account-registration-flow.svg)

Her organizasyonun sahip olduğu özellikler:
- Benzersiz bir ad (varsayılan olarak e-posta adresiniz)
- Bir abonelik planı (COMMUNITY ile başlar)
- Varsayılan bir ekip (tüm üyeler otomatik olarak katılır)

### Üyeler ve Roller

Organizasyonlar üç rolü destekler:

![Role Hierarchy](/img/account-role-hierarchy.svg)

| Rol | Yetenekler |
|-----|-----------|
| **Owner** | Tam kontrol: faturalama, sahiplik aktarımı, tüm üyeleri ve ekipleri yönetme |
| **Admin** | Üyeleri davet etme ve kaldırma, ekip oluşturma ve yönetme, API tokenlerini iptal etme |
| **Member** | Organizasyon verilerini görüntüleme, API tokenleri oluşturma, atanan ekiplere erişim |

Üye davet etme:
```bash
# Portal üzerinden: Organizasyon > Üyeler > Davet Et
# Veya API aracılığıyla
```

Bir üye kaldırıldığında, API tokenleri ve config storage tokenleri otomatik olarak iptal edilir.

### Ekipler

Ekipler, bir organizasyon içinde kaynakları sınırlandırmanıza olanak tanır. Her organizasyon varsayılan bir ekiple başlar.

![Team Structure](/img/account-team-structure.svg)

Ekip rolleri:
- **Team Admin**: Ekip içinde üye ekleyebilir/kaldırabilir
- **Member**: Ekip kapsamındaki kaynaklara erişebilir

Organizasyon sahipleri ve yöneticileri, açık üyelik olmadan tüm ekiplere otomatik olarak erişebilir.

### Abonelikler ve Planlar

Rediacc dört plan sunar:

| Plan | Makineler | Depo Lisansı/ay | Özellikler |
|------|-----------|------------------|------------|
| COMMUNITY | 2 | 500 | Temel |
| PROFESSIONAL | 10 | 2.000 | İzin grupları, kuyruk önceliği |
| BUSINESS | 25 | 5.000 | Ceph, gelişmiş analitik, denetim günlüğü |
| ENTERPRISE | Sınırsız | Sınırsız | Özel markalama, özel hesap |

![Subscription Flow](/img/account-subscription-flow.svg)

Tüm planlar 3 günlük bir ek süre ile başlar. Makine aktivasyonları ekip bazında izlenir ve hareketsizlik sonrası otomatik olarak serbest bırakılır.

### Faturalama

Yalnızca organizasyonun **sahibi** faturlamayı yönetebilir:
- Plan yükseltmeleri için Stripe ödeme oturumu oluşturma
- Ödeme yöntemi değişiklikleri için Stripe faturalama portalına erişim
- Self-servis geri ödeme talep etme (14 gün içinde, 30 günlük bekleme süresiyle)
