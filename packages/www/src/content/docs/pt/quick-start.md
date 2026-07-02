---
title: Início Rápido
description: Coloque um serviço em contentor a funcionar no seu servidor em minutos.
category: Guides
order: -1
language: pt
sourceHash: "afd4d22ddc8e02e1"
sourceCommit: "ff9c470edf8760f63f12baf681c04db51a0c202f"
---

# Início Rápido

Instale o Rediacc no seu próprio servidor. Ambientes de contentores encriptados e isolados, sem contas na nuvem, sem dependências SaaS. Hardware seu, controlo seu.

---

## Introdução

### Conceitos Fundamentais

Um repositório é um único ficheiro encriptado em disco. Mova-o, faça backup, crie um fork. É apenas um ficheiro. Quando montado, torna-se uma pasta com um daemon Docker dedicado e os dados da sua aplicação no interior.

Pense num repositório como uma pen USB: ligue-a a qualquer máquina e as aplicações e dados são montados, prontos a correr. Mova-o entre máquinas ou fornecedores de nuvem sem reconstruir nada.

**Duas ferramentas, dois papéis:**

- **rdc** = CLI no seu portátil (TypeScript, instalado globalmente)
- **renet** = orquestrador no servidor (binário Go, gere daemons/redes/isolamento)
- O RDC provisiona o renet automaticamente durante `config machine setup`. Sem configuração manual no servidor.

> [Arquitetura](/pt/docs/architecture) explica o modelo de segurança. [rdc vs renet](/pt/docs/rdc-vs-renet) explica qual ferramenta usar em cada situação.

### 1. Instalar o CLI

```bash
curl -fsSL https://www.rediacc.com/install.sh | bash
rdc doctor     # Verificar: Node, chave SSH, renet, Docker
```

> Windows, Alpine, Arch: consulte [Instalação](/pt/docs/installation). Requisitos completos do sistema: [Requisitos](/pt/docs/requirements).

### 2. Configuração da Chave SSH

O rdc liga-se via SSH. O servidor deve confiar na sua chave pública antes de o rdc poder alcançá-lo.

```bash
# Gerar uma chave (ignorar se já tiver uma)
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519

# Copiar a chave pública para o servidor (pedirá a senha)
ssh-copy-id -i ~/.ssh/id_ed25519 user@your-server-ip

# Indicar ao rdc qual chave usar
rdc config ssh set --key ~/.ssh/id_ed25519
```

Todos os comandos rdc autenticam agora com esta chave. Sem senhas.

### 3. Adicionar o Seu Servidor

```bash
rdc config machine add --name my-server --ip 192.168.1.100 --user admin
rdc config machine setup --name my-server  # Provisiona o renet + cria o datastore
```

**O que acontece:** a chave de anfitrião SSH é analisada, o binário do renet é carregado e o datastore encriptado é inicializado no servidor. Pronto para repositórios.

> Dimensionamento do datastore, Ceph RBD, fornecedores de nuvem: [Configuração da Máquina](/pt/docs/setup). Falhas SSH: [Resolução de Problemas](/pt/docs/troubleshooting).

### 4. Ficheiro de Config

```bash
rdc config show                            # Resumo legível por humanos
cat ~/.config/rediacc/rediacc.json         # JSON em bruto: máquinas, repositórios, armazenamentos, chave SSH
```

**Um ficheiro = um ambiente.** Copie-o para outro portátil e está pronto.

---

## Trabalhar com um Repositório

### 1. Criar um Repositório

```bash
rdc repo create --name my-app -m my-server --size 2G  # Criar repositório encriptado de 2 GB
```

Cria o volume encriptado, monta-o e inicia o seu daemon Docker. O repositório é registado na sua config e está pronto para uso.

> Redimensionar, eliminar, validação: [Repositórios](/pt/docs/repositories).

### 2. Aplicar um Modelo

```bash
rdc repo template list                                        # Mostrar modelos incorporados
rdc repo template apply --name app-postgres -m my-server -r my-app  # Implementar docker-compose.yml + Rediaccfile
```

Os modelos fornecem um `docker-compose.yml`, um `Rediaccfile` e ficheiros de suporte. Sem um modelo (ou o seu próprio ficheiro compose), não há nada para iniciar. Utilize o modelo incorporado para o seu primeiro repositório. É o caminho mais rápido para ver o fluxo de trabalho completo de ponta a ponta.

### 3. Iniciar o Repositório

```bash
rdc repo up --name my-app -m my-server  # Executar Rediaccfile up()
rdc repo list -m my-server                           # Ver todos os repositórios na máquina
rdc repo status --name my-app -m my-server  # Estado de montagem, Docker, tamanho, encriptação
```

`repo up` monta automaticamente se necessário. Não são necessárias flags.

### 4. VS Code

```bash
rdc vscode connect -m my-server -r my-app              # Abre o VS Code SSH, aterra dentro da sandbox do repositório
```

Está a editar ficheiros *dentro* do volume encriptado. `docker ps` apenas mostra os contentores deste repositório. Guarde, compose up, itere.

### 5. `rdc repo up` vs `renet dev up`

| | `rdc repo up` | `renet dev up` |
|---|---|---|
| **Onde se executa** | O seu portátil (CLI) | Dentro da sandbox VS Code |
| **O que faz** | SSH → montagem automática → executar Rediaccfile `up()` | Executa Rediaccfile `up()` diretamente |
| **Caso de uso** | CI/CD, automação, operações remotas | Ciclo interno do programador |
| **Isolamento** | Orquestra de fora | Já dentro da sandbox |

**Fluxo de demonstração:** `rdc repo template apply` → `rdc vscode connect -m my-server -r my-app` → edite `docker-compose.yml` → `renet dev up` → veja a aplicação a correr → itere.

> Estrutura do Rediaccfile: [Serviços](/pt/docs/services). Quando usar cada ferramenta: [rdc vs renet](/pt/docs/rdc-vs-renet).

### 6. Modelo de Isolamento

- **Utilizador universal** (`rediacc`): Mesmo UID em todas as máquinas. Mova um repositório para outro servidor e a propriedade dos ficheiros funciona automaticamente. Sem problemas com `chown`.
- **Daemon Docker por repositório**: Cada repositório tem o seu próprio daemon Docker isolado. `docker ps` apenas mostra os contentores DESTE repositório.
- **Sandbox Landlock + OverlayFS**: A shell do VS Code tem acesso restrito ao sistema de ficheiros. Não pode ler outros repositórios. As escritas em `$HOME` são sobreposições por repositório.

> Como funciona o isolamento: [Arquitetura](/pt/docs/architecture). Ciclo de vida do Rediaccfile: [Serviços](/pt/docs/services).

### 7. Terminal, Sincronização e Túnel

**Terminal:**
```bash
rdc term connect -m my-server -r my-app                            # SSH para a sandbox do repositório
rdc term connect -m my-server -r my-app -c "curl localhost:3000"   # Executar comando e sair
rdc term connect -m my-server                                   # SSH para a máquina (sem sandbox)
```

**Sincronização de Ficheiros (rsync sobre SSH):**
```bash
rdc repo sync upload -m my-server -r my-app --local ./src                                   # Enviar um diretório
rdc repo sync upload -m my-server -r my-app --local ./config.yml --remote conf              # Enviar um único ficheiro
rdc repo sync download -m my-server -r my-app --local ./backup                              # Receber um diretório
rdc repo sync download -m my-server -r my-app --remote-file conf/config.yml --local ./dl    # Receber um único ficheiro
rdc repo sync download -m my-server -r my-app --local ./backup --dry-run                    # Pré-visualizar primeiro
```

**Túnel (encaminhamento de portas SSH para contentor):**
```bash
rdc repo tunnel -m my-server -r my-app -c app  # Detetar automaticamente a porta para o contentor da aplicação
rdc repo tunnel -m my-server -r my-app -c db --port 5432  # Túnel Postgres
rdc repo tunnel -m my-server -r my-app -c db --port 5432 --local 15432  # Porta local personalizada
```

Execute o túnel → abra `localhost:3000` no browser → aplicação ao vivo a partir do servidor remoto.

> Detalhes de sincronização, terminal e VS Code: [Ferramentas](/pt/docs/tools).

---

## Fork e Backup

### 1. Repositórios Grand e Fork

```bash
rdc repo fork --parent my-app -m my-server --tag experiment --up  # Clone CoW instantâneo + início
rdc repo list -m my-server                                  # Mostra: my-app (grand) + my-app:experiment (fork)
rdc repo delete --name my-app:experiment -m my-server  # Eliminar fork, grand intocado
```

**Clone instantâneo, sem cópia.** CoW (copy-on-write). Microssegundos, sem dados copiados. Os blocos são partilhados até um dos lados escrever.

**Casos de uso:**
- **IA / ML:** Faça fork do conjunto de dados de produção, execute a experiência, descarte ou promova
- **DevOps:** Fork → testar migração → eliminar se mau, promover se bom
- **Backup:** Fork = snapshot instantâneo, envie para fora do local

> Ciclo de vida do fork, forks entre máquinas: [Repositórios](/pt/docs/repositories).

### 2. Enviar para Outra Máquina

```bash
# Enviar repositório para outra máquina
rdc repo push --name my-app -m my-server --to backup-server

# Enviar e implementar automaticamente no destino
rdc repo push --name my-app -m my-server --to backup-server --up

# Enviar com checkpoint CRIU (migração ao vivo, preserva o estado de memória)
rdc repo push --name my-app -m my-server --to new-server --checkpoint --up

# Enviar para uma nova máquina (provisionar automaticamente via fornecedor de nuvem)
rdc repo push --name my-app -m my-server --to new-server --provision linode --up
```

### 3. Enviar para Armazenamento na Nuvem (OneDrive, Google Drive, S3)

```bash
# Importar a sua config rclone como backend de armazenamento
rdc config storage import --file ~/rclone.conf

# Listar armazenamentos disponíveis
rdc storage list

# Enviar repositório para armazenamento na nuvem
rdc repo push --name my-app -m my-server --to my-s3-backup

# Listar backups no armazenamento
rdc repo backup list --from my-s3-backup -m my-server
```

`--to` deteta automaticamente se o destino é uma máquina ou um backend de armazenamento. Funciona com qualquer fornecedor suportado pelo rclone: S3, R2, B2, OneDrive, Google Drive, SFTP, etc.

### 4. Receber de Remoto

```bash
# Receber repositório de uma máquina na nuvem para o seu servidor local
rdc repo pull --name my-app -m my-local-server --from cloud-server

# Receber do armazenamento na nuvem
rdc repo pull --name my-app -m my-local-server --from my-s3-backup

# Receber e iniciar imediatamente
rdc repo pull --name my-app -m my-local-server --from my-s3-backup --up
```

**Porquê receber?** A sua máquina local está atrás de NAT. A nuvem não consegue enviar para si. Mas pode alcançar a nuvem. Receber traz o repositório para casa.

**Ciclo completo:** Criar em dev → enviar para a nuvem → receber em produção → `--up`. Um repositório, qualquer máquina, qualquer nuvem.

> Agendamento, backups automáticos, restauro: [Backup e Restauro](/pt/docs/backup-restore).

---

## Proxy e SSL

### 1. Config de Infraestrutura

```bash
rdc config infra set -m my-server  # Configurar: domínio base, IPs públicos, intervalos de portas
rdc config infra show -m my-server  # Rever a configuração
rdc config infra push -m my-server  # Enviar a config do proxy para remoto
```

**Como funciona o encaminhamento:**
- O Traefik descobre automaticamente os contentores via etiquetas `rediacc.service_name` e `rediacc.service_port`
- Rotas: `{service}-{networkId}.{baseDomain}` → IP:porta do contentor
- SSL: Let's Encrypt via desafio DNS-01 do Cloudflare (renovação automática, certificados wildcard)

### 2. Modelo de Proxy

```bash
rdc repo template apply --name proxy -m my-server -r infra  # Implementar proxy num repositório
rdc repo up --name infra -m my-server  # Iniciar Traefik
```

O Traefik encaminha agora o tráfego externo para todos os repositórios nesta máquina. Cada contentor obtém automaticamente um endpoint HTTPS.

```bash
# Navegar para https://my-app.example.com → encaminhado para o contentor
# Encaminhamento TCP/UDP para bases de dados:
#   rediacc.tcp_ports=3306,5432 → portas externas alocadas automaticamente
```

> Regras de encaminhamento, DNS, configuração TLS: [Redes](/pt/docs/networking).

---

## Próximos Passos

- **[Guia de Migração](/pt/docs/migration)** - Trazer projetos existentes para repositórios Rediacc
- **[Monitorização](/pt/docs/monitoring)** - Saúde da máquina, contentores, serviços, diagnósticos
- **[Referência do CLI](/pt/docs/cli-application)** - Referência completa de comandos
- **[Folha de Consulta](/pt/docs/rdc-cheat-sheet)** - Consulta rápida de comandos
- **[Resolução de Problemas](/pt/docs/troubleshooting)** - Soluções para problemas comuns
- **[Regras do Rediacc](/pt/docs/rules-of-rediacc)** - Boas práticas do Rediaccfile e lista de verificação de implantação
