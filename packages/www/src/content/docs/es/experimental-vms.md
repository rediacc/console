---
title: "VMs Experimentales"
description: "Aprovisione clústeres de VMs locales para desarrollo y pruebas con rdc ops."
category: "Concepts"
order: 2
language: es
sourceHash: fa4069c48c650a79
---

# VMs Experimentales

Aprovisione clústeres de VMs locales en su estación de trabajo para desarrollo y pruebas — no se requieren proveedores de nube externos.

## Requisitos

`rdc ops` requiere el **adaptador local**. No está disponible con el adaptador cloud.

```bash
rdc ops check
```

## Descripción General

Los comandos `rdc ops` le permiten crear y gestionar clústeres de VM experimentales de forma local. Esta es la misma infraestructura utilizada por el pipeline de CI para las pruebas de integración, ahora disponible para experimentación práctica.

Casos de uso:
- Probar despliegues de Rediacc sin proveedores de VM externos (Linode, Vultr, etc.)
- Desarrollar y depurar configuraciones de repositorios localmente
- Aprender la plataforma en un entorno completamente aislado
- Ejecutar pruebas de integración en su estación de trabajo

## Soporte de Plataformas

| Plataforma | Arquitectura | Backend | Estado |
|----------|-------------|---------|--------|
| Linux | x86_64 | KVM (libvirt) | Probado en CI |
| macOS | Intel | QEMU + HVF | Probado en CI |
| Linux | ARM64 | KVM (libvirt) | Compatible (no probado en CI) |
| macOS | ARM (Apple Silicon) | QEMU + HVF | Compatible (no probado en CI) |
| Windows | x86_64 / ARM64 | Hyper-V | Planificado |

**Linux (KVM)** utiliza libvirt para virtualización de hardware nativo con redes en puente.

**macOS (QEMU)** utiliza QEMU con el Framework Hypervisor de Apple (HVF) para rendimiento casi nativo, con redes en modo usuario y reenvío de puertos SSH.

**Windows (Hyper-V)** el soporte está planificado. Consulte el [issue #380](https://github.com/rediacc/console/issues/380) para más detalles. Requiere Windows Pro/Enterprise.

## Prerrequisitos y Configuración

### Linux

```bash
# Instalar prerrequisitos automáticamente
rdc ops setup

# O manualmente:
sudo apt install libvirt-daemon-system virtinst qemu-utils cloud-image-utils docker.io
sudo systemctl enable --now libvirtd
```

### macOS

```bash
# Instalar prerrequisitos automáticamente
rdc ops setup

# O manualmente:
brew install qemu cdrtools
```

### Verificar Configuración

```bash
rdc ops check
```

Esto ejecuta verificaciones específicas de la plataforma y reporta éxito/fallo para cada prerrequisito.

## Inicio Rápido

```bash
# 1. Verificar prerrequisitos
rdc ops check

# 2. Aprovisionar un clúster mínimo (puente + 1 worker)
rdc ops up --basic

# 3. Verificar estado de las VMs
rdc ops status

# 4. Conectarse por SSH a la VM puente
rdc ops ssh 1

# 4b. O ejecutar un comando directamente
rdc ops ssh 1 hostname

# 5. Desmantelar
rdc ops down
```

## Composición del Clúster

Por defecto, `rdc ops up` aprovisiona:

| VM | ID | Rol |
|----|-----|------|
| Bridge | 1 | Nodo primario — ejecuta el servicio bridge de Rediacc |
| Worker 1 | 11 | Nodo worker para despliegues de repositorios |
| Worker 2 | 12 | Nodo worker para despliegues de repositorios |

Use la bandera `--basic` para aprovisionar solo el bridge y el primer worker (IDs 1 y 11).

Use `--skip-orchestration` para aprovisionar VMs sin iniciar los servicios de Rediacc — útil para probar la capa de VM de forma aislada.

## Configuración

La VM bridge usa valores predeterminados más pequeños que las VMs worker:

| Rol de VM | CPUs | RAM | Disco |
|---------|------|-----|------|
| Bridge | 1 | 1024 MB | 8 GB |
| Worker | 2 | 4096 MB | 16 GB |

Las variables de entorno sobreescriben los recursos de las VMs worker:

| Variable | Predeterminado | Descripción |
|----------|---------|-------------|
| `VM_CPU` | 2 | Núcleos de CPU por VM worker |
| `VM_RAM` | 4096 | RAM en MB por VM worker |
| `VM_DSK` | 16 | Tamaño de disco en GB por VM worker |
| `VM_NET_BASE` | 192.168.111 | Base de red (solo KVM) |
| `RENET_DATA_DIR` | ~/.renet | Directorio de datos para discos y configuración de VMs |

## Referencia de Comandos

| Comando | Descripción |
|---------|-------------|
| `rdc ops setup` | Instalar prerrequisitos de la plataforma (KVM o QEMU) |
| `rdc ops check` | Verificar que los prerrequisitos estén instalados y funcionando |
| `rdc ops up [options]` | Aprovisionar clúster de VMs |
| `rdc ops down` | Destruir todas las VMs y limpiar |
| `rdc ops status` | Mostrar estado de todas las VMs |
| `rdc ops ssh <vm-id> [command...]` | Conectarse por SSH a una VM, o ejecutar un comando en ella |

### Opciones de `rdc ops up`

| Opción | Descripción |
|--------|-------------|
| `--basic` | Clúster mínimo (bridge + 1 worker) |
| `--lite` | Omitir aprovisionamiento de VMs (solo claves SSH) |
| `--force` | Forzar recreación de VMs existentes |
| `--parallel` | Aprovisionar VMs en paralelo |
| `--skip-orchestration` | Solo VMs, sin servicios de Rediacc |
| `--backend <kvm\|qemu>` | Sobreescribir el backend detectado automáticamente |
| `--os <name>` | Imagen del SO (predeterminado: ubuntu-24.04) |
| `--debug` | Salida detallada |

## Diferencias de Plataforma

### Linux (KVM)
- Utiliza libvirt para la gestión del ciclo de vida de las VMs
- Redes en puente — las VMs obtienen IPs en una red virtual (192.168.111.x)
- SSH directo a las IPs de las VMs
- Requiere `/dev/kvm` y el servicio libvirtd

### macOS (QEMU + HVF)
- Utiliza procesos QEMU gestionados mediante archivos PID
- Redes en modo usuario con reenvío de puertos SSH (localhost:222XX)
- SSH mediante puertos reenviados, no IPs directas
- ISOs cloud-init creados mediante `mkisofs`

## Resolución de Problemas

### Modo de depuración

Agregue `--debug` a cualquier comando para salida detallada:

```bash
rdc ops up --basic --debug
```

### Problemas comunes

**KVM no disponible (Linux)**
- Verifique que `/dev/kvm` existe: `ls -la /dev/kvm`
- Habilite la virtualización en BIOS/UEFI
- Cargue el módulo del kernel: `sudo modprobe kvm_intel` o `sudo modprobe kvm_amd`

**libvirtd no está en ejecución (Linux)**
```bash
sudo systemctl enable --now libvirtd
```

**QEMU no encontrado (macOS)**
```bash
brew install qemu cdrtools
```

**Las VMs no arrancan**
- Verifique el espacio en disco en `~/.renet/disks/`
- Ejecute `rdc ops check` para verificar todos los prerrequisitos
- Intente `rdc ops down` y luego `rdc ops up --force`
