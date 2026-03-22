---
title: "Aprovisionamiento de VM local"
description: "Aprovisionar un clúster de VM local, ejecutar comandos por SSH y eliminarlo usando la CLI."
category: "Tutorials"
order: 1
language: es
sourceHash: "2fdc49f796b03e18"
---

# Cómo aprovisionar VMs locales con Rediacc

Probar la infraestructura localmente antes de desplegar en producción ahorra tiempo y previene errores de configuración. En este tutorial, aprovisionará un clúster de VM mínimo en su estación de trabajo, verificará la conectividad, ejecutará comandos por SSH y eliminará todo. Al finalizar, tendrá un entorno de desarrollo local repetible.

## Requisitos previos

- Una estación de trabajo Linux o macOS con virtualización de hardware habilitada
- La CLI `rdc` instalada y una configuración inicializada con el adaptador local
- KVM/libvirt (Linux) o QEMU (macOS) instalado — consulte [VMs experimentales](/es/docs/experimental-vms) para instrucciones de configuración

## Grabación interactiva

![Tutorial: rdc ops provisioning](/assets/tutorials/ops-tutorial.cast)

### Paso 1: Verificar requisitos del sistema

Antes de aprovisionar, confirme que su estación de trabajo tiene soporte de virtualización y los paquetes requeridos instalados.

```bash
rdc ops check
```

Rediacc verifica la virtualización de hardware (VT-x/AMD-V), los paquetes requeridos (libvirt, QEMU) y la configuración de red. Todas las verificaciones deben pasar antes de poder crear VMs.

### Paso 2: Aprovisionar un clúster de VM mínimo

```bash
rdc ops up --basic --skip-orchestration
```

Crea un clúster de dos VMs: una VM **puente** (1 CPU, 1024 MB RAM, 8 GB disco) y una VM **trabajador** (2 CPU, 4096 MB RAM, 16 GB disco). La opción `--skip-orchestration` omite el aprovisionamiento de la plataforma Rediacc, proporcionando VMs básicas solo con acceso SSH.

> **Nota:** El primer aprovisionamiento descarga imágenes base, lo que tarda más. Las ejecuciones posteriores reutilizan imágenes en caché.

### Paso 3: Verificar estado del clúster

```bash
rdc ops status
```

Muestra el estado de cada VM en el clúster — direcciones IP, asignación de recursos y estado de ejecución. Ambas VMs deberían aparecer como en ejecución.

### Paso 4: Ejecutar comandos en una VM

```bash
rdc ops ssh 1 hostname
rdc ops ssh 1 uname -a
```

Ejecuta comandos en la VM puente (ID `1`) por SSH. Pase cualquier comando después del ID de la VM. Para una sesión interactiva, omita el comando: `rdc ops ssh 1`.

### Paso 5: Eliminar el clúster

Cuando haya terminado, destruya todas las VMs y libere recursos.

```bash
rdc ops down
```

Elimina todas las VMs y limpia la red. El clúster puede ser reaprovisionado en cualquier momento con `rdc ops up`.

## Solución de problemas

**"KVM not available" o "hardware virtualization not supported"**
Verifique que la virtualización esté habilitada en la configuración de su BIOS/UEFI. En Linux, compruebe con `lscpu | grep Virtualization`. En WSL2, la virtualización anidada requiere flags de kernel específicos.

**"libvirt daemon not running"**
Inicie el servicio libvirt: `sudo systemctl start libvirtd`. En macOS, verifique que QEMU esté instalado vía Homebrew: `brew install qemu`.

**"Insufficient memory for VM allocation"**
El clúster básico requiere al menos 6 GB de RAM libre (1 GB puente + 4 GB trabajador + sobrecarga). Cierre otras aplicaciones que consuman muchos recursos o reduzca las especificaciones de las VMs.

## Próximos pasos

Aprovisionó un clúster de VM local, ejecutó comandos por SSH y lo eliminó. Para desplegar infraestructura real:

- [VMs experimentales](/es/docs/experimental-vms) — referencia completa para comandos `rdc ops`, configuración de VM y soporte de plataformas
- [Tutorial: Configuración de máquinas](/es/docs/tutorial-setup) — registrar máquinas remotas y configurar infraestructura
- [Inicio rápido](/es/docs/quick-start) — desplegar un servicio contenerizado de principio a fin
