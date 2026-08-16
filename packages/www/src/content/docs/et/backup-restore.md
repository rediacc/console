---
title: "Varundamine ja taastamine"
description: "Tee krüpteeritud repositooriumidest hetktõmmiseid sisupõhiselt aadresseeritud tükksalvestusse, kus laaditakse üles ainult muutunud rakud ja iga hetktõmmis taastub otse. Või hoia koopiat teisel masinal. Taasta kus tahes ja automatiseeri nimetatud strateegiate ning systemd-taimerite abil."
category: "Guides"
order: 7
language: et
sourceHash: "91f6072e230b059c"
sourceCommit: "79c84ad044d5730b6d0a20aaf7b21f21914b6bda"
---

# Varundamine ja taastamine

Rediacc varundab krüpteeritud repositooriumeid ja taastab neid samal või erineval masinal. Varukopiad on krüpteeritud, sest repositoorium ise on seda: masinast lahkub šifreeritud tekst, ning taastamiseks on vajalik repositooriumi LUKS-volitus.

Varundamiseks on kaks viisi, ja need vastavad eri küsimustele.

- **Hetktõmmised tükksalvestusse** (`rdc backup snapshot`) hoiavad ajalugu, mille kaudu saad tagasi minna. See on peamine tee.
- **Koopia teisel masinal** (`rdc repo push`, `rdc repo pull`) hoiab repositooriumi sellisena, nagu see praegu on, riistvaral, mida sina kontrollid. Pilvekontot ei kaasata.

Need on sõltumatud. Ühel viisil varundatud repositoorium ei ole teisel viisil varundatud.

## Kuidas hetktõmmised töötavad

Repositooriumi tõmmis lõigatakse fikseeritud võrgustikul fikseeritud suurusega rakkudeks. Iga rakk on kas auk, mis tähendab, et sinna pole kunagi midagi kirjutatud, või salvestatakse see võtme all, mis **on** selle raku šifreeritud teksti SHA-256.

Sellest ühest otsusest tulenevad kõik omadused.

**Ainult tegelikud muudatused maksavad midagi.** Esimene hetktõmmis laadib üles iga kirjutatud raku. Iga järgnev käivitus küsib failisüsteemilt, millised extendid puudutati, loeb ja räsib ainult neid ning laadib üles ainult need rakud, mida hoidla veel ei oma. Repositoorium, mille andmed vaevu liikusid, laadib üles peaaegu mitte midagi, ja käivitus võtab minuteid, mitte nii kaua kui tõmmis on suur.

**Identsed andmed salvestatakse üks kord.** Kuna võti on sisu räsi, jagavad kaks hetktõmmist, mis jagavad üht rakku, sama objekti, ja sama kehtib repositooriumi ja tema [forkide](/et/docs/tutorial-forking) kohta: forkide perekond varundab ühe päritolu vastu, selle asemel et oma vanemat dubleerida.

**Vana hetktõmmise taastamine ei ole aeglasem kui hiljutise taastamine.** Ahelat inkrementidest, mida läbi mängida, ei ole. Taastamine lahendab hetktõmmise täielikuks rakkude nimekirjaks ja toob need rakud otse, seega järgib taastamisaeg tõmmise suurust ja sinu ribalaiust, mitte seda, kui kaua oled varukopiaid teinud. Augud jäävad aukudeks, seega hõre tõmmis taastub hõredana, ja rakk, mis esineb tõmmises mitmes kohas, laaditakse alla üks kord.

**Iga hetktõmmis seisab omal jalal.** Ei ole "täisvarukoopiat", mida sa ei tohi kaotada, ega akent, kus katkine inkrement muudab hilisemad kehtetuks. Iga hetktõmmis nimekirjas on otse taastatav.

**Kinnitamine tähendab uuesti räsimist, mitte usaldamist.** Kuna võti on sisu räsi, tähendab varukoopia kontrollimine rakkude toomist ja räsimist. `rdc backup verify` võtab proove; `rdc backup verify --deep` räsib uuesti iga salvestatud raku.

**Katkenud käivitus ei ole raisatud.** Üleslaadimine jätkub ilma juba kohale jõudnud rakke uuesti saatmata, ja osalise taastamise taaskäivitamine räsib uuesti selle, mis on juba kettal, ja kasutab seda uuesti, selle asemel et see uuesti alla laadida.

### Mis see sulle maksma läheb

Kvooti loetakse **füüsiliste unikaalsete salvestatud baitidena**: see, mida pärast dedupleerimist tegelikult hoitakse, mitte teie hetktõmmiste loogiline kogusumma. Kolmkümmend hetktõmmist repositooriumist, mis muutub aeglaselt, maksavad peaaegu sama palju kui üks. `rdc backup usage` näitab salvestatud baite sinu kvoodi vastu, mis on tellimusepõhine number, mis algab 10 GB-st Community plaanil.

### Mida hetktõmmised vajavad

Hetktõmmise üleslaadimine käib läbi konto-serveri, mis autoriseerib iga käivituse repositooriumi paigaldatud litsentsi vastu ja annab masinale lühiajalise kirjutusõiguse. Seega vajab see tee konto-serverit, mille masin saab kätte, ja litsentseeritud repositooriumi. Ilma nendeta lükatakse hetktõmmis tagasi, selle asemel et vaikselt vahele jätta, ja `rdc backup manifests`, `rdc backup usage` ning `rdc backup retention` ei leia midagi lugeda.

See kehtib ka `--dry-run` kohta. Litsentsi loetakse enne, kui käivitus otsustab, kas ta planeerib või laadib üles, seega on proovikäivitus töö eelvaade, mitte viis proovida käsku ilma volitusteta.

Masina-masina push ja pull ei vaja kumbagi. Need on otsene ülekanne kahe masina vahel, mis on juba sinu konfiguratsioonis.

### Mida hetktõmmis ei luba

- **Hetktõmmis katab ühe repositooriumi, mitte kogu sinu masinat korraga.** Iga repositoorium jäädvustatakse omal hetkel. Kui kaks repositooriumi sõltuvad teineteisest, ei ole nende hetktõmmised koordineeritud paar.
- **See ei ole pidev replikatsioon.** Hetktõmmis on hetk, mille sa jäädvustasid, ja sa võid kaotada kõik, mis on kirjutatud alates viimasest. Kui palju see on, sõltub sellest, kui sageli sa käivitad.
- **Salvestatud objektid on üks kord kirjutatavad, mitte sertifitseeritud WORM.** Rakud kirjutatakse ainult-loomise tingimusega, masina saadav õigus ei saa midagi kustutada, ja kustutamised toimuvad serveripoolselt säilituspoliitika alusel. See on tõeline tõke kompromiteeritud masinale, mis hävitab oma varukopiad. See ei ole vastavussertifikaat ja seda ei auditeerita sellisena.

### rclone salvestustee on kadunud

`rdc repo push --to <storage>` ja tema sugulased kopeerisid varem terve varufaili pilveteenuse pakkujasse, mille sa ise registreerisid. Need keelduvad nüüd salvestussihtmärgist ja nimetavad selle asendaja. Masina-masina ülekanne ei käinud kunagi rclone kaudu ega ole mõjutatud. Kui pead endiselt lugema sel viisil kirjutatud arhiivi, vaata [Enne kaotamist kirjutatud arhiivi lugemine](#enne-kaotamist-kirjutatud-arhiivi-lugemine).

### Tükksalvestuse käsud

```bash
# Laadi tõmmis üles. Esimene käivitus külvab, hilisemad saadavad ainult muutunud rakud.
rdc backup snapshot my-app

# Planeeri ilma üles laadimata: näitab, mis liiguks.
rdc backup snapshot my-app --dry-run

# Peata konteinerid, külmuta, käivita uuesti, seejärel laadi üles.
rdc backup snapshot my-app --cold

# Ära usalda kohalikku ankrut ja laadi kogu sisu uuesti üles.
# See laadib kõik uuesti üles ja arvestab kvoodi uuesti; kasuta
# seda ainult siis, kui ankur on teadaolevalt vigane.
rdc backup snapshot my-app --reseed

# Kontrolli salvestatud sisu ja oma kvooti.
rdc backup verify my-app
rdc backup manifests my-app
rdc backup usage
```

| Valik | Kirjeldus |
|--------|-------------|
| `<repo-ref>` (positsiooniline) | Hetktõmmise repositoorium |
| `--dry-run` | Ainult planeeri: üleslaadimist ei toimu. Näitab, mis liiguks |
| `--cold` | Peata konteinerid, külmuta, käivita uuesti, seejärel laadi üles. Ei saa kombineerida `--dry-run`-iga |
| `--reseed` | Ära usalda kohalikku ankrut ja laadi üles täielik sisu. Laadib kõik uuesti üles ja arvestab kvoodi uuesti |
| `--debug` | Luba detailne väljund |

## Külmad hetktõmmised (`--cold`)

Külm hetktõmmis peatab repositooriumi enne külmutamist, nii et salvestatud tõmmis on rakenduse-järjepidev, mitte ainult krahhi-järjepidev. Käsk töötab masinas endas:

```bash
# Iga repositoorium vaikimisi andmesalves.
sudo renet backup snapshot --cold

# Ainult nimetatud repositooriumid. --repo võtab repositooriumi GUID-i ja on korratav.
sudo renet backup snapshot --cold --repo <guid> --repo <guid>
```

`--cold` ja `--dry-run` kokku ei käi. Proovikäivitus, mis konteinereid peatab, ei ole proovikäivitus, ja see, mis neid ei peata, ei ole külm; seepärast keeldub renet paarist, selle asemel et sinu eest tähendus valida.

### Mida külm käivitus teeb

Iga valitud repositooriumi puhul, selles järjekorras:

1. Peatab selle konteinerid.
2. Kirjutab repositooriumi haakepunkti ja andmesalve kettale.
3. Kontrollib, et konteinerid tõesti peatusid.
4. Teeb repositooriumi tõmmisest kirjutamisel-kopeeriva reflingi.
5. Käivitab konteinerid uuesti.

Alles siis algab üleslaadimine, ja kõik repositooriumid on selleks ajaks juba töös.

Seisak on külmutamine, mitte ülekanne. Reflink koosneb ainult metaandmetest, seega võtab see sama palju aega, hoiab repositoorium siis 1 GB või 100 GB. Üleslaadimine nii ei tööta: see kasvab koos muutunud baitidega ja esimene hetktõmmis laadib üles kogu nullist erineva sisu. Konteinerite allhoidmine kuni üleslaadimise lõpuni seoks seisaku andmemahuga, mis esimesel korral tähendab tunde, mitte millisekundeid.

Kõik valitud repositooriumid peatatakse ühes aknas, mitte ükshaaval. See maksab repositooriumi kohta veidi rohkem seisakut ja annab vastu ühe järjepidevuspunkti kogu komplekti kohta.

Repositoorium, milles ühtegi konteinerit ei tööta, on juba vaikne. Selle hetktõmmis tehakse ilma igasuguse seisakuta, ja see on tavapärane tulemus, mitte tõrge.

### Mida seisak maksab

Päris masinas mõõdetuna oli kogu seisak **222 ms**:

| Etapp | Mõõdetud | Mis toimub |
|-------|----------|------------|
| `cold_down` | 64 ms | Konteinerid peatuvad |
| `cold_sync` | 26 ms | Repositooriumi haakepunktid ja andmesalv kirjutatakse kettale |
| `cold_verify` | 31 ms | Kinnitatakse, et konteinerid on peatunud |
| `cold_stage` | 0 ms | Repositooriumi tõmmise reflink |
| `cold_up` | 99 ms | Konteinerid käivituvad uuesti |

Kõige rohkem kulub konteinerite taaskäivitamisele ja ettevalmistus on praktiliselt tasuta: reflink ei paista millisekundilise täpsuse juures üldse välja. Loe seda nulli siiski koos iga repositooriumi kirjetega, mitte omaette. Ka käivitus, mis keeldus igast repositooriumist, teatab `cold_stage=0ms`, ja ainult kirjed ütlevad, kumma juhtumiga on tegu.

Jaotus on tõend, mitte kaunistus. Ükski neist viiest etapist ei loe ega saada repositooriumi andmeid, seega ei kasva ükski neist koos varukoopiaga. Ainus osa, mis kasvab, on üleslaadimine, ja see käib siis, kui seisak on juba läbi.

renet trükib käivituse lõpus samad numbrid, nii et sa saad mõõta oma masinaid, mitte uskuda meie omi:

```text
Cold backup: <n> repositories quiesced, outage 222ms (cold_down=64ms cold_sync=26ms cold_verify=31ms cold_stage=0ms cold_up=99ms)
```

Iga repositooriumi JSON-kirje kannab sama seisakut ja samu etappe, nii et hiljem on külm hetktõmmis kuumast eristatav ilma aegadest oletamata.

### Millal valida külm

Kuum on vaikevalik ja enamiku repositooriumide puhul õige valik. Kuum hetktõmmis on krahhi-järjepidev, ehk sellises seisus, nagu repositoorium oleks pärast voolukatkestust, ja see ei maksa mingit seisakut. Enamik andmebaase ja järjekordi taastub sellest ise.

Vali külm nende andmete jaoks, mida ei saa kirjutamise ajal ohutult jäädvustada. Tüüpiline juhtum on andmebaas, millel on oma ettekirjutuslogi ja mälus hoitav olek. Sa vahetad lühikese mõõdetud seisaku hetktõmmise vastu, mille rakendus saab avada ilma end enne parandamata.

### Millest külm käivitus keeldub

Keeldumine ongi siin see väärtus. Külmaks nimetatud varukoopia, mis ei peatanud midagi, on vale, mille avastad alles taastamisel; seepärast ei alanda renet külma käivitust vaikselt kuumaks:

- **Konteinerid, mis ei peatunud.** Pärast peatamist küsib renet repositooriumi enda Dockeri soklilt, kas midagi veel töötab. Kui töötab, siis sellest repositooriumist keeldutakse, selle asemel et hetktõmmis teha. Kontroll otsustab turvalise poole kasuks: kui soklini ei saa või konteinerite loendit ei õnnestu lugeda, loetakse peatamine kinnitamata jäänuks, ja kinnitamata tähendab keeldumist.
- **Litsents, mida ei saa lugeda.** Litsentse kontrollitakse enne seisakut, mitte pärast, sest repositoorium, mille litsentsi ei saa lugeda, poleks niikuinii midagi üles laadida saanud. Selline repositoorium jäetakse vahele ilma seda peatamata. Kui ühelgi valitud repositooriumil ei ole loetavat litsentsi, keeldutakse kogu käivitusest enne, kui üksainuski konteiner alla läheb.
- **Teine külm käivitus samas andmesalves.** Lukk katab kogu andmesalve ja hõivatud lukust keeldutakse kohe, ilma et midagi oleks peatatud. Kaks kattuvat käivitust peataksid kumbki konteinereid, mida teine peab enda omaks, ja teine käivitaks uuesti repositooriume, mida esimene alles külmutab. Käivitus vahele jätta ja järgmist oodata on sellest parem.

Kui käivitus katkeb ajal, mil konteinerid on all, näiteks `systemctl stop` või taaskäivituse tõttu, käivitab renet need enne väljumist uuesti. Masina taastus on varuvõrk: see märkab külma varukoopiat, mille omanik on kadunud, ja toob need repositooriumid tagasi üles.

## Varukoopia saatmine teise masinasse

Kopeeri repositoorium SSH kaudu teise masinasse:

```bash
rdc repo push my-app --to server-1
```

`--to <machine>` lahendab sihtkoha sinu konfiguratsioonist ja `--to-machine <machine>` ütleb sama asja selgesõnaliselt. Salvestuse nimi lükatakse tagasi: see tee on kaotatud.

Krüpteeritud tõmmis kopeeritakse SAMA GUID-iga, seega on tegu varukoopia või migratsiooniga, mitte fork'iga. Sõltumatu koopia saamiseks käivita kõigepealt `rdc repo fork` ja saada fork.

Esimene saatmine kannab kogu tõmmise. Iga järgnev saatmine saadab ainult muutunud plokid muutumatu baastõmmise vastu, mida hoitakse mõlemal masinal, ilma et peaksid ühtegi lippu seadma. `--delta-base <guid>` nimetab selle baasi ise, kui vaja.

Saadetud koopia jõuab sihtkohta varukoopia artefaktina, mitte töötava repositooriumina. Muuda see üheks käsuga `rdc backup restore`:

```bash
rdc backup restore my-app@server-1 --as my-app --machine server-1 --up
```

Kindla ajahetke varundamiseks kasuta selle asemel tükksalvestust: `rdc backup snapshot my-app` laadib üles ainult muutunud rakud ning `rdc backup restore my-app --at <snapshot>` toob need tagasi.

| Valik | Kirjeldus |
|--------|-------------|
| `<ref>` (positsiooniline) | Saadetava repositooriumi viide |
| `--to <remote>` | Sihtmasin või -klaster |
| `--to-machine <machine>` | Sihtmasin, selgesõnaliselt märgitud |
| `--provision <provider>` | Sihtmasina provisioneerimine selle pilveteenuse pakkuja kaudu, kui see ei eksisteeri |
| `--checkpoint` | Loob CRIU kontrollpunkti enne saatmist (konteineritele, millel on silt `rediacc.checkpoint=true`). Sihtmärk taastab automaatselt käsuga `repo up` |
| `--force` | Kirjuta olemasolev varukoopia üle |
| `--bwlimit <limit>` | Ribalaiuse piirang rsync-ülekandele (nt `10M`, `500K`) |
| `--delta-base <guid>` | Kanna üle ainult muutunud plokid võrreldes selle muutumatu baas-GUID-iga. Jäta ära automaatse baasi jaoks |
| `--strategy <strategy>` | Plokk-delta strateegia delta-baasi kasutamisel: `auto`, `physical` või `shared` |
| `--debug` | Luba detailne väljund |
| `--skip-router-restart` | Jäta marsruudiserverit pärast toimingut taaskäivitamata |

## Varukoopia tõmbamine teisest masinast

Too repositoorium tagasi masinast, kus see asub:

```bash
rdc repo pull my-app --from server-1
```

Lisa `--up`, et see samas käsus ühendada ja juurutada. Tükksalvestusest taastamiseks kasuta selle asemel käsku `rdc backup restore my-app --at <snapshot-id>`.

Pull keeldub üle kirjutamast repositooriumi, mis on hetkel **ühendatud**. Ühenda see kõigepealt lahti, tee pull ja too see siis tagasi käsuga `rdc repo up`. Kaustapõhised repositooriumid on erand: need sünkroonivad end kohapeal ka ühendatuna.

| Valik | Kirjeldus |
|--------|-------------|
| `<ref>` (positsiooniline) | Tõmmatava repositooriumi viide |
| `--from <remote>` | Lähtemasin või -klaster |
| `--from-machine <machine>` | Lähtemasin, selgesõnaliselt märgitud |
| `--force` | Kirjuta olemasolev kohalik varukoopia üle |
| `--up` | Ühenda ja juuruta repositoorium pärast tõmbamist |
| `--bwlimit <limit>` | Ribalaiuse piirang rsync-ülekandele (nt `10M`, `500K`) |
| `--delta-base <guid>` | Võta vastu ainult muutunud plokid võrreldes selle muutumatu baas-GUID-iga |
| `--strategy <strategy>` | Plokk-delta strateegia delta-baasi kasutamisel: `auto`, `physical` või `shared` |
| `--debug` | Luba detailne väljund |
| `--skip-router-restart` | Jäta marsruudiserverit pärast toimingut taaskäivitamata |

## Varukoopiote loetlemine

Loetle tükksalvestuses olevad hetktõmmised:

```bash
rdc backup manifests my-app
```

Iga rida on üks salvestatud ajahetk:

| Veerg | Tähendus |
|---|---|
| `Repo` | Repositooriumi nimi, lahendatud sinu kohalikust konfiguratsioonist (langeb tagasi GUID-ile repo-de puhul, mida konfiguratsioonis pole) |
| `Snapshot` | Hetktõmmise id. Seda võtab `rdc backup restore --at` |
| `Created` | UTC-aeg, millal hetktõmmis tehti |
| `Total` | Repositooriumi tõmmise suurus, mida see hetktõmmis esindab |
| `Added` | Baidid, mille see hetktõmmis tegelikult üles laadis lisaks eelnevatele |
| `Chunks` | Mitu rakku see lisas |

Et näha, mida `rdc repo push --to <machine>` sihtkohta jättis, küsi sellelt masinalt, mida ta hoiab:

```bash
rdc repo list --machine server-1
```

Saadetud koopia ilmub oma nime all. Teine rida, mis kannab kõrval toorest GUID-i, on säilitatud delta-baas, mis teeb järgmise saatmise sellele masinale inkrementaalseks, mitte täielikuks ülekandeks.

`rdc backup list --machine <machine>` loeb `hot/` ja `cold/` kaustu, kuhu ajastatud käivitused kirjutavad, seega on see vale tööriist koopia jaoks, mille saatmine sinna jättis, ega näita sulle midagi.

| Veerg | Tähendus |
|---|---|
| `Mode` | `hot` või `cold`. Milline ajastatud varundamise kaust see kirje asub |
| `Name` | Repositooriumi nimi, lahendatud sinu kohalikust konfiguratsioonist (langeb tagasi GUID-ile repo-de puhul, mida konfiguratsioonis pole) |
| `GUID` | Kettal olev repositooriumi GUID |
| `Size` | Inimloetav varukoopifaili suurus |
| `Modified` | UTC ajatempel failist masinal |

Salvestusliidese loetlemine on kaotatud koos rclone-haruga; käsk keeldub ja nimetab need kaks asendust.

## Säilitamine

Server jõustab andmehoidla kohta repositooriumipõhist säilituspoliitikat tükksalvestuse üle, nii et vanad hetktõmmised kärbitakse ilma, et sa peaksid midagi käsitsi kustutama. Deklareerimata poliitika korral säilitatakse iga hetktõmmis.

```bash
# Mida praegu jõustatakse.
rdc backup retention my-app

# Hoia rulluvat akent: 7 päevast, 4 nädalast, 6 kuist.
rdc backup retention set my-app --keep-daily 7 --keep-weekly 4 --keep-monthly 6

# Mine tagasi kõige säilitamise juurde.
rdc backup retention clear my-app
```

| Valik | Kirjeldus |
|--------|-------------|
| `--keep-last <n>` | Säilita see arv kõige uuemaid hetktõmmiseid |
| `--keep-hourly <n>` | Säilita kõige uuem hetktõmmis igast neist tundidest |
| `--keep-daily <n>` | Säilita kõige uuem hetktõmmis igast neist päevadest |
| `--keep-weekly <n>` | Säilita kõige uuem hetktõmmis igast neist nädalatest |
| `--keep-monthly <n>` | Säilita kõige uuem hetktõmmis igast neist kuudest |
| `--keep-yearly <n>` | Säilita kõige uuem hetktõmmis igast neist aastatest |

Anna vähemalt üks reegel. Reegliteta `set` lükatakse tagasi, selle asemel et käsitleda seda kui "ära säilita midagi", sest poliitika tühjendamiseks on olemas `clear`.

## Taastamine

`rdc backup restore` muudab varukoopia toimivaks repositooriumiks, ja see on sama käsk mõlema tee jaoks. Erinevus on selles, millele sa selle suunad.

```bash
# Ajahetk tükksalvestusest.
rdc backup restore my-app --as my-app-yesterday --at <snapshot-id> --up

# Artefakt, mille saatmine masinale jättis.
rdc backup restore my-app@server-1 --as my-app --machine server-1 --up
```

`--at` võtab hetktõmmise id käsust `rdc backup manifests` või RFC 3339 aja, näiteks `2026-08-14T12:00:00Z`, mis lahendatakse kõige uuemaks hetktõmmiseks, mis on tehtud sellel hetkel või varem. Aeg, millele ei eelne hetktõmmist, lükatakse tagasi, selle asemel et see edasi ümardada.

Taastamine uue nime alla käsuga `--as` ei kirjuta midagi üle, seega on taastamise harjutus ohutu käivitada elava masina vastu. Taastamine juba olemasoleva nime alla lükatakse tagasi.

| Valik | Kirjeldus |
|--------|-------------|
| `<artifact-ref>` (positsiooniline) | Mida taastada. `repo` tükksalvestuse hetktõmmise jaoks, `repo@place` masinal oleva artefakti jaoks |
| `--as <name>` | Taastatud repositooriumi nimi (vaikimisi artefakti nimi) |
| `-m, --machine <machine>` | Masin, kuhu taastada |
| `--datastore <name>` | Taasta sellesse nimetatud andmehoidlasse, mille ühendatud masin seda majutab |
| `--at <time>` | Taasta ajahetk: hetktõmmise id või RFC 3339 aeg |
| `--up` | Juuruta taastatud repositoorium pärast ülekannet |
| `--health-window <seconds>` | Kui kaua jälgida juurutatud repositooriumi tervist |
| `--health-timeout <seconds>` | Kui kaua oodata, kuni see saab terveks |
| `-y, --yes` | Jäta kinnitus vahele |
| `--debug` | Luba detailne väljund |

Repositooriumi taastamine vajab selle LUKS-volitust, mis elab sinu konfiguratsioonis. Kui sul on konfiguratsiooni salvestus lubatud, tuleb see volitus tagasi koos sinu konfiguratsiooniga uuel masinal. Kui mitte, hoia konfiguratsiooni koopiat kuskil, kuhu ebaõnnestuv masin seda endaga kaasa ei võta.

### Taastamise tõestamine igal masinal

Masin, mis pole kunagi täisringi läbinud, ei ole varundatud, ükskõik kui roheliseks tema üleslaadimised tunduvad. Üleslaadimised ja taastamised ebaõnnestuvad erinevatel põhjustel, ja teist tüüpi näed ainult siis, kui proovid.

Tee seda üks kord masina kohta, enne kui varukoopiatele lootma jääd:

1. Tee hetktõmmis: `rdc backup snapshot my-app`.
2. Kinnita, et see on salvestatud: `rdc backup manifests my-app`.
3. Taasta see äravisatava nime alla: `rdc backup restore my-app --as my-app-drill --at <snapshot-id>`.
4. Võrdle taastatud repositooriumi algallikaga, siis kustuta harjutuskoopia käsuga `rdc repo delete my-app-drill --yes`.

Miski selles jadas ei puuduta elavat repositooriumi, seega on see ohutu masinal, mis teenindab liiklust. Kui liigud üle vanemalt varundusskeemilt, hoia seda töös, kuni see on sellel masinal vähemalt korra läbinud. Kaks varundusteed maksavad salvestusruumi; üks tõestamata tee maksab andmed.

## Sünkroniseeri üks repositoorium korraga

Push ja pull toimivad korraga ühe repositooriumi peal, mis on adresseeritud viitega (`name`, `name:tag` või `name@machine`). Vormi "kõik repositooriumid korraga" ei ole: käivita käsk iga repositooriumi jaoks eraldi.

Viide, mis nimetab forki ja masinat, toimib samamoodi nagu tavaline nimi:

```bash
rdc repo push shop:nightly@server-1 --to server-2
rdc repo pull shop:nightly@server-1 --from server-2
```

Täielikud valikute nimekirjad on [Varukoopia saatmine teise masinasse](#varukoopia-saatmine-teise-masinasse) ja [Varukoopia tõmbamine teisest masinast](#varukoopia-tõmbamine-teisest-masinast) all.

## Ajastatud varundamine

Rediacc kasutab nimetatud varundamisstrateegiaid. Iga strateegia määratleb ajakava, varundamisrežiimi, valikulise ribalaiuse piirangu ja failifiltrid. Masinad viitavad strateegiatele nimede järgi, et määrata, millised varukopiad neil käitatakse.

### Varundamisrežiimid

| Režiim | Käitumine | Seisakuaeg |
|------|----------|----------|
| `hot` | Repositooriumi tõmmis külmutatakse, samal ajal kui teenused jätkavad tööd (krahhi-ühilduvalt) | Puudub |
| `cold` | Teenused peatatakse, hetktõmmis võetakse, teenused taaskäivitatakse, hetktõmmis laaditakse üles (rakenduse-ühilduvalt) | Repo-kohane peatus+käivitus aken, paralleelselt repo-dega. Vaata "Külma varundamise seisakuaja hindamine" allpool. |

Kasuta `hot` teenuste puhul, mis taluvad krahhi-ühilduvaid hetktõmmiseid. Kasuta `cold`, kui vajad garanteeritud järjepidevust ja saad lühikest taaskäivitust taluda.

### Külma varundamise semantika

Külm varundamine käib kolmes faasis kaasatud repo kohta: **peatus → hetktõmmis → käivitus**. Garantiide lõpu mõistmine aitab operaatoritel osalisi tõrkeid varakult märgata.

**Mida külm varundamine garanteerib:**

- Enne hetktõmmist peatatakse iga kaasatud repo iga töötav konteiner graatsiliselt selle Rediaccfile'i `down()` konksuga ja repo-kohane Dockeri daemon rahustatatakse. Hetktõmmis on seega rakenduse-ühilduv, mitte ainult krahhi-ühilduv.
- Konteinerite ID-de hulk, mis töötasid enne hetktõmmist, salvestatakse kõrvalfaili asukohas `/var/run/rediacc/cold-backup-<guid>.running.json`. See on tõeallikas "mis peaks pärast lõpetamist töötama".
- Pärast hetktõmmist kutsutakse repo Rediaccfile'i `up()` konks täieliku compose-hunniku taastamiseks.
- Käivitusepõhine olekukõrvalfail asukohas `/var/run/rediacc/cold-backup-<guid>.status.json` kirjendab iga katse faasi, tulemuse ja võimalikud vead.

**Mida külm varundamine EI garanteeri:**

- `up()` on parima püüdluse alusel. See võib ebaõnnestuda põhjustel, mis pole külma varundamise kontrolli all (nt `depends_on: service_healthy` tingimus, mis ootab veel, compose-faili süntaksiviga, mööduv võrgutõrge pildi tõmbamisel). Kui see ebaõnnestub, logib külm varundamine vea veatasemele, kirjutab olekukõrvalfaili ja liigub järgmisele repo-le.
- Kui `up()` ebaõnnestub, rakendub **tagavarana otsene taaskäivitus**: loetakse töötamise kõrvalfail ja iga kirjendatud konteineri ID taaskäivitatakse otse Dockeri API kaudu (ilma compose'ita). See toob teenused tagasi isegi kui compose-voog on takerdunud, kuigi ilma Rediaccfile'i konksude uuesti käivitamiseta.
- Kui isegi tagavara ebaõnnestub mõne konteineri ID puhul (näiteks Dockeri daemon ise on maas), **jäetakse kõrvalfail paika**, et marsruuteri valvekoer saaks igal taktil uuesti proovida.

**Valvekoera taastamine:** igal taktil kontrollib valvekoer töötamise kõrvalfaili. Kõik seal loetletud konteineri ID-d, mis praegu on peatatud, taaskäivitatakse, *olenemata konteineri salvestatud `restart_policy`-st*. See tähendab, et teenused, millel on `restart: on-failure` (mida Docker ei taaskäivitaks pärast puhtast peatust) tulevad pärast külma varundamist tagasi. Kui kõik loetletud konteinerid töötavad, kustutatakse kõrvalfail.

**Kuidas operaatorid tõrkeid tuvastavad:**

- `rdc machine status <machine> --containers` näitab töötavat olekut. Võrdle oodatud hulgaga.
- `/var/run/rediacc/cold-backup-<guid>.status.json` masinas. Vaata seda käsuga `rdc term connect <repo> -c "cat /var/run/rediacc/cold-backup-$GUID.status.json"`. `success: false` koos vana `startedAt`-ga tähendab, et viimane varukoopia ei lõppenud puhtalt.
- Logid renet-i varundamiskäivitusest (`journalctl -u renet-*` või otsene `rdc backup schedule` kutse) väljastavad lõplik kokkuvõtterida kujul `Cold backup: post-snapshot restart summary total=N compose_ok=N fallback_ok=N failed=N failed_repos=[...]`. Mittetühi `failed_repos` on grep-sihtmärk.

### Külma varundamise seisakuaja hindamine

Iga repo on maas ainult oma `down()` + `up()` akna jooksul. Soojal hostil on need tavaliselt:

| Repo kuju | Tüüpiline peatus+käivitus |
|------------|--------------------|
| Väike (1-2 konteinerit, ilma DB-ta) | 5-15 s |
| Keskmine (veebirakendus + vahemälu) | 20-45 s |
| Raske (DB + järjekorrad + meil) | 60-120 s |

Külmutamise samm on repositooriumi tõmmise kirjutamisel-kopeeriv reflink. See koosneb ainult metaandmetest, seega võtab sama palju aega, hoiab repositoorium siis 1 GB või 100 GB, ning mõõdetud käivitusel ei paistnud see millisekundilise täpsuse juures üldse välja. Repo ei ole maas teiste repo-de külmutamise ajal. Üleslaadija käivitatakse siis külmutatud koopia vastu, samal ajal kui iga repo on juba jälle üleval.

**Kogu käivituse kogu seinakell** sõltub sellest, mitu repo-d taaskäivituvad samaaegselt. Renet tuletab selle hostist:

```text
concurrency = min(repoCount, max(2, NumCPU/2), 8)
```

Näited:

| Host | Repo-d | Samaaegsus | Seinakell taaskäivitus |
|------|-------|-------------|--------------------|
| 4 CPU VM | 5 repo-d, keski 30 s | 2 | ~75 s |
| 16 CPU server | 10 repo-d, keski 40 s | 8 | ~80 s |
| 64 CPU flotii sõlm | 50 repo-d, keski 40 s | 8 | ~4 min |

**Ülekate keskkonna kaudu:** sea `REDIACC_COLD_BACKUP_CONCURRENCY=N` varundamisteenuse keskkonnas (tavaliselt systemd drop-in kaudu), et kinnitada konkreetne väärtus. `=1` sunnib rangelt jadaviisilisi taaskäivitusi, mis on kasulik ühe repo `up()` konksus crashloop'i silumisel.

Kui käitad latentsuse suhtes tundlikku repo-t (avalik veebirakendus, meil), on selle seisakuaeg piiratud oma peatus+käivitus ajaga (tavaliselt 30-90 s), mitte kogu käivituse pikkusega. Repo-d ajastatakse samaaegsuse pesadesse avastamise järjekorras; prioriteedijonot pole. Anna raskete repo-de jaoks oma `--include`-ulatusega strateegia, kui vajad täpsemat ajastamist.

### Pikalt kestvad varukopiad ja kattuvad ajakavad

Külm varukoopia, mis kestab kauem kui oma ajakava intervall (näiteks 500 GB repo esmane seemnestamine tagasihoidlikul lingil võib seaduslikult vajada üle 24 h, mille jooksul öine taimer uuesti käivitub), ei pane järjekorda ega käivita teist käivitust. Systemd `Type=oneshot` üksus on üksainus eksemplar: kui taimer käivitub ja teenus on juba `activating`, ühendab systemd käivituse olemasoleva tööga. Uut protsessi ei käivitata, ühtki käivitust ei panda järjekorda hiljem.

Konkreetselt näide, kus käivitus algab esmaspäeval kell 03:00 UTC ja lõpeb neljapäeval lõunal:

| Päev | 03:00 UTC käivitus | Tulemus |
|------|---------------|--------|
| Esmaspäev | Esimene käivitus | Käivitus algab |
| Teisipäev | Teine käivitus | Langetatakse vaikselt (eelmine käivitus on veel aktiivne) |
| Kolmapäev | Kolmas käivitus | Langetatakse vaikselt (eelmine käivitus on veel aktiivne) |
| Neljapäev | Käivitus lõpeb lõunal | Järelejõudmist pole; järgmine käivitus on reede kell 03:00 UTC |

Taimeri `Persistent=true` direktiiv **ei** päästa neid käivitusi. `Persistent=true` kordab käivitusi, mis jäid vahele, kuna taimer ise oli mitteaktiivne (süsteem väljas, taimer keelatud). Käivitused, mis langetati, kuna teenus oli hõivatud, on kadunud.

See vaikeväärtus on tahtlik. Kahe külma varukoopia paralleelne käivitamine sama andmesalve vastu konkureeriks külmutamisteel, üleslaadimisel ja repo-kohastel kõrvalfailidel asukohas `/var/run/rediacc/cold-backup-<guid>.status.json`. Töötava eksemplari taga ootamine on parem kui samu andmeid kahest suunast koormata. Andmesalve lukk jõustab seda: teine külm käivitus leiab luku hõivatuna ja lükatakse otsemaid tagasi, ilma et miski peatataks.

**Jälgimise tähendus.** Hangiv varukoopia (näiteks üleslaadimine, mis on kinni jäänud võrguaugu tõttu) langetab vaikselt kõik järgnevad taimeri käivitused. Ajastaja ei anna häiret. Jälgi `systemctl show <unit> -p ActiveEnterTimestamp`: kui teenus on olnud `activating` kauem kui oodatud käivituse pikkus (näiteks üle 48 h öösel taimeri puhul), uuri.

**Kui vajad iga ajastatud käivitust**, vaheta taimer `OnCalendar=<cron>` asemel `OnUnitInactiveSec=<interval>` peale. See käivitub N tundi pärast eelmise käivituse lõppu, mitte fikseeritud seinakella ajakava alusel, nii et pikad käivitused ei põhjusta langusi. Need lükkavad lihtsalt järgmist käivitust edasi. Kompromiss on ajakava drift: sinu 03:00 öine muutub "24 h pärast eelmise lõppu".

### Hetktõmmised, katkestused ja basseini ruum

Iga push töötab ajutise andmehoidla hetktõmmise põhjal, nii et üleslaaditud andmed on järjepidevad isegi siis, kui repositooriumid jätkavad kirjutamist. Varundamise ajal hoiab see hetktõmmis kõiki plokke, mida ta jagab elavate repositooriumidega: kustutamised ja [trimmimised](/et/docs/repositories#ruumi-tagasinõudmine-trim) vabastavad vähem basseiniruumi kuni tsükkel lõpeb ja hetktõmmis kustutatakse. [Salvestuse tervise raport](/et/docs/monitoring#salvestuse-tervis) näitab, kui palju ruumi varukoopia hetktõmmised parajasti kinni hoiavad.

Katkestused on ohutud. Teenuse peatamine (või masina taaskäivitamine) paneb varundamise oma ülekande katkestama ja hetktõmmise enne väljumist kustutama; järgmine ajastatud käivitus jätkab sealt, kus see pooleli jäi, kuna juba salvestatud rakke ei laadita uuesti üles. Kui protsess tapetakse liiga kõvasti puhastamiseks (toitekatkestus), tuvastatakse ja eemaldatakse orvuks jäänud hetktõmmis automaatselt salvestuse hooldaja poolt minutite jooksul.

### Strateegia määratlemine

Kanooniline vaikeväärtus on kahe strateegiaga jaotus: kiire tunnine hot-voog, mis hõlmab kõiki repo-sid, ja aeglasem iganädalane cold-voog, mis peatab konteinerid rakenduse-järjepidevate hetktõmmiste jaoks. Mõlemad kirjutavad samasse tükksalvestusse ja jagatud rakud salvestatakse üks kord, mitte iga voo kohta eraldi.

```bash
rdc backup strategy set hourly-hot \
  --destination rediacc \
  --cron "0 * * * *" \
  --mode hot \
  --bwlimit 20M \
  --enable
```

```bash
rdc backup strategy set weekly-cold \
  --destination rediacc \
  --cron "15 3 * * 0" \
  --mode cold \
  --include shop --include mail \
  --enable
```

`--destination <name>` nimetab sihtkoha strateegia sees; see on sinu valitud silt ja kirjeldab tükksalvestust. `--include` loetleb varundatavad repositooriumid ja selle kordamine lisab veel. Ära anna see ja strateegia katab iga repositooriumi andmesalves. Nimed vastavad kohaliku konfiguratsiooni repositooriumi nimele (ilma `:tag`-ita).

`--exclude` lükatakse tükksalvestuse sihtkoha puhul tagasi, selle asemel et vaikselt maha visata, sest aluseks olev `backup snapshot` valib repositooriume neid nimetades ega oma iseenda välistust. Selle austamine tähendaks nende repositooriumide varundamist, mille sa palusid välja jätta. Piiritle strateegia selle asemel `--include`-ga, nii et see, mida ajastatud käivitus katab, on kirja pandud, mitte tuletatud.

| Valik | Kirjeldus |
|--------|-------------|
| `<strategy>` (positsiooniline) | Strateegia nimi (kasutatakse masinaga sidumiseks) |
| `--destination <name>` | Sihtkoha nimi strateegia sees. Vaikimisi tükksalvestus |
| `--storage <name>` | Vali kaotatud rclone-sihtkoha liik. Seda kasutavat ajakava ei saa juurutada |
| `--cron <expression>` | Cron-avaldis (nt `"0 2 * * *"` päevaks kell 2) |
| `--mode <hot\|cold>` | Varundamisrežiim |
| `--bwlimit <limit>` | Ribalaiuse piirang üleslaadimiseks (nt `10M`) |
| `--include <repos>` | Selle strateegia kaetud repositooriumid (korratav) |
| `--exclude <repos>` | Vahelejäetavad repositooriumid (korratav). Tükksalvestuse sihtkoha puhul tagasi lükatud |
| `--folder <path>` | Alamkaust rclone-i bucketi sees. Tükksalvestuse sihtkoha puhul tagasi lükatud |
| `--enable` / `--disable` | Luba või keela strateegia |

### Strateegiate vaatamine

```bash
rdc backup strategy list
rdc backup strategy show weekly-cold
```

### Strateegia eemaldamine

```bash
rdc backup strategy remove weekly-cold
```

### Strateegiate sidumine masinaga

Strateegia, mis pole seotud ühegi masinaga, ei juuruta kunagi. Seo üks või mitu masinaga:

```bash
rdc backup strategy bind hourly-hot --machine hostinger
rdc backup strategy bind weekly-cold --machine hostinger
rdc backup strategy unbind weekly-cold --machine hostinger
```

Sidumine salvestatakse sinu konfiguratsioonis nimekirjana masinal, mida `rdc backup schedule` loeb, et otsustada, milliseid üksuseid juurutada:

```json
{
  "machines": {
    "hostinger": {
      "backupStrategies": ["hourly-hot", "weekly-cold"]
    }
  }
}
```

> **Sidumine on ainult kohalik konfiguratsioon.** Strateegia määratlemine ja masinaga sidumine ei muuda masinat. Käivitage `rdc backup schedule -m <machine>` (vt [Ajakava juurutamine masinale](#ajakava-juurutamine-masinale)), et juurutada systemd-taimerid, ja käivitage see uuesti pärast iga strateegia või sidumise muudatust.

## Kuuma ja külma valimine ning repositooriumipõhine filtreerimine

### Kuum vs külm lühidalt

| | Kuum | Külm |
|---|------|------|
| **Järjepidevus** | Krahhi-järjepidev (tõmmis külmutatud töötamise ajal) | Rakenduse-järjepidev (stop → hetktõmmis → start) |
| **Seisak** | Puudub | Repositooriumi kohane stop+start aken (tavaliselt 5-120 s) |
| **Sobiv sagedus** | Kõrge (nt tunnis) | Madal (nt iga päev või kord nädalas) |
| **Tüüpiline kasutus** | Sagedane turvavõrk | Ajastatud garanteeritud järjepidevusega varukoopia |

**Kuum** on kõrgsageduslike käivituste jaoks õige vaikevalik. Teenused jätkavad töötamist hetktõmmise tegemise ajal, nii et varundamisaken ei katkesta kasutajaid. Hetktõmmis on krahhi-järjepidev: see vastab sellele, mida saaksite pärast ebapuhast seiskamist. Enamiku kaasaegsete andmebaaside ja sõnumijärjekordade jaoks on see vastuvõetav.

**Külm** on asjakohane, kui vajate garanteeritud rakenduse-järjepidevat hetktõmmist ja saate lubada lühikest repositooriumi kohast taaskäivitust. Teenused peatatakse enne hetktõmmist ja taaskäivitatakse enne üleslaadimise algust, nii et aeglane või ebaõnnestunud üleslaadimine ei pikenda seisakuaknit kunagi. Täieliku garantiimudeli jaoks vaadake [Külma varundamise semantika](#kulma-varundamise-semantika).

Mõlemad režiimid kirjutavad samasse tükksalvestusse, ja režiim käib selle kohta, kuidas repositooriumi koheldakse, kui tõmmis on külmutatud, mitte selle kohta, kuhu andmed jõuavad. Repositoorium, mida katavad nii tunnine kuum kui iganädalane külm ajakava, salvestab jagatud rakud üks kord, mitte kaks korda.

### Repositooriumide piiritlemine strateegia järgi

Strateegia ilma `--include`-ta katab iga repositooriumi andmesalves. `--include` kordamine kitsendab seda repositooriumidele, mida sa nimetad, vastavuses kohaliku konfiguratsiooni repositooriuminimega (ilma `:tag`-ita).

```bash
# Kuum strateegia: varunda kõik tunnis
rdc backup strategy set hourly-hot \
  --destination rediacc \
  --cron "0 * * * *" \
  --mode hot \
  --bwlimit 6M \
  --enable

# Külm strateegia: nädalas, ja ainult repositooriumid, mida on vaja rahustada
rdc backup strategy set weekly-cold \
  --destination rediacc \
  --cron "15 3 * * 0" \
  --mode cold \
  --include shop --include mail \
  --enable
```

### Millal jätta repositoorium sagedasest kuumast strateegiast välja

Nimeta repositooriumid, mida soovid kõrgsageduslikus käivituses, selle asemel et lasta sel kõike võtta, kui:

- Repositoorium on suur ja **täielikult taasgenereeritav** köitel juba olevatest lähteandmetest, nii et iga tunnine varukoopia kulutab ribalaiust ilma taasteväärtust lisamata.
- Varundamise käivitamine ületaks oma ajakavaintervalli teie saadaoleval üleslaadimiskiirusel.

**Näide.** Repositoorium `analytics-demo` sisaldab ligikaudu 114 GB tuletatud Postgres-tabeleid, mida saab taastada samas köites juba salvestatud toorest CSV-dumpi failidest. 6 MB/s üleslaadimispiiriga võtab selle repositooriumi esimene hetktõmmis üle 5 tunni. Selle tunnine käivitamine tähendab, et iga käivitamine on veel pooleli, kui järgmine käivitub, mis põhjustab iga järgneva käivituse vaikse mahajätmise (vaadake [Pikalt kestvad varukopiad ja kattuvad ajakavad](#pikalt-kestvad-varukopiad-ja-kattuvad-ajakavad)). Teiste repositooriumide loetlemine `hourly-hot`-is ja `analytics-demo` jätmine `weekly-cold`-i jaoks tähendab, et see varundatakse kord nädalas mitte kunagi asemel.

> **Kui andmed on puhtalt taasgenereeritavad**, kaaluge, kas peate neid üldse varundama. Alternatiiviks on varundada ainult toorallikate sisendid (CSV-dumpid selles näites) ja jätta tuletatud koopia täielikult vahele. Toorallikate sisendite nädalane külm varukoopia on palju väiksem ja taaste jaoks täiesti piisav.

Repositoorium, mida katavad mõlemad strateegiad, saab tunnised krahhi-järjepidevad hetktõmmised ja ühe iganädalase rakenduse-järjepideva. `rdc backup manifests <repo>` näitab neid koos, ning nende jagatud rakud salvestatakse üks kord.

## Varundamistoimingud

### Ajakava juurutamine masinale

Lükka seotud strateegiad masinale systemd-taimeritena:

```bash
rdc backup schedule -m server-1
rdc backup schedule -m server-1 --dry-run
```

Juurutamine on oleku sobitaja. See loeb masinalt praegused üksuse failid ja systemd oleku, võrdleb konfiguratsioonist tuleneva vastu (SHA-256 faili kohta) ja puudutab ainult üksusi, mille sisu tegelikult muutus. Uuesti käivitamine ilma konfiguratsioonimuutusteta on no-op: pole kirjutusi, pole `daemon-reload`-i, pole taimeri müra.

`--dry-run` prindib plaani iga strateegia kohta (`created`, `updated (service, timer, env)`, `unchanged`, `removed`) ilma masinat puudutamata. Kombineeri `--debug`-iga, et printida ka genereeritud üksuse keha, kusjuures volitused on kustutatud. Tükksalvestuse üksus ei kanna neid algusest peale: masin autentib end oma allkirjastatud repositooriumi litsentsiga ja server annab tagasi lühiajalise õiguse, nii et midagi tundlikku ei kirjutata üksuse faili.

Kui strateegia, mida kavatsed uuendada või eemaldada, puhul on käimas varukoopia, ebaõnnestub juurutamine vihjega seda tühistada või `--force` kasutada. `--force`-ga hoiab käimasolev kutse oma mälu-üksust ja uus konfiguratsioon rakendub järgmisel taimeri taktil, nii et käimasolevat varundamist ei tapeta.

`--reset-failed` on valikuline. Kui see on antud, puhastab see systemd ebaõnnestunud oleku puudutatud teenustel pärast edukat juurutamist. Vaikimisi välja, et eelnevad tõrke-signaalid jäävad hoiatusele nähtavaks.

### Varukoopia kohe käivitamine

Käivita varukoopia koheselt ilma taimeri ootamiseta. Töötab isegi kui taimereid pole juurutatud, kasutades ad-hoc täitmiseks `systemd-run`-i:

```bash
rdc backup run -m server-1
rdc backup run weekly-cold -m server-1
```

### Varundamise oleku vaatamine

Näita varundamise taimerite praegust olekut ja hiljutisi töö tulemusi:

```bash
rdc backup status -m server-1
rdc backup status hourly-hot -m server-1
```

### Käimasoleva varundamise tühistamine

```bash
rdc backup cancel -m server-1
rdc backup cancel weekly-cold -m server-1
```

## Repositooriumi migreerimine

Liiguta repositoorium ühelt masinalt teisele:

```bash
rdc repo migrate my-app@server-1 --to server-2
```

| Valik | Kirjeldus |
|--------|-------------|
| `<ref>` (positsiooniline) | Teisaldatava hoidla viide; selle `@machine` osa määrab lähte |
| `--to <place>` | Sihtmasin või klaster |
| `--provision <provider>` | Sihtmasina automaatne provisioneerimine selle pilveteenuse pakkuja kaudu (nt `hetzner`, `linode`) |
| `--checkpoint` | Loo CRIU kontrollpunkt enne migreerimist, nii et ka protsessi mälu liigub kaasa |
| `--delta-base <guid>` | Muutumatu baas-GUID ülemineku delta jaoks. Vaikimisi esimese faasi baas |
| `--strategy <strategy>` | Plokk-delta strateegia ülemineku jaoks: `auto`, `physical` või `shared` |
| `--skip-dns` | Jäta DNS-kirjete uuendamine pärast migreerimist vahele |
| `--keep-source` | Säilita lähtetõmmised pärast edukat kolimist |
| `--bwlimit <limit>` | Ribalaiuse piirang ülekandele (nt `50M`) |

Migreerimine kannab krüpteeritud repositooriumi andmed üle rsync kaudu kahes faasis: massülekanne, samal ajal kui repositoorium jätkab tööd, seejärel lühike peatus delta jaoks. Migreerimine **liigutab** repositooriumi, seega kustutatakse lähtetõmmised pärast kolimise õnnestumist. Anna `--keep-source`, et need säilitada. See on erinevus `repo migrate` ja `repo push` vahel: push jätab lähte töötama ja puutumatuks.

## Enne kaotamist kirjutatud arhiivi lugemine

`rdc storage` on see, mis jäi rclone-harust järele, ja see on kirjutuskaitstud. See ei saa enam olla varunduse sihtkoht, kuid pääseb endiselt ligi arhiivile, mis kirjutati sinna.

```bash
# Registreeri remote, mille oled juba rclone jaoks konfigureerinud.
rdc storage import rclone.conf
rdc storage list

# Vaata, mis seal on. See käivitab sinu PATH-il oleva rclone'i.
rdc storage browse my-storage
```

`import` loeb rclone-konfiguratsioonifaili ja salvestab remote'id sinu konfiguratsiooni; toetatud tüübid on S3, B2, Google Drive, OneDrive, Mega, Dropbox, Box, Azure Blob ja Swift.

**`browse` vajab `rclone`-i sinu PATH-il.** See käivitab rclone'i, mis on paigaldatud masinasse, kus sa tipid; sisseehitatud koopiat enam ei ole. Ilma selleta ütleb see seda ega tee muud.

Salvestusliidesesse saatmine, sealt tõmbamine, selle loetlemine ja sellest taastamine on kaotatud; iga käsk keeldub ja nimetab tükksalvestuse käsu, mis selle asendab.

## Parimad praktikad

- Ajasta päevased külmad varukopiad kriitiliste andmete rakenduse-ühilduvate koopiate jaoks
- Kasuta kuumi hetktõmmiseid kõrgsageduslike käivituste jaoks, kus nullseisakuaeg on nõutav
- Testi taastamist perioodiliselt. `rdc backup restore --as <new-name>` ei kirjuta midagi üle, seega on harjutus elaval masinal ohutu
- Sea säilituspoliitika käsitsi kärpimise asemel, nii et hoitav aken on kirja pandud
- Hoia hetktõmmiste kõrval ka masina-masina koopiat, kui soovid koopiat riistvaral, mida sa kontrollid
- Hoia volitused turvaliselt; varukopiad on krüpteeritud, kuid LUKS-volitus on taastamiseks vajalik
