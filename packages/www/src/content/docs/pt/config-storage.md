---
title: Armazenamento de Configuração
description: Sincronização de configuração encriptada no dispositivo, com desbloqueio por passkey, palavra-passe mestra ou código de recuperação
category: Guides
tags:
  - account
  - security
subcategory: account
order: 8
language: pt
sourceHash: "ccced160d151eeeb"
sourceCommit: "6cfcb0017e6db164abaf81c7e0a10d0d8086370b"
---

# Armazenamento de Configuração

O armazenamento de configuração sincroniza uma configuração do CLI entre dispositivos. As configurações são encriptadas no dispositivo com uma chave de encriptação de conteúdo (CEK) que o servidor nunca detém. A secção [Segurança](#security) indica exatamente o que isso protege e o que não protege.

## Métodos de desbloqueio (slots de chave)

Existe uma CEK por armazenamento, protegida de forma independente para cada método de desbloqueio, à semelhança dos slots de chave do LUKS. Qualquer slot individual abre a mesma chave, e os slots podem ser adicionados ou removidos sem reencriptar os seus dados:

| Método | O que é | Notas |
|--------|-----------|-------|
| **Passkey** | Passkey WebAuthn com a extensão PRF | A opção mais forte; protegida por hardware |
| **Palavra-passe mestra** | Uma palavra-passe à sua escolha, reforçada com PBKDF2-SHA256 (600.000 iterações) | Funciona sem hardware compatível com PRF; também permite a inscrição headless do CLI |
| **Código de recuperação** | Um código gerado no formato `RC1-XXXXXXXX-XXXXXXXX-XXXXXXXX-XXXXXXXX` | Mostrado apenas uma vez na criação; guarde-o num local seguro |

Todos os métodos alimentam o mesmo processo: o slot produz um segredo que se combina com um segredo guardado no servidor para desbloquear a CEK. Nenhuma das duas metades é suficiente por si só, e o segredo do slot nunca chega ao servidor. Um slot de palavra-passe mestra é o mais fraco dos três: o servidor tem tudo o que é necessário para testar tentativas de palavra-passe offline, por isso a palavra-passe tem de ser forte. Os slots de passkey e de código de recuperação não têm esta fraqueza.

Os slots são geridos no portal, na página Armazenamento de Configuração. As organizações que queiram exigir desbloqueio apenas por hardware podem ativar a política **exigir passkey**, que recusa e revoga slots não-passkey em todo o armazenamento.

O desbloqueio é feito por dispositivo: desbloqueia uma vez num dispositivo novo e, a partir daí, as operações diárias do CLI (push/pull) funcionam sem tocar numa passkey ou introduzir uma palavra-passe.

## Pré-requisitos

- **Autenticação de dois fatores** ativada na sua conta
- Para o método de **passkey**: um fornecedor de passkey com suporte PRF, como uma chave de segurança FIDO2 (por exemplo, YubiKey), iCloud Keychain, Google Password Manager, 1Password ou Dashlane
- **Browser**: Chrome 133+, Edge 133+, Firefox 130+ ou Safari 17+

O requisito de PRF aplica-se apenas ao slot de passkey. Os métodos de palavra-passe mestra e código de recuperação funcionam em qualquer browser suportado.

## Configuração

1. Navegue até **Armazenamento de Configuração** na barra lateral e clique em **Configurar Armazenamento de Configuração**
2. A lista de verificação de requisitos valida o seu browser, 2FA e estado da sessão
3. Escolha o primeiro método de desbloqueio e clique em **Criar armazenamento de configuração**:
   - **Passkey**, se o seu provedor suportar PRF: você toca a chave de segurança duas vezes, uma para registrá-la e outra para derivar as chaves de criptografia.
   - **Senha mestra**, que funciona em qualquer navegador, inclusive com provedores de passkey sem PRF, como o Bitwarden.
   - Opcionalmente, um **código de recuperação**, exibido uma única vez, para guardar antes de o armazenamento ser criado.
4. Configuração concluída. A CLI guarda o segredo de desbloqueio no chaveiro do seu sistema operacional.

Uma passkey pode ser adicionada depois na página Config Storage. Mantenha pelo menos dois métodos de desbloqueio, para que um autenticador perdido ou incompatível não bloqueie seu acesso.

## Compatibilidade de Fornecedores PRF

| Fornecedor | Suporte PRF | Plataformas |
|----------|:-----------:|-----------|
| YubiKey / chaves de segurança FIDO2 | ✅ | Windows 11, macOS, Linux |
| iCloud Keychain | ✅ | macOS 15+, iOS 18+ |
| Google Password Manager | ✅ | Android |
| 1Password | ✅ | Android, iOS |
| Dashlane | ✅ | Multiplataforma |
| Extensão Bitwarden | ❌ | Use antes uma palavra-passe mestra |
| Windows Hello | ❌ | Não suportado |

## Inscrição headless do CLI

Uma máquina sem browser (um servidor, um executor de CI, um daemon executor) pode inscrever-se num armazenamento existente através do método de palavra-passe mestra:

```bash
rdc config remote enable --password
```

Requisitos:

- Um **slot de palavra-passe mestra** já provisionado através do portal (é o browser que detém a chave durante o provisionamento, pelo que este passo em si não pode ser headless)
- Um **token de API com o âmbito `config:enroll`** para autenticar o pedido

A inscrição é uma leitura: o CLI obtém os parâmetros KDF públicos do slot e a chave protegida, deriva o segredo da palavra-passe localmente e desbloqueia a CEK no próprio dispositivo. Isto concede ao dispositivo a capacidade de desencriptar e sincronizar a configuração; não altera o armazenamento.

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

- Os **códigos de recuperação são sempre invalidados** pela rotação; gere e guarde um novo depois
- Um **slot de palavra-passe mestra** só sobrevive se a palavra-passe for reintroduzida durante o assistente de rotação
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
| Testar tentativas de palavra-passe mestra offline | Abrir um slot de passkey ou de código de recuperação |

Outras proteções:

- **Chave dividida**: a desencriptação requer tanto o segredo do slot (no dispositivo) como o segredo do servidor
- **A eliminação exige conhecimento**: remover um valor confirmado de uma configuração exige provar que o valor era conhecido, para que um agente com acesso parcial não consiga eliminar campos silenciosamente
- **Tokens rotativos**: cada pedido roda o token de configuração; um token está vinculado ao endereço IP do seu primeiro uso e expira ao fim de 7 dias
- **Revogação**: remover um membro elimina de imediato os seus slots de chave e tokens; o que já tinha obtido permanece no seu dispositivo, e uma rotação da CEK impede que uma chave que tenha guardado abra versões posteriores

## Resolução de Problemas

| Erro | Causa | Solução |
|-------|-------|-----|
| PRF não suportado | O autenticador não tem a extensão PRF | Use YubiKey, iCloud Keychain, 1Password ou Dashlane, ou adicione um slot de palavra-passe mestra |
| X25519 não suportado | Versão do browser demasiado antiga | Atualize para Chrome 133+, Edge 133+, Firefox 130+ ou Safari 17+ |
| Já configurado | Existe um armazenamento para a sua organização | Visite /account/config-storage para gerir |
| Armazenamento de configuração não configurado | Servidor sem armazenamento de blobs | Contacte o seu administrador para configurar R2/RustFS |
| Token expirado | Sem atividade durante 7 dias, ou a máquina mudou de rede | Renovado automaticamente através do login; se não houver login guardado, execute `rdc subscription login` ou `rdc config remote enable` |
| A configuração voltou numa versão mais antiga | O servidor devolveu uma cópia mais antiga do que a que este dispositivo já tinha visto | Nada mudou localmente; tente novamente e reporte se persistir |
| Não é possível remover o último membro | Bloquearia o armazenamento permanentemente | Adicione primeiro outro membro |
| Slot obsoleto | O slot é anterior à última rotação de chaves | Adicione o slot novamente (os códigos de recuperação têm de ser regenerados após cada rotação) |

## Relacionados

- [Consola Web](/pt/docs/web-console), desbloquear o armazenamento no browser para executar comandos
- [Proxy e Executor](/pt/docs/proxy-and-executor), como a chave desbloqueada é concedida a um executor
