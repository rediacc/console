---
title: "Monitorização"
description: "Monitorize o estado da máquina, contentores, serviços, repositórios e execute diagnósticos."
category: "Guides"
order: 9
language: pt
sourceHash: "2289d50dac21f9bf"
sourceCommit: "43aec6b89a55f69f994476d3a124e749d4d2223f"
---

# Monitorização

O Rediacc fornece comandos de monitorização integrados para inspecionar o estado da máquina, contentores em execução, serviços, estado do repositório e diagnósticos do sistema.

## Estado da Máquina

Obter um relatório de estado completo para uma máquina:

```bash
rdc machine health --name server-1
```

Isto reporta:
- **Sistema**: tempo de atividade, uso do disco, uso do datastore
- **Contentores**: contagens de em execução, saudáveis, não saudáveis
- **Armazenamento**: estado de saúde SMART
- **Problemas**: problemas identificados

Use `--output json` para saída legível por máquina.

## Listar Contentores

Ver todos os contentores em execução em todos os repositórios numa máquina:

```bash
rdc machine containers --name server-1
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
rdc machine services --name server-1
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
rdc machine repos --name server-1
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
rdc machine query --name server-1 --storage-health
```

| Coluna | Descrição |
|--------|-------------|
| Size | Tamanho do ficheiro de imagem LUKS (como o repositório aparenta ser) |
| Unique | Dados únicos reais pertencentes apenas a este repositório |
| Shared | Blocos de dados reutilizados entre repositórios via reflinks BTRFS (cópias gratuitas) |
| Divergence | Percentagem da imagem única deste repositório em vez de partilhada (maior = mais recuperável se eliminado) |
| Extents | Número de extents de ficheiro na imagem copy-on-write (maior = mais fragmentado) |
| Frag | Nível de fragmentação: baixo, moderado ou alto (apenas informativo) |

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

O resultado do último scrub é guardado fora do volume BTRFS (em `/var/lib/rediacc/scrub-last-result.json`) para que permaneça legível mesmo que o volume tenha problemas. A saída de `rdc machine query --system` inclui um campo `scrub_status`:

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
rdc term connect -m server-1 -c "sudo renet maintenance scrub --datastore /mnt/rediacc"
```

O resultado é guardado no mesmo ficheiro JSON e fica imediatamente visível no próximo `rdc machine query --system`.

## Estado do Vault

Obter uma visão geral completa de uma máquina incluindo informações de implementação:

```bash
rdc machine vault-status --name server-1
```

Isto fornece:
- Hostname e tempo de atividade
- Uso de memória, disco e datastore
- Total de repositórios, contagem de montados, contagem de Docker em execução
- Informações detalhadas por repositório

Use `--output json` para saída legível por máquina.

## Testar Conexão

> **Apenas para adaptador cloud.** Com o adaptador local, use `rdc term connect -m server-1 -c "hostname"` para verificar a conectividade.

Verificar a conectividade SSH a uma máquina:

```bash
rdc machine test-connection --ip 203.0.113.50 --user deploy
```

Reporta:
- Estado da conexão (sucesso/falhado)
- Método de autenticação usado
- Configuração da chave SSH
- Estado de implementação da chave pública
- Entrada de hosts conhecidos

Opções:
- `--port <number>`, Porta SSH (predefinição: 22)
- `--save -m server-1`, Guardar a chave de host verificada na configuração da máquina

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
