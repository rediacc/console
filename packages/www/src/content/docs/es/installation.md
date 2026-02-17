---
title: "Instalacion"
description: "Instale la CLI de Rediacc en Linux, macOS o Windows."
category: "Getting Started"
order: 1
language: es
---

# Instalacion

Instale la CLI `rdc` en su estacion de trabajo. Esta es la unica herramienta que necesita instalar manualmente -- todo lo demas se gestiona automaticamente cuando configura las maquinas remotas.

## Linux y macOS

Ejecute el script de instalacion:

```bash
curl -fsSL https://get.rediacc.com | sh
```

Esto descarga el binario `rdc` en `$HOME/.local/bin/`. Asegurese de que este directorio este en su PATH:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

Agregue esta linea a su perfil de shell (`~/.bashrc`, `~/.zshrc`, etc.) para hacerla permanente.

## Windows

Ejecute el script de instalacion en PowerShell:

```powershell
irm https://www.rediacc.com/install.ps1 | iex
```

Esto descarga el binario `rdc.exe` en `%LOCALAPPDATA%\rediacc\bin\`. Asegurese de que este directorio este en su PATH. El instalador le pedira que lo agregue si aun no esta presente.

## Verificar la Instalacion

```bash
rdc --version
```

Deberia ver el numero de version instalado.

## Actualizar

Para actualizar `rdc` a la ultima version:

```bash
rdc update
```

Para buscar actualizaciones sin instalar:

```bash
rdc update --check-only
```

Para revertir a la version anterior despues de una actualizacion:

```bash
rdc update rollback
```
