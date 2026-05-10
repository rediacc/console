---
title: "Criar o Seu Primeiro Repositório"
description: "Crie um repositório encriptado no seu servidor e abra-o no VS Code."
category: "Tutorials"
subcategory: essentials
order: 4
language: pt
sourceHash: "1294b0494f20671b"
---

# Criar o Seu Primeiro Repositório

Um repositório Rediacc é um único ficheiro encriptado no seu servidor. Quando montado, torna-se uma pasta com o seu próprio daemon Docker e os seus próprios dados de aplicação -- completamente isolada, completamente portátil.

Pense nisto como uma pen USB para produção: um ficheiro em repouso, um servidor em execução.

## Ver o tutorial

![Tutorial: Creating your first repository](/assets/tutorials/tutorial-create-repo.cast)

## Ficheiro em disco, ambiente quando montado

![Encrypted file mounts as an isolated folder](/img/tutorials/tutorial-create-repo/slide-1.svg)

A forma em disco é uma única imagem encriptada. Quando monta, obtém:

- Um daemon Docker dedicado (separado do do servidor anfitrião)
- Dados da aplicação dentro do volume encriptado
- IPs de loopback que não colidem com nada mais no servidor

Os repositórios são portáteis. Pode mover um entre máquinas, fazer backup ou criar um fork instantaneamente. Cada repositório está isolado de todos os outros repositórios no mesmo servidor.

## Criar um

```bash
time rdc repo create --name my-app -m my-server --size 2G
```

Isto cria um repositório encriptado de 2 GB em `my-server`. Verifique:

```bash
time rdc repo list -m my-server
```

## Abri-lo no VS Code

```bash
rdc vscode connect -m my-server -r my-app
```

O VS Code abre diretamente dentro do repositório. Repare que o espaço de trabalho está vazio -- este é o seu ambiente isolado. Tudo o que criar aqui vive dentro do volume encriptado, invisível para qualquer outro repositório no mesmo servidor.

---

Próximo: [Implementar a Sua Primeira Aplicação](/pt/docs/tutorial-deploy-app).
