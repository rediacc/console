---
title: "Andmesuveräänsus"
description: "Kuidas Rediacc'i ise majutatud arhitektuur rahuldab andmete elukoha ja suveräänsuse nõuded ülemaailmsetes jurisdiktsioonides."
category: "Legal"
order: 7
language: et
---

Paljud riigid nõuavad, et nende kodanike isikuandmeid hoitaks ja töödeldaks riigipiiride sees. Rediacc'i ise majutatud arhitektuur rahuldab need nõuded disaini tasandil: andmed jäävad teie masinasse, teie andmekeskusesse, teie jurisdiktsiooni. Kloonimisel ei lahku ükski andmehulk masinast ning ükski kolmanda osapoole SaaS-teenus ei töötle teie andmeid.

## Miks ise majutamine lahendab andmesuveräänsuse probleemi

Piiriülene andmeedastus on pilvandmetöötluse kõige raskem vastavusprobleem. Igal jurisdiktsioonil on erinevad reeglid, adekvaatsuse otsused ja ülekandmismehhanismid. Ise majutamine kõrvaldab selle probleemikategooria täielikult:

- **Piiriülest ülekannet ei toimu**: CoW-kloonimine (`cp --reflink=always`) dubleerib andmed samal masinal
- **Kolmanda osapoole töötlejat ei ole**: Rediacc töötab teie infrastruktuuril, mitte Rediacc'i serveritel
- **Adekvaatsuse hindamist pole vaja**: andmed ei lahku kunagi jurisdiktsioonist, seega ülekandereeglit ei kohaldata
- **Standardseid lepingutingimusi pole vaja**: rahvusvahelist andmevoogu, mida reguleerida, ei ole

## Jurisdiktsioonide katvus

### Euroopa Liit

[GDPR](https://gdpr-info.eu/) piirab isikuandmete edastamist väljapoole EL-i/EMM-i, kui sihtkohariik ei taga piisavat kaitset. Maailma tähelepanu köitnud Schrems II otsus tühistas EL-i ja USA vahelise Privacy Shieldi ning [Meta vastu määratud 1,2 miljardit eurot trahvi](https://www.dataprotection.ie/en/news-media/press-releases/Data-Protection-Commission-announces-conclusion-of-inquiry-into-Meta-Ireland) näitas, mis maksab vale piiriülene andmeedastus.

EL-is paigaldatud ise majutatud Rediacc hoiab kõik andmed EL-is. Ülekandemehhanism pole vajalik. Artiklitasandi kaardistuse kohta vaadake [GDPR-i vastavust](/en/docs/legal-gdpr).

### Hiina

[Isikuandmete kaitse seadus (PIPL)](http://www.npc.gov.cn/npc/c30834/202108/a8c4e3672c74491a80b53a172bb753fe.shtml) nõuab, et Hiina kodanike isikuandmeid hoitaks Hiinas. Piiriülene andmeedastus nõuab Hiina küberruumi haldamise ameti (CAC) turvalisushindamist. Rediacc'i ise majutamine Hiina infrastruktuuril väldib CAC-i turvahindamisi täielikult.

### Brasiilia

[Lei Geral de Proteção de Dados (LGPD)](https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm) nõuab piisavaid turvameetmeid ja piirab rahvusvahelisi ülekandeid. Ise majutamine Brasiilias kõrvaldab ülekande murekohad ning rahuldab Art. 46 tehniliste meetmete nõude LUKS2 krüptimise ja võrgueralduse kaudu.

### India

[Digitaalse isikuandmete kaitse seadus (DPDP Act, 2023)](https://www.meity.gov.in/content/digital-personal-data-protection-act-2023) piirab andmete edastamist riikidesse, mis ei kuulu valitsuse kinnitatud nimekirja. Ise majutamine India infrastruktuuril tähendab, et ülekandeid ei toimu sõltumata sellest, millised riigid musta nimekirja satuvad. India valitsuse ja kaitsesektori asutused eelistavad tugevalt kohapealseid lahendusi.

### Türkiye

[KVKK (seadus nr 6698)](https://kvkk.gov.tr/en/) piirab rahvusvahelisi ülekandeid keerukate adekvaatsuse nõuetega. Türkiye ei kuulu EL-i adekvaatsusloendisse, seega nõuavad piiriülesed ülekanded selgesõnalist heakskiitu. Ise majutamine Türkiye's kõrvaldab selle vajaduse täielikult.

### Lõuna-Korea

[Isikuandmete kaitse seadus (PIPA)](https://www.pipc.go.kr/eng/index.do) on üks maailma rangemaid ning nõuab sõnaselgelt isikuandmete krüptimist nii salvestamisel kui edastamisel. LUKS2 AES-256 rahuldab selle nõude otseselt. Trahvid ulatuvad kuni 3% käibest.

### Jaapan

[Isikuandmete kaitse seadus (APPI)](https://www.ppc.go.jp/en/legal/) piirab piiriüleseid ülekandeid, kui sihtriik ei taga piisavat kaitset. Ise majutamine Jaapanis väldib ülekandepiirangutest ning on kooskõlas turu kultuurilise eelistusega kohapealsete lahenduste osas.

### Austraalia

[Privacy Act 1988](https://www.legislation.gov.au/C2004A03712/latest/text) teeb avalikustava üksuse vastutavaks välisriigi andmesaaja andmekäitluse eest (APP 8). Ise majutamine kõrvaldab selle vastutuse täielikult. LUKS2 krüptimine ja võrgueraldus pakuvad konkreetseid "mõistlikke samme" APP 11 alusel.

### Araabia Ühendemiraadid

[Föderaalne dekreetseadus nr 45/2021](https://u.ae/en/about-the-uae/digital-uae/data/data-protection-laws) nõuab piisavaid turvameetmeid ja piirab piiriüleseid ülekandeid. AÜE valitsuse ja finantssektori asutused eelistavad tugevalt kohapealseid lahendusi.

### Saudi Araabia

[Isikuandmete kaitse seadus (PDPL)](https://sdaia.gov.sa/en/SDAIA/about/Documents/Personal%20Data%20English%20V2.pdf) nõuab, et Saudi Araabia elanike isikuandmeid hoitaks ja töödeldaks Saudi Araabias. Ise majutamine rahuldab selle range lokaliseerimise nõude otseselt.

### Singapur

[Isikuandmete kaitse seadus (PDPA)](https://sso.agc.gov.sg/Act/PDPA2012) nõuab mõistlikku turvalisust ja piirab piiriüleseid ülekandeid. Ise majutamine Singapuris, mis on oluline APAC-i andmekeskus, rahuldab ASEAN-i piirkondliku vastavuse nõuded.

### Venemaa

[Föderaalseadus 242-FZ](https://pd.rkn.gov.ru/) nõuab, et Venemaa kodanike isikuandmeid hoitaks Venemaal asuvatel serveritel. Rikkumised võivad kaasa tuua veebisaidi blokeerimise. Ise majutamine Venemaa pinnasel tagab vastavuse arhitektuuri tasandil.

## Muster

Kõigis jurisdiktsioonides on vastavusvõrrand sama:

| Omadus | Pilv/SaaS | Ise majutatud Rediacc |
|----------|-----------|-------------------|
| Andmete asukoht | Teenusepakkuja andmekeskused (võivad ületada piire) | Teie masin, teie jurisdiktsioon |
| Ülekandemehhanism vajalik | Jah (SCCd, adekvaatsus, nõusolek) | Ei (ülekannet ei toimu) |
| Kolmanda osapoole töötleja vastutus | Jah | Ei |
| Krüptimise kontroll | Teenusepakkuja hallatavad võtmed | Teie LUKS-i volitused, lokaalselt salvestatud |
| Kloonimine/lavastuse andmed | Võivad ületada piire või väljuda teie kontrolli alt | CoW samal masinal, samas jurisdiktsioonis |

## Majutatud teenus: piirkondlik andmete elukoht

Rediacc'i majutatud teenuse kasutajatele (mitte ise majutatavatele) tagatakse andmete elukoht piirkondliku infrastruktuuri kaudu. Saadaval on kolm piirkonda: EL (Frankfurt), USA (Virginia) ja Aasia-Vaikne ookean (Tokyo). Iga piirkond töötab sõltumatute andmebaaside ja salvestusega, piirkonnaüleseid andmevooge ei toimu. Tehingulist e-posti edastatakse AWS SES-i kaudu; EL ja USA kasutavad spetsiaalseid piirkondlikke lõpp-punkte, Aasia-Vaikse ookeani piirkond kasutab EL-i lõpp-punkti (eu-central-1). EL-i piirkond kasutab R2-salvestuse puhul jurisdiktsioonilist täitmist. Täieliku tehnilise ülevaate saamiseks vaadake [Andmepiirkondi](/en/docs/data-regions).
