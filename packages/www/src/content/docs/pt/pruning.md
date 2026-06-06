---
title: "Pruning"
description: "Remover backups órfãos, snapshots obsoletos, imagens de repositório e resíduos da config local para recuperar espaço em disco e manter a coerência do estado."
category: "Guides"
order: 12
language: pt
sourceHash: "9b74e1ea24b9735f"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# Pruning

O pruning elimina estado que já não corresponde a um recurso ativo. Três comandos cobrem três âmbitos diferentes:

| Comando | O que limpa | Onde reside a fonte de verdade |
|---|---|---|
| `rdc storage prune --name <storage> -m <machine>` | Backups órfãos no armazenamento na nuvem | Config local do CLI (verificada cruzadamente com a máquina executora para segurança de montagem) |
| `rdc machine prune --name <machine>` | Artefactos do datastore na máquina (sempre); imagens de repositório órfãs ou desconhecidas (opcional) | Config local do CLI + o espelho `.interim/state` da máquina |
| `rdc config prune` | Resíduos da config local (cache de certificados, arquivos expirados, referências cruzadas pendentes) | Apenas a config local do CLI |

Os três são independentes. Pode executar qualquer um sem os outros. Partilham um modelo de segurança comum descrito em [Segurança](#safety-model) abaixo.

## Preflight de segurança de montagem

`storage prune` e `machine prune --prune-unknown` executam ambos um **preflight de segurança de montagem** antes de eliminar qualquer coisa: consultam a máquina executora para repositórios atualmente montados ou em execução, intersectam com os candidatos a eliminação e **recusam eliminar um candidato que ainda esteja ativo na máquina**. Eliminar o backup fora da máquina de um repositório montado, ou eliminar uma imagem de repositório ativa, é um risco real de perda de dados. O preflight torna impossível fazê-lo por acidente.

Para substituir (raro; apenas quando sabe genuinamente que o estado ativo está errado), passe `--force-delete-mounted`. Esta é uma flag separada de `--force` (que controla o período de carência do arquivo) para que as duas saídas de escape permaneçam distintas.

## Storage Prune

Analisa um fornecedor de armazenamento e elimina backups cujos GUIDs já não aparecem em nenhum ficheiro de config local.

```bash
# Apenas pré-visualização - mostrar o que seria eliminado
rdc storage prune --name my-s3 -m server-1 --dry-run

# Eliminar efetivamente os backups órfãos (comportamento predefinido)
rdc storage prune --name my-s3 -m server-1

# Substituir o período de carência (predefinição 7 dias)
rdc storage prune --name my-s3 -m server-1 --grace-days 14

# Substituir a verificação de segurança de montagem (usar com cuidado)
rdc storage prune --name my-s3 -m server-1 --force-delete-mounted
```

`--machine` é obrigatório porque as chamadas rclone são executadas na máquina executora, não no seu portátil. Não se espera que os clientes tenham rclone instalado localmente. As credenciais de armazenamento ainda provêm da sua config local; a máquina é apenas o executor do rclone.

### O que verifica

1. Lista todos os GUIDs de backup no armazenamento nomeado (em ambos os subdiretórios `hot/` e `cold/`. Consulte [Backup e Restauro](/pt/docs/backup-restore#scheduled-backups)).
2. Analisa todos os ficheiros de config em disco (`~/.config/rediacc/*.json`).
3. Um backup está **órfão** se o seu GUID não for referenciado pela secção de repositórios de nenhuma config.
4. Repositórios arquivados recentemente dentro do período de carência estão **protegidos** mesmo que removidos da config ativa.
5. Preflight de segurança de montagem: GUIDs atualmente montados em `--machine` são ignorados e reportados, nunca eliminados.

### Desempenho

As eliminações são agrupadas por subcaminho de armazenamento: uma chamada rclone por diretório `hot/` ou `cold/` independentemente de quantos GUIDs estão a ser removidos. Um atraso de 11 órfãos passa de cerca de 50 s de overhead SSH para uma única ida e volta por subcaminho.

## Machine Prune

Limpa recursos na máquina em três fases. A Fase 1 é sempre executada; as fases 2 e 3 são opcionais e podem ser combinadas.

### Fase 1: Limpeza do datastore (sempre executada)

Remove todos os tipos de recursos que podem ficar para trás quando um repositório é eliminado ou quando uma refatoração ao nível da máquina retira uma convenção de nomenclatura. Cada categoria é analisada de forma independente, e a limpeza é uma passagem idempotente única, pelo que executar o pruning repetidamente é seguro e converge para um datastore limpo.

| Categoria | O que remove |
|---------|-----------------|
| Diretórios de montagem vazios | Diretórios `mounts/<guid>/` sem imagem de repositório de suporte |
| Diretórios imovíveis órfãos | Diretórios `immovable/<guid>/` sem imagem de repositório de suporte |
| Ficheiros de bloqueio obsoletos | `repositories/.lock-<guid>` para repositórios eliminados |
| Snapshots de backup obsoletos | `.snapshot-*` e `.backup-*` deixados por execuções de backup interrompidas |
| Diretórios sandbox VS Code órfãos | `.interim/sandbox/<name>` para repositórios já não ativos na máquina |
| Cadeias iptables órfãs | Cadeias `REDIACC_WILDCARD_<N>` e `DOCKER_ISOLATED_NET_<N>` para redes eliminadas |
| Entradas authorized_keys órfãs | Linhas `sandbox-gateway <repo> --guid <uuid>` cujo `--guid` já não corresponde a um diretório de montagem ativo |

A análise de authorized_keys verifica `/home/*/.ssh/authorized_keys` e `/root/.ssh/authorized_keys`. Uma entrada é mantida apenas se a sua etiqueta `--guid` mapear para um GUID de diretório de montagem ativo, pelo que os repositórios atualmente implantados na máquina são sempre preservados independentemente de o seu nome aparecer em algum lugar no disco. As entradas legadas escritas antes de o renet começar a adicionar a etiqueta `--guid` não podem ser validadas e são sempre reportadas como órfãs.

```bash
# Dry-run, mostra o que seria removido (sem alterações aplicadas)
rdc machine prune --name server-1 --dry-run

# Executar a limpeza
rdc machine prune --name server-1
```

> **Limpeza em cascata.** Algumas categorias dependem de categorias anteriores. Por exemplo, eliminar diretórios de montagem vazios pode expor órfãos de sandbox adicionais cujo suporte de montagem acabou de desaparecer. Executar `rdc machine prune` uma segunda vez captura a cascata e termina a limpeza. O dry-run final termina com `No orphaned resources found. Datastore is clean.` quando não há nada mais a fazer.

### Fase 2: `--orphaned-repos` (grosseiro)

Com `--orphaned-repos`, o CLI também elimina imagens de repositório na máquina que não aparecem em **nenhum** ficheiro de config local.

```bash
rdc machine prune --name server-1 --orphaned-repos --dry-run
rdc machine prune --name server-1 --orphaned-repos
```

Isto é **grosseiro**. Elimina tudo o que não está na sua config local, incluindo forks legítimos geridos por outras ferramentas ou o checkout do CLI de outro operador. Se o espelho `.interim/state` do renet identificar corretamente um repositório como um fork mas a config local nunca o tiver visto, esta fase remove-o na mesma. Prefira a fase 3 (`--prune-unknown`) quando quiser ser conservador.

### Fase 3: `--prune-unknown` (cirúrgico)

Com `--prune-unknown`, o CLI elimina apenas repositórios que **ambos** os sinais não conseguem classificar: não estão em nenhuma config local **e** não têm entrada marcada como fork no espelho `.interim/state` da máquina (consulte [Repositórios. Coluna `Type`](/pt/docs/repositories#type-column-and-the-state-mirror)).

```bash
rdc machine prune --name server-1 --prune-unknown --dry-run
rdc machine prune --name server-1 --prune-unknown
```

Na prática, `--prune-unknown` é o que se quer para limpeza de rotina; `--orphaned-repos` só é correto quando tem a certeza de que a sua config local é o inventário completo e autoritativo de todos os repositórios na máquina. Órfãos legados pré-espelho e repositórios cuja entrada de config foi eliminada por engano caem ambos no balde "desconhecido". São genuinamente incertos, e a flag cirúrgica pede ao operador que reconheça isso explicitamente.

O preflight de segurança de montagem também é executado nesta fase: um repositório atualmente montado em `--machine` é reportado e ignorado a menos que `--force-delete-mounted` seja passado.

```bash
# Combinado: limpeza completa da máquina com o caminho cirúrgico consciente de forks
rdc machine prune --name server-1 --prune-unknown
```

## Config Prune

Varre resíduos obsoletos **dentro do ficheiro de config local** em `~/.config/rediacc/<config>.json`. Puramente local. Sem SSH, sem chamadas renet. Três categorias são limpas:

1. **Entradas de cache de certificados ACME** cujo âncora (GUID, nome do repositório ou nome da máquina) já não está na config ativa. Os wildcards de certificado nunca podem encaminhar para lado nenhum, por isso são peso morto.
2. **Repositórios arquivados expirados** em `resources.deletedRepositories[]`. Entradas cujo `deletedAt` é mais antigo que `defaults.pruneGraceDays` (predefinição 7 dias). Entradas dentro da carência são reportadas (com dias restantes) e mantidas.
3. **Referências cruzadas pendentes** entre categorias da config:
   - Entradas `resources.machines.<m>.backupStrategies[]` que nomeiam uma estratégia que já não existe.
   - Entradas `resources.backupStrategies.<s>.exclude[]` e `include[]` que nomeiam um repositório que já não existe.
   - Destinos de armazenamento cujo armazenamento alvo está em falta. Assinalados como aviso, não removidos automaticamente (a remoção automática alteraria a semântica da estratégia).

```bash
# Apenas pré-visualização
rdc config prune --dry-run

# Aplicar (comportamento predefinido)
rdc config prune

# Restringir a uma categoria
rdc config prune --certs-only
rdc config prune --archives-only
rdc config prune --refs-only

# Eliminar TODOS os repositórios arquivados independentemente da carência
rdc config prune --purge-archived

# Substituir a janela de carência de arquivo para esta invocação
rdc config prune --grace-days 30
```

### O que NÃO toca

- Recursos ativos (máquinas, armazenamentos, repositórios, estratégias de backup, fornecedores de nuvem).
- Credenciais, o bloco de conta, o bloco de encriptação, as predefinições.
- `vaultContent` de armazenamento (incluindo `access_token` expirado do OneDrive. O refresh_token ainda cria novos; o pruning forçaria a reautenticação).
- Entradas `knownHosts` (o caminho de atualização automática é `rdc config machine scan-keys`).
- O array comprimido de blobs de certificado (`infra.acmeCertCache.<base>.data[]`) é reconstruído automaticamente a partir da lista de certificados limpa; não perde nenhuma cadeia que ainda cubra um nome mantido.

### Exemplo prático

Saída de uma execução real numa máquina com quatro wildcards de GUID órfão e dois wildcards de nome de máquina obsoletos:

```text
Scanning local config for stale leftovers...
6 cert cache entry/entries would be removed:
  *.linode-1.rediacc.io  (unknown machine linode-1)
  *.marketing.linode-1.rediacc.io  (unknown machine linode-1)
  *.5b749533-99be-446c-9fe3-e6d0eec905a6.hostinger.rediacc.io  (unknown GUID 5b749533-…)
  *.5d09f3a6-9558-4df1-8a6e-b63140a6a7a6.hostinger.rediacc.io  (unknown GUID 5d09f3a6-…)
  *.e18d8c0f-367e-43c7-919e-2dbc59db4b5e.hostinger.rediacc.io  (unknown GUID e18d8c0f-…)
  *.9806c9b8-6bfb-4a87-9eaa-4b757ce1daca.hostinger.rediacc.io  (unknown GUID 9806c9b8-…)
Dry run: 6 change(s) would be applied. Re-run without --dry-run to commit.
```

Os nomes de certificados cujo âncora é uma máquina, repositório ou GUID ativo são deixados intactos, assim como qualquer wildcard de rótulo único `<service>.<base>` ou raiz `*.<base>`.

## Migração: preenchimento retroativo do espelho de estado

O espelho `.interim/state/<guid>/.rediacc.json` que alimenta `--prune-unknown` e a coluna `Type` em `rdc repo list -m` é escrito:

- **No momento do fork** (`rdc repo fork`). Imediatamente, mesmo antes de o fork ser montado pela primeira vez.
- **Em cada salvaguarda de estado** (`rdc repo mount` e qualquer operação que atualize o estado do repositório). Para repositórios criados antes de o código do espelho ter sido lançado.

Repositórios criados **antes de o espelho existir e que não foram remontados desde a atualização** não têm ficheiro de espelho. Aparecem como `unknown` em `rdc repo list -m` mesmo que alguns sejam legalmente forks. Para corrigir isto para órfãos legados, execute o preenchimento retroativo único na máquina:

```bash
sudo /usr/local/bin/renet repository backfill-state-mirror \
    --datastore /mnt/rediacc \
    --mark-as-fork <guid1>,<guid2>,<guid3>
```

O preenchimento retroativo copia o estado ativo em volume para o espelho dos repositórios atualmente montados e escreve um espelho sintético marcado como fork para quaisquer GUIDs que liste em `--mark-as-fork`. Após o preenchimento retroativo, os backups agendados deixam de carregar os forks listados (o pipeline de carregamento verifica o espelho para `is_fork: true`).

## Modelo de Segurança

O pruning é concebido para ser seguro por predefinição em configurações com múltiplas configs.

### Consciência de múltiplas configs

`storage prune` e `machine prune --orphaned-repos` analisam **todos** os ficheiros de config em `~/.config/rediacc/`, não apenas o ativo. Um repositório referenciado por `production.json` não será eliminado mesmo que esteja ausente de `staging.json`. Isto evita eliminações acidentais quando as configs estão limitadas a ambientes diferentes.

### Período de carência

Quando um repositório é removido de uma config com `--archive-config`, a sua entrada de credencial é movida para `resources.deletedRepositories[]` com um timestamp `deletedAt`. Os comandos de pruning respeitam um período de carência (predefinição 7 dias) durante o qual repositórios arquivados recentemente estão protegidos contra eliminação. Isto dá-lhe tempo para restaurar um repositório (`rdc config repository restore-archived --name <guid>`) se tiver sido removido acidentalmente. Após a carência expirar, `storage prune`, `machine prune` e `config prune` eliminam automaticamente a entrada.

### Preflight de segurança de montagem

Abordado acima. `storage prune` e `machine prune --prune-unknown` recusam eliminar repositórios que estejam atualmente montados ou em execução na máquina executora. Substitua apenas com `--force-delete-mounted`.

### Aplicar por predefinição; `--dry-run` para pré-visualizar

Os três comandos de pruning aplicam **as alterações** por predefinição. Passe `--dry-run` para pré-visualizar sem escrever. Isto corresponde ao verbo: "prune" é destrutivo por si só, e uma flag de dry-run é a saída explícita.

## Configuração

### `pruneGraceDays`

Defina um período de carência predefinido personalizado no seu ficheiro de config para não ter de passar `--grace-days` sempre:

```bash
# Definir o período de carência para 14 dias na config ativa
rdc config field set --pointer /defaults/pruneGraceDays --new 14
```

A flag `--grace-days` do CLI substitui este valor quando fornecida.

### Precedência

1. Flag `--grace-days <N>` (prioridade mais alta)
2. `pruneGraceDays` no ficheiro de config
3. Predefinição incorporada: 7 dias

## Boas Práticas

- **Execute dry-run primeiro em produção.** Pré-visualize sempre antes de executar um pruning destrutivo, especialmente no armazenamento de produção.
- **Mantenha múltiplas configs atualizadas.** O pruning de armazenamento e de máquina verifica todas as configs no diretório de config. Se um ficheiro de config estiver obsoleto ou eliminado, os seus repositórios perdem a proteção. Mantenha os ficheiros de config precisos.
- **Prefira `--prune-unknown` a `--orphaned-repos`.** A flag cirúrgica respeita o espelho renet; a flag grosseira elimina com prazer forks criados por outras ferramentas.
- **Use períodos de carência generosos para produção.** O período de carência predefinido de 7 dias é adequado para a maioria dos fluxos de trabalho. Para ambientes de produção com janelas de manutenção pouco frequentes, considere 14 ou 30 dias.
- **Agende o storage prune após as execuções de backup.** Combine `storage prune` com o seu agendamento de backup para manter os custos de armazenamento sob controlo sem intervenção manual.
- **Combine o machine prune com o agendamento de backup.** Após implementar agendamentos de backup (`rdc machine backup schedule`), adicione um pruning periódico de máquina para limpar snapshots obsoletos e artefactos de datastore órfãos.
- **Execute `config prune` periodicamente.** O inchaço da config local (especialmente a cache de certificados) acumula-se silenciosamente; um `config prune --dry-run` trimestral é suficiente para o detetar.
- **Audite antes de usar `--force` ou `--force-delete-mounted`.** Ambas as flags contornam verificações de segurança. Use `--force` apenas quando tiver a certeza de que nenhuma outra config referencia os repositórios em questão; use `--force-delete-mounted` apenas quando tiver a certeza de que o estado ativo na máquina está errado.
