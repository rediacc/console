---
title: Proxy y ejecutor
description: Cómo se ejecutan los comandos del navegador y de clientes ligeros sin que el cliente tenga nunca claves SSH ni direcciones de máquina
category: Concepts
tags:
  - security
  - networking
order: 4
language: es
sourceHash: "39ec44d8efc3f9b5"
sourceCommit: "5197d1c0349438c2bff2442377a5166d0b8214b6"
---

# Proxy y ejecutor

Normalmente, `rdc` se ejecuta en su máquina con su configuración y sus claves SSH, y se conecta directamente a sus servidores. El modelo de proxy divide esto en dos: un cliente ligero que no tiene ningún secreto, y un **ejecutor** que sí los tiene y realiza el trabajo. El botón Ejecutar de la [consola web](/es/docs/web-console) y el flag `--proxy` del CLI son ambos clientes ligeros, y hablan el mismo protocolo de transporte.

## Intención del comando, no comandos

Un cliente ligero nunca tiene una clave SSH, una dirección de máquina ni una configuración descifrada. Cuando quiere ejecutar algo, envía solo la intención del comando: un identificador del comando (su ruta en el contrato del CLI, por ejemplo `repo up`) más los parámetros. El ejecutor busca el comando en ese mismo contrato, lo resuelve a la función del lado del servidor correspondiente, resuelve la máquina de destino a partir de la configuración descifrada y lo ejecuta a través de su propia conexión SSH. La salida se transmite de vuelta al cliente.

El ejecutor es el propio CLI, iniciado como servidor con `rdc serve`. El mismo binario que los operadores ejecutan en un portátil se convierte en lo que ejecuta comandos en su nombre. Tiene dos ubicaciones posibles:

- **`--mode daemon`**: se ejecuta en un host que usted controla, inscrito de forma headless como cualquier CLI (vea [Almacenamiento de configuración](/es/docs/config-storage)), de modo que puede derivar por sí solo la clave de configuración y no necesita una concesión por sesión. Este es el nivel estricto: el SSH nunca sale de su red.
- **`--mode container`**: se ejecuta en un contenedor alojado para usted, asociado a su organización. Arranca sin ninguna clave y no puede hacer nada hasta que un cliente le conceda una para la sesión. Este es el nivel de conveniencia.

## La concesión de la CEK

El almacenamiento de configuración es de conocimiento cero: el servidor solo almacena blobs cifrados, y la clave de cifrado de contenido (CEK) existe en claro únicamente en un cliente que la haya desbloqueado. Por eso, a un ejecutor en modo contenedor hay que *concederle* la clave, y esa concesión no debe exponerla al servidor en ningún momento intermedio.

El flujo es el siguiente: un navegador desbloqueado abre una sesión con el ejecutor, recibe la clave pública de esa sesión y sella la CEK para esa sesión mediante X25519. El blob sellado viaja a través del servidor de la cuenta, pero el servidor no puede abrirlo, así que la propiedad de conocimiento cero se mantiene de extremo a extremo. El ejecutor descifra la CEK solo en RAM, con una expiración por inactividad de 30 minutos; nunca se escribe nada en disco. Las siguientes solicitudes de comandos hacen referencia a la sesión concedida mediante la cabecera `X-Config-Session`.

Un detalle importa para la auditoría: la misma identidad de usuario recorre las tres etapas (abrir la sesión, conceder la clave, ejecutar comandos). El servidor de la cuenta nunca reenvía su propia credencial al ejecutor. Para cada etapa emite un token de corta duración atribuido al usuario real, y vuelve a comprobar la pertenencia de ese usuario cada vez. El ejecutor verifica el token que se le presente, sea cual sea, antes de actuar. Una concesión hecha por un usuario no puede ser usada por otro.

La mitad de `state` de una configuración (datos de ejecución locales al host) nunca viaja dentro del blob de configuración, así que tampoco llega nunca a un ejecutor por esta vía.

## Qué puede ejecutarse a través de un proxy

No todos los comandos tienen sentido de forma remota. Cada comando del contrato lleva un flag `proxyCapable`, y el ejecutor lo hace cumplir del lado del servidor, con independencia de cualquier configuración de política:

- Los **comandos del plano de máquina, no interactivos** (deploy, backup, status, logs, etc.) son aptos para proxy.
- Los **comandos del plano de configuración** no lo son: editan la configuración, lo cual, en esta vía, es tarea del navegador (la consola web los dirige a su editor de configuración en su lugar).
- Los **comandos interactivos** (terminales, sesiones de VS Code) no lo son: no hay TTY a través de este canal.
- Los **comandos de transferencia del lado del cliente** (`rdc repo sync`) no lo son: mueven datos entre el sistema de archivos del *cliente* y una máquina, y el ejecutor no tiene los archivos del cliente.

La consola web lee ese mismo flag para decidir si un comando recibe o no un botón Ejecutar, pero el ejecutor rechaza los comandos no aptos sin importar lo que envíe el cliente.

## El ejecutor simulado

En desarrollo, cuando no hay un ejecutor real configurado, el servidor de la cuenta responde él mismo a las solicitudes de comandos con flujos simulados y datos claramente falsos (nombres de recursos con el prefijo `mock-`). Esto permite ejercitar toda la consola, incluidos formularios, streaming y renderizado de resultados, sin necesidad de una máquina ni de un desbloqueo. La ejecución real requiere un ejecutor real.

## Relacionado

- [Consola web](/es/docs/web-console), el cliente de navegador construido sobre este modelo
- [Almacenamiento de configuración](/es/docs/config-storage), el almacén de conocimiento cero que protege la CEK
