---
title: "Relatórios de incidentes: por fases, assinados e verificáveis"
description: "Gere o alerta precoce, a notificação e o relatório final de um incidente num repositório de cliente em JSON, STIX 2.1 ou PDF. Cada relatório é assinado com Ed25519, traz um link de verificação com QR e mapeia os seus campos para a NIS2, o formato 2025/302 e o art. 33.º, n.º 3, do RGPD."
category: "Guides"
tags:
  - security
  - compliance
subcategory: data-protection
order: 11
language: pt
sourceHash: "777d8ae1dde17294"
sourceCommit: "0531ce955ea0d1658b8fceefd6aa44e3c270521c"
---

# Relatórios de incidentes

Um incidente declarado ([resposta a incidentes](/pt/docs/incident-response)) produz três relatórios por fases para o cliente entregar a um regulador. A Rediacc gera os documentos a partir das evidências. Saber se um incidente é significativo ou notificável continua a ser um juízo do cliente, e todos os relatórios o dizem.

## Fases

Cada fase lista as secções que exige e nenhuma outra, por isso uma secção de que a fase não precisa é omitida em vez de ficar em branco.

| Fase | Prazo | Acrescenta |
|---|---|---|
| Alerta precoce | 24 horas após o conhecimento | Cabeçalho, linha cronológica, indicadores de comprometimento, impacto malicioso suspeito e transfronteiriço |
| Notificação | 72 horas após o conhecimento | Avaliação inicial, impacto nos dados (categorias, números aproximados, Estados-Membros) e técnicas ATT&CK |
| Final | Um mês civil após a notificação | Causa raiz e medidas de mitigação |

O relatório final segue-se a uma notificação, por isso a notificação é gerada primeiro. Cada fase inclui as secções da fase anterior.

Cada facto de um relatório indica como é conhecido: observado nas evidências, introduzido pelo cliente ou inferido. Um facto inferido traz uma confiança e o motivo do detetor. A avaliação, as categorias de dados, os Estados-Membros, a causa suspeita, as ações tomadas, o ponto de contacto e as técnicas são dados que o cliente introduz na página do incidente antes de gerar.

## Formatos

| Formato | Utilização |
|---|---|
| JSON | A forma canónica e verificável |
| STIX 2.1 | Um pacote de indicadores para ferramentas de threat intelligence |
| PDF | Um documento legível, que apresenta escritas não latinas, com o aviso legal, um código QR e o hash do relatório no rodapé de cada página |

A partir da página do incidente, cada fase tem um botão de descarga por formato. A partir da linha de comandos:

```bash
rdc incident export <id> --stage early-warning
rdc incident export <id> --stage notification --format stix
rdc incident export <id> --stage final --format pdf --out ./reports
```

O formato predefinido é JSON. `--format` só se aplica com `--stage`. O ficheiro é escrito com o seu identificador de relatório.

## Assinatura e verificação

Cada relatório é assinado com uma chave de relatório Ed25519, e o identificador, a fase e o hash do relatório ficam num registo público. A assinatura cobre o conteúdo canónico do relatório, pelo que qualquer alteração após a assinatura é detetada.

Um relatório é verificado em três locais:

- A página de verificação em `/account/verify/report/<id>`, que o código QR do PDF abre. A verificação corre no navegador contra a chave de relatório publicada, e nada é enviado. Um ficheiro JSON é totalmente verificado. Um PDF não pode ser recalculado em hash no navegador, por isso a página confirma que o PDF traz o hash do relatório e remete para o ficheiro JSON para uma verificação completa.
- A linha de comandos, para um relatório JSON:

```bash
rdc forensics verify --report ./reports/<report-id>.json
```

O comando termina com código 1 quando o conteúdo ou a assinatura não coincidem. Um PDF é verificado através do relatório JSON a partir do qual foi criado.

- O carimbo de evidências dentro do relatório, que regista o resultado de Verify evidence para a janela: quem verificou, com que versão e quando.

## Mapa de campos

Cada campo do relatório é mapeado para os regimes ao abrigo dos quais o cliente notifica, para que o conteúdo possa ser transposto sem voltar a ser escrito. O mapa abrange três regimes: NIS2 art. 23.º, n.º 4, o formato de notificação de incidentes do Regulamento de Execução (UE) 2025/302 e o art. 33.º, n.º 3, do RGPD. Exemplos:

| Campo do relatório | NIS2 | RGPD |
|---|---|---|
| Momento do conhecimento | Art. 23(4)(a) | Art. 33(1) |
| Cronologia | Art. 23(4)(d) | Art. 33(3)(a) |
| Ponto de contacto | Art. 23(4) | Art. 33(3)(b) |

Um campo sem equivalente num regime explica porquê em vez de ser omitido. A notificação do art. 33.º, n.º 3, do RGPD não tem número de referência nem hora de encerramento, por exemplo.

## O que um relatório não afirma

Duas declarações são impressas em cada fase:

- Os registos de fluxo provam volume e destino, não conteúdo.
- Saber se o incidente é significativo ou notificável é um juízo do cliente.

A Rediacc não apresenta nada a um regulador em nome do cliente.
