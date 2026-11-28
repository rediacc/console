---
title: "SIEM-i integratsioon"
description: "Suuna Rediacc'i auditisündmused Splunki, OpenSearchi, Sentineli või mis tahes OpenTelemetry-ühilduvasse SIEM-i"
category: "Guides"
tags:
  - security
  - operations
subcategory: operations
order: 15
language: et
sourceHash: "69ec0d3d122d13df"
sourceCommit: "f9ac63ac37dff49f6c980f00fdacb7e41099ce81"
---

# SIEM-i integratsioon

Iga Rediacc'i CLI kaudu antud masinatasandi toiming logitakse konto serveri tabelisse `event_log` ja saadetakse samal ajal välja OpenTelemetry logikirjena. Operaatorid suunavad need kirjed SIEM-i (Splunk, OpenSearch, Microsoft Sentinel, AWS CloudWatch jne), suunates konto serveri OpenTelemetry Collectorile, mis ekspordib valitud SIEM-i.

See leht selgitab, kuidas see üles seada. Auditisündmuste skeem ja collectori näidispaigaldus asuvad avalikus monorepos asukohas [`compose/otel-collector/`](https://github.com/rediacc/console/tree/main/compose/otel-collector).

## Mida logitakse

Iga konto serveri tabelisse `event_log` kirjutatud kirje, nii konto tasandi sündmused (autentimine, konfiguratsioonihoidla, litsents) kui ka masinatasandi CLI sündmused (`cli.repo.up`, `cli.repo.fork`, `cli.backup.push`, `cli.sync.upload`, `cli.term.session`, …), peegeldatakse OTLP logitorusse.

Sündmusetüüpide sõnavara on suletud diskrimineeritud ühend, mis on defineeritud failis [`packages/shared/src/audit/event-schema.ts`](https://github.com/rediacc/console/blob/main/packages/shared/src/audit/event-schema.ts). Uue sündmusetüübi lisamine nõuab koodimuudatust ja seda kontrollib CI, nii et SIEM-i reeglite autorid saavad sõnavara stabiilsusele loota.

Iga logikirje kannab OpenTelemetry semantilisi atribuute:

| Atribuut | Tähendus |
|---|---|
| `event.domain` | Fikseeritud `rediacc.audit`: filtreeri selle järgi, et mitteseotud logid kõrvale jätta |
| `event.name` | Kanooniline sündmusetüüp (nt `cli.repo.up`) |
| `event.source` | `cli`, `api`, `system`, … |
| `enduser.id` | Toimingu algataja |
| `organization.id`, `team.id` | Organisatsiooni/meeskonna ulatus |
| `cloud.account.id` | Stripe'i kliendi ID |
| `subscription.id` | Litsentsi tellimus |
| `audit.data.*` | Lamendatud toimingu andmed |

## Seadistamine

### 1. Collectori paigaldamine

```bash
git clone https://github.com/rediacc/console
cd console/compose/otel-collector
docker compose up -d
```

Vaikimisi kuulab collector pordil `:4318` (OTLP/HTTP) ja kirjutab oma stdout'i `debug` eksportija kaudu. See sobib torustiku kontrollimiseks enne kulukamasse sihtkohta suunamist.

### 2. Konto serveri suunamine collectorile

Kontoserveri keskkonnas (Workeri saladused või kohapealse serveri protsessikeskkond):

```bash
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318
```

Taaskäivita konto server. Auditisündmused hakkavad collectorisse voolama kohe.

### 3. SIEM-i eksportija seadistamine

Muuda faili `compose/otel-collector/config.yaml`. Fail sisaldab nelja kommenteeritud eksportija näidet:

- **OpenSearch / Elasticsearch**: `opensearch` eksportija, vajab laiendust `basicauth/opensearch`.
- **Splunk HEC**: `splunk_hec` eksportija, vajab HEC-žetooni ja indeksit.
- **AWS CloudWatch Logs**: `awscloudwatchlogs` eksportija, vajab IAM-i mandaate collectori keskkonnas.
- **Microsoft Sentinel**: `azuremonitor` eksportija kaudu App Insightsi ühendusstringiga.

Eemalda täpselt ühelt kommentaar, vaheta see `logs:` torustiku `exporters:` loendis `debug` vastu ja taaskäivita collector.

Töötab iga [OTel Collector contribi eksportija](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/exporter), mis logisid vastu võtab: auditi torustik toodab standardseid OTLP logikirjeid.

## Tuvastussisu

Auditisündmused on mõeldud [Sigma](https://sigmahq.io) reeglite kirjutamiseks. Sigma reeglid on tarnijaneutraalsed ja teisenduvad `sigma-cli` abil natiivseteks päringuteks OpenSearchi, Splunki, Sentineli ja teiste jaoks.

Näidisreegel (ebaõnnestunud `repo.fork` ootamatult kasutajalt):

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

## Vastavuse seisukoht

Auditi torustik on alus auditilogimise nõuetele, millele Rediacc'i vastavusdokumentatsioon viitab:

- **GDPR Art. 30**: töötlemistoimingute registrid
- **SOC 2 CC6.1 / CC7.2**: juurdepääsu logimine ja seire
- **HIPAA 45 CFR 164.312(b)**: auditikontrollid
- **PCI DSS Req 10**: kogu juurdepääsu jälgimine ja seire
- **NIS2 Art. 21**: auditisündmused on intsidentide käsitlemise sisend; intsidendi ajajoon, kellad ja etapiaruanded on eraldi funktsioonid
- **DORA Art. 10**: auditisündmused on tuvastamise sisend; anomaaliadetektorid töötavad masinas ja serveris forensics'i voo kirjetel, mitte sellel torustikul

## Töökindlus

OTLP väljasaatmine on "saada ja unusta" tüüpi: collectori katkestus ei blokeeri ega ebaõnnestuta kunagi ühtegi Rediacc'i API päringut ning iga sündmus salvestatakse igal juhul konto serveri tabelisse `event_log`. Koos collectori pakettide ja kordusloogikaga muudab see torustiku ohutuks paigaldada mis tahes SIEM-i ette.
