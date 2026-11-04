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
sourceHash: "c7310ede42dd2da0"
sourceCommit: "cce23c4daecfe425f572f17d98ad6dd1f4bce5d7"
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

## Executor'ın hangi adreslerden bağlanacağını kısıtlama

Yapılandırmanın `access` bölümü, SSH anahtarları için izin verilen IPv4 ve IPv6 kaynak aralıklarını tutar. Aralıklar yapılandırma genelinde, anahtar başına ve makine başına belirlenebilir; böylece bir makine bir anahtarı yalnızca kendi executor'ının bağlandığı adreslerden kabul eder.

- `rdc config access add <key> --public-key ... --hosted-executor` bir anahtarı kaydeder ve barındırılan executor'ın iki aralığını ekler: `104.28.0.0/16` ve `2a09:bac0::/29`. İkisi de gözlemlenmiş Cloudflare çıkış aralıklarıdır; Cloudflare'in yayımladığı bir liste değildir, bu yüzden değişebilirler.
- `rdc machine access set <machine> --key <key>` bir makineye anahtar atar; `--ipv4`, `--ipv6` ve `--clear-ranges` o makinenin aralıklarını ayarlar.
- `rdc machine access push <machine>` erişim satırlarını makineye yazar; `--dry-run` hiçbir şeyi değiştirmeden sonucu gösterir.
- `rdc machine access show <machine>` geçerli erişim satırlarını yazdırır.

`machine setup` erişim satırlarını yeniden uygular, böylece yeniden kurulan bir makine kısıtlamalarına geri kavuşur.

Mevcut SSH oturumunu dışarıda bırakacak bir push, adresi kullanılan anahtarın aralıklarının dışında kaldığı için `ACCESS_LOCKOUT` ile reddedilir ve hiçbir şey yazılmaz. Dosya makinede bu arada değiştiyse push `ACCESS_FILE_CHANGED` ile reddedilir; hiçbir şey uygulanmadığından push güvenle yeniden denenebilir.

## İşler, biletler ve yoklama

Makine düzlemindeki her komut, makinede bir iş olarak çalışır: renet'in yönettiği bir systemd birimi; durumu ve olay günlüğü makinedeki bir spool'da tutulur. Bağlantının kopması bu yüzden işi hiçbir zaman durdurmaz ve herhangi bir istemci işi kimliğiyle yeniden devralabilir.

- **Bağlanma penceresi.** Yürütücü bir işin olaylarını en fazla 20 saniye boyunca akıtır; akış sessizken her 10 saniyede bir heartbeat satırı gönderir. Pencere içinde biten bir iş sonucunu aynı istekte döndürür. Daha uzun süren bir iş, makineyi ve çakışan işleri taşıyan bir `job` satırından sonra `state: running` ve iş kimliğiyle bir sonuç döndürür.
- **Yoklama.** İstemci bundan sonra `GET /v1/jobs/<id>/poll` ile son gördüğü satırdan sonraki olayları işin durumuyla birlikte ister ve cevaplar boş geldikçe aralıkları açar. `POST /v1/jobs/<id>/cancel` işi iptal eder. Her iki yol da işi başlatan komutla aynı ilkeyi uygular ve bir uç durumu ilk gören yoklama denetim olayını yalnızca bir kez yazar.
- **Biletler.** Her çağrı ayrıca CLI'ın yapılandırma dizinine bir bilet yazar (`jobs/<config>.jsonl`). `rdc job wait <id>` bir işi bekler ve işin çıkış koduyla biter; `rdc job list`, `status`, `logs`, `cancel` ve `gc` gerisini yönetir. İzleme sırasında Ctrl-C iptal etmeden ayrılır ve 130 ile çıkar. Bağlantısı yeniden kurulamayan bir izleme 16 ile çıkar ve bileti korur.
- **Adımlar.** Bir işi izleyen çalışma, örneğin bir sonucu yapılandırmaya kaydetmek veya bir listeyi göstermek, bilete ve spool'a yazılan bir adımdır. Bir adım, işin bittiğini ilk gören yerde bir kez çalışır: komutun kendisi, `rdc job wait`, sonraki komutun yazdığı bildirim ya da yürütücünün yoklaması. Hak makinede alınır; böylece iki gözlemci aynı adımı asla çalıştırmaz.
- **Çakışmalar.** Aynı depoda veya aynı makinede canlı bir işle çakışan bir başlatma, canlı işe bağlanan komutu içeren bir uyarı yazdırır. Çakışma ilkesi başlatmayı reddettiğinde komut 15 (`BUSY`) ile çıkar ve ret, çakışan işleri `overlaps` içinde taşır.
- **İstisnalar.** Etkileşimli komutlar, istemci tarafı aktarımlar ve `job` komutlarının kendisi iş olarak çalışmaz.
- **Saklama.** Makine bitmiş salt okunur bir işi bir saat, bitmiş diğer her işi yedi gün saklar ve en çok 2000 bitmiş iş tutar.

## İlgili

- [Web Konsolu](/tr/docs/web-console), bu model üzerine kurulu tarayıcı istemcisi
- [Yapılandırma Depolama](/tr/docs/config-storage), CEK'in koruduğu sıfır bilgi depo
