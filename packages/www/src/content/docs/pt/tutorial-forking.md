---
title: "Criar um Fork de um Repositório"
description: "Clone um repositório inteiro -- aplicação, base de dados, ficheiros -- em segundos. Qualquer tamanho. Zero disco extra."
category: "Tutorials"
subcategory: advanced
order: 7
language: pt
sourceHash: "9237f00dce2ee5ec"
---

# Criar um Fork de um Repositório

Esta é a funcionalidade principal: clonar um ambiente de produção inteiro -- a aplicação, a base de dados, os ficheiros de configuração -- em segundos. Qualquer tamanho. Zero disco extra. Faça fork quantas vezes quiser.

O lema: **clone production, break nothing.**

## Ver o tutorial

![Tutorial: Forking a repository](/assets/tutorials/tutorial-forking.cast)

## Preparar algo para perder

Primeiro, dê à aplicação em execução um ficheiro para poder provar o isolamento do fork. Abra o repositório no VS Code:

```bash
rdc vscode connect -m my-server -r my-app
```

Dentro do repositório, crie um ficheiro de marcador:

```bash
time echo "Hello from production" > index.html
```

Agora faça o fork.

## Fork

```bash
time rdc repo fork --parent my-app -m my-server --tag experiment --up
```

![Parent fans out into independent clones](/img/tutorials/tutorial-forking/slide-1.svg)

Um comando. Clonou tudo -- a aplicação, a base de dados, os ficheiros de configuração -- e aconteceu em segundos. Execute novamente e obtém outro clone independente.

## Porquê tão rápido?

![Sharing a folder link is the same speed regardless of the folder's size](/img/tutorials/tutorial-forking/slide-2.svg)

Imagine partilhar uma hiperligação para uma pasta. A hiperligação é a mesma seja a pasta pequena ou enorme -- a pasta é pesada, a hiperligação é leve.

![1 GB, 100 GB, 1 TB -- same time, every time](/img/tutorials/tutorial-forking/slide-3.svg)

O fork funciona da mesma forma. 1 GB, 100 GB, 1 TB -- o mesmo tempo, sempre.

## O que é partilhado, o que é seu

![Many mirrors, one sun -- shared base, your changes are yours](/img/tutorials/tutorial-forking/slide-4.svg)

Pense no repositório pai como o sol. Não pode segurar o sol, mas pode segurar um espelho que o capta -- e esse espelho é o seu fork. Pinte no espelho e os seus desenhos são seus. O sol permanece igual, não importa quantos espelhos estejam voltados para ele.

> Não pode segurar o sol, mas pode segurá-lo num espelho.

## E se o pai mudar mais tarde?

![A fork is a frozen photograph; the parent keeps flowing like a river](/img/tutorials/tutorial-forking/slide-5.svg)

Agora pense num rio. A água continua a fluir -- a cada momento é diferente. Quando faz um fork, tira uma fotografia do rio, congelada naquele momento. O rio continua a fluir. A sua fotografia não.

Se o repositório pai mudar mais tarde, o seu fork fica onde estava.

> Não pode segurar um rio, mas pode segurá-lo numa fotografia.

## O uso do disco mantém-se estável

![Five forks of a 100 GB repo -- still about 100 GB](/img/tutorials/tutorial-forking/slide-6.svg)

É por isso que o seu disco não explode. Cinco forks de um repositório de 100 GB? Ainda cerca de 100 GB no total. Só paga disco pelo que alterar em cada fork.

> Faça fork cinco vezes se quiser -- o seu disco nem vai dar conta.

## O que os forks *não* herdam: segredos

Há uma coisa que o fork deliberadamente não segue: segredos. Um fork começa sem chaves de API, sem palavras-passe de bases de dados, sem tokens Stripe. É por isso que "clone production, break nothing" funciona de verdade -- o seu sandbox não pode faturar clientes reais porque não consegue fazer-se passar por si. Configuramos isto corretamente no tutorial [Gerir Segredos](/pt/docs/tutorial-managing-secrets).

## Verificar o isolamento

Liste ambos os repositórios lado a lado:

```bash
time rdc repo list -m my-server
```

Verá `my-app` e `my-app:experiment` a correr em simultâneo.

No repositório original, verifique o que está a correr:

```bash
time docker ps
```

Repare no tempo de atividade -- estes são os contentores originais. Agora mude para o fork:

```bash
rdc vscode connect -m my-server -r my-app:experiment
```

```bash
time docker ps
```

As mesmas imagens, mas o tempo de atividade é recente -- estes arrancaram quando o fork foi criado.

Torne a diferença ainda mais óbvia -- adicione um contentor apenas ao fork:

```bash
time docker run --rm -it -d nginx
time docker ps
```

O Nginx está a correr, mas apenas dentro deste fork.

Tente algo destrutivo:

```bash
time rm index.html
```

Desapareceu aqui. Agora volte ao original:

```bash
rdc vscode connect -m my-server -r my-app
time docker ps
```

Sem nginx. Os contentores do fork ficaram no fork. E `index.html` ainda está aqui, intocado. O original nunca soube que algo aconteceu. As mesmas imagens, daemons Docker separados, sistemas de ficheiros separados.

## Limpar

Quando terminar, basta apagar o fork:

```bash
time rdc repo delete --name my-app:experiment -m my-server
```

O original fica exatamente como estava. **Fork, experimente, quebre coisas, apague.** Sem risco.

---

Próximo: [Gerir Segredos](/pt/docs/tutorial-managing-secrets).
