---
title: "Canais de Versão"
description: "Compreender os canais de versão Edge e Stable, as suas diferenças e como escolher."
category: "Concepts"
order: 2
language: pt
---

O Rediacc publica atualizações através de dois canais de versão: **Stable** e **Edge**. Cada canal serve um público diferente e tem diferentes compromissos.

## Canal Stable

O Stable é o canal predefinido para todos os utilizadores. As versões são promovidas a partir do Edge após um período de maturação de 7 dias sem problemas reportados.

- Recomendado quando prefere uma cadência de atualização conservadora e quer acesso a planos pagos
- Implementado após 7 dias de testes no Edge
- Correções críticas podem ser enviadas diretamente quando necessário
- Domínios: `eu.rediacc.com`, `us.rediacc.com`, `asia.rediacc.com`

## Canal Edge

O Edge recebe cada alteração imediatamente após ser integrada no ramo principal. É a versão mais recente do software, implementada de forma contínua.

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

Os utilizadores do Edge no plano Community recebem limites de recursos duplicados sem custo adicional:

| Recurso | Community Stable | Community Edge |
|---|---|---|
| Tamanho do repositório | 10 GB | 20 GB |
| Emissões de licença por mês | 500 | 1.000 |
| Ativações de máquina | 2 | 4 |

Se precisar de limites mais elevados ou funcionalidades de planos pagos, crie uma conta no canal Stable e faça a atualização aí.

## Contas Separadas

O Edge e o Stable funcionam em infraestrutura separada com bases de dados separadas. Uma conta criada no Edge não existe no Stable, e vice-versa. Não há caminho de migração entre canais. Se começar no Edge e posteriormente quiser um plano pago, precisará de criar uma nova conta no Stable.

## Como Funcionam as Promoções

1. Cada integração no ramo principal é implementada imediatamente no Edge.
2. Após 7 dias sem problemas, o Edge é promovido automaticamente para Stable.
3. Correções críticas podem ser enviadas para ambos os canais simultaneamente.

Isto significa que o Stable está sempre no máximo 7 dias atrás do Edge. O período de maturação deteta regressões antes de se propagarem do Edge para o Stable.

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

Consulte [Instalação](/pt/docs/installation) para comandos de instalação a partir de qualquer canal, incluindo configuração de gestor de pacotes e etiquetas Docker.

## Gestão do Canal do CLI

O CLI utiliza automaticamente o canal configurado durante a instalação ou início de sessão. Para mudar de canal:

```bash
rdc update --channel edge      # Mudar para Edge
rdc update --channel stable    # Mudar para Stable
```

Quando executa `rdc subscription login` e seleciona uma região Edge, o CLI configura automaticamente o canal de atualização Edge. Não é necessária a flag `--channel` manualmente.
