---
title: "Varundamine ja taastamine"
description: "Varunda krüpteeritud repositooriumeid mis tahes rclone-ühilduvasse salvestusse, taasta neid mis tahes masinal ja automatiseeri varundamine nimetatud strateegiate ja systemd-taimerite abil."
category: "Guides"
order: 7
language: et
sourceHash: "e241aa122868e629"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# Varundamine ja taastamine

Rediacc saab varundada krüpteeritud repositooriumeid väliste salvestusteenuste pakkujatele ja taastada neid samadel või erinevatel masinatel. Varukopiad on krüpteeritud; repositooriumi LUKS-volitus on taastamiseks vajalik.

## Salvestuse seadistamine

Enne varukoopiaid, registreeri salvestusteenuse pakkuja. Rediacc toetab mis tahes rclone-ühilduvat salvestust: S3, B2, Google Drive ja palju muud.

### Importimine rclone'ist

Kui sul on juba rclone-kaughoidla konfigureeritud:

```bash
rdc config storage import --file rclone.conf
```

See impordib salvestuskonfiguratsioone rclone-konfiguratsioonifailist praegusesse konfiguratsiooni. Toetatud tüübid: S3, B2, Google Drive, OneDrive, Mega, Dropbox, Box, Azure Blob ja Swift.

### Salvestuste vaatamine

```bash
rdc config storage list
```

## Varukoopia saatmine

Saada repositooriumi varukoopia välisesse salvestusse:

```bash
rdc repo push --name my-app -m server-1 --to my-storage
```

Push kontrollib alati enne kirjutamist, kas siht-repositoorium on ühendatud. Kui see pole ühendatud, katkestatakse toiming.

| Valik | Kirjeldus |
|--------|-------------|
| `--to <storage>` | Sihtmärk salvestuskoht |
| `--to-machine <machine>` | Sihtmasin masina-masina varundamiseks |
| `--dest <filename>` | Kohandatud sihtfaili nimi |
| `--checkpoint` | Loob CRIU kontrollpunkti enne saatmist (konteineritele, millel on silt `rediacc.checkpoint=true`). Sihtmärk taastab automaatselt käsuga `repo up` |
| `--force` | Kirjuta olemasolev varukoopia üle |
| `--bwlimit <limit>` | Ribalaiuse piirang rsync-ülekandele (nt `10M`, `500K`) |
| `--tag <tag>` | Märgista varukoopia |
| `-w, --watch` | Jälgi toimingu edenemist |
| `--debug` | Luba detailne väljund |
| `--skip-router-restart` | Jäta marsruudiserverit pärast toimingut taaskäivitamata |

## Varukoopia tõmbamine / taastamine

Tõmba repositooriumi varukoopia välisest salvestusest:

```bash
rdc repo pull --name my-app -m server-1 --from my-storage
```

Pull kontrollib alati enne kirjutamist, kas siht-repositoorium on ühendatud. Kui see pole ühendatud, katkestatakse toiming.

| Valik | Kirjeldus |
|--------|-------------|
| `--from <storage>` | Lähtesalvestuskoht |
| `--from-machine <machine>` | Lähtemašin masina-masina taastamiseks |
| `--force` | Kirjuta olemasolev kohalik varukoopia üle |
| `--bwlimit <limit>` | Ribalaiuse piirang rsync-ülekandele (nt `10M`, `500K`) |
| `-w, --watch` | Jälgi toimingu edenemist |
| `--debug` | Luba detailne väljund |
| `--skip-router-restart` | Jäta marsruudiserverit pärast toimingut taaskäivitamata |

## Varukoopiote loetlemine

Vaata salvestuskohas saadaolevaid varukoopiad:

```bash
rdc repo backup list --from my-storage -m server-1
```

Väljund on ühtne tabel, mis ühendab mõlemad [ajastatud varundamise kaustad](#ajastatud-varundamine) (`hot/` ja `cold/`), et näeksid kõiki varukoopiad ühes vaates:

| Veerg | Tähendus |
|---|---|
| `Mode` | `hot` või `cold`. Milline ajastatud varundamise kaust see kirje asub |
| `Name` | Repositooriumi nimi, mis on lahendatud sinu kohalikust konfiguratsioonist (langeb tagasi GUID-ile repo-de puhul, mida konfiguratsioonis pole) |
| `GUID` | Kettal olev repositooriumi GUID |
| `Size` | Inimloetav varukoopifaili suurus |
| `Modified` | UTC ajatempel salvestusteenuse pakkujalt |

Ühe režiimis süvitsi minekuks kasuta `--path`:

```bash
rdc repo backup list --from my-storage -m server-1 --path hot
rdc repo backup list --from my-storage -m server-1 --path cold
```

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

## Masstihkroniseerimine

Saada või tõmba kõik repositooriumid korraga:

### Saada kõik salvestusse

```bash
rdc repo push --to my-storage -m server-1
```

### Tõmba kõik salvestusest

```bash
rdc repo pull --from my-storage -m server-1
```

| Valik | Kirjeldus |
|--------|-------------|
| `--to <storage>` | Sihtmärk salvestus (saatmise suund) |
| `--from <storage>` | Lähtesalvestus (tõmbamise suund) |
| `--repo <name>` | Sünkroniseeri konkreetsed repositooriumid (korratav) |
| `--override` | Kirjuta olemasolevad varukopiad üle |
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

- `rdc machine query --name <machine> --containers` näitab töötavat olekut. Võrdle oodatud hulgaga.
- `/var/run/rediacc/cold-backup-<guid>.status.json` masinas. Vaata seda käsuga `rdc term connect -m <machine> -r <repo> -c "cat /var/run/rediacc/cold-backup-$GUID.status.json"`. `success: false` koos vana `startedAt`-ga tähendab, et viimane varukoopia ei lõppenud puhtalt.
- Logid renet-i varundamiskäivitusest (`journalctl -u renet-*` või otsene `rdc machine backup schedule` kutse) väljastavad lõplik kokkuvõtterida kujul `Cold backup: post-snapshot restart summary total=N compose_ok=N fallback_ok=N failed=N failed_repos=[...]`. Mittevühi `failed_repos` on grep-sihtmärk.

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
rdc config backup-strategy set \
  --name hourly-hot \
  --destination my-storage \
  --cron "0 * * * *" \
  --mode hot \
  --bwlimit 20M \
  --enable
```

```bash
rdc config backup-strategy set \
  --name weekly-cold \
  --destination my-storage \
  --cron "15 3 * * 0" \
  --mode cold \
  --exclude very-large-repo \
  --enable
```

`--exclude` filter külma strateegia puhul on soovitatav pääsetee väga suurte repo-de jaoks, mis ei mahu sinu iganädalasesse hooldusaknasse. Tunnine hot-strateegia katab neid ikka; cold lihtsalt jätab vahele. Repo-nimed `--exclude` valikutes vastavad kohaliku konfiguratsiooni repo-nimele (ilma `:tag`-ita).

| Valik | Kirjeldus |
|--------|-------------|
| `--name <name>` | Strateegia nimi (kasutatakse masina sidumiseks) |
| `--destination <storage>` | Salvestusteenuse pakkuja üleslaadimiseks |
| `--cron <expression>` | Cron-avaldis (nt `"0 2 * * *"` päevaks kell 2) |
| `--mode <hot\|cold>` | Varundamisrežiim |
| `--bwlimit <limit>` | Ribalaiuse piirang üleslaadimiseks (nt `10M`) |
| `--include <pattern>` | Kaasamisfilter (korratav) |
| `--exclude <pattern>` | Välistusfilter (korratav) |
| `--enable` / `--disable` | Luba või keela strateegia |

### Strateegiate vaatamine

```bash
rdc config backup-strategy list
rdc config backup-strategy show --name weekly-cold
```

### Strateegia eemaldamine

```bash
rdc config backup-strategy remove --name weekly-cold
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

> **Sidumine on ainult kohalik konfiguratsioon.** Strateegia määratlemine ja masinaga sidumine ei muuda masinat. Käivitage `rdc machine backup schedule -m <machine>` (vt [Ajakava juurutamine masinale](#ajakava-juurutamine-masinale)), et juurutada systemd-taimerid, ja käivitage see uuesti pärast iga strateegia või sidumise muudatust.

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
rdc config backup-strategy set \
  --name hourly-hot \
  --destination my-storage \
  --cron "0 * * * *" \
  --mode hot \
  --bwlimit 6M \
  --enable

# Külm strateegia: varundage kõik nädalas, välja arvatud suur tuletatud andmestik
rdc config backup-strategy set \
  --name weekly-cold \
  --destination my-storage \
  --cron "15 3 * * 0" \
  --mode cold \
  --exclude analytics-demo \
  --enable
```

### Millal jätta repositoorium kõrgsagedusliku kuuma strateegia vahele

Jätage repositoorium kõrgsageduslikust käivitamisest välja, kui:

- Repositoorium on suur ja **täielikult taasgenereeritav** köitel juba olevatest lähteandmetest, nii et iga tunnine varukoopia raiskab märkimisväärset ribalaiust ilma sisukaid taasteandmeid lisamata.
- Varundamise käivitamine ületaks oma ajakavaintervallit teie saadaoleval üleslaadimiskiirusel.

**Näide.** Repositoorium `analytics-demo` sisaldab ligikaudu 114 GB tuletatud Postgres-tabeleid, mida saab täielikult taastada samas köites juba salvestatud toorest CSV-dumpi failidest. 6 MB/s üleslaadimispiiriga võtab selle repositooriumi üks kuum varukoopia üle 5 tunni. Selle tunnine käivitamine tähendab, et iga käivitamine on veel pooleli, kui järgmine käivitub, mis põhjustab iga järgneva käivitamise vaikse mahajätmise (vaadake [Pikalt kestvad varukopiad ja kattuvad ajakavad](#pikalt-kestvad-varukopiad-ja-kattuvad-ajakavad)). Selle jätmine `hourly-hot`-ist välja ja hoidmine `weekly-cold`-is tähendab, et see varundatakse kord nädalas mitte kunagi asemel.

> **Kui andmed on puhtalt taasgenereeritavad**, kaaluge, kas peate neid üldse varundama. Alternatiiviks on varundada ainult toorallikate sisendid (CSV-dumpid selles näites) ja jätta tuletatud koopia täielikult vahele. Toorallikate sisendite nädalane külm varukoopia on palju väiksem ja taaste jaoks täiesti piisav.

Repositooriumid, mis ei ole kummastki strateegiast välja jäetud, ilmuvad mõlemas salvestuse alamkaustas `hot/` ja `cold/`. `rdc repo backup list` ühendatud väljund näitab mõlemat rida, nii et saate kontrollida, millised vood milliseid repositooriumeid katavad.

## Varundamistoimingud

### Ajakava juurutamine masinale

Lükka seotud strateegiad masinale systemd-taimeritena:

```bash
rdc machine backup schedule -m server-1
rdc machine backup schedule -m server-1 --dry-run
```

Juurutamine on oleku sobitaja. See loeb masinalt praegused üksuse failid ja systemd oleku, võrdleb konfiguratsioonist tuleneva vastu (SHA-256 faili kohta) ja puudutab ainult üksusi, mille sisu tegelikult muutus. Uuesti käivitamine ilma konfiguratsioonimuutusteta on no-op: pole kirjutusi, pole `daemon-reload`-i, pole taimeri müra.

`--dry-run` prindib plaani iga strateegia kohta (`created`, `updated (service, timer, env)`, `unchanged`, `removed`) ilma masinat puudutamata. Kombineeri `--debug`-iga, et printida ka genereeritud üksuse keha; rclone-tokenid on redakteeritud.

Kui strateegia, mida kavatsed uuendada või eemaldada, puhul on käimas varukoopia, ebaõnnestub juurutamine vihjega seda tühistada või `--force` kasutada. `--force`-ga hoiab käimasolev kutse oma mälu-üksust ja uus konfiguratsioon rakendub järgmisel taimeri taktil, nii et käimasolevat varundamist ei tappa.

`--reset-failed` on valikuline. Kui see on antud, puhastab see systemd ebaõnnestunud oleku puudutatud teenustel pärast edukat juurutamist. Vaikimisi välja, et eelnevad tõrke-signaalid jäävad hoiatusele nähtavaks.

### Varukoopia kohe käivitamine

Käivita varukoopia koheselt ilma taimeri ootamiseta. Töötab isegi kui taimereid pole juurutatud, kasutades ad-hoc täitmiseks `systemd-run`-i:

```bash
rdc machine backup now -m server-1
rdc machine backup now -m server-1 --strategy weekly-cold
```

### Varundamise oleku vaatamine

Näita varundamise taimerite praegust olekut ja hiljutisi töö tulemusi:

```bash
rdc machine backup status -m server-1
rdc machine backup status -m server-1 --strategy hourly-hot
```

### Käimasoleva varundamise tühistamine

```bash
rdc machine backup cancel -m server-1
rdc machine backup cancel -m server-1 --strategy weekly-cold
```

## Repositooriumi migreerimine

Liiguta repositoorium ühelt masinalt teisele:

```bash
rdc repo migrate --name my-app --from server-1 --to server-2
```

| Valik | Kirjeldus |
|--------|-------------|
| `--name <repo>` | Migreeritav repositoorium |
| `--from <machine>` | Lähtemašin |
| `--to <machine>` | Sihtmasin |
| `--provision` | Provisiona repositoorium sihtmasinat enne ülekandmist |
| `--checkpoint` | Loo CRIU kontrollpunkt enne migreerimist |
| `--skip-dns` | Jäta DNS-kirjete uuendamine pärast migreerimist vahele |
| `--bwlimit <limit>` | Ribalaiuse piirang ülekandele (nt `50M`) |

Migreerimine kannab krüpteeritud repositooriumi andmed üle rsync kaudu. Lähte-repositoorium jääb puutumatuks kuni selle eksplitsiitse eemaldamiseni.

## Salvestuse sirvimine

Sirvi salvestuskoha sisu:

```bash
rdc storage browse --name my-storage
```

## Parimad praktikad

- Ajasta päevased külmad varukopiad kriitiliste andmete rakenduse-ühilduvate hetktõmmiste jaoks
- Kasuta kuumi varukoopiad sagedaste hetktõmmiste jaoks, kus nullseisakuaeg on nõutav
- Testi taastamist perioodiliselt varukoopia terviklikkuse kontrollimiseks
- Kasuta kriitiliste andmete jaoks mitut salvestusteenuse pakkujat (nt S3 + B2)
- Hoia volitused turvaliselt; varukopiad on krüpteeritud, kuid LUKS-volitus on taastamiseks vajalik
