---
title: "Repositórios"
description: "Crie, gerencie e opere repositórios criptografados com LUKS em máquinas remotas."
category: "Guides"
order: 4
language: pt
sourceHash: "ffb07e5870accfd8"
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

> O repositório deve estar desmontado antes de redimensionar.

## Fork

Crie uma cópia de um repositório existente em seu estado atual:

```bash
rdc repo fork --parent my-app --tag staging -m server-1
```

Forks usam o modelo name:tag: o fork resultante é nomeado `my-app:staging`. Isto cria uma nova cópia criptografada com seu próprio GUID e ID de rede, enquanto compartilha o nome do pai. O fork compartilha a mesma credencial LUKS do pai.

> Forks compartilham os dados do pai via reflink BTRFS, incluindo quaisquer credenciais armazenadas em disco. Veja [O que o Rediacc não isola](/en/docs/ai-agents-safety#what-rediacc-does-not-isolate) para as implicações quando essas credenciais autorizam serviços externos como Stripe, AWS ou Railway. Para manter credenciais de tempo de deploy fora do alcance do fork, use [per-repo secrets](#secrets) em vez de baking valores em arquivos `.env` dentro do repositório.

Na criação do fork, `repo fork` escreve o [arquivo sidecar do espelho de estado](#type-column-and-the-state-mirror) em `<datastore>/.interim/state/<fork-guid>/.rediacc.json` imediatamente. Sem desbloquear o volume. Então o novo fork é corretamente identificado como `is_fork: true` a partir do momento da criação. Isto permite que backups agendados o ignorem (forks são excluídos do pipeline de upload por padrão) mesmo que nunca seja montado. Ao fazer fork de um fork, `grand_guid` encadeia corretamente: o espelho do novo fork aponta para o GUID do avô original, não para o fork intermediário.

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
