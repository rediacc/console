---
title: "Varundamine ja taastamine"
description: "Varunda krüpteeritud repositooriumeid kahel viisil: sisupõhiselt aadresseeritud tükksalvestusse, mis laadib üles ainult muutunud rakud, või täieliku push'iga mis tahes rclone-ühilduvasse salvestusse. Taasta mis tahes masinal ja automatiseeri nimetatud strateegiate ning systemd-taimerite abil."
category: "Guides"
order: 7
language: et
sourceHash: "c02ab3e78c40fa92"
sourceCommit: "522dceadb04b6a3e7f4ea60ac1e47308f6a1a600"
---

# Varundamine ja taastamine

Rediacc saab varundada krüpteeritud repositooriumeid väliste salvestusteenuste pakkujatele ja taastada neid samadel või erinevatel masinatel. Varukopiad on krüpteeritud; repositooriumi LUKS-volitus on taastamiseks vajalik.

## Kaks varundamisviisi

Rediacc'il on kaks sõltumatut varundamisviisi ja see juhend käsitleb mõlemat. Need kasutavad erinevat salvestust ja erinevaid käske, seega üht viisi kasutades varundatud repositoorium ei ole teise viisi kaudu varundatud.

**Tükksalvestus** (`rdc backup snapshot`) laadib repositooriumi tõmmise üles fikseeritud suurusega rakkudena, mis on aadresseeritud oma sisu järgi. Esimene käivitus laadib üles kogu nullist erineva sisu; iga järgnev käivitus laadib üles ainult muutunud rakud, mis otsustatakse failisüsteemi eraldusmetaandmete, mitte kogu tõmmise lugemise põhjal. Identsed rakud salvestatakse üks kord kõigi tõmmiste ja kogu forkide perekonna ulatuses, ning kasutust arvestatakse sinu salvestuskvoodi vastu (`rdc backup usage`).

**Salvestuse push on kaotatud.** `rdc repo push --to <storage>` kopeeris varem terve varufaili rclone-ühilduvasse teenusepakkujasse, mille registreerisid ise. rclone-haru on täielikult eemaldatud ning push, pull, list ja restore keelduvad nüüd salvestussihtmärgist ja suunavad sind siia. Masinalt masinale ülekanne jääb puutumata: see ei käinud kunagi rclone kaudu.

Taastamine tükksalvestusest toimib: `rdc backup restore <repo> --at <snapshot-id>` teostab salvestatud hetktõmmise, ja `--at` aktsepteerib ka RFC 3339 ajatempli, mis lahendatakse hetktõmmise inventuuri vastu. Lisage `--as <name>` taastamiseks erineva nimega ja `--up` repositooriumi pärast juurutamiseks. Tükksalvestus annab ka üleslaadimist (`rdc backup snapshot`), kinnitamist (`rdc backup verify`, ja `--deep` iga raku uuesti räsimiseks, mitte proovi asemel), hetktõmmiste inventuuri (`rdc backup manifests`) ja kvootide arvestust (`rdc backup usage`).

### Tükksalvestuse käsud

```bash
# Laadi tõmmis üles. Esimene käivitus külvab, hilisemad saadavad ainult muutunud rakud.
rdc backup snapshot my-app

# Planeeri ilma üles laadimata: näitab, mis liiguks.
rdc backup snapshot my-app --dry-run

# Ära usalda kohalikku ankrut ja laadi kogu sisu uuesti üles.
# See laadib kõik uuesti üles ja arvestab kvoodi uuesti; kasuta
# seda ainult siis, kui ankur on teadaolevalt vigane.
rdc backup snapshot my-app --reseed

# Kontrolli salvestatud sisu ja oma kvooti.
rdc backup verify my-app
rdc backup manifests my-app
rdc backup usage
```

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

## Salvestuse seadistamine

Enne varukoopiaid, registreeri salvestusteenuse pakkuja. Rediacc toetab mis tahes rclone-ühilduvat salvestust: S3, B2, Google Drive ja palju muud.

### Importimine rclone'ist

Kui sul on juba rclone-kaughoidla konfigureeritud:

```bash
rdc storage import rclone.conf
```

See impordib salvestuskonfiguratsioone rclone-konfiguratsioonifailist praegusesse konfiguratsiooni. Toetatud tüübid: S3, B2, Google Drive, OneDrive, Mega, Dropbox, Box, Azure Blob ja Swift.

### Salvestuste vaatamine

```bash
rdc storage list
```

## Varukoopia saatmine teise masinasse

Kopeeri repositoorium SSH kaudu teise masinasse:

```bash
rdc repo push my-app --to-machine server-1
```

Krüpteeritud tõmmis kopeeritakse SAMA GUID-iga, seega on tegu varukoopia või migratsiooniga, mitte fork'iga. Sõltumatu koopia saamiseks käivita kõigepealt `rdc repo fork` ja saada fork.

Kindla ajahetke varundamiseks kasuta selle asemel tükksalvestust: `rdc backup snapshot my-app` laadib üles ainult muutunud rakud ning `rdc backup restore my-app --at <snapshot>` toob need tagasi.

| Valik | Kirjeldus |
|--------|-------------|
| `--to-machine <machine>` | Sihtmasin masina-masina varundamiseks |
| `--dest <filename>` | Kohandatud sihtfaili nimi |
| `--checkpoint` | Loob CRIU kontrollpunkti enne saatmist (konteineritele, millel on silt `rediacc.checkpoint=true`). Sihtmärk taastab automaatselt käsuga `repo up` |
| `--force` | Kirjuta olemasolev varukoopia üle |
| `--bwlimit <limit>` | Ribalaiuse piirang rsync-ülekandele (nt `10M`, `500K`) |
| `--tag <tag>` | Märgista varukoopia |
| `-w, --watch` | Jälgi toimingu edenemist |
| `--debug` | Luba detailne väljund |
| `--skip-router-restart` | Jäta marsruudiserverit pärast toimingut taaskäivitamata |

## Varukoopia tõmbamine teisest masinast

Too repositoorium tagasi masinast, kus see asub:

```bash
rdc repo pull my-app --from-machine server-1
```

Tükksalvestusest taastamiseks kasuta selle asemel käsku
`rdc backup restore my-app --at <snapshot-id>`.

Pull keeldub üle kirjutamast repositooriumi, mis on hetkel **ühendatud**. Ühenda see kõigepealt lahti, tee pull ja too see siis tagasi käsuga `rdc repo up`. Kaustapõhised repositooriumid on erand: need sünkroonivad end kohapeal ka ühendatuna.

| Valik | Kirjeldus |
|--------|-------------|
| `--from-machine <machine>` | Lähtemašin masina-masina taastamiseks |
| `--force` | Kirjuta olemasolev kohalik varukoopia üle |
| `--bwlimit <limit>` | Ribalaiuse piirang rsync-ülekandele (nt `10M`, `500K`) |
| `-w, --watch` | Jälgi toimingu edenemist |
| `--debug` | Luba detailne väljund |
| `--skip-router-restart` | Jäta marsruudiserverit pärast toimingut taaskäivitamata |

## Varukoopiote loetlemine

Loetle tükksalvestuses olevad hetktõmmised:

```bash
rdc backup snapshot list my-app
```

Masinal olevate varunduskoopiate nägemiseks:

```bash
rdc backup list -m server-1
```

Väljund on ühtne tabel, mis ühendab mõlemad [ajastatud varundamise kaustad](#ajastatud-varundamine) (`hot/` ja `cold/`), et näeksid kõiki varukoopiad ühes vaates:

| Veerg | Tähendus |
|---|---|
| `Mode` | `hot` või `cold`. Milline ajastatud varundamise kaust see kirje asub |
| `Name` | Repositooriumi nimi, mis on lahendatud sinu kohalikust konfiguratsioonist (langeb tagasi GUID-ile repo-de puhul, mida konfiguratsioonis pole) |
| `GUID` | Kettal olev repositooriumi GUID |
| `Size` | Inimloetav varukoopifaili suurus |
| `Modified` | UTC ajatempel salvestusteenuse pakkujalt |

Salvestusliidese loetlemine on kaotatud koos rclone-haruga; käsk keeldub ja nimetab need kaks asendust.

### Salvestuse paigutus

Ajastatud varukopiad maanduvad salvestuse konfigureeritud kausta sees režiimipõhistes alamkaustades, nii et sama salvestus majutab puhtalt nii tunniset kui iganädalast voogu, ilma et need seguneksid:

```text
<bucket>/<folder>/
├── hot/
│   ├── <guid-1>
│   ├── <guid-2>
│   └── ...
└── cold/
    ├── <guid-1>
    ├── <guid-3>
    └── ...
```

Repo võib ilmuda nii `hot/` kui ka `cold/` kaustas (tunnine ajakava teeb sellest hetktõmmise; iganädalane ajakava teeb uuesti). Ühendatud loend näitab mõlemat rida, nii et on selge, millised vood milliseid repo-sid katavad.

## Sünkroniseeri üks repositoorium korraga

Push ja pull toimivad korraga ühe repositooriumi peal, mis on adresseeritud viitega (`name`, `name:tag` või `name@machine`). Vormi "kõik repositooriumid korraga" ei ole: käivita käsk iga repositooriumi jaoks eraldi.

### Saada teise masinasse

```bash
rdc repo push shop@server-1 --to-machine server-2
```

### Tõmba teisest masinast

```bash
rdc repo pull shop@server-1 --from-machine server-2
```

| Valik | Kirjeldus |
|--------|-------------|
| `--to-machine <machine>` | Sihtmasin masina-masina saatmiseks |
| `--from-machine <machine>` | Lähtemašin masina-masina tõmbamiseks |
| `--force` | Kirjuta olemasolev varukoopia või repositoorium üle |
| `--checkpoint` | Loo enne saatmist CRIU kontrollpunkt (ainult saatmine) |
| `--up` | Ühenda ja juuruta repositoorium pärast tõmbamist (ainult tõmbamine) |
| `--bwlimit <limit>` | Ribalaiuse piirang rsync-ülekandele (nt `10M`) |
| `--delta-base <guid>` | Kanna üle ainult muutunud plokid võrreldes muutumatu baas-GUID-iga |
| `--debug` | Luba detailne väljund |
| `--skip-router-restart` | Jäta marsruudiserverit pärast toimingut taaskäivitamata |

## Ajastatud varundamine

Rediacc kasutab nimetatud varundamisstrateegiaid. Iga strateegia määratleb ajakava, varundamisrežiimi, valikulise ribalaiuse piirangu ja failifiltrid. Masinad viitavad strateegiatele nimede järgi, et määrata, millised varukopiad neil käitatakse.

### Varundamisrežiimid

| Režiim | Käitumine | Seisakuaeg |
|------|----------|----------|
| `hot` | BTRFS-hetktõmmis võetakse teenuste töötamise ajal (krahhi-ühilduvalt) | Puudub |
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
- Logid renet-i varundamiskäivitusest (`journalctl -u renet-*` või otsene `rdc backup schedule` kutse) väljastavad lõplik kokkuvõtterida kujul `Cold backup: post-snapshot restart summary total=N compose_ok=N fallback_ok=N failed=N failed_repos=[...]`. Mittevühi `failed_repos` on grep-sihtmärk.

### Külma varundamise seisakuaja hindamine

Iga repo on maas ainult oma `down()` + `up()` akna jooksul. Soojal hostil on need tavaliselt:

| Repo kuju | Tüüpiline peatus+käivitus |
|------------|--------------------|
| Väike (1-2 konteinerit, ilma DB-ta) | 5-15 s |
| Keskmine (veebirakendus + vahemälu) | 20-45 s |
| Raske (DB + järjekorrad + meil) | 60-120 s |

Hetktõmmise samm (`btrfs subvolume snapshot -r`) on O(1) olenemata repo suurusest: 0,1-1 s. Repo ei ole maas teiste repo-de hetktõmmiste tõttu. Laadija käivitatakse siis kirjutuskaitstud hetktõmmise vastu, samal ajal kui kõik repo-d on juba jälle üleval.

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

Kui käitad latentsuse suhtes tundlikku repo-t (avalik veebirakendus, meil), on selle seisakuaeg piiratud oma peatus+käivitus ajaga (tavaliselt 30-90 s), mitte kogu käivituse pikkusega. Repo-d ajastatatakse samaaegsuse slottidesse avastamise järjekorras; prioriteedijonot pole. Jaga rasked repo-d oma `--exclude`-ulatusega strateegiatesse, kui vajad täpsemat ajastamist.

### Pikalt kestvad varukopiad ja kattuvad ajakavad

Külm varukoopia, mis kestab kauem kui oma ajakava intervall (näiteks 500 GB repo esmane seemnestamine tagasihoidlikul lingil võib seaduslikult vajada üle 24 h, mille jooksul öine taimer uuesti käivitub), ei pane järjekorda ega käivita teist käivitust. Systemd `Type=oneshot` üksus on üksainus eksemplar: kui taimer käivitub ja teenus on juba `activating`, ühendab systemd käivituse olemasoleva tööga. Uut protsessi ei käivitata, ühtki käivitust ei panda järjekorda hiljem.

Konkreetselt näide, kus käivitus algab esmaspäeval kell 03:00 UTC ja lõpeb neljapäeval lõunal:

| Päev | 03:00 UTC käivitus | Tulemus |
|------|---------------|--------|
| Esmaspäev | Esimene käivitus | Käivitus algab |
| Teisipäev | Teine käivitus | Langetatakse vaikselt (eelmine käivitus on veel aktiivne) |
| Kolmapäev | Kolmas käivitus | Langetatakse vaikselt (eelmine käivitus on veel aktiivne) |
| Neljapäev | Käivitus lõpeb lõunal | Järelehoiavat käivitust pole; järgmine käivitus on reede kell 03:00 UTC |

Taimeri `Persistent=true` direktiiv **ei** päästa neid käivitusi. `Persistent=true` kordab käivitusi, mis jäid vahele, kuna taimer ise oli mitteaktiivne (süsteem väljas, taimer keelatud). Käivitused, mis langetati, kuna teenus oli hõivatud, on kadunud.

See vaikeväärtus on tahtlik. Kahe külma varukoopia paralleelne käivitamine sama andmesalve vastu konkureeriks BTRFS-hetktõmmise teel, rclone-kaughoidlal ja repo-kohastele kõrvalfailidel asukohas `/var/run/rediacc/cold-backup-<guid>.status.json`. Pikalt kestava eksemplari taga serialiseerimine on turvaline tulemus.

**Jälgimise tähendus.** Hangiv varukoopia (näiteks rclone, mis on kinni jäänud võrguaugu tõttu) langetab vaikselt kõik järgnevad taimeri käivitused. Ajastaja ei anna häiret. Jälgi `systemctl show <unit> -p ActiveEnterTimestamp`: kui teenus on olnud `activating` kauem kui oodatud käivituse pikkus (näiteks üle 48 h öösel taimeri puhul), uuri.

**Kui vajad iga ajastatud käivitust**, vaheta taimer `OnCalendar=<cron>` asemel `OnUnitInactiveSec=<interval>` peale. See käivitub N tundi pärast eelmise käivituse lõppu, mitte fikseeritud seinakella ajakava alusel, nii et pikad käivitused ei põhjusta langusi. Need lükkavad lihtsalt järgmist käivitust edasi. Kompromiss on ajakava drift: sinu 03:00 öine muutub "24 h pärast eelmise lõppu".

### Hetktõmmised, katkestused ja basseini ruum

Iga push töötab ajutise andmehoidla hetktõmmise põhjal, nii et üleslaaditud andmed on järjepidevad isegi siis, kui repositooriumid jätkavad kirjutamist. Varundamise ajal hoiab see hetktõmmis kõiki plokke, mida ta jagab elavate repositooriumidega: kustutamised ja [trimmimised](/et/docs/repositories#ruumi-tagasinõudmine-trim) vabastavad vähem basseiniruumi kuni tsükkel lõpeb ja hetktõmmis kustutatakse. [Salvestuse tervise raport](/et/docs/monitoring#salvestuse-tervis) näitab, kui palju ruumi varukoopia hetktõmmised parajasti kinni hoiavad.

Katkestused on ohutud. Teenuse peatamine (või masina taaskäivitamine) paneb varundamise oma ülekande katkestama ja hetktõmmise enne väljumist kustutama; järgmine ajastatud käivitus jätkab sealt, kus see pooleli jäi, kuna muutmata failid jäetakse kontrollsumma alusel vahele. Kui protsess tapetakse liiga kõvasti puhastamiseks (toitekatkestus), tuvastatakse ja eemaldatakse orvuks jäänud hetktõmmis automaatselt salvestuse hooldaja poolt minutite jooksul.

### Strateegia määratlemine

Kanooniline vaikeväärtus on kahe strateegiaga jaotus: kiire tunnine hot-voog, mis hõlmab kõiki repo-sid, ja aeglasem iganädalane cold-voog, mis teeb rakenduse-ühilduvaid hetktõmmiseid. Kaks strateegiat kirjutavad erinevatesse salvestuse alamkaustadesse (`hot/` ja `cold/`), nii et varukopiad ei segune kunagi.

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
  --exclude very-large-repo \
  --enable
```

`--exclude` filter külma strateegia puhul on soovitatav pääsetee väga suurte repo-de jaoks, mis ei mahu sinu iganädalasesse hooldusaknasse. Tunnine hot-strateegia katab neid ikka; cold lihtsalt jätab vahele. Repo-nimed `--exclude` valikutes vastavad kohaliku konfiguratsiooni repo-nimele (ilma `:tag`-ita).

| Valik | Kirjeldus |
|--------|-------------|
| `<strategy>` (positsiooniline) | Strateegia nimi (kasutatakse masinaga sidumiseks) |
| `--destination <storage>` | Salvestusteenuse pakkuja üleslaadimiseks |
| `--cron <expression>` | Cron-avaldis (nt `"0 2 * * *"` päevaks kell 2) |
| `--mode <hot\|cold>` | Varundamisrežiim |
| `--bwlimit <limit>` | Ribalaiuse piirang üleslaadimiseks (nt `10M`) |
| `--include <pattern>` | Kaasamisfilter (korratav) |
| `--exclude <pattern>` | Välistusfilter (korratav) |
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

Oma konfiguratsioonis seo üks või mitu strateegianime masinaga:

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
| **Järjepidevus** | Krahhi-järjepidev (BTRFS-i hetktõmmis käitamise ajal) | Rakenduse-järjepidev (stop → hetktõmmis → start) |
| **Seisak** | Puudub | Repositooriumi kohane stop+start aken (tavaliselt 5-120 s) |
| **Sobiv sagedus** | Kõrge (nt tunnis) | Madal (nt iga päev või kord nädalas) |
| **Tüüpiline kasutus** | Sagedane turvavõrk | Ajastatud garanteeritud järjepidevusega varukoopia |

**Kuum** on kõrgsageduslike käivituste jaoks õige vaikevalik. Teenused jätkavad töötamist hetktõmmise tegemise ajal, nii et varundamisaken ei katkesta kasutajaid. Hetktõmmis on krahhi-järjepidev: see vastab sellele, mida saaksite pärast ebapuhast seiskamist. Enamiku kaasaegsete andmebaaside ja sõnumijärjekordade jaoks on see vastuvõetav.

**Külm** on asjakohane, kui vajate garanteeritud rakenduse-järjepidevat hetktõmmist ja saate lubada lühikest repositooriumi kohast taaskäivitust. Teenused peatatakse enne hetktõmmist ja taaskäivitatakse enne üleslaadimise algust, nii et aeglane või ebaõnnestunud üleslaadimine ei pikenda seisakuaknit kunagi. Täieliku garantiimudeli jaoks vaadake [Külma varundamise semantika](#kulma-varundamise-semantika).

### Repositooriumide filtreerimine strateegia järgi

Igal strateegial võivad olla `--include` ja `--exclude` filtrid. Repositooriumide nimed, mis vastavad `--exclude` mustrile, jäetakse selle strateegia puhul vahele; `--include` piirab käivitamist ainult nende nimedega. Filtrid vastavad kohaliku konfiguratsiooni repositooriuminimele (ilma `:tag`-ita).

```bash
# Kuum strateegia: varundage kõik tunnis
rdc backup strategy set hourly-hot \
  --destination rediacc \
  --cron "0 * * * *" \
  --mode hot \
  --bwlimit 6M \
  --enable

# Külm strateegia: varundage kõik nädalas, välja arvatud suur tuletatud andmestik
rdc backup strategy set weekly-cold \
  --destination rediacc \
  --cron "15 3 * * 0" \
  --mode cold \
  --exclude analytics-demo \
  --enable
```

### Millal jätta repositoorium kõrgsagedusliku kuuma strateegia vahele

Jätke repositoorium kõrgsageduslikust käivitamisest välja, kui:

- Repositoorium on suur ja **täielikult taasgenereeritav** köitel juba olevatest lähteandmetest, nii et iga tunnine varukoopia raiskab märkimisväärset ribalaiust ilma sisukaid taasteandmeid lisamata.
- Varundamise käivitamine ületaks oma ajakavaintervallit teie saadaoleval üleslaadimiskiirusel.

**Näide.** Repositoorium `analytics-demo` sisaldab ligikaudu 114 GB tuletatud Postgres-tabeleid, mida saab täielikult taastada samas köites juba salvestatud toorest CSV-dumpi failidest. 6 MB/s üleslaadimispiiriga võtab selle repositooriumi üks kuum varukoopia üle 5 tunni. Selle tunnine käivitamine tähendab, et iga käivitamine on veel pooleli, kui järgmine käivitub, mis põhjustab iga järgneva käivitamise vaikse mahajätmise (vaadake [Pikalt kestvad varukopiad ja kattuvad ajakavad](#pikalt-kestvad-varukopiad-ja-kattuvad-ajakavad)). Selle jätmine `hourly-hot`-ist välja ja hoidmine `weekly-cold`-is tähendab, et see varundatakse kord nädalas mitte kunagi asemel.

> **Kui andmed on puhtalt taasgenereeritavad**, kaaluge, kas peate neid üldse varundama. Alternatiiviks on varundada ainult toorallikate sisendid (CSV-dumpid selles näites) ja jätta tuletatud koopia täielikult vahele. Toorallikate sisendite nädalane külm varukoopia on palju väiksem ja taaste jaoks täiesti piisav.

Repositooriumid, mis ei ole kummastki strateegiast välja jäetud, ilmuvad mõlemas salvestuse alamkaustas `hot/` ja `cold/`. `rdc backup list` ühendatud väljund näitab mõlemat rida, nii et saate kontrollida, millised vood milliseid repositooriumeid katavad.

## Varundamistoimingud

### Ajakava juurutamine masinale

Lükka seotud strateegiad masinale systemd-taimeritena:

```bash
rdc backup schedule -m server-1
rdc backup schedule -m server-1 --dry-run
```

Juurutamine on oleku sobitaja. See loeb masinalt praegused üksuse failid ja systemd oleku, võrdleb konfiguratsioonist tuleneva vastu (SHA-256 faili kohta) ja puudutab ainult üksusi, mille sisu tegelikult muutus. Uuesti käivitamine ilma konfiguratsioonimuutusteta on no-op: pole kirjutusi, pole `daemon-reload`-i, pole taimeri müra.

`--dry-run` prindib plaani iga strateegia kohta (`created`, `updated (service, timer, env)`, `unchanged`, `removed`) ilma masinat puudutamata. Kombineeri `--debug`-iga, et printida ka genereeritud üksuse keha; rclone-tokenid on redakteeritud.

Kui strateegia, mida kavatsed uuendada või eemaldada, puhul on käimas varukoopia, ebaõnnestub juurutamine vihjega seda tühistada või `--force` kasutada. `--force`-ga hoiab käimasolev kutse oma mälu-üksust ja uus konfiguratsioon rakendub järgmisel taimeri taktil, nii et käimasolevat varundamist ei tappa.

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
| `--provision` | Provisiona repositoorium sihtmasinat enne ülekandmist |
| `--checkpoint` | Loo CRIU kontrollpunkt enne migreerimist |
| `--skip-dns` | Jäta DNS-kirjete uuendamine pärast migreerimist vahele |
| `--bwlimit <limit>` | Ribalaiuse piirang ülekandele (nt `50M`) |

Migreerimine kannab krüpteeritud repositooriumi andmed üle rsync kaudu. Lähte-repositoorium jääb puutumatuks kuni selle eksplitsiitse eemaldamiseni.

## Salvestuse sirvimine

`rdc storage browse` ja `rdc storage import` on erand sellest kaotamisest: need käivitavad sinu enda rclone'i PATH-ist, mitte sisseehitatud koopiat, ja jäävad viisiks lugeda arhiivi, mis on kirjutatud enne muudatust.

```bash
rdc storage browse my-storage
```

Sirvimine on ainult lugemiseks. Salvestusliidesesse saatmine, sealt tõmbamine ja selle loetlemine on kaotatud; iga käsk keeldub ja nimetab tükksalvestuse käsu, mis selle asendab.

## Parimad praktikad

- Ajasta päevased külmad varukopiad kriitiliste andmete rakenduse-ühilduvate hetktõmmiste jaoks
- Kasuta kuumi varukoopiad sagedaste hetktõmmiste jaoks, kus nullseisakuaeg on nõutav
- Testi taastamist perioodiliselt varukoopia terviklikkuse kontrollimiseks
- Kasuta kriitiliste andmete jaoks mitut salvestusteenuse pakkujat (nt S3 + B2)
- Hoia volitused turvaliselt; varukopiad on krüpteeritud, kuid LUKS-volitus on taastamiseks vajalik
