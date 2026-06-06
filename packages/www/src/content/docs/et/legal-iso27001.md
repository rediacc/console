---
title: "ISO 27001 vastavus"
description: "Kuidas Rediacc vastab ISO 27001 infoturbe kontrollidele krüptimise, juurdepääsuhalduse ja operatsiooniturvalisuse valdkonnas."
category: "Legal"
order: 5
language: et
sourceHash: "52709a22c0b38178"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

Okei. ISO/IEC 27001:2022 on rahvusvaheline infoturbe haldussüsteemide standard. ISO/IEC on selle avaldanud ja tegemist on pika dokumendiga, mis käsitleb kontrolle krüptimise, juurdepääsuhalduse, juhtumitevastase reageerimise ja kümnete muude turvavaldkondade osas. Te kindlasti teate, mis see on. Ütlen siis otse: Rediacc ei käsitle kõiki selle standardi kontrolle ja me ei kavatse seda teeskella. Järgnev on aus kaardistus sellest, kuidas Rediacc sobib. Kehtiv versioon on ISO/IEC 27001:2022.

Viide: [ISO/IEC 27001:2022](https://www.iso.org/standard/27001)

Noh, Rediacc on üks komponent ISMS-i tehniliste kontrollide kihis. Alljärgnev tabel kaardistab Rediacc'i võimalused asjakohaste Lisa A kontrollvaldkondadega.

## Lisa A kontrollide kaardistamine

| Kontrollvaldkond | Kontroll | Rediacc'i võimekus |
|---------------|---------|-------------------|
| **A.8**, Varade haldamine | A.8.1 Varade inventuur | Iga hoidla on eraldiseisev, identifitseeritav vara unikaalse GUID-iga. `rdc machine query --name <machine> --repositories` loetleb kõik hoidlad koos suuruse, ühendamisoleku ja konteinerite arvuga. |
| **A.8**, Varade haldamine | A.8.24 Krüptograafia kasutamine | LUKS2 AES-256 kohustuslik krüptimine kõigil hoidlatel. Võtmehaldus: volitused salvestatakse ainult operaatori lokaalses konfiguratsioonis, mitte kunagi serveris. |
| **A.9**, Juurdepääsukontroll | A.9.2 Kasutajate juurdepääsuhaldamine | SSH-võtme autentimine. API-žetoonid IP-sidumise, meeskonnaulatuse ja automaatse tühistamisega meeskonnast eemaldamisel. Kahefaktoriline autentimine (TOTP) toetatud. |
| **A.10**, Krüptograafia | A.10.1 Krüptograafilised kontrollid | LUKS2 konfigureeritavate võtmeparameetritega. Hoidlapõhised krüptimisvolitused. Kogu kaugtransport SSH kaudu. Konfiguratsioonihoidla rakendab null-teadmise krüptimist: AES-256-GCM HKDF võtme tuletamisega, X25519 liikmete võtmevahetus ja ajaaknaline SDK-võtmed koheseks tühistamiseks. |
| **A.12**, Operatsiooniturvalisus | A.12.3 Varukoopia | `rdc repo push/pull` krüptitud väliseks salvestuseks mitmesse sihtkohta (SSH, S3, B2, Azure, GDrive). CoW-hetktõmmised ajapõhiseks taastumiseks. `rdc repo validate` kontrollib varukoopia seisundit ja hoidla terviklust. |
| **A.12**, Operatsiooniturvalisus | A.12.4 Logimine ja jälgimine | Üle 70 sündmusetüübi (autentimine, API-žetoonid, konfiguratsioon, litsentsid, masina toimingud). Masina terviseseire `rdc machine query` kaudu. Konteineri olek ja ressursside jälgimine. |
| **A.13**, Side turvalisus | A.13.1 Võrguturbe haldamine | Hoidlapõhine Docker-deemoni eraldus. iptablesi reeglid blokeerivad hoidlatevahelise liikluse. Loopback-IP-alamvõrgud (/26) hoidla kohta. Pöördproxy TLS-lõpetusega väliseks juurdepääsuks. |
| **A.14**, Süsteemi arendamine | A.14.2 Turvalisus arenduses | Hargipõhised arenduskeskkonnad pakuvad tootmissarnasust ilma tootmisandmete avaldumiseta. Rediaccfile elutsükli konksud võimaldavad automaatset andmete saniteerimist kloonitud keskkondades. |

## Varade haldamine

Rediacc'i hoidlamudel toetab varade inventuuri nõudeid loomulikul viisil:

- Igal hoidlal on loomise ajal määratud unikaalne GUID
- Hoidlad on masinate kaupa loendatavad (`rdc machine query --repositories`)
- Iga hoidla krüptimisstaatus, ühendamisolek, konteinerite arv ja kettakasutus on nähtavad
- Hargi seosed jälgivad kloonitud keskkondade päritolu

## Muudatuste haldamine

Siin läheb huvitavaks: hargi-testimise-edendamise töövoog on kooskõlas ISO 27001 muudatuste haldamise nõuetega:

1. **Hark**: loo tootmiskeskkonnast eraldatud koopia
2. **Testimine**: rakenda ja valideeri muudatused hargis
3. **Edendamine**: kasuta `rdc repo takeover`, et vahetada hark tootmisse
4. **Auditeerimine**: kõik toimingud logitakse ajatemplite ja tegutseja identifitseerimisega

## Pidev täiustamine

- Auditlogi eksport toetab perioodilisi turvaülevaateid
- Masina tervise kontroll (`rdc machine query --system`) toetab operatiivset seiret
- `rdc repo validate` kontrollib varukoopia seisundit pärast iga toimingut
