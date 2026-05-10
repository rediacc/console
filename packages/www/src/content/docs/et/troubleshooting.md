---
title: "Tõrkeotsing"
description: "Lahendused levinud probleemidele SSH, seadistamise, repositooriumide, teenuste ja Dockeriga."
category: "Guides"
order: 10
language: et
---

# Tõrkeotsing

Levinud probleemid ja nende lahendused. Kahtluse korral alusta käsuga `rdc doctor`, mis käivitab põhjaliku diagnostilise kontrolli.

## SSH-ühendus ebaõnnestub

- Veendu, et saad käsitsi ühenduda: `ssh -i ~/.ssh/id_ed25519 deploy@203.0.113.50`
- Käivita `rdc config machine scan-keys -m server-1`, et hostimisvõtmeid uuendada
- Kontrolli, et SSH-port ühtib: `--port 22`
- Testi lihtsa käsuga: `rdc term connect -m server-1 -c "hostname"`

## Hostimisvõtme lahknevus

Kui server paigaldati uuesti või selle SSH-võtmed muutusid, näed teadet "host key verification failed":

```bash
rdc config machine scan-keys -m server-1
```

See hangib värsked hostimisvõtmed ja uuendab sinu konfiguratsiooni.

## Masina seadistamine ebaõnnestub

- Veendu, et SSH-kasutajal on sudo-ligipääs ilma paroolita, või konfigureeri vajalike käskude jaoks `NOPASSWD`
- Kontrolli serveris saadaolevat kettaruumi
- Käivita lipuga `--debug` üksikasjaliku väljundi saamiseks: `rdc config machine setup --name server-1 --debug`

## Distributsioonipõhised seadistamisprobleemid

Viis ametlikult toetatud serverit (Ubuntu 24.04, Debian 13, Fedora 43, openSUSE Leap 16.0, Oracle Linux 10) kasutavad erinevaid turvapoliitikaid ja paketihaldurid. Enamik seadistusi "lihtsalt toimib"; allpool on kirjeldatud juhtumid, mis ei toimi.

### SELinux keelud (Fedora 43, Oracle Linux 10)

Mõlemad käitavad SELinuxi jõustamisrežiimis. rdc setup ei paigalda kohandatud SELinuxi poliitikat; repositooriumipõhine dockeri deemon töötab standardse `container_t` kontekstis. Kui seadistamine ebaõnnestub AVC keeldudega, kontrolli auditi logi ja tuvasta domeen:

```bash
sudo ausearch -m AVC -ts recent | head -40
# Või:
sudo tail -f /var/log/audit/audit.log | grep AVC
```

Kui keeld osutab renet-binaarfailile või konkreetsele failitee, on lahendus peaaegu alati ümbersildimine (`restorecon -v /path`), mitte SELinuxi keelamine. Ajutise lahendusena uurimise ajal liigutab `sudo setenforce 0` süsteemi lubavasse režiimi. Luba uuesti käsuga `sudo setenforce 1`, kui kinnitad, et ümbersildistamine toimib.

### AppArmor keelud (Ubuntu 24.04, openSUSE Leap 16.0)

Mõlemad käitavad vaikimisi AppArmorit; repositooriumipõhine dockeri deemon kasutab konteineri vaikeprofiilit. Kui repositooriumi sees olev konteiner on blokeeritud:

```bash
dmesg | grep -i apparmor
sudo aa-status
```

CRIU on teadaolev juhtum, mis puudutab AppArmorit. Renet seab automaatselt `security_opt: apparmor=unconfined` konteineritele, mille sildiks on `rediacc.checkpoint=true`. Muude asjade jaoks ei tohiks sul olla vaja ise AppArmori profiile konfigureerida. Vaata CRIU märkmeid jaotisest [Rediacc reeglid](/en/docs/rules-of-rediacc).

### Paketihalduri veateated

| OS | Paketihaldur | Tüüpiline viga | Lahendus |
|----|-----------------|---------------|------------|
| Ubuntu / Debian | apt-get | `File has unexpected size (N != M). Mirror sync in progress?` | Cloudflare'i servast peegeldumine. Proovi uuesti `apt-get update` ~15s pärast; terviklikkuse kontroll läbib järgmisel päringul. |
| Fedora / Oracle | dnf | `Problem: nothing provides rediacc-cli` | Kettal olevad RPM-i repositooriumi metaandmed on aegunud. Käivita `sudo dnf clean all && sudo dnf makecache`. |
| openSUSE | zypper | `Repository 'rediacc' needs to be refreshed.` | Käivita üks kord `sudo zypper refresh rediacc`; järgnevad paigaldused peaksid õnnestuma. |

### btrfs-moodul puudub (RHEL 10 / Rocky Linux 10 / AlmaLinux 10)

Kui `rdc config machine setup` või `renet system check-btrfs` ebaõnnestub veaga:

```
Module btrfs not found
```

...siis töötab server RHEL 10 standardse kernelil, mis ei sisalda btrfs-moodulit. See ei ole Rediacc'i viga; RHEL 10 eemaldas btrfs'i tahtlikult. Lahenduseks on kasutada **Oracle Linux 10**. Oracle 10 kasutab vaikimisi Unbreakable Enterprise Kerneli (UEK), mis säilitab btrfs'i. Täielikku selgitust vaata jaotisest [Nõuded - miks UEK?](/en/docs/requirements).

## Repositooriumi loomine ebaõnnestub

- Veendu, et seadistamine on lõpetatud: andmehoidla kataloog peab eksisteerima
- Kontrolli kettaruumi serveris
- Veendu, et renet-binaarfail on paigaldatud (vajadusel käivita seadistamine uuesti)

## Teenused ei käivitu

- Kontrolli Rediaccfile'i süntaksit: see peab olema kehtiv Bash
- Veendu, et sinu Rediaccfile kasutab `renet compose --` (mitte `docker compose`)
- Kontrolli, et Dockeri kujutised on ligipääsetavad (kaalu `renet compose -- pull` funktsioonis `up()`)
- Kontrolli konteineri logisid repositooriumi Dockeri soklit kasutades:

```bash
rdc term connect -m server-1 -r my-app -c "docker logs <container-name>"
```

Või vaata kõiki konteinereid:

```bash
rdc machine containers --name server-1
```

## Ligipääsu keelamine vead

- Repositooriumi toimingud nõuavad serveris juurkasutajat (renet töötab `sudo` kaudu)
- Veendu, et sinu SSH-kasutaja on `sudo` grupis
- Kontrolli, et andmehoidla kataloogil on õiged õigused

## Dockeri sokliprobleemid

Igal repositooriumil on oma Dockeri deemon. Dockeri käskude käsitsi käivitamisel tuleb määrata õige sokel:

```bash
# Kasutades rdc term (automaatselt konfigureeritud):
rdc term connect -m server-1 -r my-app -c "docker ps"

# Või käsitsi sokliga:
docker -H unix:///var/run/rediacc/docker-2816.sock ps
```

Asenda `2816` oma repositooriumi võrgu ID-ga (leiad selle `rediacc.json`-ist või käsuga `rdc repo status`).

## `docker run` pole võrku, `apt update` ebaõnnestub, `curl` hangub

Repositooriumi kestas konteineri käivitamine ilma `--network host` annab sulle isoleeritud konteineri ainult loopback-liidesega, ilma DNS-i ja väljamineva ühenduvuseta. Käsud nagu `apt update`, `pip install`, `curl https://...` või mis tahes võrgupäring ebaõnnestuvad koheselt DNS-i vigadega.

See on tahtlik. Rediacc'i võrgumudel on **hosti võrgustamine iga teenuse jaoks**, mida jõustab `renet compose`. Vaikimisi Dockeri sild NAT-iga mööduks kerneli taseme loopback-isolatsioonist, mis takistab ühel repositooriumil teise repositooriumi teenustele jõudmast, seega on repositooriumipõhine Dockeri deemon konfigureeritud seadetega `"bridge": "none"` ja `"iptables": false`. Tavalisel `docker run` konteineril pole marsruutitavat silda, millega ühenduda.

**Võrguligipääsuks ad-hoc konteineris kasuta hosti võrgustamist:**

```bash
# Repositooriumi kestas (rdc term connect -m <machine> -r <repo>)
docker run --rm --network host -it ubuntu bash
# Nüüd toimivad apt update, curl, pip install.
```

**Tootmisteenuste jaoks kasuta Rediaccfile'i koos `renet compose`'iga** tavalise `docker run` asemel. `renet compose` sisestab `network_mode: host`, teenuse IP-sildid ja Traefiki marsruutimise sildid automaatselt. Üksikasju vaata jaotisest [Teenused](/en/docs/services).

## VS Code "Permission Denied" liivakastifailides

Ühendamisel käsuga `rdc vscode connect -m <machine> -r <repo>` võisid näha vigu nagu `scp: .../.vscode-server/vscode-cli-*.tar.gz: Permission denied` pärast eelmist VS Code seanssi. See oli põhjustatud liivakasti kataloogis segamini failiomandiõigustest, mis hoidsid nii sinu SSH-kasutaja kui ka sisemise `rediacc` kasutaja kirjutatud faile.

Renet'i uuemad versioonid lahendavad selle:

- Luues repositooriumipõhise liivakasti tööruumi (`/mnt/rediacc/.interim/sandbox/<repo>/`) grupiga `rediacc` ja set-group-ID bitiga (režiim `2775`), nii et kõik alla kirjutatud failid pärivad õige grupi.
- Rakendades liivakasti käitusajal umask `002`, nii et uued failid luuakse grupikirjutatavana (`0664`/`0775`).
- Normaliseerides käivitumisel olemasoleva `.vscode-server/` alampuu, nii et paranduse eelsed aegunud failid saavad automaatselt parandatud.

Kui näed endiselt õiguste vigu, taaskäivita repositooriumi Dockeri deemon üks kord käsuga `sudo systemctl restart rediacc-docker-<network-id>` masinal olevast kestast, et normaliseerimise käik töötaks, seejärel proovi uuesti `rdc vscode connect`.

## Deemon ei käivitu pärast renet'i uuendust

Enne iga käivitamist kirjutab `renet daemon start-foreground` `daemon.json` ja `containerd.toml` repositooriumi konfiguratsioonikataloogis uuesti praegustest mallidest üle, nii et vanemat renet'i versiooni konfiguratsiooni kasutav repositoorium võtab automaatselt kasutusele uue formaadi. Sa ei pea käivitama ühtegi migratsioonikommando ega käsitsi systemd ühikut uuesti genereerima. Lihtsalt taaskäivita teenus:

```bash
sudo systemctl restart rediacc-docker-<network-id>
```

Kui ühik ikka veel ebaõnnestub, kontrolli ajakirja konkreetse vea saamiseks:

```bash
sudo journalctl -u rediacc-docker-<network-id> --no-pager -n 50
```

## Konteinerid luuakse vale Dockeri deemoniga

Kui sinu konteinerid ilmuvad hostsüsteemi Dockeri deemonis repositooriumi isoleeritud deemoni asemel, on kõige levinum põhjus `sudo docker` kasutamine Rediaccfile'is.

`sudo` lähtestab keskkonna muutujad, nii et `DOCKER_HOST` läheb kaotsi ja Docker kasutab vaikimisi süsteemi soklit (`/var/run/docker.sock`). Rediacc blokeerib selle automaatselt, kuid kui see juhtub:

- **Kasuta `docker` otse**, Rediaccfile'i funktsioonid töötavad juba piisavate õigustega
- Kui pead sudo kasutama, kasuta `sudo -E docker`, et keskkonna muutujaid säilitada
- Kontrolli oma Rediaccfile'i `sudo docker` käskude suhtes ja eemalda `sudo`

## Terminal ei tööta

Kui `rdc term` ei suuda terminaliakent avada:

- Kasuta ridade käivitamiseks sisemist režiimi lipuga `-c`:
  ```bash
  rdc term connect -m server-1 -c "ls -la"
  ```
- Jõusta väline terminal lipuga `--external`, kui sisel režiimil on probleeme
- Linuxis veendu, et sul on paigaldatud `gnome-terminal`, `xterm` või mõni muu terminaaliemulaat

## Diagnostika käivitamine

```bash
rdc doctor
```

See kontrollib sinu keskkonda, renet'i paigaldust, konfiguratsiooni seadistust ja autentimise olekut. Iga kontroll annab lühikese selgitusega tulemuse OK, Hoiatus või Viga.
