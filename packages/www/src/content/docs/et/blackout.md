---
title: Panganduse järjepidevus elektrikatkestuse ajal
description: Hoia pangandusoperatsioone käigus elektrikatkestuste ajal mandritevaheline andmete peegeldamisega.
category: Use Cases
order: 6
language: et
---

> **Kui tuled kustuvad, su äri jätkub.**

**Märkus:** See on **kasutusjuhu näide**, mis demonstreerib, kuidas Rediacc saab seda probleemi lahendada. Idufirmana esindavad need stsenaariumid potentsiaalseid rakendusi, mitte lõpetatud juhtumiuuringuid.

**Kriisiskenaarium:** Massiivne elektrikatkestus mõjutas Hispaaniat ja Portugali 28. aprillil 2025, mille käivitas Prantsusmaal kahjustatud ülekandeliin. Elektrikatkestus lõhkus kriitilise IT-infrastruktuuri, mistõttu suurpangad ja tehnoloogiaettevõtted kaotasid juurdepääsu oma süsteemidele.

## Probleem

Ibeeria elektrivõrk koges katastroofilist tõrkekaskaadi:

* **Tulekahju Edela-Prantsusmaal** kahjustas kriitilist ülekandeliini
* Kahjustus põhjustas piiriüleste ühenduste **äkilise katkemise**
* Hispaania ja Portugal muutusid Euroopa elektrivõrgust **elektriliselt isoleerituks**

**Mõju ettevõtetele:**
* Andmekeskused üle Hispaania kogesid **kohest toitekatkestust**
* Varuagregaadid ei käivitunud mitmes kohas juhtimissüsteemide tõrgete tõttu
* Pangasüsteemid läksid võrguühenduseta, takistades tehinguid üle kogu riigi

**IT-infrastruktuuri väljakutsed:**
* **Kohalikud varusüsteemid** olid ebatõhusad, kuna asusid samas mõjutatud piirkonnas
* **Hädaolukorra taastamisprotseduurid** sõltusid kohalikust juurdepääsust füüsilistele serveritele
* **Ärijätkuvuse plaanid** ei arvestanud üleriigilise elektrikatkestusega, mis kestab üle 4 tunni

## Kriisi mõju

IT-teenuste katkestus viis:
* **Finantssüsteemi kokkuvarisemiseni** hinnanguliselt 4,5 miljardi euro suuruste tehinguviivitustega
* Kriitilised äriandmed muutusid kättesaamatuks 14+ tunniks
* Suuremad e-kaubanduse platvormid kogesid täielikku sulgemist
* Klienditeenindusse süsteemid ebaõnnestusid mitmes tööstusharus

## Rediacc lahendus

Suurem Hispaania pangakontsern, kes rakendas Rediacc mandritevahelist replikatsiooni, hoidis kriisi vältel operatsioone üleval:

![Panganduse järjepidevus elektrikatkestuse ajal](/img/blackout-continuity.svg)

### 1. **Mandritevaheline andmete peegeldamine**
* Põhilised pangaandmebaasid ja tehingusüsteemid **replikeeriti pidevalt** andmekeskustesse Ameerika Ühendriikides
* Kõik kliendiandmed ja tehingukirjed sünkroniseeriti **alla 3-sekundilise viivitusega**

### 2. **Sujuv operatiivne üleminek**
* Kui Hispaania serverid kaotasid toite, **suunati liiklus automaatselt ümber** USA-põhistele süsteemidele
* Kliendid kogesid ainult lühikest 47-sekundilist katkestust enne teenuste taastumist

### 3. **Kaugteenuste jätkamine**
* Kõnekeskused mõjutamata riikides pääsesid replitseeritud süsteemidele, et säilitada klienditugi
* Mobiilipanganduse rakendused jäid toimivaks, ühendudes alternatiivsete andmekeskustega

## Potentsiaalne tulemus

**Ärijätkuvus:**
* Samal ajal kui konkurendid olid 14+ tundi võrguühenduseta, hoidis pank **98% teenuste saadavust**

**Klientide usaldus:**
* Pank oli ainus suur finantsasutus, kes töötas tehinguid kriisi ajal
* Klientide rahulolu kasvas 27% kriisijärgsetes uuringutes

**Finantskaitse:**
* Pank hoidis ära ligikaudu 370 miljoni euro suurused kahjud tehingutõrgetest
* Andmeid ei kaotatud ega rikutud, kõrvaldades kulukad taastamistoimingud

**Konkurentsieelis:**
* Pank registreeris järgneva kuu jooksul 140 000 uut klienti konkurentidelt, kes ei suutnud teenust säilitada
