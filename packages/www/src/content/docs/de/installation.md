---
title: "Installation"
description: "Installieren Sie die Rediacc-CLI unter Linux, macOS oder Windows."
category: "Guides"
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

## Windows

Führen Sie das Installationsskript in PowerShell aus:

```powershell
irm https://www.rediacc.com/install.ps1 | iex
```

Dies lädt die `rdc.exe`-Datei nach `%LOCALAPPDATA%\rediacc\bin\` herunter. Stellen Sie sicher, dass dieses Verzeichnis in Ihrem PATH enthalten ist. Das Installationsprogramm fordert Sie auf, es hinzuzufügen, falls es noch nicht vorhanden ist.

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
