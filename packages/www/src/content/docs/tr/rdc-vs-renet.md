---
title: "rdc vs renet"
description: "rdc ne zaman, renet ne zaman kullanilir."
category: "Guides"
order: 1
language: tr
sourceHash: "cb2c174b8cf1a078"
---

# rdc vs renet

Rediacc iki farkli binary kullanir:

- `rdc`, workstation uzerinde calistirdiginiz kullanici odakli CLI'dir.
- `renet`, sunucuda calisan dusuk seviye uzak sistem binary'sidir.

Gunluk islemlerin neredeyse tamami icin `rdc` kullanin.

## Zihinsel Model

`rdc`yi kontrol duzlemi, `renet`i veri duzlemi gibi dusunun.

`rdc`:
- Yerel baglaminizi ve makine eslesmelerini okur
- Sunuculara SSH ile baglanir
- Gerektiginde `renet`i kurar/gunceller
- Sizin icin dogru uzak islemi calistirir

`renet`:
- Sunucuda yuksek yetkilerle calisir
- Datastore, LUKS volume, mount ve izole Docker daemon'larini yonetir
- Depo ve sistem seviyesinde dusuk seviye islemler yapar

## Pratikte Hangisini Kullanmalisiniz

### Varsayilan olarak `rdc`

Normal akislarda `rdc` kullanin:

```bash
rdc context setup-machine server-1
rdc repo create my-app -m server-1 --size 10G
rdc repo up my-app -m server-1 --mount
rdc repo down my-app -m server-1
rdc machine status server-1
```

### `renet` (ileri seviye / uzak taraf)

`renet`i dogrudan sadece bilincli olarak dusuk seviye uzak kontrol gerektiginde kullanin. Ornek:

- Sunucuda dogrudan acil hata ayiklama
- Host seviyesinde bakim ve kurtarma
- `rdc`nin aciga cikarmadigi internal kontroller

Cogu kullanicinin rutin islerde `renet`i dogrudan calistirmasi gerekmez.

### Deneysel: `rdc ops` (yerel VM'ler)

`rdc ops`, workstation'iniz uzerinde yerel VM kumeleri yonetmek icin `renet ops`u sarmalar:

```bash
rdc ops setup    # On kosullari yukle (KVM veya QEMU)
rdc ops up --basic  # Minimal kume olustur
rdc ops status   # VM durumunu kontrol et
rdc ops ssh 1    # Bridge VM'e SSH baglan
rdc ops down     # Kumeyi yok et
```

Bu komutlar `renet`i yerel olarak calistirir (SSH uzerinden degil). Tam dokumantasyon icin [Deneysel VM'ler](/tr/docs/experimental-vms) sayfasina bakin.

## Rediaccfile Notu

`Rediaccfile` icinde `renet compose -- ...` gorebilirsiniz. Bu normaldir: Rediaccfile fonksiyonlari `renet`in bulundugu uzak tarafta calisir.

Workstation tarafinda is yuklerini baslatip/durdurmak icin genellikle yine `rdc repo up` ve `rdc repo down` kullanirsiniz.
