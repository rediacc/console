---
title: "Turvaintsidentidele reageerimine"
description: "Kuidas Rediacc käsitleb oma turvaintsidente: etapiviisilised teated klientidele, GDPR art. 33(3) väljad, CRA teavitamistee ja mida kliendid saavad."
category: "Legal"
tags:
  - security
  - compliance
subcategory: foundations
order: 10
language: et
sourceHash: "6b9f728f093ecb0c"
sourceCommit: "72636750e43d473936cbb242ec9c7511fd246f65"
---

Leht kirjeldab, mis juhtub, kui turvaintsident tabab Rediaccit ennast, näiteks kui tema enda süsteemid satuvad kompromiteerimise ohvriks või toodetes avastatakse aktiivselt ärakasutatav haavatavus. Intsidente kliendi enda hoidlates uurib ja menetleb klient ise ning Rediacc pakub selleks tõendite kogumise tööriistu. Väljastpoolt tulevaid haavatavusteateid käsitleb [avalikustamise poliitika](/et/docs/security-disclosure-policy).

## Etapid

Iga intsidendi kell hakkab käima hetkest, kui Rediacc sellest teada saab. Teave antakse etapiviisiliselt, sest täielik pilt on harva esimesel päeval teada ja GDPR art. 33(4) lubab teavet esitada osadena.

| Etapp | Tähtaeg | Sisu |
|-------|---------|------|
| Varajane hoiatus | 24 tunni jooksul | mis on seni teada ja kas kahtlustatakse pahatahtlikku tegevust |
| Teavitus | 72 tunni jooksul | intsidendi laad, esmane hinnang ja võetud meetmed |
| Lõpparuanne | ühe kuu jooksul | üksikasjalik kirjeldus, algpõhjus ning rakendatud ja käimasolevad meetmed |

## Art. 33(3) väljad

Iga etapp sisaldab nelja GDPR art. 33(3) loetletud punkti:

1. rikkumise laad, sealhulgas asjaomaste andmesubjektide kategooriad ja ligikaudne arv ning asjaomaste isikuandmete kirjete ligikaudne arv
2. täiendava teabe saamiseks vajaliku kontaktisiku nimi ja kontaktandmed
3. tõenäolised tagajärjed
4. rikkumise lahendamiseks võetud või kavandatud meetmed, sealhulgas meetmed selle võimalike kahjulike mõjude leevendamiseks

Kui mõni väärtus pole veel teada, märgib etapp seda ja nimetab kuupäeva, mis ajaks see selgub.

## Mida kliendid saavad

Kui intsident mõjutab organisatsiooni:

- iga etapp saadetakse teatena konto portaalis ja e-kirjana organisatsiooni omanikele ja administraatoritele ning selle turvakontaktile
- teade ja e-kiri saadetakse sõltumata teavitamiseelistustest, sest need on turvasõnumid
- portaali bänner viitab intsidendi lehele, mis näitab kõiki avaldatud etappe
- iga etapp pakub STIX 2.1 komplekti kompromiteerimisnäitajatega masinloetavas vormingus, mille turvatööriistad saavad importida

Mõjutamata organisatsioon ei saa midagi. Omanikud ja administraatorid määravad organisatsiooni turvakontakti portaalis, et kiri jõuaks õige inimeseni.

## Regulatiivne teavitamine

Rediacc teavitab oma intsidentidest seal, kus seadus seda nõuab.

- **GDPR.** Kui Rediacc tegutseb volitatud töötlejana, teavitab etapiviisiline teade vastutavat töötlejat põhjendamatu viivituseta (art. 33(2)) ja vastutav töötleja otsustab oma järelevalveasutuse teavitamise üle. Kui Rediacc on ise vastutav töötleja, teavitab ta pädevat järelevalveasutust võimaluse korral 72 tunni jooksul (art. 33(1)).
- **Küberturvalisuse vastupidavuse määrus (Cyber Resilience Act).** Alates 11. septembrist 2026 kohustab määruse (EL) 2024/2847 art. 14 tootjat teatama aktiivselt ärakasutatavast haavatavusest või digielementidega toote turvalisust mõjutavast tõsisest intsidendist määratud CSIRT-ile ja ENISA-le ühtse teavitusplatvormi kaudu. Kehtivad samad 24 tunni, 72 tunni ja lõpparuande sammud ning sama intsidendikirje annab aluse nii klienditeatele kui ka esitatavale teatisele.

## Kahtlustatavast intsidendist teatamine

Igaüks, kes kahtlustab Rediaccit mõjutavat intsidenti, sealhulgas klient, kes märkab Rediacci komponendis ootamatut käitumist, kirjutab aadressil [security@rediacc.com](mailto:security@rediacc.com). Haavatavusest teatamisel kehtib [avalikustamise poliitika](/et/docs/security-disclosure-policy).
