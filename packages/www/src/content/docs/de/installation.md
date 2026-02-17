---
title: "Installation"
description: "Installieren Sie die Rediacc-CLI unter Linux, macOS oder Windows."
category: "Getting Started"
order: 1
language: de
---

# Installation

Installieren Sie die `rdc`-CLI auf Ihrer Workstation. Dies ist das einzige Tool, das Sie manuell installieren müssen -- alles andere wird automatisch erledigt, wenn Sie entfernte Maschinen einrichten.

## Linux und macOS

Führen Sie das Installationsskript aus:

```bash
curl -fsSL https://get.rediacc.com | sh
```

Dies lädt die `rdc`-Binary nach `$HOME/.local/bin/` herunter. Stellen Sie sicher, dass dieses Verzeichnis in Ihrem PATH enthalten ist:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

Fügen Sie diese Zeile Ihrem Shell-Profil (`~/.bashrc`, `~/.zshrc` usw.) hinzu, um sie dauerhaft zu machen.

## Windows (WSL2)

Rediacc läuft innerhalb von WSL2 unter Windows. Falls Sie WSL2 noch nicht eingerichtet haben:

```powershell
wsl --install
```

Führen Sie dann innerhalb Ihrer WSL2-Linux-Distribution dasselbe Installationsskript aus:

```bash
curl -fsSL https://get.rediacc.com | sh
```

## Installation überprüfen

```bash
rdc --version
```

Sie sollten die installierte Versionsnummer sehen.

## Aktualisieren

Um `rdc` auf die neueste Version zu aktualisieren:

```bash
rdc update
```

Um nach Updates zu suchen, ohne sie zu installieren:

```bash
rdc update --check-only
```

Um nach einem Update zur vorherigen Version zurückzukehren:

```bash
rdc update rollback
```
