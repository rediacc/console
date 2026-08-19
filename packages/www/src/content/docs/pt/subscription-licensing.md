---
title: Assinatura e Licenciamento
description: >-
  Compreenda como account, rdc e renet lidam com slots de máquina, licenças de
  repositório e limites de plano.
category: Guides
tags:
  - account
order: 7
language: pt
sourceHash: "15886ad7ee04e90c"
sourceCommit: "fd9d3476b1fdf0ac6ffaa14f486f20f9642fe2d5"
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

Veja [rdc vs renet](/pt/docs/rdc-vs-renet) para a divisão estação de trabalho versus servidor, e [Repositories](/pt/docs/repositories) para o ciclo de vida do repositório em si.

Para automação e agentes de IA, use um token de assinatura com escopo em vez de login pelo navegador:

```bash
rdc subscription login --token "$REDIACC_TOKEN"
```

Você também pode injetar o token diretamente através do ambiente para que a CLI possa emitir e atualizar licenças de repositório sem qualquer etapa de login interativo:

```bash
export REDIACC_TOKEN="rdt_..."
export REDIACC_ACCOUNT_SERVER="https://www.rediacc.com/account"
```

## Slots de Máquina e Licenças de Repositório

### Slots de máquina (lado do servidor)

O rastreamento de slots de máquina é aplicado do lado do servidor. Quando a CLI emite uma licença de repositório, o servidor de conta verifica a cota de slots de máquina da assinatura. Todo plano self-service (Community, Professional, Business) inclui um slot de máquina; implantações multi-máquina são uma configuração Enterprise dimensionada junto com nossos parceiros. Um slot é mantido por 5 horas a partir da última emissão de licença de repositório naquela máquina e é liberado automaticamente após inatividade. Como um slot só fica retido enquanto você está provisionando ativamente, um único slot ainda pode cobrir várias máquinas ao longo de um mês.

O teto é lido do registo da sua assinatura, e não de uma constante fixa do plano, por isso um número de ativações negociado passa a valer assim que é definido na assinatura. O nível do plano apenas decide o valor inicial.

A emissão e a renovação são aplicadas de forma diferente, e essa diferença importa:

- **A emissão de uma nova licença é bloqueada no teto.** Se todos os slots estiverem ocupados, o pedido falha com `MAX_MACHINES_REACHED` e nada é provisionado.
- **A renovação de uma licença existente nunca é bloqueada.** Uma máquina que renova enquanto todos os slots estão ocupados continua a funcionar e o seu slot fica registado como acima do limite. Pode ver isso no portal, na página Machines, em `rdc subscription status` e no campo `overLimitCount` da API de estado de licenças. A marca desaparece sozinha assim que a máquina volta a caber dentro do limite.

A renovação é deliberadamente o caminho mais brando. Uma máquina que renova uma licença que já detém não é capacidade nova, e recusá-la pararia backups em infraestrutura que já foi paga. O que continua bloqueado é acrescentar capacidade.

Nenhum arquivo de licença de máquina é armazenado na máquina. A aplicação de slots acontece no momento da emissão no servidor.

### Licença de repositório

Uma licença de repositório é uma licença assinada para um repositório em uma máquina. É o único arquivo de licença armazenado na máquina, organizado por datastore e por chave de assinatura:

```
/var/lib/rediacc/license/repos/{guid}/{keyId}.json
/var/lib/rediacc/license/datastores/{datastoreId}/repos/{guid}/{keyId}.json
```

Os repositórios no armazenamento predefinido de uma máquina usam o primeiro caminho. Os repositórios num datastore com nome usam o segundo, onde `{datastoreId}` é a identidade que esse datastore recebeu quando foi criado. É esse enquadramento que faz um fork de datastore contabilizar honestamente: um datastore forkado recebe uma identidade totalmente nova, por isso os seus repositórios começam sem nenhuma licença, reportam `missing` na primeira operação licenciada e recebem as suas próprias licenças. Um repositório cuja licença aponta para um datastore diferente daquele onde está falha de imediato com `identity_mismatch` em vez de ser reemitida automaticamente, e é isso que impede que um ficheiro de licença seja copiado de lado.

`{keyId}` é uma impressão digital de 16 caracteres hexadecimais (os primeiros 8 bytes de `SHA-256` da chave pública Ed25519 do servidor de assinatura). Um repositório gerido por mais de um universo de conta (por exemplo, produção e bench a implantar na mesma máquina) mantém um ficheiro por chave de assinatura sob o seu diretório `{guid}`. A compilação renet da máquina valida apenas o ficheiro que a sua chave incorporada, ou um certificado de delegação encadeado a ela, consegue verificar; os ficheiros de outros universos ficam inertes. Trocar de universo nunca invalida licenças: a primeira operação num novo universo emite a licença desse universo uma vez (um resultado `missing` emite automaticamente), e ambos coexistem depois disso.

É utilizada para:

- `rdc repo create`, `rdc repo fork` e `rdc repo commit`, validadas antes do provisionamento (pré-emitidas sem provas de identidade e depois reemitidas com provas de identidade após a criação, porque o repositório ainda não existe no momento da verificação)
- `rdc repo resize`, `rdc repo expand`, `rdc repo merge` e `rdc repo promote`, **totalmente validadas, incluindo expiração**
- transferência de backup, **totalmente validada, incluindo expiração**: `rdc repo push`, `rdc repo pull`, `rdc repo migrate` e backups agendados
- `rdc repo up`, `rdc repo up --all`, `rdc repo exec` e o autostart de repositórios no reinício da máquina, validados com **a expiração e a janela do certificado de delegação ambas ignoradas**
- `rdc repo down`, `rdc repo delete` e comandos apenas de leitura, como listar repositórios, não precisam de licença nenhuma

Assinaturas, vinculação de chave, vinculação de máquina, vinculação de repositório e todas as restrições do certificado de delegação são impostas em todos estes casos. O que o último grupo dispensa são apenas as duas janelas de tempo, para que uma licença expirada ou um certificado caducado nunca o impeçam de executar ou desligar os seus próprios dados.

Licenças de repositório são vinculadas à máquina e ao repositório de destino. Cada licença contém o ID da máquina, GUID do repositório, ID da assinatura, limites de plano e expiração. Para repositórios criptografados, o Rediacc também verifica a identidade LUKS do volume subjacente.

Múltiplas assinaturas podem coexistir na mesma máquina. Cada repositório carrega sua própria licença com seu próprio contexto de assinatura.

## Clusters

O clustering é vendido através dos nossos parceiros como parte de um acordo Enterprise. Não é uma opção de plano self-service, e as secções abaixo descrevem como é contabilizado, não como comprá-lo.

**Um Nó é uma máquina.** Um Cluster não tem identidade de licenciamento própria. Cada Nó dentro dele é uma máquina comum com o Renet Agent instalado, e conta exatamente como uma máquina isolada.

**Não há agrupamento.** Um Cluster de cinco Nós não consome um único slot de Cluster partilhado. Cada Nó reclama o seu próprio slot na primeira vez que um repositório é colocado nele, e esse slot segue o mesmo modelo flutuante de 5 horas de qualquer outro: fica retido durante 5 horas a contar da última emissão de licença de repositório nesse Nó e liberta-se sozinho depois disso.

**Construir o Cluster é gratuito. O que conta é colocar repositórios.** Criar o Cluster, juntar Nós, instalar a camada de armazenamento distribuído e levantar o control plane do Kubernetes não custam nenhum slot. A contabilização começa quando um repositório aterra num Nó.

**Um fork de Cluster volta a contabilizar repositório a repositório.** Fazer fork de um Cluster inteiro dá ao datastore forkado uma identidade nova, por isso cada repositório do fork recebe a sua própria licença na primeira vez que é tocado, seja qual for o Nó onde está a correr. A migração simples é o caso oposto: mover um repositório entre máquinas leva a licença consigo e continua a validar, porque nada mudou na identidade do seu armazenamento.

**A renovação num Cluster segue a regra branda descrita acima.** Os Nós renovam as suas próprias licenças sem supervisão, por isso um Cluster que cresceu para além do seu número de ativações continua a funcionar e reporta os Nós acima do limite, em vez de falhar backups a meio da noite. Acrescentar um Nó novo continua a ser bloqueado no teto.

Dimensionar um Cluster é uma conversa, não uma caixa a assinalar. Os números de ativações para Clusters são acordados na encomenda, e o seu parceiro define-os diretamente na assinatura. Veja [Contacto](/pt/contact) para começar essa conversa.

## Limites Padrão

O tamanho do repositório depende do nível de direito:

- Community: até `10 GB`
- planos pagos: limite de plano ou contrato

Os limites padrão para planos pagos são:

| Plano | Licenças Flutuantes | Tamanho do Repositório | Emissões mensais de licença de repositório | Validade padrão / máxima do cert. de delegação |
|-------|----------------------|--------------------------|------------------------------------------------|--------------------------------------------------|
| Community | 1 | 10 GB | 100 | 15d / 30d |
| Professional | 1 | 100 GB | 2.000+ | 60d / 120d |
| Business | 1 | 500 GB | 5.000+ | 90d / 180d |
| Enterprise | Personalizado | 1 TB+ | 15.000+ | 120d / 365d |

Limites específicos do contrato podem aumentar ou diminuir esses valores para um cliente específico. A validade do certificado de delegação também é limitada a `subscription.expiresAt + 3 day grace`, portanto assinaturas faturadas mensalmente naturalmente obtêm certificados alinhados ao seu ciclo de faturamento. Veja [License Chain & Delegation - Validity Policy](/pt/docs/license-chain) para as regras completas.

## Teste Gratuito e o Retorno ao Community

Novas contas começam um teste gratuito de 14 dias no plano Professional ou Business. O cartão de crédito é coletado no cadastro, e a primeira cobrança só acontece quando o teste termina, então cancelar antes disso não custa nada. Há apenas um teste disponível por cliente.

Community é o piso gratuito permanente. Ele não é mais uma opção de cadastro direta para novas contas; em vez disso, uma conta cai para o Community sempre que uma assinatura termina: cancelamento durante o teste, cancelamento de um plano pago depois, ou um pagamento que falhou. No Community de fallback você mantém uma máquina com 10 GB por repositório e 100 configurações por mês. Contas criadas antes do lançamento do modelo baseado em teste mantêm o acesso Community que já tinham.

A aplicação continua branda onde mais importa: repositórios em execução (`up`, `down`, `delete`, autostart) continuam funcionando mesmo depois que uma assinatura termina. Para além disso, aplicam-se duas regras diferentes, e confundi-las é o que faz a graça de 60 dias parecer inconsistente:

- **As operações que precisam do servidor de conta** não acontecem sem uma assinatura ativa, porque o servidor recusa-se a assinar. São elas `create`, `fork` e qualquer atualização ou renovação de licença. Nada de novo é provisionado depois de a assinatura caducar.
- **As operações que só precisam de uma licença instalada válida** continuam a funcionar até essa licença atingir a expiração dura, sem qualquer servidor pelo meio. São elas `resize` e `expand` em repositórios que já tem, e a transferência de backup (`push`, `pull`, backups agendados). A licença principal de um repositório atinge a expiração dura 60 dias depois da data de fim da assinatura, que é de onde vem a graça de 60 dias. A licença de um fork é bem mais curta, limitada a 7 dias, e é por isso que máquinas com muitos forks dependem da auto-renovação descrita abaixo.

Ou seja, uma assinatura caducada impede-o de imediato de aumentar a sua frota, e 60 dias depois impede-o de aumentar os repositórios que estão nela.

## Período de Graça de Migração de VM

Quando um provedor de hospedagem migra uma VM para hardware físico diferente, o ID da máquina muda (é derivado de identificadores de hardware como UUID DMI, `/etc/machine-id` e endereços MAC de NIC). Licenças de repositório são vinculadas ao ID da máquina, portanto uma migração normalmente invalidaria todas as licenças.

Para lidar com isso de forma transparente, licenças de repositório incluem um **período de graça de ID de máquina de 40 dias**. Se o ID da máquina não corresponder mas a licença foi emitida há menos de 40 dias, a licença ainda é aceita. Como as licenças são atualizadas a cada 30 dias, a próxima atualização vincula automaticamente ao novo ID da máquina.

Na prática:
- VM migrada, ID da máquina muda: repositórios continuam executando (dentro da janela de 40 dias)
- Próxima operação `rdc` atualiza a licença com o novo ID da máquina
- Nenhuma intervenção manual necessária
- Verifique o ID da máquina e o status da licença com `rdc machine status <machine> --system --licenses`

**Contas no canal Edge** funcionam no plano Community com o dobro dos limites (repositórios de 20 GB, 200 configurações/mês, 2 máquinas). Planos pagos estão disponíveis apenas no canal Stable. Veja [Canais de Lançamento](/pt/docs/release-channels) para detalhes.

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
rdc subscription login --token "$REDIACC_TOKEN"
```

Para ambientes não interativos, definir `REDIACC_TOKEN` é a opção mais simples. O token deve ter escopo apenas para as operações de assinatura e licenças de repositório que o agente precisa.

Mostrar status de assinatura respaldado por conta:

```bash
rdc subscription status
```

Mostrar detalhes de ativação de máquina para uma máquina:

```bash
rdc subscription status -m hostinger
```

Mostrar detalhes de licenças de repositório instaladas em uma máquina:

```bash
rdc subscription status -m hostinger
```

Atualizar a licença de um repositório numa máquina:

```bash
rdc subscription refresh -m hostinger --repo my-app
```

O ref de `--repo` tem de ser resolúvel na sua configuração `rdc` local. Um repositório descoberto na máquina mas ausente da configuração local é rejeitado: é reportado como falha e não é classificado automaticamente.

No primeiro uso, uma operação de repositório licenciado ou backup que não encontra nenhuma licença de repositório utilizável pode acionar um handoff de autorização de conta automaticamente. A CLI imprime uma URL de autorização, tenta abrir o navegador em terminais interativos e tenta novamente a operação uma vez após autorização e emissão bem-sucedidas.

Em ambientes não interativos, a CLI não aguarda aprovação do navegador. Em vez disso, ela informa para você fornecer um token com escopo usando `rdc subscription login --token ...` ou `REDIACC_TOKEN`.

Para configuração inicial de máquina, veja [Machine Setup](/pt/docs/setup).

## Auto-Renovação de Licenças

Tudo o que ficou dito acima parte do princípio de que está sentado ao teclado. Os backups agendados não estão, e é para esse caso que existe a auto-renovação.

Um backup agendado valida no nível estrito, por isso precisa de uma licença que não tenha expirado. E a licença de um fork está limitada a 7 dias. As suas máquinas não guardam credenciais de conta, por definição de desenho, portanto antes da auto-renovação o backup de um fork simplesmente parava uma semana depois de o fork ser criado, em silêncio, às três da manhã.

### Como uma máquina renova sem guardar um token

Cada licença que o Rediacc emite ou renova transporta um `renewalUrl`, o endereço completo do endpoint de renovação no servidor de conta que a assinou. A máquina lê esse endereço a partir da licença que tem instalada, por isso nunca precisa que lhe digam onde está o seu servidor de conta.

Depois, a máquina apresenta a licença instalada a esse endpoint. A licença é a sua própria credencial: está assinada, o servidor verifica essa assinatura, e não há nenhum token de API envolvido em ponto algum. O servidor devolve uma licença nova com novas janelas de validade, e a máquina instala-a e volta a validá-la antes de dar a renovação por concluída.

A renovação é uma operação para a máquina inteira:

```bash
sudo renet license renew
```

Os repositórios são agrupados pelo servidor que os assinou, por isso uma máquina que serve dois universos de conta contacta cada um deles uma vez. Um ficheiro de bloqueio impede que duas renovações corram ao mesmo tempo, e o `--jitter` espalha uma frota de máquinas que, de outra forma, acordariam todas à hora certa.

O servidor recusa uma renovação em três casos, e cada um significa uma coisa diferente:

| Recusa | O que significa |
|---|---|
| A assinatura caducou, está suspensa ou passou o período de graça | Faturação. A renovação recomeça sozinha assim que a assinatura voltar a estar ativa |
| O certificado de delegação está expirado ou revogado | Configuração on-premise. Renove o certificado no seu servidor on-premise e as máquinas voltam a renovar normalmente |
| A identidade da máquina já não corresponde e a graça de 40 dias passou | A licença pertence a uma máquina que esta não é. Reemita a partir do contexto da máquina atual |

Uma recusa nunca trava a execução inteira. Um repositório caducado não impede a renovação dos restantes na mesma máquina.

### Os backups agendados renovam-se sozinhos

Cada unidade de backup que o Rediacc escreve corre primeiro uma renovação:

```
ExecStartPre=-<renet> license renew --jitter 45s
```

O `-` inicial marca-a como melhor esforço, e é de propósito. Uma renovação recusada, uma falha momentânea de rede ou um Renet Agent mais antigo que ainda não conhece o comando nunca podem levar o backup atrás. O backup corre, e a licença é renovada pelo caminho sempre que for possível.

### Quando um backup é bloqueado

Se o licenciamento chegar mesmo a recusar um backup, a máquina regista esse facto. Essa marca é o único sinal de que os backups não supervisionados deixaram de copiar dados, por isso é mostrada bem à vista:

```bash
rdc machine status <machine> --licenses
```

A coluna `backups` mostra `BLOCKED` com o motivo, e a mesma informação é impressa por baixo da tabela como erro, para não se perder no meio de trinta repositórios. A coluna `renewed` mostra como correu a última renovação não supervisionada, incluindo o código de recusa do servidor quando houve um, e é isso que lhe diz se o que tem em mãos é uma questão de faturação ou uma questão de certificado on-premise.

Uma renovação bem-sucedida limpa a marca, tal como um backup que passa a sua verificação de licença. Não há nada para confirmar ou repor à mão.

## Comportamento Offline e Expiração

A validação de licença acontece localmente na máquina. Você não precisa entrar em contato com o servidor de conta para operar seus repositórios.

Isso significa:

- um ambiente em execução não precisa de conectividade de conta ativa em cada comando
- todos os repositórios sempre podem iniciar, parar e ser deletados mesmo com licenças expiradas, os usuários nunca são bloqueados de operar seus próprios repositórios
- operações de provisionamento (`create`, `fork`) requerem uma licença de repositório pré-emitida, e operações de crescimento (`resize`, `expand`) requerem uma licença de repositório válida
- licenças de repositório verdadeiramente expiradas têm de ser substituídas antes de redimensionamento/expansão, seja através de `rdc` a partir da sua estação de trabalho, seja pela própria máquina a renovar-se
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
- `cert_expired`: falha rapidamente nas operações de crescimento (`create`, `fork`, `resize`) e na transferência de backup (`push`, `pull`); `repo up` e autostart continuam a funcionar, o que corresponde ao modelo de expiração suave da licença. Renove o certificado de delegação
- `cert_invalid`: falha rápido, o certificado de delegação falhou numa restrição (assinatura de chave mestra inválida, incompatibilidade de subscrição/plano, limite de tamanho, ou sequência acima de `maxTotalIssuances`). Reemita o certificado depois de corrigir o limite subjacente

Esses casos de falha rápida não consomem automaticamente chamadas de atualização ou emissão respaldadas por conta.

Duas notas sobre como ler esta lista:

- `missing` nem sempre é um problema. É também o resultado normal da primeira vez que um repositório é tocado dentro de um datastore acabado de forkar, e é exatamente o que faz esse fork contabilizar: a licença é emitida, um slot é reclamado e a operação continua. `identity_mismatch` é o oposto deliberado, para que um ficheiro de licença copiado de outro datastore falhe de imediato em vez de ser reemitido em silêncio.
- Esta lista descreve a recuperação a partir da sua estação de trabalho. Uma máquina que se renova a si própria tem os seus próprios desfechos, reportados por `rdc machine status <machine> --licenses` em vez de levantados como falha de comando, porque um backup agendado não tem a quem contar.

## Certificados de Delegação para On-Premise

Para implantações on-premise e isoladas de ar, isso fica complexo. O servidor de conta upstream emite um **certificado de delegação** que autoriza sua instalação on-premise a assinar licenças com sua própria chave Ed25519. Isso o restringe aos limites do seu plano e cria uma cadeia à prova de adulteração.

Pontos principais para proprietários de assinatura:

- **Um certificado ativo por assinatura.** Cada instalação on-premise aplica cotas por mês e por máquina contra seu próprio ledger local, portanto múltiplas instalações multiplicariam a cota efetiva sem nenhuma possibilidade de reconciliação. Clientes que precisam de produção, staging e DR devem comprar uma assinatura por instalação.
- **Validade baseada em nível** (15d / 60d / 90d / 120d) e limites (30d / 120d / 180d / 365d) - veja a tabela de limites acima.
- **Auto-atendimento do portal do cliente.** Proprietários de org e admins podem criar, renovar e revogar certificados de delegação em `/account/delegation-certs`. A página é visível para todos os clientes independentemente do nível de plano - apenas os limites diferem.
- **Auto-renovação** é suportada via um bootstrap de um clique que emite um token de api com escopo `delegation:renew` para on-premise usar para chamadas de renovação upstream.
- **Renovação isolada de ar** é suportada via um manifesto de solicitação de renovação assinado que o admin on-premise baixa, transfere offline para upstream, e upstream processa para emitir um novo certificado.

Veja [On-Premise Installation - Licensing for Air-Gapped Deployments](/pt/docs/on-premise) para a configuração operacional, e [License Chain & Delegation](/pt/docs/license-chain) para o design criptográfico.

## Emissões Mensais de Licenças de Repositório

Esta métrica conta a atividade de emissão de licenças de repositório respaldada por conta bem-sucedida no mês de calendário UTC atual.

Inclui:

- emissão de licença de repositório pela primeira vez
- atualização bem-sucedida de licença de repositório que retorna uma licença recém-assinada

Não inclui:

- entradas de lote inalteradas
- tentativas de emissão falhadas
- repositórios rastreados rejeitados antes da emissão

Se você precisar de uma visualização de uso voltada para o cliente e histórico recente de emissão de licenças de repositório, use o portal de conta. Se você precisar de inspeção do lado da máquina, use `rdc subscription status -m` e `rdc subscription status -m`.
