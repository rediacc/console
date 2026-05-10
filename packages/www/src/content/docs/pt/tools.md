---
title: "Ferramentas"
description: "Sincronização de ficheiros, acesso por terminal, integração com VS Code e atualizações do CLI."
category: "Guides"
order: 9
language: pt
---

# Ferramentas

O Rediacc inclui ferramentas de produtividade para trabalhar com repositórios remotos: sincronização de ficheiros, terminal SSH, integração com VS Code e atualizações do CLI.

## Sincronização de Ficheiros (sync)

Transfira ficheiros entre a sua estação de trabalho e um repositório remoto via rsync sobre SSH.

### Enviar Ficheiros

`--local` aceita um ou mais caminhos. Cada caminho pode ser um ficheiro ou um diretório. Os ficheiros ficam em `<remoto>/<basename>`; o conteúdo de diretórios é fundido em `<remoto>/`. Para um único ficheiro, prefira `--remote-file` para indicar explicitamente o caminho de destino.

```bash
# Diretório (conteúdo fundido no remoto)
rdc repo sync upload -m server-1 -r my-app --local ./src --remote /app/src

# Ficheiro único colocado num diretório remoto (basename preservado)
rdc repo sync upload -m server-1 -r my-app --local ./config.yml --remote /app/conf

# Ficheiro único com caminho de destino explícito
rdc repo sync upload -m server-1 -r my-app --local ./config.yml --remote-file /app/conf/config.yml

# Várias origens numa só chamada
rdc repo sync upload -m server-1 -r my-app --local a.yml b.yml ./assets --remote /app
```

`--remote` e `--remote-file` são mutuamente exclusivos. `--remote-file` exige exatamente um caminho `--local` que aponte para um ficheiro.

`--mirror` não pode ser combinado com uma origem de ficheiro; eliminaria ficheiros adjacentes no diretório remoto.

### Descarregar Ficheiros

Use `--remote` para um diretório (predefinição atual) ou `--remote-file` para um único ficheiro. Os dois sinalizadores são mutuamente exclusivos.

```bash
# Diretório
rdc repo sync download -m server-1 -r my-app --remote /app/data --local ./data

# Ficheiro único -- --local deve ser um diretório existente
rdc repo sync download -m server-1 -r my-app --remote-file /app/conf/config.yml --local ./local-conf
```

### Verificar Estado da Sincronização

```bash
rdc repo sync status -m server-1 -r my-app
```

### Opções

| Opção | Descrição |
|-------|-----------|
| `-m, --machine <name>` | Máquina de destino |
| `-r, --repository <name>` | Repositório de destino |
| `--local <paths...>` | Um ou mais caminhos locais de ficheiro ou diretório (upload) ou diretório de destino local (download) |
| `--remote <path>` | Diretório remoto (relativo ao mount do repositório) |
| `--remote-file <path>` | Caminho de ficheiro remoto para uploads ou downloads de ficheiro único (alternativa a `--remote`) |
| `--dry-run` | Pré-visualizar alterações sem transferir |
| `--mirror` | Espelhar origem no destino, eliminando ficheiros extra (apenas origens de diretório) |
| `--verify` | Verificar checksums após a transferência |
| `--confirm` | Confirmação interativa com vista de detalhe |
| `--exclude <patterns...>` | Excluir padrões de ficheiros |
| `--skip-router-restart` | Ignorar o reinício do servidor de rotas após a operação |

## Terminal SSH (term)

Abra uma sessão SSH interativa numa máquina ou no ambiente de um repositório.

### Sintaxe Abreviada

A forma mais rápida de se ligar:

```bash
rdc term connect -m server-1                    # Ligar a uma máquina
rdc term connect -m server-1 -r my-app             # Ligar a um repositório
```

### Executar um Comando

Execute um comando sem abrir uma sessão interativa:

```bash
rdc term connect -m server-1 -c "uptime"
rdc term connect -m server-1 -r my-app -c "docker ps"
```

Ao ligar a um repositório, `DOCKER_HOST` é definido automaticamente para o socket Docker isolado do repositório, pelo que `docker ps` mostra apenas os contentores desse repositório.

### Subcomando Connect

O subcomando `connect` oferece a mesma funcionalidade com sinalizadores explícitos:

```bash
rdc term connect -m server-1
rdc term connect -m server-1 -r my-app
```

### Ações em Contentores

Interaja diretamente com um contentor em execução:

```bash
# Abrir uma shell dentro de um contentor
rdc term connect -m server-1 -r my-app --container <container-id>

# Ver logs do contentor
rdc term connect -m server-1 -r my-app --container <container-id> --container-action logs

# Seguir logs em tempo real
rdc term connect -m server-1 -r my-app --container <container-id> --container-action logs --follow

# Ver estatísticas do contentor
rdc term connect -m server-1 -r my-app --container <container-id> --container-action stats

# Executar um comando num contentor
rdc term connect -m server-1 -r my-app --container <container-id> --container-action exec -c "ls -la"
```

| Opção | Descrição |
|-------|-----------|
| `--container <id>` | ID do contentor Docker de destino |
| `--container-action <action>` | Ação: `terminal` (predefinição), `logs`, `stats`, `exec` |
| `--log-lines <n>` | Número de linhas de log a mostrar (predefinição: 50) |
| `--follow` | Seguir logs continuamente |
| `--external` | Usar terminal externo em vez de SSH inline |

## Integração com VS Code (vscode)

Abra uma sessão SSH remota no VS Code, pré-configurada com as definições SSH corretas.

### Ligar a um Repositório

```bash
rdc vscode connect -r my-app -m server-1
```

Este comando:
1. Deteta a sua instalação do VS Code
2. Configura a ligação SSH em `~/.ssh/config`
3. Mantém a chave SSH para a sessão
4. Abre o VS Code com uma ligação Remote SSH ao caminho do repositório

### Listar Ligações Configuradas

```bash
rdc vscode list
```

### Limpar Ligações

```bash
rdc vscode cleanup
```

Remove as configurações SSH do VS Code que já não são necessárias.

### Verificar Configuração

```bash
rdc vscode check
```

Verifica a instalação do VS Code, a extensão Remote SSH e as ligações ativas.

> **Pré-requisito:** Instale a extensão [Remote - SSH](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-ssh) no VS Code.

## Atualizações do CLI (update)

Mantenha o CLI `rdc` atualizado.

### Verificar Atualizações

```bash
rdc update --check-only
```

### Aplicar Atualização

```bash
rdc update
```

As atualizações são descarregadas e aplicadas no local. O CLI escolhe automaticamente o binário correto para a sua plataforma (Linux, macOS ou Windows). A nova versão entra em vigor na próxima execução.

### Reverter

```bash
rdc update --rollback
```

Reverte para a versão anteriormente instalada. Disponível apenas após uma atualização ter sido aplicada.

### Estado das Atualizações

```bash
rdc update --status
```

Mostra a versão atual, o canal de atualização e a configuração de atualização automática.

#### Canais de Lançamento

```bash
rdc update --channel edge      # Atualizações de produção com entrega contínua
rdc update --channel stable    # Promovido do edge após 7 dias de estabilização (predefinição)
rdc update --status            # Mostrar canal atual e informação de versão
```
