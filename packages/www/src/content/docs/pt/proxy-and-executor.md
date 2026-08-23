---
title: Proxy e Executor
description: Como os comandos do browser e de clientes leves são executados sem que o cliente alguma vez detenha chaves SSH ou endereços de máquinas
category: Concepts
tags:
  - security
  - networking
subcategory: architecture
order: 4
language: pt
sourceHash: "39ec44d8efc3f9b5"
sourceCommit: "5197d1c0349438c2bff2442377a5166d0b8214b6"
---

# Proxy e Executor

Normalmente, o `rdc` corre na sua máquina com a sua configuração e chaves SSH, e liga-se diretamente aos seus servidores. O modelo de proxy divide isto em duas partes: um cliente leve que não detém quaisquer segredos, e um **executor** que os detém e faz o trabalho. O botão Executar da [consola web](/pt/docs/web-console) e a flag `--proxy` da CLI são ambos clientes leves, e falam o mesmo protocolo.

## Intenção do comando, não comandos

Um cliente leve nunca detém uma chave SSH, um endereço de máquina ou uma configuração desencriptada. Quando quer executar algo, envia apenas a intenção do comando: um identificador para o comando (o seu caminho no contrato da CLI, por exemplo `repo up`) mais os parâmetros. O executor procura o comando nesse mesmo contrato, resolve-o para a função correspondente do lado do servidor, resolve a máquina de destino a partir da configuração desencriptada, e executa tudo através da sua própria ligação SSH. A saída é transmitida de volta ao cliente.

O executor é a própria CLI, iniciada como servidor com `rdc serve`. O mesmo binário que os operadores usam num portátil torna-se aquilo que executa comandos em seu nome. Tem duas colocações possíveis:

- **`--mode daemon`**: corre num host que controla, inscrito de forma headless como qualquer CLI (ver [Armazenamento de Configuração](/pt/docs/config-storage)), pelo que consegue derivar a chave de configuração por si próprio e não precisa de qualquer concessão por sessão. Este é o nível rigoroso: o SSH nunca sai da sua rede.
- **`--mode container`**: corre num container alojado para si, associado à sua organização. Começa sem qualquer chave e não pode fazer nada até um cliente lhe conceder uma para a sessão. Este é o nível de conveniência.

## A concessão da CEK

O armazenamento de configuração é zero-knowledge: o servidor armazena apenas blobs encriptados, e a chave de encriptação de conteúdo (CEK) só existe em claro num cliente que a tenha desbloqueado. Um executor em modo container tem, por isso, de *receber a chave por concessão*, e essa concessão não pode expô-la ao servidor entretanto.

O fluxo é o seguinte: um browser desbloqueado abre uma sessão com o executor, recebe a chave pública dessa sessão e sela a CEK para essa sessão usando X25519. O blob selado passa pelo servidor da conta, mas o servidor não o consegue abrir, pelo que a propriedade zero-knowledge se mantém de ponta a ponta. O executor desencripta a CEK apenas em RAM, com uma expiração por inatividade de 30 minutos; nada é alguma vez escrito em disco. Os pedidos de comando seguintes referem-se à sessão concedida através do cabeçalho `X-Config-Session`.

Um pormenor importante para efeitos de auditoria: a mesma identidade de utilizador atravessa as três etapas (abertura da sessão, concessão da chave, execução de comandos). O servidor da conta nunca reencaminha a sua própria credencial para o executor. Em cada etapa emite um token de curta duração atribuído ao utilizador real, e volta a verificar a pertença desse utilizador de cada vez. O executor verifica qualquer token que lhe seja apresentado antes de agir. Uma concessão feita por um utilizador não pode ser usada por outro.

A metade `state` de uma configuração (dados de runtime locais ao host) nunca viaja no blob de configuração, pelo que também nunca chega a um executor por esta via.

## O que pode correr através de um proxy

Nem todos os comandos fazem sentido remotamente. Cada comando no contrato tem uma flag `proxyCapable`, e o executor impõe-na do lado do servidor, independentemente de qualquer configuração de política:

- Os **comandos do plano de máquina, não interativos** (deploy, backup, status, logs, etc.) são compatíveis com proxy.
- Os **comandos do plano de configuração** não são: editam a configuração, o que neste percurso é tarefa do browser (a consola web encaminha-os antes para o seu próprio editor de configuração).
- Os **comandos interativos** (terminais, sessões VS Code) não são: não há um TTY neste canal.
- Os **comandos de transferência do lado do cliente** (`rdc repo sync`) não são: movem dados entre o sistema de ficheiros do *cliente* e uma máquina, e o executor não tem os ficheiros do cliente.

A consola web lê a mesma flag para decidir se um comando recebe ou não um botão Executar, mas o executor recusa comandos não compatíveis independentemente do que o cliente enviar.

## O executor fictício

Em desenvolvimento, quando não está configurado nenhum executor real, o servidor da conta responde ele próprio aos pedidos de comando com streams fictícios e dados claramente falsos (nomes de recursos com o prefixo `mock-`). Isto torna toda a consola utilizável, incluindo formulários, streaming e renderização de resultados, sem necessidade de uma máquina ou de um desbloqueio. A execução real requer um executor real.

## Relacionados

- [Consola Web](/pt/docs/web-console), o cliente de browser construído sobre este modelo
- [Armazenamento de Configuração](/pt/docs/config-storage), o armazenamento zero-knowledge que protege a CEK
