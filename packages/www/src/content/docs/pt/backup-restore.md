---
title: "Backup e Restauro"
description: "Faça backup de repositórios encriptados para armazenamento externo, restaure a partir de backups e agende backups automáticos."
category: "Guides"
order: 7
language: pt
sourceHash: "196ee7b649ac7371"
sourceCommit: "c6b8f8b9e4b708273e922469c7a454bb49702265"
---

# Backup e Restauro

A Rediacc pode fazer backup de repositórios encriptados para fornecedores de armazenamento externo e restaurá-los na mesma máquina ou em máquinas diferentes. Os backups são encriptados; a credencial LUKS do repositório é necessária para restaurar.

## Configurar Armazenamento

Antes de enviar backups, registe um fornecedor de armazenamento. A Rediacc suporta qualquer armazenamento compatível com rclone: S3, B2, Google Drive e muitos mais.

### Importar do rclone

Se já tiver um remoto rclone configurado:

```bash
rdc config storage import --file rclone.conf
```

Isto importa configurações de armazenamento de um ficheiro de configuração rclone para a configuração atual. Tipos suportados: S3, B2, Google Drive, OneDrive, Mega, Dropbox, Box, Azure Blob e Swift.

### Ver Armazenamentos

```bash
rdc config storage list
```

## Enviar um Backup

Envie um backup de repositório para armazenamento externo:

```bash
rdc repo push --name my-app -m server-1 --to my-storage
```

O envio verifica sempre que o repositório de destino está montado antes de escrever. Se não estiver montado, a operação é cancelada.

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
rdc repo pull --name my-app -m server-1 --from my-storage
```

A receção verifica sempre que o repositório de destino está montado antes de escrever. Se não estiver montado, a operação é cancelada.

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
rdc repo backup list --from my-storage -m server-1
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
rdc repo backup list --from my-storage -m server-1 --path hot
rdc repo backup list --from my-storage -m server-1 --path cold
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

## Sincronização em Massa

Envie ou receba todos os repositórios de uma vez:

### Enviar Tudo para o Armazenamento

```bash
rdc repo push --to my-storage -m server-1
```

### Receber Tudo do Armazenamento

```bash
rdc repo pull --from my-storage -m server-1
```

| Opção | Descrição |
|--------|-------------|
| `--to <storage>` | Armazenamento de destino (direção de envio) |
| `--from <storage>` | Armazenamento de origem (direção de receção) |
| `--repo <name>` | Sincronizar repositórios específicos (repetível) |
| `--override` | Substituir backups existentes |
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

- `rdc machine query --name <machine> --containers` mostra o estado de execução. Compare com o conjunto esperado.
- `/var/run/rediacc/cold-backup-<guid>.status.json` na máquina. Inspecione via `rdc term connect -m <machine> -r <repo> -c "cat /var/run/rediacc/cold-backup-$GUID.status.json"`. `success: false` com um `startedAt` desatualizado significa que o último backup não completou de forma limpa.
- Os logs da execução de backup do renet (`journalctl -u renet-*` ou a invocação direta de `rdc machine backup schedule`) emitem uma linha de resumo final da forma `Cold backup: post-snapshot restart summary total=N compose_ok=N fallback_ok=N failed=N failed_repos=[...]`. Um `failed_repos` não vazio é o alvo do grep.

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

### Definir uma Estratégia

A predefinição canónica é uma divisão em duas estratégias: um fluxo hot horário rápido que captura todos os repositórios, e um fluxo cold semanal mais lento que tira snapshots consistentes para a aplicação. As duas estratégias escrevem em subpastas de armazenamento diferentes (`hot/` e `cold/`) para que os backups nunca se misturem.

```bash
rdc config backup-strategy set \
  --name hourly-hot \
  --destination my-storage \
  --cron "0 * * * *" \
  --mode hot \
  --bwlimit 20M \
  --enable
```

```bash
rdc config backup-strategy set \
  --name weekly-cold \
  --destination my-storage \
  --cron "15 3 * * 0" \
  --mode cold \
  --exclude very-large-repo \
  --enable
```

O filtro `--exclude` na estratégia cold é a saída de emergência recomendada para repositórios muito grandes que não cabem na sua janela de manutenção semanal. A estratégia hot horária ainda os cobre; o cold simplesmente ignora. Os nomes de repositórios em `--exclude` correspondem ao nome do repositório na configuração local (sem `:tag`).

| Opção | Descrição |
|--------|-------------|
| `--name <name>` | Nome da estratégia (usado para associação à máquina) |
| `--destination <storage>` | Fornecedor de armazenamento para onde enviar |
| `--cron <expression>` | Expressão cron (por exemplo, `"0 2 * * *"` para diário às 2h) |
| `--mode <hot\|cold>` | Modo de backup |
| `--bwlimit <limit>` | Limite de largura de banda para uploads (por exemplo, `10M`) |
| `--include <pattern>` | Filtro de inclusão (repetível) |
| `--exclude <pattern>` | Filtro de exclusão (repetível) |
| `--enable` / `--disable` | Ativar ou desativar a estratégia |

### Ver Estratégias

```bash
rdc config backup-strategy list
rdc config backup-strategy show --name weekly-cold
```

### Remover uma Estratégia

```bash
rdc config backup-strategy remove --name weekly-cold
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

> **A vinculação é apenas configuração local.** Definir uma estratégia e vinculá-la a uma máquina não afeta a máquina. Execute `rdc machine backup schedule -m <machine>` (consulte [Implementar Agendamento na Máquina](#implementar-agendamento-na-máquina)) para implantar os temporizadores systemd, e execute novamente após qualquer alteração de estratégia ou vinculação.

## Escolher entre Hot e Cold e Filtragem por Repositório

### Hot vs cold em resumo

| | Hot | Cold |
|---|-----|------|
| **Consistência** | Crash-consistent (snapshot BTRFS durante a execução) | Application-consistent (stop → snapshot → start) |
| **Downtime** | Nenhum | Janela de stop+start por repositório (normalmente 5-120 s) |
| **Frequência adequada** | Alta (ex: de hora em hora) | Baixa (ex: diária ou semanal) |
| **Uso típico** | Rede de segurança de alta frequência | Backup agendado com consistência garantida |

**Hot** é o padrão correcto para execuções de alta frequência. Os serviços continuam a correr enquanto o snapshot é efectuado, por isso a janela de backup não interrompe os utilizadores. O snapshot é crash-consistent: é equivalente ao que se obteria após um encerramento não limpo. Para a maioria das bases de dados modernas e filas de mensagens, isto é aceitável.

**Cold** é apropriado quando precisa de um snapshot application-consistent garantido e pode aceitar um breve reinício por repositório. Os serviços são parados antes do snapshot e reiniciados antes de o carregamento começar, por isso um carregamento lento ou falhado nunca prolonga a janela de downtime. Consulte [Semântica do Backup Cold](#semantica-do-backup-cold) para o modelo de garantia completo.

### Filtrar repositórios por estratégia

Cada estratégia pode ter filtros `--include` e `--exclude`. Os nomes de repositório que correspondem a um padrão `--exclude` são ignorados para essa estratégia; `--include` restringe a execução apenas a esses nomes. Os filtros correspondem ao nome do repositório na configuração local (sem `:tag`).

```bash
# Estratégia hot: fazer backup de tudo de hora em hora
rdc config backup-strategy set \
  --name hourly-hot \
  --destination my-storage \
  --cron "0 * * * *" \
  --mode hot \
  --bwlimit 6M \
  --enable

# Estratégia cold: fazer backup de tudo semanalmente, excluindo o conjunto de dados derivado de grande dimensão
rdc config backup-strategy set \
  --name weekly-cold \
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

Os repositórios não excluídos de nenhuma das estratégias aparecem em ambas as subpastas de armazenamento `hot/` e `cold/`. O resultado unificado de `rdc repo backup list` mostra ambas as linhas para que possa verificar quais os fluxos que cobrem quais repositórios.

## Operações de Backup

### Implementar Agendamento na Máquina

Envie as estratégias associadas a uma máquina como temporizadores systemd:

```bash
rdc machine backup schedule -m server-1
rdc machine backup schedule -m server-1 --dry-run
```

A implementação é um reconciliador de estado. Lê os ficheiros de unidade atuais e o estado systemd na máquina, compara com o que a configuração produziria (SHA-256 por ficheiro), e apenas toca nas unidades cujo conteúdo realmente mudou. Re-executar sem alterações de configuração é uma operação sem efeito: sem escritas, sem `daemon-reload`, sem perturbação de temporizadores.

`--dry-run` imprime o plano para cada estratégia (`created`, `updated (service, timer, env)`, `unchanged`, `removed`) sem tocar na máquina. Combine com `--debug` para também imprimir os corpos das unidades geradas; os tokens rclone são redatados.

Se um backup estiver atualmente a correr para uma estratégia que está prestes a atualizar ou remover, a implementação falha rapidamente com uma dica para cancelá-lo ou passar `--force`. Com `--force`, a invocação em execução mantém a sua unidade em memória e a nova configuração aplica-se no próximo tick do temporizador, pelo que o backup em execução nunca é terminado.

`--reset-failed` é opcional. Quando passado, limpa o estado de falha do systemd nos serviços tocados após uma implementação bem-sucedida. Desativado por omissão para que os sinais de falha anteriores permaneçam visíveis para alertas.

### Executar um Backup Agora

Acione um backup imediatamente sem aguardar pelo temporizador. Funciona mesmo que nenhum temporizador tenha sido implementado, usando `systemd-run` para execução ad-hoc:

```bash
rdc machine backup now -m server-1
rdc machine backup now -m server-1 --strategy weekly-cold
```

### Ver Estado do Backup

Mostrar o estado atual dos temporizadores de backup e os resultados de jobs recentes:

```bash
rdc machine backup status -m server-1
rdc machine backup status -m server-1 --strategy hourly-hot
```

### Cancelar um Backup em Execução

```bash
rdc machine backup cancel -m server-1
rdc machine backup cancel -m server-1 --strategy weekly-cold
```

## Migração de Repositório

Mover um repositório de uma máquina para outra:

```bash
rdc repo migrate --name my-app --from server-1 --to server-2
```

| Opção | Descrição |
|--------|-------------|
| `--name <repo>` | Repositório a migrar |
| `--from <machine>` | Máquina de origem |
| `--to <machine>` | Máquina de destino |
| `--provision` | Provisionar o repositório no destino antes de transferir |
| `--checkpoint` | Criar um checkpoint CRIU antes de migrar |
| `--skip-dns` | Ignorar a atualização de registos DNS após a migração |
| `--bwlimit <limit>` | Limite de largura de banda para a transferência (por exemplo, `50M`) |

A migração transfere os dados encriptados do repositório via rsync. O repositório de origem permanece intacto até o remover explicitamente.

## Navegar no Armazenamento

Navegar pelo conteúdo de uma localização de armazenamento:

```bash
rdc storage browse --name my-storage
```

## Boas Práticas

- Agende backups cold diários para snapshots consistentes para a aplicação de dados críticos
- Use backups hot para snapshots de alta frequência onde zero downtime é necessário
- Teste os restauros periodicamente para verificar a integridade dos backups
- Use múltiplos fornecedores de armazenamento para dados críticos (por exemplo, S3 + B2)
- Mantenha as credenciais seguras; os backups são encriptados mas a credencial LUKS é necessária para restaurar
