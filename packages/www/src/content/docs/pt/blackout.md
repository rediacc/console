---
title: Continuidade Bancária Durante Apagão
description: Manter as operações bancárias durante cortes de energia com espelhamento de dados intercontinental.
category: Use Cases
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
* As bases de dados bancárias centrais e os sistemas de transações foram **continuamente replicados** para centros de dados nos Estados Unidos
* Todos os dados de clientes e registos de transações foram sincronizados com **menos de 3 segundos de atraso**

### 2. **Transição Operacional Contínua**
* Quando os servidores espanhóis perderam energia, o tráfego foi **automaticamente redirecionado** para sistemas baseados nos EUA
* Os clientes experienciaram apenas uma breve interrupção de 47 segundos antes de os serviços serem retomados

### 3. **Continuação Remota do Serviço**
* Centros de atendimento em países não afetados acederam aos sistemas replicados para manter o apoio ao cliente
* As aplicações de banca móvel mantiveram-se funcionais ao ligar-se a centros de dados alternativos

## Resultado Potencial

**Continuidade do Negócio:**
* Enquanto os concorrentes estavam offline por mais de 14 horas, o banco manteve **98% de disponibilidade de serviço**

**Confiança dos Clientes:**
* O banco foi a única grande instituição financeira a processar transações durante a crise
* A satisfação dos clientes aumentou 27% em inquéritos pós-crise

**Proteção Financeira:**
* O banco evitou aproximadamente €370 milhões em perdas por falhas de transações
* Nenhum dado foi perdido ou corrompido, eliminando operações de recuperação dispendiosas

**Vantagem Competitiva:**
* O banco conquistou 140.000 novos clientes no mês seguinte, provenientes de concorrentes que falharam em manter o serviço
