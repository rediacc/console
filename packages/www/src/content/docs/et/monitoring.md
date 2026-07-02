---
title: "Jälgimine"
description: "Jälgige masina tervist, konteinereid, teenuseid, hoidlaid ning käivitage diagnostikat."
category: "Guides"
order: 9
language: et
sourceHash: "e2f5d37c534fc40d"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# Jälgimine

Rediacc pakub sisseehitatud jälgimiskäske masina tervise, töötavate konteinerite, teenuste, hoidlate oleku ja süsteemi diagnostika kontrollimiseks.

## Masina tervis

Hankige masina kohta täielik terviseraport:

```bash
rdc machine health --name server-1
```

See raporteerib:
- **Süsteem**: tööaeg, ketta kasutus, andmehoidla kasutus
- **Konteinerid**: töötavate, tervete, ebatervete arv
- **Salvestus**: SMART tervise olek
- **Probleemid**: tuvastatud probleemid

Kasutage `--output json` masinloetava väljundi jaoks.

## Konteinerite loetlemine

Vaadake kõiki töötavaid konteinereid kõikides hoidlates masinal:

```bash
rdc machine containers --name server-1
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
rdc machine services --name server-1
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
rdc machine repos --name server-1
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
rdc machine query --name server-1 --storage-health
```

| Veerg | Kirjeldus |
|--------|-------------|
| Quota | Repositooriumi maksimaalne suurus (kasvulagi, mis on seatud loomise ajal või resize/auto-grow kaudu) |
| Allocated | See, mida hõre kujutis basseinis hetkel tegelikult hõivab |
| Unique | Tegelik unikaalne andmemaht, mis kuulub ainult sellele repositooriumile |
| Shared | Andmeplokid, mida taaskasutatakse repositooriumite vahel BTRFS-i reflink'ide kaudu (tasuta koopiad) |
| Reclaimable | Eraldatud ja kasutatud vahemaa, mille [`repo trim`](/et/docs/repositories#ruumi-tagasinõudmine-trim) saab basseinile tagastada. Näitab `-` lahtiühendatud repositooriumite puhul |
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

Viimase skrubimise tulemus salvestatakse väljaspool BTRFS-i mahtu (aadressil `/var/lib/rediacc/scrub-last-result.json`), nii et see jääb loetavaks isegi kui mahul on probleeme. `rdc machine query --system` väljund sisaldab välja `scrub_status`:

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
rdc term connect -m server-1 -c "sudo renet maintenance scrub --datastore /mnt/rediacc"
```

Tulemus salvestatakse samasse JSON-faili ja on koheselt nähtav järgmises `rdc machine query --system` väljundis.

## Masina ülevaade

Hankige masina täielik ülevaade koos juurutusteabega:

```bash
rdc machine query --name server-1
```

See annab:
- Hostinimi ja tööaeg
- Mälu-, ketta- ja andmehoidla kasutus
- Hoidlate koguarv, ühendatud arv, Dockeri töötav arv
- Üksikasjalik teave hoidla kaupa

Kasutage `--output json` masinloetava väljundi jaoks.

## Ühenduse testimine

Kontrollige SSH-ühenduvust masinaga:

```bash
rdc term connect -m server-1 -c "hostname"
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
