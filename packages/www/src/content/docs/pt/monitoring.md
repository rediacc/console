---
title: "Monitorização"
description: "Monitorize o estado da máquina, contentores, serviços, repositórios e execute diagnósticos."
category: "Guides"
tags:
  - operations
subcategory: operations
order: 9
language: pt
sourceHash: "acef592a7065cac7"
sourceCommit: "9f58d83e01b4d46f8ce31af467a203b4d195e801"
---

# Monitorização

O Rediacc fornece comandos de monitorização integrados para inspecionar o estado da máquina, contentores em execução, serviços, estado do repositório e diagnósticos do sistema.

## Estado da Máquina

Obter um relatório de estado completo para uma máquina:

```bash
rdc machine health server-1
```

Isto reporta:
- **Sistema**: tempo de atividade, memória (aviso acima de 80 %, erro acima de 90 %), uso do disco e do datastore (aviso acima de 85 %, erro acima de 95 %)
- **Contentores**: contagens de em execução, saudáveis e não saudáveis; um contentor num ciclo `Restarting` é crítico
- **Serviços**: unidades systemd com falha (um erro) e unidades que reiniciam continuamente (crítico)
- **Armazenamento**: estado de saúde SMART (um disco a falhar é crítico) e temperatura do disco
- **Repositórios**: repositórios de arranque automático que não estão montados e uso do sistema de ficheiros de cada repositório (aviso acima de 85 %, erro acima de 95 %)
- **Cópias de segurança**: repositórios sem cópia há mais de 10 dias, atrasados em relação ao agendamento ou ao destino, ou cuja última verificação falhou
- **Licenças**: licenças de repositório expiradas, em falta, divergentes ou inválidas, e licenças a renovar
- **Processos do renet**: daemons que ainda executam um binário do renet substituído
- **Saúde do repositório**: o resultado do `health()` de cada repositório montado (ver abaixo)
- **Certificados**: certificados do proxy perto de expirar e CNAMEs de desafio ACME partilhados
- **Problemas**: problemas identificados

O código de saída é o veredicto: `0` sem achados (um repositório sem verificação `health()` é listado como «sem verificação», nunca contado como saudável), `1` aviso, `2` erro, `3` crítico (um disco a falhar, ou um contentor ou serviço num ciclo de reinício). Use `--output json` para saída legível por máquina; inclui `repo_health` (um relatório por repositório) e `findings`, cada um com um código, uma gravidade (`info`, `warning`, `error` ou `critical`), um assunto, um detalhe e, onde existe uma correção, `fix` (ver [Reparação](#repair)).

## Saúde do repositório

Um Rediaccfile pode definir uma função `health()` que verifica os serviços do próprio repositório ([Serviços](/pt/docs/services)): saída `0` ok, `1` aviso, `2` erro. Execute-a para um repositório:

```bash
rdc repo health my-app@server-1
```

O comando termina com o pior nível entre os Rediaccfiles do repositório. Um repositório em que nenhum Rediaccfile define `health()` imprime **sem verificação** e termina com `0`; nunca é reportado como saudável. Um `health()` que esgota o tempo, é terminado ou sai com qualquer outro código é um erro, tal como a impossibilidade de contactar a máquina (saída `2`).

O `rdc machine health` executa o `health()` de cada repositório montado numa só chamada e incorpora o pior nível no seu próprio código de saída, com um achado por repositório como aviso (`repo.health.warning`) ou erro (`repo.health.error`). Os repositórios sem verificação são listados, não reportados. Quando o renet da máquina é anterior às verificações de saúde de repositório, o resultado é um aviso, `renet.repo-health.unsupported`, até o `rdc machine setup` o atualizar.

## Expiração de certificados e desafios ACME

O `rdc machine health` lê os certificados ACME do proxy e reporta `cert.expiry.near` para cada um a menos de 21 dias de expirar (um aviso) ou a menos de 7 dias (um erro). O proxy renova com 30 dias de antecedência, pelo que um certificado abaixo de 21 dias significa que a sua renovação falha há pelo menos nove dias.

Também reporta `acme.challenge.cname-shared` quando o registo `_acme-challenge.<name>` do nome de um certificado segue um CNAME para um nome que não é ele próprio um nome `_acme-challenge.`, ou quando dois nomes acabam no mesmo nome. Um registo wildcard que é um CNAME produz esta forma: todos os desafios caem num só nome e as renovações colidem. Uma delegação deliberada (por exemplo, `_acme-challenge.mail.example.com` a apontar para `_acme-challenge.mail.example.io`) não é reportada; liste qualquer outra delegação pretendida em `ACME_DELEGATED_NAMES` (uma lista separada por vírgulas de nomes de certificado) no `config.env` do proxy. Um nome cuja cadeia de desafio não pôde ser resolvida (nenhum resolvedor DNS respondeu por ele) é reportado como `acme.challenge.unknown`, um aviso, porque a verificação não foi executada para ele.

## Reparação

Cada achado traz um código e, onde existe uma correção segura, um `fix` com `action`, uma `class` de segurança e `window_only`. O `rdc machine health` continua só de leitura; o `rdc machine repair` é o comando que age:

```bash
rdc machine repair server-1 --dry-run     # list what would run
rdc machine repair server-1               # run the auto-safe fixes, then re-check
rdc machine repair server-1 --code cert.expiry.near
```

| Classe | Significado |
|---|---|
| `auto-safe` | Executa por predefinição: reiniciar um contentor ou o Traefik, fazer trim e limpeza, escrever a âncora ACME |
| `auto-with-backup` | Só executa com `--with-backup`, depois de um snapshot bem-sucedido do repositório; um snapshot falhado cancela a correção |
| `operator-only` | Nunca executa. O comando imprime o comando exato a executar manualmente. Tudo o que apaga dados nomeados ou gasta dinheiro fica aqui |

`window_only` é uma condição adicional à classe: a correção só executa dentro da janela de manutenção da máquina, `HH:MM-HH:MM` em UTC (pode atravessar a meia-noite). Uma máquina sem janela nunca executa estas correções por si só; `--window-override` executa-as manualmente. Defina ou limpe a janela com:

```bash
rdc machine repair server-1 --set-window 00:00-03:00
rdc machine repair server-1 --set-window off
```

Cada correção verifica primeiro que o seu achado ainda existe, pelo que uma segunda execução não tem nada a fazer. As correções que atuam sobre a mesma coisa executam uma vez (um reinício do Traefik cobre todos os certificados). Cada correção é registada no journal da máquina com a etiqueta `rediacc-repair` e no JSON `actions` (`code`, `subject`, `action`, `class`, `result`, `before`, `after`), e a execução termina com uma nova verificação completa. O código de saída é `0` quando nada resta, `1` quando restam avisos ou itens operator-only, e `2` quando resta um erro ou um achado crítico, ou uma correção falhou. `rdc machine repair` nunca termina com `3`; só `rdc machine health` o faz.

| Achado | Correção | Classe |
|---|---|---|
| `datastore.usage.high`, `repo.disk.high` | Trim e depois limpeza de contentores parados, volumes anónimos órfãos e imagens não utilizadas | auto-safe |
| `container.unhealthy`, `container.restart-loop` | Reiniciar o contentor | auto-safe |
| `renet.binary.replaced` | Reiniciar os supervisores de repositório afetados (`rdc machine restart-services --include-docker`, limitado a eles) | auto-safe, só na janela |
| `cert.expiry.near` | Reiniciar o Traefik para que repita a renovação | auto-safe |
| `acme.challenge.cname-shared` | Escrever a âncora ACME (abaixo) | auto-safe (operator-only quando uma delegação é declarada e não existe um token Cloudflare utilizável) |
| `repo.health.warning`, `repo.health.error` | Executar o `repair()` do repositório ([Serviços](/pt/docs/services)) | a classe que o Rediaccfile declara |
| `repo.unmounted`, `service.failed`, `service.restart-loop`, `backup.*`, `license.*`, `renet.repo-health.unsupported` | Impresso como o comando a executar | operator-only |

Os achados sem correção (falhas SMART, temperatura, memória, o disco do sistema, uma verificação falhada) são reportados e deixados ao operador.

A limpeza nunca toca no hub: os contentores com a etiqueta `rediacc.hub.*` e os volumes com a etiqueta `rediacc.hub.user` ou com o nome `rediacc-hub-home-*` ficam excluídos, para que a pasta pessoal de um utilizador do hub sobreviva a cada recuperação de espaço. Um resíduo que o trim e a limpeza não conseguem libertar (volumes nomeados, grandes dados de aplicações) continua a ser uma decisão do operador.

### Reparação de repositório

```bash
rdc repo repair my-app@server-1 --dry-run
rdc repo repair my-app@server-1
```

O `rdc repo repair` executa as funções `repair()` do repositório com as mesmas classes: `auto-safe` executa, `auto-with-backup` precisa de `--with-backup`, e um `repair()` não declarado (`operator-only`) só executa depois de a pergunta ser respondida ou com `--yes`. Depois o `health()` executa novamente e o código de saída segue o nível em que termina: `0` ok ou sem verificação, `1` aviso, `2` erro ou um `repair()` falhado.

### A âncora ACME

Um registo DNS wildcard que é um CNAME faz com que todos os nomes `_acme-challenge.<host>` o sigam, pelo que todos os desafios caem num só nome e as renovações colidem (`acme.challenge.cname-shared`). A correção escreve um registo TXT com o valor `rediacc-acme-anchor` em cada `_acme-challenge.<name>` em colisão, através do token Cloudflare do proxy, e depois reinicia o Traefik. Um registo explícito tira o nome do alcance do wildcard, e o desafio cai onde deve. A correção só acrescenta registos, e uma âncora existente é deixada como está. Um nome de desafio que é ele próprio um CNAME não pode ter um registo TXT ao lado: a Cloudflare recusa a escrita, e a correção segue a mesma alternativa que para uma zona que o seu token não pode escrever (parágrafo seguinte).

Os nomes listados em `ACME_DELEGATED_NAMES` (uma lista separada por vírgulas de nomes de certificado no `config.env` do proxy) são delegações deliberadas: nunca são ancorados nem reportados. Quando o proxy não tem um token Cloudflare utilizável, a correção recorre a `LEGO_DISABLE_CNAME_SUPPORT=true` em `config.env`, mas só quando nenhum nome delegado está declarado, porque essa variável desativa o seguimento de CNAME para todos os nomes; com uma delegação declarada, o achado continua operator-only. A mesma correção executa em cada instalação do proxy (`rdc machine infra push`) e, por si só, com `renet proxy acme-fix` na máquina.

## Listar Contentores

Ver todos os contentores em execução em todos os repositórios numa máquina:

```bash
rdc machine status server-1 --containers
```

| Coluna | Descrição |
|--------|-------------|
| Name | Nome do contentor |
| Status | Tempo de atividade ou razão de saída |
| State | Em execução, saído, etc. |
| Health | Saudável, não saudável, nenhum |
| CPU | Percentagem de uso de CPU |
| Memory | Uso de memória / limite |
| Repository | Que repositório possui o contentor |

Opções:
- `--health-check`, Realizar verificações de saúde ativas nos contentores
- `--output json`, Saída JSON legível por máquina

A saída JSON inclui detalhes completos do contentor (`labels`, `port_mappings`, `image`, `id`) mais `repository` (nome resolvido), `repository_guid` (GUID original), `domain` e `autoRoute`.

## Listar Serviços

Ver serviços systemd relacionados com o Rediacc numa máquina:

```bash
rdc machine status server-1 --services
```

| Coluna | Descrição |
|--------|-------------|
| Name | Nome do serviço |
| State | Ativo, inativo, falhado |
| Sub-state | Em execução, morto, etc. |
| Restarts | Contagem de reinícios |
| Memory | Uso de memória do serviço |
| Repository | Repositório associado |

Opções:
- `--stability-check`, Sinalizar serviços instáveis (falhados, mais de 3 reinícios, reinício automático)
- `--output json`, Saída JSON legível por máquina

A saída JSON inclui detalhes completos do serviço com `repository` (nome resolvido) e `repository_guid` (GUID original).

## Listar Repositórios

Ver repositórios numa máquina com estatísticas detalhadas:

```bash
rdc machine status server-1 --repositories
```

| Coluna | Descrição |
|--------|-------------|
| Name | Nome do repositório |
| Size | Tamanho da imagem de disco |
| Mount | Montado ou desmontado |
| Docker | Daemon Docker em execução ou parado |
| Containers | Contagem de contentores |
| Disk Usage | Uso real do disco dentro do repositório |
| Modified | Hora da última modificação |

Opções:
- `--search <text>`, Filtrar por nome ou caminho de montagem
- `--output json`, Saída JSON legível por máquina

A saída JSON inclui `name` (resolvido) e `guid` (GUID original), e aninha os `containers` de cada repositório (com `domain`, `autoRoute`, `repository`/`repository_guid`) e arrays de `services`.

## Estado do Armazenamento

Inspecionar a fragmentação BTRFS e a partilha de reflink em todos os repositórios numa máquina:

```bash
rdc machine status server-1 --storage-health
```

| Coluna | Descrição |
|--------|-------------|
| Quota | O tamanho máximo do repositório (o seu teto de crescimento, definido na criação ou por resize/auto-grow) |
| Allocated | O espaço que a imagem esparsa ocupa atualmente no pool |
| Unique | Dados únicos reais pertencentes apenas a este repositório |
| Shared | Blocos de dados reutilizados entre repositórios via reflinks BTRFS (cópias gratuitas) |
| Reclaimable | A diferença entre alocado e usado que [`repo trim`](/pt/docs/repositories#reclaim-space-trim) pode devolver ao pool. Mostra `-` para repositórios desmontados |
| Discards | Se o volume encriptado passa discards (`on` para qualquer repositório montado por uma versão atual) |
| Divergence | Percentagem da imagem única deste repositório em vez de partilhada (maior significa mais recuperável se eliminado) |
| Frag | Extents por GB na imagem copy-on-write (apenas informativo) |

Quota e alocação são números diferentes propositadamente: um repositório com uma quota de 20 GB que armazena 6 GB de dados apenas custa ao pool o que efetivamente alocou. O pool pode assim prometer uma quota total superior à sua capacidade física, e a coluna Reclaimable mostra quanto da alocação de cada repositório já não está em uso e pode ser recuperada com trim.

Abaixo da tabela, um resumo do pool reporta o nível de preenchimento do datastore e quanto espaço os snapshots de backup estão a reservar:

```
Pool: 265.4 GB used, 95.2 GB free (73.6% full)
Backup snapshots pin 2.1 GB (1 active, 0 stale; stale ones are removed by 'rdc machine prune')
```

Enquanto um backup corre, o seu snapshot continua a referenciar todos os blocos que partilha com os repositórios ativos, pelo que eliminações e trims libertam menos espaço no pool até que esse ciclo de backup termine e o snapshot seja eliminado. Snapshots obsoletos de backups interrompidos são removidos automaticamente pelo mantenedor de armazenamento em poucos minutos.

O resumo mostra a poupança total dos reflinks BTRFS:

```
14 repos, 224.3 GB virtual size
Unique data: 323.7 MB | Shared: 224.0 GB | Efficiency: 99.9%
```

- O **tamanho virtual** é a soma de todos os tamanhos de imagem de repositório. É assim que os repositórios parecem ser, mas conta em duplicado os blocos partilhados via reflinks.
- Os **dados únicos** são o armazenamento real consumido por dados de repositório que existem apenas num repositório. É o que liberaria ao eliminar um repositório.
- O **partilhado** são dados reutilizados entre repositórios via reflinks BTRFS. Fazer fork de um repositório cria cópias de reflink que partilham blocos até que qualquer um dos lados escreva novos dados, momento em que os blocos divergem.
- A **eficiência** é a percentagem de dados reutilizados via reflinks. Maior é melhor. Uma máquina com muitos forks do mesmo pai mostrará eficiência próxima de 100%.

A coluna Frag é apenas informativa. Conta os extents do ficheiro de imagem copy-on-write, não os ficheiros que a sua aplicação lê dentro dele, por isso apresenta valores altos sob cargas de trabalho normais de escrita aleatória (bases de dados, camadas de contentor) e não prevê o desempenho de leitura em armazenamento com suporte SSD. O Rediacc não oferece deliberadamente um comando de desfragmentação: o `btrfs filesystem defragment` despartilha forks e snapshots com reflink, o que num pool quase cheio pode aumentar dramaticamente o uso de espaço sem que os benchmarks mostrem qualquer ganho de leitura mensurável. Para as medições completas e o raciocínio, consulte [O Seu Número de Fragmentação Parece Assustador. Medi o Que Custa.](/pt/blog/i-benchmarked-btrfs-fragmentation).

A análise corre em paralelo e demora entre 5 e 15 segundos dependendo do número e tamanho dos repositórios. Quando `--storage-health` não é especificado, aparece uma dica de uma linha após a saída da consulta como lembrete.

## Scrub BTRFS

O Rediacc agenda automaticamente um scrub BTRFS semanal em cada máquina. O scrub lê cada bloco de dados no datastore, verifica os checksums e reporta qualquer corrupção. Isto deteta a corrupção silenciosa de dados (bitrot) antes de se propagar para cópias de segurança e forks.

O scrub corre todos os domingos às 02:00 hora local (fuso horário da máquina) com um atraso aleatório de até 1 hora. Corre com a prioridade de E/S mais baixa (`ionice idle`, `nice 19`) para não interferir com serviços em execução. Em máquinas com suporte SSD, espere aproximadamente 8 minutos por 100 GB de datastore.

O temporizador de scrub é instalado automaticamente no primeiro arranque do daemon após uma atualização do renet. Quando a política de scrub muda numa versão futura do renet, atualiza-se no próximo arranque do daemon sem necessidade de ação do utilizador.

### Estado do scrub

O resultado do último scrub é guardado fora do volume BTRFS (em `/var/lib/rediacc/scrub-last-result.json`) para que permaneça legível mesmo que o volume tenha problemas. A saída de `rdc machine status --system` inclui um campo `scrub_status`:

```json
"scrub_status": {
  "last_run_human": "3 days ago",
  "status": "ok",
  "total_errors": 0,
  "uncorrectable": 0,
  "duration_seconds": 312
}
```

| Estado | Significado |
|--------|---------|
| `ok` | O último scrub concluiu sem erros |
| `never_run` | O scrub ainda não correu (o temporizador foi acabado de instalar) |
| `overdue` | O último scrub foi há mais de 14 dias |
| `errors_found` | O scrub encontrou incompatibilidades de checksum (verificar as contagens `total_errors` e `uncorrectable`) |
| `failed` | O processo de scrub saiu com um código diferente de zero |

Se `uncorrectable` for maior que zero, os blocos afetados não podem ser reparados automaticamente (o BTRFS de disco único não tem cópia redundante). Restaure o repositório afetado a partir da cópia de segurança mais recente.

### Scrub manual

Para executar um scrub imediatamente (por exemplo, após uma falha de energia ou migração de disco):

```bash
rdc term connect server-1 -c "sudo renet maintenance scrub --datastore /mnt/rediacc"
```

O resultado é guardado no mesmo ficheiro JSON e fica imediatamente visível no próximo `rdc machine status --system`.

## Visão Geral da Máquina

Obter uma visão geral completa de uma máquina incluindo informações de implementação:

```bash
rdc machine status server-1
```

Isto fornece:
- Hostname e tempo de atividade
- Uso de memória, disco e datastore
- Total de repositórios, contagem de montados, contagem de repositórios cujo daemon Docker responde
- Informações detalhadas por repositório

Use `--output json` para saída legível por máquina.

## Testar Conexão

Verificar a conectividade SSH a uma máquina:

```bash
rdc term connect server-1 -c "hostname"
```

O comando imprime o hostname remoto em caso de sucesso e um erro de
conexão caso contrário, o que verifica o DNS, a porta SSH e a
autenticação por chave num único passo.

## Diagnósticos (doctor)

Executar uma verificação de diagnóstico completa do seu ambiente Rediacc:

```bash
rdc doctor
```

| Categoria | Verificações |
|----------|--------|
| **Ambiente** | Versão de Node.js, versão da CLI, modo SEA, instalação de Go, disponibilidade de Docker |
| **Renet** | Localização do binário, versão, CRIU, rsync, ativos incorporados SEA |
| **Configuração** | Configuração ativa, adaptador, máquinas, chave SSH |
| **Virtualização** | Verifica se o seu sistema pode correr máquinas virtuais locais (`rdc ops`) |

Cada verificação reporta **OK**, **Aviso** ou **Erro**. Use isto como primeiro passo ao resolver qualquer problema.

Códigos de saída: `0` = todos passados, `1` = avisos, `2` = erros.

## Verificações de Prontidão de Serviços

Durante `repo up`, o renet aguarda que os serviços HTTP aceitem conexões antes de os declarar prontos. A espera é compatível com health checks:

- Contentores que o Docker reporta como **healthy** são considerados prontos imediatamente, sem sonda TCP.
- Contentores ainda dentro do `start_period` do health check registam uma nota informativa, não um aviso; o proxy continua a tentar até que se vinculem.
- Serviços Compose sem contentor em execução (por exemplo, atrás de um perfil inactivo) são ignorados.
- Todos os outros são sondados via TCP durante até 15 segundos (defina `REDIACC_READINESS_TIMEOUT`, em segundos, para alterar este valor).

Definir um [health check do Docker](https://docs.docker.com/reference/dockerfile/#healthcheck) em serviços de arranque lento fornece ao renet um sinal de prontidão autoritativo e elimina ruído de sondas na saída do deploy.
