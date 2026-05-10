---
title: "SOC 2 vastavus"
description: "Kuidas Rediacc vastab SOC 2 usaldusteenuse kriteeriumitele turvalisuse, kättesaadavuse ja konfidentsiaalsuse osas."
category: "Legal"
order: 2
language: et
---

SOC 2 (System and Organization Controls 2) on Ameerika sertifitseeritud avalike raamatupidajate instituudi (AICPA) välja töötatud raamistik organisatsiooni kontrollide hindamiseks seoses turvalisuse, kättesaadavuse, töötlemise terviklikkuse, konfidentsiaalsuse ja privaatsusega.

Viide: [AICPA SOC 2](https://www.aicpa-cima.com/topic/audit-assurance/audit-and-assurance-greater-than-soc-2)

## Usaldusteenuse kriteeriumite vastavusmaatriks

| Usaldusprintsiip | Kriteerium | Rediacc võimalus |
|----------------|----------|-------------------|
| **Turvalisus** (CC6) | Loogilised juurdepääsukontrollid, krüptimine | LUKS2 AES-256 puhkeoleku krüptimine. Mandaadid talletatakse ainult operaatori kohalikus konfiguratsioonis (`~/.config/rediacc/`), mitte serveris. SSH-võtmepõhine juurdepääs. Eraldatud Dockeri deemonid hoidla kohta. |
| **Kättesaadavus** (A1) | Süsteemi taastamine ja resilients | `rdc repo backup push/pull` krüptitud väliskoopiatega SSH, S3, B2, Azure või GDrive'i. CoW-hetktõmmised koheseks tagasipöördumiseks. Hargnemispõhised uuendused nullilähedase seisakuajaga muutuste jaoks. |
| **Töötlemise terviklikkus** (PI1) | Täpne ja täielik töötlemine | Deterministlikud Rediaccfile elutsükli haagid (`up`/`down`) tagavad järjepidevad juurutused. `rdc repo validate` kontrollib hoidla terviklikkust ja varukoopia seisundit pärast ootamatuid seisakuid või varundamistoiminguid. |
| **Konfidentsiaalsus** (C1) | Andmete kaitse volitamata juurdepääsu eest | Hoidlapõhine krüptimine unikaalsete LUKS-mandaatidega. Võrgueraldus iptablesi, eraldi Dockeri deemonite ja loopback-IP-alamvõrkude kaudu. Eri hoidlate konteinerid ei näe üksteist. Zero-knowledge konfiguratsioonihoidla krüpteerib konfiguratsioonid kliendipoolselt enne üleslaadimist. Server talletab ainult läbipaistmatuid plokke, mida ta ei saa dekrüpteerida. |
| **Privaatsus** (P1-P8) | Isikuandmete käitlemine | Isehallatav: toimingute ajal andmeid välja ei kanta. Auditijälg kogu andmetele juurdepääsu kohta. Krüptimisvõtmete haldus on kliendi kontrolli all. Konfiguratsioonihoidla kasutab jagatud võtme tuletamist (pääsvõtme PRF + serveri saladus), nii et kumbki pool üksi ei pääse andmetele ligi. |

## Auditijälg

Rediacc logib 70+ sündmusetüüpi, sealhulgas:

- **Autentimine**: sisselogimine, väljalogimine, paroolimuutused, 2FA lubamine/keelamine, seansi tühistamine
- **Autoriseerimine**: API-tokeni loomine/tühistamine, rolli muutused, meeskonna liikmelisus
- **Konfiguratsioon**: konfiguratsioonihoidla tõukamine/tõmbamine, liikmete haldus, juurdepääsutõrked (IP-mittevastavus, SDK keelatud)
- **Litsentsimine**: hoidla litsentsi väljastamine, masina pesa jälgimine, tellimuse muutused
- **Masina toimingud**: hoidla loomine/käivitamine/peatamine/kustutamine, hargnemine, varukoopia tõukamine/tõmbamine, faili sünkroonimine, terminaliseanssid

Need logid on kättesaadavad haldusarmatuurlaua kaudu (filtreerimisega kasutaja, meeskonna ja kuupäeva järgi), portaali tegevuslehe kaudu (organisatsioonipõhise tüübi ja kuupäeva filtreerimisega organisatsiooni administraatoritele) ning `rdc audit` CLI kaudu programmiliseks ekspordiks. Masina toimingud salvestatakse ka teie süsteemilogidesse kaitsesügavuse eesmärgil.

## Muudatuste haldus

Hargnemispõhine töövoog toetab kontrollitud muudatuste haldust:

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
