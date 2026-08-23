---
title: Proxy ve Executor
description: İstemcinin hiçbir zaman SSH anahtarı ya da makine adresi tutmadığı tarayıcı ve ince istemci komutlarının nasıl çalıştırıldığı
category: Concepts
tags:
  - security
  - networking
subcategory: architecture
order: 4
language: tr
sourceHash: "39ec44d8efc3f9b5"
sourceCommit: "5197d1c0349438c2bff2442377a5166d0b8214b6"
---

# Proxy ve Executor

Normalde `rdc`, kendi yapılandırmanız ve SSH anahtarlarınızla sizin makinenizde çalışır ve sunucularınıza doğrudan bağlanır. Proxy modeli bunu ikiye böler: hiçbir sır tutmayan ince bir istemci ve bu sırları tutup işi yapan bir **executor**. [Web konsolu](/tr/docs/web-console)'nun Çalıştır düğmesi ve CLI'ın `--proxy` bayrağı, ikisi de ince istemcidir ve aynı hat protokolünü konuşur.

## Komut niyeti, komutların kendisi değil

İnce bir istemci hiçbir zaman bir SSH anahtarı, bir makine adresi veya çözülmüş bir yapılandırma tutmaz. Bir şey çalıştırmak istediğinde yalnızca komut niyetini gönderir: komut için bir tanımlayıcı (CLI sözleşmesindeki yolu, örneğin `repo up`) artı parametreler. Executor, komutu aynı sözleşmede arar, onu altta yatan sunucu tarafı fonksiyona çözer, hedef makineyi çözülmüş yapılandırmadan belirler ve her şeyi kendi SSH bağlantısı üzerinden çalıştırır. Çıktı istemciye akış olarak geri döner.

Executor, `rdc serve` ile sunucu olarak başlatılan CLI'ın kendisidir. Operatörlerin bir dizüstü bilgisayarda çalıştırdığı aynı ikili dosya, onlar adına komutları çalıştıran şeye dönüşür. İki yerleşimi vardır:

- **`--mode daemon`**: kontrolünüzdeki bir hostta çalışır, herhangi bir CLI gibi başsız kaydedilir (bkz. [Yapılandırma Depolama](/tr/docs/config-storage)), böylece yapılandırma anahtarını kendi başına türetebilir ve oturum başına bir izne ihtiyaç duymaz. Bu katı katmandır: SSH asla ağınızın dışına çıkmaz.
- **`--mode container`**: sizin için barındırılan, organizasyonunuza özel bir container içinde çalışır. Hiçbir anahtar olmadan başlar ve bir istemci oturum için bir tane vermeden hiçbir şey yapamaz. Bu kolaylık katmanıdır.

## CEK izni

Yapılandırma deposu sıfır bilgi ilkesiyle çalışır: sunucu yalnızca şifreli blob'lar saklar, içerik şifreleme anahtarı (CEK) yalnızca onu açmış bir istemcide düz metin olarak var olur. Bu yüzden container modundaki bir executor'a anahtarın *izin olarak verilmesi* gerekir ve bu izin, anahtarı bu sırada sunucuya açık etmemelidir.

Akış şöyledir: kilidi açılmış bir tarayıcı, executor ile bir oturum açar, oturumun genel anahtarını alır ve CEK'i X25519 kullanarak bu oturuma mühürler. Mühürlenmiş blob, hesap sunucusundan geçer, ancak sunucu onu açamaz, dolayısıyla sıfır bilgi özelliği uçtan uca korunur. Executor, CEK'in şifresini yalnızca RAM'de çözer, 30 dakikalık bir hareketsizlik süresiyle; hiçbir şey diske yazılmaz. Sonraki komut istekleri, izin verilen oturuma `X-Config-Session` başlığı üzerinden atıfta bulunur.

Denetim açısından önemli bir ayrıntı: aynı kullanıcı kimliği her üç aşamayı da kapsar (oturum açma, anahtar izni verme, komut çalıştırma). Hesap sunucusu kendi kimlik bilgisini asla executor'a iletmez. Her aşama için gerçek kullanıcıya atfedilen kısa ömürlü bir token üretir ve o kullanıcının üyeliğini her seferinde yeniden kontrol eder. Executor, kendisine sunulan her token'ı harekete geçmeden önce doğrular. Bir kullanıcının verdiği izin başka bir kullanıcı tarafından kullanılamaz.

Bir yapılandırmanın `state` yarısı (hosta özel çalışma zamanı verisi) yapılandırma blob'unda hiç seyahat etmez, dolayısıyla bu yoldan da bir executor'a asla ulaşmaz.

## Proxy üzerinden ne çalıştırılabilir

Her komut uzaktan çalıştırılmaya uygun değildir. Sözleşmedeki her komut bir `proxyCapable` bayrağı taşır ve executor bunu, herhangi bir politika yapılandırmasından bağımsız olarak sunucu tarafında zorunlu kılar:

- **Makine düzlemi, etkileşimsiz komutlar** (dağıtım, yedekleme, durum, günlükler ve benzerleri) proxy'ye uygundur.
- **Yapılandırma düzlemi komutları** uygun değildir: bunlar yapılandırmayı düzenler, bu yol üzerinde bu işin sahibi tarayıcıdır (web konsolu bunları kendi yapılandırma düzenleyicisine yönlendirir).
- **Etkileşimli komutlar** (terminaller, VS Code oturumları) uygun değildir: bu hat üzerinde TTY yoktur.
- **İstemci tarafı aktarım komutları** (`rdc repo sync`) uygun değildir: bunlar veriyi *istemcinin* dosya sistemi ile bir makine arasında taşır ve executor'ın istemcinin dosyalarına erişimi yoktur.

Web konsolu, bir komutun Çalıştır düğmesi alıp almayacağına karar vermek için aynı bayrağı okur, ancak executor, istemci ne gönderirse göndersin uygun olmayan komutları reddeder.

## Sahte (mock) executor

Geliştirme ortamında, gerçek bir executor yapılandırılmadığında, hesap sunucusu komut isteklerini kendisi, sahte akışlar ve açıkça uydurma verilerle (kaynak adları `mock-` önekiyle) yanıtlar. Bu, bir makine veya kilit açma olmadan konsolun tamamının, formlar, akış ve sonuç render'ı dahil, denenebilir olmasını sağlar. Gerçek çalıştırma gerçek bir executor gerektirir.

## İlgili

- [Web Konsolu](/tr/docs/web-console), bu model üzerine kurulu tarayıcı istemcisi
- [Yapılandırma Depolama](/tr/docs/config-storage), CEK'in koruduğu sıfır bilgi depo
