---
title: Visão Geral da Integração com Agentes de IA
description: Como assistentes de programação com IA, como o Claude Code, o Cursor e o Cline, se integram com a infraestrutura Rediacc para implementação e gestão autónomas.
category: Guides
order: 30
language: pt
---

Os assistentes de programação com IA podem gerir a infraestrutura Rediacc de forma autónoma através do CLI `rdc`. Este guia aborda as abordagens de integração e como começar.

## Por Que Self-Hosted + Agentes de IA

A arquitetura da Rediacc é naturalmente compatível com agentes:

- **CLI-first**: Todas as operações são comandos `rdc`, sem necessidade de interface gráfica
- **Baseado em SSH**: O protocolo que os agentes conhecem melhor a partir dos dados de treino
- **Saída JSON**: Todos os comandos suportam `--output json` com um envelope consistente
- **Isolamento Docker**: Cada repositório tem o seu próprio daemon e namespace de rede
- **Scriptável**: `--yes` ignora confirmações, `--dry-run` pré-visualiza operações destrutivas

## Abordagens de Integração

### 1. Template AGENTS.md / CLAUDE.md

A forma mais rápida de começar. Copie o nosso [template AGENTS.md](/en/docs/agents-md-template) para a raiz do seu projeto:

- `CLAUDE.md` para o Claude Code
- `.cursorrules` para o Cursor
- `.windsurfrules` para o Windsurf

Isto fornece ao agente contexto completo sobre os comandos disponíveis, a arquitetura e as convenções.

### 2. Pipeline de Saída JSON

Quando os agentes chamam `rdc` num subshell, a saída muda automaticamente para JSON (deteção de não-TTY). Todas as respostas JSON usam um envelope consistente:

```json
{
  "success": true,
  "command": "machine query",
  "data": { ... },
  "errors": null,
  "warnings": [],
  "metrics": { "duration_ms": 42 }
}
```

As respostas de erro incluem os campos `retryable` e `guidance`:

```json
{
  "success": false,
  "errors": [{
    "code": "NOT_FOUND",
    "message": "Machine \"prod-2\" not found",
    "retryable": false,
    "guidance": "Verify the resource name with \"rdc machine query\" or \"rdc config repository list\""
  }]
}
```

### 3. Descoberta de Capacidades do Agente

O subcomando `rdc agent` fornece introspeção estruturada:

```bash
# Listar todos os comandos com argumentos e opções
rdc agent capabilities

# Mostrar o esquema detalhado de um comando específico
rdc agent schema --command "machine query"

# Executar um comando com stdin JSON
echo '{"name": "prod-1"}' | rdc agent exec "machine query"
```

## Flags Principais para Agentes

| Flag | Finalidade |
|------|---------|
| `--output json` / `-o json` | Saída JSON legível por máquina |
| `--yes` / `-y` | Ignorar confirmações interativas |
| `--quiet` / `-q` | Suprimir saída informativa para stderr |
| `--fields name,status` | Limitar a saída a campos específicos |
| `--dry-run` | Pré-visualizar operações destrutivas sem as executar |

## Segurança e Controlos

O CLI trata os agentes de IA de forma diferente dos utilizadores humanos. As operações sensíveis requerem prova de conhecimento prévio (a flag `--current`), os fluxos de editor interativo são recusados por omissão, e cada recusa é registada em auditoria. A referência [Segurança e Controlos para Agentes de IA](/en/docs/ai-agents-safety) cobre a tabela completa de firewall, o modelo de knowledge-gate, o scope-override `REDIACC_ALLOW_CONFIG_EDIT`, e o registo de auditoria com cadeia de hashes.

## Próximos Passos

- [Segurança e Controlos para Agentes de IA](/en/docs/ai-agents-safety), O que os agentes podem e não podem fazer, knowledge-gate, registo de auditoria
- [Guia de Configuração do Claude Code](/en/docs/ai-agents-claude-code), Configuração passo a passo do Claude Code
- [Guia de Configuração do Cursor](/en/docs/ai-agents-cursor), Integração com o Cursor IDE
- [Referência de Saída JSON](/en/docs/ai-agents-json-output), Documentação completa da saída JSON
- [Template AGENTS.md](/en/docs/agents-md-template), Template de configuração de agente pronto a copiar
