---
title: Actualizações sem Risco
description: Teste actualizações de bases de dados sem risco com clonagem instantânea e snapshots de hora em hora.
category: Use Cases
order: 4
language: pt
---

> **Teste Tudo. Arrisque Nada. Actualize com Confiança.**

**Nota:** Este e um **exemplo de caso de uso** que demonstra como o Rediacc pode resolver este problema. Enquanto startup, estes cenarios representam aplicacoes potenciais e nao estudos de caso concluidos.

**Cenario de Crise:** Durante uma actualizacao de base de dados, ocorreu um **erro inesperado** que impediu reverter para a versao antiga ou avanzar para a nova. Os clientes nao conseguiam aceder aos sistemas e mais de 5000 colaboradores ficaram sem poder trabalhar.

## O Problema

O Mehmet e um administrador de sistemas experiente que gere bases de dados de grande escala. Decide **actualizar uma base de dados PostgreSQL de 100 TB da versao 13 para a 14**. O seu plano:

1. **Fazer um backup** -> No entanto, o backup demora **varios dias** devido ao tamanho dos dados
2. **Realizar a actualizacao ao fim de semana** -> Os departamentos sao notificados de uma interrupcao de **sabado das 01:00 as 05:00**

## Impacto da Crise

* Ocorre um **erro inesperado** durante a actualizacao
* A base de dados **nao consegue reverter para a versao antiga nem avanzar para a nova**
* Mesmo as equipas de suporte externo nao conseguem resolver o problema

**Impactos:**
* Os clientes **nao conseguem aceder aos sistemas de pagamento e encomendas**
* Os colaboradores da organizacao (**mais de 5000 pessoas**) nao conseguem trabalhar
* **Perda de reputacao** e aumento de reclamacoes

**Solucao Temporaria:**
* O ultimo backup e carregado para **um novo servidor** -> **O custo de hardware duplica**
* Os dados de quinta e sexta-feira estao **apenas no ambiente de producao**, causando perda de dados
* **Duas bases de dados com versoes diferentes** sao criadas -> Aumentam as inconsistencias

## Solucao Rediacc

O Mehmet resolve o problema de forma estrutural com o Rediacc:

![Actualizacoes sem Risco](/img/risk-free-upgrades.svg)

### 1. **Clonagem Instantanea**
* Um **clone da base de dados de 100 TB e criado em segundos**
* Os testes de actualizacao sao realizados **sem afectar o sistema em producao**

### 2. **Snapshots de Hora em Hora**
* Determina-se **desde quando e em que passo a actualizacao falha**
* As operacoes problematicas sao **identificadas antecipadamente** e corrigidas

### 3. **Actualizacao Sem Interrupcoes**
* Se a actualizacao falhar, **o ambiente de producao nao e afectado**
* Se a actualizacao for bem sucedida, o novo ambiente de producao passa a ser o clone mais recente

## Resultado

**Poupanca de Tempo e Custo:**
* O tempo de backup foi reduzido de **7 dias para 10 segundos**

**Actualizacao sem Risco:**
* Os erros foram detectados antecipadamente no ambiente de teste -> **Sem problemas no sistema de producao**

**Zero Tempo de Inatividade:**
* Clientes e colaboradores **nao sentiram qualquer interrupcao**
