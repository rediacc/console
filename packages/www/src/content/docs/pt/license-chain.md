---
title: "Cadeia de Licenças e Delegação"
description: "Emissão de licenças à prova de adulteração, assinatura delegada para instalações on-premise e deteção de forks."
category: "Guides"
order: 8
language: pt
sourceHash: "9b062d6866c1ccb4"
sourceCommit: "4e60a12e0664cdee5ad9079a7b75e2d05980d0f5"
---

# Cadeia de Licenças e Delegação

O Rediacc utiliza uma cadeia de hashes à prova de adulteração para emissão de licenças e um modelo de certificado de delegação para implementações on-premise. Esta página explica como o sistema protege contra adulteração, ataques de repetição e partilha de licenças.

## Porquê uma Cadeia?

Cada licença emitida por um servidor de conta é registada num livro-razão de acrescentamento apenas. Cada entrada está ligada à anterior via um hash SHA-256, formando uma cadeia. A cadeia tem três propriedades que tornam a adulteração detetável:

1. Os **números de sequência** são globais e monotónicos por subscrição. Saltar ou reordenar entradas quebra a cadeia.
2. Os **hashes da cadeia** vinculam cada entrada a todas as anteriores. Modificar qualquer entrada passada invalida todas as que se seguem.
3. O **Renet armazena a sequência mais alta que viu** por subscrição. Um servidor que reverta a sua sequência é detetado imediatamente.

## Como uma Licença é Emitida

Quando a CLI solicita uma licença de repositório, o servidor de conta:

1. Lê o cabeçalho atual da cadeia (última sequência + hash) para a subscrição.
2. Constrói o payload da licença com o número de sequência seguinte e o hash de cadeia anterior incorporados.
3. Assina o payload com Ed25519.
4. Calcula `chainHash = SHA256(prevChainHash + ":" + signedPayload)`.
5. Acrescenta a entrada ao livro-razão de emissão de forma atómica. Se dois pedidos concorrentes colidirem na mesma sequência, o perdedor readquire a sequência seguinte e volta a assinar.
6. Devolve o blob assinado com o hash da cadeia à CLI.

A `sequence` e o `prevChainHash` estão dentro do payload assinado (por isso não podem ser modificados sem invalidar a assinatura). O `chainHash` está no envelope (calculado após a assinatura para evitar uma dependência circular).

## Como o Renet Valida

Cada máquina que corre o Renet armazena o seu último estado conhecido da cadeia em `{licenseDir}/chain-state.json`. Em cada validação de licença, o Renet verifica:

| Verificação | Falha significa |
|---|---|
| A assinatura Ed25519 é válida | A licença foi falsificada ou adulterada |
| `sequence > lastKnownSequence` | O servidor reverteu a cadeia (ataque de repetição) |
| `chainHash == SHA256(prevChainHash + ":" + payload)` | A entrada da cadeia foi modificada |
| `issuedAt >= lastKnownIssuedAt` | Manipulação do relógio (relógio do servidor definido para trás) |

Se alguma verificação falhar, a licença é rejeitada e o motivo da falha é reportado.

## Certificados de Delegação (On-Premise)

Para implementações com air-gap ou self-hosted, o servidor de conta upstream emite um **certificado de delegação** que autoriza um servidor on-premise a assinar licenças com a sua própria chave Ed25519. O certificado restringe o que o servidor on-premise pode fazer.

### Estrutura do certificado

Um certificado de delegação contém:

- `subscriptionId` -- a que subscrição este certificado se aplica
- `planCode`, `maxMachines`, `maxRepositorySizeGb`, `maxRepoLicenseIssuancesPerMonth` -- limites do plano incorporados
- `maxTotalIssuances` -- limite superior no número de sequência da cadeia
- `delegatedPublicKey` -- a chave pública Ed25519 do servidor on-premise (SPKI base64)
- `genesisHash` -- o ponto de partida da cadeia (continuação do certificado anterior, ou "genesis")
- `genesisSequence` -- sequência da cadeia no momento da emissão. Usado por `/onprem/cert-upload` para validar que o novo certificado se liga a uma entrada conhecida no livro-razão de emissão local quando a cadeia avançou durante o trânsito. Opcional para compatibilidade retroativa (tratado como 0 se ausente).
- `validFrom`, `validUntil` -- janela de validade (regida pela política de validade abaixo)
- Assinado pela chave Ed25519 mestra upstream

### Como funciona a delegação

1. O administrador empresarial gera um par de chaves Ed25519 no servidor on-premise.
2. O administrador solicita um certificado de delegação ao upstream:
   ```
   POST /admin/delegation-certs
   { subscriptionId, validDays: 90, delegatedPublicKey: "MCowBQYDK2VwAyEA..." }
   ```
3. O upstream assina o certificado com a sua chave mestra e devolve-o.
4. O servidor on-premise armazena o certificado e a sua chave privada, pronto para assinar licenças.
5. Quando uma CLI solicita uma licença ao servidor on-premise, o servidor assina com a sua chave delegada e inclui uma referência ao certificado.
6. O Renet realiza **validação de dois níveis**:
   - Verificar a assinatura do certificado contra a chave mestra upstream incorporada.
   - Verificar a assinatura do blob contra a chave delegada do certificado.
   - Verificar que `blob.sequence <= cert.maxTotalIssuances`.
   - Aplicar todas as verificações padrão da cadeia.

O servidor on-premise não pode:
- Falsificar uma licença fora dos limites do plano do certificado de delegação (o renet rejeita-a).
- Emitir mais do que `maxTotalIssuances` operações no total (o renet rejeita excesso de sequência).
- Modificar o certificado (a assinatura upstream quebra).

## Política de Validade

A janela de validade de um certificado de delegação é calculada por um helper de política partilhado (`computeDelegationCertValidity()`) que corre tanto no backend upstream como no frontend do portal do cliente. As mesmas entradas produzem sempre o mesmo `validUntil`, para que os clientes possam pré-visualizar a validade efetiva no modal de criação antes de submeter.

### Predefinições e limites por plano

| Plano | Validade predefinida | Limite do plano |
|---|---|---|
| COMMUNITY | 15 dias | 30 dias |
| PROFESSIONAL | 60 dias | 120 dias |
| BUSINESS | 90 dias | 180 dias |
| ENTERPRISE | 120 dias | 365 dias |

A predefinição é o que o endpoint de criação escolhe quando o chamador omite `validDays`. O limite é o valor máximo que o chamador pode solicitar.

### Substituição por subscrição

Os administradores podem definir um valor personalizado de `delegationCertDefaultDays` numa subscrição específica através da página de Detalhes de Subscrição do administrador. **A substituição substitui tanto a predefinição como o limite para essa subscrição.** É uma saída de emergência para clientes especiais (por exemplo, um contrato empresarial que necessite de um certificado de 200 dias num plano COMMUNITY). O schema Zod ainda impõe um intervalo absoluto de `1..365`.

### Limite máximo: fim da subscrição + 3 dias de tolerância

Independentemente do limite do plano e da substituição, cada certificado tem um limite máximo absoluto de `subscription.expiresAt + 3 dias` (o `SUBSCRIPTION_CONFIG.gracePeriodDays` existente). Isto significa:

- Para subscrições perpétuas (`expiresAt = null`), não se aplica limite de expiração - apenas o limite do plano.
- Para subscrições mensais faturadas via Stripe, o limite é aproximadamente a data de faturação seguinte + 3 dias. Quando o Stripe avança `expiresAt` cada mês, o limite move-se com ele.
- Para subscrições de teste, o limite é o fim do período de teste + 3 dias.

### Dias efetivos + razão

Cada resposta de criação/renovação inclui `effectiveDays` e `reason` para que o chamador possa ver exatamente por que motivo o certificado obteve a validade que obteve:

| Razão | Significado |
|---|---|
| `plan_default` | Sem pedido, sem substituição: usada a predefinição do plano |
| `subscription_override` | Sem pedido: usada a substituição por subscrição como predefinição |
| `requested` | Pedido do chamador respeitado dentro de todos os limites |
| `plan_max_clamp` | O pedido do chamador excedeu o limite do plano - reduzido |
| `override_max_clamp` | O pedido do chamador excedeu a substituição por subscrição - reduzido |
| `subscription_cap_clamp` | O alvo, de outra forma válido, sobreviveria ao `expiresAt + 3 dias` da subscrição |

O modal de criação do portal do cliente usa estas razões para renderizar uma pré-visualização ao vivo ("Receberá um certificado de 18 dias. Reduzido porque o certificado não pode sobreviver à data de fim da subscrição em mais de 3 dias.") para que os clientes não submetam às cegas.

### Limiar de renovação adaptativo

O ciclo de renovação automática on-premise usa um limiar adaptativo modelado após o Let's Encrypt:

```
effectiveThresholdDays = min(env.RENEW_THRESHOLD_DAYS, ceil(certValidityDays / 3))
```

Um certificado COMMUNITY de 15 dias renova aos 5 dias restantes. Um certificado BUSINESS de 90 dias renova aos 14 dias restantes (o limite configurado por env entra em ação). Um certificado ENTERPRISE de 120 dias renova aos 14 dias restantes. Isto impede que certificados de curta duração desencadeiem a renovação imediatamente, mantendo ainda uma margem confortável para certificados de longa duração.

## Aplicação de Ativo Único

Uma subscrição pode ter **no máximo um certificado de delegação ativo de cada vez** (`MAX_ACTIVE_DELEGATION_CERTS_PER_SUBSCRIPTION = 1`).

### Porquê um?

Cada instalação on-premise impõe `maxRepoLicenseIssuancesPerMonth`, `maxActivations` e integridade da cadeia contra o seu próprio livro-razão de emissão local. O on-premise não sincroniza contagens de uso com o upstream. Esse é o ponto central da delegação com capacidade offline.

Se uma subscrição tivesse múltiplos certificados ativos (um por instalação), cada instalação imporia o limite de forma independente:

- Uma subscrição de 500/mês com 3 certificados ativos permite até **1500 emissões/mês** na prática.
- Três cadeias paralelas, cada uma ancorada ao genesis, sem possível reconciliação de auditoria.

O upstream não consegue detetar este bypass porque os on-prems foram concebidos para operar offline. **O ativo único é o único modelo aplicável.** Os clientes com múltiplas instalações (produção + staging + DR) devem adquirir uma subscrição por instalação.

### Comportamento de colisão

`POST /admin/delegation-certs` e `POST /portal/delegation-certs` rejeitam uma segunda criação com:

```json
HTTP/1.1 409 Conflict
{
  "code": "DELEGATION_CERT_ALREADY_ACTIVE",
  "existingCertId": "...",
  "actions": {
    "renew": "POST /portal/delegation-certs/process-renewal-request (preserves chain)",
    "revokeAndCreate": "POST /portal/delegation-certs/{existingCertId}/revoke then retry create"
  }
}
```

O portal do cliente apresenta isto com um diálogo dedicado explicando as consequências:

- **Renovar (recomendado)** - estende a cadeia existente. Todas as licenças de repositório emitidas anteriormente continuam a funcionar.
- **Revogar e Criar** - descarta a cadeia existente e começa do zero a partir do genesis. As licenças de repositório emitidas anteriormente tornam-se inverificáveis quando o `validUntil` do certificado ANTIGO expirar. Use apenas quando migrou para um novo on-prem com uma chave de assinatura diferente, ou ao recuperar de uma chave comprometida.

`renew()` é a troca atómica que preserva o ativo único e **não** está sujeita à verificação de colisão 409.

### Limite de taxa

Mesmo com ativo único, um chamador malicioso poderia criar um ciclo `revogar -> criar -> revogar -> criar` para queimar ciclos de assinatura de chave mestra upstream. Ambos os endpoints de criação têm um limite de **10 tentativas por 24 horas consecutivas** por subscrição via a tabela `rateLimits` existente:

```
HTTP/1.1 429 Too Many Requests
Retry-After: 78234
{ "code": "DELEGATION_CERT_RATE_LIMITED", "retryAfterSec": 78234 }
```

O contador incrementa em cada tentativa independentemente do resultado (os ciclos de spam de colisão também são limitados).

## Deteção de Fork

Se um cliente partilhar o seu certificado de delegação com outra parte (ou correr dois servidores on-premise com o mesmo certificado), as cadeias divergem. O upstream deteta isto no momento da renovação.

### Fluxo de renovação

1. O administrador on-premise chama `POST /admin/delegation-certs/renew` com o cabeçalho atual da cadeia:
   ```
   { subscriptionId, currentChainHash, currentSequence, delegatedPublicKey }
   ```
2. O upstream percorre as entradas da cadeia contra o seu próprio registo no livro-razão.
3. Se `currentChainHash` não corresponder à cadeia registada pelo upstream em `currentSequence`, fork detetado:
   ```
   409 { code: 'CHAIN_FORK_DETECTED', divergedAtSequence: N }
   ```
4. O `genesisHash` do novo certificado é definido para o hash atual da cadeia, para que as máquinas com o estado antigo da cadeia possam continuar a partir de onde ficaram.

Se o certificado for partilhado com um não-cliente:
- Podem usá-lo durante o período de validade do certificado.
- Na primeira renovação, o upstream vê apenas uma cadeia (a legítima).
- O `genesisHash` do novo certificado corresponde apenas à cadeia legítima.
- As máquinas na cadeia partilhada rejeitarão novas licenças imediatamente porque o seu `chainHash` armazenado não se conecta ao `genesisHash` do novo certificado.

## Renovação com Air-Gap

Para instalações on-premise sem acesso HTTPS de saída ao upstream, o fluxo de renovação é totalmente offline. Existem três novos endpoints que fecham o ciclo:

**No on-premise (`auth, root, requireElevated()`):**
- `GET /onprem/cert-current` - descarregar o certificado assinado atualmente carregado (cópia de segurança, auditoria, re-importação)
- `GET /onprem/renewal-request` - gerar um manifesto assinado contendo o cabeçalho da cadeia local + chave pública delegada, assinado pela chave privada on-premise

**No upstream (admin ou portal com âmbito de organização):**
- `POST /admin/delegation-certs/process-renewal-request` (raiz do sistema cross-customer)
- `POST /portal/delegation-certs/process-renewal-request` (proprietário/admin da organização)

### Manifesto do pedido de renovação

O pedido de renovação é um pequeno documento JSON:

```json
{
  "manifest": {
    "schemaVersion": 1,
    "generatedAt": "2026-04-15T12:00:00.000Z",
    "subscriptionId": "...",
    "currentChainHash": "...",
    "currentSequence": 42,
    "delegatedPublicKey": "MCowBQYDK2VwAyEA...",
    "currentCertValidUntil": "...",
    "currentCertPublicKeyId": "...",
    "currentCertId": null
  },
  "signature": "<base64 Ed25519>",
  "publicKeyId": "..."
}
```

A assinatura é calculada sobre a codificação canónica do manifesto (chaves ordenadas alfabeticamente e depois `JSON.stringify`) usando a chave privada on-premise. Isto garante que ambos os lados calculam bytes idênticos independentemente da ordem de construção do objeto.

### Verificação no upstream

`processRenewalManifest()` executa cinco verificações:

1. **Existe certificado ativo** para a subscrição do manifesto. Devolve `404 NO_ACTIVE_CERT` caso contrário - o cliente deve usar o fluxo de criação, não de renovação.
2. **A chave pública delegada corresponde** ao certificado ativo. Devolve `400 DELEGATED_KEY_MISMATCH` caso contrário - protege contra repetição de um on-prem diferente.
3. **A assinatura do manifesto verifica** contra o `delegatedPublicKey` do certificado ativo. Devolve `400 MANIFEST_SIGNATURE_INVALID` caso contrário - prova que o manifesto veio de um detentor da chave privada on-premise.
4. **A idade do manifesto** está dentro de 7 dias (`RENEWAL_MANIFEST_MAX_AGE_MS`). Devolve `400 MANIFEST_EXPIRED` caso contrário - âncora anti-repetição.
5. **A ligação do hash da cadeia** na `currentSequence` do manifesto corresponde ao livro-razão do upstream. Devolve `409 CHAIN_FORK_DETECTED` caso contrário - protege contra cadeias em fork.

Se todas as verificações passarem, `processRenewalManifest` chama o fluxo `renew()` existente, que expira atomicamente o certificado antigo e insere um novo. **Não está sujeito ao 409 de ativo único do lado de criação** porque é uma troca atómica, não um revogar+criar em 2 passos.

### Avanço de sequência durante o trânsito

Um manifesto de pedido de renovação captura o cabeçalho da cadeia no momento da geração. Enquanto o manifesto está em trânsito (entrega via USB, email encriptado), o on-premise pode continuar a emitir licenças de repositório, avançando a sua cadeia local.

Quando o novo certificado é carregado de volta para o on-premise, `/onprem/cert-upload` valida que o `genesisSequence` do novo certificado ainda se liga a uma entrada conhecida no livro-razão de emissão local:

- Se `cert.genesisSequence > localHead.sequence` devolve `409 CHAIN_HEAD_BEHIND` (o upstream está numa cadeia em fork).
- Se `cert.genesisSequence > 0` e a entrada do livro-razão local nessa sequência tiver um `chainHash` diferente de `cert.genesisHash` devolve `409 CHAIN_FORK_ON_UPLOAD` (a cadeia local divergiu).
- Caso contrário, o certificado é aceite. As emissões futuras continuam a partir de `localHead.sequence + 1`.

Isto significa que **não é necessário nenhum bloqueio de escrita durante o trânsito**. A cadeia estende-se naturalmente em ambos os lados. Corresponde a como a renovação de certificados X.509 lida com números de série em trânsito.

## Auditoria Periódica

O upstream fornece um endpoint de auditoria para verificar a integridade da cadeia sem renovar o certificado:

```
POST /admin/delegation-certs/audit
{ subscriptionId, chainEntries: [{ sequence, chainHash }, ...] }
```

O upstream percorre as entradas e devolve `{ valid: true }` ou `{ valid: false, divergedAtSequence: N, expected, actual }`.

Os servidores on-premise devem chamar este endpoint periodicamente (predefinição: semanalmente via variável de ambiente `UPSTREAM_AUDIT_URL`) para detetar forks antecipadamente.

### Provas de auditoria do lado da máquina

O Renet pode verificar a continuidade da cadeia localmente usando `VerifyAuditProof`. Quando uma máquina renova a sua licença após uma longa pausa, o servidor pode devolver as entradas intermédias da cadeia como prova. A máquina percorre a prova para verificar que cada `chainHash` deriva do `prevHash + blobHash` anterior via SHA-256, detetando qualquer adulteração sem contactar o upstream.

## Segurança de Concorrência

O D1 (base de dados da Cloudflare) não suporta transações interativas. A emissão concorrente de licenças para a mesma subscrição pode colidir no número de sequência. O servidor de conta trata isto da seguinte forma:

1. Ler a sequência seguinte + hash de cadeia anterior.
2. Construir e assinar o blob com essa sequência incorporada.
3. Inserir a entrada no livro-razão com `onConflictDoNothing`.
4. Se a inserção devolver 0 linhas alteradas, a sequência foi reclamada por outro pedido - readquirir a sequência, reconstruir, **voltar a assinar** e tentar novamente.
5. Após 10 tentativas falhadas, falhar com um erro.

O detalhe crítico: a nova tentativa **volta a assinar** o blob. Uma nova tentativa ingénua que apenas atualizasse a entrada do livro-razão deixaria o blob assinado com um número de sequência desatualizado, quebrando a cadeia.

## Transporte de Email

O servidor de conta pode enviar emails transacionais (links mágicos, reposições de palavra-passe, notificações de segurança) via dois transportes configuráveis:

| Transporte | Configuração |
|---|---|
| `ses` (predefinido) | `AWS_SES_ACCESS_KEY_ID`, `AWS_SES_SECRET_ACCESS_KEY`, `AWS_SES_REGION`, `AWS_SES_FROM` |
| `smtp` | `EMAIL_TRANSPORT=smtp`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_SECURE`, `SMTP_FROM` |

Ambos os transportes funcionam para implementações cloud e on-premise. Escolha o que melhor se adequa à sua infraestrutura: AWS SES com a sua própria conta AWS, ou qualquer servidor SMTP (Microsoft Exchange, Postfix, SendGrid, Mailgun, etc.).

O transporte é selecionado no arranque via a variável de ambiente `EMAIL_TRANSPORT`. O SMTP usa pooling de ligações e carregamento tardio, por isso a biblioteca cliente SMTP só é inicializada se o SMTP for selecionado.

Todos os modelos de email e a API pública de email são idênticos em todos os transportes.

## Documentação Relacionada

- [Instalação On-Premise](/pt/docs/on-premise) -- como implementar o servidor on-premise
- [Subscrição e Licenciamento](/pt/docs/subscription-licensing) -- limites do plano e slots de máquina
- [Canais de Lançamento](/pt/docs/release-channels) -- canais edge vs stable
- [Regiões de Dados](/pt/docs/data-regions) -- residência regional de dados
