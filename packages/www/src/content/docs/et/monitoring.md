---
title: "Jälgimine"
description: "Jälgige masina tervist, konteinereid, teenuseid, hoidlaid ning käivitage diagnostikat."
category: "Guides"
tags:
  - operations
subcategory: operations
order: 9
language: et
sourceHash: "acef592a7065cac7"
sourceCommit: "9f58d83e01b4d46f8ce31af467a203b4d195e801"
---

# Jälgimine

Rediacc pakub sisseehitatud jälgimiskäske masina tervise, töötavate konteinerite, teenuste, hoidlate oleku ja süsteemi diagnostika kontrollimiseks.

## Masina tervis

Hankige masina kohta täielik terviseraport:

```bash
rdc machine health server-1
```

See raporteerib:
- **Süsteem**: tööaeg, mälu (hoiatus üle 80%, viga üle 90%), ketta ja andmehoidla kasutus (hoiatus üle 85%, viga üle 95%)
- **Konteinerid**: töötavate, tervete ja ebatervete arv; `Restarting` tsüklis olev konteiner on kriitiline
- **Teenused**: ebaõnnestunud systemd üksused (viga) ja üksused, mis taaskäivituvad pidevalt (kriitiline)
- **Salvestus**: SMART tervise olek (rikkis ketas on kriitiline) ja ketta temperatuur
- **Hoidlad**: automaatkäivitusega hoidlad, mis pole haagitud, ja iga hoidla failisüsteemi kasutus (hoiatus üle 85%, viga üle 95%)
- **Varukoopiad**: hoidlad, millest pole üle 10 päeva varukoopiat tehtud, mis jäävad oma ajakavast või sihtkohast maha või mille viimane kontroll ebaõnnestus
- **Litsentsid**: aegunud, puuduvad, mittevastavad või kehtetud hoidlalitsentsid ja litsentsid, mis vajavad uuendamist
- **Renet-protsessid**: deemonid, mis käitavad endiselt asendatud renet-i binaarfaili
- **Hoidla tervis**: iga haagitud hoidla enda `health()` tulemus (vt allpool)
- **Sertifikaadid**: proksi aegumisele lähenevad sertifikaadid ja jagatud ACME väljakutse CNAME-kirjed
- **Probleemid**: tuvastatud probleemid

Väljumiskood on otsus: `0` leide pole (hoidla, millel pole `health()` kontrolli, kuvatakse kui „kontroll puudub“ ja seda ei loeta kunagi terveks), `1` hoiatus, `2` viga, `3` kriitiline (rikkis ketas või taaskäivitustsüklis olev konteiner või teenus). Kasutage `--output json` masinloetava väljundi jaoks; see sisaldab välju `repo_health` (üks aruanne hoidla kohta) ja `findings`, kus igal leiul on kood, tõsidus (`info`, `warning`, `error` või `critical`), subjekt, üksikasi ja, kui parandus on olemas, `fix` (vt [Parandus](#repair)).

## Hoidla tervis

Rediaccfile võib määratleda funktsiooni `health()`, mis kontrollib hoidla enda teenuseid ([Teenused](/et/docs/services)): väljumiskood `0` korras, `1` hoiatus, `2` viga. Ühe hoidla jaoks käivitatakse see nii:

```bash
rdc repo health my-app@server-1
```

Käsk lõpeb halvima tasemega hoidla kõigi Rediaccfile'ide seas. Hoidla, mille ükski Rediaccfile `health()` ei defineeri, prindib **kontroll puudub** ja lõpeb koodiga `0`; seda ei teatata kunagi terve hoidlana. Ajalõpuga, katkestatud või mõne muu koodiga lõppev `health()` on viga, samuti masinaga ühenduse puudumine (väljumiskood `2`).

`rdc machine health` käivitab iga haagitud hoidla `health()` ühe kutsega ja liidab halvima taseme oma väljumiskoodi, tehes hoidla kohta ühe leiu hoiatusena (`repo.health.warning`) või veana (`repo.health.error`). Kontrollita hoidlad loetletakse, neist ei teatata. Kui masina renet on hoidla tervisekontrollidest vanem, on tulemuseks üks hoiatus, `renet.repo-health.unsupported`, kuni `rdc machine setup` selle uuendab.

## Sertifikaadi aegumine ja ACME väljakutsed

`rdc machine health` loeb proksi ACME sertifikaate ja teatab `cert.expiry.near` iga sertifikaadi kohta, mille aegumiseni on alla 21 päeva (hoiatus) või alla 7 päeva (viga). Proksi uuendab 30 päeva ette, seega alla 21 päeva tähendab, et uuendamine on ebaõnnestunud vähemalt üheksa päeva.

Samuti teatab see `acme.challenge.cname-shared`, kui sertifikaadi nime kirje `_acme-challenge.<name>` järgib CNAME-i nimeni, mis ise pole `_acme-challenge.` nimi, või kui kaks nime lõpevad samal nimel. CNAME-ina olev metamärgikirje tekitab just sellise kuju: kõik väljakutsed jõuavad ühele nimele ja uuendused põrkuvad. Tahtlikku delegeerimist (näiteks `_acme-challenge.mail.example.com` viitab nimele `_acme-challenge.mail.example.io`) ei teatata; muud ettenähtud delegeerimised loetlege proksi `config.env` failis muutujas `ACME_DELEGATED_NAMES` (sertifikaatide nimede komaga eraldatud loend). Nimi, mille väljakutseahelat ei õnnestunud lahendada (ükski DNS-lahendaja ei vastanud selle nime kohta), esitatakse kui `acme.challenge.unknown`, hoiatus, sest selle nime kontrolli ei saanud teha.

## Parandus

Igal leiul on kood ja, kui turvaline parandus on olemas, `fix` väljadega `action`, turvaklass `class` ja `window_only`. `rdc machine health` jääb kirjutuskaitstuks; tegutseb käsk `rdc machine repair`:

```bash
rdc machine repair server-1 --dry-run     # list what would run
rdc machine repair server-1               # run the auto-safe fixes, then re-check
rdc machine repair server-1 --code cert.expiry.near
```

| Klass | Tähendus |
|---|---|
| `auto-safe` | Käivitub vaikimisi: konteineri või Traefiku taaskäivitamine, trim ja puhastus, ACME ankru kirjutamine |
| `auto-with-backup` | Käivitub ainult koos lipuga `--with-backup`, pärast hoidla edukat hetktõmmist; ebaõnnestunud hetktõmmis tühistab paranduse |
| `operator-only` | Ei käivitu kunagi. Käsk prindib täpse käsu, mis tuleb käsitsi käivitada. Siia kuulub kõik, mis kustutab nimega andmeid või kulutab raha |

`window_only` on klassile lisanduv tingimus: parandus käivitub ainult masina hooldusakna sees, kujul `HH:MM-HH:MM` UTC-s (aken võib ületada keskööd). Aknata masin ei käivita neid parandusi kunagi ise; `--window-override` käivitab need käsitsi. Akna määramine või eemaldamine:

```bash
rdc machine repair server-1 --set-window 00:00-03:00
rdc machine repair server-1 --set-window off
```

Iga parandus kontrollib esmalt, et selle leid on endiselt olemas, seega teisel käivitusel pole midagi teha. Parandused, mis puudutavad sama asja, käivituvad üks kord (üks Traefiku taaskäivitus katab kõik sertifikaadid). Iga parandus logitakse masina päevikusse sildiga `rediacc-repair` ning JSON-i väljale `actions` (`code`, `subject`, `action`, `class`, `result`, `before`, `after`) ja käivitus lõpeb täieliku uuesti kontrolliga. Väljumiskood on `0`, kui midagi ei jää, `1`, kui jäävad hoiatused või operator-only punktid, ja `2`, kui jääb viga või kriitiline leid või parandus ebaõnnestus. `rdc machine repair` ei lõpe kunagi koodiga `3`; seda teeb ainult `rdc machine health`.

| Leid | Parandus | Klass |
|---|---|---|
| `datastore.usage.high`, `repo.disk.high` | Trim, seejärel peatatud konteinerite, anonüümsete orbude ja kasutamata kujutiste puhastamine | auto-safe |
| `container.unhealthy`, `container.restart-loop` | Konteineri taaskäivitamine | auto-safe |
| `renet.binary.replaced` | Mõjutatud hoidlate järelevaatajate taaskäivitamine (`rdc machine restart-services --include-docker`, piiratud nendega) | auto-safe, ainult aknas |
| `cert.expiry.near` | Traefiku taaskäivitamine, et see uuendust uuesti prooviks | auto-safe |
| `acme.challenge.cname-shared` | ACME ankru kirjutamine (vt allpool) | auto-safe (operator-only, kui delegeerimine on deklareeritud ja kasutatavat Cloudflare'i tokenit pole) |
| `repo.health.warning`, `repo.health.error` | Hoidla `repair()` käivitamine ([Teenused](/et/docs/services)) | klass, mille Rediaccfile deklareerib |
| `repo.unmounted`, `service.failed`, `service.restart-loop`, `backup.*`, `license.*`, `renet.repo-health.unsupported` | Prinditakse käivitatava käsuna | operator-only |

Leide, millel parandust pole (SMART-rikked, temperatuur, mälu, süsteemiketas, ebaõnnestunud kontroll), teatatakse ja need jäetakse operaatorile.

Puhastus ei puutu kunagi jaoturit (hub): sildiga `rediacc.hub.*` konteinerid ja sildiga `rediacc.hub.user` või nimega `rediacc-hub-home-*` mahud on välistatud, nii et jaoturi kasutaja kodukataloog püsib iga ruumi tagasivõtmise järel alles. Jääk, mida trim ja puhastus ei suuda vabastada (nimega mahud, suured rakenduse andmed), jääb operaatori otsustada.

### Hoidla parandus

```bash
rdc repo repair my-app@server-1 --dry-run
rdc repo repair my-app@server-1
```

`rdc repo repair` käivitab hoidla `repair()` funktsioonid samade klassidega: `auto-safe` käivitub, `auto-with-backup` vajab lippu `--with-backup` ning deklareerimata (`operator-only`) `repair()` käivitub alles pärast küsimusele vastamist või lipuga `--yes`. Seejärel käivitub `health()` uuesti ja väljumiskood järgib taset, kus see lõpeb: `0` korras või kontroll puudub, `1` hoiatus, `2` viga või ebaõnnestunud `repair()`.

### ACME ankur

CNAME-ina olev metamärgi DNS-kirje paneb iga nime `_acme-challenge.<host>` seda järgima, nii et kõik väljakutsed jõuavad ühele nimele ja uuendused põrkuvad (`acme.challenge.cname-shared`). Parandus kirjutab proksi Cloudflare'i tokeni abil igale põrkuvale `_acme-challenge.<name>` kirjele TXT-kirje väärtusega `rediacc-acme-anchor` ja taaskäivitab seejärel Traefiku. Selgesõnaline kirje viib nime metamärgi mõjualast välja, nii et väljakutse jõuab sinna, kuhu peab. Parandus ainult lisab kirjeid ja olemasolevat ankrut ei muudeta. Väljakutse nimi, mis ise on CNAME, ei saa enda kõrval TXT-kirjet hoida: Cloudflare keeldub kirjutamisest ja parandus valib sama varulahenduse nagu tsooni puhul, kuhu selle token kirjutada ei saa (järgmine lõik).

Muutujas `ACME_DELEGATED_NAMES` (sertifikaatide nimede komaga eraldatud loend proksi `config.env` failis) loetletud nimed on tahtlikud delegeerimised: neid ei ankurdata ega teatata kunagi. Kui proksil pole kasutatavat Cloudflare'i tokenit, langeb parandus tagasi väärtusele `LEGO_DISABLE_CNAME_SUPPORT=true` failis `config.env`, kuid ainult siis, kui ühtegi delegeeritud nime pole deklareeritud, sest see muutuja lülitab CNAME-ide järgimise välja kõigi nimede jaoks; deklareeritud delegeerimise korral jääb leid operator-only. Sama parandus käivitub iga proksi paigaldusega (`rdc machine infra push`) ja eraldi käsuga `renet proxy acme-fix` masinas.

## Konteinerite loetlemine

Vaadake kõiki töötavaid konteinereid kõikides hoidlates masinal:

```bash
rdc machine status server-1 --containers
```

| Veerg | Kirjeldus |
|--------|-------------|
| Name | Konteineri nimi |
| Status | Tööaeg või väljumispõhjus |
| State | Töötab, väljunud jne |
| Health | Terve, ebaterve, puudub |
| CPU | CPU kasutuse protsent |
| Memory | Mälukasutus / piirang |
| Repository | Milline hoidla omab konteinerit |

Valikud:
- `--health-check`, Teosta aktiivseid tervisekontrolle konteineritele
- `--output json`, Masinloetav JSON-väljund

JSON-väljund sisaldab täielikke konteineri üksikasju (`labels`, `port_mappings`, `image`, `id`) koos `repository` (lahendatud nimi), `repository_guid` (algne GUID), `domain` ja `autoRoute` väljadega.

## Teenuste loetlemine

Vaadake Rediacciga seotud systemd teenuseid masinal:

```bash
rdc machine status server-1 --services
```

| Veerg | Kirjeldus |
|--------|-------------|
| Name | Teenuse nimi |
| State | Aktiivne, mitteaktiivne, nurjunud |
| Sub-state | Töötab, surnud jne |
| Restarts | Taaskäivituste arv |
| Memory | Teenuse mälukasutus |
| Repository | Seotud hoidla |

Valikud:
- `--stability-check`, Märgi ebastabiilsed teenused (nurjunud, >3 taaskäivitust, automaatne taaskäivitus)
- `--output json`, Masinloetav JSON-väljund

JSON-väljund sisaldab täielikke teenuse üksikasju koos `repository` (lahendatud nimi) ja `repository_guid` (algne GUID) väljadega.

## Hoidlate loetlemine

Vaadake hoidlaid masinal koos üksikasjalike statistikatega:

```bash
rdc machine status server-1 --repositories
```

| Veerg | Kirjeldus |
|--------|-------------|
| Name | Hoidla nimi |
| Size | Kettapildi suurus |
| Mount | Ühendatud või lahti ühendatud |
| Docker | Dockeri deemon töötab või peatunud |
| Containers | Konteinerite arv |
| Disk Usage | Tegelik ketta kasutus hoidlas |
| Modified | Viimane muutmisaeg |

Valikud:
- `--search <text>`, Filtreeri nime või ühendamistee järgi
- `--output json`, Masinloetav JSON-väljund

JSON-väljund sisaldab `name` (lahendatud) ja `guid` (algne GUID) ning pesastab iga hoidla `containers` (koos `domain`, `autoRoute`, `repository`/`repository_guid` väljadega) ja `services` massiivid.

## Salvestuse tervis

Kontrollige BTRFS-i fragmentatsiooni ja reflink'i jagamist kõikides hoidlates masinal:

```bash
rdc machine status server-1 --storage-health
```

| Veerg | Kirjeldus |
|--------|-------------|
| Quota | Repositooriumi maksimaalne suurus (kasvulagi, mis on seatud loomise ajal või resize/auto-grow kaudu) |
| Allocated | See, mida hõre kujutis basseinis hetkel tegelikult hõivab |
| Unique | Tegelik unikaalne andmemaht, mis kuulub ainult sellele repositooriumile |
| Shared | Andmeplokid, mida taaskasutatakse repositooriumite vahel BTRFS-i reflink'ide kaudu (tasuta koopiad) |
| Reclaimable | Eraldatud ja kasutatud vahemaa, mille [`repo trim`](/et/docs/repositories#reclaim-space-trim) saab basseinile tagastada. Näitab `-` lahtiühendatud repositooriumite puhul |
| Discards | Kas krüpteeritud maht edastab discard-käsud läbi (`on` iga repositooriumi puhul, mis on ühendatud praeguse versiooniga) |
| Divergence | Protsent kujutisest, mis on selle repositooriumi jaoks unikaalne, mitte jagatud (kõrgem tähendab rohkem tagasinõutavat ruumi kustutamisel) |
| Frag | Laiendeid GB kohta copy-on-write kujutises (ainult informatiivne) |

Kvoot ja eraldus on tahtlikult erinevad numbrid: repositoorium 20 GB kvoodiga, mis salvestab 6 GB andmeid, maksab basseinile ainult selle, mida ta on eraldanud. Bassein võib seetõttu lubada kokku rohkem kvooti kui tal füüsiliselt on, ja Reclaimable veerg näitab, kui palju iga repositooriumi eraldusest ei kasutata enam ja saab trimmida tagasi.

Tabeli all kirjeldab basseini kokkuvõte andmehoidla täitumist ja seda, kui palju ruumi varukoopia hetktõmmised parajasti kinni hoiavad:

```
Pool: 265.4 GB used, 95.2 GB free (73.6% full)
Backup snapshots pin 2.1 GB (1 active, 0 stale; stale ones are removed by 'rdc machine prune')
```

Varundamise ajal hoiab selle hetktõmmis kõiki plokke, mida see jagab elavate repositooriumidega, seega kustutamised ja trimmimised vabastavad vähem basseiniruumi kuni varundamise tsükkel lõpeb ja hetktõmmis kustutatakse. Katkestunud varunduste aegunud hetktõmmised eemaldatakse salvestuse hooldaja poolt automaatselt minutite jooksul.

Kokkuvõte näitab BTRFS-i reflink'idest saadud säästu kokku:

```
14 repos, 224.3 GB virtual size
Unique data: 323.7 MB | Shared: 224.0 GB | Efficiency: 99.9%
```

- **Virtuaalne suurus** on kõikide hoidla pildisuuruste summa. See on see, kuidas hoidlad välja näevad, kuid see loeb topelt reflink'ide kaudu jagatud plokke.
- **Unikaalsed andmed** on tegelik salvestusruum, mida tarbivad hoidla andmed, mis eksisteerivad ainult ühes hoidlas. See on see, mida vabastaksite hoidla kustutamisel.
- **Jagatud** on andmed, mida taaskasutatakse hoidlate vahel BTRFS-i reflink'ide kaudu. Hoidla hargnemine loob reflink'i koopiad, mis jagavad plokke, kuni kumbki pool kirjutab uusi andmeid, mille tulemusel plokid lahknevad.
- **Efektiivsus** on reflink'ide kaudu taaskasutatud andmete protsent. Kõrgem on parem. Masin, millel on palju hargnemisi samalt vanemalt, näitab lähedal-100% efektiivsust.

Frag-veerg on informatiivne. See loeb copy-on-write pildifaili laiendeid, mitte faile, mida su rakendus selle sees loeb, seega loeb see kõrgeks tavapäraste juhuslik-kirjutamise töökoormate korral (andmebaasid, konteinerite kihid) ega ennusta lugemise jõudlust SSD-toega salvestusel. Rediacc ei paku tahtlikult defragmenteerimiskäsku: `btrfs filesystem defragment` jagab lahku reflingitud harked ja hetktõmmised, mis täis-basseiniga võib kasutust dramatiliselt paisutada, samas kui võrdlusmõõtmised ei näita mõõdetavat lugemiskasumit. Täielikud mõõtmised ja põhjendused leiad siit: [Sinu fragmentatsiooninumber näeb kohutav välja. Mõõtsin, mida see tegelikult maksab.](/et/blog/i-benchmarked-btrfs-fragmentation).

Skaneerimine töötab paralleelselt ja võtab 5-15 sekundit sõltuvalt hoidlate arvust ja suurusest. Kui `--storage-health` ei ole täpsustatud, ilmub päringuväljundi järel üherealise vihje meeldetuletusena.

## BTRFS-i skrubb

Rediacc planeerib automaatselt iganädalase BTRFS-i skrubimise igal masinal. Skrubb loeb iga andmeploki andmehoidlas, kontrollib kontrollsummasid ja raporteerib igasuguse riknemise. See tabab vaikse andmete riknemise (bitrot) enne, kui see levib varukoopiatesse ja hargnemistesse.

Skrubb töötab igal pühapäeval kell 02:00 kohalikus ajas (masina ajavöönd) koos juhusliku viivitusega kuni 1 tund. See töötab madalaimal I/O prioriteedil (`ionice idle`, `nice 19`), nii et see ei häiri töötavaid teenuseid. SSD-toega masinatel oodake ligikaudu 8 minutit 100 GB andmehoidla kohta.

Skrubimise taimer installitakse automaatselt esimesel deemoni käivitusel pärast reneti uuendust. Kui skrubimispoliitika muutub tulevases reneti versioonis, uuendab see end järgmisel deemoni käivitusel ilma kasutaja sekkumiseta.

### Skrubimise olek

Viimase skrubimise tulemus salvestatakse väljaspool BTRFS-i mahtu (aadressil `/var/lib/rediacc/scrub-last-result.json`), nii et see jääb loetavaks isegi kui mahul on probleeme. `rdc machine status --system` väljund sisaldab välja `scrub_status`:

```json
"scrub_status": {
  "last_run_human": "3 days ago",
  "status": "ok",
  "total_errors": 0,
  "uncorrectable": 0,
  "duration_seconds": 312
}
```

| Olek | Tähendus |
|--------|---------|
| `ok` | Viimane skrubb lõpetati vigadeta |
| `never_run` | Skrubimist pole veel toimunud (taimer installiti just) |
| `overdue` | Viimane skrubb oli rohkem kui 14 päeva tagasi |
| `errors_found` | Skrubb leidis kontrollsumma mittevastavusi (kontrollige `total_errors` ja `uncorrectable` arve) |
| `failed` | Skrubimise protsess väljus nullist erineva koodiga |

Kui `uncorrectable` on suurem kui null, ei saa mõjutatud plokke automaatselt parandada (ühe kettaga BTRFS-il pole redundantset koopiat). Taastage mõjutatud hoidla viimasest varukoopia versioonist.

### Käsitsi skrubb

Skrubimise koheseks käivitamiseks (nt pärast toitekatkestust või ketta migreerimist):

```bash
rdc term connect server-1 -c "sudo renet maintenance scrub --datastore /mnt/rediacc"
```

Tulemus salvestatakse samasse JSON-faili ja on koheselt nähtav järgmises `rdc machine status --system` väljundis.

## Masina ülevaade

Hankige masina täielik ülevaade koos juurutusteabega:

```bash
rdc machine status server-1
```

See annab:
- Hostinimi ja tööaeg
- Mälu-, ketta- ja andmehoidla kasutus
- Hoidlate koguarv, ühendatud arv, nende hoidlate arv, mille Dockeri deemon vastab
- Üksikasjalik teave hoidla kaupa

Kasutage `--output json` masinloetava väljundi jaoks.

## Ühenduse testimine

Kontrollige SSH-ühenduvust masinaga:

```bash
rdc term connect server-1 -c "hostname"
```

Käsk väljastab õnnestumisel kaugmasina hostinime ja ebaõnnestumisel ühendustõrke, kontrollides ühe sammuga nii DNS-i, SSH-porti kui ka võtmepõhist autentimist.

## Diagnostika (doctor)

Käivitage täielik diagnostikakontroll oma Rediacc keskkonnale:

```bash
rdc doctor
```

| Kategooria | Kontrollid |
|----------|--------|
| **Keskkond** | Node.js versioon, CLI versioon, SEA režiim, Go installatsioon, Dockeri kättesaadavus |
| **Renet** | Binaarifail asukoht, versioon, CRIU, rsync, SEA manustatud varad |
| **Konfiguratsioon** | Aktiivne konfiguratsioon, adapter, masinad, SSH-võti |
| **Virtualiseerimine** | Kontrollib, kas teie süsteem saab käitada kohalikke virtuaalmasinaid (`rdc ops`) |

Iga kontroll raporteerib **OK**, **Hoiatus** või **Tõrge**. Kasutage seda esimese sammuna igasuguse probleemi tõrkeotsinguks.

Väljumiskoodid: `0` = kõik läbisid, `1` = hoiatused, `2` = tõrked.

## Teenuse valmisolekukontrollid

`repo up` käivitamisel ootab renet, kuni HTTP-teenused aktsepteerivad ühendusi, enne kui kuulutab need käivitunuteks. Ooteaeg arvestab tervisekontrolle:

- Konteinerid, mille Docker raporteerib **terveks**, usaldatakse otsekohe, TCP-proovi ei teostata.
- Konteinerid, mis viibivad veel tervisekontrolli `start_period`-is, logivad informatiivse teate, mitte hoiatuse; puhverserver jätkab ühenduskatseid, kuni need seovad end.
- Compose'i teenused, millel pole töötavat konteinerit (näiteks mitteaktiivse profiili taga), jäetakse vahele.
- Kõiki ülejäänuid testitakse TCP kaudu kuni 15 sekundit (muutmiseks seadke `REDIACC_READINESS_TIMEOUT` sekunditeks).

[Dockeri tervisekontrolli](https://docs.docker.com/reference/dockerfile/#healthcheck) määratlemine aeglaselt käivituvatel teenustel annab renet'ile autoriteetse valmisolekusignaali ja eemaldab proovimüra juurutusväljundist.
