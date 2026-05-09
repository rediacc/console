---
title: "Installimine"
description: "Installige Rediacci CLI Linuxi, macOS-i või Windowsi."
category: "Guides"
order: 1
language: et
---

# Installimine

Installige `rdc` CLI oma tööjaamas. See on ainus tööriist, mille peate käsitsi installima -- kõik muu hallatakse automaatselt, kui seadistate kaugmasinaid.

## Kiirintall

### Linux ja macOS

```bash
curl -fsSL https://www.rediacc.com/install.sh | bash
```

See laadib `rdc` binaari alla asukohta `$HOME/.local/bin/`. Veenduge, et see kataloog oleks teie PATH-is:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

Lisage see rida oma shelli profiili (`~/.bashrc`, `~/.zshrc` jne), et muuta see püsivaks.

### Windows

Käivitage PowerShellis:

```powershell
irm https://www.rediacc.com/install.ps1 | iex
```

See laadib `rdc.exe` alla asukohta `%LOCALAPPDATA%\rediacc\bin\`. Installer küsib, kas lisada see PATH-i, kui vajalik.

## Paketihaldid

### APT (Debian / Ubuntu)

```bash
curl -fsSL https://releases.rediacc.com/apt/stable/gpg.key | sudo gpg --dearmor -o /usr/share/keyrings/rediacc.gpg
echo "deb [signed-by=/usr/share/keyrings/rediacc.gpg] https://releases.rediacc.com/apt/stable stable main" | sudo tee /etc/apt/sources.list.d/rediacc.list
sudo apt-get update && sudo apt-get install rediacc-cli
```

### DNF (Fedora / RHEL-ühilduv)

```bash
sudo curl -fsSL https://releases.rediacc.com/rpm/stable/rediacc.repo -o /etc/yum.repos.d/rediacc.repo
sudo dnf install rediacc-cli
```

Oracle Linux, AlmaLinux ja Rocky Linux kasutavad kõik sama DNF protsessi; mis tahes RHEL-ühilduv distributsioon koos `dnf`-iga saab ülaltoodud hoidla tõmmata. Märkus: **Oracle Linux 10 on ainus RHEL-perekonna distributsioon, mis on Rediacci serveri sihtmärgina ametlikult toetatud** (vaadake [Nõuded](/et/docs/requirements)). Rocky/Alma 10-l puudub renet andmetasandi jaoks vajalik btrfs-tuuma moodul, kuigi `rdc` CLI installub neile hästi.

### Zypper (openSUSE Leap)

```bash
sudo zypper addrepo https://releases.rediacc.com/rpm/stable/rediacc.repo
sudo zypper --gpg-auto-import-keys refresh
sudo zypper install rediacc-cli
```

Testitud openSUSE Leap 16.0+ versiooniga.

### APK (Alpine Linux)

```bash
echo "https://releases.rediacc.com/apk/stable" | sudo tee -a /etc/apk/repositories
sudo apk update
sudo apk add --allow-untrusted rediacc-cli
```

Märkus: `gcompat` pakett (glibc ühilduvuskiht) installitakse automaatselt sõltuvusena.

### Pacman (Arch Linux)

```bash
echo "[rediacc]
SigLevel = Optional TrustAll
Server = https://releases.rediacc.com/archlinux/stable/\$arch" | sudo tee -a /etc/pacman.conf

sudo pacman -Sy rediacc-cli
```

### npm (Node.js)

```bash
npm install -g https://releases.rediacc.com/npm/stable/rediacc-cli-latest.tgz
```

Nõuab Node.js 22 või uuema versiooni. Konkreetse versiooni installimiseks:

```bash
npm install -g https://releases.rediacc.com/npm/stable/rediacc-cli-0.8.5.tgz
```

## Docker

Tõmmake ja käivitage CLI konteinerina:

```bash
docker pull ghcr.io/rediacc/elite/cli:stable

docker run --rm ghcr.io/rediacc/elite/cli:stable --version
```

Looge alias mugavuse huvides:

```bash
alias rdc='docker run --rm -it -v $(pwd):/workspace ghcr.io/rediacc/elite/cli:stable'
```

Saadaolevad Docker sildid:

| Silt | Kirjeldus |
|-----|-------------|
| `:stable` | Viimane stabiilne väljalase (soovitatav) |
| `:edge` | Viimane edge väljalase |
| `:0.8.4` | Fikseeritud versioon (muutumatu) |
| `:latest` | `:stable` alias |

## Installimise kontrollimine

```bash
rdc --version
```

## Uuendamine

Uuendage uusimale versioonile:

```bash
rdc update
```

Kontrollige uuendusi ilma installimiseta:

```bash
rdc update --check-only
```

Vaadake praegust uuenduse olekut:

```bash
rdc update --status
```

Tagasipöördumine eelmisele versioonile:

```bash
rdc update --rollback
```

## Väljalasekanalid

Rediacc kasutab kanalipõhist väljalasesüsteemi. Kanal määrab, millise versiooni saate CLI uuenduste, paketihalduri installide ja Docker tõmmiste jaoks.

| Kanal | Kirjeldus | Millal uuendatakse |
|---------|-------------|--------------|
| `stable` | Tootmine, edendatud edge'ist pärast 7-päevast leotamist | Iganädalane leotamisedendus |
| `edge` | Pidevalt juurutatud tootmine | Iga ühendamine main-harusse |
| `pr-N` | PR eelvaate koostamised | Automaatselt iga pull-requesti kohta |

### Kanalite vahetamine

```bash
rdc update --channel edge      # Lülitu edge kanalile
rdc update --channel stable    # Lülitu tagasi stable kanalile
```

Installige otse edge kanalist:

```bash
REDIACC_CHANNEL=edge curl -fsSL https://www.rediacc.com/install.sh | bash
```

Pakethaldite puhul asendage hoidla URL-is `stable` sõnaga `edge`:

```bash
# APT edge
echo "deb [signed-by=/usr/share/keyrings/rediacc.gpg] https://releases.rediacc.com/apt/edge stable main" | sudo tee /etc/apt/sources.list.d/rediacc.list

# Docker edge
docker pull ghcr.io/rediacc/elite/cli:edge
```

### Kuidas kanalid töötavad

Kanal rakendub ühtlaselt kõigi tarnimismeetodite lõikes:

- **Installiskriptid**: `REDIACC_CHANNEL` keskkonna muutuja valib kanali
- **Pakettide hoidlad**: `releases.rediacc.com/{format}/{channel}/`
- **Docker sildid**: `ghcr.io/rediacc/elite/cli:{channel}`
- **CLI uuendused**: `rdc update` kontrollib installimise ajal konfigureeritud kanalit

### PR eelvaate automaatkonfiguratsioon

Kui installite PR eelvaate juurutusest (nt `pr-420.rediacc.workers.dev`), konfigureeritakse kanal ja konto server automaatselt:

- CLI binaer laaditakse alla `pr-420` kanalist
- `rdc update` kontrollib uuendusi `pr-420` kanalist
- Kõik konto/tellimuse käsud ühenduvad PR eelvaate serveriga
- Docker käsud eelvaate saidil näitavad `cli:pr-420`

Käsitsi konfiguratsiooni pole vaja. Installiskript tuvastab juurutamise konteksti URL-ist.

## Kaugbinaari uuendused

Kui käivitate käske kaugmasina vastu, valmistab CLI automaatselt ette sobiva `renet` binaarid. Kui binaari uuendatakse, taaskäivitub marsruudi server (`rediacc-router`) automaatselt, et saada uus versioon.

Taaskäivitamine on läbipaistev ja ei põhjusta **seisakut**:

- Marsruudi server taaskäivitub umbes 1-2 sekundiga.
- Selle akna ajal jätkab Traefik liikluse teenindamist, kasutades oma viimast teadaolevat marsruutimiskonfiguratsiooni. Ühtegi marsruuti ei kaotata.
- Traefik võtab uue konfiguratsiooni järgmisel küsimistsüklil (5 sekundi jooksul).
- **Olemasolevaid klientühendusi (HTTP, TCP, UDP) ei mõjutata.** Marsruudi server on konfiguratsiooni pakkuja -- see ei ole andmeteel. Traefik haldab kogu liiklust otse.
- Teie rakenduse konteinereid ei puututa -- taaskäivitatakse ainult süsteemitaseme marsruudi serveri protsess.

Automaatse taaskäivitamise vahelejätmiseks edastage mis tahes käsule `--skip-router-restart` või seadistage keskkonna muutuja `RDC_SKIP_ROUTER_RESTART=1`.
