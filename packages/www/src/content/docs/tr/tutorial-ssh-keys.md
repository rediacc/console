---
title: "SSH Anahtar Yapılandırması"
description: "SSH anahtarınızı yapılandırın; rdc sunucularınıza parola olmadan bağlansın."
category: "Tutorials"
subcategory: essentials
order: 2
language: tr
sourceHash: "009a1bd345e93413"
---

# SSH Anahtar Yapılandırması

`rdc`, sunucularınıza SSH üzerinden bağlanır. Bu nedenle her sunucunun SSH anahtarınıza güvenmesi gerekir. Toplamda üç adım vardır. İlk ikisi tek seferlik kurulum gerektirirken üçüncüsü eklediğiniz her yeni sunucu için tekrarlanır.

## Öğreticiyi izleyin

![Tutorial: SSH key configuration](/assets/tutorials/tutorial-ssh-keys.cast)

## Üç adım

![Generate, copy, register](/img/tutorials/tutorial-ssh-keys/slide-1.svg)

1. Dizüstü bilgisayarınızda bir SSH anahtarı **oluşturun**. Yalnızca bir kez yapılır.
2. Anahtarı sunucunuza **kopyalayın**. Her yeni sunucu için tekrarlanır.
3. Anahtarı `rdc`'ye **kaydedin**. Yalnızca bir kez yapılır.

## Adım 1: Anahtar oluşturun

Kullanmak istediğiniz bir anahtarınız zaten varsa bu adımı atlayabilirsiniz. Aksi hâlde:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519
```

`ed25519`, küçük boyutlu, hızlı ve geniş destekli modern standarttır.

## Adım 2: Anahtarı sunucunuza kopyalayın

```bash
ssh-copy-id -i ~/.ssh/id_ed25519 user@your-server-ip
```

`user` ve `your-server-ip` kısımlarını kendi SSH kullanıcısı ve sunucu IP'niz ile değiştirin. Sunucu parolanız son kez istenecektir. Bu adımdan sonra parola ile kimlik doğrulama artık gerekmez.

## Adım 3: Anahtarı `rdc`'ye kaydedin

```bash
time rdc config ssh set --key ~/.ssh/id_ed25519
```

Hepsi bu kadar. Bundan sonra her `rdc` komutu bu anahtarla kimlik doğrulaması yapar. Artık parola gerekmez, etkileşimli istemler de olmaz.

---

Sonraki: [İlk Sunucunuzu Ekleyin](/en/docs/tutorial-add-server).
