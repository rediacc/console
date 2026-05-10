---
title: "Deponuzla Çalışın"
description: "Bir portu tarayıcınıza tünelleyin, sandbox içinde komut çalıştırın ve dizüstü bilgisayarınız ile depo arasında dosya senkronize edin."
category: "Tutorials"
subcategory: essentials
order: 6
language: tr
sourceHash: "3d56eb69e72c1a5a"
---

# Deponuzla Çalışın

Uygulamanız çalışıyor, ancak şimdiye kadar yalnızca `docker ps` ile gördünüz. Günlük iş akışını üç komut karşılar: uygulamayı tarayıcıda görmek için **tunnel**, sandbox içinde komut çalıştırmak için **term**, dizüstü bilgisayarınız ile depo arasında dosya taşımak için **sync**.

## Öğreticiyi izleyin

![Tutorial: Working with your repo](/assets/tutorials/tutorial-work-with-repo.cast)

## Günlük üçlü

![Tunnel, term, sync](/img/tutorials/tutorial-work-with-repo/slide-1.svg)

1. **Tunnel**: uygulamanızı tarayıcıda açın.
2. **Term**: sandbox içinde komut çalıştırın.
3. **Sync**: dosyaları içeri veya dışarı taşıyın.

## Tunnel: uygulamanızı tarayıcıda görün

Uygulama dizüstü bilgisayarınızda değil, sunucuda çalışır. Bir container'ın portunu SSH üzerinden yönlendirin:

```bash
rdc repo tunnel -m my-server -r my-app -c app
```

Tarayıcınızda `localhost`'u açın. Uygulamanız oradadır. İşiniz bittiğinde `Ctrl+C`'ye basın.

Farklı bir container için `-c` seçeneğini ve portu değiştirin:

```bash
rdc repo tunnel -m my-server -r my-app -c db --port 5432
```

## Term: depo içinde komut çalıştırın

Yalnızca bir shell'e ihtiyaç duyduğunuzda VS Code'u atlayın:

```bash
rdc term connect -m my-server -r my-app
```

Artık deponun sandbox'ının içindesiniz. Deneyin:

```bash
time docker ps
```

Yalnızca `my-app`'e ait container'ları görürsünüz; VS Code'da göreceğinizin aynısı.

Tek seferlik komutlar için `-c` kullanın ve etkileşimli shell'i atlayın:

```bash
time rdc term connect -m my-server -r my-app -c "df -h ."
```

## Sync: dizüstü bilgisayar ile depo arasında dosya taşıyın

Dizüstü bilgisayarınızdan depoya klasör gönderin:

```bash
time rdc repo sync upload -m my-server -r my-app --local ./src
```

Dosyaları geri çekin:

```bash
time rdc repo sync download -m my-server -r my-app --local ./backup
```

Emin değilseniz önce önizleme yapın. `--dry-run`, gerçekten kopyalamadan neyin değişeceğini gösterir:

```bash
time rdc repo sync upload -m my-server -r my-app --local ./src --dry-run
```

Tunnel, term, sync. Günlük döngüyü üç komut karşılar.

---

Sonraki: [Depo Fork'lama](/en/docs/tutorial-forking).
