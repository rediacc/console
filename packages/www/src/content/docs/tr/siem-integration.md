---
title: "SIEM Entegrasyonu"
description: "Rediacc denetim olaylarını Splunk, OpenSearch, Sentinel veya OpenTelemetry uyumlu herhangi bir SIEM'e yönlendirme"
category: "Guides"
tags:
  - security
  - operations
subcategory: operations
order: 15
language: tr
sourceHash: "224ef90a952edb1c"
sourceCommit: "5f4fc4c93d74073e5a9b8f8431444495a7f641b6"
---

# SIEM Entegrasyonu

Rediacc CLI üzerinden verilen her makine düzeyi işlem, hesap sunucusunun `event_log` tablosuna kaydedilir ve aynı anda bir OpenTelemetry günlük kaydı olarak yayımlanır. Operatörler, hesap sunucusunu seçtikleri SIEM'e aktaran bir OpenTelemetry Collector'a yönlendirerek bu kayıtları SIEM'e (Splunk, OpenSearch, Microsoft Sentinel, AWS CloudWatch vb.) iletir.

Bu sayfa kurulumun nasıl yapılacağını anlatır. Denetim olayı şeması ve collector referans dağıtımı, herkese açık monorepoda [`compose/otel-collector/`](https://github.com/rediacc/console/tree/main/compose/otel-collector) altındadır.

## Neler kaydedilir

Hesap sunucusunun `event_log` tablosuna yazılan her kayıt -- hem hesap düzeyi olaylar (kimlik doğrulama, yapılandırma deposu, lisans) hem de makine düzeyi CLI olayları (`cli.repo.up`, `cli.repo.fork`, `cli.backup.push`, `cli.sync.upload`, `cli.term.session`, …) -- OTLP günlük hattına yansıtılır.

Olay türü sözlüğü, [`packages/shared/src/audit/event-schema.ts`](https://github.com/rediacc/console/blob/main/packages/shared/src/audit/event-schema.ts) içinde tanımlı, kapalı bir ayrımlı birleşimdir. Yeni bir olay türü eklemek kod değişikliği gerektirir ve CI tarafından denetlenir; böylece SIEM kural yazarları sözlüğün kararlı kalacağına güvenebilir.

Her günlük kaydı OpenTelemetry anlamsal özniteliklerini taşır:

| Öznitelik | Anlamı |
|---|---|
| `event.domain` | Sabit `rediacc.audit` -- ilgisiz günlükleri yok saymak için buna göre filtrelenir |
| `event.name` | Kanonik olay türü (ör. `cli.repo.up`) |
| `event.source` | `cli`, `api`, `system`, … |
| `enduser.id` | İşlemi başlatan kullanıcı |
| `organization.id`, `team.id` | Kuruluş/ekip kapsamı |
| `cloud.account.id` | Stripe müşteri kimliği |
| `subscription.id` | Lisans aboneliği |
| `audit.data.*` | Düzleştirilmiş işlem verisi |

## Kurulum

### 1. Collector'ı dağıtma

```bash
git clone https://github.com/rediacc/console
cd console/compose/otel-collector
docker compose up -d
```

Collector varsayılan olarak `:4318` (OTLP/HTTP) üzerinde dinler ve `debug` exporter'ı aracılığıyla kendi stdout'una yazar -- pahalı bir yere yönlendirmeden önce hattı doğrulamak için kullanışlıdır.

### 2. Hesap sunucusunu collector'a yönlendirme

Hesap sunucusunun ortamında (Worker gizli anahtarları veya şirket içi sunucunun süreç ortamı):

```bash
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318
```

Hesap sunucusu yeniden başlatıldığında denetim olayları hemen collector'a akmaya başlar.

### 3. SIEM exporter'ını yapılandırma

`compose/otel-collector/config.yaml` dosyası düzenlenir. Dosya, yorum satırı halinde dört exporter örneğiyle gelir:

- **OpenSearch / Elasticsearch** -- `opensearch` exporter'ı, `basicauth/opensearch` uzantısını gerektirir.
- **Splunk HEC** -- `splunk_hec` exporter'ı, bir HEC token'ı ve dizin gerektirir.
- **AWS CloudWatch Logs** -- `awscloudwatchlogs` exporter'ı, collector'ın ortamında IAM kimlik bilgileri gerektirir.
- **Microsoft Sentinel** -- `azuremonitor` exporter'ı üzerinden, bir App Insights bağlantı dizesiyle.

Yalnızca birinin yorumu kaldırılır, `logs:` hattının `exporters:` listesinde `debug` yerine konur ve collector yeniden başlatılır.

Günlük kabul eden herhangi bir [OTel Collector contrib exporter'ı](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/exporter) çalışır -- denetim hattı standart OTLP günlük kayıtları üretir.

## Tespit içeriği

Denetim olayları [Sigma](https://sigmahq.io) kuralı yazımı için tasarlanmıştır. Sigma kuralları satıcıdan bağımsızdır ve `sigma-cli` ile OpenSearch, Splunk, Sentinel ve diğerleri için yerel sorgulara dönüştürülür.

Örnek kural (beklenmeyen bir kullanıcıdan başarısız `repo.fork`):

```yaml
title: Unexpected Rediacc repo fork
detection:
  selection:
    event.domain: rediacc.audit
    event.name: cli.repo.fork
    audit.data.success: false
  condition: selection
level: medium
```

## Uyumluluk duruşu

Denetim hattı, Rediacc'ın uyumluluk belgelerinde anılan denetim günlüğü gereksinimlerinin temelidir:

- **GDPR Art. 30** -- işleme faaliyeti kayıtları
- **SOC 2 CC6.1 / CC7.2** -- erişim günlüğü ve izleme
- **HIPAA 45 CFR 164.312(b)** -- denetim kontrolleri
- **PCI DSS Req 10** -- tüm erişimi izleme ve takip etme
- **NIS2 Art. 21** -- denetim olayları olay işlemeye girdi sağlar; olay zaman çizelgesi, sayaçlar ve aşamalı raporlar ayrı özelliklerdir
- **DORA Art. 10** -- denetim olayları tespite girdi sağlar; anomali dedektörleri bu hat üzerinde değil, forensics akış kayıtları üzerinde çalışır

## Güvenilirlik

OTLP yayımı ateşle-ve-unut şeklindedir -- bir collector kesintisi Rediacc API isteğini hiçbir zaman engellemez veya başarısız kılmaz ve her olay yine de hesap sunucusunun `event_log` tablosunda saklanır. Collector'ın toplu işleme ve yeniden deneme davranışıyla birleştiğinde bu, hattı herhangi bir SIEM'in önünde dağıtmak için güvenli kılar.
