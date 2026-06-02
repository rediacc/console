---
title: Segurança da Conta e API
description: Autenticação, tokens de API, gestão de sessão e o modelo de permissões.
category: Guides
order: 13
language: pt
sourceHash: "dcd061b971573573"
sourceCommit: "4e60a12e0664cdee5ad9079a7b75e2d05980d0f5"
---

### Autenticação

O Rediacc suporta vários métodos de autenticação:

![Auth Flow](/img/account-auth-flow.svg)

- **Password**: Início de sessão tradicional com e-mail e palavra-passe
- **Magic Link**: Início de sessão sem palavra-passe via link por e-mail (expiração em 15 minutos)
- **Autenticação de Dois Fatores (2FA)**: Baseada em TOTP com códigos de recuperação

Quando a 2FA está ativada, o início de sessão requer tanto a palavra-passe (ou magic link) como um código TOTP de 6 dígitos.

### Tokens de API

Os tokens de API autenticam operações máquina-a-máquina (ativação de licenças da CLI, verificações de estado).

![API Token Lifecycle](/img/account-api-token-lifecycle.svg)

**Âmbitos:**
- `license:read` -- Consultar estado de subscrição e licença
- `license:activate` -- Ativar máquinas e emitir licenças de repositório
- `subscription:read` -- Ler detalhes da subscrição

**Funcionalidades de segurança:**
- Vinculação a IP: o primeiro pedido bloqueia o token nesse endereço IP
- Âmbito de equipa: os tokens podem ser restritos a uma equipa específica
- Revogação automática: os tokens são revogados quando o criador é removido da organização

Criar um token:
```bash
# Via portal: API Tokens > Create
# O valor do token é apresentado uma única vez -- guarde-o em segurança
```

### Fluxo de Código de Dispositivo

A CLI pode autenticar em máquinas sem interface gráfica usando o fluxo de código de dispositivo:

![Device Code Flow](/img/account-device-code-flow.svg)

```bash
rdc config remote enable --headless
# Apresenta: Enter code XXXX-XXXX-XX at https://www.rediacc.com/account/authorize
# Após aprovação, a CLI recebe as credenciais automaticamente
```

### Armazenamento de Configuração

Para configuração encriptada e sincronizada com o servidor, consulte [Armazenamento de Configuração](/en/docs/config-storage) para o guia completo. O armazenamento de configuração utiliza:
- Encriptação de conhecimento zero (o servidor nunca vê texto em claro)
- Derivação de chave baseada em passkey (WebAuthn + PRF)
- Tokens rotativos com rotação por pedido

### Segurança de Sessão

| Tipo de Token | Duração | Armazenamento | Renovação |
|---------------|---------|---------------|-----------|
| Token de Acesso (JWT) | 15 minutos | Cookie HttpOnly | Automática via token de renovação |
| Token de Renovação | 7 dias | Cookie HttpOnly | Rotativo em cada uso |
| Sessão Elevada | 10 minutos | Lado do servidor | Despoletada por reautenticação |

As sessões elevadas são necessárias para operações sensíveis: alterações de palavra-passe, alterações de e-mail, configuração de 2FA, transferências de propriedade e ações administrativas destrutivas.

### Modelo de Permissões

O Rediacc utiliza três camadas de permissões independentes:

![Permission Flow](/img/account-permission-flow.svg)

**Camada 1: Função de Sistema** -- Determina o acesso aos endpoints de administração do sistema.

**Camada 2: Função de Organização** -- Controla o que um utilizador pode fazer dentro da sua organização (proprietário, administrador, membro).

**Camada 3: Função de Equipa** -- Delimita o acesso a recursos específicos de equipa (team_admin, member). Os proprietários e administradores da organização ignoram as verificações de função de equipa.

Cada pedido de API passa por todas as camadas aplicáveis em sequência. Um pedido a um endpoint com âmbito de equipa deve satisfazer a autenticação de sessão, a adesão à organização e o acesso à equipa.

### Canais de Atualização

A CLI suporta dois canais de lançamento:
- **stable** (predefinido): Promovido a partir do edge após um período de 7 dias; escolha este para uma cadência de atualização conservadora
- **edge**: Produção com implementação contínua, atualizado a cada fusão para main

```bash
rdc update --channel edge      # Mudar para edge
rdc update --channel stable    # Voltar para stable
rdc update --status            # Mostrar canal atual
```

### Postura de Segurança da CLI para Agentes de IA

Os agentes de codificação que invocam o `rdc` são uma superfície de ameaça real, pelo que os tratamos como um principal separado. Cada invocação do `rdc` é classificada no arranque como **human** ou **agent** com base em sinais de ambiente (CLAUDECODE, GEMINI_CLI, COPILOT_CLI, CURSOR_TRACE_ID, REDIACC_AGENT) e uma travessia da árvore de processos `/proc` do Linux. A deteção é de melhor esforço. Um wrapper determinado pode falsificar variáveis de ambiente, razão pela qual a ancestralidade importa. Os agentes recebem um conjunto de permissões reduzido: as mutações de configuração sensíveis requerem o knowledge-gate (`--current <old>`), o editor interativo é recusado sem uma substituição `REDIACC_ALLOW_CONFIG_EDIT` verificada por ancestralidade, e `--reveal` em qualquer comando de exibição está bloqueado. Cada decisão (permitir, recusar ou conceder `--reveal`) escreve uma linha JSONL encadeada por hash em `~/.config/rediacc/audit.log.jsonl`. Execute `rdc config audit verify` para verificar a integridade da cadeia.

Consulte [Segurança e Salvaguardas de Agentes de IA](/en/docs/ai-agents-safety) para a matriz completa do que os agentes podem e não podem fazer, exemplos práticos do knowledge-gate e a mecânica de substituição de âmbito.
