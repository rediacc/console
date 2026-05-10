---
title: Dünaamiline ressursside skaleerimine
description: Ehitage piiramatu paindlikkusega pilvearenhitektuur tehisintellekti treenimise ja dünaamiliste töökoormuste jaoks.
category: Use Cases
order: 1
language: et
---

> **Kas teie pilvearenhitektuur on jäik? Ehitage piiramatu paindlikkusega.**

**Märkus:** See on **kasutusjuhtumi näide**, mis demonstreerib, kuidas Rediacc suudab seda probleemi lahendada. Idufirmana esindavad need stsenaariumid potentsiaalseid rakendusi, mitte lõpetatud juhtumiuuringuid.

**Kriisiolukord:** Tehisintellekti treenimisajad **pikenesid 2-3 korda**, põhjustades projekti viivitusi. Insenerid kogesid olulist tootlikkuse langust ressursside ootamise ajal, ähvardades organisatsiooni konkurentsieelist.

## Probleem

Organisatsiooni tarkvarainsenerid kogevad jõudlusprobleeme **kohapealsete** serveritega, mida kasutatakse **tehisintellekti mudelite treenimiseks**:
* **Tööajal** (08:00-17:00) jõuavad serveri päringud 99% läbilaskevõimeni
* Suurt töötlusvõimsust nõudev treenimine põhjustab riistvara **ebapiisavuse**

**Lahenduse otsimine:**
* Serveri uuenduse kulu ei peeta sobivaks **6-7-tunnise igapäevase kasutuse** tõttu
* Kuigi pilvemigratsiooni kaalutakse, on takistusteks **andmeedastuse kulu** ja **sünkroniseerimisraskused**

## Kriisi mõju

* Tehisintellekti treenimisajad **pikenevad 2-3 korda**, projektid hilinevad
* Insenerid kogevad **tootlikkuse langust** ressursside ootamise ajal
* Organisatsioon seisab silmitsi riskiga **järk-järgult kaotada konkurentsieelist**

## Rediacci lahendus

Süsteemiinsener Yüksel arendab **hübriidmudeli** koos Rediacciga:

![Hübriidpilve skaleerimine](/img/hybrid-cloud-scaling.svg)

### 1. **Kohene pilverändamine**
* Tööajal kloonitakse kohapealsed teenused pilve **koos kõigi andmete ja konfiguratsioonidega**
* 100 TB andmeid sünkroniseeritakse 9 minutiga, edastades **ainult muutunud osad** tänu Rediaccile

### 2. **Dünaamiline skaleerimine**
* Pilvekeskkonnas olevaid servereid renditakse **nii palju kui vaja tehisintellekti treenimiseks**
* Töötlusvõimsust saab **suurendada 10 korda** vastavalt nõudlusele

### 3. **Öine sünkroniseerimine**
* Tööpäeva lõpus **tõmmatakse kõik pilves tehtud muudatused** automaatselt kohapealsesse keskkonda
* Öösel töötavad insenerid jätkavad tööd **ajakohaste andmetega**

## Tulemus

**Kulude eelis:**
* **Pilveressursside tunnipõhise rentimise** teel vähenes kuukulu **60%**
* Vajadus kohapealsete serverite uuendamiseks **kadus**

**Jõudluse kasv:**
* Tehisintellekti treenimisajad vähenesid **8 tunnilt 1,5 tunnini**
* Inseneride tootlikkus kasvas **40%**

**Paindlik töötamine:**
* **Andmete järjepidevus** pilve ja kohapealsete keskkondade vahel tagati sujuvalt
* Öise vahetuse meeskondadel **oli kohene ligipääs ajakohastele andmetele**
