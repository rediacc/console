---
title: Päranddandmebaasi skaleerimine
description: Skaleerige päranddandmebaase ilma andmeid migreerida, kasutades reaalajas andmereplikatsiooni ja päringujaotust.
category: Use Cases
order: 3
language: et
---

> **Teie päranddandmebaas pidurdab teid. Vabanege sellest, ilma seda lõhkumata.**

**Märkus:** See on **kasutusnäide**, mis demonstreerib, kuidas Rediacc seda probleemi lahendada saab. Idufirmana esindavad need stsenaariumid potentsiaalseid rakendusi, mitte lõpetatud juhtumiuuringuid.

**Kriisistsenaarium:** Vaatamata serverite kümnekordisele skaleerimisele Kubernetesiga paranes jõudlus vaid kaks korda. Kliendid kaeblesid aeglaste päringute üle, kulud kasvasid rahuldamatute tulemustega ning maine oli ohus.

## Probleem

Organisatsiooni teenused pilvekeskkonnas **ei suutnud päringutele vastata**. Lahendusena tegi tarkvarameeskond järgmist:
* Viis läbi **horisontaalse skaleerimise Kubernetesiga** ja **suurendas serverite arvu kümme korda**
* Jõudlus paranes siiski **vaid kaks korda**

**Kitsaskoha tuvastamine:**
* Selgus, et probleemi allikas on **päranddandmebaas, mida ei saa skaleerida**
* Andmebaas ei suutnud töötada hajusalt nagu kaasaegsed arhitektuurid

**Dilemma:**
* Kaasaegsele andmebaasile migreerimine **võis võtta aastaid** -- see nõudis koodi ümberkirjutamist, andmete migreerimist ja testimisprotsesse
* Kulu ja ajakadu olid vastuvõetamatud

## Kriisi mõju

* Kliendid kaeblevad **aeglaste päringute** tõttu
* Serverikulud kasvavad, kuid **jõudlus ei ole rahuldav**
* **Maine kaotuse** oht kasvab konkurentsitihedas turul

## Rediacc'i lahendus

Süsteemiinsener Yüksel kasutas Rediacc'i ristvarukoopia funktsiooni:

![Legacy DB Scaling](/img/legacy-scaling.svg)

### 1. **Reaalajas andmereplikatsioon**
* Muudatused päranddandmebaasis edastati teistele serveritele **10--15-minutiliste intervallidega**
* Sünkrooniti **ainult muutunud andmed** -- **ribalaius vähenes 95%**

### 2. **Päringujaotus**
* Lugemispäringud **jagati mitme masina vahel**
* Kirjutamisoperatsioonid jäid **põhiandmebaasi**, et tagada järjepidevus

### 3. **Tasuta skaleerimine**
* Pärandsüsteemi toetati lisaserveritega **ilma seda muutmata**
* Uut riistvara pole vaja osta -- **pilvservereid renditi tunni kaupa** kulude optimeerimiseks

## Tulemus

**Jõudluse kasv:**
* Päringute aeg lühenes **55 sekundilt 7 sekundini**
* Süsteemi maht kasvas **8 korda**

**Kulude kontroll:**
* Säästud pärandsüsteemi ümberkirjutamata jätmisest -- **rahalised vahendid säilisid**

**Ajasääst:**
* Lahendus juurutati **3 nädala jooksul**
* Kliendikaebus lahendati **99,99% ulatuses (sõltuvalt hetktõmmiste vahelise kogu andmemahu uuendussuhtest)**
