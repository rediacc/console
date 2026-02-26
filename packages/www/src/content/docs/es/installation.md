---
title: "Instalación"
description: "Instale la CLI de Rediacc en Linux, macOS o Windows."
category: "Guides"
order: 1
language: es
sourceHash: "2cb00a8aeec6988c"
---

# Instalación

Instale la CLI `rdc` en su estación de trabajo. Esta es la única herramienta que necesita instalar manualmente -- todo lo demás se gestiona automáticamente cuando configura las máquinas remotas.

## Linux y macOS

Ejecute el script de instalación:

```bash
curl -fsSL https://get.rediacc.com | sh
```

Esto descarga el binario `rdc` en `$HOME/.local/bin/`. Asegúrese de que este directorio esté en su PATH:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

Agregue esta línea a su perfil de shell (`~/.bashrc`, `~/.zshrc`, etc.) para hacerla permanente.

## Windows

Ejecute el script de instalación en PowerShell:

```powershell
irm https://www.rediacc.com/install.ps1 | iex
```

Esto descarga el binario `rdc.exe` en `%LOCALAPPDATA%\rediacc\bin\`. Asegúrese de que este directorio esté en su PATH. El instalador le pedirá que lo agregue si aún no está presente.

## Alpine Linux (APK)

```bash
# Add the repository
echo "https://www.rediacc.com/apk/x86_64" | sudo tee -a /etc/apk/repositories

# Install
sudo apk update
sudo apk add --allow-untrusted rediacc-cli
```

Nota: El paquete `gcompat` (capa de compatibilidad glibc) se instala automáticamente como dependencia.

## Arch Linux (Pacman)

```bash
# Add the repository to /etc/pacman.conf
echo "[rediacc]
SigLevel = Optional TrustAll
Server = https://www.rediacc.com/archlinux/\$arch" | sudo tee -a /etc/pacman.conf

# Install
sudo pacman -Sy rediacc-cli
```

## Verificar la Instalación

```bash
rdc --version
```

Debería ver el número de versión instalado.

## Actualizar

Para actualizar `rdc` a la última versión:

```bash
rdc update
```

Para buscar actualizaciones sin instalar:

```bash
rdc update --check-only
```

Para revertir a la versión anterior después de una actualización:

```bash
rdc update rollback
```

### Remote Binary Updates

When you run commands against a remote machine, the CLI automatically provisions the matching `renet` binary. If the binary is updated, the route server (`rediacc-router`) is restarted automatically so it picks up the new version.

The restart is transparent and causes **no downtime**:

- The route server restarts in ~1–2 seconds.
- During that window, Traefik continues serving traffic using its last known routing configuration. No routes are dropped.
- Traefik picks up the new configuration on its next poll cycle (within 5 seconds).
- **Existing client connections (HTTP, TCP, UDP) are not affected.** The route server is a configuration provider — it is not in the data path. Traefik handles all traffic directly.
- Your application containers are not touched — only the system-level route server process is restarted.

To skip the automatic restart, pass `--skip-router-restart` to any command, or set the `RDC_SKIP_ROUTER_RESTART=1` environment variable.
