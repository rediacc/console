---
title: "Forense: evidências de dentro de um repositório comprometido"
description: "Registos de fluxos de rede e de aberturas de ficheiros sensíveis por repositório, ao nível que o cliente escolhe, enviados a cada 30 segundos como lotes assinados e encadeados. Cobre os três níveis de captura, o gatilho de pico, as quotas do plano, a deteção offline e no servidor, e o que o servidor consegue ler."
category: "Guides"
tags:
  - security
  - compliance
subcategory: data-protection
order: 9
language: pt
sourceHash: "cb8be2dcf3970c81"
sourceCommit: "f9ac63ac37dff49f6c980f00fdacb7e41099ce81"
---

# Forense

A forense responde a duas perguntas quando o software que corre dentro de um repositório é comprometido: quando é que os dados foram levados e quais foram. A Rediacc não consegue fechar uma falha em software de terceiros, por isso a funcionalidade regista evidências que sobrevivem ao comprometimento. Os registos são escritos por um coletor com permissões de root na máquina, fora da sandbox do repositório, e enviados para um bucket a que os administradores do cliente não têm acesso.

Os registos mostram volume, destino e momento. Os registos de fluxo provam volume e destino, não conteúdo. O [fluxo de trabalho de incidentes](/pt/docs/incident-response) lê-os, e os [relatórios de incidentes](/pt/docs/incident-reports) transformam-nos em documentos assinados para um regulador.

## O que é registado

A captura é feita por repositório. Os repositórios usam a rede do anfitrião, por isso o tráfego é atribuído por cgroup (a slice do próprio repositório), nunca por endereço IP.

| Registo | Conteúdo |
|---|---|
| Fluxo de rede | Hora, processo, endereço e porta de destino, protocolo, bytes enviados e recebidos, nome DNS quando conhecido, e ASN e país do destino quando conhecidos |
| Abertura de ficheiro | Hora, processo e caminho, para um caminho que corresponde à lista de caminhos sensíveis |
| Heartbeat | Uma marca assinada em cada lote, para que um coletor parado apareça como uma lacuna e não como silêncio |

A lista sensível predefinida abrange ficheiros `.env`, ficheiros de chaves e certificados (`*.pem`, `*.key`, `id_rsa*`, `id_ed25519*`), bases de dados de palavras-passe (`*.kdbx`), dumps e ficheiros de bases de dados (`*.sql`, `*.dump`, `*.bak`, `*.sqlite*`) e diretórios de dados de bases de dados como `pgdata`. Um repositório pode alargar a lista ou substituí-la pelos seus próprios padrões.

Os conteúdos dos pacotes e dos ficheiros nunca são registados.

## Níveis de captura

Cada repositório tem um único nível, e o mais baixo é o predefinido. Um nível mais alto regista tudo o que um mais baixo regista.

| Nível | Registado |
|---|---|
| `basic` | Um resumo a cada 5 minutos por destino, porta e protocolo, com bytes de entrada e saída |
| `standard` | Um registo de fluxo por minuto, com processo e nome DNS |
| `full` | Standard, mais aberturas de ficheiros em caminhos sensíveis |

O nível é definido por repositório:

```bash
rdc forensics level mail basic
rdc forensics level mail standard
rdc forensics level mail full
```

O coletor limita o nível ao que o plano inclui. Quando um plano não tem quota de forense, o repositório não regista nada.

### O gatilho de pico

Todos os níveis armam um gatilho. Quando os bytes de saída de um repositório num minuto ultrapassam dez vezes a sua própria média móvel (e mais de 50 MiB por minuto), depois de o repositório ser observado durante 24 horas, o repositório passa para Full durante 24 horas. Um minuto que dispara não entra na média, para que uma exfiltração não possa subir a linha de base que deveria apanhar a seguinte.

## Planos e quotas

A forense destina-se a planos pagos e só regista enquanto o plano estiver pago. Uma subida de plano começa sem histórico.

| Plano | Quota de forense |
|---|---|
| Free, Community | 0 (nada é registado) |
| Professional | 25 GB |
| Business | 125 GB |
| Enterprise | 512 GB, ou uma quota personalizada definida pelos administradores da Rediacc |

A quota corresponde a um quarto da quota de cópias de segurança do plano e é contabilizada à parte. Mais quota só se obtém com uma subida de plano.

Quando a quota está cheia, os registos mais antigos são removidos primeiro (FIFO). Os últimos 7 dias ficam bloqueados e nunca são removidos, porque o bucket os bloqueia durante 7 dias. Se só os bytes bloqueados já excedessem a quota, os novos lotes são recusados. Se a ingestão prevista para 7 dias não coubesse, o nível é limitado a Basic. Os proprietários e administradores recebem um aviso aos 80 por cento da quota, quando o limite desce para Basic e quando um lote é recusado.

Os registos que caem dentro de um incidente declarado ficam fora da remoção até 30 dias depois de o incidente ser fechado. Consulte a [resposta a incidentes](/pt/docs/incident-response).

## Envio e integridade

O coletor corta um lote a cada 30 segundos. Cada lote é assinado com a chave de spool da máquina e leva o hash do lote anterior, pelo que um lote removido ou editado quebra a cadeia. Os lotes são enviados através de URLs pré-assinados que só permitem criar, gerados a partir do blob de licença da máquina, por isso a máquina pode acrescentar registos mas não os pode substituir nem apagar. Quando a ligação se perde, os lotes aguardam num spool local assinado e são enviados quando a ligação regressa.

A compactação noturna junta os lotes num ficheiro diário por repositório e num ficheiro de cabeçalhos por máquina, onde cada cabeçalho assinado é listado e qualquer lacuna é assinalada. Os ficheiros diários de auditoria da conta encadeiam-se da mesma forma, por organização e por dia.

`rdc forensics verify` e o botão Verify evidence da página de investigação recalculam estas cadeias. Consulte a [resposta a incidentes](/pt/docs/incident-response).

## Deteção

A deteção de anomalias corre duas vezes. Um detetor estatístico na máquina reage de imediato, passando o repositório para Full. O servidor corre os seus próprios detetores na ingestão, pelo que a deteção sobrevive a um anfitrião comprometido. Nenhuma IA corre por cada registo.

Os detetores estão em camadas e cada repositório aprende com o seu próprio tráfego:

| Detetor | Procura |
|---|---|
| Linhas de base por hora da semana | Bytes, ligações, destinos distintos, novos nomes DNS e novos processos fora do ritmo habitual do repositório para essa hora da semana |
| Half-Space Trees | Um fluxo diferente dos fluxos vistos antes |
| ECOD e HBOS | Lotes de fluxos que pontuam como atípicos, com as características que determinaram a pontuação |
| Visto pela primeira vez | Um processo a abrir um ficheiro sensível que nunca tinha aberto |

Cada deteção traz os motivos por característica que a produziram, e a explicação é um modelo construído a partir desses motivos. Offline não há modelo de linguagem. Uma deteção torna-se um aviso da conta e um e-mail para proprietários, administradores e o contacto de segurança. Quando a máquina está offline, age logo localmente (captura Full e um registo no seu spool assinado) e entrega o alerta quando a ligação regressa, mantendo a hora original da deteção.

### Pacotes de modelos

Os parâmetros dos detetores são distribuídos como pacotes assinados em `data.rediacc.com/models/`, carregados pela tarefa de publicação (ainda não há nenhum canal publicado lá): ficheiros endereçados por conteúdo, um manifesto assinado com uma chave de modelo Ed25519 offline incorporada no renet, uma versão mínima do renet e uma versão que só aumenta, pelo que um downgrade é recusado. Um pacote é verificado antes de ser instalado, e o anterior pode ser restaurado.

```bash
renet models status
renet models update
renet models rollback
```

As instalações isoladas da rede recebem o mesmo pacote assinado dentro de `rdc server bundle`, a menos que se passe `--no-models`.

## O que o servidor consegue ler

O servidor de contas lê os registos, porque a linha cronológica, a verificação e os detetores do servidor precisam deles: destinos, portas, nomes de processos, nomes DNS, contagens de bytes e caminhos de ficheiros sensíveis. Não recebe conteúdos de pacotes nem de ficheiros.

O endereço de um cliente de entrada é guardado truncado nos registos (para /24 em IPv4 e /48 em IPv6), e o endereço completo fica numa secção separada que é apagada após 30 dias. O hash da secção apagada permanece no cabeçalho assinado, pelo que a cadeia continua a verificar e o verificador indica o endereço como ocultado. Os destinos de saída ficam completos, porque são a evidência.

Os clientes abrem os registos através de uma investigação, que exige um plano pago, a função de proprietário ou administrador e uma reautenticação recente, e cada consulta é auditada. O suporte da Rediacc só vê dados forenses com uma autorização limitada no tempo emitida pelo cliente. Os termos de tratamento estão no [acordo de tratamento de dados](/pt/data-processing-agreement).
