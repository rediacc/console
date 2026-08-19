---
title: Web Konsolu
description: Formlar, kaynak seçiciler ve çalıştırma geçmişiyle tüm rdc CLI'ını tarayıcınızdan yönetin
category: Guides
tags:
  - cli
  - account
order: 8
language: tr
sourceHash: "972ed654ae294102"
sourceCommit: "5197d1c0349438c2bff2442377a5166d0b8214b6"
---

# Web Konsolu

Web konsolu, tüm `rdc` CLI'ının üzerine kurulu bir tarayıcı arayüzüdür. Her CLI komutu, konsolda bir form, doğrulama, kaynak seçiciler ve bir Çalıştır düğmesiyle görünür. Ayrı bir "web özellik seti" yoktur: konsol CLI sözleşmesinden üretilir, dolayısıyla CLI'da olan her komut konsolda da vardır ve yeni komutlar otomatik olarak ortaya çıkar.

Web portalında `/account/console` adresinde bulunur.

## Erişilebilirlik

Web konsolu ücretli bir özelliktir. Ücretli planlara dahildir ve Community planında gizlidir. Erişim ayrıca rol bazlı kısıtlanmıştır, böylece bir organizasyon yöneticisi kimlerin gördüğünü kontrol edebilir.

## Yapılandırma deposuyla ilişkisi

Konsol, kaynaklarınızı (makineler, depolar ve benzerleri) şifreli yapılandırma deponuzdan okur ve bu yapılandırmanın şifresini yalnızca tarayıcıda çözer. Bu şu anlama gelir:

- **Kilitliyken** bile, komut kataloğunun tamamına göz atabilir, herhangi bir komutun formunu açabilir ve parametrelerini okuyabilirsiniz. Bu, herhangi bir kurulum gerektirmeden çalışır.
- **Komut çalıştırmak ve seçicileri kullanmak için** önce yapılandırma deponuzun kilidini açmanız gerekir (passkey, ana parola veya kurtarma kodu, bkz. [Yapılandırma Depolama](/tr/docs/config-storage)). Çalıştır düğmeleri, kaynak sayfaları ve kaynak seçicilerinin hepsi açık oturuma bağlıdır.

Şifresi çözülmüş anahtar yalnızca tarayıcı belleğinde kalır. Sayfayı yenilemek konsolu yeniden kilitler ve 30 dakikalık hareketsizlik onu otomatik olarak kilitler.

## Kaynak seçiciler

Kilit açıldıktan sonra, komut formları serbest metin alanlarını şifresi çözülmüş yapılandırmanızdan beslenen seçicilerle değiştirir: makineler, depolar, veri depoları, storage'lar, kümeler, bulut sağlayıcıları ve yedekleme stratejileri. Bazı seçiciler bunun yerine canlı olarak çözülür, bir komut çalıştırılarak; örneğin bir makinedeki container'lar veya bir veri deposundaki anlık görüntüler gibi.

Seçiciler birbirine bağımlı olarak filtrelenir: bir makine seçin, depo seçici o makineye daralır. Depo referansları için bir ref oluşturucu, tek tek seçimlerden tam `name:tag@machine` biçimini oluşturur. Seçiciler ipucudur, kısıtlama değildir; her zaman bir değeri elle yazabilirsiniz.

## Komutları çalıştırma

Tarayıcı hiçbir zaman bir SSH anahtarı veya makine adresi tutmaz. Çalıştır'a tıkladığınızda, konsol yalnızca komut niyetini gönderir (hangi komut ve hangi parametreler) ve bir executor geri kalan her şeyi çözüp çalıştırır. Bunun nasıl çalıştığını ve hangi komutların bu şekilde çalışabileceğini görmek için [Proxy ve Executor](/tr/docs/proxy-and-executor) sayfasına bakın.

Yalnızca yapılandırmanızı düzenleyen komutlar (örneğin bir makine girdisi oluşturmak) uzaktan hiç çalışmaz. Konsol bunları, değişikliğin şifrelenip diğer her yapılandırma düzenlemesi gibi gönderildiği yerleşik yapılandırma düzenleyicisine yönlendirir.

Her form ayrıca eşdeğer CLI komut satırını gösterir, böylece konsolda kurduğunuz her şeyi doğrudan bir terminale veya betiğe kopyalayabilirsiniz.

## Yolunuzu bulma

- **Kaynak sayfaları**: makineler, depolar ve işler, ilgili komutları eylem olarak eklenmiş liste ve ayrıntı sayfalarına sahiptir.
- **Komut paleti**: herhangi bir komuta veya kaynağa adıyla atlamak için Cmd-K (Ctrl-K) tuşlarına basın.
- **Çalıştırma geçmişi**: geçmiş çalıştırmalar oturum başına saklanır, böylece çıktıyı inceleyebilir ve aynı parametrelerle yeniden çalıştırabilirsiniz.

## İlgili

- [Yapılandırma Depolama](/tr/docs/config-storage), şifreli yapılandırma deposunu kurma ve kilidini açma
- [Proxy ve Executor](/tr/docs/proxy-and-executor), Çalıştır düğmesinin arkasındaki çalıştırma modeli
