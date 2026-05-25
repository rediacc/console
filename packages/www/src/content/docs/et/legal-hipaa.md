---
title: "HIPAA vastavus"
description: "Kuidas Rediacc'i krüptimis- ja eraldusarhitektuur vastab HIPAA kaitsemeetmete nõuetele terviseteabe kaitsmisel."
category: "Legal"
order: 3
language: et
sourceHash: "f5fbdaa4a00491ea"
sourceCommit: "43aec6b89a55f69f994476d3a124e749d4d2223f"
---

Tervisekindlustuse ülekantavuse ja vastutuse seadus (HIPAA) on Ameerika Ühendriikide föderaalseadus, mis kehtestab standardid tundlike patsientide terviseandmete (PHI) kaitseks. See kehtib kaetud üksustele (tervishoiuteenuse osutajad, tervisekavad, tervishoiu kliiringukojad) ja nende äripartneritele.

Täistekst: [Public Law 104-191](https://www.govinfo.gov/content/pkg/PLAW-104publ191/html/PLAW-104publ191.htm)

## Kaitsemeetmete kaardistamine

HIPAA nõuab haldus-, tehnilisi ja füüsilisi kaitsemeetmeid. Alljärgnev tabel kaardistab need Rediacc'i võimalustega.

### Tehnilised kaitsemeetmed

| Nõue | HIPAA viide | Rediacc'i võimekus |
|-------------|----------------|-------------------|
| Juurdepääsu kontroll | [45 CFR 164.312(a)](https://www.govinfo.gov/content/pkg/PLAW-104publ191/html/PLAW-104publ191.htm) | SSH-võtmepõhine autentimine. API-žetoonid IP-sidumise ja ulatuse piirangutega. Hoidlapõhine Docker-deemoni eraldus takistab hoidlate vahelist juurdepääsu. |
| Auditikontrollid | [45 CFR 164.312(b)](https://www.govinfo.gov/content/pkg/PLAW-104publ191/html/PLAW-104publ191.htm) | Üle 70 sündmusetüübi, mis hõlmavad autentimist, API-žetoone, konfiguratsioone, litsentse ja masina toiminguid (hoidla elutsükkel, varukoopia, sünkroonimine, terminal). Kasutaja- ja meeskonnapõhine jälg. Eksport haldusarmatuurlaua, portaali tegevuslehe või `rdc audit` CLI kaudu. |
| Tervikluskontrollid | [45 CFR 164.312(c)](https://www.govinfo.gov/content/pkg/PLAW-104publ191/html/PLAW-104publ191.htm) | CoW-hetktõmmised säilitavad algsed andmed enne muudatusi. `rdc repo validate` kontrollib hoidla terviklust ja varukoopia seisundit (LUKS-konteiner, failisüsteemi järjepidevus, konfiguratsioon). |
| Krüptimine puhkeolekus | [45 CFR 164.312(a)(2)(iv)](https://www.govinfo.gov/content/pkg/PLAW-104publ191/html/PLAW-104publ191.htm) | LUKS2 AES-256 krüptimine kõigil hoidla mahtudel. Volitused salvestatakse ainult operaatori lokaalses konfiguratsioonis, mitte kunagi serveris. Konfiguratsioonihoidla kasutab null-teadmise AES-256-GCM krüptimist jagatud võtme tuletamisega. Isegi server ei suuda salvestatud konfiguratsioone dekrüpteerida. |
| Edastuse turvalisus | [45 CFR 164.312(e)](https://www.govinfo.gov/content/pkg/PLAW-104publ191/html/PLAW-104publ191.htm) | Kõik kaugoperatsioonid kasutavad SSH-i. Varukoopia transport on lõpust lõpuni krüptitud. Krüptimata andmeedastust ei toimu. |

### Haldusmeetmed

| Nõue | Rediacc'i võimekus |
|-------------|-------------------|
| Tööjõu juurdepääsu haldamine | API-žetoonid ulatusega piiratud õigustega. Meeskonnapõhine juurdepääsukontroll. Žetooni automaatne tühistamine meeskonnast eemaldamisel. |
| Turvaincidendi menetlused | Auditlogid pakuvad kõigi toimingute kohtuekspertiisi rada. Hoidlapõhine eraldus piirab kahjustuse ulatust. |
| Hädaolukorra planeerimine | `rdc repo push/pull` toetab mitme sihtkoha krüptitud varukoopiat. CoW-hetktõmmised võimaldavad koheselt taastuda. |

### Füüsilised kaitsemeetmed

| Nõue | Rediacc'i võimekus |
|-------------|-------------------|
| Rajatise juurdepääsukontroll | Ise majutatud: teie organisatsioon kontrollib serverite füüsilist turvalisust. Põhitoimingute puhul puudub sõltuvus kolmandate osapoolte andmekeskustest. |
| Tööjaama turvalisus | LUKS krüptib kõik puhkeolekus andmed. Ühendamata hoidlad on kettal krüptitud plokid, mida ei saa ilma operaatori volitusteta lugeda. |

## Äripartneri leping (BAA)

Kuna Rediacc on ise majutatud tarkvara, mis töötab teie infrastruktuuril, ei töötle, salvesta ega edasta see PHI-d Rediacc'i (ettevõttena) süsteemide kaudu. Tüüpiline BAA-nõue kehtib teie infrastruktuuripakkujale (pilveteenuse pakkuja või kolokatsioonirajatis), mitte Rediacc'ile.

Rediacc töötab teie serveritel tarkvaratööriistad sarnaselt operatsioonisüsteemile või andmebaasimootoriga. Sellel puudub juurdepääs teie andmetele. Vabatahtlik konfiguratsioonihoidla sünkroonib krüptitud plokke Rediacc'i serverite kaudu, kuid selle null-teadmise disain tähendab, et server ei suuda sisu dekrüpteerida. See salvestab ainult läbipaistmatut šifriteksti.

## Arenduskeskkonnad PHI-ga

PHI-d sisaldavate tootmiskeskkondade kloonimiseks arendusotstarbel kasutage Rediaccfile `up()` elutsükli konksu saniteerimiskriptide käivitamiseks, mis:

- Eemaldavad PHI andmebaasitabelitest
- Asendavad patsiendi identifikaatorid sünteetiliste andmetega
- Eemaldavad seansimarkerid ja API-võtmed

Arendajad saavad tootmislaadse infrastruktuuri de-identifitseeritud andmetega, rahuldades HIPAA minimaalse vajaliku standardi.
