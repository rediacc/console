---
title: "Configuración de claves SSH"
description: "Configura tu clave SSH para que rdc pueda conectarse a tus servidores sin contraseñas."
category: "Tutorials"
subcategory: essentials
order: 2
language: es
sourceHash: "009a1bd345e93413"
---

# Configuración de claves SSH

`rdc` se conecta a tus servidores por SSH, así que cada servidor necesita confiar en tu clave SSH. Son tres pasos en total. Dos son configuración de una sola vez, y uno se repite por cada nuevo servidor que agregues.

## Ver el tutorial

![Tutorial: Configuración de claves SSH](/assets/tutorials/tutorial-ssh-keys.cast)

## Los tres pasos

![Generar, copiar, registrar](/img/tutorials/tutorial-ssh-keys/slide-1.svg)

1. **Generar** una clave SSH en tu laptop. Una vez, para siempre.
2. **Copiarla** a tu servidor. Se repite por cada nuevo servidor.
3. **Registrar** la clave en `rdc`. Una vez, para siempre.

## Paso 1: Generar una clave

Si ya tienes una clave que quieras usar, pasa al siguiente paso. De lo contrario:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519
```

`ed25519` es el estándar moderno: pequeño, rápido y ampliamente compatible.

## Paso 2: Copiarla a tu servidor

```bash
ssh-copy-id -i ~/.ssh/id_ed25519 user@your-server-ip
```

Reemplaza `user` y `your-server-ip` con el usuario SSH y la IP de tu servidor. Se te pedirá la contraseña del servidor por última vez. Después de esto, la autenticación por contraseña ya no será necesaria.

## Paso 3: Registrar la clave en `rdc`

```bash
time rdc config ssh set --key ~/.ssh/id_ed25519
```

Listo. A partir de ahora, cada comando de `rdc` se autentica con esta clave. Sin contraseñas, sin prompts interactivos.

---

Siguiente: [Agregar tu primer servidor](/en/docs/tutorial-add-server).
