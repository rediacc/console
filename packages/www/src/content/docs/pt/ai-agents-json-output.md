---
title: Referência de Saída JSON
description: Referência completa para o formato de saída JSON da CLI rdc, esquema do envelope, tratamento de erros e comandos de descoberta para agentes.
category: Reference
tags:
  - ai-agents
  - cli
order: 51
language: pt
sourceHash: "36ba86893c3817ac"
sourceCommit: "23543669cd22bce3f14d69a0886bac8a12061412"
---

Todos os comandos `rdc` produzem JSON estruturado. Encaminhe para um script ou passe diretamente a um agente.

## Ativar Saída JSON

### Flag Explícita

```bash
rdc machine status prod-1 --output json
rdc machine status prod-1 -o json
```

### Deteção Automática

Quando o `rdc` é executado num ambiente não-TTY (canalizado, subshell ou lançado por um agente de IA), a saída muda automaticamente para JSON. Não é necessária nenhuma flag.

```bash
# Produz JSON automaticamente
result=$(rdc machine status prod-1)
```

## Envelope JSON

Cada resposta JSON usa um envelope consistente:

```json
{
  "success": true,
  "command": "machine query",
  "data": {
    "name": "prod-1",
    "status": "running",
    "repositories": []
  },
  "errors": null,
  "warnings": [],
  "metrics": {
    "duration_ms": 142
  }
}
```

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `success` | `boolean` | Se o comando foi concluído com sucesso |
| `command` | `string` | O caminho completo do comando (ex., `"machine query"`, `"repo up"`) |
| `data` | `object \| array \| null` | Payload específico do comando em caso de sucesso, `null` em caso de erro |
| `errors` | `array \| null` | Objetos de erro em caso de falha, `null` em caso de sucesso |
| `warnings` | `string[]` | Avisos não fatais recolhidos durante a execução |
| `metrics` | `object` | Metadados de execução |

## Respostas de Erro

Os comandos falhados devolvem erros estruturados com sugestões de recuperação:

```json
{
  "success": false,
  "command": "machine query",
  "data": null,
  "errors": [
    {
      "code": "NOT_FOUND",
      "message": "Machine \"prod-2\" not found",
      "retryable": false,
      "guidance": "Verify the resource name with \"rdc machine status\" or \"rdc repo list\""
    }
  ],
  "warnings": [],
  "metrics": {
    "duration_ms": 12
  }
}
```

### Campos de Erro

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `code` | `string` | Código de erro legível por máquina (consulte as constantes `ERROR_CODES` para a lista canónica) |
| `message` | `string` | Descrição legível por humanos |
| `retryable` | `boolean` | Se repetir o mesmo comando pode ter sucesso |
| `guidance` | `string` | Sugestão em texto livre (legado. Prefira `next` para dados de ação estruturados) |
| `next` | `object?` | Sugestão de próxima ação estruturada (quando presente). Ver abaixo |

### Sugestões de ação `next` estruturadas

Para códigos de erro de alto valor como `PRECONDITION_MISMATCH`, o erro inclui um campo `next` com os comandos exatos a apresentar ao utilizador. Nem todos os códigos de erro incluem este campo. Apenas aqueles com um caminho de recuperação definido. **Os agentes devem transmitir `next.options[].run` literalmente ao ser humano, em vez de sintetizarem o seu próprio comando.** Isto evita o modo de falha em que o agente inventa um comando que não existe. Acontece mais do que se pensa.

```json
{
  "errors": [{
    "code": "PRECONDITION_MISMATCH",
    "message": "--current digest mismatch (expected 3264f8ee…, got 611dfd8a…)",
    "next": {
      "summary": "Provide the current value or acknowledge rotation.",
      "options": [
        {
          "description": "Re-read current digest, then retry with --current",
          "run": "rdc repo secret get mail --key STRIPE_KEY"
        },
        {
          "description": "Skip the precondition (rotation, audited)",
          "run": "rdc repo secret set mail --key STRIPE_KEY --value <new> --mode file --rotate-secret"
        }
      ]
    }
  }]
}
```

Esquema:

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `next.summary` | `string` | Descrição numa linha do que o utilizador precisa de decidir |
| `next.options[]` | `array` | Ações concretas; cada uma é uma alternativa que o utilizador pode escolher |
| `next.options[].description` | `string` | Explicação legível por humanos desta opção |
| `next.options[].run` | `string` | Comando CLI exato. Transmitir literalmente ao utilizador |

### Erros com Possibilidade de Repetição

Estes tipos de erro são marcados como `retryable: true`:

- **NETWORK_ERROR**, falha de ligação SSH ou de rede
- **RATE_LIMITED**, demasiados pedidos, aguardar e repetir
- **API_ERROR**, falha transitória do backend

Os erros não repetíveis (autenticação, não encontrado, argumentos inválidos) requerem ação corretiva antes de repetir.

## Filtrar Saída

Use `--fields` para limitar a saída a chaves específicas e reduzir o uso de tokens:

```bash
rdc machine status prod-1 --containers -o json --fields name,status,repository
```

## Saída de Dry-Run

Os comandos destrutivos suportam `--dry-run` para pré-visualizar o que aconteceria:

```bash
rdc repo delete mail@prod-1 --dry-run -o json
```

```json
{
  "success": true,
  "command": "repo delete",
  "data": {
    "dryRun": true,
    "repository": "mail",
    "machine": "prod-1",
    "guid": "a1b2c3d4-..."
  },
  "errors": null,
  "warnings": [],
  "metrics": {
    "duration_ms": 8
  }
}
```

Comandos com suporte a `--dry-run`: `repo up`, `repo down`, `repo delete`, `snapshot delete`, `sync upload`, `sync download`.

## Exemplos de Análise

### Shell (jq)

```bash
status=$(rdc machine status prod-1 -o json | jq -r '.data.status')
```

### Python

```python
import subprocess, json

result = subprocess.run(
    ["rdc", "machine", "query", "--name", "prod-1", "-o", "json"],
    capture_output=True, text=True
)
envelope = json.loads(result.stdout)

if envelope["success"]:
    print(envelope["data"]["status"])
else:
    error = envelope["errors"][0]
    if error["retryable"]:
        # retry logic
        pass
    else:
        print(f"Error: {error['message']}")
        print(f"Fix: {error['guidance']}")
```

### Node.js

```javascript
import { execFileSync } from 'child_process';

const raw = execFileSync('rdc', ['machine', 'query', '--name', 'prod-1', '-o', 'json'], { encoding: 'utf-8' });
const { success, data, errors } = JSON.parse(raw);

if (!success) {
  const { message, retryable, guidance } = errors[0];
  throw new Error(`${message} (retryable: ${retryable}, fix: ${guidance})`);
}
```
