---
title: "Serveri viide"
description: "Kataloogipaigutus, renet-käsud, systemd-teenused ja tööprotsessid kaugserveri jaoks."
category: "Concepts"
order: 3
language: et
sourceHash: "4fb53bb4cb1512f6"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# Serveri viide

SSH-ga Rediacci serverisse sisenedes leiate: kataloogipaigutuse, `renet`-käsud, systemd-teenused ja tööprotsessid, mida vajate.

Enamik kasutajaid haldab servereid `rdc` kaudu oma tööjaamast ja ei vaja seda lehte kunagi. See leht on täpsema silumise või serveri otsese töötamise jaoks.

Kõrgetasemelise arhitektuuri kohta vaadake [Arhitektuur](/en/docs/architecture). `rdc` ja `renet` erinevuse kohta vaadake [rdc vs renet](/en/docs/rdc-vs-renet).

## Kataloogipaigutus

```
/mnt/rediacc/                          # Peamine andmesalv
├── repositories/                      # Krüpteeritud kettapildid (LUKS)
│   └── {uuid}                         # Igaüks on silmuseseadme pilt
├── mounts/                            # Ühenduspunktid dekrüpteeritud repositooriumite jaoks
│   └── {uuid}/
│       ├── .rediacc.json              # Teenus → IP-pesa kaardistus
│       ├── .rediacc/docker/           # Dockeri deemoni andmed (pildid, konteinerid)
│       └── {service-name}/            # Teenuse kataloog
│           ├── docker-compose.yml     # Compose'i definitsioon
│           ├── Rediaccfile            # Elutsükli konksud (bash)
│           └── data/                  # Püsivad andmed
├── immovable/                         # Kirjutuskaitstud jagatud sisu
├── .credentials/                      # Krüpteeritud saladused
└── .backup-*/                         # BTRFS-hetktõmmised

/opt/rediacc/proxy/                    # Traefiku pöördpuhverserver
├── docker-compose.yml
├── config.env                         # CERTBOT_EMAIL, CF_DNS_API_TOKEN
├── letsencrypt/                       # ACME-sertifikaadid
└── traefik/dynamic/                   # Dünaamilised marsruutifailid

/run/rediacc/docker-{id}.sock          # Võrgupõhised Dockeri pesad
/var/lib/rediacc/router/               # Marsruuteri olek (pordi eraldised)
```

## renet-käsud

`renet` on serveripoolne binaarne. Kõik käsud vajavad root-õigusi (`sudo`).

### Repositooriumi elutsükkel

```bash
# Loetle kõik repositooriumid
renet repository list

# Kuva repositooriumi üksikasjad
renet repository status --name {uuid}

# Käivita repositoorium (ühenda + käivita Rediaccfile up)
renet repository up --name {uuid} --network-id {id} --password-stdin

# Peata repositoorium (käivita Rediaccfile down)
renet repository down --name {uuid} --network-id {id}

# Loo uus repositoorium
renet repository create --name {uuid} --network-id {id} --size 2G --encrypted

# Fork (kohene koopia BTRFS-reflinkide abil)
renet repository fork --source {uuid} --target {new-uuid}

# Laienda töötavat repositooriumi (ilma seisakuta)
renet repository expand --name {uuid} --size 4G

# Kustuta repositoorium ja kõik selle andmed
renet repository delete --name {uuid} --network-id {id}
```

### Docker Compose

Käivitage compose-käsud konkreetse repositooriumi Dockeri deemoni vastu:

```bash
sudo renet compose -- up -d
sudo renet compose -- down
sudo renet compose -- logs -f
sudo renet compose -- config
```

Käivitage docker-käsud otse:

```bash
sudo renet docker --network-id {id} -- ps
sudo renet docker --network-id {id} -- logs -f {container}
sudo renet docker --network-id {id} -- exec -it {container} bash
```

Samuti saate kasutada Dockeri pesa otse:

```bash
DOCKER_HOST=unix:///run/rediacc/docker-{id}.sock docker ps
```

> Käivitage compose alati kataloogist, mis sisaldab `docker-compose.yml`-i, vastasel juhul Docker ei leia faili.

### Failisüsteemi liivakast

```bash
# Kontrollige Landlocki tuge
renet sandbox-exec --detect

# Käivitage käsk Landlocki liivakastis (kasutatakse sisemiselt)
renet sandbox-exec --allow-rw /path --allow-ro /usr --allow-exec /bin -- command
```

`sandbox-exec` rakendab Landlock LSM failisüsteemi piiranguid, seejärel käivitab antud käsu. Seda käivitatakse automaatselt `sandbox-gateway` poolt (SSH ForceCommand töötleja) kõigi repositooriumitasandi ühenduste jaoks.

### Kasutajapõhine Hub (arenduskeskkonnad)

Hub annab igale kasutajale arenduskeskkondade jaoks oma Dockeri demoni, mis on eraldatud repositooriumipõhistest `FlavorRediacc` demonitest.

```bash
# Kasutajapõhiste Hub systemd-üksuste installimine / eemaldamine
sudo renet hub install
sudo renet hub uninstall

# Jõudeolekus kasutajapõhiste Hub-demonite koristamine
sudo renet hub gc
```

Demonid töötavad ühes kahest flavori all, mis valitakse `--flavor` abil:

```bash
# Repositooriumipõhine isoleeritud demon (bridge=none, iptables=false) — vaikimisi
sudo renet daemon start-foreground --flavor=rediacc ...

# Kasutajapõhine Hub-demon (bridge=docker0, iptables=true, live-restore=true)
sudo renet daemon start-foreground --flavor=hub ...
```

`hub` flavor lubab tavalist bridge-võrgustikku, et kasutaja käitatavatel konteineritel oleks väljuv ühenduvus; `rediacc` flavor tagab repositooriumite vahelise loopback-isolatsiooni. Hubi auditiloge kirjutatakse asukohta `/var/log/rediacc/hub/<user>.log`.

**Lipud:**
- `--allow-rw`, `--allow-ro`, `--allow-exec`: Landlocki teereeglid
- `--home-overlay`: Ühenda OverlayFS kodu-kataloogi kohale repositooriumipõhise kirjutuse isoleerimiseks
- `--sandbox-dir`: Repositooriumipõhine tööala (`<datastore>/.interim/sandbox/<name>/`)
- `--work-dir`: Määrake töökataloog ja laadige `.envrc` repositooriumi keskkonna jaoks
- `--run-as`: Langeta õigused sihtkasutajale pärast seadistust
- `--reset-home`: Tühjendage repositooriumipõhine kodu-ülekate värske alguse jaoks

**`sandbox-gateway`** on SSH ForceCommand töötleja, mis on seatud `command=` kaudu `authorized_keys`-is. Iga repositooriumi SSH-võti käivitab lüüsi repositooriumi nimega sisse küpsetatud kujul, mida klient ei saa võltsida. Lüüs ehitab sandbox-exec argumendid ja käivitab sudo kaudu.

### Puhverserver ja marsruutimine

```bash
renet proxy status          # Kontrolli Traefiku + marsruuteri tervist
renet proxy routes          # Kuva kõik konfigureeritud marsruudid
renet proxy refresh         # Värskenda marsruute töötavatest konteineritest
renet proxy up / down       # Käivita/peata Traefik
renet proxy logs            # Vaata puhverserveri logisid
```

Marsruudid avastatakse automaatselt konteineri siltidest. Vaadake [Võrgundus](/en/docs/networking), kuidas konfigureerida Traefiku silte.

### Süsteemi olek

```bash
renet ps                    # Üldine süsteemi olek
renet list all              # Kõik: süsteem, konteinerid, repositooriumid
renet list containers       # Kõik konteinerid kõigil Dockeri deemonitel
renet list repositories     # Repositooriumi olek ja ketta kasutus
renet list system           # Protsessor, mälu, ketas, võrk
renet ips --network-id {id} # IP-eraldised võrgu jaoks
```

### Deemoni haldamine

Igal repositooriumil on oma Dockeri deemon. Saate neid eraldi hallata:

```bash
renet daemon status --network-id {id}    # Dockeri deemoni tervis
renet daemon start  --network-id {id}    # Käivita deemon
renet daemon stop   --network-id {id}    # Peata deemon
renet daemon logs   --network-id {id}    # Deemoni logid
```

### Varundamine ja taastamine

Lükake varukoopiad teisele masinale või pilvesalvestusse:

```bash
# Lükka kaugmasinale (SSH + rsync)
renet backup push --name {uuid} --network-id {id} --target machine \
  --dest-host {host} --dest-user {user} --dest-path /mnt/rediacc --dest {uuid}.backup

# Lükka pilvesalvestusse (rclone)
renet backup push --name {uuid} --network-id {id} --target storage \
  --dest {uuid}.backup --rclone-backend {backend} --rclone-bucket {bucket}

# Tõmba kaugelt
renet backup pull --name {uuid} --network-id {id} --source machine \
  --src-host {host} --src-user {user} --src-path /mnt/rediacc --src {uuid}.backup

# Loetle kaugvarukoopiad
renet backup list --source machine --src-host {host} --src-user {user} --src-path /mnt/rediacc
```

> Enamik kasutajaid peaks kasutama hoopis `rdc repo push/pull`. `rdc`-käsud käsitsevad mandaate ja masina lahendamist automaatselt.

### Kontrollpunktimine (CRIU)

Kontrollpunkt salvestab töötavate konteinerite oleku, et neid hiljem taastada:

```bash
renet checkpoint create    --network-id {id}   # Salvesta töötava konteineri olek
renet checkpoint restore   --network-id {id}   # Taasta kontrollpunktist
renet checkpoint validate  --network-id {id}   # Kontrolli kontrollpunkti terviklikkust
```

### Hooldus

```bash
renet prune --dry-run       # Eelvaade mahajäetud võrkudest ja IP-dest
renet prune                 # Puhasta mahajäetud ressursid
renet datastore status      # BTRFS-andmesalve tervis
renet datastore validate    # Failisüsteemi tervikluse kontroll
renet datastore expand      # Laienda andmesalve veebis
```

## Systemd-teenused

Iga repositoorium loob need systemd-üksused:

| Üksus | Eesmärk |
|------|---------|
| `rediacc-docker-{id}.service` | Isoleeritud Dockeri deemon |
| `rediacc-docker-{id}.socket` | Dockeri API pesa aktiveerimine |
| `rediacc-loopback-{id}.service` | Loopback-IP aliase seadistus |

Globaalsed teenused, mis on jagatud kõigile repositooriumitele:

| Üksus | Eesmärk |
|------|---------|
| `rediacc-router.service` | Marsruudi avastamine (port 7111) |
| `rediacc-autostart.service` | Käivitusaegne repositooriumi ühendamine |
| `rediacc-autostart-reconcile.service` | Perioodiline automaatkäivituse leppija (käivitatakse alljärgneva taimeri poolt) |
| `rediacc-autostart-reconcile.timer` | Käivitab `renet repository reconcile` ligikaudu iga 3 minuti järel, et taastada pärast käivitamist seiskunud automaatkäivitusega repositooriumeid |

## Tavalised tööprotsessid

### Juuruta uus teenus

1. Looge krüpteeritud repositoorium:
   ```bash
   renet repository create --name {uuid} --network-id {id} --size 2G --encrypted
   ```
2. Ühendage see ja lisage oma `docker-compose.yml`, `Rediaccfile` ja `.rediacc.json` failid.
3. Käivitage see:
   ```bash
   renet repository up --name {uuid} --network-id {id} --password-stdin
   ```

### Pääsege töötava konteineri juurde

```bash
sudo renet docker --network-id {id} -- exec -it {container} bash
```

### Leidke, milline Dockeri pesa konteinerit käitab

```bash
for sock in /run/rediacc/docker-*.sock; do
  result=$(DOCKER_HOST=unix://$sock docker ps --format '{{.Names}}' 2>/dev/null | grep {name})
  [ -n "$result" ] && echo "Found on: $sock"
done
```

### Taastage teenus pärast konfiguratsioonimuudatusi

```bash
sudo renet compose -- up -d
```

Käivitage see kataloogist, kus asub `docker-compose.yml`. Muudetud konteinerid luuakse automaatselt uuesti.

### Kontrollige kõiki konteinereid kõigil deemonitel

```bash
renet list containers
```

## Näpunäited

- Kasutage alati `sudo`-d `renet compose`, `renet repository` ja `renet docker` käskude jaoks, neil on vaja root-õigusi LUKS ja Dockeri toiminguteks
- `--`-eraldaja on nõutav enne argumentide edastamist `renet compose`-le ja `renet docker`-ile
- Käivitage compose kataloogist, mis sisaldab `docker-compose.yml`-i
- `.rediacc.json`-pesa omistused on stabiilsed, ärge muutke neid pärast juurutamist
- Kasutage `/run/rediacc/docker-{id}.sock`-teid (systemd võib muuta pärand `/var/run/`-teid)
- Käivitage aeg-ajalt `renet prune --dry-run`, et leida mahajäetud ressursse
- BTRFS-hetktõmmised (`renet backup`) on kiired ja odavad, kasutage neid enne riskantseid muudatusi
- Repositooriumid on LUKS-krüpteeritud, parooli kaotamine tähendab andmete kaotamist
