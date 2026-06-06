---
title: "Probleemide lahendamine"
description: "Lahendused tavalistele SSH, seadistuse, repositooriumi, teenuse ja Dockeri probleemidele."
category: "Guides"
order: 10
language: et
sourceHash: "17dc03eb0589d606"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# Probleemide lahendamine

Levinud probleemid ja nende lahendused. Kui oled ebakindel, alusta käsuga `rdc doctor`, mis käivitab täieliku diagnostikakontrolli.

## SSH-ühendus ebaõnnestub

- Kinnita, et saad käsitsi ühenduse luua: `ssh -i ~/.ssh/id_ed25519 deploy@203.0.113.50`
- Käivita `rdc config machine scan-keys -m server-1` hostivõtmete värskendamiseks
- Kontrolli, et SSH-port vastab: `--port 22`
- Testi lihtsa käsuga: `rdc term connect -m server-1 -c "hostname"`

## Hostivõtme lahknevus

Kui server paigaldati ümber või selle SSH-võtmed muutusid, näed "host key verification failed":

```bash
rdc config machine scan-keys -m server-1
```

See tõmbib uued hostivõtmed ja värskendab sinu konfiguratsiooni.

## Masina seadistamine ebaõnnestub

- Tagara, et SSH-kasutajal on sudo-juurdepääs ilma parooliga või konfigureerida `NOPASSWD` vajalike käskude jaoks
- Kontrolli saadaolevat kettaruumi serveris
- Käivita `--debug` piiretega, et näha üksikasjalikku väljundit: `rdc config machine setup --name server-1 --debug`

## Operatsioonisüsteem-spetsiifilised seadistusprobleemid

Viis ametlikult toetatud serveriteoperatsioonisüsteemi (Ubuntu 24.04, Debian 13, Fedora 43, openSUSE Leap 16.0, Oracle Linux 10) kasutavad erinevaid turvalisuspoliitikaid ja paketihaldureid. Enamik seadistusi toimib otse; allpool käsitletakse juhtumeid, kus see nii ei ole.

### SELinux keeldumised (Fedora 43, Oracle Linux 10)

Mõlemad käitavad SELinuxi jõustuva režiimiga. rdc seadistus ei paigalda kohandatud SELinux-i poliitikat; repo kohta eraldi Docker-i daemon käitub standardse `container_t` konteksti all. Kui seadistus ebaõnnestub AVC keeldumiste tõttu, kontrolli auditilogi ja identifitseeri domeeni:

```bash
sudo ausearch -m AVC -ts recent | head -40
# Või:
sudo tail -f /var/log/audit/audit.log | grep AVC
```

Kui keeldumine osutab renet-i binaari või konkreetsele faili teele, on lahendus peaaegu alati ümarmärkimine (`restorecon -v /path`) pigem kui SELinuxi keelamine. Ajutise lahendusena uurimise ajal käivita `sudo setenforce 0`, et liigutada süsteem permissiivse režiimi. Luba ümber käsuga `sudo setenforce 1`, kui kinnitad, et ümarmärkimine püsib.

### AppArmor keeldumised (Ubuntu 24.04, openSUSE Leap 16.0)

Mõlemad käitavad AppArmor-i vaikimisi; repo kohta eraldi Docker-i daemon kasutab vaikimisi konteineri profiili. Kui repositooriumi sees olev konteiner on blokeeritud:

```bash
dmesg | grep -i apparmor
sudo aa-status
```

CRIU on teada juhtum, mis tabab AppArmor-i. renet seab automaatselt `security_opt: apparmor=unconfined` konteineri sildile `rediacc.checkpoint=true`. Sa ei peaks ise konfigureerima AppArmor-i profiile millekski muuks. Vaata CRIU märkusi [Rediacc-i reeglites](/en/docs/rules-of-rediacc).

### Paketihalduri vea signatuurid

| OS | Paketihaldur | Tüüpiline viga | Lahendus |
|----|-----------------|---------------|------------|
| Ubuntu / Debian | apt-get | `File has unexpected size (N != M). Mirror sync in progress?` | Cloudflare-i serverpiin päritolu taga. Proovi `apt-get update` umbes 15 sekundi pärast; integraalsusevalik läbib järgmisele küsitlusele. |
| Fedora / Oracle | dnf | `Problem: nothing provides rediacc-cli` | RPM repo metaandmed kettal on vananenud. Käivita `sudo dnf clean all && sudo dnf makecache`. |
| openSUSE | zypper | `Repository 'rediacc' needs to be refreshed.` | Käivita `sudo zypper refresh rediacc` korra; järgnev paigaldamine peaks õnnestuma. |

### btrfs moodul puudu (RHEL 10 / Rocky Linux 10 / AlmaLinux 10)

Kui `rdc config machine setup` või `renet system check-btrfs` ebaõnnestub:

```
Module btrfs not found
```

...server käitab RHEL 10 standardkerne, mis kaasas btrfs mooduli ilma. See pole Rediacc-i viga; RHEL 10 lobus btrfs-ist tahtlikult. Lahendus on käivitada **Oracle Linux 10 selle asemel**. Oracle 10 vaikimisi Unbreakable Enterprise Kernel (UEK), mis säilitab btrfs-i. Vaata [Nõuded → Miks UEK?](/en/docs/requirements) täisloo jaoks.

## Repositooriumi loomine ebaõnnestub

- Kinnita seadistus oli lõpetatud: andmesalve kaust peab olemas olema
- Kontrolli kettaruumi serveris
- Tagara renet-i binaari on paigaldatud (käivita seadistus uuesti vajaduse korral)

## Teenused ei käivitu

- Kontrolli Rediaccfile-i süntaksit: see peab olema kehtiv Bash
- Tagara Rediaccfile kasutab `renet compose --` (mitte `docker compose`)
- Kinnita Docker-i pildid on ligipääsetavad (arvesta `renet compose -- pull` kasutamisega `up()`)
- Kontrolli konteineri logisid, kasutades repositooriumi Docker-i soklit:

```bash
rdc term connect -m server-1 -r my-app -c "docker logs <container-name>"
```

Või vaata kõiki konteinereid:

```bash
rdc machine containers --name server-1
```

## Juurdepääsu keeldumine vead

- Repositooriumi toimingud nõuavad root õiguseid serveris (renet käitub läbi `sudo`)
- Kinnita, et sinu SSH-kasutaja on `sudo` rühmas
- Kontrolli, et andmesalve kataloogil on õiged õigused

## Docker sokli probleemid

Igal repositooriumil on oma Docker daemon. Docker-i käskude käitamisel käsitsi pead määrama õige sokli:

```bash
# rdc termini kasutamine (automaatselt konfigureeritud):
rdc term connect -m server-1 -r my-app -c "docker ps"

# Või käsitsi soklist:
docker -H unix:///var/run/rediacc/docker-2816.sock ps
```

Asenda `2816` oma repositooriumi võrgu ID-ga (leitud `rediacc.json` või `rdc repo status` kohta).

## `docker run` on ilma võrguta, `apt update` ebaõnnestub, `curl` jääb jääma

Repositooriumi kestis käivitamisel konteinerit ilma `--network host` annab sulle isoleeritud konteineri ainult loopback liidesega, DNS-ita ja ilma väljamineva ühenduseta. Käsud nagu `apt update`, `pip install`, `curl https://...` või mis tahes võrgutõmmis ebaõnnestuvad kohe DNS vigadega.

See on kavatsuslik. Rediacc-i võrgu mudel on **kõigi teenuste jaoks host võrk**, mille jõustab `renet compose`. Vaikimisi Docker bridge NAT-iga möödunuks südamiku taseme loopback isolatsiooni, mis takistab ühel repo-l teise repo teenuseid saavutamast, seega repo kohta Docker daemon (`FlavorRediacc`) on konfigureeritud `"bridge": "none"` ja `"iptables": false` koos. Lihtsa `docker run` konteineri jaoks reitavat bridge-i pole. (Kasutaja poolt Hub daemoniid (`FlavorHub`) töötajad arenduskeskkondadel on erand: nad lubavad bridge + iptables nii kasutaja poolt käituvatel konteineritest on väljaminev võrk.)

**Võrguligipääsuks ad-hoc konteineris kasuta host võrgu:**

```bash
# Repositooriumi kestis (rdc term connect -m <machine> -r <repo>)
docker run --rm --network host -it ubuntu bash
# Nüüd toimivad apt update, curl, pip install.
```

**Tootmisteenus kasutavad Rediaccfile-i `renet compose` kasutamisega** raw `docker run` asemel. `renet compose` süstib `network_mode: host`, teenuse IP sildid ja Traefik-i marsruutimissildid automaatselt. Vaata [Teenused](/en/docs/services) täpsustamiseks.

## VS Code juurdepääsu keeldumine liivakasti failidel

Kui ühendad `rdc vscode connect -m <machine> -r <repo>` pärast eelmist VS Code-i seanssi, vanemad renet-i versioonid tekitasid vigu nagu `scp: .../.vscode-server/vscode-cli-*.tar.gz: Permission denied`. Põhjus: segatõõ omandisuhe liivakasti kataloogis, kus nii sinu SSH-kasutaja kui sisemine `rediacc` kasutaja kirjutasid faile.

Kaasaegsed renet-i versioonid parandavad seda:

- Luumine repo kohta liivakasti tööruumi (`/mnt/rediacc/.interim/sandbox/<repo>/`) `rediacc` rühmaga ja määrake rühma-ID bitti (režiim `2775`), nii et iga selle alla kirjutatud fail pärib õige rühma.
- Rakendada umask `002` liivakasti runtime-is nii et uued failid on loodud rühm-kirjutatavad (`0664`/`0775`).
- Normaliseerib olemasoleva `.vscode-server/` alampuud käivitamisel nii staled failid enne parandust saavad automaatselt parandatud.

Kui näed endiselt juurdepääsu vigu, käivita repo Docker daemon korra `sudo systemctl restart rediacc-docker-<network-id>` seest masina kestis nii normaliseerimise läbisõit käitub, siis proovi uuesti `rdc vscode connect`.

## Daemon ei käivitu pärast renet-i uuendamist

Enne iga stardist `renet daemon start-foreground` kirjutab ümber `daemon.json` ja `containerd.toml` repositooriumi konfiguratsioonist praegusest mallidest, nii et repositoorium, kelle konfig oli genereeritud vanemast renet-i versioonist, korjab automaatselt uue vormingu. Sa ei pea käivitama mis tahes migratsiooni käsku ja sa ei pea käsitsi ümber loodud systemd üksust. Käivita teenus uuesti:

```bash
sudo systemctl restart rediacc-docker-<network-id>
```

Kui üksus on endiselt ebaõnnestumises, kontrolli konkreetse vea jaoks päevaraamatut:

```bash
sudo journalctl -u rediacc-docker-<network-id> --no-pager -n 50
```

## Konteinerid loodud vale Docker Daemon-i

Kui sinu konteinerid ilmuvad host-süsteemi Docker daemon-i asemel repo isoleeritud daemon-i, on kõige levinum põhjus `sudo docker` kasutamine Rediaccfile-is.

`sudo` lähtestab keskkonna muutujad, seega `DOCKER_HOST` kaob ja Docker vaikimisi sokli (`/var/run/docker.sock`). Rediacc blokeerib seda automaatselt, aga kui sa selle kohta:

- **Kasuta `docker` otse**, Rediaccfile funktsioonid käitavad juba piisavate õigustega
- Kui pead kasutama sudo-t, kasuta `sudo -E docker` keskkonna muutujate säilitamiseks
- Kontrolli oma Rediaccfile-i mis tahes `sudo docker` käskude jaoks ja eemalda `sudo`

## Terminal ei toimi

Kui `rdc term` ei avane terminaliakent:

- Kasuta siseside režiimi koos `-c` käskude otseseks käivitamiseks:
  ```bash
  rdc term connect -m server-1 -c "ls -la"
  ```
- Jõusta väline terminal `--external` kui siseside režiim on probleeme
- Linux-is tagara sul on `gnome-terminal`, `xterm` või teised terminali emulaator paigaldatud

## Käivita diagnostika

```bash
rdc doctor
```

See kontrollib sinu keskkonda, renet paigaldust, konfiguratsiooni ja autentimise staatust. Iga kontroll teatab OK, Hoiatus või Viga lühikese selgitusega.
