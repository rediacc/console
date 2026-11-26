---
title: "Respuesta a incidentes: investigar, declarar y conservar la evidencia"
description: "Abra una investigación sobre un repositorio o una máquina, lea una línea de tiempo única de auditoría, ejecuciones, flujos y aperturas de archivos, verifique las cadenas de hash, declare un incidente para congelar la evidencia e iniciar los relojes de 24 horas, 72 horas y un mes, y maneje todo desde rdc."
category: "Guides"
tags:
  - security
  - compliance
subcategory: data-protection
order: 10
language: es
sourceHash: "0e7681b5366968f0"
sourceCommit: "f9ac63ac37dff49f6c980f00fdacb7e41099ce81"
---

# Respuesta a incidentes

Aquí, un incidente es el que ocurre dentro de los repositorios del propio cliente. La página de investigación, los comandos `rdc incident` y los lectores `rdc repo flows` y `rdc repo opens` trabajan con los registros descritos en [análisis forense](/es/docs/forensics). Los incidentes en los sistemas de Rediacc siguen la [respuesta a incidentes de seguridad](/es/docs/security-incident-response).

## Acceso

La investigación exige un plan de pago y el rol de propietario o administrador. Abrir una investigación pide una reautenticación reciente, y una investigación abierta sigue siendo válida durante 60 minutos. Cada consulta se escribe en el registro de auditoría.

El soporte de Rediacc solo ve datos forenses con una autorización de soporte que emite el cliente. Una autorización dura como máximo 7 días y se puede revocar en cualquier momento.

Las lecturas de la CLI necesitan el scope `forensics:read`, y declarar y cerrar necesitan `incident:manage`. Un inicio de sesión de la CLI incluye ambos para propietarios y administradores tras una aprobación elevada en el navegador. Cuando un comando responde que hace falta una aprobación elevada reciente, el portal de la cuenta la solicita y el comando se vuelve a ejecutar.

## La línea de tiempo

La página Investigate fusiona un ámbito (un repositorio o una máquina) en una sola línea de tiempo con cinco tipos de fila: eventos de auditoría de la consola, ejecuciones, flujos de red, aperturas de archivos y anomalías. Los cambios desde la última instantánea se pueden comparar con ella. Un control deslizante de ventana temporal fija la ventana, y una ventana abarca como máximo 31 días.

Un tramo sin evidencia aparece como una fila de hueco que nombra la máquina y el motivo, nunca como un tramo vacío. Sobre las filas hay un gráfico de bytes salientes por minuto y una lista de los destinos principales.

Las mismas lecturas están disponibles desde la línea de comandos:

```bash
rdc repo flows mail --since 24h
rdc repo flows mail --since 2026-11-20T00:00:00Z --until 2026-11-21T00:00:00Z
rdc repo opens mail --since 7d
```

`--since` y `--until` aceptan un instante ISO 8601 o un intervalo hacia atrás desde ahora como `90m`, `24h` o `7d`. La ventana predeterminada son las últimas 24 horas. Las filas de flujo muestran hora, proceso, destino, bytes de salida y entrada, y ASN y país si se conocen. Las filas de apertura muestran hora, proceso y ruta, con las rutas sensibles marcadas.

## Verificar la evidencia

Verify evidence recalcula en el navegador la cadena de hash de los archivos diarios de auditoría y las cadenas de lotes firmados de los registros forenses para la ventana, y lista cada hueco y cada edición. Las firmas de los lotes se comprueban con las claves de spool que el servidor de cuentas fijó para cada máquina. Nunca se confía en una clave escrita dentro de la evidencia. El resultado se estampa en los informes exportados.

La evidencia de más de 2 GiB es demasiado grande para el navegador. El mismo módulo se ejecuta desde la línea de comandos:

```bash
rdc forensics verify --dir ./incident-evidence
rdc forensics verify --dir ./incident-evidence --since 7d --machine-key web-1=<public-key-hex>
```

El comando termina con código 1 cuando encuentra algún hueco o edición. `--machine-key <machine>=<public-key-hex>` (la clave tiene 64 caracteres hexadecimales) aporta una clave externa al directorio y se puede repetir. Una máquina sin clave externa falla.

## Declarar un incidente

Declarar congela la evidencia. Primero se registra el incidente en la cuenta y después se prepara el repositorio para la investigación:

1. El incidente se registra con su ventana, quién lo declaró y cuándo tuvo conocimiento la organización.
2. Una retención de expulsión cubre la ventana, y las reglas de bloqueo del bucket se extienden sobre ella, de modo que FIFO no puede eliminar esos días.
3. El repositorio se bifurca como instantánea forense, con la etiqueta `incident-<id>`.
4. El nivel de captura del repositorio pasa a Full.

Tres relojes arrancan desde el momento de conocimiento, que puede fijarse antes de la declaración y nunca después: la alerta temprana vence 24 horas después del conocimiento, la notificación 72 horas después y el informe final un mes natural después de la notificación (contado desde el plazo de notificación hasta que se registra una notificación). La página muestra cada reloj como pendiente, vence en menos de 6 horas, vencido o hecho.

```bash
rdc incident declare mail
rdc incident declare mail --since 48h --aware-at 2026-11-20T09:30:00Z
rdc incident status
rdc incident status <id>
```

Un paso fallido en la máquina deja el registro y su retención en su sitio, termina con código 1 y nombra el comando que vuelve a ejecutar solo los pasos fallidos:

```bash
rdc incident declare mail --resume <id>
```

`--resume` conserva la ventana y el conocimiento de la declaración original, por lo que `--since`, `--until` y `--aware-at` no se combinan con él.

## Exportar la evidencia

`rdc incident export` escribe la ventana del incidente en un directorio: el registro del incidente con sus relojes, la línea de tiempo fusionada, los agregados de bytes salientes, el manifiesto de cadena sin procesar y los archivos sin procesar que enumera. Cuando el manifiesto lista archivos diarios de auditoría o archivos de cabeceras forenses, las cadenas se verifican por el camino y el resultado va a `verification.json`. El comando termina con código 1 cuando la evidencia muestra un hueco o una edición.

```bash
rdc incident export <id>
rdc incident export <id> --out ./incident-evidence
```

Con `--stage`, el mismo comando escribe en su lugar un informe firmado. Consulte los [informes de incidentes](/es/docs/incident-reports).

## Cerrar un incidente

```bash
rdc incident close <id>
```

Nada se libera de inmediato. La retención de expulsión y las reglas de bloqueo del bucket terminan 30 días después del cierre.

## Preguntar a la IA

La página de investigación tiene un asistente que responde preguntas sobre el ámbito y la ventana abiertos. Solo lee ese ámbito y esa ventana, con un ticket de un solo uso generado desde la investigación abierta, que se puede canjear durante 15 minutos. La pregunta y las filas que lee van al proveedor de IA propio de la organización. El asistente puede ejecutar los comandos `rdc` anteriores con las mismas reglas de permisos que cualquier otro comando.

## Comandos

| Comando | Finalidad |
|---|---|
| `rdc repo flows <ref>` | Flujos de red de un repositorio en una ventana |
| `rdc repo opens <ref>` | Aperturas de archivos sensibles de un repositorio en una ventana |
| `rdc forensics level <ref> <level>` | Establecer el nivel de captura |
| `rdc forensics verify` | Verificar un directorio de evidencia o un informe firmado |
| `rdc incident declare <ref>` | Registrar un incidente, bifurcar el repositorio y pasar a Full |
| `rdc incident status [id]` | Listar incidentes, o mostrar uno con sus relojes |
| `rdc incident export <id>` | Escribir la ventana de evidencia, o un informe firmado con `--stage` |
| `rdc incident close <id>` | Cerrar un incidente |
