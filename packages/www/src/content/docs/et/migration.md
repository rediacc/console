---
title: "Migratsioonijuhend"
description: "Olemasolevate projektide migreerimine krüpteeritud Rediacc hoidlatesse."
category: "Guides"
order: 11
language: et
sourceHash: "4517142676f9fa8f"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# Migratsioonijuhend

Migreerige olemasolev projekt, failid, Dockeri teenused, andmebaasid, traditsiooniliselt serverilt või kohalikust arenduskeskkonnast krüpteeritud Rediacc hoidlasse.

## Eeltingimused

- `rdc` CLI installitud ([Installatsioon](/en/docs/installation))
- Masin lisatud ja ettevalmistatud ([Seadistus](/en/docs/setup))
- Serveri kettaruum on piisav teie projekti jaoks (kontrollige `rdc machine query` abil)

## Samm 1: Looge hoidla

Looge krüpteeritud hoidla, mis mahutab teie projekti. Eraldage lisaruumi Dockeri piltide ja konteinerite andmete jaoks.

```bash
rdc repo create --name my-project -m server-1 --size 20G
```

> **Vihje:** Suurust saate hiljem muuta `rdc repo resize` abil vajadusel, kuid hoidla peab enne olema lahti ühendatud. Lihtsam on alustada piisava ruumiga.

## Samm 2: Laadige oma failid üles

Kasutage `rdc repo sync upload`, et edastada projekti failid hoidlasse.

```bash
# Eelvaade edastatavast (muudatusi ei tehta)
rdc repo sync upload -m server-1 -r my-project --local ./my-project --dry-run

# Failide üleslaadimine
rdc repo sync upload -m server-1 -r my-project --local ./my-project
```

Hoidla peab olema ühendatud enne üleslaadimist. Kui seda pole veel tehtud:

```bash
rdc repo mount --name my-project -m server-1
```

Järgnevate sünkroonimiste jaoks, kus soovite kaugserveri täpselt vastata oma kohalikule kaustale:

```bash
rdc repo sync upload -m server-1 -r my-project --local ./my-project --mirror
```

> Lipp `--mirror` kustutab kaugserveris failid, mis ei ole kohalikult olemas. Kasutage esmalt `--dry-run` kontrollimiseks.

## Samm 3: Parandage failide omandiõigus

Üleslaaditud failid saabuvad teie kohaliku kasutaja UID-ga (nt 1000). Rediacc kasutab üldkasutajat (UID 7111), et VS Code, terminaliseanssid ja tööriistad omaksid järjepidevat juurdepääsu. Käivitage omandiõiguse käsk teisendamiseks:

```bash
rdc repo ownership --name my-project -m server-1
```

### Dockeri-teadlik välistamine

Kui Dockeri konteinerid töötavad (või on töötanud), tuvastab omandiõiguse käsk automaatselt nende kirjutatavad andmekaustad ja **jätab need vahele**. See takistab konteinerite katkemist, mis haldavad oma faile eri UID-dega (nt MariaDB kasutab UID 999, Nextcloud kasutab UID 33).

Käsk teatab, mida see teeb:

```
Excluding Docker volume: database/data
Excluding Docker volume: redis/data
Ownership set to UID 7111 (245 changed, 4 skipped, 0 errors)
```

### Millal käivitada

- **Pärast failide üleslaadimist**, et teisendada kohalik UID 7111-ks
- **Pärast konteinerite käivitamist**, kui soovite Dockeri mahukaustad automaatselt välistada. Kui konteinereid pole veel käivitatud, pole mahte, mida välistada, ja kõik kaustad saavad chown'itud (mis on hästi, konteinerid loovad oma andmed esimesel käivitusel uuesti)

### Sunnirežiim

Dockeri mahu tuvastamise vahele jätmiseks ja kõige, sealhulgas konteinerite andmekataloogide, chown'imiseks:

```bash
rdc repo ownership --name my-project -m server-1
```

> **Hoiatus:** See võib katkestada töötavaid konteinereid. Peatage need esmalt vajaduse korral `rdc repo down` abil.

### Kohandatud UID

Vaikimisi 7111-st erineva UID seadistamiseks:

```bash
rdc repo ownership --name my-project -m server-1 --uid 1000
```

> **Ettevaatus:** `7111` on kõikjal kasutatav universaalne Rediacc UID (see vastab devcontaineri pilti põimitud `rediacc` kasutajale). Seda tuleks `--uid` abil üle kirjutada ainult selleks, et tagada ühilduvus konkreetse välise UID-ga omistatud failidega. See **ei** ole migratsioonisihtmärk. Uued hoidlad peaksid säilitama vaikeväärtuse.

## Samm 4: Seadistage oma Rediaccfile

Looge `Rediaccfile` projekti juures. See Bash-skript määratleb, kuidas teie teenused käivitatakse ja peatatakse.

```bash
#!/bin/bash

up() {
    renet compose -- up -d
}

down() {
    renet compose -- down
}
```

Kaks elutsüklifunktsiooni:

| Funktsioon | Eesmärk | Tõrke käitumine |
|----------|---------|----------------|
| `up()` | Käivita teenused | Juure tõrge on kriitiline; alamkausta tõrked logitakse ja jätkuvad |
| `down()` | Peata teenused | Parima pingutusega: proovib alati kõiki |

> **Oluline:** Kasutage oma Rediaccfile'is alati `renet compose --` asemel `docker compose`. `renet compose` ümbris jõustab hosti võrguse, CRIU kontrollpunkti/taastamise võimalused, IP eraldamise ja renet-poxy nõutud teenuse tuvastamise. `docker compose` otsene kasutamine möödub kõigist neist ja lükatakse valideerimise ajal tagasi.
>
> Ärge kasutage ka `sudo docker`, `sudo` lähtestab keskkonna muutujad sealhulgas `DOCKER_HOST`, mis põhjustab konteinerite loomist süsteemi Dockeri deemonis hoidla eraldatud deemoni asemel. Rediaccfile funktsioonid töötavad juba piisavate privileegidega.

Vt täpseid üksikasju Rediaccfile'ide, mitme teenuse paigutuste ja täitmise järjekorra kohta [Teenustest](/en/docs/services).

## Samm 5: Konfigureerige teenuse võrk

Rediacc käitab eraldatud Dockeri deemoni hoidla kohta. Teenused kasutavad `network_mode: host` ja seovad unikaalsete loopback-IP-dega, et nad saaksid kasutada standardporte ilma hoidlate vaheliste konfliktideta.

### docker-compose.yml kohandamine

**Enne (traditsiooniline):**

```yaml
services:
  postgres:
    image: postgres:16
    ports:
      - "5432:5432"
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
    environment:
      POSTGRES_PASSWORD: secret

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  app:
    image: my-app:latest
    ports:
      - "8080:8080"
    environment:
      DATABASE_URL: postgresql://postgres:secret@postgres:5432/mydb
      REDIS_URL: redis://redis:6379
```

**Pärast (Rediacc):**

```yaml
services:
  postgres:
    image: postgres:16
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
    environment:
      POSTGRES_PASSWORD: secret

  redis:
    image: redis:7-alpine

  app:
    image: my-app:latest
    environment:
      DATABASE_URL: postgresql://postgres:secret@postgres:5432/mydb
      REDIS_URL: redis://redis:6379
      LISTEN_ADDR: 0.0.0.0:8080
```

Peamised muutused:

1. **Eemaldage `ports:` vastendused** -- `renet compose` kasutab hosti võrgustamist ja eemaldab portide vastendused automaatselt
2. **Eemaldage `network_mode: host`** -- `renet compose` lisab selle teie eest
3. **Taaskäivituspoliitikat on ohutu hoida** -- renet eemaldab need automaatselt CRIU ühilduvuse jaoks ja marsruuteri valvekoer taastab peatunud konteinerid automaatselt
4. **Kasutage teenuse nimesid teenusetevaheliste ühenduste jaoks** (nt `postgres`, `redis`) -- renet sisestab iga teenuse nime lahendatava hostinimena. Ärge manustage ühendusstringe, mis salvestatakse andmebaasidesse või konfiguratsioonifailidesse, tooreid IP-sid; kasutage selle asemel teenuse nime, et hargnemise eraldus püsiks
5. **Sidumine on automaatne** -- tuum kirjutab `bind()` ümber õigele loopback-IP-le. Teenused saavad kasutada `0.0.0.0` või `localhost`

`{SERVICE}_IP` muutujad on endiselt saadaval, kui vajate neid, kuid sõnaselge sidumine ei ole enam vajalik. Sidumine toimub automaatselt. Nimetamise konventsioon: suurtähtedega, sidekriipsud asendatud alljoontega, järelliide `_IP`. Näiteks `listmonk-app` saab `LISTMONK_APP_IP`.

Vt IP eraldamise ja `.rediacc.json` üksikasju [Teenuse võrgust](/en/docs/services#service-networking-rediaccjson).

## Samm 6: Käivitage teenused

Ühendage hoidla (kui pole veel ühendatud) ja käivitage kõik teenused:

```bash
rdc repo up --name my-project -m server-1
```

See teeb järgmist:
1. Ühendab krüpteeritud hoidla
2. Käivitab eraldatud Dockeri deemoni
3. Genereerib automaatselt `.rediacc.json` koos teenuse IP eraldamistega
4. Käivitab `up()` kõikidest Rediaccfile'idest

Kontrollige, et teie konteinerid töötavad:

```bash
rdc machine containers --name server-1
```

## Samm 7: Lubage autostart (valikuline)

Vaikimisi tuleb hoidlad pärast serveri taaskäivitamist käsitsi ühendada ja käivitada. Lubage autostart, et teie teenused käivituksid automaatselt:

```bash
rdc repo autostart enable --name my-project -m server-1
```

Teilt küsitakse hoidla paroolifraasi.

> **Turvamärkus:** Autostart salvestab serverile LUKS-võtmefaili. Igaüks, kellel on juurjuurdepääs, saab hoidla ühendada ilma paroolifraasita. Vt üksikasju [Autostardist](/en/docs/services#autostart-on-boot).

## Levinud migratsioonistsenaariumid

### WordPress / PHP koos andmebaasiga

```
my-wordpress/
├── Rediaccfile
├── docker-compose.yml
├── app/                    # WordPress failid (UID 33 töötades)
├── database/data/          # MariaDB andmed (UID 999 töötades)
└── wp-content/uploads/     # Kasutaja üleslaadimised
```

1. Laadige üles oma projekti failid
2. Käivitage esmalt teenused (`rdc repo up`), et konteinerid loovad oma andmekaustad
3. Käivitage omandiõiguse parandus, MariaDB ja rakenduste andmekaustad jäetakse automaatselt vahele

### Node.js / Python koos Redisega

```
my-api/
├── Rediaccfile
├── docker-compose.yml
├── src/                    # Rakenduse lähtetekst
├── node_modules/           # Sõltuvused
└── redis-data/             # Redise püsimine (UID 999 töötades)
```

1. Laadige projekt üles (kaaluge `node_modules` välistamist ja tõmbamist `up()` funktsioonis)
2. Käivitage omandiõiguse parandus pärast konteinerite käivitamist

### Kohandatud Dockeri projekt

Mis tahes Dockeri teenustega projekti jaoks:

1. Laadige projekti failid üles
2. Kohandage `docker-compose.yml` (vt Samm 5)
3. Looge `Rediaccfile` elutsüklifunktsioonidega
4. Käivitage omandiõiguse parandus
5. Käivitage teenused

## Tõrkeotsing

### Juurdepääs keelatud pärast üleslaadimist

Failidel on endiselt teie kohalik UID. Käivitage omandiõiguse käsk:

```bash
rdc repo ownership --name my-project -m server-1
```

### Konteiner ei käivitu

Kontrollige, et teenused töötavad ja vaadake nende logid üle:

```bash
# Kontrollige eraldatud IP-sid
rdc term connect -m server-1 -r my-project -c "cat .rediacc.json"

# Kontrollige konteineri logisid
rdc term connect -m server-1 -r my-project -c "docker logs <container-name>"
```

### Pordi konflikt hoidlate vahel

Iga hoidla saab unikaalsed loopback-IP-d ja tuum kirjutab automaatselt `bind()` kutsed õigele IP-le ümber. Portide konfliktid hoidlate vahel ei esine. Kui näete ootamatut käitumist, kontrollige, et teenused on käivitatud `renet compose` kaudu (mitte `docker compose`). **Teistele teenustele** ühendamiseks kasutage teenuse nime (nt `postgres`), mitte toorkeid IP-sid. Teenuse nimed lahenduvad õigesti igas hargnemises.

### Omandiõiguse parandus katkestab konteinerid

Kui käivitasite `rdc repo ownership` ja konteiner lakkas töötamast, chown'iti konteineri andmefailid. Peatage konteiner, kustutage selle andmekaust ja taaskäivitage. Konteiner loob selle uuesti:

```bash
rdc repo down --name my-project -m server-1
# Kustutage konteineri andmekaust (nt database/data)
rdc repo up --name my-project -m server-1
```
