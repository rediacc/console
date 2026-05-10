---
title: "Instalación"
description: "Instala el CLI rdc en tu laptop con un solo comando y verifícalo con rdc doctor."
category: "Tutorials"
subcategory: essentials
order: 1
language: es
sourceHash: "99d4ca1a4f89278e"
---

# Instalación

Instalar `rdc` son tres pasos: abre la página de instalación, elige tu sistema operativo y pega el comando en tu terminal. Todo el proceso suele terminar en uno o dos minutos.

## Ver el tutorial

![Tutorial: Instalación](/assets/tutorials/tutorial-installation.cast)

## Los tres pasos

![Resumen de los tres pasos](/img/tutorials/tutorial-installation/slide-1.svg)

1. Abre la [página de instalación](/en/install).
2. Elige tu sistema operativo.
3. Copia el comando de instalación y pégalo en tu terminal.

## Instalar en tu plataforma

La página de instalación genera el comando adecuado para ti, pero aquí están los one-liners canónicos.

**Linux / macOS:**

```bash
time curl -fsSL https://www.rediacc.com/install.sh | bash
```

**Windows (PowerShell):**

```powershell
iwr -useb https://www.rediacc.com/install.ps1 | iex
```

> El prefijo `time` es un truco de shell que imprime cuánto tardó un comando. Lo usamos a lo largo de esta serie para que puedas ver la velocidad real de cada paso. Es opcional; puedes omitirlo si no lo necesitas.

## Verificar la instalación

Una vez que el script termine, comprueba que todo lo que `rdc` necesita esté presente:

```bash
time rdc doctor
```

`rdc doctor` revisa Node, SSH y el resto de las dependencias de `rdc`, e informa sobre cualquier problema.

## Por qué `rdc` vive en tu laptop

![rdc en tu laptop, renet en el servidor](/img/tutorials/tutorial-installation/slide-2.svg)

`rdc` es el CLI en tu laptop. El servidor ejecuta un componente separado llamado `renet`, que `rdc` provisiona y controla por SSH. Nunca necesitas conectarte por SSH a un servidor manualmente. `rdc` lo hace por ti.

Configuraremos eso correctamente en los próximos dos tutoriales.

---

Siguiente: [Configuración de claves SSH](/en/docs/tutorial-ssh-keys).
