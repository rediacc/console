---
title: Armazenamento de Configuração
description: Sincronização de configuração encriptada no dispositivo, com desbloqueio por passkey ou kit de recuperação
category: Guides
tags:
  - account
  - security
subcategory: account
order: 8
language: pt
sourceHash: "3972742d77ac9e63"
sourceCommit: "45ae253620c97f781ac426d3a84bca6b9a8bc528"
---

# Armazenamento de Configuração

O armazenamento de configuração sincroniza uma configuração do CLI entre dispositivos. As configurações são encriptadas no dispositivo com uma chave de encriptação de conteúdo (CEK) que o servidor nunca detém. A secção [Segurança](#security) indica exatamente o que isso protege e o que não protege.

## Métodos de desbloqueio (slots de chave)

Existe uma CEK por armazenamento, protegida de forma independente para cada método de desbloqueio, à semelhança dos slots de chave do LUKS. Qualquer slot individual abre a mesma chave, e os slots podem ser adicionados ou removidos sem reencriptar os seus dados:

| Método | O que é | Notas |
|--------|-----------|-------|
| **Passkey** | Passkey WebAuthn com a extensão PRF, neste dispositivo ou num telemóvel através de um código QR | A opção mais forte; protegida por hardware |
| **Kit de recuperação** | Um código gerado no formato `RC1-XXXXXXXX-XXXXXXXX-XXXXXXXX-XXXXXXXX`, guardado como kit impresso ou transferido | Obrigatório para todos os membros; o código só é mostrado enquanto o kit é guardado, por isso guarde o kit num local seguro |

Um **segredo de máquina** não é um slot: inscreve uma máquina headless (consulte [Inscrição headless do CLI](#headless-cli-enrollment)) e não conta como forma de desbloquear o armazenamento para uma pessoa.

Todos os métodos alimentam o mesmo processo: o slot produz um segredo que se combina com um segredo guardado no servidor para desbloquear a CEK. Nenhuma das duas metades é suficiente por si só, e o segredo do slot nunca chega ao servidor. Ambos os segredos têm entropia suficiente para que o servidor, que guarda a chave protegida e a sua metade da chave de proteção, não tenha nada para adivinhar offline.

Os slots são geridos no portal, na página Armazenamento de Configuração. As organizações que queiram exigir desbloqueio apenas por hardware podem ativar a política **exigir passkey**, que recusa e revoga slots não-passkey em todo o armazenamento.

O desbloqueio é feito por dispositivo: desbloqueia uma vez num dispositivo novo e, a partir daí, as operações diárias do CLI (push/pull) funcionam sem tocar numa passkey ou introduzir um código de recuperação.

## Pré-requisitos

- **Autenticação de dois fatores** ativada na sua conta
- Para o método de **passkey**: um fornecedor de passkey com suporte PRF, como uma chave de segurança FIDO2 (por exemplo, YubiKey), iCloud Keychain, Google Password Manager, 1Password ou Dashlane, no dispositivo ou num telemóvel através de QR
- **Browser**: Chrome 133+, Edge 133+, Firefox 130+ ou Safari 17+

O requisito de PRF aplica-se apenas ao slot de passkey. O kit de recuperação funciona em qualquer browser suportado.

## Configuração

1. Navegue até **Armazenamento de Configuração** na barra lateral e clique em **Configurar Armazenamento de Configuração**
2. A lista de verificação de requisitos valida o seu browser, 2FA e estado da sessão
3. Registe uma passkey e clique em **Criar armazenamento de configuração**. O provedor tem de suportar PRF: a chave de segurança é tocada duas vezes, uma para a registar e outra para derivar as chaves de encriptação.
   - Um **código de recuperação** é gerado com o armazenamento e mostrado uma única vez, num kit de recuperação. Guarde o kit antes de o armazenamento ser criado; a configuração não termina sem ele.
4. Configuração concluída. A CLI guarda o segredo de desbloqueio no chaveiro do seu sistema operacional.

Uma passkey pode ser adicionada depois na página Config Storage.

### Telemóvel através de QR

Um computador de secretária sem autenticador PRF local pode usar um telemóvel: o browser mostra um código QR, o telemóvel aprova o pedido de passkey através de WebAuthn híbrido e o resultado PRF desbloqueia o armazenamento como o faria uma passkey local. O slot de passkey memoriza a credencial e o transporte com que foi registado. Se um resultado PRF não conseguir desbloquear a chave, por exemplo porque um telemóvel devolveu uma saída PRF diferente da do dispositivo que registou a passkey, a página pede para registar a passkey de novo em vez de apresentar um erro de desencriptação. O PRF híbrido requer iOS 18.4+ ou um Android recente.

### Kit de recuperação

Cada membro recebe um kit de recuperação na inscrição, e a configuração não termina enquanto o kit não for guardado. O kit contém o nome do armazenamento, o email da conta, a data de criação, o código em grupos, um QR do código e os passos de recuperação. Uma verificação de gravação pede os últimos 4 carateres do código, ou a leitura do respetivo QR, antes de a inscrição prosseguir. Não há forma de dispensar o kit, e guardar a impressão em segurança é da responsabilidade do membro.

- Uma **passkey perdida** recupera-se com o kit, e depois regista-se uma nova passkey.
- Um **kit perdido** é gerado de novo a partir de uma passkey que funcione; a impressão antiga deixa de funcionar.
- **Ambos perdidos**: um proprietário ou administrador volta a adicionar o membro através da transferência de membro.

### Rede de segurança

O servidor recusa eliminar um slot, remover um membro ou aceitar a saída de um membro quando isso deixaria o armazenamento com menos de dois titulares de chave e sem slot de recuperação. Um titular de chave é um utilizador distinto com um slot de passkey ou de recuperação na geração de chave atual; os segredos de máquina e as concessões de agente não contam. Uma impressão perdida é invisível para o servidor, por isso a página Armazenamento de Configuração aconselha um segundo titular de chave enquanto o armazenamento tiver apenas um. Se o último titular de chave perder a passkey e o kit, o armazenamento não pode ser recuperado.

## Compatibilidade de Fornecedores PRF

| Fornecedor | Suporte PRF | Plataformas |
|----------|:-----------:|-----------|
| YubiKey / chaves de segurança FIDO2 | ✅ | Windows 11, macOS, Linux |
| iCloud Keychain | ✅ | macOS 15+, iOS 18+ |
| Google Password Manager | ✅ | Android |
| 1Password | ✅ | Android, iOS |
| Dashlane | ✅ | Multiplataforma |
| Extensão Bitwarden | ❌ | Use uma chave de hardware ou outro provedor de passkey |
| Windows Hello | ❌ | Não suportado |

## Inscrição headless do CLI

Uma máquina sem browser (um servidor, um executor de CI, um daemon executor) pode inscrever-se num armazenamento existente com um segredo de máquina:

```bash
export REDIACC_MACHINE_SECRET=RM1-XXXXXXXX-XXXXXXXX-XXXXXXXX-XXXXXXXX
rdc config remote enable --machine-secret <id>
```

Requisitos:

- Um **segredo de máquina** criado através do portal (o browser detém a chave enquanto a protege com o segredo, pelo que este passo em si não pode ser headless). O portal mostra o segredo `RM1-` uma única vez, juntamente com o seu id; o segredo tem como âmbito a organização, uma equipa ou uma configuração
- Um **token de API com o âmbito `config:enroll`** para autenticar o pedido

O segredo vem de `REDIACC_MACHINE_SECRET`; se esta não existir, da entrada padrão, quando recebido por pipe; caso contrário, de um pedido oculto. Nunca é um argumento da linha de comandos. A inscrição é uma leitura: o CLI obtém os parâmetros KDF públicos do segredo e a chave protegida, deriva localmente o segredo de proteção e desbloqueia a CEK no próprio dispositivo. Isto concede ao dispositivo a capacidade de desencriptar e sincronizar a configuração; não altera o armazenamento. Revogar o segredo no portal impede novas inscrições com ele.

## Como as chaves chegam ao seu CLI

`rdc config remote enable` (e `rdc config rotate-cek`) entregam o segredo de desbloqueio ao CLI através do servidor da conta. O CLI e o browser nunca comunicam diretamente, pelo que o processo funciona da mesma forma num servidor sem browser, no WSL com o browser no Windows ou num telemóvel.

1. Inicie primeiro sessão no CLI com `rdc subscription login`. O servidor associa o pedido a essa conta.
2. O CLI cria um pedido de curta duração e apresenta uma ligação e um **código de emparelhamento** como `7KQ2-M9XD-P4RT`. A ligação guarda tudo o que transporta depois do `#`, parte que os browsers nunca enviam a um servidor.
3. Abra a ligação em qualquer browser com sessão iniciada na mesma conta. Um pedido de outra conta é recusado.
4. Quando a página pedir, introduza o código de emparelhamento que aparece no seu terminal. O botão de desbloqueio fica desativado até o código coincidir.
5. Desbloqueie com uma passkey (neste dispositivo ou num telemóvel através de QR) ou com o kit de recuperação. O browser sela a chave para o CLI e o servidor limita-se a retransmitir um blob que não consegue ler.
6. O CLI desencripta o blob, guarda o segredo no chaveiro do sistema operativo e indica que a operação foi concluída.

O pedido expira ao fim de 10 minutos. Prima **Ctrl+C** no CLI para o cancelar: o CLI pede ao servidor que descarte a ligação, que deixa de funcionar de imediato, e a página indica que deve executar o comando outra vez. Se esse pedido não chegar, a ligação continua utilizável até o pedido expirar. Se a ligação for aberta depois de expirar, ou depois de um redirecionamento de início de sessão ter perdido a parte a seguir ao `#`, execute o comando novamente.

O código de emparelhamento é derivado da chave que vai dentro da ligação. Se alguém trocar a ligação pela sua, o código no seu terminal não coincidirá com o que a página espera, pelo que nada é libertado.

Isto protege contra a adulteração da ligação e contra um retransmissor que troque ou forje um blob. Não protege contra um servidor que sirva código de página modificado: a página que abre é servida pelo servidor da conta, e as chaves estão tão seguras quanto esse código. A mesma confiança aplica-se a todas as páginas do portal que lidam com a chave da configuração.

## Ativação e leituras offline

`rdc config remote enable` liga a configuração ativa ao armazenamento. Quando o armazenamento está vazio, a ativação **semeia-o a partir da sua configuração local atual**: os recursos locais são enviados como a primeira versão do armazenamento e depois obtidos de volta para comprovar a ida e volta. Quando o armazenamento já tem conteúdo, a ativação concilia com ele em vez de o sobrescrever (aborta em caso de divergência genuína, a menos que passe `--force`).

Depois de ativada, a configuração mantém uma **cache de leitura** completa, encriptada em repouso com o mesmo mecanismo de qualquer configuração local, para que o armazenamento continue utilizável quando o servidor de conta estiver inacessível:

- **As leituras funcionam offline.** O conteúdo em cache é servido com um aviso de desatualização no stderr, identificado com a versão e o carimbo de data/hora em cache (`cachedVersion` / `cachedAt`).
- **As escritas exigem o servidor e falham de forma fechada.** Não existe fila de escrita offline: uma escrita que não consiga alcançar o servidor termina em erro e indica o servidor. Se um comando de escrita foi bem-sucedido, a alteração está no servidor.
- **As edições concorrentes a partir de duas máquinas** resolvem-se por obtenção-repetição-reenvio (pull-replay-repush): o servidor só aceita um envio sobre a versão que substitui, e o envio perdedor é repetido sobre a cópia atualizada, pelo que uma edição simultânea noutro local não é sobrescrita.
- **Uma configuração local** (sem bloco `remote`) não é afetada por nada disto e funciona totalmente offline.

## O que sincroniza

Tudo numa configuração é sincronizado, incluindo o ID de rede de cada repositório, exceto estes campos locais ao dispositivo: `schemaVersion`, `version`, `remote`, `encryption`, `renetPath`, `credentials.masterPasswordVerifier`, e os campos de sessão `account.accountServer` e `account.e2ePublicKey`. Iniciar e terminar sessão é por dispositivo.

## Versões e restauro

O servidor mantém as últimas 50 versões de cada configuração.

```bash
rdc config remote versions
rdc config remote restore <version>
```

Um restauro publica o conteúdo antigo como uma nova versão sobre a atual; nunca recua o número de versão. Todos os dispositivos recebem o conteúdo restaurado na próxima obtenção (pull), e o restauro fica registado no registo de auditoria.

## Rotação de chaves

Rodar a CEK do armazenamento volta a protegê-la sob uma nova geração:

- Os **kits de recuperação são sempre invalidados** pela rotação; gere e guarde um novo depois
- Um slot deixado numa geração mais antiga é reportado como obsoleto em vez de falhar com um erro de desencriptação críptico
- Os tokens de configuração dos outros membros são revogados, e um dispositivo que ainda tenha a chave antiga é instruído a reativar com `rdc config remote enable`

## Gestão de Membros

O armazenamento de configuração tem âmbito por organização. Os membros são geridos via portal web:

- **Ver membros**: Armazenamento de Configuração → Membros
- **Adicionar membro**: Atualmente apenas via CLI (interface web planeada)
- **Remover membro**: Clique no botão de remoção na página Membros (requer 2FA + reautenticação)

As proteções de segurança impedem a remoção do último membro ativo ou a remoção de si próprio.

As configurações no armazenamento têm ainda âmbito por equipa, mas esse âmbito é **controlo de acesso do lado do servidor, não isolamento criptográfico**: uma única CEK à escala da organização encripta as configurações de todas as equipas, e o servidor impõe quais as equipas que um membro pode ler.

## Segurança

**O que está protegido.** As configurações armazenadas são confidenciais perante um comprometimento do armazenamento do servidor e perante um operador passivo. Cada blob está vinculado ao seu armazenamento, configuração, equipa e versão, pelo que o servidor não pode trocar o blob de uma configuração pelo de outra nem alterá-lo sem ser detetado.

**O que não está protegido.** Um operador que sirva código malicioso no portal pode ler a chave no browser. Um operador também pode reter a versão mais recente de um dispositivo que nunca a viu.

| O servidor consegue | O servidor não consegue |
|---|---|
| Ver os IDs de configuração, equipas, números de versão, carimbos de data/hora, tamanhos dos blobs, quantos campos uma configuração contém e o tipo de cada campo, e os endereços IP dos clientes | Ver nomes de máquinas, repositórios ou armazenamentos (são ofuscados) ou qualquer valor de configuração |
| Recusar, atrasar ou eliminar configurações e o seu histórico | Servir o conteúdo de uma configuração como se fosse outra, ou editá-lo, sem que o dispositivo detete isso |
| Servir uma versão antiga a um dispositivo que nunca viu uma mais recente | Servir ao CLI uma versão mais antiga do que outra que já viu: o CLI recusa-a |

Outras proteções:

- **Chave dividida**: a desencriptação requer tanto o segredo do slot (no dispositivo) como o segredo do servidor
- **A eliminação exige conhecimento**: remover um valor confirmado de uma configuração exige provar que o valor era conhecido, para que um agente com acesso parcial não consiga eliminar campos silenciosamente
- **Tokens rotativos**: cada pedido roda o token de configuração; um token está vinculado ao endereço IP do seu primeiro uso e expira ao fim de 7 dias
- **Revogação**: remover um membro elimina de imediato os seus slots de chave e tokens; o que já tinha obtido permanece no seu dispositivo, e uma rotação da CEK impede que uma chave que tenha guardado abra versões posteriores

## Resolução de Problemas

| Erro | Causa | Solução |
|-------|-------|-----|
| PRF não suportado | O autenticador não tem a extensão PRF | Use YubiKey, iCloud Keychain, 1Password, Dashlane ou um telemóvel através de QR |
| X25519 não suportado | Versão do browser demasiado antiga | Atualize para Chrome 133+, Edge 133+, Firefox 130+ ou Safari 17+ |
| Já configurado | Existe um armazenamento para a sua organização | Visite /account/config-storage para gerir |
| Armazenamento de configuração não configurado | Servidor sem armazenamento de blobs | Contacte o seu administrador para configurar R2/RustFS |
| Token expirado | Sem atividade durante 7 dias, ou a máquina mudou de rede | Renovado automaticamente através do login; se não houver login guardado, execute `rdc subscription login` ou `rdc config remote enable` |
| A configuração voltou numa versão mais antiga | O servidor devolveu uma cópia mais antiga do que a que este dispositivo já tinha visto | Nada mudou localmente; tente novamente e reporte se persistir |
| Não é possível remover o último membro | Bloquearia o armazenamento permanentemente | Adicione primeiro outro membro |
| Slot obsoleto | O slot é anterior à última rotação de chaves | Adicione o slot novamente (o kit de recuperação tem de ser regenerado após cada rotação) |

## Relacionados

- [Modelo de Segurança](/pt/docs/security-model), quem pode ver o quê, âmbito das chaves, agentes e o que é recuperável
- [Consola Web](/pt/docs/web-console), desbloquear o armazenamento no browser para executar comandos
- [Proxy e Executor](/pt/docs/proxy-and-executor), como a chave desbloqueada é concedida a um executor
