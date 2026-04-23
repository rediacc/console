---
title: "Instalación"
description: "Instale la CLI de Rediacc en Linux, macOS o Windows."
category: "Guides"
order: 1
language: es
sourceHash: "5bdc0ff205ae9c73"
sourceCommit: "407174f41c12c0a2ee252a7812290c1ef9ecc9ca"
---

# Instalación

Instale la CLI `rdc` en su estación de trabajo. Esta es la única herramienta que necesita instalar manualmente -- todo lo demás se gestiona automáticamente cuando configura máquinas remotas.

## Instalación rápida

### Linux y macOS

```bash
curl -fsSL https://www.rediacc.com/install.sh | bash
```

Esto descarga el binario `rdc` en `$HOME/.local/bin/`. Asegúrese de que este directorio esté en su PATH:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

Añada esta línea a su perfil de shell (`~/.bashrc`, `~/.zshrc`, etc.) para hacerlo permanente.

### Windows

Ejecute en PowerShell:

```powershell
irm https://www.rediacc.com/install.ps1 | iex
```

Esto descarga `rdc.exe` en `%LOCALAPPDATA%\rediacc\bin\`. El instalador le pedirá que lo añada a su PATH si es necesario.

## Gestores de paquetes

### APT (Debian / Ubuntu)

```bash
curl -fsSL https://releases.rediacc.com/apt/stable/gpg.key | sudo gpg --dearmor -o /usr/share/keyrings/rediacc.gpg
echo "deb [signed-by=/usr/share/keyrings/rediacc.gpg] https://releases.rediacc.com/apt/stable stable main" | sudo tee /etc/apt/sources.list.d/rediacc.list
sudo apt-get update && sudo apt-get install rediacc-cli
```

### DNF (Fedora / compatible con RHEL)

```bash
sudo curl -fsSL https://releases.rediacc.com/rpm/stable/rediacc.repo -o /etc/yum.repos.d/rediacc.repo
sudo dnf install rediacc-cli
```

Oracle Linux, AlmaLinux y Rocky Linux utilizan el mismo flujo DNF; cualquier distribución compatible con RHEL que tenga `dnf` puede añadir el repositorio anterior. Nota: **Oracle Linux 10 es la única distribución de la familia RHEL oficialmente compatible como destino de servidor Rediacc** (consulte [Requisitos](/en/docs/requirements)). Rocky/Alma 10 carecen del módulo de kernel btrfs necesario para el plano de datos de renet, aunque la CLI `rdc` se instala en ellas correctamente.

### Zypper (openSUSE Leap)

```bash
sudo zypper addrepo https://releases.rediacc.com/rpm/stable/rediacc.repo
sudo zypper --gpg-auto-import-keys refresh
sudo zypper install rediacc-cli
```

Probado en openSUSE Leap 16.0+.

### APK (Alpine Linux)

```bash
echo "https://releases.rediacc.com/apk/stable" | sudo tee -a /etc/apk/repositories
sudo apk update
sudo apk add --allow-untrusted rediacc-cli
```

Nota: El paquete `gcompat` (capa de compatibilidad con glibc) se instala automáticamente como dependencia.

### Pacman (Arch Linux)

```bash
echo "[rediacc]
SigLevel = Optional TrustAll
Server = https://releases.rediacc.com/archlinux/stable/\$arch" | sudo tee -a /etc/pacman.conf

sudo pacman -Sy rediacc-cli
```

## Docker

Descargue y ejecute la CLI como contenedor:

```bash
docker pull ghcr.io/rediacc/elite/cli:stable

docker run --rm ghcr.io/rediacc/elite/cli:stable --version
```

Cree un alias para mayor comodidad:

```bash
alias rdc='docker run --rm -it -v $(pwd):/workspace ghcr.io/rediacc/elite/cli:stable'
```

Etiquetas de Docker disponibles:

| Etiqueta | Descripción |
|----------|-------------|
| `:stable` | Última versión estable (recomendada) |
| `:edge` | Última versión edge |
| `:0.8.4` | Versión fijada (inmutable) |
| `:latest` | Alias de `:stable` |

## Verificar la instalación

```bash
rdc --version
```

## Actualización

Actualizar a la última versión:

```bash
rdc update
```

Comprobar actualizaciones sin instalar:

```bash
rdc update --check-only
```

Ver el estado actual de actualización:

```bash
rdc update --status
```

Revertir a la versión anterior:

```bash
rdc update --rollback
```

## Canales de lanzamiento

Rediacc utiliza un sistema de lanzamiento basado en canales. El canal determina qué versión recibe para las actualizaciones de CLI, instalaciones de gestores de paquetes y descargas de Docker.

| Canal | Descripción | Cuándo se actualiza |
|-------|-------------|---------------------|
| `stable` | Versiones listas para producción | Promovida desde edge tras 7 días de prueba |
| `edge` | Últimas características y correcciones | En cada merge a main |
| `pr-N` | Compilaciones de vista previa de PR | Automáticamente por pull request |

### Cambiar de canal

```bash
rdc update --channel edge      # Cambiar al canal edge
rdc update --channel stable    # Volver al canal stable
```

Instalar directamente desde el canal edge:

```bash
REDIACC_CHANNEL=edge curl -fsSL https://www.rediacc.com/install.sh | bash
```

Para gestores de paquetes, reemplace `stable` por `edge` en la URL del repositorio:

```bash
# APT edge
echo "deb [signed-by=/usr/share/keyrings/rediacc.gpg] https://releases.rediacc.com/apt/edge stable main" | sudo tee /etc/apt/sources.list.d/rediacc.list

# Docker edge
docker pull ghcr.io/rediacc/elite/cli:edge
```

### Cómo funcionan los canales

El canal se aplica de manera uniforme en todos los métodos de distribución:

- **Scripts de instalación**: La variable de entorno `REDIACC_CHANNEL` selecciona el canal
- **Repositorios de paquetes**: `releases.rediacc.com/{formato}/{canal}/`
- **Etiquetas de Docker**: `ghcr.io/rediacc/elite/cli:{canal}`
- **Actualizaciones de CLI**: `rdc update` verifica el canal configurado durante la instalación

### Configuración automática de vista previa de PR

Cuando instala desde un despliegue de vista previa de PR (por ejemplo, `pr-420.rediacc.workers.dev`), el canal y el servidor de cuenta se configuran automáticamente:

- El binario de CLI se descarga del canal `pr-420`
- `rdc update` verifica el canal `pr-420` para actualizaciones
- Todos los comandos de cuenta/suscripción se conectan al servidor de vista previa de PR
- Los comandos de Docker en el sitio de vista previa muestran `cli:pr-420`

No se necesita configuración manual. El script de instalación detecta el contexto de despliegue a partir de la URL.

## Actualizaciones de binarios remotos

Cuando ejecuta comandos contra una máquina remota, la CLI aprovisiona automáticamente el binario `renet` correspondiente. Si el binario se actualiza, el servidor de rutas (`rediacc-router`) se reinicia automáticamente para que adopte la nueva versión.

El reinicio es transparente y no causa **ningún tiempo de inactividad**:

- El servidor de rutas se reinicia en ~1-2 segundos.
- Durante esa ventana, Traefik continúa sirviendo tráfico usando su última configuración de enrutamiento conocida. No se pierden rutas.
- Traefik recoge la nueva configuración en su siguiente ciclo de sondeo (dentro de 5 segundos).
- **Las conexiones de cliente existentes (HTTP, TCP, UDP) no se ven afectadas.** El servidor de rutas es un proveedor de configuración -- no está en la ruta de datos. Traefik gestiona todo el tráfico directamente.
- Sus contenedores de aplicación no se tocan -- solo se reinicia el proceso del servidor de rutas a nivel de sistema.

Para omitir el reinicio automático, pase `--skip-router-restart` a cualquier comando, o establezca la variable de entorno `RDC_SKIP_ROUTER_RESTART=1`.
