---
title: "Git-laadne hargnemine"
description: "Käsitle koopiakirjutamise harke git-komitidena: külmuta hark muutumatuks komitiks, nimeta harusid, võta komitid välja kirjutatavate harkidena, jaluta ajalugu ja ühenda ilma kunagi elavat repositooriumi muutmata."
category: Reference
tags:
  - forking
  - repositories
subcategory: commands
order: 41
language: et
sourceHash: "7aaa25bc83dfcf5b"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# Git-laadne hargnemine

Siin on mõttermudel: Rediacc muudab koopiakirjutamise hargid git-laadseks versiooniajalooks. Iga muutumatu hark on **komit**: baidiliselt stabiilne, külmutatud kujutis, mis keeldub ühendamast. Harud on nimega viited, mis osutavad komitile. `rdc repo checkout` reflink-kloonib komiti tagasi kirjutatavaks töötavaks hargiks ja `rdc repo merge` ühendab kaks ajalooliini ilma kunagi elavat repositooriumi muutmata.

Mudel kaardistub kahele hoidlale. **Masin on objektihoidla**: komitid on muutumatud hargikujutised, mis elavad andmehoidlas. **CLI konfiguratsioon on viitehoidla**: harunimed, praegune `HEAD` ja reflog elavad sinu lokaalses konfiguratsioonis, mitte masinal. See on sama jaotus, mida git kasutab `.git/objects` ja `.git/refs` vahel.

## Millal kasutada

Kasuta hargnemist siis, kui hark on teeninud nime. AI agent jooksis tootmise hargis vabalt, tulemus näeb hea välja ja soovid külmutatud, nimega kontrollpunkti, mille juurde saad hiljem naasta või mille saad edendada: `rdc repo commit` külmutab selle, `rdc repo branch` nimetab selle. Enne riskantset migratsiooni komita töötav hark, et sul oleks täpne taastepunkt, mis on garanteeritult muutumatu (muutumatu komit keeldub ühendamast, nii et miski ei saa sellesse kirjutada). Kahe kontrollpunkti võrdlemiseks töötab `rdc repo diff` iga kahe komiti vahel, sest neil on ühine koopiakirjutamise esivanem. Ülevaadatud tööliini sihtharku tagasi toomiseks ehitab `rdc repo merge` tulemuse reflink-kloonist ja vahetab selle atomaarselt sisse, nii et töötav sihtmärk ei korrupteeruks ühendamise keskel.

Ära kasuta seda `rdc repo fork` asendajana, kui vajad ainult äravisatavat koopiat. Tavaline hark on õige üksus ajutise, testipõhise isolatsiooni jaoks. Komitid lisavad väärtust siis, kui olek on väärt hoidmist, nimetamist või tarne.

## Kuidas komitid ja hargid seostuvad

Repositoorium on üks LUKS-kujutisfail btrfs-basseinil. Hark on konstantaja reflink sellest kujutisest, nii et 1 GB repositooriumi ja 100 GB repositooriumi hargimiseks kulub sama aeg. **Komit** on hark, mis on märgitud muutumatuks: renet keeldub seda ühendamast, mis hoiab selle kujutise baidiliselt stabiilsena igavesti. See baidistabilisus muudab komiti usaldusväärseks taastepunktiks ja deterministlikuks aluseks masinate vaheliseks delta edastuseks.

`rdc repo commit` salvestab komiti sõnumi, autori, ajatempli ja vanemkomiti **mahu sees** (et metaandmed rändaksid kujutisega edastamisel kaasa) ning peegeldab selle ka väljaspool mahtu (et `rdc repo log` saaks ajalugu jalutada ilma midagi avamata). Komiteeritud töötav hark jätkub muutumatult, täpselt nii nagu git jätab su töökataloogile komiti järel puutumatuks.

## Käsud

### rdc repo commit

Külmuta ühendatud töötav hark uueks muutumatuks komitiks.

```bash
rdc repo commit <hark> --message "<sõnum>"
```

| Valik | Kirjeldus | Vaikimisi |
|--------|-------------|---------|
| `<ref>` (positsiooniline) | Komitatav töötav hark. Peab olema haagitud. Kohustuslik. | kohustuslik |
| `--message <msg>` | Komiti sõnum. Kohustuslik. | kohustuslik |
| `--author <author>` | Komiti autor, mis salvestatakse komiti metaandmetesse. | seadmata |
| `--debug` | Detailsed diagnostikateated stderr-i. | väljas |

Uus komit registreeritakse lokaalses konfiguratsioonis atribuudiga `immutable: true` ja töötava hargi `headCommit` edeneb sellele osutama. Muutumatu repositooriumi komiteerimine lükatakse tagasi: tee sellest esmalt kirjutatav hark kasutades checkout-i.

### rdc repo branch

Loo nimega haru viide, mis osutab töötava hargi praegusele komitile.

```bash
rdc repo branch <fork> --branch <nimi>
```

| Valik | Kirjeldus | Vaikimisi |
|--------|-------------|---------|
| `--branch <branch>` | Uue haru nimi. Kohustuslik. | kohustuslik |
| `<ref>` (positsiooniline) | Töötav hark, mille praegusele komitile haru osutab. Kohustuslik. | kohustuslik |

See on ainult konfiguratsioonitoimingud. Masinal ei toimu midagi. Haru viide kaardistab nime töötava hargi `headCommit`-ile, seega peab hargil olema vähemalt üks komit esmalt.

### rdc repo checkout

Reflink-klooni muutumatu komit (või haru tipp) värskeks kirjutatavaks töötavaks hargiks.

```bash
rdc repo checkout <komit> --tag <uusHark>
rdc repo checkout <haruNimi> --from <hark> --tag <uusHark>
```

| Valik | Kirjeldus | Vaikimisi |
|--------|-------------|---------|
| `<commit-or-branch-ref>` (positsiooniline) | Väljavõetava komiti GUID või haru nimi, kui `--from` on antud. Kohustuslik. | kohustuslik |
| `--tag <name>` | Uue kirjutatava töötava hargi nimi. Kohustuslik. | kohustuslik |
| `--from <workingFork>` | Lahendab positsioonilise viite haru nimeks selle töötava hargi harude hulgas. | otsene komit |
| `--debug` | Detailsed diagnostikateated stderr-i. | väljas |
| `--skip-router-restart` | Jäta marsruuteri taaskäivitussamm vahele. | väljas |

Checkout taaskasutab hargi reflink teed, seega on see peaaegu kohene ja konstantaja olenemata repositooriumi suurusest. Uue töötava hargi `headCommit` seatakse väljavõetud komitile.

### rdc repo log

Jaluta komitide ajalugu, mis on töötavast hargist või komitist kättesaadav.

```bash
rdc repo log <hark>
```

| Valik | Kirjeldus | Vaikimisi |
|--------|-------------|---------|
| `<ref>` (positsiooniline) | Töötav hark või komit, millest ajaloo läbimist alustada. Kohustuslik. | kohustuslik |
| `-o json` | Väljasta komitide ajalugu JSON-ina. | `table` |
| `--debug` | Detailsed diagnostikateated stderr-i. | väljas |

`log` jalutab vanemate ahela, mida `rdc repo commit` salvestas, lugedes väljaspool mahtu olevat olekupeegli, nii et ühtegi komiti ei avata ega ühendata. See on ainult lugemiseks.

### rdc repo merge

Ühenda lähtekomit või hark sihtmärgi töötavasse harku, muutmata elavat sihtmärki kohapeal.

```bash
rdc repo merge <sihtmärk> --from <allikas>
rdc repo merge <sihtmärk> --from <allikas> --resolve theirs
```

| Valik | Kirjeldus | Vaikimisi |
|--------|-------------|---------|
| `<ref>` (positsiooniline) | Sihtmärk-töötav hark, millesse ühendada. Kohustuslik. | kohustuslik |
| `--from <source>` | Lähtekomit või hark, millest ühendada. Kohustuslik. | kohustuslik |
| `--force` | Vaigistu ühendatud või töötav sihtmärk esmalt, seejärel ühenda. Ei muuda kunagi elavat ühendust. | väljas |
| `--resolve <ours\|theirs>` | Failipõhine kolmesuunaline ühendamine: voldi allika failipõhised muudatused sihtmärgile, hoides (`ours`) või võttes (`theirs`) allika versiooni failide jaoks, mis on muutunud mõlemal poolel. Välja jätmisel võetakse kogu kujutis allikast. | väljas |
| `--base <guid>` | Ühise esivanema komit kolmesuunaliseks ühendamiseks (kasutatakse koos `--resolve`). Vaikimisi on allika komiti vanem või sihtmärgi praegune komit. | automaatne |
| `--debug` | Detailsed diagnostikateated stderr-i. | väljas |

Tulemus ehitatakse reflink-kloonist ja vahetatakse atomaarselt sisse krahhikindla markeri taha, nii et katkestatud ühendamine jätab algse sihtmärgi terveks. Ühendatud või töötav sihtmärk lükatakse tagasi, välja arvatud `--force`, mis sulgeb sihtmärgi puhaste enne vahetust.

Ilma `--resolve`-ta on ühendamine kogu kujutise võtmine allikast (sihtmärgist saab allikas). Koos `--resolve`-ga on see failipõhine kolmesuunaline ühendamine allika komiti salvestatud vanema vastu: failid, mis muutusid ainult ühel poolel, võetakse sellelt poolelt, ja failid, mis muutusid mõlemal poolel, lahendatakse lipuga. Konfliktsed teed raporteeritakse.

### rdc repo gc

Kogu masinal prügi, muutumatud komiti objektid, mida ükski haru või HEAD ei jõua.

```bash
rdc repo gc -m <masin>            # kuiva jooksu eelvaade (vaikimisi)
rdc repo gc --apply -m <masin>    # kustuta kättesaamatud komitid
```

| Valik | Kirjeldus | Vaikimisi |
|--------|-------------|---------|
| `-m, --machine <name>` | Masin, millelt koguda. Kohustuslik. | kohustuslik |
| `--apply` | Kustuta tegelikult kättesaamatud komitid (muidu kuiva jooksu eelvaade). | väljas |
| `--debug` | Detailsed diagnostikateated stderr-i. | väljas |

Kättesaadavus arvutatakse lokaalse konfiguratsiooni põhjal (viitehoidla): komitide hulk, mis on kättesaadavad, järgides iga haru tippu ja HEAD-i vanemate ahela kaudu. Masinal olevad muutumatud komitid, mis jäävad sellest hulgast väljapoole, on kättesaamatud. Ühendatud objekti ega töötavat harku ei koguta kunagi.

### rdc repo admin fsck

Valideeri konfiguratsiooni viited masinal olevate objektide vastu.

```bash
rdc repo admin fsck -m <masin>
```

| Valik | Kirjeldus | Vaikimisi |
|--------|-------------|---------|
| `-m, --machine <name>` | Kontrollitav masin. Kohustuslik. | kohustuslik |

Raporteerib rippuvad viited (haru tipp või HEAD, mis osutab GUID-ile ilma objektita masinal) ja orb-komitid (muutumatu komit masinal, mida ükski viide ei jõua). See on ainult lugemiseks; puhasta orbsid käsuga `rdc repo gc --apply`.

### Muutumatud hargid

`rdc repo fork --immutable` märgib uue harki loomise hetkel ainult lugemiseks, tootes komitiekvivalentse aluse ilma eraldi `commit` sammuta.

```bash
rdc repo fork <nimi> --tag <tag> --immutable
```

Muutumatu hark keeldub ühendamast, mis hoiab selle kujutise baidiliselt stabiilsena igavesti. See on kasulik külmutatud alusena masinate vaheliseks delta edastuseks, kus alus peab mõlemal otsas identne olema. Muudatuste tegemiseks tee sellest checkout (või hargista uuesti) kirjutatavasse koopisse.

## Näited

### Töötava hargi komiteerimine

```bash
$ rdc repo commit myapp:work --message "schema migration applied"
Committed 4f3c2a1b9d8e: schema migration applied
```

### Komiteerimine selgesõnalise autoriga

```bash
$ rdc repo commit myapp:work --message "nightly snapshot" --author ci-bot
Committed 7a1b2c3d4e5f: nightly snapshot
```

### Haru nimetamine praegusel komitil

```bash
$ rdc repo branch myapp:work --branch staging
Branch "staging" -> 4f3c2a1b9d8e
```

### Komiti väljavõtmine värskesse kirjutatavasse harku

```bash
$ rdc repo checkout 4f3c2a1b9d8e --tag rollback-test
```

### Haru tipu väljavõtmine nime järgi

Koos `--from`-iga lahendatakse `--ref` väärtus haru nimena antud töötaval hargil:

```bash
$ rdc repo checkout staging --from myapp:work --tag staging-copy
```

### Ajaloo jalutamine

```bash
$ rdc repo log myapp:work
commit 4f3c2a1b9d8e
  Author: ci-bot  Date: 2026-05-29T10:14:02Z
  schema migration applied
commit 9d8e7a1b2c3d
  Author: ci-bot  Date: 2026-05-28T22:01:55Z
  initial import
```

### Ajalugu JSON-ina

`-o json` annab struktureeritud läbimise, uusimast esimesena:

```bash
$ rdc repo log myapp:work -o json
{
  "success": true,
  "start": "4f3c2a1b9d8e",
  "entries": [
    {
      "guid": "4f3c2a1b9d8e",
      "message": "schema migration applied",
      "author": "ci-bot",
      "parent": "9d8e7a1b2c3d",
      "committed_at": "2026-05-29T10:14:02Z",
      "immutable": true
    }
  ]
}
```

### Kahe komiti võrdlemine

`rdc repo diff` töötab iga kahe komiti vahel, sest neil on ühine koopiakirjutamise esivanem. Võta üks komit välja, seejärel võrdle teisega:

```bash
$ rdc repo checkout 4f3c2a1b9d8e --tag review
$ rdc repo diff review --base myapp:work
M  db/schema.sql

1 file changed: 0 added, 1 modified, 0 deleted, 0 renamed
```

Täieliku difividite kohta vaata [rdc repo diff](/et/docs/repo-diff).

### Ülevaadatud tööliini tagasi ühendamine

```bash
$ rdc repo merge myapp:main --from myapp:work
Merged myapp:work into myapp:main
```

### Ühendamine töötava sihtmärgiga

Ühendatud või töötav sihtmärk lükatakse tagasi, välja arvatud `--force`, mis vaikib selle esmalt:

```bash
$ rdc repo merge myapp:main --from myapp:work --force
Merged myapp:work into myapp:main
```

### Failipõhine kolmesuunaline ühendamine

Kaks harku (`feature` ja `hotfix`), mis on väljavõetud samast komitist, muutsid mõlemad mõningaid faile. `--resolve theirs` voldib allika (`hotfix`) sihtmärgile (`feature`): failid, mida muutis ainult üks pool, võetakse sellelt poolelt, ja failid, mida muutsid mõlemad pooled, lahendatakse allika kasuks. Alus tuvastatakse automaatselt jagatud esivanema põhjal (või kinnita `--base`-ga):

```bash
$ rdc repo merge myapp:feature --from myapp:hotfix --resolve theirs
Merged myapp:hotfix into myapp:feature (three-way); 1 conflict(s) resolved --theirs: [config/app.yaml]
```

`config/app.yaml` muutus mõlemal poolel ja lahendati allika kasuks; fail, mille lisas ainult `hotfix`, rakendatakse, ja fail, mida muutis ainult `feature`, hoitakse. Konfliktsed teed raporteeritakse, et saad need üle vaadata.

### Muutumatu aluse otse loomine

```bash
$ rdc repo fork myapp --tag baseline-v1 --immutable
```

## Delta edastus ja tõmbamine

Muutumatu, baidiliselt stabiilne kujutis on ka alus **plokitaseme delta edastusele**. Kui sama muutumatu alus eksisteerib kahel masinal, saab edastamine arvutada muutunud plokid selle aluse vastu ja edastada ainult need, selle asemel et skannida kogu krüpteeritud kujutist. 1 GB repositoorium mõne muutunud plokiga edastatakse siis megabaitides.

Tavaliselt ei pea alust käsitsi andma. Pärast täielikku edastamist säilitab CLI edastatud kujutise muutumatu alusena mõlemal masinal ja salvestab selle, nii et **järgmine** selle repositooriumi edastamine saadab automaatselt ainult delta, ilma liputa, isegi hargi puhul, mis sihtmasinal juba eksisteerib. (Olemasoleva hargi *täielikuks* uuesti edastamiseks on endiselt vaja `--force`, kuna see asendab kogu kujutise, mitte ei rakenda verifitseeritud deltat.) Anna `--delta-base <guid>`, et kindlustada konkreetne alus, ja `--strategy <auto|physical|shared>`, et kontrollida, kuidas muutunud plokke tuvastatakse (`auto` on peaaegu alati õige).

```bash
# Esimene edastamine on täielik; see säilitab ka korduvkasutatava aluse mõlemal otsas.
$ rdc repo push myapp:work --to backup-1

# Pärast lokaalseid muudatusi saadab järgmine edastamine ainult muutunud plokid, ilma liputa.
$ rdc repo push myapp:work --to backup-1

# Kinnita selgesõnaline alus (muutumatu komit, mis on mõlemal masinal olemas).
$ rdc repo push myapp:work --to backup-1 --delta-base 4f3c2a1b9d8e

# Delta töötab ka vastupidises suunas, tõmmates ainult muutunud plokid masinalt.
$ rdc repo pull myapp:work --from backup-1 --delta-base 4f3c2a1b9d8e

# Tõmba uuesti olemasolev lokaalne repositoorium (kirjuta üle) koos --force.
$ rdc repo pull myapp:work --from backup-1 --force
```

Delta edastamine rakendub ainult masinate vahel (kaugarvutiga, millel on FIEMAP alus). Pilveobjektide salvestusele edastamine edastab alati täieliku kujutise. Alus peab mõlemal otsas baidiliselt identne olema, mis on täpselt see, mida muutumatu komit või `--immutable` hark garanteerib.

## JSON-skeem

`rdc repo log <repo> --output json` mähib renet-i tulemuse standardümbrikusse. Jalutatud ajalugu elab `entries`-is, uusimast esimesena:

| Väli | Tüüp | Kirjeldus |
|-------|------|-------------|
| `success` | boolean | Kas jalutamine lõpetati. |
| `start` | string | GUID, millest jalutamine algas. |
| `entries` | array | Üks objekt komiti kohta, uusimast esimesena. |
| `entries[].guid` | string | Komiti GUID. |
| `entries[].message` | string | Komiti sõnum. Välja jäetud, kui tühi. |
| `entries[].author` | string | Komiti autor. Välja jäetud, kui tühi. |
| `entries[].parent` | string | Vanema komiti GUID. Välja jäetud juurel. |
| `entries[].committed_at` | string | RFC 3339 komiti ajatempel. Välja jäetud, kui seadmata. |
| `entries[].immutable` | boolean | Kas komit on märgitud ainult lugemiseks (päris komiti puhul alati tõene). |

Ümbriku väljade ja automaatse tuvastamise reeglite kohta, mis annavad JSON-i mitte-TTY keskkondades, vaata [JSON Väljundi viide](/et/docs/ai-agents-json-output).

## Piirangud

- **Viited on lokaalsed.** Harunimed, `HEAD` ja reflog elavad CLI konfiguratsioonis, mitte masinal. Komiti edastamine teisele masinale saadab komiti objekti ja selle mahusissese metaandmed, kuid haru viide on konfiguratsiooni poolne mõiste.
- **Komit keeldub ühendamast.** See on mõte: muutumatus muudab komiti baidiliselt stabiilseks. Komiti käivitamiseks või redigeerimiseks tee sellest esmalt checkout kirjutatavasse töötavasse harku.
- **Ühendamise lahendamine on failipõhine, mitte reapõhine.** Mõlemad, kogu kujutise võtmine allikast (ilma `--resolve`-ta) ja failipõhine kolmesuunaline (`--resolve ours|theirs`), on toetatud. Kolmesuunaline ühendamine lahendab konfliktid terve faili korraga vastavalt lipule; see ei anna reapõhiseid tükke ega ühendamise markereid faili sees.
- **Ajalugu on vanemate ahel.** `rdc repo log` jalutab üksiku `parent` lingi, mis salvestati komiteerimise ajal. See peatub, kui jõuab komitini, mille metaandmed pole küsitud masinal olemas.

## Vaata ka

- [rdc repo diff](/et/docs/repo-diff). Failitaseme diff iga kahe seotud komiti või hargi vahel.
- [Repositooriumid](/et/docs/repositories). Repositooriumide loomine, hargnemine, ühendamine ja käitamine.
