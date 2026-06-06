---
title: "Referência do Servidor"
description: "Estrutura de directórios, comandos renet, serviços systemd e fluxos de trabalho para o servidor remoto."
category: "Concepts"
order: 3
language: pt
sourceHash: "4fb53bb4cb1512f6"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# Referência do Servidor

Ao ligar-se por SSH a um servidor Rediacc, aqui está o que encontra: a estrutura de directórios, comandos `renet`, serviços systemd e os fluxos de trabalho que vai precisar.

A maioria dos utilizadores gere os servidores através do `rdc` a partir do seu computador de trabalho e nunca precisará desta página. Esta aqui para depuração avançada ou quando precisa de trabalhar directamente no servidor.

Para a arquitectura de alto nivel, consulte [Arquitectura](/pt/docs/architecture). Para a diferenca entre `rdc` e `renet`, consulte [rdc vs renet](/pt/docs/rdc-vs-renet).

## Estrutura de Diretorios

```
/mnt/rediacc/                          # Datastore principal
├── repositories/                      # Imagens de disco encriptadas (LUKS)
│   └── {uuid}                         # Cada uma e uma imagem de dispositivo loop
├── mounts/                            # Pontos de montagem para repositorios desencriptados
│   └── {uuid}/
│       ├── .rediacc.json              # Mapeamento servico -> slot IP
│       ├── .rediacc/docker/           # Dados do daemon Docker (imagens, contentores)
│       └── {service-name}/            # Diretorio do servico
│           ├── docker-compose.yml     # Definicao Compose
│           ├── Rediaccfile            # Hooks de ciclo de vida (bash)
│           └── data/                  # Dados persistentes
├── immovable/                         # Conteudo partilhado apenas de leitura
├── .credentials/                      # Segredos encriptados
└── .backup-*/                         # Snapshots BTRFS

/opt/rediacc/proxy/                    # Proxy reverso Traefik
├── docker-compose.yml
├── config.env                         # CERTBOT_EMAIL, CF_DNS_API_TOKEN
├── letsencrypt/                       # Certificados ACME
└── traefik/dynamic/                   # Ficheiros de rotas dinamicas

/run/rediacc/docker-{id}.sock          # Sockets Docker por rede
/var/lib/rediacc/router/               # Estado do router (alocacoes de portas)
```

## Comandos renet

`renet` e o binario do lado do servidor. Todos os comandos necessitam de privilegios root (`sudo`).

### Ciclo de Vida do Repositorio

```bash
# Listar todos os repositorios
renet repository list

# Mostrar detalhes do repositorio
renet repository status --name {uuid}

# Iniciar um repositorio (montar + executar Rediaccfile up)
renet repository up --name {uuid} --network-id {id} --password-stdin

# Parar um repositorio (executar Rediaccfile down)
renet repository down --name {uuid} --network-id {id}

# Criar um novo repositorio
renet repository create --name {uuid} --network-id {id} --size 2G --encrypted

# Fork (copia instantanea usando reflinks BTRFS)
renet repository fork --source {uuid} --target {new-uuid}

# Expandir um repositorio em execucao (sem tempo de inatividade)
renet repository expand --name {uuid} --size 4G

# Eliminar um repositorio e todos os seus dados
renet repository delete --name {uuid} --network-id {id}
```

### Docker Compose

Executar comandos compose contra o daemon Docker de um repositorio especifico:

```bash
sudo renet compose -- up -d
sudo renet compose -- down
sudo renet compose -- logs -f
sudo renet compose -- config
```

Executar comandos docker directamente:

```bash
sudo renet docker --network-id {id} -- ps
sudo renet docker --network-id {id} -- logs -f {container}
sudo renet docker --network-id {id} -- exec -it {container} bash
```

Tambem pode usar o socket Docker directamente:

```bash
DOCKER_HOST=unix:///run/rediacc/docker-{id}.sock docker ps
```

> Execute sempre o compose a partir do diretorio que contem o `docker-compose.yml`, caso contrario o Docker nao encontrara o ficheiro.

### Sandbox do Sistema de Ficheiros

```bash
# Verificar suporte Landlock
renet sandbox-exec --detect

# Executar um comando dentro de uma sandbox Landlock (usado internamente)
renet sandbox-exec --allow-rw /path --allow-ro /usr --allow-exec /bin -- command
```

`sandbox-exec` aplica restricoes do sistema de ficheiros Landlock LSM e depois executa o comando fornecido. E invocado automaticamente pelo `sandbox-gateway` (o handler SSH ForceCommand) para todas as conexoes ao nivel do repositorio.

### Hub por utilizador (ambientes de desenvolvimento)

O Hub fornece a cada utilizador o seu proprio daemon Docker para ambientes de desenvolvimento, separado dos daemons `FlavorRediacc` por repositorio.

```bash
# Instalar / remover as unidades systemd do Hub por utilizador
sudo renet hub install
sudo renet hub uninstall

# Recolher daemons Hub por utilizador inactivos
sudo renet hub gc
```

Os daemons correm sob um de dois flavors, seleccionado com `--flavor`:

```bash
# Daemon isolado por repositorio (bridge=none, iptables=false) — o padrao
sudo renet daemon start-foreground --flavor=rediacc ...

# Daemon Hub por utilizador (bridge=docker0, iptables=true, live-restore=true)
sudo renet daemon start-foreground --flavor=hub ...
```

O flavor `hub` activa a rede bridge normal para que os contentores do utilizador tenham conectividade de saida; o flavor `rediacc` enforaca o isolamento loopback entre repositorios. Os registos de auditoria do Hub sao escritos em `/var/log/rediacc/hub/<user>.log`.

**Flags:**
- `--allow-rw`, `--allow-ro`, `--allow-exec`: regras de caminho Landlock
- `--home-overlay`: monta OverlayFS sobre o diretorio home para isolamento de escrita por repositorio
- `--sandbox-dir`: espaco de trabalho por repositorio (`<datastore>/.interim/sandbox/<name>/`)
- `--work-dir`: define o diretorio de trabalho e carrega `.envrc` para o ambiente do repositorio
- `--run-as`: abandona privilegios para o utilizador alvo apos configuracao
- `--reset-home`: limpa o overlay home por repositorio para comecar de raiz

**`sandbox-gateway`** e o handler SSH ForceCommand definido via `command=` em `authorized_keys`. A chave SSH de cada repositorio aciona o gateway com o nome do repositorio incorporado, impossivel de falsificar pelo cliente. O gateway constroi os argumentos sandbox-exec e executa via sudo.

### Proxy e Routing

```bash
renet proxy status          # Verificar saude do Traefik + router
renet proxy routes          # Mostrar todas as rotas configuradas
renet proxy refresh         # Actualizar rotas a partir de contentores em execucao
renet proxy up / down       # Iniciar/parar Traefik
renet proxy logs            # Ver logs do proxy
```

As rotas sao descobertas automaticamente a partir de labels de contentores. Consulte [Networking](/pt/docs/networking) para saber como configurar labels Traefik.

### Estado do Sistema

```bash
renet ps                    # Estado geral do sistema
renet list all              # Tudo: sistema, contentores, repositorios
renet list containers       # Todos os contentores em todos os daemons Docker
renet list repositories     # Estado dos repositorios e utilizacao de disco
renet list system           # CPU, memoria, disco, rede
renet ips --network-id {id} # Alocacoes de IP para uma rede
```

### Gestao de Daemons

Cada repositorio corre o seu proprio daemon Docker. Pode geri-los individualmente:

```bash
renet daemon status --network-id {id}    # Saude do daemon Docker
renet daemon start  --network-id {id}    # Iniciar daemon
renet daemon stop   --network-id {id}    # Parar daemon
renet daemon logs   --network-id {id}    # Logs do daemon
```

### Backup e Restauro

Enviar backups para outra maquina ou para armazenamento na nuvem:

```bash
# Enviar para maquina remota (SSH + rsync)
renet backup push --name {uuid} --network-id {id} --target machine \
  --dest-host {host} --dest-user {user} --dest-path /mnt/rediacc --dest {uuid}.backup

# Enviar para armazenamento na nuvem (rclone)
renet backup push --name {uuid} --network-id {id} --target storage \
  --dest {uuid}.backup --rclone-backend {backend} --rclone-bucket {bucket}

# Obter de remoto
renet backup pull --name {uuid} --network-id {id} --source machine \
  --src-host {host} --src-user {user} --src-path /mnt/rediacc --src {uuid}.backup

# Listar backups remotos
renet backup list --source machine --src-host {host} --src-user {user} --src-path /mnt/rediacc
```

> A maioria dos utilizadores deve usar `rdc repo push/pull` em vez disso. Os comandos `rdc` tratam automaticamente das credenciais e da resolucao de maquinas.

### Checkpointing (CRIU)

O checkpoint guarda o estado dos contentores em execucao para que possam ser restaurados mais tarde:

```bash
renet checkpoint create    --network-id {id}   # Guardar estado do contentor em execucao
renet checkpoint restore   --network-id {id}   # Restaurar a partir do checkpoint
renet checkpoint validate  --network-id {id}   # Verificar integridade do checkpoint
```

### Manutencao

```bash
renet prune --dry-run       # Pre-visualizar redes e IPs orfaos
renet prune                 # Limpar recursos orfaos
renet datastore status      # Saude do datastore BTRFS
renet datastore validate    # Verificacao de integridade do sistema de ficheiros
renet datastore expand      # Expandir o datastore em linha
```

## Servicos Systemd

Cada repositorio cria estas unidades systemd:

| Unidade | Proposito |
|---------|-----------|
| `rediacc-docker-{id}.service` | Daemon Docker isolado |
| `rediacc-docker-{id}.socket` | Activacao de socket da API Docker |
| `rediacc-loopback-{id}.service` | Configuracao de alias de IP loopback |

Servicos globais partilhados entre todos os repositorios:

| Unidade | Proposito |
|---------|-----------|
| `rediacc-router.service` | Descoberta de rotas (porta 7111) |
| `rediacc-autostart.service` | Montagem de repositorios no arranque |
| `rediacc-autostart-reconcile.service` | Reconciliador periódico de autostart (executado pelo temporizador seguinte) |
| `rediacc-autostart-reconcile.timer` | Dispara `renet repository reconcile` aproximadamente a cada 3 minutos para recuperar repositórios de autostart que ficaram inactivos após o arranque |

## Fluxos de Trabalho Comuns

### Fazer Deploy de um Novo Servico

1. Criar um repositorio encriptado:
   ```bash
   renet repository create --name {uuid} --network-id {id} --size 2G --encrypted
   ```
2. Monte-o e adicione os seus ficheiros `docker-compose.yml`, `Rediaccfile` e `.rediacc.json`.
3. Inicie-o:
   ```bash
   renet repository up --name {uuid} --network-id {id} --password-stdin
   ```

### Aceder a um Contentor em Execucao

```bash
sudo renet docker --network-id {id} -- exec -it {container} bash
```

### Encontrar o Socket Docker que Corre um Contentor

```bash
for sock in /run/rediacc/docker-*.sock; do
  result=$(DOCKER_HOST=unix://$sock docker ps --format '{{.Names}}' 2>/dev/null | grep {name})
  [ -n "$result" ] && echo "Found on: $sock"
done
```

### Recriar um Servico Apos Alteracoes de Configuracao

```bash
sudo renet compose -- up -d
```

Execute a partir do diretorio com `docker-compose.yml`. Os contentores alterados sao automaticamente recriados.

### Verificar Todos os Contentores em Todos os Daemons

```bash
renet list containers
```

## Dicas

- Use sempre `sudo` para os comandos `renet compose`, `renet repository` e `renet docker`; necessitam de root para operacoes LUKS e Docker
- O separador `--` e obrigatorio antes de passar argumentos para `renet compose` e `renet docker`
- Execute o compose a partir do diretorio que contem `docker-compose.yml`
- Os slots de `.rediacc.json` sao estaveis; nao os altere apos o deployment
- Use caminhos `/run/rediacc/docker-{id}.sock` (o systemd pode alterar os caminhos legados `/var/run/`)
- Execute `renet prune --dry-run` periodicamente para encontrar recursos orfaos
- Os snapshots BTRFS (`renet backup`) sao rapidos e baratos; use-os antes de fazer alteracoes arriscadas
- Os repositorios estao encriptados com LUKS; perder a password significa perder os dados
