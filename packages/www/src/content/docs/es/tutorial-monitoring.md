---
title: "Monitoreo y diagnósticos"
description: "Verificar el estado de la máquina, inspeccionar contenedores, revisar servicios systemd, escanear claves de host y ejecutar diagnósticos del entorno."
category: "Tutorials"
order: 4
language: es
sourceHash: "af9f17a05dfb13b9"
---

# Cómo monitorear y diagnosticar infraestructura con Rediacc

Mantener la infraestructura saludable requiere visibilidad del estado de la máquina, el estado de los contenedores y la salud de los servicios. En este tutorial, ejecutará diagnósticos del entorno, verificará el estado de la máquina, inspeccionará contenedores y servicios, revisará el estado de la bóveda y verificará la conectividad. Al finalizar, sabrá cómo identificar e investigar problemas en toda su infraestructura.

## Requisitos previos

- La CLI `rdc` instalada con una configuración inicializada
- Una máquina aprovisionada con al menos un repositorio en ejecución (ver [Tutorial: Ciclo de vida del repositorio](/es/docs/tutorial-repos))

## Grabación interactiva

![Tutorial: Monitoreo y diagnósticos](/assets/tutorials/monitoring-tutorial.cast)

### Paso 1: Ejecutar diagnósticos

Comience verificando su entorno local en busca de problemas de configuración.

```bash
rdc doctor
```

Verifica Node.js, la versión de CLI, el binario de renet, la configuración y el soporte de virtualización. Cada verificación reporta **OK**, **Warning** o **Error**.

### Paso 2: Verificación de estado de la máquina

```bash
rdc machine health server-1
```

Obtiene un informe de salud completo de la máquina remota: tiempo de actividad del sistema, uso de disco, uso del almacén de datos, recuento de contenedores, estado SMART del almacenamiento y cualquier problema identificado.

### Paso 3: Ver contenedores en ejecución

```bash
rdc machine containers server-1
```

Lista todos los contenedores en ejecución en todos los repositorios de la máquina, mostrando nombre, estado, condición, salud, uso de CPU, uso de memoria y qué repositorio posee cada contenedor.

### Paso 4: Verificar servicios systemd

Para ver los servicios subyacentes que alimentan el Docker daemon y la red de cada repositorio:

```bash
rdc machine services server-1
```

Lista los servicios systemd relacionados con Rediacc (Docker daemons, alias de loopback) con su estado, subestado, conteo de reinicios y uso de memoria.

### Paso 5: Resumen del estado de la bóveda

```bash
rdc machine vault-status server-1
```

Proporciona una vista general de alto nivel de la máquina: nombre de host, tiempo de actividad, memoria, disco, almacén de datos y recuento total de repositorios.

### Paso 6: Escanear claves de host

Si una máquina fue reconstruida o su IP cambió, actualice la clave SSH de host almacenada.

```bash
rdc config machine scan-keys server-1
```

Obtiene las claves de host actuales del servidor y actualiza su configuración. Esto previene errores de "host key verification failed".

### Paso 7: Verificar conectividad

Una verificación rápida de conectividad SSH para confirmar que la máquina es accesible y responde.

```bash
rdc term server-1 -c "hostname"
rdc term server-1 -c "uptime"
```

El nombre de host confirma que está conectado al servidor correcto. El tiempo de actividad confirma que el sistema está funcionando normalmente.

## Solución de problemas

**La verificación de salud expira o muestra "SSH connection failed"**
Verifique que la máquina esté en línea y sea accesible: `ping <ip>`. Compruebe que su clave SSH esté configurada correctamente con `rdc term <machine> -c "echo ok"`.

**"Service not found" en el listado de servicios**
Los servicios de Rediacc solo aparecen después de que se haya desplegado al menos un repositorio. Si no existen repositorios, la lista de servicios está vacía.

**El listado de contenedores muestra contenedores obsoletos o detenidos**
Los contenedores de despliegues anteriores pueden permanecer si `repo down` no se ejecutó limpiamente. Deténgalos con `rdc repo down <repo> -m <machine>` o inspeccione directamente vía `rdc term <machine> <repo> -c "docker ps -a"`.

## Próximos pasos

Ejecutó diagnósticos, verificó el estado de la máquina, inspeccionó contenedores y servicios, y verificó la conectividad. Para trabajar con sus despliegues:

- [Monitoreo](/es/docs/monitoring) — referencia completa de todos los comandos de monitoreo
- [Solución de problemas](/es/docs/troubleshooting) — problemas comunes y soluciones
- [Tutorial: Herramientas](/es/docs/tutorial-tools) — terminal, sincronización de archivos e integración con VS Code
