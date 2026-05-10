---
title: Recuperação com Viagem no Tempo
description: Recupere dados apagados acidentalmente há semanas com recuperação no tempo baseada em snapshots.
category: Use Cases
order: 2
language: pt
---

> **Quando os outros perdem dados para sempre, você pode viajar de volta no tempo.**

**Nota:** Este é um **exemplo de caso de uso** que demonstra como o Rediacc pode resolver este problema. Sendo uma startup, estes cenários representam aplicações potenciais e não estudos de caso concluídos.

**Cenário de Crise:** Um funcionário recém-contratado **apagou acidentalmente** dados críticos da base de dados em produção há 3 semanas. O sistema de backup da organização guardava apenas 2 semanas de backups, tornando a recuperação de dados praticamente impossível pelos meios convencionais.

## O Problema

Mehmet é especialista em sistemas e responsável pela base de dados de uma grande organização de comércio eletrónico. Numa manhã, perante reclamações de clientes, apercebe-se de que alguns registos de encomendas anteriores **não estão visíveis** no sistema. A investigação revela que um funcionário recém-contratado **apagou acidentalmente** alguns dados críticos da base de dados em produção há 3 semanas, **ligando-se à base de dados de produção em vez do ambiente de testes**.

**Sistema de Backup Existente:**
* Backups completos são feitos uma vez por semana
* **Backups incrementais** são registados diariamente

**Dilema:** A eliminação ocorreu **antes da data dos backups completos**, pelo que os dados perdidos não constam dos backups. Os backups diários **registam apenas os dados mais recentes**, pelo que **os itens eliminados não podem ser recuperados**.

## Impacto da Crise

Devido à perda de dados:
* Os clientes **não conseguem processar pedidos de reembolso**
* Ocorrem inconsistências no sistema de pagamentos
* As reclamações propagam-se rapidamente nas redes sociais

**Resultados:**
* A equipa de apoio ao cliente está sob **pressão intensa**
* A reputação da organização é **rapidamente prejudicada**
* Os esforços manuais de recuperação de dados alcançam **apenas 15% de sucesso**

**Desafio Adicional:**
* Para reduzir os custos de armazenamento, a organização mantém **apenas as últimas 2 semanas de backups**
* Os dados eliminados não constam dos **backups recentes**

## Solução Rediacc

Mehmet propõe uma solução semelhante a uma "máquina do tempo" com o Rediacc:

![Time Travel Recovery](/img/time-travel-recovery.svg)

### 1. **Snapshots**
* O Rediacc tira snapshots do sistema automaticamente a cada hora
* Esses snapshots cobrem também os momentos imediatamente antes da eliminação dos dados

### 2. **Voltar no Tempo**
* Mehmet seleciona a data e hora em que a eliminação ocorreu na interface do Rediacc
* Restaura um snapshot do sistema de há 3 semanas para uma nova instância em 1 minuto

### 3. **Recuperação Completa**
* Os dados perdidos são restaurados de forma completa e consistente

## Resultado

* A reputação da organização foi recuperada **em 24 horas**
* A perda financeira foi evitada em **95%**
* O Rediacc provou que backups frequentes podiam ser feitos **sem aumentar os custos de armazenamento**
