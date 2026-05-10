---
title: "Üretim Modu"
description: "Uygulamanızı dizüstü bilgisayarınızdan bağımsız çalıştırın ve otomatik başlatma ile sunucu yeniden başlamalarından kurtulun."
category: "Tutorials"
subcategory: advanced
order: 10
language: tr
sourceHash: "0e070fcd877900ab"
---

# Üretim Modu

Şimdiye kadar uygulamayı depo içinden `renet dev up` ile çalıştırdınız. Bu, geliştirme için idealdir. Üretim için her şeyi dizüstü bilgisayarınızdan `rdc` ile yönetirsiniz. Dizüstü bilgisayarınızı kapatın; uygulama çalışmaya devam eder.

## Öğreticiyi izleyin

![Tutorial: Production mode](/assets/tutorials/tutorial-production-mode.cast)

## Geliştirme ile üretim farkı

Fark basittir:

- `renet dev up`, **deponun içinde** çalışır. Bağlı olmanız gerekir.
- `rdc repo up`, **dizüstü bilgisayarınızdan** çalışır. Sonrasında bağlantıya gerek yoktur.

Geliştirmeden üretime geçmek için üç işlem:

![Stop, start, autostart](/img/tutorials/tutorial-production-mode/slide-1.svg)

## Adım 1: Geliştirme oturumunu durdurun

Depoya bağlanın ve kapatın:

```bash
rdc vscode connect -m my-server -r my-app
time renet dev down
```

## Adım 2: Üretim modunda başlatın

Dizüstü bilgisayarınızın terminalinden:

```bash
time rdc repo up --name my-app -m my-server
```

Hepsi bu kadar. Uygulamanız çalışıyor ve dizüstü bilgisayarınızı kapatabilirsiniz. `Rediaccfile` her şeyi halleder. `rdc repo up`, `renet dev up`'ın çağırdığı `up` fonksiyonunun aynısını çağırır. Aynı `Rediaccfile`, farklı çağrı yöntemi.

## Adım 3: Sunucu yeniden başlamalarından kurtulun

Sunucu yeniden başladığında uygulamanızın otomatik olarak geri gelmesini sağlayın:

```bash
time rdc repo autostart enable --name my-app -m my-server
```

Hangi depolarda otomatik başlatmanın etkin olduğunu doğrulayın:

```bash
time rdc repo autostart list -m my-server
```

## Üretimde durdurma

Uygulamanızı durdurmak gerektiğinde:

```bash
time rdc repo down --name my-app -m my-server
```

Bir komutla açın, bir komutla kapatın. Hepsi dizüstü bilgisayarınızdan.

---

Sonraki: [Yedekleme ve Geri Yükleme](/en/docs/tutorial-backup-restore).
