---
title: "Configuração de Chave SSH"
description: "Configure a sua chave SSH para que o rdc possa ligar-se aos seus servidores sem palavras-passe."
category: "Tutorials"
subcategory: essentials
order: 2
language: pt
sourceHash: "009a1bd345e93413"
---

# Configuração de Chave SSH

O `rdc` liga-se aos seus servidores via SSH, por isso cada servidor precisa de confiar na sua chave SSH. Três passos no total -- dois são de configuração única, um repete-se para cada novo servidor que adicionar.

## Ver o tutorial

![Tutorial: SSH key configuration](/assets/tutorials/tutorial-ssh-keys.cast)

## Os três passos

![Generate, copy, register](/img/tutorials/tutorial-ssh-keys/slide-1.svg)

1. **Gere** uma chave SSH no seu computador portátil. Uma vez, para sempre.
2. **Copie-a** para o seu servidor. Repita para cada novo servidor.
3. **Registe** a chave no `rdc`. Uma vez, para sempre.

## Passo 1: Gerar uma chave

Se já tem uma chave que quer usar, avance. Caso contrário:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519
```

`ed25519` é o padrão moderno -- pequeno, rápido e bem suportado.

## Passo 2: Copiá-la para o seu servidor

```bash
ssh-copy-id -i ~/.ssh/id_ed25519 user@your-server-ip
```

Substitua `user` e `your-server-ip` pelo utilizador SSH e IP do seu servidor. Ser-lhe-á pedida a palavra-passe do servidor uma última vez. A partir daí, a autenticação por palavra-passe deixa de ser necessária.

## Passo 3: Registar a chave no `rdc`

```bash
time rdc config ssh set --key ~/.ssh/id_ed25519
```

Pronto. A partir de agora, todos os comandos `rdc` autenticam com esta chave. Sem mais palavras-passe, sem mais pedidos interativos.

---

Próximo: [Adicionar o Seu Primeiro Servidor](/pt/docs/tutorial-add-server).
