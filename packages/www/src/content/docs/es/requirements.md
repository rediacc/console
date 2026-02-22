---
title: Requisitos
description: Requisitos mínimos del sistema y plataformas compatibles para ejecutar Rediacc.
category: Guides
order: 0
language: es
sourceHash: 35e75948e9858c6d
---

# Requisitos

Si no tienes claro qué herramienta usar, consulta [rdc vs renet](/es/docs/rdc-vs-renet).

Antes de desplegar con Rediacc, asegúrese de que su estación de trabajo y los servidores remotos cumplan con los siguientes requisitos.

## Estación de Trabajo (Plano de Control)

La CLI `rdc` se ejecuta en su estación de trabajo y orquesta servidores remotos a través de SSH.

| Plataforma | Versión Mínima | Notas |
|------------|---------------|-------|
| macOS | 12 (Monterey)+ | Intel y Apple Silicon compatibles |
| Linux (x86_64) | Cualquier distribución moderna | glibc 2.31+ (Ubuntu 20.04+, Debian 11+, Fedora 34+) |
| Windows | 10+ | Soporte nativo mediante instalador PowerShell |

**Requisitos adicionales:**
- Un par de claves SSH (por ejemplo, `~/.ssh/id_ed25519` o `~/.ssh/id_rsa`)
- Acceso de red a sus servidores remotos en el puerto SSH (predeterminado: 22)

## Servidor Remoto (Plano de Datos)

El binario `renet` se ejecuta en servidores remotos con privilegios de root. Gestiona imágenes de disco cifradas, daemons Docker aislados y orquestación de servicios.

### Sistemas Operativos Compatibles

| SO | Versión | Arquitectura |
|----|---------|-------------|
| Ubuntu | 24.04+ | x86_64 |
| Debian | 12+ | x86_64 |
| Fedora | 43+ | x86_64 |
| openSUSE Leap | 15.6+ | x86_64 |
| Alpine | 3.19+ | x86_64 (requiere gcompat) |
| Arch Linux | Rolling release | x86_64 |

Estas son las distribuciones probadas en CI. Otras distribuciones de Linux con systemd, soporte para Docker y cryptsetup pueden funcionar, pero no tienen soporte oficial.

### Requisitos Previos del Servidor

- Una cuenta de usuario con privilegios de `sudo` (sudo sin contraseña recomendado)
- Su clave pública SSH agregada a `~/.ssh/authorized_keys`
- Al menos 20 GB de espacio libre en disco (más dependiendo de sus cargas de trabajo)
- Acceso a internet para descargar imágenes Docker (o un registro privado)

### Instalado Automáticamente

El comando `rdc context setup-machine` instala lo siguiente en el servidor remoto:

- **Docker** y **containerd** (entorno de ejecución de contenedores)
- **cryptsetup** (cifrado de disco LUKS)
- Binario **renet** (subido mediante SFTP)

No necesita instalar estos manualmente.

## Máquinas Virtuales Locales (Opcional)

Si desea probar despliegues localmente usando `rdc ops`, su estación de trabajo necesita soporte de virtualización: KVM en Linux o QEMU en macOS. Consulte la guía de [VMs Experimentales](/es/docs/experimental-vms) para los pasos de configuración y detalles de plataforma.
