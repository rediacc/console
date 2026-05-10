---
title: "Guia de Migração"
description: "Migre projetos existentes para repositórios Rediacc encriptados."
category: "Guides"
order: 11
language: pt
sourceHash: "feb1fcafc824b4b2"
---

# Guia de Migração

Migre um projeto existente, ficheiros, serviços Docker e bases de dados de um servidor tradicional ou ambiente de desenvolvimento local para um repositório Rediacc encriptado.

## Pré-requisitos

- CLI `rdc` instalada ([Instalação](/pt/docs/installation))
- Uma máquina adicionada e provisionada ([Configuração](/pt/docs/setup))
- Espaço em disco suficiente no servidor para o seu projeto (verificar com `rdc machine status`)

## Passo 1: Criar um Repositório

Crie um repositório encriptado dimensionado para o seu projeto. Aloque espaço extra para imagens Docker e dados de contentores.

```bash
rdc repo create --name my-project -m server-1 --size 20G
```

> **Dica:** Pode redimensionar mais tarde com `rdc repo resize` se necessário, mas o repositório deve estar desmontado primeiro. É mais fácil começar com espaço suficiente.

## Passo 2: Carregar os Seus Ficheiros

Use `rdc repo sync upload` para transferir os ficheiros do seu projeto para o repositório.

```bash
# Pré-visualizar o que será transferido (sem alterações)
rdc repo sync upload -m server-1 -r my-project --local ./my-project --dry-run

# Carregar ficheiros
rdc repo sync upload -m server-1 -r my-project --local ./my-project
```

O repositório deve estar montado antes de carregar. Se não estiver:

```bash
rdc repo mount --name my-project -m server-1
```

Para sincronizações subsequentes onde pretende que o remoto corresponda exatamente ao diretório local:

```bash
rdc repo sync upload -m server-1 -r my-project --local ./my-project --mirror
```

> O sinalizador `--mirror` elimina ficheiros no remoto que não existem localmente. Use `--dry-run` primeiro para verificar.

## Passo 3: Corrigir a Propriedade dos Ficheiros

Os ficheiros carregados chegam com o UID do utilizador local (por exemplo, 1000). O Rediacc usa um utilizador universal (UID 7111) para que o VS Code, as sessões de terminal e as ferramentas tenham acesso consistente. Execute o comando de propriedade para converter:

```bash
rdc repo ownership --name my-project -m server-1
```

### Exclusão com Reconhecimento de Docker

Se os contentores Docker estiverem a correr (ou tiverem sido executados), o comando de propriedade deteta automaticamente os seus diretórios de dados graváveis e **ignora-os**. Isto impede a quebra de contentores que gerem os seus próprios ficheiros com UIDs diferentes (por exemplo, o MariaDB usa o UID 999, o Nextcloud usa o UID 33).

O comando reporta o que faz:

```
Excluding Docker volume: database/data
Excluding Docker volume: redis/data
Ownership set to UID 7111 (245 changed, 4 skipped, 0 errors)
```

### Quando Executar

- **Após carregar ficheiros**, para converter o UID local para 7111
- **Após iniciar contentores**, se pretende que os diretórios de volumes Docker sejam automaticamente excluídos. Se os contentores ainda não foram iniciados, não há volumes a excluir e todos os diretórios ficam com chown aplicado (o que é correto, os contentores recriam os seus dados no primeiro arranque)

### Modo Forçado

Para ignorar a deteção de volumes Docker e aplicar chown a tudo, incluindo diretórios de dados de contentores:

```bash
rdc repo ownership --name my-project -m server-1
```

> **Aviso:** Isto pode quebrar contentores em execução. Pare-os primeiro com `rdc repo down` se necessário.

### UID Personalizado

Para definir um UID diferente do predefinido 7111:

```bash
rdc repo ownership --name my-project -m server-1 --uid 1000
```

## Passo 4: Configurar o Seu Rediaccfile

Crie um `Rediaccfile` na raiz do seu projeto. Este script Bash define como os seus serviços são iniciados e parados.

```bash
#!/bin/bash

up() {
    renet compose -- up -d
}

down() {
    renet compose -- down
}
```

As duas funções de ciclo de vida:

| Função | Finalidade | Comportamento em erro |
|----------|---------|----------------|
| `up()` | Iniciar serviços | Falha na raiz é crítica; falhas em subdiretórios são registadas e continuam |
| `down()` | Parar serviços | Best-effort: tenta sempre todos |

> **Importante:** Use sempre `renet compose --` em vez de `docker compose` no seu Rediaccfile. O wrapper `renet compose` impõe rede host, capacidades de checkpoint/restore CRIU, alocação de IP e descoberta de serviços necessárias pelo renet-proxy. Usar `docker compose` diretamente contorna tudo isso e será rejeitado durante a validação.
>
> Nunca use `sudo docker` também, o `sudo` repõe variáveis de ambiente incluindo `DOCKER_HOST`, o que faz com que os contentores sejam criados no daemon Docker do sistema em vez do daemon isolado do repositório. As funções do Rediaccfile já correm com privilégios suficientes.

Consulte [Serviços](/pt/docs/services) para detalhes completos sobre Rediaccfiles, layouts multi-serviço e ordem de execução.

## Passo 5: Configurar a Rede dos Serviços

O Rediacc corre um daemon Docker isolado por repositório. Os serviços usam `network_mode: host` e fazem bind a IPs de loopback únicos para que possam usar portas padrão sem conflitos entre repositórios.

### Adaptar o Seu docker-compose.yml

**Antes (tradicional):**

```yaml
services:
  postgres:
    image: postgres:16
    ports:
      - "5432:5432"
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
    environment:
      POSTGRES_PASSWORD: secret

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  app:
    image: my-app:latest
    ports:
      - "8080:8080"
    environment:
      DATABASE_URL: postgresql://postgres:secret@postgres:5432/mydb
      REDIS_URL: redis://redis:6379
```

**Depois (Rediacc):**

```yaml
services:
  postgres:
    image: postgres:16
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
    environment:
      POSTGRES_PASSWORD: secret

  redis:
    image: redis:7-alpine

  app:
    image: my-app:latest
    environment:
      DATABASE_URL: postgresql://postgres:secret@postgres:5432/mydb
      REDIS_URL: redis://redis:6379
      LISTEN_ADDR: 0.0.0.0:8080
```

Principais alterações:

1. **Remover mapeamentos `ports:`** - o `renet compose` usa rede host e remove mapeamentos de porta automaticamente
2. **Remover `network_mode: host`** - o `renet compose` adiciona isto por si
3. **As políticas de reinício são seguras para manter** - o renet remove-as automaticamente para compatibilidade CRIU e o watchdog do router recupera automaticamente contentores parados
4. **Use nomes de serviço para conexões entre serviços** (por exemplo `postgres`, `redis`) - o renet injeta cada nome de serviço como um hostname resolvível. Não incorpore IPs brutos em strings de conexão que ficam armazenadas em bases de dados ou ficheiros de configuração; use o nome do serviço para manter o isolamento de fork intacto
5. **O bind é automático** - o kernel reescreve `bind()` para o IP de loopback correto. Os serviços podem usar `0.0.0.0` ou `localhost`

As variáveis `{SERVICE}_IP` ainda estão disponíveis se precisar delas, mas o bind explícito já não é necessário - é tratado automaticamente. A convenção de nomenclatura: maiúsculas, hífenes substituídos por underscores, sufixo `_IP`. Por exemplo, `listmonk-app` torna-se `LISTMONK_APP_IP`.

Consulte [Rede de Serviços](/pt/docs/services#service-networking-rediaccjson) para detalhes sobre atribuição de IP e `.rediacc.json`.

## Passo 6: Iniciar os Serviços

Monte o repositório (se ainda não estiver montado) e inicie todos os serviços:

```bash
rdc repo up --name my-project -m server-1
```

Isto irá:
1. Montar o repositório encriptado
2. Iniciar o daemon Docker isolado
3. Gerar automaticamente `.rediacc.json` com atribuições de IP de serviço
4. Executar `up()` de todos os Rediaccfiles

Verificar que os seus contentores estão a correr:

```bash
rdc machine containers --name server-1
```

## Passo 7: Ativar o Arranque Automático (Opcional)

Por predefinição, os repositórios devem ser montados e iniciados manualmente após um reinício do servidor. Ative o arranque automático para que os seus serviços iniciem automaticamente:

```bash
rdc repo autostart enable --name my-project -m server-1
```

Ser-lhe-á solicitada a frase-passe do repositório.

> **Nota de segurança:** O arranque automático armazena um ficheiro de chave LUKS no servidor. Qualquer pessoa com acesso root pode montar o repositório sem a frase-passe. Consulte [Arranque Automático](/pt/docs/services#autostart-on-boot) para detalhes.

## Cenários Comuns de Migração

### WordPress / PHP com Base de Dados

```
my-wordpress/
├── Rediaccfile
├── docker-compose.yml
├── app/                    # WordPress files (UID 33 when running)
├── database/data/          # MariaDB data (UID 999 when running)
└── wp-content/uploads/     # User uploads
```

1. Carregue os ficheiros do seu projeto
2. Inicie os serviços primeiro (`rdc repo up`) para que os contentores criem os seus diretórios de dados
3. Execute a correção de propriedade; os diretórios de dados do MariaDB e da aplicação são automaticamente excluídos

### Node.js / Python com Redis

```
my-api/
├── Rediaccfile
├── docker-compose.yml
├── src/                    # Application source
├── node_modules/           # Dependencies
└── redis-data/             # Redis persistence (UID 999 when running)
```

1. Carregue o seu projeto (considere excluir `node_modules` e puxar em `up()`)
2. Execute a correção de propriedade após os contentores terem iniciado

### Projeto Docker Personalizado

Para qualquer projeto com serviços Docker:

1. Carregue os ficheiros do projeto
2. Adapte `docker-compose.yml` (ver Passo 5)
3. Crie um `Rediaccfile` com funções de ciclo de vida
4. Execute a correção de propriedade
5. Inicie os serviços

## Resolução de Problemas

### Permissão Negada Após Carregar

Os ficheiros ainda têm o UID local. Execute o comando de propriedade:

```bash
rdc repo ownership --name my-project -m server-1
```

### O Contentor Não Inicia

Verifique se os serviços estão a correr e consulte os seus registos:

```bash
# Verificar IPs atribuídos
rdc term connect -m server-1 -r my-project -c "cat .rediacc.json"

# Verificar registos do contentor
rdc term connect -m server-1 -r my-project -c "docker logs <container-name>"
```

### Conflito de Portas Entre Repositórios

Cada repositório obtém IPs de loopback únicos, e o kernel reescreve automaticamente as chamadas `bind()` para o IP correto. Os conflitos de portas entre repositórios não devem ocorrer. Se verificar comportamento inesperado, confirme que os serviços são iniciados via `renet compose` (não `docker compose`). Para conectar **a** outros serviços, use o nome do serviço (por exemplo `postgres`) em vez de IPs brutos - os nomes de serviço resolvem corretamente em cada fork.

### A Correção de Propriedade Quebra Contentores

Se executou `rdc repo ownership` e um contentor deixou de funcionar, os ficheiros de dados do contentor foram alvo de chown. Pare o contentor, elimine o seu diretório de dados e reinicie; o contentor irá recriá-lo:

```bash
rdc repo down --name my-project -m server-1
# Eliminar o diretório de dados do contentor (por exemplo, database/data)
rdc repo up --name my-project -m server-1
```
