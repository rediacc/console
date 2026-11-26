---
title: "Política de divulgação de vulnerabilidades"
description: "Como reportar uma vulnerabilidade de segurança na Rediacc: escopo, porto seguro, como reportar e quais prazos de resposta esperar."
category: "Legal"
tags:
  - security
  - compliance
subcategory: foundations
order: 9
language: pt
sourceHash: "612e816f7a8be282"
sourceCommit: "f9ac63ac37dff49f6c980f00fdacb7e41099ce81"
---

A Rediacc recebe com satisfação relatos de vulnerabilidades de segurança em seus produtos e serviços. Esta política descreve o que está no escopo, como reportar e o que o autor do relato pode esperar em troca. O arquivo de contato legível por máquina está em [`/.well-known/security.txt`](https://www.rediacc.com/.well-known/security.txt) (RFC 9116).

## Escopo

Dentro do escopo:

- a CLI `rdc` e o orquestrador de máquinas `renet`
- o servidor de contas, seu portal web e sua API
- os sites da Rediacc em `rediacc.com` e `rediacc.cloud`
- os artefatos de release: binários, imagens de contêiner e instaladores

Fora do escopo:

- achados que exigem acesso físico a uma máquina, ou um endpoint comprometido que o autor do relato já controla
- negação de serviço por volume, spam ou engenharia social contra funcionários
- relatos de scanners automáticos sem impacto demonstrado
- vulnerabilidades em software de terceiros que a Rediacc apenas redistribui sem alterações; elas devem ir para o projeto original, e uma cópia é bem-vinda aqui

## Como reportar

Envie o relato para [security@rediacc.com](mailto:security@rediacc.com). Inclua:

- o produto e a versão afetados, ou a URL
- os passos para reproduzir, ou uma prova de conceito
- o impacto que o autor do relato espera
- se o problema já é público ou está sendo explorado
- um endereço de contato para acompanhamento e se deseja receber crédito

Relatos em inglês são preferidos. Dados reais de clientes devem ficar fora do relato: uma prova mínima do acesso é suficiente.

## Porto seguro

A Rediacc não tomará nem apoiará ação judicial contra quem reporta de boa-fé conforme esta política, ou seja, quem:

- testa apenas contra as próprias contas, máquinas e dados, ou contra ativos que pertencem à Rediacc
- para no ponto de comprovar o problema e não lê, altera, copia nem apaga dados de terceiros
- não degrada o serviço para outros usuários
- reporta sem demora e mantém os detalhes em sigilo até a data de divulgação coordenada abaixo

O trabalho que se mantém dentro desses limites é tratado como autorizado, e a Rediacc o confirmará a qualquer terceiro que perguntar.

## Prazos de resposta

| Etapa | Meta |
|------|--------|
| Confirmação de recebimento do relato | 2 dias úteis |
| Primeira avaliação, com a gravidade | 5 dias úteis |
| Atualizações de status enquanto aberto | pelo menos a cada 14 dias |
| Correção ou mitigação de um problema crítico | 14 dias a partir da avaliação |
| Correção ou mitigação dos demais problemas confirmados | 90 dias a partir da avaliação |

As metas são objetivos, e um relato que precise de mais tempo recebe uma explicação e uma nova data.

## Divulgação coordenada

Os detalhes são publicados junto com a correção, normalmente em até 90 dias após a primeira avaliação. Quem quiser uma publicação mais cedo ou mais tarde indica a data no relato, e as duas partes combinam uma data. Uma vulnerabilidade já explorada na prática é tratada como incidente, conforme descrito na [página de resposta a incidentes](/pt/docs/security-incident-response).

## Crédito

Um relato confirmado recebe crédito nas notas de versão ou no comunicado de segurança, com o nome ou apelido que o autor escolher. A Rediacc não mantém um programa de recompensas pago.

## Relacionados

- [Resposta a incidentes](/pt/docs/security-incident-response)
- [Segurança da conta e API](/pt/docs/account-security)
