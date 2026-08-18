---
title: Limites e Quotas
description: >-
  Referência para os limites, máximos e quotas que se aplicam a repositórios,
  serviços, redes e armazenamento do Rediacc.
category: Reference
order: 99
language: pt
sourceHash: "58ee35faeda9b8df"
sourceCommit: "79c84ad044d5730b6d0a20aaf7b21f21914b6bda"
---

# Limites e Quotas

Limites de implementação do Rediacc. Três são rígidos e não podem ser alterados com hardware adicional: o limite de 61 serviços por repositório (alocação de espaço de endereços de rede), o kernel 6.1 mínimo (requisitos de CRIU) e o limite de emissão de Let's Encrypt de 50 certificados wildcard por domínio registado por semana. Tudo o resto é flexível: move-se quando adiciona hardware. Compreenda a diferença antes de se comprometer com uma topologia.

---

## Serviços por Repositório

Cada repositório suporta até **61 serviços** a correr em simultâneo.

Este é um limite rígido determinado pelo espaço de endereços de rede alocado a cada repositório. Cada serviço obtém o seu próprio endereço IP privado dedicado, e o bloco de endereços de cada repositório acomoda exatamente 61 slots de serviço.

Tenha em conta: atingir 61 serviços num repositório geralmente sinaliza um problema arquitectónico, não uma restrição do Rediacc. A solução é mover sidecars e agentes de monitorização para o seu próprio repositório com um limite de isolamento separado, ou reduzir o número de processos a correr de forma independente na própria aplicação.

---

## Repositórios por Máquina

Não existe um limite rígido imposto pelo Rediacc. O limite prático depende dos recursos da sua máquina:

| Recurso | Impacto |
|----------|--------|
| Espaço em disco | Cada repositório é uma imagem de disco encriptada. Uma máquina com 1 TB de armazenamento utilizável pode conter muitos repositórios, mas o tamanho total de todas as imagens deve caber dentro do pool do datastore. |
| RAM | Cada repositório em execução inicia o seu próprio daemon Docker e contentores. O uso de memória depende das suas cargas de trabalho. |
| CPU | Operações de repositório paralelas (iniciar, cópia de segurança, fork) adicionam carga de CPU temporária. |

**As implementações típicas** correm entre 10 e 50 repositórios por máquina sem problemas. Máquinas com 32 GB+ de RAM e 500 GB+ de armazenamento correm regularmente mais de 100 repositórios.

### Limite de ID de rede ao nível do sistema

Cada repositório recebe um **ID de rede** único, um número usado para calcular o seu intervalo de endereços IP privados. Este pool é partilhado por todas as máquinas e repositórios geridos pela mesma configuração do Rediacc.

| Limite | Valor |
|-------|-------|
| IDs de rede disponíveis no total | ~261.944 |
| Âmbito | Por configuração (partilhado por todas as máquinas numa configuração) |

Quando um repositório é eliminado, o seu ID de rede é libertado e fica disponível para reutilização. O Rediacc aloca IDs sequencialmente e apenas procura intervalos libertados quando o contador avançado se aproxima do limite. Na prática, este limite nunca é atingido. Exigiria criar e rastrear centenas de milhares de repositórios ao longo da vida de uma única configuração.

---

## Forks

Não existe limite no número de forks ativos de um repositório. Cada fork é um clone completo copy-on-write com o seu próprio armazenamento encriptado, endereços de rede e daemon Docker. Os forks consomem espaço em disco proporcional aos dados escritos neles após a criação (não ao tamanho total do pai).

---

## Portas Externas

### Portas sempre ativas

As portas só são abertas quando configurar um IP público com `rdc machine infra set <machine> --public-ipv4`. Até então, não há portas abertas na máquina. Uma vez configurado:

| Porta | Protocolo | Finalidade |
|------|----------|---------|
| 80 | TCP | HTTP: gerido pelo Traefik; devolve 404 para domínios não configurados, não passa para nenhum serviço |
| 443 | TCP | HTTPS: igual ao anterior; pedidos sem rota correspondente são rejeitados na camada de proxy |
| 10000-10010 | TCP | Intervalo dinâmico para encaminhamento TCP gerido pelo Rediacc |

HTTP/HTTPS diferem das portas TCP brutas: mesmo que as portas 80 e 443 estejam abertas, cada pedido é validado pelo proxy reverso contra uma tabela de encaminhamento explícita. Sem um serviço configurado e domínio correspondente, nenhum código de aplicação é atingido e nenhum dado é exposto.

### Encaminhamento TCP/UDP por opt-in

Todas as outras portas (bases de dados, caches, message brokers, DNS, correio) estão **fechadas por predefinição** e devem ser abertas explicitamente. Isto mantém a superfície de ataque da máquina mínima.

Para expor uma porta de um serviço específico:

```yaml
labels:
  - "rediacc.tcp_ports=5432"   # expose PostgreSQL from this container
  - "rediacc.udp_ports=53"     # expose DNS from this container
```

Para abrir uma porta ao nível da máquina (disponível para todos os serviços):

```bash
rdc machine infra set server-1 --tcp-ports 25,587,993   # mail server
rdc machine infra push server-1
```

> Nunca exponha portas de base de dados ou cache externamente a não ser que tenha um requisito específico. Use rotas automáticas HTTPS para serviços web e mantenha os serviços de armazenamento internos.

---

## Datastore

O datastore é um pool de tamanho fixo criado quando uma máquina é configurada pela primeira vez. O seu tamanho não cresce automaticamente.

- **Tamanho mínimo recomendado**: 50 GB
- **Tamanho máximo**: Limitado pelo seu disco. Um único pool pode abranger um disco completo.
- **Redimensionar**: Use `rdc datastore resize` para alterar o tamanho do pool (todos os repositórios devem estar desmontados primeiro).
- **Sistema de ficheiros**: O Rediacc usa BTRFS internamente para snapshots copy-on-write e forking eficiente. Requer uma máquina a correr **Linux kernel 6.1 ou posterior** para estabilidade total em produção.

Cada repositório tem um tamanho máximo definido no momento da criação (predefinição: 10 GB). Use `rdc repo resize` para alterá-lo manualmente, ou defina uma [política de tamanho automático](/pt/docs/repositories#automatic-size-policy) para que a máquina o aumente online quando ficar cheio (limitado por um teto explícito por repositório e uma reserva de espaço livre no pool). O crescimento automático aplica-se apenas a repositórios individuais; o pool em si nunca é aumentado automaticamente.

As imagens de repositório são esparsas: um repositório apenas ocupa o pool com o que efetivamente escreveu, e o espaço libertado por eliminações retorna ao pool via [`repo trim`](/pt/docs/repositories#reclaim-space-trim) ou um auto-trim agendado. As quotas podem portanto somar mais do que o tamanho do pool, sendo o [relatório de estado do armazenamento](/pt/docs/monitoring#storage-health) a mostrar o nível de preenchimento real.

---

## Rotas HTTP

Cada serviço com a etiqueta `rediacc.service_port` obtém uma rota HTTPS automaticamente. Não existe limite no número de serviços com rotas, sujeito ao máximo de 61 serviços por repositório.

Os certificados TLS wildcard são provisionados por repositório na primeira implementação via Let's Encrypt (desafio Cloudflare DNS-01). O Let's Encrypt limita a emissão a **50 certificados por domínio registado por semana**. Como o Rediacc usa um certificado wildcard por repositório (não por serviço), uma implementação que crie mais de 50 novos repositórios numa única semana atingirá este limite.

Os forks reutilizam o certificado wildcard existente do repositório pai e não consomem nenhuma quota de certificado.

---

## Checkpoint / Restore (CRIU)

A migração ao vivo via CRIU tem as seguintes restrições:

- **Por opt-in**: Apenas os contentores com a etiqueta `rediacc.checkpoint=true` são submetidos a checkpoint. As bases de dados e serviços sem estado são excluídos por predefinição e arrancam do zero no restore.
- **Requisito de kernel**: Linux 6.1+ tanto na máquina de origem como na de destino.
- **Modo de rede**: O CRIU requer modo de rede host. Os contentores que usam configurações de rede personalizadas não podem ser submetidos a checkpoint.
- **Memória**: O tamanho dos dados do checkpoint é igual à memória residente do processo submetido a checkpoint. Conjuntos de dados grandes em memória (por exemplo, uma aplicação Node.js com 4 GB de dados em cache) produzem ficheiros de checkpoint de 4 GB.
- **Conexões TCP**: As aplicações devem tolerar perda de conexão no restore. As conexões TCP ativas **não** são preservadas. O processo restaurado vê os sockets como fechados e deve reconectar. Isto aplica-se tanto aos caminhos de restore na mesma máquina como entre máquinas.
- **O fork ao vivo na mesma máquina redireciona os endereços do repositório pai**: `rdc repo fork X --tag Y --checkpoint` seguido de `rdc repo up` funciona enquanto o pai continua em execução. Os processos restaurados carregam os endereços loopback do pai do momento do checkpoint, então o sistema os redireciona de forma transparente para os endereços próprios do fork (mesmo serviço, cópia dos dados do fork). O primeiro uso de uma conexão TCP restaurada ainda falha e o aplicativo precisa reconectar, conforme o item de TCP acima.

---

## Cópias de Segurança

| Limite | Valor |
|-------|-------|
| Snapshots por repositório | Sem limite além da sua quota de armazenamento. Cada snapshot é restaurável de forma independente, pelo que manter mais deles custa apenas espaço de armazenamento, e mais nada |
| Snapshots simultâneos de um repositório | 1. Uma segunda execução encontra o bloqueio de preparação do repositório já detido e é **ignorada**, não colocada em fila: reporta que outra execução o detém e termina. Volte a executá-la depois |
| Snapshots a frio simultâneos | 1 por datastore; um segundo `renet backup snapshot --cold` é recusado de imediato e não para nada |
| Frequência de cópia de segurança | Sem intervalo mínimo imposto; limitado pela largura de banda do seu armazenamento. Use `rdc backup strategy set <name> --bwlimit "6M"` para limitar a velocidade de envio |
| Retenção | Declarada com `rdc backup retention set` (`--keep-last`, `--keep-hourly`, `--keep-daily`, `--keep-weekly`, `--keep-monthly`, `--keep-yearly`) e imposta no servidor; `rdc backup retention clear` remove-a, e a partir daí todos os snapshots são mantidos |
| Cópia de segurança entre máquinas | Suportado; a máquina de destino deve ter espaço suficiente no datastore |

### Quota de armazenamento de backup

Os snapshots vão para o armazenamento em chunks, medido por subscrição em **bytes físicos únicos armazenados**: o que está efetivamente retido após a deduplicação, não a soma do que os seus snapshots representam logicamente. Snapshots que partilham dados, e repositórios da mesma família de forks, contam esses dados uma única vez.

| Plano | Quota | Mostrado por `rdc backup usage` como |
|------|-------|-------------------------------|
| Community | 10 GB | `10G` |
| Professional | 100 GB | `100G` |
| Business | 500 GB | `500G` |
| Enterprise | 2 TB | `2T` |

Estes são os valores predefinidos do plano. Uma subscrição pode ter a sua própria substituição, por isso verifique `rdc backup usage` em vez de presumir a linha acima.

A quota é imposta antes de qualquer dado se mover: um snapshot que a excederia é recusado quando a máquina pede permissão para enviar, e não a meio da transferência. Ficar exatamente na quota é permitido; um byte a mais é recusado. O que conta como usado inclui envios ainda em curso, pelo que duas execuções simultâneas não conseguem, ambas, encaixar-se por baixo do limite.

Exceder a quota nunca apaga nada. Interrompe novos envios, e os snapshots que já tem permanecem onde estão.

Se uma subscrição caducar, o armazenamento de backup fica só de leitura: os snapshots existentes continuam legíveis e não é possível enviar novos. Esses dados são mantidos durante **60 dias** após a caducidade, após os quais uma única limpeza os remove. Um reembolso em aberto na organização congela essa limpeza em vez de a executar.

As cópias máquina a máquina feitas com `rdc repo push` não afetam esta quota. Ficam alojadas no datastore da máquina de destino, limitadas pelo seu espaço livre.

---
## CLI e API

| Limite | Valor |
|-------|-------|
| Comandos `rdc` concorrentes contra a mesma máquina | Ilimitado (cada comando abre a sua própria conexão SSH) |
| Concorrência predefinida de arranque paralelo de repositório | 3 (ajustável com `--concurrency`) |
| Tempo de espera de conexão SSH | 30 segundos para a conexão inicial |
| Duração da sessão `rdc` | Sem tempo limite; operações de longa duração mantêm a conexão ativa |

---

## Versões de SO Suportadas

As máquinas remotas devem correr um dos seguintes para satisfazer os requisitos de kernel, sistema de ficheiros e isolamento de rede do Rediacc. Esta lista é o conjunto autoritativo testado em CI (matriz Bridge Workers) e deve permanecer sincronizada com os [Requisitos](/pt/docs/requirements):

| SO | Versão Mínima | Kernel Predefinido | Notas |
|----|-----------------|----------------|-------|
| Ubuntu | 24.04 LTS *(recomendado)* | 6.8 | AppArmor predefinido. |
| Debian | 13 (Trixie); 12 Bookworm também funciona | 6.12 (6.1 no Debian 12) | |
| Fedora | 43 | 6.12 | SELinux enforcing predefinido. |
| openSUSE Leap | 16.0 | 6.4+ | AppArmor predefinido. |
| Oracle Linux | 10 (UEK) | UEK 7+ | O UEK mantém btrfs; SELinux enforcing predefinido. |

**Kernel mínimo exigido: 6.1.** As máquinas com kernels mais antigos são rejeitadas no momento da configuração com uma mensagem de erro clara.

> **Porquê o kernel 6.1?** O Rediacc usa BTRFS para armazenamento encriptado de repositório e forking copy-on-write. O Linux 6.1 introduziu melhorias críticas no BTRFS que reduzem significativamente os tempos de montagem para grandes datastores, melhoram o desempenho de eliminação de snapshots e corrigem problemas de integridade de dados presentes em kernels anteriores. O kernel 6.1 também é necessário para os hooks de isolamento de rede ao nível do kernel que impõem o isolamento entre repositórios, reescrevendo transparentemente as chamadas `bind()` e bloqueando conexões entre repositórios.

> **Porquê não o kernel stock do Rocky Linux 10 / RHEL 10?** O kernel stock do RHEL 10 é distribuído sem o módulo `btrfs` (`modprobe btrfs` falha com "Module btrfs not found"). O backend de armazenamento encriptado do Rediacc não consegue funcionar sem btrfs. **O Oracle Linux 10 é o único alvo compatível com RHEL na lista suportada** porque usa por predefinição o Unbreakable Enterprise Kernel (UEK), que mantém btrfs. Consulte [Requisitos - Porquê o UEK?](/pt/docs/requirements) para a explicação completa.

### Matriz de funcionalidades do kernel

Leia a matriz como uma vista rápida do que cada SO testado em CI fornece de origem. Os cinco satisfazem todos os requisitos, pelo que esta é uma referência para operadores, não um critério de bloqueio.

| SO | módulo btrfs | cgroups v2 | Landlock (ABI >= 1) | hooks eBPF cgroup |
|----|--------------|------------|--------------------|-------------------|
| Ubuntu 24.04 | in-tree | hierarquia unificada | sim (5.13+) | sim |
| Debian 13 | in-tree | hierarquia unificada | sim | sim |
| Fedora 43 | in-tree | hierarquia unificada | sim | sim |
| openSUSE Leap 16.0 | in-tree | hierarquia unificada | sim | sim |
| Oracle Linux 10 (UEK) | in-tree (via UEK) | hierarquia unificada | sim | sim |
