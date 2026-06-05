---
title: "SOC 2 vastavus"
description: "SOC 2-ga on asi lihtne: audiitorid tahavad tõendeid, et sinu kontrollid toimivad. Rediacc annab sulle logid, muudatuste haldamise jälje ja kõik muu, mida nad küsivad."
category: "Legal"
order: 2
language: et
sourceHash: "27d2366f84e21d8c"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

Tean SOC 2-st, sest olen paaril auditoorimiskoosolekul käinud. Audiitorid kasutavad AICPA raamistikku, et kontrollida, kas sinu kontrollid tegelikult toimivad, mitte ainult seda, et sa väidad nende toimivat. Viis usaldusteenuse kriteeriumi: turvalisus, kättesaadavus, töötlemise terviklikkus, konfidentsiaalsus ja privaatsus.

Viide: [AICPA SOC 2](https://www.aicpa-cima.com/topic/audit-assurance/audit-and-assurance-greater-than-soc-2)

## Usaldusteenuse kriteeriumite vastavusmaatriks

| Usaldusprintsiip | Kriteerium | Rediacc võimalus |
|----------------|----------|-------------------|
| **Turvalisus** (CC6) | Loogilised juurdepääsukontrollid, krüptimine | LUKS2 AES-256 puhkeoleku krüptimine. Mandaadid talletatakse ainult operaatori kohalikus konfiguratsioonis (`~/.config/rediacc/`), mitte serveris. SSH-võtmepõhine juurdepääs. Eraldatud Dockeri deemonid hoidla kohta. |
| **Kättesaadavus** (A1) | Süsteemi taastamine ja resilients | `rdc repo push/pull` krüptitud väliskoopiatega SSH, S3, B2, Azure või GDrive'i. CoW-hetktõmmised koheseks tagasipöördumiseks. Hargnemispõhised uuendused nullilähedase seisakuajaga muutuste jaoks. |
| **Töötlemise terviklikkus** (PI1) | Täpne ja täielik töötlemine | Deterministlikud Rediaccfile elutsükli haagid (`up`/`down`) tagavad järjepidevad juurutused. `rdc repo validate` kontrollib hoidla terviklikkust ja varukoopia seisundit pärast ootamatuid seisakuid või varundamistoiminguid. |
| **Konfidentsiaalsus** (C1) | Andmete kaitse volitamata juurdepääsu eest | Hoidlapõhine krüptimine unikaalsete LUKS-mandaatidega. Võrgueraldus iptablesi, eraldi Dockeri deemonite ja loopback-IP-alamvõrkude kaudu. Eri hoidlate konteinerid ei näe üksteist. Zero-knowledge konfiguratsioonihoidla krüpteerib konfiguratsioonid kliendipoolselt enne üleslaadimist. Server talletab ainult läbipaistmatuid plokke, mida ta ei saa dekrüpteerida. |
| **Privaatsus** (P1-P8) | Isikuandmete käitlemine | Isehallatav: toimingute ajal andmeid välja ei kanta. Auditijälg kogu andmetele juurdepääsu kohta. Krüptimisvõtmete haldus on kliendi kontrolli all. Konfiguratsioonihoidla kasutab jagatud võtme tuletamist (pääsvõtme PRF + serveri saladus), nii et kumbki pool üksi ei pääse andmetele ligi. |

## Auditijälg

Rediacc logib 70+ erinevat sündmusetüüpi - kasutajatoimingud, süsteemimuutused, konfiguratsiooniotsustused, juurdepääsukontroli muudatused, turvalisussündmused, hargnemisteoperatsioonid, auditijäljed. Tea, et see kuulob palju, kuid audiitorid tahavad just neid näha.

- **Autentimine**: sisselogimine, väljalogimine, paroolimuutused, 2FA lubamine/keelamine, seansi tühistamine
- **Autoriseerimine**: API-tokeni loomine/tühistamine, rolli muutused, meeskonna liikmelisus
- **Konfiguratsioon**: konfiguratsioonihoidla tõukamine/tõmbamine, liikmete haldus, juurdepääsutõrked (IP-mittevastavus, SDK keelatud)
- **Litsentsimine**: hoidla litsentsi väljastamine, masina pesa jälgimine, tellimuse muutused
- **Masina toimingud**: hoidla loomine/käivitamine/peatamine/kustutamine, hargnemine, varukoopia tõukamine/tõmbamine, faili sünkroonimine, terminaliseanssid

Neid logisid saad kolmel viisil: haldusarmatuurlaud kasutaja-, meeskonna- ja kuupäevafiltreerimisega, organisatsiooniadministraatoritele portaali tegevusleht tüübi- ja kuupäevafiltreerimisega, või `rdc audit` CLI programmiliseks ekspordiks. Paiguta need oma tööriistadesse, integreeri kuhu tahad. Masina toimingud logitakse ka sinu süsteemilogidesse, nii et sul on kaitses sügavus.

## Muudatuste haldus

Hargid muudavad muudatuste halduse auditeeritavaks. Hargnedes tootmisest saad tegeoleku koopia. Testi seda. Vaata seda üle. Edenda seda või visata minema. Iga samm ajatemplega ja isikuga seotud. Just seda tahavad audiitorid näha - ei anonüümseid muudatusi.

1. Tootmishoidla hargnemine (`rdc repo fork`)
2. Muudatuste rakendamine ja testimine harul
3. Haru iseseisev valideerimine
4. Haru edendamine tootmisse (`rdc repo takeover`)

Iga samm logitakse koos ajatemplite ja toimija tuvastusega.

## Juurdepääsukontroll

- **Masina juurdepääs**: ainult SSH-võtme autentimine. Paroolipõhist SSH-d pole.
- **API-tokenid**: piiratud õigused, valikuline IP-sidumine, automaatne tühistamine meeskonnast eemaldamisel.
- **Hoidla eraldus**: igal hoidlal on oma Dockeri deemoni sokkel. Juurdepääs ühele hoidlale ei anna juurdepääsu teisele samal masinal.
- **Konfiguratsioonihoidla tokenid**: ühekordselt kasutatavad pöörlevad tokenid IP-sidumisega esimesel kasutamisel, 24-tunnise automaatse aegumisega ja 3-päringu lubamiskäivitiga samaaegsuse jaoks. Liikmete juurdepääs hallatakse X25519 võtmevahetuse kaudu kohese tühistamisega.
