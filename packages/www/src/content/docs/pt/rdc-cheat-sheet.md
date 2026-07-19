---
title: Folha de Consulta do CLI RDC
description: "Referência rápida para rdc: configs, repositórios, máquinas, sincronização e contentores. Conjunto completo de opções: adicione --help a qualquer comando."
category: Guides
order: 3
language: pt
sourceHash: "d92987c4766d91ae"
sourceCommit: "70a4ca883754f1c0a7f4684c9fde02a5a01d3681"
---

# Folha de Consulta do CLI RDC

Nem todos os comandos `rdc` estão listados aqui, apenas os que surgem em todas as implementações. Para ver o conjunto completo de opções, execute qualquer comando rdc com `--help`. Casos extremos e opções raramente utilizadas estão na referência completa.

## Ciclo de Vida do Repositório

| Comando | Descrição |
|---------|-------------|
| `rdc repo create <repo> -m <machine>` | Criar um novo repositório numa máquina |
| `rdc repo up <repo>@<machine>` | Implementar ou atualizar um repositório |
| `rdc repo down <repo>@<machine>` | Parar um repositório |
| `rdc repo delete <repo>@<machine>` | Eliminar um repositório |
| `rdc repo fork <repo>@<machine> --tag <tag>` | Fazer fork de um repositório (quase instantâneo, reflink BTRFS) |
| `rdc repo promote <repo>:<tag>` | Promover um fork validado a produção com o nome do repositório original |
| `rdc repo list` | Listar todos os repositórios com nome e GUID |

## Segredos por Repositório

Credenciais de implantação apenas de escrita. `get` devolve apenas o digest. O valor nunca é devolvido. Consulte [Repositórios § Segredos](/pt/docs/repositories#secrets) para o guia completo.

| Comando | Descrição |
|---------|-------------|
| `rdc repo secret set <repo> --key <KEY> --value <val> [--mode env\|file] --current ""` | Criar um novo segredo (`--current ""` para a primeira escrita) |
| `rdc repo secret set <repo> --key <KEY> --value <val> --current <prev>` | Substituir um segredo existente (precondição estilo passwd) |
| `rdc repo secret set <repo> --key <KEY> --value <val> --rotate-secret` | Substituir sem verificar o valor anterior (registado como rotação) |
| `rdc repo secret list <repo>` | Listar nomes de segredos e modos de entrega (nunca valores, nunca digests) |
| `rdc repo secret get <repo> --key <KEY>` | Mostrar digest e modo do segredo (sem valor em texto simples, jamais) |
| `rdc repo secret unset <repo> --key <KEY> --current <prev>` | Eliminar um segredo |
| `rdc repo secret unset <repo> --key <KEY> --rotate-secret` | Eliminar sem verificar o valor anterior |

> Os forks não herdam segredos. Defina-os no fork explicitamente com `rdc repo secret set <repo>:<tag>`.

## Backup e Restauro

| Comando | Descrição |
|---------|-------------|
| `rdc repo push <repo>@<machine> --to <storage>` | Enviar um backup de repositório para o armazenamento |
| `rdc repo pull <repo>@<machine> --from <storage>` | Restaurar um repositório do armazenamento |
| `rdc repo push ... --bwlimit <limit>` | Limitar a largura de banda rsync durante o envio (p. ex. `10M`) |
| `rdc repo pull ... --bwlimit <limit>` | Limitar a largura de banda rsync durante a receção |
| `rdc repo push ... --checkpoint` | Criar checkpoint dos contentores antes de enviar |
| `rdc backup list --storage <storage> | Listar backups disponíveis no armazenamento |
| `rdc storage browse <storage>` | Navegar pelo conteúdo do armazenamento |

## Migração de Repositório

| Comando | Descrição |
|---------|-------------|
| `rdc repo migrate <repo>@<machine> --to <machine>` | Mover um repositório entre máquinas |
| `rdc repo migrate ... --provision` | Provisionar no destino antes de transferir |
| `rdc repo migrate ... --checkpoint` | Criar checkpoint antes de migrar |
| `rdc repo migrate ... --skip-dns` | Ignorar atualização de DNS após migração |
| `rdc repo migrate ... --bwlimit <limit>` | Limitar a largura de banda de transferência |

## Estratégias de Backup

| Comando | Descrição |
|---------|-------------|
| `rdc backup strategy set <name> --destination <storage> --cron <expr> --mode <hot\|cold> --enable` | Criar ou atualizar uma estratégia de backup nomeada |
| `rdc backup strategy list` | Listar todas as estratégias de backup definidas |
| `rdc backup strategy show <name>` | Mostrar detalhes de uma estratégia |
| `rdc backup strategy remove <name>` | Remover uma estratégia |
| `rdc backup schedule -m <machine>` | Implementar estratégias de backup configuradas numa máquina |

## Operações de Backup

| Comando | Descrição |
|---------|-------------|
| `rdc backup schedule -m <machine>` | Implementar estratégias associadas como temporizadores systemd |
| `rdc backup schedule -m <machine> --dry-run` | Pré-visualizar unidades de temporizador sem implementar (tokens mascarados) |
| `rdc backup run -m <machine>` | Executar todas as estratégias associadas imediatamente |
| `rdc backup run <name> -m <machine>` | Executar uma estratégia específica imediatamente |
| `rdc backup status -m <machine>` | Mostrar estado do temporizador e resultados de tarefas recentes |
| `rdc backup status <name> -m <machine>` | Mostrar estado de uma estratégia específica |
| `rdc backup cancel -m <machine>` | Cancelar backups em execução |
| `rdc backup cancel <name> -m <machine>` | Cancelar um backup específico em execução |

## Gestão de Máquinas

| Comando | Descrição |
|---------|-------------|
| `rdc machine status <machine>` | Estado completo da máquina (sistema, contentores, serviços, repositórios, rede) |
| `rdc machine status <machine> --system` | Apenas informação do sistema |
| `rdc machine status <machine> --containers` | Apenas lista de contentores |
| `rdc machine status <machine> --repositories` | Apenas lista de repositórios |
| `rdc machine status <machine> --services` | Apenas lista de serviços |
| `rdc machine status <machine> --network` | Apenas informação de rede |
| `rdc machine status <machine> --block-devices` | Apenas informação de dispositivos de bloco |
| `rdc machine list` | Listar todas as máquinas na config |
| `rdc machine setup <machine>` | Executar o provisionamento inicial da máquina |
| `rdc machine prune <machine>` | Remover recursos não utilizados da máquina |
| `rdc machine deprovision <machine>` | Desprovicionar completamente uma máquina |

## Terminal e Sincronização

| Comando | Descrição |
|---------|-------------|
| `rdc term connect <machine>` | Abrir terminal SSH para a máquina |
| `rdc term connect <repo>@<machine>` | Abrir terminal SSH para o repositório (define DOCKER_HOST) |
| `rdc term connect <machine> -c "<command>"` | Executar um comando na máquina |
| `rdc repo sync upload <repo>@<machine> --local <paths...>` | Carregar um ou mais ficheiros/diretórios locais para o repositório |
| `rdc repo sync upload <repo>@<machine> --local <file> --remote-file <path>` | Carregar um único ficheiro local para um caminho remoto explícito |
| `rdc repo sync download <repo>@<machine> --local <dir>` | Transferir o diretório do repositório localmente |
| `rdc repo sync download <repo>@<machine> --remote-file <path> --local <dir>` | Transferir um único ficheiro remoto para um diretório local |
| `rdc vscode connect <repo>@<machine>` | Abrir sessão VS Code Remote SSH |

## Configuração

| Comando | Descrição |
|---------|-------------|
| `rdc config init <name>` | Criar um ficheiro de config nomeado |
| `rdc machine add <machine> --ip <host> --user <user>` | Adicionar uma máquina à config |
| `rdc storage import rclone.conf` | Importar fornecedores de armazenamento da config rclone |
| `rdc storage list` | Listar fornecedores de armazenamento configurados |
| `rdc backup strategy set ...` | Definir uma estratégia de backup nomeada |
| `rdc --config <name> <command>` | Usar um ficheiro de config nomeado |

## Depuração e Saída de Emergência

| Comando | Descrição |
|---------|-------------|
| `rdc term connect <repo>@<machine> -c "docker ps"` | Listar contentores num repositório |
| `rdc term connect <repo>@<machine> -c "docker logs <name>"` | Obter registos do contentor |
| `rdc term connect <repo>@<machine> -c "docker exec <name> <cmd>"` | Executar comando num contentor |
| `rdc term connect <repo>@<machine> -c "docker restart <name>"` | Reiniciar um contentor |
