---
title: Segurança e Controlos para Agentes de IA
description: >-
  Como o CLI da Rediacc impede que assistentes de programação com IA exponham segredos,
  substituam credenciais ou escalonem privilégios. Knowledge-gates,
  redação, overrides verificados por ancestralidade e um registo de auditoria com cadeia de hashes.
category: Concepts
order: 35
language: pt
---

Quando o Claude Code, o Cursor, o Gemini CLI, o Copilot CLI ou qualquer outro assistente de programação com IA controla o `rdc`, o CLI trata-o de forma diferente de um utilizador humano ao teclado. Esta página explica o que o agente pode fazer, o que não pode fazer e como os controlos se mantêm mesmo quando o agente tenta contorná-los.

## Referência rápida: o que os agentes podem e não podem fazer

| Operação | Predefinição para agentes | Como desbloquear para um caso de uso específico |
|---|---|---|
| `rdc config show` (redatado) | ✅ permitido |  |
| `rdc config field get --pointer <pointer>` (stub redatado ou digest) | ✅ permitido |  |
| `rdc config field get --pointer <pointer> --digest` | ✅ permitido |  |
| `rdc config field set --pointer <pointer>` (campo público) | ✅ permitido |  |
| `rdc config field set --pointer <pointer>` (campo sensível, **com `--current` correto**) | ✅ permitido |  |
| `rdc config edit --dump` (JSONC redatado) | ✅ permitido |  |
| `rdc config audit {log, tail, verify}` | ✅ permitido |  |
| `rdc config field set --pointer <pointer>` (campo sensível, sem `--current`) | 🔴 recusado | Forneça `--current "<valor antigo>"` |
| `rdc config field get --pointer <pointer> --reveal` | 🔴 recusado | Use `--digest` em alternativa |
| `rdc config show --reveal` | 🔴 recusado | Use `rdc config show` sem flags |
| `rdc config edit` (editor interativo) | 🔴 recusado | O utilizador define `REDIACC_ALLOW_CONFIG_EDIT=*` antes de iniciar o agente |
| `rdc config edit --apply <file>` | 🔴 recusado | Mesmo override |
| `rdc config field rotate --pointer <pointer>` | 🔴 recusado | Mesmo override; usa confirmação interativa |
| `rdc term connect -m <machine>` (SSH direto à máquina) | 🔴 recusado | Crie um fork do repositório primeiro e ligue-se ao fork |

Tudo o que é recusado a um agente é registado no log de auditoria com `outcome: refused` e um motivo.

## Como os agentes são detetados

O CLI trata um processo como agente quando qualquer uma destas condições for verdadeira:

- Uma das variáveis `REDIACC_AGENT`, `CLAUDECODE`, `GEMINI_CLI`, `COPILOT_CLI` está definida como `"1"`, ou `CURSOR_TRACE_ID` está definida com qualquer valor.
- No Linux: qualquer processo pai na cadeia de ancestralidade tem uma dessas variáveis no seu ambiente (via `/proc/<pid>/environ`). Mesmo que o agente anule as suas próprias variáveis com `env -i` ou um script wrapper, a cadeia de ancestralidade continua a informar o CLI sobre quem o iniciou.

A deteção é executada uma vez por processo e fica em cache. Não pode ser desativada.

## O modelo de knowledge-gate

As mutações sensíveis seguem a convenção do `passwd(1)`: para alterar um segredo, prove que já o conhecia. **Simétrico para humanos e agentes**. Ambos passam pelo mesmo controlo. Não existe um bypass de "estou ao teclado".

- Pretende rodar um token de API armazenado em `/credentials/cfDnsApiToken`?
- O CLI pergunta: "qual é o valor atual?"
- O agente (ou utilizador) fornece o texto simples via `--current "$OLD"`. O CLI faz o hash de `$OLD` com SHA-256 e compara com o digest do valor atualmente armazenado. Coincidência: a escrita é executada. Não coincidência: recusado, auditado.
- Para rodar sem verificar o valor anterior, passe `--rotate-secret` (mutuamente exclusivo com `--current`). Isto fica auditado como uma rotação.

O modelo fecha três superfícies de ataque:

1. **Rotação silenciosa**: um chamador (agente ou utilizador) sem acesso prévio a `$OLD` não pode substituí-lo por um valor seu.
2. **Exfiltração por sondagem**: a resposta de digest nunca contém texto simples; mesmo um log de auditoria comprometido mostra `expected abc12345…, got deadbeef…`, e não os valores subjacentes.
3. **Substituição acidental da configuração de produção**: requer `--current` deliberado a cada vez, mesmo num TTY. Apanha o erro "pretendia definir STRIPE_TEST mas estou no shell de produção".

### Sugestões de próxima ação estruturadas

Quando a pré-condição falha, o envelope JSON (`--output json`) inclui um campo `errors[].next` estruturado que indica aos agentes exatamente o que sugerir ao utilizador:

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

**Os agentes devem transmitir `next.options[].run` literalmente ao utilizador em vez de sintetizarem os seus próprios comandos.** Isto evita o modo de falha "o agente inventa um comando que não existe" e mantém o operador no controlo da ação real.

### Exemplo prático

```bash
# Descobrir o digest curto do stub de redação (seguro para agentes).
$ rdc config field get --pointer /credentials/cfDnsApiToken
{"pointer": "/credentials/cfDnsApiToken", "value": "<redacted:secret>:abc12345"}

# Tentar substituir sem prova: recusado.
$ rdc config field set --pointer /credentials/cfDnsApiToken --new '"agent-picked-value"'
✗ Precondition failed: sensitive path requires --current (or --rotate-secret)

# Fornecer o texto simples atual: permitido.
$ rdc config field set --pointer /credentials/cfDnsApiToken \
    --current "$OLD_CF_TOKEN" \
    --new   "$NEW_CF_TOKEN"
Set /credentials/cfDnsApiToken
```

Se o agente nunca teve acesso a `$OLD_CF_TOKEN`, não consegue satisfazer a pré-condição e a rotação é recusada. O utilizador que o *tem* pode ainda fazê-lo através do editor ou passando `--current` a partir do seu shell.

## Redação por omissão

Todos os comandos `rdc` que leem estado sensível: `config show`, `config field get`, `config machine list`, `config edit --dump`: devolvem **stubs de redação** para campos secretos, e não texto simples:

```
"sshKey":       "<redacted:credential>:9f3a2c1b"
"cfDnsApiToken":"<redacted:secret>:abc12345"
"storages.s3-prod.vaultContent": "<redacted:secret>:1f2e3d4c"
```

O sufixo hexadecimal de 8 caracteres do stub são os primeiros 8 caracteres de `sha256(canonicalize(value))`: suficiente para distinguir dois valores diferentes à primeira vista, insuficiente para reverter. Um agente pode usar um stub para acompanhar se um valor mudou sem nunca o ver.

`--reveal` remove a redação para utilizadores humanos num TTY interativo. Os agentes são recusados independentemente do estado do TTY. Cada concessão escreve uma entrada de auditoria `reveal_granted`; cada recusa escreve uma entrada `refused` com os sinais de agente do ator anexados.

## O override `REDIACC_ALLOW_CONFIG_EDIT`

Algumas operações: o editor interativo, `--apply`, `field rotate`: existem para utilizadores humanos e não têm um caminho seguro para agentes. Se pretender ativamente que um agente execute uma delas, defina:

```bash
export REDIACC_ALLOW_CONFIG_EDIT='*'          # bypass completo
# ou
export REDIACC_ALLOW_CONFIG_EDIT='/credentials/ssh/privateKey,/infra/cfDnsZoneId'
# (globs de âmbito separados por vírgulas: wildcards * permitidos por segmento)
```

...e o agente herda-o.

**Detalhe crucial**: o override deve aparecer num processo **acima** do agente na cadeia de ancestralidade. Se o agente o definir no seu próprio ambiente (ou num subshell que criou), o CLI recusa e informa:

> `Interactive editor is blocked in agent environments (REDIACC_ALLOW_CONFIG_EDIT was set but ancestry verification failed: the override must be set by your shell, not by an agent).`

O efeito: um agente não consegue contornar um controlo executando `export REDIACC_ALLOW_CONFIG_EDIT='*'` a meio da sessão. Apenas um processo pai (você, no seu terminal, antes de iniciar o agente) pode abrir essa porta.

## Suporte de plataforma: apenas Linux para os overrides

`REDIACC_ALLOW_CONFIG_EDIT` e `REDIACC_ALLOW_GRAND_REPO` dependem da verificação de ancestralidade para provar que o override foi definido por si e não injetado pelo agente. A verificação lê `/proc/<pid>/environ` para cada processo na cadeia. Esse ficheiro é definido pelo kernel no momento do exec e não pode ser modificado pelo próprio processo, pelo que o ambiente do shell pai é uma testemunha inviolável.

Esse ficheiro não existe no macOS ou no Windows. Sem forma de verificar a legitimidade, o CLI falha de forma fechada. Mesmo quando define o override corretamente no seu shell antes de iniciar o agente, o override é rejeitado. A mensagem de erro indica exatamente o que fazer:

> The REDIACC_ALLOW_GRAND_REPO override is not supported on darwin. This override only works on Linux. On Windows and macOS, agents must use the fork-first workflow. … To use the override, run your agent on Linux (directly, WSL, Docker, or a VM).

Na prática, os utilizadores não-Linux não têm escape do fluxo fork-first. Isso é intencional. Os agentes são forçados através de uma sandbox que não conseguem contornar, independentemente de como foram instruídos. Execute o seu agente dentro do WSL, de um contentor Linux ou de uma VM Linux se precisar do override; caso contrário, trabalhe num fork.

## Registo de auditoria

Cada mutação, cada recusa, cada concessão de `--reveal` escreve uma linha JSONL em `~/.config/rediacc/audit.log.jsonl` (modo `0600`, rotado a 10 MB). Cada linha está encadeada por hash: o seu campo `prevHash` é `sha256("<linha anterior>")`. Qualquer adulteração de uma linha quebra a cadeia em todas as linhas seguintes.

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

# Apenas entradas originadas por agentes
rdc config audit log --actor agent

# Transmitir novas entradas em tempo real (Ctrl+C para parar)
rdc config audit tail

# Verificar se a cadeia de hashes está intacta
rdc config audit verify
# → "Chain integrity verified across 247 entries."
#   OU
# → "Chain broken at line 103: file has been tampered with or corrupted."
```

### O que nunca aparece no registo de auditoria

- Valores de segredos em texto simples
- Passphrases, tokens, chaves SSH
- Os valores antigos/novos numa incompatibilidade de pré-condição `--current` (apenas o prefixo digest de 8 caracteres)

O registo é seguro para partilhar com um revisor de segurança ou anexar a um relatório de erro.

## Limites do modelo comportamental

Os controlos dos agentes são **comportamentais, não criptográficos**. Um agente determinado ou instruído que corra com o mesmo UID do ficheiro de configuração pode sempre executar `cat ~/.config/rediacc/rediacc.json` e ler o texto simples, porque o ficheiro é legível pelo processo.

Para aplicação criptográfica real, use o [armazenamento de configuração encriptado](/en/docs/config-storage): os segredos residem no servidor, cada campo sensível tem um compromisso HMAC por campo, e o account worker recusa escritas cujo `--current` não corresponda ao hash armazenado. O servidor nunca vê o texto simples: zero-knowledge: mas aplica o controlo.

O caminho de ficheiro local é "o caminho fácil é seguro". O caminho de armazenamento remoto é "o caminho difícil também é difícil".

## O que a Rediacc não isola

Os controlos dos agentes desta página protegem a infraestrutura própria da Rediacc: o ficheiro de configuração, o daemon Docker por repositório, os dados encriptados com LUKS, a sandbox SSH com âmbito. Não protegem serviços externos para os quais o seu repositório detém credenciais.

Um fork de repositório é um reflink BTRFS do volume do pai. Tudo o que existe no disco no pai é byte a byte idêntico no fork: código, dados e ficheiros `.env`. Se o seu repositório contiver uma `STRIPE_LIVE_KEY`, um `AWS_ACCESS_KEY_ID`, um token de API da Railway ou qualquer outra credencial de longa duração para um serviço de terceiros, o fork herda-a. Um agente que opere na sandbox do fork pode ler esse ficheiro, exfiltrar o valor ou usá-lo para chamar a API do terceiro. O serviço terceiro não tem forma de saber que a chamada veio de um fork em vez de produção.

Esta é a linha de responsabilidade partilhada:

| Fronteira | Responsável |
|---|---|
| Dados do repositório, namespace de mount, âmbito Docker, controlos do agente, registo de auditoria, injeção de segredos em tempo de implementação | Rediacc |
| Código da aplicação que usa esses segredos, e quaisquer credenciais incorporadas na imagem no momento da construção | Programador do repositório |

A principal mitigação está incorporada: **[segredos por repositório](/en/docs/repositories#secrets)** são armazenados num plano separado da imagem encriptada do repositório e não são copiados através da fronteira do fork. Os contentores de um fork arrancam com um mapa de segredos vazio e identificam-se como um principal externo diferente do pai. Defina-os com `rdc repo secret set` (modo env para interpolação do compose, modo file para blocos `secrets:` em tmpfs). O mutation gate é simétrico. Humanos e agentes têm de fornecer igualmente `--current` (pré-condição estilo passwd) ou `--rotate-secret` (rotação auditada) para substituir ou eliminar um valor existente.

**O isolamento entre repositórios é aplicado.** Um ficheiro compose malicioso ou descuidado no repositório B não pode referenciar o diretório de segredos do repositório A. O validador de compose do Renet rejeita categoricamente qualquer caminho `secrets: file:`, `configs: file:` ou `env_file:` que aponte para fora do diretório `${REDIACC_NETWORK_ID}` do repositório atual, e a rejeição NÃO é substituível por `--unsafe`. Defesa em profundidade: a sandbox Landlock em torno do subprocesso bash do Rediaccfile limita as leituras do sistema de ficheiros apenas ao diretório de segredos da rede atual, pelo que um `cat /var/run/rediacc/secrets/<other>/X` de um Rediaccfile malicioso falha com EACCES ao nível do kernel.

Dois padrões adicionais fecham casos extremos:

1. **Não incorpore credenciais de produção no próprio sistema de ficheiros do repositório.** Um ficheiro `.env` incorporado na imagem, ou uma credencial persistida num volume durante `up()`, é reflinked no fork. A funcionalidade de segredos por repositório só protege os valores que mantém no plano de segredos. Não pode proteger retroativamente bytes que já vivem dentro da imagem LUKS. Para repositórios existentes com ficheiros `.env` incorporados, mova-os manualmente para segredos por repositório.
2. **Restrinja a rede de saída do fork com filtragem de egress eBPF** para que o fork só possa alcançar localhost e endpoints explícitos de sandbox. O isolamento de rede por repositório da Rediacc é a base; as allowlists de egress por fork não estão construídas hoje, mas o caminho está aberto.

A Rediacc trata da injeção em tempo de implementação, do isolamento entre forks e do isolamento entre repositórios. A parte "não incorporar na imagem" é da sua responsabilidade.

## Receitas rápidas

### Permitir que um agente rode um único token cloud

```bash
# Como você, antes de iniciar o agente:
export REDIACC_ALLOW_CONFIG_EDIT='/credentials/cfDnsApiToken'
claude-code              # ou cursor, gemini, etc.
```

Agora o agente pode executar `config field rotate /credentials/cfDnsApiToken --new ...` mas continua sem poder editar `/credentials/ssh/privateKey` ou abrir o editor interativo.

### Permitir que um agente faça uma sessão de edição de configuração ampla

```bash
export REDIACC_ALLOW_CONFIG_EDIT='*'
claude-code
```

O agente pode abrir `rdc config edit`, usar `--reveal` e executar `field rotate`. Cada ação continua a ser registada em auditoria com `actor.kind: agent` e o sinal `CLAUDECODE`.

### Descobrir quais campos um agente tem permissão para tocar

```bash
rdc config field list --sensitive --output json
```

Devolve cada template de pointer, o seu tipo (`secret` / `credential` / `pii` / `identifier`), e se está comprometido com o envelope HMAC do lado do servidor.

## Ver também

- [Visão Geral da Integração com Agentes de IA](/en/docs/ai-agents-overview): a visita geral de nível superior
- [Configuração do Claude Code](/en/docs/ai-agents-claude-code): template de integração
- [Envelope de saída JSON](/en/docs/ai-agents-json-output): respostas legíveis por máquina
- [Armazenamento de configuração encriptado](/en/docs/config-storage): aplicação criptográfica do lado do servidor
- [Segurança da conta](/en/docs/account-security): postura de segurança orientada ao operador
