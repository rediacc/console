---
title: "Resposta a incidentes de segurança"
description: "Como a Rediacc trata seus próprios incidentes de segurança: os avisos escalonados aos clientes, os campos do GDPR Art. 33(3), o caminho de notificação do CRA e o que os clientes recebem."
category: "Legal"
tags:
  - security
  - compliance
subcategory: foundations
order: 10
language: pt
sourceHash: "6b9f728f093ecb0c"
sourceCommit: "72636750e43d473936cbb242ec9c7511fd246f65"
---

Esta página descreve o que acontece quando a própria Rediacc sofre um incidente de segurança, como o comprometimento de seus sistemas ou uma vulnerabilidade ativamente explorada em seus produtos. Incidentes dentro dos repositórios do próprio cliente cabem ao cliente investigar e notificar, e a Rediacc fornece as ferramentas de evidência para isso. Relatos de vulnerabilidades vindos de fora são tratados na [política de divulgação](/pt/docs/security-disclosure-policy).

## Etapas

Cada incidente tem um relógio que começa quando a Rediacc toma conhecimento dele. As informações são liberadas por etapas, porque o quadro completo raramente é conhecido no primeiro dia e o GDPR Art. 33(4) permite que as informações sejam fornecidas em fases.

| Etapa | Prazo | Conteúdo |
|-------|-----|---------|
| Alerta precoce | em até 24 horas | o que se sabe até o momento e se há suspeita de atos maliciosos |
| Notificação | em até 72 horas | a natureza do incidente, uma avaliação inicial e as medidas tomadas |
| Relatório final | em até um mês | uma descrição detalhada, a causa raiz e as medidas aplicadas e em andamento |

## Os campos do Art. 33(3)

Cada etapa traz os quatro itens listados no GDPR Art. 33(3):

1. a natureza da violação, com as categorias e o número aproximado de titulares de dados e de registros de dados pessoais em causa
2. o nome e os dados de contato do ponto de contato para mais informações
3. as prováveis consequências
4. as medidas adotadas ou propostas para tratar a violação, incluindo medidas para atenuar seus possíveis efeitos adversos

Quando um valor ainda não é conhecido, a etapa informa isso e indica a data em que será conhecido.

## O que os clientes recebem

Quando um incidente afeta uma organização:

- cada etapa é enviada como aviso no portal da conta e por e-mail, aos proprietários e administradores da organização e ao seu contato de segurança
- o aviso e o e-mail são enviados independentemente das preferências de notificação, por serem comunicações de segurança
- um banner no portal leva à página do incidente, que mostra todas as etapas publicadas
- cada etapa oferece um pacote STIX 2.1 com os indicadores de comprometimento, em formato legível por máquina que as ferramentas de segurança podem importar

Uma organização que não é afetada não recebe nada. Proprietários e administradores definem o contato de segurança da organização no portal, para que a mensagem chegue à pessoa certa.

## Notificação às autoridades

A Rediacc notifica seus próprios incidentes quando a lei exige.

- **GDPR.** Quando a Rediacc atua como operadora, o aviso escalonado informa o controlador sem demora injustificada (Art. 33(2)), e o controlador decide sobre a notificação à sua autoridade de controle. Quando a Rediacc é a controladora, ela notifica a autoridade de controle competente em até 72 horas, sempre que possível (Art. 33(1)).
- **Cyber Resilience Act.** Desde 11 de setembro de 2026, o Art. 14 do Regulation (EU) 2024/2847 exige que o fabricante notifique uma vulnerabilidade ativamente explorada ou um incidente grave que afete a segurança de um produto com elementos digitais ao CSIRT designado e à ENISA, por meio da plataforma única de notificação. Aplicam-se as mesmas etapas de 24 horas, 72 horas e relatório final, e o mesmo registro do incidente alimenta tanto o aviso ao cliente quanto a notificação.

## Reportar um incidente suspeito

Quem suspeitar de um incidente que afete a Rediacc, inclusive um cliente que note um comportamento inesperado em um componente da Rediacc, escreve para [security@rediacc.com](mailto:security@rediacc.com). O relato de uma vulnerabilidade segue a [política de divulgação](/pt/docs/security-disclosure-policy).
