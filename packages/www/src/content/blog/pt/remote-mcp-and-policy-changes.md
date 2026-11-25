---
title: "MCP remoto: um agente que lê apenas o que a sua pessoa pode ler"
description: "O MCP remoto roda nos três Workers regionais. Um grant carrega a chave de uma config e as chaves de política da sua pessoa, nunca a chave mestra, e nenhum token sobrevive ao grant."
author: Rediacc
publishedDate: 2026-11-25
category: announcement
tags:
  - mcp
  - ai-agents
  - security
  - policy
featured: false
language: pt
sourceHash: "ce8dbe4241a2d7ab"
sourceCommit: "dda643f43f9dadc19e08a84858e87f115d428f85"
---

> **Resumo.** O MCP remoto dá a um agente de IA uma URL em vez de um terminal. A questão de projeto nunca foi como conectar o agente, e sim o que ele pode ver depois de conectado. A resposta: exatamente o que vê a pessoa que criou o grant, e nada além disso.
>
> - Um grant alcança **uma config** e vive em **uma região**.
> - Os tokens duram no máximo **1 hora** (acesso) e **30 dias** (renovação), e nunca mais que o próprio grant.
> - O grant carrega a chave de conteúdo de uma config e duas **chaves de leitura de política**, nunca a chave mestra do config store.
> - O formato dos registros de política mudou. Os antigos são recusados e não há caminho de migração.

## Uma URL, não um shell de login

O servidor MCP local (`rdc mcp serve`) roda ao lado do agente e herda o acesso da máquina em que está. O servidor remoto é diferente. Um Worker MCP roda em cada região em `mcp.<region>.rediacc.cloud`, e cada agente se conecta à URL de um grant: `https://mcp.<region>.rediacc.cloud/g/<grantId>`. As chamadas de ferramentas rodam no executor da organização, não no notebook de quem desenvolve.

Clientes interativos como o claude.ai entram por OAuth 2.1 com PKCE. Agentes headless enviam um bearer `rmcp_<grantId>.<secret>`. As duas formas identificam o grant, e o id na URL apenas o nomeia.

## O grant é a fronteira

Um grant é um objeto pequeno e específico. Ele nomeia uma config, uma validade e um escopo: um indicador de somente leitura, uma allowlist de ferramentas e padrões de nomes de máquinas e repositórios.

Três regras decorrem desse formato:

- **Uma config.** Um `tools/call` que nomeia outra config é recusado com `REDIACC_GRANT_SCOPE` antes de qualquer coisa rodar. Quem tem três configs autoriza três grants.
- **Uma região.** Os ids de grant começam pela região. Uma requisição que chega ao Worker errado recebe HTTP 421 com a URL correta e nunca é encaminhada.
- **Uma duração.** Um token de acesso dura o menor valor entre 1 hora e o tempo que resta ao grant. Um token de renovação dura o menor valor entre 30 dias e o tempo que resta ao grant. Cada renovação consulta o grant de novo, então um grant revogado para de funcionar na próxima troca. Apresentar duas vezes um token de renovação revoga o grant.

A URL de um grant vale 7 dias por padrão e 30 no máximo.

## Avaliado como a sua pessoa

O ponto interessante é o material de chaves. Um grant é um segredo dividido. O navegador sorteia um valor aleatório e o mostra uma única vez. O servidor de contas guarda apenas o hash de uma etiqueta derivada dele, e o executor só deriva a chave de slot enquanto tem as duas metades. O que essa chave de slot abre é a chave de conteúdo da config, nunca a chave mestra da organização.

A mesma chave de slot abre também duas **chaves de política**. A política, isto é, as regras de autorização de uma entrada de config, agora vive em um registro próprio, selado com uma chave derivada da chave do store e do ponteiro do registro: store, config, equipe e geração da chave. O grant carrega a chave da config da sua equipe e a da config no nível da organização. São os dois registros de política que a sua pessoa lê, então o executor lê os mesmos.

O efeito é que um agente é avaliado como a sua pessoa. O teto é a política da organização, restringida pela da equipe. O agente só age onde um consentimento humano e esse teto permitem os dois. Ele não pode editar a política, ler valores de segredos nem ampliar o próprio grant. Uma chave que a organização trava é ignorada na política de uma equipe, e o agente encontra esse resultado do mesmo modo que a pessoa.

Prender cada chave a um ponteiro tem um efeito colateral que vale registrar. Quem tem uma chave de política abre os registros desse ponteiro sob aquela geração de chave e nenhum outro. Um blob servido para outro store, outra config ou outra equipe, ou reapresentado sob outra versão, falha na etiqueta de integridade.

## O que muda para instalações existentes

- **Os registros de política passam à versão 2.** Um registro de versão 1, selado com a própria chave do store, não abre. É uma ruptura limpa, de propósito.
- **Escritas hospedadas seguem a mesma política.** As escritas de config feitas pelo executor hospedado são conferidas contra o teto da política antes de serem salvas.
- **Agentes locais mantêm o mesmo teto.** `REDIACC_ALLOW_CONFIG_EDIT` ainda habilita um agente a editar a config nos ponteiros que nomeia, mas só dentro do que a política permite.
- **Grants expirados ou rotacionados falham de forma clara.** `initialize` e `tools/list` continuam respondendo, e cada chamada devolve `REDIACC_GRANT_EXPIRED`, `REDIACC_GRANT_REVOKED` ou `REDIACC_KEY_ROTATED` com uma `reauthUrl`.

Cada grant permite 60 chamadas por minuto e 5 em andamento.

## O que uma URL vazada rende

Uma URL vazada age como aquele usuário na sua única config até expirar ou ser revogada. Ela não abre nenhuma outra config da organização, nem nada fora do executor hospedado da sua região. A saída das ferramentas chega, sim, ao provedor de modelos que o usuário conecta. A Rediacc não escolhe esse provedor.

O guia de configuração é o [MCP Server Setup](/pt/docs/ai-agents-mcp), e a estrutura de chaves está no [modelo de segurança](/pt/docs/security-model).
