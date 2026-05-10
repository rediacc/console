---
title: "İlk Deponuzu Oluşturun"
description: "Sunucunuzda şifreli bir depo oluşturun ve VS Code'da açın."
category: "Tutorials"
subcategory: essentials
order: 4
language: tr
sourceHash: "1294b0494f20671b"
---

# İlk Deponuzu Oluşturun

Rediacc deposu, sunucunuzdaki tek bir şifreli dosyadır. Bağlandığında; kendi Docker daemon'ı ve kendi uygulama verisiyle birlikte bir klasöre dönüşür: tamamen izole, tamamen taşınabilir.

Bunu üretim için bir USB sürücü gibi düşünebilirsiniz: depolandığında bir dosya, çalıştırıldığında bir sunucu.

## Öğreticiyi izleyin

![Tutorial: Creating your first repository](/assets/tutorials/tutorial-create-repo.cast)

## Diskte dosya, bağlandığında ortam

![Encrypted file mounts as an isolated folder](/img/tutorials/tutorial-create-repo/slide-1.svg)

Diskteki hali tek bir şifreli görüntüdür. Bağlandığında şunları elde edersiniz:

- Ayrılmış bir Docker daemon'ı (ana sisteminkinden bağımsız)
- Şifreli birim içinde uygulama verisi
- Sunucudaki başka hiçbir şeyle çakışmayan geri döngü IP'leri

Depolar taşınabilir. Bir depoyu makineler arasında taşıyabilir, yedekleyebilir veya anında fork'layabilirsiniz. Her depo, aynı sunucudaki diğer depolardan tamamen izole edilmiştir.

## Depo oluşturun

```bash
time rdc repo create --name my-app -m my-server --size 2G
```

Bu komut `my-server` üzerinde 2 GB şifreli bir depo oluşturur. Doğrulayın:

```bash
time rdc repo list -m my-server
```

## VS Code'da açın

```bash
rdc vscode connect -m my-server -r my-app
```

VS Code doğrudan depo içinde açılır. Çalışma alanının boş olduğunu fark edeceksiniz. Bu, izole ortamınızdır. Burada oluşturduğunuz her şey şifreli birim içinde yaşar; aynı sunucudaki başka hiçbir depo göremez.

---

Sonraki: [İlk Uygulamanızı Dağıtın](/en/docs/tutorial-deploy-app).
