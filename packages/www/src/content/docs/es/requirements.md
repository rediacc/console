---
title: Requisitos
description: Requisitos mínimos del sistema y plataformas compatibles para ejecutar Rediacc.
category: Guides
order: 0
language: es
sourceHash: "eb237c7beb1bb942"
sourceCommit: "d5c06171af0ef58b551a9682905d98af81e496cd"
---

# Requisitos

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

Si no tiene claro qué herramienta usar, consulte [rdc vs renet](/en/docs/rdc-vs-renet). En resumen: use `rdc` para operaciones normales y `renet` directamente solo para tareas avanzadas en el lado del servidor.

### Sistemas Operativos Compatibles

Los servidores remotos ejecutan el binario `renet` y alojan los daemons Docker cifrados y aislados por repositorio. Las siguientes cinco distribuciones son ejercitadas por la matriz Bridge Workers en CI en cada pull request y son las únicas oficialmente compatibles:

| SO | Versión | Kernel predeterminado | Notas |
|----|---------|----------------------|-------|
| Ubuntu | 24.04 LTS | 6.8 | Recomendado. AppArmor habilitado por defecto. |
| Debian | 13 (Trixie) | 6.12 | Debian 12 también funciona (kernel 6.1 mínimo). |
| Fedora | 43 | 6.12 | SELinux en modo enforcing por defecto. |
| openSUSE Leap | 16.0 | 6.4+ | AppArmor habilitado por defecto. |
| Oracle Linux | 10 | UEK 7+ | Usa UEK, que conserva el módulo btrfs. SELinux en modo enforcing por defecto. Consulte "¿Por qué UEK?" a continuación. |

Todas las filas son `x86_64`. `arm64` se compila pero no se prueba continuamente para cada SO de servidor; abra un issue si lo necesita en una distribución específica. Otras distribuciones Linux con systemd, soporte de Docker y cryptsetup pueden funcionar, pero no tienen soporte oficial y pueden dejar de funcionar en actualizaciones sin previo aviso.

#### ¿Por qué UEK? (y por qué Rocky 10 / RHEL 10 estándar no está soportado)

El backend de almacenamiento cifrado de Rediacc requiere el módulo de kernel `btrfs` integrado. **El kernel estándar de RHEL 10 no lo incluye**: `modprobe btrfs` falla con "Module btrfs not found" y `dnf search btrfs` no devuelve nada. Rocky Linux 10 y AlmaLinux 10 heredan el mismo kernel y, por tanto, no pueden funcionar como servidores Rediacc.

Oracle Linux 10 usa el **Unbreakable Enterprise Kernel (UEK)** por defecto, que mantiene btrfs integrado. Este es el único objetivo compatible con RHEL en la lista de sistemas soportados. Si debe ejecutar un servidor de la familia RHEL, use Oracle Linux 10 con UEK. (La fuente de verdad para esta decisión se encuentra en `.github/workflows/ct-tests.yml` como la matriz CI Bridge Workers.)

#### Solo para estación de trabajo (destinos de instalación de CLI)

La CLI `rdc` también se instala correctamente en Alpine 3.19+ (APK con la capa de compatibilidad `gcompat`, instalada automáticamente) y Arch Linux (rolling, via pacman). Estas son rutas de instalación solo del lado del cliente (consulte [Instalación](/en/docs/installation)) y no están soportadas como destinos de servidor `renet`.

### Políticas de Seguridad por SO

El daemon Docker por repositorio y los propios contenedores del repositorio se ejecutan con **etiquetas de contenedor predeterminadas** en todos los sistemas operativos soportados. `rdc config machine setup` no instala políticas SELinux personalizadas ni perfiles AppArmor. Comportamiento por SO:

- **Ubuntu 24.04, openSUSE Leap 16.0**: AppArmor está habilitado por defecto. Se aplica el perfil docker-container predeterminado; no se requiere configuración adicional.
- **Fedora 43, Oracle Linux 10**: SELinux funciona en modo enforcing. El daemon por repositorio etiqueta los contenedores con el contexto estándar `container_t`. No se necesita ninguna política SELinux personalizada.
- **CRIU** (checkpoint/restore) es el único caso que omite el perfil AppArmor con `apparmor=unconfined`, ya que el soporte AppArmor de CRIU upstream aún no es estable. Consulte las notas de CRIU en [Reglas de Rediacc](/en/docs/rules-of-rediacc).

Si un paso de configuración falla con rechazos AVC de SELinux o rechazos de AppArmor, consulte [Solución de problemas](/en/docs/troubleshooting), sección "Problemas de configuración específicos de la distribución".

### Requisitos Previos del Servidor

- Una cuenta de usuario con privilegios de `sudo` (sudo sin contraseña recomendado)
- Su clave pública SSH agregada a `~/.ssh/authorized_keys`
- Al menos 20 GB de espacio libre en disco (más dependiendo de sus cargas de trabajo)
- Acceso a internet para descargar imágenes Docker (o un registro privado)

### Instalado Automáticamente

El comando `rdc config machine setup` instala lo siguiente en el servidor remoto:

- **Docker** y **containerd** (entorno de ejecución de contenedores)
- **cryptsetup** (cifrado de disco LUKS)
- Binario **renet** (subido mediante SFTP)

No necesita instalar estos manualmente.

## Máquinas Virtuales Locales (Opcional)

Si desea probar despliegues localmente usando `rdc ops`, su estación de trabajo necesita soporte de virtualización: KVM en Linux o QEMU en macOS. Consulte la guía de [VMs Experimentales](/en/docs/experimental-vms) para los pasos de configuración y detalles de plataforma.
