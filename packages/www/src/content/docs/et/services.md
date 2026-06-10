---
title: Teenused
description: >-
  Juurutage ja hallake konteineripõhiseid teenuseid Rediaccfile'ide, teenuse
  võrgunduse ja automaatkäivituse abil.
category: Guides
order: 5
language: et
sourceHash: "aa77a4f937206e58"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# Teenused

Siin on, mida see lehekülg käsitleb: konteineripõhiste teenuste juurutamine ja haldamine, sealhulgas Rediaccfile'id, teenuse võrgundus, käivitamine/peatamine, hulgioperatsioonid ja automaatkäivitus.

## Rediaccfile

**Rediaccfile** on Bash-skript, mis määrab, kuidas teie teenuseid käivitatakse ja peatatakse. See **laaditakse** (ei käivitata eraldi protsessina), seega jagavad selle funktsioonid sama kesta konteksti ja omavad juurdepääsu kõigile eksporditud keskkonna muutujatele. See peab olema nimetatud `Rediaccfile` või `rediaccfile` (tõsust sõltumatu) ja asuma repositooriumi ühendatud failisüsteemis.

Rediaccfile'id leitakse kahes asukohas:
1. Repositooriumi ühendusraja **juur**
2. Ühendusraja **esimese taseme alamkataloogid** (mitterelaatiivne)

Peidetud kataloogid (nimed algavad `.`-ga) jäetakse vahele.

### Elutsükli funktsioonid

Rediaccfile sisaldab kuni kahte funktsiooni:

| Funktsioon | Millal käivitub | Eesmärk | Vea käitumine |
|----------|-------------|---------|----------------|
| `up()` | Käivitamisel | Käivita teenused (nt `renet compose -- up -d`) | Juure tõrge on **kriitiline** (peatab kõik). Alamkataloogi tõrked on **mittekritiiilised** (logitakse, jätkab) |
| `down()` | Peatamisel | Peata teenused (nt `renet compose -- down`) | **Parima jõu põhimõttel** - tõrked logitakse, kuid kõiki Rediaccfile'e proovitakse alati |

Mõlemad funktsioonid on valikulised. Kui funktsiooni pole määratletud, jäetakse see vaikselt vahele.

### Täitmise järjekord

- **Käivitamisel (`up`):** Juure Rediaccfile esmalt, seejärel alamkataloogid **tähestikulises järjekorras** (A kuni Z).
- **Peatamisel (`down`):** Alamkataloogid **vastupidises tähestikulises järjekorras** (Z kuni A), seejärel juur viimasena.

### Keskkonna muutujad

Kui Rediaccfile'i funktsioon käivitub, on saadaval järgmised keskkonna muutujad:

| Muutuja | Kirjeldus | Näide |
|----------|-------------|---------|
| `REDIACC_WORKING_DIR` | Repositooriumi ühendusrada | `/mnt/rediacc/mounts/abc123` |
| `REDIACC_REPOSITORY` | Repositooriumi GUID | `a1b2c3d4-e5f6-...` |
| `REDIACC_NETWORK_ID` | Võrgu ID (täisarv) | `2816` |
| `DOCKER_HOST` | Dockeri pesa selle repositooriumi isoleeritud deemoni jaoks | `unix:///var/run/rediacc/docker-2816.sock` |
| `{SERVICE}_IP` | Loopback-IP igale teenusele, mis on määratletud `.rediacc.json`-is | `POSTGRES_IP=127.0.11.2` |

`{SERVICE}_IP`-muutujad genereeritakse automaatselt `.rediacc.json`-i pesa kaardistustest ja eksporditakse enne teie Rediaccfile'i funktsioonide käivitamist. Nimetamiskonventsioon teisendab teenuse nime suurtähtedeks, asendab sidekriipsud alljoontega ja lisab siis `_IP`. Näiteks teenus nimega `listmonk-app` pesaga `0` saab `LISTMONK_APP_IP=127.0.11.2`.

> **Hoiatus: Ärge kasutage `sudo docker`-it Rediaccfile'ides.** Käsk `sudo` lähtestab keskkonna muutujad, mis tähendab, et `DOCKER_HOST` kaob ja Dockeri käsud suunatakse süsteemi deemonile repositooriumi isoleeritud deemoni asemel. See katkestab konteineri isoleerimise ja võib põhjustada pordinäitude. Rediacc blokeerib täitmise, kui tuvastab `sudo docker` ilma `-E`-ta.
>
> Kasutage oma Rediaccfile'ides `renet compose`-it, see käsitseb automaatselt `DOCKER_HOST`-i, süstib võrgunduse sildid teeserveri avastamiseks ja konfigureerib teenuse võrgunduse. Vaadake [Võrgundus](/en/docs/networking) üksikasjade saamiseks, kuidas teenused puhverserveri kaudu avastuvad. Dockeri otsene kutsumine ilma sudo-ta, Rediaccfile'i funktsioonid juba töötavad piisavate õigustega. Kui peate sudo-d kasutama, kasutage `sudo -E docker` keskkonna muutujate säilitamiseks.
>
> `renet` on kaugjuhtimise madala taseme tööriist. Tavaliste kasutaja töövoode jaoks oma tööjaamast eelistage `rdc` käske nagu `rdc repo up` ja `rdc repo down`. Vaadake [rdc vs renet](/en/docs/rdc-vs-renet).

### Näide

```bash
#!/bin/bash

up() {
    echo "Starting services..."
    renet compose -- up -d
}

down() {
    echo "Stopping services..."
    renet compose -- down
}
```

> **Tähtis:** Kasutage alati `renet compose --` `docker compose` asemel. `renet compose` ümbris jõustab host-võrgunduse, IP-eraldise ja teenuste avastamise silte, mida renet-proxy nõuab. CRIU kontrollpunkti/taastamise võimalused lisatakse konteineritele sildiga `rediacc.checkpoint=true`. Otsene `docker compose` kasutamine lükatakse tagasi Rediaccfile'i valideerimisega. Vaadake [Võrgundus](/en/docs/networking) üksikasjade saamiseks.

### Mitmeteenuseline paigutus

Mitme sõltumatu teenuste rühma projektide jaoks kasutage alamkatalooge:

```
/mnt/rediacc/repos/my-app/
├── Rediaccfile              # Juur: jagatud seadistus
├── docker-compose.yml
├── database/
│   ├── Rediaccfile          # Andmebaasiteenused
│   └── docker-compose.yml
├── backend/
│   ├── Rediaccfile          # API-server
│   └── docker-compose.yml
└── monitoring/
    ├── Rediaccfile          # Prometheus, Grafana jne
    └── docker-compose.yml
```

Käivitamise (`up`) järjekord: juur, seejärel `backend`, `database`, `monitoring` (A-Z).
Peatamise (`down`) järjekord: `monitoring`, `database`, `backend`, seejärel juur (Z-A).

## Teenuse võrgundus (.rediacc.json)

Iga repositoorium saab /26-alamvõrgu (64 IP-d) `127.x.x.x`-loopback-vahemikus. Teenused seovad end kordumatu loopback-IP-ga, et nad saaksid töötada samadel portidel ilma konfliktideta.

### .rediacc.json-fail

Kaardistab teenuste nimed **pesa**-numbritega. Iga pesa vastab kordumatul IP-aadressile repositooriumi alamvõrgus.

```json
{
  "services": {
    "api": {"slot": 0},
    "postgres": {"slot": 1},
    "redis": {"slot": 2}
  }
}
```

### Autogenereeriminer Docker Composest

Te ei pea `.rediacc.json`-i käsitsi looma. Kui käivitate `rdc repo up`, teeb Rediacc automaatselt:

1. Skaneerib kõik kataloogid, mis sisaldavad Rediaccfile'i, compose-failide jaoks (`docker-compose.yml`, `docker-compose.yaml`, `compose.yml` või `compose.yaml`)
2. Ekstraktib teenuste nimed `services:` jaotisest
3. Omistab järgmise saadaoleva pesa uutele teenustele
4. Salvestab tulemuse `{repository}/.rediacc.json`-sse

### IP-arvutus

Teenuse IP arvutatakse repositooriumi võrgu ID ja teenuse pesa põhjal. Võrgu ID jaotatakse `127.x.y.z`-loopback-aadressi teise, kolmanda ja neljanda okteti vahel. Teenused algavad nihe 2-st:

| Nihe | Aadress | Eesmärk |
|--------|---------|---------|
| .0 | `127.0.11.0` | Võrgu aadress (reserveeritud) |
| .1 | `127.0.11.1` | Lüüs (reserveeritud) |
| .2–.62 | `127.0.11.2–127.0.11.62` | Teenused (`pesa + 2`) |
| .63 | `127.0.11.63` | Leviaadress (reserveeritud) |

**Näide** võrgu ID `2816` (`0x0B00`), baasiaaadress `127.0.11.0`:

| Teenus | Pesa | IP-aadress |
|---------|------|------------|
| api | 0 | `127.0.11.2` |
| postgres | 1 | `127.0.11.3` |
| redis | 2 | `127.0.11.4` |

Iga repositoorium toetab kuni **61 teenust** (pesad 0 kuni 60).

### Teenuse IP-de kasutamine Docker Composessas

Kuna iga repositoorium käitab isoleeritud Dockeri deemonit, konfigureerib `renet compose` automaatselt kõigile teenustele `network_mode: host`. Kernel kirjutab `bind()` kutsed läbipaistvalt teenuse määratud loopback-IP-le, nii et teenused saavad seotuda `0.0.0.0`-le või `localhost`-ile ilma konfliktideta. **Teiste teenustega** ühenduse loomiseks kasutage **teenuse nime**. renet süstib iga teenuse nime hostinimi, mis lahendatakse alati õigele IP-le, isegi forkides:

```yaml
services:
  postgres:
    image: postgres:16
    environment:
      PGDATA: /var/lib/postgresql/data
      POSTGRES_PASSWORD: secret
    # Selgesõnaline listen_addresses pole vaja - kernel kirjutab sidumise õige loopback-IP-le

  api:
    image: my-api:latest
    environment:
      DATABASE_URL: postgresql://postgres:secret@postgres:5432/mydb  # kasuta teenuse nime
      LISTEN_ADDR: 0.0.0.0:8080                                      # kernel kirjutab teenuse IP-le
```

> **Teenuse nimed ühendusteks:** Kasutage **teenuse nime** (nt `postgres`, `redis`) et **ühenduda teiste teenustega** - renet kaardistab automaatselt iga teenuse nime selle loopback-IP-ga `/etc/hosts` kaudu. `${POSTGRES_IP}` sisestamine andmebaaside või konfiguratsioonifailides talletatud ühendusstringidesse küpsetab raakIP, mis katkestab forgi isoleerimise ja on **valideerimise viga**. `${SERVICE_IP}` muutujad on endiselt saadaval selgesõnaliseks kasutamiseks, kuid sidumine käsitleb kernel automaatselt.

> **Märkus:** Ärge lisage `network_mode: host` käsitsi, `renet compose` süstib selle automaatselt. Taaskäivituspoliitikad (nt `restart: always`) on ohutu kasutada, renet eemaldab need automaatselt CRIU ühilduvuse jaoks ja teeserver valvekoer käsitleb konteineri taastamist.

### Konteineri taastamine ja taaskäivituspoliitika

renet ja Docker ei nõustu tahtlikult, kuidas käsitleda konteineri taaskäivitusi. Jaotuse mõistmine on oluline silumisel, miks konteiner jäi püsti või ei jäänud.

**Taaskäivituspoliitika tõlkimine.** Kui kirjutate `restart: always` (või `unless-stopped` või `on-failure`) oma compose-faili, **eemaldab** renet selle tegeliku compose-juurutuse sünteesimisel ja asendab `restart: no`-ga. Algne väärtus salvestatakse repositooriumi `.rediacc.json`-sse `services.<name>.restart_policy` alla. See takistab Dockeri deemoni taseme automaatne taaskäivitus sekkumast CRIU kontrollpunkti/taastamisega (deemoni juhtitud taaskäivitus jätkuks vanast eelkontrollpunkti olekust).

**Valvekoera jõustamine.** Teeserveri valvekoer töötab perioodiliselt igal masinal. Iga tiksuga:

1. Loeb `.rediacc.json`-i igale repositooriumile ja leiab teenused taastatava `restart_policy`-ga.
2. Loetleb kõik konteinerid selle repositooriumi deemoni jaoks, tuvastab peatatud ja taaskäivitab neid salvestatud poliitika järgi. 30-sekundiline armuaeg hoiab ära võitlemise operaatoriga, kes just käivitas `docker stop`.
3. Sama tsükkel käsitleb ka `/var/run/rediacc/cold-backup-<guid>.running.json`-i (vaadake [Külma varukoopia semantika](backup-restore.md#cold-backup-semantics)). Loetletud konteinerid taaskäivitatakse sõltumata salvestatud poliitikast, kuna külgfail tähendab "renet peatas need tahtlikult ja võlgneb operaatorile taaskäivituse."

**Miks `on-failure` võib tunduda katkisena.** Dockeri `on-failure` poliitika taaskäivitab ainult siis, kui konteiner väljub nullist erineva koodiga. Sujuv peatus (väljumiskood 0) `docker stop` käsk või deemoni sulgemine ei ole "tõrge" ega käivita taaskäivitust, ei Dockeri natiivsele loogikale ega valvekoera salvestatud poliitika teele. Külm varukoopia külgfail on turvavõrk: iga konteiner, mille me tahtlikult peatame, taaskäivitatakse sõltumata selle poliitikast.

**Kuidas tõlgendada käitusaja olekut:**

- `docker inspect <container>` → `RestartPolicy.Name`: renet-hallatavate konteinerite jaoks on alati `no`. Ärge tuginege sellele semantilise poliitika jaoks.
- `.rediacc.json` repositooriumi ühendusraja juures → `services.<name>.restart_policy`: tegelik kavatsus.
- `docker ps --format '{{.Status}}'`: käitusaja olek.

**Kuidas triivi parandada.** Kui konteineri `.rediacc.json`-sse salvestatud poliitika on vale (näiteks sellepärast, et muutsite compose'i, kuid ei loonud kunagi konteinerit uuesti), käivitage uuesti `rdc repo up --name <repo> -m <machine>`. Konteiner luuakse uuesti koos uuendatud salvestatud poliitikaga.

> **Eksperimentaalne:** Külma varukoopia külgfailist taastamine ja `--sync-certs` lipp `rdc machine query` saadeti renet 0.9+-s. Vanemad versioonid toetuvad ainult salvestatud `restart_policy`-le valvekoera taastamiseks, mis võib jätta `on-failure` konteinerid külma varukoopia järel ummikusse.

> **Dockeri silla võrgundus on keelatud repositooriumipõhiste deemonite jaoks.** Iga repositooriumipõhine deemon (`FlavorRediacc`) on konfigureeritud koos `"bridge": "none"` ja `"iptables": false`-ga. Tavaline `docker run <image>` repositooriumi kestus käivitub siiski, kuid konteiner saab ainult loopback-liidese ning ei oma DNS-i ega väljuvat ühendust. See on disaini järgi, kuna repositooriumite vaheline loopback-isoleerimine on jõustatud eBPF-cgroup-konksude abil, millest sillaga konteiner möödub. Tootmisteenused peaksid kasutama `renet compose`-it (mis süstib hosti võrgunduse teie eest); ad-hoc silumisel edastage `--network host` selgesõnaliselt: `docker run --rm --network host -it ubuntu bash`.
>
> Kasutajapõhised Hub-deemonid (`FlavorHub`, mida kasutatakse arenduskeskkondades) on erand: nad sestavad `bridge="docker0"`, `iptables=true` ja `live-restore=true`, nii et kasutaja käivitatud konteinerid saavad normaalse silla võrgunduse ja väljuvat ühendust.

> **Märkus:** Fork-repositooriumid saavad automaatsed teeserveri marsruudid vanema alamdomeeni all: `{service}-fork-{tag}.{repo}.{machine}.{baseDomain}`. Forkide jaoks kohandatud domeenid jäetakse vahele.

## Teenuste käivitamine

Ühendage repositoorium ja käivitage kõik teenused:

```bash
rdc repo up --name my-app -m server-1
```

| Valik | Kirjeldus |
|--------|-------------|
| `--detach` | Tagasta kohe, kui konteinerid on käivitatud; tervisekontrollid jätkavad taustal |
| `--skip-router-restart` | Jätke teeserveri taaskäivitamine pärast toimingut vahele |

Täitmise järjekord on:
1. Ühendage LUKS-krüpteeritud repositoorium (ühendatakse automaatselt, kui lahti ühendatud)
2. Käivitage isoleeritud Dockeri deemon
3. Genereerige `.rediacc.json` automaatselt compose-failidest
4. Käivitage `up()` kõigis Rediaccfile'ides (A-Z järjekorras)

Pärast juurutamist näitab väljund **PROXY ROUTES** jaotist iga teenuse tegelike URL-idega. Teenused kohandatud Traefiku siltidega (nt `traefik.http.routers.myapp.rule=Host(...)`) näitavad oma kohandatud domeene peamiste URL-idena:

```
HTTP services (accessible via proxy after ~3s):
  gitlab-server:
    HTTPS: https://gitlab.example.com  (custom)
    Auto:  https://gitlab-server.gitlab.server-1.example.com
    IP:    127.0.11.130
```

Teenused ilma kohandatud Traefiku siltideta näitavad ainult automaatselt genereeritud teeserveri marsruuti. Kasutage neid URL-e (mitte CLI-le prinditud üldist mustrit) brauseri juurdepääsuks, API kutsete jaoks ja teenuste vaheliseks konfiguratsiooniks.

### Eraldusrežiimis käivitamine

`--detach`-iga naaseb käsk kohe, kui konteinerid on käivitatud, ootamata tervisekontrollide lõppemist. Käivitamine jätkub taustal: puhverserver kordab ühendustkatseid ülesvoolu, kuni iga teenus end seob, nii et marsruudid taastuvad omal käel. Edenemist saab jälgida käsuga `rdc machine query --containers --name <machine>`. Sobib suurepäraselt ühekordsetele kahvlitele ja skriptitud silmustele, kus järgmine samm ei nõua teenuste valmidust.

### Valmisolekuproov

Pärast `up()` käivitamist testib renet iga HTTP-teenust, kuni see aktsepteerib TCP-ühendusi; see väldib puhverserveri 502-viga esimesel brauseripäringul. Teenused, mille konteinerid sisaldavad Dockeri tervisekontrolli, on otse usaldusväärsed: terve konteiner jätab proovi vahele ja `start_period`-is viibiv konteiner logib informatiivse teate, mitte hoiatuse. Proov annab 15 sekundi pärast alla (muutke käitusajal masinale seades `REDIACC_READINESS_TIMEOUT` sekunditeks); eraldusrežiimis käivitamine jätab selle täielikult vahele.

## Teenuste peatamine

```bash
rdc repo down --name my-app -m server-1
```

| Valik | Kirjeldus |
|--------|-------------|
| `--unmount` | Lahtiühendage krüpteeritud repositoorium pärast peatamist. Kui see ei rakendu, kasutage `rdc repo unmount` eraldi. |
| `--skip-router-restart` | Jätke teeserveri taaskäivitamine pärast toimingut vahele |

Täitmise järjekord on:
1. Käivitage `down()` kõigis Rediaccfile'ides (Z-A vastupidises järjekorras, parima jõu põhimõttel)
2. Peatage isoleeritud Dockeri deemon (kui `--unmount`)
3. Lahtiühendage ja sulgege LUKS-krüpteeritud maht (kui `--unmount`)

## Hulgioperatsioonid

Käivitage või peatage kõik repositooriumid masinal korraga:

```bash
rdc repo up -m server-1
```

| Valik | Kirjeldus |
|--------|-------------|
| `--include-forks` | Kaasa forkitud repositooriumid |
| `--mount-only` | Ainult ühenda, ära käivita konteinereid |
| `--dry-run` | Näita, mida tehtaks |
| `--parallel` | Käivita toimingud paralleelselt |
| `--concurrency <n>` | Maksimaalsed samaaegsed toimingud (vaikimisi: 3) |
| `--skip-router-restart` | Jätke teeserveri taaskäivitamine pärast toimingut vahele |

## Automaatkäivitus käivitamisel

Vaikimisi tuleb repositooriumid pärast serveri taaskäivitust käsitsi ühendada ja käivitada. **Automaatkäivitus** muudab repositooriumid automaatselt ühendama, Dockerit käivitama ja Rediaccfile'i `up()`-i käivitama serveri käivitamisel.

### Kuidas see töötab

Kui lubate repositooriumile automaatkäivituse:

1. Genereeritakse 256-baidine juhuslik LUKS-võtmefail ja lisatakse repositooriumi LUKS-pessa 1 (pesa 0 jääb kasutaja paroolilaususeks)
2. Võtmefail salvestatakse `{datastore}/.credentials/keys/{guid}.key`-sse õigustega `0600` (ainult root)
3. Systemd-teenus (`rediacc-autostart`) käivitub käivitamisel, et ühendada kõik lubatud repositooriumid ja käivitada nende teenused

Sulgemise ajal peatab teenus sujuvalt kõik teenused (Rediaccfile'i `down()`), peatab Dockeri deemonid ja sulgeb LUKS-mahud.

> **Turvamärkus:** Automaatkäivituse lubamine salvestab LUKS-võtmefaili serveri kettale. Igaüks, kellel on root-juurdepääs serverile, saab repositooriumi ühendada ilma paroolilaususeta. Hinnake seda oma ohumudelil põhinedes.

### Lubamine

```bash
rdc repo autostart enable --name my-app -m server-1
```

Teilt küsitakse repositooriumi paroolilauset.

### Kõigi lubamine

```bash
rdc repo autostart enable -m server-1
```

### Keelamine

```bash
rdc repo autostart disable --name my-app -m server-1
```

See eemaldab võtmefaili ja tapab LUKS-pesa 1.

### Võtmefaili uuendamine juurutamisel

Kui automaatkäivitus on lubatud, valideerib `rdc repo up` LUKS-pesa 1 võtmefaili.
Kui kettale salvestatud võtmefail ühtib endiselt LUKS-pesaga, muudatusi ei tehta.

Pärast repositooriumi ülekandmist masinate vahel `repo push` / `repo pull` kaudu
ei ühti võtmefail uuel masinal. Sellisel juhul regenereerib `repo up` automaatselt
võtmefaili ja uuendab LUKS-pesa 1. Näete logisõnumeid:

```
Refreshing keyfile credential for <guid>
Killing LUKS slot 1: /mnt/rediacc/repositories/<guid>
Adding keyfile to LUKS slot 1: /mnt/rediacc/repositories/<guid>
```

See on ohutu, pesa 0 (teie paroolilause) ei muudeta kunagi. Kui automaatkäivitus pole
lubatud, jäetakse kontroll vaikselt vahele. Ebaõnnestumised ei ole surmavad ega blokeeri
juurutamist.

### Oleku loetlemine

```bash
rdc repo autostart list -m server-1
```

Üksikasjade saamiseks selle kohta, kuidas perioodiline leppija taastab pärast käivitamist seiskunud repositooriumeid, vaadake [Automaatkäivitus ja taastamine](/et/docs/autostart-recovery).

## Täielik näide

See juurutab veebirakenduse PostgreSQL-i, Redise ja API-serveriga.

### 1. Seadistamine

```bash
curl -fsSL https://www.rediacc.com/install.sh | bash
rdc config init --name production --ssh-key ~/.ssh/id_ed25519
rdc config machine add --name prod-1 --ip 203.0.113.50 --user deploy
rdc config machine setup --name prod-1
rdc repo create --name webapp -m prod-1 --size 10G
```

### 2. Ühendamine ja ettevalmistamine

```bash
rdc repo mount --name webapp -m prod-1
```

### 3. Rakenduse failide loomine

Looge repositooriumi sees:

**docker-compose.yml:**

```yaml
services:
  postgres:
    image: postgres:16
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
    environment:
      POSTGRES_DB: webapp
      POSTGRES_USER: app
      POSTGRES_PASSWORD: changeme

  redis:
    image: redis:7-alpine

  api:
    image: myregistry/api:latest
    environment:
      DATABASE_URL: postgresql://app:changeme@postgres:5432/webapp
      REDIS_URL: redis://redis:6379
      LISTEN_ADDR: 0.0.0.0:8080
```

**Rediaccfile:**

```bash
#!/bin/bash

up() {
    mkdir -p data/postgres
    renet compose -- up -d

    echo "Waiting for PostgreSQL..."
    for i in $(seq 1 30); do
        if renet compose -- exec postgres pg_isready -q 2>/dev/null; then
            echo "PostgreSQL is ready."
            return 0
        fi
        sleep 1
    done
    echo "Warning: PostgreSQL did not become ready within 30 seconds."
}

down() {
    renet compose -- down
}
```

### 4. Käivitamine

```bash
rdc repo up --name webapp -m prod-1
```

### 5. Automaatkäivituse lubamine

```bash
rdc repo autostart enable --name webapp -m prod-1
```

## Repositooriumipõhiste saladuste kasutamine compose'is

Ülaltoodud `POSTGRES_PASSWORD: changeme` kohatäite sobib õpetuseks, kuid päris rakendused vajavad päris mandaate ning nende sidumine compose-faili (või `.env`-faili repositooriumi sees) tähendab, et fork pärib need samuti. Juurutusaegsete mandaatide jaoks kasutage `rdc repo secret`. Väärtused asuvad väljaspool krüpteeritud repositooriumi pilti, nii et forkid alustavad tühja saladuste kaardiga.

Kaks edastusrežiimi töötavad compose'is:

**`env` režiim**. Interpoleerige `${REDIACC_SECRET_<KEY>}` kaudu mis tahes `environment:` väärtuses. renet ümbris edastab väärtuse juurutusajal konteineri keskkonda.

**`file` režiim**. Väärtus maandub host-pool tmpfs-faili aadressile `/var/run/rediacc/secrets/<networkID>/<KEY>` ja ühendate selle konteinerisse Dockeri compose'i standse `secrets:` ploki kaudu. Konteiner loeb faili `/run/secrets/<key>`. Eelistage seda režiimi kõige tundliku jaoks. Väärtused ei ilmu kunagi `docker inspect` ega `/proc/<pid>/environ` väljunditesse.

```yaml
services:
  api:
    image: myregistry/api:latest
    environment:
      DATABASE_URL: ${REDIACC_SECRET_DATABASE_URL}
    secrets:
      - stripe_live_key

secrets:
  stripe_live_key:
    file: /var/run/rediacc/secrets/${REDIACC_NETWORK_ID}/STRIPE_LIVE_KEY
```

Seemendage väärtused käsuga `rdc repo secret set --name <repo> --key DATABASE_URL --value <val> --mode env --current ""` ja faili-režiimi ekvivalendiga. Vaadake [Repositooriumid § Saladused](/en/docs/repositories#secrets) täieliku juhendi saamiseks ja [Repositooriumipõhised saladused](/en/docs/rdc-cheat-sheet#per-repo-secrets) käsuviite jaoks.

> **Repositooriumivahelised teed lükatakse tagasi valideerimise ajal.** Compose'i `secrets: file:` (või `configs: file:` või `env_file:`), mis osutab teise repositooriumi `/var/run/rediacc/secrets/<other-networkID>/` kataloogi, lükatakse renet-ümbriku poolt kõvasti tagasi enne docker compose'i käivitamist. `--unsafe` EI tühista seda. Kaitse süviti: Landlocki liivakast Rediaccfile'i kesta ümber piirab lugemist praeguse võrgu saladuste kataloogiga, nii et `cat /var/run/rediacc/secrets/<other>/X` Rediaccfile'i bash-ist ebaõnnestub EACCES-ga isegi kui see möödub YAML validaatorist. Te ei pea sisse lülitama; see on vaikimisi sees iga `repo up` jaoks.
