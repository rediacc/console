---
title: "Canais de Versão"
description: "Como o Edge e o Stable diferem, e qual canal executar."
category: "Concepts"
order: 2
language: pt
sourceHash: "5fdcb0e8944f5d60"
sourceCommit: "4e60a12e0664cdee5ad9079a7b75e2d05980d0f5"
---

O Rediacc distribui atualizações através de dois canais: **Stable** e **Edge**. Correm em infraestrutura separada e têm diferentes compromissos.

## Canal Stable

O Stable é o canal predefinido. Uma versão só chega a ele depois de ter estado no Edge durante 7 dias sem problemas reportados.

- Recomendado quando prefere uma cadência de atualização conservadora e quer acesso a planos pagos
- Implementado após 7 dias de testes no Edge
- Correções críticas podem ser enviadas diretamente quando necessário
- Domínios: `eu.rediacc.com`, `us.rediacc.com`, `asia.rediacc.com`

## Canal Edge

O Edge recebe cada alteração no momento em que é integrada no ramo principal. É a versão em produção do software, implementada de forma contínua.

- Produção implementada continuamente, lançada a cada integração no ramo principal
- Limites do plano Community 2X (consulte a tabela abaixo)
- Gratuito para sempre. Não há planos pagos disponíveis no Edge.
- Contas separadas do Stable. Os dados não transitam entre canais.
- Domínios: `edge-eu.rediacc.com`, `edge-us.rediacc.com`, `edge-asia.rediacc.com`

## Comparação

| | Stable | Edge |
|---|---|---|
| **Cadência de implementação** | Após maturação de 7 dias | A cada integração no ramo principal |
| **Estabilidade** | Testado durante 7 dias | Produção, implementado continuamente |
| **Limites do plano Community** | Repositórios de 10 GB, 500 emissões/mês, 2 máquinas | Repositórios de 20 GB, 1.000 emissões/mês, 4 máquinas |
| **Planos pagos** | Disponíveis (Professional, Business, Enterprise) | Não disponíveis |
| **Contas** | Independentes | Independentes (separadas do Stable) |
| **Melhor para** | Produção, cargas de trabalho pagas | Produção, projetos pessoais, acesso antecipado |

## Limites 2X do Edge

Execute o Edge no plano Community e os seus limites de recursos duplicam, sem custo adicional:

| Recurso | Community Stable | Community Edge |
|---|---|---|
| Tamanho do repositório | 10 GB | 20 GB |
| Emissões de licença por mês | 500 | 1.000 |
| Ativações de máquina | 2 | 4 |

Precisa de limites mais elevados ou funcionalidades pagas? Crie a sua conta no Stable e faça a atualização aí.

## Contas Separadas

O Edge e o Stable funcionam em infraestrutura separada com bases de dados separadas. Uma conta num canal não existe no outro, e não há caminho de migração. Começou no Edge, depois decidiu que quer um plano pago, e terá de criar uma conta nova no Stable do zero.

## Como Funcionam as Promoções

1. Cada integração no ramo principal é implementada imediatamente no Edge.
2. Após 7 dias sem problemas, o Edge é promovido automaticamente para Stable.
3. Correções críticas podem ser enviadas para ambos os canais simultaneamente.

Portanto, o Stable atrasa o Edge no máximo 7 dias. A janela de maturação deteta regressões no Edge antes de chegarem ao Stable.

## Qual Canal Devo Escolher?

**Escolha Stable se:**
- Prefere uma cadência de atualização conservadora com uma janela de maturação de 7 dias
- Precisa de planos pagos (Professional, Business, Enterprise)
- Prefere máxima fiabilidade em detrimento das funcionalidades mais recentes

**Escolha Edge se:**
- Quer experimentar novas funcionalidades mais cedo
- Está a avaliar a plataforma
- Quer limites gratuitos generosos para projetos pessoais
- Está confortável com código mais recente e menos testado

## Instalação

Consulte [Instalação](/pt/docs/installation) para os comandos de instalação, configuração de gestor de pacotes e etiquetas Docker para cada canal.

## Gestão do Canal do CLI

O CLI utiliza o canal que configurou na instalação ou no início de sessão. Para mudar:

```bash
rdc update --channel edge      # Mudar para Edge
rdc update --channel stable    # Mudar para Stable
```

Execute `rdc subscription login` e escolha uma região Edge, e o CLI define o canal de atualização Edge automaticamente. Não é necessária a flag `--channel`.
