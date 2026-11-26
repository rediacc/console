---
title: "Digitaalne kriminalistika: tõendid kompromiteeritud hoidla seest"
description: "Hoidlapõhised võrguvoogude ja tundlike failide avamiste kirjed kliendi valitud detailsusega, mida edastatakse iga 30 sekundi järel allkirjastatud ja aheldatud partiidena. Käsitleb kolme jäädvustustaset, hüppeliselt käivitajat, paketikvoote, võrguühenduseta ja serveripoolset tuvastust ning seda, mida server näeb."
category: "Guides"
tags:
  - security
  - compliance
subcategory: data-protection
order: 9
language: et
sourceHash: "c349f479d246dee4"
sourceCommit: "0531ce955ea0d1658b8fceefd6aa44e3c270521c"
---

# Digitaalne kriminalistika

Digitaalne kriminalistika vastab kahele küsimusele olukorras, kus hoidlas töötav tarkvara on kompromiteeritud: millal andmeid välja viidi ja milliseid andmeid. Rediacc ei saa kolmanda osapoole tarkvara auku sulgeda, seega salvestab funktsioon tõendeid, mis kompromiteerimise üle elavad. Kirjeid kirjutab masinas juurõigustega kogur väljaspool hoidla liivakasti ning need saadetakse ämbrisse, millele kliendi administraatorid ligi ei pääse.

Kirjed näitavad mahtu, sihtkohta ja ajastust. Voogude kirjed tõendavad mahtu ja sihtkohta, mitte sisu. [Intsidendi töövoog](/et/docs/incident-response) loeb neid ning [intsidendiaruanded](/et/docs/incident-reports) teevad neist järelevalveasutusele allkirjastatud dokumendid.

## Mida salvestatakse

Jäädvustus on hoidlapõhine. Hoidlad kasutavad hosti võrku, mistõttu liiklus seotakse cgroupi (hoidla enda slice) järgi, mitte kunagi IP-aadressi järgi.

| Kirje | Sisu |
|---|---|
| Võrguvoog | Aeg, protsess, sihtaadress ja port, protokoll, väljuvad ja sissetulevad baidid, DNS-nimi kui teada ning sihtkoha ASN ja riik kui teada |
| Faili avamine | Aeg, protsess ja tee, tundlike teede loendiga sobiva tee puhul |
| Südamelöök | Allkirjastatud märge igas partiis, nii et peatunud kogur paistab lünga, mitte vaikusena |

Tundlike teede vaikeloend hõlmab `.env`-faile, võtme- ja sertifikaadifaile (`*.pem`, `*.key`, `id_rsa*`, `id_ed25519*`), paroolibaase (`*.kdbx`), andmebaasivedusid ja -faile (`*.sql`, `*.dump`, `*.bak`, `*.sqlite*`) ning andmebaaside andmekaustu nagu `pgdata`. Hoidla võib loendit laiendada või asendada oma mustritega.

Pakettide sisu ja failide sisu ei salvestata kunagi.

## Jäädvustustasemed

Igal hoidlal on üks tase ja vaikimisi on selleks madalaim. Kõrgem tase salvestab kõike, mida madalam salvestab.

| Tase | Salvestatakse |
|---|---|
| `basic` | Kokkuvõte iga 5 minuti järel sihtkoha, pordi ja protokolli kohta, sissetulevate ja väljuvate baitidega |
| `standard` | Voo kirje iga minut, koos protsessi ja DNS-nimega |
| `full` | Standard ning lisaks failiavamised tundlikel teedel |

Tase määratakse hoidlapõhiselt:

```bash
rdc forensics level mail basic
rdc forensics level mail standard
rdc forensics level mail full
```

Kogur piirab taseme sellega, mida pakett sisaldab. Kui paketil pole kriminalistika kvooti, ei salvesta hoidla midagi.

### Hüppeline käivitaja

Iga tase seab käivitaja valmis. Kui hoidla väljuvad baidid ühe minuti jooksul ületavad kümnekordse enda libiseva keskmise (ja ületavad 50 MiB minutis) pärast seda, kui hoidlat on jälgitud 24 tundi, lülitub hoidla 24 tunniks tasemele Full. Käivitav minut keskmisse ei lähe, nii et üks andmeleke ei saa tõsta lähtetaset, mis peaks tabama järgmise.

## Paketid ja kvoodid

Digitaalne kriminalistika on tasuliste pakettide jaoks ja salvestab ainult seni, kuni pakett on tasutud. Uuendamisel algab ajalugu nullist.

| Pakett | Kriminalistika kvoot |
|---|---|
| Free, Community | 0 (midagi ei salvestata) |
| Professional | 25 GB |
| Business | 125 GB |
| Enterprise | 512 GB või Rediacci administraatorite määratud eraldi kvoot |

Kvoot on veerand paketi varukoopia kvoodist ja seda arvestatakse varukoopiatest eraldi. Rohkem kvooti saab ainult paketi uuendamisega.

Kui kvoot saab täis, kõrvaldatakse esimesena vanimad kirjed (FIFO). Viimased 7 päeva on lukustatud ja neid ei kõrvaldata kunagi, sest ämber lukustab need 7 päevaks. Kui juba ainult lukustatud baidid ületaksid kvoodi, lükatakse uued partiid tagasi. Kui prognoositav 7 päeva vastuvõtt ei mahuks, piiratakse tase Basicuga. Omanikud ja administraatorid saavad teate, kui kvoodist on kasutatud 80 protsenti, kui piir langeb Basicule ja kui partii tagasi lükatakse.

Deklareeritud intsidendi sisse jäävad kirjed jäetakse kõrvaldamisest välja kuni 30 päeva pärast intsidendi sulgemist. Vt [intsidentidele reageerimine](/et/docs/incident-response).

## Edastus ja terviklus

Kogur lõikab partii iga 30 sekundi järel. Iga partii allkirjastatakse masina spuuli võtmega ja sellel on eelmise partii räsi, nii et eemaldatud või muudetud partii katkestab ahela. Partiid laaditakse üles ainult loomist lubavate eelallkirjastatud URL-ide kaudu, mis väljastatakse masina litsentsiploki põhjal, seega saab masin kirjeid lisada, kuid mitte üle kirjutada ega kustutada. Ühenduse katkemisel ootavad partiid kohalikus allkirjastatud spuulis ja saadetakse, kui ühendus taastub.

Öine tihendamine liidab partiid üheks päevafailiks hoidla kohta ja üheks päisefailiks masina kohta, kus on loetletud iga allkirjastatud päis ja märgitud iga lünk. Konto auditi päevafailid aheldatakse samamoodi, organisatsiooni ja päeva kaupa.

`rdc forensics verify` ja uurimislehe nupp Verify evidence arvutavad need ahelad uuesti. Vt [intsidentidele reageerimine](/et/docs/incident-response).

## Tuvastus

Anomaaliate tuvastus töötab kaks korda. Masinas olev statistiline detektor reageerib kohe ja lülitab hoidla tasemele Full. Server käitab vastuvõtul oma detektoreid, nii et tuvastus püsib ka kompromiteeritud hosti korral. Ühegi logikirje kohta ei käivitata tehisintellekti.

Detektorid on kihilised ja iga hoidla õpib oma liiklusest:

| Detektor | Otsib |
|---|---|
| Nädalatunni lähtetasemed | Baite, ühendusi, erinevaid sihtkohti, uusi DNS-nimesid ja uusi protsesse väljaspool hoidla tavapärast rütmi sellel nädalatunnil |
| Half-Space Trees | Voogu, mis ei sarnane varem nähtud voogudele |
| ECOD ja HBOS | Voopartiisid, mis hinnatakse erandiks, koos tunnustega, mis hinde määrasid |
| Esimest korda nähtud | Protsessi, mis avab tundliku faili, mida ta pole varem avanud |

Iga tuvastus kannab tunnuspõhiseid põhjusi, mis selle tekitasid, ja selgitus on nendest põhjustest koostatud mall. Võrguühenduseta keelemudelit ei ole. Tuvastus muutub konto teateks ning e-kirjaks omanikele, administraatoritele ja turvakontaktile. Kui masin on võrgust väljas, tegutseb ta kohe kohapeal (Full-jäädvustus ja kirje oma allkirjastatud spuulis) ning edastab hoiatuse, kui ühendus taastub, säilitades algse tuvastusaja.

### Mudelipaketid

Detektori parameetrid avaldatakse allkirjastatud pakettidena aadressil `data.rediacc.com/models/`: sisuaadressiga failid, manifest, mis on allkirjastatud renetisse sisseehitatud võrguühenduseta Ed25519 mudelivõtmega, renet'i minimaalne versioon ja ainult kasvav versioon, nii et versiooni langetamine lükatakse tagasi. Pakett kontrollitakse enne paigaldamist ja eelmise saab taastada.

```bash
renet models status
renet models update
renet models rollback
```

Õhkvahega paigaldused saavad sama allkirjastatud paketi `rdc server bundle` sees, kui ei anta `--no-models`.

## Mida server näeb

Kontoserver loeb kirjeid, sest ajatelg, kontroll ja serveri detektorid vajavad neid: sihtkohti, porte, protsessinimesid, DNS-nimesid, baidiloendureid ja tundlike failide teid. Pakettide sisu ja failide sisu ta ei saa.

Sissetuleva kliendi aadress salvestatakse kirjetes kärbituna (IPv4 puhul /24 ja IPv6 puhul /48) ning täielik aadress asub eraldi sektsioonis, mis kustutatakse 30 päeva pärast. Kustutatud sektsiooni räsi jääb allkirjastatud päisesse, nii et ahel kontrollitakse endiselt läbi ja kontrollija teatab aadressi maskeerituks. Väljuvad sihtkohad jäävad tervikuna, sest need on tõend.

Kliendid avavad kirjed uurimise kaudu, mis nõuab tasulist paketti, omaniku või administraatori rolli ja hiljutist uuesti autentimist, ning iga vaatamine auditeeritakse. Rediacci tugi näeb kriminalistika andmeid ainult ajaliselt piiratud volituse alusel, mille klient annab. Töötlemistingimused on [andmetöötluslepingus](/et/data-processing-agreement).
