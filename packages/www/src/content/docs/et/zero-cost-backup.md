---
title: Kiirendatud arendustoimingud
description: Vähenda keskkonna seadistamise aega päevadelt minutitele nutika deduplikatsiooni salvestusarhetektuuriga.
category: Use Cases
order: 7
language: et
---

> **Vähenda keskkonna seadistamise aega päevadelt minutitele nutika deduplikatsiooni salvestusarhitektuuriga.**

**Märkus:** See on **kasutusjuhtumi näide**, mis demonstreerib, kuidas Rediacc-i AI-käitatavate toimingute jaoks loodud infrastruktuuri automatiseerimise platvorm saab arendust kiirendada. Idufirmana esindavad need stsenaariumid potentsiaalseid rakendusi, mitte lõpetatud juhtumiuuringuid.

## Probleem

Mehmet töötab DevOpsi insenerina e-kaubanduse organisatsioonis. Arendusmeeskond vajab **tootmissarnaseid keskkondi** testimiseks, lavastamiseks ja arendamiseks. Põhjus on järgmine:

**Traditsioonilised keskkonna väljakutsed:**
* Tootmissarnaste keskkondade seadistamine võtab **tunde või päevi**
* Arendajad ootavad infrastruktuuri eraldamist testimise lõpetamiseks
* Keskkondade ebajärjepidevus põhjustab "töötab minu masinal" probleeme

Organisatsioon vaevles aeglaste arendustsüklitega, kuna keskkonna eraldamine oli kitsaskoht. See olukord:

* Aeglustas **arenduse kiirust** märkimisväärselt
* Lõi sõltuvusi ja ooteaegu arenduse torujuhtmes

## Kriisi mõju

* Salvestuskulud muutusid IT-eelarve jaoks **jätkusuutmatuks**
* Varukoopia aknad ületasid saadaolevat hooldusakent
* Süsteemi jõudlus halvenes varukoopiategevuste ajal
* Andmekao risk suurenes mittetäielike varukoopiate tõttu

## Rediacc-i lahendus

Mehmet avastas Rediacc-i ja selle süsteemiga:

![Varukoopia diagramm](/img/backup-optimization.svg)

### Nutikas varukoopia tehnoloogia
* **Täielikud varukoopiad näivad tehtavat**, kuid füüsiliselt salvestatakse ainult **muutunud andmed**
* Näiteks kui 10 TB andmebaasis on **keskmiselt 100 GB päevaseid muutusi**, salvestab süsteem **ainult need 100 GB**
* Varukoopiad toimivad **täielikult ja sujuvalt taastamisel**, isegi kui salvestatud ühe failina

### Peamised eelised

**1. Kulude kokkuhoid**
* Isegi 10 TB andmebaasis **100 GB** päevaste muutustega on kuu salvestuskulu piiratud **~3 TB-ga** (vanasüsteemiga oli see **~300 TB**)

**2. Universaalne tugi**
* Rediacc ei piirdu SQL Serveriga. See töötab ühilduvalt **MySQL, PostgreSQL, MongoDB** ja kõigi teiste andmebaasidega
* Erinevate süsteemide jaoks pole vaja **eraldi oskusteavet**

**3. Aja ja ressursside tõhusus**
* Varukoopia aeg väheneb **tundidelt minutitele**
* Ketta ja võrgu ressursside koormus väheneb 99,99% (sõltuvalt snapshots-ide vahel uuendatud andmete osakaalust kogumahust)

## Tulemus

Tänu Rediaccile suutis organisatsioon:
* Vähendada salvestuskulusid **99,99% (sõltuvalt snapshots-ide vahel uuendatud andmete osakaalust kogumahust)**
* Standardiseerida varundamis- ja taastamisprotsessid
* Katta kõik vajadused **ühe lahendusega** erinevate andmebaasisüsteemide jaoks
