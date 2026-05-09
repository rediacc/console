---
title: "Eksperimentaalsed VM-id ülevaade"
description: "Valmistage ette kohalikud VM-klastrid arenduseks ja testimiseks rdc ops abil ühe käsuga."
category: "Concepts"
order: 2
language: et
---

# Eksperimentaalsed VM-id

Valmistage ette kohalikud VM-klastrid oma tööjaamas arenduseks ja testimiseks, ilma väliste pilveteenuse pakkujateta.

## Nõuded

`rdc ops` nõuab **kohalikku adapterit**. See ei ole pilvadapteriga saadaval.

```bash
rdc ops check
```

## Ülevaade

`rdc ops` käsud võimaldavad teil luua ja hallata eksperimentaalseid VM-klastreid kohapeal. See on sama infrastruktuur, mida CI konveier kasutab integratsioonitestide jaoks, nüüd saadaval praktiliseks katsetamiseks.

Kasutusjuhtumid:
- Rediacci juurutuste testimine ilma väliste VM-teenuse pakkujateta (Linode, Vultr jne)
- Hoidlakonfiguratsioonide arendamine ja silumine kohapeal
- Platvormi õppimine täielikult isoleeritud keskkonnas
- Integratsioonitestide käitamine oma tööjaamas

## Platvormide tugi

| Platvorm | Arhitektuur | Taustarakendus | Olek |
|----------|-------------|---------|--------|
| Linux | x86_64 | KVM (libvirt) | Testitud CI-s |
| macOS | Intel | QEMU + HVF | Testitud CI-s |
| Linux | ARM64 | KVM (libvirt) | Toetatud (CI-s testimata) |
| macOS | ARM (Apple Silicon) | QEMU + HVF | Toetatud (CI-s testimata) |
| Windows | x86_64 / ARM64 | Hyper-V | Kavandatud |

**Linux (KVM)** kasutab libvirti natiivseks riistvara virtualiseerimiseks sillatud võrgustikuga.

**macOS (QEMU)** kasutab QEMU-t koos Apple'i hüpervisori raamistikuga (HVF) natiivse jõudlusele lähedase töö jaoks, kasutajarežiimi võrgustiku ja SSH-pordi suunamisega.

**Windowsi (Hyper-V)** tugi on kavandatud. Vaadake üksikasju [probleem #380](https://github.com/rediacc/console/issues/380). Nõuab Windows Pro/Enterprise.

## Eeltingimused ja seadistamine

### Linux

```bash
# Installi eeltingimused automaatselt
rdc ops setup

# Või käsitsi:
sudo apt install libvirt-daemon-system virtinst qemu-utils cloud-image-utils docker.io
sudo systemctl enable --now libvirtd
```

### macOS

```bash
# Installi eeltingimused automaatselt
rdc ops setup

# Või käsitsi:
brew install qemu cdrtools
```

### Kontrolli seadistust

```bash
rdc ops check
```

See käivitab platvormispetsiifilised kontrollid ja teatab iga eeltingimuse läbimisest/ebaõnnestumisest.

## Kiirstart

```bash
# 1. Kontrolli eeltingimusi
rdc ops check

# 2. Valmista ette minimaalne klaster (sild + 1 töötaja)
rdc ops up --basic

# 3. Kontrolli VM-i olekut
rdc ops status

# 4. SSH silla VM-i
rdc ops ssh --vm-id 1

# 4b. Või käivita käsk otse
rdc ops ssh --vm-id 1 -c hostname

# 5. Lammuta
rdc ops down
```

## Klastri koosseis

Vaikimisi valmistab `rdc ops up` ette:

| VM | ID | Roll |
|----|-----|------|
| Sild | 1 | Peamine sõlm, käitab Rediacci sillateenus |
| Töötaja 1 | 11 | Töötajasõlm hoidlate juurutuste jaoks |
| Töötaja 2 | 12 | Töötajasõlm hoidlate juurutuste jaoks |

Kasutage `--basic` lippu, et valmistada ette ainult sild ja esimene töötaja (ID-d 1 ja 11).

Kasutage `--skip-orchestration`, et valmistada ette VM-id ilma Rediacci teenuseid käivitamata, mis on kasulik VM-kihi isoleeritud testimiseks.

## Konfiguratsioon

Silla VM kasutab väiksemaid vaikeväärtusi kui töötaja VM-id:

| VM roll | CPU-d | RAM | Ketas |
|---------|------|-----|------|
| Sild | 1 | 1024 MB | 8 GB |
| Töötaja | 2 | 4096 MB | 16 GB |

Keskkonna muutujad kirjutavad töötaja VM-i ressursid üle:

| Muutuja | Vaikeväärtus | Kirjeldus |
|----------|---------|-------------|
| `VM_CPU` | 2 | CPU tuumad töötaja VM kohta |
| `VM_RAM` | 4096 | RAM MB-des töötaja VM kohta |
| `VM_DSK` | 16 | Ketta suurus GB-des töötaja VM kohta |
| `VM_NET_BASE` | 192.168.111 | Võrgu alus (ainult KVM) |
| `RENET_DATA_DIR` | ~/.renet | VM-ketaste ja konfiguratsiooni andmekataloog |

## Käsuviide

| Käsk | Kirjeldus |
|---------|-------------|
| `rdc ops setup` | Installi platvormieeltingimused (KVM või QEMU) |
| `rdc ops check` | Kontrolli, kas eeltingimused on installitud ja töötavad |
| `rdc ops up [options]` | Valmista ette VM-klaster |
| `rdc ops down` | Hävita kõik VM-id ja puhasta |
| `rdc ops status` | Näita kõigi VM-ide olekut |
| `rdc ops ssh --vm-id <id> [command...]` | SSH VM-i või käivita sellel käsk |

### `rdc ops up` valikud

| Valik | Kirjeldus |
|--------|-------------|
| `--basic` | Minimaalne klaster (sild + 1 töötaja) |
| `--lite` | Jäta VM-i ettevalmistamine vahele (ainult SSH-võtmed) |
| `--force` | Sundige olemasolevate VM-ide taasloomisel |
| `--parallel` | Valmistage VM-id ette paralleelselt |
| `--skip-orchestration` | Ainult VM-id, Rediacci teenuseid ei käivitata |
| `--backend <kvm\|qemu>` | Kirjutage automaatselt tuvastatud taustarakendus üle |
| `--os <name>` | OS-i kujutis (vaikimisi: ubuntu-24.04) |
| `--debug` | Detailne väljund |

## Platvormide erinevused

### Linux (KVM)
- Kasutab libvirti VM-i elutsükli haldamiseks
- Sillatud võrgustik, VM-id saavad IP-aadresse virtuaalvõrgus (192.168.111.x)
- Otsene SSH VM-i IP-aadressidele
- Nõuab `/dev/kvm` ja libvirtd teenust

### macOS (QEMU + HVF)
- Kasutab PID-failide kaudu hallatud QEMU protsesse
- Kasutajarežiimi võrgustik SSH-pordi suunamisega (localhost:222XX)
- SSH suunatud portide kaudu, mitte otseste IP-aadresside kaudu
- Cloud-init ISO-d loodud `mkisofs` abil

## Tõrkeotsing

### Silumisrežiim

Lisage `--debug` mis tahes käsule detailse väljundi saamiseks:

```bash
rdc ops up --basic --debug
```

### Levinud probleemid

**KVM pole saadaval (Linux)**
- Kontrollige, kas `/dev/kvm` eksisteerib: `ls -la /dev/kvm`
- Lubage virtualiseerimise BIOS/UEFI-s
- Laadige tuuma moodul: `sudo modprobe kvm_intel` või `sudo modprobe kvm_amd`

**libvirtd ei tööta (Linux)**
```bash
sudo systemctl enable --now libvirtd
```

**QEMU ei leita (macOS)**
```bash
brew install qemu cdrtools
```

**VM-id ei käivitu**
- Kontrollige kettaruumi `~/.renet/disks/` kaustas
- Käitage `rdc ops check`, et kontrollida kõiki eeltingimusi
- Proovige `rdc ops down` seejärel `rdc ops up --force`
