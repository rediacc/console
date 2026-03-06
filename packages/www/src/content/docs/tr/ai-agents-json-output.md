---
title: JSON Çıktı Referansı
description: rdc CLI JSON çıktı formatı, zarf şeması, hata işleme ve ajan keşif komutları için eksiksiz referans.
category: Reference
order: 51
language: tr
---

Tüm `rdc` komutları, AI ajanları ve betikler tarafından programatik tüketim için yapılandırılmış JSON çıktısını destekler.

## JSON Çıktısını Etkinleştirme

### Açık Bayrak

```bash
rdc machine info prod-1 --output json
rdc machine info prod-1 -o json
```

### Otomatik Algılama

`rdc` TTY olmayan bir ortamda (boru hattı, alt kabuk veya AI ajanı tarafından başlatılmış) çalıştığında, çıktı otomatik olarak JSON'a geçer. Bayrak gerekmez.

```bash
# These all produce JSON automatically
result=$(rdc machine info prod-1)
echo '{}' | rdc agent exec "machine info"
```

## JSON Zarfı

Her JSON yanıtı tutarlı bir zarf kullanır:

```json
{
  "success": true,
  "command": "machine info",
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
| `command` | `string` | Tam komut yolu (ör. `"machine info"`, `"repo up"`) |
| `data` | `object \| array \| null` | Başarıda komuta özel veri, hatada `null` |
| `errors` | `array \| null` | Başarısızlıkta hata nesneleri, başarıda `null` |
| `warnings` | `string[]` | Yürütme sırasında toplanan önemli olmayan uyarılar |
| `metrics` | `object` | Yürütme meta verileri |

## Hata Yanıtları

Başarısız komutlar, kurtarma ipuçlarıyla yapılandırılmış hatalar döndürür:

```json
{
  "success": false,
  "command": "machine info",
  "data": null,
  "errors": [
    {
      "code": "NOT_FOUND",
      "message": "Machine \"prod-2\" not found",
      "retryable": false,
      "guidance": "Verify the resource name with \"rdc machine info\" or \"rdc config repositories\""
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
| `code` | `string` | Makine tarafından okunabilir hata kodu |
| `message` | `string` | İnsan tarafından okunabilir açıklama |
| `retryable` | `boolean` | Aynı komutun yeniden denenmesinin başarılı olup olamayacağı |
| `guidance` | `string` | Hatayı çözmek için önerilen sonraki eylem |

### Yeniden Denenebilir Hatalar

Bu hata türleri `retryable: true` olarak işaretlenir:

- **NETWORK_ERROR** — SSH bağlantısı veya ağ hatası
- **RATE_LIMITED** — Çok fazla istek, bekleyip yeniden deneyin
- **API_ERROR** — Geçici arka uç hatası

Yeniden denenemez hatalar (kimlik doğrulama, bulunamadı, geçersiz argümanlar) yeniden denemeden önce düzeltici eylem gerektirir.

## Çıktı Filtreleme

Çıktıyı belirli anahtarlarla sınırlamak için `--fields` kullanın. Bu, yalnızca belirli verilere ihtiyaç duyulduğunda token kullanımını azaltır:

```bash
rdc machine containers prod-1 -o json --fields name,status,repository
```

## Kuru Çalıştırma Çıktısı

Yıkıcı komutlar, ne olacağını önizlemek için `--dry-run` destekler:

```bash
rdc repo delete mail -m prod-1 --dry-run -o json
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

`rdc agent` alt komutu, AI ajanlarının çalışma zamanında mevcut işlemleri keşfetmesi için yapılandırılmış iç gözlem sağlar.

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
        "name": "machine info",
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
rdc agent schema "machine info"
```

Tüm argümanlar ve seçeneklerin türleri ve varsayılanlarıyla birlikte tek bir komut için ayrıntılı şema döndürür.

### JSON ile Çalıştır

```bash
echo '{"machine": "prod-1"}' | rdc agent exec "machine info"
```

Stdin üzerinden JSON kabul eder, anahtarları komut argümanlarına ve seçeneklerine eşler ve JSON çıktısı zorunlu olarak çalıştırır. Kabuk komut dizileri oluşturmadan yapılandırılmış ajan-CLI iletişimi için kullanışlıdır.

## Ayrıştırma Örnekleri

### Shell (jq)

```bash
status=$(rdc machine info prod-1 -o json | jq -r '.data.status')
```

### Python

```python
import subprocess, json

result = subprocess.run(
    ["rdc", "machine", "info", "prod-1", "-o", "json"],
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

const raw = execFileSync('rdc', ['machine', 'info', 'prod-1', '-o', 'json'], { encoding: 'utf-8' });
const { success, data, errors } = JSON.parse(raw);

if (!success) {
  const { message, retryable, guidance } = errors[0];
  throw new Error(`${message} (retryable: ${retryable}, fix: ${guidance})`);
}
```
