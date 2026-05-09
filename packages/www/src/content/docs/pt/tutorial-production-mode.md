---
title: "Modo de Produção"
description: "Execute a sua aplicação desligada do seu computador portátil e sobreviva a reinícios do servidor com arranque automático."
category: "Tutorials"
subcategory: advanced
order: 10
language: pt
sourceHash: "0e070fcd877900ab"
---

# Modo de Produção

Até agora tem estado a executar a aplicação com `renet dev up` a partir do interior do repositório. Ótimo para desenvolvimento. Para produção, gere tudo a partir do seu computador portátil com `rdc` -- feche o portátil e a aplicação continua a funcionar.

## Ver o tutorial

![Tutorial: Production mode](/assets/tutorials/tutorial-production-mode.cast)

## Dev vs produção

A diferença é simples:

- `renet dev up` executa **dentro do repositório**. Precisa de estar ligado.
- `rdc repo up` executa **a partir do seu computador portátil**. Não é necessária ligação a seguir.

Três ações levam-no do desenvolvimento à produção:

![Stop, start, autostart](/img/tutorials/tutorial-production-mode/slide-1.svg)

## Passo 1: Parar a sessão de desenvolvimento

Ligue ao repositório e pare-o:

```bash
rdc vscode connect -m my-server -r my-app
time renet dev down
```

## Passo 2: Arrancar em modo de produção

A partir do terminal do seu computador portátil:

```bash
time rdc repo up --name my-app -m my-server
```

Pronto. A sua aplicação está a funcionar e pode fechar o portátil. O `Rediaccfile` trata de tudo -- `rdc repo up` chama a mesma função `up` que `renet dev up` chamava. O mesmo `Rediaccfile`, uma forma diferente de invocá-lo.

## Passo 3: Sobreviver a reinícios do servidor

Certifique-se de que a sua aplicação volta automaticamente quando o servidor reiniciar:

```bash
time rdc repo autostart enable --name my-app -m my-server
```

Verifique quais os repositórios com arranque automático ativado:

```bash
time rdc repo autostart list -m my-server
```

## Parar em produção

Quando precisar de parar a aplicação:

```bash
time rdc repo down --name my-app -m my-server
```

Um comando para arrancar, um comando para parar -- tudo a partir do seu computador portátil.

---

Próximo: [Backup e Restauro](/pt/docs/tutorial-backup-restore).
