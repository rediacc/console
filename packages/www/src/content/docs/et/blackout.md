---
sourceHash: "63861113cf5e7809"
sourceCommit: "b8e332b73573133a282b5c508bc049af1fbeb581"
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
* Põhilised pangaandmebaasid ja tehingusüsteemid **replikeeritaks pidevalt** andmekeskustesse Ameerika Ühendriikides
* Kliendiandmed ja tehingukirjed püsiksid sünkroonis replikatsiooniviivituse piires, mille sinu ühendus ja andmemaht võimaldavad

### 2. **Sujuv operatiivne üleminek**
* Kui Hispaania serverid kaotaksid toite, **suunataks liiklus automaatselt ümber** USA-põhistele süsteemidele
* Kliendid märkaksid vaid lühikest katkestust ümbersuunamise lõpuleviimise ajal, mitte katkestust, mis kestaks sama kaua kui elektrivõrgu rike ise

### 3. **Kaugteenuste jätkamine**
* Kõnekeskused mõjutamata riikides pääseksid replitseeritud süsteemidele ja jätkaksid klienditoe pakkumist
* Mobiilipanganduse rakendused püsiksid toimivana, ühendudes alternatiivsete andmekeskustega

## Potentsiaalne tulemus

**Ärijätkuvus:**
* Konkurendid olid võrguühenduseta üle 14 tunni. Seda arhitektuuri kasutav pank jätkaks teenindamist kogu selle aja jooksul

**Teenuse järjepidevus:**
* Pank saaks jätkata tehingute töötlemist ajal, mil teise regioonita asutused seda ei suudaks

**Finantskaitse:**
* Väldiks kahjusid, mis kogunevad iga tunniga, mil maksesüsteem on maas
* Andmeid ei kaotataks ega rikutaks, mistõttu poleks taastamistoimingut vaja
