---
title: "Backup e Restauro"
description: "Faça backup de repositórios encriptados de duas formas: armazenamento fragmentado endereçado por conteúdo que envia apenas as células alteradas, ou um push completo para qualquer armazenamento compatível com rclone. Restaure em qualquer máquina e automatize com estratégias nomeadas e temporizadores systemd."
category: "Guides"
order: 7
language: pt
sourceHash: "c02ab3e78c40fa92"
sourceCommit: "522dceadb04b6a3e7f4ea60ac1e47308f6a1a600"
---

# Backup e Restauro

A Rediacc pode fazer backup de repositórios encriptados para fornecedores de armazenamento externo e restaurá-los na mesma máquina ou em máquinas diferentes. Os backups são encriptados; a credencial LUKS do repositório é necessária para restaurar.

## Duas vias de backup

A Rediacc tem duas vias de backup independentes, e este guia cobre ambas. Utilizam
armazenamento e comandos diferentes, pelo que um repositório com backup feito por uma via não fica com backup feito pela outra.

**Armazenamento fragmentado** (`rdc backup snapshot`) envia a imagem do repositório em células de tamanho fixo endereçadas pelo seu conteúdo. A primeira execução envia todo o inventário não vazio; cada execução seguinte envia apenas as células que mudaram, decidido a partir dos metadados de alocação do sistema de ficheiros em vez de ler a imagem inteira. As células idênticas são armazenadas uma única vez entre snapshots e entre toda uma família de forks, e a utilização é medida face à sua quota de armazenamento (`rdc backup usage`).

**Push de armazenamento** (`rdc repo push`) copia um ficheiro de backup completo para um fornecedor compatível com rclone que regista você mesmo. Está a ser descontinuado em favor do armazenamento fragmentado, e as estratégias agendadas já não o utilizam. As secções abaixo que o descrevem ainda funcionam hoje, mas considere-o como a via legada.

Restaurar a partir do armazenamento fragmentado funciona: `rdc backup restore <repo> --at <snapshot-id>` materializa um snapshot armazenado, e `--at` também aceita um timestamp RFC 3339, que é resolvido contra o inventário de snapshots. Adicione `--as <name>` para restaurar com um nome diferente e `--up` para colocar o repositório em funcionamento depois. O armazenamento fragmentado também oferece envio (`rdc backup snapshot`), verificação (`rdc backup verify`, e `--deep` para re-hashear cada célula em vez de uma amostra), o inventário de snapshots (`rdc backup manifests`) e contabilidade de quotas (`rdc backup usage`).

### Comandos de armazenamento fragmentado

```bash
# Enviar um snapshot. A primeira execução semeia; as seguintes enviam apenas as células alteradas.
rdc backup snapshot my-app

# Planear sem enviar: relata o que se moveria.
rdc backup snapshot my-app --dry-run

# Desconfiar da âncora local e reenviar todo o inventário.
# Isto reenvia tudo e volta a debitar a quota; use apenas
# quando a âncora for sabidamente má.
rdc backup snapshot my-app --reseed

# Verificar o inventário armazenado e a sua quota.
rdc backup verify my-app
rdc backup manifests my-app
rdc backup usage
```

## Snapshots a Frio (`--cold`)

Um snapshot a frio para um repositório antes de o congelar, pelo que a imagem armazenada fica consistente ao nível da aplicação em vez de consistente por falha. O comando corre na própria máquina:

```bash
# Todos os repositórios do datastore predefinido.
sudo renet backup snapshot --cold

# Apenas os repositórios indicados. --repo recebe um GUID de repositório e repete-se.
sudo renet backup snapshot --cold --repo <guid> --repo <guid>
```

`--cold` não se combina com `--dry-run`. Uma execução em seco que para contentores não é em seco, e uma que não os para não é a frio, por isso o renet recusa o par em vez de escolher um significado por si.

### O que faz uma execução a frio

Para cada repositório selecionado, por esta ordem:

1. Parar os seus contentores.
2. Escrever em disco a montagem do repositório e o datastore.
3. Confirmar que os contentores pararam mesmo.
4. Criar um reflink copy-on-write da imagem do repositório.
5. Voltar a arrancar os contentores.

Só depois começa o envio, já com todos os repositórios de volta.

O downtime é o congelamento, não a transferência. Um reflink é só metadados, por isso demora o mesmo quer o repositório guarde 1 GB quer guarde 100 GB. Um envio não funciona assim: cresce com os bytes alterados, e o primeiro snapshot envia todo o inventário não vazio. Manter os contentores em baixo até o envio acabar prenderia o downtime ao tamanho dos dados, o que na primeira cópia significa horas em vez de milissegundos.

Todos os repositórios selecionados são parados dentro de uma só janela, e não um de cada vez. Isso custa um pouco mais de downtime por repositório e dá em troca um único ponto de consistência para todo o conjunto.

Um repositório sem contentores em execução já está parado. É capturado sem downtime nenhum, e isso é um resultado normal, não uma falha.

### Quanto custa o downtime

Medido numa máquina real, o downtime total foi de **222 ms**:

| Fase | Medido | O que acontece |
|------|--------|----------------|
| `cold_down` | 64 ms | Os contentores param |
| `cold_sync` | 26 ms | Montagens do repositório e datastore escritos em disco |
| `cold_verify` | 31 ms | Confirma-se que os contentores estão parados |
| `cold_stage` | 0 ms | Reflink da imagem do repositório |
| `cold_up` | 99 ms | Os contentores voltam a arrancar |

O reinício dos contentores domina, e a preparação sai praticamente de graça: o reflink nem sequer aparece com resolução de milissegundos. Ainda assim, leia esse zero ao lado dos registos de cada repositório e não isoladamente. Uma execução que recusou todos os repositórios também indica `cold_stage=0ms`, e só os registos dizem qual dos dois casos está a ver.

O detalhe é a prova, não enfeite. Nenhuma destas cinco fases lê ou envia dados do repositório, por isso nenhuma cresce quando a cópia cresce. A parte que cresce, o envio, corre quando o downtime já terminou.

O renet imprime os mesmos números no fim de uma execução, para que meça as suas próprias máquinas em vez de acreditar nas nossas:

```text
Cold backup: <n> repositories quiesced, outage 222ms (cold_down=64ms cold_sync=26ms cold_verify=31ms cold_stage=0ms cold_up=99ms)
```

O registo JSON de cada repositório leva o mesmo downtime e as mesmas fases, pelo que mais tarde se distingue um snapshot a frio de um a quente sem o adivinhar pelos tempos.

### Quando escolher o frio

O modo a quente é a predefinição e a escolha certa para a maioria dos repositórios. Um snapshot a quente é consistente por falha, ou seja, fica no estado em que um repositório ficaria depois de uma quebra de energia, e não custa downtime nenhum. A maioria das bases de dados e das filas recupera sozinha a partir daí.

Escolha o frio para dados que não podem ser capturados em segurança enquanto estão a ser escritos. Uma base de dados com o seu próprio write-ahead log e estado em memória é o caso óbvio. Está a trocar um downtime curto e medido por um snapshot que a aplicação consegue abrir sem se reparar primeiro.

### O que uma execução a frio recusa

Recusar é a funcionalidade. Uma cópia rotulada como a frio que nunca parou nada é uma mentira que só descobriria no restauro, por isso o renet nunca despromove em silêncio uma execução a frio para uma a quente:

- **Contentores que não pararam.** Depois da paragem, o renet pergunta ao socket Docker do próprio repositório se ainda corre alguma coisa. Se sim, esse repositório é recusado em vez de capturado. A verificação decide pelo lado seguro: se o socket estiver inacessível ou a lista de contentores ilegível, a paragem conta como não verificada, e não verificada é recusada.
- **Uma licença que não se consegue ler.** As licenças são verificadas antes do downtime e não depois, porque um repositório com licença ilegível nunca teria conseguido enviar nada. Esse repositório é saltado sem ser parado. Se nenhum dos repositórios selecionados tiver licença legível, a execução inteira é recusada antes de cair um único contentor.
- **Uma segunda execução a frio no mesmo datastore.** O bloqueio cobre o datastore, e um bloqueio ocupado é recusado logo, sem ter parado nada. Duas execuções sobrepostas parariam cada uma contentores que a outra julga seus, e a segunda arrancaria repositórios que a primeira ainda está a congelar. Saltar a execução e esperar pela seguinte é melhor do que isso.

Se uma execução for interrompida com os contentores em baixo, por um `systemctl stop` ou um reinício, o renet volta a arrancá-los antes de sair. A recuperação na máquina serve de rede: deteta uma cópia a frio cujo dono desapareceu e repõe esses repositórios.

## Configurar Armazenamento

Antes de enviar backups, registe um fornecedor de armazenamento. A Rediacc suporta qualquer armazenamento compatível com rclone: S3, B2, Google Drive e muitos mais.

### Importar do rclone

Se já tiver um remoto rclone configurado:

```bash
rdc storage import rclone.conf
```

Isto importa configurações de armazenamento de um ficheiro de configuração rclone para a configuração atual. Tipos suportados: S3, B2, Google Drive, OneDrive, Mega, Dropbox, Box, Azure Blob e Swift.

### Ver Armazenamentos

```bash
rdc storage list
```

## Enviar um Backup

Envie um backup de repositório para armazenamento externo:

```bash
rdc repo push my-app --to my-storage
```

O backup fica na pasta `hot/` do armazenamento quando o repositório está montado no momento do envio, e em `cold/` quando está desmontado. É o mesmo layout usado pelos backups agendados, por isso `rdc backup list` mostra todos os backups numa única tabela.

| Opção | Descrição |
|--------|-------------|
| `--to <storage>` | Localização de armazenamento de destino |
| `--to-machine <machine>` | Máquina de destino para backup máquina a máquina |
| `--dest <filename>` | Nome de ficheiro de destino personalizado |
| `--checkpoint` | Criar um checkpoint CRIU antes de enviar (para contentores com a etiqueta `rediacc.checkpoint=true`). O destino restaura automaticamente em `repo up` |
| `--force` | Substituir um backup existente |
| `--bwlimit <limit>` | Limite de largura de banda para transferência rsync (por exemplo, `10M`, `500K`) |
| `--tag <tag>` | Etiquetar o backup |
| `-w, --watch` | Observar o progresso da operação |
| `--debug` | Ativar saída detalhada |
| `--skip-router-restart` | Ignorar o reinício do servidor de rotas após a operação |

## Receber / Restaurar um Backup

Receba um backup de repositório do armazenamento externo:

```bash
rdc repo pull my-app --from my-storage
```

A receção recusa substituir um repositório que esteja atualmente **montado**. Desmonte-o primeiro, faça a receção e volte a colocá-lo em funcionamento com `rdc repo up`. Os repositórios baseados em diretório são a exceção: sincronizam-se no próprio local mesmo estando montados.

| Opção | Descrição |
|--------|-------------|
| `--from <storage>` | Localização de armazenamento de origem |
| `--from-machine <machine>` | Máquina de origem para restauro máquina a máquina |
| `--force` | Substituir backup local existente |
| `--bwlimit <limit>` | Limite de largura de banda para transferência rsync (por exemplo, `10M`, `500K`) |
| `-w, --watch` | Observar o progresso da operação |
| `--debug` | Ativar saída detalhada |
| `--skip-router-restart` | Ignorar o reinício do servidor de rotas após a operação |

## Listar Backups

Ver os backups disponíveis numa localização de armazenamento:

```bash
rdc backup list --storage my-storage
```

A saída é uma tabela unificada que combina ambas as [pastas de backups agendados](#backups-agendados) (`hot/` e `cold/`) para que veja todos os backups numa só vista:

| Coluna | Significado |
|---|---|
| `Mode` | `hot` ou `cold`. Em que pasta de backup agendado esta entrada reside |
| `Name` | Nome do repositório resolvido a partir da sua configuração local (usa o GUID para repositórios não presentes na configuração) |
| `GUID` | O GUID do repositório em disco |
| `Size` | Tamanho legível por humanos do ficheiro de backup |
| `Modified` | Timestamp UTC do backend de armazenamento |

Para analisar um único modo, passe `--path`:

```bash
rdc backup list --storage my-storage --path hot
rdc backup list --storage my-storage --path cold
```

### Layout de armazenamento

Os backups agendados ficam em subpastas por modo dentro da pasta configurada do armazenamento, para que o mesmo armazenamento aloje de forma organizada tanto o fluxo horário como o semanal sem os misturar:

```text
<bucket>/<folder>/
├── hot/
│   ├── <guid-1>
│   ├── <guid-2>
│   └── ...
└── cold/
    ├── <guid-1>
    ├── <guid-3>
    └── ...
```

Um repositório pode aparecer em `hot/` e em `cold/` (o agendamento horário tira snapshot; o agendamento semanal tira outro). A listagem combinada mostra ambas as linhas para que fique claro quais os fluxos que cobrem quais repositórios.

## Sincronizar um repositório de cada vez

Push e pull atuam sobre um único repositório, identificado pelo ref (`name`, `name:tag` ou `name@machine`). Não existe uma forma para «todos os repositórios de uma vez»: execute o comando uma vez por repositório.

### Enviar para o armazenamento

```bash
rdc repo push shop@server-1 --to my-storage
```

### Receber do armazenamento

```bash
rdc repo pull shop@server-1 --from my-storage
```

| Opção | Descrição |
|--------|-------------|
| `--to <remote>` | Armazenamento ou máquina de destino (envio) |
| `--to-machine <machine>` | Máquina de destino para envio máquina a máquina |
| `--from <remote>` | Armazenamento ou máquina de origem (receção) |
| `--from-machine <machine>` | Máquina de origem para receção máquina a máquina |
| `--force` | Substituir um backup ou repositório existente |
| `--checkpoint` | Criar um checkpoint CRIU antes de enviar (apenas envio) |
| `--up` | Montar e implementar o repositório após a receção (apenas receção) |
| `--bwlimit <limit>` | Limite de largura de banda para a transferência rsync (por exemplo, `10M`) |
| `--delta-base <guid>` | Transferir apenas os blocos alterados em relação a uma GUID base imutável |
| `--debug` | Ativar saída detalhada |
| `--skip-router-restart` | Ignorar o reinício do servidor de rotas após a operação |

## Backups Agendados

A Rediacc usa estratégias de backup nomeadas. Cada estratégia define um agendamento, modo de backup, limite de largura de banda opcional e filtros de ficheiros. As máquinas referenciam estratégias pelo nome para determinar quais os backups que correm nelas.

### Modos de Backup

| Modo | Comportamento | Downtime |
|------|----------|----------|
| `hot` | Snapshot BTRFS tirado com os serviços em execução (consistente por falha) | Nenhum |
| `cold` | Serviços parados, snapshot tirado, serviços reiniciados, snapshot enviado (consistente para a aplicação) | Janela de paragem+arranque por repositório, paralelizada entre repositórios. Consulte "Estimar o Downtime do Backup Cold" abaixo. |

Use `hot` para serviços que toleram snapshots consistentes por falha. Use `cold` quando precisar de consistência garantida e puder aceitar um breve reinício.

### Semântica do Backup Cold

Um backup cold corre em três fases por repositório incluído: **parar -> snapshot -> arrancar**. Compreender onde terminam as garantias ajuda os operadores a detetar falhas parciais cedo.

**O que o backup cold garante:**

- Antes do snapshot, todos os contentores em execução em cada repositório incluído são parados graciosamente através do gancho `down()` do Rediaccfile e o daemon Docker por repositório é quiesced. O snapshot é, portanto, consistente para a aplicação, e não apenas consistente por falha.
- O conjunto de IDs de contentores que estavam em execução antes do snapshot é persistido num sidecar em `/var/run/rediacc/cold-backup-<guid>.running.json`. Esta é a fonte de verdade para "o que deve estar de volta a funcionar quando terminarmos."
- Após o snapshot, o gancho `up()` do Rediaccfile do repositório é invocado para restaurar a stack compose completa.
- Um sidecar de estado por execução em `/var/run/rediacc/cold-backup-<guid>.status.json` regista a fase, o resultado e qualquer erro de cada tentativa.

**O que o backup cold NÃO garante:**

- `up()` é de melhor esforço. Pode falhar por razões fora do controlo do backup cold (uma condição `depends_on: service_healthy` ainda a aguardar, um erro de sintaxe no ficheiro compose, uma falha de rede transitória ao obter uma imagem). Quando falha, o backup cold regista o erro ao nível de erro, escreve o sidecar de estado e passa para o próximo repositório.
- Quando `up()` falha, um **reinício direto de fallback** é acionado: o sidecar de execução é lido e cada ID de contentor registado é reiniciado via API Docker direta (sem compose). Isto repõe os serviços mesmo que o fluxo compose tenha um problema, embora sem re-executar quaisquer ganchos do Rediaccfile.
- Se mesmo o fallback falhar para alguns IDs de contentores (por exemplo, o próprio daemon Docker está inativo), o sidecar é **mantido no lugar** para que o watchdog do router possa continuar a tentar em cada tick.

**Recuperação pelo watchdog:** em cada tick, o watchdog verifica um sidecar de execução. Qualquer ID de contentor aí listado que esteja atualmente parado é reiniciado, *independentemente da `restart_policy` guardada do contentor*. Isto significa que os serviços com `restart: on-failure` (que o Docker NÃO reiniciaria após uma paragem limpa) voltam a funcionar após um backup cold. Quando todos os contentores listados estão em execução, o sidecar é eliminado.

**Como os operadores detetam falhas:**

- `rdc machine status <machine> --containers` mostra o estado de execução. Compare com o conjunto esperado.
- `/var/run/rediacc/cold-backup-<guid>.status.json` na máquina. Inspecione via `rdc term connect <repo> -c "cat /var/run/rediacc/cold-backup-$GUID.status.json"`. `success: false` com um `startedAt` desatualizado significa que o último backup não completou de forma limpa.
- Os logs da execução de backup do renet (`journalctl -u renet-*` ou a invocação direta de `rdc backup schedule`) emitem uma linha de resumo final da forma `Cold backup: post-snapshot restart summary total=N compose_ok=N fallback_ok=N failed=N failed_repos=[...]`. Um `failed_repos` não vazio é o alvo do grep.

### Estimar o Downtime do Backup Cold

Cada repositório está inativo apenas durante a sua própria janela de `down()` + `up()`. Num host aquecido, estes são tipicamente:

| Forma do repositório | Paragem+arranque típico |
|------------|--------------------|
| Pequeno (1-2 contentores, sem BD) | 5-15 s |
| Médio (app web + cache) | 20-45 s |
| Grande (BD + filas + correio) | 60-120 s |

O passo de snapshot (`btrfs subvolume snapshot -r`) é O(1) independentemente do tamanho do repositório: 0.1-1 s. Um repositório não é mantido inativo durante os snapshots de outros repositórios. O uploader corre depois contra um snapshot só de leitura enquanto todos os repositórios já estão de volta a funcionar.

**O tempo total de execução** é governado pelo número de repositórios que reiniciam em simultâneo. O Renet deriva isto do host:

```text
concurrency = min(repoCount, max(2, NumCPU/2), 8)
```

Exemplos:

| Host | Repos | Concorrência | Reinício total |
|------|-------|-------------|--------------------|
| VM 4 CPU | 5 repos, média 30 s cada | 2 | ~75 s |
| Servidor 16 CPU | 10 repos, média 40 s cada | 8 | ~80 s |
| Nó de frota 64 CPU | 50 repos, média 40 s cada | 8 | ~4 min |

**Override via env:** defina `REDIACC_COLD_BACKUP_CONCURRENCY=N` no ambiente do serviço de backup (um drop-in systemd é a rota habitual) para fixar um valor específico. `=1` força reinícios estritamente em série, útil ao depurar um crashloop no gancho `up()` de um repositório.

Se tiver um repositório sensível à latência (app web pública, correio), o seu downtime é limitado pela sua própria paragem+arranque (tipicamente 30-90 s), e não pela duração total da execução. Os repositórios são agendados em slots de concorrência pela ordem em que foram descobertos; não há fila de prioridade. Divida repositórios grandes nas suas próprias estratégias com âmbito `--exclude` se precisar de agendamento mais granular.

### Backups Longos e Agendamentos Sobrepostos

Um backup cold que demora mais do que o seu próprio intervalo de agendamento (por exemplo, um seed inicial de um repositório de 500 GB numa ligação modesta pode legitimamente precisar de mais de 24 h, durante o qual o temporizador noturno dispara novamente) não coloca em fila nem inicia uma segunda execução. A unidade systemd `Type=oneshot` é uma instância única: quando o temporizador dispara e o serviço já está em `activating`, o systemd coalesce o arranque no job existente. Nenhum novo processo é iniciado, nenhuma execução fica em fila para mais tarde.

Concretamente, uma execução que começa segunda-feira às 03:00 UTC e termina quinta-feira ao meio-dia:

| Dia | Disparo às 03:00 UTC | Resultado |
|------|---------------|--------|
| Segunda | Primeiro disparo | Execução começa |
| Terça | Segundo disparo | Ignorado silenciosamente (a execução anterior ainda está ativa) |
| Quarta | Terceiro disparo | Ignorado silenciosamente (a execução anterior ainda está ativa) |
| Quinta | Execução termina ao meio-dia | Sem recuperação; próxima execução é sexta às 03:00 UTC |

A diretiva `Persistent=true` do temporizador **não** resgata estes disparos. `Persistent=true` repete disparos que foram perdidos porque o próprio temporizador estava inativo (sistema desligado, temporizador desativado). Os disparos ignorados porque o serviço estava ocupado desaparecem.

Esta predefinição é deliberada. Executar dois backups cold em paralelo contra o mesmo datastore geraria contenção no caminho de snapshot BTRFS, no remoto rclone e nos sidecars por repositório em `/var/run/rediacc/cold-backup-<guid>.status.json`. Serializar atrás de uma instância de longa duração é o resultado seguro.

**Implicação para monitorização.** Um backup bloqueado (por exemplo, rclone preso num buraco negro de rede) ignora silenciosamente todos os disparos do temporizador subsequentes. O agendador não emite nenhum alarme. Observe `systemctl show <unit> -p ActiveEnterTimestamp`: se o serviço estiver em `activating` por mais tempo do que a duração esperada de execução (por exemplo, mais de 48 h num temporizador noturno), investigue.

**Se precisar que cada disparo agendado corra**, mude o temporizador de `OnCalendar=<cron>` para `OnUnitInactiveSec=<interval>`. Isso dispara N horas após a conclusão da execução anterior em vez de num agendamento de relógio fixo, pelo que as execuções longas não causam perdas. Apenas empurram a próxima execução para mais tarde. O trade-off é a deriva do agendamento: o seu noturno às 03:00 torna-se "24 h após o fim do último."

### Snapshots, Interrupções e Espaço no Pool

Cada push é feito a partir de um snapshot momentâneo do datastore, pelo que os dados enviados são consistentes mesmo enquanto os repositórios continuam a escrever. Enquanto o backup corre, esse snapshot continua a referenciar todos os blocos que partilha com os repositórios ativos: eliminações e [trims](/pt/docs/repositories#reclamar-espaco-trim) libertam menos espaço no pool até que o ciclo termine e o snapshot seja eliminado. O [relatório de estado do armazenamento](/pt/docs/monitoring#estado-do-armazenamento) mostra quanto espaço os snapshots de backup estão atualmente a reservar.

As interrupções são seguras. Parar o serviço (ou reiniciar a máquina) faz com que o backup cancele a transferência e elimine o seu snapshot antes de sair; a próxima execução agendada retoma onde parou, uma vez que os ficheiros não alterados são ignorados por checksum. Se o processo for terminado de forma abrupta sem hipótese de limpeza (corte de energia), o snapshot órfão é detetado e removido automaticamente pelo mantenedor de armazenamento em poucos minutos.

### Definir uma Estratégia

A predefinição canónica é uma divisão em duas estratégias: um fluxo hot horário rápido que captura todos os repositórios, e um fluxo cold semanal mais lento que tira snapshots consistentes para a aplicação. As duas estratégias escrevem em subpastas de armazenamento diferentes (`hot/` e `cold/`) para que os backups nunca se misturem.

```bash
rdc backup strategy set hourly-hot \
  --destination my-storage \
  --cron "0 * * * *" \
  --mode hot \
  --bwlimit 20M \
  --enable
```

```bash
rdc backup strategy set weekly-cold \
  --destination my-storage \
  --cron "15 3 * * 0" \
  --mode cold \
  --exclude very-large-repo \
  --enable
```

O filtro `--exclude` na estratégia cold é a saída de emergência recomendada para repositórios muito grandes que não cabem na sua janela de manutenção semanal. A estratégia hot horária ainda os cobre; o cold simplesmente ignora. Os nomes de repositórios em `--exclude` correspondem ao nome do repositório na configuração local (sem `:tag`).

| Opção | Descrição |
|--------|-------------|
| `<strategy>` (posicional) | Nome da estratégia (usado para a associação à máquina) |
| `--destination <storage>` | Fornecedor de armazenamento para onde enviar |
| `--cron <expression>` | Expressão cron (por exemplo, `"0 2 * * *"` para diário às 2h) |
| `--mode <hot\|cold>` | Modo de backup |
| `--bwlimit <limit>` | Limite de largura de banda para uploads (por exemplo, `10M`) |
| `--include <pattern>` | Filtro de inclusão (repetível) |
| `--exclude <pattern>` | Filtro de exclusão (repetível) |
| `--enable` / `--disable` | Ativar ou desativar a estratégia |

### Ver Estratégias

```bash
rdc backup strategy list
rdc backup strategy show weekly-cold
```

### Remover uma Estratégia

```bash
rdc backup strategy remove weekly-cold
```

### Associar Estratégias a uma Máquina

Na sua configuração, associe um ou mais nomes de estratégia a uma máquina:

```json
{
  "machines": {
    "hostinger": {
      "backupStrategies": ["hourly-hot", "weekly-cold"]
    }
  }
}
```

> **A vinculação é apenas configuração local.** Definir uma estratégia e vinculá-la a uma máquina não afeta a máquina. Execute `rdc backup schedule -m <machine>` (consulte [Implementar Agendamento na Máquina](#implementar-agendamento-na-maquina)) para implantar os temporizadores systemd, e execute novamente após qualquer alteração de estratégia ou vinculação.

## Escolher entre Hot e Cold e Filtragem por Repositório

### Hot vs cold em resumo

| | Hot | Cold |
|---|-----|------|
| **Consistência** | Crash-consistent (snapshot BTRFS durante a execução) | Application-consistent (stop -> snapshot -> start) |
| **Downtime** | Nenhum | Janela de stop+start por repositório (normalmente 5-120 s) |
| **Frequência adequada** | Alta (ex: de hora em hora) | Baixa (ex: diária ou semanal) |
| **Uso típico** | Rede de segurança de alta frequência | Backup agendado com consistência garantida |

**Hot** é o padrão correto para execuções de alta frequência. Os serviços continuam a correr enquanto o snapshot é effectuado, por isso a janela de backup não interrompe os utilizadores. O snapshot é crash-consistent: é equivalente ao que se obteria após um encerramento não limpo. Para a maioria das bases de dados modernas e filas de mensagens, isto é aceitável.

**Cold** é apropriado quando precisa de um snapshot application-consistent garantido e pode aceitar um breve reinício por repositório. Os serviços são parados antes do snapshot e reiniciados antes de o carregamento começar, por isso um carregamento lento ou falhado nunca prolonga a janela de downtime. Consulte [Semântica do Backup Cold](#semantica-do-backup-cold) para o modelo de garantia completo.

### Filtrar repositórios por estratégia

Cada estratégia pode ter filtros `--include` e `--exclude`. Os nomes de repositório que correspondem a um padrão `--exclude` são ignorados para essa estratégia; `--include` restringe a execução apenas a esses nomes. Os filtros correspondem ao nome do repositório na configuração local (sem `:tag`).

```bash
# Estratégia hot: fazer backup de tudo de hora em hora
rdc backup strategy set hourly-hot \
  --destination my-storage \
  --cron "0 * * * *" \
  --mode hot \
  --bwlimit 6M \
  --enable

# Estratégia cold: fazer backup de tudo semanalmente, excluindo o conjunto de dados derivado de grande dimensão
rdc backup strategy set weekly-cold \
  --destination my-storage \
  --cron "15 3 * * 0" \
  --mode cold \
  --exclude analytics-demo \
  --enable
```

### Quando excluir um repositório da estratégia hot de alta frequência

Exclua um repositório da execução de alta frequência quando:

- O repositório é grande e **totalmente regenerável** a partir de dados de origem já presentes no volume, por isso cada backup de hora em hora desperdiça largura de banda significativa sem acrescentar valor de recuperação significativo.
- A execução do backup ultrapassaria o seu próprio intervalo de agendamento à velocidade de carregamento disponível.

**Exemplo.** Um repositório `analytics-demo` contém aproximadamente 114 GB de tabelas Postgres derivadas que podem ser totalmente reconstruídas a partir de ficheiros de dump CSV brutos já armazenados dentro do mesmo volume. Com um limite de carregamento de 6 MB/s, um único backup hot desse repositório demora mais de 5 horas. Executá-lo de hora em hora significa que cada execução ainda está em curso quando a próxima dispara, o que faz com que cada execução subsequente seja silenciosamente descartada (consulte [Backups Longos e Agendamentos Sobrepostos](#backups-longos-e-agendamentos-sobrepostos)). Excluí-lo de `hourly-hot` e mantê-lo em `weekly-cold` significa que é feito backup uma vez por semana em vez de nunca.

> **Se os dados são puramente regeneráveis**, considere se precisa de os fazer backup. Uma alternativa é fazer backup apenas das entradas de origem brutas (os dumps CSV, neste exemplo) e ignorar completamente a cópia derivada. Um backup cold semanal das entradas de origem é muito mais pequeno e completamente suficiente para a recuperação.

Os repositórios não excluídos de nenhuma das estratégias aparecem em ambas as subpastas de armazenamento `hot/` e `cold/`. O resultado unificado de `rdc backup list` mostra ambas as linhas para que possa verificar quais os fluxos que cobrem quais repositórios.

## Operações de Backup

### Implementar Agendamento na Máquina

Envie as estratégias associadas a uma máquina como temporizadores systemd:

```bash
rdc backup schedule -m server-1
rdc backup schedule -m server-1 --dry-run
```

A implementação é um reconciliador de estado. Lê os ficheiros de unidade atuais e o estado systemd na máquina, compara com o que a configuração produziria (SHA-256 por ficheiro), e apenas toca nas unidades cujo conteúdo realmente mudou. Re-executar sem alterações de configuração é uma operação sem efeito: sem escritas, sem `daemon-reload`, sem perturbação de temporizadores.

`--dry-run` imprime o plano para cada estratégia (`created`, `updated (service, timer, env)`, `unchanged`, `removed`) sem tocar na máquina. Combine com `--debug` para também imprimir os corpos das unidades geradas; os tokens rclone são redatados.

Se um backup estiver atualmente a correr para uma estratégia que está prestes a atualizar ou remover, a implementação falha rapidamente com uma dica para cancelá-lo ou passar `--force`. Com `--force`, a invocação em execução mantém a sua unidade em memória e a nova configuração aplica-se no próximo tick do temporizador, pelo que o backup em execução nunca é terminado.

`--reset-failed` é opcional. Quando passado, limpa o estado de falha do systemd nos serviços tocados após uma implementação bem-sucedida. Desativado por omissão para que os sinais de falha anteriores permaneçam visíveis para alertas.

### Executar um Backup Agora

Acione um backup imediatamente sem aguardar pelo temporizador. Funciona mesmo que nenhum temporizador tenha sido implementado, usando `systemd-run` para execução ad-hoc:

```bash
rdc backup run -m server-1
rdc backup run weekly-cold -m server-1
```

### Ver Estado do Backup

Mostrar o estado atual dos temporizadores de backup e os resultados de jobs recentes:

```bash
rdc backup status -m server-1
rdc backup status hourly-hot -m server-1
```

### Cancelar um Backup em Execução

```bash
rdc backup cancel -m server-1
rdc backup cancel weekly-cold -m server-1
```

## Migração de Repositório

Mover um repositório de uma máquina para outra:

```bash
rdc repo migrate my-app@server-1 --to server-2
```

| Opção | Descrição |
|--------|-------------|
| `<ref>` (posicional) | Referência do repositório a migrar; a parte `@machine` indica a origem |
| `--to <place>` | Máquina ou cluster de destino |
| `--provision` | Provisionar o repositório no destino antes de transferir |
| `--checkpoint` | Criar um checkpoint CRIU antes de migrar |
| `--skip-dns` | Ignorar a atualização de registos DNS após a migração |
| `--bwlimit <limit>` | Limite de largura de banda para a transferência (por exemplo, `50M`) |

A migração transfere os dados encriptados do repositório via rsync. O repositório de origem permanece intacto até o remover explicitamente.

## Navegar no Armazenamento

Navegar pelo conteúdo de uma localização de armazenamento:

```bash
rdc storage browse my-storage
```

## Boas Práticas

- Agende backups cold diários para snapshots consistentes para a aplicação de dados críticos
- Use backups hot para snapshots de alta frequência onde zero downtime é necessário
- Teste os restauros periodicamente para verificar a integridade dos backups
- Use múltiplos fornecedores de armazenamento para dados críticos (por exemplo, S3 + B2)
- Mantenha as credenciais seguras; os backups são encriptados mas a credencial LUKS é necessária para restaurar
