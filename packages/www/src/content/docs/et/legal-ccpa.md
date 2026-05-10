---
title: "CCPA vastavus"
description: "Kuidas Rediacc'i ise majutatud mudel rahuldab California tarbijate privaatsusseaduse nõuded tarbijate andmekaitse valdkonnas."
category: "Legal"
order: 4
language: et
---

California tarbijate privaatsusseadus (CCPA) on osariigi seadus, mis annab California tarbijatele õigused nende isikuandmete üle, sealhulgas õiguse teada, milliseid andmeid kogutakse, õiguse need kustutada ning õiguse keelduda nende müümisest.

Viide: [California Attorney General, CCPA](https://oag.ca.gov/privacy/ccpa)

## Tarbija õiguste kaardistamine

CCPA keskendub isikuandmetega seotud tarbija õigustele. Rediacc on ise majutatud tööriist, mis on paigaldatud teie infrastruktuurile -- mitte kolmanda osapoole teenus, mis kogub või müüb tarbijate andmeid. Alljärgnev tabel kaardistab CCPA õigused ja selle, kuidas Rediacc toetab teie organisatsiooni vastavust.

| CCPA õigus | Nõue | Rediacc'i võimekus |
|-----------|-------------|-------------------|
| Teabeõigus (1798.100) | Avalikustada kogutavate andmete kategooriad ja eesmärgid | Auditlogi jälgib kõiki andmeoperatsioone. Ise majutatud: teie organisatsioon säilitab täieliku ülevaate sellest, millised andmed igas hoidlas asuvad. |
| Kustutamisõigus (1798.105) | Kustutada tarbija isikuandmed taotluse alusel | `rdc repo destroy` kustutab LUKS-krüptitud mahu krüptograafiliselt. Hargi kustutamine eemaldab kloonitud koopiad. |
| Loobumisõigus (1798.120) | Mitte müüa ega jagada isikuandmeid | Ise majutatud arhitektuur: andmeid ei edastata Rediacc'ile ega ühelegi kolmandale osapoolele. Andmed jäävad teie serveritesse. Konfiguratsioonihoidla sünkroonimine kasutab null-teadmise krüptimist. Isegi sünkroonimisserver ei saa andmeid lugeda. |
| Andmeturve (1798.150) | Rakendada mõistlikke turvameetmeid | LUKS2 AES-256 krüptimine, võrgueraldus, ainult SSH-põhine juurdepääs, eraldatud Docker-deemonid, auditeerimine. Konfiguratsioonihoidla kasutab kolmekihilist krüptimist koos jagatud võtme tuletamise ja pöörlevate ühekordse kasutuse žetoonidega. |

## Teenusepakkuja staatus

Rediacc tarkvarana ei liigu tarbijate andmetele ligi, ei töötle ega salvesta neid. Teie IT-meeskond käitab Rediacc'i teie enda infrastruktuuril. Andmed ei voogla Rediacc'i ettevõttele. Tagajärjed:

- Rediacc ei ole CCPA tähenduses "teenusepakkuja" (ta ei töötle andmeid teie nimel)
- Rediacc'iga ei ole vaja sõlmida andmetöötluslepingut ise majutatud toote puhul
- Teie CCPA kohustused on teie organisatsiooni ja teie tarbijate vahel

## Andmete inventuur

Iga Rediacc'i hoidla on eraldiseisev, krüptitud andmeüksus unikaalse GUID-iga. Saate täpselt inventeerida, millised andmed kus asuvad:

- `rdc machine query --name <machine> --repositories` loetleb kõik masinasse kuuluvad hoidlad koos suuruse ja ühendamisolekuga
- Iga hoidla on failisüsteemi, võrgu ja konteineri tasemel eraldatud
- Hargi seosed on jälgitavad, nii saate tuvastada kõik andmestiku koopiad

CCPA nõuab andmekaardistamist. Rediacc'i hoidlamudel pakub seda: üks GUID andmestiku kohta, loendatav masinate kaupa, koos hargi päritoluga jälgimisega.
