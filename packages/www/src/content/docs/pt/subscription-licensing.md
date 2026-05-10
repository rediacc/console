---
title: "Subscrição e Licenciamento"
description: "Compreenda como o account, o rdc e o renet gerem os slots de máquinas, as licenças de repositórios e os limites dos planos."
category: "Guides"
order: 7
language: pt
---

# Subscrição e Licenciamento

O licenciamento do Rediacc tem três componentes:

- `account` assina os direitos e acompanha o uso
- `rdc` autentica, solicita licenças, entrega-as nas máquinas e aplica-as em tempo de execução
- `renet` (o runtime na máquina) valida as licenças instaladas localmente sem chamar o servidor de contas

Esta página explica como estes componentes se encaixam para deployments locais.

## O que o Licenciamento Faz

O licenciamento controla duas coisas distintas:

- **Contabilizacao de acesso a maquinas** atraves de **Licencas Flutuantes**
- **Autorizacao de runtime de repositorios** atraves de **licencas de repositorios**

Estas estao relacionadas, mas nao sao o mesmo artefacto.

## Como Funciona o Licenciamento

`account` e a fonte de verdade para planos, substituicoes contratuais, estado dos slots de maquinas e emissoes mensais de licencas de repositorios.

`rdc` corre no seu computador de trabalho. Autentica-o no servidor de contas, solicita as licencas necessarias e instala-as nas maquinas remotas via SSH. Quando executa um comando de repositorio, `rdc` garante que as licencas necessarias estao no lugar e valida-as na maquina em tempo de execucao.

O fluxo normal e o seguinte:

1. Autentica-se com `rdc subscription login`
2. Executa um comando de repositorio como `rdc repo create`, `rdc repo up` ou `rdc repo down`
3. Se a licenca necessaria estiver em falta ou expirada, `rdc` solicita-a ao `account`
4. `rdc` escreve a licenca assinada na maquina
5. A licenca e validada localmente na maquina e a operacao continua

Consulte [rdc vs renet](/pt/docs/rdc-vs-renet) para a divisao computador de trabalho vs servidor, e [Repositorios](/pt/docs/repositories) para o proprio ciclo de vida do repositorio.

Para automacao e agentes de IA, use um token de subscricao com ambito em vez de login no browser:

```bash
rdc subscription login --token "$REDIACC_SUBSCRIPTION_TOKEN"
```

Tambem pode injectar o token directamente atraves do ambiente para que o CLI possa emitir e renovar licencas de repositorios sem qualquer passo de login interactivo:

```bash
export REDIACC_SUBSCRIPTION_TOKEN="rdt_..."
export REDIACC_ACCOUNT_SERVER="https://www.rediacc.com/account"
```

## Slots de Maquinas e Licencas de Repositorios

### Slots de maquinas (lado do servidor)

O acompanhamento de slots de maquinas e aplicado do lado do servidor. Quando o CLI emite uma licenca de repositorio, o servidor de contas verifica a quota de slots de maquinas da subscricao (por exemplo, 2 maquinas para Community, 5 para Professional). Um slot e reservado durante 1 hora a partir da ultima emissao de licenca de repositorio nessa maquina e e libertado automaticamente apos inatividade. Isto significa que um plano de 5 slots pode servir dezenas de maquinas ao longo do tempo; os slots so sao reservados durante o provisionamento activo.

Nenhum ficheiro de licenca de maquina e guardado na maquina. A aplicacao de slots ocorre no momento da emissao no servidor.

### Licenca de repositorio

Uma licenca de repositorio e uma licenca assinada para um repositorio numa maquina. E o unico ficheiro de licenca guardado na maquina (`/var/lib/rediacc/license/repos/{guid}.json`).

E usada para:

- `rdc repo create` e `rdc repo fork`, validadas antes do provisionamento (pre-emitidas sem provas de identidade, depois re-emitidas com provas de identidade apos a criacao)
- `rdc repo resize` e `rdc repo expand`, validacao completa incluindo expiracao
- `rdc repo up`, `rdc repo down`, `rdc repo delete`, validadas com **expiracao ignorada**
- `rdc repo push`, `rdc repo pull`, `rdc repo sync`, validadas com **expiracao ignorada**
- autostart de repositorio no reinicio da maquina, validado com **expiracao ignorada**

As licencas de repositorios estao vinculadas a maquina e ao repositorio alvo. Cada licenca contem o ID da maquina, o GUID do repositorio, o ID da subscricao, os limites do plano e a expiracao. Para repositorios encriptados, o Rediacc tambem verifica a identidade LUKS do volume subjacente.

Multiplas subscricoes podem coexistir na mesma maquina; cada repositorio carrega a sua propria licenca com o seu proprio contexto de subscricao.

## Limites Predefinidos

O tamanho do repositorio depende do nivel de direitos:

- Community: ate `10 GB`
- planos pagos: limite do plano ou contrato

Os limites predefinidos dos planos pagos sao:

| Plano | Licencas Flutuantes | Tamanho do Repositorio | Emissoes mensais de licencas de repositorios | Validade padrao / max do cert de delegacao |
|-------|---------------------|------------------------|----------------------------------------------|--------------------------------------------|
| Community | 2 | 10 GB | 500 | 15d / 30d |
| Professional | 5 | 100 GB | 5.000 | 60d / 120d |
| Business | 20 | 500 GB | 20.000 | 90d / 180d |
| Enterprise | 50 | 2048 GB | 100.000 | 120d / 365d |

Os limites especificos de contrato podem aumentar ou diminuir estes valores para um cliente especifico. A validade do cert de delegacao tambem e limitada a `subscription.expiresAt + 3 dias de graca`, pelo que as subscricoes facturadas mensalmente obtem naturalmente certs alinhados com o seu ciclo de facturacao. Consulte [Cadeia de Licencas e Delegacao - Politica de Validade](/pt/docs/license-chain) para as regras completas.

## Periodo de Graca de Migracao de VM

Quando um fornecedor de hosting migra uma VM para hardware fisico diferente, o ID da maquina muda (e derivado de identificadores de hardware como DMI UUID, `/etc/machine-id` e enderecos MAC de NIC). As licencas de repositorios estao vinculadas ao ID da maquina, pelo que uma migracao normalmente invalidaria todas as licencas.

Para tratar isto de forma transparente, as licencas de repositorios incluem um **periodo de graca de 40 dias para o ID da maquina**. Se o ID da maquina nao corresponder, mas a licenca tiver sido emitida ha menos de 40 dias, a licenca e ainda aceite. Como as licencas sao renovadas a cada 30 dias, a proxima renovacao vincula automaticamente ao novo ID da maquina.

Na pratica:
- VM migrada, ID da maquina muda: os repositorios continuam a funcionar (dentro do periodo de 40 dias)
- A proxima operacao `rdc` renova a licenca com o novo ID da maquina
- Nao e necessaria intervencao manual
- Verifique o ID da maquina e o estado da licenca com `rdc machine query --system --licenses --name <machine>`

**Os utilizadores do canal edge** recebem 2X os limites Community sem custo (repositorios de 20 GB, 1.000 emissoes/mes, 4 maquinas). Os planos pagos so estao disponiveis no canal Stable. Consulte [Canais de Lancamento](/pt/docs/release-channels) para detalhes.

## O que Acontece Durante Repo Create, Up, Down e Restart

### Criar e fazer fork de repositorio

Quando cria ou faz fork de um repositorio:

1. `rdc` garante que o seu token de subscricao esta disponivel (acciona autenticacao por codigo de dispositivo se necessario)
2. `rdc` pre-emite uma licenca de repositorio do servidor de contas (o servidor verifica a quota de slots de maquinas e os limites de emissao mensais neste ponto)
3. A licenca de repositorio pre-emitida e escrita na maquina e validada localmente (assinatura, ID da maquina, GUID do repositorio, expiracao e limite de tamanho)
4. Apos criacao bem sucedida, `rdc` re-emite a licenca de repositorio com provas de identidade do repositorio (UUID LUKS ou impressao digital de armazenamento)

Essa emissao suportada pela conta conta para o seu uso mensal de **emissoes de licencas de repositorios**. Cada licenca contem o email e o nome da empresa do titular da conta, que e registado quando o renet valida a licenca.

### Repo up, down e delete

`rdc` valida a licenca de repositorio instalada na maquina mas **ignora a verificacao de expiracao**. A assinatura, o ID da maquina, o GUID do repositorio e a identidade sao ainda verificados. Os utilizadores nunca ficam impedidos de operar os seus repositorios, mesmo com uma subscricao expirada.

### Repo resize e expand

`rdc` realiza validacao completa da licenca de repositorio incluindo expiracao e limites de tamanho.

### Reinicio da maquina e autostart

O autostart usa as mesmas regras que `rdc repo up`; a expiracao e ignorada, pelo que os repositorios reiniciam sempre livremente.

As licencas de repositorios usam um modelo de validade de longa duracao:

- `refreshRecommendedAt` e o ponto de renovacao suave
- `hardExpiresAt` e o ponto de bloqueio

Se a licenca de repositorio estiver desactualizada mas ainda antes da expiracao rigida, o runtime pode continuar. Uma vez atingida a expiracao rigida, `rdc` deve renova-la para operacoes de resize/expand.

### Outras operacoes de repositorio

Operacoes como listar repositorios, inspeccionar informacoes de repositorios e montar nao requerem qualquer validacao de licenca.

## Verificar Estado e Renovar Licencas

Login humano:

```bash
rdc subscription login
```

Login de automacao ou agente de IA:

```bash
rdc subscription login --token "$REDIACC_SUBSCRIPTION_TOKEN"
```

Para ambientes nao interactivos, definir `REDIACC_SUBSCRIPTION_TOKEN` e a opcao mais simples. O token deve ter ambito apenas para as operacoes de subscricao e licenca de repositorio de que o agente necessita.

Mostrar estado de subscricao suportado pela conta:

```bash
rdc subscription status
```

Mostrar detalhes de activacao da maquina para uma maquina:

```bash
rdc subscription activation status -m hostinger
```

Mostrar detalhes de licenca de repositorio instalada numa maquina:

```bash
rdc subscription repo status -m hostinger
```

Renovar em massa as licencas de repositorios numa maquina:

```bash
rdc subscription refresh -m hostinger
```

Os repositorios descobertos na maquina mas em falta na configuracao local do `rdc` sao rejeitados durante a renovacao em massa. Sao reportados como falhas e nao sao classificados automaticamente.

Forcar a renovacao de uma licenca de repositorio para um repositorio existente:

```bash
rdc subscription refresh repo --name my-app -m hostinger
```

No primeiro uso, uma operacao de repositorio ou backup licenciada que nao encontre uma licenca de repositorio utilizavel pode acionar automaticamente uma transferencia de autorizacao de conta. O CLI mostra um URL de autorizacao, tenta abrir o browser em terminais interactivos e retenta a operacao uma vez apos autorizacao e emissao bem sucedidas.

Em ambientes nao interactivos, o CLI nao aguarda aprovacao do browser. Em vez disso, indica que deve fornecer um token com ambito com `rdc subscription login --token ...` ou `REDIACC_SUBSCRIPTION_TOKEN`.

Para a configuracao inicial da maquina, consulte [Configuracao da Maquina](/pt/docs/setup).

## Comportamento Offline e Expiracao

A validacao de licencas ocorre localmente na maquina; nao requer conectividade ao vivo com o servidor de contas.

Isso significa que:

- um ambiente em execucao nao precisa de conectividade ao vivo com a conta em cada comando
- todos os repositorios podem sempre iniciar, parar e ser eliminados mesmo com licencas expiradas; os utilizadores nunca ficam impedidos de operar os seus proprios repositorios
- as operacoes de provisionamento (`create`, `fork`) requerem uma licenca de repositorio pre-emitida, e as operacoes de crescimento (`resize`, `expand`) requerem uma licenca de repositorio valida
- as licencas de repositorios verdadeiramente expiradas devem ser renovadas atraves do `rdc` antes de operacoes de resize/expand
- as assinaturas de licencas sao verificadas contra uma chave publica incorporada; a verificacao de assinatura nao pode ser desactivada

## Comportamento de Recuperacao

A recuperacao automatica e intencionalmente limitada:

- `missing`: `rdc` pode autorizar acesso a conta se necessario, renovar em massa as licencas de repositorios e retentar uma vez
- `expired`: `rdc` pode renovar em massa as licencas de repositorios e retentar uma vez
- `machine_mismatch`: falha rapidamente e indica que deve re-emitir a partir do contexto da maquina actual
- `repository_mismatch`: falha rapidamente e indica que deve renovar as licencas de repositorios explicitamente
- `sequence_regression`: falha rapidamente como um problema de integridade/estado de licenca de repositorio
- `invalid_signature`: falha rapidamente como um problema de integridade/estado de licenca de repositorio
- `identity_mismatch`: falha rapidamente; a identidade do repositorio nao corresponde a licenca instalada

Estes casos de falha rapida nao consomem automaticamente chamadas de renovacao ou emissao suportadas pela conta.

## Certificados de Delegacao para On-Premise

Para deployments on-premise e air-gapped, o servidor de contas upstream emite um **certificado de delegacao** que autoriza a sua instalacao on-premise a assinar licencas com a sua propria chave Ed25519. O certificado limita a instalacao on-premise aos seus limites de plano e cria uma cadeia a prova de adulteracao.

Pontos-chave para proprietarios de subscricoes:

- **Um certificado activo por subscricao.** Cada instalacao on-premise aplica quotas por mes e por maquina contra o seu proprio livro de registos local, pelo que multiplas instalacoes multiplicariam a quota efectiva sem possibilidade de reconciliacao. Os clientes que necessitam de producao + staging + DR devem comprar uma subscricao por instalacao.
- **Validade padrao baseada em nivel** (15d / 60d / 90d / 120d) e limites maximos (30d / 120d / 180d / 365d); consulte a tabela de limites acima.
- **Self-service a partir do portal do cliente.** Os proprietarios e administradores de organizacoes podem criar, renovar e revogar certificados de delegacao em `/account/delegation-certs`. A pagina e visivel para todos os clientes independentemente do nivel do plano; apenas os limites diferem.
- **Renovacao automatica** e suportada via um bootstrap de um clique que cria um token de API com ambito `delegation:renew` para a instalacao on-premise usar em chamadas de renovacao upstream.
- **Renovacao air-gapped** e suportada via um manifesto de pedido de renovacao assinado que o administrador on-premise transfere, transporta offline para o upstream, e o upstream processa para emitir um novo certificado.

Consulte [Instalacao On-Premise - Licenciamento para Deployments Air-Gapped](/pt/docs/on-premise) para a configuracao operacional, e [Cadeia de Licencas e Delegacao](/pt/docs/license-chain) para o design criptografico.

## Emissoes Mensais de Licencas de Repositorios

Esta metrica conta a actividade de emissao de licencas de repositorios suportada pela conta no mes de calendario UTC actual.

Inclui:

- emissao de licenca de repositorio pela primeira vez
- renovacao de licenca de repositorio bem sucedida que devolve uma licenca recentemente assinada

Nao inclui:

- entradas de lote inalteradas
- tentativas de emissao falhadas
- repositorios nao rastreados rejeitados antes da emissao

Se precisar de uma vista orientada para o cliente do uso e historico recente de emissoes de licencas de repositorios, use o portal de conta. Se precisar de inspeccao do lado da maquina, use `rdc subscription activation status -m` e `rdc subscription repo status -m`.
