---
title: Armazenamento de Configuração
description: Sincronização de configuração encriptada zero-knowledge com encriptação baseada em passkey
category: Guides
order: 8
language: pt
sourceHash: "daf79946b8925246"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# Armazenamento de Configuração

O armazenamento de configuração fornece sincronização encriptada zero-knowledge da sua configuração CLI entre dispositivos. As suas configurações são encriptadas com chaves derivadas da sua passkey; o servidor nunca vê dados em texto simples.

## Pré-requisitos

- **Autenticação de dois fatores** ativada na sua conta
- **Fornecedor de passkey com suporte PRF**: chave de segurança FIDO2 (por exemplo, YubiKey), iCloud Keychain, Google Password Manager, 1Password ou Dashlane
- **Browser**: Chrome 133+, Edge 133+, Firefox 130+ ou Safari 17+

## Configuração

1. Navegue até **Armazenamento de Configuração** na barra lateral e clique em **Configurar Armazenamento de Configuração**
2. A lista de verificação de requisitos valida o seu browser, 2FA e estado da sessão
3. Clique em **Iniciar Configuração**; precisará de tocar na sua chave de segurança duas vezes:
   - Primeiro toque: regista a passkey
   - Segundo toque: deriva as chaves de encriptação via PRF
4. Configuração concluída; o segredo da sua passkey fica armazenado no keyring do seu sistema operativo

Após a configuração, as operações diárias do CLI (push/pull) funcionam sem a passkey. Aviso importante: a configuração requer uma passkey com suporte de extensão PRF. Nem todos os tokens de hardware ou autenticadores de plataforma possuem este suporte.

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

## Gestão de Membros

O armazenamento de configuração tem âmbito por organização. Os membros são geridos via portal web:

- **Ver membros**: Armazenamento de Configuração → Membros
- **Adicionar membro**: Atualmente apenas via CLI (interface web planeada)
- **Remover membro**: Clique no botão de remoção na página Membros (requer 2FA + reautenticação)

As proteções de segurança impedem a remoção do último membro ativo ou a remoção de si próprio.

## Segurança

- **Zero-knowledge**: O servidor armazena dados triplamente encriptados que não consegue desencriptar
- **Chave dividida**: A desencriptação requer tanto o segredo da sua passkey (cliente) como o segredo do servidor (servidor)
- **Tokens rotativos**: Cada chamada de API usa um token novo; os tokens antigos autodestroem-se
- **Vinculação de IP**: Os tokens ficam vinculados ao seu IP no primeiro uso
- **Revogação instantânea**: Os membros removidos perdem o acesso em 30 segundos

## Resolução de Problemas

| Erro | Causa | Solução |
|-------|-------|-----|
| PRF não suportado | O autenticador não tem a extensão PRF | Use YubiKey, iCloud Keychain, 1Password ou Dashlane |
| X25519 não suportado | Versão do browser demasiado antiga | Atualize para Chrome 133+, Edge 133+, Firefox 130+ ou Safari 17+ |
| Já configurado | Existe um armazenamento para a sua organização | Visite /account/config-storage para gerir |
| Armazenamento de configuração não configurado | Servidor sem armazenamento de blobs | Contacte o seu administrador para configurar R2/RustFS |
| Token expirado | Sem atividade há 24 horas | Execute qualquer comando de armazenamento de configuração para atualizar |
| Não é possível remover o último membro | Bloquearia o armazenamento permanentemente | Adicione primeiro outro membro |
