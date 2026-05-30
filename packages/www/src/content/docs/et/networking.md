---
title: "Võrgundus"
description: "Avalda teenuseid pöördproksi, Dockeri siltide, TLS-sertifikaatide, DNS-i ja TCP/UDP pordiedastuse abil."
category: "Guides"
order: 6
language: et
sourceHash: "d60a43cd573517a1"
sourceCommit: "4e60a12e0664cdee5ad9079a7b75e2d05980d0f5"
---

# Võrgundus

Sellel lehel selgitatakse, kuidas isoleeritud Dockeri daemonites töötavad teenused muutuvad internetist kättesaadavaks. Käsitletakse pöördproksisüsteemi, Dockeri silte marsruutimiseks, TLS-sertifikaate, DNS-i ja TCP/UDP pordiedastust.

Kuidas teenused saavad oma loopback-IP-d ja `.rediacc.json` pesasüsteemi kohta vt [Teenused](/et/docs/services#service-networking-rediaccjson).

## Võrgueraldumine

Iga hoidla on tuumatasandil automaatselt eraldatud võrgukonksude abil. See nõuab Linuxi tuuma versiooni 6.1 või uuemat. Konfiguratsiooni ei ole vaja.

- **Automaatne bind-ümberkirjutus**: Teenused saavad siduda `0.0.0.0` või `127.0.0.1` nagu tavaliselt. Tuum kirjutab aadressi läbipaistvalt ümber teenusele määratud loopback-IP-ks. `${SERVICE_IP}` aadressi ei pea eksplitsiitselt siduma.
- **Ristühenduste blokeerimine**: Kui teenus proovib ühenduda loopback-IP-ga, mis asub väljaspool hoidla `/26` alamvõrku, blokeerib tuum selle. Hoidla A protsess ei saa jõuda hoidla B teenusteni.
- **Rakendusi ei pea muutma**: Teenused kasutavad sidumiseks `0.0.0.0` või `localhost` ning tuum tagab, et nad kuulavad ainult õigel loopback-IP-l. Eraldumine on täielikult läbipaistev.

## Kuidas see toimib

Rediacc kasutab välise liikluse konteineriteni suunamiseks kahest komponendist koosnevat proksisüsteemi:

1. **Marsruutimisserver**, systemd-teenus, mis avastab töötavaid konteinereid kõigis hoidla Dockeri daemonites. See kontrollib konteineri silte ja genereerib marsruutimiskonfiguratsiooni, mida pakutakse YAML-lõpp-punktina.
2. **Traefik**, pöördproksi, mis küsib marsruutimisserverist iga 5 sekundi tagant ja rakendab avastatud marsruudid. See tegeleb HTTP/HTTPS-marsruutimise, TLS-lõpetamise ja TCP/UDP-edastusega.

Voog näeb välja nii:

```
Internet → Traefik (pordid 80/443/TCP/UDP)
               ↓ küsib iga 5s
           Marsruutimisserver (avastab konteinereid)
               ↓ kontrollib silte
           Dockeri daemonid (/var/run/rediacc/docker-*.sock)
               ↓
           Konteinerid (seotud 127.x.x.x loopback-IP-dega)
```

Kui lisad konteineri jaoks õiged sildid ja käivitad selle `renet compose`'iga, muutub see automaatselt marsruuditavaks, ilma käsitsi puhvrikonfiguratsiooni vajamata.

> Marsruutimisserveri binaarne fail hoitakse sünkroonis CLI versiooniga. Kui CLI uuendab masinal renet-binaari, taaskäivitatakse marsruutimisserver automaatselt (~1-2 sekundit). See ei põhjusta seisakuid -- Traefik jätkab liikluse teenindamist viimase teadaoleva konfiguratsiooniga taaskäivitamise ajal ja võtab uue konfiguratsiooni kasutusele järgmisel küsimisel. Olemasolevaid kliendiühendusi ei mõjutata. Rakenduse konteinereid ei puudutata.

## Dockeri sildid

Marsruutimist juhivad Dockeri konteineri sildid. Neid on kahte taset:

### Tase 1: `rediacc.*` sildid (automaatsed)

Need sildid **lisatakse automaatselt** `renet compose` poolt teenuste käivitamisel. Sa ei pea neid käsitsi lisama.

| Silt | Kirjeldus | Näide |
|-------|-------------|---------|
| `rediacc.service_name` | Teenuse identiteet | `myapp` |
| `rediacc.service_ip` | Määratud loopback-IP | `127.0.11.2` |
| `rediacc.network_id` | Hoidla daemoni ID | `2816` |
| `rediacc.repo_name` | Hoidla nimi | `marketing` |
| `rediacc.tcp_ports` | TCP-pordid, mida teenus kuulab | `8080,8443` |
| `rediacc.udp_ports` | UDP-pordid, mida teenus kuulab | `53` |

Kui konteineril on ainult `rediacc.*` sildid (ilma `traefik.enable=true`), genereerib marsruutimisserver **automarsruudi** hoidla nime ja masina alamdomeeni kasutades:

```
{service}.{repoName}.{machineName}.{baseDomain}
```

Näiteks teenus nimega `myapp` hoidlas nimega `marketing` masinal `server-1` baasdomääniga `example.com` saab:

```
myapp.marketing.server-1.example.com
```

Forkide puhul kombineeritakse teenuse nimi reserveeritud sõnaga `fork` ja sildiga:

```
{service}-fork-{tag}.{repoName}.{machineName}.{baseDomain}
```

Näiteks `marketing` fork sildi `staging` all saab:

```
myapp-fork-staging.marketing.server-1.example.com
```

Iga forki URL asub vanemhoidla alamdomeeni all ja on kaetud selle olemasoleva metamärgisertifikaadiga, seega pole uut sertifikaati vaja. Eraldusmärk `-fork-` väldib kokkupõrkeid tootmishoidla päristeenuste nimedega. Kohandatud domeenidega teenuste puhul kasuta 2. taseme silte või silti `rediacc.domain`.

#### Kohandatud domeen `rediacc.domain` abil

Saad teenuse jaoks kohandatud domeeni seada, kasutades `docker-compose.yml` failis silti `rediacc.domain`. Toetatud on nii lühikesed nimed kui ka täielikud domeenid:

```yaml
labels:
  # Lühike nimi, lahendatakse cloud.example.com-ks masina baseDomain abil
  - "rediacc.domain=cloud"

  # Täielik domeen, kasutatakse nii nagu on
  - "rediacc.domain=cloud.example.com"
```

Väärtust ilma punktideta käsitletakse lühikese nimena ja masina `baseDomain` lisatakse automaatselt. Punktidega väärtust kasutatakse täieliku domeenina. See kehtib nii automarsruudi genereerimise kui ka CLI kuvamise kohta.

Kui `machineName` on seadistatud, saavad kohandatud domeeniteenused **kaks marsruuti**: ühe põhidomeenis (`cloud.example.com`) ja ühe masina alamdomeenis (`cloud.server-1.example.com`).

### Tase 2: `traefik.*` sildid (kasutaja määratud)

Lisa need sildid oma `docker-compose.yml` faili, kui soovid kohandatud domeenil marsruutimist, TLS-i või konkreetseid sisenemispunkte. `traefik.enable=true` seadmine ütleb marsruutimisserverile, et kasutada sinu kohandatud reegleid automarsruudi genereerimise asemel.

```yaml
labels:
  - "traefik.enable=true"
  - "traefik.http.routers.myapp.rule=Host(`app.example.com`)"
  - "traefik.http.routers.myapp.entrypoints=websecure,websecure-v6"
  - "traefik.http.routers.myapp.tls.certresolver=letsencrypt"
  - "traefik.http.services.myapp.loadbalancer.server.port=8080"
```

Need kasutavad standardset [Traefik v3 siltide süntaksit](https://doc.traefik.io/traefik/routing/providers/docker/).

> **Nõuanne:** Ainult sisekasutuseks mõeldud teenustel (andmebaasid, vahemälud, sõnumijärjekorrad) **ei** tohiks olla `traefik.enable=true`. Nad vajavad ainult `rediacc.*` silte, mis lisatakse automaatselt.

## HTTP/HTTPS teenuste avaldamine

### Eeltingimused

1. Infrastruktuur seadistatud masinal ([Masina seadistamine, infrastruktuuri konfigureerimine](/et/docs/setup#infrastructure-configuration)):

   ```bash
   # Ühised mandaadid (üks kord konfiguratsiooni kohta, kehtib kõigile masinatele)
   rdc config infra set -m server-1 \
     --cert-email admin@example.com \
     --cf-dns-token your-cloudflare-api-token

   # Masinapõhised seaded
   rdc config infra set -m server-1 \
     --public-ipv4 203.0.113.50 \
     --base-domain example.com

   rdc config infra push -m server-1
   ```

2. DNS-kirjed, mis suunavad sinu domeeni serveri avalikule IP-le (vt allpool [DNS-konfigureerimine](#dns-konfigureerimine)).

### Siltide lisamine

Lisa `traefik.*` sildid teenustele, mida soovid oma `docker-compose.yml` failis avaldada:

```yaml
services:
  myapp:
    image: myapp:latest
    environment:
      - LISTEN_ADDR=0.0.0.0:8080
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.myapp.rule=Host(`app.example.com`)"
      - "traefik.http.routers.myapp.entrypoints=websecure,websecure-v6"
      - "traefik.http.routers.myapp.tls.certresolver=letsencrypt"
      - "traefik.http.services.myapp.loadbalancer.server.port=8080"

  database:
    image: postgres:17
    # Traefik-silte pole, andmebaas on ainult sisekasutuseks
```

| Silt | Eesmärk |
|-------|---------|
| `traefik.enable=true` | Lubab selle konteineri jaoks kohandatud Traefiku marsruutimise |
| `traefik.http.routers.{name}.rule` | Marsruutimisreegel, tavaliselt `Host(\`domeen\`)` |
| `traefik.http.routers.{name}.entrypoints` | Milliseid porte kuulata: `websecure` (HTTPS IPv4), `websecure-v6` (HTTPS IPv6) |
| `traefik.http.routers.{name}.tls.certresolver` | Sertifikaadi lahendaja, kasuta `letsencrypt` automaatse Let's Encrypt'i jaoks |
| `traefik.http.services.{name}.loadbalancer.server.port` | Port, mida su rakendus konteineri sees kuulab |

Siltides olev `{name}` on suvaline identifikaator. See peab lihtsalt olema järjepidev seotud marsruuteri/teenuse/vahevara siltide vahel.

> **Märkus:** `rediacc.*` sildid (`rediacc.service_name`, `rediacc.service_ip`, `rediacc.network_id`) lisatakse automaatselt `renet compose` poolt. Sa ei pea neid oma compose-faili lisama.

## TLS-sertifikaadid

TLS-sertifikaadid saadakse automaatselt Let's Encrypt'i kaudu, kasutades Cloudflare DNS-01 proovivõtet. Mandaadid seadistatakse üks kord konfiguratsiooni kohta (jagatud kõigi masinate vahel):

```bash
rdc config infra set -m server-1 \
  --cert-email admin@example.com \
  --cf-dns-token your-cloudflare-api-token
```

Automarsruudid kasutavad **metamärgisertifikaate** hoidla alamdomeeni tasemel (`*.marketing.server-1.example.com`), mitte teenusepõhiseid serte. Sertifikaat provisioreeritakse automaatselt Traefikuga esimese `repo up` käivitamisel -- käsitsi sammu pole vaja. Forkid taaskasutavad vanemhoidla olemasolevat metamärki, seega ei käivita need kunagi uut sertifikaadi taotlust. Kohandatud domeeni marsruudid kasutavad masinatasemel metamärke (`*.server-1.example.com`).

> **Nõuab Cloudflare'i mandaate.** Metamärgiserdid kasutavad DNS-01 proovivõtet. Ilma `--cf-dns-token`'ita (ja valikulise `--cert-email`'ita) ei suuda Traefik proovivõtet lõpetada ja HTTPS ei tööta. HTTP jääb toimivaks. Konfigureeri mandaadid `rdc config infra set` abil enne esimest juurutamist.

2. taseme marsruutidel `traefik.http.routers.{name}.tls.certresolver=letsencrypt` puhul lisatakse metamärgi domeeni SAN-id automaatselt marsruudi hostinimi põhjal.

Cloudflare DNS API tookenil on vaja `Zone:DNS:Edit` õigust domeenidele, mida soovid turvata.

### TLS-sertifikaadi elutsükkel

Täielik tee, mille Let's Encrypt sert väljastamisest iga hoidla konteineriteni läbib:

1. **Väljastamine hostil.** Masinataseme Traefiku konteiner (`rediacc-proxy`, juurutatud asukohta `/opt/rediacc/proxy/`) omab ACME uuendamist. See salvestab kogu oleku faili `/opt/rediacc/proxy/letsencrypt/acme.json` hostil. Uuendamine käivitub automaatselt ~30 päeva enne aegumist -- operaatori tegevust pole vaja, kuni `--cf-dns-token` on seadistatud.

2. **Hoidlapõhine väljapumpamine (valikuline).** Teenused, mis vajavad serdi faile oma konteineri sees (näiteks meiliserverid, mis loevad `.pem` faili otse), juurutavad kõrval väikese `traefik-certs-dumper` konteineri. Väljapumpaja ühendab kirjutuskaitstult `/opt/rediacc/proxy/letsencrypt` ja kirjutab ekstraheeritud serdi + võtme hoidla andmemahtu failidena `cert.pem` / `key.pem`. Selleks peab hoidlapõhine Dockeri daemon omama `/opt/rediacc/proxy` oma mount-nimeruumi lubamisloendis. See on vaikimisi juba lisatud.

3. **Kliendipoolne vahemälu (`rediacc.json`).** CLI vahemälustab `acme.json` tihendatud koopia `acmeCertCache` alla oma konfiguratsioonifailis, võtmena `baseDomain`. See võimaldab mitmel masinal serte jagada (läbi `rdc config cert-cache push -m <machine>`) ja toimib offline-inventuurina.

**Kliendivahemälu sünkroonimise käivitajad:**

- Automaatselt pärast `rdc repo up`, kuid ainult juhul, kui masina `baseDomain` kohalik vahemälu on vanem kui 6 tundi. Värskeid vahemälusid ei puudutata, et järjestikused juurutamised SSH-d ei koormaauks.
- Nõudmisel: `rdc config cert-cache pull -m <machine>` (sunniviisiline tõmbamine) või `rdc machine query --name <machine> --sync-certs` (tõmbamine olekupäringu kõrvalefektina).
- `rdc config infra push` käivitamisel lükatakse vahemälu masinale üles (pikema aegumisega kohalikud serdid võidavad kaugserdi üle).

**Vahemälu hooldus:**

- Aegunud automarsruudi kirjed (vanad võrgu-ID sildistatud domeenid, nagu `service-3200.rediacc.io`) kustutatakse iga tõmbamise käigus.
- Serdid, mille `notAfter` on rohkem kui 7 päeva minevikus, eemaldatakse täielikult. Need on passiivsed ja ainult paisutavad vahemälu.
- `rdc config cert-cache clear` kustutab kõik; `rdc config cert-cache status` näitab inventuuri.

**Tõrkeotsing:** kui `traefik-certs-dumper` jookseb kokku veateatega `/traefik/acme.json: no such file or directory`, ei näe hoidlapõhine daemon hosti letsencrypt-poodi. Kontrolli, et (a) `/opt/rediacc/proxy/letsencrypt/acme.json` eksisteerib hostil (see on hostitseme `rediacc-proxy` vastutus) ja (b) hoidlapõhine daemon käivitati piisavalt uue renet-versiooniga, mis lubab `/opt/rediacc/proxy`. Renet'i uuendamisel rakenda muudatused käsuga `rdc repo up`.

> **Eksperimentaalne:** Auto-sünkroonimise sagedus ja aegumispõhine puhastamine laevati renet 0.9-ga. Vanemad CLI/renet versioonid kasutavad ainult käsitsi sünkroniseerimist `rdc config cert-cache pull` kaudu.

## TCP/UDP pordiedastus

Mitte-HTTP protokollide jaoks (meiliserverid, DNS, väliselt avaldatud andmebaasid) kasuta TCP/UDP pordiedastust.

### 1. samm: registreeri pordid

Lisa vajalikud pordid infrastruktuuri konfigureerimisel:

```bash
rdc config infra set -m server-1 \
  --tcp-ports 25,143,465,587,993 \
  --udp-ports 53

rdc config infra push -m server-1
```

See loob Traefiku sisenemispunktid nimedega `tcp-{port}` ja `udp-{port}`.

> Pärast portide lisamist või eemaldamist käivita alati uuesti `rdc config infra push`, et proksi konfiguratsiooni uuendada.

### 2. samm: lisa TCP/UDP sildid

Kasuta oma compose-failis `traefik.tcp.*` või `traefik.udp.*` silte:

```yaml
services:
  mail-server:
    image: ghcr.io/docker-mailserver/docker-mailserver:latest
    labels:
      - "traefik.enable=true"

      # SMTP (port 25)
      - "traefik.tcp.routers.mail-smtp.entrypoints=tcp-25"
      - "traefik.tcp.routers.mail-smtp.rule=HostSNI(`*`)"
      - "traefik.tcp.routers.mail-smtp.service=mail-smtp"
      - "traefik.tcp.services.mail-smtp.loadbalancer.server.port=25"

      # IMAPS (port 993), TLS läbivool
      - "traefik.tcp.routers.mail-imaps.entrypoints=tcp-993"
      - "traefik.tcp.routers.mail-imaps.rule=HostSNI(`mail.example.com`)"
      - "traefik.tcp.routers.mail-imaps.tls.passthrough=true"
      - "traefik.tcp.routers.mail-imaps.service=mail-imaps"
      - "traefik.tcp.services.mail-imaps.loadbalancer.server.port=993"
```

Põhimõisted:
- **`HostSNI(\`*\`)`** sobib mis tahes hostinamega (protokollide jaoks, mis ei saada SNI-d, näiteks tavaline SMTP)
- **`tls.passthrough=true`** tähendab, et Traefik edastab toores TLS-ühenduse dekrüpteerimata, rakendus tegeleb TLS-iga ise
- Sisenemispunkti nimed järgivad konventsiooni `tcp-{port}` või `udp-{port}`

### Lihtne TCP näide (andmebaas)

Andmebaasi väliselt avaldamiseks ilma TLS-läbivoota (Traefik edastab toores TCP):

```yaml
services:
  postgres:
    image: postgres:17
    labels:
      - "traefik.enable=true"
      - "traefik.tcp.routers.mydb.entrypoints=tcp-5432"
      - "traefik.tcp.routers.mydb.rule=HostSNI(`*`)"
      - "traefik.tcp.services.mydb.loadbalancer.server.port=5432"
```

Port 5432 on eelkonfigureeritud (vt allpool), seega pole `--tcp-ports` seadistust vaja.

> **Turvahoiatus:** Andmebaasi internetti avaldamine on risk. Kasuta seda ainult siis, kui kaugklientidel on vaja otseühendust. Enamiku seadistuste puhul hoia andmebaas sisemisena ja ühenda rakenduse kaudu.

### Eelkonfigureeritud pordid

Järgmistel TCP/UDP portidel on sisenemispunktid vaikimisi (pole vaja lisada `--tcp-ports` kaudu). Sisenemispunktid genereeritakse ainult seadistatud aadressiperekondade jaoks: IPv4 sisenemispunktid nõuavad `--public-ipv4`, IPv6 sisenemispunktid nõuavad `--public-ipv6`:

| Port | Protokoll | Tavaline kasutus |
|------|----------|------------|
| 80 | HTTP | Veebi (automaatümbersuunamine HTTPS-ile) |
| 443 | HTTPS | Veebi (TLS) |
| 3306 | TCP | MySQL/MariaDB |
| 5432 | TCP | PostgreSQL |
| 6379 | TCP | Redis |
| 27017 | TCP | MongoDB |
| 11211 | TCP | Memcached |
| 5672 | TCP | RabbitMQ |
| 9092 | TCP | Kafka |
| 53 | UDP | DNS |
| 10000-10010 | TCP | Dünaamiline vahemik (automaateraldus) |

## DNS-konfigureerimine

### Automaatne DNS (Cloudflare)

Kui `--cf-dns-token` on seadistatud, loob `rdc config infra push` automaatselt DNS-kirjed masina alamdomeeni jaoks Cloudflare'is:

| Kirje | Tüüp | Sisu | Loob |
|--------|------|---------|------------|
| `server-1.example.com` | A / AAAA | Masina avalik IP | `push-infra` |
| `*.server-1.example.com` | A / AAAA | Masina avalik IP | `push-infra` |
| `*.marketing.server-1.example.com` | A / AAAA | Masina avalik IP | `repo up` |

Masinataseme kirjed loob `push-infra` ja need katavad kohandatud domeeni marsruudid (`rediacc.domain`). Hoidlapõhised metamärgikirjed loob `repo up` automaatselt ja need katavad selle hoidla automarsruudid.

See on idempotentne: olemasolevaid kirjeid uuendatakse, kui IP muutub, ja jäetakse muutmata, kui need on juba õiged.

Põhidomeeni metamärk (`*.example.com`) tuleb luua käsitsi, kui kasutad kohandatud domeeni silte nagu `rediacc.domain=erp`.

### Käsitsi DNS

Kui ei kasuta Cloudflare'i või haldad DNS-i käsitsi, loo A (IPv4) ja/või AAAA (IPv6) kirjed:

```
# Masina alamdomeen (kohandatud domeeni marsruutide jaoks nagu rediacc.domain=erp)
server-1.example.com           A     203.0.113.50
*.server-1.example.com         A     203.0.113.50
*.server-1.example.com         AAAA  2001:db8::1

# Hoidlapõhised metamärgid (automarsruutide jaoks nagu myapp.marketing.server-1.example.com)
*.marketing.server-1.example.com    A     203.0.113.50
*.marketing.server-1.example.com    AAAA  2001:db8::1

# Põhidomeeni metamärk (kohandatud domeeniteenuste jaoks nagu rediacc.domain=erp)
*.example.com                  A     203.0.113.50
```

Cloudflare DNS-iga seadistatult loob `repo up` hoidlapõhised metamärgikirjed automaatselt. Mitme masina puhul saab iga masin oma DNS-kirjed, mis osutavad tema enda IP-le.

## Vahevarad

Traefiku vahevarad muudavad päringuid ja vastuseid. Rakenda neid siltide kaudu.

### HSTS (HTTP Strict Transport Security)

```yaml
labels:
  - "traefik.http.middlewares.myapp-hsts.headers.stsSeconds=15768000"
  - "traefik.http.middlewares.myapp-hsts.headers.stsIncludeSubdomains=true"
  - "traefik.http.middlewares.myapp-hsts.headers.stsPreload=true"
  - "traefik.http.routers.myapp.middlewares=myapp-hsts"
```

### Suurte failide üleslaadimise puhverdamine

```yaml
labels:
  - "traefik.http.middlewares.myapp-buffering.buffering.maxRequestBodyBytes=536870912"
  - "traefik.http.routers.myapp.middlewares=myapp-buffering"
```

### Mitu vahevara

Ahela vahevarad koma eraldusega:

```yaml
labels:
  - "traefik.http.routers.myapp.middlewares=myapp-hsts,myapp-buffering"
```

Täieliku saadaolevate vahevarade loendi leiad [Traefiku vahevara dokumentatsioonist](https://doc.traefik.io/traefik/middlewares/overview/).

## Diagnostika

Kui teenus pole kättesaadav, SSH-i serverisse ja kontrolli marsruutimisserveri lõpp-punkte:

### Terviskontroll

```bash
curl -s http://127.0.0.1:7111/health | python3 -m json.tool
```

Näitab üldist olekut, avastatud marsruuterite ja teenuste arvu ning kas automarsruudid on lubatud.

### Avastatud marsruudid

```bash
curl -s http://127.0.0.1:7111/routes.json | python3 -m json.tool
```

Loetleb kõik HTTP, TCP ja UDP marsruuterid koos nende reeglite, sisenemispunktide ja tagateenustega.

### Pordi eraldused

```bash
curl -s http://127.0.0.1:7111/ports | python3 -m json.tool
```

Näitab dünaamiliselt eraldatud portide TCP ja UDP pordimappinguid.

### Levinud probleemid

| Probleem | Põhjus | Lahendus |
|---------|-------|----------|
| Teenust pole marsruutides | Konteiner ei tööta või puuduvad sildid | Kontrolli `docker ps`-ga hoidla daemonist; kontrolli silte |
| Sertifikaati pole väljastatud | DNS ei osuta serverile või Cloudflare'i token on vale | Kontrolli DNS-i lahendust; kontrolli Cloudflare API tokeni õigusi |
| 502 Bad Gateway | Rakendus ei kuula deklareeritud pordil | Kontrolli, et rakendus töötab ja port vastab `loadbalancer.server.port`-ile |
| TCP-port pole kättesaadav | Port pole infrastruktuuris registreeritud | Käivita `rdc config infra set --tcp-ports ...` ja `push-infra` |
| Marsruutimisserver töötab vana versiooniga | Binaarne fail uuendati, kuid teenust ei taaskäivitatud | Toimub automaatselt provisioneerimisel; käsitsi: `sudo systemctl restart rediacc-router` |
| STUN/TURN relee pole kättesaadav | Relee aadressid vahemälustati käivitamisel | Taas-loo teenus pärast DNS-i või IP muutusi, et see võtaks uue võrgukonfiguratsiooni |

## Täielik näide

See juurutab veebirakenduse PostgreSQL andmebaasiga. Rakendus on avalikult kättesaadav aadressil `app.example.com` TLS-iga; andmebaas on ainult sisemine.

### docker-compose.yml

```yaml
services:
  webapp:
    image: myregistry/webapp:latest
    environment:
      DATABASE_URL: postgresql://app:changeme@postgres:5432/webapp
      LISTEN_ADDR: 0.0.0.0:3000
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.webapp.rule=Host(`app.example.com`)"
      - "traefik.http.routers.webapp.entrypoints=websecure,websecure-v6"
      - "traefik.http.routers.webapp.tls.certresolver=letsencrypt"
      - "traefik.http.services.webapp.loadbalancer.server.port=3000"
      # HSTS
      - "traefik.http.middlewares.webapp-hsts.headers.stsSeconds=15768000"
      - "traefik.http.middlewares.webapp-hsts.headers.stsIncludeSubdomains=true"
      - "traefik.http.routers.webapp.middlewares=webapp-hsts"

  postgres:
    image: postgres:17
    environment:
      POSTGRES_DB: webapp
      POSTGRES_USER: app
      POSTGRES_PASSWORD: changeme
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
    # Traefik-silte pole, ainult sisekasutuseks
```

### Rediaccfile

```bash
#!/bin/bash

up() {
    mkdir -p data/postgres
    renet compose -- up -d
}

down() {
    renet compose -- down
}
```

### DNS

Loo A-kirje, mis osutab `app.example.com` sinu serveri avalikule IP-le:

```
app.example.com   A   203.0.113.50
```

### Juurutamine

```bash
rdc repo up --name my-app -m server-1
```

Mõne sekundi jooksul avastab marsruutimisserver konteineri, Traefik võtab marsruudi üle, taotleb TLS-sertifikaati ja `https://app.example.com` on live.
