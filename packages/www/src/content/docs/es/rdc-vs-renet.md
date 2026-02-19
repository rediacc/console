---
title: "rdc vs renet"
description: "Cuando usar rdc y cuando usar renet."
category: "Guides"
order: 1
language: es
---

# rdc vs renet

Rediacc usa dos binarios:

- `rdc` es la CLI orientada al usuario que ejecutas en tu workstation.
- `renet` es el binario remoto y de bajo nivel que se ejecuta en los servidores.

Para casi todas las operaciones del dia a dia, usa `rdc`.

## Modelo Mental

Piensa en `rdc` como el plano de control y en `renet` como el plano de datos.

`rdc`:
- Lee tu contexto local y mapeos de maquinas
- Se conecta a servidores por SSH
- Aprovisiona/actualiza `renet` cuando hace falta
- Ejecuta por ti la operacion remota correcta

`renet`:
- Se ejecuta con privilegios elevados en el servidor
- Gestiona datastore, volumenes LUKS, montajes y daemons Docker aislados
- Realiza operaciones de bajo nivel sobre repositorios y sistema

## Que Usar en la Practica

### Usa `rdc` (predeterminado)

Usa `rdc` para flujos normales:

```bash
rdc context setup-machine server-1
rdc repo create my-app -m server-1 --size 10G
rdc repo up my-app -m server-1 --mount
rdc repo down my-app -m server-1
rdc machine status server-1
```

### Usa `renet` (avanzado / lado remoto)

Usa `renet` directo solo cuando necesites control remoto de bajo nivel, por ejemplo:

- Depuracion de emergencia directamente en el servidor
- Mantenimiento y recuperacion a nivel host
- Verificacion de internals no expuestos por comandos de alto nivel de `rdc`

La mayoria de usuarios no necesita invocar `renet` directamente en tareas rutinarias.

## Nota sobre Rediaccfile

Puedes ver `renet compose -- ...` dentro de un `Rediaccfile`. Es esperado: las funciones de Rediaccfile se ejecutan en el lado remoto donde `renet` esta disponible.

Desde tu workstation, normalmente sigues iniciando/deteniendo cargas con `rdc repo up` y `rdc repo down`.
