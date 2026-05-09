---
title: Escalamento de Bases de Dados Legadas
description: Escale bases de dados legadas sem migração, aproveitando a replicação de dados em tempo real e a distribuição de consultas.
category: Use Cases
order: 3
language: pt
---

> **A Sua Base de Dados Legada Está a Travar-lhe o Caminho. Liberte-se Sem a Quebrar.**

**Nota:** Este é um **exemplo de caso de uso** que demonstra como a Rediacc pode resolver este problema. Enquanto startup, estes cenários representam aplicações potenciais e não estudos de caso concluídos.

**Cenário de Crise:** Apesar de escalar os servidores 10 vezes com Kubernetes, o desempenho melhorou apenas 2 vezes. Os clientes queixavam-se de tempos de consulta lentos, os custos aumentaram sem resultados satisfatórios e a reputação estava em risco.

## O Problema

Os serviços da organização no ambiente cloud **estavam com dificuldades em responder**. Como solução, a equipa de software:
* Realizou **escalamento horizontal com Kubernetes** e **aumentou o número de servidores 10 vezes**
* No entanto, o desempenho melhorou **apenas 2 vezes**

**Deteção do Estrangulamento:**
* Percebeu-se que a origem do problema era uma **base de dados legada que não pode ser escalada**
* A base de dados não conseguia funcionar de forma distribuída como nas arquiteturas modernas

**Dilema:**
* A migração para uma base de dados moderna **poderia demorar anos** -- exigia reescrita de código, migração de dados e processos de teste
* A perda de custos e tempo era inaceitável

## Impacto da Crise

* Os clientes queixam-se de **tempos de consulta lentos**
* Os custos dos servidores estão a aumentar, mas o **desempenho não é satisfatório**
* O risco de **perda de reputação** aumenta num mercado competitivo

## Solução Rediacc

O engenheiro de sistemas Yüksel, usando a funcionalidade de cross-backup da Rediacc:

![Escalamento de BD Legada](/img/legacy-scaling.svg)

### 1. **Replicação de Dados em Tempo Real**
* As alterações na base de dados legada foram transferidas para outros servidores **em intervalos de 10 a 15 minutos**
* **Apenas os dados alterados** foram sincronizados -- **o consumo de largura de banda foi reduzido em 95%**

### 2. **Distribuição de Consultas**
* As consultas de leitura foram **distribuídas por múltiplas máquinas**
* As operações de escrita foram mantidas **na base de dados principal** para garantir consistência

### 3. **Escalamento Sem Custos Adicionais**
* O sistema legado foi suportado com servidores adicionais **sem ser alterado**
* Sem necessidade de aquisição de hardware novo -- **os servidores cloud foram alugados à hora** para otimização de custos

## Resultado

**Aumento de Desempenho:**
* Os tempos de consulta foram reduzidos de **55 segundos para 7 segundos**
* A capacidade do sistema aumentou **8 vezes**

**Controlo de Custos:**
* Poupanças ao evitar a reescrita do sistema legado -- **os recursos financeiros foram preservados**

**Ganho de Tempo:**
* A solução foi implementada **em 3 semanas**
* As queixas dos clientes foram resolvidas em **99,99% (dependendo do rácio de atualização dos dados totais entre snapshots)**
