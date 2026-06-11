---
title: "Repositórios"
description: "Crie, gerencie e opere repositórios criptografados com LUKS em máquinas remotas."
category: "Guides"
order: 4
language: pt
sourceHash: "65fd6e7f9e6a83c1"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# Repositórios

Um **repositório** é uma imagem de disco criptografada com LUKS em um servidor remoto. Quando montado, fornece:
- Um sistema de arquivos isolado para os dados da sua aplicação
- Um daemon Docker dedicado (separado do Docker do host)
- IPs de loopback únicos para cada serviço dentro de uma subnet /26

## Criar um Repositório

```bash
rdc repo create --name my-app -m server-1 --size 10G
```

| Opção | Obrigatório | Descrição |
|--------|----------|-------------|
| `-m, --machine <name>` | Sim | Máquina de destino onde o repositório será criado |
| `--size <size>` | Sim | Tamanho da imagem de disco criptografada (por ex: `5G`, `10G`, `50G`) |
| `--skip-router-restart` | Não | Pular o reinício do servidor de rota após a operação |

A saída mostrará três valores gerados automaticamente:

- **Repository GUID**: Uma UUID que identifica a imagem de disco criptografada no servidor.
- **Credential**: Uma frase de senha aleatória usada para criptografar/descriptografar o volume LUKS.
- **Network ID**: Um inteiro (começando em 2816, incrementando em 64) que determina a subnet de IP para os serviços deste repositório.

> **Armazene a credencial com segurança.** É a chave de criptografia do seu repositório. Se perdida, os dados não poderão ser recuperados. A credencial é armazenada no seu `config.json` local, mas não é armazenada no servidor.

## Montar e Desmontar

Montar descriptografa e torna o sistema de arquivos do repositório acessível. Desmontar fecha o volume criptografado.

```bash
rdc repo mount --name my-app -m server-1  # Descriptografa e monta
rdc repo unmount --name my-app -m server-1  # Desmonta e re-criptografa
```

| Opção | Descrição |
|--------|-------------|
| `--checkpoint` | Cria um checkpoint CRIU antes de montar/desmontar (para contêineres com label `rediacc.checkpoint=true`) |
| `--skip-router-restart` | Pula o reinício do servidor de rota após a operação |

## Verificar Status

```bash
rdc repo status --name my-app -m server-1
```

## Listar Repositórios

```bash
rdc repo list -m server-1
```

### Coluna Type e o espelho de estado

A tabela de saída inclui uma coluna `Type` com três valores:

- **`grand`**: Um repositório de nível superior registrado na sua configuração de CLI local sem um pai. O caso base.
- **`fork`**: Uma cópia copy-on-write de outro repositório. Identificado via `grandGuid` na configuração local **ou** via o espelho `.interim/state` do renet na máquina. Qualquer uma das fontes é autoritária; ambas devem concordar uma vez que o espelho está preenchido.
- **`unknown`**: Nenhum sinal consegue classificar o repositório. Frequentemente um fork legacy pré-espelho (criado antes do código do espelho ser entregue e nunca remontado desde então), ou um `grand` obsoleto cuja entrada de configuração local foi deletada por engano. O CLI recusa adivinhar; o operador deve executar o [preenchimento de backfill do espelho de estado](/en/docs/pruning#migration-state-mirror-backfill) ou remover o diretório se for genuinamente órfão.

O arquivo de espelho `.interim/state/<guid>/.rediacc.json` é um pequeno arquivo sidecar escrito **fora** do volume criptografado com LUKS para que ferramentas de backup e `repo list` possam ler a linhagem de fork sem desbloquear cada imagem. Carrega a mesma forma que o `.rediacc.json` no volume (`is_fork`, `grand_guid`, `name`, etc.) e é atualizado a cada `Repository.SaveState`. Ou seja, a cada montagem e toda mutação de estado. É a fonte da verdade para detecção de fork em backups agendados: um fork desmontado com um espelho que diz `is_fork: true` é corretamente ignorado dos uploads `cold` e `hot`.

Para limpeza rotineira de entradas desconhecidas, veja [`rdc machine prune --prune-unknown`](/en/docs/pruning#phase-3---prune-unknown-surgical).

## Redimensionar

Defina o repositório para um tamanho exato ou expanda por uma quantidade específica:

```bash
rdc repo resize --name my-app -m server-1 --size 20G  # Define para tamanho exato
rdc repo expand --name my-app -m server-1 --size 5G  # Adiciona 5G ao tamanho atual
```

> O repositório deve estar desmontado antes de redimensionar. `repo expand` funciona online. Redimensionar altera o tamanho máximo do repositório; para devolver blocos libertos ao pool sem alterar o máximo, use [`repo trim`](#reclamar-espaco-trim) em alternativa.

## Reclamar Espaço (trim)

Eliminar ficheiros dentro de um repositório liberta espaço para esse repositório, e `repo trim` devolve esses blocos libertos ao pool partilhado do datastore. Funciona online, sem qualquer downtime:

```bash
rdc repo trim -m server-1                       # Trim every mounted repository plus the datastore
rdc repo trim -m server-1 --name my-app          # Trim one repository
rdc repo trim -m server-1 --report-only          # Show reclaimable space without trimming
rdc repo trim -m server-1 --docker               # Also clear stopped containers, dangling images, and build cache first
```

Como funciona: as imagens de repositório são ficheiros esparsos, e o volume encriptado passa os discards. Um trim instrui o sistema de ficheiros dentro do repositório a libertar todos os blocos não utilizados, o que cria lacunas na imagem de suporte e reduz imediatamente o uso do pool.

Notas:

- Repositórios com um backup ativo são ignorados e reportados. Fazer trim durante um backup não libertaria espaço, pois o snapshot do backup ainda referencia os blocos.
- Executar trim duas vezes seguidas reporta 0 bytes na segunda vez. O sistema de ficheiros recorda quais os grupos de blocos que já foram processados; isto é esperado, não é uma falha.
- `--docker` nunca remove imagens com tag, apenas as dangling, contentores parados e a cache de compilação. Adicione `--docker-volumes` para também remover volumes não utilizados (isto elimina dados; apenas na CLI).

## Política de Tamanho Automático

Em vez de redimensionar manualmente, deixe a máquina gerir os tamanhos dos repositórios. Uma política ativa o crescimento automático online (o tamanho máximo do repositório aumenta quando fica cheio) e trims agendados. A máquina aplica as políticas a cada poucos minutos através do temporizador systemd `rediacc-storage-maintain`.

```bash
# Machine-wide default: trim every repository daily
rdc repo policy set -m server-1 --auto-trim true

# Per-repository: grow my-app automatically, up to a hard ceiling
rdc repo policy set -m server-1 --name my-app --auto-grow true --max-quota 50G

# Inspect the stored and effective policy
rdc repo policy get -m server-1 --name my-app
```

Campos da política:

| Campo | Significado | Predefinição |
|---|---|---|
| `--auto-grow` | Aumentar o repositório online quando o seu sistema de ficheiros ultrapassa o limiar | desativado |
| `--max-quota` | Teto máximo para o crescimento automático. Obrigatório: defini-lo é o seu consentimento explícito para sobreprovisionar o pool | nenhum |
| `--grow-threshold` | Percentagem de uso do sistema de ficheiros que aciona o crescimento | 85 |
| `--grow-step` | Quanto adicionar por crescimento: valor absoluto (`10G`) ou percentagem do tamanho atual (`20%`) | 20% |
| `--auto-trim` | Executar trims agendados | desativado |
| `--trim-interval` | Horas mínimas entre trims automáticos | 24 |

Salvaguardas: o crescimento automático recusa quando o espaço livre do pool está abaixo de uma reserva (10 GB ou 5% do pool, o que for maior), aguarda pelo menos 30 minutos entre crescimentos do mesmo repositório, e nunca ultrapassa `--max-quota`. Não há redução automática: diminuir o tamanho máximo de um repositório continua a ser um [`repo resize`](#redimensionar) manual e offline.

As definições por repositório substituem a predefinição a nível de máquina. Chamadas repetidas de `policy set` alteram apenas as flags que passar.

## Fork

Crie uma cópia de um repositório existente em seu estado atual:

```bash
rdc repo fork --parent my-app --tag staging -m server-1
```

Forks usam o modelo name:tag: o fork resultante é nomeado `my-app:staging`. Isto cria uma nova cópia criptografada com seu próprio GUID e ID de rede, enquanto compartilha o nome do pai. O fork compartilha a mesma credencial LUKS do pai.

> Forks compartilham os dados do pai via reflink BTRFS, incluindo quaisquer credenciais armazenadas em disco. Veja [O que o Rediacc não isola](/en/docs/ai-agents-safety#what-rediacc-does-not-isolate) para as implicações quando essas credenciais autorizam serviços externos como Stripe, AWS ou Railway. Para manter credenciais de tempo de deploy fora do alcance do fork, use [per-repo secrets](#secrets) em vez de baking valores em arquivos `.env` dentro do repositório.

Na criação do fork, `repo fork` escreve o [arquivo sidecar do espelho de estado](#type-column-and-the-state-mirror) em `<datastore>/.interim/state/<fork-guid>/.rediacc.json` imediatamente. Sem desbloquear o volume. Então o novo fork é corretamente identificado como `is_fork: true` a partir do momento da criação. Isto permite que backups agendados o ignorem (forks são excluídos do pipeline de upload por padrão) mesmo que nunca seja montado. Ao fazer fork de um fork, `grand_guid` encadeia corretamente: o espelho do novo fork aponta para o GUID do avô original, não para o fork intermediário.

### Fork e inicialização em uma etapa

`--up` executa fork, montagem e inicialização dos serviços em uma única operação remota. Adicione `--detach` para recuperar o terminal assim que os contêineres estiverem em execução; as verificações de saúde terminam em segundo plano e o proxy tenta novamente até que cada serviço esteja vinculado:

```bash
rdc repo fork --parent my-app --tag staging -m server-1 --up
rdc repo fork --parent my-app --tag scratch -m server-1 --up --detach
```

Em nossos testes, um repositório de 128 GB fez fork e chegou a serviços em execução em aproximadamente 57 segundos, e cerca de 31 segundos com `--detach`. Execuções em modo detached exibem uma dica para acompanhar o progresso: `rdc machine query --containers --name <machine>`.

### Por onde vai o tempo

Execuções com duração acima de alguns segundos encerram com um resumo de temporização: um detalhamento por etapa, um gráfico em cascata mostrando o que correu em paralelo, e uma linha de atribuição separando o pipeline do Rediacc da inicialização própria dos seus serviços:

```
  Rediacc pipeline 19.2s (61%) · service startup 12.3s (39%)
```

A inicialização dos serviços corresponde à subida dos seus contêineres (imagens, init, verificações de saúde, conforme definido pelo Rediaccfile do repositório; e varia de aplicação para aplicação. Os gráficos são renderizados em terminais interativos; defina `RDC_TIMING_CHART=1` para forçá-los em saída redirecionada.

## Versionamento tipo Git

Forks podem atuar como commits git. `rdc repo commit` congela um fork de trabalho em um commit imutável e byte-estável; `rdc repo branch` nomeia uma linha de histórico; `rdc repo checkout` reflink-clona um commit de volta para um fork gravável; `rdc repo log` caminha a cadeia de pais; e `rdc repo merge` combina duas linhas sem mutar um repositório vivo no local. `rdc repo fork --immutable` produz uma base equivalente a um commit em um único passo.

```bash
rdc repo commit --name my-app:work --message "schema migration applied" -m server-1
rdc repo branch --branch staging --name my-app:work
rdc repo checkout --ref staging --from my-app:work --tag staging-copy -m server-1
```

Veja a [referência de branching tipo Git](/en/docs/repo-branching) para o conjunto completo de comandos, opções e exemplos práticos.

## Secrets

Secrets por repositório são credenciais de tempo de deploy injetadas em contêineres sem ser escritas para a imagem do repositório criptografado. Elas são mantidas em um plano separado dos dados do repositório, então `rdc repo fork` não as propaga. Um fork começa com um mapa de secrets vazio e seus contêineres inicializam se identificando como um principal externo diferente do pai.

> Quer um passo a passo? Veja o [tutorial Gerenciando Secrets](/en/docs/tutorial-managing-secrets) para o conjunto completo de ciclo de set/list/deploy/verify/rotate.

**Modelo write-only (estilo GitHub)**: `get` retorna apenas o digest SHA-256. O valor de texto simples nunca é retornado para ninguém, humano ou agente. Se esquecer qual é um valor, procure-o no seu gerenciador de senhas e rotacione; você não pode lê-lo de volta do Rediacc por design. Isto elimina uma classe inteira de vazamento: gravações de terminal, histórico de shell, redirecionamento acidental, espiação de ombro.

Dois modos de entrega:

- `env`: O secret é exportado como `REDIACC_SECRET_<KEY>` no shell do renet na máquina de destino. Referencie-o do seu `docker-compose.yml` via interpolação `${REDIACC_SECRET_<KEY>}`. Visível dentro do ambiente do contêiner, então use isso para valores em forma de string de conexão que a aplicação já espera em env.
- `file`: O secret é escrito em `/var/run/rediacc/secrets/<networkID>/<KEY>` no host (tmpfs, nunca persistido). Referencie-o do seu arquivo compose via declaração `secrets:` de nível superior com fonte `file:`, mais uma lista `secrets:` por serviço. Contêineres leem de `/run/secrets/<key>`. Prefira este modo para qualquer coisa sensível. Nunca aparece em `docker inspect` ou `/proc/<pid>/environ`.

```bash
# Set, list, get (digest only), unset
rdc repo secret set --name my-app --key STRIPE_LIVE_KEY --value sk_live_xxx --mode file --current ""
rdc repo secret set --name my-app --key DB_HOST         --value postgres.internal --mode env --current ""
rdc repo secret list --name my-app
rdc repo secret get  --name my-app --key DB_HOST    # → { key, mode, digest } — no value
rdc repo secret unset --name my-app --key STRIPE_LIVE_KEY --current sk_live_xxx
```

**Gate de mutação simétrica**: Tanto humanos quanto agentes precisam de `--current <previous-value>` para sobrescrever ou desabilitar um secret (precondição estilo passwd). Para primeira escrita de uma chave nova, passe `--current ""` (vazio). Para rotacionar sem verificar o valor anterior, passe `--rotate-secret` em vez disso. Isto é loudly auditado como uma rotação. `--current` e `--rotate-secret` são mutuamente exclusivos.

Passe `--value -` para ler de stdin em vez de argv (evita exposição de histórico de shell para escritas únicas).

No seu `docker-compose.yml`:

```yaml
services:
  api:
    image: myapp
    environment:
      DATABASE_HOST: ${REDIACC_SECRET_DB_HOST}
    secrets:
      - stripe_live_key

secrets:
  stripe_live_key:
    file: /var/run/rediacc/secrets/${REDIACC_NETWORK_ID}/STRIPE_LIVE_KEY
```

A referência no lado do serviço em minúsculas (`stripe_live_key`) é o nome do arquivo `/run/secrets/<name>` no contêiner; a cauda em maiúsculas do caminho do host (`STRIPE_LIVE_KEY`) coincide com o que você definiu com `--key`. `${REDIACC_NETWORK_ID}` é interpolado pelo `renet compose` automaticamente.

> **Isolamento entre repositórios executado**: o validador compose do renet rejeita caminhos `secrets: file:` (e `configs: file:`, e `env_file:`) que referenciem qualquer outro network ID de repositório. O token literal `${REDIACC_NETWORK_ID}` (ou o inteiro da sua própria rede) é a única forma aceita para referências `/var/run/rediacc/secrets/...`. E `--unsafe` NÃO sobrescreve esta verificação. A sandbox Landlock ao redor do subprocess bash do Rediaccfile também limita o acesso do sistema de arquivos apenas ao diretório de secrets da sua própria rede, então um `cat /var/run/rediacc/secrets/<other>/X` malicioso de um Rediaccfile falha com EACCES na camada do kernel.

> **Forks**: `rdc repo fork` **não** copia secrets. Para usar secrets em um fork, execute `rdc repo secret set --name <fork>` no fork explicitamente. Esta é a propriedade de segurança que sustenta a carga. Os contêineres do fork não devem ser capazes de agir como o principal de produção contra serviços externos.

> **Agentes** (Claude Code, Cursor, etc.): `repo secret list` e `repo secret get` são expostos como ferramentas MCP (read-safe: apenas nomes + digests, nunca valores). `set` e `unset` são apenas CLI porque a cerimônia `--current`/`--rotate-secret` requer olhos humanos; agentes que os chamam via shell recebem o mesmo gate que humanos. Quando a precondição falha, o envelope JSON contém um campo estruturado `errors[].next.options[].run`. Agentes devem retransmitir esses comandos verbatim para o usuário. Veja [AI agent safety](/en/docs/ai-agents-safety) para o modelo completo.

## Validar

Verifique a integridade do sistema de arquivos de um repositório:

```bash
rdc repo validate --name my-app -m server-1
```

## Propriedade

Defina a propriedade de arquivo dentro de um repositório para o usuário universal (UID 7111). Isto é tipicamente necessário após fazer upload de arquivos da sua estação de trabalho, que chegam com seu UID local.

```bash
rdc repo ownership --name my-app -m server-1
```

O comando detecta automaticamente diretórios de dados de contêiner Docker (bind mounts graváveis) e os exclui. Isto previne quebrar contêineres que gerenciam arquivos com seus próprios UIDs (ex: MariaDB=999, www-data=33).

| Opção | Descrição |
|--------|-------------|
| `--uid <uid>` | Define um UID customizado em vez de 7111 |
| `--skip-router-restart` | Pula o reinício do servidor de rota após a operação |

Para forçar propriedade em todos os arquivos, incluindo dados de contêiner:

```bash
rdc repo ownership --name my-app -m server-1
```


Veja o [Guia de Migração](/en/docs/migration) para um passo a passo completo de quando e como usar propriedade durante migração de projeto.

## Template

Aplique um template para inicializar um repositório com arquivos:

```bash
rdc repo template apply --name my-template -m server-1 -r my-app --file ./my-template.tar.gz
```

## Deletar

Destrua permanentemente um repositório e todos os dados dentro dele:

```bash
rdc repo delete --name my-app -m server-1
```

> Isto destrói permanentemente a imagem de disco criptografada. Esta ação não pode ser desfeita.

## Migrar Repositório

Migre um repositório ao vivo de uma máquina para outra. O único downtime é a fase final de delta-sync: tipicamente segundos a poucos minutos dependendo da taxa de escrita no cutover.

```bash
rdc repo migrate --name my-app --from server-1 --to server-2
```

| Opção | Descrição |
|--------|-------------|
| `--provision` | Provision o repositório na máquina de destino antes de migrar (cria imagem LUKS e registra configuração) |
| `--checkpoint` | Cria um checkpoint CRIU de contêineres em execução antes do cutover |
| `--bwlimit <kbps>` | Limita largura de banda do rsync em kilobytes por segundo |
| `--skip-dns` | Pula atualização de registros DNS após cutover |

**Fluxo de três fases:**

1. **Hot pre-copy**: rsync transfere dados enquanto o repositório fica em execução na origem. Arquivos grandes são transferidos antes de qualquer downtime.
2. **Cutover**: o repositório é parado na origem, um passe final do rsync sincroniza mudanças restantes, e o repositório inicia na máquina de destino.
3. **Start on target**: renet monta e inicia o repositório na máquina de destino. DNS é atualizado a menos que `--skip-dns` seja passado.

![Repository Live Migration](/img/repo-migrate-flow.svg)

**Push vs migrate:**

| | `repo push` | `repo migrate` |
|--|-------------|----------------|
| Operação | Cópia | Movimento |
| Origem depois | Inalterada | Parada |
| Downtime | Nenhum (apenas cópia) | Breve janela de cutover |
| Atualização DNS | Não | Sim (a menos que `--skip-dns`) |
| Caso de uso | Backup, clone de staging | Substituição de máquina, mudança de servidor |

## Prune

Depois de deletar repositórios ou recuperar de operações falhadas, diretórios de montagem órfãos, arquivos de lock e marcadores imóveis podem permanecer. Prune remove estes com segurança:

```bash
# Preview o que seria removido
rdc machine prune --name server-1 --dry-run

# Remove recursos órfãos
rdc machine prune --name server-1
```

Apenas recursos sem imagem de repositório correspondente são afetados. Diretórios de montagem não vazios nunca são removidos.
