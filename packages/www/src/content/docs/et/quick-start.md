---
title: Kiirjuhend
description: Konteineerpõhise teenuse käivitamine oma serveris minutitega.
category: Guides
order: -1
language: et
sourceHash: "b2745d4f0d99d7a4"
sourceCommit: "a56b03aa5da8df74255a6bc9bc9463665c3499b6"
---

# Kiirjuhend

Juuruta Rediacc oma serveris. Krüpteeritud, isoleeritud konteinerikeskkond, ilma pilvekontoide ega SaaS-sõltuvusteta. Sinu riistvara, sinu kontroll.

---

## Sissejuhatus

### Põhimõisted

Hoidla on üks krüpteeritud fail kettal. Liiguta seda, varunda see, tee sellest fork. See on lihtsalt fail. Ühendatuna muutub see kaustaks, mille sees on pühendatud Dockeri daemon ja sinu rakenduse andmed.

Mõtle hoidlast kui USB-kettast: ühenda see mis tahes masina külge ja rakendused ning andmed ühenduvad, valmis töötamiseks. Liiguta seda masinate või pilveteenuse pakkujate vahel ilma midagi uuesti ehitamata.

**Kaks tööriista, kaks rolli:**

- **rdc** = CLI sinu sülearvutis (TypeScript, paigaldatud globaalselt)
- **renet** = orkestreerimisteenus serveris (Go binaar, haldab daemoneid/võrke/eraldumist)
- RDC provisioonib renet'i automaatselt `config machine setup` käigus. Serveris käsitsi seadistamist pole vaja.

> [Arhitektuur](/et/docs/architecture) selgitab turvamudelit. [rdc vs renet](/et/docs/rdc-vs-renet) selgitab, millist tööriista millal kasutada.

### 1. Paigalda CLI

```bash
curl -fsSL https://www.rediacc.com/install.sh | bash
rdc doctor     # Kontrolli: Node, SSH-võti, renet, Docker
```

> Windows, Alpine, Arch: vt [Paigaldamine](/et/docs/installation). Täielikud süsteeminõuded: [Nõuded](/et/docs/requirements).

### 2. SSH-võtme seadistamine

rdc ühendub üle SSH. Server peab usaldama sinu avalikku võtit enne, kui rdc saab selleni jõuda.

```bash
# Genereeri võti (jäta vahele, kui sul on juba üks)
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519

# Kopeeri avalik võti serverisse (küsib parooli)
ssh-copy-id -i ~/.ssh/id_ed25519 user@your-server-ip

# Ütle rdc-le, millist võtit kasutada
rdc config ssh set --key ~/.ssh/id_ed25519
```

Iga rdc käsk autentib nüüd selle võtmega. Paroole pole.

### 3. Lisa oma server

```bash
rdc machine add my-server --ip 192.168.1.100 --user admin
rdc machine setup my-server  # Provisioonib renet + loob andmehoidla
```

**Mis juhtub:** SSH-hostivõti skannitakse, renet-binaar laaditakse üles, serveris initsialiseeritakse krüpteeritud andmehoidla. Valmis hoidlateks.

> Andmehoidla suuruse seadistamine, Ceph RBD, pilvepakkujad: [Masina seadistamine](/et/docs/setup). SSH vead: [Tõrkeotsing](/et/docs/troubleshooting).

### 4. Konfiguratsioonifail

```bash
rdc config show                            # Inimloetav kokkuvõte
cat ~/.config/rediacc/rediacc.json         # Toores JSON: masinad, hoidlad, mäluhoidlad, SSH-võti
```

**Üks fail = üks keskkond.** Kopeeri see teise sülearvutisse ja oled valmis.

---

## Töötamine hoidlaga

### 1. Loo hoidla

```bash
rdc repo create my-app -m my-server --size 2G  # Loo 2 GB krüpteeritud hoidla
```

Loob krüpteeritud mahu, ühendab selle ja käivitab selle Dockeri daemoni. Hoidla registreeritakse sinu konfiguratsioonis ja on kasutamiseks valmis.

> Suuruse muutmine, kustutamine, valideerimine: [Hoidlad](/et/docs/repositories).

### 2. Rakenda mall

```bash
rdc repo admin template list                                        # Kuva sisseehitatud mallid
rdc repo admin template apply my-app --template app-postgres  # Juuruta docker-compose.yml + Rediaccfile
```

Mallid pakuvad `docker-compose.yml`, `Rediaccfile` ja toetavad faile. Ilma mallit (või oma compose-faili) pole midagi käivitada. Kasuta sisseehitatud malli oma esimese hoidla jaoks. See on kiireim viis kogu töövoo nägemiseks otsast lõpuni.

### 3. Käivita hoidla

```bash
rdc repo up my-app  # Käivita Rediaccfile up()
rdc repo list -m my-server                           # Vaata kõiki hoidlaid masinal
rdc repo status my-app  # Ühenduse olek, Docker, suurus, krüpteerimine
```

`repo up` ühendab automaatselt vajadusel. Lippe pole vaja.

### 4. VS Code

```bash
rdc vscode connect my-app              # Avab VS Code SSH, maandub hoidla liivakastis
```

Redigeerid faile *krüpteeritud mahu sees*. `docker ps` näitab ainult selle hoidla konteinereid. Salvesta, compose up, tee uuesti.

### 5. `rdc repo up` vs `renet dev up`

| | `rdc repo up` | `renet dev up` |
|---|---|---|
| **Kus sa seda käivitad** | Sinu sülearvutis (CLI) | VS Code liivakasti sees |
| **Mida see teeb** | SSH → automaatühendus → käivita Rediaccfile `up()` | Käivitab Rediaccfile `up()` otse |
| **Kasutusjuhtum** | CI/CD, automatiseerimine, kaugoperatsioonid | Arendaja sisesilmus |
| **Eraldumine** | Orkestreerib väljastpoolt | On juba liivakastis |

**Demo voog:** `rdc repo admin template apply` → `rdc vscode connect my-app` → muuda `docker-compose.yml` → `renet dev up` → vaata töötavat rakendust → korda.

> Rediaccfile struktuur: [Teenused](/et/docs/services). Millist tööriista millal kasutada: [rdc vs renet](/et/docs/rdc-vs-renet).

### 6. Eraldumismudel

- **Universaalne kasutaja** (`rediacc`): sama UID kõigis masinates. Liiguta hoidla teise serverisse ja failide omand lihtsalt toimib. Pole `chown` peavalu.
- **Hoidlapõhine Dockeri daemon**: igal hoidlal on oma isoleeritud Dockeri daemon. `docker ps` näitab ainult SELLE hoidla konteinereid.
- **Landlock + OverlayFS liivakast**: VS Code kest on failisüsteemiga piiratud. Sa ei saa lugeda teisi hoidlaid. Kirjutused `$HOME`-i on hoidlapõhised kattekihid.

> Kuidas eraldumine toimib: [Arhitektuur](/et/docs/architecture). Rediaccfile elutsükkel: [Teenused](/et/docs/services).

### 7. Terminal, sünkroonimine ja tunnel

**Terminal:**
```bash
rdc term connect my-app                            # SSH hoidla liivakasti
rdc term connect my-app -c "curl localhost:3000"   # Käivita käsk ja välju
rdc term connect my-server                                   # SSH masinale (ilma liivakastita)
```

**Failisünkroonimine (rsync üle SSH):**
```bash
rdc repo sync upload my-app --local ./src                                   # Lükka kataloog üles
rdc repo sync upload my-app --local ./config.yml --remote conf              # Lükka üks fail üles
rdc repo sync download my-app --local ./backup                              # Tõmba kataloog alla
rdc repo sync download my-app --remote-file conf/config.yml --local ./dl    # Tõmba üks fail alla
rdc repo sync download my-app --local ./backup --dry-run                    # Esmalt eelvaade
```

**Tunnel (SSH pordiedastus konteinerile):**
```bash
rdc repo tunnel my-app -c app  # Tuvasta automaatselt port rakenduse konteinerile
rdc repo tunnel my-app -c db --port 5432  # Tunnel Postgres'ile
rdc repo tunnel my-app -c db --port 5432 --local 15432  # Kohandatud kohalik port
```

Käivita tunnel → ava brauseris `localhost:3000` → elav rakendus kaugserverist.

> Sünkroonimine, terminal, VS Code üksikasjad: [Tööriistad](/et/docs/tools).

---

## Fork ja varundamine

### 1. Grand ja fork hoidlad

```bash
rdc repo fork my-app --tag experiment --up  # Kohene CoW kloon + käivita
rdc repo list -m my-server                                  # Näitab: my-app (grand) + my-app:experiment (fork)
rdc repo delete my-app:experiment  # Kustuta fork, grand puutumata
```

**Kohene, nullkopeerimisega kloon.** CoW (copy-on-write ehk kirjutamisel kopeerimine). Mikrosekundid, andmeid ei kopeerita. Plokid on jagatud kuni üks pool kirjutab.

**Kasutusjuhtumid:**
- **AI / ML:** Forgi tootmisandmestik, tee katse, loobu või edenda
- **DevOps:** Fork → testi migreerimist → kustuta, kui halb, edenda, kui hea
- **Varundamine:** Fork = kohene hetktõmmis, lükka see väljapoole

> Forki elutsükkel, masinate-vahelised forkid: [Hoidlad](/et/docs/repositories).

### 2. Lükka teisele masinale

```bash
# Lükka hoidla teisele masinale
rdc repo push my-app --to backup-server

# Lükka ja juuruta automaatselt sihtkohas
rdc backup restore my-app --as my-app -m backup-server --up

# Lükka CRIU kontrollpunktiga (elav migreerimine, säilitab mäluoleku)
rdc repo push my-app --to new-server --checkpoint

# Lükka uuele masinale (automaatne provisioneerimine pilvepakkuja kaudu)
rdc repo push my-app --to new-server --provision linode
```

### 3. Varunda tükksalvestusse

```bash
# Tee kindla ajahetke tõmmis
rdc backup snapshot my-app

# Vaata, millised tõmmised on olemas
rdc backup manifests my-app

# Kontrolli salvestatud baite sinu kvoodi suhtes
rdc backup usage
```

Tõmmised laaditakse üles tükksalvestusse, mis vajab konto-serverit ja litsentseeritud repositooriumi. Salvestatakse ainult muutunud andmed, seega maksab sama repositooriumi teine tõmmis ainult erinevuse, mitte kogu tõmmise hinda.

Repositooriumi lükkamine pilvemällu käsuga `--to <storage>` on kaotatud ja lükatakse nüüd tagasi. Enne seda muudatust kirjutatud arhiivi lugemiseks toimib `rdc storage browse` endiselt ja vajab `rclone`-i sinu PATH-is.

### 4. Tõmba kaugelt

```bash
# Tõmba hoidla pilvemassinalt oma kohalikku serverisse
rdc repo pull my-app@my-local-server --from cloud-server

# Tõmba ja käivita kohe
rdc repo pull my-app@my-local-server --from cloud-server --up

# Selle asemel taasta kindel ajahetk tükksalvestusest
rdc backup restore my-app --at <snapshot> --as my-app --up
```

**Miks tõmmata?** Sinu kohalik masin on NAT taga. Pilv ei saa sulle lükata. Aga sina saad pilve jõuda. Tõmbamine toob hoidla koju.

**Täielik tsükkel:** Loo arenduses → lükka pilve → tõmba tootmises → `--up`. Üks hoidla, mis tahes masin, mis tahes pilv.

> Ajakava seadistamine, automatiseeritud varukoopiad, taastamine: [Varundus ja taastamine](/et/docs/backup-restore).

---

## Proksi ja SSL

### 1. Infrastruktuuri konfiguratsioon

```bash
rdc machine infra set my-server  # Konfigureeri: põhidomeen, avalikud IP-d, pordivahemikud
rdc machine infra show my-server  # Vaata konfiguratsiooni
rdc machine infra push my-server  # Lükka proksi konfiguratsioon kaugele
```

**Kuidas marsruutimine toimib:**
- Traefik avastab konteinerid automaatselt `rediacc.service_name` ja `rediacc.service_port` siltide kaudu
- Marsruudid: `{service}-{networkId}.{baseDomain}` → konteineri IP:port
- SSL: Let's Encrypt Cloudflare DNS-01 proovivõtte kaudu (automaatne uuendamine, metamärgiserdid)

### 2. Proksi mall

```bash
rdc repo admin template apply infra --template proxy  # Juuruta proksi hoidlasse
rdc repo up infra  # Käivita Traefik
```

Traefik suunab nüüd välist liiklust kõigile selle masina hoidlatele. Iga konteiner saab HTTPS lõpp-punkti automaatselt.

```bash
# Mine https://my-app.example.com → suunatakse konteinerile
# TCP/UDP edastus andmebaaside jaoks:
#   rediacc.tcp_ports=3306,5432 → automaatselt eraldatud välispordid
```

> Marsruutimisreeglid, DNS, TLS konfigureerimine: [Võrgundus](/et/docs/networking).

---

## Järgmised sammud

- **[Migreerimise juhend](/et/docs/migration)** - Tõsta olemasolevad projektid Rediacc hoidlatesse
- **[Monitooring](/et/docs/monitoring)** - Masina tervis, konteinerid, teenused, diagnostika
- **[CLI viide](/et/docs/cli-application)** - Täielik käskude viide
- **[Petuleht](/et/docs/rdc-cheat-sheet)** - Kiire käskude otsing
- **[Tõrkeotsing](/et/docs/troubleshooting)** - Levinud probleemide lahendused
- **[Rediacc reeglid](/et/docs/rules-of-rediacc)** - Rediaccfile parimad tavad ja juurutamise kontrollnimekiri
