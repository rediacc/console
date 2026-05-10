---
title: "Hub"
description: "Pakkuge autentitud, kasutajapõhiseid konteineriseeritud keskkondi kasutajapõhiste Docker daemonitega, mitmemallivalikuga, CRIU kontrollpunkti/taastamisega, auditilogidega ja andmejuure prügikorjega."
category: "Guides"
order: 14
language: et
---

# Hub

Hub pakub kasutajapõhiseid konteineriseeritud keskkondi OAuth-autentimise taga. Kasutajad külastavad ühte URL-i, autendivad ennast mis tahes OAuth2-teenuse pakkujaga ja suunatakse läbipaistvalt oma isiklikku konteinerisse. Konteinerid luuakse nõudmisel, igal kasutajal on oma isoleeritud Docker daemon ja jõude seansid CRIU-kontrollpunkituvad koheseks jätkamiseks.

Kõik on konfigureeritud `docker-compose.yml` siltide kaudu. Hub ise töötab hostis systemd-teenusena, mille materaliseerib `renet hub install` käsk teie hoidla compose-failist. Hoidlad defineerivad käitumise; Hub haldab autentimist, marsruutimist, elutsüklit ja kasutajapõhist isolatsiooni.

## Kuidas see töötab

1. Kasutaja külastab `code.example.com` (või `term.`, `desktop.` või muud konfigureeritud prefiksit).
2. Hub kontrollib seansiküpsist. Kui seda pole, suunatakse kasutaja konfigureeritud OAuth2-teenuse pakkujale (Nextcloud, Keycloak, GitHub jne).
3. Pärast autentimist tuvastab Hub kasutaja ja otsib tema konteinerit.
4. Kui konteinerit pole, valmistab Hub ette pühendatud Docker daemoni selle kasutaja jaoks hostis, seejärel loob tema konteinerit.
5. Päring suunatakse pöördproksi kaudu kasutaja konteinerisse loopback-võrgu kaudu.
6. Jõude konteinerid CRIU-kontrollpunkituvad; kasutajapõhine daemon peatatakse mälu vabastamiseks. Järgmisel sisselogimisel käivitub daemon uuesti ja CRIU taastab konteineri oleku sekunditega.

## Kiirstart

Lisage Hub teenusena oma hoidla `docker-compose.yml`-i. Teenus on märgitud `install_as=systemd`, nii et see töötab hostteeenusena, mitte Docker konteinerina (vajalik kasutajapõhise daemoni haldamiseks, mis kasutab systemd-i).

```yaml
services:
  hub:
    env_file:
      - ./hub/.env
    command:
      - hub
      - start
      - --docker-socket=${DOCKER_SOCKET}
      - --network-id=${REDIACC_NETWORK_ID}
      - --port=7112
      - --base-domain=${HUB_DOMAIN:-example.com}
      - --workspace-dir=${REDIACC_WORKING_DIR}/devbox/workspaces
      - --idle-timeout=30m
      - --checkpoint
    labels:
      - "rediacc.install_as=systemd"

      # Marsruudi kaardistamine: alamdomeeni prefiks -> port kasutaja konteinerites
      - "rediacc.hub.route.code=8080"
      - "rediacc.hub.route.term=7681"
      - "rediacc.hub.route.desktop=6080"

      # Konteineri mall
      - "rediacc.hub.image=ghcr.io/your-org/devcontainer:latest"
      - "rediacc.hub.command=start-desktop.sh & ttyd --writable --port 7681 bash & exec openvscode-server --host __SERVICE_IP__ --port 8080"
      - "rediacc.hub.user=vscode"
      - "rediacc.hub.docker=per-user"

      # Traefik marsruudid (failiteenuse pakkuja; rediacc-router loeb neid silte samuti)
      - "traefik.http.routers.hub-code.rule=Host(`code.${HUB_DOMAIN:-example.com}`)"
      - "traefik.http.routers.hub-code.entrypoints=websecure"
      - "traefik.http.routers.hub-code.tls.certresolver=letsencrypt"
      - "traefik.http.services.hub-code.loadbalancer.server.port=7112"
      - "traefik.http.routers.hub-term.rule=Host(`term.${HUB_DOMAIN:-example.com}`)"
      - "traefik.http.routers.hub-term.entrypoints=websecure"
      - "traefik.http.routers.hub-term.tls.certresolver=letsencrypt"
      - "traefik.http.services.hub-term.loadbalancer.server.port=7112"
      - "traefik.http.routers.hub-desktop.rule=Host(`desktop.${HUB_DOMAIN:-example.com}`)"
      - "traefik.http.routers.hub-desktop.entrypoints=websecure"
      - "traefik.http.routers.hub-desktop.tls.certresolver=letsencrypt"
      - "traefik.http.services.hub-desktop.loadbalancer.server.port=7112"
```

Looge `hub/.env` oma OAuth2-teenuse pakkuja mandaatidega:

```bash
HUB_DOMAIN=example.com
HUB_OAUTH_CLIENT_ID=your-client-id
HUB_OAUTH_CLIENT_SECRET=your-client-secret
HUB_OAUTH_AUTHORIZE_URL=https://auth.example.com/authorize
HUB_OAUTH_TOKEN_URL=https://auth.example.com/token
HUB_OAUTH_USERINFO_URL=https://auth.example.com/userinfo
HUB_OAUTH_USERINFO_PATH=preferred_username
HUB_SESSION_SECRET=64-character-hex-string
```

Installige hosti systemd-üksus (ühekordne, nõuab juurõigusi):

```bash
sudo renet hub install /path/to/docker-compose.yml
```

See loeb `install_as=systemd` teenuseid ja kirjutab:

- `/etc/systemd/system/rediacc-hub.service` (üksus)
- `/etc/rediacc/hub/hub.labels.yaml` (mallsildid)
- `/opt/rediacc/proxy/traefik/dynamic/rediacc-hub.yaml` (Traefik failiteenuse pakkuja marsruudid)

Seejärel `systemctl daemon-reload && systemctl enable --now rediacc-hub`. Eemaldamiseks: `sudo renet hub uninstall /path/to/docker-compose.yml`.

## Installikäsu viide

| Käsk | Eesmärk |
|---------|---------|
| `sudo renet hub install <compose-file>` | Tõlgi `install_as=systemd` teenused compose-failist hosti artefaktideks ja käivita üksus. |
| `sudo renet hub uninstall <compose-file>` | Peata, keela ja eemalda kõik teenuste artefaktid. Andmejuured `<workspace>/<user>-docker/` all säilitatakse. |
| `sudo renet hub gc <workspace-dir>` | Kärbi mahajäetud kasutajapõhiseid andmejuuri (vaikimisi: vanemad kui 30 päeva ilma aktiivse daemonita). Lipud: `--max-age=30d`, `--dry-run`. |
| `renet hub status` | JSON-olek kõigist konteineritest töötava Hubi API kaudu. |
| `renet hub stop <username>` | Peata konkreetse kasutaja konteiner. |

## Konfiguratsioon

Kogu Hubi konfiguratsioon asub compose-siltides Hubi teenusel. Saladused (OAuth client_secret, session_secret) lähevad `hub/.env`-i, mitte siltidesse.

### Marsruudi kaardistamine

Kaardistage alamdomeeni prefiksid portidele kasutaja konteinerites. Hub loeb neid silte, et teada, kuhu iga päringut edastada.

| Silt | Kirjeldus | Näide |
|-------|-------------|---------|
| `rediacc.hub.route.{prefix}` | Kaardistab `{prefix}.{domain}` sellele portile kasutaja konteineris | `rediacc.hub.route.code=8080` |

```yaml
labels:
  - "rediacc.hub.route.code=8080"      # code.example.com -> :8080
  - "rediacc.hub.route.term=7681"      # term.example.com -> :7681
  - "rediacc.hub.route.desktop=6080"   # desktop.example.com -> :6080
  - "rediacc.hub.route.jupyter=8888"   # jupyter.example.com -> :8888
```

Iga marsruut vajab ka vastavat Traefik ruuterit, mis osutab Hubi pordile (7112). Hub haldab kasutajapõhist marsruutimist sisemiselt hosti nime alusel.

### Konteineri mall

Defineerige, milline näevad välja kasutaja konteinerid. Hub loeb neid silte ja kasutab neid uue konteineri loomisel.

| Silt | Kirjeldus | Vaikeväärtus |
|-------|-------------|---------|
| `rediacc.hub.image` | Konteineri kujutis | `--container-image` lipu väärtus |
| `rediacc.hub.command` | Käivituskäsk (bash -c ühilduv) | puudub |
| `rediacc.hub.user` | Konteineri kasutaja (mittejuurkasutaja on soovitatav) | `vscode` |
| `rediacc.hub.workspace` | Tööruumi ühenduspunkt konteineris | `/workspace` |
| `rediacc.hub.shm_size` | Jagatud mälu maht baitides | `1073741824` (1 GB) |
| `rediacc.hub.docker` | `per-user` pühendatud dockerd ettevalmistamiseks kasutaja kohta (tungivalt soovitatav) | `""` |

`command` silt toetab `${SERVICE_IP}` ja `__SERVICE_IP__` laiendamist (viimane väldib compose eellaiendamist) konteineri määratud loopback-IP jaoks.

```yaml
labels:
  - "rediacc.hub.image=ghcr.io/my-org/dev-env:latest"
  - "rediacc.hub.command=exec jupyter lab --ip=__SERVICE_IP__ --port=8888 --no-browser"
  - "rediacc.hub.user=vscode"
  - "rediacc.hub.workspace=/workspace"
  - "rediacc.hub.docker=per-user"
```

### Kasutajapõhine Docker daemon

Kui `rediacc.hub.docker=per-user` on seadistatud, saab iga kasutaja pühendatud `dockerd` eksemplari hostis, mis ühendatakse `/var/run/docker.sock`-na nende konteinerisse. See annab:

- Täielikud `docker ps`, `docker run`, `docker build` kasutaja keskkonnas ilma privilegeeritud konteinerite või Docker-in-Docker-ita.
- Täielik isolatsioon kasutajate vahel (kasutaja A ei näe kasutaja B konteinereid ega kujutisi).
- Kasutajapõhine BTRFS andmejuur `<workspace-dir>/<user>-docker/.rediacc/docker/data` aadressil, mis säilib seanssidele üle, nii et vahemällu salvestatud kujutised elavad üle jõude-kontrollpunkti tsüklid.

Daemonid eraldatakse pühendatud võrgu-ID vahemikus, alustades 32768-st. `.networkid` markerfail iga kasutaja andmejuuris salvestab nende määratud ID, nii et naasevad kasutajad saavad sama daemoni.

### Ressursipiirangud

Seadistage kasutajapõhised ressursipiirangud, et takistada üksikutel kasutajatel kõigi hosti ressursside tarbimist. Piirangud kehtivad nii kasutaja konteinerile kui ka nende kasutajapõhisele dockerd eksemplarile (systemd `CPUQuota=` / `MemoryMax=` kaudu).

| Silt | Kirjeldus | Näide |
|-------|-------------|---------|
| `rediacc.hub.limits.cpu` | systemd CPUQuota väärtus | `200%` (2 tuuma) |
| `rediacc.hub.limits.memory` | systemd MemoryMax väärtus | `8G` |

```yaml
labels:
  - "rediacc.hub.limits.cpu=200%"
  - "rediacc.hub.limits.memory=8G"
```

Daemonid paigutatakse `rediacc.slice` systemd sektsiooni, nii et sektsioonitaseme piirangud päritakse.

### Mitme malli tugi

Pakkuge mitut keskkonna tüüpi. Kasutajad valivad malli sisselogimisel, külastades `https://code.example.com/_hub/login?template=python` (valik ringliikleb OAuth-oleku kaudu). Mallide vahetamine järgnevatel sisselogimistel ehitab konteineri uuesti.

Defineerige mallid `rediacc.hub.templates.<name>.<field>` siltidega. Tasased `rediacc.hub.image` / `rediacc.hub.command` / jne sildid defineerivad jätkuvalt kaudse "vaikimisi" malli kasutajatele, kes ühtegi ei vali.

```yaml
labels:
  # Vaikimisi mall, kui ?template=... on ära jäetud.
  - "rediacc.hub.template=fulldev"

  # Rikas VS Code + töölaud + terminali keskkond.
  - "rediacc.hub.templates.fulldev.image=ghcr.io/org/devcontainer:latest"
  - "rediacc.hub.templates.fulldev.command=start-desktop.sh & ttyd --writable --port 7681 bash --login & exec openvscode-server --host __SERVICE_IP__ --port 8080 --without-connection-token"
  - "rediacc.hub.templates.fulldev.user=vscode"

  # Kerge ainult VS Code.
  - "rediacc.hub.templates.lite.image=ghcr.io/org/devcontainer:lite"
  - "rediacc.hub.templates.lite.command=exec openvscode-server --host __SERVICE_IP__ --port 8080"
  - "rediacc.hub.templates.lite.user=vscode"

  # Pythoni-spetsiifiline keskkond.
  - "rediacc.hub.templates.python.image=python:3.12-slim"
  - "rediacc.hub.templates.python.command=pip install jupyterlab && exec jupyter lab --ip=__SERVICE_IP__ --port=8888"
  - "rediacc.hub.templates.python.user=1000:1000"
```

### Elutsükli konkse

Käivitage käske kasutaja konteineris elutsükli punktides. Konkse käitatakse konteineri kasutajana (mitte juurkasutajana).

| Silt | Millal käivitub | Näide |
|-------|-------------|---------|
| `rediacc.hub.hook.on_create` | Pärast konteineri loomist (esimene sisselogimine) | Hoidlate kloonimine, sõltuvuste installimine |
| `rediacc.hub.hook.checkpoint.pre_dump` | Enne jõude seansi CRIU-kontrollpunkti | Daemonite peatamine, mida ei saa kontrollpunkti teha (X-server, dbus) |
| `rediacc.hub.hook.checkpoint.post_restore` | Pärast CRIU taastamist | pre_dump-is peatatud daemonite taaskäivitamine |

```yaml
labels:
  - "rediacc.hub.hook.on_create=git clone https://github.com/org/repo /workspace/project"
  - "rediacc.hub.hook.checkpoint.pre_dump=start-desktop.sh stop"
  - "rediacc.hub.hook.checkpoint.post_restore=start-desktop.sh"
```

### Kontrollpunkt / Taastamine

Kui `--checkpoint` on seadistatud, CRIU-kontrollpunkituvad jõude kasutajakonteinerid ja nende kasutajapõhine daemon peatatakse mälu vabastamiseks. Järgmisel sisselogimisel daemon taaskäivitub ja CRIU taastab konteineri oleku kettalt, säilitades avatud failid, töötavad protsessid ja terminalisessioonid. Tüüpiline jätkamisaeg on mõni sekund sõltumata töökoormusest.

| Silt | Kirjeldus | Vaikeväärtus |
|-------|-------------|---------|
| `rediacc.hub.checkpoint` | Luba CRIU kontrollpunkt kasutaja konteinerite jaoks | `false` |

Edastage `--checkpoint` ja nullist erinev `--idle-timeout` (nt `30m`) Hubi käsus. Kontrollpunkti kataloogid asuvad `<workspace-dir>/<user>/.checkpoint/` all.

Kui CRIU ebaõnnestub kasutaja jaoks järjest 3 korda, keelatakse kontrollpunkt selle kasutaja jaoks ja varumeetmeks muutub peata-ja-loo-uuesti.

### Ajutine režiim

Vaikimisi on kasutajate tööruumid püsivad (elavad taaskäivitamise üle). Ajutine režiim annab igal sisselogimisel puhta keskkonna, mis on kasulik demode, koolituse või CI jaoks.

| Silt | Kirjeldus | Vaikeväärtus |
|-------|-------------|---------|
| `rediacc.hub.mode` | `persistent` või `ephemeral` | `persistent` |

Ajutises režiimis on tööruumil tmpfs (RAM-toega) ja konteiner eemaldatakse automaatselt peatamisel.

### Jõude aegumine

| Lipp | Kirjeldus | Vaikeväärtus |
|------|-------------|---------|
| `--idle-timeout=<dur>` | Peata/kontrollpunkti konteinerid, mis on sellest kauem jõude olnud | `0` (keelatud) |

`0` hoiab konteinerid igavesti töötamas. Praktiline väärtus on `30m`: jõude kasutajad vabastavad mälu poole tunni pärast ja naasevad kasutajad jätkavad sekunditega CRIU kaudu.

### Ligipääsu juhtimine

| Muutuja | Kirjeldus |
|----------|-------------|
| `HUB_ALLOWED_GROUPS` | Komaga eraldatud grupid, kellel on Hubi kasutamise luba (kui teie pakkuja paljastab grupi nõuded) |
| `HUB_ADMIN_USERS` | Komaga eraldatud administraatori kasutajanimed. Administraatorid näevad ja juhivad teiste kasutajate konteinereid armatuurlaual. |

## Auditilogi

Iga kasutaja algatatud konteineri/kujutise sündmus (loo, käivita, peata, hävita, tapa, tõmba, lükka) kasutajapõhises daemonis lisatakse reaga eraldatud JSON-kirjena `/var/log/rediacc/hub/<user>.log`-i:

```json
{"ts":"2026-04-16T05:53:12Z","user":"alice","net_id":32768,"type":"container","action":"start","resource":"abc123...","attrs":{"image":"hello-world:latest","name":"happy_pike"}}
```

Kirjed elavad CRIU kontrollpunkti/taastamise üle (auditivoog relvastub taastamisel uuesti). Kasutage `logrotate`-i kettakasutuse piiramiseks; näidiskonfiguratsioon:

```
/var/log/rediacc/hub/*.log {
  daily
  rotate 30
  compress
  missingok
  notifempty
  copytruncate
}
```

## Armatuurlaud

Hub sisaldab iseteeninduslikku armatuurlauda aadressil `/_hub/dashboard`. See näitab:

- Kõiki töötavaid keskkondi koos nende olekuga
- Valitud malli
- Teenuste linke (ühe klõpsuga koodile, terminali, töölauale või muule marsruudile avamiseks)
- Jõude taimerid
- Kasutajapõhist kettakasutust, töötavate konteinerite arvu ja kujutiste arvu
- Administraatorid näevad kõiki konteinereid; tavalised kasutajad näevad ainult omi

Statistikat kogutakse iga 30 sekundi järel.

## Andmejuure prügikorje

Kasutajapõhised andmejuured kogunevad pikaajalistes hostides. Planeerige `renet hub gc` mahajäetute kärpimiseks. systemd taimer töötab hästi:

```ini
# /etc/systemd/system/rediacc-hub-gc.service
[Unit]
Description=Rediacc Hub data-root GC

[Service]
Type=oneshot
ExecStart=/usr/lib/rediacc/renet/current/renet hub gc /mnt/rediacc/mounts/<repo-guid>/devbox/workspaces --max-age=30d
```

```ini
# /etc/systemd/system/rediacc-hub-gc.timer
[Unit]
Description=Daily Rediacc Hub GC

[Timer]
OnCalendar=daily
RandomizedDelaySec=1h
Persistent=true

[Install]
WantedBy=timers.target
```

`--dry-run` logib kandidaadid ilma kustutamata. Andmejuur on kõlblik, kui selle `.networkid` marker on vanem kui `--max-age` JA salvestatud daemon ei ole enam hostis konfigureeritud.

## OAuth seadistamine

Hub töötab mis tahes standardse OAuth2-teenuse pakkujaga. Konfiguratsioon toimub keskkonna muutujate kaudu.

| Muutuja | Kirjeldus | Nõutav |
|----------|-------------|----------|
| `HUB_OAUTH_CLIENT_ID` | OAuth2 kliendi ID | Jah |
| `HUB_OAUTH_CLIENT_SECRET` | OAuth2 kliendisaladus | Jah |
| `HUB_OAUTH_AUTHORIZE_URL` | Pakkuja autoriseerimise lõpp-punkt | Jah |
| `HUB_OAUTH_TOKEN_URL` | Pakkuja loa lõpp-punkt | Jah |
| `HUB_OAUTH_USERINFO_URL` | Pakkuja kasutajateabe lõpp-punkt | Jah |
| `HUB_OAUTH_USERINFO_PATH` | Punktidega eraldatud tee kasutajanime eraldamiseks JSON-vastusest | Jah |
| `HUB_OAUTH_REDIRECT_URI` | Kirjuta tagasihelistamise URL üle (arvutatakse automaatselt, kui tühi) | Ei |
| `HUB_OAUTH_SCOPES` | Lisaulatused (tühikuga eraldatud) | Ei |
| `HUB_SESSION_SECRET` | 32+ baiti pikk hex-string küpsise allkirjastamiseks | Soovitatav |

### Teenuse pakkujate näited

**Nextcloud:**
```bash
HUB_OAUTH_AUTHORIZE_URL=https://cloud.example.com/apps/oauth2/authorize
HUB_OAUTH_TOKEN_URL=https://cloud.example.com/apps/oauth2/api/v1/token
HUB_OAUTH_USERINFO_URL=https://cloud.example.com/ocs/v2.php/cloud/user?format=json
HUB_OAUTH_USERINFO_PATH=ocs.data.id
```

**Keycloak:**
```bash
HUB_OAUTH_AUTHORIZE_URL=https://auth.example.com/realms/master/protocol/openid-connect/auth
HUB_OAUTH_TOKEN_URL=https://auth.example.com/realms/master/protocol/openid-connect/token
HUB_OAUTH_USERINFO_URL=https://auth.example.com/realms/master/protocol/openid-connect/userinfo
HUB_OAUTH_USERINFO_PATH=preferred_username
```

**GitHub:**
```bash
HUB_OAUTH_AUTHORIZE_URL=https://github.com/login/oauth/authorize
HUB_OAUTH_TOKEN_URL=https://github.com/login/oauth/access_token
HUB_OAUTH_USERINFO_URL=https://api.github.com/user
HUB_OAUTH_USERINFO_PATH=login
HUB_OAUTH_SCOPES=read:user
```

`HUB_OAUTH_USERINFO_PATH` on punktidega eraldatud tee JSON-vastusesse. Pesastatud objektide jaoks nagu Nextcloudi `{"ocs":{"data":{"id":"alice"}}}` kasutage `ocs.data.id`.

## Näited

### Arenduskeskkond (VS Code + Terminal + Töölaud)

Täielik arenduskeskkond koos OpenVSCode Serveriga, veebiterminali (ttyd) ja noVNC töölauaga. Kasutajad saavad oma Docker daemoni sees.

```yaml
services:
  hub:
    env_file:
      - ./hub/.env
    command:
      - hub
      - start
      - --docker-socket=${DOCKER_SOCKET}
      - --network-id=${REDIACC_NETWORK_ID}
      - --port=7112
      - --base-domain=${HUB_DOMAIN}
      - --workspace-dir=${REDIACC_WORKING_DIR}/devbox/workspaces
      - --idle-timeout=30m
      - --checkpoint
    labels:
      - "rediacc.install_as=systemd"
      - "rediacc.hub.route.code=8080"
      - "rediacc.hub.route.term=7681"
      - "rediacc.hub.route.desktop=6080"
      - "rediacc.hub.image=ghcr.io/your-org/devcontainer:latest"
      - "rediacc.hub.command=start-desktop.sh & ttyd --writable --port 7681 bash --login & exec openvscode-server --host __SERVICE_IP__ --port 8080 --without-connection-token"
      - "rediacc.hub.user=vscode"
      - "rediacc.hub.docker=per-user"
      - "rediacc.hub.limits.cpu=200%"
      - "rediacc.hub.limits.memory=8G"
      - "rediacc.hub.checkpoint=true"
      - "rediacc.hub.hook.checkpoint.pre_dump=start-desktop.sh stop"
      - "rediacc.hub.hook.checkpoint.post_restore=start-desktop.sh"
      # ... Traefik ruuterid iga prefiksi jaoks ...
```

### Jupyter Notebook keskkond

Andmeteaduse keskkond JupyterLabiga:

```yaml
labels:
  - "rediacc.install_as=systemd"
  - "rediacc.hub.route.notebook=8888"
  - "rediacc.hub.image=jupyter/datascience-notebook:latest"
  - "rediacc.hub.command=exec jupyter lab --ip=__SERVICE_IP__ --port=8888 --no-browser --NotebookApp.token='' --NotebookApp.password=''"
  - "rediacc.hub.user=1000:100"
  - "rediacc.hub.workspace=/home/jovyan/work"
  - "rediacc.hub.limits.cpu=400%"
  - "rediacc.hub.limits.memory=16G"
```

### Lihtne veebirakendus (ajutine)

Üheteenuse keskkond, mis käivitub igal sisselogimisel puhtalt:

```yaml
labels:
  - "rediacc.install_as=systemd"
  - "rediacc.hub.route.app=3000"
  - "rediacc.hub.image=node:22-alpine"
  - "rediacc.hub.command=cd /workspace && npm install && exec npm run dev -- --host __SERVICE_IP__"
  - "rediacc.hub.user=1000:1000"
  - "rediacc.hub.mode=ephemeral"
```

## Seotud juhendid

- [**Teenused**](/et/docs/services) -- Rediaccfile elutsükkel, compose mustrid
- [**Võrgustik**](/et/docs/networking) -- Docker sildid, Traefik marsruutimine, TLS sertifikaadid
- [**Varundamine ja taastamine**](/et/docs/backup-restore) -- Tööruumi püsivus ja taastamine
- [**Arenduskeskkonnad**](/et/docs/development-environments) -- Tootmise kloonimine arenduskeskkondade jaoks
