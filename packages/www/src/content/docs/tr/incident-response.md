---
title: "Olay Müdahalesi: Soruşturma, Bildirme ve Kanıtı Koruma"
description: "Bir depo veya makine üzerinde soruşturma açın, denetim, çalıştırmalar, akışlar ve dosya açmalardan oluşan tek bir zaman çizelgesi okuyun, özet zincirlerini doğrulayın, kanıtı dondurmak ve 24 saatlik, 72 saatlik ve bir aylık süreleri başlatmak için olay bildirin ve hepsini rdc ile yönetin."
category: "Guides"
tags:
  - security
  - compliance
subcategory: data-protection
order: 10
language: tr
sourceHash: "0e7681b5366968f0"
sourceCommit: "f9ac63ac37dff49f6c980f00fdacb7e41099ce81"
---

# Olay Müdahalesi

Buradaki olay, müşterinin kendi depolarının içinde gerçekleşen olaydır. Soruşturma sayfası, `rdc incident` komutları ve `rdc repo flows` ile `rdc repo opens` okuyucularının hepsi [adli analiz](/tr/docs/forensics) bölümünde anlatılan kayıtlarla çalışır. Rediacc'in kendi sistemlerindeki olaylar [güvenlik olayı müdahalesini](/tr/docs/security-incident-response) izler.

## Erişim

Soruşturma için ücretli plan ve sahip veya yönetici rolü gerekir. Soruşturma açmak yakın zamanda yeniden kimlik doğrulama ister ve açılmış bir soruşturma 60 dakika geçerli kalır. Her görüntüleme denetim günlüğüne yazılır.

Rediacc desteği adli verileri yalnızca müşterinin verdiği bir destek izniyle görür. Bir izin en fazla 7 gün sürer ve istendiği an iptal edilebilir.

CLI okumaları `forensics:read` kapsamını, bildirme ve kapatma ise `incident:manage` kapsamını gerektirir. Sahipler ve yöneticiler için bir CLI oturumu, tarayıcıda yükseltilmiş onaydan sonra ikisini de taşır. Bir komut yakın zamanlı yükseltilmiş onay gerektiğini söylediğinde hesap portalı onayı ister ve komut yeniden çalıştırılır.

## Zaman çizelgesi

Investigate sayfası tek bir kapsamı (bir depo veya bir makine) beş satır türünden oluşan tek bir zaman çizelgesinde birleştirir: konsol denetim olayları, çalıştırmalar, ağ akışları, dosya açmalar ve anomaliler. Son anlık görüntüden bu yana olan değişiklikler onunla karşılaştırılabilir. Bir zaman penceresi kaydırıcısı pencereyi belirler ve bir pencere en fazla 31 günü kapsar.

Kanıtsız bir dilim, makineyi ve nedeni belirten bir boşluk satırı olarak görünür; asla boş bir aralık olarak değil. Satırların üstünde dakika başına giden bayt grafiği ve en çok kullanılan hedeflerin listesi bulunur.

Aynı okumalar komut satırından da yapılabilir:

```bash
rdc repo flows mail --since 24h
rdc repo flows mail --since 2026-11-20T00:00:00Z --until 2026-11-21T00:00:00Z
rdc repo opens mail --since 7d
```

`--since` ve `--until`, bir ISO 8601 anı veya şimdiden geriye `90m`, `24h` ya da `7d` gibi bir süre alır. Varsayılan pencere son 24 saattir. Akış satırları zaman, süreç, hedef, giden ve gelen bayt ile biliniyorsa ASN ve ülkeyi gösterir. Açma satırları zaman, süreç ve yolu gösterir; hassas yollar işaretlidir.

## Kanıtı doğrulama

Verify evidence, pencere için denetim gün dosyalarının özet zincirini ve adli kayıtların imzalı grup zincirlerini tarayıcıda yeniden hesaplar ve her boşluğu ve değişikliği listeler. Grup imzaları, hesap sunucusunun her makine için sabitlediği spool anahtarlarıyla denetlenir. Kanıtın içinde yazılı bir anahtara asla güvenilmez. Sonuç, dışa aktarılan raporlara damgalanır.

2 GiB üzerindeki kanıt tarayıcı için fazla büyüktür. Aynı modül komut satırından çalışır:

```bash
rdc forensics verify --dir ./incident-evidence
rdc forensics verify --dir ./incident-evidence --since 7d --machine-key web-1=<public-key-hex>
```

Komut herhangi bir boşluk veya değişiklik bulursa 1 koduyla çıkar. `--machine-key <machine>=<public-key-hex>` (anahtar 64 onaltılık karakterdir) dizinin dışından bir anahtar sağlar ve tekrarlanabilir. Dış anahtarı olmayan makine başarısız olur.

## Olay bildirme

Bildirmek kanıtı dondurur. Önce hesap kaydı girilir, ardından depo soruşturmaya hazırlanır:

1. Olay; penceresi, kimin bildirdiği ve organizasyonun ne zaman haberdar olduğu ile kaydedilir.
2. Bir çıkarma tutması pencereyi kapsar ve bucket kilit kuralları onu da içine alır; böylece FIFO bu günleri silemez.
3. Depo, `incident-<id>` etiketiyle adli anlık görüntü olarak fork edilir.
4. Deponun yakalama düzeyi Full'a geçer.

Haberdar olunan andan üç süre başlar; bu an bildirimden önceye ayarlanabilir, sonraya asla: erken uyarı haberdar olunduktan 24 saat sonra, bildirim 72 saat sonra ve nihai rapor bildirimden bir takvim ayı sonra (bildirim kaydedilene kadar bildirim süresinden itibaren sayılır) esedir. Sayfa her süreyi beklemede, 6 saat içinde vadeli, gecikmiş veya tamamlandı olarak gösterir.

```bash
rdc incident declare mail
rdc incident declare mail --since 48h --aware-at 2026-11-20T09:30:00Z
rdc incident status
rdc incident status <id>
```

Başarısız bir makine adımı kaydı ve tutmasını yerinde bırakır, 1 koduyla çıkar ve yalnızca başarısız adımları yeniden çalıştıran komutu belirtir:

```bash
rdc incident declare mail --resume <id>
```

`--resume`, özgün bildirimin penceresini ve haberdar olma anını korur; bu yüzden `--since`, `--until` ve `--aware-at` onunla birlikte kullanılmaz.

## Kanıtı dışa aktarma

`rdc incident export`, olayın penceresini bir dizine yazar: süreleriyle olay kaydı, birleştirilmiş zaman çizelgesi, giden bayt toplamları, ham zincir manifesti ve manifestin listelediği ham dosyalar. Manifest denetim gün dosyalarını veya adli başlık dosyalarını listeliyorsa zincirler yol boyunca doğrulanır ve sonuç `verification.json` dosyasına gider. Kanıt bir boşluk veya değişiklik gösterirse komut 1 koduyla çıkar.

```bash
rdc incident export <id>
rdc incident export <id> --out ./incident-evidence
```

`--stage` ile aynı komut bunun yerine imzalı bir rapor yazar. Bkz. [olay raporları](/tr/docs/incident-reports).

## Olayı kapatma

```bash
rdc incident close <id>
```

Hiçbir şey hemen serbest bırakılmaz. Çıkarma tutması ve bucket kilit kuralları kapatmadan 30 gün sonra sona erer.

## Yapay zekaya sor

Soruşturma sayfasında, açık kapsam ve pencere hakkındaki soruları yanıtlayan bir asistan vardır. Yalnızca o kapsamı ve pencereyi okur; bunun için açık soruşturmadan üretilen, 15 dakika kullanılabilir kalan tek kullanımlık bir bilet kullanır. Soru ve okuduğu satırlar organizasyonun kendi yapay zeka sağlayıcısına gider. Asistan yukarıdaki `rdc` komutlarını, diğer tüm komutlarla aynı izin kuralları altında çalıştırabilir.

## Komutlar

| Komut | Amaç |
|---|---|
| `rdc repo flows <ref>` | Bir deponun bir penceredeki ağ akışları |
| `rdc repo opens <ref>` | Bir deponun bir penceredeki hassas dosya açmaları |
| `rdc forensics level <ref> <level>` | Yakalama düzeyini ayarlar |
| `rdc forensics verify` | Bir kanıt dizinini veya imzalı bir raporu doğrular |
| `rdc incident declare <ref>` | Olayı kaydeder, depoyu fork eder ve Full'a geçer |
| `rdc incident status [id]` | Olayları listeler veya birini süreleriyle gösterir |
| `rdc incident export <id>` | Kanıt penceresini veya `--stage` ile imzalı raporu yazar |
| `rdc incident close <id>` | Bir olayı kapatır |
