---
title: "Kohapealne paigaldus"
description: "Konto-serveri ja CLI jaotuse käitamine oma infrastruktuuris."
category: "Guides"
order: 5
language: et
sourceHash: "eea76db2d612133f"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

Rediacc saab töötada täielikult sinu enda infrastruktuuris. Eraldiseisev Dockeri pilt sisaldab konto-serverit, veebiportaali, turunduslehte ja CLI jaotuse lõpp-punkti. Rediacc hostitud teenustele pole väliseid sõltuvusi.

## Dockeri pilt

Tõmba eraldiseisev pilt:

```bash
docker pull ghcr.io/rediacc/server:stable
```

Käivita vaikimisi seadistustega:

```bash
docker run -p 80:80 -p 443:443 ghcr.io/rediacc/server:stable
```

Pilt pakub:
- Konto API aadressil `/account/api/v1/`
- Veebiportaali aadressil `/account/`
- Turunduslehte aadressil `/`
- CLI artefakte aadressil `/releases/`
- Renet binaare aadressil `/bin/`

## CLI paigaldamine oma serverist

Paigalda CLI otse oma kohapealsest serverist. Paigaldusskript tuvastab automaatselt uuenduskanali ja seadistab CLI, et see kontrolliks uuendusi oma serverist.

```bash
curl -fsSL https://account.example.com/install.sh | \
  REDIACC_SERVER_URL=https://account.example.com bash
```

See üks käsk:
1. Laadib alla CLI binaari sinu serveri `/releases/` lõpp-punktist
2. Pärib `/account/api/v1/.well-known/server-info`, et tuvastada uuenduskanal
3. Kirjutab `server.json` sinu serveri URL-i, uuenduskanali ja krüptovõtmetega
4. Seadistab `rdc update` kontrollima sinu serverist tulevasi uuendusi

`REDIACC_CHANNEL` muutujat pole vaja. Paigaldusskript loeb kanali automaatselt sinu serveri konfiguratsioonist.

## CLI seadistamine nimega konfiguratsioonidega

Mitme serveriga (kohapealne, tootmine, edge) ühendamisel hoiavad nimega konfiguratsioonid iga keskkonna eraldatuna:

```bash
# Loo konfiguratsioon sinu kohapealsele serverile
rdc config init --name myserver --server https://account.example.com

# Logi sisse seda konfiguratsiooni kasutades
rdc --config myserver subscription login

# Kõik käsud --config-iga kasutavad kohapealset serverit
rdc --config myserver machine query --name prod-1
```

Iga nimega konfiguratsioon salvestab oma konto-serveri URL-i ja tellimustoekeni. Konfiguratsiooni vahetamine vahetab kogu serveri konteksti.

## Õhulõhega keskkonnad

Internetiühenduseta keskkondade jaoks sea nii serveri URL kui ka kohandatud väljalasete URL:

```bash
curl -fsSL https://account.example.com/install.sh | \
  REDIACC_SERVER_URL=https://account.example.com \
  REDIACC_RELEASES_URL=https://account.example.com/releases \
  bash
```

CLI kontrollib uuendusi aadressilt `account.example.com/releases/cli/stable/manifest.json` avaliku väljalasete CDN asemel.

Kui server on täielikult võrguühenduseta, paigalda CLI npm-i kaudu pakitud tõrvikfailist:

```bash
npm install -g https://account.example.com/npm/rediacc-cli-latest.tgz
```

## Keskkonna muutujate viide

| Muutuja | Kasutatakse | Eesmärk |
|---|---|---|
| `REDIACC_SERVER_URL` | Paigaldusskript | Konto-serveri URL. Tuvastab automaatselt kanali ja krüptovõtmed. |
| `REDIACC_RELEASES_URL` | Paigaldusskript, CLI uuendaja | Kohandatud väljalasete lõpp-punkt CLI binaride jaoks. Vaikimisi: `https://releases.rediacc.com` |
| `REDIACC_CHANNEL` | Paigaldusskript | Uuenduskanali alistamine. Tuvastab serverist automaatselt, kui pole seatud. |
| `REDIACC_ACCOUNT_SERVER` | CLI käitusaeg | Konto-serveri URL-i alistamine kõigi CLI käskude jaoks. |
| `RDC_UPDATE_CHANNEL` | CLI käitusaeg | Uuenduskanali alistamine `rdc update` jaoks. |

## Serveri seadistamine

Kohapealne Dockeri pilt kasutab sama `ENVIRONMENT` muutujat kui hostitud teenus. Sea see oma Dockeri keskkonnas või orkestreerimiskonfiguratsioonis:

- `ENVIRONMENT=production` (vaikimisi): standardsed ressursipiirangud; selle serveriga ühenduvad CLI-d kasutavad vaikimisi **stable** uuenduskanalit. Väärtuse nimi `production` on pärand juurutusidentifikaator. Mõlemad `production` ja `edge` režiimid on tootmiskvaliteediga.
- `ENVIRONMENT=edge`: 2X Community piirangud; CLI-d kasutavad vaikimisi **edge** uuenduskanalit

Iga keskkonna pakutavate üksikasjade kohta vt [Väljalaskekanalid](/et/docs/release-channels).

## Mida server CLI-le ütleb

Kui CLI ühendub sinu serveriga, pärib see `/.well-known/server-info`, et tuvastada:

- **E2E krüpteerimise avalik võti**: nullteadmiste konfiguratsiooni salvestamiseks
- **Minimaalne CLI versioon**: blokeerib aegunud CLI-d ühendumast
- **Uuenduskanal**: ütleb CLI-le, millist väljalaskekanalit uuenduste jaoks kasutada
- **Keskkond**: millist juurutusprofiili server kasutab (standardpiirangud vs. edge-2X-piirangutega)

See automaatseadistus tähendab, et kasutajad vajavad ainult serveri URL-i. Kõik muu tuvastatakse automaatselt.

## Litsentsimislahendus õhulõhega juurutustele

Õhulõhega ja isehostitavad kohapealsed serverid väljastavad litsentse lokaalselt, kasutades ülesvoolu peaserveri allkirjastatud **delegeerimissertifikaati**. Sertifikaat piirab kohapealset serverit tema plaanipiirangutega ja loob rikkumiskindla ahela. Krüptograafilise kujunduse (ahela terviklus, forki tuvastamine, auditijäljed) kohta vt [Litsentsiahelad ja delegeerimine](/et/docs/license-chain).

See jaotis käsitleb operatiivset seadistust: võtmete genereerimine, sertifikaadi taotlemine, automaatse uuendamise seadistamine ja offline (õhulõhega) uuendamisvoog.

### Üks tellimus, üks kohapealne paigaldus

Tellimusel võib olla **korraga kõige rohkem üks aktiivne delegeerimissertifikaat**. Iga kohapealne paigaldus jõustab kuu- ja masinapiiranguid oma kohaliku väljastamise raamatu alusel, seega mitme aktiivse serdi korral korrutuvad kehtivad kvoodid ilma võimaliku ühitamiseta.

Kui vajad eraldi keskkondi (tootmine, lavastamine, DR, mitme piirkond), osta üks tellimus paigalduse kohta. Ühe-aktiivse jõustamine kodifitseerib selle lepingu: katse luua teine aktiivne sert tagastab `409 DELEGATION_CERT_ALREADY_ACTIVE` olemasoleva serdi id-ga ja juhistega uuendamiseks (eelistatav, säilitab ahela) või tühistamiseks-ja-loomiseks (lähtestab ahela).

### 1. Genereeri kohapealne Ed25519 võtmepaar

Kohapealne server kasutab litsentside allkirjastamiseks eraldi Ed25519 võtmepaari. Ülesvoolu delegeerimissert autoriseerib selle konkreetse avaliku võtme.

```bash
# Genereeri uus võtmepaar
openssl genpkey -algorithm Ed25519 -out onprem-private.pem
openssl pkey -in onprem-private.pem -pubout -out onprem-public.pem

# Teisenda base64-ks (formaat, mida kohapealne eeldab env-muutujates)
ON_PREMISE_PRIVATE_KEY=$(openssl pkey -in onprem-private.pem -outform DER | base64 -w 0)
ON_PREMISE_PUBLIC_KEY=$(openssl pkey -in onprem-private.pem -pubout -outform DER | base64 -w 0)
```

Salvesta privaatvõti koos teiste saladustega (näiteks Dockeri saladus või Kubernetes Secret). See ei lahku kunagi kohapealsest masinast.

### 2. Taotle delegeerimissert ülesvoolu käest

Saad sertifikaati ülesvoolu konto portaalist taotleda kolmel viisil:

**Variant A: Kliendi iseteenindus (soovitatav).** Logi ülesvoolu portaali org-omaniku või administraatorina sisse ja mine aadressile **/account/delegation-certs**. Klõpsa **Create New**, kleebi kohapealne avalik võti (base64 SPKI), vali kehtivus (või aktsepteeri plaanipõhine vaikeväärtus) ja laadi alla saadud `.json` fail.

**Variant B: Administraator (ristklient).** Rediacc'i tugi või ülesvoolu süsteemiadministraator saab kutsuda `POST /admin/delegation-certs` samade parameetritega.

**Variant C: `rdc` CLI (kavandatud).** Tulevane CLI käsk mähib portaali voo sisse.

Tagastatud `.json` näeb välja nii:

```json
{
  "payload": "eyJ2ZXJzaW9uIjoxLCJzdWJzY3JpcHRpb25JZCI6...",
  "signature": "...",
  "publicKeyId": "..."
}
```

Serdi kehtivust juhib kehtivuspoliitika (plaanipõhised vaikeväärtused ja laed, tellimusepõhine alistamine, piiratud tellimuse lõpuni + 3-päevane armuaeg). Vastus sisaldab ka `effectiveDays` ja `reason` välja, et näeksid, miks see väärtus valiti. Täielike reeglite jaoks vt [Litsentsiahelad - Kehtivuspoliitika](/et/docs/license-chain).

### 3. Paigalda sert kohapealsele serverile

Salvesta allalaaditud `.json` teadaolevale teele ja osuta kohapealne sellele:

```bash
DELEGATION_CERT_PATH=/etc/rediacc/delegation-cert.json
```

Või lühiajaliste / Dockeri saladuste töövoogude jaoks manusta sert base64-na env-muutujasse:

```bash
DELEGATION_CERT_BASE64=$(base64 -w 0 < delegation-cert.json)
```

### 4. Seadista ülesvoolu kontroll + automaatne uuendamine (valikuline, kuid soovitatav)

Kui sinu kohapealne server omab ülesvoolu suunatud väljaminevat HTTPS-juurdepääsu, sea automaatne uuendamine, et sert uueneks enne aegumist ilma käsitsi sekkumiseta:

```bash
# Nõutav /onprem/cert-upload jaoks, et kontrollida üleslaaditud serdi ülesvoolu peaserveri vastu.
# Kiire ebaõnnestumine käivitamisel, kui UPSTREAM_API_KEY on seatud ilma selleta.
UPSTREAM_PUBLIC_KEY="<upstream master Ed25519 SPKI public key, base64>"

# Nõutav automaatse uuendamise silmuse jaoks. Mindi portaali kaudu:
#   Org omanik/admin → /account/delegation-certs → "Get auto-renew token"
# See on AINUS viis delegation:renew-ulatusega API tokeni saamiseks.
UPSTREAM_URL="https://www.rediacc.com"
UPSTREAM_API_KEY="rdt_..."

# Valikuline häälestus (vaikeväärtused näidatud).
AUTO_RENEW_INTERVAL_HOURS=24
RENEW_THRESHOLD_DAYS=14
```

Kohapealne automaatse uuendamise silmus käivitub üks kord käivitamisel ja seejärel seadistatud intervalliga. See kasutab **adaptiivset läve** (`min(env.RENEW_THRESHOLD_DAYS, ceil(certValidityDays / 3))`), nii et 15-päevane COMMUNITY sert uueneb 5 päeva järel, mitte päeval 1. 90-päevane BUSINESS sert uueneb 14 päeva järel (env-seadistatud lagi).

Kui uuendamine ebaõnnestub, jääb sert kasutusse kuni loomulik aegumine. Ebaõnnestumine lükkub 1 tunni võrra edasi ja salvestatakse faili `${DELEGATION_CERT_PATH}.status.json` ning avatakse `GET /onprem/cert-status` kaudu.

### 5. Õhulõhega uuendamine (ilma väljamineva HTTPS-ita)

Kui sinu kohapealne server ei suuda ülesvoolu jõuda, kasuta käsitsi ülekande voogu:

1. **Laadi alla uuendustaotlus kohapealsest administraatoriportaalist.** Kohapealne süsteemi root pärib `GET /onprem/renewal-request`. See tagastab JSON-manifesti, mis sisaldab kohaliku ahela otsa, delegeeritud avalikku võtit ja rikkumiskindlat Ed25519 allkirja sinu kohapealsest privaatvõtmest.
2. **Kanna manifest ülesvoolu** USB-ketta, krüpteeritud meili või mis tahes riba-välise kanali kaudu. Manifest on väike (mõni KB) ja ei sisalda saladusi.
3. **Töötle manifest ülesvoolu.** Org omanik/admin avab **/account/delegation-certs** > **Upload renewal request** > valib manifesti faili. Ülesvool kontrollib manifesti allkirja aktiivse serdi `delegatedPublicKey` vastu (tõestab, et see pärineb kohapeelse privaatvõtme hoidjalt), kontrollib anti-korduse (üle 7 päeva vanad manifestid lükatakse tagasi), seejärel väljastab uue serdi.
4. **Laadi alla uus sert** ülesvoolu portaalist `.json` failina.
5. **Kanna sert tagasi** kohapealsele.
6. **Laadi üles kohapealsele** kohaliku administraatoriportaali kaudu (`POST /onprem/cert-upload`). Kohapealne kontrollib uut serti `UPSTREAM_PUBLIC_KEY` vastu ja kinnitab, et serdi `genesisSequence` seob endiselt kohaliku väljastamise raamatu ahela kirjega (järjestuse edasiliikumine transiidi ajal on toetatud -- ahel laieneb loomulikult).

See kogu silmus ei nõua kohapealselt kunagi võrguegress-ühendust.

#### Manifesti ebaõnnestumisrežiimid

| Kood | Põhjus | Lahendus |
|---|---|---|
| `NO_ACTIVE_CERT` | Ülesvoolu pole sellel tellimusel aktiivset serti | Väljasta uus sert loomise voo kaudu uuendamise asemel |
| `DELEGATED_KEY_MISMATCH` | Manifesti `delegatedPublicKey` erineb aktiivsest serdist | Manifest võib olla kordus teisest kohapealsest paigaldusest |
| `MANIFEST_SIGNATURE_INVALID` | Allkiri ei kinnita delegeeritud avaliku võtme vastu | Manifest muudeti transiidi käigus, või genereerisid seda teises kohapealses |
| `MANIFEST_EXPIRED` | Manifest on vanem kui 7 päeva | Genereeri kohapealsest uus uuendustaotlus |

#### Serdi üleslaadimise ebaõnnestumisrežiimid

| Kood | Põhjus | Lahendus |
|---|---|---|
| `CHAIN_HEAD_BEHIND` | Uue serdi `genesisSequence` on kohaliku ahela otsa ees | Ülesvool on hargnenud ahelal -- uuri |
| `CHAIN_FORK_ON_UPLOAD` | Ahela räsi serdi `genesisSequence`'il ei vasta kohalikule raamatule | Kohalik ahel on ülesvoolust hargnenud -- uuri |
| `Signature verification failed` | Sert pole seadistatud `UPSTREAM_PUBLIC_KEY` allkirjastatud | Kontrolli, et `UPSTREAM_PUBLIC_KEY` vastab ülesvoolu peaserveri avalikule võtmele |

### 6. Olek ja seire

Päri kohapealse kohalik serdi olek igal ajal:

```bash
curl https://onprem.example.com/account/api/v1/onprem/cert-status \
  -H "Cookie: <admin session>"
```

Tagastab laaditud serdi `subscriptionId`, `planCode`, `validUntil`, `daysUntilExpiry`, pluss `autoRenew` bloki (`enabled`, `lastSuccessAt`, `lastErrorAt`, `lastError`). Haak see sinu seiregruppesse, et teavitada vananenud `lastSuccessAt` või mitte-null `lastError` puhul.

Varunduse ja auditi jaoks saab kohapealne administraator alla laadida ka hetkel laaditud allkirjastatud serdi `GET /onprem/cert-current` kaudu (nõuab kõrgendatud seanssi).

### Delegeerimissert env-muutujate viide

| Muutuja | Nõutav? | Eesmärk |
|---|---|---|
| `ON_PREMISE_MODE` | Jah | Seada `true`-ks, et lubada kohapealsete marsruutide alamhulk |
| `ON_PREMISE_PRIVATE_KEY` | Jah | Base64 PKCS8 Ed25519 privaatvõti delegeeritud allkirjastamise jaoks |
| `ON_PREMISE_PUBLIC_KEY` | Jah | Base64 SPKI Ed25519 avalik võti (peab vastama serdi `delegatedPublicKey`-le) |
| `DELEGATION_CERT_PATH` | Üks neist | Failisüsteemi tee allkirjastatud serdi JSON-i |
| `DELEGATION_CERT_BASE64` | Üks neist | Base64-kodeeritud serdi JSON (alternatiiv failiteele) |
| `UPSTREAM_PUBLIC_KEY` | Nõutav kui `UPSTREAM_API_KEY` on seatud, või `/onprem/cert-upload` tööks | Ülesvoolu peaserveri avaliku võtme base64 SPKI. Kiire ebaõnnestumine käivitamisel kui puudub. |
| `UPSTREAM_URL` | Automaatseks uuendamiseks | Ülesvoolu konto-serveri baas-URL, nt `https://www.rediacc.com` |
| `UPSTREAM_API_KEY` | Automaatseks uuendamiseks | `delegation:renew`-ulatusega API token. Loe portaali kaudu -- vt 4. samm. |
| `AUTO_RENEW_INTERVAL_HOURS` | Valikuline | Vaikimisi 24. Kui sageli kontrollida, kas sert vajab uuendamist. |
| `RENEW_THRESHOLD_DAYS` | Valikuline | Vaikimisi 14. Toimib adapteeritud 1/3-kehtivuse lae ülempiirana. |

### Ohumudeli kokkuvõte

Delegeerimissertide mudel kaitseb järgmise vastu:

- **Võltsitud litsentsid**: kohapealne saab allkirjastada ainult oma plaanipiirangutes; renet lükkab tagasi kõik väljaspool serdi piire.
- **Serdi jagamine juurutuste vahel**: ahela hargnemine tuvastatakse uuendamisel (tagastab `CHAIN_FORK_DETECTED`).
- **Kvoodi möödasõit mitme paigalduse kaudu**: jõustatakse ülesvoolu ühe-aktiivse poolt (üks sert tellimuse kohta).
- **Ahela tagasipööramine**: renet salvestab kõrgeima-järjestuse-nähtud iga tellimuse kohta ja lükkab tagasi mis tahes blokki madalamate järjestustega.
- **Kompromiteeritud ülesvoolu mandaadid**: bootstrap `delegation:renew` token on loodav ainult pühendatud portaali lõpp-punkti kaudu ja on administraatoriga piiratud. Token annab ainult uuendamise -- see ei saa lugeda ega muuta ühtegi muud ressurssi.
- **Kordusrünnakud manifestidele**: üle 7 päeva vanad manifestid lükatakse tagasi.

Mille vastu see **ei** kaitse:

- **Kompromiteeritud kohapealne privaatvõti**: lekkiv privaatvõti lubab ründajal allkirjastada litsentse kuni serdi `validUntil`. Leevendus: pöörake võtmepaar (tühistage vana sert + looge uus uue võtmega) ja käsitlege kõiki vana võtmega allkirjastatud litsentse kahtlustatavana.
- **Kompromiteeritud ülesvoolu peaserveri võti**: see on usalduse juur. Pööramisprotseduurid on siin käsitlusest väljas.
