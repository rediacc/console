---
title: JSON Çıktı Referansı
description: >-
  rdc CLI JSON çıktı formatı, zarf şeması, hata işleme ve ajan keşif komutları
  için eksiksiz referans.
category: Reference
order: 51
language: tr
sourceHash: "9f8d61df26b59757"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

Tüm `rdc` komutları yapılandırılmış JSON çıktısı üretir. Bir betiğe pipe edin ya da doğrudan bir ajana besleyin.

## JSON Çıktısını Etkinleştirme

### Açık Bayrak

```bash
rdc machine query --name prod-1 --output json
rdc machine query --name prod-1 -o json
```

### Otomatik Algılama

`rdc` TTY olmayan bir ortamda (boru hattı, alt kabuk veya AI ajanı tarafından başlatılmış) çalıştığında, çıktı otomatik olarak JSON'a geçer. Bayrak gerekmez.

```bash
# These all produce JSON automatically
result=$(rdc machine query --name prod-1)
echo '{}' | rdc agent exec "machine query"
```

## JSON Zarfı

Her JSON yanıtı tutarlı bir zarf kullanır:

```json
{
  "success": true,
  "command": "machine query",
  "data": {
    "name": "prod-1",
    "status": "running",
    "repositories": []
  },
  "errors": null,
  "warnings": [],
  "metrics": {
    "duration_ms": 142
  }
}
```

| Alan | Tür | Açıklama |
|-------|------|-------------|
| `success` | `boolean` | Komutun başarıyla tamamlanıp tamamlanmadığı |
| `command` | `string` | Tam komut yolu (ör. `"machine query"`, `"repo up"`) |
| `data` | `object \| array \| null` | Başarıda komuta özel veri, hatada `null` |
| `errors` | `array \| null` | Başarısızlıkta hata nesneleri, başarıda `null` |
| `warnings` | `string[]` | Yürütme sırasında toplanan önemli olmayan uyarılar |
| `metrics` | `object` | Yürütme meta verileri |

## Hata Yanıtları

Başarısız komutlar, kurtarma ipuçlarıyla yapılandırılmış hatalar döndürür:

```json
{
  "success": false,
  "command": "machine query",
  "data": null,
  "errors": [
    {
      "code": "NOT_FOUND",
      "message": "Machine \"prod-2\" not found",
      "retryable": false,
      "guidance": "Verify the resource name with \"rdc machine query\" or \"rdc config repository list\""
    }
  ],
  "warnings": [],
  "metrics": {
    "duration_ms": 12
  }
}
```

### Hata Alanları

| Alan | Tür | Açıklama |
|-------|------|-------------|
| `code` | `string` | Makine tarafından okunabilir hata kodu (kanonik liste için `ERROR_CODES` sabitlerine bakın) |
| `message` | `string` | İnsan tarafından okunabilir açıklama |
| `retryable` | `boolean` | Aynı komutun yeniden denenmesinin başarılı olup olamayacağı |
| `guidance` | `string` | Serbest metin ipucu (eski. Yapılandırılmış eylem verisi için `next` tercih edin) |
| `next` | `object?` | Yapılandırılmış sonraki eylem ipucu (varsa). Aşağıya bakın |

### Yapılandırılmış `next` Eylem İpuçları

`PRECONDITION_MISMATCH` gibi yüksek değerli hata kodlarında, hata kullanıcıya sunulacak tam komutları içeren bir `next` alanı taşır. Her hata kodu bu alanı içermez; yalnızca tanımlı bir kurtarma yolu olanlar içerir. **Ajanlar, `next.options[].run` değerini olduğu gibi kullanıcıya iletmeli, kendi komutlarını türetmemelidir.** Bu, ajanın var olmayan bir komut uydurma hata modunu ortadan kaldırır. Tahmin ettiğinizden daha sık yaşanır.

```json
{
  "errors": [{
    "code": "PRECONDITION_MISMATCH",
    "message": "--current digest mismatch (expected 3264f8ee…, got 611dfd8a…)",
    "next": {
      "summary": "Provide the current value or acknowledge rotation.",
      "options": [
        {
          "description": "Re-read current digest, then retry with --current",
          "run": "rdc repo secret get --name mail --key STRIPE_KEY"
        },
        {
          "description": "Skip the precondition (rotation, audited)",
          "run": "rdc repo secret set --name mail --key STRIPE_KEY --value <new> --mode file --rotate-secret"
        }
      ]
    }
  }]
}
```

Şema:

| Alan | Tür | Açıklama |
|-------|------|-------------|
| `next.summary` | `string` | Kullanıcının karar vermesi gereken şeyin tek satırlık açıklaması |
| `next.options[]` | `array` | Somut eylemler; her biri kullanıcının seçebileceği bir alternatiftir |
| `next.options[].description` | `string` | Bu seçeneğin insan tarafından okunabilir açıklaması |
| `next.options[].run` | `string` | Tam CLI komutu. Kullanıcıya olduğu gibi iletin |

### Yeniden Denenebilir Hatalar

Bu hata türleri `retryable: true` olarak işaretlenir:

- **NETWORK_ERROR**, SSH bağlantısı veya ağ hatası
- **RATE_LIMITED**, Çok fazla istek, bekleyip yeniden deneyin
- **API_ERROR**, Geçici arka uç hatası

Yeniden denenemez hatalar (kimlik doğrulama, bulunamadı, geçersiz argümanlar) yeniden denemeden önce düzeltici eylem gerektirir.

## Çıktı Filtreleme

Çıktıyı belirli anahtarlarla sınırlamak ve token kullanımını azaltmak için `--fields` kullanın:

```bash
rdc machine containers --name prod-1 -o json --fields name,status,repository
```

## Kuru Çalıştırma Çıktısı

Yıkıcı komutlar, ne olacağını önizlemek için `--dry-run` destekler:

```bash
rdc repo delete --name mail -m prod-1 --dry-run -o json
```

```json
{
  "success": true,
  "command": "repo delete",
  "data": {
    "dryRun": true,
    "repository": "mail",
    "machine": "prod-1",
    "guid": "a1b2c3d4-..."
  },
  "errors": null,
  "warnings": [],
  "metrics": {
    "duration_ms": 8
  }
}
```

`--dry-run` desteği olan komutlar: `repo up`, `repo down`, `repo delete`, `snapshot delete`, `sync upload`, `sync download`.

## Ajan Keşif Komutları

`rdc agent` alt komutu, AI ajanlarına çalışma zamanında mevcut işlemleri keşfetmek için yapılandırılmış bir yol sunar.

### Tüm Komutları Listele

```bash
rdc agent capabilities
```

Argümanlar, seçenekler ve açıklamalarla birlikte tam komut ağacını döndürür:

```json
{
  "success": true,
  "command": "agent capabilities",
  "data": {
    "version": "1.0.0",
    "commands": [
      {
        "name": "machine query",
        "description": "Show machine status",
        "arguments": [
          { "name": "machine", "description": "Machine name", "required": true }
        ],
        "options": [
          { "flags": "-o, --output <format>", "description": "Output format" }
        ]
      }
    ]
  }
}
```

### Komut Şemasını Al

```bash
rdc agent schema --command "machine query"
```

Tek bir komut için tüm argümanlar ve seçeneklerin türleri ve varsayılanlarıyla birlikte eksiksiz şemayı döndürür.

### JSON ile Çalıştır

```bash
echo '{"machine": "prod-1"}' | rdc agent exec "machine query"
```

Stdin üzerinden JSON kabul eder, anahtarları komut argümanlarına ve seçeneklerine eşler ve JSON çıktısı zorunlu olarak komutu çalıştırır. Ajan-CLI çağrıları için kabuk komut dizileri oluşturmak istemediğinizde kullanın.

## Ayrıştırma Örnekleri

### Shell (jq)

```bash
status=$(rdc machine query --name prod-1 -o json | jq -r '.data.status')
```

### Python

```python
import subprocess, json

result = subprocess.run(
    ["rdc", "machine", "query", "--name", "prod-1", "-o", "json"],
    capture_output=True, text=True
)
envelope = json.loads(result.stdout)

if envelope["success"]:
    print(envelope["data"]["status"])
else:
    error = envelope["errors"][0]
    if error["retryable"]:
        # retry logic
        pass
    else:
        print(f"Error: {error['message']}")
        print(f"Fix: {error['guidance']}")
```

### Node.js

```javascript
import { execFileSync } from 'child_process';

const raw = execFileSync('rdc', ['machine', 'query', '--name', 'prod-1', '-o', 'json'], { encoding: 'utf-8' });
const { success, data, errors } = JSON.parse(raw);

if (!success) {
  const { message, retryable, guidance } = errors[0];
  throw new Error(`${message} (retryable: ${retryable}, fix: ${guidance})`);
}
```
