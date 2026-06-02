---
title: "Ambientes de Desenvolvimento Semelhantes à Produção em Minutos"
description: "Reduza a configuração de ambientes de desenvolvimento de dias para minutos com deduplicação ao nível de bloco."
category: Use Cases
order: 7
language: pt
sourceHash: "2aa115fc621f5258"
sourceCommit: "4e60a12e0664cdee5ad9079a7b75e2d05980d0f5"
---

> **Reduza a Configuração de Ambientes de Dias para Minutos com Arquitetura de Armazenamento por Deduplicação Inteligente.**

**Nota:** Este é um **exemplo de caso de uso** que mostra como o Rediacc acelera o trabalho de desenvolvimento. Somos uma startup sem clientes pagantes ainda, por isso trate isto como um cenário para o qual concebemos o produto, não como um estudo de caso concluído.

## O Problema

Mehmet é responsável pelo DevOps numa empresa de comércio eletrónico. A sua equipa precisa de **ambientes semelhantes à produção** para testes, staging e desenvolvimento. Eis porquê:

**Onde a abordagem antiga falha:**
* Configurar ambientes semelhantes à produção demora **horas ou dias**
* Os programadores esperam pelo provisionamento de infraestrutura para concluir os testes
* As inconsistências de ambiente levam a problemas de "funciona na minha máquina"

Os ciclos de desenvolvimento arrastavam-se porque criar um novo ambiente demorava dias. Esse gargalo:

* Reduziu significativamente a **velocidade de desenvolvimento**
* Criou dependências e tempos de espera no pipeline de desenvolvimento

## Impacto da Crise

* Os custos de armazenamento tornaram-se **insustentáveis** para o orçamento de TI
* As janelas de backup excederam o tempo de manutenção disponível
* O desempenho do sistema degradou-se durante as operações de backup
* O risco de perda de dados aumentou devido a backups incompletos

## Solução Rediacc

Mehmet encontrou o Rediacc. Com ele:

![Backup Diagram](/img/backup-optimization.svg)

### Tecnologia de Backup Inteligente
* **Os backups completos parecem ser feitos**, mas apenas os **dados alterados** são fisicamente armazenados
* Por exemplo, se houver **alterações diárias médias de 100 GB** numa base de dados de 10 TB, o sistema **regista apenas esses 100 GB**
* Os backups funcionam **de forma completa e transparente durante o restauro**, mesmo que armazenados como um único ficheiro

### Vantagens Principais

**1. Poupança de Custos**
* Mesmo com alterações diárias de **100 GB** numa base de dados de 10 TB, o custo mensal de armazenamento fica limitado a **~3 TB** (era **~300 TB** com o sistema antigo)

**2. Funciona com Qualquer Stack**
* O Rediacc não se limita ao SQL Server. Funciona de forma compatível com **MySQL, PostgreSQL, MongoDB** e todas as outras bases de dados
* Sem necessidade de **conhecimento especializado separado** para diferentes sistemas

**3. Ciclos Mais Rápidos, Menos Hardware**
* O tempo de backup é reduzido de **horas para minutos**
* A carga nos recursos de disco e rede diminui 99,99% (dependendo do rácio de atualização dos dados totais entre snapshots)

## Resultado

Com o Rediacc, a equipa:
* Reduziu os custos de armazenamento em **99,99% (dependendo do rácio de atualização dos dados totais entre snapshots)**
* Padronizou os processos de backup e restauro
* Satisfez todas as suas necessidades com **uma solução única** para diferentes sistemas de bases de dados
