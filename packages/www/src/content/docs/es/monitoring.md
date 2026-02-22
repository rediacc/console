---
title: Monitoreo
description: >-
  Monitoree el estado de las máquinas, contenedores, servicios, repositorios y
  ejecute diagnósticos.
category: Guides
order: 9
language: es
sourceHash: 72f77c1ae5a0dbce
---

# Monitoreo

Rediacc proporciona comandos de monitoreo integrados para inspeccionar el estado de las máquinas, contenedores en ejecución, servicios, estado de repositorios y diagnósticos del sistema.

## Estado de la Máquina

Obtenga un informe completo del estado de una máquina:

```bash
rdc machine health server-1
```

Esto reporta:
- **Sistema**: tiempo de actividad, uso de memoria, uso de disco
- **Datastore**: capacidad y uso
- **Contenedores**: conteos de en ejecución, saludables, no saludables
- **Servicios**: estado y conteos de reinicios
- **Almacenamiento**: estado SMART y temperatura
- **Repositorios**: estado de montaje y estado del daemon Docker
- **Problemas**: problemas identificados

Use `--output json` para salida legible por máquinas.

## Listar Contenedores

Vea todos los contenedores en ejecución en todos los repositorios de una máquina:

```bash
rdc machine containers server-1
```

| Columna | Descripción |
|---------|-------------|
| Name | Nombre del contenedor |
| Status | En ejecución, detenido, etc. |
| Health | Saludable, no saludable, ninguno |
| CPU | Porcentaje de uso de CPU |
| Memory | Uso de memoria |
| Repository | Qué repositorio es propietario del contenedor |

Opciones:
- `--health-check` -- Realizar verificaciones de estado activas en los contenedores
- `--output json` -- Salida JSON legible por máquinas

## Listar Servicios

Vea los servicios systemd relacionados con Rediacc en una máquina:

```bash
rdc machine services server-1
```

| Columna | Descripción |
|---------|-------------|
| Name | Nombre del servicio |
| State | Activo, inactivo, fallido |
| Sub-state | En ejecución, muerto, etc. |
| Restarts | Conteo de reinicios |
| Memory | Uso de memoria del servicio |
| Repository | Repositorio asociado |

Opciones:
- `--stability-check` -- Marcar servicios inestables (fallidos, >3 reinicios, reinicio automático)
- `--output json` -- Salida JSON legible por máquinas

## Listar Repositorios

Vea los repositorios en una máquina con estadísticas detalladas:

```bash
rdc machine repos server-1
```

| Columna | Descripción |
|---------|-------------|
| Name | Nombre del repositorio |
| Size | Tamaño de la imagen de disco |
| Mount | Montado o desmontado |
| Docker | Daemon Docker en ejecución o detenido |
| Containers | Conteo de contenedores |
| Disk Usage | Uso de disco real dentro del repositorio |
| Modified | Hora de última modificación |

Opciones:
- `--search <text>` -- Filtrar por nombre o ruta de montaje
- `--output json` -- Salida JSON legible por máquinas

## Estado del Vault

Obtenga una visión general completa de una máquina incluyendo información de despliegue:

```bash
rdc machine vault-status server-1
```

Esto proporciona:
- Nombre del host y tiempo de actividad
- Uso de memoria, disco y datastore
- Total de repositorios, conteo de montados, conteo de Docker en ejecución
- Información detallada por repositorio

Use `--output json` para salida legible por máquinas.

## Probar Conexión

Verifique la conectividad SSH a una máquina:

```bash
rdc machine test-connection --ip 203.0.113.50 --user deploy
```

Reporta:
- Estado de la conexión (exitosa/fallida)
- Método de autenticación utilizado
- Configuración de la clave SSH
- Estado del despliegue de la clave pública
- Entrada de hosts conocidos

Opciones:
- `--port <number>` -- Puerto SSH (predeterminado: 22)
- `--save -m server-1` -- Guardar la clave del host verificada en la configuración de la máquina

## Diagnósticos (doctor)

Ejecute una verificación de diagnóstico completa de su entorno Rediacc:

```bash
rdc doctor
```

| Categoría | Verificaciones |
|-----------|---------------|
| **Entorno** | Versión de Node.js, versión de la CLI, modo SEA, instalación de Go, disponibilidad de Docker |
| **Renet** | Ubicación del binario, versión, CRIU, rsync, activos embebidos SEA |
| **Configuración** | Contexto activo, modo, máquinas, clave SSH |
| **Autenticación** | Estado de inicio de sesión, correo del usuario |
| **Virtualización** | Verifica si su sistema puede ejecutar máquinas virtuales locales (`rdc ops`) |

Cada verificación reporta **OK**, **Advertencia** o **Error**. Use esto como primer paso al resolver cualquier problema.

Códigos de salida: `0` = todo pasó, `1` = advertencias, `2` = errores.
