---
title: JSON-väljundi viide
description: Täielik viide rdc CLI JSON-väljundi formaadi, ümbriku skeemi, veakäsitluse ja agendi avastamiskäskude jaoks.
category: Reference
tags:
  - ai-agents
  - cli
order: 51
language: et
sourceHash: "36ba86893c3817ac"
sourceCommit: "23543669cd22bce3f14d69a0886bac8a12061412"
---

Kõik `rdc` käsud väljustavad struktureeritud JSON-i. Suunake see skripti või edastage otse agendile.

## JSON-väljundi lubamine

### Sõnaselge lipp

```bash
rdc machine status prod-1 --output json
rdc machine status prod-1 -o json
```

### Automaatne tuvastamine

Kui `rdc` töötab mitte-TTY-keskkonnas (torustatud, alamkest või AI-agendi poolt käivitatud), lülitub väljund automaatselt JSON-ile. Lippu pole vaja.

```bash
# Toodab automaatselt JSON-i
result=$(rdc machine status prod-1)
```

## JSON-ümbrik

Iga JSON-vastus kasutab ühtset ümbrikut:

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

| Väli | Tüüp | Kirjeldus |
|------|------|-----------|
| `success` | `boolean` | Kas käsk lõpetati edukalt |
| `command` | `string` | Täielik käsu tee (nt `"machine query"`, `"repo up"`) |
| `data` | `object \| array \| null` | Käsupõhine kasulik koormus eduka täitmise korral, `null` vea korral |
| `errors` | `array \| null` | Veaobjektid ebaõnnestumise korral, `null` eduka täitmise korral |
| `warnings` | `string[]` | Täitmise ajal kogutud mittekriitilised hoiatused |
| `metrics` | `object` | Täitmise metaandmed |

## Vearesponssid

Ebaõnnestunud käsud tagastavad struktureeritud vead koos taastumisvihjete:

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
      "guidance": "Verify the resource name with \"rdc machine status\" or \"rdc repo list\""
    }
  ],
  "warnings": [],
  "metrics": {
    "duration_ms": 12
  }
}
```

### Veaväljad

| Väli | Tüüp | Kirjeldus |
|------|------|-----------|
| `code` | `string` | Masinloetav veakood (kanonilise loendi jaoks vaadake `ERROR_CODES` konstante) |
| `message` | `string` | Inimloetav kirjeldus |
| `retryable` | `boolean` | Kas sama käsu uuesti proovimine võib õnnestuda |
| `guidance` | `string` | Vabatekstiline vihje (pärand. Struktureeritud toiminguandmete jaoks eelistage `next`) |
| `next` | `object?` | Struktureeritud järgmise toimingu vihje (kui on olemas). Vaadake allpool |

### Struktureeritud `next` toiminguvihjed

Kõrge väärtusega veakoodide jaoks (nt `PRECONDITION_MISMATCH`) sisaldab vea objekt välja `next`, kus on täpselt need käsud, mida kasutajale pakkuda. Mitte iga veakood ei sisalda seda välja. Ainult need, millel on määratletud taastumistee. **Agendid peaksid edastama `next.options[].run` sõna-sõnalt inimesele, mitte sünteesima oma käsku.** See väldib ebaõnnestumise mustrit, kus agent leiutab käsu, mida pole olemas. See juhtub sagedamini, kui arvata võiks.

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
          "run": "rdc repo secret get mail --key STRIPE_KEY"
        },
        {
          "description": "Skip the precondition (rotation, audited)",
          "run": "rdc repo secret set mail --key STRIPE_KEY --value <new> --mode file --rotate-secret"
        }
      ]
    }
  }]
}
```

Skeem:

| Väli | Tüüp | Kirjeldus |
|------|------|-----------|
| `next.summary` | `string` | Üherealine kirjeldus sellest, mida kasutaja otsustama peab |
| `next.options[]` | `array` | Konkreetsed toimingud; iga on alternatiiv, mille kasutaja saab valida |
| `next.options[].description` | `string` | Selle valiku inimloetav selgitus |
| `next.options[].run` | `string` | Täpne CLI-käsk. Edastage sõna-sõnalt kasutajale |

### Korduskatseid väärivad vead

Need veatüübid on märgitud `retryable: true`:

- **NETWORK_ERROR**, SSH-ühenduse või võrgu tõrge
- **RATE_LIMITED**, Liiga palju päringuid, oodake ja proovige uuesti
- **API_ERROR**, Mööduv taustaprogrammi tõrge

Mittekorduskatseid väärivad vead (autentimine, ei leitud, valed argumendid) nõuavad enne korduskatset parandusmeetmeid.

## Väljundi filtreerimine

Kasutage `--fields`, et piirata väljundit konkreetsete võtmetega ja vähendada tokenikasutust:

```bash
rdc machine status prod-1 --containers -o json --fields name,status,repository
```

## Kuivkäituse väljund

Hävitavad käsud toetavad `--dry-run`, et eelvaadata, mis juhtuks:

```bash
rdc repo delete mail@prod-1 --dry-run -o json
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

Käsud koos `--dry-run` toetusega: `repo up`, `repo down`, `repo delete`, `snapshot delete`, `sync upload`, `sync download`.

## Sõelumise näited

### Shell (jq)

```bash
status=$(rdc machine status prod-1 -o json | jq -r '.data.status')
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
        # korduskatsete loogika
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
