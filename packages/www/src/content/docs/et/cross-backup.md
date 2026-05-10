---
title: Ristvarundusstrateegia
description: Kaitske andmeid katastroofide eest tõhusa mandritevahelise varunduse ja kiire taastamisega.
category: Use Cases
order: 5
language: et
---

> **Kui katastroof tabab, kas teie andmed jäävad ellu? Rediacciga jäävad alati.**

**Märkus:** See on **kasutusjuhtumi näide**, mis demonstreerib, kuidas Rediacc suudab seda probleemi lahendada. Idufirmana esindavad need stsenaariumid potentsiaalseid rakendusi, mitte lõpetatud juhtumiuuringuid.

**Kriisiolukord:** Pärast kliendikõnet selgus, et teenused ei tööta **ketta rikke** tõttu. Kaugvarundusserveri viimane varukoopia oli **3 nädalat vana**, mis põhjustas olulise andmekao.

## Probleem

Organisatsioon saab teadlikuks andmete varundamise riskidest **ainult samal masinal**:
* Riistvara rikked
* Küberrünnakud
* Füüsilised katastroofid nagu sõda, maavärin, tulekahju, üleujutus
* Ebapiisav kaitse andmekao vastu

**Lahenduse otsimine:**
* Otsustatakse varundada 20 TB andmeid **kaugserverisse**
* Traditsiooniliste meetoditega võtab see varukoopia aga **2 nädalat** ja kasutab ära **99,99% (sõltuvalt muudatuste osakaalust koguandmetes hetktõmmiste vahel)** ribalaiusest

## Kriisi mõju

Pärast kliendikõnet:
* Märgatakse, et **teenused ei tööta**
* Tuvastatakse **ketta rike**
* Kaugvarundusserverit kontrollides selgub, et **viimane varukoopia tehti 3 nädalat tagasi**

**Tagajärjed:**
* Ketta käsitsi taastamise katsed **ebaõnnestuvad**
* 3-nädalase andmekao tõttu **tühistatakse kliendilepingud**
* Organisatsiooni **maine saab tõsiselt kahjustada**

## Rediacci lahendus

![Ristvarundusstrateegia](/img/cross-backup.svg)

### 1. **Esmane varukoopia**
* Esimesel korral võtab 20 TB andmete ülekanne kaugserverisse 2 nädalat

### 2. **Tunniajased ristivarukoopiad**
* Iga tund luuakse täieliku varukoopia mulje, kuid edastatakse **ainult muutunud andmed**

### 3. **Ettevalmistus katastroofistsenaariumiteks**
* Andmeid saab varundada isegi **mandritevahelist** serveritesse
* Isegi kui peamine masin jookseb kokku, **aktiveeritakse** kuni 1 tund tagasi pärinevad andmed **minutitega**

## Tulemus

**Aja kokkuhoid:**
* Varundusaeg vähenes **2 nädalalt keskmiselt 4 minutile**
* Andmekao risk vähenes **1 tunnini**

**Kulude optimeerimine:**
* Ribalaiuse tarbimine vähenes **98%**

**Katkematu ärijätkuvus:**
* Kui peamine server kokku jooksis, aktiveeriti kaugvarukoopia **7 minutiga**
