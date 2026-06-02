---
title: "git diff krüpteeritud kettakujutistele: harkide võrdlemine ilma neid dekrüpteerimata"
description: "rdc repo diff võrdleb krüpteeritud kujutisi ploki tasemel ja raporteerib A/M/D/R. Võtit ei puututa. Kulu sõltub muutunud plokkidest, mitte repositooriumi suurusest."
author: Muhammed Fatih Bayraktar
publishedDate: 2026-05-28
category: guide
tags:
  - luks
  - btrfs
  - ext4
  - fiemap
  - cli
featured: false
language: et
sourceHash: "516ffb7de9941f15"
sourceCommit: "0a3e9865997659698502ad551e078be854b4b2c4"
---

> **TL;DR.** `rdc repo diff` näitab failitaseme erinevust kahe hargitud repositooriumi vahel `git status --short` grammatikas (A/M/D/R), dekrüpteerimata kumbagi.
>
> - See võrdleb kaht LUKS-kujutisfaili ploki tasemel FIEMAP ioctl abil, mis loeb ainult laiendite kaardi metaandmeid. Võtit ei laadita, lihtteksti ei loeta.
> - aes-xts on pikkust säilitav ja krüpteerib iga 512-baidise sektori iseseisvalt, nii et muutunud lihtteksti sektor on muutunud šifriteksti sektor samal nihkel (nihutatud 16 MiB LUKS andmenihke võrra). Lahuta nihe, kaardista seadme vahemikud failinimedele ext4 laiendite kaardi kaudu, ja sul on failide loend.
> - Kulu sõltub muutunud plokkide arvust, mitte repositooriumi suurusest. 1 GB hark ja 100 GB hark võrreldakse sama millisekunditega, sest võrdlus on ainult metaandmete põhine.

Rediacci hark on repositooriumi LUKS-kujutise `cp --reflink=always`. Kohene, ja suurus ei loe. 100 GB repositoorium hargib sama kiiresti kui 1 GB repositoorium. Tean, et see kõlab nagu turundus, aga see on lihtsalt see, kuidas reflingid toimivad: btrfs kopeerib laiendite kaardi ja jagab sellealuseid plokke. Tuginame sellele tugevalt. Hargid on testkeskkond, äravisatav haru, lavastuskoopia, mille pärast töö lõppu prügikasti viskad.

Mis meil puudus, oli odav vastus järgmisele ilmsele küsimusele: mida see hark tegelikult muutis. Naiivsena: ühenda hark, ava LUKS-konteiner, käi läbi sisemine ext4, räsige iga fail vanema vastu. See skaleerub repositooriumi suurusega nii lugemises kui dekrüpteerimises. Selleks on vaja võtmeid difiteele. Ja see viskab ära ainsa asja, mida salvestuskiht juba tasuta teab: millised plokid lahknesid. `rdc repo diff` valib teise tee. See skaleerub muutunud plokkidega. See ei laadi võtit. See saab oma faililoendi kahe krüpteeritud kujutise võrdlemisest.

## Pinn, mida võrdled

Olgu täpne selles, mida "kaks repositooriumi" kettal tähendab. Kogu trikk sõltub sellest. Alt üles: SSD, hosti salvestus, btrfs-bassein. Selle peal üks LUKS2-kujutisfail repositooriumi kohta. Ava see ja saad dm-crypt seadme. Sees elab ext4-failisüsteem, mida konteinerid kasutavad. Üks repositoorium on üks fail btrfs-basseinil.

Hark on selle faili reflink. Vahetult pärast hargimist on kaks kujutisfaili baidiliselt identsed. Need jagavad iga füüsilist plokki. Vanem ja hark pole kaks andmekopiat. Need on kaks laiendite kaarti, mis osutavad samadele plokkidele. Kui kirjutad hargi sisse, eraldab salvestuskiht muutunud piirkonnale uue ploki. Ainult selle hargi laiendite kaart kirjutatakse ümber. Vanema plokid jäävad puutumata.

Seega taandub "kaks repositooriumi võrrelda" küsimusele "võrdle kahte faili, mis jagavad enamikku oma laienditest." Kernel saab sellele juba vastata. Keegi ei pea kumbagi faili ühtegi baiti lugema.

## FIEMAP: kernelit küsida, mis muutus, seda lugemata

FIEMAP ioctl tagastab faili laiendite kaardi: loendi (loogiline nihe, füüsiline nihe, pikkus) tuuplitest. Iga tuupel ütleb, kus üks faili osa kettal asub. See on puhas failisüsteemi metaandmed. See ei loe faili andmeid. Krüpteeritud kujutise puhul ei vaja see võtit. Šifritekst on lihtsalt baidid, mida kernel ei pea tõlgendama.

Võrdle kaht laiendite kaarti. Iga loogiline vahemik, kus mõlemad hargid osutavad samale füüsilisele plokile, on jagatud. Jagatud tähendab identset, sest see on sõna otseses mõttes sama plokk seadmel. Vahemikud, kus hargil on oma privaatne plokk, on kirjutised. Need on muutunud plokid. Saime need metaandmetest, mida salvestuskiht niikuinii hoiab.

Siit tuleb kuluarvestus. FIEMAP võrdlus loeb laiendite kirjeid, mitte andmeid. Selle töö skaleerub muutunud laiendite arvuga, mitte repositooriumi suurusega. 1 GB hark ja 100 GB hark tagastavad sama lühikese privaatsete laiendite loendi. Sama millisekundid, kui nad muutsid samu faile. Aus hoiatus: laiendite läbimise aeg skaleerub kujutise fragmentatsiooniga, mitte suurusega. Koopiakirjutamise kujutis tiheda juhusliku kirjutamisega kuhjab laiendeid. Täielik `filefrag` läbimine võttis 3,19 sekundit kõige rohkem fragmenteeritud tootmiskujutisel, mida mõõtsin. Vaata fragmentatsiooni võrdlusmõõtmise postitust. See on lagi metaandmete poolel. See on taustaotsimine, mitte andmete lugemine.

## Muutunud plokist failinimele, läbi kahe krüpteeritud kihi

Loend muutunud baidivahemiketest krüpteeritud kujutises pole veel kasulik. Vahemikud on šifriteksti positsioonid. Nimed, mida soovid, asuvad kaks kihti kõrgemal, sisemises ext4-s. Nende vaheline sild on aadressiaritmeetika, mitte dekrüpteerimine.

LUKS krüpteerib aes-xts-iga. See on pikkust säilitav ja krüpteerib iga 512-baidise sektori iseseisvalt. Muutunud lihtteksti sektor annab muutunud šifriteksti sektori samal nihkel. Ainus nihe on LUKS andmenihe. See on krüpteeritud kasuliku koormuse ees olev 16 MiB päist ja võtmepesadest. Lahuta see nihe igast muutunud kujutise vahemikust. Nüüd on sul vastav vahemik dm-crypt seadmel. See on plokseade, mille peal sisemine ext4 istub. Võtit ei kasutatud. See on lahutamine.

Nüüd kaardista seadme vahemikud failidele. ext4 hoiab ka inoodi kohta laiendite kaarti. Sama (loogiline, füüsiline, pikkus) struktuur. Jõuad selleni FIEMAP kaudu ühendatud sisemisel failisüsteemil. Käi inoodid korra läbi, et luua ploki-faili indeks. Seejärel otsi iga muutunud seadme vahemik sellest indeksist. Vahemik, mis kattub inoodi 1234 andmelaiendiga, kuulub selle inoodi teele. See tee on muutunud fail.

Öelgem selgelt, mida see kunagi ei tee. See ei tuleta muutunud kujutisest kunagi lihtteksti. See loeb failisüsteemi struktuuri teadaolevatel nihketel. Seda teeb ta nii krüpteeritud kui dekrüpteeritud poolel. Seejärel ühendab need kahe aadresse. Plokifiilter ütleb, millised seadme piirkonnad liikusid. ext4 laiendite kaart ütleb, milline fail igale piirkonnale kuulub. Kumbki samm ei kontrolli muutunud ploki sisu, et otsustada, kas see muutus.

## Lisandused, kustutused ja ümbernimetamised: inoodi-identiteedi läbimine

Muudatused tulenevad ploki võrdlusest otse. Lisandused, kustutused ja ümbernimetamised vajavad üht lisatäheldust. Reflink annab selle meile tasuta: hark säilitab inoodi numbrid. Kogu kujutise reflingimine kloonib kogu sisemise failisüsteemi baidiliselt enne, kui midagi lahkneb. Seega on inoodil, mis eksisteeris vanemas, sama number hargis.

See muudab identiteedi hulkade võrdluseks. Inood mõlemal poolel erineva teega on ümbernimetamine. Inood ainult uuel poolel on lisandus. Inood ainult vanalt poolelt on kustutus. Ümbernimetamist kinnitab seadme laiendite kattumine. Ümbernimetatud faili andmeplokid asuvad samadel seadme nihketel mõlemal hargil. Mõlemad hargid jagavad ühte koordinaatide süsteemi. See kattumine välistab ka inoodi numbri uuesti kasutamise mitteseotud andmete jaoks. Puhas ümbernimetamine ilmub siis faili andmeplookkidega muutumatuna. Ainult kataloogikanne liikus.

Siin on vaikimisi nimeoleku vorm, sama A/M/D/R grammatika, mida juba lugesid `git status --short` väljundist:

```
$ rdc repo diff --name test-1gb:fork1 -m hostinger
M  hello.txt

1 file changed: 0 added, 1 modified, 0 deleted, 0 renamed
```

Üks muudetud fail 1 GB repositooriumis. Raporteeritud plokivõrdlusest, mis ei lugenud faili andmeid. Midagi ei avatud.

Vaikimisi teeb see ühe asja veel korrektsuse tagamiseks. Plokifiilter on ülemhulk. btrfs laiend võib katta rohkem baite, kui tegelikult muutus. Seega võib kirjutamine ühte faili lipustada naabri, kes jagab laiendit. Et vältida faili raporteerimist, mis ei muutunud, kinnitab vaikimisi iga ploki poolt märgitud kandidaadi. See räsib ainult seda faili mõlemal poolel. See räsib kandidaadid, mitte repositooriumi. Seega sõltub kinnituse kulu endiselt muutuste hulgast. `--fast` usaldab plokifiltrit ja jätab kinnituse vahele. Kasuta seda, kui soovid kiiret vastust ja talud harva esinevaid valepositiivseid.

## Miks AI agent seda vajab

Põhjus, miks see käsk üldse eksisteerib, on agendi töövoog. Vaatasin pidevalt, kuidas agendid tootmist hargisid, muudatusi tegid ja siis ei leidnud puhast viisi raporteerida, mida nad tegelikult puutusid. AI agent saab tootmist koheselt hargida. Ta käitab riskantse muudatuse isoleeritud hargis. Seejärel peab ta enne midagi tagasi edendamist teadma täpselt, mida ta puudutas. Hark on haru. Diff on ülevaade.

Agent ei loe nimeolekut, ta loeb `--json` väljundit:

```
$ rdc repo diff --name prod:experiment --json -m hostinger
```

Struktureeritud väljund annab agendile täpse muudatuste hulga. Milliseid teid ta muutis, lõi, kustutas. Koos `--stat` väljundiga faili muudatuste suurus baitides ja plokkides. Agent, kes näeb oma difi enne edendamist, on selline, keda saad tootmise lähedale lasta. Plahvatusraadius on kontrollitav, mitte kinnitatav. Teised režiimid teenivad sama ülevaatustsüklit. `--name-only` puhta teede loendi jaoks. `--content <tee>` ühe faili ühendatud tekstidifiks (ainult tekst; binaarne fail raporteerib `Binary files differ`). `--stat` kui agent peab teadma, mis muutus ja kui palju.

## Miks DR testimine seda vajab

Sama primitiiv vastab DR küsimusele, mida varem oli ebamugav esitada ilma riskita. Hargita tootmine. Taasta varukoopia harki. Võrdle harki tootmisega. Diff ütleb sulle, kas taastamine reprodutseeris eeldatava failikomplekti. See teeb seda tootmist seisaku ajal alla viimata. Ja see ei dekrüpteeri difiteel midagi.

See on harjutus, mida saad ajakava järgi käitada. Taastamine maandub isoleeritud harki. Diff raporteerib delta git grammatikas. Puhas harjutus: muutuste hulk vastab sellele, mida varukoopia pidi sisaldama. Valideeri taastamine elusa tootmise vastu. Koopia on tasuta teha ja tasuta ära visata.

## Ausad piirangud

Sisu diff on ainult teksti jaoks. `--content` annab ühendatud difi tekstifailide jaoks. Kõige muu jaoks raporteerib see `Binary files differ`, samamoodi nagu git teeb. Rea-orienteeritud diff krüpteeritud-seejärel-tihendatud blobile on müra.

See võrdleb seotud harke, mitte suvalisi repositooriume. Kogu mehhanism tugineb jagatud koordinaatide süsteemile. Jagatud laiendid tõestavad võrdsust. Säilitatud inoodi numbrid ankurdavad identiteedi. Ühine andmenihe seob kõik kokku. Kaks repositooriumi, mida pole kunagi ühisest esivanemast hargitud, ei jaga midagi sellest. Nende vahel pole odavat difi. See on tunnus, mitte viga. Samamoodi nagu `git diff` kahe mitteseotud ajaloo vahel pole mõttekas.

Ümbernimetamise tuvastamine on inoodipõhine. See on täpne ümbernimetamiste jaoks, mida failisüsteem tegelikult ümbernimetamistena salvestab. Identse sisu kustutamine ja seejärel uue nime all loomine? Kaks toimingut inoodi tabelis. Seega raporteeritakse ühe kustutuse ja ühe lisandusena, mitte ümbernimetamisena. Giti sisusarnasuse heuristika nimetaks seda ümbernimetamiseks. Inoodi läbimine ei nimeta. See on õige vastus selle kohta, mida failisüsteem tegi. Isegi kui see pole vastus inimese kavatsuse kohta.

Ja metaandmete läbimine skaleerub fragmentatsiooniga. Tugevalt fragmenteeritud kujutisel on laiendite loendamine sekundites, mitte millisekundites. See on endiselt repositooriumi suurusest sõltumatu. See on endiselt vaba igasugusest andmete lugemisest. Kuid see pole sõna otseses mõttes kohene kõige rohkem fragmenteeritud kujutistel.

## Kokkuvõte

`rdc repo diff` paigutab versioonikontrolli ergonoomikat krüpteeritud, töötavale infrastruktuurile. Liides on tahtlikult git-stiilis. A/M/D/R, ühendatud difid, `--stat`. Midagi uut pole vaja õppida. Kui oskad lugeda `git status --short` väljundit, oskad lugeda difi kahe LUKS-kujutise vahel. Selle alla peidetud insenerteadus on osa, millest tasub hoolida. See taandub kahele keeldumisele. See ei dekrüpteeri kunagi. aes-xts lubab plokitaseme FIEMAP võrdlusel leida iga muutunud sektori aadressiga. Ja see ei maksa kunagi andmete eest, mis ei muutunud. Salvestuskiht salvestas juba, millised plokid lahknesid. Hark on haru. Diff on ülevaatus. Ülevaatuse kulu on see, mida muudatus maksab, mitte see, mida repositoorium kaalub.
