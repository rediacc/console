---
title: Consola Web
description: Execute toda a CLI rdc a partir do seu browser, com formulários, seletores de recursos e histórico de execuções
category: Guides
tags:
  - cli
  - account
subcategory: cli-tools
order: 8
language: pt
sourceHash: "972ed654ae294102"
sourceCommit: "5197d1c0349438c2bff2442377a5166d0b8214b6"
---

# Consola Web

A consola web é uma interface de browser sobre toda a CLI `rdc`. Cada comando da CLI aparece na consola com um formulário, validação, seletores de recursos e um botão Executar. Não existe um "conjunto de funcionalidades web" separado: a consola é gerada a partir do contrato da CLI, pelo que qualquer comando que a CLI tenha, a consola também tem, e os comandos novos aparecem automaticamente.

Está disponível no portal web em `/account/console`.

## Disponibilidade

A consola web é uma funcionalidade paga. Está incluída nos planos pagos e escondida no plano Community. O acesso também é limitado por função, pelo que um administrador da organização pode controlar quem a vê.

## Como se relaciona com o armazenamento de configuração

A consola lê os seus recursos (máquinas, repositórios, etc.) a partir do seu armazenamento de configuração encriptado, e só desencripta essa configuração no browser. Isto significa que:

- **Enquanto bloqueada**, ainda pode navegar por todo o catálogo de comandos, abrir o formulário de qualquer comando e ler os seus parâmetros. Isto funciona sem qualquer configuração prévia.
- **Para executar comandos e usar seletores**, tem primeiro de desbloquear o seu armazenamento de configuração (passkey, palavra-passe mestra ou código de recuperação, ver [Armazenamento de Configuração](/pt/docs/config-storage)). Os botões Executar, as páginas de recursos e os seletores de recursos dependem todos da sessão desbloqueada.

A chave desencriptada permanece apenas na memória do browser. Atualizar a página volta a bloquear a consola, e 30 minutos de inatividade bloqueiam-na automaticamente.

## Seletores de recursos

Depois de desbloqueada, os formulários de comandos substituem os campos de texto livre por seletores alimentados pela sua configuração desencriptada: máquinas, repositórios, datastores, armazenamentos, clusters, fornecedores cloud e estratégias de backup. Alguns seletores são resolvidos em tempo real, através da execução de um comando, por exemplo containers numa máquina ou snapshots num datastore.

Os seletores filtram de forma dependente: escolha uma máquina e o seletor de repositórios restringe-se a essa máquina. Para referências de repositório, um construtor de referências compõe a forma completa `nome:tag@máquina` a partir das escolhas individuais. Os seletores são sugestões, não restrições, e pode sempre introduzir um valor manualmente.

## Executar comandos

O browser nunca detém uma chave SSH ou um endereço de máquina. Quando clica em Executar, a consola envia apenas a intenção do comando, qual o comando e quais os parâmetros, e um executor resolve tudo o resto e executa-o. Ver [Proxy e Executor](/pt/docs/proxy-and-executor) para perceber como isto funciona e que comandos podem correr desta forma.

Os comandos que apenas editam a sua configuração (por exemplo, criar uma entrada de máquina) não são executados remotamente. A consola encaminha-os para o editor de configuração incorporado, onde a alteração é encriptada e enviada como qualquer outra edição de configuração.

Cada formulário também mostra a linha de comando CLI equivalente, para que qualquer coisa que configure na consola possa ser copiada diretamente para um terminal ou um script.

## Como se orientar

- **Páginas de recursos**: máquinas, repositórios e jobs têm cada um páginas de lista e de detalhe, com os comandos relevantes associados como ações.
- **Paleta de comandos**: prima Cmd-K (Ctrl-K) para saltar para qualquer comando ou recurso pelo nome.
- **Histórico de execuções**: as execuções anteriores são guardadas por sessão, para poder rever o resultado e voltar a executar com os mesmos parâmetros.

## Relacionados

- [Armazenamento de Configuração](/pt/docs/config-storage), configurar e desbloquear o armazenamento de configuração encriptado
- [Proxy e Executor](/pt/docs/proxy-and-executor), o modelo de execução por trás do botão Executar
