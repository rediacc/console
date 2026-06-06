---
title: "Assinatura e Licenciamento"
description: "Compreenda como account, rdc e renet lidam com slots de máquina, licenças de repositório e limites de plano."
category: "Guides"
order: 7
language: pt
sourceHash: "0e18efe91c91f74c"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# Assinatura e Licenciamento

O licenciamento do Rediacc se divide em três componentes principais:

- `account` assina direitos e rastreia uso
- `rdc` autentica, solicita licenças, as entrega para máquinas e as valida em tempo de execução
- `renet` (o runtime na máquina) valida licenças instaladas localmente sem chamar o servidor de conta

Esta página explica como essas partes se encaixam para implantações locais.

## O que o Licenciamento Faz

O licenciamento controla duas coisas diferentes:

- **Contabilidade de acesso à máquina** através de **Floating Licenses**
- **Autorização de runtime de repositório** através de **licenças de repositório**

Esses estão relacionados, mas não são o mesmo artefato.

## Como o Licenciamento Funciona

`account` é a fonte de verdade para planos, substituições de contrato, estado de slots de máquina e emissões mensais de licenças de repositório.

`rdc` executa em sua estação de trabalho. Ele o conecta ao servidor de conta, solicita as licenças que precisa e as instala em máquinas remotas via SSH. Quando você executa um comando de repositório, `rdc` garante que as licenças necessárias estejam em vigor e as valida na máquina em tempo de execução.

O fluxo normal é assim:

1. Você autentica com `rdc subscription login`
2. Você executa um comando de repositório como `rdc repo create`, `rdc repo up` ou `rdc repo down`
3. Se a licença necessária estiver ausente ou expirada, `rdc` a solicita de `account`
4. `rdc` escreve a licença assinada na máquina
5. A licença é validada localmente na máquina e a operação continua

Veja [rdc vs renet](/en/docs/rdc-vs-renet) para a divisão estação de trabalho versus servidor, e [Repositories](/en/docs/repositories) para o ciclo de vida do repositório em si.

Para automação e agentes de IA, use um token de assinatura com escopo em vez de login pelo navegador:

```bash
rdc subscription login --token "$REDIACC_SUBSCRIPTION_TOKEN"
```

Você também pode injetar o token diretamente através do ambiente para que a CLI possa emitir e atualizar licenças de repositório sem qualquer etapa de login interativo:

```bash
export REDIACC_SUBSCRIPTION_TOKEN="rdt_..."
export REDIACC_ACCOUNT_SERVER="https://www.rediacc.com/account"
```

## Slots de Máquina e Licenças de Repositório

### Slots de máquina (lado do servidor)

O rastreamento de slots de máquina é aplicado pelo lado do servidor. Quando a CLI emite uma licença de repositório, o servidor de conta verifica a cota de slots de máquina da assinatura (por exemplo, 2 máquinas para Community, 5 para Professional). Um slot é mantido por 1 hora a partir da última emissão de licença de repositório naquela máquina e é liberado automaticamente após inatividade. Um plano com 5 slots pode, portanto, cobrir dezenas de máquinas ao longo do tempo, já que os slots são apenas retidos enquanto você está provisionando ativamente.

Nenhum arquivo de licença de máquina é armazenado na máquina. A aplicação de slots acontece no momento da emissão no servidor.

### Licença de repositório

Uma licença de repositório é uma licença assinada para um repositório em uma máquina. É o único arquivo de licença armazenado na máquina (`/var/lib/rediacc/license/repos/{guid}.json`).

É utilizada para:

- `rdc repo create` e `rdc repo fork`, validada antes do provisionamento (pré-emitida sem provas de identidade, depois re-emitida com provas de identidade após criação)
- `rdc repo resize` e `rdc repo expand`, validação completa incluindo expiração
- `rdc repo up`, `rdc repo down`, `rdc repo delete`, validada com **expiração pulada**
- `rdc repo push`, `rdc repo pull`, `rdc repo sync`, validada com **expiração pulada**
- autostart de repositório no reinício da máquina, validada com **expiração pulada**

Licenças de repositório são vinculadas à máquina e ao repositório de destino. Cada licença contém o ID da máquina, GUID do repositório, ID da assinatura, limites de plano e expiração. Para repositórios criptografados, o Rediacc também verifica a identidade LUKS do volume subjacente.

Múltiplas assinaturas podem coexistir na mesma máquina. Cada repositório carrega sua própria licença com seu próprio contexto de assinatura.

## Limites Padrão

O tamanho do repositório depende do nível de direito:

- Community: até `10 GB`
- planos pagos: limite de plano ou contrato

Os limites padrão para planos pagos são:

| Plan | Floating Licenses | Repository Size | Monthly repo license issuances | Delegation cert default / max |
|------|-------------------|-----------------|-------------------------------|---|
| Community | 2 | 10 GB | 500 | 15d / 30d |
| Professional | 5 | 100 GB | 5,000 | 60d / 120d |
| Business | 20 | 500 GB | 20,000 | 90d / 180d |
| Enterprise | 50 | 2048 GB | 100,000 | 120d / 365d |

Limites específicos do contrato podem aumentar ou diminuir esses valores para um cliente específico. A validade do certificado de delegação também é limitada a `subscription.expiresAt + 3 day grace`, portanto assinaturas faturadas mensalmente naturalmente obtêm certificados alinhados ao seu ciclo de faturamento. Veja [License Chain & Delegation - Validity Policy](/en/docs/license-chain) para as regras completas.

## Período de Graça de Migração de VM

Quando um provedor de hospedagem migra uma VM para hardware físico diferente, o ID da máquina muda (é derivado de identificadores de hardware como UUID DMI, `/etc/machine-id` e endereços MAC de NIC). Licenças de repositório são vinculadas ao ID da máquina, portanto uma migração normalmente invalidaria todas as licenças.

Para lidar com isso de forma transparente, licenças de repositório incluem um **período de graça de ID de máquina de 40 dias**. Se o ID da máquina não corresponder mas a licença foi emitida há menos de 40 dias, a licença ainda é aceita. Como as licenças são atualizadas a cada 30 dias, a próxima atualização vincula automaticamente ao novo ID da máquina.

Na prática:
- VM migrada, ID da máquina muda: repositórios continuam executando (dentro da janela de 40 dias)
- Próxima operação `rdc` atualiza a licença com o novo ID da máquina
- Nenhuma intervenção manual necessária
- Verifique o ID da máquina e o status da licença com `rdc machine query --system --licenses --name <machine>`

**Usuários do edge channel** recebem 2X dos limites Community sem custo (repositórios de 20 GB, 1.000 emissões/mês, 4 máquinas). Planos pagos estão disponíveis apenas no canal Stable. Veja [Release Channels](/en/docs/release-channels) para detalhes.

## O que Acontece Durante Criação, Up, Down e Reinício de Repositório

### Criação e fork de repositório

Quando você cria ou faz fork de um repositório:

1. `rdc` garante que seu token de assinatura esteja disponível (aciona autenticação por código de dispositivo se necessário)
2. `rdc` pré-emite uma licença de repositório do servidor de conta (o servidor verifica cota de slots de máquina e limites de emissões mensais neste ponto)
3. A licença de repositório pré-emitida é escrita na máquina e validada localmente (assinatura, ID da máquina, GUID do repositório, expiração e limite de tamanho)
4. Após criação bem-sucedida, `rdc` re-emite a licença do repositório com provas de identidade do repositório (UUID LUKS ou impressão digital de armazenamento)

Essa emissão respaldada por conta conta em relação ao seu uso mensal de **emissões de licenças de repositório**. Cada licença contém o email do titular da conta e nome da empresa, que é registado quando renet valida a licença.

### Repositório up, down e delete

`rdc` valida a licença de repositório instalada na máquina mas **pula a verificação de expiração**. Assinatura, ID da máquina, GUID do repositório e identidade ainda são verificados. Os usuários nunca são bloqueados de operar seus repositórios, mesmo com uma assinatura expirada.

### Redimensionamento e expansão de repositório

`rdc` executa validação completa de licença de repositório incluindo expiração e limites de tamanho.

### Reinício de máquina e autostart

Autostart usa as mesmas regras que `rdc repo up`: expiração é pulada, portanto os repositórios sempre reiniciam livremente.

Licenças de repositório usam um modelo de validade de longa duração:

- `refreshRecommendedAt` é o ponto de atualização suave
- `hardExpiresAt` é o ponto de bloqueio

Se a licença do repositório estiver desatualizada mas ainda antes da expiração dura, o runtime pode continuar. Depois de atingir a expiração dura, `rdc` deve atualizá-la para operações de redimensionamento/expansão.

### Outras operações de repositório

Operações como listar repositórios, inspecionar informações de repositório e montar não requerem qualquer validação de licença.

## Verificando Status e Atualizando Licenças

Login humano:

```bash
rdc subscription login
```

Login de automação ou agente de IA:

```bash
rdc subscription login --token "$REDIACC_SUBSCRIPTION_TOKEN"
```

Para ambientes não interativos, definir `REDIACC_SUBSCRIPTION_TOKEN` é a opção mais simples. O token deve ter escopo apenas para as operações de assinatura e licenças de repositório que o agente precisa.

Mostrar status de assinatura respaldado por conta:

```bash
rdc subscription status
```

Mostrar detalhes de ativação de máquina para uma máquina:

```bash
rdc subscription activation status -m hostinger
```

Mostrar detalhes de licenças de repositório instaladas em uma máquina:

```bash
rdc subscription repo status -m hostinger
```

Atualizar em lote licenças de repositório em uma máquina:

```bash
rdc subscription refresh repos -m hostinger
```

Repositórios descobertos na máquina mas ausentes da configuração `rdc` local são rejeitados durante atualização em lote. Eles são reportados como falhas e não são auto-classificados.

Forçar uma atualização de licença de repositório para um repositório existente:

```bash
rdc subscription refresh repo --name my-app -m hostinger
```

No primeiro uso, uma operação de repositório licenciado ou backup que não encontra nenhuma licença de repositório utilizável pode acionar um handoff de autorização de conta automaticamente. A CLI imprime uma URL de autorização, tenta abrir o navegador em terminais interativos e tenta novamente a operação uma vez após autorização e emissão bem-sucedidas.

Em ambientes não interativos, a CLI não aguarda aprovação do navegador. Em vez disso, ela informa para você fornecer um token com escopo usando `rdc subscription login --token ...` ou `REDIACC_SUBSCRIPTION_TOKEN`.

Para configuração inicial de máquina, veja [Machine Setup](/en/docs/setup).

## Comportamento Offline e Expiração

A validação de licença acontece localmente na máquina. Você não precisa entrar em contato com o servidor de conta para operar seus repositórios.

Isso significa:

- um ambiente em execução não precisa de conectividade de conta ativa em cada comando
- todos os repositórios sempre podem iniciar, parar e ser deletados mesmo com licenças expiradas, os usuários nunca são bloqueados de operar seus próprios repositórios
- operações de provisionamento (`create`, `fork`) requerem uma licença de repositório pré-emitida, e operações de crescimento (`resize`, `expand`) requerem uma licença de repositório válida
- licenças de repositório verdadeiramente expiradas devem ser atualizadas através de `rdc` antes de redimensionamento/expansão
- assinaturas de licença são verificadas contra uma chave pública incorporada, verificação de assinatura não pode ser desabilitada

## Comportamento de Recuperação

A recuperação automática é intencionalmente restrita:

- `missing`: `rdc` pode autorizar acesso a conta se necessário, atualizar licenças de repositório em lote e tentar novamente uma vez
- `expired`: `rdc` pode atualizar licenças de repositório em lote e tentar novamente uma vez
- `machine_mismatch`: falha rápido e informa para você re-emitir do contexto de máquina atual
- `repository_mismatch`: falha rápido e informa para você atualizar licenças de repositório explicitamente
- `sequence_regression`: falha rápido como um problema de integridade/estado de licença de repositório
- `invalid_signature`: falha rápido como um problema de integridade/estado de licença de repositório
- `identity_mismatch`: falha rápido, a identidade do repositório não corresponde à licença instalada

Esses casos de falha rápida não consomem automaticamente chamadas de atualização ou emissão respaldadas por conta.

## Certificados de Delegação para On-Premise

Para implantações on-premise e isoladas de ar, isso fica complexo. O servidor de conta upstream emite um **certificado de delegação** que autoriza sua instalação on-premise a assinar licenças com sua própria chave Ed25519. Isso o restringe aos limites do seu plano e cria uma cadeia à prova de adulteração.

Pontos principais para proprietários de assinatura:

- **Um certificado ativo por assinatura.** Cada instalação on-premise aplica cotas por mês e por máquina contra seu próprio ledger local, portanto múltiplas instalações multiplicariam a cota efetiva sem nenhuma possibilidade de reconciliação. Clientes que precisam de produção, staging e DR devem comprar uma assinatura por instalação.
- **Validade baseada em nível** (15d / 60d / 90d / 120d) e limites (30d / 120d / 180d / 365d) - veja a tabela de limites acima.
- **Auto-atendimento do portal do cliente.** Proprietários de org e admins podem criar, renovar e revogar certificados de delegação em `/account/delegation-certs`. A página é visível para todos os clientes independentemente do nível de plano - apenas os limites diferem.
- **Auto-renovação** é suportada via um bootstrap de um clique que emite um token de api com escopo `delegation:renew` para on-premise usar para chamadas de renovação upstream.
- **Renovação isolada de ar** é suportada via um manifesto de solicitação de renovação assinado que o admin on-premise baixa, transfere offline para upstream, e upstream processa para emitir um novo certificado.

Veja [On-Premise Installation - Licensing for Air-Gapped Deployments](/en/docs/on-premise) para a configuração operacional, e [License Chain & Delegation](/en/docs/license-chain) para o design criptográfico.

## Emissões Mensais de Licenças de Repositório

Esta métrica conta a atividade de emissão de licenças de repositório respaldada por conta bem-sucedida no mês de calendário UTC atual.

Inclui:

- emissão de licença de repositório pela primeira vez
- atualização bem-sucedida de licença de repositório que retorna uma licença recém-assinada

Não inclui:

- entradas de lote inalteradas
- tentativas de emissão falhadas
- repositórios rastreados rejeitados antes da emissão

Se você precisar de uma visualização de uso voltada para o cliente e histórico recente de emissão de licenças de repositório, use o portal de conta. Se você precisar de inspeção do lado da máquina, use `rdc subscription activation status -m` e `rdc subscription repo status -m`.
