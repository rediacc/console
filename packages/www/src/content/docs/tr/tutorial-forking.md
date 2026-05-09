---
title: "Depo Fork'lama"
description: "Tüm bir depoyu (uygulama, veritabanı, dosyalar) saniyeler içinde klonlayın. Her boyutta. Sıfır ek disk."
category: "Tutorials"
subcategory: advanced
order: 7
language: tr
sourceHash: "9237f00dce2ee5ec"
---

# Depo Fork'lama

Bu, en güçlü özelliktir: tüm bir üretim ortamını (uygulama, veritabanı, yapılandırma dosyaları) saniyeler içinde klonlayın. Her boyutta. Sıfır ek disk. İstediğiniz kadar fork alın.

Slogan: **üretimi klonlayın, hiçbir şeyi bozmayın.**

## Öğreticiyi izleyin

![Tutorial: Forking a repository](/assets/tutorials/tutorial-forking.cast)

## Kaybedecek bir şey kurun

Önce fork'un izolasyonunu kanıtlayabilmek için çalışan uygulamaya bir dosya ekleyin. Depoyu VS Code'da açın:

```bash
rdc vscode connect -m my-server -r my-app
```

Deponun içinde bir işaret dosyası oluşturun:

```bash
time echo "Hello from production" > index.html
```

Şimdi fork alın.

## Fork

```bash
time rdc repo fork --parent my-app -m my-server --tag experiment --up
```

![Parent fans out into independent clones](/img/tutorials/tutorial-forking/slide-1.svg)

Tek komut. Her şeyi (uygulama, veritabanı, yapılandırma dosyaları) klonladı ve saniyeler içinde oldu. Tekrar çalıştırırsanız başka bir bağımsız klon elde edersiniz.

## Neden bu kadar hızlı?

![Sharing a folder link is the same speed regardless of the folder's size](/img/tutorials/tutorial-forking/slide-2.svg)

Bir klasör bağlantısı paylaştığınızı hayal edin. Klasör küçük ya da büyük olsun, bağlantı aynıdır. Klasör ağırdır; bağlantı hafif.

![1 GB, 100 GB, 1 TB. Same time, every time.](/img/tutorials/tutorial-forking/slide-3.svg)

Fork'lama da aynı şekilde çalışır. 1 GB, 100 GB, 1 TB. Her seferinde aynı süre.

## Neler paylaşılır, neler size aittir

![Many mirrors, one sun: shared base, your changes are yours](/img/tutorials/tutorial-forking/slide-4.svg)

Üst depoyu güneş gibi düşünün. Güneşi tutamazsınız, ama onu yakalayan bir ayna tutabilirsiniz. O ayna sizin fork'unuzdur. Aynaya resim çizin; çizimler size aittir. Güneş, kaç ayna ona baksa da değişmez.

> Güneşi tutamazsınız, ama onu aynada tutabilirsiniz.

## Üst depo daha sonra değişirse ne olur?

![A fork is a frozen photograph; the parent keeps flowing like a river](/img/tutorials/tutorial-forking/slide-5.svg)

Şimdi bir nehri düşünün. Su akmaya devam eder. Her an farklıdır. Fork aldığınızda nehrin o andaki fotoğrafını çekmiş gibi olursunuz; fotoğraf o anda donup kalır. Nehir akmaya devam eder; fotoğrafınız devam etmez.

Üst depo daha sonra değişirse, fork'unuz olduğu yerde kalır.

> Nehri tutamazsınız, ama onu fotoğrafta tutabilirsiniz.

## Disk kullanımı sabit kalır

![Five forks of a 100 GB repo, still about 100 GB total](/img/tutorials/tutorial-forking/slide-6.svg)

İşte bu yüzden diskiniz patlamaz. 100 GB'lık bir deponun beş fork'u mı? Toplam hâlâ yaklaşık 100 GB. Yalnızca her fork'ta değiştirdiğiniz veriler için disk kullanırsınız.

> İstediğiniz kadar fork alın. Diskiniz fark bile etmez.

## Fork'ların *devralmadiği* şey: gizli bilgiler

Fork'un kasıtlı olarak takip etmediği bir şey vardır: gizli bilgiler. Bir fork; API anahtarı, veritabanı parolası, Stripe token'ı olmadan başlar. "Üretimi klonlayın, hiçbir şeyi bozmayın" sloganının gerçekten işe yaramasının nedeni budur. Sandbox'ınız sizi taklit edemeyeceği için gerçek müşterilere fatura kesamaz. Bunu [Gizli Bilgileri Yönetme](/en/docs/tutorial-managing-secrets) öğreticisinde düzgünce ayarlıyoruz.

## İzolasyonu doğrulayın

Her iki depoyu yan yana listeleyin:

```bash
time rdc repo list -m my-server
```

`my-app` ve `my-app:experiment`'in aynı anda çalıştığını göreceksiniz.

Orijinal depoda neyin çalıştığını kontrol edin:

```bash
time docker ps
```

Çalışma süresine dikkat edin. Bunlar orijinal container'lardır. Şimdi fork'a geçin:

```bash
rdc vscode connect -m my-server -r my-app:experiment
```

```bash
time docker ps
```

Aynı görüntüler, ama çalışma süresi taze. Bunlar fork oluşturulduğunda başladı.

Farkı daha belirgin kılın. Fork'a yalnızca bu depoyu içeren bir container ekleyin:

```bash
time docker run --rm -it -d nginx
time docker ps
```

Nginx çalışıyor, ama yalnızca bu fork içinde.

Yıkıcı bir şey deneyin:

```bash
time rm index.html
```

Burada silindi. Şimdi orijinale geri dönün:

```bash
rdc vscode connect -m my-server -r my-app
time docker ps
```

Nginx yok. Fork'un container'ları fork içinde kaldı. `index.html` ise hâlâ burada, dokunulmamış. Orijinal, hiçbir şeyin olduğunu fark etmedi. Aynı görüntüler, ayrı Docker daemon'ları, ayrı dosya sistemleri.

## Temizleyin

İşiniz bittiğinde fork'u silin:

```bash
time rdc repo delete --name my-app:experiment -m my-server
```

Orijinal tam olarak olduğu gibi kalır. **Fork alın, deneyin, bir şeyleri bozun, silin.** Hiçbir risk yok.

---

Sonraki: [Gizli Bilgileri Yönetin](/en/docs/tutorial-managing-secrets).
