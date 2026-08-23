---
title: "Kubernetes"
description: "Execute Kubernetes com a mentalidade de repositório da Rediacc: faça fork ou mova um cluster em execução, incluindo os seus dados, para outra máquina ou centro de dados com um curto período de corte."
category: "Guides"
tags:
  - containers
  - migration
subcategory: workloads
order: 6
language: pt
sourceHash: "22eef465dfd46ccf"
sourceCommit: "4401262fffbf29b9480dee8ecd209013e4b87f60"
---

# Kubernetes

A Rediacc traz o Kubernetes para o produto sem abdicar da mentalidade de repositório sobre a qual o resto da plataforma é construído. A afirmação diferenciadora é direta: pode **fazer fork ou mover um cluster em execução, incluindo os seus dados, para outra máquina ou centro de dados com um curto período de corte**. Isto não é migração por paragem-e-restauro, nem é magia de indisponibilidade zero. As cargas de trabalho reiniciam no destino, o corte é medido em segundos, e os dados seguem juntos.

O Kubernetes é potenciado pelo [k3s](https://k3s.io/), uma distribuição Kubernetes certificada, incorporada no renet da mesma forma que os outros binários do lado do servidor.

## O Modelo de Objetos

A Rediacc inverte a imagem habitual "o cluster envolve tudo" para que a mentalidade de repositório continue a aplicar-se:

- **Um cluster é o contentor.** Uma máquina aloja repositórios Docker (inalterado) e/ou clusters. Um cluster de nó único numa máquina mantém, ao nível do cluster, a história de "um ficheiro move todo o sistema". O estado do cluster (o diretório de dados do k3s: o seu datastore incorporado e o containerd) vive em ficheiros de imagem copy-on-write suportados pelo datastore, um por nó, com o `--data-dir` do k3s ligado dentro do mount da imagem.
- **Um repositório Kubernetes é um namespace.** `rdc repo create <repo> -m <name>` cria um repositório cuja casa de execução é o namespace Kubernetes `<repo>` dentro desse cluster.
- **Os volumes persistentes são unidades copy-on-write separadas.** Os PVs são imagens RBD no Ceph, ou pequenos ficheiros de imagem do datastore através de um provisionador de PV local do renet no backend local. Nunca são diretórios dentro de uma única imagem de cluster opaca: o sistema de ficheiros interno não tem reflinks, pelo que forks independentes por repositório exigem imagens de PV independentes.

Esta divisão é o que torna ambas as promessas fisicamente possíveis ao mesmo tempo: **forks de namespace sempre copy-on-write** (os dados de cada repositório clonam-se de forma independente) e **portabilidade de todo o cluster** (as imagens do cluster mais cada imagem de PV movem-se em conjunto).

| Conceito | Repositório Docker | Repositório Kubernetes |
|---|---|---|
| Casa de execução | Daemon Docker isolado | Namespace num cluster |
| Env injetado | `DOCKER_HOST` | `KUBECONFIG` |
| Wrapper de deploy | `renet compose` | `renet kube` |
| Unidade de dados | Uma imagem LUKS | Imagens de cluster mais imagens por PV |
| Unidade de fork | A imagem do repositório | O namespace mais os seus clones de PV |
| Clonagem de todo o lugar | (o repositório é o lugar) | `rdc cluster fork` / `rdc cluster migrate` |

## Declarar e Criar um Cluster

Um cluster é um conjunto nomeado de pools de nós numa rede privada. Declare-o primeiro na configuração, depois provisione-o.

```bash
# Declarar um cluster com pools (nada é provisionado ainda)
rdc cluster create prod --declare-only \
  --provider my-linode \
  --pool ceph:ceph:3 \
  --pool k8s:k8s-server:3

# Provisionar os membros do pool, inicializar o renet em cada um, instalar componentes (Ceph primeiro)
rdc cluster create prod
```

Os papéis de pool são `ceph`, `k8s-server`, `k8s-agent` e `hyperconverged` (adesão explícita, já que os alvos de memória do Ceph e os limiares de despejo do kubelet competem pela mesma RAM). Cada pool carrega a assimetria de hardware como tamanho e parâmetros de disco por pool: nós Ceph pesados em disco, nós Kubernetes pesados em CPU/RAM.

Os membros do pool materializam-se em `resources.machines` como `<cluster>-<pool>-<n>` com uma referência inversa, pelo que **todos os comandos `-m` existentes funcionam neles**: `rdc machine status`, `rdc term connect`, comandos de repositório e estratégias de backup veem todos os nós de cluster como máquinas comuns.

Os fornecedores de nuvem provisionam através do [OpenTofu](https://opentofu.org/), seguindo o mesmo registo `ProviderMapping` que `rdc machine provision` usa, alargado com um bloco de rede privada (VLAN ou VPC, o MTU a definir, a nomenclatura da NIC privada). O KVM local é o caminho de teste sempre disponível via `rdc ops`.

```bash
# Inspecionar clusters
rdc cluster status                 # listar todos os clusters
rdc cluster status prod     # configuração completa de um cluster

# Aumentar ou reduzir um pool (adiciona/remove máquinas, junta/drena nós)
rdc cluster scale prod --pool k8s --count 5


# Desmontar membros provisionados e remover o cluster da configuração
rdc cluster destroy prod
```

### Obter um kubeconfig

O kubeconfig nunca é guardado no seu ficheiro de configuração (é grande e roda). É obtido a pedido via SSH e colocado em cache localmente com permissões `0600`, seguindo o mesmo padrão de estado lateral que os workdirs do OpenTofu e a cache de certificados.

```bash
rdc cluster kubeconfig prod
# Imprime: export KUBECONFIG=~/.config/rediacc/kube/prod.yaml
```

## Repositórios Kubernetes

A flag de destino decide o runtime. Não há flag de tipo.

```bash
# Repositório Docker (inalterado): um daemon Docker isolado numa máquina
rdc repo create shop -m server-1 --size 10G

# Repositório Kubernetes: namespace "shop" mais o seu armazenamento, dentro de um cluster
rdc repo create shop --datastore prod --size 10G
```

Os verbos de repositório são a superfície única para o trabalho com âmbito de repositório. Através do funil de resolução de destino, praticamente todo o conjunto de comandos de repositório torna-se compatível com clusters: `fork`, `migrate`, `push`, `pull`, `up`, `down`, `resize`, `diff`, `commit`, `branch`, `checkout`, `merge`, `trim`, `cat`, `mount`, `sync`, `list`, `status` e `log` aceitam todos `--cluster`. Um destino de cluster resolve-se para o seu nó de controlo mais o contexto KUBECONFIG fixado ao namespace do repositório, o análogo de resolver uma máquina para `DOCKER_HOST` mais um diretório de trabalho.

```bash
rdc repo sync upload shop --local ./config
rdc cluster kubeconfig prod           # exportar KUBECONFIG, depois usar o kubectl diretamente
```

Os nós de cluster também se materializam em `resources.machines`, pelo que pode fazer SSH para um nó específico com o comando comum `rdc term connect <cluster>-<pool>-<n>`.

### Rediaccfile de runtime duplo

A portabilidade entre Docker e Kubernetes assenta numa convenção, não numa conversão automática de manifestos. Um repositório que fornece tanto um caminho `renet compose` como um caminho `renet kube` sob as mesmas funções `up()` e `down()` migra livremente em ambas as direções, porque as convenções do diretório de dados são idênticas. O renet injeta `DOCKER_HOST` num destino de máquina e `KUBECONFIG` num destino de cluster; `up()` lê qual está definido e despacha em conformidade.

```bash
up() {
  if [ -n "$KUBECONFIG" ]; then
    renet kube apply -f manifests/     # runtime Kubernetes
  else
    renet compose -- up -d             # runtime Docker
  fi
}
```

Um repositório que não tem o runtime de destino recebe uma recusa clara **depois** da etapa de transferência de dados: as imagens movem-se, e o passo de deploy informa que o repositório não declara um caminho Kubernetes (ou Docker), em vez de corromper o estado.

## Fazer Fork de um Repositório

O `rdc repo fork` num repositório Kubernetes copia sempre os dados, sempre instantaneamente. Não há flag `--full` nem variantes.

```bash
rdc repo fork shop --tag joseph
```

Isto cria o namespace `shop-joseph` no mesmo cluster, clona cada volume de forma copy-on-write (um clone RBD no Ceph, um reflink dos ficheiros de imagem de PV no backend local), e implementa as cargas de trabalho lá. O URL do fork está ativo instantaneamente sob o certificado wildcard do pai, pelo que não é emitido nenhum certificado ou registo DNS novo.

Escalonamento de destino:

- `--to-cluster <name>` faz fork para outro cluster existente. Mesmo backend Ceph: o clone RBD mantém-se copy-on-write. Backend diferente: a maquinaria de push move as imagens.
- `--provider <p>` provisiona um novo cluster primeiro, com especificações de pool que refletem por defeito a forma do pool do cluster de origem (as flags substituem).

Medido no laboratório de testes KVM, um fork de namespace completa-se em cerca de um a cinco segundos com a carga de trabalho do pai intocada e os dois namespaces a divergir de forma independente.

## Fazer Fork ou Mover um Cluster Inteiro

As operações de cluster inteiro residem no grupo `rdc cluster`, porque atuam sobre um objeto diferente (o lugar inteiro com todos os seus repositórios) e não podem ser expressas através de um comando que aceita um único nome de repositório. Esta é a história emblemática.

```bash
# Clonar um cluster inteiro, incluindo os dados dos seus repositórios, para um novo cluster
rdc cluster fork prod --to spare --tag staging

# Mover um cluster inteiro, incluindo os dados dos seus repositórios, para outra máquina ou centro de dados
rdc cluster migrate prod --to spare
```

Ambos coordenam um copy-on-write das imagens do cluster mais cada imagem de PV de repositório, e depois reescrevem a identidade do nó para que o clone ou o cluster relocalizado arranque de forma saudável nos seus novos endereços. Como o k3s guarda o estado do control plane no seu datastore incorporado, a própria imagem do cluster é o snapshot: a ordem de consistência é primeiro o control plane, depois os PVs, depois os agentes.

Os números honestos, medidos de ponta a ponta no laboratório de testes KVM:

| Operação | O que faz | Medido |
|---|---|---|
| Fork de namespace | Clona o namespace de um repositório mais os seus PVs no mesmo lugar | ~1 a 5 s |
| Fork de imagem RBD única | Copy-on-write de um clone de PV suportado pelo Ceph | ~5 s |
| Fork de cluster de 2 nós inteiro | Drena, faz reflink do control plane e do agente, reescreve a identidade para os novos IPs, o pai fica intocado | ~46 s |
| Migração de cluster entre máquinas | Pré-cópia a quente mais o corte de paragem-e-reinício | ~16 s de corte |

A consistência predefinida é **consistente com falha e referencialmente íntegra**: a mesma semântica de um ciclo de energia, que é o que as cargas de trabalho veem. Snapshots consistentes com a aplicação estão disponíveis quando os sistemas de ficheiros da carga de trabalho são congelados durante a cópia. Isto não é deliberadamente apresentado como indisponibilidade zero. Mais ninguém oferece "fazer fork de um cluster em execução incluindo os seus dados"; o enquadramento honesto é um corte curto e medido, em vez de um absoluto de marketing.

## Armazenamento: ceph-csi e Volumes Persistentes

O Ceph é provisionado pelo fluxo cephadm do renet no pool `ceph`, **fora** de qualquer cluster Kubernetes, e os clusters consomem-no através de manifestos ceph-csi gerados por templates do renet. Cada instância de cluster (e cada fork) recebe o seu próprio namespace RBD/RADOS, que é a primitiva de isolamento por inquilino. O armazenamento está abaixo de todos os clusters, pelo que também suporta repositórios Docker simples e o backend do datastore, e um fork de cluster clona imagens RBD abaixo do Kubernetes em vez de fazer fork do seu próprio backend de armazenamento.

No backend local (sem Ceph), um provisionador de PV local do renet suporta cada PV com um pequeno ficheiro de imagem copy-on-write no datastore, clonado por reflink no fork. Consulte [Referência do Servidor](/en/docs/server-reference) para o esquema em disco e os comandos do renet.

## Escolher uma Distribuição

A distribuição é uma abstração com uma interface pequena e real (instalar, juntar, kubeconfig, verificação de saúde, atualização, entre outros):

- **k3s** é a predefinição e a única distribuição incorporada. É Apache-2.0, certificada pela CNCF, um único binário relocalizável, e tanto o seu Traefik incorporado como o ServiceLB estão desativados em favor do proxy Rediacc. O seu `--data-dir` liga-se no arranque, o que é exatamente o que o fork e a migração de cluster precisam quando o caminho do mount da imagem muda. O k3s está assinalado como `repoEmbeddable`.
- **external** é traga-o-seu-próprio-kubeconfig. Apenas `getKubeconfig` e `healthcheck` fazem trabalho real; os verbos de ciclo de vida devolvem resultados de primeira classe "não aplicável" em vez de erros.
- **RKE2** é o terceiro backend planeado para clientes FIPS/CIS, e não faz parte desta versão.

O fork e a migração de cluster recusam-se a executar numa distribuição não `repoEmbeddable` com um erro claro em vez de corromper o estado, porque incorporar o estado do cluster em imagens do datastore exige um data-dir que se liga no arranque.

## Registo

Dois problemas de imagem distintos, duas ferramentas:

- **Dor a montante** (limites de taxa do Docker Hub, pulls recusados, offline): uma cache pull-through [zot](https://zotregistry.dev/) incorporada corre no pool de controlo com `sync.onDemand` contra múltiplos upstreams (docker.io, ghcr.io, quay.io). Está incorporada no renet da mesma forma que os outros binários, e substitui o registo de teste de ops para que cada execução a exercite.
- **Distribuição intra-cluster**: o mirror de registo incorporado do k3s permite que os nós partilhem imagens já obtidas entre si (peer-to-peer).

A ligação é transparente e sem reinício através do `certs.d/hosts.toml` do containerd e do `registries.yaml` do k3s. O armazenamento containerd por repositório dentro da imagem do cluster continua a ser a fonte de verdade que os forks e as migrações usam; o registo é uma cache à frente da internet, nunca estado.

## Redes e URLs

Os URLs de repositório Kubernetes seguem o esquema plano, com a identidade do namespace dobrada na etiqueta mais à esquerda e o cluster como a segunda etiqueta estável:

```
{service}--{repo}.{cluster}.{machine}.{base}          Repositório Kubernetes (namespace = repo)
{service}--{repo}-{tag}.{cluster}.{machine}.{base}    fork (namespace = repo-tag)
```

Todos os namespaces e todos os forks herdam o certificado wildcard e o registo DNS do pai, pelo que os URLs de fork ficam ativos instantaneamente e novos certificados só são emitidos quando um novo cluster ou repositório é criado. O router descobre serviços Kubernetes ao sondar o cluster em busca de Services anotados com `rediacc.*`, o análogo Kubernetes de ler labels do Docker. Consulte [Redes](/en/docs/networking) para o modelo de encaminhamento e [Arquitetura](/en/docs/architecture) para os backends de armazenamento.

## Atribuição

A Rediacc transporta vários binários de terceiros (k3s, zot, e os outros que o renet incorpora). Imprima as suas versões, identificadores de licença SPDX, e URLs de arquivo de código-fonte a qualquer momento:

```bash
rdc credits
rdc credits --licenses    # texto completo THIRD_PARTY_LICENSES incluído nas versões
```
