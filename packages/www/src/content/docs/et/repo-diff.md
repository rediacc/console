---
title: "rdc repo diff"
description: "Näita git-stiilis failipõhist erinevust kahe kopeerimise ajal kirjutusega hargnemise hoidla vahel, võrreldes nende krüpteeritud kettaandmeid plokitasandil, dekrüpteerimiseta."
category: Reference
subcategory: advanced
order: 40
language: et
sourceHash: "c72fbcc13e7e77ed"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# rdc repo diff

`rdc repo diff` näitab, millised failid muutusid kahe seotud hoidla vahel: hargnemise ja selle vanemat vahel, või kahe hoidla vahel, mis jagavad kopeerimise ajal kirjutusega eelkäijat. Kasuta `--name <fork>` hargnemise võrdlemiseks selle vanemaga, mille kohalik konfig salvestab, või lisa `--base <repo>` võrdlemiseks suvalise seotud hoidlaga, kus `--base` on baas (vana) pool ja `--name` on siht (uus) pool. Käsk on lugemiskaitsega ja ei dekrüpteeri kunagi image'e. See võrdleb neid plokitasandil kaugmasinal, seega maksumus jälgib muutunud plokkide arvu, mitte hoidla suurust: 1 GB hoidla ja 100 GB hoidla samade muudatustega võtavad sama aja. Kui terve hoidla muutus, plokkide arv skaleerlub suurusega ja nii ka maksumus.

## Millal seda kasutada

Niisiis: kasuta `repo diff` enne hargnemise edutamist. AI-agent jooksis lahti tootmise hargnemise koopias ja soovid näha täpselt, milliseid faile ta muutis enne muudatuse tagasi ühendamist: `repo diff --name <fork> -m <machine>` annab sulle selle failide nimekirja sekundites. Sekundites. Pärast katastroofitaastetaastamist võrdle taastatud hargnemmist pildikoopia vastu, et kinnitada, et oodatav failikomplekt tuli tagasi ja midagi muud ei kaldunud. Pikaajalise hargnemise puhul, kes käib kõrvuti oma vanemat mitmeid nädalaid, näitab diff kogunenud lahknemist (config muudatused, logi kasv, skeemi migratsioonid) ilma mõlema puu monteerimiseta ja käsitsi kõndimiseta.

Ära kasuta seda seotud hoidlate vahel. Mõlemad pooled peavad jagama kopeerimise ajal kirjutusega eelkäijat, sest võrdlus töötab jagatud plokkiajaloos. See pole ka binaarne diff tööriist: `--content` annab reajärgseid väljundeid ainult tekstifailidele, binaarfailid teatavad `Binary files differ`.

## Käsukeele viide

### Süntaks

```bash
rdc repo diff --name <fork> -m <machine>            # diff a fork against its parent
rdc repo diff --name <fork> --base <repo> -m <machine>   # diff against an arbitrary related repo
```

### Valikud

| Valik | Kirjeldus | Vaikeväärtus |
|--------|-------------|---------|
| `--name <name>` | Kontrollitav hoidla (siht, uus pool). Nõutav. | nõutav |
| `--base <name>` | Hoidla, millega võrrelda (baas, vana pool). Vaikimisi `--name` vanem, lahendatud kohaliku configist. | `--name` vanem |
| (formaadivali puudub) | Nime-staatuse väljund: värviline `A`/`M`/`D`/`R` täht muutunud faili kohta pluss üherealisi kokkuvõte. | sees |
| `--name-only` | Üks muutunud tee rea kohta, staatuse täht puudub. Müra-sõbralik. | välja |
| `--stat` | Faili kohta muutuste suuruus (baidi ja ploki deltad) kokku-

võttega jaluses. | välja |
| `--content <path>` | Ühendatud teksti diff ühe faili jaoks. Ainult tekst; binaarfailid teatavad `Binary files differ`. | välja |
| `--json` | Struktureeritud väljund agentidele ja skriptidele. | välja |
| `--fast` | Jäta sisu-räsi kinnitamise etapp vahele ja usalda plokkfiltrit. Kiirem, kuid võib üle teatada failidest kui Muudetud. | välja |
| `-m, --machine <name>` | Sihtmasin. Nõutav. | nõutav |
| `--debug` | Üksikasjalik diagnostika stderr kohale. | välja |
| `--skip-router-restart` | Jäta marsruuteri taaskäivitamise etapp vahele. | välja |

## Näited

### Vaikimisi nime-olek vanemat vastu

Ainult `--name` järgi võrdletakse hargnemmist vanemat vastu, mille kohalik konfig salvestab. Siin on hargnemine `test-1gb:fork1` ühe muutunud failiga:

```bash
$ rdc repo diff --name test-1gb:fork1 -m hostinger
M  hello.txt

1 file changed: 0 added, 1 modified, 0 deleted, 0 renamed
```

### Võrdlemine otsese baaside vastu

Kasuta `--base` võrdlemiseks suvalise seotud hoidlaga. `--base` on baas (vana) pool, `--name` on siht (uus) pool:

```bash
$ rdc repo diff --name test-1gb:fork1 --base test-1gb:latest -m hostinger
M  hello.txt

1 file changed: 0 added, 1 modified, 0 deleted, 0 renamed
```

### Muudatuste suuruus `--stat` abil

`--stat` lisab baidi ja plokkide delta faili kohta ja kokku

võtte jaluse:

```bash
$ rdc repo diff --name test-1gb:fork1 --stat -m hostinger
 hello.txt | +8 bytes, 1 block

1 file changed, 4096 bytes touched
```

### Ainult teed, edasi teisele tööriistale

`--name-only` prindib ühe tee rea kohta ilma staatuse tähe, valmis toidame teisele käsule:

```bash
$ rdc repo diff --name test-1gb:fork1 --name-only -m hostinger | xargs -I{} echo "review: {}"
review: hello.txt
```

### Reajärgsed diff ühe faili jaoks

`--content` annab ühendatud diff ühe tekstifaili jaoks:

```bash
$ rdc repo diff --name test-1gb:fork1 --content hello.txt -m hostinger
--- a/hello.txt
+++ b/hello.txt
@@ -1 +1 @@
-the original line of text in the parent
+the original line of text in the parent, now edited
```

### JSON filtreerimine jq-ga

`--json` väljastab struktureeritud ümbrise stdout-le, nii et see toru puhtalt `jq`-sse:

```bash
$ rdc repo diff --name test-1gb:fork1 --json -m hostinger | jq '.data.entries[] | select(.status=="M")'
{
  "status": "M",
  "path": "/hello.txt",
  "type": "file",
  "old_size": 53,
  "size": 61,
  "bytes_changed": 4096,
  "blocks_changed": 1,
  "inode": 13,
  "content_changed": true,
  "mode_changed": false,
  "uid_changed": false,
  "gid_changed": false
}
```

## Väljundivormingud

### Nime-olek (vaikimisi)

Iga muutunud fail saab staatuse tähe ja selle tee. `A` on lisatud, `M` muudetud, `D` kustutatud, `R` ümbenimetatud (koos vanade teega). Järgneb kokkuvõte rida koos arvuga kategooria kohta.

### `--name-only`

Üks tee rea kohta, staatuse täht puudub, kokkuvõte puudub. Kasuta seda, kui järgnev käsk soovib puhast failide nimekirja.

### `--stat`

Iga rida kannab faili baidi deltad plokkide deltad. Jalus teatab kogu faili arvu ja kokku puutunud baitide. See näitab, kus muudatuse kaal istub, mitte ainult milliseid faile liigutati.

### `--content <path>`

Standardne ühendatud diff (`---`/`+++` pealkirjad, `@@` hunks) ühe tekstifaili jaoks. Binaarfailid teatavad `Binary files differ` ja ei tekita hunks.

### `--json`

Täis struktureeritud tulemus. Andmed lähevad stdout-le; progress ja diagnostika lähevad stderr-le, seega JSON toru puhtalt `jq` või teise parseeri, isegi kui progress trükib.

## JSON skeemi

CLI korraldab renet tulemuse standardse ümbrises (`success`, `command`, `data`, `errors`, `warnings`, `metrics`). Diff tulemus asub `data` osas snake_case väljadega:

```json
{
  "success": true,
  "command": "repo diff",
  "data": {
    "base": "<base-guid>",
    "target": "<target-guid>",
    "added": 0,
    "modified": 1,
    "deleted": 0,
    "renamed": 0,
    "strategy": "shared",
    "fast": false,
    "degraded": false,
    "block_size": 4096,
    "total_bytes_changed": 4096,
    "entries": [
      {
        "status": "M",
        "path": "/hello.txt",
        "type": "file",
        "old_size": 53,
        "size": 61,
        "bytes_changed": 4096,
        "blocks_changed": 1,
        "inode": 13,
        "content_changed": true,
        "mode_changed": false,
        "uid_changed": false,
        "gid_changed": false
      }
    ]
  }
}
```

Iga objekt `entries[]` kirjeldab üht muutunud teed:

| Väli | Tüüp | Kirjeldus |
|-------|------|-------------|
| `status` | `A` \| `M` \| `D` \| `R` | Lisatud, Muudetud, Kustutatud või Ümbenimetatud. |
| `path` | string | Tee sihtpoolel (või baas poolel kustutamise jaoks). |
| `old_path` | string | Eelmine tee. Kohal ainult ümbernimetamise puhul. |
| `type` | `file` \| `dir` \| `symlink` \| `other` | Sisestuse liik. |
| `old_size` | number | Suurus baitides baas poolel. |
| `size` | number | Suurus baitides sihtpoolel. |
| `bytes_changed` | number | Baidid, mis erinevad, ümardades täisplokiks. |
| `blocks_changed` | number | Muutunud plokkide arv. |
| `inode` | number | Inode number, kasutatud ümbernimetamise tuvastamiseks. |
| `content_changed` | boolean | Kas fail sisu (mitte ainult metaandmed) muutus. |
| `mode_changed` | boolean | Kas faili režiim muutus. `old_mode`/`new_mode` on kohal, kui tõsi. |
| `uid_changed` | boolean | Kas omanik muutus. `old_uid`/`new_uid` on kohal, kui tõsi. |
| `gid_changed` | boolean | Kas rühm muutus. `old_gid`/`new_gid` on kohal, kui tõsi. |
| `old_target` / `new_target` | string | Symlink sihtmärgid. Muutunud symlinki jaoks kohal. |

Ümbrises väljad ja auto-tuvastamise reeglid, mis väljastada JSON mitte-TTY keskkondades, vaata [JSON väljund viide](/en/docs/ai-agents-json-output).

## Kuidas see töötab

Hoidla on LUKS2 kujutisfail btrfs pool-il ja hargnemine on pidev-ajaliselt reflink selle kujutisest. `repo diff` võrdleb kahte krüpteeritud kujutist plokitasandil FIEMAP-i kaudu, luges faili süsteemi metaandmeid ainult ja kunagi midagi dekrüpteerimata. See nihutab muutunud krüptotext-nihet LUKS andmete poolt, et saada ext4-seadme nihete, siis kaardistab need nihked failinimede tagasi iga faili ext4 extent maakaardia kaudu. Lõplik inode-identiteedi kõnd mõlema mountimise abil ühendab tulemuse Lisatakse, Muudetud, Kustutatud ja Ümbenimetatud sisestusteks. Sest töö on piiratud muutunud plokkide arvuga, diff ei sõltu hoidla suurusest, ja sest see kasutab uuesti elu mount paigal, see kunagi ei häiri töötavat hoidlat. Täielik mehhanism on kirjeldatud [Git diff krüpteeritud kettakujutiste jaoks](/en/blog/git-diff-for-encrypted-disk-images).

## Piirangud

- **Seotud hargneminged ainult.** Mõlemad pooled peavad jagama kopeerimise ajal kirjutusega eelkäijat. Seotud hoidlate vahel pole tähendusrikas plokitasandi võrdlus.
- **Ümbernimetamise tuvastus on inode-põhine.** Fail teatada ümbernimetatuks, kui sama inode ilmub uude teesse. Kustutamine-siis-taaslumine (uus inode) näeb Kustutamist pluss Lisatud sisestust, mitte ümbenimetamist.
- **`--content` ainult tekst.** See annab reajärgseid hunkse tekstifailidele. Binaarfailid teatavad `Binary files differ`.
- **`--fast` võib üle teatada Muudetud.** See usaldab plokkfiltrit ja jätab sisu-räsi kinnitamise vahele, nii et fail, kelle plokkid liikusid sisu muutmata, võib ilmuda kui Muudetud.
- **Extent-kõnd aja skaalad fragmendeerituse, mitte suurusega.** Tugevalt fragmenteeritud faili süsteemil on rohkem extent'e kaardistada, mis pikendab kõndi isegi kui muudatuste baidi maht on väike.

## Vt ka

- [rdc repo fork](/en/docs/repositories). Looge kopeerimise ajal kirjutusega hargnemine, mida see käsk eristab.
- [rdc repo status](/en/docs/repositories). Ühe hoidla praegune olek.
- [rdc repo cat](/en/docs/repositories). Lugege üks fail hoidlast.
