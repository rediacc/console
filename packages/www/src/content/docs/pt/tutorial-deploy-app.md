---
title: "Implementar a Sua Primeira Aplicação"
description: "Implemente uma aplicação em contentor a partir de um modelo integrado usando renet dev up."
category: "Tutorials"
subcategory: essentials
order: 5
language: pt
sourceHash: "f75b5b6a716e94bf"
---

# Implementar a Sua Primeira Aplicação

Tem um repositório vazio. O `rdc` inclui modelos integrados para que possa lançar aplicações reais sem escrever um `docker-compose` do zero. Três passos: escolha um modelo, aplique-o, execute-o.

## Ver o tutorial

![Tutorial: Deploying your first app](/assets/tutorials/tutorial-deploy-app.cast)

## Escolher · Aplicar · Executar

![Pick a template, apply it, run it](/img/tutorials/tutorial-deploy-app/slide-1.svg)

## Passo 1: Escolher

Navegue pelos modelos disponíveis:

```bash
time rdc repo template list
```

Verá configurações prontas para aplicações comuns -- Postgres, Redis, servidores web e mais.

## Passo 2: Aplicar

Coloque o modelo no seu repositório. Usaremos `app-postgres`:

```bash
time rdc repo template apply --name app-postgres -m my-server -r my-app
```

Dois novos ficheiros aparecem no repositório: `docker-compose.yml` e `Rediaccfile`. O ficheiro compose descreve os contentores; o `Rediaccfile` define o que acontece quando a aplicação arranca e para -- os seus hooks de ciclo de vida `up` e `down`.

## Passo 3: Executar

Já está dentro do sandbox do repositório (via a ligação VS Code do tutorial anterior), por isso use o `renet` diretamente:

```bash
time renet dev up
```

Pronto -- a sua aplicação está a funcionar. Verifique:

```bash
time docker ps
```

`docker ps` aqui lista apenas os contentores deste repositório. Os outros repositórios no mesmo servidor têm os seus próprios daemons Docker e são completamente invisíveis a partir deste.

---

Próximo: [Trabalhar com o Seu Repositório](/pt/docs/tutorial-work-with-repo).
