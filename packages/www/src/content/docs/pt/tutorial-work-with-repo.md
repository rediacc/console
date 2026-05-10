---
title: "Trabalhar com o Seu Repositório"
description: "Encaminhe uma porta para o seu browser, execute comandos dentro do sandbox e sincronize ficheiros entre o seu computador portátil e o repositório."
category: "Tutorials"
subcategory: essentials
order: 6
language: pt
sourceHash: "3d56eb69e72c1a5a"
---

# Trabalhar com o Seu Repositório

A sua aplicação está a correr, mas até agora só a viu através do `docker ps`. Três comandos cobrem o fluxo de trabalho diário: **tunnel** para ver a aplicação num browser, **term** para executar comandos dentro do sandbox, **sync** para mover ficheiros entre o seu computador portátil e o repositório.

## Ver o tutorial

![Tutorial: Working with your repo](/assets/tutorials/tutorial-work-with-repo.cast)

## Os três diários

![Tunnel, term, sync](/img/tutorials/tutorial-work-with-repo/slide-1.svg)

1. **Tunnel** -- abra a sua aplicação num browser.
2. **Term** -- execute um comando dentro do sandbox.
3. **Sync** -- mova ficheiros para dentro e para fora.

## Tunnel: ver a sua aplicação num browser

A aplicação corre no servidor, não no seu computador portátil. Encaminhe a porta de um contentor via SSH:

```bash
rdc repo tunnel -m my-server -r my-app -c app
```

Abra `localhost` no seu browser -- a sua aplicação está mesmo ali. Prima `Ctrl+C` quando terminar.

Para um contentor diferente, troque `-c` e escolha a porta:

```bash
rdc repo tunnel -m my-server -r my-app -c db --port 5432
```

## Term: executar comandos dentro do repositório

Ignore o VS Code quando só precisa de uma shell:

```bash
rdc term connect -m my-server -r my-app
```

Está agora dentro do sandbox do repositório. Experimente:

```bash
time docker ps
```

Vê apenas os contentores de `my-app` -- a mesma vista que veria no VS Code.

Para comandos pontuais, use `-c` e ignore a shell interativa:

```bash
time rdc term connect -m my-server -r my-app -c "df -h ."
```

## Sync: mover ficheiros entre computador portátil e repositório

Envie uma pasta do seu computador portátil para o repositório:

```bash
time rdc repo sync upload -m my-server -r my-app --local ./src
```

Puxe ficheiros de volta:

```bash
time rdc repo sync download -m my-server -r my-app --local ./backup
```

Pré-visualize primeiro se tiver dúvidas -- `--dry-run` mostra o que seria alterado sem copiar realmente:

```bash
time rdc repo sync upload -m my-server -r my-app --local ./src --dry-run
```

Tunnel, term, sync. Três comandos cobrem o ciclo diário.

---

Próximo: [Criar um Fork de um Repositório](/pt/docs/tutorial-forking).
