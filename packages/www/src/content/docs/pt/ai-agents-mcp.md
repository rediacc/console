---
title: Configuração do Servidor MCP
description: Ligue agentes de IA à infraestrutura Rediacc usando o servidor Model Context Protocol (MCP).
category: Guides
tags:
  - ai-agents
  - cli
subcategory: ai-agents
order: 33
language: pt
sourceHash: "ece2cec7cd2f4bc9"
sourceCommit: "948dc510c78b93b73ea5b1b7b379cdb93141486e"
---

## Visão Geral

Dois servidores MCP (Model Context Protocol) obtêm as suas ferramentas de um único registo, e o servidor remoto oferece um subconjunto:

| Servidor | Transporte | Execução | Ferramentas |
|---|---|---|---|
| Local | stdio | `rdc mcp serve`, iniciado pelo agente | Todas as ferramentas |
| Remoto | Streamable HTTP | `https://mcp.<region>.rediacc.cloud/g/<grantId>` | As ferramentas remotas, ou seja, todas exceto as da tabela das exclusivamente locais |

**Pré-requisitos:** `rdc` instalado e configurado com pelo menos uma máquina para o servidor local. Para o servidor remoto é preciso um grant numa configuração.

## Servidor local

`rdc mcp serve` inicia um servidor MCP por stdio. O agente lança-o como subprocesso e comunica com ele através de JSON-RPC.

### Claude Code

O ficheiro `.mcp.json` do projeto contém a entrada:

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

### Cursor

Abra Settings → MCP Servers → Add Server:

- **Name**: `rdc`
- **Command**: `rdc mcp serve`
- **Transport**: stdio

### Opções

| Opção | Predefinição | Descrição |
|-------|--------------|-----------|
| `--config <name>` | (configuração predefinida) | Configuração com nome a usar em todos os comandos |
| `--timeout <ms>` | `120000` | Tempo limite predefinido dos comandos, em milissegundos |

## Servidor remoto

Em cada região corre um Worker MCP em `mcp.<region>.rediacc.cloud`. Cada agente liga-se ao URL de um grant: `https://mcp.<region>.rediacc.cloud/g/<grantId>`. O grant indica uma configuração, um prazo de validade e um âmbito: um indicador de só leitura, uma lista de ferramentas permitidas e padrões (globs) de nomes de máquinas e repositórios. As chamadas de ferramentas correm no executor da organização do grant.

### Credenciais

Ambas as formas identificam o grant; o id do grant no URL limita-se a nomeá-lo.

| Forma | Utilização | Enviada como |
|---|---|---|
| Token de acesso OAuth | Clientes interativos como o claude.ai | `Authorization: Bearer <token>` |
| Bearer de agente `rmcp_<grantId>.<secret>` | Agentes sem interface | `Authorization: Bearer` ou `x-api-key` |

Uma credencial na query string é recusada com 400. Um token OAuth em falta, expirado ou de outro grant recebe 401 com um cabeçalho `WWW-Authenticate: Bearer resource_metadata=...` que aponta para o documento de recurso protegido do grant, para que o cliente OAuth renove o token ou inicie sessão. Um grant desconhecido, um segredo errado e um bearer de agente de outro grant recebem todos o mesmo 401 simples.

### OAuth

O Worker é um servidor de autorização OAuth 2.1 com PKCE (apenas S256). Os clientes registam-se através de um Client ID Metadata Document ou do registo dinâmico de clientes em `/register`.

| Endpoint | Finalidade |
|---|---|
| `/.well-known/oauth-authorization-server` | Metadados do servidor |
| `/.well-known/oauth-protected-resource/g/<grantId>` | Documento de recurso protegido de um grant |
| `/authorize` | Inicia a autorização e redireciona para a página de conta `/account/mcp/authorize` |
| `/oauth/token` | Troca de código, renovação e revogação |
| `/register` | Registo dinâmico de clientes |

O cliente envia `resource=https://mcp.<region>.rediacc.cloud/g/<grantId>`. A autorização só se conclui para o grant que o recurso nomeia, e um token só funciona no URL do seu grant. O redirecionamento de `/authorize` leva um identificador assinado de utilização única e nenhum segredo.

### Duração dos tokens

Um token nunca sobrevive ao seu grant.

| Token | Duração |
|---|---|
| Token de acesso | O menor entre 1 hora e o tempo que resta ao grant |
| Token de renovação | O menor entre 30 dias e o tempo que resta ao grant |

Cada troca de código e cada renovação volta a consultar o grant. Um grant expirado, revogado ou com a chave rodada responde `invalid_grant` e revoga a concessão OAuth. Os tokens de renovação rodam, e apresentar um duas vezes revoga o grant.

### Uma configuração por grant

Um grant serve apenas a configuração que nomeia. Um `tools/call` com um argumento que nomeie outra configuração (`config` ou uma variante de escrita) é recusado com `REDIACC_GRANT_SCOPE` antes de qualquer execução. Quem tem várias configurações autoriza um grant por configuração. Uma ferramenta fora da lista permitida do grant, ou uma ferramenta de escrita num grant de só leitura, não aparece em `tools/list` e é recusada quando chamada.

### Regiões

O id de um grant começa pela sua região, por exemplo `eu_`. Um pedido a `/g/<grantId>` no Worker de outra região recebe 421 com o URL correto:

```json
{
  "code": "REDIACC_WRONG_REGION",
  "message": "This grant lives in the us region. Use https://mcp.us.rediacc.cloud/g/us_...",
  "region": "us",
  "mcpUrl": "https://mcp.us.rediacc.cloud/g/us_..."
}
```

Um grant nunca é aceite como recurso OAuth, audiência de token ou alvo de autorização fora da sua região.

### Estados do grant e limites

Um grant que expirou, foi revogado ou perdeu a chave por uma rotação de chaves do armazenamento de configuração continua a responder a `initialize` e `tools/list`. Cada `tools/call` devolve então `REDIACC_GRANT_EXPIRED`, `REDIACC_GRANT_REVOKED` ou `REDIACC_KEY_ROTATED` com um `reauthUrl` que o utilizador abre para autorizar de novo.

Cada grant permite 60 chamadas por minuto e 5 chamadas em simultâneo. Uma chamada acima de qualquer dos limites devolve `REDIACC_RATE_LIMITED` com `retryAfterSeconds`.

## Ferramentas Disponíveis

<!-- >>> translated-table: mcp-tools -->

| Ferramenta | Destrutiva | Descrição |
|---|---|---|
| `backup_browse` | não | Lista os arquivos que um repositório contém. |
| `backup_cancel` | não | Cancela um backup em execução em uma máquina remota. |
| `backup_check` | não | Comprova que um snapshot armazenado abre com a senha (passphrase), restaurando um arquivo. |
| `backup_immutability_show` | não | Mostra a janela de exclusão adiada em vigor. |
| `backup_list` | não | Lista os artefatos de backup de uma máquina. |
| `backup_manifests` | não | Lista os manifestos de snapshots de backup registrados no servidor. |
| `backup_reconcile` | sim | Redefine o registro de bytes armazenados de um repositório para o que o armazenamento realmente contém (nunca exclui um chunk). |
| `backup_repair` | sim | Reenvia, a partir da âncora desta máquina, os chunks que o armazenamento perdeu ou guarda com erro. |
| `backup_restore` | sim | Transforma um artefato de backup em um repositório ativo. |
| `backup_retention` | não | Mostra a política de retenção de snapshots que o servidor aplica. |
| `backup_retention_preview` | não | Mostra quais snapshots a próxima limpeza excluiria e quanto espaço liberaria. |
| `backup_run` | não | Executa um backup agora. |
| `backup_snapshot` | não | Envia um snapshot do armazenamento de chunks: primeiro o inventário completo, depois as células alteradas. |
| `backup_status` | não | Mostra o status dos backups e do temporizador em uma máquina remota. |
| `backup_strategy_list` | não | Lista todas as estratégias de backup. |
| `backup_strategy_show` | não | Mostra os detalhes de uma estratégia de backup. |
| `backup_toc-key_sync` | não | Instala a chave de listagem do repositório na máquina dele, ou substitui uma diferente. |
| `backup_undelete` | não | Cancela a exclusão adiada de um snapshot antes que ela entre em vigor. |
| `backup_usage` | não | Mostra a cota de armazenamento de backup, os bytes armazenados e o uso por repositório. |
| `backup_verify` | não | Verifica a âncora de backup de um repositório em relação ao armazenamento de chunks. |
| `cluster_snapshot_list` | não | Lista os snapshots de grupo do cluster. |
| `cluster_status` | não | Lista todos os clusters ou, com o nome de um cluster, mostra a configuração completa dele. |
| `config_access_list` | não | Lista as chaves de acesso da configuração. |
| `config_prune` | não | Remove o que sobra do arquivo de configuração local ~/.config/rediacc/<config>.json. |
| `config_reconcile` | não | Reconstrói o repositório de estado local a partir do estado real das máquinas (renet list all). |
| `config_show` | não | Mostra os detalhes da configuração atual. |
| `credits` | não | Mostra o saldo de créditos restante desta conta. |
| `datastore_list` | não | Lista os datastores nomeados, onde estão anexados e o que contêm. |
| `datastore_snapshot_list` | não | Lista os snapshots de um datastore. |
| `datastore_status` | não | Mostra um datastore: backend, anexo, uso, repositórios e snapshots. |
| `feedback_list` | não | Lista os relatórios de feedback visíveis para esta máquina: id, impressão digital curta, status e datas. |
| `feedback_report` | não | Monta um relatório a partir do último comando com falha (--last), de um comando registrado (--command <n>) ou apenas de uma mensagem, mostra exatamente o que seria enviado e envia após a confirmação. |
| `feedback_show` | não | Mostra um relatório de feedback pelo id (ou por um prefixo único), com status, número de ocorrências e datas. |
| `incident_status` | não | Lista os incidentes da organização ou mostra um com seu escopo, janela, etapas por máquina e os relógios dos prazos de alerta antecipado, notificação e relatório final. |
| `job_cancel` | sim | Cancela um job desanexado em execução. |
| `job_dismiss` | sim | Abandona tickets de job localmente: os passos pendentes são descartados e o ticket deixa de aparecer. |
| `job_gc` | sim | Remove jobs concluídos e seus logs. |
| `job_list` | não | Lista os jobs desanexados de uma máquina, do mais recente ao mais antigo. |
| `job_logs` | não | Reproduz ou acompanha o log de eventos de um job desanexado. |
| `job_status` | não | Mostra o status de um job desanexado. |
| `job_wait` | não | Aguarda até 50 s para um job terminar. |
| `legal` | não | Imprime os links dos documentos legais no idioma da CLI junto com os links vinculantes em inglês, a versão atual dos Termos de Serviço com checksum e URL do arquivo, o aceite registrado (do servidor de contas quando há login, desta configuração no modo anônimo) e a entidade contratante. |
| `machine_access_show` | não | Mostra as chaves de acesso vinculadas a uma máquina e os intervalos que cada uma resolve nela. |
| `machine_add` | não | Registra uma máquina existente acessível por SSH. |
| `machine_containers` | não | Lista os contêineres Docker de uma máquina. |
| `machine_converge` | sim | Reinicia, um repositório por vez, cada daemon de repositório que ainda roda em um layout de runtime mais antigo, para que passe ao atual. |
| `machine_deprovision` | sim | Destrói uma máquina provisionada na nuvem e a remove da configuração. |
| `machine_gpu_list` | não | Lista as GPUs detectadas em uma máquina, os nomes de dispositivo CDI definidos pelas suas especificações e os repositórios aos quais cada dispositivo é concedido. |
| `machine_health` | não | Verifica a saúde de uma máquina para pipelines de CI/CD. |
| `machine_infra_show` | não | Mostra a configuração de infraestrutura de uma máquina (domínio base, IPs públicos, portas), as configurações TLS compartilhadas (e-mail do certificado, token DNS da CF) e o ID da zona da Cloudflare. |
| `machine_list` | não | Lista as máquinas. |
| `machine_provider_add` | não | Adiciona um provedor de nuvem. |
| `machine_provider_list` | não | Lista os provedores de nuvem configurados para o provisionamento de máquinas. |
| `machine_provider_remove` | sim | Remove a configuração de um provedor de nuvem. |
| `machine_provision` | sim | Provisiona uma nova máquina em um provedor de nuvem com o OpenTofu. |
| `machine_prune` | sim | Remove de uma máquina os recursos órfãos do datastore e os snapshots obsoletos. |
| `machine_remove` | sim | Remove uma máquina da configuração. |
| `machine_repos` | não | Lista os repositórios implantados em uma máquina. |
| `machine_restart-services` | sim | Passa os daemons do renet que ainda executam um binário substituído para o binário instalado, uma unidade por vez, confirmando que cada uma está ativa antes de seguir para a próxima. |
| `machine_scan-keys` | não | Registra na configuração local as chaves de host SSH da máquina. |
| `machine_services` | não | Lista os serviços systemd gerenciados pelo Rediacc em uma máquina (nome, estado, subestado, número de reinicializações, memória, repositório resolvido para o nome com o original em repository_guid). |
| `machine_setup` | não | Conclui a integração de uma máquina: instala o renet e a prepara para hospedar repositórios. |
| `machine_status` | não | Obtém os detalhes de conexão (IP, usuário, porta, datastore), as informações do sistema, os contêineres (repositório resolvido para o nome, original em repository_guid, domínio, autoRoute), os serviços (repositório resolvido para o nome), os repositórios (nome resolvido a partir do GUID, original em guid) e o uso de recursos de uma máquina. |
| `repo_admin_fsck` | não | Valida as referências da configuração (branches/HEAD) em relação aos objetos presentes em uma máquina e informa referências pendentes e commits órfãos. |
| `repo_cat` | não | Lê em stdout uma janela limitada de um arquivo de um repositório (os diagnósticos vão para stderr). |
| `repo_checkout` | sim | Clona por reflink um commit imutável (ou a ponta de um branch) em um novo fork de trabalho gravável e aponta o HEAD para ele. |
| `repo_commit` | sim | Congela um fork de trabalho montado em um novo commit imutável (como no git). |
| `repo_create` | sim | Cria um novo repositório. |
| `repo_delete` | sim | Exclui um repositório e seus dados. |
| `repo_diff` | não | Diff em nível de arquivo no estilo git entre dois repositórios fork com copy-on-write. |
| `repo_down` | sim | Interrompe os contêineres Docker de um repositório (executa Rediaccfile down). |
| `repo_exec` | sim | Executa um comando dentro de um contêiner de um repositório. |
| `repo_flows` | não | Lista os fluxos de rede registrados para um repositório em uma janela de tempo: hora, processo, destino, bytes enviados e recebidos, e o ASN e o país do destino quando conhecidos. |
| `repo_fork` | sim | Cria um fork CoW quase instantâneo de um repositório com um GUID e um networkId NOVOS (cópia totalmente independente). |
| `repo_gc` | sim | Coleta de lixo por alcançabilidade: exclui os objetos de commit imutáveis de uma máquina que nenhum branch ou HEAD alcança. |
| `repo_health` | não | Executa as verificações health() do Rediaccfile de um repositório e termina com 0 (ok), 1 (aviso) ou 2 (erro). |
| `repo_list` | não | Lista os repositórios de uma máquina. |
| `repo_log` | não | Imprime o histórico de commits alcançável a partir do commit atual de um fork de trabalho (ou de uma referência de commit), percorrendo a cadeia de pais registrada por 'rdc repo commit'. |
| `repo_logs` | não | Mostra os logs da aplicação dos contêineres de um repositório. |
| `repo_merge` | sim | Mescla, de forma segura para o ciclo de vida, um commit ou fork de origem em um fork de trabalho de destino. |
| `repo_migrate` | sim | Move um repositório para outra máquina com o mínimo de indisponibilidade: cópia em duas fases (sincronização em massa em execução, depois uma parada curta, sincronização do delta e início no destino) com troca de DNS. |
| `repo_opens` | não | Lista as aberturas de arquivos registradas para um repositório em uma janela de tempo: hora, processo e caminho, com os caminhos sensíveis marcados. |
| `repo_pull` | sim | Baixa um repositório de outra máquina. |
| `repo_push` | sim | Envia o backup de um repositório para o armazenamento ou diretamente para outra máquina. |
| `repo_replicate` | não | Provisiona réplicas de leitura de um repositório. |
| `repo_replicate_remove` | sim | Remove um conjunto de réplicas: exclui os objetos k8s gerados (limitados por rótulo), descarta os datastores fork, remove o snapshot e esquece o estado. |
| `repo_replicate_status` | não | Mostra os conjuntos de réplicas gerenciados: réplicas, nós hospedeiros, datastores fork, snapshot e horários de atualização. |
| `repo_secret_get` | não | Mostra o digest SHA-256 de um segredo. |
| `repo_secret_list` | não | Lista as chaves e os modos dos segredos (nunca valores, nunca digests). |
| `repo_status` | não | Obtém o status de um repositório (estado da montagem, daemon do Docker em execução, número de contêineres, uso de disco). |
| `repo_trim` | não | Recupera espaço do pool do datastore a partir de repositórios montados (online, sem indisponibilidade). |
| `repo_up` | sim | Implanta ou atualiza um repositório (executa Rediaccfile up via renet compose e inicia os contêineres). |

<!-- <<< translated-table -->

<!-- >>> translated-table: mcp-tools-local -->

| Ferramenta | Destrutiva | Descrição |
|---|---|---|
| `cluster_kubeconfig` | não | Obtém por SSH o kubeconfig do nó de controle do cluster e o guarda em cache local (0600) para o kubectl. |
| `config_audit_log` | não | Lê o log de auditoria das alterações feitas por esta configuração. |
| `config_audit_verify` | não | Verifica se a cadeia de hashes do log de auditoria não foi adulterada. |
| `config_current` | não | Mostra a configuração ativa: nome, arquivo, servidor e canal resolvidos, estado do token. |
| `config_list` | não | Lista todos os arquivos de configuração. |
| `forensics_verify` | não | Recalcula a cadeia de hashes dos arquivos diários de auditoria e as cadeias de lotes forenses assinados de um diretório de evidências (um diretório de exportação do rdc incident) e lista cada lacuna e cada edição. |
| `incident_export` | não | Grava a janela do incidente em um diretório: o registro do incidente com seus relógios, a linha do tempo mesclada, os agregados de bytes enviados, o manifesto bruto da cadeia e os arquivos brutos que ele lista, sob as chaves do manifesto. |
| `machine_infra_cert_status` | não | Mostra o inventário de certificados em cache. |
| `server_status` | não | Mostra o estado, o nível, o certificado e a imagem de um servidor instalado. |
| `version` | não | Imprime a versão da CLI, a plataforma, o canal de atualização e a licença ativa: o plano quando há login, "anonymous (FREE per repository)" sem login e "unknown (server unreachable)" quando o servidor de contas está inacessível. |

<!-- <<< translated-table -->

## Exemplos de Fluxos de Trabalho

**Verificar o estado de uma máquina:**
> "Qual é o estado da minha máquina de produção?"

O agente chama `machine_status` e obtém os detalhes de ligação, as informações do sistema, os contentores, os serviços, os repositórios e a utilização de recursos.

**Implementar uma aplicação:**
> "Implementa o gitlab na minha máquina de staging"

O agente chama `repo_up` com `name: "gitlab"` e `machine: "staging"`, o que implementa o repositório e devolve sucesso ou falha.

**Acompanhar um job longo:**
> "Restaura o backup da noite passada do nextcloud"

O agente chama `backup_restore`. Um comando que excede a sua janela devolve um identificador de job, e o agente chama `job_wait` (até 50 s por chamada) e `job_logs` até o job terminar.

**Depurar um serviço com falhas:**
> "O meu nextcloud está lento, descobre o que se passa"

O agente chama `machine_health`, depois `machine_containers` e `repo_logs`, e sugere uma correção.

## Segurança

O servidor MCP local aplica duas camadas de proteção. Os limites do servidor remoto estão em [Servidor remoto](#servidor-remoto).

### Modo apenas-fork (predefinição)

Por predefinição, o servidor corre em **modo apenas-fork**: as ferramentas de escrita (`repo_up`, `repo_down`, `repo_delete`, `repo_exec`, `repo_push`, `repo_pull`) só podem atuar sobre repositórios fork. Os agentes não podem tocar nos repositórios grand (originais). Por design.

> **Os segredos por repositório são exclusivos da CLI por design.** `repo_secret_set` e `repo_secret_unset` são intencionalmente **não** expostos como ferramentas MCP. As escritas requerem uma pré-condição `--current <previous-value>` (ou `--rotate-secret` para reconhecer uma rotação não verificada), e essa cerimónia precisa de ser acompanhada por um humano. Os agentes que precisem de sugerir uma rotação de segredo devem chamar `repo_secret_get` para confirmar o digest e depois transmitir o comando CLI orientado ao operador ao utilizador através do campo estruturado `next.options[].run` no envelope de erro JSON. Consulte [Segurança de Agentes de IA](/en/docs/ai-agents-safety#structured-next-action-hints) para o padrão completo, e [Repositórios § Segredos](/en/docs/repositories#secrets) para o procedimento orientado ao utilizador.

Para permitir que um agente modifique repositórios grand, exporte `REDIACC_ALLOW_GRAND_REPO` em seu terminal **antes de iniciar o agente que hospeda o servidor MCP**:

```bash
export REDIACC_ALLOW_GRAND_REPO='gitlab'   # um repositório
# ou 'repo1,repo2,repo3' (espaços em branco em torno das entradas são ignorados), ou '*' para todos os repositórios
claude   # ou cursor, gemini, etc.
```

A anulação é verificada contra a ancestralidade do processo: ela apenas conta quando já estava presente no ambiente do próprio processo agente, o que significa que você a exportou antes do agente (e do servidor MCP que ele criou) iniciar. Um agente não pode se conceder acesso definindo a variável no meio da sessão. Não há intencionalmente nenhum sinalizador de servidor para isso: um sinalizador nos argumentos do servidor MCP não carrega prova de quem o colocou lá, enquanto a verificação de ancestralidade faz. O acesso ao nível da máquina (como `term connect <machine>` sem um repositório) ainda requer `*`; uma lista de nomes de repositórios não o desbloqueia.

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

O servidor MCP local não guarda estado. Cada chamada de ferramenta lança `rdc` como processo filho isolado com as flags `--output json --yes --quiet`. Isto significa:

- Não há fugas de estado entre chamadas de ferramentas
- Usa a sua configuração `rdc` e chaves SSH existentes
- Os erros num comando não afetam os outros
