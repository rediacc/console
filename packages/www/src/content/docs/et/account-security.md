---
title: Konto turvalisus ja API ülevaade
description: Autentimine, API-tokenid, seansihaldus ja õiguste mudel.
category: Guides
order: 13
language: et
---

### Autentimine

Rediacc toetab mitut autentimismeetodit:

![Autentimise voog](/img/account-auth-flow.svg)

- **Parool**: Traditsiooniline e-posti ja parooliga sisselogimine
- **Magic Link**: Paroolivaba sisselogimine e-posti lingi kaudu (15-minutine kehtivus)
- **Kahefaktoriline autentimine (2FA)**: TOTP-põhine varuoodidega

Kui 2FA on lubatud, nõuab sisselogimine nii teie parooli (või magic linki) kui ka 6-kohaline TOTP-koodi.

### API-tokenid

API-tokenid autendivad masinatevahelisi toiminguid (CLI litsentsi aktiveerimine, olekukontrollid).

![API-tokeni elutsükkel](/img/account-api-token-lifecycle.svg)

**Ulatused:**
- `license:read` - Tellimuse ja litsentsi oleku pärimine
- `license:activate` - Masinate aktiveerimine ja repo-litsentside väljastamine
- `subscription:read` - Tellimuse üksikasjade lugemine

**Turvafunktsioonid:**
- IP-sidumine: esimene päring lukustab tokeni sellele IP-aadressile
- Meeskonna piirang: tokeneid saab piirata konkreetse meeskonnaga
- Automaatne tühistamine: tokenid tühistatakse, kui looja eemaldatakse organisatsioonist

Tokeni loomine:
```bash
# Portaali kaudu: API Tokens > Create
# Tokeni väärtus kuvatakse üks kord - salvestage see turvaliselt
```

### Seadme koodivogu

CLI saab peata masinatel autentida seadme koodivogu abil:

![Seadme koodivogu](/img/account-device-code-flow.svg)

```bash
rdc config remote enable --headless
# Kuvatakse: Enter code XXXX-XXXX-XX at https://www.rediacc.com/account/authorize
# Pärast kinnitamist saab CLI mandaadid automaatselt
```

### Konfiguratsioonihoidla

Krüpteeritud serveripoolse sünkroonimisega konfiguratsiooni jaoks vaadake täielikku juhendit jaotisest [Konfiguratsioonihoidla](/et/docs/config-storage). Konfiguratsioonihoidla kasutab:
- Nullteadmiste krüpteerimist (server ei näe kunagi lihtteksti)
- Passkey-põhist võtme tuletamist (WebAuthn + PRF)
- Päringupõhiselt pöörlevaid tokeneid

### Seansi turvalisus

| Tokeni tüüp | Kehtivus | Salvestus | Värskendamine |
|-------------|----------|-----------|---------------|
| Juurdepääsutoken (JWT) | 15 minutit | HttpOnly küpsis | Automaatne värskendustoken kaudu |
| Värskendustoken | 7 päeva | HttpOnly küpsis | Pöördutakse igal kasutamisel |
| Kõrgendatud seanss | 10 minutit | Serveripoolne | Käivitatakse taasautentimisega |

Kõrgendatud seansid on vajalikud tundlike toimingute jaoks: parooli muutmine, e-posti muutmine, 2FA seadistamine, omandiõiguse üleandmine ja hävitavad adminitoimingud.

### Lubade mudel

Rediacc kasutab kolme sõltumatut lubade kihti:

![Lubade voog](/img/account-permission-flow.svg)

**Kiht 1: Süstemiroll** - Määrab juurdepääsu süsteemiadministreerimise lõpp-punktidele.

**Kiht 2: Organisatsiooni roll** - Kontrollib, mida kasutaja saab oma organisatsioonis teha (omanik, admin, liige).

**Kiht 3: Meeskonna roll** - Piirab juurdepääsu konkreetsetele meeskonna ressurssidele (team_admin, member). Organisatsiooni omanikud ja adminid mööduvad meeskonna rollikontrollidest.

Iga API-päring läbib järjestikku kõik kohaldatavad kihid. Meeskonnale piiratud lõpp-punkti päring peab täitma seansi autentimise, org-liikmesuse ja meeskonnale juurdepääsu tingimused.

### Uuenduskanalid

CLI toetab kahte väljalaskekanali:
- **stable** (vaikimisi): Tõstetud edge'ist pärast 7-päevast leotust; valige see konservatiivse uuenduskaadentsi jaoks
- **edge**: Pidevalt juurutatud tootmine, uuendatakse igal ühendamisel peaharusse

```bash
rdc update --channel edge      # Lülitu edge-kanalile
rdc update --channel stable    # Lülitu tagasi stable-kanalile
rdc update --status            # Kuva praegune kanal
```

### CLI turvahoiak AI-agentide jaoks

Iga `rdc` käivitamine klassifitseeritakse käivitamisel kas **inimeseks** või **agendiks** keskkonnasignaalide põhjal (CLAUDECODE, GEMINI_CLI, COPILOT_CLI, CURSOR_TRACE_ID, REDIACC_AGENT) koos Linuxi `/proc` esivanemate läbimisega. Agendid saavad vähendatud lubade komplekti: tundlikud konfiguratsioonide muutmised nõuavad teadmiseväravat (`--current <vana>`), interaktiivne redaktor keeldutakse ilma esivanemate kontrollitud `REDIACC_ALLOW_CONFIG_EDIT` alistamiseta, ning `--reveal` mis tahes kuvamiskäsul on blokeeritud. Iga otsus - lubamine, keeldumine, `--reveal` andmine - kirjutab ühe räsiaheldatud JSONL-rea faili `~/.config/rediacc/audit.log.jsonl`. Käivitage `rdc config audit verify`, et kontrollida ahela terviklust.

Vaadake AI-agentide täielikku maatriksit jaotisest [AI-agendi turvalisus ja kaitsemehhanismid](/et/docs/ai-agents-safety), sealhulgas teadmisevärava töönäidiseid ja ulatuse alistamise mehhanisme.
