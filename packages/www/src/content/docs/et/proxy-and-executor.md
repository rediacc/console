---
title: Proxy ja käitaja
description: Kuidas brauseri ja õhukese kliendi käsud töötavad ilma, et klient hoiaks kunagi SSH-võtmeid või masinate aadresse
category: Concepts
tags:
  - security
  - networking
order: 4
language: et
sourceHash: "39ec44d8efc3f9b5"
sourceCommit: "5197d1c0349438c2bff2442377a5166d0b8214b6"
---

# Proxy ja käitaja

Tavaliselt töötab `rdc` sinu enda masinas koos sinu konfiguratsiooni ja SSH-võtmetega ning ühendub serveritega otse. Proxy-mudel jagab selle kaheks: õhuke klient, mis ei hoia ühtegi saladust, ja **käitaja**, mis hoiab neid ja teeb töö ära. [Veebikonsooli](/et/docs/web-console) Käivita nupp ja CLI `--proxy` lipp on mõlemad õhukesed kliendid ning nad räägivad sama juhtmeprotokolli.

## Käsu kavatsus, mitte käsk ise

Õhuke klient ei hoia kunagi SSH-võtit, masina aadressi ega dekrüpteeritud konfiguratsiooni. Kui ta soovib midagi käivitada, saadab ta ainult käsu kavatsuse: identifikaatori käsu jaoks (selle asukoht CLI lepingus, näiteks `repo up`) koos parameetritega. Käitaja otsib käsu samast lepingust üles, lahendab selle vastavaks serveripoolseks funktsiooniks, lahendab sihtmasina dekrüpteeritud konfiguratsioonist ja käivitab selle oma SSH-ühenduse kaudu. Väljund voogedastatakse tagasi kliendile.

Käitaja on CLI ise, käivitatud serverina käsuga `rdc serve`. Sama binaarfail, mida operaatorid sülearvutis kasutavad, muutub selleks, mis nende nimel käske käivitab. Sellel on kaks paigutusviisi:

- **`--mode daemon`**: töötab sinu enda hallatud hostis, registreeritud pealdiseta nagu iga teine CLI (vt [Konfiguratsioonisalv](/et/docs/config-storage)), nii et see saab konfiguratsioonivõtme ise tuletada ega vaja seansipõhist andmist. See on range tase: SSH ei lahku kunagi sinu võrgust.
- **`--mode container`**: töötab sinu jaoks hallatud organisatsioonipõhises konteineris. See alustab ilma ühegi võtmeta ja ei saa midagi teha, kuni klient seansi jaoks võtme annab. See on mugavuse tase.

## CEK-i andmine

Konfiguratsioonisalv on null-teadmisega: server salvestab ainult krüpteeritud plokke ja sisukrüpteerimisvõti (CEK) eksisteerib lahtiselt ainult kliendil, kes selle avas. Konteinerirežiimis käitajale tuleb seetõttu võti *anda* ning andmine ei tohi seda vahepeal serverile paljastada.

Voog on selline: avatud brauser avab käitajaga seansi, saab seansi avaliku võtme ja pitseerib CEK-i sellele seansile X25519 abil. Pitseeritud plokk läbib kontoserverit, kuid server ei suuda seda avada, seega säilib null-teadmine läbivalt. Käitaja dekrüpteerib CEK-i ainult mällu, 30-minutilise jõudeaja aegumisega; midagi ei kirjutata kunagi kettale. Järgnevad käsupäringud viitavad antud seansile `X-Config-Session` päise kaudu.

Auditeerimise seisukohalt on oluline üks detail: sama kasutajaidentiteet käib läbi kõiki kolme etappi (seansi avamine, võtme andmine, käskude käivitamine). Kontoserver ei edasta käitajale kunagi enda mandaati. Iga etapi jaoks vermib ta lühiajalise tokeni, mis on seotud tegeliku kasutajaga, ja kontrollib iga kord uuesti selle kasutaja liikmesust. Käitaja kontrollib, milline token talle iga toimingu jaoks esitatakse. Ühe kasutaja tehtud andmist ei saa kasutada teine kasutaja.

Konfiguratsiooni `state` pool (hostikohalikud käitusandmed) ei liigu kunagi konfiguratsiooniploki sees, seega ei jõua see ka selle tee kaudu kunagi käitajani.

## Mis saab proxy kaudu töötada

Mitte iga käsk pole kaugkäivituseks mõistlik. Iga käsk lepingus kannab `proxyCapable` lippu ja käitaja jõustab seda serveripoolselt, sõltumata mistahes poliitikaseadistusest:

- **Masinatasandi, mitteinteraktiivsed käsud** (deploy, backup, staatus, logid jms) on proxy-toega.
- **Konfiguratsioonitasandi käsud** ei ole: need muudavad konfiguratsiooni, mis sellel teel on brauseri ülesanne (veebikonsool suunab need selle asemel oma konfiguratsiooniredaktorisse).
- **Interaktiivsed käsud** (terminalid, VS Code seansid) ei ole: sellel juhtmel puudub TTY.
- **Kliendipoolsed ülekandekäsud** (`rdc repo sync`) ei ole: need liigutavad andmeid *kliendi* failisüsteemi ja masina vahel, käitajal pole ligipääsu kliendi failidele.

Veebikonsool loeb sama lippu, et otsustada, kas käsk saab üldse Käivita nupu, kuid käitaja keeldub mittetoetatud käskudest sõltumata sellest, mida klient saadab.

## Mock-käitaja

Arenduse ajal, kui ühtegi päris käitajat pole konfigureeritud, vastab kontoserver käsupäringutele ise mock-voogude ja selgelt võltsandmetega (ressursside nimed eesliitega `mock-`). See võimaldab kogu konsooli testida, sealhulgas vorme, voogedastust ja tulemuste kuvamist, ilma masina või avamiseta. Päris käivitamiseks on vaja päris käitajat.

## Seotud

- [Veebikonsool](/et/docs/web-console), sellel mudelil põhinev brauseriklient
- [Konfiguratsioonisalv](/et/docs/config-storage), null-teadmisega salv, mida CEK kaitseb
