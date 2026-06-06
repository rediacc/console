---
title: Estratégia de Backup Cruzado
description: "Seu backup falha no momento em que sua máquina falha. A Rediacc replica snapshots para uma máquina separada, portanto uma falha de disco não leva tudo consigo."
category: Use Cases
order: 5
language: pt
sourceHash: "39dbeac1faec121c"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

> **Quando o Desastre Acontece, os Seus Dados Sobrevivem? Com a Rediacc, Sempre.**

**Nota:** Este é um **exemplo de caso de uso** que demonstra como a Rediacc pode resolver este problema. Estes cenários representam aplicações potenciais e não estudos de caso concluídos.

**Cenário de Crise:** Uma chamada de cliente revela a indisponibilidade: **falha de disco**. O último backup do servidor remoto tinha **3 semanas**. Semanas de dados, perdidos.

## O Problema

A organização tomou consciência dos riscos de fazer backup de dados **apenas na mesma máquina**:
* Falhas de hardware
* Ataques cibernéticos
* Desastres físicos como guerra, terramoto, incêndio, inundação
* Proteção insuficiente contra perda de dados

**Procura de Solução:**
* Decide-se fazer backup de 20 TB de dados para **um servidor remoto**
* No entanto, com métodos tradicionais, este backup demora **2 semanas** e ocupa **99,99% (dependendo do rácio de atualização dos dados totais entre snapshots)** da largura de banda

## Impacto da Crise

Após uma chamada de cliente:
* Constata-se que os **serviços não estão a funcionar**
* Deteta-se uma **falha de disco**
* Ao verificar o servidor de backup remoto, compreende-se que **o último backup foi tirado há 3 semanas**

**Resultados:**
* As tentativas de recuperação manual do disco **falham**
* Devido a 3 semanas de perda de dados, **contratos de clientes são cancelados**
* A **reputação da organização fica gravemente afetada**

## Solução Rediacc

![Cross Backup Strategy](/img/cross-backup.svg)

### 1. **Primeiro Backup**
* Na primeira vez, 20 TB de dados são transferidos para um servidor remoto, o que demora 2 semanas

### 2. **Backups Cruzados Horários**
* A cada hora, é criada uma perceção de backup completo, mas **apenas os dados alterados** são transferidos

### 3. **Preparação para Cenários de Desastre**
* Os dados podem ser salvaguardados mesmo em servidores **intercontinentais**
* Mesmo que a máquina principal falhe, os dados de há apenas 1 hora **ficam ativos em minutos**

## Resultado

**Poupança de Tempo:**
* O tempo de backup foi reduzido de **2 semanas para uma média de 4 minutos**
* O risco de perda de dados foi reduzido para **1 hora**

**Otimização de Custos:**
* O consumo de largura de banda diminuiu **98%**

**Continuidade de Negócio Ininterrupta:**
* Quando o servidor principal falhou, o backup remoto foi ativado em **7 minutos**
