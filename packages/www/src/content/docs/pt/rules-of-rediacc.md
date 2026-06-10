---
title: "Regras do Rediacc"
description: "Regras e convenções essenciais para construir aplicações na plataforma Rediacc. Abrange Rediaccfile, compose, networking, armazenamento, CRIU e deployment."
category: "Guides"
order: 5
language: pt
sourceHash: "4b6899adea7f0712"
sourceCommit: "ff9c470edf8760f63f12baf681c04db51a0c202f"
---

# Regras do Rediacc

Cada repositório Rediacc corre dentro de um ambiente isolado com o seu próprio daemon Docker, volume LUKS encriptado e intervalo de IPs dedicado. Estas regras garantem que a sua aplicação funciona correctamente dentro desta arquitectura.

## Rediaccfile

- **Cada repositorio precisa de um Rediaccfile**, um script bash com funcoes de ciclo de vida.
- **Funcoes de ciclo de vida**: `up()`, `down()`. Opcional: `info()`.
- `up()` inicia os seus servicos. `down()` para-os.
- `info()` fornece informacoes de estado (estado do contentor, logs recentes, saude).
- O Rediaccfile e carregado (sourced) pelo renet; tem acesso a variaveis de shell, nao apenas a variaveis de ambiente.

### Variaveis de ambiente disponiveis no Rediaccfile

| Variavel | Exemplo | Descricao |
|----------|---------|-----------|
| `REDIACC_WORKING_DIR` | `/mnt/rediacc/mounts/abc123/` | Caminho raiz do repositorio montado |
| `REDIACC_NETWORK_ID` | `6336` | Identificador de isolamento de rede |
| `REDIACC_REPOSITORY` | `abc123-...` | GUID do repositorio |
| `{SVCNAME}_IP` | `HEARTBEAT_IP=127.0.24.195` | IP de loopback por servico (nome do servico em maiusculas) |

### Rediaccfile Minimal

```bash
#!/bin/bash

_compose() {
  renet compose -- "$@"
}

up() {
  _compose up -d
}

down() {
  _compose down
}
```

## Compose

- **Use `renet compose`, nunca `docker compose`**, o renet injeta isolamento de rede, host networking, IPs de loopback e labels de servico.
- **NAO defina `network_mode`** no seu ficheiro compose; o renet forca `network_mode: host` em todos os servicos. Qualquer valor que defina sera sobrescrito.
- **NAO defina labels `rediacc.*`**, o renet injeta automaticamente `rediacc.network_id`, `rediacc.service_ip` e `rediacc.service_name`.
- **Os mapeamentos `ports:` sao ignorados** em modo host networking. Adicione a label `rediacc.service_port` para routing HTTP (servicos sem esta label nao obtem rotas HTTP). Use as labels `rediacc.tcp_ports`/`rediacc.udp_ports` para reencaminhamento TCP/UDP.
- **As politicas de reinicio (`restart: always`, `on-failure`, etc.) sao seguras de usar**; o renet remove-as automaticamente para compatibilidade com CRIU. O watchdog do router recupera automaticamente os contentores parados com base na politica original guardada em `.rediacc.json`.
- **As configuracoes perigosas sao bloqueadas por padrao**: `privileged: true`, `pid: host`, `ipc: host` e bind mounts do host para caminhos de sistema sao rejeitados. Use `renet compose --unsafe` para substituir por sua propria conta e risco.

### Variaveis de ambiente dentro dos contentores

O renet injeta-as automaticamente em cada contentor:

| Variavel | Descricao |
|----------|-----------|
| `SERVICE_IP` | IP de loopback dedicado deste contentor |
| `REDIACC_NETWORK_ID` | ID de isolamento de rede |

### Nomenclatura de servicos e routing

- O **nome do servico** no compose torna-se o prefixo do URL de rota automatica.
- **Repositorios grand**: `https://{service}.{repo}.{machine}.{baseDomain}` (por exemplo, `https://myapp.marketing.server-1.example.com`).
- **Repositorios fork**: `https://{service}-fork-{tag}.{repo}.{machine}.{baseDomain}` (por exemplo, `https://myapp-fork-staging.marketing.server-1.example.com`). O separador `-fork-` evita colisoes de URL com nomes de servico do repositorio grand. O URL do fork usa sempre o certificado wildcard existente do repositorio pai, pelo que nao e necessario um novo certificado.
- Para dominios personalizados, use labels Traefik (mas atencao: os dominios personalizados NAO sao compativeis com forks; o dominio pertence ao repositorio grand).

## Networking

- **Cada repositorio tem o seu proprio daemon Docker** em `/var/run/rediacc/docker-<networkId>.sock`.
- **Cada servico tem um IP de loopback unico** dentro de uma subnet /26 (por exemplo, `127.0.24.192/26`).
- **O binding e automatico**: os servicos podem fazer bind a `0.0.0.0` ou `localhost`; o kernel reescreve transparentemente o endereco para o IP de loopback atribuido ao servico. O binding explicito via `${SERVICE_IP}` ainda funciona, mas ja nao e necessario.
- **Os health checks podem usar `localhost`** ou `${SERVICE_IP}`. Exemplo: `healthcheck: test: ["CMD", "curl", "-f", "http://localhost:8080/health"]`
- **As conexoes entre repositorios sao bloqueadas pelo kernel**: o kernel bloqueia automaticamente conexoes para IPs de loopback fora da subnet `/26` do repositorio. Um servico num repositorio nao consegue aceder a servicos de outro repositorio.
- **Comunicacao entre servicos**: use **nomes de servico** (por exemplo, `db`, `redis`); o renet injeta automaticamente cada nome de servico como hostname que resolve para o IP correto. Os nomes DNS do Docker NAO funcionam em modo host, mas os nomes de servico via `/etc/hosts` funcionam. Evite incorporar `${DB_IP}` ou semelhante em ficheiros de configuracao persistentes (por exemplo, strings de conexao guardadas numa base de dados); se fizer fork, o IP bruto e transportado e aponta para o repositorio errado. Os nomes de servico resolvem sempre correctamente por repositorio.
- **Conflitos de portas sao impossiveis** entre repositorios; cada um tem o seu proprio daemon Docker e intervalo de IPs.
- **Reencaminhamento de portas TCP/UDP**: adicione labels para expor portas nao HTTP:
  ```yaml
  labels:
    - "rediacc.tcp_ports=5432,3306"
    - "rediacc.udp_ports=53"
  ```

## Armazenamento

- **Todos os dados Docker sao guardados dentro do repositorio encriptado**; o `data-root` do Docker esta em `{mount}/.rediacc/docker/data` dentro do volume LUKS. Volumes nomeados, imagens e camadas de contentores sao todos encriptados, incluidos nos backups e clonados automaticamente.
- **Bind mounts para `${REDIACC_WORKING_DIR}/...` sao recomendados** para maior clareza, mas volumes nomeados tambem funcionam com seguranca.
  ```yaml
  volumes:
    - ${REDIACC_WORKING_DIR}/data:/data        # bind mount (recomendado)
    - pgdata:/var/lib/postgresql/data      # volume nomeado (tambem seguro)
  ```
- O volume LUKS e montado em `/mnt/rediacc/mounts/<guid>/`.
- Os snapshots BTRFS capturam o ficheiro de suporte LUKS completo, incluindo todos os dados em bind mount.
- O datastore e um ficheiro de pool BTRFS de tamanho fixo no disco do sistema. Use `rdc machine query --name <name> --system` para ver o espaco livre efectivo. Expanda com `rdc datastore resize`.

## CRIU (Migracao ao Vivo)

- **Opt-in via label**: adicione `rediacc.checkpoint=true` aos contentores que pretende fazer checkpoint. Os contentores sem esta label (bases de dados, caches) iniciam de raiz e recuperam pelos seus proprios mecanismos (WAL, LDF, AOF).
- **`repo down --checkpoint`** guarda o estado do processo antes de parar; o proximo `repo up` restaura automaticamente. **Este e o fluxo principal na mesma maquina**, verificado como funcional.
- **`backup push --checkpoint`** captura a memoria do processo em execucao e o estado do disco para contentores com label, depois transfere o volume para outra maquina. Restaure na maquina de destino via `repo up`.
- **`repo fork --checkpoint`** captura o estado dos processos do pai em execução e clona o checkpoint junto com o fork via CoW. O `repo up` do fork restaura os processos enquanto o pai continua em execução, na mesma máquina. Processos restaurados que referenciam endereços loopback do pai (sockets vinculados, IPs de serviço em memória) são redirecionados de forma transparente para os endereços próprios do fork, então eles falam com a cópia de dados do fork, nunca com a do pai.
- **`repo up`** detecta automaticamente dados de checkpoint e restaura se encontrados. Use `--skip-checkpoint` para forcar inicio limpo.
- **Restauro com consciencia de dependencias**: usa `depends_on` do compose para iniciar primeiro as bases de dados (aguarda que fiquem saudaveis) e depois restaura os contentores da aplicacao com CRIU.
- **As conexoes TCP ficam obsoletas apos o restauro**; as aplicacoes devem tratar `ECONNRESET` e reconectar. O CRIU nao preserva o estado de conexoes TCP activas apos o restauro em nenhum fluxo suportado.
- **O modo experimental do Docker** e activado automaticamente nos daemons por repositorio.
- **O CRIU e instalado** durante `rdc config machine setup`.
- **`/etc/criu/runc.conf`** e configurado com `tcp-established` por padrao.
- **As configuracoes de seguranca do contentor sao injectadas automaticamente para contentores com label**: o `renet compose` adiciona o seguinte aos contentores com `rediacc.checkpoint=true`:
  - `cap_add`: `CHECKPOINT_RESTORE`, `SYS_PTRACE`, `NET_ADMIN` (conjunto minimo para CRIU no kernel 5.9+)
  - `security_opt`: `apparmor=unconfined` (o suporte AppArmor do CRIU ainda nao e estavel upstream)
  - `userns_mode: host` (o CRIU necessita de acesso ao namespace init para `/proc/pid/map_files`)
- Os contentores sem a label correm com uma postura de seguranca mais limpa (sem capacidades extra).
- O perfil seccomp padrao do Docker e preservado; o CRIU usa `PTRACE_O_SUSPEND_SECCOMP` (kernel 4.3+) para suspender temporariamente os filtros durante checkpoint/restore.
- **NAO defina manualmente as capacidades CRIU** no seu ficheiro compose; o renet trata disso com base na label.
- Consulte o [template heartbeat](https://github.com/rediacc/console/tree/main/packages/json/templates/monitoring/heartbeat) para uma implementacao de referencia compativel com CRIU.

### Padroes de aplicacao compativeis com CRIU

- Trate `ECONNRESET` em todas as conexoes persistentes (pools de bases de dados, websockets, filas de mensagens).
- Use bibliotecas de pool de conexoes que suportem reconexao automatica.
- Adicione `process.on("uncaughtException")` como rede de seguranca para erros de socket obsoletos de objectos de biblioteca internos.
- As politicas de reinicio sao geridas automaticamente pelo renet (removidas para CRIU; o watchdog trata da recuperacao).
- Evite depender do DNS do Docker; use IPs de loopback para comunicacao entre servicos.

### Politicas de seguranca do host por SO

Nos cinco SOs de servidor com suporte oficial (consulte [Requisitos](/pt/docs/requirements)), o daemon Docker por repositorio e os contentores que executa usam **labels de contentor padrao**. `rdc config machine setup` nao instala uma politica SELinux personalizada nem um perfil AppArmor. Isto e intencional: o trade-off e que os processos de contentor funcionam sob a politica de rotulo do SO anfitrao por defeito, nao sob um perfil de confinamento especifico do Rediacc. Se o seu modelo de ameaca exigir controles de acesso obrigatorio ao nivel do contentor, configure-os ao nivel do anfitrao antes de implementar.

- **Ubuntu 24.04 / openSUSE Leap 16.0**: AppArmor esta activo por padrao. Os contentores correm sob o perfil docker-container padrao. A unica excepcao e o CRIU (`apparmor=unconfined` para contentores com `rediacc.checkpoint=true`, conforme a nota acima).
- **Fedora 43 / Oracle Linux 10**: SELinux corre em modo enforcing por padrao. Os contentores recebem o contexto `container_t` padrao. Nao e necessaria instalacao de politica adicional. Se um passo de configuracao falhar com negacoes AVC, consulte [Resolucao de Problemas -> Negacoes SELinux](/pt/docs/troubleshooting).
- **Debian 13**: AppArmor esta disponivel mas nao e aplicado por padrao em todos os dominios. Os contentores continuam a usar o perfil docker-container.

Bottom line: `rdc` e `renet` detectam automaticamente o SO em execucao e produzem o mesmo isolamento por repositorio nas cinco distribuicoes com suporte. Nao e necessaria nenhuma flag de postura de seguranca por SO.

## Seguranca

- **A encriptacao LUKS** e obrigatoria para repositorios padrao. Cada repositorio tem a sua propria chave de encriptacao.
- **As credenciais sao guardadas na configuracao do CLI** (`~/.config/rediacc/rediacc.json`). Perder a configuracao significa perder o acesso aos volumes encriptados.
- **Nunca coloque credenciais** em controlo de versao. Use `env_file` e gere segredos em `up()`.
- **Isolamento de repositorios**: o daemon Docker, a rede e o armazenamento de cada repositorio estao totalmente isolados de outros repositorios na mesma maquina.
- **Isolamento de agentes**: os agentes de IA operam em modo apenas fork por padrao. Cada repositorio tem a sua propria chave SSH com aplicacao de sandbox do lado do servidor (`sandbox-gateway` ForceCommand). Todas as conexoes estao em sandbox com Landlock LSM, OverlayFS home overlay e TMPDIR por repositorio. O acesso ao sistema de ficheiros entre repositorios e bloqueado pelo kernel.
- **`sudo` esta desactivado dentro de uma sandbox de repositorio por concepcao.** O isolamento do sistema de ficheiros Landlock requer `NoNewPrivs`, o que impede qualquer elevacao de privilegios, pelo que `sudo` falhara com `no new privileges flag is set`. O utilizador proprietario do repositorio ja tem as permissoes necessarias para tudo dentro do mount e do socket Docker do repositorio. Para operacoes genuinamente privilegiadas (instalacao de pacotes no host, ajuste do kernel), execute-as fora da sandbox ou a partir de uma funcao `up()` do Rediaccfile executada pelo caminho de infraestrutura.
- **O bridge networking do Docker esta desactivado nos daemons por repositorio.** O `daemon.json` (`FlavorRediacc`) de cada repositorio tem `"bridge": "none"` e `"iptables": false`, portanto um simples `docker run <image>` cria um contentor com apenas uma interface de loopback e sem conectividade de saida. Isto nao e um bug; e assim que o isolamento entre repositorios e aplicado: os hooks eBPF ao nivel do kernel que bloqueiam um repositorio de aceder aos IPs de loopback de outro repositorio so se aplicam a contentores que vivem no namespace de rede do host. Para servicos de producao, use `renet compose`, que injeta `network_mode: host` automaticamente. Para contentores ad-hoc numa shell, passe `--network host` explicitamente. (Os daemons Hub por utilizador (`FlavorHub`, ambientes de desenvolvimento) sao a excecao: activam `bridge="docker0"` e `iptables=true` para que os contentores executados pelo utilizador tenham conectividade de saida normal.)

## Deployment

- **`rdc repo up`** monta automaticamente o volume LUKS se nao estiver montado e depois executa `up()` em todos os Rediaccfiles.
- **`rdc repo down`** executa `down()` e para o daemon Docker.
- **`rdc repo down --unmount`** tambem fecha o volume LUKS (bloqueia o armazenamento encriptado).
- **Forks** (`rdc repo fork`) criam um clone CoW (copy-on-write) com um novo GUID e networkId, em **tempo constante independentemente do tamanho do repositorio**. O reflink BTRFS duplica os metadados da imagem, nao os dados, pelo que um repositorio de 100 GB e clonado nos mesmos segundos que um de 1 GB. O fork partilha a chave de encriptacao do pai.
- **Takeover** (`rdc repo takeover --name <fork> -m <machine>`) substitui os dados do repositorio grand pelos dados de um fork. O grand mantem a sua identidade (GUID, networkId, dominios, autostart, cadeia de backup). Os dados antigos de producao sao preservados como um fork de backup. Use para: testar actualizacao no fork, verificar e depois fazer takeover para producao. Reverta com `rdc repo takeover --name <backup-fork> -m <machine>`.
- **As rotas do proxy** demoram cerca de 3 segundos a ficar activas apos o deployment. O aviso "Proxy is not running" durante `repo up` e informativo em ambientes de operacoes/desenvolvimento.
- **`rdc repo up` e `rdc repo fork --up` mostram o padrao de URL** para servicos com label `rediacc.service_port` no final do deployment. Substitua `{service}` pelo nome do servico exposto para obter o URL exacto. Os servicos sem `rediacc.service_port` (bases de dados, workers) nao obtem rotas e nao sao mostrados.

## Erros Comuns

- Usar `docker compose` em vez de `renet compose`; os contentores nao obterao isolamento de rede.
- As politicas de reinicio sao seguras; o renet remove-as automaticamente e o watchdog trata da recuperacao.
- Usar `privileged: true`; nao e necessario, o renet injeta capacidades CRIU especificas em vez disso.
- Incorporar IPs brutos em ficheiros de configuracao persistentes; use nomes de servico para conexoes, de modo a manter o isolamento de fork intacto.
- Usar `rdc term connect -c` como alternativa a comandos que falharam; reporte bugs em vez disso.
- `repo delete` realiza uma limpeza completa, incluindo IPs de loopback e unidades systemd. Execute `rdc machine prune --name <name>` para limpar residuos de eliminacoes antigas.
