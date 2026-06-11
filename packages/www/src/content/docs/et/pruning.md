---
title: "Kärpimine"
description: "Eemalda orvuks jäänud varukoopiad, aegunud hetktõmmised, hoidlakujutised ja kohaliku konfiguratsiooni jäänukid, et vabastada kettaruumi ja hoida olek sidusana."
category: "Guides"
order: 12
language: et
sourceHash: "d2700c2ac4473962"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# Kärpimine

Kärpimine eemaldab olekud, mis ei vasta enam elusale ressursile. Kolm käsku katavad kolme erinevat ulatust:

| Käsk | Mida puhastab | Kus asub tõeallikas |
|---|---|---|
| `rdc storage prune --name <storage> -m <machine>` | Orvuks jäänud varukoopiad pilvemälus | Kohalik CLI konfiguratsioon (ristleeritakse koos teostusmasina vastu ühendamise ohutuse jaoks) |
| `rdc machine prune --name <machine>` | Masinal olevad andmehoidla artefaktid (alati); orvuks jäänud või tundmatud hoidlakujutised (valikuline) | Kohalik CLI konfiguratsioon + masina `.interim/state` peegel |
| `rdc config prune` | Kohaliku konfiguratsiooni jäänukid (serdi vahemälu, aegunud arhiivid, rippuvad ristviited) | Ainult kohalik CLI konfiguratsioon |

Need kolm on sõltumatud. Saad käivitada mis tahes ühe ilma teisteta. Need jagavad ühist ohutusmudelit, mida kirjeldatakse allpool jaotises [Ohutus](#ohutusmudel).

Kärpimine eemaldab oleku, mille on jätnud maha kustutatud ressursid. *Elavate* repositooriumite hõivatud ruumi tagasinõudmiseks (plokid, mille nende failisüsteemid on vabastanud, kuid bassein endiselt hoiab), kasuta selle asemel [`rdc repo trim`](/et/docs/repositories#ruumi-tagasinõudmine-trim); need kaks täiendavad teineteist.

## Ühendamise ohutuse eelkontroll

`storage prune` ja `machine prune --prune-unknown` käivitavad enne millegi kustutamist mõlemad **ühendamise ohutuse eelkontrolli**: need pärivad teostusmasinalt hetkel ühendatud või töötavaid hoidlaid, ristivad kustutamiskandidaatidega ja **keelduvad kustutamast kandidaati, mis on masinal endiselt aktiivne**. Ühendatud hoidla masinaväline varukoopia või elava hoidla kujutise kustutamine on tõeline andmekao oht. Eelkontroll muudab selle õnnetusliku tegemise võimatuks.

Alistamiseks (harv; ainult siis, kui oled kindel, et elav olek on vale), lisa `--force-delete-mounted`. See on eraldi lipp `--force`'ist (mis juhib arhiivi armuaega), nii et kaks turvaluugi pääsu jäävad eraldatuks.

## Mäluhoidla kärpimine

Skannib mälupakkuja ja kustutab varukoopiad, mille GUID-id ei esine enam üheski kohalikus konfiguratsioonifailis.

```bash
# Ainult eelvaade -- näita, mida kustutataks
rdc storage prune --name my-s3 -m server-1 --dry-run

# Tegelikult kustuta orvuks jäänud varukoopiad (vaikekäitumine)
rdc storage prune --name my-s3 -m server-1

# Alista armuaeg (vaikimisi 7 päeva)
rdc storage prune --name my-s3 -m server-1 --grace-days 14

# Alista ühendamise ohutuse kontroll (kasuta ettevaatlikult)
rdc storage prune --name my-s3 -m server-1 --force-delete-mounted
```

`--machine` on nõutav, kuna rclone kutsed käivituvad teotusmasinal, mitte sinu sülearvutis. Klientidel ei eeldata rclone'i kohalikku paigaldust. Mälumandaadid pärinevad endiselt sinu kohalikust konfiguratsioonist; masin on lihtsalt rclone käivitaja.

### Mida see kontrollib

1. Loendab kõik varukoopiate GUID-id nimetatud mäluhoidlas (mõlemas `hot/` ja `cold/` alamkataloogi üleselt. Vt [Varundus ja taastamine](/et/docs/backup-restore#scheduled-backups)).
2. Skannib kõik konfiguratsioonifailid kettal (`~/.config/rediacc/*.json`).
3. Varukoopia on **orvuks jäänud**, kui selle GUID-ile ei viida üheski konfiguratsiooni hoidlate jaotises.
4. Hiljuti arhiveeritud hoidlad armuaja jooksul on **kaitstud** isegi siis, kui need on aktiivsest konfiguratsioonist eemaldatud.
5. Ühendamise ohutuse eelkontroll: `--machine`-l hetkel ühendatud GUID-id jäetakse vahele ja nendest teatatakse, neid ei kustutata kunagi.

### Jõudlus

Kustutamised grupeeritakse mäluhoidla alamtee järgi: üks rclone kutse `hot/` või `cold/` kataloogi kohta, sõltumata sellest, mitu GUID-i eemaldatakse. 11 orvuks jäänud varukoopia mahajäämus kahaneb ~50 s SSH üldkuludest ühe ringreisi kohta alamtee kohta.

## Masina kärpimine

Puhastab masinal olevad ressursid kolmes faasis. Faas 1 käivitub alati; faasid 2 ja 3 on valikulised ja neid saab kombineerida.

### Faas 1: andmehoidla puhastamine (käivitub alati)

Eemaldab iga liiki ressursid, mis võivad jääda maha, kui hoidla kustutatakse või kui masina taseme refaktoreerimine pensioneerib nimetuskonventsiooni. Iga kategooria skannitakse iseseisvalt ja puhastamine on üks idemotentne läbimine, seega kärpimise kordamine on ohutu ja koondub puhtale andmehoidlale.

| Kategooria | Mida eemaldab |
|---------|-----------------|
| Tühjad ühenduse kataloogid | `mounts/<guid>/` kataloogid ilma toetava hoidlakujutiseta |
| Orvuks jäänud liigutamatud kataloogid | `immovable/<guid>/` kataloogid ilma toetava hoidlakujutiseta |
| Aegunud lukufailid | `repositories/.lock-<guid>` kustutatud hoidlate jaoks |
| Aegunud varukoopiate hetktõmmised | `.snapshot-*` ja `.backup-*`, mis jäid maha katkestatud varundusjooksudest |
| Orvuks jäänud VS Code liivakasti kataloogid | `.interim/sandbox/<name>` hoidlate jaoks, mis ei ole masinal enam aktiivsed |
| Orvuks jäänud iptables-ahelad | `REDIACC_WILDCARD_<N>` ja `DOCKER_ISOLATED_NET_<N>` ahelad kustutatud võrkude jaoks |
| Orvuks jäänud authorized_keys kirjed | `sandbox-gateway <repo> --guid <uuid>` read, mille `--guid` ei vasta enam aktiivsele ühenduskataloogi GUID-ile |

Authorized_keys skaneerimine vaatab `/home/*/.ssh/authorized_keys` ja `/root/.ssh/authorized_keys`. Kirje jäetakse alles ainult siis, kui selle `--guid` silt kaardistub elava ühenduskataloogi GUID-iga, seega masinal hetkel juurutatud hoidlad säilitatakse alati, sõltumata sellest, kas nende nimi esineb kusagil kettal. Pärandkirjeid, mis kirjutati enne, kui renet hakkas `--guid` silte lisama, ei saa valideerida ja neist teatatakse alati orvudena.

```bash
# Kuiv käivitus, näitab, mida eemaldataks (muudatusi ei rakendateta)
rdc machine prune --name server-1 --dry-run

# Käivita puhastamine
rdc machine prune --name server-1
```

> **Kaskaadpuhastamine.** Mõned kategooriad sõltuvad varasematest. Näiteks tühjade ühenduskataloogide kustutamine võib paljastada täiendavaid liivakasti orve, mille toetav ühendus äsja kadus. `rdc machine prune` teine käivitamine tabab kaskaadi ja lõpetab puhastamise. Lõplik kuiv käivitus lõpeb teatega `No orphaned resources found. Datastore is clean.` kui midagi pole enam teha.

### Faas 2: `--orphaned-repos` (jäme)

`--orphaned-repos` puhul kustutab CLI ka masinal olevad hoidlakujutised, mis ei esine **üheski** kohalikus konfiguratsioonifailis.

```bash
rdc machine prune --name server-1 --orphaned-repos --dry-run
rdc machine prune --name server-1 --orphaned-repos
```

See on **jäme**. See kustutab kõik, mis pole sinu kohalikus konfiguratsioonis, sealhulgas legitiimsed forkid, mida haldavad teised tööriistad või teise operaatori CLI väljavõte. Kui renet `.interim/state` peegel tuvastab hoidla korrektselt forkina, kuid kohalik konfiguratsioon pole seda kunagi näinud, eemaldab see faas selle ikkagi. Eelista 3. faasi (`--prune-unknown`), kui soovid olla konservatiivne.

### Faas 3: `--prune-unknown` (kirurgiline)

`--prune-unknown` puhul kustutab CLI ainult hoidlad, mida **mõlemad** signaalid ei suuda klassifitseerida: pole üheski kohalikus konfiguratsioonis **ega** masina `.interim/state` peeglis fork-märgistatud kirjet (vt [Hoidlad. `Type` veerg](/et/docs/repositories#type-column-and-the-state-mirror)).

```bash
rdc machine prune --name server-1 --prune-unknown --dry-run
rdc machine prune --name server-1 --prune-unknown
```

Praktikas on `--prune-unknown` see, mida soovid rutiinil puhastamiseks; `--orphaned-repos` on õige ainult siis, kui oled kindel, et sinu kohalik konfiguratsioon on täielik ja autoriteetne inventuur kõigist hoidlatest masinal. Eelpeegli pärandforkid ja hoidlad, mille konfiguratsioonikirje kustutati kogemata, kuuluvad mõlemad "tundmatu" kategooriasse. Need on tõesti ebakindlad, ja kirurgiline lipp palub operaatoril seda sõnaselgelt tunnistada.

Ühendamise ohutuse eelkontroll töötab ka sellel faasil: hetkel `--machine`-l ühendatud hoidlast teatatakse ja see jäetakse vahele, välja arvatud siis, kui `--force-delete-mounted` on edastatud.

```bash
# Kombineeritud: täielik masina puhastamine kirurgilise fork-teadliku teega
rdc machine prune --name server-1 --prune-unknown
```

## Konfiguratsiooni kärpimine

Puhastab aegunud jäänukid **kohalikus konfiguratsioonifailis** `~/.config/rediacc/<config>.json`. Puhtalt kohalik. SSH-d ega renet-kutseid pole. Kolm korvikest puhastatakse:

1. **ACME serdi-vahemälu kirjed**, mille ankur (GUID, hoidla nimi või masina nimi) ei esine enam aktiivses konfiguratsioonis. Serdi metamärgid ei saa kunagi kusagile suunata, seega on need surnud kaal.
2. **Aegunud arhiveeritud hoidlad** `resources.deletedRepositories[]` sees. Kirjed, mille `deletedAt` on vanem kui `defaults.pruneGraceDays` (vaikimisi 7 päeva). Armuaja sees olevad kirjed esitatakse (koos allesjäänud päevadega) ja hoitakse alles.
3. **Rippuvad ristviited** konfiguratsioonikorvide vahel:
   - `resources.machines.<m>.backupStrategies[]` kirjed, mis nimetavad strateegiat, mida pole enam olemas.
   - `resources.backupStrategies.<s>.exclude[]` ja `include[]` kirjed, mis nimetavad hoidlat, mida pole enam olemas.
   - Mäluhoidla sihtkohad, mille sihtmälu puudub. Märgitud hoiatusena, mitte automaatselt eemaldatavana (automaatne eemaldamine muudaks strateegia semantikat).

```bash
# Ainult eelvaade
rdc config prune --dry-run

# Rakenda (vaikekäitumine)
rdc config prune

# Piira ühe korvisena
rdc config prune --certs-only
rdc config prune --archives-only
rdc config prune --refs-only

# Eemaldage KÕIK arhiveeritud hoidlad sõltumata armuajast
rdc config prune --purge-archived

# Alista arhiivi armuajaaken selle kutsumise jaoks
rdc config prune --grace-days 30
```

### Mida see EI puuduta

- Aktiivsed ressursid (masinad, mäluhoidlad, hoidlad, varundustrateegiad, pilvepakkujad).
- Mandaadid, konto blokk, krüpterimisblokk, vaikeväärtused.
- Mäluhoidla `vaultContent` (kaasa arvatud aegunud OneDrive `access_token`. Refresh_token vermib endiselt uusi; kärpimine sunniks uuesti autentima).
- `knownHosts` kirjed (automaatne värskendamise tee on `rdc config machine scan-keys`).
- Tihendatud serdi blobimassiiv (`infra.acmeCertCache.<base>.data[]`) taastatakse automaatselt puhastatud serdinimistust; sa ei kaota ühtegi ahelat, mis katab endiselt säilitatud nime.

### Töötav näide

Väljund reaalsest jooksust masinal, millel on neli orvu GUID-i metamärki ja kaks aegunud masina-nime metamärki:

```text
Scanning local config for stale leftovers...
6 cert cache entry/entries would be removed:
  *.linode-1.rediacc.io  (unknown machine linode-1)
  *.marketing.linode-1.rediacc.io  (unknown machine linode-1)
  *.5b749533-99be-446c-9fe3-e6d0eec905a6.hostinger.rediacc.io  (unknown GUID 5b749533-…)
  *.5d09f3a6-9558-4df1-8a6e-b63140a6a7a6.hostinger.rediacc.io  (unknown GUID 5d09f3a6-…)
  *.e18d8c0f-367e-43c7-919e-2dbc59db4b5e.hostinger.rediacc.io  (unknown GUID e18d8c0f-…)
  *.9806c9b8-6bfb-4a87-9eaa-4b757ce1daca.hostinger.rediacc.io  (unknown GUID 9806c9b8-…)
Dry run: 6 change(s) would be applied. Re-run without --dry-run to commit.
```

Serdinimed, mille ankur on elav masin, hoidla või GUID, jäetakse alles, samuti kõik ühe-sildi `<service>.<base>` või juure `*.<base>` metamärgid.

## Migreerimine: olekupeegli tagasiasustamine

`.interim/state/<guid>/.rediacc.json` peegel, mis toitab `--prune-unknown` ja `rdc repo list -m` veergu `Type`, kirjutatakse:

- **Forki ajal** (`rdc repo fork`). Kohe, isegi enne, kui fork on kunagi ühendatud.
- **Iga olekusalvestuse korral** (`rdc repo mount` ja mis tahes toimingul, mis uuendab hoidla olekut). Hoidlate jaoks, mis loodi enne peegelkoodi laevamist.

Hoidlad, mis loodi **enne peegli olemasolu ja mida pole pärast uuendust uuesti ühendatud**, pole peeglifaili. Need kuvatakse `rdc repo list -m` all kui `unknown`, isegi kui mõned on legitiimselt forkid. Pärandforkide parandamiseks käivita masinal ühekordne tagasiasustamine:

```bash
sudo /usr/local/bin/renet repository backfill-state-mirror \
    --datastore /mnt/rediacc \
    --mark-as-fork <guid1>,<guid2>,<guid3>
```

Tagasiasustamine kopeerib hetkel ühendatud hoidlate jaoks otse mahus oleva oleku peeglisse ja kirjutab sünteetilise fork-märgistusega peegli mis tahes GUID-idele, mille lisad `--mark-as-fork` alla. Pärast tagasiasustamist lõpetavad ajakavastatud varukoopiad loetletud forkide üleslaadimise (üleslaadimise konveier kontrollib peegli `is_fork: true` olekut).

## Ohutusmudel

Kärpimine on loodud olema mitme konfiguratsiooni seadistustes vaikimisi ohutu.

### Mitme konfiguratsiooni teadlikkus

`storage prune` ja `machine prune --orphaned-repos` skannivad **kõik** konfiguratsioonifailid `~/.config/rediacc/` kaustas, mitte ainult aktiivset. Hoidlale, millele viitab `production.json`, ei kustutata isegi siis, kui see puudub `staging.json`-ist. See väldib kogemata kustutamist, kui konfiguratsioonid on ulatuselt seotud erinevate keskkondadega.

### Armuaeg

Kui hoidla eemaldatakse konfiguratsioonist `--archive-config` abil, liigutatakse selle mandaadikirje `resources.deletedRepositories[]` alla koos `deletedAt` ajatempliga. Kärpimiskäsud austavad armuaega (vaikimisi 7 päeva), mille jooksul on hiljuti arhiveeritud hoidlad kustutamise eest kaitstud. See annab sulle aega hoidla taastamiseks (`rdc config repository restore-archived --name <guid>`), kui see eemaldati kogemata. Pärast armuaja lõppu puhastab `storage prune`, `machine prune` ja `config prune` kirje automaatselt.

### Ühendamise ohutuse eelkontroll

Käsitletud eespool. `storage prune` ja `machine prune --prune-unknown` keelduvad kustutamast hoidlaid, mis on hetkel teotusmasinal ühendatud või töötavad. Alista ainult `--force-delete-mounted` abil.

### Rakenda vaikimisi; `--dry-run` eelvaateks

Kõik kolm kärpimiskäsku **rakendavad** muudatused vaikimisi. Edasta `--dry-run` kirjutamata eelvaateks. See vastab tegusõnale: "prune" on iseenesest destruktiivne, ja kuiva käivituse lipp on sõnaselge loobumisvõimalus.

## Konfigureerimine

### `pruneGraceDays`

Sea konfiguratsioonifailis kohandatud vaikearmuaeg, nii et sa ei pea iga kord `--grace-days` edastama:

```bash
# Sea armuaeg 14 päevale aktiivses konfiguratsioonis
rdc config field set --pointer /defaults/pruneGraceDays --new 14
```

`--grace-days` CLI lipp alistab selle väärtuse, kui see on esitatud.

### Eeliskord

1. `--grace-days <N>` lipp (kõrgeim prioriteet)
2. `pruneGraceDays` konfiguratsioonifailis
3. Sisseehitatud vaikeväärtus: 7 päeva

## Parimad tavad

- **Käivita tootmises esmalt kuiv käivitus.** Vaata enne destruktiivse kärpimise teostamist alati ette, eriti tootmise mäluhoidla puhul.
- **Hoia mitut konfiguratsiooni ajakohasena.** Mäluhoidla ja masina kärpimine kontrollivad kõiki konfiguratsioone konfiguratsioonikataloogis. Kui konfiguratsioonifail on aegunud või kustutatud, kaotavad selle hoidlad kaitse. Hoia konfiguratsioonifailid täpsena.
- **Eelista `--prune-unknown` vs `--orphaned-repos`.** Kirurgiline lipp austab renet-peegli; jäme lipp kustutab rõõmsalt teiste tööriistade loodud forkid.
- **Kasuta tootmises suuremeelseid armuaegu.** Vaikimisi 7-päevane armuaeg sobib enamiku töövoogudega. Ebaregulaarsetel hooldusakendega tootmiskeskkondade jaoks kaaluge 14 või 30 päeva.
- **Ajasta mäluhoidla kärpimine pärast varunduskäivitusi.** Sidumine `storage prune` sinu varundusajakavaga, et hoida mäluhoidla kulusid kontrolli all ilma käsitsi sekkumiseta.
- **Kombineeri masina kärpimine varundusajakavaga.** Pärast varundusajakavade juurutamist (`rdc machine backup schedule`) lisa perioodiline masina kärpimine, et puhastada aegunud hetktõmmised ja orvuks jäänud andmehoidla artefaktid.
- **Käivita `config prune` perioodiliselt.** Kohaliku konfiguratsiooni paisumine (eriti serdi vahemälu) koguneb vaikselt; kord kvartalis tehtud `config prune --dry-run` on piisav selle tabamiseks.
- **Auditeeri enne `--force` või `--force-delete-mounted` kasutamist.** Mõlemad lipud mööduvad ohutuskontrollidest. Kasuta `--force` ainult siis, kui oled kindel, et ükski teine konfiguratsioon ei viita küsimuses olevatele hoidlatele; kasuta `--force-delete-mounted` ainult siis, kui oled kindel, et masina elav olek on vale.
