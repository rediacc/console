---
title: "Requisitos"
description: "Requisitos del sistema y plataformas compatibles para ejecutar Rediacc."
category: "Getting Started"
order: 0
language: es
---

# Requisitos

Antes de desplegar con Rediacc, asegurese de que su estacion de trabajo y los servidores remotos cumplan con los siguientes requisitos.

## Estacion de Trabajo (Plano de Control)

La CLI `rdc` se ejecuta en su estacion de trabajo y orquesta servidores remotos a traves de SSH.

| Plataforma | Version Minima | Notas |
|------------|---------------|-------|
| macOS | 12 (Monterey)+ | Intel y Apple Silicon compatibles |
| Linux (x86_64) | Cualquier distribucion moderna | glibc 2.31+ (Ubuntu 20.04+, Debian 11+, Fedora 34+) |
| Windows | 10+ con WSL2 | Ejecute `rdc` dentro de una distribucion Linux WSL2 |

**Requisitos adicionales:**
- Un par de claves SSH (por ejemplo, `~/.ssh/id_ed25519` o `~/.ssh/id_rsa`)
- Acceso de red a sus servidores remotos en el puerto SSH (predeterminado: 22)

## Servidor Remoto (Plano de Datos)

El binario `renet` se ejecuta en servidores remotos con privilegios de root. Gestiona imagenes de disco cifradas, daemons Docker aislados y orquestacion de servicios.

### Sistemas Operativos Compatibles

| SO | Version | Arquitectura |
|----|---------|-------------|
| Ubuntu | 24.04+ | x86_64 |
| Debian | 12+ | x86_64 |
| Fedora | 43+ | x86_64 |
| openSUSE Leap | 15.6+ | x86_64 |

Estas son las distribuciones probadas en CI. Otras distribuciones de Linux con systemd, soporte para Docker y cryptsetup pueden funcionar, pero no tienen soporte oficial.

### Requisitos Previos del Servidor

- Una cuenta de usuario con privilegios de `sudo` (sudo sin contrasena recomendado)
- Su clave publica SSH agregada a `~/.ssh/authorized_keys`
- Al menos 20 GB de espacio libre en disco (mas dependiendo de sus cargas de trabajo)
- Acceso a internet para descargar imagenes Docker (o un registro privado)

### Instalado Automaticamente

El comando `rdc context setup-machine` instala lo siguiente en el servidor remoto:

- **Docker** y **containerd** (entorno de ejecucion de contenedores)
- **cryptsetup** (cifrado de disco LUKS)
- Binario **renet** (subido mediante SFTP)

No necesita instalar estos manualmente.
