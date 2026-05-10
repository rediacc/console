---
title: Nõuded
description: Süsteeminõuded ja toetatud platvormid Rediacci käitamiseks.
category: Guides
order: 0
language: et
---

# Nõuded

Enne Rediacciga juurutamist veenduge, et teie tööjaam ja kaugserverid vastavad järgmistele nõuetele.

## Tööjaam (juhtimistasand)

`rdc` CLI töötab teie tööjaamas ja korraldab kaugservereid SSH kaudu.

| Platvorm | Minimaalne versioon | Märkused |
|----------|----------------|-------|
| macOS | 12 (Monterey)+ | Intel ja Apple Silicon toetatud |
| Linux (x86_64) | Mis tahes kaasaegne distributsioon | glibc 2.31+ (Ubuntu 20.04+, Debian 11+, Fedora 34+) |
| Windows | 10+ | Natiivne tugi PowerShelli installija kaudu |

**Täiendavad nõuded:**
- SSH võtmepaar (nt `~/.ssh/id_ed25519` või `~/.ssh/id_rsa`)
- Võrguühendus teie kaugserveri SSH-pordiga (vaikimisi: 22)

## Kaugserver (andmetasand)

`renet` binaarne käivitub kaugserveritel root-õigustega. See haldab krüpteeritud kettapilte, isoleeritud Dockeri deemoneid ja teenuste orkestreerimist.

Kui te pole kindel, millist binaari kasutada, vaadake [rdc vs renet](/en/docs/rdc-vs-renet). Lühidalt: kasutage `rdc`-d tavapärasteks toiminguteks ja otsest `renet`-i ainult täpsemateks kaugpoolseteks ülesanneteks.

### Toetatud operatsioonisüsteemid

Kaugserverid käitavad `renet` binaari ja majutavad krüpteeritud, repositooriumipõhiseid Dockeri deemoneid. Järgmist viit distributsiooni katsetatakse Bridge Workers maatriksis CI-s igal tõmbetaotlusel ja need on ainsad ametlikult toetatud:

| OS | Versioon | Vaikimisi kernel | Märkused |
|----|---------|----------------|-------|
| Ubuntu | 24.04 LTS | 6.8 | Soovitatav. AppArmor on vaikimisi lubatud. |
| Debian | 13 (Trixie) | 6.12 | Debian 12 töötab samuti (kernel 6.1 minimaalselt). |
| Fedora | 43 | 6.12 | SELinux jõustataval režiimil vaikimisi. |
| openSUSE Leap | 16.0 | 6.4+ | AppArmor on vaikimisi lubatud. |
| Oracle Linux | 10 | UEK 7+ | Kasutab UEK-i, mis säilitab btrfs-mooduli. SELinux jõustataval režiimil vaikimisi. Vaadake allpool jaotist "Miks UEK?" |

Kõik read on `x86_64`. `arm64` on ehitatud, kuid mitte pidevalt testitud iga serveri OS-i jaoks; avage probleem, kui vajate seda konkreetsel distributsioonil. Teised Linuxi distributsioonid koos systemd, Dockeri toe ja cryptsetup'iga võivad töötada, kuid neid ei toetata ametlikult ja need võivad uuendustega etteteatamata katkeda.

#### Miks UEK? (ja miks Rocky 10 / standardne RHEL 10 ei ole toetatud)

Rediacci krüpteeritud salvestusserveri taustarakendus nõuab puusisest `btrfs` kerneli moodulit. **RHEL 10 standardne kernel saadetakse ilma selleta**: `modprobe btrfs` ebaõnnestub teatega "Module btrfs not found" ja `dnf search btrfs` ei tagasta midagi. Rocky Linux 10 ja AlmaLinux 10 pärivad sama kerneli ja seetõttu ei saa töötada Rediacci serveritena.

Oracle Linux 10 kasutab vaikimisi **Unbreakable Enterprise Kernel (UEK)**, mis hoiab btrfs-i sisseehitatuna. See on ainus RHEL-ühilduv sihtmärk toetatud loendis. Kui peate käitama RHEL-perekonna serverit, kasutage Oracle Linux 10 koos UEK-iga. (Selle otsuse tõde elab `.github/workflows/ct-tests.yml`-s CI Bridge Workers maatriksina.)

#### Ainult tööjaam (CLI installimise sihtmärgid)

`rdc` CLI installitakse samuti puhtalt Alpine 3.19+-le (APK koos `gcompat` ühilduvuskihiga, installitakse automaatselt) ja Arch Linuxile (jooksev, pacmani kaudu). Need on ainult klientpoolsed installimisteed (vaadake [Installimine](/en/docs/installation)) ja neid ei toetata `renet` serveri sihtmärkidena.

### Turvapoliitikad OS-i kaupa

Repositooriumipõhine Dockeri deemon ja repositooriumi konteinerid ise töötavad **vaikimisi konteinerisiltidega** kõigil toetatud OS-del. `rdc config machine setup` ei installi kohandatud SELinuxi poliitikaid ega AppArmori profiile. Käitumine OS-i kaupa:

- **Ubuntu 24.04, openSUSE Leap 16.0**: AppArmor on vaikimisi lubatud. Rakendub vaikimisi docker-container profiil; lisaseadistust ei nõuta.
- **Fedora 43, Oracle Linux 10**: SELinux töötab jõustataval režiimil. Repositooriumipõhine deemon märgistab konteinerid standardse `container_t` kontekstiga. Kohandatud SELinuxi poliitika pole vajalik.
- **CRIU** (kontrollpunkt/taastamine) on ainuke juhtum, mis möödub AppArmori profiilist koos `apparmor=unconfined`-ga, kuna ülalvoolne CRIU AppArmori tugi pole veel stabiilne. Vaadake CRIU märkusi [Rediacci reeglites](/en/docs/rules-of-rediacc).

Kui seadistamise samm ebaõnnestub SELinuxi AVC-keeldumiste või AppArmori tagasilükkamistega, vaadake [Tõrkeotsing](/en/docs/troubleshooting) → Distributsioonipõhised seadistusprobleemid.

### Serveri eeltingimused

- Kasutajakonto `sudo` õigustega (paroolita sudo on soovitatav)
- Teie SSH avalik võti lisatud `~/.ssh/authorized_keys`-sse
- Vähemalt 20 GB vaba kettaruumi (rohkem sõltuvalt töökoormusest)
- Interneti juurdepääs Dockeri piltide tõmbamiseks (või privaatne register)

### Installitakse automaatselt

`rdc config machine setup` käsk installib kaugserverile järgmised:

- **Docker** ja **containerd** (konteineri käitusaeg)
- **cryptsetup** (LUKS-ketta krüpteerimine)
- **renet** binaarne (üles laaditud SFTP kaudu)

Te ei pea neid käsitsi installima.

## Kohalikud virtuaalmasinad (valikuline)

Kui soovite juurutusi kohalikult testida kasutades `rdc ops`, vajab teie tööjaam virtualiseerimise tuge: KVM Linuxil või QEMU macOS-il. Vaadake seadistusetappide ja platvormi üksikasjade jaoks [Eksperimentaalsete VM-ide](/en/docs/experimental-vms) juhendit.
