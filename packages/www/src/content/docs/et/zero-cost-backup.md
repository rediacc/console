---
title: "Tootmissarnased arenduskeskkonnad minutitega"
description: "Vähenda arenduskeskkonna seadistamise aega päevadelt minutitele plokitaseme deduplikatsiooniga."
category: Use Cases
order: 7
language: et
sourceHash: "2aa115fc621f5258"
sourceCommit: "4e60a12e0664cdee5ad9079a7b75e2d05980d0f5"
---

> **Vähenda keskkonna seadistamise aega päevadelt minutitele nutika deduplikatsiooni salvestusarhetektuuriga.**

**Märkus:** See on **kasutusjuhtumi näide**, mis näitab, kuidas Rediacc kiirendab arendustööd. Oleme idufirma ilma maksvate klientideta, seega käsitle seda stsenaariumina, mille jaoks oleme toote kujundanud, mitte lõpetatud juhtumiuuringuna.

## Probleem

Mehmet juhib DevOpsi e-kaubanduse ettevõttes. Tema meeskond vajab **tootmissarnaseid keskkondi** testimiseks, lavastamiseks ja arendamiseks. Põhjus on järgmine:

**Kus vana lähenemisviis laguneb:**
* Tootmissarnaste keskkondade seadistamine võtab **tunde või päevi**
* Arendajad ootavad infrastruktuuri eraldamist testimise lõpetamiseks
* Keskkondade ebajärjepidevus põhjustab "töötab minu masinal" probleeme

Arendusahelad vedasid, kuna uue keskkonna ülesseadmine võttis päevi. See kitsaskoht:

* Aeglustas **arenduse kiirust** märkimisväärselt
* Lõi sõltuvusi ja ooteaegu arenduse torujuhtmes

## Kriisi mõju

* Salvestuskulud muutusid IT-eelarve jaoks **jätkusuutmatuks**
* Varukoopia aknad ületasid saadaolevat hooldusakent
* Süsteemi jõudlus halvenes varukoopiategevuste ajal
* Andmekao risk suurenes mittetäielike varukoopiate tõttu

## Rediacc-i lahendus

Mehmet leidis Rediacc-i. Sellega:

![Varukoopia diagramm](/img/backup-optimization.svg)

### Nutikas varukoopia tehnoloogia
* **Täielikud varukoopiad näivad tehtavat**, kuid füüsiliselt salvestatakse ainult **muutunud andmed**
* Näiteks kui 10 TB andmebaasis on **keskmiselt 100 GB päevaseid muutusi**, salvestab süsteem **ainult need 100 GB**
* Varukoopiad toimivad **täielikult ja sujuvalt taastamisel**, isegi kui salvestatud ühe failina

### Peamised eelised

**1. Kulude kokkuhoid**
* Isegi 10 TB andmebaasis **100 GB** päevaste muutustega on kuu salvestuskulu piiratud **~3 TB-ga** (vanasüsteemiga oli see **~300 TB**)

**2. Toimib iga tehnoloogiapinuga**
* Rediacc ei piirdu SQL Serveriga. See töötab ühilduvalt **MySQL, PostgreSQL, MongoDB** ja kõigi teiste andmebaasidega
* Erinevate süsteemide jaoks pole vaja **eraldi oskusteavet**

**3. Kiiremad arendustsüklid, vähem riistvara**
* Varukoopia aeg väheneb **tundidelt minutitele**
* Ketta ja võrgu ressursside koormus väheneb 99,99% (sõltuvalt snapshots-ide vahel uuendatud andmete osakaalust kogumahust)

## Tulemus

Rediacciga suutis meeskond:
* Vähendada salvestuskulusid **99,99% (sõltuvalt snapshots-ide vahel uuendatud andmete osakaalust kogumahust)**
* Standardiseerida varundamis- ja taastamisprotsessid
* Katta kõik vajadused **ühe lahendusega** erinevate andmebaasisüsteemide jaoks
