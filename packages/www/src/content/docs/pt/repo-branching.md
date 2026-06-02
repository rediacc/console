---
title: "Ramificação semelhante ao git"
description: "Trate forks copy-on-write como commits git: congele um fork num commit imutável, nomeie branches, faça checkout de commits para forks graváveis, percorra o histórico e faça merge sem nunca modificar um repositório em produção."
category: Reference
subcategory: advanced
order: 41
language: pt
sourceHash: "6ca18986dfd6e237"
sourceCommit: "4e60a12e0664cdee5ad9079a7b75e2d05980d0f5"
---

# Ramificação semelhante ao git

Os repositórios Rediacc suportam versionamento semelhante ao git baseado em forks copy-on-write. Cada fork imutável é um **commit**: uma imagem congelada e byte-estável que recusa ser montada. Os branches são refs com nome que apontam para um commit. `rdc repo checkout` clona um commit via reflink de volta para um fork de trabalho gravável, e `rdc repo merge` combina duas linhas de histórico sem nunca modificar um repositório em produção no local.

O modelo mapeia para duas estruturas de armazenamento. A **máquina é o object store**: os commits são imagens de fork imutáveis que vivem no datastore. A **config do CLI é o ref store**: os nomes de branches, o `HEAD` atual e o reflog vivem na sua config local, não na máquina. Esta é a mesma divisão que o git usa entre `.git/objects` e `.git/refs`.

## Quando usar

Recorra à ramificação quando um fork ganhou um nome. Um agente de IA correu livremente num fork da produção, o resultado parece bom, e quer um checkpoint congelado e nomeado ao qual possa regressar ou promover mais tarde: `rdc repo commit` congela-o, `rdc repo branch` dá-lhe um nome. Antes de uma migração arriscada, faça commit do fork de trabalho para ter um ponto de rollback exato que nunca mudará (um commit imutável recusa ser montado, pelo que nada pode escrever nele). Para comparar dois checkpoints, `rdc repo diff` funciona entre quaisquer dois commits porque partilham um ancestral copy-on-write. Para trazer uma linha de trabalho revista de volta para um fork alvo, `rdc repo merge` constrói o resultado num clone por reflink e substitui-o atomicamente, pelo que um alvo em execução nunca é corrompido a meio do merge.

Não recorra a isto como substituto de `rdc repo fork` quando apenas precisa de uma cópia descartável. Um fork simples é a unidade certa para isolamento efémero por teste. Os commits acrescentam valor quando um estado vale a pena manter, nomear ou promover.

## Como os commits e os forks se relacionam

Um repositório é um único ficheiro de imagem LUKS num pool btrfs. Um fork é um reflink do tempo constante dessa imagem, pelo que fazer fork de um repositório de 1 GB e de um de 100 GB custa o mesmo. Um **commit** é um fork que foi marcado como imutável: o renet recusa montá-lo, o que mantém a sua imagem byte-estável para sempre. Essa byte-estabilidade é o que torna um commit um ponto de rollback fiável e uma base determinística para transferência delta entre máquinas.

`rdc repo commit` regista a mensagem de commit, o autor, o timestamp e o commit pai **dentro do volume** (para que os metadados viajem com a imagem no push) e também os espelha fora do volume (para que `rdc repo log` possa percorrer o histórico sem desbloquear nada). O fork de trabalho do qual fez commit continua inalterado, exatamente como o git deixa a sua árvore de trabalho intacta após um commit.

## Comandos

### rdc repo commit

Congela um fork de trabalho montado num novo commit imutável.

```bash
rdc repo commit --name <fork> --message "<message>" -m <machine>
```

| Opção | Descrição | Predefinição |
|-------|-----------|--------------|
| `--name <name>` | Fork de trabalho a commitar. Deve estar montado. Obrigatório. | obrigatório |
| `--message <msg>` | Mensagem de commit. Obrigatório. | obrigatório |
| `--author <author>` | Autor do commit registado nos metadados. | não definido |
| `-m, --machine <name>` | Máquina alvo. Obrigatório. | obrigatório |
| `--debug` | Diagnósticos verbosos no stderr. | desligado |

O novo commit é registado na config local com `immutable: true`, e o `headCommit` do fork de trabalho avança para apontar para ele. Commitar um repositório imutável é recusado: faça primeiro checkout num fork gravável.

### rdc repo branch

Cria um ref de branch com nome apontando para o commit atual de um fork de trabalho.

```bash
rdc repo branch --branch <name> --name <fork>
```

| Opção | Descrição | Predefinição |
|-------|-----------|--------------|
| `--branch <branch>` | Nome do novo branch. Obrigatório. | obrigatório |
| `--name <name>` | Fork de trabalho cujo commit atual o branch aponta. Obrigatório. | obrigatório |

Esta é uma operação apenas na config. Não acontece trabalho na máquina. O ref do branch mapeia um nome para o `headCommit` do fork de trabalho, pelo que o fork deve ter pelo menos um commit primeiro.

### rdc repo checkout

Clona via reflink um commit imutável (ou a ponta de um branch) num novo fork de trabalho gravável.

```bash
rdc repo checkout --ref <commit> --tag <newFork> -m <machine>
rdc repo checkout --ref <branchName> --from <fork> --tag <newFork> -m <machine>
```

| Opção | Descrição | Predefinição |
|-------|-----------|--------------|
| `--ref <commit\|branch>` | GUID de commit a fazer checkout, ou nome de branch quando `--from` é fornecido. Obrigatório. | obrigatório |
| `--tag <name>` | Nome para o novo fork de trabalho gravável. Obrigatório. | obrigatório |
| `-m, --machine <name>` | Máquina alvo. Obrigatório. | obrigatório |
| `--from <workingFork>` | Resolve `--ref` como nome de branch neste conjunto de branches do fork de trabalho. | commit direto |
| `--debug` | Diagnósticos verbosos no stderr. | desligado |
| `--skip-router-restart` | Ignora o passo de reinício do router. | desligado |

O checkout reutiliza o caminho de reflink do fork, pelo que é quase instantâneo e de tempo constante independentemente do tamanho do repositório. O `headCommit` do novo fork de trabalho é definido para o commit do qual foi feito checkout.

### rdc repo log

Percorre o histórico de commits acessível a partir de um fork de trabalho ou de um commit.

```bash
rdc repo log --name <fork> -m <machine>
```

| Opção | Descrição | Predefinição |
|-------|-----------|--------------|
| `--name <name>` | Fork de trabalho ou commit a partir do qual iniciar o percurso do histórico. Obrigatório. | obrigatório |
| `-m, --machine <name>` | Máquina alvo. Obrigatório. | obrigatório |
| `--json` | Saída do histórico de commits como JSON. | desligado |
| `--debug` | Diagnósticos verbosos no stderr. | desligado |

O `log` percorre a cadeia de pais registada por `rdc repo commit`, lendo o espelho de estado fora do volume para que nenhum commit seja desbloqueado ou montado. É apenas de leitura.

### rdc repo merge

Faz merge de um commit ou fork fonte num fork de trabalho alvo, sem modificar o alvo em produção no local.

```bash
rdc repo merge --name <target> --from <source> -m <machine>
rdc repo merge --name <target> --from <source> --resolve theirs -m <machine>
```

| Opção | Descrição | Predefinição |
|-------|-----------|--------------|
| `--name <name>` | Fork de trabalho alvo do merge. Obrigatório. | obrigatório |
| `--from <source>` | Commit ou fork fonte do merge. Obrigatório. | obrigatório |
| `-m, --machine <name>` | Máquina alvo. Obrigatório. | obrigatório |
| `--force` | Quiece um alvo montado ou em execução primeiro, depois faz merge. Nunca modifica um mount em produção. | desligado |
| `--resolve <ours\|theirs>` | Merge de três vias por ficheiro: integra as alterações por ficheiro da fonte no alvo, mantendo (`ours`) ou assumindo (`theirs`) a versão da fonte para ficheiros alterados em ambos os lados. Omitir para whole-image take-theirs. | desligado |
| `--base <guid>` | Commit ancestral comum para o merge de três vias (usado com `--resolve`). Por predefinição usa o pai do commit fonte, ou o commit atual do alvo. | automático |
| `--debug` | Diagnósticos verbosos no stderr. | desligado |

O resultado é construído num clone por reflink e substituído atomicamente por um marcador crash-safe, pelo que um merge interrompido deixa o alvo original intacto. Um alvo montado ou em execução é recusado a menos que se use `--force`, que desliga o alvo de forma limpa antes da substituição.

Sem `--resolve`, o merge é um whole-image take-theirs (o alvo torna-se a fonte). Com `--resolve`, é um merge de três vias por ficheiro contra o pai registado do commit fonte: os ficheiros alterados apenas num lado são tomados desse lado, e os ficheiros alterados em ambos os lados são resolvidos pela flag. Os caminhos em conflito são reportados.

### rdc repo gc

Recolhe objetos de commit imutáveis numa máquina que nenhum branch ou HEAD alcança.

```bash
rdc repo gc -m <machine>            # pré-visualização dry-run (predefinição)
rdc repo gc --apply -m <machine>    # elimina os commits inacessíveis
```

| Opção | Descrição | Predefinição |
|-------|-----------|--------------|
| `-m, --machine <name>` | Máquina a recolher. Obrigatório. | obrigatório |
| `--apply` | Elimina efetivamente os commits inacessíveis (caso contrário é apenas uma pré-visualização). | desligado |
| `--debug` | Diagnósticos verbosos no stderr. | desligado |

A acessibilidade é calculada a partir da config local (o ref store): o conjunto de commits acessíveis seguindo cada ponta de branch e HEAD pela cadeia de pais. Os commits imutáveis na máquina fora desse conjunto são inacessíveis. Um objeto montado ou um fork de trabalho nunca são recolhidos.

### rdc repo fsck

Valida os refs da config contra os objetos presentes numa máquina.

```bash
rdc repo fsck -m <machine>
```

| Opção | Descrição | Predefinição |
|-------|-----------|--------------|
| `-m, --machine <name>` | Máquina a verificar. Obrigatório. | obrigatório |

Reporta refs pendentes (uma ponta de branch ou HEAD a apontar para um GUID sem objeto na máquina) e commits órfãos (um commit imutável na máquina que nenhum ref alcança). É apenas de leitura; recupere órfãos com `rdc repo gc --apply`.

### Forks imutáveis

`rdc repo fork --immutable` marca o novo fork como só de leitura na criação, produzindo uma base equivalente a um commit sem um passo `commit` separado.

```bash
rdc repo fork --parent <name> --tag <tag> --immutable -m <machine>
```

Um fork imutável recusa ser montado, o que mantém a sua imagem byte-estável para sempre. Isto é útil como base congelada para transferência delta entre máquinas, onde a base deve ser idêntica em ambos os lados. Para fazer alterações, faça checkout (ou fork novamente) numa cópia gravável.

## Exemplos

### Commitar um fork de trabalho

```bash
$ rdc repo commit --name myapp:work --message "schema migration applied" -m server-1
Committed 4f3c2a1b9d8e: schema migration applied
```

### Commitar com um autor explícito

```bash
$ rdc repo commit --name myapp:work --message "nightly snapshot" --author ci-bot -m server-1
Committed 7a1b2c3d4e5f: nightly snapshot
```

### Nomear um branch no commit atual

```bash
$ rdc repo branch --branch staging --name myapp:work
Branch "staging" -> 4f3c2a1b9d8e
```

### Fazer checkout de um commit num novo fork gravável

```bash
$ rdc repo checkout --ref 4f3c2a1b9d8e --tag rollback-test -m server-1
```

### Fazer checkout da ponta de um branch por nome

Com `--from`, o valor de `--ref` é resolvido como nome de branch no fork de trabalho indicado:

```bash
$ rdc repo checkout --ref staging --from myapp:work --tag staging-copy -m server-1
```

### Percorrer o histórico

```bash
$ rdc repo log --name myapp:work -m server-1
commit 4f3c2a1b9d8e
  Author: ci-bot  Date: 2026-05-29T10:14:02Z
  schema migration applied
commit 9d8e7a1b2c3d
  Author: ci-bot  Date: 2026-05-28T22:01:55Z
  initial import
```

### Histórico em JSON

`--json` emite o percurso estruturado, do mais recente para o mais antigo:

```bash
$ rdc repo log --name myapp:work --json -m server-1
{
  "success": true,
  "start": "4f3c2a1b9d8e",
  "entries": [
    {
      "guid": "4f3c2a1b9d8e",
      "message": "schema migration applied",
      "author": "ci-bot",
      "parent": "9d8e7a1b2c3d",
      "committed_at": "2026-05-29T10:14:02Z",
      "immutable": true
    }
  ]
}
```

### Comparar dois commits

`rdc repo diff` funciona entre quaisquer dois commits porque partilham um ancestral copy-on-write. Faça checkout de um commit e depois compare-o com outro:

```bash
$ rdc repo checkout --ref 4f3c2a1b9d8e --tag review -m server-1
$ rdc repo diff --name review --base myapp:work -m server-1
M  db/schema.sql

1 file changed: 0 added, 1 modified, 0 deleted, 0 renamed
```

Veja [rdc repo diff](/pt/docs/repo-diff) para a referência completa do diff.

### Fazer merge de uma linha revista de volta

```bash
$ rdc repo merge --name myapp:main --from myapp:work -m server-1
Merged myapp:work into myapp:main
```

### Fazer merge num alvo em execução

Um alvo montado ou em execução é recusado a menos que se use `--force`, que o quiece primeiro:

```bash
$ rdc repo merge --name myapp:main --from myapp:work --force -m server-1
Merged myapp:work into myapp:main
```

### Merge de três vias por ficheiro

Dois forks (`feature` e `hotfix`) com checkout a partir do mesmo commit, cada um com alguns ficheiros alterados. `--resolve theirs` integra a fonte (`hotfix`) no alvo (`feature`): os ficheiros que apenas um lado alterou são tomados desse lado, e os ficheiros que ambos os lados alteraram são resolvidos para a fonte. A base é detetada automaticamente a partir do ancestral partilhado (ou fixe-a com `--base`):

```bash
$ rdc repo merge --name myapp:feature --from myapp:hotfix --resolve theirs -m server-1
Merged myapp:hotfix into myapp:feature (three-way); 1 conflict(s) resolved --theirs: [config/app.yaml]
```

`config/app.yaml` foi alterado em ambos os lados e foi resolvido para a fonte; um ficheiro que apenas `hotfix` adicionou é aplicado, e um ficheiro que apenas `feature` alterou é mantido. Os caminhos em conflito são reportados para que possa revê-los.

### Criar uma base imutável diretamente

```bash
$ rdc repo fork --parent myapp --tag baseline-v1 --immutable -m server-1
```

## Transferência delta push e pull

Uma imagem imutável e byte-estável é também a base para **transferência delta ao nível dos blocos**. Quando a mesma base imutável existe em duas máquinas, um push ou pull pode calcular os blocos alterados relativamente a essa base e mover apenas esses, em vez de analisar toda a imagem encriptada. Um repositório de 1 GB com alguns blocos alterados transfere então em megabytes.

Normalmente não precisa de passar uma base manualmente. Após um push completo, o CLI retém a imagem enviada como base imutável em ambas as máquinas e regista-a, pelo que o **próximo** push desse repositório envia automaticamente apenas o delta, sem qualquer flag, mesmo para um fork que já existe no alvo. (Um re-push *completo* de um fork existente ainda precisa de `--force`, pois isso substitui toda a imagem em vez de aplicar um delta verificado.) Passe `--delta-base <guid>` para fixar uma base específica, e `--strategy <auto|physical|shared>` para controlar como os blocos alterados são detetados (`auto` é correto em quase todos os casos).

```bash
# O primeiro push é uma transferência completa; também retém uma base reutilizável em ambos os lados.
$ rdc repo push --name myapp:work --to-machine backup-1 -m server-1

# Após alterações locais, o próximo push envia apenas os blocos alterados, sem flag.
$ rdc repo push --name myapp:work --to-machine backup-1 -m server-1

# Fixar uma base explícita (um commit imutável presente em ambas as máquinas).
$ rdc repo push --name myapp:work --to-machine backup-1 --delta-base 4f3c2a1b9d8e -m server-1

# O delta também funciona ao contrário, puxando apenas os blocos alterados de uma máquina fonte.
$ rdc repo pull --name myapp:work --from-machine backup-1 --delta-base 4f3c2a1b9d8e -m server-1

# Re-puxar um repositório local existente (sobrescrever) com --force.
$ rdc repo pull --name myapp:work --from-machine backup-1 --force -m server-1
```

A transferência delta aplica-se apenas entre máquinas (um remoto com a base FIEMAP). Os pushes para armazenamento de objetos na nuvem transferem sempre a imagem completa. A base deve ser byte-idêntica em ambos os lados, o que é exatamente o que um commit imutável ou um fork `--immutable` garante.

## Schema JSON

`rdc repo log --json` envolve o resultado do renet no envelope padrão. O histórico percorrido vive em `entries`, do mais recente para o mais antigo:

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `success` | boolean | Se o percurso foi concluído. |
| `start` | string | GUID a partir do qual o percurso começou. |
| `entries` | array | Um objeto por commit, do mais recente para o mais antigo. |
| `entries[].guid` | string | GUID do commit. |
| `entries[].message` | string | Mensagem de commit. Omitido quando vazio. |
| `entries[].author` | string | Autor do commit. Omitido quando vazio. |
| `entries[].parent` | string | GUID do commit pai. Omitido na raiz. |
| `entries[].committed_at` | string | Timestamp do commit em RFC 3339. Omitido quando não definido. |
| `entries[].immutable` | boolean | Se o commit está marcado como só de leitura (sempre true para um commit real). |

Para os campos do envelope e as regras de deteção automática que emitem JSON em ambientes não-TTY, veja a [Referência de Saída JSON](/pt/docs/ai-agents-json-output).

## Limitações

- **Os refs são locais.** Os nomes de branches, `HEAD` e o reflog vivem na sua config do CLI, não na máquina. Fazer push de um commit para outra máquina envia o objeto do commit e os seus metadados dentro do volume, mas o ref do branch é um conceito do lado da config.
- **Um commit recusa ser montado.** Esse é o objetivo: a imutabilidade é o que torna um commit byte-estável. Para executar ou editar um commit, faça primeiro checkout num fork de trabalho gravável.
- **A resolução de merge é ao nível do ficheiro, não ao nível da linha.** Tanto o whole-image take-theirs (sem `--resolve`) como o de três vias por ficheiro (`--resolve ours|theirs`) são suportados. O merge de três vias resolve conflitos um ficheiro de cada vez segundo a flag; não produz hunks ao nível da linha nem marcadores de merge dentro de um ficheiro.
- **O histórico é uma cadeia de pais.** `rdc repo log` percorre o único link `parent` registado no momento do commit. Para quando chega a um commit cujos metadados não estão presentes na máquina consultada.

## Ver também

- [rdc repo diff](/pt/docs/repo-diff). Diff ao nível de ficheiros entre quaisquer dois commits ou forks relacionados.
- [Repositórios](/pt/docs/repositories). Criar, fazer fork, montar e operar repositórios.
