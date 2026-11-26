---
title: "Resposta a incidentes: investigar, declarar e preservar evidências"
description: "Abra uma investigação sobre um repositório ou uma máquina, leia uma única linha cronológica de auditoria, execuções, fluxos e aberturas de ficheiros, verifique as cadeias de hash, declare um incidente para congelar as evidências e iniciar os relógios de 24 horas, 72 horas e um mês, e conduza tudo a partir do rdc."
category: "Guides"
tags:
  - security
  - compliance
subcategory: data-protection
order: 10
language: pt
sourceHash: "07d8b9d09d0e2191"
sourceCommit: "d93166e47a19c588a2284e21d263cca7f8a3578d"
---

# Resposta a incidentes

Aqui, um incidente é o que acontece dentro dos repositórios do próprio cliente. A página de investigação, os comandos `rdc incident` e os leitores `rdc repo flows` e `rdc repo opens` trabalham todos a partir dos registos descritos em [forense](/pt/docs/forensics). Os incidentes nos sistemas da própria Rediacc seguem a [resposta a incidentes de segurança](/pt/docs/security-incident-response).

## Acesso

A investigação exige um plano pago e a função de proprietário ou administrador. Abrir uma pede uma reautenticação recente, e uma investigação aberta mantém-se válida durante 60 minutos. Cada consulta fica escrita no registo de auditoria.

O suporte da Rediacc só vê dados forenses com uma autorização de suporte emitida pelo cliente. Uma autorização dura no máximo 7 dias e pode ser revogada a qualquer momento.

As leituras da CLI precisam do scope `forensics:read`, e declarar e fechar precisam de `incident:manage`. Um início de sessão na CLI inclui ambos para proprietários e administradores, após uma aprovação elevada no navegador. Quando um comando responde que é necessária uma aprovação elevada recente, o portal da conta pede-a e o comando volta a ser executado.

## A linha cronológica

A página Investigate junta um âmbito (um repositório ou uma máquina) numa única linha cronológica com cinco tipos de linha: eventos de auditoria da consola, execuções, fluxos de rede, aberturas de ficheiros e anomalias. As alterações desde o último instantâneo podem ser comparadas com ele. Um seletor de janela temporal define a janela, e uma janela abrange no máximo 31 dias.

Um intervalo sem evidências aparece como uma linha de lacuna que indica a máquina e o motivo, nunca como um intervalo vazio. Um gráfico de bytes de saída por minuto e uma lista dos principais destinos ficam acima das linhas.

As mesmas leituras estão disponíveis na linha de comandos:

```bash
rdc repo flows mail --since 24h
rdc repo flows mail --since 2026-11-20T00:00:00Z --until 2026-11-21T00:00:00Z
rdc repo opens mail --since 7d
```

`--since` e `--until` aceitam um instante ISO 8601 ou um intervalo para trás a partir de agora, como `90m`, `24h` ou `7d`. A janela predefinida são as últimas 24 horas. As linhas de fluxo mostram hora, processo, destino, bytes de saída e entrada, e ASN e país quando conhecidos. As linhas de abertura mostram hora, processo e caminho, com os caminhos sensíveis assinalados.

## Verificar evidências

Verify evidence recalcula, no navegador, a cadeia de hash dos ficheiros diários de auditoria e as cadeias de lotes assinados dos registos forenses para a janela, e lista cada lacuna e cada edição. As assinaturas dos lotes são verificadas com as chaves de spool que o servidor de contas fixou para cada máquina. Uma chave escrita dentro das evidências nunca é considerada de confiança. O resultado é carimbado nos relatórios exportados.

Evidências acima de 2 GiB são demasiado grandes para o navegador. O mesmo módulo corre a partir da linha de comandos:

```bash
rdc forensics verify --dir ./incident-evidence
rdc forensics verify --dir ./incident-evidence --since 7d --machine-key web-1=<public-key-hex>
```

O comando termina com código 1 quando encontra alguma lacuna ou edição. `--machine-key <machine>=<64 hex characters>` fornece uma chave externa ao diretório e pode ser repetido. Uma máquina sem chave externa falha.

## Declarar um incidente

Declarar congela as evidências. O registo da conta entra primeiro, e depois o repositório é preparado para a investigação:

1. O incidente é registado com a sua janela, quem o declarou e quando a organização teve conhecimento.
2. Uma retenção contra remoção cobre a janela, e as regras de bloqueio do bucket estendem-se sobre ela, para que o FIFO não possa remover esses dias.
3. O repositório é bifurcado como instantâneo forense, com a etiqueta `incident-<id>`.
4. O nível de captura do repositório passa para Full.

Três relógios começam a contar a partir do momento do conhecimento, que pode ser definido antes da declaração e nunca depois: o alerta precoce vence 24 horas após o conhecimento, a notificação 72 horas depois, e o relatório final um mês civil após a notificação (contado a partir do prazo de notificação até que uma notificação seja registada). A página mostra cada relógio como pendente, a vencer em menos de 6 horas, vencido ou concluído.

```bash
rdc incident declare mail
rdc incident declare mail --since 48h --aware-at 2026-11-20T09:30:00Z
rdc incident status
rdc incident status <id>
```

Um passo falhado na máquina deixa o registo e a sua retenção no lugar, termina com código 1 e indica o comando que volta a executar apenas os passos falhados:

```bash
rdc incident declare mail --resume <id>
```

`--resume` mantém a janela e o conhecimento da declaração original, pelo que `--since`, `--until` e `--aware-at` não se combinam com ele.

## Exportar as evidências

`rdc incident export` escreve a janela do incidente num diretório: o registo do incidente com os seus relógios, a linha cronológica unificada, os agregados de bytes de saída, o manifesto de cadeia em bruto e os ficheiros em bruto que ele lista. Quando o manifesto lista ficheiros diários de auditoria ou ficheiros de cabeçalhos forenses, as cadeias são verificadas pelo caminho e o resultado vai para `verification.json`. O comando termina com código 1 quando as evidências mostram uma lacuna ou uma edição.

```bash
rdc incident export <id>
rdc incident export <id> --out ./incident-evidence
```

Com `--stage`, o mesmo comando escreve em vez disso um relatório assinado. Consulte os [relatórios de incidentes](/pt/docs/incident-reports).

## Fechar um incidente

```bash
rdc incident close <id>
```

Nada é libertado de imediato. A retenção contra remoção e as regras de bloqueio do bucket terminam 30 dias após o fecho.

## Perguntar à IA

A página de investigação tem um assistente que responde a perguntas sobre o âmbito e a janela abertos. Lê apenas esse âmbito e essa janela, com um bilhete de utilização única gerado a partir da investigação aberta, que pode ser resgatado durante 15 minutos. A pergunta e as linhas que lê vão para o fornecedor de IA da própria organização. O assistente pode executar os comandos `rdc` acima com as mesmas regras de permissões de qualquer outro comando.

## Comandos

| Comando | Finalidade |
|---|---|
| `rdc repo flows <ref>` | Fluxos de rede de um repositório numa janela |
| `rdc repo opens <ref>` | Aberturas de ficheiros sensíveis de um repositório numa janela |
| `rdc forensics level <ref> <level>` | Definir o nível de captura |
| `rdc forensics verify` | Verificar um diretório de evidências ou um relatório assinado |
| `rdc incident declare <ref>` | Registar um incidente, bifurcar o repositório e passar para Full |
| `rdc incident status [id]` | Listar incidentes, ou mostrar um com os seus relógios |
| `rdc incident export <id>` | Escrever a janela de evidências, ou um relatório assinado com `--stage` |
| `rdc incident close <id>` | Fechar um incidente |
