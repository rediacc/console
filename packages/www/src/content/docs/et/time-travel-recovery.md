---
title: Ajarändel põhinev taastamine
description: "Taasta nädala tagasi kustutatud andmed btrfs hetktõmmiste abil, isegi kui tavapärased varukoopiad on sellest ajast juba edasi liikunud."
category: Use Cases
order: 2
language: et
sourceHash: "e55d51b8df91b20f"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

> **Kui teised kaotavad andmed igaveseks, saad sina ajas tagasi rännata.**

**Märkus:** See on **kasutusjuhtumi näide**, mis näitab, kuidas Rediacc seda tüüpi probleeme lahendab. Oleme idufirma. Need on realistlikud stsenaariumid, mille jaoks toode on loodud, mitte klientide juhtumiuuringud, mida oleme juba ellu viinud.

**Kriisistsenaarium:** Uus töötaja **kustutas kogemata** kriitilised read otseandmebaasist 3 nädalat tagasi. Varundussüsteem hoiab alles ainult 2 nädala ajalugu. Tavapärases seadistuses on need andmed kadunud.

## Probleem

Mehmet haldab suure e-kaubanduse platvormi andmebaasi. Ühel hommikul hakkavad kliendid kaebama, et varasemad tellimuste kirjed **ei ole enam nähtavad**. Ta uurib asja. Äsja tööle võetud insener oli **kogemata kustutanud** kriitilised read otseandmebaasist 3 nädalat tagasi, **ühendudes otseandmebaasiga testikeskkonna asemel**. Klassikaline viga, mida iga andmebaasiadministraator on kas ise teinud või nooremalt töötajalt näinud.

**Olemasolev varundussüsteem:**
* Täisvarukoopiad tehakse kord nädalas
* **Inkrementaalsed varukoopiad** salvestatakse iga päev

**Dilemma:** kustutamine toimus **enne täisvarukoopiate kuupäeva**, seega pole kadunud andmeid üheski varukoopiafailis. Igapäevased varukoopiad **salvestavad ainult uusimad andmed**, seega **kustutatud kirjeid ei saa taastada**.

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

Siin on ajamasina lahendus, mille Mehmet Rediacciga üles ehitab:

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
