---
title: Gestão de Conta
description: Organizações, equipas, membros e subscrições no Rediacc.
category: Guides
order: 12
language: pt
sourceHash: "1a3458ba81b340d4"
sourceCommit: "8062f196566d6ba5f90b084e5484cf722b4bdf16"
---

### Organizações

Ao registar uma conta, o Rediacc cria automaticamente uma organização para si. Essa organização é o contentor de nível superior para tudo o que possui aqui: máquinas, repositórios, subscrições e as pessoas que convida. Não criará uma segunda por acidente. Existe exatamente uma organização por conta, e todas as equipas e recursos dependem dela.

![Registration Flow](/img/account-registration-flow.svg)

Cada organização tem:
- Um nome único (por omissão, o seu e-mail)
- Um plano de subscrição (começa com COMMUNITY)
- Uma equipa predefinida (todos os membros entram automaticamente)

### Membros e Funções

As organizações suportam três funções:

![Role Hierarchy](/img/account-role-hierarchy.svg)

| Função | Capacidades |
|--------|-------------|
| **Owner** | Controlo total: faturação, transferência de propriedade, gestão de todos os membros e equipas |
| **Admin** | Convidar e remover membros, criar e gerir equipas, revogar tokens de API |
| **Member** | Ver dados da organização, criar tokens de API, aceder às equipas atribuídas |

Convidar membros:
```bash
# A partir do portal: Organization > Members > Invite
# Ou via API
```

Quando um membro é removido, os seus tokens de API e tokens de armazenamento de configuração são revogados automaticamente.

### Equipas

As equipas permitem delimitar recursos dentro de uma organização. Cada organização começa com uma equipa predefinida.

![Team Structure](/img/account-team-structure.svg)

Funções de equipa:
- **Team Admin**: Pode adicionar/remover membros da equipa
- **Member**: Pode aceder aos recursos com âmbito de equipa

Os proprietários e administradores da organização têm acesso automático a todas as equipas, sem necessidade de adesão explícita.

### Subscrições e Planos

O Rediacc oferece quatro planos:

| Plano | Máquinas | Licenças de Repo/mês | Validade padrão / máxima do cert. de delegação | Funcionalidades |
|-------|----------|----------------------|------------------------------------------------|-----------------|
| COMMUNITY | 2 | 100 | 15d / 30d | Básico |
| PROFESSIONAL | 3 | 1.000 | 60d / 120d | Grupos de permissões, registo de auditoria, marca personalizada, suporte prioritário |
| BUSINESS | 10 | 10.000 | 90d / 180d | Ceph, análises avançadas, prioridade de fila, fila avançada |
| ENTERPRISE | 25+ | 25.000+ | 120d / 365d | Gestor de conta dedicado |

![Subscription Flow](/img/account-subscription-flow.svg)

Todos os planos começam com um período de carência de 3 dias. As vagas de máquina são contabilizadas por equipa e libertadas automaticamente após 1 hora de inatividade. Consulte [Subscrição e Licenciamento](/en/docs/subscription-licensing) para mais detalhes.

### Faturação

Apenas o **proprietário** da organização pode gerir a faturação:
- Criar uma sessão de checkout no Stripe para atualização de plano
- Aceder ao portal de faturação do Stripe para alterar o método de pagamento
- Solicitar reembolsos de forma autónoma (até 14 dias, com um período de espera de 30 dias)

### Região de Dados

A sua conta é armazenada na região de dados que selecionou no registo (UE, EUA ou Ásia-Pacífico). Esta escolha é permanente. O emblema de região no portal indica em que região os seus dados residem. Consulte [Regiões de Dados](/en/docs/data-regions) para mais detalhes.

### Canal Edge

Se a sua conta estiver no canal Edge, verá um emblema "Edge" na barra lateral do portal. As contas Edge têm o dobro dos limites Community, mas sem acesso a planos pagos. Consulte [Canais de Lançamento](/en/docs/release-channels) para as diferenças entre Edge e Stable.

### Certificados de Delegação

Para implementações on-premise e air-gapped, pode gerir os seus próprios certificados de delegação a partir do portal do cliente em **/account/delegation-certs**. A página é visível para todos os clientes independentemente do plano; apenas os valores de validade padrão por nível diferem.

#### Controlo por função

| Ação | Proprietário da Org | Administrador da Org | Membro |
|------|---------------------|----------------------|--------|
| Listar / ver / descarregar certs | ✓ | ✓ | ✓ |
| Criar novo cert | ✓ | ✓ | ✗ |
| Revogar cert | ✓ | ✓ | ✗ |
| Emitir token de renovação automática | ✓ | ✓ | ✗ |
| Processar pedido de renovação air-gapped | ✓ | ✓ | ✗ |

Os membros podem ver a lista e descarregar certificados existentes (útil para os distribuir por uma frota de máquinas), mas apenas proprietários e administradores podem emitir ou revogar certificados.

#### Imposição de um único certificado ativo

Uma subscrição só pode ter **um certificado de delegação ativo de cada vez**. Cada instalação on-premise impõe quotas mensais e por máquina contra o seu próprio livro-razão local; múltiplos certificados ativos multiplicariam a quota efetiva sem qualquer possibilidade de reconciliação.

Se tentar criar um segundo certificado enquanto um já está ativo, o portal apresenta uma caixa de diálogo com duas opções:

- **Renovar (recomendado)** - estende a cadeia existente. Todas as licenças de repositório emitidas anteriormente continuam a funcionar com o certificado renovado. Use esta opção ao rodar um certificado a expirar na mesma instalação on-premise.
- **Revogar e Criar Novo** - descarta a cadeia existente e começa do zero. As licenças de repositório emitidas anteriormente tornam-se inverificáveis assim que o `validUntil` do certificado ANTIGO passar. Use apenas quando migrou para uma nova instalação on-premise com uma chave de assinatura diferente, ou ao recuperar de uma chave comprometida.

Se necessitar de ambientes separados (produção + staging + DR + multi-região), adquira uma subscrição por instalação.

#### Bootstrap de renovação automática

Para ativar a renovação automática on-premise, clique em **Get auto-renew token** na página de Certificados de Delegação. Isto emite um token de API com âmbito `delegation:renew` (perpétuo, sem expiração) e apresenta os valores a colar no `.env` da sua instalação on-premise:

```
UPSTREAM_URL=https://www.rediacc.com
UPSTREAM_API_KEY=rdt_<token>
```

O token concede **apenas** a renovação de certificados de delegação. Não pode ler nem modificar qualquer outro recurso. Este é o único caminho para emitir um token `delegation:renew`; o fluxo regular `/portal/api-tokens` não inclui este âmbito.

#### Renovação air-gapped

Se a sua instalação on-premise não tiver acesso HTTPS de saída, utilize o fluxo de manifesto offline:

1. Na página de administração on-premise, clique em **Download renewal request**. A instalação on-premise gera um manifesto assinado com a cabeça da sua cadeia local.
2. Transfira o manifesto para o upstream (USB, e-mail encriptado, qualquer canal).
3. No portal upstream, clique em **Upload renewal request** e selecione o manifesto. O upstream verifica a assinatura do manifesto, emite um novo certificado e devolve-o como um `.json` transferível.
4. Transfira o novo certificado para a instalação on-premise e carregue-o através da página de administração on-premise.

O upstream rejeita manifestos com mais de 7 dias. Consulte [Instalação On-Premise](/en/docs/on-premise) para o procedimento completo e [Cadeia de Licenças e Delegação](/en/docs/license-chain) para o design criptográfico.

#### Limite de taxa

A criação de certificados tem um limite de **10 tentativas por 24h consecutivas** por subscrição, incluindo tentativas falhadas (spam de colisões, entrada inválida). Se atingir o limite, o portal apresenta um valor `Retry-After` indicando quando pode tentar novamente.
