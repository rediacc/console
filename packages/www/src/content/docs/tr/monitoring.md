---
title: "İzleme"
description: "Makine sağlığını, konteynerleri, servisleri, depoları izleyin ve tanılama çalıştırın."
category: "Guides"
order: 9
language: tr
---

# İzleme

Rediacc, makine sağlığını, çalışan konteynerleri, servisleri, depo durumunu ve sistem tanılamalarını incelemek için yerleşik izleme komutları sunar.

## Makine Sağlığı

Bir makine için kapsamlı bir sağlık raporu alın:

```bash
rdc machine health server-1
```

Rapor içeriği:
- **System**: çalışma süresi, bellek kullanımı, disk kullanımı
- **Datastore**: kapasite ve kullanım
- **Konteynerler**: çalışan, sağlıklı ve sağlıksız konteyner sayıları
- **Servisler**: durum ve yeniden başlatma sayıları
- **Depolama**: SMART sağlık durumu ve sıcaklık
- **Depolar**: bağlama durumu ve Docker daemon durumu
- **Sorunlar**: tespit edilen sorunlar

Makine tarafından okunabilir çıktı için `--output json` kullanın.

## Konteynerleri Listeleme

Bir makinedeki tüm depolardaki çalışan konteynerleri görüntüleyin:

```bash
rdc machine containers server-1
```

| Sütun | Açıklama |
|-------|----------|
| Name | Konteyner adı |
| Status | Çalışıyor, durdurulmuş vb. |
| Health | Sağlıklı, sağlıksız, yok |
| CPU | CPU kullanım yüzdesi |
| Memory | Bellek kullanımı |
| Repository | Konteynerin ait olduğu depo |

Seçenekler:
- `--health-check` — Konteynerlerde aktif sağlık kontrolleri gerçekleştir
- `--output json` — Makine tarafından okunabilir JSON çıktısı

## Servisleri Listeleme

Bir makinedeki Rediacc ile ilgili systemd servislerini görüntüleyin:

```bash
rdc machine services server-1
```

| Sütun | Açıklama |
|-------|----------|
| Name | Servis adı |
| State | Aktif, inaktif, başarısız |
| Sub-state | Çalışıyor, ölü vb. |
| Restarts | Yeniden başlatma sayısı |
| Memory | Servis bellek kullanımı |
| Repository | İlişkili depo |

Seçenekler:
- `--stability-check` — Kararsız servisleri işaretle (başarısız, 3'ten fazla yeniden başlatma, otomatik yeniden başlatma)
- `--output json` — Makine tarafından okunabilir JSON çıktısı

## Depoları Listeleme

Bir makinedeki depoları ayrıntılı istatistiklerle görüntüleyin:

```bash
rdc machine repos server-1
```

| Sütun | Açıklama |
|-------|----------|
| Name | Depo adı |
| Size | Disk imaj boyutu |
| Mount | Bağlı veya bağlı değil |
| Docker | Docker daemon çalışıyor veya durdurulmuş |
| Containers | Konteyner sayısı |
| Disk Usage | Depo içindeki gerçek disk kullanımı |
| Modified | Son değişiklik zamanı |

Seçenekler:
- `--search <text>` — Ad veya bağlama yoluna göre filtrele
- `--output json` — Makine tarafından okunabilir JSON çıktısı

## Vault Durumu

Dağıtım bilgileri dahil bir makinenin tam genel görünümünü alın:

```bash
rdc machine vault-status server-1
```

Sağlanan bilgiler:
- Ana bilgisayar adı ve çalışma süresi
- Bellek, disk ve Datastore kullanımı
- Toplam depo sayısı, bağlı olan sayısı ve çalışan Docker sayısı
- Depo başına ayrıntılı bilgi

Makine tarafından okunabilir çıktı için `--output json` kullanın.

## Bağlantı Testi

Bir makineye SSH bağlantısını doğrulayın:

```bash
rdc machine test-connection --ip 203.0.113.50 --user deploy
```

Rapor içeriği:
- Bağlantı durumu (başarılı/başarısız)
- Kullanılan kimlik doğrulama yöntemi
- SSH anahtar yapılandırması
- Genel anahtar dağıtım durumu
- Known hosts kaydı

Seçenekler:
- `--port <number>` — SSH portu (varsayılan: 22)
- `--save -m server-1` — Doğrulanmış ana bilgisayar anahtarını makine yapılandırmasına kaydet

## Tanılama (doctor)

Rediacc ortamınızın kapsamlı bir tanılama kontrolünü çalıştırın:

```bash
rdc doctor
```

| Kategori | Kontroller |
|----------|-----------|
| **Ortam** | Node.js sürümü, CLI sürümü, SEA modu, Go kurulumu, Docker kullanılabilirliği |
| **Renet** | İkili dosya konumu, sürüm, CRIU, rsync, SEA gömülü varlıklar |
| **Yapılandırma** | Aktif bağlam, mod, makineler, SSH anahtarı |
| **Kimlik Doğrulama** | Oturum açma durumu, kullanıcı e-postası |

Her kontrol **OK**, **Uyarı** veya **Hata** olarak raporlanır. Herhangi bir sorunu giderirken ilk adım olarak bunu kullanın.

Çıkış kodları: `0` = tümü geçti, `1` = uyarılar, `2` = hatalar.
