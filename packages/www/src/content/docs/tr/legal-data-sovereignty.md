---
title: "Veri Egemenliği"
description: "Rediacc'ın kendi sunucunuzda barındırma mimarisi küresel yetki alanlarındaki veri yerleşimi ve egemenlik gereksinimlerini nasıl karşılar."
category: "Legal"
order: 7
language: tr
sourceHash: "dba51d5d6dcf8197"
---

Birçok ülke, vatandaşlarının kişisel verilerinin ulusal sınırlar içinde depolanmasını ve işlenmesini gerektirir. Rediacc'ın kendi sunucunuzda barındırma mimarisi bu gereksinimleri tasarım gereği karşılar: veriler makinenizde, veri merkezinizde, yetki alanınızda kalır. Klonlama sırasında hiçbir veri makineyi terk etmez ve hiçbir üçüncü taraf SaaS verilerinizi işlemez.

## Kendi Sunucunuzda Barındırma Neden Veri Egemenliğini Çözer

Sınır ötesi veri aktarımı, bulut bilişimdeki en zor uyumluluk sorunudur. Her yetki alanının farklı kuralları, yeterlilik kararları ve aktarım mekanizmaları vardır. Kendi sunucunuzda barındırma tüm kategoriyi ortadan kaldırır:

- **Sınır ötesi aktarım yok**: CoW klonlama (`cp --reflink=always`) verileri aynı makinede çoğaltır
- **Üçüncü taraf işleyici yok**: Rediacc sizin altyapınızda çalışır, Rediacc'ın sunucularında değil
- **Yeterlilik değerlendirmesi gerekmez**: veriler yetki alanını asla terk etmez, aktarım kuralları uygulanmaz
- **Standart sözleşme maddeleri yok**: düzenlenecek uluslararası veri akışı yoktur

## Yetki Alanı Kapsamı

### Avrupa Birliği

[GDPR](https://gdpr-info.eu/) hedef ülke yeterli koruma sağlamadıkça AB/AEA dışına kişisel veri aktarımını kısıtlar. Schrems II kararı AB-ABD Gizlilik Kalkanını geçersiz kıldı ve [Meta'ya 1,2 milyar EUR ceza](https://www.dataprotection.ie/en/news-media/press-releases/Data-Protection-Commission-announces-conclusion-of-inquiry-into-Meta-Ireland) sınır ötesi aktarım hatalarının maliyetini gösterdi.

AB'de kendi sunucunuzda barındırılan Rediacc tüm verileri AB içinde tutar. Aktarım mekanizması gerekmez. Madde düzeyinde eşleme için [GDPR Uyumluluğu](/tr/docs/legal-gdpr) sayfasına bakın.

### Çin

[PIPL](http://www.npc.gov.cn/npc/c30834/202108/a8c4e3672c74491a80b53a172bb753fe.shtml) Çin vatandaşlarının kişisel verilerinin Çin'de saklanmasını gerektirir. Sınır ötesi aktarımlar CAC güvenlik değerlendirmeleri gerektirir. Çin altyapısında kendi sunucunuzda barındırılan Rediacc CAC güvenlik değerlendirmelerini tamamen önler.

### Brezilya

[LGPD](https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm) yeterli güvenlik önlemleri gerektirir ve uluslararası aktarımları kısıtlar. Brezilya'da kendi sunucunuzda barındırma aktarım endişelerini ortadan kaldırır ve LUKS2 şifreleme ile ağ izolasyonu aracılığıyla Md. 46'nın teknik önlem gereksinimini karşılar.

### Hindistan

[DPDP Yasası (2023)](https://www.meity.gov.in/content/digital-personal-data-protection-act-2023) hükümet onaylı listede olmayan ülkelere aktarımı kısıtlar. Hindistan altyapısında kendi sunucunuzda barındırma, hangi ülkelerin kara listeye alındığından bağımsız olarak aktarım olmayacağı anlamına gelir. Hindistan'ın hükümet ve savunma sektörleri yerinde çözümleri güçlü şekilde tercih eder.

### Turkiye

[KVKK (Kanun No. 6698)](https://kvkk.gov.tr/en/) karmaşık yeterlilik gereksinimleri ile uluslararası aktarımları kısıtlar. Turkiye AB yeterlilik listesinde değildir, bu nedenle sınır ötesi aktarımlar açık onay gerektirir. Turkiye'de kendi sunucunuzda barındırma bunu tamamen ortadan kaldırır.

### Güney Kore

[PIPA](https://www.pipc.go.kr/eng/index.do) dünya çapında en katılardan biridir ve depolama ile iletim sırasında kişisel verilerin şifrelenmesini açıkça zorunlu kılar. LUKS2 AES-256 bu gereksinimi doğrudan karşılar. Gelirin %3'üne kadar cezalar.

### Japonya

[APPI](https://www.ppc.go.jp/en/legal/) alıcı ülke yeterli koruma sağlamadıkça sınır ötesi aktarımları kısıtlar. Japonya'da kendi sunucunuzda barındırma aktarım kısıtlamalarını önler ve pazarın yerinde çözüm tercihi ile uyumludur.

### Avustralya

[Privacy Act 1988](https://www.legislation.gov.au/C2004A03712/latest/text) ifşa eden kuruluşu yabancı alıcının veri işlemesinden sorumlu tutar (APP 8). Kendi sunucunuzda barındırma bu sorumluluğu tamamen ortadan kaldırır. LUKS2 şifreleme ve ağ izolasyonu APP 11 kapsamında somut "makul adımlar" sağlar.

### Birleşik Arap Emirlikleri

[Federal Kararname-Kanun No. 45/2021](https://u.ae/en/about-the-uae/digital-uae/data/data-protection-laws) yeterli güvenlik önlemleri gerektirir ve sınır ötesi aktarımları kısıtlar. BAE'nin hükümet ve finans sektörleri yerinde dağıtımları güçlü şekilde tercih eder.

### Suudi Arabistan

[PDPL](https://sdaia.gov.sa/en/SDAIA/about/Documents/Personal%20Data%20English%20V2.pdf) Suudi Arabistan'da yaşayanların kişisel verilerinin ülke içinde saklanmasını ve işlenmesini gerektirir. Kendi sunucunuzda barındırma bu katı yerelleştirme gereksinimini doğrudan karşılar.

### Singapur

[PDPA](https://sso.agc.gov.sg/Act/PDPA2012) makul güvenlik gerektirir ve sınır ötesi aktarımları kısıtlar. Önemli bir APAC veri merkezi olan Singapur'da kendi sunucunuzda barındırma ASEAN operasyonları için bölgesel uyumluluğu sağlar.

### Rusya

[Federal Kanun 242-FZ](https://pd.rkn.gov.ru/) Rus vatandaşlarının kişisel verilerinin Rusya'daki sunucularda saklanmasını gerektirir. İhlaller web sitesi engellenmesine yol açabilir. Rus topraklarında kendi sunucunuzda barındırma mimari yoluyla uyumluluk sağlar.

## Kalıp

Tüm yetki alanlarında uyumluluk denklemi aynıdır:

| Özellik | Bulut/SaaS | Kendi Sunucunuzda Barındırılan Rediacc |
|---------|-----------|---------------------------------------|
| Veri konumu | Sağlayıcının veri merkezleri (sınırları geçebilir) | Sizin makineniz, sizin yetki alanınız |
| Aktarım mekanizması gerekli | Evet (SCC, yeterlilik, onay) | Hayır (aktarım gerçekleşmez) |
| Üçüncü taraf işleyici sorumluluğu | Evet | Hayır |
| Şifreleme kontrolü | Sağlayıcı tarafından yönetilen anahtarlar | Sizin LUKS kimlik bilgileriniz, yerel olarak saklanır |
| Klonlama/hazırlık verileri | Sınırları geçebilir veya kontrolünüzden çıkabilir | Aynı makinede CoW, aynı yetki alanı |
