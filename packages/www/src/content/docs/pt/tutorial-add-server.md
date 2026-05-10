---
title: "Adicionar o Seu Primeiro Servidor"
description: "Registe o seu primeiro servidor no rdc, provisione-o e compreenda a configuração e arquitectura rdc + renet."
category: "Tutorials"
subcategory: essentials
order: 3
language: pt
sourceHash: "2b5de59f61cfb88c"
---

# Adicionar o Seu Primeiro Servidor

Antes de adicionar um servidor, é útil perceber como o `rdc` funciona. O Rediacc tem uma arquitetura de duas ferramentas: `rdc` no seu computador portátil e `renet` no servidor.

## Ver o tutorial

![Tutorial: Adding your first server](/assets/tutorials/tutorial-add-server.cast)

## Porquê duas ferramentas?

![rdc on laptop, renet on server, SSH between](/img/tutorials/tutorial-add-server/slide-1.svg)

- **`rdc`** é o CLI no seu computador portátil. Aqui escreve os comandos.
- **`renet`** é o orquestrador no servidor. Gere a encriptação, o Docker e o isolamento.

Quando executa um comando localmente, o `rdc` liga-se via SSH e executa o `renet` no servidor. Nunca precisa de fazer SSH para os seus servidores manualmente -- o `rdc` faz isso por si.

## Passo 1: Registar o servidor

Diga ao `rdc` quem é o servidor. Substitua o nome, IP e utilizador pelos seus.

```bash
time rdc config machine add --name my-server --ip 192.168.1.100 --user deploy
```

## Passo 2: Provisioná-lo

O setup instala o `renet` e cria o armazenamento de dados encriptado no servidor.

```bash
time rdc config machine setup --name my-server
```

Quando concluir, o seu servidor está pronto para alojar repositórios.

## Onde fica a configuração

Verifique o que o `rdc` sabe sobre a sua configuração:

```bash
time rdc config show
```

Ou abra o ficheiro JSON diretamente:

```bash
vim ~/.config/rediacc/rediacc.json
```

Este único ficheiro contém tudo: máquinas, repositórios, chave SSH e credenciais de encriptação. Copie-o para outro computador portátil e estará pronto para trabalhar a partir dessa máquina também.

---

Próximo: [Criar o Seu Primeiro Repositório](/pt/docs/tutorial-create-repo).
