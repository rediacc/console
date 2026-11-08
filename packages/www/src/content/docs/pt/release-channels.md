---
title: "Canais de Versão"
description: "Como o Edge e o Stable diferem, e qual canal executar."
category: "Concepts"
tags:
  - cli
  - operations
subcategory: platform
order: 2
language: pt
sourceHash: "bb653747883615f5"
sourceCommit: "c69b28b08afd5e7602afd1e8efe90785e6e36938"
---

O Rediacc distribui as atualizações da CLI através de dois canais: **Stable** e **Edge**. Ambos ligam-se ao mesmo produto, por isso a conta, o plano e os limites são idênticos em qualquer um deles. Os canais só diferem na rapidez com que uma versão chega até si.

## Canal Stable

O Stable é o canal predefinido. Uma versão só chega a ele depois de ter estado no Edge durante 7 dias sem problemas reportados.

- Recomendado quando prefere uma cadência de atualização conservadora
- Implementado após 7 dias de testes no Edge
- Correções críticas podem ser enviadas diretamente quando necessário

## Canal Edge

O Edge recebe cada alteração no momento em que é integrada no ramo principal. É a versão em produção do software, implementada de forma contínua.

- Lançado a cada integração no ramo principal
- As mesmas contas, planos e limites do Stable
- Ideal para experimentar as novidades mais cedo

## Um produto, dois canais

A sua conta vive na sua região de dados, em `eu.rediacc.cloud`, `us.rediacc.cloud` ou `asia.rediacc.cloud`, seja qual for o canal que utilize. Mudar de canal nunca afeta a conta, os dados nem a subscrição. Para as regiões, consulte [Regiões de Dados](/pt/docs/data-regions).

## Comparação

| | Stable | Edge |
|---|---|---|
| **Cadência de implementação** | Após maturação de 7 dias | A cada integração no ramo principal |
| **Estabilidade** | Testado durante 7 dias | Produção, implementado continuamente |
| **Planos e limites** | Iguais | Iguais |
| **Conta e dados** | Partilhados | Partilhados |
| **Ideal para** | Produção, cargas de trabalho pagas | Acesso antecipado, avaliação |

## Como Funcionam as Promoções

1. Cada integração no ramo principal é implementada imediatamente no Edge.
2. Após 7 dias sem problemas, o Edge é promovido automaticamente para Stable.
3. Correções críticas podem ser enviadas para ambos os canais simultaneamente.

Portanto, o Stable atrasa o Edge no máximo 7 dias. A janela de maturação deteta regressões no Edge antes de chegarem ao Stable.

## Qual Canal Devo Escolher?

**Escolha Stable se:**
- Prefere uma cadência de atualização conservadora com uma janela de maturação de 7 dias
- Prefere máxima fiabilidade em detrimento das funcionalidades mais recentes

**Escolha Edge se:**
- Quer experimentar novas funcionalidades mais cedo
- Está a avaliar a plataforma
- Está confortável com código mais recente e menos testado

## Instalação

Consulte [Instalação](/pt/docs/installation) para os comandos de instalação, configuração de gestor de pacotes e etiquetas Docker para cada canal.

## Gestão do Canal do CLI

O CLI utiliza o canal que configurou na instalação. Para mudar:

```bash
rdc update --channel edge      # Mudar para Edge
rdc update --channel stable    # Mudar para Stable
```
