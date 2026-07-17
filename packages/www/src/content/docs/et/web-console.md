---
title: Veebikonsool
description: Käivita kogu rdc CLI oma brauserist vormide, ressursivalijate ja käivituste ajalooga
category: Guides
order: 8
language: et
sourceHash: "b735dd2fd77435c5"
sourceCommit: "5197d1c0349438c2bff2442377a5166d0b8214b6"
---

# Veebikonsool

Veebikonsool on brauseripõhine kasutajaliides kogu `rdc` CLI kohal. Iga CLI käsk ilmub konsoolis koos vormi, valideerimise, ressursivalijate ja Käivita nupuga. Eraldi "veebifunktsioonide komplekti" pole: konsool genereeritakse CLI lepingust, seega on konsoolis olemas iga käsk, mis on CLI-s, ja uued käsud ilmuvad automaatselt.

See asub veebiportaalis aadressil `/account/console`.

## Kättesaadavus

Veebikonsool on tasuline funktsioon. See sisaldub tasulistes plaanides ja on Community plaanil peidetud. Ligipääs on ka rollipõhiselt piiratud, nii et organisatsiooni administraator saab kontrollida, kes seda näeb.

## Seos konfiguratsioonisalvega

Konsool loeb sinu ressursse (masinad, repositooriumid jne) sinu krüpteeritud konfiguratsioonisalvest ning dekrüpteerib selle konfiguratsiooni ainult brauseris. See tähendab:

- **Lukustatud olekus** näed ikkagi kogu käsukataloogi, saad avada iga käsu vormi ja lugeda selle parameetreid. See toimib ilma igasuguse seadistuseta.
- **Käskude käivitamiseks ja valijate kasutamiseks** pead esmalt oma konfiguratsioonisalve avama (passkey, peaparool või taastekood, vt [Konfiguratsioonisalv](/et/docs/config-storage)). Käivita nupud, ressursilehed ja ressursivalijad kõik sõltuvad avatud seansist.

Dekrüpteeritud võti jääb ainult brauseri mällu. Lehe värskendamine lukustab konsooli uuesti ja 30 minutit tegevusetust lukustab selle automaatselt.

## Ressursivalijad

Kui konsool on avatud, asendavad käsuvormid vabateksti väljad valijatega, mis toituvad sinu dekrüpteeritud konfiguratsioonist: masinad, repositooriumid, andmesalved, salvestusruumid, klastrid, pilveteenuse pakkujad ja varundusstrateegiad. Mõned valijad lahendatakse selle asemel elavalt, käsku käivitades — näiteks konteinerid masinas või hetktõmmised andmesalves.

Valijad filtreerivad sõltuvalt: vali masin ja repositooriumi valija kitseneb selle masina peale. Repositooriumiviidete jaoks koostab viite koostaja täieliku `nimi:silt@masin` vormi üksikutest valikutest. Valijad on vihjed, mitte piirangud, ja sa saad väärtuse alati käsitsi sisestada.

## Käskude käivitamine

Brauser ei hoia kunagi SSH-võtit ega masina aadressi. Kui klõpsad Käivita, saadab konsool ainult käsu kavatsuse — millist käsku ja milliseid parameetreid — ning käitaja lahendab kõik muu ja käivitab selle. Vaata [Proxy ja käitaja](/et/docs/proxy-and-executor), kuidas see töötab ja millised käsud saavad sel viisil töötada.

Käsud, mis ainult muudavad sinu konfiguratsiooni (näiteks masinakirje loomine), ei käivitu kaugelt üldse. Konsool suunab need sisseehitatud konfiguratsiooniredaktorisse, kus muudatus krüpteeritakse ja lükatakse edasi nagu iga teine konfiguratsioonimuudatus.

Iga vorm näitab ka vastavat CLI käsurida, nii et kõike, mida konsoolis seadistad, saab otse kopeerida terminali või skripti.

## Orienteerumine

- **Ressursilehed**: masinatel, repositooriumitel ja töödel on kõigil nimekirja- ja detaillehed, millele on lisatud asjakohased käsud tegevustena.
- **Käsupalett**: vajuta Cmd-K (Ctrl-K), et hüpata otse mistahes käsu või ressursi juurde nime järgi.
- **Käivituste ajalugu**: varasemad käivitused säilivad seansi kaupa, nii et saad väljundit üle vaadata ja samade parameetritega uuesti käivitada.

## Seotud

- [Konfiguratsioonisalv](/et/docs/config-storage), krüpteeritud konfiguratsioonisalve seadistamine ja avamine
- [Proxy ja käitaja](/et/docs/proxy-and-executor), Käivita nupu taga olev käivitusmudel
