---
title: "Instalacion"
description: "Instale la CLI de Rediacc en Linux, macOS o Windows."
category: "Guides"
order: 1
language: es
---

# Instalacion

Instale la CLI `rdc` en su estacion de trabajo. Esta es la unica herramienta que necesita instalar manualmente -- todo lo demas se gestiona automaticamente cuando configura maquinas remotas.

## Instalacion rapida

### Linux y macOS

```bash
curl -fsSL https://www.rediacc.com/install.sh | bash
```

Esto descarga el binario `rdc` en `$HOME/.local/bin/`. Asegurese de que este directorio este en su PATH:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

Anada esta linea a su perfil de shell (`~/.bashrc`, `~/.zshrc`, etc.) para hacerlo permanente.

### Windows

Ejecute en PowerShell:

```powershell
irm https://www.rediacc.com/install.ps1 | iex
```

Esto descarga `rdc.exe` en `%LOCALAPPDATA%\rediacc\bin\`. El instalador le pedira que lo anada a su PATH si es necesario.

## Gestores de paquetes

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

Nota: El paquete `gcompat` (capa de compatibilidad con glibc) se instala automaticamente como dependencia.

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

| Etiqueta | Descripcion |
|----------|-------------|
| `:stable` | Ultima version estable (recomendada) |
| `:edge` | Ultima version edge |
| `:0.8.4` | Version fijada (inmutable) |
| `:latest` | Alias de `:stable` |

## Verificar la instalacion

```bash
rdc --version
```

## Actualizacion

Actualizar a la ultima version:

```bash
rdc update
```

Comprobar actualizaciones sin instalar:

```bash
rdc update --check-only
```

Ver el estado actual de actualizacion:

```bash
rdc update --status
```

Revertir a la version anterior:

```bash
rdc update rollback
```

## Canales de lanzamiento

Rediacc utiliza un sistema de lanzamiento basado en canales. El canal determina que version recibe para las actualizaciones de CLI, instalaciones de gestores de paquetes y descargas de Docker.

| Canal | Descripcion | Cuando se actualiza |
|-------|-------------|---------------------|
| `stable` | Versiones listas para produccion | Promovida desde edge tras 7 dias de prueba |
| `edge` | Ultimas caracteristicas y correcciones | En cada merge a main |
| `pr-N` | Compilaciones de vista previa de PR | Automaticamente por pull request |

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

### Como funcionan los canales

El canal se aplica de manera uniforme en todos los metodos de distribucion:

- **Scripts de instalacion**: La variable de entorno `REDIACC_CHANNEL` selecciona el canal
- **Repositorios de paquetes**: `releases.rediacc.com/{formato}/{canal}/`
- **Etiquetas de Docker**: `ghcr.io/rediacc/elite/cli:{canal}`
- **Actualizaciones de CLI**: `rdc update` verifica el canal configurado durante la instalacion

### Configuracion automatica de vista previa de PR

Cuando instala desde un despliegue de vista previa de PR (por ejemplo, `pr-420.rediacc.workers.dev`), el canal y el servidor de cuenta se configuran automaticamente:

- El binario de CLI se descarga del canal `pr-420`
- `rdc update` verifica el canal `pr-420` para actualizaciones
- Todos los comandos de cuenta/suscripcion se conectan al servidor de vista previa de PR
- Los comandos de Docker en el sitio de vista previa muestran `cli:pr-420`

No se necesita configuracion manual. El script de instalacion detecta el contexto de despliegue a partir de la URL.

## Actualizaciones de binarios remotos

Cuando ejecuta comandos contra una maquina remota, la CLI aprovisiona automaticamente el binario `renet` correspondiente. Si el binario se actualiza, el servidor de rutas (`rediacc-router`) se reinicia automaticamente para que adopte la nueva version.

El reinicio es transparente y no causa **ningun tiempo de inactividad**:

- El servidor de rutas se reinicia en ~1-2 segundos.
- Durante esa ventana, Traefik continua sirviendo trafico usando su ultima configuracion de enrutamiento conocida. No se pierden rutas.
- Traefik recoge la nueva configuracion en su siguiente ciclo de sondeo (dentro de 5 segundos).
- **Las conexiones de cliente existentes (HTTP, TCP, UDP) no se ven afectadas.** El servidor de rutas es un proveedor de configuracion -- no esta en la ruta de datos. Traefik gestiona todo el trafico directamente.
- Sus contenedores de aplicacion no se tocan -- solo se reinicia el proceso del servidor de rutas a nivel de sistema.

Para omitir el reinicio automatico, pase `--skip-router-restart` a cualquier comando, o establezca la variable de entorno `RDC_SKIP_ROUTER_RESTART=1`.
