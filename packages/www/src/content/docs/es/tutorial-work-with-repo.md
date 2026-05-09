---
title: "Trabajar con tu repo"
description: "Tuneliza un puerto hacia tu navegador, ejecuta comandos dentro del sandbox y sincroniza archivos entre tu laptop y el repo."
category: "Tutorials"
subcategory: essentials
order: 6
language: es
sourceHash: "3d56eb69e72c1a5a"
---

# Trabajar con tu repo

Tu app está en ejecución, pero hasta ahora solo la has visto a través de `docker ps`. Tres comandos cubren el flujo de trabajo diario: **tunnel** para ver la app en un navegador, **term** para ejecutar comandos dentro del sandbox, **sync** para mover archivos entre tu laptop y el repo.

## Ver el tutorial

![Tutorial: Trabajar con tu repo](/assets/tutorials/tutorial-work-with-repo.cast)

## El trío del día a día

![Tunnel, term, sync](/img/tutorials/tutorial-work-with-repo/slide-1.svg)

1. **Tunnel**: abre tu app en un navegador.
2. **Term**: ejecuta un comando dentro del sandbox.
3. **Sync**: mueve archivos hacia dentro y hacia fuera.

## Tunnel: ver tu app en un navegador

La app se ejecuta en el servidor, no en tu laptop. Reenvía el puerto de un contenedor por SSH:

```bash
rdc repo tunnel -m my-server -r my-app -c app
```

Abre `localhost` en tu navegador. Tu app aparece ahí mismo. Presiona `Ctrl+C` cuando termines.

Para un contenedor diferente, cambia `-c` y elige el puerto:

```bash
rdc repo tunnel -m my-server -r my-app -c db --port 5432
```

## Term: ejecutar comandos dentro del repo

Omite VS Code cuando solo necesitas una shell:

```bash
rdc term connect -m my-server -r my-app
```

Ahora estás dentro del sandbox del repo. Pruébalo:

```bash
time docker ps
```

Solo ves los contenedores de `my-app`, la misma vista que tendrías en VS Code.

Para comandos puntuales, usa `-c` y omite la shell interactiva:

```bash
time rdc term connect -m my-server -r my-app -c "df -h ."
```

## Sync: mover archivos entre la laptop y el repo

Sube una carpeta desde tu laptop al repo:

```bash
time rdc repo sync upload -m my-server -r my-app --local ./src
```

Descarga archivos de vuelta:

```bash
time rdc repo sync download -m my-server -r my-app --local ./backup
```

Si no estás seguro, previsualiza primero. `--dry-run` muestra qué cambiaría sin copiar nada:

```bash
time rdc repo sync upload -m my-server -r my-app --local ./src --dry-run
```

Tunnel, term, sync. Tres comandos cubren el ciclo diario.

---

Siguiente: [Fork de un repositorio](/en/docs/tutorial-forking).
