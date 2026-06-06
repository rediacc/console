---
title: "Rediacci reeglid"
description: "Olulised reeglid ja kokkulepped rakenduste ehitamiseks Rediacci platvormil. Katab Rediaccfile'i, compose'i, võrgunduse, salvestuse, CRIU ja juurutamise."
category: "Guides"
order: 5
language: et
sourceHash: "74803e91ef07b03c"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# Rediacci reeglid

Iga Rediacci repositoorium töötab isoleeritud keskkonnas oma Dockeri deemoni, krüpteeritud LUKS-mahu ja pühendatud IP-vahemikuga. Need reeglid tagavad, et teie rakendus töötab selles arhitektuuris õigesti.

## Rediaccfile

- **Igal repositooriumil peab olema Rediaccfile**, bash-skript elutsükli funktsioonidega.
- **Elutsükli funktsioonid**: `up()`, `down()`. Valikuline: `info()`.
- `up()` käivitab teie teenused. `down()` peatab need.
- `info()` pakub olekuteavet (konteineri olek, hiljutised logid, tervis).
- Rediaccfile'i laeb renet, sellel on juurdepääs shelli muutujatele, mitte ainult keskkonna muutujatele.

### Saadaolevad keskkonna muutujad Rediaccfile'is

| Muutuja | Näide | Kirjeldus |
|----------|---------|-------------|
| `REDIACC_WORKING_DIR` | `/mnt/rediacc/mounts/abc123/` | Ühendatud repositooriumi juuretee |
| `REDIACC_NETWORK_ID` | `6336` | Võrgupõhise isoleerimise identifikaator |
| `REDIACC_REPOSITORY` | `abc123-...` | Repositooriumi GUID |
| `{SVCNAME}_IP` | `HEARTBEAT_IP=127.0.24.195` | Teenusepõhine loopback-IP (teenuse nimi suurtähtedega) |

### Minimaalne Rediaccfile

```bash
#!/bin/bash

_compose() {
  renet compose -- "$@"
}

up() {
  _compose up -d
}

down() {
  _compose down
}
```

## Compose

- **Kasutage `renet compose`, mitte `docker compose`**, renet süstib võrgu isoleerimise, hosti võrgunduse, loopback-IP-d ja teenuse sildid.
- **Ärge määrake `network_mode`**-i oma compose-failis, renet sunnib `network_mode: host`-i kõigile teenustele. Kõik teie määratud väärtused kirjutatakse üle.
- **Ärge määrake `rediacc.*`-silte**, renet süstib automaatselt `rediacc.network_id`, `rediacc.service_ip` ja `rediacc.service_name`.
- **`ports:`-kaardistused eiratakse** hosti võrguühenduse režiimis. Lisage `rediacc.service_port`-silt HTTP-marsruutimiseks (teenused ilma selle sildita ei saa HTTP-marsruute). Kasutage `rediacc.tcp_ports`/`rediacc.udp_ports`-silte TCP/UDP-edasisuunamiseks.
- **Taaskäivituspoliitikad (`restart: always`, `on-failure` jne) on ohutu kasutada**, renet eemaldab need automaatselt CRIU ühilduvuse jaoks. Marsruuteri valvekoer taastab peatatud konteinerid automaatselt `.rediacc.json`-sse salvestatud algse poliitika alusel.
- **Ohtlikud seadistused on vaikimisi blokeeritud**, `privileged: true`, `pid: host`, `ipc: host` ja süsteemiteede hosti sidumiskohad lükatakse tagasi. Kasutage `renet compose --unsafe`, et tühistada omal vastutusel.

### Keskkonna muutujad konteinerite sees

Renet süstib need automaatselt igasse konteinerisse:

| Muutuja | Kirjeldus |
|----------|-------------|
| `SERVICE_IP` | Selle konteineri pühendatud loopback-IP |
| `REDIACC_NETWORK_ID` | Võrgupõhise isoleerimise ID |

### Teenuse nimetamine ja marsruutimine

- Compose'i **teenuse nimi** saab automaatse marsruudi URL-eesliiteks.
- **Grand repositooriumid**: `https://{service}.{repo}.{machine}.{baseDomain}` (nt `https://myapp.marketing.server-1.example.com`).
- **Fork-repositooriumid**: `https://{service}-fork-{tag}.{repo}.{machine}.{baseDomain}` (nt `https://myapp-fork-staging.marketing.server-1.example.com`). `-fork-`-eraldaja hoiab ära URL-kokkupõrked grand-repositooriumi teenuste nimedega. Forki URL kasutab alati vanema repositooriumi olemasolevat metamärgi sertifikaati, seega pole uut serti vaja.
- Kohandatud domeenide jaoks kasutage Traefiku silte (kuid märkige: kohandatud domeenid EI sobi forkidega, domeen kuulub grand-repositooriumile).

## Võrgundus

- **Igal repositooriumil on oma Dockeri deemon** aadressil `/var/run/rediacc/docker-<networkId>.sock`.
- **Igal teenusel on unikaalne loopback-IP** /26-alamvõrgus (nt `127.0.24.192/26`).
- **Sidumine on automaatne**: Teenused saavad siduda `0.0.0.0` või `localhost` külge - kernel kirjutab aadressi läbipaistvalt teenuse määratud loopback-IP-ga üle. Selgesõnaline `${SERVICE_IP}` sidumine töötab endiselt, kuid pole enam nõutav.
- **Tervisekontrollid võivad kasutada `localhost`-i** või `${SERVICE_IP}`-d. Näide: `healthcheck: test: ["CMD", "curl", "-f", "http://localhost:8080/health"]`
- **Repositooriumivahelised ühendused on kerneli poolt blokeeritud**: Kernel blokeerib automaatselt ühendused loopback-IP-dega väljaspool repositooriumi `/26`-alamvõrku. Teenus ühes repositooriumis ei saa jõuda teenusteni teises repositooriumis.
- **Teenustevaheline side**: Kasutage **teenuste nimesid** (nt `db`, `redis`) - renet süstib automaatselt iga teenuse nime hostinimena, mis lahendatakse õige IP-sse. Dockeri DNS-nimed EI tööta hosti režiimis, kuid teenuste nimed `/etc/hosts` kaudu töötavad. Vältige `${DB_IP}` või sarnase süsteemi manustamist püsivatesse konfiguratsioonifailidesse (nt andmebaasi salvestatud ühendusstringid) - forkimisel kandub toores IP üle ja osutab valele repositooriumile. Teenuste nimed lahendatakse alati õigesti repositooriumi kaupa.
- **Pordikonfliktid on võimatud** repositooriumide vahel, igal on oma Dockeri deemon ja IP-vahemik.
- **TCP/UDP pordi edasisuunamine**: Lisage sildid mitte-HTTP-portide paljastamiseks:
  ```yaml
  labels:
    - "rediacc.tcp_ports=5432,3306"
    - "rediacc.udp_ports=53"
  ```

## Salvestus

- **Kõik Dockeri andmed salvestatakse krüpteeritud repositooriumi sisse**, Dockeri `data-root` asub LUKS-mahus aadressil `{mount}/.rediacc/docker/data`. Nimetatud mahud, pildid ja konteineri kihid on kõik krüpteeritud, varundatud ja automaatselt forkitud.
- **Sidumiskohad `${REDIACC_WORKING_DIR}/...`-sse on soovitatavad** selguse huvides, kuid nimetatud mahud töötavad samuti turvaliselt.
  ```yaml
  volumes:
    - ${REDIACC_WORKING_DIR}/data:/data        # sidumine (soovitatav)
    - pgdata:/var/lib/postgresql/data      # nimetatud maht (ka turvaline)
  ```
- LUKS-maht on ühendatud aadressil `/mnt/rediacc/mounts/<guid>/`.
- BTRFS-hetktõmmised jäädvustavad kogu LUKS-taustafaili, sealhulgas kõik sidumiskoha andmed.
- Andmesalv on fikseeritud suurusega BTRFS-mahufail süsteemi kettal. Kasutage `rdc machine query --name <name> --system`, et näha tegelikku vaba ruumi. Laiendage käsuga `rdc datastore resize`.

## CRIU (reaalajas migratsioon)

- **Kaasamine sildi kaudu**: Lisage `rediacc.checkpoint=true` konteineritele, mida soovite kontrollpunkti seada. Konteinerid ilma selleta (andmebaasid, vahemälud) käivituvad värsked ja taastuvad oma mehhanismide kaudu (WAL, LDF, AOF).
- **`repo down --checkpoint`** salvestab protsessi oleku enne peatamist, järgmine `repo up` taastab automaatselt. **See on peamine sama-masina voog**, mis on kinnitatud töötavana.
- **`backup push --checkpoint`** jäädvustab töötava protsessi mälu + kettaoleku märgistatud konteinerite jaoks, seejärel edastab mahu teisele masinale. Taastage sihtmasinal käsuga `repo up`.
- **`repo fork --checkpoint`** jäädvustab protsessi oleku enne forkimist ja CoW-kloonib kontrollpunkti forkiga. ⚠️ Samal masinal ebaõnnestub järgnev `repo up` forkil **praegu** veateatega `criu failed: type RESTORE errno 0`, kui vanem on veel töötamas. Ülalvoolsed CRIU vead [checkpoint-restore/criu#478](https://github.com/checkpoint-restore/criu/issues/478) / [#514](https://github.com/checkpoint-restore/criu/issues/514). Kasutage `repo down --checkpoint` kohapealseks salvestamiseks/taastamiseks või `backup push --checkpoint` masina ülese migratsiooni jaoks.
- **`repo up`** tuvastab kontrollpunkti andmed automaatselt ja taastab, kui need leitakse. Kasutage `--skip-checkpoint`, et sundida värsket käivitamist.
- **Sõltuvusteadlik taastamine**: Kasutab compose'i `depends_on`, et käivitada andmebaasid esmalt (oodata tervena), seejärel CRIU-taastada rakenduse konteinerid.
- **TCP-ühendused muutuvad taastamisel aegunuks**, rakendused peavad käsitlema `ECONNRESET`-i ja uuesti ühenduma. CRIU ei säilita aktiivse TCP-ühenduse olekut taastamise üleselt üheski toetatud voos.
- **Dockeri eksperimentaalne režiim** on lubatud automaatselt repositooriumipõhistel deemonitel.
- **CRIU installitakse** `rdc config machine setup` käigus.
- **`/etc/criu/runc.conf`** on konfigureeritud vaikimisi koos `tcp-established`-ga.
- **Konteineri turvapoliitikad süstitakse automaatselt märgistatud konteineritele**, `renet compose` lisab järgmised `rediacc.checkpoint=true`-ga konteineritele:
  - `cap_add`: `CHECKPOINT_RESTORE`, `SYS_PTRACE`, `NET_ADMIN` (minimaalne komplekt CRIU jaoks kernelis 5.9+)
  - `security_opt`: `apparmor=unconfined` (CRIU AppArmori tugi pole ülalvoolul veel stabiilne)
  - `userns_mode: host` (CRIU nõuab init-nimeruum juurdepääsu `/proc/pid/map_files`-le)
- Konteinerid ilma sildita töötavad puhtama turvapoosiga (ilma lisavõimalusteta).
- Dockeri vaikimisi seccomp-profiil säilitatakse, CRIU kasutab `PTRACE_O_SUSPEND_SECCOMP` (kernel 4.3+), et filtreid kontrollpunkti/taastamise ajal ajutiselt peatada.
- **Ärge määrake CRIU võimalusi käsitsi** oma compose-failis, renet käsitseb seda sildi alusel.
- Vaadake [heartbeat-malli](https://github.com/rediacc/console/tree/main/packages/json/templates/monitoring/heartbeat) CRIU-ühilduva viiterakenduse jaoks.

### CRIU-ühilduvad rakenduse mustrid

- Käsitsege `ECONNRESET`-i kõigil püsiühendustel (andmebaasibasseinid, veebipesad, sõnumijärjekorrad).
- Kasutage ühendusbasseini teeke, mis toetavad automaatset taasühendamist.
- Lisage `process.on("uncaughtException")` ohutusnet aegunud pesavigade jaoks sisemistest teegiobjektidest.
- Taaskäivituspoliitikaid haldab renet automaatselt (eemaldatakse CRIU jaoks, valvekoer käsitseb taastamist).
- Vältige Dockeri DNS-ile toetumist, kasutage loopback-IP-sid teenuste vaheliseks suhtluseks.

### Hosti turvapoliitikad OS-i kaupa

Kõigil viiel ametlikult toetatud serveri OS-il (vaadake [Nõuded](/en/docs/requirements)) kasutavad repositooriumipõhine dockeri deemon ja selle käitatavad konteinerid **vaikimisi konteinersilte**. `rdc config machine setup` ei installi kohandatud SELinuxi poliitikat ega AppArmori profiili. See on tahtlik: kompromiss seisneb selles, et konteineri protsessid töötavad hosti OS-i vaikimisi sildi poliitika all, mitte Rediacci-spetsiifilise pidamispoliitika all. Kui teie ohumudelis on vajalikud kohustusliku juurdepääsu kontrollid konteineri tasandil, konfigureerige need hosti tasandil enne juurutamist.

- **Ubuntu 24.04 / openSUSE Leap 16.0**: AppArmor on vaikimisi lubatud. Konteinerid töötavad vaikimisi docker-container profiili all. Ainus erand on CRIU (`apparmor=unconfined` `rediacc.checkpoint=true`-konteinerite jaoks, vastavalt ülaltoodud märkusele).
- **Fedora 43 / Oracle Linux 10**: SELinux töötab vaikimisi jõustataval režiimil. Konteinerid saavad standardse `container_t` konteksti. Lisapoliitika installimine pole vajalik. Kui seadistamise samm ebaõnnestub AVC-keeldumistega, vaadake [Tõrkeotsing – SELinuxi keeldumised](/en/docs/troubleshooting).
- **Debian 13**: AppArmor on saadaval, kuid ei jõustata vaikimisi kõigil domeenidel. Konteinerid kasutavad endiselt docker-container profiili.

Kokkuvõte: `rdc` ja `renet` tuvastavad käitatava OS-i automaatselt ja toodavad sama repositooriumipõhise isoleerimise kõigil viiel toetatud distributsioonil. OS-põhist turvaasendi lippu pole vaja.

## Turvalisus

- **LUKS-krüpteerimine** on standardsete repositooriumide jaoks kohustuslik. Igal repositooriumil on oma krüpteerimisvõti.
- **Mandaadid on salvestatud CLI konfiguratsioonis** (`~/.config/rediacc/rediacc.json`). Konfiguratsiooni kaotamine tähendab juurdepääsu kaotamist krüpteeritud mahtudele.
- **Ärge kunagi siduge mandaate** versioonihaldusesse. Kasutage `env_file`-i ja genereerige saladused `up()`-is.
- **Repositooriumi isoleerimine**: Iga repositooriumi Dockeri deemon, võrgustik ja salvestus on täielikult isoleeritud teistest repositooriumitest samal masinal.
- **Agendi isoleerimine**: AI-agendid töötavad vaikimisi ainult fork-režiimis. Igal repositooriumil on oma SSH-võti koos serveripoolse liivakastijõustamisega (`sandbox-gateway` ForceCommand). Kõik ühendused on liivakastis Landlock LSM, OverlayFS kodu-ülekatte ja repositooriumipõhise TMPDIR-iga. Repositooriumiülene failisüsteemi juurdepääs on kerneli poolt blokeeritud.
- **`sudo` on repositooriumi liivakastis disaini järgi keelatud.** Landlock'i failisüsteemi isoleerimine nõuab `NoNewPrivs`, mis takistab igasugust privileegide tõstmist, seega `sudo` ebaõnnestub teatega `no new privileges flag is set`. Repositooriumi omaniku kasutajal on juba kõik vajalikud õigused kõige jaoks repositooriumi ühenduspunkti ja Dockeri pesa sees. Tõeliselt privilegeeritud toimingute jaoks (hosti pakettide installimine, kerneli häälestamine) käivitage need väljaspool liivakasti või Rediaccfile'i `up()` funktsioonist, mida täidab infrastruktuuritee.
- **Dockeri silla võrgundus on keelatud repositooriumipõhistel deemonitel.** Iga repositooriumi `daemon.json` (`FlavorRediacc`) sisaldab `"bridge": "none"` ja `"iptables": false`, seega tavaline `docker run <image>` loob konteineri ainult loopback-liidesega ja ilma väljuva ühenduvuseta. See pole viga, see on see, kuidas repositooriumiülene isoleerimine jõustatakse: kerneli taseme eBPF-konksud, mis blokeerivad ühe repositooriumi jõudmise teise repositooriumi loopback-IP-deni, kehtivad ainult konteineritele, mis elavad hosti võrgu nimeruumis. Tootmisteenuste jaoks kasutage `renet compose`, mis süstib automaatselt `network_mode: host`. Ad-hoc ühekordsete konteinerite jaoks shellis edastage `--network host` selgesõnaliselt. (Kasutajapõhised Hub-deemonid (`FlavorHub`, arenduskeskkonnad) on erandiks: need lubavad `bridge="docker0"` ja `iptables=true`, nii et kasutaja käivitatud konteinerid saavad tavalise väljuva võrguühenduse.)

## Juurutamine

- **`rdc repo up`** ühendab LUKS-mahu automaatselt, kui see on lahti ühendatud, seejärel käivitab kõigi Rediaccfile'ide `up()`-i.
- **`rdc repo down`** käivitab `down()` ja peatab Dockeri deemoni.
- **`rdc repo down --unmount`** sulgeb ka LUKS-mahu (lukustab krüpteeritud salvestuse).
- **Forkid** (`rdc repo fork`) loovad CoW (kopeerimise-kirjutamisel) klooni uue GUID ja networkId-ga, **konstantses ajas sõltumata repositooriumi suurusest**. BTRFS-reflink dubleerib pildimetaandmed, mitte andmed, seega forkitakse 100 GB repositoorium sama mõne sekundiga kui 1 GB repositoorium. Fork jagab vanema krüpteerimisvõtit.
- **Ülevõtmine** (`rdc repo takeover --name <fork> -m <machine>`) asendab grand-repositooriumi andmed forki andmetega. Grand säilitab oma identiteedi (GUID, networkId, domeenid, autostart, varundusakel). Vanad tootmisandmed säilitatakse varukoopia forkina. Kasutage selleks: testige uuendust forkil, kontrollige, seejärel võtke tootmine üle. Pöörduge tagasi käsuga `rdc repo takeover --name <backup-fork> -m <machine>`.
- **Puhverserveri marsruudid** muutuvad aktiivseks umbes 3 sekundit pärast juurutamist. Teade "Proxy is not running" `repo up` ajal on informatiivne ops/dev-keskkondades.
- **`rdc repo up` ja `rdc repo fork --up` trükivad URL-mustri** `rediacc.service_port`-ga märgistatud teenuste jaoks juurutamise lõpus. Asendage `{service}` oma paljastatud teenuse nimega, et saada täpne URL. Teenused ilma `rediacc.service_port`-ita (andmebaasid, töötajad) ei saa marsruute ja neid ei kuvata.

## Levinud vead

- `docker compose` kasutamine `renet compose` asemel - konteinerid ei saa võrgu isoleerimist.
- Taaskäivituspoliitikad on ohutud, renet eemaldab need automaatselt ja valvekoer käsitseb taastamist.
- `privileged: true` kasutamine - pole vajalik, renet süstib spetsiifilised CRIU võimalused.
- Toorte IP-de hardkodeerimine püsivatesse konfiguratsioonifailidesse - kasutage ühenduste jaoks teenuste nimesid, et hoida forki isoleerimine puutumata.
- `rdc term connect -c` kasutamine lahendusena ebaõnnestunud käskude jaoks - teatage vigadest.
- `repo delete` teeb täieliku puhastuse, sealhulgas loopback-IP-d ja systemd-üksused. Käivitage `rdc machine prune --name <name>`, et puhastada pärand-kustutamiste järelejäänud.
