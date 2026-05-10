---
title: Guia de Configuração do Claude Code
description: Guia passo a passo para configurar o Claude Code para a gestão autónoma da infraestrutura Rediacc.
category: Guides
order: 31
language: pt
---

O Claude Code funciona nativamente com o Rediacc através da CLI `rdc`. Este guia abrange a configuração, permissões e fluxos de trabalho comuns.

> **Segurança em primeiro lugar**: Antes de ligar um agente a qualquer coisa que toque em segredos, leia [Segurança e Salvaguardas de Agentes de IA](/en/docs/ai-agents-safety). O Claude Code a correr sob `rdc` é detetado como agente. As mutações sensíveis requerem `--current <previous-value>` (pré-condição no estilo passwd) ou `--rotate-secret` (rotação reconhecida, auditada). Simétrico para humanos e agentes. O editor interativo, `--reveal` e o SSH direto à máquina são recusados por omissão, exceto se os abrir explicitamente via `REDIACC_ALLOW_CONFIG_EDIT`. Quando uma pré-condição falha, o campo `errors[].next.options[].run` do envelope JSON indica ao agente o comando CLI exato a sugerir ao utilizador. Transmita-o literalmente.

## Configuração Rápida

1. Instalar a CLI: `curl -fsSL https://www.rediacc.com/install.sh | bash`
2. Copiar o [modelo AGENTS.md](/en/docs/agents-md-template) para a raiz do projeto como `CLAUDE.md`
3. Iniciar o Claude Code no diretório do projeto

O Claude Code lê o `CLAUDE.md` no arranque e usa-o como contexto persistente para todas as interações.

## Configuração do CLAUDE.md

Coloque este ficheiro na raiz do projeto. Consulte o [modelo AGENTS.md](/en/docs/agents-md-template) completo para uma versão completa. Secções principais:

```markdown
# Rediacc Infrastructure

## CLI Tool: rdc

### Common Operations
- Status: rdc machine query --name <machine> -o json
- Deploy: rdc repo up --name <repo> -m <machine> --yes
- Containers: rdc machine containers --name <machine> -o json
- Health: rdc machine health --name <machine> -o json
- SSH: rdc term connect -m <machine> [-r <repo>]

### Rules
- Always use --output json when parsing output
- Always use --yes for automated confirmations
- Use --dry-run before destructive operations
```

## Permissões de Ferramentas

O Claude Code solicitará permissão para executar comandos `rdc`. Pode pré-autorizar operações comuns adicionando às suas definições do Claude Code:

- Permitir `rdc machine query *`, verificações de estado apenas de leitura
- Permitir `rdc machine containers *`, listagem de contentores
- Permitir `rdc machine health *`, verificações de saúde
- Permitir `rdc config repository list`, listagem de repositórios

Para operações destrutivas (`rdc repo up`, `rdc repo delete`), o Claude Code pedirá sempre confirmação, exceto se as autorizar explicitamente.

## Exemplos de Fluxos de Trabalho

### Verificar o Estado da Infraestrutura

```
Você: "Qual é o estado de prod-1?"

Claude Code executa: rdc machine query --name prod-1 -o json
→ Mostra o estado da máquina, repositórios, contentores, serviços
```

### Implementar um Repositório

```
Você: "Implementar o repositório mail em prod-1"

Claude Code executa: rdc repo up --name mail -m prod-1 --dry-run -o json
→ Mostra o que aconteceria
Claude Code executa: rdc repo up --name mail -m prod-1 --yes
→ Implementa o repositório
```

### Diagnosticar Problemas de Contentores

```
Você: "Porque é que o contentor nextcloud está com problemas de saúde?"

Claude Code executa: rdc machine containers --name prod-1 -o json --fields name,status,repository
→ Lista os estados dos contentores
Claude Code executa: rdc term connect -m prod-1 -c "docker logs nextcloud-app --tail 50"
→ Verifica os registos recentes
```

### Sincronização de Ficheiros

```
Você: "Carregar a configuração local para o repositório mail"

Claude Code executa: rdc repo sync upload -m prod-1 -r mail -l ./config --dry-run
→ Mostra os ficheiros que seriam sincronizados
Claude Code executa: rdc repo sync upload -m prod-1 -r mail -l ./config
→ Sincroniza os ficheiros
```

## Dicas

- O Claude Code deteta automaticamente ambientes não-TTY e muda para saída JSON; não é necessário especificar `-o json` na maioria dos casos
- Use `rdc agent capabilities` para permitir que o Claude Code descubra todos os comandos disponíveis
- Use `rdc agent schema "command name"` para informação detalhada sobre argumentos e opções
- A flag `--fields` ajuda a manter baixo o uso da janela de contexto quando só precisa de dados específicos
