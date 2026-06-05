---
title: "Repositórios"
description: "Criar, gerir e operar repositórios encriptados com LUKS em máquinas remotas."
category: "Guides"
order: 4
language: pt
sourceHash: "ffb07e5870accfd8"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# Repositórios

Um **repositório** é uma imagem de disco encriptada com LUKS num servidor remoto. Quando montado, fornece:
- Um sistema de ficheiros isolado para os dados da sua aplicação
- Um daemon Docker dedicado (separado do Docker do anfitrião)
- IPs de loopback únicos para cada serviço numa sub-rede /26

## Criar um Repositório

```bash
rdc repo create --name my-app -m server-1 --size 10G
```

| Opção | Obrigatório | Descrição |
|--------|----------|-------------|
| `-m, --machine <name>` | Sim | Máquina de destino onde o repositório será criado |
| `--size <size>` | Sim | Tamanho da imagem de disco encriptada (ex., `5G`, `10G`, `50G`) |
| `--skip-router-restart` | Não | Ignorar reinício do servidor de encaminhamento após a operação |

A saída mostrará três valores gerados automaticamente:

- **GUID do Repositório** — Um UUID que identifica a imagem de disco encriptada no servidor.
- **Credencial** — Uma frase-passe aleatória usada para encriptar/desencriptar o volume LUKS.
- **ID de Rede** — Um inteiro (começando em 2816, incrementando em 64) que determina a sub-rede IP para os serviços deste repositório.

> **Guarde a credencial de forma segura.** É a chave de encriptação do seu repositório. Se perdida, os dados não podem ser recuperados. A credencial é armazenada no seu ficheiro `config.json` local, mas não é armazenada no servidor.

## Montar e Desmontar

Montar desencripta e torna o sistema de ficheiros do repositório acessível. Desmontar fecha o volume encriptado.

```bash
rdc repo mount --name my-app -m server-1  # Desencriptar e montar
rdc repo unmount --name my-app -m server-1  # Desmontar e re-encriptar
```

| Opção | Descrição |
|--------|-------------|
| `--checkpoint` | Criar um ponto de verificação CRIU antes de montar/desmontar (para contentores com etiqueta `rediacc.checkpoint=true`) |
| `--skip-router-restart` | Ignorar reinício do servidor de encaminhamento após a operação |

## Verificar Estado

```bash
rdc repo status --name my-app -m server-1
```

## Listar Repositórios

```bash
rdc repo list -m server-1
```

### Coluna Tipo e o espelho de estado

A tabela de saída inclui uma coluna `Type` com três valores:

- **`grand`**. Um repositório de nível superior registado na sua configuração de CLI local sem um repositório-pai. O caso base.
- **`fork`**. Um fork copy-on-write de outro repositório. Identificado via `grandGuid` na configuração local **ou** via o espelho renet `.interim/state` na máquina. Qualquer uma das fontes é autoritária; ambas devem concordar uma vez que o espelho esteja preenchido.
- **`unknown`**. Nenhum sinal consegue classificar o repositório. Frequentemente um fork legacy pré-espelho (criado antes do código do espelho ser enviado e nunca remontado desde então), ou um `grand` obsoleto cuja entrada de configuração local foi eliminada por engano. A CLI recusa-se a adivinhar; o operador deve executar o [preenchimento do espelho](/pt/docs/pruning#migration-state-mirror-backfill) ou remover o diretório se for genuinamente órfão.

O espelho `.interim/state/<guid>/.rediacc.json` é um pequeno ficheiro sidecar escrito **fora** do volume encriptado com LUKS para que as ferramentas de backup e `repo list` possam ler a linhagem de forks sem desbloquear cada imagem. Tem a mesma forma que o `.rediacc.json` no volume (`is_fork`, `grand_guid`, `name`, etc.) e é actualizado cada vez que `Repository.SaveState`. Ou seja, cada montagem e cada mutação de estado. É a fonte da verdade para detecção de fork em backups programados: um fork desmontado com um espelho que diz `is_fork: true` é correctamente ignorado de uploading de `cold` e `hot`.

Para limpeza rotineira de entradas desconhecidas, veja [`rdc machine prune --prune-unknown`](/pt/docs/pruning#phase-3---prune-unknown-surgical).

## Redimensionar

Defina o repositório para um tamanho exacto ou expanda por uma quantidade determinada:

```bash
rdc repo resize --name my-app -m server-1 --size 20G  # Definir tamanho exacto
rdc repo expand --name my-app -m server-1 --size 5G  # Adicionar 5G ao tamanho actual
```

> O repositório deve estar desmontado antes de redimensionar.

## Fork

Crie uma cópia de um repositório existente no seu estado actual:

```bash
rdc repo fork --parent my-app --tag staging -m server-1
```

Forks usam o modelo nome:tag: o fork resultante é nomeado `my-app:staging`. Isto cria uma nova cópia encriptada com o seu próprio GUID e ID de rede, enquanto partilha o nome do repositório-pai. O fork partilha a mesma credencial LUKS que o repositório-pai.

> Os forks partilham os dados do repositório-pai via reflink BTRFS, incluindo quaisquer credenciais armazenadas em disco. Veja [O que o Rediacc não isola](/pt/docs/ai-agents-safety#what-rediacc-does-not-isolate) para as implicações quando essas credenciais autorizam serviços externos como Stripe, AWS ou Railway. Para manter credenciais de tempo de implantação fora do alcance do fork, use [secrets por repositório](#secrets) em vez de integrar valores em ficheiros `.env` dentro do repositório.

Na criação do fork, `repo fork` escreve o [sidecar do espelho de estado](#type-column-and-the-state-mirror) em `<datastore>/.interim/state/<fork-guid>/.rediacc.json` imediatamente. Sem desbloquear o volume. Para que o novo fork seja correctamente identificado como `is_fork: true` desde o momento da criação. Isto permite que backups programados o ignorem (forks são excluídos do pipeline de upload por predefinição) mesmo que nunca seja montado. Ao fazer fork de um fork, `grand_guid` encadeia correctamente: o espelho do novo fork aponta para o GUID do repositório-pai original, não para o fork intermédio.

## Versionamento semelhante ao git

Forks podem funcionar como commits git. `rdc repo commit` congela um fork de trabalho num commit imutável e byte-estável; `rdc repo branch` nomeia uma linha de histórico; `rdc repo checkout` clona um commit via reflink de volta num fork gravável; `rdc repo log` percorre a cadeia de pais; e `rdc repo merge` combina duas linhas sem modificar um repositório em produção no local. `rdc repo fork --immutable` produz uma base equivalente a um commit num único passo.

```bash
rdc repo commit --name my-app:work --message "schema migration applied" -m server-1
rdc repo branch --branch staging --name my-app:work
rdc repo checkout --ref staging --from my-app:work --tag staging-copy -m server-1
```

Veja a [referência de ramificação semelhante ao git](/pt/docs/repo-branching) para o conjunto completo de comandos, opções e exemplos práticos.

## Secrets

Secrets por repositório são credenciais de tempo de implantação injectadas em contentores sem serem escritas na imagem encriptada do repositório. São mantidas num plano separado dos dados do repositório, para que `rdc repo fork` não as propague. Um fork começa com um mapa de secrets vazio e os seus contentores inicializam identificando-se como um principal externo diferente do repositório-pai.

> Quer um passeio passo a passo? Veja o [tutorial Gerir Secrets](/pt/docs/tutorial-managing-secrets) para o ciclo completo de set/list/deploy/verify/rotate.

**Modelo só-escrita (estilo GitHub):** `get` retorna apenas o resumo SHA-256. O valor em texto simples nunca é retornado a ninguém, humano ou agente. Se esquecer qual é um valor, procure-o no seu gestor de palavras-passe e rode-o; não pode ler-o novamente do Rediacc por design. Isto elimina uma classe inteira de fugas: gravações de terminal, histórico de shell, redirecionamento acidental, ombro-surfing.

Dois modos de entrega:

- `env`. O secret é exportado como `REDIACC_SECRET_<KEY>` no shell renet na máquina de destino. Referencie-o do seu `docker-compose.yml` via interpolação `${REDIACC_SECRET_<KEY>}`. Visível dentro do ambiente do contentor, portanto use isto para valores em forma de cadeia de ligação que a aplicação já espera em env.
- `file`. O secret é escrito em `/var/run/rediacc/secrets/<networkID>/<KEY>` no anfitrião (tmpfs, nunca persistido). Referencie-o do seu ficheiro compose via uma declaração `secrets:` de nível superior com fonte `file:`, mais uma lista `secrets:` por serviço. Os contentores leem em `/run/secrets/<key>`. Prefira este modo para qualquer coisa sensível. Nunca aparece em `docker inspect` ou `/proc/<pid>/environ`.

```bash
# Set, list, get (digest only), unset
rdc repo secret set --name my-app --key STRIPE_LIVE_KEY --value sk_live_xxx --mode file --current ""
rdc repo secret set --name my-app --key DB_HOST         --value postgres.internal --mode env --current ""
rdc repo secret list --name my-app
rdc repo secret get  --name my-app --key DB_HOST    # → { key, mode, digest } — no value
rdc repo secret unset --name my-app --key STRIPE_LIVE_KEY --current sk_live_xxx
```

**Porta de mutação simétrica.** Tanto humanos como agentes precisam de `--current <previous-value>` para sobrescrever ou desactivar um secret (pré-condição estilo passwd). Para primeira escrita de uma chave nova, passe `--current ""` (vazio). Para rodar sem verificar o valor anterior, passe `--rotate-secret` em vez disso. Isto é auditado em voz alta como uma rotação. `--current` e `--rotate-secret` são mutuamente exclusivos.

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

A referência no lado do serviço em minúsculas (`stripe_live_key`) é o nome de ficheiro `/run/secrets/<name>` no contentor; a cauda em maiúsculas do caminho do anfitrião (`STRIPE_LIVE_KEY`) corresponde ao que definiu com `--key`. `${REDIACC_NETWORK_ID}` é interpolado pelo `renet compose` automaticamente.

> **Isolamento entre repositórios forçado**: o validador compose renet rejeita caminhos `secrets: file:` (e `configs: file:`, e `env_file:`) que referenciem qualquer ID de rede de outro repositório. O token literal `${REDIACC_NETWORK_ID}` (ou o inteiro da sua rede) é a única forma aceite para referências `/var/run/rediacc/secrets/...`. E `--unsafe` NÃO substitui esta verificação. O sandbox Landlock em torno do subprocesso bash Rediaccfile também limita o acesso de sistema de ficheiros apenas ao directório de secrets da sua própria rede, para que um malicioso `cat /var/run/rediacc/secrets/<other>/X` de um Rediaccfile falhe com EACCES na camada kernel.

> **Forks**: `rdc repo fork` **não** copia secrets. Para usar secrets num fork, execute `rdc repo secret set --name <fork>` no fork explicitamente. Esta é a propriedade de segurança crítica. Os contentores do fork não devem conseguir actuar como o principal de produção contra serviços externos.

> **Agentes** (Claude Code, Cursor, etc.): `repo secret list` e `repo secret get` são expostos como ferramentas MCP (leitura-segura. Apenas nomes + resumos, nunca valores). `set` e `unset` são apenas CLI porque a cerimónia `--current`/`--rotate-secret` requer supervisão humana; agentes que os chamam via shell obtêm a mesma porta que humanos. Quando a pré-condição falha, o envelope JSON contém um campo estruturado `errors[].next.options[].run`. Os agentes devem retransmitir esses comandos verbatim ao utilizador. Veja [segurança de agentes IA](/pt/docs/ai-agents-safety) para o modelo completo.

## Validar

Verifique a integridade do sistema de ficheiros de um repositório:

```bash
rdc repo validate --name my-app -m server-1
```

## Propriedade

Defina a propriedade de ficheiro dentro de um repositório para o utilizador universal (UID 7111). Isto é normalmente necessário após fazer upload de ficheiros da sua estação de trabalho, que chegam com o seu UID local.

```bash
rdc repo ownership --name my-app -m server-1
```

O comando detecta automaticamente diretórios de dados de contentores Docker (bind mounts graváveis) e exclui-os. Isto previne quebrar contentores que gerem ficheiros com seus próprios UIDs (ex., MariaDB=999, www-data=33).

| Opção | Descrição |
|--------|-------------|
| `--uid <uid>` | Definir um UID customizado em vez de 7111 |
| `--skip-router-restart` | Ignorar reinício do servidor de encaminhamento após a operação |

Para forçar propriedade em todos os ficheiros, incluindo dados de contentor:

```bash
rdc repo ownership --name my-app -m server-1
```


Veja o [Guia de Migração](/pt/docs/migration) para um passeio completo de quando e como usar propriedade durante migração de projecto.

## Template

Aplique um template para inicializar um repositório com ficheiros:

```bash
rdc repo template apply --name my-template -m server-1 -r my-app --file ./my-template.tar.gz
```

## Eliminar

Destrua permanentemente um repositório e todos os dados dentro dele:

```bash
rdc repo delete --name my-app -m server-1
```

> Isto destrói permanentemente a imagem de disco encriptada. Esta acção não pode ser desfeita.

## Migrar Repositório

Migre um repositório ao vivo de uma máquina para outra. O único tempo de inactividade é a fase de sincronização delta final: tipicamente segundos a alguns minutos dependendo da taxa de escrita no corte.

```bash
rdc repo migrate --name my-app --from server-1 --to server-2
```

| Opção | Descrição |
|--------|-------------|
| `--provision` | Provisionar o repositório na máquina de destino antes de migrar (cria imagem LUKS e registra configuração) |
| `--checkpoint` | Criar um ponto de verificação CRIU de contentores em execução antes do corte |
| `--bwlimit <kbps>` | Limitar largura de banda rsync em kilobytes por segundo |
| `--skip-dns` | Ignorar actualizar registos DNS após o corte |

**Fluxo de três fases:**

1. **Pré-cópia quente** - rsync transfere dados enquanto o repositório permanece em execução na origem. Ficheiros grandes são transferidos antes de qualquer tempo de inactividade.
2. **Corte** - o repositório é parado na origem, um passe rsync final sincroniza mudanças remanescentes, e o repositório inicia na máquina de destino.
3. **Iniciar no destino** - renet monta e inicia o repositório na máquina de destino. DNS é actualizado a menos que `--skip-dns` seja passado.

![Repository Live Migration](/img/repo-migrate-flow.svg)

**Push vs migrate:**

| | `repo push` | `repo migrate` |
|--|-------------|----------------|
| Operação | Copiar | Mover |
| Origem após | Inalterada | Parada |
| Tempo de inactividade | Nenhum (apenas cópia) | Breve janela de corte |
| Actualização DNS | Não | Sim (a menos que `--skip-dns`) |
| Caso de uso | Backup, clone de staging | Substituição de máquina, mudança de servidor |

## Limpar

Após eliminar repositórios ou recuperar de operações falhadas, directórios de montagem órfãos, ficheiros de bloqueio e marcadores imóveis podem permanecer. Limpar remove estes com segurança:

```bash
# Visualizar pré-avaliação o que seria removido
rdc machine prune --name server-1 --dry-run

# Remover recursos órfãos
rdc machine prune --name server-1
```

Apenas recursos sem imagem de repositório correspondente são afectados. Directórios de montagem não-vazios nunca são removidos.
