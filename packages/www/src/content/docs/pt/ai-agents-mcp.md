---
title: Configuração do Servidor MCP
description: Ligue agentes de IA à infraestrutura Rediacc usando o servidor Model Context Protocol (MCP).
category: Guides
order: 33
language: pt
sourceHash: "ce5f1392ebaa380b"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

## Visão Geral

O comando `rdc mcp serve` inicia um servidor MCP (Model Context Protocol) local que os agentes de IA podem usar para gerir a sua infraestrutura. O servidor usa transporte stdio; o agente de IA lança-o como subprocesso e comunica via JSON-RPC.

**Pré-requisitos:** `rdc` instalado e configurado com pelo menos uma máquina.

## Claude Code

Adicione ao ficheiro `.mcp.json` do seu projeto:

```json
{
  "mcpServers": {
    "rdc": {
      "command": "rdc",
      "args": ["mcp", "serve"]
    }
  }
}
```

Ou com uma configuração com nome:

```json
{
  "mcpServers": {
    "rdc": {
      "command": "rdc",
      "args": ["mcp", "serve", "--config", "production"]
    }
  }
}
```

## Cursor

Abra Definições -> Servidores MCP -> Adicionar Servidor:

- **Nome**: `rdc`
- **Comando**: `rdc mcp serve`
- **Transporte**: stdio

## Ferramentas Disponíveis

### Ferramentas de Leitura (seguras, sem efeitos secundários)

| Ferramenta | Descrição |
|------------|-----------|
| `machine_query` | Obter informação do sistema, contentores, serviços e uso de recursos de uma máquina |
| `machine_containers` | Listar contentores Docker com estado, saúde, uso de recursos, labels e domínio de rota automática |
| `machine_services` | Listar serviços systemd geridos pelo rediacc (nome, estado, sub-estado, contagem de reinícios, memória, repositório proprietário) |
| `machine_repos` | Listar repositórios implementados (nome, GUID, tamanho, estado de montagem, estado Docker, contagem de contentores, uso de disco, data de modificação, Rediaccfile presente) |
| `machine_health` | Executar verificação de saúde numa máquina (sistema, contentores, serviços, armazenamento) |
| `machine_list` | Listar todas as máquinas configuradas |
| `config_repositories` | Listar repositórios configurados com mapeamentos nome-para-GUID |
| `config_show_infra` | Mostrar configuração de infraestrutura para uma máquina (domínio base, IPs públicos, TLS, zona Cloudflare) |
| `config_providers` | Listar fornecedores de nuvem configurados para aprovisionamento de máquinas |
| `agent_capabilities` | Listar todos os comandos CLI rdc disponíveis com os seus argumentos e opções |
| `repo_secret_list` | Listar nomes de segredos + modos de entrega para um repositório (nunca valores, nunca digests). Seguro para leitura. |
| `repo_secret_get` | Obter o digest SHA-256 de um segredo + modo de entrega. O valor em texto simples nunca é devolvido por design. Use para verificar se um segredo existe ou foi rodado. |

### Ferramentas de Escrita (destrutivas)

| Ferramenta | Descrição |
|------------|-----------|
| `repo_create` | Criar um novo repositório encriptado numa máquina |
| `repo_up` | Implementar/atualizar um repositório (executa Rediaccfile up, inicia contentores). Use `mount` para primeira implementação ou após pull |
| `repo_down` | Parar contentores do repositório. Por omissão, NÃO desmonta. Use `unmount` para também fechar o contentor LUKS |
| `repo_delete` | Eliminar um repositório (destrói contentores, volumes, imagem encriptada). Credencial arquivada para recuperação |
| `repo_fork` | Criar um fork CoW com novo GUID e networkId (cópia totalmente independente, forking online suportado) |
| `backup_push` | Enviar cópia de segurança do repositório para armazenamento ou outra máquina (mesmo GUID -- cópia de segurança/migração, não fork) |
| `backup_pull` | Receber cópia de segurança do repositório de armazenamento ou máquina. Após pull, implementar com `repo_up` (mount=true) |
| `machine_provision` | Aprovisionar uma nova máquina num fornecedor de nuvem usando OpenTofu |
| `machine_deprovision` | Destruir uma máquina aprovisionada na nuvem e remover da configuração |
| `config_add_provider` | Adicionar uma configuração de fornecedor de nuvem para aprovisionamento de máquinas |
| `config_remove_provider` | Remover uma configuração de fornecedor de nuvem |
| `term_exec` | Executar um comando numa máquina remota via SSH |

## Exemplos de Fluxos de Trabalho

**Verificar estado da máquina:**
> "Qual é o estado da minha máquina de produção?"

O agente chama `machine_query` -> devolve informação do sistema, contentores em execução, serviços e uso de recursos.

**Implementar uma aplicação:**
> "Implementa o gitlab na minha máquina de staging"

O agente chama `repo_up` com `name: "gitlab"` e `machine: "staging"` -> implementa o repositório, devolve sucesso/falha.

**Depurar um serviço com falhas:**
> "O meu nextcloud está lento, descobre o que está errado"

O agente chama `machine_health` -> `machine_containers` -> `term_exec` para ler os registos -> identifica o problema e sugere uma solução.

## Opções de Configuração

| Opção | Predefinição | Descrição |
|-------|--------------|-----------|
| `--config <name>` | (configuração predefinida) | Configuração com nome a usar para todos os comandos |
| `--timeout <ms>` | `120000` | Tempo limite predefinido do comando em milissegundos |
| `--allow-grand` | desligado | Permitir operações destrutivas em repositórios grand (não-fork) |

## Segurança

O servidor MCP impõe duas camadas de proteção:

### Modo apenas-fork (predefinição)

Por omissão, o servidor corre em **modo apenas-fork**: as ferramentas de escrita (`repo_up`, `repo_down`, `repo_delete`, `backup_push`, `backup_pull`, `term_exec`) só podem operar em repositórios fork. Os agentes não podem tocar em repositórios grand (originais). Por design.

> **Os segredos por repositório são exclusivos da CLI por design.** `repo_secret_set` e `repo_secret_unset` são intencionalmente **não** expostos como ferramentas MCP. As escritas requerem uma pré-condição `--current <previous-value>` (ou `--rotate-secret` para reconhecer uma rotação não verificada), e essa cerimónia precisa de ser acompanhada por um humano. Os agentes que precisem de sugerir uma rotação de segredo devem chamar `repo_secret_get` para confirmar o digest e depois transmitir o comando CLI orientado ao operador ao utilizador através do campo estruturado `next.options[].run` no envelope de erro JSON. Consulte [Segurança de Agentes de IA](/en/docs/ai-agents-safety#structured-next-action-hints) para o padrão completo, e [Repositórios § Segredos](/en/docs/repositories#secrets) para o procedimento orientado ao utilizador.

Para permitir que um agente modifique repositórios grand, inicie com `--allow-grand`:

```json
{
  "mcpServers": {
    "rdc": {
      "command": "rdc",
      "args": ["mcp", "serve", "--allow-grand"]
    }
  }
}
```

Também pode definir a variável de ambiente `REDIACC_ALLOW_GRAND_REPO` com o nome de um único repositório, uma lista separada por vírgulas de nomes de repositórios (por exemplo `repo1,repo2,repo3`), ou `*` para todos os repositórios. Os espaços em branco em torno das entradas são ignorados, pelo que `repo1, repo2` também funciona. O acesso ao nível da máquina (como `term connect -m <machine>` sem repositório) ainda requer `*`; uma lista de nomes de repositórios não o desbloqueia.

### Chaves SSH por repositório e sandbox do lado do servidor

Cada repositório tem o seu próprio par de chaves SSH. A chave pública é implementada em `authorized_keys` com um prefixo `command=` que força todas as sessões SSH através de `renet sandbox-gateway <repo-name>`, um ForceCommand do lado do servidor que não pode ser contornado por nenhum cliente, incluindo o VS Code.

**Como funciona:**
1. `rdc repo create` ou `rdc repo fork` gera um par de chaves ed25519 único por repositório
2. A chave pública é implementada no remoto com `command="renet sandbox-gateway <name>"`
3. Cada ligação SSH usando essa chave passa pelo gateway, que aplica:
   - **Landlock LSM**, restrições de sistema de ficheiros ao nível do kernel para o caminho de montagem do repositório
   - **Overlay OverlayFS do home**, escritas em `$HOME` capturadas por repositório, leituras passam para o home real
   - **TMPDIR por repositório** em `<datastore>/.interim/sandbox/<name>/tmp/`
   - **Acesso Docker** via o socket Docker isolado do repositório
   - **Descida de privilégios** para o utilizador universal (`rediacc`)
4. O `.envrc` do repositório é carregado automaticamente para configuração do Docker e do ambiente

**RW Permitido**: caminho de montagem do repositório, espaço de trabalho sandbox por repositório, diretório home (via overlay), socket Docker
**RO Permitido**: caminhos do sistema (`/usr`, `/bin`, `/etc`, `/proc`, `/sys`)
**Bloqueado**: caminhos de montagem de outros repositórios, ficheiros do sistema fora da lista de permissões

**Integração com VS Code**: Cada repositório tem a sua própria instalação do servidor VS Code em `<datastore>/.interim/sandbox/<name>/.vscode-server/`. Múltiplos repositórios podem estar abertos simultaneamente com ambientes sandbox independentes, sem partilha de servidor entre repositórios.

Isto previne o movimento lateral. Mesmo que um agente obtenha acesso shell a um fork, não pode ler nem modificar outros repositórios na mesma máquina. O SSH ao nível da máquina (sem repositório) usa a chave de equipa e não tem sandbox.

## Arquitetura

O servidor MCP é sem estado. Cada chamada de ferramenta lança o `rdc` como processo filho isolado com as flags `--output json --yes --quiet`. Isto significa:

- Não há fugas de estado entre chamadas de ferramentas
- Usa a sua configuração `rdc` e chaves SSH existentes
- Funciona com os adaptadores local e cloud
- Os erros num comando não afetam os outros
