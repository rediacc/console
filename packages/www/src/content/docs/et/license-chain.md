---
title: "Litsentsiahelad ja delegeerimine"
description: "Võltsimiskindel litsentside väljastamine, delegeeritud allkirjastamine kohapealsete lahenduste jaoks ning hargnemise tuvastamine."
category: "Guides"
tags:
  - account
  - security
order: 8
language: et
sourceHash: "d6d980d721be2373"
sourceCommit: "fc24769cfd0684622952395c5bafe44e6180530d"
---

# Litsentsiahelad ja delegeerimine

Rediacc kasutab litsentside väljastamiseks võltsimiskindlat räsiahela ning kohapealsete juurutuste jaoks delegeerimissertifikaadi mudelit. See leht selgitab, kuidas süsteem kaitseb võltsimise, kordusründe ja litsentsi jagamise eest.

## Miks ahel?

Iga kontoserveri poolt väljastatud litsents salvestatakse ainult lisatavasse registrisse. Iga kirje on seotud eelmisega SHA-256 räsi kaudu, moodustades ahela. Ahelal on kolm omadust, mis muudavad võltsimise tuvastatavaks:

1. **Järjekorranumbrid** on globaalsed ja monotoonselt kasvavad tellimuse kohta. Kirjete vahelejätmine või ümberseadmine murrab ahela.
2. **Ahela räsid** seovad iga kirje kõikide eelmistega. Mis tahes varasema kirje muutmine tühistab kõik sellele järgnevad kirjed.
3. **Renet talletab kõrgeima nähtud järjekorranumbri** allkirjastamisvõtme ja tellimuse kohta. Server, mis oma järjekorranumbrit tagasi pöörab, tuvastatakse koheselt.

## Kuidas litsents väljastatakse

Kui CLI taotleb hoidla litsentsi, teeb kontoserver järgmist:

1. Loeb praeguse ahela pea (viimane järjekorranumber + räsi) tellimuse jaoks.
2. Koostab litsentsikoorma järgmise järjekorranumbruga ja eelmise ahela räsiga sisseehitatuna.
3. Allkirjastab koorma Ed25519-ga.
4. Arvutab `chainHash = SHA256(prevChainHash + ":" + signedPayload)`.
5. Lisab kirje väljastamisregistrisse aatomiliselt. Kui kaks samaaegset päringut põrkuvad samal järjekorranumbril, omandab kaotaja järgmise järjekorranumbri uuesti ja allkirjastab uuesti.
6. Tagastab allkirjastatud ploki koos ahela räsiga CLI-le.

`sequence` ja `prevChainHash` on allkirjastatud koormas (nii et neid ei saa muuta allkirja tühistamata). `chainHash` on ümbrisel (arvutatud pärast allkirjastamist, et vältida ringlussõltuvust).

## Kuidas litsentsi uuendatakse

Väljastamine käib sinu tööjaamast ja on autenditud sinuna. Uuendamine aga käib masinast, millel ei ole ühtegi konto mandaati. Seepärast vajab see teist ust:

```
POST /licenses/renew
{ license: <paigaldatud allkirjastatud plokk>, machineId, clusterId? }
```

**Esitatud litsents ongi mandaat.** Sellel lõpp-punktil ei ole API-tokenit. Server kontrollib ploki Ed25519 allkirja ja, kui plokk kannab delegeerimissertifikaati, ka selle kaudu, täpselt nagu Renet seda masinas teeb. Kehtivalt allkirjastatud repositooriumilitsentsi omamine ongi õiguse tõend, ja masinale, kellel see olemas on, on see juba varem antud.

Selle lõpp-punkti täielik URL liigub kaasas iga litsentsiga, mille server väljastab või uuendab, väljal `renewalUrl`. Masin loeb oma account-serveri aadressi omaenda litsentsist, selle asemel et see talle eraldi seadistada, ja just tänu sellele saab kahte konto-universumit teenindav masin end mõlemas uuendada.

Uuendatud plokk säilitab esitatud ploki repositooriumi GUID-i, grand-GUID-i ja tüübi, võtab samast registrist järgmise järjekorranumbri koos sellest tuleneva ahela räsiga ning saab värskelt arvutatud kehtivusaknad. Masina ID seotakse uuesti selle masinaga, kes ploki esitas, ja just nii paraneb VM-i migratsioon 40-päevase tähtajaperioodi jooksul ise. Salvestuse identiteet (LUKS UUID või salvestuse sõrmejälg) kantakse muutmata kujul üle, sest võrgupäring ei saa üle vaadata ketast, mida ta kirjeldab.

### Keeldumised

| Kood | Olek | Tähendus |
|---|---|---|
| `INVALID_LICENSE_SIGNATURE` | 403 | Ploki allkirja ei õnnestunud kontrollida või selle ahela räsi ei ühti serveri registriga sellel järjekorranumbril |
| `INVALID_LICENSE_PAYLOAD` | 400 | Plokk on vigase kujuga |
| `DELEGATION_CERT_INVALID` | 403 | Kaasas olev sert ei vastanud mõnele piirangule või selle peamise võtme allkirjale |
| `DELEGATION_CERT_EXPIRED` | 403 | Kaasas olev sert on väljaspool oma kehtivusakent |
| `DELEGATION_CERT_REVOKED` | 403 | Kaasas olev sert on ülesvoolu tühistatud |
| `LICENSE_IDENTITY_MISMATCH` | 403 | Litsentsi esitav masin ei ole litsentsitud masin ja 40-päevane tähtajaperiood on möödas |
| `SUBSCRIPTION_LAPSED` | 403 | Tellimus on aegunud või peatatud |
| `GRACE_PERIOD_ENDED` | 403 | Tellimuse tähtajaperiood on läbi |
| `TRIAL_REQUIRED` | 403 | Tellimus vajab aktiivset prooviperioodi või plaani |
| `REPO_GUID_OWNERSHIP_CONFLICT` | 403 | Repositooriumi GUID kuulub teisele tellimusele |
| `LICENSE_RENEWAL_FAILED` | 500 | Kõik klassifitseerimata juhtumid |

Keeldumine jätab paigaldatud litsentsi puutumata. Masin töötab olemasoleva litsentsiga edasi kuni selle kõva aegumiseni.

### Uuendamine ja masina koht

Edukas uuendamine puudutab masina aktiveerimise kirjet: kui masinal kohta ei olnud, võtab see koha, ja kui oli, värskendab seda. Erinevalt väljastamisest ei keelduta sellest kunagi limiidi ületamise pärast. Vastus kannab välja `overLimit` ja aktiveering märgistatakse, nii et portaal, litsentsi oleku lõpp-punkt ja `rdc subscription status` saavad seda näidata. Päris uue litsentsi väljastamine seevastu põrkab endiselt kõvasti lae vastu. Põhjendust vaata jaotisest [Tellimus ja litsentsid - masina kohad](/et/docs/subscription-licensing).

### Juurutamise järjekord

Account-serverid juurutatakse enne neid CLI ja Renet'i agendi ehitusi, mis ülalkirjeldatud väljadest sõltuvad. Renet'i agent, mis litsentsist `renewalUrl` välja ei loe, jätab selle repositooriumi vahele ja ütleb seda välja, selle asemel et nurjuda, nii et vanem litsents töötab edasi, kuni tööjaama poolne värskendus välja täidab. Vastupidises järjekorras juurutades jäävad masinad küsima lõpp-punkti, mida veel ei ole.

## Kuidas Renet valideerib

Iga Renet'i käitav masin talletab oma viimati teada ahela oleku aadressil `{licenseDir}/chain-state.json` (see tähendab `/var/lib/rediacc/license/chain-state.json`, mis asub hoidla-põhise `repos/` kataloogi kõrval). Ahela olek on piiritletud allkirjastamisvõtme, tellimuse, repositooriumi ja andmesalve kaupa, võtmega `"<keyId>:<subscriptionId>:<repositoryGuid>:<datastoreId>"` (andmesalve osa jääb tühjaks repositooriumi puhul, mis asub masina vaikimisi andmesalves).

Selle võtme repositooriumi- ja andmesalve-osa on hädavajalikud. Serveripoolsed järjekorranumbrid on tellimuse kaupa, nii et masinal, kus on ühe tellimuse all mitu repositooriumi, jääks repositooriumi B jaoks salvestatud ahela pea ettepoole litsentsist, mida repositoorium A esitama hakkab, ja repositoorium A lükataks tagasi kordusründena, millega tal midagi pistmist ei ole. Andmesalve kahvel teravdab sama probleemi: kahvel säilitab repositooriumi GUID-i ja ainult tema andmesalve identiteet vermitakse uuesti, nii et ilma andmesalve osata viiks kahvli värskem litsents pea edasi, mille vastu algne repositoorium ikka veel valideerib. Salvestatud pea sidumine just selle repositooriumi ja andmesalvega, mille litsents nimetab, kaotab mõlemad probleemid. Kirjed, mille vanem Renet'i agent kirjutas lühemas võtmevormingus, kustutatakse esimesel oleku salvestamisel ja järgmine valideerimine seab pea uuesti paika.

Ahela olekut loetakse ja edendatakse ainult nendel toimingutel, mis valideeritakse täies mahus. Käitustase seda ei loe ega edenda, seega repositooriumi käivitamine ei saa kunagi pead liigutada.

Iga litsentsi valideerimisel kontrollib Renet:

| Kontroll | Tõrge tähendab |
|---|---|
| Ed25519 allkiri on kehtiv | Litsents on võltsitud või võltsimisega muudetud |
| `sequence >= lastKnownSequence` | Server pööras ahela tagasi (kordusrünne) |
| `lastKnownSequence` kordus kannab sama `chainHash` väärtust | Hargnenud ahel kasutas järjekorranumbrit uuesti |
| `chainHash == SHA256(prevChainHash + ":" + payload)` | Ahela kirjet on muudetud |

Juba paigaldatud litsentsi uuesti valideerimine ei ole regressioon: sama järjekorranumber sama ahela räsiga võetakse vastu, ja just see lubab masinal sama faili iga repositooriumi käivitamise juures üle kontrollida.

Kui mõni kontroll ebaõnnestub, lükatakse litsents tagasi ja esitatakse tõrke põhjus.

## Delegeerimissertifikaadid (kohapealne)

Õhulõhega eraldatud või isehallatavate juurutuste jaoks väljastab ülesvoolu kontoserver **delegeerimissertifikaadi**, mis volitab kohapealset serverit allkirjastama litsentse oma Ed25519 võtmega. Sertifikaat piirab, mida kohapealne server teha saab.

### Sertifikaadi struktuur

Delegeerimissertifikaat sisaldab järgmist:

- `subscriptionId` -- millisele tellimusele see sertifikaat kohaldub
- `planCode`, `maxMachines`, `maxRepositorySizeGb`, `maxRepoLicenseIssuancesPerMonth` -- plaani piirangud sisseehitatuna
- `maxTotalIssuances` -- ahela järjekorranumbri ülempiir
- `delegatedPublicKey` -- kohapealse serveri Ed25519 avalik võti (SPKI base64). Selle 16-kohaline hex-sõrmejälg (toorvõtme `SHA-256` esimesed 8 baiti) on `publicKeyId`, mis salvestatakse igasse litsentsiplokki, mille see võti allkirjastab. `publicKeyId` on alati tegelik võtme sõrmejälg, mitte kunagi kohatäide nagu `"default"`.
- `genesisHash` -- ahela lähtepunkt (jätk eelmisest sertifikaadist või "genesis")
- `genesisSequence` -- ahela järjekorranumber väljastamise ajal. Kasutatakse `/onprem/cert-upload` poolt, et valideerida, et uus sertifikaat seostub kohaliku väljastamisregistri teadaoleva kirjega, kui ahel on transiidi ajal edenenud. Valikuline tagasiühilduvuse jaoks (käsitletakse 0-na, kui puudub).
- `validFrom`, `validUntil` -- kehtivusaken (reguleeritud allpool kirjeldatud kehtivuspoliitika järgi)
- Allkirjastatud ülesvoolu peamise Ed25519 võtmega

### Kuidas delegeerimine toimib

1. Ettevõtte administraator genereerib Ed25519 võtmepaari kohapealsel serveril.
2. Administraator taotleb delegeerimissertifikaati ülesvoolu serverilt:
   ```
   POST /admin/delegation-certs
   { subscriptionId, validDays: 90, delegatedPublicKey: "MCowBQYDK2VwAyEA..." }
   ```
3. Ülesvoolu server allkirjastab sertifikaadi oma peamise võtmega ja tagastab selle.
4. Kohapealne server talletab sertifikaadi ja oma privaatvõtme, olles valmis litsentse allkirjastama.
5. Kui CLI taotleb kohapealselt serverilt litsentsi, allkirjastab server delegeeritud võtmega ja **manustab kogu delegeerimissertifikaadi litsentsiploki sisse** (väli `delegationCert`). Sertifikaati ei tooda eraldi; see liigub kaasas iga hoidla litsentsiga.
6. Renet teostab **kaheastmelise valideerimise** selles järjekorras:
   - Kontrollib sertifikaadi allkirja sisseehitatud ülesvoolu peamise võtme suhtes.
   - Jõustab sertifikaadi kehtivusakna (`validFrom` / `validUntil`) kasvutoimingutel (`repo create`, `fork`, `resize`, `expand`) ja varunduse ülekandel (`repo push`, `pull`, varundused). Käitustase (`repo up`, `up all`, automaatkäivitus) jätab vahele ainult akna, sarnaselt sellele, kuidas ta juba jätab vahele litsentsi aegumise: teie töötavad koormused ei peatu kunagi sertifikaadi aegumise tõttu, kuid aegunud sertifikaat ei saa autoriseerida midagi uut. Allkiri, võtme sidumine ja kõik muud sertifikaadi piirangud jäävad jõustatuks kõigil tasemetel.
   - Nõuab, et `fingerprint(cert.delegatedPublicKey) == blob.publicKeyId` (16-kohaline hex-võtme sõrmejälg), nii et sertifikaat saab kinnitada ainult litsentse, mis on allkirjastatud täpselt selle võtmega, millele ta delegeerib.
   - Kontrollib ploki allkirja sertifikaadi delegeeritud võtme suhtes.
   - Jõustab sertifikaadi piirangud: tellimuse vastavus, plaani vastavus, suuruse ülempiir (`maxRepositorySizeGb`) ja `blob.sequence <= cert.maxTotalIssuances`.
   - Rakendab kõik standardsed ahela kontrollid.

Sertifikaadi tõrge nurjub kohe pühendatud põhjusega: `cert_expired` (väljaspool kehtivusakent) või `cert_invalid` (vigane peamise võtme allkiri või rikutud piirang). Neid kontrollitakse **enne** `invalid_signature` kontrolli, seega võidab sertifikaadi põhjus.

Kohapealne server ei saa:
- Võltsida litsentsi väljaspool delegeerimissertifikaadi plaani piiranguid (Renet lükkab selle tagasi).
- Väljastada rohkem kui `maxTotalIssuances` kokku toiminguid (Renet lükkab järjekorranumbri ületamise tagasi).
- Jätkata käivitatavate litsentside allkirjastamist pärast sertifikaadi `validUntil` möödumist (aken jõustatakse ka toimingutel, mis aegumist muidu vahele jätavad).
- Muuta sertifikaati (ülesvoolu allkiri murrab).

## Kehtivuspoliitika

Delegeerimissertifikaadi kehtivusaken arvutatakse jagatud poliitika abifunktsiooniga (`computeDelegationCertValidity()`), mis töötab nii ülesvoolu taustal kui ka kliendi portaali esiküljel. Samad sisendid toodavad alati sama `validUntil`, nii et kliendid saavad loomise dialoogis enne esitamist tegeliku kehtivuse eelvaadet näha.

### Plaanipõhised vaikeväärtused ja laed

| Plaan | Vaikekehtivus | Plaani lagi |
|---|---|---|
| COMMUNITY | 15 päeva | 30 päeva |
| PROFESSIONAL | 60 päeva | 120 päeva |
| BUSINESS | 90 päeva | 180 päeva |
| ENTERPRISE | 120 päeva | 365 päeva |

Vaikeväärtus on see, mille loomise lõpp-punkt valib, kui helistaja jätab `validDays` ära. Lagi on ülempiir, mida helistaja saab taotleda.

### Tellimusepõhine alistamine

Administraatorid saavad seada kohandatud `delegationCertDefaultDays` väärtuse konkreetsele tellimusele haldus-Subscription Detail lehe kaudu. **Alistamine asendab nii vaikeväärtuse KUI KA lae sellele tellimusele.** See on pääsetee erilistele klientidele (nt ettevõttleping, mis vajab 200-päevast sertifikaati COMMUNITY plaanil). Zod-skeem jõustab siiski absoluutse `1..365` vahemiku.

### Kõva piir: tellimuse lõpp + 3-päevane armuaeg

Sõltumata plaani laest ja alistamisest, on iga sertifikaat kõvalt piiratud väärtusega `subscription.expiresAt + 3 päeva` (olemasolev `SUBSCRIPTION_CONFIG.gracePeriodDays`). See tähendab:

- Igaveste tellimuste korral (`expiresAt = null`) ei kohaldata aegumise piirangut -- ainult plaani lagi.
- Stripe'i kuu-arveldusega tellimuste korral on piir ligikaudu järgmine arveldusdaatup + 3 päeva. Kui Stripe edasiviib igakuiselt `expiresAt`, liigub piir sellega kaasa.
- Proovitellimuste korral on piir prooviaeg + 3 päeva.

### Tegelik kehtivus + põhjus

Iga loomine/uuendamine vastus sisaldab `effectiveDays` ja `reason` välju, et helistaja näeks täpselt, miks sertifikaat sai selle kehtivuse:

| Põhjus | Tähendus |
|---|---|
| `plan_default` | Taotlust pole, alistamist pole -- kasutati plaanipõhist vaikeväärtust |
| `subscription_override` | Taotlust pole -- kasutati tellimusepõhist alistamist vaikeväärtusena |
| `requested` | Helistaja taotlus täideti kõikide piirangute piires |
| `plan_max_clamp` | Helistaja taotlus ületas plaani lae -- vähendati |
| `override_max_clamp` | Helistaja taotlus ületas tellimusepõhist alistamist -- vähendati |
| `subscription_cap_clamp` | Muidu kehtiv sihtmärk ületab tellimuse `expiresAt + 3 päeva` |

Portaali loomise dialoog kasutab neid põhjuseid reaalajas eelvaate kuvamiseks ("Saate 18-päevase sertifikaadi. Vähendati, kuna sertifikaat ei tohi ületada teie tellimuse lõppkuupäeva rohkem kui 3 päeva võrra."), et kliendid ei esitaks pimesi.

### Kohanduv uuendamislävi

Kohapealne automaatse uuendamise silmus kasutab Let's Encrypt'i eeskujul kohanduvat läve:

```
effectiveThresholdDays = min(env.RENEW_THRESHOLD_DAYS, ceil(certValidityDays / 3))
```

15-päevane COMMUNITY sertifikaat uueneb 5 jääval päeval. 90-päevane BUSINESS sertifikaat uueneb 14 jääval päeval (keskkonnaseadistuse lagi lülitub sisse). 120-päevane ENTERPRISE sertifikaat uueneb 14 jääval päeval. See takistab lühikese elueaga sertifikaatide kohest uuendamise käivitamist, andes samas pika elueaga sertifikaatidele mugava puhvri.

## Ühe aktiivse sertifikaadi jõustamine

Tellimusel võib olla **korraga maksimaalselt üks aktiivne delegeerimissertifikaat** (`MAX_ACTIVE_DELEGATION_CERTS_PER_SUBSCRIPTION = 1`).

### Miks üks?

Iga kohapealne installatsioon jõustab `maxRepoLicenseIssuancesPerMonth`, `maxActivations` ja ahela terviklikkust oma kohaliku väljastamisregistri suhtes. Kohapealne installatsioon ei sünkrooni kasutusarve ülesvoolu serveriga. See ongi võrguühenduseta võimelise delegeerimise mõte.

Kui tellimusel oleks mitu aktiivset sertifikaati (üks installi kohta), jõustaks iga installatsioon piirangu iseseisvalt:

- 500/kuus tellimus 3 aktiivse sertifikaadiga lubab tegelikkuses kuni **1500 väljastamist kuus**.
- Kolm paralleelset ahelat, millest iga on ankurdatud genesisele, ilma võimaliku auditi lepitamiseta.

Ülesvoolu server ei suuda seda möödaminekut tuvastada, kuna kohapealsed on loodud võrguühenduseta töötamiseks. **Ühe aktiivse sertifikaadi mudel on ainus jõustatav mudel.** Mitme installatsiooniga kliendid (tootmine + lavastus + DR) peavad ostma ühe tellimuse installi kohta.

### Kokkupõrke käitumine

`POST /admin/delegation-certs` ja `POST /portal/delegation-certs` lükkavad teise loomise tagasi:

```json
HTTP/1.1 409 Conflict
{
  "code": "DELEGATION_CERT_ALREADY_ACTIVE",
  "existingCertId": "...",
  "actions": {
    "renew": "POST /portal/delegation-certs/process-renewal-request (preserves chain)",
    "revokeAndCreate": "POST /portal/delegation-certs/{existingCertId}/revoke then retry create"
  }
}
```

Portaal kuvab seda spetsiaalse dialoogiga, mis selgitab tagajärgi:

- **Uuendamine (soovitatav)** -- pikendab olemasolevat ahelat. Kõik varem väljastatud hoidla litsentsid töötavad edasi.
- **Tühistamine ja loomine** -- hülgab olemasoleva ahela ja alustab genesisest uuesti. Varem väljastatud hoidla litsentsid muutuvad kontrollitamatuks, kui VANA sertifikaadi `validUntil` möödub. Kasutage ainult juhul, kui olete rändanud uuele kohapealsele serverile erineva allkirjavõtmega, või kui taastute ohustatud võtmest.

`renew()` on aatomiline vahetus, mis säilitab ühe aktiivsuse ja ei allu 409 kokkupõrke kontrollile.

### Kiiruspiirang

Isegi ühe aktiivse sertifikaadi korral võib pahatahtlik helistaja aaseldada `tühista -> loo -> tühista -> loo`, et kulutada ülesvoolu peamise võtme allkirjatsükleid. Mõlemad loomise lõpp-punktid piiravad **10 katse keemisaega per 24 tunni jooksul** tellimuse kohta olemasoleva `rateLimits` tabeli kaudu:

```
HTTP/1.1 429 Too Many Requests
Retry-After: 78234
{ "code": "DELEGATION_CERT_RATE_LIMITED", "retryAfterSec": 78234 }
```

Loendur suureneb iga katse korral sõltumata tulemusest (kokkupõrke rämpspost on samuti piiratud).

## Hargnemise tuvastamine

Kui klient jagab oma delegeerimissertifikaati teise osapoolega (või käitab kaht kohapealset serverit samalt sertifikaadilt), hargnevad ahelad. Ülesvoolu server tuvastab selle uuendamise ajal.

### Uuendamise voog

1. Kohapealne administraator kutsub `POST /admin/delegation-certs/renew` praeguse ahela peaga:
   ```
   { subscriptionId, currentChainHash, currentSequence, delegatedPublicKey }
   ```
2. Ülesvoolu server läbib ahela kirjed oma registri kirje suhtes.
3. Kui `currentChainHash` ei vasta ülesvoolu salvestatud ahelale `currentSequence` juures, tuvastatakse hargnemine:
   ```
   409 { code: 'CHAIN_FORK_DETECTED', divergedAtSequence: N }
   ```
4. Uue sertifikaadi `genesisHash` on seatud praegusele ahela räsile, nii et vana ahela olekuga masinad saavad jätkata sealt, kus jäid.

Kui sertifikaat jagatakse mitte-kliendiga:
- Nad saavad seda kasutada sertifikaadi kehtivusaja jooksul.
- Esimesel uuendamisel näeb ülesvoolu server ainult ühte ahelat (legitiimset).
- Uue sertifikaadi `genesisHash` sobib ainult legitiimsele ahelale.
- Jagatud ahelal olevad masinad lükkavad uued litsentsid koheselt tagasi, kuna nende salvestatud `chainHash` ei ühendu uue sertifikaadi `genesisHash`-iga.

## Võrguühenduseta uuendamine

Kohapealsete installatsioonide jaoks, millel puudub väljaminev HTTPS-juurdepääs ülesvoolu serverile, on uuendamise voog täielikult võrguühenduseta. On kolm uut lõpp-punkti, mis sulgeva ringi:

**Kohapealsel serveril (`auth, root, requireElevated()`):**
- `GET /onprem/cert-current` -- laadi alla praegu laaditud allkirjastatud sertifikaat (varukoopia, audit, reimport)
- `GET /onprem/renewal-request` -- genereeri allkirjastatud manifest, mis sisaldab kohalikku ahela pead + delegeeritud avalikku võtit, allkirjastatud kohapealse privaatvõtmega

**Ülesvoolu serveril (administraator või organisatsioonipõhine portaal):**
- `POST /admin/delegation-certs/process-renewal-request` (ristikliendi süsteemi juur)
- `POST /portal/delegation-certs/process-renewal-request` (organisatsiooni omanik/administraator)

### Uuendamistaotle manifest

Uuendamistaotlus on väike JSON-dokument:

```json
{
  "manifest": {
    "schemaVersion": 1,
    "generatedAt": "2026-04-15T12:00:00.000Z",
    "subscriptionId": "...",
    "currentChainHash": "...",
    "currentSequence": 42,
    "delegatedPublicKey": "MCowBQYDK2VwAyEA...",
    "currentCertValidUntil": "...",
    "currentCertPublicKeyId": "...",
    "currentCertId": null
  },
  "signature": "<base64 Ed25519>",
  "publicKeyId": "..."
}
```

Allkiri arvutatakse manifesti kanoonilist kodeeringut (võtmed tähestiku järjekorraga sorteeritud, seejärel `JSON.stringify`) kasutades kohapealse privaatvõtmega. See garanteerib, et mõlemad pooled arvutavad identsed baidid sõltumata objekti koostamise järjekorrast.

### Kontroll ülesvoolu serveril

`processRenewalManifest()` teostab viis kontrolli:

1. **Aktiivne sertifikaat eksisteerib** manifesti tellimuse jaoks. Tagastab muul juhul `404 NO_ACTIVE_CERT` -- klient peaks kasutama loomise voogu, mitte uuendamist.
2. **Delegeeritud avalik võti vastab** aktiivsele sertifikaadile. Tagastab muul juhul `400 DELEGATED_KEY_MISMATCH` -- kaitseb kordusründe eest eri kohapealsest serverist.
3. **Manifesti allkiri on kehtiv** aktiivse sertifikaadi `delegatedPublicKey` suhtes. Tagastab muul juhul `400 MANIFEST_SIGNATURE_INVALID` -- tõendab, et manifest tuli kohapealse privaatvõtme hoidja käest.
4. **Manifesti vanus** on 7 päeva piires (`RENEWAL_MANIFEST_MAX_AGE_MS`). Tagastab muul juhul `400 MANIFEST_EXPIRED` -- kordusrünnete ankur.
5. **Ahela räsi linkimine** manifesti `currentSequence` juures vastab ülesvoolu registrile. Tagastab muul juhul `409 CHAIN_FORK_DETECTED` -- kaitseb hargnenud ahelate eest.

Kui kõik kontrollid läbivad, kutsub `processRenewalManifest` olemasolevat `renew()` voogu, mis aatomiliselt aegub vana sertifikaadi ja lisab uue. **See ei allu loomispoole ühe aktiivse 409 kontrollile**, kuna tegemist on aatamilise vahetusega, mitte 2-sammulise tühistamise+loomisega.

### Järjekorranumbri edenemine transiidi ajal

Uuendamistaotle manifest jäädvustab ahela pea genereerimise hetkel. Kuni manifest on transiidis (USB-tarnimine, krüpteeritud e-post), võib kohapealne server jätkata hoidla litsentside väljastamist, edendades oma kohalikku ahelat.

Kui uus sertifikaat laaditakse kohapealsele serverile tagasi, valideerib `/onprem/cert-upload`, et uue sertifikaadi `genesisSequence` seostub endiselt kohaliku väljastamisregistri teadaoleva kirjega:

- Kui `cert.genesisSequence > localHead.sequence` -- tagastab `409 CHAIN_HEAD_BEHIND` (ülesvoolu server on hargnenud ahelal).
- Kui `cert.genesisSequence > 0` ja kohaliku registri kirjel sel järjekorranumbril on erinev `chainHash` kui `cert.genesisHash` -- tagastab `409 CHAIN_FORK_ON_UPLOAD` (kohalik ahel on harunenud).
- Vastasel juhul aktsepteeritakse sertifikaat. Tulevased väljastamised jätkuvad `localHead.sequence + 1`-st.

See tähendab, et **transiidi ajal ei ole kirjutamise külmutamine vajalik**. Ahel laieneb loomulikult mõlemal poolel. Vastab sellele, kuidas X.509 sertifikaadi uuendamine käitleb lennul olevaid seerianumbreid.

## Perioodiline audit

Ülesvoolu server pakub auditi lõpp-punkti ahela terviklikkuse kontrollimiseks ilma sertifikaati uuendamata:

```
POST /admin/delegation-certs/audit
{ subscriptionId, chainEntries: [{ sequence, chainHash }, ...] }
```

Ülesvoolu server läbib kirjed ja tagastab kas `{ valid: true }` või `{ valid: false, divergedAtSequence: N, expected, actual }`.

Kohapealsed serverid peaksid seda lõpp-punkti perioodiliselt kutsuma (vaikimisi: iganädalaselt `UPSTREAM_AUDIT_URL` keskkonna muutuja kaudu), et tuvastada hargnemised varakult.

### Masinasüsteemi auditijälg

Renet saab kontrollida ahela järjepidevust kohalikult `VerifyAuditProof` abil. Kui masin uuendab oma litsentsi pärast pikka pausi, saab server tagastada vahepealsed ahela kirjed tõendina. Masin läbib tõendi, et kontrollida, et iga `chainHash` tuleneb eelmisest `prevHash + blobHash` SHA-256 kaudu, tabades igasuguse võltsimise ilma ülesvoolu serveriga ühendust võtmata.

## Samaaegsuse turvalisus

D1 (Cloudflare'i andmebaas) ei toeta interaktiivseid tehinguid. Samaaegsed litsentside väljastamised samale tellimusele võivad järjekorranumbril põrkuda. Kontoserver käitleb seda järgmiselt:

1. Loeb järgmise järjekorranumbri + eelmise ahela räsi.
2. Koostab ja allkirjastab ploki selle järjekorranumbriga sisseehitatuna.
3. Sisestab registri kirje `onConflictDoNothing` valikuga.
4. Kui sisestamine tagastab 0 muudetud rida, nõudis järjekorranumbri teise päringu -- omandab uuesti järjekorranumbri, koostab uuesti, **allkirjastab uuesti** ja proovib uuesti.
5. Pärast 10 ebaõnnestunud katset nurjub veaga.

Kriitiline detail: uuesti proovimisega **allkirjastatakse plokk uuesti**. Naiivne uuesti proovimine, mis värskendas ainult registri kirjet, jätaks allkirjastatud ploki aegunud järjekorranumbriga, murdes ahela.

## E-posti transport

Kontoserver saab saata tehingulisi e-kirju (maagilised lingid, paroolide lähtestamine, turvateated) kahe ühendatava transpordi kaudu:

| Transport | Konfiguratsioon |
|---|---|
| `ses` (vaikimisi) | `AWS_SES_ACCESS_KEY_ID`, `AWS_SES_SECRET_ACCESS_KEY`, `AWS_SES_REGION`, `AWS_SES_FROM` |
| `smtp` | `EMAIL_TRANSPORT=smtp`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_SECURE`, `SMTP_FROM` |

Mõlemad transpordid töötavad pilve ja kohapealsete juurutuste jaoks. Valige see, mis sobib teie infrastruktuuriga: AWS SES oma AWS-kontoga või mis tahes SMTP-server (Microsoft Exchange, Postfix, SendGrid, Mailgun jne).

Transport valitakse käivitamisel `EMAIL_TRANSPORT` keskkonna muutuja kaudu. SMTP kasutab ühenduse kogumist ja laiska laadimist, nii et SMTP-klientide teek lähtestub ainult siis, kui SMTP on valitud.

Kõik e-posti mallid ja avalik e-posti API on transpordite lõikes identsed.

## Seotud dokumentatsioon

- [Kohapealne installatsioon](/et/docs/on-premise) -- kuidas juurutada kohapealset serverit
- [Tellimus ja litsentsimine](/et/docs/subscription-licensing) -- plaani piirangud ja masina pesad
- [Väljalaskekanalid](/et/docs/release-channels) -- edge vs stable kanalid
- [Andmeregioonid](/et/docs/data-regions) -- piirkondlik andmete residentsus
