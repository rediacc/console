---
title: Atualizações sem Risco
description: Teste atualizações de bases de dados sem risco com clonagem instantânea e snapshots de hora em hora.
category: Use Cases
order: 4
language: pt
sourceHash: "242617b8bede9535"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

> **Teste Tudo. Arrisque Nada. Atualize com Confiança.**

Nota rápida: O Rediacc ainda não tem clientes em produção. Este é um exemplo de caso de uso que mostra como a arquitetura lida com este cenário na prática, não um estudo de caso de uma implementação real.

**Cenário de Crise:** Durante uma atualização de base de dados, ocorreu um **erro inesperado** que impediu reverter para a versão antiga ou avançar para a nova. Os clientes não conseguiam aceder aos sistemas e mais de 5000 colaboradores ficaram sem poder trabalhar. A única saída foi uma restauração completa do sistema, custando horas de trabalho de engenheiros enquanto a empresa estava offline.

## O Problema

O Mehmet gere bases de dados de produção que a sua equipa não pode permitir ficar offline. Hoje está a atualizar uma **base de dados PostgreSQL de 100 TB da versão 13 para 14**. O seu plano:

1. **Fazer um backup** -> No entanto, o backup demora **vários dias** devido ao tamanho dos dados
2. **Realizar a atualização ao fim de semana** -> Os departamentos são notificados de uma interrupção de **sábado das 01:00 às 05:00**

## Impacto da Crise

* Ocorre um **erro inesperado** durante a atualização
* A base de dados **não consegue reverter para a versão antiga nem avançar para a nova**
* Mesmo as equipas de suporte externo não conseguem resolver o problema

**Impactos:**
* Os clientes **não conseguem aceder aos sistemas de pagamento e encomendas**
* Os colaboradores da organização (**mais de 5000 pessoas**) não conseguem trabalhar
* **Perda de reputação** e aumento de reclamações

**Solução Temporária:**
* O último backup é carregado para **um novo servidor** -> **O custo de hardware duplica**
* Os dados de quinta e sexta-feira estão **apenas no ambiente de produção**, causando perda de dados
* **Duas bases de dados com versões diferentes** são criadas -> Aumentam as inconsistências

## Solução Rediacc

Eis o que muda com o Rediacc:

![Atualizações sem Risco](/img/risk-free-upgrades.svg)

### 1. **Clonagem Instantânea**
* Um **clone da base de dados de 100 TB é criado em segundos**
* Os testes de atualização são realizados **sem afetar o sistema em produção**

### 2. **Snapshots de Hora em Hora**
* Determina-se **desde quando e em que passo a atualização falha**
* As operações problemáticas são **identificadas antecipadamente** e corrigidas

### 3. **Atualização Sem Interrupções**
* Se a atualização falhar, **o ambiente de produção não é afetado**
* Se a atualização for bem-sucedida, o novo ambiente de produção passa a ser o clone mais recente

## Resultado

**Poupança de Tempo e Custo:**
* O tempo de backup foi reduzido de **7 dias para 10 segundos**

**Atualização sem Risco:**
* Os erros foram detectados antecipadamente no ambiente de teste -> **Sem problemas no sistema de produção**

**Zero Tempo de Inatividade:**
* Clientes e colaboradores **não sentiram qualquer interrupção**
