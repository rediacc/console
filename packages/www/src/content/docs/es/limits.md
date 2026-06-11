---
title: Límites y cuotas
description: >-
  Referencia de los límites, máximos y cuotas que se aplican a los
  repositorios, servicios, redes y almacenamiento de Rediacc.
category: Reference
order: 99
language: es
sourceHash: "ece2d423d416e7ec"
sourceCommit: "ff9c470edf8760f63f12baf681c04db51a0c202f"
---

# Límites y cuotas

Límites de despliegue de Rediacc. Tres son duros y no pueden cambiarse simplemente agregando hardware: el límite de 61 servicios por repositorio (asignación de espacio de direcciones de red), el requisito mínimo de kernel 6.1 (requisitos de CRIU) y el límite de emisión de Let's Encrypt de 50 certificados comodín por dominio registrado por semana. Todo lo demás es flexible: cambia cuando se agrega hardware. Conozca esta diferencia antes de comprometerse con una topología.

---

## Servicios por repositorio

Cada repositorio admite hasta **61 servicios** ejecutándose simultáneamente.

Este es un límite fijo determinado por el espacio de direcciones de red asignado a cada repositorio. Cada servicio recibe su propia dirección IP privada dedicada, y el bloque de direcciones de cada repositorio permite exactamente 61 espacios de servicio.

Observe: alcanzar 61 servicios en un repositorio generalmente señala un problema de arquitectura, no una restricción de Rediacc. La solución es trasladar los sidecars y agentes de monitoreo a su propio repositorio con su propio límite de aislamiento, o reducir la cantidad de procesos que se ejecutan independientemente dentro de la aplicación misma.

---

## Repositorios por máquina

No hay un límite fijo impuesto por Rediacc. El límite práctico depende de los recursos de su máquina:

| Recurso | Impacto |
|---------|---------|
| Espacio en disco | Cada repositorio es una imagen de disco cifrada. Una máquina con 1 TB de almacenamiento utilizable puede contener muchos repositorios, pero el tamaño total de todas las imágenes debe caber dentro del pool del datastore. |
| RAM | Cada repositorio en ejecución inicia su propio Docker daemon y contenedores. El uso de memoria depende de sus cargas de trabajo. |
| CPU | Las operaciones paralelas de repositorios (inicio, backup, fork) agregan carga temporal de CPU. |

**Los despliegues típicos** ejecutan de 10 a 50 repositorios por máquina sin problemas. Las máquinas con 32 GB+ de RAM y 500 GB+ de almacenamiento ejecutan regularmente 100+ repositorios.

### Límite de ID de red a nivel del sistema

A cada repositorio se le asigna un **ID de red** único, un número utilizado para calcular su rango de direcciones IP privadas. Este pool se comparte entre todas las máquinas y repositorios gestionados por la misma configuración de Rediacc.

| Límite | Valor |
|--------|-------|
| IDs de red disponibles en total | ~261.944 |
| Alcance | Por configuración (compartido entre todas las máquinas de una configuración) |

Cuando se elimina un repositorio, su ID de red se libera y queda disponible para reutilización. Rediacc asigna IDs secuencialmente y solo busca espacios liberados cuando el contador progresivo se acerca al techo. En la práctica, este límite nunca se alcanza. Requeriría crear y gestionar cientos de miles de repositorios durante la vida útil de una sola configuración.

---

## Forks

No hay límite en la cantidad de forks activos de un repositorio. Cada fork es un clon completo de copia en escritura con su propio almacenamiento cifrado, direcciones de red y Docker daemon. Los forks consumen espacio en disco proporcional a los datos escritos después de la creación (no el tamaño completo del repositorio padre).

---

## Puertos externos

### Puertos siempre activos

Los puertos solo se abren una vez que configura una IP pública con `rdc config infra set --public-ipv4`. Hasta entonces, no hay puertos abiertos en la máquina. Una vez configurado:

| Puerto | Protocolo | Propósito |
|--------|-----------|-----------|
| 80 | TCP | HTTP: gestionado por Traefik; devuelve 404 para dominios no configurados, no se pasa a ningún servicio |
| 443 | TCP | HTTPS: igual que arriba; las solicitudes sin una ruta coincidente se rechazan en la capa del proxy |
| 10000–10010 | TCP | Rango dinámico para reenvío TCP gestionado por Rediacc |

HTTP/HTTPS se diferencian de los puertos TCP sin procesar: aunque 80 y 443 están abiertos, cada solicitud es validada por el proxy inverso contra una tabla de enrutamiento explícita. Sin un servicio configurado y un dominio coincidente, no se alcanza ningún código de aplicación y no se exponen datos.

### Reenvío TCP/UDP opcional

Todos los demás puertos (bases de datos, cachés, brokers de mensajes, DNS, correo) están **cerrados por defecto** y deben abrirse explícitamente. Esto mantiene la superficie de ataque de la máquina al mínimo.

Para exponer un puerto de un servicio específico:

```yaml
labels:
  - "rediacc.tcp_ports=5432"   # expose PostgreSQL from this container
  - "rediacc.udp_ports=53"     # expose DNS from this container
```

Para abrir un puerto a nivel de máquina (disponible para todos los servicios):

```bash
rdc config infra set -m server-1 --tcp-ports 25,587,993   # mail server
rdc config infra push -m server-1
```

> Nunca exponga puertos de bases de datos o cachés externamente a menos que tenga un requisito específico. Use rutas automáticas HTTPS para servicios web y mantenga los servicios de almacenamiento internos.

---

## Datastore

El datastore es un pool de tamaño fijo creado cuando se configura una máquina por primera vez. Su tamaño no crece automáticamente.

- **Tamaño mínimo recomendado**: 50 GB
- **Tamaño máximo**: Limitado por su disco. Un solo pool puede abarcar un disco completo.
- **Redimensionar**: Use `rdc datastore resize` para cambiar el tamaño del pool (todos los repositorios deben estar desmontados primero).
- **Sistema de archivos**: Rediacc usa BTRFS internamente para snapshots de copia en escritura y forking eficiente. Requiere una máquina con **Linux kernel 6.1 o posterior** para estabilidad completa en producción.

Cada repositorio tiene un tamaño máximo establecido en el momento de la creación (por defecto: 10 GB). Use `rdc repo resize` para cambiarlo manualmente, o configure una [política de tamaño automático](/es/docs/repositories#politica-de-tamano-automatico) para que la máquina lo amplíe en línea cuando se llene (acotado por un techo explícito por repositorio y una reserva de espacio libre del pool). El crecimiento automático se aplica solo a repositorios individuales; el pool en sí nunca crece automáticamente.

Las imágenes de repositorio son sparse: un repositorio solo ocupa en el pool lo que ha escrito realmente, y el espacio liberado por eliminaciones vuelve al pool mediante [`repo trim`](/es/docs/repositories#recuperar-espacio-trim) o un auto-trim programado. Las cuotas pueden por lo tanto sumar más que el tamaño del pool, y el [informe de salud del almacenamiento](/es/docs/monitoring#salud-del-almacenamiento) muestra el nivel de llenado real.

---

## Rutas HTTP

Cada servicio con la etiqueta `rediacc.service_port` obtiene una ruta HTTPS automáticamente. No hay límite en la cantidad de servicios con rutas, sujeto al máximo de 61 servicios por repositorio.

Los certificados TLS comodín se provisionan por repositorio en el primer despliegue a través de Let's Encrypt (desafío Cloudflare DNS-01). Let's Encrypt limita la emisión a **50 certificados por dominio registrado por semana**. Dado que Rediacc usa un certificado comodín por repositorio (no por servicio), un despliegue que cree 50+ nuevos repositorios en una sola semana alcanzará este límite.

Los forks reutilizan el certificado comodín existente del repositorio padre y no consumen cuota de certificados.

---

## Checkpoint / Restore (CRIU)

La migración en vivo a través de CRIU tiene las siguientes restricciones:

- **Opt-in**: Solo los contenedores con la etiqueta `rediacc.checkpoint=true` se incluyen en el checkpoint. Las bases de datos y los servicios sin estado se excluyen por defecto y se inician de nuevo en la restauración.
- **Requisito de kernel**: Linux 6.1+ tanto en la máquina de origen como en la de destino.
- **Modo de red**: CRIU requiere el modo de red del host. Los contenedores que usan configuraciones de red personalizadas no pueden ser incluidos en el checkpoint.
- **Memoria**: El tamaño de los datos del checkpoint equivale a la memoria residente del proceso. Los grandes conjuntos de datos en memoria (por ejemplo, una aplicación Node.js que almacena en caché 4 GB de datos) producen archivos de checkpoint de 4 GB.
- **Conexiones TCP**: Las aplicaciones deben tolerar la pérdida de conexiones durante la restauración. Las conexiones TCP activas **no** se preservan, el proceso restaurado ve los sockets como cerrados y debe reconectarse. Esto se aplica tanto a restauraciones en la misma máquina como entre máquinas.
- **El fork en vivo en la misma máquina redirige las direcciones del padre**: `rdc repo fork --parent X --tag Y --checkpoint` seguido de `rdc repo up` funciona mientras el repositorio padre sigue en ejecución. Los procesos restaurados conservan las direcciones loopback del padre del momento del checkpoint, así que el sistema las redirige de forma transparente a las direcciones propias del fork (mismo servicio, copia de datos del fork). El primer uso de una conexión TCP restaurada sigue fallando y la aplicación debe reconectarse, según el punto de TCP de arriba.

---

## Backups

| Límite | Valor |
|--------|-------|
| Destinos de backup por repositorio | Ilimitados |
| Trabajos de backup simultáneos | 1 por repositorio (los trabajos se ponen en cola si se activan simultáneamente) |
| Frecuencia de backup | Sin intervalo mínimo impuesto; limitado por el ancho de banda de su almacenamiento. Use `rdc config backup-strategy set --name <name> --bwlimit "6M"` para limitar la velocidad de subida (sintaxis rclone `--bwlimit`: simple `6M`, direccional `6M:off`, o tabla de tiempo `08:00,3M;22:00,10M`) |
| Retención | Controlada por su proveedor de almacenamiento (S3, Cloudflare R2, etc.). Rediacc no impone políticas de retención. |
| Backup entre máquinas | Soportado; la máquina de destino debe tener suficiente espacio en el datastore |

---

## CLI & API

| Límite | Valor |
|--------|-------|
| Comandos `rdc` simultáneos contra la misma máquina | Ilimitados (cada comando abre su propia conexión SSH) |
| Concurrencia predeterminada de inicio de repositorios en paralelo | 3 (ajustable con `--concurrency`) |
| Tiempo de espera de conexión SSH | 30 segundos para la conexión inicial |
| Duración de la sesión `rdc` | Sin tiempo de espera; las operaciones de larga duración mantienen la conexión activa |

---

## Versiones de SO soportadas

Las máquinas remotas deben ejecutar uno de los siguientes sistemas para cumplir con los requisitos de kernel, sistema de archivos y aislamiento de red de Rediacc. Esta lista es el conjunto canónico probado en CI (matriz Bridge Workers) y debe mantenerse sincronizada con [Requisitos](/en/docs/requirements):

| SO | Versión mínima | Kernel predeterminado | Notas |
|----|----------------|-----------------------|-------|
| Ubuntu | 24.04 LTS *(recomendado)* | 6.8 | AppArmor por defecto. |
| Debian | 13 (Trixie); 12 Bookworm también funciona | 6.12 (6.1 en Debian 12) | |
| Fedora | 43 | 6.12 | SELinux enforcing por defecto. |
| openSUSE Leap | 16.0 | 6.4+ | AppArmor por defecto. |
| Oracle Linux | 10 (UEK) | UEK 7+ | UEK conserva btrfs; SELinux enforcing por defecto. |

**Kernel mínimo requerido: 6.1.** Las máquinas con kernels anteriores se rechazan en el momento de la configuración con un mensaje de error claro.

> **Por qué kernel 6.1?** Rediacc usa BTRFS para el almacenamiento cifrado de repositorios y el forking de copia en escritura. Linux 6.1 introdujo mejoras críticas de BTRFS que reducen significativamente los tiempos de montaje para grandes datastores, mejoran el rendimiento de eliminación de snapshots y corrigen problemas de integridad de datos presentes en kernels anteriores. El kernel 6.1 también es necesario para los hooks de aislamiento de red a nivel de kernel que aplican el aislamiento entre repositorios, reescribiendo de forma transparente las llamadas `bind()` y bloqueando conexiones entre repositorios.

> **Por qué no Rocky Linux 10 / kernel stock de RHEL 10?** El kernel stock de RHEL 10 se distribuye sin el módulo `btrfs` (`modprobe btrfs` falla con "Module btrfs not found"). El backend de almacenamiento cifrado de Rediacc no puede funcionar sin btrfs. **Oracle Linux 10 es el único objetivo compatible con RHEL en la lista soportada** porque usa por defecto el Unbreakable Enterprise Kernel (UEK), que conserva btrfs. Consulte [Requisitos: Por qué UEK?](/en/docs/requirements) para la explicación completa.

### Matriz de características del kernel

Usa la tabla como una vista de un solo vistazo de lo que cada SO probado en CI proporciona por defecto. Los cinco satisfacen todos los requisitos, así que esta es una referencia para operadores, no un criterio de selección.

| SO | Módulo btrfs | cgroups v2 | Landlock (ABI ≥ 1) | Hooks eBPF cgroup |
|----|--------------|------------|---------------------|-------------------|
| Ubuntu 24.04 | integrado | unified hierarchy | sí (5.13+) | sí |
| Debian 13 | integrado | unified hierarchy | sí | sí |
| Fedora 43 | integrado | unified hierarchy | sí | sí |
| openSUSE Leap 16.0 | integrado | unified hierarchy | sí | sí |
| Oracle Linux 10 (UEK) | integrado (via UEK) | unified hierarchy | sí | sí |
