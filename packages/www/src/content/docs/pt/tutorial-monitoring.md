---
title: "Monitorização"
description: "Verifique o estado de saúde dos seus servidores e repositórios a partir do seu computador portátil com os comandos rdc machine."
category: "Tutorials"
subcategory: advanced
order: 12
language: pt
sourceHash: "e6eaaed180c35e36"
sourceCommit: "be90e8e7896623c088b86360ec29c1baef2e86b4"
---

# Monitorização

A sua aplicação está implementada, em produção e com backup. Agora certifique-se de que tudo continua saudável. O `rdc` dá-lhe uma visão completa de qualquer servidor -- saúde, contentores, repositórios -- tudo a partir do seu computador portátil.

## Ver o tutorial

![Tutorial: Monitoring](/assets/tutorials/tutorial-monitoring.cast)

## Três coisas que pode verificar

![Health, containers, repos](/img/tutorials/tutorial-monitoring/slide-1.svg)

## Saúde

Comece com uma verificação de saúde:

```bash
time rdc machine health --name my-server
```

Mostra o tempo de atividade do sistema, uso do disco, saúde dos contentores e estado do armazenamento. Se algo estiver errado, diz-lho.

## Contentores

Para ver todos os contentores em execução em todos os repositórios da máquina:

```bash
time rdc machine containers --name my-server
```

Obtém nome, estado, saúde, CPU e memória para cada contentor, mais qual o repositório a que pertence.

## Repositórios

Para verificar os seus repositórios:

```bash
time rdc machine repos --name my-server
```

Mostra cada repositório com o seu tamanho, estado de montagem, estado Docker e uso do disco.

## Tudo de uma vez

```bash
time rdc machine query --name my-server
```

Informação do sistema, repositórios, contentores -- tudo num único comando.

## Verificação local

`rdc doctor` verifica a sua configuração local -- Node, chave SSH, `renet`, Docker -- independentemente de qualquer servidor específico:

```bash
time rdc doctor
```

## Terminou

Esta é a série completa. Pode agora instalar, configurar, implementar, criar forks, passar para produção, configurar arranque automático, fazer backup e monitorizar -- tudo a partir do seu terminal, tudo nos seus próprios servidores.
