---
title: "Şifreli Disk Görüntüleri için git diff: Şifreyi Çözmeden Fork'ları Karşılaştırma"
description: "rdc repo diff, şifrelenmiş görüntüleri blok düzeyinde karşılaştırarak A/M/D/R raporluyor. Anahtar kullanılmaz. Maliyet depo boyutuna değil, değişen bloklara göre ölçekleniyor."
author: Muhammed Fatih Bayraktar
publishedDate: 2026-05-28
category: guide
tags:
  - luks
  - btrfs
  - ext4
  - fiemap
  - cli
featured: false
language: tr
sourceHash: "516ffb7de9941f15"
sourceCommit: "0a3e9865997659698502ad551e078be854b4b2c4"
---

> **Özet.** `rdc repo diff`, iki fork'lu depo arasındaki dosya düzeyindeki farkı `git status --short` gramerinde (A/M/D/R) gösterir ve hiçbirinin şifresini çözmez.
>
> - İki LUKS görüntü dosyasını blok düzeyinde FIEMAP ioctl ile karşılaştırır; bu yalnızca extent haritası meta verisini okur. Hiçbir anahtar yüklenmez, düz metin okunmaz.
> - aes-xts uzunluk koruyucudur ve her 512 baytlık sektörü bağımsız olarak şifreler; bu nedenle değişen bir düz metin sektörü, aynı ofset konumunda değişen bir şifreli metin sektörüdür (16 MiB LUKS veri ofseti kadar kaydırılmış). Ofseti çıkar, cihaz aralıklarını ext4 extent haritası ve inode yürüyüşü aracılığıyla dosya adlarına eşle; dosya listesini elde edersin.
> - Maliyet, değişen blok sayısına göre ölçeklenir, depo boyutuna göre değil. 1 GB fork ile 100 GB fork aynı milisaniyelerde farklılaşır; karşılaştırma yalnızca meta veridir.

Kısaca, Rediacc'ta bir fork, bir deponun LUKS görüntüsünün `cp --reflink=always` kopyasıdır. Anlıktır ve boyutla ilgilenmez. 100 GB'lık bir depo, 1 GB'lık depo kadar hızlı fork'lanır. Kulağa pazarlama gibi gelebilir ama reflink'lerin çalışma biçimi tam olarak bu: btrfs extent haritasını kopyalar ve altındaki blokları paylaşır. Buna sıkı sıkıya güveniyoruz. Fork'lar test sandbox'ı, geçici dal ve işiniz bittiğinde çöpe attığınız staging kopyasıdır.

Eksik olan şey, bir sonraki açık soruya ucuz bir yanıttı: bu fork aslında neyi değiştirdi. Naif yol şu: fork'u bağla, LUKS konteynerini aç, iç ext4'ü dolaş, her dosyayı üst depoya göre hash'le. Bu, hem okuma hem de şifre çözme açısından depo boyutuyla ölçeklenir. Anahtarların diff yolunda canlı olmasını gerektirir. Üstelik depolama katmanının zaten ücretsiz olarak bildiği tek şeyi çöpe atar: hangi bloklar ayrışmış. `rdc repo diff` başka bir yol kullanır. Değişen bloklarla ölçeklenir. Hiçbir anahtar yüklemez. Dosya listesini iki şifreli görüntüyü farklılaştırarak alır.

## Farklılaştırdığınız yığın

"İki depo"nun diskte ne anlama geldiğini tam olarak belirteyim. Tüm numara buna dayanıyor. Alttan yukarıya: bir SSD, ana depolama, bir btrfs havuzu. Bunun üstünde, depo başına bir LUKS2 görüntü dosyası. Kilidi açarsanız bir dm-crypt cihazı elde edersiniz. İçinde konteynerlerin kullandığı ext4 dosya sistemi yaşar. Bir depo, btrfs havuzundaki bir dosyadır.

Bir fork bu dosyanın reflinkidir. Fork'tan hemen sonra iki görüntü dosyası bayt bayta özdeştir. Her fiziksel bloğu paylaşırlar. Üst depo ve fork verinin iki kopyası değildir. Aynı bloklara işaret eden iki extent haritasıdır. Fork içinde yazdığınızda, depolama katmanı değişen bölge için yeni bir blok tahsis eder. Yalnızca o fork'un extent haritası yeniden yazılır. Üst deponun blokları dokunulmaz.

Yani "iki depoyu farklılaştır" ifadesi "extent'lerinin çoğunu paylaşan iki dosyayı farklılaştır" ifadesine indirgenir. Çekirdek bunu zaten yanıtlayabilir. Kimsenin her iki dosyadan tek bir bayt okumasına gerek yoktur.

## FIEMAP: Çekirdeğe okumadan neyin değiştiğini sormak

FIEMAP ioctl, bir dosyanın extent haritasını döndürür: (mantıksal ofset, fiziksel ofset, uzunluk) tuple'larının listesi. Her tuple, dosyanın bir bölümünün diskte nerede yaşadığını söyler. Bu saf dosya sistemi meta verisidir. Dosya verisi okumaz. Şifreli bir görüntü için anahtar gerekmez. Şifreli metin, çekirdeğin hiçbir zaman yorumlamak zorunda olmadığı baytlardır.

İki extent haritasını farklılaştır. Her iki fork'un da aynı fiziksel bloğu gösterdiği mantıksal aralıklar paylaşılmış demektir. Paylaşılan, özdeş demektir; çünkü cihazda kelimenin tam anlamıyla aynı bloktur. Fork'un kendi özel bloğuna sahip olduğu aralıklar yazmalardır. Bunlar değişen bloklardır. Bunları depolama katmanının zaten tuttuğu meta veriden aldık.

Maliyet hikayesi buradan geliyor. FIEMAP karşılaştırması extent kayıtlarını okur, veri okumaz. İşi kaç extent'in değiştiğiyle ölçeklenir, depo boyutuyla değil. 1 GB fork ve 100 GB fork aynı kısa özel extent listesini döndürür. Aynı dosyaları değiştirdiyseler aynı milisaniyeler. Dürüst uyarı: extent yürüyüş süresi boyutla değil görüntü parçalanmasıyla ölçeklenir. Yoğun rastgele yazma altındaki bir kopyala-yaz görüntüsü extent biriktirir. Tam `filefrag` yürüyüşü, ölçtüğüm en kötü parçalanmış üretim görüntüsünde 3,19 saniye sürdü. Parçalanma kıyaslama yazısına bakın. Bu meta veri tarafındaki tavandır. Bir arka plan taramasıdır, veri okuması değil.

## Değişen bir bloktan iki şifreli katman üzerinden dosya adına

Şifreli görüntüdeki değişen bayt aralıklarının listesi henüz kullanışlı değil. Aralıklar şifreli metindeki konumlardır. İstediğiniz adlar iki katman yukarıda, iç ext4'te. Aralarındaki köprü adres aritmetiğidir, şifre çözme değil.

LUKS, aes-xts ile şifreler. Uzunluk koruyucudur ve her 512 baytlık sektörü kendi başına şifreler. Değişen bir düz metin sektörü, aynı ofset konumunda değişen bir şifreli metin sektörü üretir. Tek fark LUKS veri ofsettir. Bu, şifreli yükün önündeki 16 MiB başlık ve anahtar yuvalarıdır. Bu ofseti her değişen görüntü aralığından çıkar. Artık dm-crypt cihazındaki eşleşen aralığa sahipsiniz. Bu, iç ext4'ün üzerinde oturduğu blok cihazıdır. Hiçbir anahtar kullanılmadı. Bu bir çıkarmadır.

Şimdi cihaz aralıklarını dosyalara eşle. ext4 de inode başına extent haritası tutar. Aynı (mantıksal, fiziksel, uzunluk) yapısı. Bağlı iç dosya sisteminde FIEMAP aracılığıyla ulaşırsınız. İnode'ları bir kez dolaşarak bloktan dosyaya dizin oluşturun. Sonra her değişen cihaz aralığını bu dizinde arayın. Bir inode'un 1234 veri extent'leriyle örtüşen aralık, o inode'un yoluna aittir. Bu yol değişen dosyadır.

Bunun hiçbir zaman yapmadığını açıkça belirteyim. Değişen görüntüden hiçbir zaman düz metin türetmez. Bilinen ofsetlerde dosya sistemi yapısını okur. Bunu hem şifreli tarafta hem de şifresi çözülmüş tarafta yapar. Sonra ikisini adresle birleştirir. Blok filtresi hangi cihaz bölgelerinin taşındığını söyler. ext4 extent haritası hangi dosyanın her bölgeye sahip olduğunu söyler. Her iki adım da bir bloğun değişip değişmediğine karar vermek için değişen bloğun içeriğini incelemez.

## Eklemeler, silmeler ve yeniden adlandırmalar: inode kimlik yürüyüşü

Değişiklikler doğrudan blok karşılaştırmasından çıkar. Eklemeler, silmeler ve yeniden adlandırmalar için bir gözlem daha gerekir. Reflink bunu bize ücretsiz verir: fork, inode numaralarını korur. Tüm görüntüyü yeniden bağlamak, herhangi bir şey ayrışmadan önce iç dosya sistemini bayt bayta klonlar. Yani üst depoda var olan bir inode, fork'ta aynı numaraya sahiptir.

Bu, kimliği bir küme karşılaştırması yapar. Her iki tarafta da farklı bir yola sahip inode yeniden adlandırmadır. Yalnızca yeni tarafta olan inode eklemedir. Yalnızca eski tarafta olan inode silmedir. Yeniden adlandırma, cihaz extent örtüşmesiyle onaylanır. Yeniden adlandırılan dosyanın veri blokları her iki fork'ta da aynı cihaz ofsetlerinde durur. İki fork tek bir koordinat sistemini paylaşır. Bu örtüşme aynı zamanda ilgisiz veriler için inode numarasının yeniden kullanılmasını da dışlar. Saf bir yeniden adlandırma, dosyanın veri bloklarının değişmeden görünmesiyle ortaya çıkar. Yalnızca dizin girişi taşındı.

İşte varsayılan isim-durum formu, `git status --short`'tan zaten okuduğunuz A/M/D/R grameri:

```
$ rdc repo diff --name test-1gb:fork1 -m hostinger
M  hello.txt

1 file changed: 0 added, 1 modified, 0 deleted, 0 renamed
```

1 GB'lık bir depoda değişen bir dosya. Hiçbir dosya verisi okunmayan bir blok karşılaştırmasından raporlandı. Hiçbir şeyin kilidi açılmadı.

Varsayılan, doğruluk için bir şey daha yapar. Blok filtresi bir üst kümedir. Bir btrfs extent, gerçekten değişen baytlardan daha fazlasını kapsayabilir. Dolayısıyla bir dosyaya yapılan yazma, bir extent'i paylaşan komşuyu işaretleyebilir. Değişmeyen bir dosyayı raporlamaktan kaçınmak için varsayılan, blokla işaretlenen her adayı onaylar. Yalnızca o dosyayı her iki tarafta hash'ler. Adayları hash'ler, depoyu değil. Onay maliyeti hâlâ değişiklik kümesini izler. `--fast`, blok filtresine güvenir ve onaylamayı atlar. Hızlı yanıt istediğinizde ve ara sıra yanlış pozitifi tolere ettiğinizde kullanın.

## Bir yapay zeka ajanının neden buna ihtiyacı var

Bu komutun var olmasının nedeni ajan iş akışıdır. Ajanların üretimi fork'layıp değişiklik yapmasını ve ardından gerçekte neye dokunduklarını temiz bir şekilde raporlayamamasını izlemeye devam ettim. Bir yapay zeka ajanı üretimi anlık olarak fork'layabilir. Riskli bir değişikliği izole fork içinde çalıştırır. Sonra herhangi bir şeyi geri tanıtmadan önce tam olarak neye dokunduğunu bilmesi gerekir. Fork daldır. Diff incelemedir.

Ajan isim-durumu okumaz, `--json` okur:

```
$ rdc repo diff --name prod:experiment --json -m hostinger
```

Yapılandırılmış çıktı ajana kesin bir değişiklik kümesi verir: hangi yolları değiştirdiği, oluşturduğu, sildiği. `--stat` ile bayt ve blok cinsinden dosya başına değişiklik boyutu. Tanıtmadan önce farkını gören bir ajan, üretim yakınına izin verebileceğiniz ajandır. Patlama yarıçapı incelenebilir, savunulabilir değil. Diğer modlar aynı inceleme döngüsüne hizmet eder. `--name-only`, yalın yol listesi için. `--content <path>`, tek bir dosyanın birleşik metin farkı için (yalnızca metin; bir ikili dosya `Binary files differ` bildirir). `--stat`, ajan neyin değiştiğini ve ne kadar değiştiğini bilmek istediğinde.

## DR testinin neden buna ihtiyacı var

Aynı ilkel, eskiden risk almadan sormak garip olan bir DR sorusunu yanıtlar. Üretimi fork'la. Bir yedek fork'a geri yükle. Fork'u üretime göre farklılaştır. Fark, geri yüklemenin beklediğiniz dosya setini yeniden oluşturup oluşturmadığını söyler. Bunu üretimi durdurmadan yapar. Diff yolunda hiçbir şeyin şifresini çözmez.

Bu, bir programa çalıştırabileceğiniz bir prova. Geri yükleme izole bir fork'a düşer. Fark, deltayı git gramerinde raporlar. Temiz bir prova: değişen set, yedeğin içermesi beklenen şeyle eşleşir. Canlı üretime karşı kurtarmayı doğruluyorsunuz. Kopya yapmak ücretsiz, çöpe atmak ücretsiz.

## Dürüst sınırlar

İçerik farkı yalnızca metindir. `--content`, metin dosyaları için birleşik fark üretir. Diğer her şey için git'in yaptığı gibi `Binary files differ` raporlar. Şifrelenmiş sonra sıkıştırılmış bir blob'un satır odaklı farkı gürültüdür.

İlgili fork'ları farklılaştırır, rastgele depoları değil. Tüm mekanizma paylaşılan bir koordinat sistemine dayanır. Paylaşılan extent'ler eşitliği kanıtlar. Korunan inode numaraları kimliği çapalar. Ortak bir veri ofseti hepsini bir arada tutar. Ortak bir atadan hiç fork'lanmamış iki depo bunların hiçbirini paylaşmaz. Aralarında ucuz bir fark yoktur. Bu özellik, hata değil. Tıpkı ilgisiz geçmişler arasındaki `git diff`'in anlamlı olmaması gibi.

Yeniden adlandırma tespiti inode tabanlıdır. Dosya sisteminin gerçekten yeniden adlandırma olarak kaydettiği yeniden adlandırmalar için kesindir. Aynı içerikle yeni bir ad altında önce silip sonra oluşturmak? İnode tablosuna iki işlem. Bu nedenle bir silme ve bir ekleme olarak raporlar, yeniden adlandırma olarak değil. Git'in içerik benzerliği sezgiselliği buna yeniden adlandırma der. İnode yürüyüşü demez. Bu, dosya sisteminin yaptığı şey hakkında doğru yanıttır. İnsan niyeti hakkındaki yanıt olmasa bile.

Meta veri yürüyüşü parçalanmayla ölçeklenir. Yoğun parçalanmış bir görüntüde extent numaralandırması milisaniyeler değil saniyeler alır. Yine de depo boyutundan bağımsızdır. Yine de herhangi bir veri okumasından bağımsızdır. Ama en kötü parçalanmış görüntülerde kelimenin tam anlamıyla anlık değildir.

## Sonuç

`rdc repo diff`, şifrelenmiş, çalışan altyapıya sürüm kontrolü ergonomisi katar. Arayüz kasıtlı olarak git'tir: A/M/D/R, birleşik farklar, `--stat`. Öğrenilecek yeni bir şey yok. `git status --short` okuyabiliyorsanız, iki LUKS görüntüsü arasındaki farkı okuyabilirsiniz. Alttaki mühendislik önem vermeye değer olan kısımdır. İki redde kadar indirgenir. Hiçbir zaman şifreyi çözmez. aes-xts, blok düzeyinde FIEMAP karşılaştırmasının her değişen sektörü adresle bulmasına izin verir. Ve hiçbir zaman değişmeyen veri için ödeme yapmaz. Depolama katmanı hangi blokların ayrışmış olduğunu zaten kaydetti. Fork daldır. Diff incelemedir. İnceleme, değişikliğin maliyetine mal olur, deponun ağırlığına değil.
