---
title: Ristivarunduse strateegia
description: "Teie varukoopia ei toimi hetkel, kui tema masin rikki läheb. Rediacc kopeerib hetktõmmised eraldi masinasse, et ühe ketta rike ei võtaks kaasa kõike."
category: Use Cases
order: 5
language: et
sourceHash: "39dbeac1faec121c"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

> **Kui katastroof tabab, kas teie andmed jäävad ellu? Rediacciga jäävad alati.**

**Märkus:** See on **kasutusjuhtumi näide**, mis näitab, kuidas Rediacc suudab seda probleemi lahendada. Need stsenaariumid esindavad potentsiaalseid rakendusi, mitte lõpetatud juhtumiuuringuid.

**Kriisiolukord:** Kliendikõne paljastab katkestuse: **ketta rike**. Kaugvarundusserveri viimane varukoopia oli **3 nädalat vana**. Kolm nädalat andmeid on kadunud.

## Probleem

Andmete varundamine samale masinale, millel nad asuvad, ei ole strateegia. Siin on, mida see rike tõestab:
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

![Ristivarunduse strateegia](/img/cross-backup.svg)

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
