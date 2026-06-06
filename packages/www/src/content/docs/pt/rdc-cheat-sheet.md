---
title: Folha de Consulta do CLI RDC
description: "Referência rápida para rdc: configs, repositórios, máquinas, sincronização e contentores. Conjunto completo de opções: adicione --help a qualquer comando."
category: Guides
order: 3
language: pt
sourceHash: "bc52628ba870dfbb"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# Folha de Consulta do CLI RDC

Nem todos os comandos `rdc` estão listados aqui, apenas os que surgem em todas as implementações. Para ver o conjunto completo de opções, execute qualquer comando rdc com `--help`. Casos extremos e opções raramente utilizadas estão na referência completa.

## Ciclo de Vida do Repositório

| Comando | Descrição |
|---------|-------------|
| `rdc repo create --name <repo> -m <machine>` | Criar um novo repositório numa máquina |
| `rdc repo up --name <repo> -m <machine>` | Implementar ou atualizar um repositório |
| `rdc repo down --name <repo> -m <machine>` | Parar um repositório |
| `rdc repo delete --name <repo> -m <machine>` | Eliminar um repositório |
| `rdc repo fork --parent <repo> --tag <tag> -m <machine>` | Fazer fork de um repositório (quase instantâneo, reflink BTRFS) |
| `rdc repo takeover --name <repo> -m <machine>` | Assumir a propriedade de um repositório existente |
| `rdc config repository list` | Listar todos os repositórios com nome e GUID |

## Segredos por Repositório

Credenciais de implantação apenas de escrita. `get` devolve apenas o digest. O valor nunca é devolvido. Consulte [Repositórios § Segredos](/pt/docs/repositories#secrets) para o guia completo.

| Comando | Descrição |
|---------|-------------|
| `rdc repo secret set --name <repo> --key <KEY> --value <val> [--mode env\|file] --current ""` | Criar um novo segredo (`--current ""` para a primeira escrita) |
| `rdc repo secret set --name <repo> --key <KEY> --value <val> --current <prev>` | Substituir um segredo existente (precondição estilo passwd) |
| `rdc repo secret set --name <repo> --key <KEY> --value <val> --rotate-secret` | Substituir sem verificar o valor anterior (registado como rotação) |
| `rdc repo secret list --name <repo>` | Listar nomes de segredos e modos de entrega (nunca valores, nunca digests) |
| `rdc repo secret get --name <repo> --key <KEY>` | Mostrar digest e modo do segredo (sem valor em texto simples, jamais) |
| `rdc repo secret unset --name <repo> --key <KEY> --current <prev>` | Eliminar um segredo |
| `rdc repo secret unset --name <repo> --key <KEY> --rotate-secret` | Eliminar sem verificar o valor anterior |

> Os forks não herdam segredos. Defina-os no fork explicitamente com `rdc repo secret set --name <repo>:<tag>`.

## Backup e Restauro

| Comando | Descrição |
|---------|-------------|
| `rdc repo push --name <repo> -m <machine> --to <storage>` | Enviar um backup de repositório para o armazenamento |
| `rdc repo push --to <storage> -m <machine>` | Enviar todos os repositórios para o armazenamento |
| `rdc repo pull --name <repo> -m <machine> --from <storage>` | Restaurar um repositório do armazenamento |
| `rdc repo pull --from <storage> -m <machine>` | Restaurar todos os repositórios do armazenamento |
| `rdc repo push ... --bwlimit <limit>` | Limitar a largura de banda rsync durante o envio (p. ex. `10M`) |
| `rdc repo pull ... --bwlimit <limit>` | Limitar a largura de banda rsync durante a receção |
| `rdc repo push ... --checkpoint` | Criar checkpoint dos contentores antes de enviar |
| `rdc repo backup list --from <storage> -m <machine>` | Listar backups disponíveis no armazenamento |
| `rdc storage browse --name <storage>` | Navegar pelo conteúdo do armazenamento |

## Migração de Repositório

| Comando | Descrição |
|---------|-------------|
| `rdc repo migrate --name <repo> --from <machine> --to <machine>` | Mover um repositório entre máquinas |
| `rdc repo migrate ... --provision` | Provisionar no destino antes de transferir |
| `rdc repo migrate ... --checkpoint` | Criar checkpoint antes de migrar |
| `rdc repo migrate ... --skip-dns` | Ignorar atualização de DNS após migração |
| `rdc repo migrate ... --bwlimit <limit>` | Limitar a largura de banda de transferência |

## Estratégias de Backup

| Comando | Descrição |
|---------|-------------|
| `rdc config backup-strategy set --name <name> --destination <storage> --cron <expr> --mode <hot\|cold> --enable` | Criar ou atualizar uma estratégia de backup nomeada |
| `rdc config backup-strategy list` | Listar todas as estratégias de backup definidas |
| `rdc config backup-strategy show --name <name>` | Mostrar detalhes de uma estratégia |
| `rdc config backup-strategy remove --name <name>` | Remover uma estratégia |
| `rdc machine backup schedule -m <machine>` | Implementar estratégias de backup configuradas numa máquina |

## Operações de Backup

| Comando | Descrição |
|---------|-------------|
| `rdc machine backup schedule -m <machine>` | Implementar estratégias associadas como temporizadores systemd |
| `rdc machine backup schedule -m <machine> --dry-run` | Pré-visualizar unidades de temporizador sem implementar (tokens mascarados) |
| `rdc machine backup now -m <machine>` | Executar todas as estratégias associadas imediatamente |
| `rdc machine backup now -m <machine> --strategy <name>` | Executar uma estratégia específica imediatamente |
| `rdc machine backup status -m <machine>` | Mostrar estado do temporizador e resultados de tarefas recentes |
| `rdc machine backup status -m <machine> --strategy <name>` | Mostrar estado de uma estratégia específica |
| `rdc machine backup cancel -m <machine>` | Cancelar backups em execução |
| `rdc machine backup cancel -m <machine> --strategy <name>` | Cancelar um backup específico em execução |

## Gestão de Máquinas

| Comando | Descrição |
|---------|-------------|
| `rdc machine query --name <machine>` | Estado completo da máquina (sistema, contentores, serviços, repositórios, rede) |
| `rdc machine query --name <machine> --system` | Apenas informação do sistema |
| `rdc machine query --name <machine> --containers` | Apenas lista de contentores |
| `rdc machine query --name <machine> --repositories` | Apenas lista de repositórios |
| `rdc machine query --name <machine> --services` | Apenas lista de serviços |
| `rdc machine query --name <machine> --network` | Apenas informação de rede |
| `rdc machine query --name <machine> --block-devices` | Apenas informação de dispositivos de bloco |
| `rdc machine list` | Listar todas as máquinas na config |
| `rdc config machine setup --name <machine>` | Executar o provisionamento inicial da máquina |
| `rdc machine prune --name <machine>` | Remover recursos não utilizados da máquina |
| `rdc machine deprovision --name <machine>` | Desprovicionar completamente uma máquina |
| `rdc machine vault-status --name <machine>` | Mostrar estado do cofre LUKS |

## Terminal e Sincronização

| Comando | Descrição |
|---------|-------------|
| `rdc term connect -m <machine>` | Abrir terminal SSH para a máquina |
| `rdc term connect -m <machine> -r <repo>` | Abrir terminal SSH para o repositório (define DOCKER_HOST) |
| `rdc term connect -m <machine> -c "<command>"` | Executar um comando na máquina |
| `rdc repo sync upload -m <machine> -r <repo> --local <paths...>` | Carregar um ou mais ficheiros/diretórios locais para o repositório |
| `rdc repo sync upload -m <machine> -r <repo> --local <file> --remote-file <path>` | Carregar um único ficheiro local para um caminho remoto explícito |
| `rdc repo sync download -m <machine> -r <repo> --local <dir>` | Transferir o diretório do repositório localmente |
| `rdc repo sync download -m <machine> -r <repo> --remote-file <path> --local <dir>` | Transferir um único ficheiro remoto para um diretório local |
| `rdc vscode connect -m <machine> -r <repo>` | Abrir sessão VS Code Remote SSH |

## Configuração

| Comando | Descrição |
|---------|-------------|
| `rdc config init --name <name>` | Criar um ficheiro de config nomeado |
| `rdc config machine add --name <machine> --host <host> --user <user>` | Adicionar uma máquina à config |
| `rdc config storage import --file rclone.conf` | Importar fornecedores de armazenamento da config rclone |
| `rdc config storage list` | Listar fornecedores de armazenamento configurados |
| `rdc config backup-strategy set ...` | Definir uma estratégia de backup nomeada |
| `rdc --config <name> <command>` | Usar um ficheiro de config nomeado |

## Depuração e Saída de Emergência

| Comando | Descrição |
|---------|-------------|
| `rdc term connect -m <machine> -r <repo> -c "docker ps"` | Listar contentores num repositório |
| `rdc term connect -m <machine> -r <repo> -c "docker logs <name>"` | Obter registos do contentor |
| `rdc term connect -m <machine> -r <repo> -c "docker exec <name> <cmd>"` | Executar comando num contentor |
| `rdc term connect -m <machine> -r <repo> -c "docker restart <name>"` | Reiniciar um contentor |
