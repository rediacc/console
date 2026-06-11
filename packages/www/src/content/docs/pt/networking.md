---
title: "Redes"
description: "Exponha serviços com o proxy reverso, etiquetas Docker, certificados TLS, DNS e encaminhamento de portas TCP/UDP."
category: "Guides"
order: 6
language: pt
sourceHash: "2bb63d224370c266"
sourceCommit: "20f014619af1ee41e75cd46a3c8e4abc5add0983"
---

# Redes

Esta página explica como os serviços que correm dentro de daemons Docker isolados ficam acessíveis a partir da internet. Abrange o sistema de proxy reverso, etiquetas Docker para encaminhamento, certificados TLS, DNS e encaminhamento de portas TCP/UDP.

Para saber como os serviços obtêm os seus IPs de loopback e o sistema de slots `.rediacc.json`, consulte [Serviços](/pt/docs/services#service-networking-rediaccjson).

## Isolamento de Rede

Cada repositório é automaticamente isolado ao nível do kernel usando hooks de rede. Isto requer o kernel Linux 6.1 ou posterior. Não é necessária qualquer configuração.

- **Reescrita automática de bind**: Os serviços podem fazer bind a `0.0.0.0` ou `127.0.0.1` como habitualmente. O kernel reescreve transparentemente o endereço para o IP de loopback atribuído ao serviço. Não é necessário fazer bind explicitamente a `${SERVICE_IP}`.
- **Bloqueio de conexões entre repositórios**: Se um serviço tentar conectar a um IP de loopback fora da sub-rede `/26` do seu repositório, o kernel bloqueia-o. Um processo no repositório A não consegue alcançar serviços no repositório B. Os forks são a única exceção: as suas conexões para a sub-rede do pai são redirecionadas para os serviços do próprio fork (consulte [Limites](/pt/docs/limits)); o pai em si permanece inacessível.
- **Sem alterações à aplicação necessárias**: Os serviços usam `0.0.0.0` ou `localhost` para bind, e o kernel garante que apenas ouvem no seu IP de loopback correto. O isolamento é totalmente transparente.

## Como Funciona

O Rediacc usa um sistema de proxy de dois componentes para encaminhar tráfego externo para contentores:

1. **Servidor de rotas**, um serviço systemd que descobre contentores em execução em todos os daemons Docker de repositório. Inspeciona as etiquetas dos contentores e gera a configuração de encaminhamento, servida como endpoint YAML.
2. **Traefik**, um proxy reverso que consulta o servidor de rotas a cada 5 segundos e aplica as rotas descobertas. Trata do encaminhamento HTTP/HTTPS, terminação TLS e encaminhamento TCP/UDP.

O fluxo é o seguinte:

```
Internet → Traefik (ports 80/443/TCP/UDP)
               ↓ polls every 5s
           Route Server (discovers containers)
               ↓ inspects labels
           Docker Daemons (/var/run/rediacc/docker-*.sock)
               ↓
           Containers (bound to 127.x.x.x loopback IPs)
```

Quando adiciona as etiquetas corretas a um contentor e o inicia com `renet compose`, fica automaticamente encaminhável, sem necessidade de configuração manual do proxy.

> O binário do servidor de rotas é mantido sincronizado com a versão da sua CLI. Quando a CLI atualiza o binário renet numa máquina, o servidor de rotas é automaticamente reiniciado (aprox. 1 a 2 segundos). Isto não causa tempo de inatividade; o Traefik continua a servir tráfego com a sua última configuração conhecida durante o reinício e aplica a nova configuração na próxima consulta. As conexões de clientes existentes não são afetadas. Os seus contentores de aplicação não são tocados.

## Etiquetas Docker

O encaminhamento é controlado por etiquetas de contentor Docker. Existem dois níveis:

### Nível 1: Etiquetas `rediacc.*` (Automáticas)

Estas etiquetas são **injetadas automaticamente** pelo `renet compose` ao iniciar serviços. Não precisa de as adicionar manualmente.

| Etiqueta | Descrição | Exemplo |
|-------|-------------|---------|
| `rediacc.service_name` | Identidade do serviço | `myapp` |
| `rediacc.service_ip` | IP de loopback atribuído | `127.0.11.2` |
| `rediacc.network_id` | ID do daemon do repositório | `2816` |
| `rediacc.repo_name` | Nome do repositório | `marketing` |
| `rediacc.tcp_ports` | Portas TCP em que o serviço ouve | `8080,8443` |
| `rediacc.udp_ports` | Portas UDP em que o serviço ouve | `53` |

Quando um contentor tem apenas etiquetas `rediacc.*` (sem `traefik.enable=true`), o servidor de rotas gera uma **rota automática** usando o nome do repositório e o subdomínio da máquina:

```
{service}.{repoName}.{machineName}.{baseDomain}
```

Por exemplo, um serviço chamado `myapp` num repositório chamado `marketing` na máquina `server-1` com domínio base `example.com` obtém:

```
myapp.marketing.server-1.example.com
```

Para forks, o nome do serviço é combinado com a palavra reservada `fork` e a tag:

```
{service}-fork-{tag}.{repoName}.{machineName}.{baseDomain}
```

Por exemplo, um fork de `marketing` com a tag `staging` obtém:

```
myapp-fork-staging.marketing.server-1.example.com
```

Cada URL de fork fica sob o subdomínio do repositório pai e é coberto pelo seu certificado wildcard existente, pelo que não é necessário nenhum novo certificado. O separador `-fork-` previne colisões com nomes de serviços reais no repositório de produção. Para serviços com domínios personalizados, use etiquetas de Nível 2 ou a etiqueta `rediacc.domain`.

#### Domínio Personalizado via `rediacc.domain`

Pode definir um domínio personalizado para um serviço usando a etiqueta `rediacc.domain` no seu `docker-compose.yml`. Tanto nomes curtos como domínios completos são suportados:

```yaml
labels:
  # Short name, resolved to cloud.example.com using the machine's baseDomain
  - "rediacc.domain=cloud"

  # Full domain, used as-is
  - "rediacc.domain=cloud.example.com"
```

Um valor sem pontos é tratado como nome curto e o `baseDomain` da máquina é acrescentado automaticamente. Um valor com pontos é usado como domínio completo. Isto aplica-se tanto à geração de rotas automáticas como à exibição na CLI.

Quando `machineName` está configurado, os serviços com domínio personalizado obtêm **duas rotas**: uma no domínio base (`cloud.example.com`) e outra no subdomínio da máquina (`cloud.server-1.example.com`).

### Nível 2: Etiquetas `traefik.*` (Definidas pelo Utilizador)

Adicione estas etiquetas ao seu `docker-compose.yml` quando pretender encaminhamento de domínio personalizado, TLS ou entrypoints específicos. Definir `traefik.enable=true` indica ao servidor de rotas para usar as suas regras personalizadas em vez de gerar uma rota automática.

```yaml
labels:
  - "traefik.enable=true"
  - "traefik.http.routers.myapp.rule=Host(`app.example.com`)"
  - "traefik.http.routers.myapp.entrypoints=websecure,websecure-v6"
  - "traefik.http.routers.myapp.tls.certresolver=letsencrypt"
  - "traefik.http.services.myapp.loadbalancer.server.port=8080"
```

Estas usam a [sintaxe de etiquetas padrão do Traefik v3](https://doc.traefik.io/traefik/routing/providers/docker/).

> **Dica:** Os serviços apenas internos (bases de dados, caches, filas de mensagens) **não** devem ter `traefik.enable=true`. Apenas necessitam de etiquetas `rediacc.*`, que são injetadas automaticamente.

## Expor Serviços HTTP/HTTPS

### Pré-requisitos

1. Infraestrutura configurada na máquina ([Configuração de Máquina, Configuração de Infraestrutura](/pt/docs/setup#infrastructure-configuration)):

   ```bash
   # Credenciais partilhadas (uma vez por configuração, aplica-se a todas as máquinas)
   rdc config infra set -m server-1 \
     --cert-email admin@example.com \
     --cf-dns-token your-cloudflare-api-token

   # Definições específicas da máquina
   rdc config infra set -m server-1 \
     --public-ipv4 203.0.113.50 \
     --base-domain example.com

   rdc config infra push -m server-1
   ```

2. Registos DNS a apontar o seu domínio para o IP público do servidor (ver [Configuração de DNS](#dns-configuration) abaixo).

### Adicionar Etiquetas

Adicione etiquetas `traefik.*` aos serviços que pretende expor no seu `docker-compose.yml`:

```yaml
services:
  myapp:
    image: myapp:latest
    environment:
      - LISTEN_ADDR=0.0.0.0:8080
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.myapp.rule=Host(`app.example.com`)"
      - "traefik.http.routers.myapp.entrypoints=websecure,websecure-v6"
      - "traefik.http.routers.myapp.tls.certresolver=letsencrypt"
      - "traefik.http.services.myapp.loadbalancer.server.port=8080"

  database:
    image: postgres:17
    # No traefik labels, database is internal only
```

| Etiqueta | Finalidade |
|-------|---------|
| `traefik.enable=true` | Ativa o encaminhamento Traefik personalizado para este contentor |
| `traefik.http.routers.{name}.rule` | Regra de encaminhamento, tipicamente `Host(\`domain\`)` |
| `traefik.http.routers.{name}.entrypoints` | Em que portas ouvir: `websecure` (HTTPS IPv4), `websecure-v6` (HTTPS IPv6) |
| `traefik.http.routers.{name}.tls.certresolver` | Resolvedor de certificados; use `letsencrypt` para Let's Encrypt automático |
| `traefik.http.services.{name}.loadbalancer.server.port` | A porta em que a sua aplicação ouve dentro do contentor |

O `{name}` nas etiquetas é um identificador arbitrário. Apenas precisa de ser consistente entre as etiquetas de router/serviço/middleware relacionadas.

> **Nota:** As etiquetas `rediacc.*` (`rediacc.service_name`, `rediacc.service_ip`, `rediacc.network_id`) são injetadas automaticamente pelo `renet compose`. Não precisa de as adicionar ao seu ficheiro compose.

## Certificados TLS

Os certificados TLS são obtidos automaticamente via Let's Encrypt usando o desafio DNS-01 da Cloudflare. As credenciais são configuradas uma vez por configuração (partilhadas por todas as máquinas):

```bash
rdc config infra set -m server-1 \
  --cert-email admin@example.com \
  --cf-dns-token your-cloudflare-api-token
```

As rotas automáticas usam **certificados wildcard** ao nível do subdomínio do repositório (`*.marketing.server-1.example.com`) em vez de certificados por serviço. O certificado é provisionado automaticamente pelo Traefik no primeiro `repo up`; não é necessário nenhum passo manual. Os forks reutilizam o wildcard existente do repositório pai, pelo que nunca acionam um novo pedido de certificado. As rotas de domínio personalizado usam wildcards ao nível da máquina (`*.server-1.example.com`).

> **Requer credenciais Cloudflare.** Os certificados wildcard usam o desafio DNS-01. Sem `--cf-dns-token` (e opcionalmente `--cert-email`), o Traefik não consegue completar o desafio e HTTPS não funcionará. HTTP permanece funcional. Configure as credenciais com `rdc config infra set` antes da primeira implementação.

Para rotas de Nível 2 com `traefik.http.routers.{name}.tls.certresolver=letsencrypt`, os SANs de domínio wildcard são injetados automaticamente com base no hostname da rota.

O token de API DNS da Cloudflare precisa de permissão `Zone:DNS:Edit` para os domínios que pretende proteger.

### Ciclo de Vida do Certificado TLS

O caminho completo que um certificado Let's Encrypt percorre desde a emissão até aos contentores de cada repositório:

1. **Emissão no host.** Um contentor Traefik ao nível da máquina (`rediacc-proxy`, implementado em `/opt/rediacc/proxy/`) é responsável pela renovação ACME. Armazena todo o estado em `/opt/rediacc/proxy/letsencrypt/acme.json` no host. A renovação aciona automaticamente aproximadamente 30 dias antes da expiração; não é necessária nenhuma ação do operador enquanto `--cf-dns-token` estiver configurado.

2. **Despejo por repositório (opcional).** Os serviços que precisam de ficheiros de certificado dentro do seu próprio contentor (por exemplo, um servidor de correio que lê um `.pem` diretamente) implementam um pequeno contentor `traefik-certs-dumper` ao seu lado. O dumper monta `/opt/rediacc/proxy/letsencrypt` apenas para leitura e escreve o certificado + chave extraídos no volume de dados do repositório como `cert.pem` / `key.pem`. Para que isto funcione, o daemon Docker por repositório deve ter `/opt/rediacc/proxy` na lista de permissões do namespace de montagem. Isto já está incluído por predefinição.

3. **Cache do lado do cliente (`rediacc.json`).** A CLI guarda em cache uma cópia comprimida de `acme.json` em `acmeCertCache` no seu ficheiro de configuração, com chave por `baseDomain`. Isto permite que múltiplas máquinas partilhem certificados (via `rdc config cert-cache push -m <machine>`) e serve como inventário offline.

**Acionadores de sincronização para a cache do cliente:**

- Automaticamente após `rdc repo up`, mas apenas se a cache local para o `baseDomain` da máquina tiver mais de 6 horas. As caches recentes são deixadas intactas para que implementações consecutivas não sobrecarreguem o SSH.
- A pedido: `rdc config cert-cache pull -m <machine>` (forçar pull) ou `rdc machine query --name <machine> --sync-certs` (pull como efeito secundário de uma consulta de estado).
- Em `rdc config infra push`, a cache é enviada para a máquina (certificados locais com validade mais longa ganham sobre os remotos).

**Manutenção da cache:**

- As entradas de rota automática obsoletas (domínios antigos com tag de ID de rede como `service-3200.rediacc.io`) são podadas em cada pull.
- Os certificados cujo `notAfter` é mais de 7 dias no passado são removidos completamente. São inertes e apenas congestionam a cache.
- `rdc config cert-cache clear` limpa tudo; `rdc config cert-cache status` mostra o inventário.

**Resolução de problemas:** se `traefik-certs-dumper` entrar em crashloop com `/traefik/acme.json: no such file or directory`, o daemon por repositório não consegue ver o repositório letsencrypt do host. Verifique (a) se `/opt/rediacc/proxy/letsencrypt/acme.json` existe no host (esta é responsabilidade do `rediacc-proxy` ao nível do host) e (b) se o daemon por repositório foi iniciado com uma versão de renet suficientemente recente que inclui `/opt/rediacc/proxy` na lista de permissões. Reimplemente o repositório com `rdc repo up` após atualizar o renet para aplicar.

> **Experimental:** A cadência de sincronização automática e a poda baseada em expiração foram incluídas no renet 0.9+. Versões mais antigas da CLI/renet usam sincronização puramente manual via `rdc config cert-cache pull`.

## Encaminhamento de Portas TCP/UDP

Para protocolos não-HTTP (servidores de correio, DNS, bases de dados expostas externamente), use o encaminhamento de portas TCP/UDP.

### Passo 1: Registar Portas

Adicione as portas necessárias durante a configuração de infraestrutura:

```bash
rdc config infra set -m server-1 \
  --tcp-ports 25,143,465,587,993 \
  --udp-ports 53

rdc config infra push -m server-1
```

Isto cria entrypoints Traefik com o nome `tcp-{port}` e `udp-{port}`.

> Após adicionar ou remover portas, execute sempre `rdc config infra push` novamente para atualizar a configuração do proxy.

### Passo 2: Adicionar Etiquetas TCP/UDP

Use etiquetas `traefik.tcp.*` ou `traefik.udp.*` no seu ficheiro compose:

```yaml
services:
  mail-server:
    image: ghcr.io/docker-mailserver/docker-mailserver:latest
    labels:
      - "traefik.enable=true"

      # SMTP (port 25)
      - "traefik.tcp.routers.mail-smtp.entrypoints=tcp-25"
      - "traefik.tcp.routers.mail-smtp.rule=HostSNI(`*`)"
      - "traefik.tcp.routers.mail-smtp.service=mail-smtp"
      - "traefik.tcp.services.mail-smtp.loadbalancer.server.port=25"

      # IMAPS (port 993), TLS passthrough
      - "traefik.tcp.routers.mail-imaps.entrypoints=tcp-993"
      - "traefik.tcp.routers.mail-imaps.rule=HostSNI(`mail.example.com`)"
      - "traefik.tcp.routers.mail-imaps.tls.passthrough=true"
      - "traefik.tcp.routers.mail-imaps.service=mail-imaps"
      - "traefik.tcp.services.mail-imaps.loadbalancer.server.port=993"
```

Conceitos-chave:
- **`HostSNI(\`*\`)`** corresponde a qualquer hostname (para protocolos que não enviam SNI, como SMTP simples)
- **`tls.passthrough=true`** significa que o Traefik encaminha a conexão TLS bruta sem desencriptar; a aplicação trata o TLS por si mesma
- Os nomes de entrypoint seguem a convenção `tcp-{port}` ou `udp-{port}`

### Exemplo TCP Simples (Base de Dados)

Para expor uma base de dados externamente sem passthrough TLS (o Traefik encaminha TCP bruto):

```yaml
services:
  postgres:
    image: postgres:17
    labels:
      - "traefik.enable=true"
      - "traefik.tcp.routers.mydb.entrypoints=tcp-5432"
      - "traefik.tcp.routers.mydb.rule=HostSNI(`*`)"
      - "traefik.tcp.services.mydb.loadbalancer.server.port=5432"
```

A porta 5432 está pré-configurada (ver abaixo), pelo que não é necessária nenhuma configuração `--tcp-ports`.

> **Nota de segurança:** Expor uma base de dados à internet é um risco. Use isto apenas quando os clientes remotos precisam de acesso direto. Para a maioria das configurações, mantenha a base de dados interna e conecte-se através da sua aplicação.

### Portas Pré-Configuradas

As seguintes portas TCP/UDP têm entrypoints por predefinição (não é necessário adicionar via `--tcp-ports`). Os entrypoints são gerados apenas para as famílias de endereços configuradas; os entrypoints IPv4 requerem `--public-ipv4`, os entrypoints IPv6 requerem `--public-ipv6`:

| Porta | Protocolo | Uso Comum |
|------|----------|------------|
| 80 | HTTP | Web (redirecionamento automático para HTTPS) |
| 443 | HTTPS | Web (TLS) |
| 3306 | TCP | MySQL/MariaDB |
| 5432 | TCP | PostgreSQL |
| 6379 | TCP | Redis |
| 27017 | TCP | MongoDB |
| 11211 | TCP | Memcached |
| 5672 | TCP | RabbitMQ |
| 9092 | TCP | Kafka |
| 53 | UDP | DNS |
| 10000-10010 | TCP | Intervalo dinâmico (alocação automática) |

## Configuração de DNS

### DNS Automático (Cloudflare)

Quando `--cf-dns-token` está configurado, `rdc config infra push` cria automaticamente registos DNS para o subdomínio da máquina na Cloudflare:

| Registo | Tipo | Conteúdo | Criado por |
|--------|------|---------|------------|
| `server-1.example.com` | A / AAAA | IP público da máquina | `push-infra` |
| `*.server-1.example.com` | A / AAAA | IP público da máquina | `push-infra` |
| `*.marketing.server-1.example.com` | A / AAAA | IP público da máquina | `repo up` |

Os registos ao nível da máquina são criados pelo `push-infra` e cobrem as rotas de domínio personalizado (`rediacc.domain`). Os registos wildcard por repositório são criados automaticamente pelo `repo up` e cobrem as rotas automáticas para esse repositório.

Isto é idempotente: os registos existentes são atualizados se o IP mudar e deixados inalterados se já estiverem corretos.

O wildcard do domínio base (`*.example.com`) deve ser criado manualmente se usar etiquetas de domínio personalizado como `rediacc.domain=erp`.

### DNS Manual

Se não usar a Cloudflare ou gerir o DNS manualmente, crie registos A (IPv4) e/ou AAAA (IPv6):

```
# Machine subdomain (for custom domain routes like rediacc.domain=erp)
server-1.example.com           A     203.0.113.50
*.server-1.example.com         A     203.0.113.50
*.server-1.example.com         AAAA  2001:db8::1

# Per-repo wildcards (for auto-routes like myapp.marketing.server-1.example.com)
*.marketing.server-1.example.com    A     203.0.113.50
*.marketing.server-1.example.com    AAAA  2001:db8::1

# Base domain wildcard (for custom domain services like rediacc.domain=erp)
*.example.com                  A     203.0.113.50
```

Com o DNS da Cloudflare configurado, os registos wildcard por repositório são criados automaticamente pelo `repo up`. Com múltiplas máquinas, cada máquina obtém os seus próprios registos DNS apontando para o seu próprio IP.

## Middlewares

Os middlewares do Traefik modificam pedidos e respostas. Aplique-os via etiquetas.

### HSTS (HTTP Strict Transport Security)

```yaml
labels:
  - "traefik.http.middlewares.myapp-hsts.headers.stsSeconds=15768000"
  - "traefik.http.middlewares.myapp-hsts.headers.stsIncludeSubdomains=true"
  - "traefik.http.middlewares.myapp-hsts.headers.stsPreload=true"
  - "traefik.http.routers.myapp.middlewares=myapp-hsts"
```

### Buffering para Upload de Ficheiros Grandes

```yaml
labels:
  - "traefik.http.middlewares.myapp-buffering.buffering.maxRequestBodyBytes=536870912"
  - "traefik.http.routers.myapp.middlewares=myapp-buffering"
```

### Múltiplos Middlewares

Encadeie middlewares separando-os por vírgula:

```yaml
labels:
  - "traefik.http.routers.myapp.middlewares=myapp-hsts,myapp-buffering"
```

Para a lista completa de middlewares disponíveis, consulte a [documentação de middlewares do Traefik](https://doc.traefik.io/traefik/middlewares/overview/).

## Diagnósticos

Se um serviço não estiver acessível, faça SSH para o servidor e verifique os endpoints do servidor de rotas:

### Verificação de Estado

```bash
curl -s http://127.0.0.1:7111/health | python3 -m json.tool
```

Mostra o estado geral, o número de routers e serviços descobertos e se as rotas automáticas estão ativadas.

### Rotas Descobertas

```bash
curl -s http://127.0.0.1:7111/routes.json | python3 -m json.tool
```

Lista todos os routers HTTP, TCP e UDP com as suas regras, entrypoints e serviços de backend.

### Alocações de Portas

```bash
curl -s http://127.0.0.1:7111/ports | python3 -m json.tool
```

Mostra mapeamentos de portas TCP e UDP para portas alocadas dinamicamente.

### Problemas Comuns

| Problema | Causa | Solução |
|---------|-------|----------|
| Serviço não está nas rotas | Contentor não está a correr ou etiquetas em falta | Verificar com `docker ps` no daemon do repositório; verificar etiquetas |
| Certificado não emitido | DNS não aponta para o servidor, ou token Cloudflare inválido | Verificar resolução DNS; verificar permissões do token de API Cloudflare |
| 502 Bad Gateway | Aplicação não está a ouvir na porta declarada | Verificar se a aplicação está a correr e se a porta corresponde a `loadbalancer.server.port` |
| Porta TCP não acessível | Porta não registada na infraestrutura | Executar `rdc config infra set --tcp-ports ...` e `push-infra` |
| Servidor de rotas a correr versão antiga | Binário foi atualizado mas o serviço não foi reiniciado | Acontece automaticamente no provisionamento; manual: `sudo systemctl restart rediacc-router` |
| Relay STUN/TURN não acessível | Endereços de relay em cache no arranque | Recriar o serviço após alterações de DNS ou IP para que aplique a nova configuração de rede |

## Exemplo Completo

Este exemplo implementa uma aplicação web com uma base de dados PostgreSQL. A aplicação é publicamente acessível em `app.example.com` com TLS; a base de dados é apenas interna.

### docker-compose.yml

```yaml
services:
  webapp:
    image: myregistry/webapp:latest
    environment:
      DATABASE_URL: postgresql://app:changeme@postgres:5432/webapp
      LISTEN_ADDR: 0.0.0.0:3000
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.webapp.rule=Host(`app.example.com`)"
      - "traefik.http.routers.webapp.entrypoints=websecure,websecure-v6"
      - "traefik.http.routers.webapp.tls.certresolver=letsencrypt"
      - "traefik.http.services.webapp.loadbalancer.server.port=3000"
      # HSTS
      - "traefik.http.middlewares.webapp-hsts.headers.stsSeconds=15768000"
      - "traefik.http.middlewares.webapp-hsts.headers.stsIncludeSubdomains=true"
      - "traefik.http.routers.webapp.middlewares=webapp-hsts"

  postgres:
    image: postgres:17
    environment:
      POSTGRES_DB: webapp
      POSTGRES_USER: app
      POSTGRES_PASSWORD: changeme
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
    # No traefik labels, internal only
```

### Rediaccfile

```bash
#!/bin/bash

up() {
    mkdir -p data/postgres
    renet compose -- up -d
}

down() {
    renet compose -- down
}
```

### DNS

Crie um registo A a apontar `app.example.com` para o IP público do seu servidor:

```
app.example.com   A   203.0.113.50
```

### Implementar

```bash
rdc repo up --name my-app -m server-1
```

Em poucos segundos, o servidor de rotas descobre o contentor, o Traefik aplica a rota, solicita um certificado TLS e `https://app.example.com` fica disponível.
