---
title: "İlk Uygulamanızı Dağıtın"
description: "renet dev up komutunu kullanarak yerleşik bir şablondan container tabanlı bir uygulama dağıtın."
category: "Tutorials"
subcategory: essentials
order: 5
language: tr
sourceHash: "f75b5b6a716e94bf"
---

# İlk Uygulamanızı Dağıtın

Elinizde boş bir depo var. `rdc`, sıfırdan `docker-compose` yazmak zorunda kalmadan gerçek uygulamalar ayağa kaldırmanızı sağlayan yerleşik şablonlar sunar. Üç adım: bir şablon seçin, uygulayın, çalıştırın.

## Öğreticiyi izleyin

![Tutorial: Deploying your first app](/assets/tutorials/tutorial-deploy-app.cast)

## Seç - Uygula - Çalıştır

![Pick a template, apply it, run it](/img/tutorials/tutorial-deploy-app/slide-1.svg)

## Adım 1: Seç

Mevcut şablonlara göz atın:

```bash
time rdc repo template list
```

Postgres, Redis, web sunucuları ve daha fazlası için hazır kurulumlar göreceksiniz.

## Adım 2: Uygula

Şablonu deponuza ekleyin. `app-postgres` şablonunu kullanacağız:

```bash
time rdc repo template apply --name app-postgres -m my-server -r my-app
```

Depoda iki yeni dosya oluşur: `docker-compose.yml` ve `Rediaccfile`. Compose dosyası container'ları tanımlar; `Rediaccfile` ise uygulamanın başlarken ve dururken ne yapacağını belirtir (`up` ve `down` yaşam döngüsü kancaları).

## Adım 3: Çalıştır

Önceki öğreticideki VS Code bağlantısı aracılığıyla deponun sandbox'ının içindesiniz; dolayısıyla `renet`'i doğrudan kullanabilirsiniz:

```bash
time renet dev up
```

Hepsi bu kadar. Uygulamanız çalışıyor. Doğrulayın:

```bash
time docker ps
```

Buradaki `docker ps` yalnızca bu depoya ait container'ları listeler. Aynı sunucudaki diğer depolar kendi Docker daemon'larına sahiptir ve bu görünümden tamamen görünmezdir.

---

Sonraki: [Deponuzla Çalışın](/en/docs/tutorial-work-with-repo).
