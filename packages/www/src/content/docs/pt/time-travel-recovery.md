---
title: Time Travel Recovery
description: Recupere dados apagados há semanas usando snapshots do btrfs, mesmo quando seus backups normais já não cobrem esse período.
category: Use Cases
order: 2
language: pt
sourceHash: "e55d51b8df91b20f"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

> **Quando os outros perdem dados para sempre, você pode viajar de volta no tempo.**

**Nota:** Este é um **exemplo de caso de uso** que mostra como o Rediacc lida com este tipo de problema. Somos uma startup. Estes são cenários realistas para os quais o produto foi construído, não estudos de caso de clientes que já concluímos.

**Cenário de Crise:** Um novo funcionário **apagou acidentalmente** linhas críticas da sua base de dados em produção há 3 semanas. O seu sistema de backup guarda apenas 2 semanas de histórico. Com uma configuração normal, esses dados perderam-se.

## O Problema

Mehmet é especialista em sistemas e responsável pela base de dados de uma grande organização de comércio eletrónico. Numa manhã, perante reclamações de clientes, apercebe-se de que alguns registos de encomendas anteriores **não estão visíveis** no sistema. A investigação revela que um funcionário recém-contratado **apagou acidentalmente** alguns dados críticos da base de dados em produção há 3 semanas, **ligando-se à base de dados de produção em vez do ambiente de testes**. É o erro clássico. Todo DBA ou já cometeu este erro ou viu alguém recém-contratado cometê-lo.

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

Aqui está a solução de viagem no tempo que Mehmet constrói com o Rediacc:

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
