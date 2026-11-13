---
title: "Instalação On-Premise"
description: "Executar o servidor de conta e a distribuição do CLI na sua própria infraestrutura."
category: "Guides"
tags:
  - account
  - operations
subcategory: setup
order: 5
language: pt
sourceHash: "7216d032580dd4e1"
sourceCommit: "48fd8400c9f2754ab1653f0247fb0d77a1835c5b"
---

O Rediacc pode funcionar inteiramente na sua própria infraestrutura. A imagem Docker autónoma inclui o servidor de conta, o portal web, o site de marketing e o endpoint de distribuição do CLI. Não existem dependências externas dos serviços alojados pelo Rediacc.

## Instalar com o rdc

`rdc server install` instala o servidor de contas como repositório numa máquina que a CLI alcança por SSH. Um único comando cobre a verificação da máquina, a configuração do renet, o DNS, o TLS, a geração de chaves, o licenciamento, a inicialização e a conta do proprietário. Cada valor tem uma opção. Num terminal, o valor em falta é perguntado; com `--yes`, nada é perguntado e um valor em falta é recusado. Cada etapa fica registrada, por isso uma nova execução ignora o que já foi feito.

As etapas, por ordem: `preflight` (sudo sem senha, arquitetura, portas 80 e 443, espaço em disco, desvio do relógio), `setup` (`rdc machine setup`, só quando falta o renet), `dns`, `tls`, `repo`, `keys`, `licence`, `image`, `up` e `owner`.

### Primeiro, máquinas existentes

A instalação tem como alvo uma máquina que já existe: um servidor num data center ou um dispositivo da rede local. Uma máquina configurada é indicada como argumento. Uma máquina ainda não registrada é adicionada pelo endereço:

```bash
rdc server install --ip 203.0.113.10 --user admin --domain accounts.example.com
rdc server install server-1 --domain accounts.example.com --owner owner@example.com --yes
```

`--port` e `--name` definem a porta SSH e o nome sob o qual a máquina é registrada. Uma VM na nuvem é criada antes com `rdc machine provision`; a instalação nunca cria uma.

### DNS

A instalação imprime os registros A e AAAA do domínio do servidor e do domínio do seu armazenamento de backup (`--store-domain`, por padrão `<nome>-store.<resto do domínio>`) e espera até que ambos resolvam para a máquina. Nenhum registro é escrito numa zona. `--no-dns-wait` imprime os registros e segue em frente, o que serve a um nome de rede local atendido por um resolvedor local.

### TLS

`--tls` escolhe um de três métodos:

| Método | Requisitos | Notas |
|---|---|---|
| `letsencrypt` | Portas 80 e 443 acessíveis pela internet | Desafio HTTP-01. `--cert-email` recebe os avisos de expiração; o padrão é o proprietário. |
| `cloudflare` | `--cf-token` | Desafio DNS-01 por meio de um token de API da Cloudflare. |
| `byo` | `--tls-cert` e `--tls-key` | Um certificado PEM existente que cubra os dois domínios. `--tls-ca` indica a CA em que a verificação de saúde confia. |

```bash
rdc server install lab --domain lab.example.internal --tls byo \
  --tls-cert host.crt --tls-key host.key --tls-ca ca.crt \
  --licence free --no-dns-wait --yes
```

### Imagem

A etapa de imagem baixa `ghcr.io/rediacc/server:latest` na máquina por padrão. `--image` escolhe outra referência. `--image-file` envia um tar gerado por `docker save`, e `--local-image` salva a `--image` do Docker local e a envia. Ambos dispensam qualquer acesso da máquina a um registro.

### Licenciamento e plano gratuito

`--licence auto` (o padrão) usa um certificado de delegação da conta conectada ou inicia no plano gratuito quando não há nenhum. `--licence free` inicia sempre no plano gratuito. Uma conta que entrou antes de o comando de instalação existir precisa executar `rdc subscription login` de novo para ter o escopo certo.

Para uma máquina sem rota até o servidor de contas, `--cert <file>` aceita um certificado de delegação obtido em outro lugar. O certificado deve nomear a chave gerada na máquina, por isso a ordem habitual é instalar primeiro no plano gratuito e depois aplicar o certificado:

```bash
rdc server install server-1 --domain accounts.example.com --licence free --yes
rdc server licence accounts.example.com --cert delegation-cert.json
```

`rdc server licence` move um servidor do plano gratuito para um certificado da conta conectada ou de `--cert`. A etapa 3 da seção de licenciamento, mais abaixo, descreve o que o servidor verifica.

### Pacote de recuperação

Todas as chaves são geradas na máquina e gravadas apenas no `secrets.env` do repositório. Num terminal, a instalação termina imprimindo uma única vez um pacote de recuperação: o par de chaves delegado, a chave do servidor de configuração da conta e as credenciais do armazenamento de objetos. O pacote nunca é registrado em log nem faz parte de `--output json`. Sem terminal, ele não é impresso, e a linha final cita `rdc server backup`.

```bash
rdc server backup accounts.example.com --out elite-recovery.env
```

`--out` grava o arquivo com modo 0600; sem ele, o pacote vai para stdout. `--bws-project <id>` na instalação também copia as chaves para um projeto do Bitwarden Secrets Manager, e `--rotate` substitui um valor armazenado que seja diferente. Sem `--bws-project`, nenhuma chave sai da máquina.

### Status

```bash
rdc server status accounts.example.com
```

O status mostra a saúde, o plano, o certificado e a imagem do servidor. `--machine` e `--repo` indicam o alvo quando o dispositivo não tem registro de instalação para o domínio.

### Atualizações

| Componente | Comando |
|---|---|
| CLI | `rdc update` |
| renet na máquina | `rdc machine setup <machine>` |
| Imagem e modelo do servidor | `rdc server upgrade <domain>` |

`rdc server upgrade` faz um fork do repositório como ponto de retorno, coloca a nova imagem, reaplica o modelo quando o embutido é mais novo e reinicia. Aceita `--image`, `--image-file` e `--local-image` como a instalação, de modo que uma máquina isolada atualiza a partir de um tar de imagem salvo.

## Imagem Docker

Obtenha a imagem autónoma:

```bash
docker pull ghcr.io/rediacc/server:stable
```

Execute com as definições predefinidas:

```bash
docker run -p 80:80 -p 443:443 ghcr.io/rediacc/server:stable
```

A imagem serve:
- API de conta em `/account/api/v1/`
- Portal web em `/account/`
- Site de marketing em `/`
- Artefactos do CLI em `/releases/`
- Binários do renet em `/bin/`

## Instalar o CLI a partir do Seu Servidor

Os utilizadores podem instalar o CLI diretamente a partir do seu servidor on-premise. O script de instalação deteta automaticamente o canal de atualização e configura o CLI para verificar as atualizações no seu servidor.

```bash
curl -fsSL https://account.example.com/install.sh | \
  REDIACC_SERVER_URL=https://account.example.com bash
```

Este único comando:
1. Transfere o binário do CLI a partir do endpoint `/releases/` do seu servidor
2. Consulta `/account/api/v1/.well-known/server-info` para descobrir o canal de atualização
3. Escreve a config predefinida (`rediacc.json`) com o URL do seu servidor, o canal de atualização e as chaves de encriptação sob os seus campos `account.*`
4. Configura `rdc update` para verificar futuras atualizações no seu servidor

Não é necessária a variável `REDIACC_CHANNEL`. O script de instalação lê o canal automaticamente a partir da configuração do seu servidor.

## Configuração do CLI com Configs Nomeadas

Para utilizadores que se ligam a vários servidores (on-premise, produção, edge), as configs nomeadas mantêm cada ambiente isolado:

```bash
# Criar uma config para o seu servidor on-premise
rdc config init myserver --server https://account.example.com

# Iniciar sessão com essa config
rdc --config myserver subscription login

# Todos os comandos com --config utilizam o servidor on-premise
rdc --config myserver machine status prod-1
```

Cada config nomeada armazena o seu próprio URL do servidor de conta (sob `account.*`) e o seu próprio token de API de conta, guardado junto à config em `api-token-<name>.json`. Mudar de config muda todo o contexto do servidor.

## Ambientes Air-Gapped

Para ambientes sem acesso à internet, defina tanto o URL do servidor como um URL de versões personalizado:

```bash
curl -fsSL https://account.example.com/install.sh | \
  REDIACC_SERVER_URL=https://account.example.com \
  REDIACC_RELEASES_URL=https://account.example.com/releases \
  bash
```

O CLI verificará as atualizações em `account.example.com/releases/cli/stable/manifest.json` em vez do CDN público de versões.

Se o servidor estiver completamente offline, instale o CLI via npm a partir do tarball incluído:

```bash
npm install -g https://account.example.com/npm/rediacc-cli-latest.tgz
```

## Referência de Variáveis de Ambiente

| Variável | Usada por | Finalidade |
|---|---|---|
| `REDIACC_SERVER_URL` | Script de instalação | URL do servidor de conta. Descobre automaticamente o canal e as chaves de encriptação. |
| `REDIACC_RELEASES_URL` | Script de instalação, atualizador do CLI | Endpoint de versões personalizado para binários do CLI. Predefinição: `https://releases.rediacc.com` |
| `REDIACC_CHANNEL` | Script de instalação | Substituir o canal de atualização. Detetado automaticamente pelo servidor se não for definido. |
| `REDIACC_ACCOUNT_SERVER` | Runtime do CLI | Substituir o URL do servidor de conta para todos os comandos do CLI. |
| `REDIACC_UPDATE_CHANNEL` | Runtime do CLI | Substituir o canal de atualização para `rdc update`. |

## Configuração do Servidor

A imagem Docker on-premise utiliza a mesma variável `ENVIRONMENT` que o serviço alojado. Defina-a no seu ambiente Docker ou na configuração de orquestração:

- `ENVIRONMENT=production` (predefinição): limites de recursos padrão; os CLIs que se ligam a este servidor utilizam por predefinição o canal de atualização **stable**. O nome do valor `production` é um identificador de implantação legado. Tanto o modo `production` como o `edge` são de qualidade de produção.
- `ENVIRONMENT=edge`: limites Community 2X; os CLIs utilizam por predefinição o canal de atualização **edge**

Consulte [Canais de Versão](/pt/docs/release-channels) para obter detalhes sobre o que cada ambiente disponibiliza.

## O que o Servidor Comunica ao CLI

Quando o CLI se liga ao seu servidor, consulta `/.well-known/server-info` para descobrir:

- **Chave pública de encriptação E2E**: para armazenamento de configs com conhecimento zero
- **Versão mínima do CLI**: bloqueia CLIs desatualizados de se ligarem
- **Canal de atualização**: indica ao CLI qual o canal de versão a utilizar para atualizações
- **Ambiente**: qual o perfil de implantação em que o servidor está a executar (limites padrão vs. edge com limites 2X)

Esta autoconfiguração significa que os utilizadores só precisam do URL do servidor. Tudo o resto é descoberto automaticamente.

## Licenciamento para Implantações Air-Gapped

Os servidores on-premise air-gapped e auto-alojados emitem licenças localmente utilizando um **certificado de delegação** assinado pela chave mestre upstream. O certificado restringe o servidor on-premise aos limites do seu plano e cria uma cadeia à prova de adulteração. Consulte [Cadeia de Licença e Delegação](/pt/docs/license-chain) para o design criptográfico (integridade da cadeia, deteção de fork, provas de auditoria).

Esta secção abrange a configuração operacional: gerar chaves, solicitar o certificado, configurar a renovação automática e o fluxo de renovação offline (air-gapped).

### Uma subscrição, uma instalação on-premise

Uma subscrição pode ter **no máximo um certificado de delegação ativo de cada vez**. Cada instalação on-premise aplica os limites mensais e por máquina contra o seu próprio registo de emissão local, pelo que múltiplos certificados ativos multiplicariam a quota efetiva sem possibilidade de reconciliação.

Se precisar de ambientes separados (produção, staging, DR, multi-região), compre uma subscrição por instalação. A aplicação de único ativo codifica este contrato: uma tentativa de criar um segundo certificado ativo devolve `409 DELEGATION_CERT_ALREADY_ACTIVE` com o id do certificado existente e instruções para renovar (preferido, preserva a cadeia) ou revogar e criar (reinicia a cadeia).

### 1. Gerar o par de chaves Ed25519 on-premise

O servidor on-premise utiliza um par de chaves Ed25519 separado para assinar licenças. O certificado de delegação do upstream autoriza esta chave pública específica.

```bash
# Gerar um novo par de chaves
openssl genpkey -algorithm Ed25519 -out onprem-private.pem
openssl pkey -in onprem-private.pem -pubout -out onprem-public.pem

# Converter para base64 (o formato que o on-premise espera nas variáveis de ambiente)
ON_PREMISE_PRIVATE_KEY=$(openssl pkey -in onprem-private.pem -outform DER | base64 -w 0)
ON_PREMISE_PUBLIC_KEY=$(openssl pkey -in onprem-private.pem -pubout -outform DER | base64 -w 0)
```

Armazene a chave privada juntamente com os seus outros segredos (por exemplo, um Docker secret ou um Kubernetes Secret). Nunca sai do servidor on-premise.

### 2. Solicitar um certificado de delegação ao upstream

Pode solicitar o certificado ao portal de conta do upstream de três maneiras:

**Opção A: Autoatendimento do cliente (recomendado).** Inicie sessão no portal upstream como proprietário ou administrador da organização e vá a **/account/delegation-certs**. Clique em **Create New**, cole a chave pública on-premise (base64 SPKI), escolha uma validade (ou aceite a predefinição por plano) e transfira o ficheiro `.json` resultante.

**Opção B: Administrador (entre clientes).** O suporte do Rediacc ou o administrador do sistema upstream pode chamar `POST /admin/delegation-certs` com os mesmos parâmetros.

**Opção C: CLI `rdc` (planeado).** Um futuro comando do CLI irá encapsular o fluxo do portal.

O `.json` devolvido tem o seguinte aspeto:

```json
{
  "payload": "eyJ2ZXJzaW9uIjoxLCJzdWJzY3JpcHRpb25JZCI6...",
  "signature": "...",
  "publicKeyId": "..."
}
```

A validade do certificado é regida pela política de validade (predefinições e limites por plano, substituição por subscrição, limitada ao fim da subscrição + 3 dias de carência). A resposta também inclui `effectiveDays` e `reason` para que possa ver o motivo pelo qual esse valor foi escolhido. Consulte [Cadeia de Licença - Política de Validade](/pt/docs/license-chain) para as regras completas.

### 3. Instalar o certificado no servidor on-premise

O servidor lê o seu certificado de delegação de um único ficheiro no volume de dados, `/data/delegation-cert.json` (`DELEGATION_CERT_PATH`). Mais nada transporta um certificado: não existe uma variável de ambiente para isso. `rdc server install` coloca lá o certificado transferido, e `rdc server licence` substitui-o mais tarde:

```bash
rdc server install <domain> --cert delegation-cert.json
rdc server licence <domain> --cert delegation-cert.json
rdc server status <domain>
```

Ambos os comandos entregam o certificado ao servidor em execução através da sua caixa de entrada de certificados (`data/web/cert-inbox/new.json`). O servidor verifica-o e responde com `applied.json` ou `rejected.json`, e o comando confirma o id do novo certificado com `rdc server status` (os mesmos dados de `cert-status` do passo 6). `rdc server upgrade` usa a mesma caixa. Um passo da atualização move um `DELEGATION_CERT_BASE64` deixado em `secrets.env` para a caixa, de modo que uma máquina instalada antes de a caixa existir mantém o seu certificado.

O servidor carrega o certificado no arranque e compara-o com a chave com que assina licenças: a impressão digital da chave de assinatura tem de ser igual à do `delegatedPublicKey` do certificado, porque licenças assinadas com uma chave que o certificado não autoriza não seriam validáveis em nenhuma máquina. Mantenha sincronizados o par de chaves de assinatura e o `delegatedPublicKey` do certificado.

Um certificado que o servidor recusa no arranque (assinatura inválida, chave errada, `UPSTREAM_PUBLIC_KEY` em falta ou ficheiro malformado) não o impede de arrancar. O servidor inicia no nível gratuito e move o ficheiro defeituoso para `delegation-cert.rejected.json`, junto ao original. A assinatura de licenças de repositórios responde `503 DELEGATION_CERT_REFUSED` até haver um certificado válido, e `rdc server status` mostra `cert REFUSED (reason)`. Execute `rdc server licence` com um certificado válido para reparar. Um certificado expirado continua a ser carregado: degrada-se de forma suave em vez de ser recusado.

### 4. Configurar a verificação upstream e a renovação automática (opcional mas recomendado)

Se o seu on-premise tiver acesso HTTPS de saída ao upstream, configure a renovação automática para que o certificado seja atualizado antes de expirar sem intervenção manual:

```bash
# Necessário para /onprem/cert-upload verificar os certificados carregados face à chave mestre upstream.
# Falha imediatamente no arranque se UPSTREAM_API_KEY estiver definido sem isto.
UPSTREAM_PUBLIC_KEY="<chave pública SPKI Ed25519 mestre do upstream, base64>"

# Necessário para o ciclo de renovação automática. Obtenha via portal:
#   Proprietário/administrador da organização → /account/delegation-certs → "Get auto-renew token"
# Esta é a ÚNICA forma de obter um token de API com âmbito delegation:renew.
UPSTREAM_URL="https://www.rediacc.com"
UPSTREAM_API_KEY="rdt_..."

# Ajuste opcional (valores predefinidos mostrados).
AUTO_RENEW_INTERVAL_HOURS=24
RENEW_THRESHOLD_DAYS=14
```

O ciclo de renovação automática on-premise é executado uma vez no arranque e depois no intervalo configurado. Utiliza um **limiar adaptativo** (`min(env.RENEW_THRESHOLD_DAYS, ceil(certValidityDays / 3))`) para que um certificado COMMUNITY de 15 dias seja renovado com 5 dias restantes em vez de acionar a renovação no primeiro dia. Um certificado BUSINESS de 90 dias é renovado com 14 dias restantes (o limite configurado no ambiente).

Se a renovação falhar, o certificado permanece em uso até à expiração natural. A falha regride 1 hora e é registada em `${DELEGATION_CERT_PATH}.status.json` e exposta via `GET /onprem/cert-status`.

### 5. Renovação air-gapped (sem HTTPS de saída)

Se o seu on-premise não conseguir alcançar o upstream, utilize o fluxo de transferência manual:

1. **Transfira um pedido de renovação do portal de administração on-premise.** Como root do sistema on-premise, execute `GET /onprem/renewal-request`. Isto devolve um manifesto JSON contendo a cabeça da cadeia local, a chave pública delegada e uma assinatura Ed25519 à prova de adulteração da sua chave privada on-premise.
2. **Transfira o manifesto para o upstream** via USB, email encriptado ou qualquer canal fora de banda. O manifesto é pequeno (alguns KB) e não contém segredos.
3. **Processe o manifesto no upstream.** O proprietário/administrador da organização abre **/account/delegation-certs** → **Upload renewal request** → seleciona o ficheiro de manifesto. O upstream verifica a assinatura do manifesto face à `delegatedPublicKey` do certificado ativo (prova que veio de um titular da chave privada on-premise), verifica o anti-replay (manifestos com mais de 7 dias são rejeitados) e emite um novo certificado.
4. **Transfira o novo certificado** do portal upstream como ficheiro `.json`.
5. **Transfira o certificado de volta** para o on-premise.
6. **Carregue para o on-premise** via o portal de administração local (`POST /onprem/cert-upload`). O on-premise verifica o novo certificado face a `UPSTREAM_PUBLIC_KEY` e valida que o `genesisSequence` do certificado ainda está ligado a uma entrada da cadeia no registo de emissão local (o avanço da sequência durante o trânsito é suportado - a cadeia estende-se naturalmente).

Todo este ciclo nunca requer saída de rede do on-premise.

#### Modos de falha do manifesto

| Código | Causa | Correção |
|---|---|---|
| `NO_ACTIVE_CERT` | O upstream não tem certificado ativo para esta subscrição | Emita um novo certificado através do fluxo de criação em vez de renovar |
| `DELEGATED_KEY_MISMATCH` | A `delegatedPublicKey` do manifesto difere do certificado ativo | O manifesto pode ser uma repetição de uma instalação on-premise diferente |
| `MANIFEST_SIGNATURE_INVALID` | A assinatura não verifica face à chave pública delegada | O manifesto foi adulterado em trânsito, ou foi gerado noutro on-premise |
| `MANIFEST_EXPIRED` | O manifesto tem mais de 7 dias | Gere um novo pedido de renovação a partir do on-premise |

#### Modos de falha de carregamento do certificado

`POST /onprem/cert-upload` responde `{uploaded: true, bootstrap, certId}` em caso de sucesso. Um certificado recusado devolve `{error, code}`: `error` traz o detalhe e `code` é um dos motivos da tabela. Cada certificado aplicado ou rejeitado fica registado no log e é enviado por e-mail ao proprietário da máquina.

`rdc server licence` deposita o certificado por SSH na caixa de entrada da máquina (`data/web/cert-inbox`) e volta a ler `applied.json` ou `rejected.json`. Depois confirma o novo id do certificado através de `cert-status`. Uma rejeição traz os mesmos motivos, mais `not-a-regular-file` e `too-large`, gerados pela própria caixa de entrada.

| Código | HTTP | Causa |
|---|---|---|
| `malformed` | 400 | O ficheiro enviado não é um certificado válido |
| `bad-signature` | 400 | O certificado não está assinado com a `UPSTREAM_PUBLIC_KEY` configurada |
| `wrong-key` | 400 | O certificado foi emitido para uma chave diferente da desta instalação on-premise |
| `expired` | 400 | O certificado já passou o seu `validUntil` |
| `not-newer` | 409 | O certificado não é mais recente do que o que está em vigor |
| `other-subscription` | 409 | O certificado pertence a outra subscrição |
| `chain-ahead` | 409 | O `genesisSequence` do certificado está à frente da cabeça da cadeia local |
| `chain-fork` | 409 | O hash da cadeia no `genesisSequence` do certificado não coincide com o registo local |
| `no-upstream-key` | 500 | `UPSTREAM_PUBLIC_KEY` não está configurada |
| `write-failed` | 500 | Não foi possível gravar o certificado em disco |
| `adoption-failed` | 500 | O servidor não conseguiu carregar o certificado gravado |

### 6. Estado e monitorização

Consulte o estado do certificado local on-premise a qualquer momento:

```bash
curl https://onprem.example.com/account/api/v1/onprem/cert-status \
  -H "Cookie: <admin session>"
```

Devolve o `subscriptionId`, `planCode`, `validUntil`, `daysUntilExpiry` do certificado carregado, mais o bloco `autoRenew` (`enabled`, `lastSuccessAt`, `lastErrorAt`, `lastError`). Integre isto na sua pilha de monitorização para alertar sobre `lastSuccessAt` desatualizado ou `lastError` não nulo.

Para backup e auditoria, o administrador on-premise também pode transferir o certificado assinado atualmente carregado via `GET /onprem/cert-current` (requer sessão elevada).

### Referência de variáveis de ambiente do certificado de delegação

| Variável | Obrigatória? | Finalidade |
|---|---|---|
| `ON_PREMISE_MODE` | Sim | Definir como `true` para ativar o subconjunto de rotas on-premise |
| `ON_PREMISE_PRIVATE_KEY` | Sim | Chave privada Ed25519 PKCS8 em Base64 para assinatura delegada |
| `ON_PREMISE_PUBLIC_KEY` | Sim | Chave pública Ed25519 SPKI em Base64 (deve corresponder à `delegatedPublicKey` do certificado) |
| `DELEGATION_CERT_PATH` | Opcional | Caminho do sistema de ficheiros para o JSON do certificado assinado. Predefinição `/data/delegation-cert.json` no volume de dados. Substitua o certificado com `rdc server licence`, não à mão. |
| `UPSTREAM_PUBLIC_KEY` | Obrigatório se `UPSTREAM_API_KEY` estiver definido, ou para `/onprem/cert-upload` funcionar | SPKI Base64 da chave pública mestre do upstream. Falha imediatamente no arranque se estiver em falta. |
| `UPSTREAM_URL` | Para renovação automática | URL base do servidor de conta upstream, p. ex. `https://www.rediacc.com` |
| `UPSTREAM_API_KEY` | Para renovação automática | Um token de API com âmbito `delegation:renew`. Obtenha via portal - consulte o Passo 4. |
| `AUTO_RENEW_INTERVAL_HOURS` | Opcional | Predefinição 24. Com que frequência verificar se o certificado precisa de renovação. |
| `RENEW_THRESHOLD_DAYS` | Opcional | Predefinição 14. Atua como limite no limiar adaptativo de 1/3 da validade. |

### Resumo do modelo de ameaça

O modelo de certificado de delegação defende contra:

- **Licenças falsificadas**: o on-premise só pode assinar dentro dos limites do seu plano; o renet rejeita qualquer coisa fora dos limites do certificado.
- **Partilha de certificados entre implantações**: a divergência de cadeia é detetada na renovação (devolve `CHAIN_FORK_DETECTED`).
- **Contornar a quota via multi-instalação**: aplicado no upstream por único ativo (um certificado por subscrição).
- **Reversão de cadeia**: o renet armazena a sequência mais alta vista por subscrição e rejeita qualquer blob com uma sequência inferior.
- **Credenciais upstream comprometidas**: o token de arranque `delegation:renew` só pode ser criado via o endpoint dedicado do portal e é restrito a administradores. O token concede apenas renovação - não pode ler ou modificar qualquer outro recurso.
- **Ataques de repetição em manifestos**: manifestos com mais de 7 dias são rejeitados.

O que **não** defende:

- **Chave privada on-premise comprometida**: uma chave privada vazada permite a um atacante assinar licenças até ao `validUntil` do certificado. Mitigação: rodar o par de chaves (revogar o certificado antigo e criar um novo com a nova chave) e tratar todas as licenças assinadas pela chave antiga como suspeitas.
- **Chave mestre upstream comprometida**: esta é a raiz de confiança. Os procedimentos de rotação estão fora do âmbito aqui.
