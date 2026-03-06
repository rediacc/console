---
title: "Ciclo de vida del repositorio"
description: "Crear un repositorio cifrado, desplegar una aplicación en contenedores, inspeccionar contenedores y limpiar."
category: "Tutorials"
order: 3
language: es
sourceHash: "e6c55c46e8e4cd9c"
---

# Cómo desplegar y gestionar repositorios con Rediacc

Los repositorios son la unidad de despliegue principal en Rediacc — cada uno es un entorno aislado y cifrado con su propio Docker daemon y almacenamiento dedicado. En este tutorial, crearás un repositorio cifrado, desplegarás una aplicación en contenedores, inspeccionarás los contenedores en ejecución y limpiarás. Al finalizar, habrás completado un ciclo de despliegue completo.

## Requisitos previos

- El CLI `rdc` instalado con una configuración inicializada
- Una máquina aprovisionada (ver [Tutorial: Configuración de máquina](/es/docs/tutorial-setup))
- Una aplicación sencilla con un `Rediaccfile` y `docker-compose.yml`

## Grabación interactiva

![Tutorial: Ciclo de vida del repositorio](/assets/tutorials/repos-tutorial.cast)

### Paso 1: Crear un repositorio cifrado

Cada repositorio obtiene su propio volumen de almacenamiento cifrado con LUKS. Especifica la máquina y el tamaño del almacenamiento.

```bash
rdc repo create test-app -m server-1 --size 2G
```

Rediacc crea un volumen cifrado de 2 GB, lo formatea y lo monta automáticamente. El repositorio está listo para subir archivos.

### Paso 2: Listar repositorios

Confirma que el nuevo repositorio está disponible.

```bash
rdc repo list -m server-1
```

Muestra todos los repositorios en la máquina con su tamaño, estado de montaje y estado de cifrado.

### Paso 3: Inspeccionar la ruta de montaje

Antes de desplegar, verifica que el almacenamiento del repositorio está montado y accesible.

```bash
rdc term server-1 -c "ls -la /mnt/rediacc/mounts/test-app/"
```

El directorio de montaje es donde residen los archivos de la aplicación — `Rediaccfile`, `docker-compose.yml` y cualquier volumen de datos.

### Paso 4: Iniciar servicios

Despliega la aplicación montando el repositorio e iniciando sus servicios Docker.

```bash
rdc repo up test-app -m server-1 --mount
```

Esto monta el repositorio (si no está ya montado), inicia un Docker daemon aislado, descarga imágenes mediante `prep()` e inicia servicios mediante `up()`.

> **Nota:** El primer despliegue tarda más ya que se descargan las imágenes Docker. Los inicios posteriores reutilizan las imágenes en caché.

### Paso 5: Ver contenedores en ejecución

```bash
rdc machine containers server-1
```

Muestra todos los contenedores en ejecución en todos los repositorios de la máquina, incluyendo el uso de CPU y memoria.

### Paso 6: Acceder al terminal del repositorio

Para ejecutar comandos dentro del entorno Docker aislado del repositorio:

```bash
rdc term server-1 test-app -c "docker ps"
```

La sesión de terminal establece `DOCKER_HOST` al socket Docker aislado del repositorio. Cualquier comando Docker se ejecuta solo contra los contenedores de ese repositorio.

### Paso 7: Detener y limpiar

Cuando hayas terminado, detén los servicios, cierra el volumen cifrado y opcionalmente elimina el repositorio.

```bash
rdc repo down test-app -m server-1      # Detener servicios
rdc repo unmount test-app -m server-1   # Cerrar volumen cifrado
rdc repo delete test-app -m server-1    # Eliminar repositorio permanentemente
```

`down` detiene los contenedores y el Docker daemon. `unmount` cierra el volumen LUKS. `delete` elimina permanentemente el repositorio y su almacenamiento cifrado.

> **Advertencia:** `repo delete` es irreversible. Todos los datos del repositorio se destruyen. Crea una copia de seguridad primero si es necesario.

## Solución de problemas

**"Espacio en disco insuficiente" durante la creación del repositorio**
El volumen cifrado necesita espacio libre contiguo en el host. Verifica el espacio disponible con `df -h` en el servidor. Considera un valor `--size` más pequeño o libera espacio en disco.

**Tiempo de espera agotado al descargar imagen Docker durante `repo up`**
Las imágenes grandes pueden agotar el tiempo de espera en conexiones lentas. Reintenta con `rdc repo up` — reanuda donde se detuvo. Para entornos aislados, precarga las imágenes en el Docker daemon del repositorio.

**"Fallo de montaje" o "Fallo al abrir LUKS"**
La contraseña LUKS se deriva de la configuración. Verifica que estás usando la misma configuración que creó el repositorio. Si el volumen ya está montado por otro proceso, desmóntalo primero.

## Próximos pasos

Has creado un repositorio cifrado, desplegado una aplicación, inspeccionado contenedores y limpiado. Para monitorear tus despliegues:

- [Servicios](/es/docs/services) — referencia de Rediaccfile, redes de servicios, autoinicio y diseños multi-servicio
- [Tutorial: Monitoreo y diagnóstico](/es/docs/tutorial-monitoring) — comprobaciones de salud, inspección de contenedores y diagnóstico
- [Herramientas](/es/docs/tools) — terminal, sincronización de archivos e integración con VS Code
