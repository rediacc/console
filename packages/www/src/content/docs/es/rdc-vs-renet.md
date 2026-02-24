---
title: rdc vs renet
description: Cuándo usar rdc y cuándo usar renet.
category: Concepts
order: 1
language: es
sourceHash: e0ef5f051cefb407
---

# rdc vs renet

Rediacc tiene dos binarios. Aquí se explica cuándo usar cada uno.

| | rdc | renet |
|---|-----|-------|
| **Se ejecuta en** | Su estación de trabajo | El servidor remoto |
| **Se conecta vía** | SSH | Se ejecuta localmente con root |
| **Usado por** | Todos | Solo depuración avanzada |
| **Instalación** | Usted lo instala | `rdc` lo aprovisiona automáticamente |

> Para el trabajo diario, use `rdc`. Raramente necesitará `renet` directamente.

## Cómo Funcionan Juntos

`rdc` se conecta a su servidor mediante SSH y ejecuta comandos de `renet` por usted. Usted escribe un solo comando en su estación de trabajo, y `rdc` se encarga del resto:

1. Lee su configuración local (`~/.rediacc/rediacc.json`)
2. Se conecta al servidor mediante SSH
3. Actualiza el binario `renet` si es necesario
4. Ejecuta la operación correspondiente de `renet` en el servidor
5. Devuelve el resultado a su terminal

## Use `rdc` para el Trabajo Normal

Todas las tareas comunes se realizan a través de `rdc` en su estación de trabajo:

```bash
# Configurar un nuevo servidor
rdc config setup-machine server-1

# Crear e iniciar un repositorio
rdc repo create my-app -m server-1 --size 10G
rdc repo up my-app -m server-1 --mount

# Detener un repositorio
rdc repo down my-app -m server-1

# Verificar el estado de la máquina
rdc machine health server-1
```

Consulte el [Inicio Rápido](/es/docs/quick-start) para un recorrido completo.

## Use `renet` para Depuración en el Servidor

Solo necesita `renet` directamente cuando se conecta por SSH a un servidor para:

- Depuración de emergencia cuando `rdc` no puede conectarse
- Verificar detalles internos del sistema no disponibles a través de `rdc`
- Operaciones de recuperación de bajo nivel

Todos los comandos de `renet` necesitan privilegios de root (`sudo`). Consulte la [Referencia del Servidor](/es/docs/server-reference) para la lista completa de comandos de `renet`.

## Experimental: `rdc ops` (VMs Locales)

`rdc ops` envuelve `renet ops` para gestionar clústeres de VMs locales en su estación de trabajo:

```bash
rdc ops setup              # Instalar prerrequisitos (KVM o QEMU)
rdc ops up --basic         # Iniciar un clúster mínimo
rdc ops status             # Verificar el estado de las VMs
rdc ops ssh 1              # Conectarse por SSH a la VM puente
rdc ops ssh 1 hostname     # Ejecutar un comando en la VM puente
rdc ops down               # Destruir el clúster
```

> Requiere el adaptador local. No disponible con el adaptador cloud.

Estos comandos ejecutan `renet` localmente (no mediante SSH). Consulte [VMs Experimentales](/es/docs/experimental-vms) para la documentación completa.

## Nota sobre el Rediaccfile

Puede ver `renet compose -- ...` dentro de un `Rediaccfile`. Esto es normal — las funciones del Rediaccfile se ejecutan en el servidor donde `renet` está disponible.

Desde su estación de trabajo, inicie y detenga cargas de trabajo con `rdc repo up` y `rdc repo down`.
