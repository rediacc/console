---
title: Consola web
description: Ejecute todo el CLI rdc desde su navegador, con formularios, selectores de recursos e historial de ejecuciones
category: Guides
tags:
  - cli
  - account
subcategory: cli-tools
order: 8
language: es
sourceHash: "972ed654ae294102"
sourceCommit: "5197d1c0349438c2bff2442377a5166d0b8214b6"
---

# Consola web

La consola web es una interfaz de navegador sobre todo el CLI `rdc`. Cada comando del CLI aparece en la consola con un formulario, validación, selectores de recursos y un botón Ejecutar. No existe un "conjunto de funciones web" aparte: la consola se genera a partir del contrato del CLI, así que cualquier comando que tenga el CLI, lo tiene también la consola, y los comandos nuevos aparecen automáticamente.

Se encuentra en el portal web, en `/account/console`.

## Disponibilidad

La consola web es una función de pago. Está incluida en los planes de pago y oculta en el plan Community. El acceso también está controlado por rol, así que un administrador de la organización puede decidir quién la ve.

## Su relación con el almacenamiento de configuración

La consola lee sus recursos (máquinas, repositorios, etc.) desde su almacén de configuración cifrado, y descifra esa configuración únicamente en el navegador. Eso implica que:

- **Mientras está bloqueada**, aún puede explorar todo el catálogo de comandos, abrir el formulario de cualquier comando y leer sus parámetros. Esto funciona sin ninguna configuración previa.
- **Para ejecutar comandos y usar los selectores**, primero debe desbloquear su almacén de configuración (passkey, contraseña maestra o código de recuperación, vea [Almacenamiento de configuración](/es/docs/config-storage)). Los botones Ejecutar, las páginas de recursos y los selectores de recursos dependen todos de la sesión desbloqueada.

La clave descifrada permanece solo en la memoria del navegador. Al recargar la página, la consola vuelve a bloquearse, y 30 minutos de inactividad la bloquean automáticamente.

## Selectores de recursos

Una vez desbloqueados, los formularios de comandos sustituyen los campos de texto libre por selectores alimentados desde su configuración descifrada: máquinas, repositorios, datastores, almacenamientos, clústeres, proveedores de nube y estrategias de backup. Algunos selectores se resuelven en vivo en su lugar, ejecutando un comando, por ejemplo los contenedores de una máquina o las instantáneas de un datastore.

Los selectores filtran de forma dependiente: elija una máquina y el selector de repositorios se acota a esa máquina. Para las referencias de repositorio, un constructor de referencias compone la forma completa `nombre:etiqueta@máquina` a partir de selecciones individuales. Los selectores son sugerencias, no restricciones, y siempre puede escribir un valor manualmente.

## Ejecución de comandos

El navegador nunca tiene una clave SSH ni una dirección de máquina. Cuando hace clic en Ejecutar, la consola envía solo la intención del comando (qué comando y qué parámetros), y un ejecutor resuelve todo lo demás y lo ejecuta. Vea [Proxy y ejecutor](/es/docs/proxy-and-executor) para saber cómo funciona esto y qué comandos pueden ejecutarse de esta forma.

Los comandos que solo editan su configuración (por ejemplo, crear una entrada de máquina) no se ejecutan de forma remota en absoluto. La consola los dirige al editor de configuración integrado, donde el cambio se cifra y se envía como cualquier otra edición de configuración.

Cada formulario también muestra la línea de comando CLI equivalente, así que cualquier cosa que configure en la consola puede copiarse directamente a una terminal o a un script.

## Cómo orientarse

- **Páginas de recursos**: las máquinas, los repositorios y las tareas tienen cada uno páginas de listado y de detalle, con los comandos relevantes disponibles como acciones.
- **Paleta de comandos**: pulse Cmd-K (Ctrl-K) para saltar a cualquier comando o recurso por su nombre.
- **Historial de ejecuciones**: las ejecuciones pasadas se conservan por sesión, así que puede revisar la salida y volver a ejecutar con los mismos parámetros.

## Relacionado

- [Almacenamiento de configuración](/es/docs/config-storage), configurar y desbloquear el almacén de configuración cifrado
- [Proxy y ejecutor](/es/docs/proxy-and-executor), el modelo de ejecución detrás del botón Ejecutar
