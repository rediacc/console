---
title: "Installation"
description: "Installieren Sie die Rediacc CLI unter Linux, macOS oder Windows."
category: "Guides"
order: 1
language: de
---

# Installation

Installieren Sie die `rdc` CLI auf Ihrer Arbeitsstation. Dies ist das einzige Tool, das Sie manuell installieren muessen -- alles andere wird automatisch erledigt, wenn Sie Remote-Maschinen einrichten.

## Schnellinstallation

### Linux und macOS

```bash
curl -fsSL https://www.rediacc.com/install.sh | bash
```

Dieser Befehl laedt die `rdc`-Binaerdatei nach `$HOME/.local/bin/` herunter. Stellen Sie sicher, dass dieses Verzeichnis in Ihrem PATH enthalten ist:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

Fuegen Sie diese Zeile zu Ihrem Shell-Profil (`~/.bashrc`, `~/.zshrc`, usw.) hinzu, um sie dauerhaft zu machen.

### Windows

Fuehren Sie dies in PowerShell aus:

```powershell
irm https://www.rediacc.com/install.ps1 | iex
```

Dieser Befehl laedt `rdc.exe` nach `%LOCALAPPDATA%\rediacc\bin\` herunter. Das Installationsprogramm fordert Sie auf, es bei Bedarf zu Ihrem PATH hinzuzufuegen.

## Paketmanager

### APT (Debian / Ubuntu)

```bash
curl -fsSL https://releases.rediacc.com/apt/stable/gpg.key | sudo gpg --dearmor -o /usr/share/keyrings/rediacc.gpg
echo "deb [signed-by=/usr/share/keyrings/rediacc.gpg] https://releases.rediacc.com/apt/stable stable main" | sudo tee /etc/apt/sources.list.d/rediacc.list
sudo apt-get update && sudo apt-get install rediacc-cli
```

### DNF (Fedora / RHEL)

```bash
sudo curl -fsSL https://releases.rediacc.com/rpm/stable/rediacc.repo -o /etc/yum.repos.d/rediacc.repo
sudo dnf install rediacc-cli
```

### APK (Alpine Linux)

```bash
echo "https://releases.rediacc.com/apk/stable" | sudo tee -a /etc/apk/repositories
sudo apk update
sudo apk add --allow-untrusted rediacc-cli
```

Hinweis: Das Paket `gcompat` (glibc-Kompatibilitaetsschicht) wird automatisch als Abhaengigkeit installiert.

### Pacman (Arch Linux)

```bash
echo "[rediacc]
SigLevel = Optional TrustAll
Server = https://releases.rediacc.com/archlinux/stable/\$arch" | sudo tee -a /etc/pacman.conf

sudo pacman -Sy rediacc-cli
```

## Docker

Ziehen und starten Sie die CLI als Container:

```bash
docker pull ghcr.io/rediacc/elite/cli:stable

docker run --rm ghcr.io/rediacc/elite/cli:stable --version
```

Erstellen Sie einen Alias zur Vereinfachung:

```bash
alias rdc='docker run --rm -it -v $(pwd):/workspace ghcr.io/rediacc/elite/cli:stable'
```

Verfuegbare Docker-Tags:

| Tag | Beschreibung |
|-----|-------------|
| `:stable` | Neuestes stabiles Release (empfohlen) |
| `:edge` | Neuestes Edge-Release |
| `:0.8.4` | Fixierte Version (unveraenderlich) |
| `:latest` | Alias fuer `:stable` |

## Installation ueberpruefen

```bash
rdc --version
```

## Aktualisierung

Auf die neueste Version aktualisieren:

```bash
rdc update
```

Nach Updates suchen, ohne zu installieren:

```bash
rdc update --check-only
```

Aktuellen Update-Status anzeigen:

```bash
rdc update --status
```

Auf die vorherige Version zuruecksetzen:

```bash
rdc update rollback
```

## Release-Kanaele

Rediacc verwendet ein kanalbasiertes Release-System. Der Kanal bestimmt, welche Version Sie bei CLI-Updates, Paketmanager-Installationen und Docker-Pulls erhalten.

| Kanal | Beschreibung | Wann aktualisiert |
|-------|-------------|-------------------|
| `stable` | Produktionsreife Releases | Nach 7-taegiger Testphase von Edge uebernommen |
| `edge` | Neueste Funktionen und Fehlerbehebungen | Bei jedem Merge in Main |
| `pr-N` | PR-Vorschau-Builds | Automatisch pro Pull Request |

### Kanal wechseln

```bash
rdc update --channel edge      # Zum Edge-Kanal wechseln
rdc update --channel stable    # Zurueck zum Stable-Kanal
```

Direkt vom Edge-Kanal installieren:

```bash
REDIACC_CHANNEL=edge curl -fsSL https://www.rediacc.com/install.sh | bash
```

Fuer Paketmanager ersetzen Sie `stable` durch `edge` in der Repository-URL:

```bash
# APT edge
echo "deb [signed-by=/usr/share/keyrings/rediacc.gpg] https://releases.rediacc.com/apt/edge stable main" | sudo tee /etc/apt/sources.list.d/rediacc.list

# Docker edge
docker pull ghcr.io/rediacc/elite/cli:edge
```

### Wie Kanaele funktionieren

Der Kanal gilt einheitlich fuer alle Bereitstellungsmethoden:

- **Installationsskripte**: Die Umgebungsvariable `REDIACC_CHANNEL` waehlt den Kanal
- **Paket-Repositories**: `releases.rediacc.com/{format}/{kanal}/`
- **Docker-Tags**: `ghcr.io/rediacc/elite/cli:{kanal}`
- **CLI-Updates**: `rdc update` prueft den bei der Installation konfigurierten Kanal

### Automatische PR-Vorschau-Konfiguration

Wenn Sie von einer PR-Vorschau-Bereitstellung (z.B. `pr-420.rediacc.workers.dev`) installieren, werden Kanal und Account-Server automatisch konfiguriert:

- Die CLI-Binaerdatei wird vom Kanal `pr-420` heruntergeladen
- `rdc update` prueft den Kanal `pr-420` auf Updates
- Alle Account-/Abonnement-Befehle verbinden sich mit dem PR-Vorschau-Server
- Docker-Befehle auf der Vorschau-Seite zeigen `cli:pr-420`

Keine manuelle Konfiguration erforderlich. Das Installationsskript erkennt den Bereitstellungskontext anhand der URL.

## Remote-Binaer-Updates

Wenn Sie Befehle gegen eine Remote-Maschine ausfuehren, stellt die CLI automatisch die passende `renet`-Binaerdatei bereit. Wenn die Binaerdatei aktualisiert wird, wird der Route-Server (`rediacc-router`) automatisch neu gestartet, damit er die neue Version uebernimmt.

Der Neustart ist transparent und verursacht **keine Ausfallzeit**:

- Der Route-Server startet in ~1-2 Sekunden neu.
- Waehrend dieses Zeitfensters bedient Traefik den Datenverkehr mit seiner zuletzt bekannten Routing-Konfiguration weiter. Keine Routen gehen verloren.
- Traefik uebernimmt die neue Konfiguration beim naechsten Abfragezyklus (innerhalb von 5 Sekunden).
- **Bestehende Client-Verbindungen (HTTP, TCP, UDP) sind nicht betroffen.** Der Route-Server ist ein Konfigurationsanbieter -- er befindet sich nicht im Datenpfad. Traefik verarbeitet den gesamten Datenverkehr direkt.
- Ihre Anwendungscontainer werden nicht beruehrt -- nur der Route-Server-Prozess auf Systemebene wird neu gestartet.

Um den automatischen Neustart zu ueberspringen, uebergeben Sie `--skip-router-restart` an einen beliebigen Befehl oder setzen Sie die Umgebungsvariable `RDC_SKIP_ROUTER_RESTART=1`.
