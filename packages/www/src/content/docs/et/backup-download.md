---
title: "Varukoopia allalaadimine"
description: "Repositooriumi krüpteeritud tõmmise kopeerimine kohalikku kataloogi või välisele kettale, selle uuendamine kohapeal järgmistel käivitustel või taastamine otse varukoopiasalvest ilma ühegi masinata."
category: "Guides"
tags:
  - backup
  - storage
subcategory: data-protection
order: 8
language: et
sourceHash: "c52e6a0471befc30"
---

# Varukoopia allalaadimine

`rdc backup download` hoiab repositooriumi krüpteeritud tõmmise koopiat kohalikus kataloogis või välisel kettal. Koopia on sama šifreeritud tekst, mis asub masinas, mistõttu ei dekrüpteerita teel midagi. Seda avav mandaat jääb konfiguratsiooni, seega on [config storage](/et/docs/config-storage) registreerimine viis selle turvaliselt hoidmiseks. Ilma mandaadita ei saa tõmmist avada.

Allikaid on kaks. Vaikimisi on selleks töötav masin. Teine on varukoopiasalv, mis valitakse lipuga `--store`.

## Allalaadimine masinast

```bash
rdc backup download mail@prod --to /mnt/usb
```

`--to` nimetab olemasoleva kirjutatava kataloogi. Seda ei looda kunagi, seega tuleb ketas enne ühendada. Tõmmis satub asukohta `<machine>/<name>.<tag>.img` ning selle kõrvale tekib fail `.state.json`.

Iga käivitus teeb repositooriumist värske hetktõmmise, mida hoitakse ainult ülekande kestel, saadab erinevused rsynciga ja võrdleb tulemuse sha256 masina hetktõmmisega.

| Lipp | Mõju |
|------|--------|
| `--all -m <machine>` | Kopeeri iga masinasse paigutatud grand-repositoorium |
| `--include-forks` | Koos lipuga `--all` kopeeri ka forkid |
| `--bwlimit <rate>` | Piira võrgu ribalaiust, näiteks `100Mbps` või `12.5M` |
| `--checkpoint` | Tee repositooriumile enne hetktõmmist checkpoint ja külmuta see (kuum varukoopia) |
| `--retries <n>` | Käivituse-sisesed korduskatsed pärast võrguviga (vaikimisi 3) |
| `--skip-verify` | Jäta sha256 võrdlus vahele; rsynci enda kontrollsumma jookseb endiselt |
| `--skip-space-check` | Hoiata keeldumise asemel, kui sihtkohas võib vaba ruumi puududa |

### Koopia uuendamine

Teine käivitus uuendab olemasolevat tõmmist kohapeal rsynci delta abil. Iganädalane käivitus saadab ainult muutunu ning sihtkoht vajab ruumi ühe tõmmisekoopia, mitte kahe jaoks. Enne käivituse algust kontrollitakse vaba ruumi tõmmise suuruse suhtes ning `--skip-space-check` muudab keeldumise hoiatuseks.

### Katkenud käivitused ja jätkamine

Olekufail salvestab välja `status`. See on `incomplete` ajast enne esimese baidi kirjutamist kuni käivituse kontrollimiseni ning `incomplete` tõmmis ei ole kasutatav. Ctrl-C, katkenud ühendus või jõuga lõpetatud protsess jätavad selle sellesse olekusse. Sama käsu uuesti käivitamine jätkab ning saadetakse ainult erinevused. Käsk lõpeb väljumiskoodiga 0, kui olek on `complete`.

### Nõuded

Ülekanne vajab sellel arvutil rsynci versiooni 3.1.3 või uuemat ning SFTP-varuvarianti pole. Linuxi distributsioonid toovad selle kaasa. macOS-is asendab `brew install rsync` kaasasoleva openrsynci, mis ei suuda ülekannet teha. Windowsis paigaldatakse MSYS2 koos rsynci paketiga või kasutatakse töölauarakendust.

### Välised kettad

Mahtuvuse määrab sihtkoha failisüsteem.

- **FAT32** ei mahuta üle 4 GiB suurust faili ning käsk keeldub käivitamast.
- **exFAT** ilma hõredate failide toeta salvestab tõmmise selle täieliku näiva suurusega, mistõttu vaba ruumi kontroll arvestab just seda suurust.
- Sihtkohast kohapeal tehtud **copy-on-write-hetktõmmis** (btrfs, ZFS, APFS) säilitab tõmmise varasemad versioonid. Iga kohapealne uuendus maksab siis vanade plokkide kõrval ka muutunud plokid.

## Allalaadimine varukoopiasalvest

```bash
export REDIACC_TOKEN=<api-token>
rdc backup download mail --store --to /mnt/usb
```

`--store` ehitab tõmmise otse tükisalvest uuesti üles, ilma ühegi masinata. Muutujas `REDIACC_TOKEN` olev tunnus vajab skoope `backup:read` ja `backup:restore`. CLI sisselogimine ei kanna kunagi skoopi `backup:restore`, seega luuakse tunnus portaali lehel API Tokens. See peab kuuluma tiimile ning selle peab olema loonud organisatsiooni praegune omanik või administraator.

`--store` võtab täpselt ühe repositooriumi nime. See ei võta lippe `-m`, `--checkpoint`, `--all`, `--include-forks`, `--bwlimit`, `--retries`, `--skip-verify` ega `--skip-space-check`: salvest toomisel on oma jätkamine ja see kontrollib iga tüki.

Tõmmis kirjutatakse asukohta `<dir>/<name>.<tag>.img`. Katkenud toomine säilitab osalise koopia ning sama käsk jätkab sellest.

### Hetktõmmise valimine lipuga `--at`

Vaikimisi tuuakse uusim hetktõmmis. `--at <time|snapshot>` valib mõne muu, kas ISO 8601 ajana või hetktõmmise id-na. See kehtib ainult koos lipuga `--store`.

```bash
rdc backup download mail --store --to /mnt/usb --at 2026-10-01T00:00:00Z
```

Muul platvormil kui Linux on toodud tõmmis krüpteeritud ning seda ei saa kohapeal avada. See saadetakse Linuxi masinasse käsuga `rdc backup upload`.

## Koopia üleslaadimine tagasi

```bash
rdc backup upload /mnt/usb/prod/mail.latest.img --to prod --as mail-copy --up
```

`rdc backup upload` saadab alla laaditud tõmmise masinasse ja registreerib selle uue repositooriumina. Ülekanne jätkub pärast katkestust ning masin kontrollib sha256 ja LUKS-päist enne tõmmise paigutamist. Tõmmise kõrval olev olekufail annab mandaadi. Kui see fail on kadunud, nimetab `--from-repo <name>` repositooriumi, mis selle annab.

| Lipp | Mõju |
|------|--------|
| `--as <name>` | Uue repositooriumi nimi (vaikimisi tõmmise nimi) |
| `--datastore <name>` | Paiguta tõmmis nimetatud datastore'i |
| `--from-repo <name>` | Anna mandaat ja põlvnemine, kui olekufail pole kasutatav |
| `--bwlimit <rate>`, `--retries <n>` | Sama mis allalaadimisel |
| `--up` | Käivita repositoorium pärast registreerimist |
| `--skip-verify` | Jäta vahele võrdlus allalaadimisel salvestatud sha256-ga |

## Aegunud ülekande hetktõmmised

Jõuga lõpetatud ülekanne võib jätta oma hetktõmmise masinasse. `rdc machine status` loeb aegunud ülekande hetktõmmised kokku pooli kokkuvõttes ning `rdc machine prune <machine> --dry-run` loetleb need. Käsk `rdc machine prune <machine>` eemaldab need.

Hetktõmmiste kohta tükisalvestusse vt [Varundamine ja taastamine](/et/docs/backup-restore).
