---
title: Ajarändel põhinev taastamine
description: Taasta nädala tagasi kogemata kustutatud andmed hetktõmmisepõhise ajarände abil.
category: Use Cases
order: 2
language: et
---

> **Kui teised kaotavad andmed igaveseks, saad sina ajas tagasi rännata.**

**Märkus:** See on **kasutusjuhtumi näide**, mis demonstreerib, kuidas Rediacc suudab seda probleemi lahendada. Idufirmana kujutavad need stsenaariumid potentsiaalseid rakendusvõimalusi, mitte lõpetatud juhtumiuuringuid.

**Kriisistsenaarium:** Äsja tööle võetud töötaja **kustutas kogemata** kriitilised andmed otseandmebaasist 3 nädalat tagasi. Organisatsiooni varunduslahendus hoidis varukoopiad alles vaid 2 nädalat, muutes andmete taastamise tavapärasel teel peaaegu võimatuks.

## Probleem

Mehmet on süsteemiekspert, kes vastutab suure veebipoe organisatsiooni andmebaasi eest. Ühel hommikul, klientide kaebustele reageerides, märkab ta, et mõned varasemad tellimuste kirjed **ei ole süsteemis nähtavad**. Uurimine paljastab, et äsja tööle võetud töötaja **kustutas kogemata** mõned kriitilised andmed otseandmebaasist 3 nädalat tagasi, **ühendudes otseandmebaasiga testikeskkonna asemel**.

**Olemasolev varundussüsteem:**
* Täisvarukoopiad tehakse kord nädalas
* **Inkrementaalsed varukoopiad** salvestatakse iga päev

**Dilemma:** Kustutamine toimus **enne täisvarukoopiate kuupäeva**, seega pole kadunud andmeid varukoopiates. Igapäevased varukoopiad **salvestavad ainult uusimad andmed**, seega **kustutatud kirjeid ei saa taastada**.

## Kriisi mõju

Kadunud andmete tõttu:
* Kliendid **ei saa hüvitistaotlusi töödelda**
* Maksesüsteemis tekivad ebajärjepidevused
* Kaebused levivad kiiresti sotsiaalmeedias

**Tulemused:**
* Klienditeenindusmeeskond on **tugeva surve all**
* Organisatsiooni maine **kahjustub kiiresti**
* Käsitsi andmete taastamine saavutab **ainult 15% edu**

**Lisakomistuskivi:**
* Salvestuskulude vähendamiseks hoiab organisatsioon alles **ainult viimase 2 nädala varukoopiad**
* Kustutatud andmed ei ole **hiljutistes varukoopiates**

## Rediacc lahendus

Mehmet pakub Rediacciga "ajamasina"-laadse lahenduse:

![Time Travel Recovery](/img/time-travel-recovery.svg)

### 1. **Hetktõmmised**
* Rediacc teeb süsteemist automaatselt hetktõmmiseid iga tund
* Need hetktõmmised katavad ka hetki vahetult enne andmete kustutamist

### 2. **Ajas tagasi minek**
* Mehmet valib Rediacc liideses kuupäeva ja kellaaja, mil kustutamine toimus
* Taastab 3 nädala taguse süsteemi hetktõmmise uuele eksemplarile 1 minutiga

### 3. **Täielik taastamine**
* Kadunud andmed taastatakse täielikult ja järjepidevalt

## Tulemus

* Organisatsiooni maine taastati **24 tunni jooksul**
* Rahaline kahju hoiti ära **95% ulatuses**
* Rediacc tõestas, et sagedasi varukoopiad saab teha **salvestuskulusid suurendamata**
