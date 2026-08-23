---
sourceHash: "8817b7a0a9304cd0"
sourceCommit: "b8e332b73573133a282b5c508bc049af1fbeb581"
title: Continuidade Bancária Durante Apagão
description: Manter as operações bancárias durante cortes de energia com espelhamento de dados intercontinental.
category: Use Cases
tags:
  - backup
  - migration
subcategory: resilience
order: 6
language: pt
---

> **Quando as Luzes se Apagam, o Seu Negócio Continua.**

**Nota:** Este é um **exemplo de caso de uso** que demonstra como a Rediacc pode resolver este problema. Como startup, estes cenários representam aplicações potenciais e não estudos de caso concluídos.

**Cenário de Crise:** Um grande apagão afetou Espanha e Portugal a 28 de abril de 2025, desencadeado por uma linha de transmissão danificada em França. O corte de energia derrubou infraestrutura de TI crítica, fazendo com que os principais bancos e empresas tecnológicas perdessem o acesso aos seus sistemas.

## O Problema

A rede elétrica ibérica enfrentou uma cascata de falhas catastróficas:

* Um **incêndio no sudoeste de França** danificou uma linha de transmissão crítica
* O dano causou a **desconexão súbita** das interligações transfronteiriças
* Espanha e Portugal ficaram **eletricamente isoladas** da rede europeia

**Impacto nas Empresas:**
* Centros de dados em toda a Espanha sofreram **perda imediata de energia**
* Os geradores de backup falharam em ativar em vários locais devido a falhas nos sistemas de controlo
* Os sistemas bancários ficaram offline, impedindo transações em todo o país

**Desafios de Infraestrutura de TI:**
* Os **sistemas de backup locais** foram ineficazes por estarem localizados na mesma região afetada
* Os **procedimentos de recuperação de emergência** dependiam de acesso local a servidores físicos
* Os **planos de continuidade de negócio** não contemplavam falhas de energia a nível nacional com duração superior a 4 horas

## Impacto da Crise

A interrupção dos serviços de TI levou a:
* **Colapso do sistema financeiro** com estimativas de €4,5 mil milhões em atrasos de transações
* Dados críticos de negócio inacessíveis por mais de 14 horas
* Plataformas de comércio eletrónico importantes com encerramento total
* Sistemas de atendimento ao cliente a falhar em múltiplas indústrias

## Solução Rediacc

Um grande grupo bancário espanhol que implementou a solução de replicação transcontinental da Rediacc manteve as operações durante toda a crise:

![Banking Continuity During Blackout](/img/blackout-continuity.svg)

### 1. **Espelhamento de Dados Intercontinental**
* As bases de dados bancárias centrais e os sistemas de transações seriam **continuamente replicados** para centros de dados nos Estados Unidos
* Os dados dos clientes e os registos de transações manter-se-iam sincronizados dentro do atraso de replicação que a sua ligação e o seu volume permitissem

### 2. **Transição Operacional Contínua**
* Se os servidores espanhóis perdessem energia, o tráfego seria **automaticamente redirecionado** para sistemas baseados nos EUA
* Os clientes notariam apenas uma breve interrupção até o redirecionamento se concluir, em vez de uma falha tão longa quanto a da rede elétrica

### 3. **Continuação Remota do Serviço**
* Centros de atendimento em países não afetados poderiam aceder aos sistemas replicados e continuar a apoiar os clientes
* As aplicações de banca móvel manter-se-iam funcionais ao ligar-se a centros de dados alternativos

## Resultado Potencial

**Continuidade do Negócio:**
* Os concorrentes estiveram offline mais de 14 horas. Um banco com esta arquitetura continuaria a operar durante toda essa janela

**Continuidade do Serviço:**
* Poderia continuar a processar transações enquanto instituições sem uma segunda região não conseguiriam

**Proteção Financeira:**
* Evitaria as perdas por falhas de transações que se acumulam a cada hora em que um sistema de pagamentos está indisponível
* Nenhum dado seria perdido ou corrompido, pelo que nenhuma operação de recuperação seria necessária
