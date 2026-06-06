---
title: "Vastavuse ülevaade"
description: "Rediacc töötab teie infrastruktuuril. Te kontrolliite oma andmeid. Kuidas see vastab peamiste vastavusraamistike nõuetele."
category: "Legal"
order: 0
language: et
sourceHash: "1e36a25c724f4185"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

Rediacc töötab täielikult teie infrastruktuuril. Keskkonna kloonimise, varundamise ja juurutamise toimingute ajal ei lahku andmed teie masinast. Teie ollete nii andmete kontrollija kui ka töötleja. Kolmandate osapoolte SaaS-teenuseid pole, välist juurdepääsu pole.

See jaotis seob Rediacc tehnilised võimalused peamiste vastavusraamistike nõuetega. Iga leht käsitleb konkreetset määrust koos viidetega ametlike õigustekstide asjakohastele artiklitele.

## Vastavusmaatriks

| Raamistik | Ulatus | Rediacc peamised võimalused |
|-----------|--------|--------------------------|
| [GDPR](/en/docs/legal-gdpr) | EL-i andmekaitse ja privaatsus | CoW kloonimine samal masinal, LUKS2 krüptimine, zero-knowledge konfiguratsioonihoidla, auditilogi, kustutamisõigus `rdc repo delete` kaudu |
| [SOC 2](/en/docs/legal-soc2) | Usaldusteenuse kriteeriumid teenuseorganisatsioonidele | Puhkeoleku krüptimine, zero-knowledge konfiguratsiooni sünkroonimine, võrgueraldus, auditijälg, varundamine ja taastamine |
| [HIPAA](/en/docs/legal-hipaa) | USA terviseteabe kaitse | LUKS2 krüptimine, zero-knowledge konfiguratsioonihoidla, ainult SSH juurdepääs, eraldatud Dockeri deemonid, edastusturvalisus |
| [CCPA](/en/docs/legal-ccpa) | California tarbijate privaatsusõigused | Isehallatav (andmemüüki/jagamist ei toimu), zero-knowledge krüptimine, krüptograafiline kustutamine, andmete inventuur hoidla kaupa |
| [ISO 27001](/en/docs/legal-iso27001) | Infoturbe halduse kontrollid | Varahaldus, krüptograafilised kontrollid, zero-knowledge konfiguratsioonihoidla, juurdepääsukontroll, operatsiooniturvalisus |
| [PCI DSS](/en/docs/legal-pci-dss) | Maksekaardi andmete kaitse | Võrgusegmenteerimine arhitektuuri tasandil, kohustuslik krüptimine, auditilogi, ulatuse vähendamine isehallatava lahenduse kaudu |
| [NIS2 ja DORA](/en/docs/legal-nis2-dora) | EL-i küberturvalisus ja finantsresilients | Tarneahela riski kõrvaldamine, resilientsi testimine CoW kloonimisega, krüptimine, intsidentide tuvastamine |
| [Andmesuveren](/en/docs/legal-data-sovereignty) | Globaalsed andmete asukohaseadused (PIPL, LGPD, KVKK, PIPA jm) | Isehallatav = andmed ei lahku kunagi teie jurisdiktsioonist. Piiriüleseid edastusi ega piisavushinnanguid ei toimu |

## Arhitektuurilised alused

Iga selles jaotises käsitletav vastavusraamistik põhineb samadel tehnilistel omadustel:

- **Puhkeoleku krüptimine**: iga hoidla on LUKS2 AES-256 krüptitud. Mandaadid talletatakse ainult operaatori kohalikus konfiguratsioonis, mitte serveris.
- **Võrgueraldus**: igal hoidlal on oma Dockeri deemon, loopback-IP-alamvõrk (/26) ja iptables-reeglid. Eri hoidlate konteinerid ei saa omavahel suhelda.
- **Kirjutamisel kopeeriv kloonimine**: `rdc repo fork` kasutab failisüsteemi reflinke (`cp --reflink=always`). Andmed dubleeritakse samal masinal ilma võrguedastuseta.
- **Auditilogi**: 70+ sündmusetüüpi, mis hõlmavad autentimist (sisselogimine, 2FA, paroolimuutused, seansi tühistamine), API-tokeni elutsüklit, konfiguratsioonihoidla toiminguid, tellimuse/litsentsimise tegevust ning CLI masina toiminguid (hoidla elutsükkel, varundamine, sünkroonimine, terminaliseanssid). Juurdepääs haldusarmatuurlaua, portaali tegevuslehe (organisatsioonipõhise filtreerimisega) ja `rdc audit` CLI kaudu. Masina toimingud salvestatakse ka teie süsteemilogidesse kaitsesügavuse eesmärgil.
- **Krüpteeritud varundamine**: `rdc repo push/pull` edastab andmeid üle SSH. Varukoopia sihtkoht saab LUKS-krüpteeritud mahud.
- **Zero-knowledge konfiguratsioonihoidla**: valikuline krüpteeritud konfiguratsiooni sünkroonimine seadmete vahel. Konfiguratsioonid krüpteeritakse kliendipoolselt AES-256-GCM-iga enne üleslaadimist. Server salvestab ainult läbipaistmatuid plokke. Server ei saa lugeda SSH-võtmeid, mandaate, IP-aadresse ega ühtegi konfiguratsioonitekstiandmet. Võtme tuletamine kasutab pääsvõtme PRF-laiendust koos HKDF-iga ja domeenieraldusega. Liikmete juurdepääsu haldab X25519 võtmevahetus ning tühistamine on kohene.

Nende võimaluste kohta vt [Arhitektuur](/en/docs/architecture), [Hoidlad](/en/docs/repositories), [Konfiguratsioonihoidla](/en/docs/config-storage) ja [Konto turvalisus](/en/docs/account-security).

## Miks see on oluline

Vastavusrikkumised on väga kulukad. Järgmised juhtumid näitavad probleeme, mida Rediacc arhitektuur struktuuriliselt ennetab:

| Juhtum | Trahv | Mis läks valesti |
|--------|-------|----------------|
| [Meta: EL-USA andmeedastused](https://www.dataprotection.ie/en/news-media/press-releases/Data-Protection-Commission-announces-conclusion-of-inquiry-into-Meta-Ireland) | 1,2 mld EUR | Isikuandmeid edastati piiriüleselt ilma piisavate kaitsemeetmeteta. Isehallatav lahendus tähendab, et edastust ei toimu. |
| [Equifax: krüpteerimata andmed](https://www.ftc.gov/news-events/news/press-releases/2019/07/equifax-pay-575-million-part-settlement-ftc-cfpb-states-related-2017-data-breach) | 700 mln $ | 147 miljonit kirjet talletati krüpteerimata koos nõrga võrgusegmenteerimisega. LUKS2 on kohustuslik, mitte valikuline. |
| [Target: külgsuunaline liikumine](https://oag.ca.gov/news/press-releases/attorney-general-becerra-target-settles-record-185-million-credit-card-data) | 18,5 mln $ | Ründajad liikusid HVAC-tarnija kaudu maksesüsteemidesse läbi tasase võrgu. Hoidlapõhine eraldus ennetab seda. |
| [Anthem: krüpteerimata PHI](https://www.hhs.gov/hipaa/for-professionals/compliance-enforcement/agreements/anthem/index.html) | 16 mln $ | 79 miljonit terviseandmete kirjet talletati ilma krüptimiseta. LUKS2 AES-256 on alati sisse lülitatud. |
| [Blackbaud: SaaS-rikkumise kaskaad](https://www.sec.gov/newsroom/press-releases/2023-48) | 49,5 mln $ | Lunavara ühes SaaS-tarnijas paljastas andmeid 13 000+ kliendiorganisatsioonist. Isehallatav lahendus tähendab, et tarnija rikkumine ei saa jõuda teie andmeteni. |
| [British Airways: nõrk segmenteerimine](https://www.edpb.europa.eu/news/national-news/2019/ico-statement-intention-fine-british-airways-ps18339m-under-gdpr-data_en) | 20 mln GBP | Ründajad süstisid pahatahtliku koodi ebapiisavate võrgukontrollide tõttu. Eraldatud Dockeri deemonid ja iptables ennetavad külgsuunalist juurdepääsu. |
| [Google: kustutamisõigus](https://www.edpb.europa.eu/news/national-news/2019/cnils-restricted-committee-imposes-financial-penalty-50-million-euros_en) | 50 mln EUR | Raskused andmete täielikul kustutamisel hajutatud süsteemides. Krüptograafiline kustutamine LUKS-i hävitamise kaudu on kohene ja täielik. |

## Oluline teadaanne

Need lehed kirjeldavad, kuidas Rediacc arhitektuur vastavusnõuetega ühtib. Kuid tegelikkus on selline: vastavus on rohkem kui tarkvara. Te vajate poliitikaid, protseduure, koolitust ja tõenäoliselt kolmanda osapoole auditeid. Rediacc käsitleb infrastruktuuri osa. Ülejäänud osaga töötage koos oma juriidilise ja vastavusmeeskonnaga.
