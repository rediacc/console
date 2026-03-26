---
title: Hesap Yonetimi
description: Rediacc'ta organizasyonlar, ekipler, uyeler ve abonelikler.
category: Guides
order: 12
language: tr
---

### Organizasyonlar

Kayit oldugunuzda, Rediacc sizin icin otomatik olarak bir organizasyon olusturur. Organizasyonunuz tum kaynaklar icin ust duzey kapsayicidir -- makineler, depolar, abonelikler ve ekip uyeleri.

![Registration Flow](/img/account-registration-flow.svg)

Her organizasyonun sahip oldugu ozellikler:
- Benzersiz bir ad (varsayilan olarak e-posta adresiniz)
- Bir abonelik plani (COMMUNITY ile baslar)
- Varsayilan bir ekip (tum uyeler otomatik olarak katilir)

### Uyeler ve Roller

Organizasyonlar uc rolu destekler:

![Role Hierarchy](/img/account-role-hierarchy.svg)

| Rol | Yetenekler |
|-----|-----------|
| **Owner** | Tam kontrol: faturalama, sahiplik aktarimi, tum uyeleri ve ekipleri yonetme |
| **Admin** | Uyeleri davet etme ve kaldirma, ekip olusturma ve yonetme, API tokenlerini iptal etme |
| **Member** | Organizasyon verilerini goruntuleme, API tokenleri olusturma, atanan ekiplere erisim |

Uye davet etme:
```bash
# From the portal: Organization > Members > Invite
# Or via API
```

Bir uye kaldirildiginda, API tokenleri ve config storage tokenleri otomatik olarak iptal edilir.

### Ekipler

Ekipler, bir organizasyon icinde kaynaklari sinirlandirmaniza olanak tanir. Her organizasyon varsayilan bir ekiple baslar.

![Team Structure](/img/account-team-structure.svg)

Ekip rolleri:
- **Team Admin**: Ekip icinde uye ekleyebilir/kaldirabili
- **Member**: Ekip kapsamindaki kaynaklara erisebilir

Organizasyon sahipleri ve yoneticileri, acik uyelik olmadan tum ekiplere otomatik olarak erisebilir.

### Abonelikler ve Planlar

Rediacc dort plan sunar:

| Plan | Makineler | Depo Lisansi/ay | Ozellikler |
|------|-----------|------------------|------------|
| COMMUNITY | 2 | 500 | Temel |
| PROFESSIONAL | 10 | 2.000 | Izin gruplari, kuyruk onceligi |
| BUSINESS | 25 | 5.000 | Ceph, gelismis analitik, denetim gunlugu |
| ENTERPRISE | Sinirsiz | Sinirsiz | Ozel markalama, ozel hesap |

![Subscription Flow](/img/account-subscription-flow.svg)

Tum planlar 3 gunluk bir ek sure ile baslar. Makine aktivasyonlari ekip bazinda izlenir ve hareketsizlik sonrasi otomatik olarak serbest birakilir.

### Faturalama

Yalnizca organizasyonun **sahibi** faturalamayi yonetebilir:
- Plan yukseltmeleri icin Stripe odeme oturumu olusturma
- Odeme yontemi degisiklikleri icin Stripe faturalama portalina erisim
- Self-servis geri odeme talep etme (14 gun icinde, 30 gunluk bekleme suresiyle)
