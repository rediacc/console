---
title: Armazenamento de Configuração
description: Sincronização de configuração encriptada zero-knowledge com desbloqueio por passkey, palavra-passe mestra ou código de recuperação
category: Guides
order: 8
language: pt
sourceHash: "97c64241ff4c0d81"
sourceCommit: "433347c5ea4754300fe3da80c4bfcee42dd161bc"
---

# Armazenamento de Configuração

O armazenamento de configuração fornece sincronização encriptada zero-knowledge da sua configuração CLI entre dispositivos. As suas configurações são encriptadas no lado do cliente com uma chave de encriptação de conteúdo (CEK); o servidor nunca vê dados em texto simples.

## Métodos de desbloqueio (slots de chave)

Existe uma CEK por armazenamento, protegida de forma independente para cada método de desbloqueio, à semelhança dos slots de chave do LUKS. Qualquer slot individual abre a mesma chave, e os slots podem ser adicionados ou removidos sem reencriptar os seus dados:

| Método | O que é | Notas |
|--------|-----------|-------|
| **Passkey** | Passkey WebAuthn com a extensão PRF | A opção mais forte; protegida por hardware |
| **Palavra-passe mestra** | Uma palavra-passe à sua escolha, reforçada com PBKDF2-SHA256 (600.000 iterações) | Funciona sem hardware compatível com PRF; também permite a inscrição headless do CLI |
| **Código de recuperação** | Um código gerado no formato `RC1-XXXXXXXX-XXXXXXXX-XXXXXXXX-XXXXXXXX` | Mostrado apenas uma vez na criação; guarde-o num local seguro |

Todos os métodos alimentam o mesmo processo: o slot produz um segredo que se combina com um segredo guardado no servidor para desbloquear a CEK. Nenhuma das duas metades é suficiente por si só, pelo que a propriedade zero-knowledge se mantém nos três métodos: o segredo do slot nunca chega ao servidor.

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
3. Clique em **Iniciar Configuração**. Para um slot de passkey, precisará de tocar na sua chave de segurança duas vezes:
   - Primeiro toque: regista a passkey
   - Segundo toque: deriva as chaves de encriptação via PRF
4. Configuração concluída; o segredo da sua passkey fica armazenado no keyring do seu sistema operativo

Após a configuração, adicione um slot de palavra-passe mestra ou de código de recuperação a partir da página Armazenamento de Configuração, para que um autenticador perdido ou não suportado não o deixe bloqueado para sempre.

## Compatibilidade de Fornecedores PRF

| Fornecedor | Suporte PRF | Plataformas |
|----------|:-----------:|-----------|
| YubiKey / chaves de segurança FIDO2 | ✅ | Windows 11, macOS, Linux |
| iCloud Keychain | ✅ | macOS 15+, iOS 18+ |
| Google Password Manager | ✅ | Android |
| 1Password | ✅ | Android, iOS |
| Dashlane | ✅ | Multiplataforma |
| Extensão Bitwarden | ❌ | Em desenvolvimento |
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
- **As edições concorrentes a partir de duas máquinas** resolvem-se por obtenção-repetição-reenvio (pull-replay-repush) ao nível do conjunto de recursos, para que uma edição simultânea noutro local não sobreponha a sua.

## Rotação de chaves

Rodar a CEK do armazenamento volta a protegê-la sob uma nova geração:

- Os **códigos de recuperação são sempre invalidados** pela rotação; gere e guarde um novo depois
- Um **slot de palavra-passe mestra** só sobrevive se a palavra-passe for reintroduzida durante o assistente de rotação
- Um slot deixado numa geração mais antiga é reportado como obsoleto em vez de falhar com um erro de desencriptação críptico

## Gestão de Membros

O armazenamento de configuração tem âmbito por organização. Os membros são geridos via portal web:

- **Ver membros**: Armazenamento de Configuração → Membros
- **Adicionar membro**: Atualmente apenas via CLI (interface web planeada)
- **Remover membro**: Clique no botão de remoção na página Membros (requer 2FA + reautenticação)

As proteções de segurança impedem a remoção do último membro ativo ou a remoção de si próprio.

As configurações no armazenamento têm ainda âmbito por equipa, mas esse âmbito é **controlo de acesso do lado do servidor, não isolamento criptográfico**: uma única CEK à escala da organização encripta as configurações de todas as equipas, e o servidor impõe quais as equipas que um membro pode ler.

## Segurança

- **Zero-knowledge**: O servidor armazena dados triplamente encriptados que não consegue desencriptar
- **Chave dividida**: A desencriptação requer tanto o segredo do seu slot (cliente) como o segredo do servidor (servidor)
- **Tokens rotativos**: Cada chamada de API usa um token novo; os tokens antigos autodestroem-se
- **Vinculação de IP**: Os tokens ficam vinculados ao seu IP no primeiro uso
- **Revogação instantânea**: Os membros removidos perdem o acesso em 30 segundos

## Resolução de Problemas

| Erro | Causa | Solução |
|-------|-------|-----|
| PRF não suportado | O autenticador não tem a extensão PRF | Use YubiKey, iCloud Keychain, 1Password ou Dashlane, ou adicione um slot de palavra-passe mestra |
| X25519 não suportado | Versão do browser demasiado antiga | Atualize para Chrome 133+, Edge 133+, Firefox 130+ ou Safari 17+ |
| Já configurado | Existe um armazenamento para a sua organização | Visite /account/config-storage para gerir |
| Armazenamento de configuração não configurado | Servidor sem armazenamento de blobs | Contacte o seu administrador para configurar R2/RustFS |
| Token expirado | Sem atividade há 24 horas | Execute qualquer comando de armazenamento de configuração para atualizar |
| Não é possível remover o último membro | Bloquearia o armazenamento permanentemente | Adicione primeiro outro membro |
| Slot obsoleto | O slot é anterior à última rotação de chaves | Adicione o slot novamente (os códigos de recuperação têm de ser regenerados após cada rotação) |

## Relacionados

- [Consola Web](/pt/docs/web-console), desbloquear o armazenamento no browser para executar comandos
- [Proxy e Executor](/pt/docs/proxy-and-executor), como a chave desbloqueada é concedida a um executor
