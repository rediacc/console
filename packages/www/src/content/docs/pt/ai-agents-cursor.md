---
title: Guia de Configuração do Cursor
description: Configure o IDE Cursor para trabalhar com a infraestrutura Rediacc usando .cursorrules e integração com o terminal.
category: Guides
order: 32
language: pt
---

O Cursor integra-se com o Rediacc através de comandos no terminal e do ficheiro de configuração `.cursorrules`.

## Configuração Rápida

1. Instalar a CLI: `curl -fsSL https://www.rediacc.com/install.sh | bash`
2. Copiar o [modelo AGENTS.md](/en/docs/agents-md-template) para a raiz do projeto como `.cursorrules`
3. Abrir o projeto no Cursor

O Cursor lê o `.cursorrules` no arranque e usa-o como contexto para o desenvolvimento assistido por IA.

## Configuração do .cursorrules

Crie o `.cursorrules` na raiz do projeto com o contexto de infraestrutura Rediacc. Consulte o [modelo AGENTS.md](/en/docs/agents-md-template) completo para uma versão completa.

As secções principais a incluir:

- Nome da ferramenta CLI (`rdc`) e instalação
- Comandos comuns com a flag `--output json`
- Visão geral da arquitetura (isolamento de repositórios, daemons Docker)
- Regras de terminologia (adaptadores, não modos)

## Integração com o Terminal

O Cursor pode executar comandos `rdc` através do seu terminal integrado. Padrões comuns:

### Verificar Estado

Pergunte ao Cursor: *"Verifica o estado do meu servidor de produção"*

O Cursor executa no terminal:
```bash
rdc machine query --name prod-1 -o json
```

### Implementar Alterações

Pergunte ao Cursor: *"Implementa a configuração atualizada do nextcloud"*

O Cursor executa no terminal:
```bash
rdc repo up --name nextcloud -m prod-1 --yes
```

### Ver Registos

Pergunte ao Cursor: *"Mostra-me os registos recentes do contentor mail"*

O Cursor executa no terminal:
```bash
rdc term connect -m prod-1 -r mail -c "docker logs mail-postfix --tail 100"
```

## Definições de Espaço de Trabalho

Para projetos de equipa, adicione as definições específicas do Rediacc para o Cursor em `.cursor/settings.json`:

```json
{
  "terminal.defaultProfile": "bash",
  "ai.customInstructions": "Use rdc CLI for all infrastructure operations. Always use --output json when parsing results."
}
```

## Dicas

- O modo Composer do Cursor funciona bem para tarefas de infraestrutura com múltiplos passos
- Use `@terminal` no chat do Cursor para referenciar a saída recente do terminal
- O comando `rdc agent capabilities` fornece ao Cursor uma referência completa de comandos
- Combine `.cursorrules` com um ficheiro `CLAUDE.md` para máxima compatibilidade entre ferramentas de IA
