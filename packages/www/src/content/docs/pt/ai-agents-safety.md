---
title: Segurança e Proteções de Agentes IA
description: >-
  Como o CLI da Rediacc impede que assistentes de código IA vazem segredos,
  sobrescrevam credenciais ou escalonem privilégios. Portões de conhecimento,
  redação, anulações verificadas por ancestralidade e um registro de auditoria encadeado por hash.
category: Concepts
order: 35
language: pt
sourceHash: "ae23c9bc851ecfcd"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

Você está apontando um assistente de código IA para sua infraestrutura. Quando Claude Code, Cursor, Gemini CLI, Copilot CLI ou qualquer coisa similar dirige `rdc`, o CLI detecta e aplica um conjunto de regras diferente do de um humano no teclado. Esta página cobre o que o agente pode e não pode fazer, e como as proteções se mantêm mesmo quando ele tenta convencer seu caminho para sair delas.

## Referência rápida: o que agentes podem e não podem fazer

| Operação | Padrão do agente | Como desbloquear para um caso de uso específico |
|---|---|---|
| `rdc config show` (redação) | ✅ permitido |  |
| `rdc config field get --pointer <pointer>` (redação de stub ou resumo) | ✅ permitido |  |
| `rdc config field get --pointer <pointer> --digest` | ✅ permitido |  |
| `rdc config field set --pointer <pointer>` (campo público) | ✅ permitido |  |
| `rdc config field set --pointer <pointer>` (campo sensível, **com `--current` correto**) | ✅ permitido |  |
| `rdc config edit --dump` (JSONC redacionado) | ✅ permitido |  |
| `rdc config audit {log, tail, verify}` | ✅ permitido |  |
| `rdc config field set --pointer <pointer>` (campo sensível, sem `--current`) | 🔴 recusado | Forneça `--current "<old value>"` |
| `rdc config field get --pointer <pointer> --reveal` | 🔴 recusado | Use `--digest` em vez disso |
| `rdc config show --reveal` | 🔴 recusado | Use `rdc config show` simples |
| `rdc config edit` (editor interativo) | 🔴 recusado | Humano define `REDIACC_ALLOW_CONFIG_EDIT=*` antes de iniciar o agente |
| `rdc config edit --apply <file>` | 🔴 recusado | Mesma anulação |
| `rdc config field rotate --pointer <pointer>` | 🔴 recusado | Mesma anulação; usa confirmação interativa |
| `rdc term connect -m <machine>` (SSH direto da máquina) | 🔴 recusado | Faça fork de um repositório primeiro e conecte ao fork |

Cada recusa é escrita no registro de auditoria com `outcome: refused` e um motivo.

## Como agentes são detectados

O CLI trata um processo como um agente quando qualquer um destes é verdadeiro:

- Um de `REDIACC_AGENT`, `CLAUDECODE`, `GEMINI_CLI`, `COPILOT_CLI` está definido como `"1"`, ou `CURSOR_TRACE_ID` está definido de alguma forma.
- No Linux: qualquer processo pai acima na cadeia de ancestralidade tem uma dessas variáveis em seu ambiente (via `/proc/<pid>/environ`). Mesmo se o agente desativar suas próprias variáveis com `env -i` ou um script de encapsulador, a cadeia pai ainda diz ao CLI quem o iniciou.

A detecção é executada uma vez por processo e é armazenada em cache. Não pode ser desabilitada.

## O modelo de conhecimento-gate

Mutações sensíveis seguem a convenção `passwd(1)`: para alterar um segredo, prove que já o conhecia. **Simétrico para humanos e agentes**. Ambos passam pelo mesmo portão. Não há bypass de "estou no teclado".

- Você quer rotacionar um token de API armazenado em `/credentials/cfDnsApiToken`?
- O CLI pergunta: "qual é o valor atual?"
- O agente (ou humano) fornece o texto simples via `--current "$OLD"`. O CLI cria um hash `$OLD` com SHA-256 e compara com o resumo do valor armazenado atualmente. Coincidência → a escrita passa. Incompatibilidade → recusada, auditada.
- Para rotacionar sem verificar o valor anterior, passe `--rotate-secret` (mutuamente exclusivo com `--current`). Isso é claramente auditado como uma rotação.

O modelo fecha três superfícies de ataque:

1. **Rotação silenciosa**: um chamador (agente ou humano) sem acesso anterior a `$OLD` não pode substituí-lo por um valor próprio.
2. **Exfiltração por sondagem**: a resposta de resumo nunca contém texto simples; mesmo um registro de auditoria comprometido mostra `expected abc12345…, got deadbeef…`, não os valores subjacentes.
3. **Pisando acidentalmente na configuração de produção**: requer `--current` deliberado a cada vez, mesmo em um TTY. Pega o erro de "queria definir STRIPE_TEST mas estou no shell de produção".

### Dicas estruturadas de próxima ação

Quando a pré-condição falha, o envelope JSON (`--output json`) carrega um campo `errors[].next` estruturado dizendo aos agentes exatamente o que sugerir ao humano fazer:

```json
{
  "errors": [{
    "code": "PRECONDITION_MISMATCH",
    "message": "...",
    "next": {
      "summary": "Provide the current value or acknowledge rotation.",
      "options": [
        { "description": "Re-read current digest, then retry with --current",
          "run": "rdc repo secret get --name mail --key STRIPE_KEY" },
        { "description": "Skip the precondition (rotation, audited)",
          "run": "rdc repo secret set --name mail --key STRIPE_KEY --value <new> --mode file --rotate-secret" }
      ]
    }
  }]
}
```

**Agentes devem retransmitir `next.options[].run` verbatim ao humano em vez de sintetizar seus próprios comandos.** Isso evita o modo de falha "agente inventa um comando que não existe" e mantém o operador no controle da ação real.

### Exemplo trabalhado

```bash
# Descobrir o resumo curto do stub de redação (seguro para agentes).
$ rdc config field get --pointer /credentials/cfDnsApiToken
{"pointer": "/credentials/cfDnsApiToken", "value": "<redacted:secret>:abc12345"}

# Tentar sobrescrever sem prova: recusado.
$ rdc config field set --pointer /credentials/cfDnsApiToken --new '"agent-picked-value"'
✗ Precondition failed: sensitive path requires --current (or --rotate-secret)

# Fornecer o texto simples atual: permitido.
$ rdc config field set --pointer /credentials/cfDnsApiToken \
    --current "$OLD_CF_TOKEN" \
    --new   "$NEW_CF_TOKEN"
Set /credentials/cfDnsApiToken
```

Se o agente nunca tiver `$OLD_CF_TOKEN`, ele não pode satisfazer a pré-condição e a rotação é recusada. O usuário que *tem* pode ainda fazer isso através do editor ou passando `--current` de seu shell.

## Redação por padrão

Cada comando `rdc` que lê estado sensível: `config show`, `config field get`, `config machine list`, `config edit --dump`: retorna **redação de stubs** para campos secretos, não texto simples:

```
"sshKey":       "<redacted:credential>:9f3a2c1b"
"cfDnsApiToken":"<redacted:secret>:abc12345"
"storages.s3-prod.vaultContent": "<redacted:secret>:1f2e3d4c"
```

O sufixo hex de 8 caracteres do stub são os primeiros 8 caracteres de `sha256(canonicalize(value))`: o suficiente para distinguir dois valores diferentes à primeira vista, não o suficiente para reverter. Um agente pode usar um stub para rastrear se um valor mudou sem nunca vê-lo.

`--reveal` não redaciona para humanos em um TTY interativo. Agentes são recusados independentemente do estado do TTY. Cada concessão escreve uma entrada de auditoria `reveal_granted`; cada recusa escreve uma entrada `refused` com os sinais do agente do ator anexados.

## A anulação `REDIACC_ALLOW_CONFIG_EDIT`

Algumas operações: o editor interativo, `--apply`, `field rotate`: existem para humanos e não têm caminho seguro para agentes. Se você realmente quer que um agente faça um deles, você define:

```bash
export REDIACC_ALLOW_CONFIG_EDIT='*'          # bypass completo
# ou
export REDIACC_ALLOW_CONFIG_EDIT='/credentials/ssh/privateKey,/infra/cfDnsZoneId'
# (globs separados por vírgulas: wildcards * permitidos por segmento)
```

…e o agente o herda.

**Detalhe crucial**: a anulação deve aparecer em um processo **acima** do agente na cadeia de ancestralidade. Se o agente a define em seu próprio ambiente (ou em um subshell que criou), o CLI recusa e diz isso:

> `Interactive editor is blocked in agent environments (REDIACC_ALLOW_CONFIG_EDIT was set but ancestry verification failed: the override must be set by your shell, not by an agent).`

O efeito: um agente não pode convencer seu caminho além de uma proteção executando `export REDIACC_ALLOW_CONFIG_EDIT='*'` no meio da sessão. Apenas um processo pai (você, em seu terminal, antes de iniciar o agente) pode abrir essa porta.

## Suporte de plataforma: apenas Linux para as anulações

`REDIACC_ALLOW_CONFIG_EDIT` e `REDIACC_ALLOW_GRAND_REPO` ambas contam com verificação de ancestralidade para provar que a anulação foi definida por você e não injetada pelo agente. A verificação lê `/proc/<pid>/environ` para cada processo acima da cadeia. Esse arquivo é definido pelo kernel no tempo de execução e não pode ser modificado pelo próprio processo, então o ambiente do shell pai é uma testemunha à prova de manipulação.

Esse arquivo não existe no macOS ou Windows. Sem forma de verificar legitimidade, o CLI falha fechado. Mesmo quando você define a anulação corretamente em seu shell antes de iniciar o agente, a anulação é rejeitada. A mensagem de erro diz exatamente o que fazer:

> The REDIACC_ALLOW_GRAND_REPO override is not supported on darwin. This override only works on Linux. On Windows and macOS, agents must use the fork-first workflow. … To use the override, run your agent on Linux (directly, WSL, Docker, or a VM).

Usuários não Linux não têm escape hatch do fluxo fork-first. Isso é intencional. Não há forma para um agente contornar a sandbox, independentemente de como foi solicitado. Se você precisar da anulação, execute seu agente dentro do WSL, um contêiner Linux ou uma VM Linux. Caso contrário, trabalhe em um fork.

## Registro de auditoria

Cada mutação, cada recusa, cada concessão `--reveal` escreve uma linha JSONL em `~/.config/rediacc/audit.log.jsonl` (modo `0600`, rodado em 10 MB). Cada linha é encadeada por hash: seu campo `prevHash` é `sha256("<previous line>")`. Manipular qualquer linha quebra a cadeia em todas as linhas seguintes.

```jsonl
{"ts":"2026-04-21T10:02:47.831Z","actor":{"kind":"agent","agentSignals":["CLAUDECODE"]},"command":"config field set","paths":["/credentials/cfDnsApiToken"],"outcome":"ok","configId":"...","configVersion":48,"prevHash":"sha256:9f3a..."}
{"ts":"2026-04-21T10:02:51.114Z","actor":{"kind":"agent","agentSignals":["CLAUDECODE"]},"command":"config edit","paths":[],"outcome":"refused","reason":"agent without REDIACC_ALLOW_CONFIG_EDIT=*","prevHash":"sha256:abc1..."}
{"ts":"2026-04-21T10:03:05.220Z","actor":{"kind":"human"},"command":"config show --reveal","paths":[],"outcome":"reveal_granted","configId":"...","configVersion":48,"prevHash":"sha256:deac..."}
```

### Inspecionar

```bash
# Listar entradas recentes
rdc config audit log --since 24h

# Filtrar por glob de pointer
rdc config audit log --path '/credentials/*'

# Apenas entradas originadas pelo agente
rdc config audit log --actor agent

# Transmitir entradas novas ao vivo (Ctrl+C para parar)
rdc config audit tail

# Verificar se a cadeia de hash está intacta
rdc config audit verify
# → "Chain integrity verified across 247 entries."
#   OU
# → "Chain broken at line 103: file has been tampered with or corrupted."
```

### O que nunca aparece no registro de auditoria

- Valores secretos em texto simples
- Senhas, tokens, chaves SSH
- Os valores antigo/novo em uma incompatibilidade de pré-condição `--current` (apenas o prefixo de resumo de 8 caracteres)

O registro é seguro para compartilhar com um revisor de segurança ou anexar a um relatório de bug.

## Limites do modelo comportamental

As proteções de agentes são **comportamentais, não criptográficas**. Um agente determinado ou solicitado executado como o mesmo UID que o arquivo de configuração sempre pode fazer `cat ~/.config/rediacc/rediacc.json` e ler o texto simples, porque o arquivo é legível pelo processo.

Para aplicação criptográfica real, use o [armazenamento de configuração criptografado](/pt/docs/config-storage): segredos vivem no lado do servidor, cada campo sensível carrega um comprometimento HMAC por campo, e o trabalhador de conta recusa gravações cuja pré-condição `--current` não corresponde ao hash do que tem armazenado. O servidor nunca vê o texto simples (conhecimento zero), mas força o portão.

Arquivos locais: o caminho fácil é o seguro. Armazenamento remoto: a rota de bypass também é criptograficamente difícil.

## O que Rediacc não isola

As proteções de agentes nesta página protegem a própria infraestrutura da Rediacc: o arquivo de configuração, o daemon Docker por repositório, os dados de repositório criptografados com LUKS, a sandbox SSH com escopo. Eles não protegem serviços externos que seu repositório mantém credenciais para.

Um fork de repositório é um reflink BTRFS do volume pai. O que quer que viva no disco no pai é idêntico em bytes no fork: código, dados e arquivos `.env` também. Se seu repositório contiver uma `STRIPE_LIVE_KEY`, uma `AWS_ACCESS_KEY_ID`, um token Railway API ou qualquer outra credencial de longa vida para um serviço de terceiros, o fork a herda. Um agente operando na sandbox do fork pode ler esse arquivo, exfiltrar o valor ou usá-lo para chamar a API de terceiros. O serviço de terceiros não tem forma de saber se a chamada veio de um fork em vez de produção.

Esta é a linha de responsabilidade compartilhada:

| Limite | Proprietário |
|---|---|
| Dados do repositório, namespace de montagem, escopo Docker, proteções de agentes, registro de auditoria, injeção de segredos no tempo de implantação | Rediacc |
| Código de aplicação que usa esses segredos, e quaisquer credenciais assadas na imagem no tempo de compilação | Desenvolvedor do repositório |

A mitigação primária é construída: **[segredos por repositório](/pt/docs/repositories#secrets)** são armazenados em um plano separado da imagem de repositório criptografada e não são copiados além do limite do fork. Os contêineres do fork inicializam com um mapa de segredos vazio e se identificam como um principal externo diferente do pai. Defina-os com `rdc repo secret set` (modo env para interpolação de composição, modo arquivo para blocos tmpfs `secrets:`). O portão de mutação é simétrico. Humanos e agentes devem fornecer `--current` (pré-condição estilo passwd) ou `--rotate-secret` (rotação auditada) para sobrescrever ou excluir um valor existente.

**Isolamento de repositório cruzado é aplicado.** Um arquivo de composição malicioso ou descuidado no repositório B não pode referenciar o diretório de segredos do repositório A. O validador de composição do Renet nega duramente qualquer caminho `secrets: file:`, `configs: file:` ou `env_file:` que aponte para fora do diretório `${REDIACC_NETWORK_ID}` do repositório atual, e a rejeição NÃO é sobrescritível por `--unsafe`. Defesa em profundidade: a sandbox Landlock ao redor do subprocesso bash Rediaccfile limita leituras do sistema de arquivos ao diretório de segredos da rede atual apenas, então um `cat /var/run/rediacc/secrets/<other>/X` de um Rediaccfile malicioso falha com EACCES na camada do kernel.

Dois padrões adicionais fecham casos extremos:

1. **Não assem credenciais de produção no próprio sistema de arquivos do repositório.** Um arquivo `.env` comprometido na imagem, ou uma credencial persistida em um volume durante `up()`, é reflinked no fork. O recurso de segredos por repositório apenas protege valores que você mantém no plano de segredos. Não pode proteger retroativamente bytes que já vivem dentro da imagem LUKS. Para repositórios existentes com arquivos `.env` assados, levante-os para segredos por repositório manualmente.
2. **Restrinja a rede de saída do fork com filtragem de egresso eBPF** para que o fork apenas possa atingir localhost e pontos de extremidade de sandbox explícitos. O isolamento de rede por repositório da Rediacc é a fundação; listas de permissão de egresso por fork não são construídas hoje, mas o caminho está aberto.

Rediacc trata da injeção no tempo de implantação, do isolamento de fork cruzado e do isolamento de repositório cruzado. A metade "não assem na imagem" é com você.

## Receitas rápidas

### Deixe um agente rotacionar um token único de nuvem

```bash
# Como você, antes de iniciar o agente:
export REDIACC_ALLOW_CONFIG_EDIT='/credentials/cfDnsApiToken'
claude-code              # ou cursor, gemini, etc.
```

Agora o agente pode `config field rotate /credentials/cfDnsApiToken --new …` mas ainda não pode editar `/credentials/ssh/privateKey` ou abrir o editor interativo.

### Deixe um agente fazer uma sessão de edição de configuração ampla

```bash
export REDIACC_ALLOW_CONFIG_EDIT='*'
claude-code
```

O agente pode abrir `rdc config edit`, usar `--reveal` e executar `field rotate`. Cada ação ainda é auditada com `actor.kind: agent` e o sinal `CLAUDECODE`.

### Descubra quais campos um agente pode tocar

```bash
rdc config field list --sensitive --output json
```

Retorna cada template de pointer, seu tipo (`secret` / `credential` / `pii` / `identifier`), e se está comprometido com o envelope HMAC do lado do servidor.

## Veja também

- [Visão geral da integração de agentes IA](/pt/docs/ai-agents-overview): o passeio de nível superior
- [Configuração do Claude Code](/pt/docs/ai-agents-claude-code): modelo de integração
- [Envelope de saída JSON](/pt/docs/ai-agents-json-output): respostas legíveis por máquina
- [Armazenamento de configuração criptografado](/pt/docs/config-storage): aplicação criptográfica do lado do servidor
- [Segurança de conta](/pt/docs/account-security): postura de segurança voltada para o operador
