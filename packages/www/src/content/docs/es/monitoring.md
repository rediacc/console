---
title: "Monitoreo"
description: "Monitoree el estado de las maquinas, contenedores, servicios, repositorios y ejecute diagnosticos."
category: "Guides"
order: 9
language: es
---

# Monitoreo

Rediacc proporciona comandos de monitoreo integrados para inspeccionar el estado de las maquinas, contenedores en ejecucion, servicios, estado de repositorios y diagnosticos del sistema.

## Estado de la Maquina

Obtenga un informe completo del estado de una maquina:

```bash
rdc machine health server-1
```

Esto reporta:
- **Sistema**: tiempo de actividad, uso de memoria, uso de disco
- **Datastore**: capacidad y uso
- **Contenedores**: conteos de en ejecucion, saludables, no saludables
- **Servicios**: estado y conteos de reinicios
- **Almacenamiento**: estado SMART y temperatura
- **Repositorios**: estado de montaje y estado del daemon Docker
- **Problemas**: problemas identificados

Use `--output json` para salida legible por maquinas.

## Listar Contenedores

Vea todos los contenedores en ejecucion en todos los repositorios de una maquina:

```bash
rdc machine containers server-1
```

| Columna | Descripcion |
|---------|-------------|
| Name | Nombre del contenedor |
| Status | En ejecucion, detenido, etc. |
| Health | Saludable, no saludable, ninguno |
| CPU | Porcentaje de uso de CPU |
| Memory | Uso de memoria |
| Repository | Que repositorio es propietario del contenedor |

Opciones:
- `--health-check` -- Realizar verificaciones de estado activas en los contenedores
- `--output json` -- Salida JSON legible por maquinas

## Listar Servicios

Vea los servicios systemd relacionados con Rediacc en una maquina:

```bash
rdc machine services server-1
```

| Columna | Descripcion |
|---------|-------------|
| Name | Nombre del servicio |
| State | Activo, inactivo, fallido |
| Sub-state | En ejecucion, muerto, etc. |
| Restarts | Conteo de reinicios |
| Memory | Uso de memoria del servicio |
| Repository | Repositorio asociado |

Opciones:
- `--stability-check` -- Marcar servicios inestables (fallidos, >3 reinicios, reinicio automatico)
- `--output json` -- Salida JSON legible por maquinas

## Listar Repositorios

Vea los repositorios en una maquina con estadisticas detalladas:

```bash
rdc machine repos server-1
```

| Columna | Descripcion |
|---------|-------------|
| Name | Nombre del repositorio |
| Size | Tamano de la imagen de disco |
| Mount | Montado o desmontado |
| Docker | Daemon Docker en ejecucion o detenido |
| Containers | Conteo de contenedores |
| Disk Usage | Uso de disco real dentro del repositorio |
| Modified | Hora de ultima modificacion |

Opciones:
- `--search <text>` -- Filtrar por nombre o ruta de montaje
- `--output json` -- Salida JSON legible por maquinas

## Estado del Vault

Obtenga una vision general completa de una maquina incluyendo informacion de despliegue:

```bash
rdc machine vault-status server-1
```

Esto proporciona:
- Nombre del host y tiempo de actividad
- Uso de memoria, disco y datastore
- Total de repositorios, conteo de montados, conteo de Docker en ejecucion
- Informacion detallada por repositorio

Use `--output json` para salida legible por maquinas.

## Probar Conexion

Verifique la conectividad SSH a una maquina:

```bash
rdc machine test-connection --ip 203.0.113.50 --user deploy
```

Reporta:
- Estado de la conexion (exitosa/fallida)
- Metodo de autenticacion utilizado
- Configuracion de la clave SSH
- Estado del despliegue de la clave publica
- Entrada de hosts conocidos

Opciones:
- `--port <number>` -- Puerto SSH (predeterminado: 22)
- `--save -m server-1` -- Guardar la clave del host verificada en la configuracion de la maquina

## Diagnosticos (doctor)

Ejecute una verificacion de diagnostico completa de su entorno Rediacc:

```bash
rdc doctor
```

| Categoria | Verificaciones |
|-----------|---------------|
| **Entorno** | Version de Node.js, version de la CLI, modo SEA, instalacion de Go, disponibilidad de Docker |
| **Renet** | Ubicacion del binario, version, CRIU, rsync, activos embebidos SEA |
| **Configuracion** | Contexto activo, modo, maquinas, clave SSH |
| **Autenticacion** | Estado de inicio de sesion, correo del usuario |

Cada verificacion reporta **OK**, **Advertencia** o **Error**. Use esto como primer paso al resolver cualquier problema.

Codigos de salida: `0` = todo paso, `1` = advertencias, `2` = errores.
