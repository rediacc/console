---
title: Escalamento Dinâmico de Recursos
description: Construa arquitetura cloud com flexibilidade ilimitada para treino de IA e cargas de trabalho dinâmicas.
category: Use Cases
order: 1
language: pt
---

> **A Sua Arquitetura Cloud É Rígida? Construa Com Flexibilidade Ilimitada.**

**Nota:** Este é um **exemplo de caso de uso** que demonstra como a Rediacc pode resolver este problema. Enquanto startup, estes cenários representam aplicações potenciais e não estudos de caso concluídos.

**Cenário de Crise:** Os tempos de treino de IA **estenderam-se 2 a 3 vezes**, causando atrasos nos projetos. Os engenheiros sofreram perdas significativas de produtividade enquanto aguardavam recursos, ameaçando a vantagem competitiva da organização.

## O Problema

Os engenheiros de software da organização estão a ter problemas de desempenho com servidores **on-premise** utilizados para **treino de modelos de IA**:
* Durante o **horário de escritório** (08:00-17:00), os pedidos ao servidor atingem 99% da capacidade
* O treino que requer grande poder de processamento faz com que o hardware **seja insuficiente**

**Procura de Solução:**
* O custo de atualização dos servidores **não é considerado adequado** devido a **6 a 7 horas de uso diário**
* Embora a migração para cloud seja considerada, o **custo de transferência de dados** e as **dificuldades de sincronização** são obstáculos

## Impacto da Crise

* Os tempos de treino de IA **estendem-se 2 a 3 vezes**, os projetos atrasam
* Os engenheiros experimentam **perda de produtividade** enquanto aguardam recursos
* A organização enfrenta o risco de **perder gradualmente a sua vantagem competitiva**

## Solução Rediacc

O engenheiro de sistemas Yüksel desenvolve **um modelo híbrido** com a Rediacc:

![Escalamento Híbrido de Cloud](/img/hybrid-cloud-scaling.svg)

### 1. **Migração Instantânea para Cloud**
* Durante o horário de escritório, os serviços on-premise são clonados para a cloud **com todos os dados e configurações**
* 100 TB de dados são sincronizados em 9 minutos transferindo **apenas as partes alteradas** graças à Rediacc

### 2. **Escalamento Dinâmico**
* Os servidores no ambiente cloud são alugados **conforme necessário para o treino de IA**
* O poder de processamento pode ser **aumentado 10 vezes** de acordo com a procura

### 3. **Sincronização Noturna**
* No fim do dia de trabalho, **todas as alterações na cloud** são **automaticamente transferidas** para o ambiente on-premise
* Os engenheiros que trabalham à noite continuam as suas operações com **dados atualizados**

## Resultado

**Vantagem de Custo:**
* Ao **alugar recursos cloud à hora**, o custo mensal foi reduzido em **60%**
* A necessidade de atualizar os servidores on-premise **foi eliminada**

**Aumento de Desempenho:**
* Os tempos de treino de IA foram reduzidos de **8 horas para 1,5 horas**
* A produtividade dos engenheiros aumentou **40%**

**Trabalho Flexível:**
* A **consistência dos dados** entre ambientes cloud e on-premise foi garantida de forma transparente
* As equipas do turno noturno **tiveram acesso imediato a dados atualizados**
