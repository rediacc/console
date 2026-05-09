---
title: "İzleme"
description: "rdc machine komutlarıyla dizüstü bilgisayarınızdan sunucularınızın ve depolarınızın durumunu kontrol edin."
category: "Tutorials"
subcategory: advanced
order: 12
language: tr
sourceHash: "e6eaaed180c35e36"
sourceCommit: "be90e8e7896623c088b86360ec29c1baef2e86b4"
---

# İzleme

Uygulamanız dağıtıldı, canlı ve yedeklendi. Şimdi her şeyin sağlıklı kaldığından emin olun. `rdc`, dizüstü bilgisayarınızdan herhangi bir sunucunun tam görünümünü (sağlık durumu, container'lar, depolar) almanızı sağlar.

## Öğreticiyi izleyin

![Tutorial: Monitoring](/assets/tutorials/tutorial-monitoring.cast)

## Kontrol edebileceğiniz üç şey

![Health, containers, repos](/img/tutorials/tutorial-monitoring/slide-1.svg)

## Sağlık durumu: sistem bilgisi

Sistem görünümüyle başlayın:

```bash
time rdc machine query --name my-server --system
```

Bu komut sistem çalışma süresini, disk kullanımını ve depolama durumunu gösterir. Bir sorun varsa bildirir.

## Container'lar

Makinedeki her depodaki tüm çalışan container'ları görmek için:

```bash
time rdc machine query --name my-server --containers
```

Her container için ad, durum, sağlık, CPU ve bellek bilgileri ile hangi depoya ait olduğu görüntülenir.

## Depolar

Depolarınızı kontrol etmek için:

```bash
time rdc machine query --name my-server --repositories
```

Her depo; boyutu, bağlama durumu, Docker durumu ve disk kullanımıyla birlikte gösterilir.

## Tek seferde her şey

```bash
time rdc machine query --name my-server
```

Sistem bilgisi, depolar, container'lar hepsi tek komutta. Filtre olmadan kullanılan `query` komutu tam görünümü döndürür; `--system`, `--containers`, `--repositories`, `--services`, `--network` veya `--block-devices` ile yalnızca ilgili bölüme odaklanılır.

## Yerel doğruluk kontrolü

`rdc doctor`, belirli bir sunucudan bağımsız olarak yerel kurulumunuzu (Node, SSH anahtarı, `renet`, Docker) kontrol eder:

```bash
time rdc doctor
```

## Tamamlandınız

Seri tamamlandı. Artık kurulum, yapılandırma, dağıtım, fork alma, yayına alma, otomatik başlatma, yedekleme ve izleme yapabilirsiniz. Hepsi terminalinizden, hepsi kendi sunucularınızda.
